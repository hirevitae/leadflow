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


class Variant(BaseModel):
    id: Optional[str] = None
    name: str = "Variant"
    template_id: Optional[str] = None
    subject: str
    html: str


class ABConfig(BaseModel):
    enabled: bool = False
    variants: List[Variant] = []
    test_percent: int = 30
    winner_metric: str = "click_rate"   # click_rate | open_rate
    winner_after_minutes: int = 60


class Recurrence(BaseModel):
    enabled: bool = False
    frequency: str = "weekly"           # daily | weekly | monthly | custom
    custom_dates: List[str] = []
    until: Optional[str] = None


class CampaignIn(BaseModel):
    name: str
    template_id: Optional[str] = None
    subject: str
    html: str
    stages: List[str] = []
    schedule: Schedule = Schedule()
    throttle: Throttle = Throttle()
    ab: ABConfig = ABConfig()
    recurrence: Recurrence = Recurrence()


class TestSendIn(BaseModel):
    to: str
    subject: str
    html: str


TRIGGERS = ["lead_created", "stage_changed", "ai_call_completed", "email_opened",
            "whatsapp_sent", "payment_pending", "birthday"]


class AutomationIn(BaseModel):
    name: str
    trigger: str
    template_id: str
    stage: Optional[str] = None      # optional filter for stage_changed
    enabled: bool = True


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


def _add_month(dt: datetime) -> datetime:
    m = dt.month + 1
    y = dt.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    day = min(dt.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.replace(year=y, month=m, day=day)


def _next_run(base: datetime, rec: dict):
    freq = rec.get("frequency", "weekly")
    if freq == "custom":
        future = sorted([d for d in (rec.get("custom_dates") or [])])
        for d in future:
            try:
                dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
                if dt > base:
                    return dt.astimezone(timezone.utc)
            except Exception:
                continue
        return None
    delta = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}.get(freq)
    nxt = _add_month(base) if freq == "monthly" else base + (delta or timedelta(days=7))
    until = rec.get("until")
    if until:
        try:
            if nxt > datetime.fromisoformat(until.replace("Z", "+00:00")).astimezone(timezone.utc):
                return None
        except Exception:
            pass
    return nxt


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
        current = await db.email_templates.find_one({"id": tid})
        if not current:
            raise HTTPException(404, "Template not found")
        update = {k: v for k, v in payload.model_dump().items() if v is not None}
        # Snapshot the current content as a version before overwriting (only on content changes).
        if any(k in update for k in ("subject", "html", "name", "category")):
            vcount = await db.email_template_versions.count_documents({"template_id": tid})
            await db.email_template_versions.insert_one({
                "id": str(uuid.uuid4()), "template_id": tid, "version_no": vcount + 1,
                "name": current.get("name"), "category": current.get("category"),
                "subject": current.get("subject"), "html": current.get("html"),
                "created_by": user["name"], "created_at": _now().isoformat()})
        update["updated_at"] = _now().isoformat()
        d = await db.email_templates.find_one_and_update({"id": tid}, {"$set": update}, return_document=True)
        d.pop("_id", None)
        return d

    @router.get("/templates/{tid}/versions")
    async def list_versions(tid: str, user=Depends(get_current_user)):
        docs = await db.email_template_versions.find({"template_id": tid}).sort("version_no", -1).to_list(200)
        for d in docs:
            d.pop("_id", None)
        return docs

    @router.post("/templates/{tid}/versions/{vid}/restore")
    async def restore_version(tid: str, vid: str, user=Depends(get_current_user)):
        v = await db.email_template_versions.find_one({"id": vid, "template_id": tid})
        if not v:
            raise HTTPException(404, "Version not found")
        current = await db.email_templates.find_one({"id": tid})
        vcount = await db.email_template_versions.count_documents({"template_id": tid})
        await db.email_template_versions.insert_one({
            "id": str(uuid.uuid4()), "template_id": tid, "version_no": vcount + 1,
            "name": current.get("name"), "category": current.get("category"),
            "subject": current.get("subject"), "html": current.get("html"),
            "created_by": f"{user['name']} (pre-restore)", "created_at": _now().isoformat()})
        d = await db.email_templates.find_one_and_update({"id": tid},
            {"$set": {"subject": v["subject"], "html": v["html"], "name": v["name"],
                      "category": v["category"], "updated_at": _now().isoformat()}}, return_document=True)
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
        send_iso = send_at.astimezone(timezone.utc).isoformat()
        import random
        random.shuffle(recipients)

        ab = payload.ab.model_dump()
        ab_on = ab.get("enabled") and len(ab.get("variants", [])) >= 2
        stats = _empty_stats()
        stats["total"] = stats["queued"] = len(recipients)

        campaign = {
            "id": cid, "name": payload.name, "template_id": payload.template_id,
            "subject": payload.subject, "html": payload.html, "stages": payload.stages,
            "schedule": payload.schedule.model_dump(), "throttle": payload.throttle.model_dump(),
            "recurrence": payload.recurrence.model_dump(),
            "status": "scheduled" if is_later else "sending", "stats": stats,
            "created_by": user["name"], "created_at": now.isoformat(),
            "send_at": send_iso, "started_at": None, "completed_at": None,
            "ab": {"enabled": False},
        }
        queue_docs = []
        if ab_on:
            variants = ab["variants"]
            for v in variants:
                v["id"] = v.get("id") or str(uuid.uuid4())
                v["stats"] = {"sent": 0, "opened": 0, "clicked": 0}
            test_count = max(len(variants), (len(recipients) * ab["test_percent"]) // 100)
            test_count = min(test_count, len(recipients))
            test, holdback = recipients[:test_count], recipients[test_count:]
            winner_at = (now + timedelta(minutes=ab["winner_after_minutes"])).isoformat()
            campaign["ab"] = {"enabled": True, "variants": variants, "test_percent": ab["test_percent"],
                              "winner_metric": ab["winner_metric"], "winner_at": winner_at,
                              "winner_variant_id": None, "holdback": len(holdback)}
            campaign["status"] = "scheduled" if is_later else "testing"
            for i, l in enumerate(test):
                v = variants[i % len(variants)]
                queue_docs.append({"id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": l["id"],
                    "to": l["email"], "status": "pending", "attempts": 0, "scheduled_for": send_iso,
                    "variant_id": v["id"], "subject": v["subject"], "html": v["html"],
                    "provider_id": None, "error": None, "created_at": now.isoformat(), "sent_at": None})
            for l in holdback:
                queue_docs.append({"id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": l["id"],
                    "to": l["email"], "status": "holdback", "attempts": 0, "scheduled_for": send_iso,
                    "variant_id": None, "subject": None, "html": None,
                    "provider_id": None, "error": None, "created_at": now.isoformat(), "sent_at": None})
        else:
            queue_docs = [{"id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": l["id"],
                "to": l["email"], "status": "pending", "attempts": 0, "scheduled_for": send_iso,
                "variant_id": None, "subject": None, "html": None,
                "provider_id": None, "error": None, "created_at": now.isoformat(), "sent_at": None} for l in recipients]

        await db.email_campaigns.insert_one(dict(campaign))
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

        # Advanced analytics: device/browser breakdown + opens heatmap (weekday × hour)
        opens = await db.email_events.find({"campaign_id": cid, "type": {"$in": ["opened", "clicked"]}}).to_list(10000)
        device_breakdown, browser_breakdown = {}, {}
        heatmap = [[0] * 24 for _ in range(7)]
        for e in opens:
            dev = e.get("device") or "Unknown"
            device_breakdown[dev] = device_breakdown.get(dev, 0) + 1
            browser_breakdown[_browser_from_ua(e.get("user_agent", ""))] = browser_breakdown.get(_browser_from_ua(e.get("user_agent", "")), 0) + 1
            try:
                dt = datetime.fromisoformat((e.get("created_at") or "").replace("Z", "+00:00"))
                heatmap[dt.weekday()][dt.hour] += 1
            except Exception:
                pass
        return {"stats": s, "rates": rates, "clicks_over_time": clicks_over_time,
                "device_breakdown": device_breakdown, "browser_breakdown": browser_breakdown,
                "heatmap": heatmap}

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
            inc = {f"stats.{stat_key}": 1}
            filt = None
            if item.get("variant_id") and stat_key in ("opened", "clicked"):
                inc[f"ab.variants.$[v].stats.{stat_key}"] = 1
                filt = [{"v.id": item["variant_id"]}]
            await db.email_campaigns.update_one({"id": cid}, {"$inc": inc}, array_filters=filt)
            url = (data.get("click") or {}).get("link") if etype == "clicked" else None
            await _record_event(cid, lid, email, stat_key, url, data)
            if etype in ("bounced", "complained"):
                await db.email_suppression.update_one({"email": email},
                    {"$set": {"email": email, "reason": etype, "created_at": _now().isoformat()}}, upsert=True)
        return {"ok": True}

    async def _record_event(cid, lid, email, etype, url=None, data=None):
        d = data or {}
        ua = d.get("user_agent") or (d.get("open") or {}).get("userAgent") or (d.get("click") or {}).get("userAgent") or ""
        ip = d.get("ip_address") or (d.get("open") or {}).get("ipAddress") or (d.get("click") or {}).get("ipAddress") or ""
        await db.email_events.insert_one({
            "id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": lid, "email": email,
            "type": etype, "url": url, "user_agent": ua, "ip": ip,
            "device": _device_from_ua(ua), "created_at": _now().isoformat()})
        labels = {"delivered": "Email delivered", "opened": "Email opened", "clicked": "Email link clicked",
                  "bounced": "Email bounced", "complained": "Marked as spam", "unsubscribed": "Unsubscribed"}
        try:
            await add_activity(lid, f"email_{etype}", labels.get(etype, etype), SYS)
        except Exception:
            pass

    # ---------------- Automations (Phase C) ----------------
    @router.get("/triggers")
    async def triggers(user=Depends(get_current_user)):
        return TRIGGERS

    @router.get("/automations")
    async def list_automations(user=Depends(get_current_user)):
        docs = await db.email_automations.find({}).sort("created_at", -1).to_list(500)
        for d in docs:
            d.pop("_id", None)
        return docs

    @router.post("/automations")
    async def create_automation(payload: AutomationIn, user=Depends(get_current_user)):
        if payload.trigger not in TRIGGERS:
            raise HTTPException(400, "Unknown trigger")
        now = _now().isoformat()
        doc = {"id": str(uuid.uuid4()), **payload.model_dump(), "runs": 0,
               "created_by": user["name"], "created_at": now}
        await db.email_automations.insert_one(dict(doc))
        doc.pop("_id", None)
        return doc

    @router.put("/automations/{aid}")
    async def update_automation(aid: str, payload: AutomationIn, user=Depends(get_current_user)):
        d = await db.email_automations.find_one_and_update({"id": aid},
            {"$set": payload.model_dump()}, return_document=True)
        if not d:
            raise HTTPException(404, "Automation not found")
        d.pop("_id", None)
        return d

    @router.delete("/automations/{aid}")
    async def delete_automation(aid: str, user=Depends(get_current_user)):
        await db.email_automations.delete_one({"id": aid})
        return {"ok": True}

    async def fire_automations(trigger: str, lead: dict):
        """Called on CRM events — sends matching automation template emails to the lead."""
        try:
            if not lead or not lead.get("email"):
                return
            if await db.email_suppression.find_one({"email": lead["email"]}):
                return
            rules = await db.email_automations.find({"trigger": trigger, "enabled": True}).to_list(100)
            if not rules:
                return
            creds = await get_creds(db, "email")
            if not creds.get("api_key"):
                return
            resend.api_key = creds["api_key"]
            sender = creds.get("sender_email") or "onboarding@resend.dev"
            base = await _stored_base(db)
            for rule in rules:
                if rule.get("stage") and lead.get("stage") != rule["stage"]:
                    continue
                tpl = await db.email_templates.find_one({"id": rule["template_id"]})
                if not tpl:
                    continue
                subject = _render(tpl["subject"], lead, base, f"auto-{rule['id']}")
                html = _render(tpl["html"], lead, base, f"auto-{rule['id']}")
                try:
                    await asyncio.to_thread(resend.Emails.send,
                        {"from": sender, "to": [lead["email"]], "subject": subject, "html": html})
                    await db.email_automations.update_one({"id": rule["id"]}, {"$inc": {"runs": 1}})
                    await add_activity(lead["id"], "email_sent", f"Automation '{rule['name']}' ({trigger})", SYS)
                except Exception as e:
                    logger.error(f"Automation send failed ({rule['id']}): {e}")
        except Exception as e:
            logger.error(f"fire_automations error: {e}")

    router.fire = fire_automations

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
        # Compliance: skip if the recipient unsubscribed / was suppressed after the campaign was built.
        if await db.email_suppression.find_one({"email": item["to"]}):
            await db.email_queue.update_one({"id": item["id"]}, {"$set": {"status": "skipped", "error": "suppressed"}})
            await db.email_campaigns.update_one({"id": campaign["id"]}, {"$inc": {"stats.queued": -1}})
            return
        subject = _render(item.get("subject") or campaign["subject"], lead, base, campaign["id"])
        html = _render(item.get("html") or campaign["html"], lead, base, campaign["id"])
        try:
            res = await asyncio.to_thread(resend.Emails.send,
                {"from": sender, "to": [item["to"]], "subject": subject, "html": html,
                 "headers": {"List-Unsubscribe": f"<{base}/api/email/unsubscribe?c={campaign['id']}&l={lead['id']}>"}})
            pid = (res or {}).get("id")
            await db.email_queue.update_one({"id": item["id"]},
                {"$set": {"status": "sent", "provider_id": pid, "sent_at": _now().isoformat()}})
            inc = {"stats.sent": 1, "stats.queued": -1}
            filt = None
            if item.get("variant_id"):
                inc["ab.variants.$[v].stats.sent"] = 1
                filt = [{"v.id": item["variant_id"]}]
            await db.email_campaigns.update_one({"id": campaign["id"]}, {"$inc": inc},
                                                array_filters=filt)
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

    async def _spawn_recurrence(campaign, now_iso):
        rec = campaign.get("recurrence", {})
        if not rec.get("enabled"):
            return
        try:
            base_dt = datetime.fromisoformat(campaign["send_at"].replace("Z", "+00:00"))
        except Exception:
            base_dt = _now()
        nxt = _next_run(base_dt, rec)
        if not nxt:
            return
        # Resolve a fresh audience at spawn time
        leads = await db.leads.find({"stage": {"$in": campaign["stages"]}}).to_list(10000)
        suppressed = {s["email"].lower() for s in await db.email_suppression.find({}).to_list(10000)}
        seen, recipients = set(), []
        for l in leads:
            e = (l.get("email") or "").lower()
            if not e or e in suppressed or e in seen:
                continue
            seen.add(e); recipients.append(l)
        if not recipients:
            return
        # Use the winning variant content if the parent ran A/B, else base content.
        ab = campaign.get("ab", {})
        subject, html = campaign["subject"], campaign["html"]
        if ab.get("enabled") and ab.get("winner_variant_id"):
            win = next((v for v in ab.get("variants", []) if v["id"] == ab["winner_variant_id"]), None)
            if win:
                subject, html = win["subject"], win["html"]
        cid = str(uuid.uuid4())
        nxt_iso = nxt.astimezone(timezone.utc).isoformat()
        stats = _empty_stats(); stats["total"] = stats["queued"] = len(recipients)
        child = {"id": cid, "name": campaign["name"], "template_id": campaign.get("template_id"),
                 "subject": subject, "html": html, "stages": campaign["stages"],
                 "schedule": {**campaign.get("schedule", {}), "mode": "later", "send_at": nxt_iso},
                 "throttle": campaign.get("throttle", {}), "recurrence": rec,
                 "status": "scheduled", "stats": stats, "created_by": campaign["created_by"],
                 "created_at": now_iso, "send_at": nxt_iso, "started_at": None, "completed_at": None,
                 "ab": {"enabled": False}, "is_recurrence_child_of": campaign["id"]}
        await db.email_campaigns.insert_one(dict(child))
        await db.email_queue.insert_many([{
            "id": str(uuid.uuid4()), "campaign_id": cid, "lead_id": l["id"], "to": l["email"],
            "status": "pending", "attempts": 0, "scheduled_for": nxt_iso, "variant_id": None,
            "subject": None, "html": None, "provider_id": None, "error": None,
            "created_at": now_iso, "sent_at": None} for l in recipients])
        logger.info(f"Recurrence: spawned next run of '{campaign['name']}' at {nxt_iso}")

    async def _handle_idle(campaign, now_iso):
        cid = campaign["id"]
        if await db.email_queue.count_documents({"campaign_id": cid, "status": "pending"}) > 0:
            return
        ab = campaign.get("ab", {})
        if campaign["status"] == "testing" and ab.get("enabled"):
            if now_iso < ab.get("winner_at", ""):
                return  # still inside the A/B test window
            variants = ab.get("variants", [])

            def _score(v):
                st = v.get("stats", {}); sent = max(st.get("sent", 0), 1)
                if ab.get("winner_metric") == "open_rate":
                    return st.get("opened", 0) / sent
                return st.get("clicked", 0) / sent
            winner = max(variants, key=_score) if variants else None
            holdback = await db.email_queue.count_documents({"campaign_id": cid, "status": "holdback"})
            if winner and holdback:
                await db.email_queue.update_many({"campaign_id": cid, "status": "holdback"},
                    {"$set": {"status": "pending", "variant_id": winner["id"],
                              "subject": winner["subject"], "html": winner["html"]}})
                await db.email_campaigns.update_one({"id": cid},
                    {"$set": {"status": "sending", "ab.winner_variant_id": winner["id"],
                              "ab.winner_name": winner.get("name")}})
            else:
                await db.email_campaigns.update_one({"id": cid},
                    {"$set": {"status": "completed", "completed_at": now_iso,
                              "ab.winner_variant_id": (winner or {}).get("id"),
                              "ab.winner_name": (winner or {}).get("name")}})
                await _spawn_recurrence(campaign, now_iso)
            return
        await db.email_campaigns.update_one({"id": cid},
            {"$set": {"status": "completed", "completed_at": now_iso}})
        await _spawn_recurrence(campaign, now_iso)

    async def worker_loop():
        base = os.environ.get("PUBLIC_BASE_URL", "")
        while True:
            try:
                await asyncio.sleep(TICK_SECONDS)
                now_iso = _now().isoformat()
                await db.email_campaigns.update_many(
                    {"status": "scheduled", "send_at": {"$lte": now_iso}}, {"$set": {"status": "sending"}})
                active = await db.email_campaigns.find({"status": {"$in": ["sending", "testing"]}}).to_list(100)
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
                        await _handle_idle(campaign, now_iso)
                        continue
                    if not campaign.get("started_at"):
                        await db.email_campaigns.update_one({"id": campaign["id"]}, {"$set": {"started_at": now_iso}})
                    for item in pending:
                        fresh = await db.email_campaigns.find_one({"id": campaign["id"]}, {"status": 1})
                        if not fresh or fresh.get("status") not in ("sending", "testing"):
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


def _device_from_ua(ua: str) -> str:
    u = (ua or "").lower()
    if any(x in u for x in ["iphone", "android", "mobile", "ipod"]):
        return "Mobile"
    if any(x in u for x in ["ipad", "tablet"]):
        return "Tablet"
    if u:
        return "Desktop"
    return "Unknown"


def _browser_from_ua(ua: str) -> str:
    u = (ua or "").lower()
    if "edg" in u:
        return "Edge"
    if "chrome" in u or "crios" in u:
        return "Chrome"
    if "firefox" in u:
        return "Firefox"
    if "safari" in u:
        return "Safari"
    if "outlook" in u:
        return "Outlook"
    if "gmail" in u or "googleimageproxy" in u:
        return "Gmail"
    return "Other" if u else "Unknown"


async def _stored_base(db) -> str:
    cfg = await db.app_config.find_one({"key": "public_base_url"})
    return (cfg or {}).get("value", "")
