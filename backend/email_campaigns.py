"""Email Outreach module (Phase A) — templates, campaigns, queue-based sending engine,
Resend webhook tracking, suppression/unsubscribe, and campaign analytics.
Reuses the existing FastAPI/Mongo stack and the DB-backed Resend credentials.
"""
import os
import re
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import resend
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

logger = logging.getLogger(__name__)

TEMPLATE_CATEGORIES = [
    "Admissions", "Promotions", "Offers", "Events", "Follow-up", "Payment Reminder",
    "Counselling", "Welcome", "Cold Outreach", "Newsletter", "Festival Wishes",
    "Announcements", "Transactional",
]
MERGE_FIELDS = [
    {"field": "{{name}}", "label": "Lead name"},
    {"field": "{{course}}", "label": "Course"},
    {"field": "{{email}}", "label": "Email"},
    {"field": "{{phone}}", "label": "Phone"},
    {"field": "{{stage}}", "label": "Pipeline stage"},
    {"field": "{{unsubscribe}}", "label": "Unsubscribe link"},
]
TICK_SECONDS = 5


class TemplateIn(BaseModel):
    name: str
    category: str = "Newsletter"
    subject: str = ""
    html: str = ""


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    archived: Optional[bool] = None
    is_favorite: Optional[bool] = None


class Schedule(BaseModel):
    mode: str = "now"           # now | later
    send_at: Optional[str] = None  # ISO datetime
    timezone: str = "Asia/Kolkata"


class Throttle(BaseModel):
    per_minute: int = 30
    business_hours_only: bool = False


class CampaignIn(BaseModel):
    name: str
    template_id: Optional[str] = None
    subject: str
    html: str
    stages: List[str] = []
    schedule: Schedule = Schedule()
    throttle: Throttle = Throttle()


class TestSendIn(BaseModel):
    to: str
    subject: str
    html: str


def _now():
    return datetime.now(timezone.utc)


def _render(html: str, lead: dict, base: str, campaign_id: str) -> str:
    unsub = f"{base}/api/email/unsubscribe?c={campaign_id}&l={lead['id']}"
    repl = {
        "name": lead.get("name") or "there",
        "course": lead.get("course") or "your course",
        "email": lead.get("email") or "",
        "phone": lead.get("phone") or "",
        "stage": lead.get("stage") or "",
        "unsubscribe": f'<a href="{unsub}">unsubscribe</a>',
    }
    out = html
    for k, v in repl.items():
        out = out.replace("{{" + k + "}}", str(v)).replace("{" + k + "}", str(v))
    if "unsubscribe" not in out.lower():
        out += (f'<div style="margin-top:24px;font-size:12px;color:#888;text-align:center">'
                f'If you no longer wish to receive these emails, <a href="{unsub}">unsubscribe</a>.</div>')
    return out


def _empty_stats():
    return {k: 0 for k in ["total", "queued", "sent", "delivered", "opened",
                           "clicked", "bounced", "complained", "unsubscribed", "failed"]}


def build_email_router(db, get_current_user, add_activity, get_creds):
    router = APIRouter(prefix="/api/email", tags=["email"])
    SYS = {"id": "system", "name": "Email Engine"}

    # ---------------- Templates ----------------
    @router.get("/template-categories")
    async def categories(user=Depends(get_current_user)):
        return TEMPLATE_CATEGORIES

    @router.get("/merge-fields")
    async def merge_fields(user=Depends(get_current_user)):
        return MERGE_FIELDS

    @router.get("/templates")
    async def list_templates(category: Optional[str] = None, archived: bool = False,
                             user=Depends(get_current_user)):
        q = {"archived": archived}
        if category:
            q["category"] = category
        docs = await db.email_templates.find(q).sort("updated_at", -1).to_list(1000)
        for d in docs:
            d.pop("_id", None)
        return docs

    @router.post("/templates")
    async def create_template(payload: TemplateIn, user=Depends(get_current_user)):
        now = _now().isoformat()
        doc = {"id": str(uuid.uuid4()), **payload.model_dump(), "archived": False,
               "is_favorite": False, "created_by": user["name"],
               "created_at": now, "updated_at": now}
        await db.email_templates.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @router.get("/templates/{tid}")
    async def get_template(tid: str, user=Depends(get_current_user)):
        d = await db.email_templates.find_one({"id": tid})
        if not d:
            raise HTTPException(404, "Template not found")
        d.pop("_id", None)
        return d

    @router.put("/templates/{tid}")
    async def update_template(tid: str, payload: TemplateUpdate, user=Depends(get_current_user)):
        update = {k: v for k, v in payload.model_dump().items() if v is not None}
        update["updated_at"] = _now().isoformat()
        d = await db.email_templates.find_one_and_update({"id": tid}, {"$set": update}, return_document=True)
        if not d:
            raise HTTPException(404, "Template not found")
        d.pop("_id", None)
        return d

    @router.post("/templates/{tid}/duplicate")
    async def duplicate_template(tid: str, user=Depends(get_current_user)):
        d = await db.email_templates.find_one({"id": tid})
        if not d:
            raise HTTPException(404, "Template not found")
        now = _now().isoformat()
        new = {**d, "id": str(uuid.uuid4()), "name": d["name"] + " (copy)",
               "is_favorite": False, "created_at": now, "updated_at": now}
        new.pop("_id", None)
        await db.email_templates.insert_one(dict(new))
        new.pop("_id", None)
        return new

    @router.delete("/templates/{tid}")
    async def delete_template(tid: str, user=Depends(get_current_user)):
        await db.email_templates.delete_one({"id": tid})
        return {"ok": True}

    # ---------------- Audience preview ----------------
    @router.post("/audience/preview")
    async def audience_preview(body: dict, user=Depends(get_current_user)):
        stages = body.get("stages") or []
        leads = await db.leads.find({"stage": {"$in": stages}}).to_list(10000)
        suppressed = {s["email"] for s in await db.email_suppression.find({}).to_list(10000)}
        with_email = [l for l in leads if l.get("email") and l["email"] not in suppressed]
        seen, unique = set(), []
        for l in with_email:
            if l["email"].lower() in seen:
                continue
            seen.add(l["email"].lower()); unique.append(l)
        return {"total_leads": len(leads), "with_email": len(with_email),
                "deliverable": len(unique), "suppressed_or_dupe": len(with_email) - len(unique),
                "sample": [{"name": l.get("name"), "email": l["email"]} for l in unique[:5]]}

    # ---------------- Campaigns ----------------
    @router.get("/campaigns")
    async def list_campaigns(user=Depends(get_current_user)):
        docs = await db.email_campaigns.find({}).sort("created_at", -1).to_list(500)
        for d in docs:
            d.pop("_id", None)
        return docs

    @router.post("/campaigns")
    async def create_campaign(payload: CampaignIn, request: Request, user=Depends(get_current_user)):
        creds = await get_creds(db, "email")
        if not creds.get("api_key"):
            raise HTTPException(400, "Email not configured. Add Resend in Settings → Integrations")
        base = _public_base(request)
        await db.app_config.update_one({"key": "public_base_url"},
                                       {"$set": {"key": "public_base_url", "value": base}}, upsert=True)
        leads = await db.leads.find({"stage": {"$in": payload.stages}}).to_list(10000)
        suppressed = {s["email"].lower() for s in await db.email_suppression.find({}).to_list(10000)}
        seen, recipients = set(), []
        for l in leads:
            e = (l.get("email") or "").lower()
            if not e or e in suppressed or e in seen:
                continue
            seen.add(e); recipients.append(l)
        if not recipients:
            raise HTTPException(400, "No deliverable recipients (no email / all suppressed) in selected stages")

        cid = str(uuid.uuid4())
        now = _now()
        is_later = payload.schedule.mode == "later" and payload.schedule.send_at
        try:
            send_at = datetime.fromisoformat(payload.schedule.send_at.replace("Z", "+00:00")) if is_later else now
        except Exception:
            send_at = now
        stats = _empty_stats()
        stats["total"] = stats["queued"] = len(recipients)
        campaign = {
            "id": cid, "name": payload.name, "template_id": payload.template_id,
            "subject": payload.subject, "html": payload.html, "stages": payload.stages,
            "schedule": payload.schedule.model_dump(), "throttle": payload.throttle.model_dump(),
            "status": "scheduled" if is_later else "sending", "stats": stats,
            "created_by": user["name"], "created_at": now.isoformat(),
            "send_at": send_at.astimezone(timezone.utc).isoformat(),
            "started_at": None, "completed_at": None,
        }
        await db.email_campaigns.insert_one(dict(campaign))
        queue_docs = [{
            "id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": l["id"],
            "to": l["email"], "status": "pending", "attempts": 0,
            "scheduled_for": send_at.astimezone(timezone.utc).isoformat(),
            "provider_id": None, "error": None,
            "created_at": now.isoformat(), "sent_at": None,
        } for l in recipients]
        if queue_docs:
            await db.email_queue.insert_many(queue_docs)
        campaign.pop("_id", None)
        return campaign

    @router.get("/campaigns/{cid}")
    async def get_campaign(cid: str, user=Depends(get_current_user)):
        c = await db.email_campaigns.find_one({"id": cid})
        if not c:
            raise HTTPException(404, "Campaign not found")
        c.pop("_id", None)
        events = await db.email_events.find({"campaign_id": cid}).sort("created_at", -1).to_list(50)
        for e in events:
            e.pop("_id", None)
        return {**c, "recent_events": events}

    @router.post("/campaigns/{cid}/pause")
    async def pause_campaign(cid: str, user=Depends(get_current_user)):
        await db.email_campaigns.update_one({"id": cid, "status": {"$in": ["sending", "scheduled"]}},
                                            {"$set": {"status": "paused"}})
        return {"ok": True}

    @router.post("/campaigns/{cid}/resume")
    async def resume_campaign(cid: str, user=Depends(get_current_user)):
        await db.email_campaigns.update_one({"id": cid, "status": "paused"},
                                            {"$set": {"status": "sending"}})
        return {"ok": True}

    @router.post("/campaigns/{cid}/cancel")
    async def cancel_campaign(cid: str, user=Depends(get_current_user)):
        await db.email_campaigns.update_one({"id": cid}, {"$set": {"status": "canceled", "completed_at": _now().isoformat()}})
        await db.email_queue.update_many({"campaign_id": cid, "status": "pending"}, {"$set": {"status": "canceled"}})
        return {"ok": True}

    @router.get("/campaigns/{cid}/analytics")
    async def campaign_analytics(cid: str, user=Depends(get_current_user)):
        c = await db.email_campaigns.find_one({"id": cid})
        if not c:
            raise HTTPException(404, "Campaign not found")
        s = c.get("stats", _empty_stats())
        sent = max(s.get("sent", 0), 1)
        rates = {
            "delivery_rate": round(s.get("delivered", 0) / sent * 100, 1),
            "open_rate": round(s.get("opened", 0) / sent * 100, 1),
            "click_rate": round(s.get("clicked", 0) / sent * 100, 1),
            "bounce_rate": round(s.get("bounced", 0) / sent * 100, 1),
        }
        events = await db.email_events.find({"campaign_id": cid, "type": "clicked"}).to_list(5000)
        buckets = {}
        for e in events:
            hr = (e.get("created_at") or "")[:13]
            buckets[hr] = buckets.get(hr, 0) + 1
        clicks_over_time = [{"t": k, "n": v} for k, v in sorted(buckets.items())]
        return {"stats": s, "rates": rates, "clicks_over_time": clicks_over_time}

    @router.post("/campaigns/test")
    async def test_send(payload: TestSendIn, user=Depends(get_current_user)):
        creds = await get_creds(db, "email")
        if not creds.get("api_key"):
            raise HTTPException(400, "Email not configured")
        resend.api_key = creds["api_key"]
        sender = creds.get("sender_email") or "onboarding@resend.dev"
        try:
            await asyncio.to_thread(resend.Emails.send,
                {"from": sender, "to": [payload.to], "subject": payload.subject, "html": payload.html})
        except Exception as e:
            raise HTTPException(400, f"Test send failed: {e}")
        return {"ok": True}

    # ---------------- Suppression / Unsubscribe ----------------
    @router.get("/suppression")
    async def list_suppression(user=Depends(get_current_user)):
        docs = await db.email_suppression.find({}).sort("created_at", -1).to_list(2000)
        for d in docs:
            d.pop("_id", None)
        return docs

    @router.get("/unsubscribe", response_class=HTMLResponse)
    async def unsubscribe(c: str = "", l: str = ""):
        lead = await db.leads.find_one({"id": l})
        email = (lead or {}).get("email")
        if email:
            await db.email_suppression.update_one({"email": email},
                {"$set": {"email": email, "reason": "unsubscribed", "created_at": _now().isoformat()}}, upsert=True)
            await db.email_campaigns.update_one({"id": c}, {"$inc": {"stats.unsubscribed": 1}})
            await _record_event(c, l, email, "unsubscribed")
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            "<h2>You're unsubscribed</h2><p>You will no longer receive marketing emails from us.</p></body></html>")

    # ---------------- Resend webhook (public) ----------------
    @router.post("/webhook/resend")
    async def resend_webhook(request: Request):
        try:
            payload = await request.json()
        except Exception:
            return {"ok": True}
        etype = (payload.get("type") or "").replace("email.", "")
        data = payload.get("data") or {}
        provider_id = data.get("email_id") or data.get("id")
        if not provider_id:
            return {"ok": True}
        item = await db.email_queue.find_one({"provider_id": provider_id})
        if not item:
            return {"ok": True}
        cid, lid, email = item["campaign_id"], item["lead_id"], item["to"]
        stat_key = {"delivered": "delivered", "opened": "opened", "clicked": "clicked",
                    "bounced": "bounced", "complained": "complained"}.get(etype)
        if stat_key:
            await db.email_campaigns.update_one({"id": cid}, {"$inc": {f"stats.{stat_key}": 1}})
            url = (data.get("click") or {}).get("link") if etype == "clicked" else None
            await _record_event(cid, lid, email, stat_key, url)
            if etype in ("bounced", "complained"):
                await db.email_suppression.update_one({"email": email},
                    {"$set": {"email": email, "reason": etype, "created_at": _now().isoformat()}}, upsert=True)
        return {"ok": True}

    async def _record_event(cid, lid, email, etype, url=None):
        await db.email_events.insert_one({
            "id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": lid, "email": email,
            "type": etype, "url": url, "created_at": _now().isoformat()})
        labels = {"delivered": "Email delivered", "opened": "Email opened", "clicked": "Email link clicked",
                  "bounced": "Email bounced", "complained": "Marked as spam", "unsubscribed": "Unsubscribed"}
        try:
            await add_activity(lid, f"email_{etype}", labels.get(etype, etype), SYS)
        except Exception:
            pass

    # ---------------- Background sending worker ----------------
    def _in_business_hours(tz_name: str) -> bool:
        try:
            hour = datetime.now(ZoneInfo(tz_name)).hour if ZoneInfo else _now().hour
        except Exception:
            hour = _now().hour
        return 9 <= hour < 20

    async def _send_one(item, campaign, creds, sender, base):
        lead = await db.leads.find_one({"id": item["lead_id"]})
        if not lead:
            await db.email_queue.update_one({"id": item["id"]}, {"$set": {"status": "failed", "error": "lead gone"}})
            await db.email_campaigns.update_one({"id": campaign["id"]}, {"$inc": {"stats.failed": 1, "stats.queued": -1}})
            return
        subject = _render(campaign["subject"], lead, base, campaign["id"])
        html = _render(campaign["html"], lead, base, campaign["id"])
        try:
            res = await asyncio.to_thread(resend.Emails.send,
                {"from": sender, "to": [item["to"]], "subject": subject, "html": html,
                 "headers": {"List-Unsubscribe": f"<{base}/api/email/unsubscribe?c={campaign['id']}&l={lead['id']}>"}})
            pid = (res or {}).get("id")
            await db.email_queue.update_one({"id": item["id"]},
                {"$set": {"status": "sent", "provider_id": pid, "sent_at": _now().isoformat()}})
            await db.email_campaigns.update_one({"id": campaign["id"]},
                {"$inc": {"stats.sent": 1, "stats.queued": -1}})
            await add_activity(lead["id"], "email_sent", f"Campaign: {campaign['name'][:50]}", SYS)
        except Exception as e:
            attempts = item.get("attempts", 0) + 1
            if attempts >= 3:
                await db.email_queue.update_one({"id": item["id"]},
                    {"$set": {"status": "failed", "attempts": attempts, "error": str(e)[:250]}})
                await db.email_campaigns.update_one({"id": campaign["id"]},
                    {"$inc": {"stats.failed": 1, "stats.queued": -1}})
            else:
                await db.email_queue.update_one({"id": item["id"]},
                    {"$set": {"attempts": attempts, "error": str(e)[:250]}})
            logger.error(f"Email send failed (attempt {attempts}): {e}")

    async def worker_loop():
        base = os.environ.get("PUBLIC_BASE_URL", "")
        while True:
            try:
                await asyncio.sleep(TICK_SECONDS)
                now_iso = _now().isoformat()
                # Flip due scheduled campaigns to sending
                await db.email_campaigns.update_many(
                    {"status": "scheduled", "send_at": {"$lte": now_iso}}, {"$set": {"status": "sending"}})
                active = await db.email_campaigns.find({"status": "sending"}).to_list(100)
                if not active:
                    continue
                creds = await get_creds(db, "email")
                if not creds.get("api_key"):
                    continue
                resend.api_key = creds["api_key"]
                sender = creds.get("sender_email") or "onboarding@resend.dev"
                if not base:
                    base = await _stored_base(db)
                for campaign in active:
                    thr = campaign.get("throttle", {})
                    if thr.get("business_hours_only") and not _in_business_hours(campaign.get("schedule", {}).get("timezone", "Asia/Kolkata")):
                        continue
                    per_tick = max(1, int(thr.get("per_minute", 30) * TICK_SECONDS / 60))
                    pending = await db.email_queue.find(
                        {"campaign_id": campaign["id"], "status": "pending",
                         "scheduled_for": {"$lte": now_iso}}).limit(per_tick).to_list(per_tick)
                    if not pending:
                        remaining = await db.email_queue.count_documents(
                            {"campaign_id": campaign["id"], "status": "pending"})
                        if remaining == 0:
                            await db.email_campaigns.update_one({"id": campaign["id"]},
                                {"$set": {"status": "completed", "completed_at": now_iso}})
                        continue
                    if not campaign.get("started_at"):
                        await db.email_campaigns.update_one({"id": campaign["id"]}, {"$set": {"started_at": now_iso}})
                    for item in pending:
                        # Skip if campaign was paused mid-tick
                        fresh = await db.email_campaigns.find_one({"id": campaign["id"]}, {"status": 1})
                        if not fresh or fresh.get("status") != "sending":
                            break
                        await _send_one(item, campaign, creds, sender, base)
            except Exception as e:
                logger.error(f"Email worker loop error: {e}")

    router.start_worker = lambda: asyncio.create_task(worker_loop())
    return router


def _public_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


async def _stored_base(db) -> str:
    cfg = await db.app_config.find_one({"key": "public_base_url"})
    return (cfg or {}).get("value", "")
