"""Meta WhatsApp + Facebook + Instagram integration + AI classifier.
All endpoints are environment-driven. Keys can be left blank — endpoints will
return an explanatory error until WHATSAPP_ACCESS_TOKEN etc. are filled in."""
import os
import uuid
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse

GRAPH = "https://graph.facebook.com/v19.0"
FAQ_KEYWORDS = {
    "fees": ["fee", "fees", "cost", "price", "शुल्क", "फीस", "कीमत"],
    "demo": ["demo", "free class", "trial", "डेमो", "मुफ्त"],
    "syllabus": ["syllabus", "curriculum", "topics", "सिलेबस", "पाठ्यक्रम"],
    "timing": ["time", "schedule", "timing", "duration", "समय", "अवधि"],
}
FAQ_ANSWERS = {
    "fees": {"english": "Our course fees start at INR 25,000 with easy EMI options. Want me to share the full fee structure?",
             "hindi": "हमारे कोर्स की फीस INR 25,000 से शुरू होती है, आसान EMI विकल्प के साथ। क्या मैं पूरी फीस संरचना भेजूँ?"},
    "demo": {"english": "Yes! We offer a free 1-hour demo class. Which day works best for you — tomorrow or this weekend?",
             "hindi": "जी हाँ! हम 1 घंटे की मुफ्त डेमो क्लास देते हैं। कौन सा दिन ठीक रहेगा — कल या इस वीकेंड?"},
    "syllabus": {"english": "Our syllabus covers fundamentals to advanced projects. I'll share the full PDF — what's your email?",
                 "hindi": "हमारा सिलेबस बेसिक से एडवांस्ड प्रोजेक्ट्स तक है। पूरा PDF भेज दूँ — आपका ईमेल बताएँ?"},
    "timing": {"english": "Classes run for 12 weeks, 1 hour daily. We have morning (7am) and evening (7pm) batches.",
              "hindi": "क्लासेस 12 हफ्ते, रोज़ 1 घंटा। सुबह 7 बजे और शाम 7 बजे के बैच उपलब्ध हैं।"},
}


def _detect_lang(text: str) -> str:
    # naive: any Devanagari char → hindi
    return "hindi" if any("\u0900" <= c <= "\u097f" for c in (text or "")) else "english"


def _detect_faq(text: str) -> str | None:
    low = (text or "").lower()
    for cat, kws in FAQ_KEYWORDS.items():
        if any(k in low for k in kws):
            return cat
    return None


async def _send_whatsapp_text(phone: str, body: str, pid: str = None, tok: str = None, ver: str = None) -> dict:
    pid = pid or os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    tok = tok or os.environ.get("WHATSAPP_ACCESS_TOKEN")
    if not pid or not tok:
        raise HTTPException(503, "WhatsApp not configured. Set it in Settings → Integrations")
    base = f"https://graph.facebook.com/{ver}" if ver else GRAPH
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{base}/{pid}/messages",
            headers={"Authorization": f"Bearer {tok}"},
            json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": body}})
        r.raise_for_status()
        return r.json()


async def _send_ig_dm(ig_user_id: str, body: str) -> dict:
    igb = os.environ.get("IG_BUSINESS_ACCOUNT_ID"); tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not igb or not tok:
        raise HTTPException(503, "Instagram not configured")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{igb}/messages",
            params={"access_token": tok},
            json={"recipient": {"id": ig_user_id}, "message": {"text": body}})
        r.raise_for_status(); return r.json()


async def _send_fb_dm(psid: str, body: str) -> dict:
    tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not tok: raise HTTPException(503, "Facebook not configured")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/me/messages",
            params={"access_token": tok},
            json={"recipient": {"id": psid}, "message": {"text": body}})
        r.raise_for_status(); return r.json()


async def _reply_fb_comment(comment_id: str, body: str) -> dict:
    tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not tok: raise HTTPException(503, "Facebook not configured")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{GRAPH}/{comment_id}/comments",
            params={"message": body, "access_token": tok})
        r.raise_for_status(); return r.json()


async def ai_classify_and_draft(history: list, incoming: str, lead_name: str = "", course: str = "") -> dict:
    """Return {category, draft_reply, language, confidence, is_faq}.
    Uses Emergent LLM key via emergentintegrations. Falls back to FAQ-only on failure."""
    lang = _detect_lang(incoming)
    faq = _detect_faq(incoming)
    if faq:
        return {"category": faq, "draft_reply": FAQ_ANSWERS[faq][lang],
                "language": lang, "confidence": 0.9, "is_faq": True}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key: raise RuntimeError("no key")
        sys_msg = (f"You are a friendly admissions counsellor for an online education academy. "
                   f"Student name: {lead_name or 'unknown'}. Course of interest: {course or 'unknown'}. "
                   f"Reply in {lang}. Keep replies under 60 words, warm, and end with a question to keep the conversation moving.")
        ctx = "\n".join([f"{m.get('direction','in')}: {m.get('body','')}" for m in history[-6:]])
        chat = LlmChat(api_key=key, session_id=f"lead-{uuid.uuid4()}", system_message=sys_msg).with_model("anthropic", "claude-sonnet-4-6")
        reply = await chat.send_message(UserMessage(text=f"Previous messages:\n{ctx}\n\nStudent just said: {incoming}\n\nDraft a reply."))
        return {"category": "general", "draft_reply": str(reply).strip(),
                "language": lang, "confidence": 0.7, "is_faq": False}
    except Exception as e:
        return {"category": "general",
                "draft_reply": ("Thanks for your message! A counsellor will get back to you shortly."
                                if lang == "english" else
                                "आपके संदेश के लिए धन्यवाद! हमारी टीम जल्दी ही आपसे संपर्क करेगी।"),
                "language": lang, "confidence": 0.3, "is_faq": False, "error": str(e)}


def build_meta_router(db, get_current_user, add_activity):
    router = APIRouter(prefix="/api/meta", tags=["meta"])

    @router.get("/webhook", response_class=PlainTextResponse)
    async def verify_webhook(request: Request):
        p = request.query_params
        vt = os.environ.get("META_VERIFY_TOKEN", "")
        if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == vt and p.get("hub.challenge"):
            return p.get("hub.challenge")
        raise HTTPException(403, "Verification failed")

    @router.post("/webhook")
    async def receive_webhook(request: Request):
        body = await request.json()
        await db.webhook_logs.insert_one({"payload": body, "received_at": datetime.now(timezone.utc).isoformat()})
        obj = body.get("object")
        # Parse incoming text + sender across channels
        msgs_to_process = []
        for entry in body.get("entry", []):
            if obj == "whatsapp_business_account":
                for ch in entry.get("changes", []):
                    v = ch.get("value", {})
                    for m in v.get("messages", []) or []:
                        if m.get("type") == "text":
                            contact = (v.get("contacts") or [{}])[0]
                            msgs_to_process.append({
                                "channel": "whatsapp", "sender_id": m.get("from"),
                                "sender_name": contact.get("profile", {}).get("name", ""),
                                "body": m.get("text", {}).get("body", ""), "message_id": m.get("id"),
                            })
            elif obj == "page":
                for ch in entry.get("changes", []):
                    v = ch.get("value", {})
                    if ch.get("field") == "feed" and v.get("item") == "comment":
                        msgs_to_process.append({
                            "channel": "facebook_comment", "sender_id": (v.get("from") or {}).get("id"),
                            "sender_name": (v.get("from") or {}).get("name", ""),
                            "body": v.get("message", ""), "message_id": v.get("comment_id"),
                        })
                # Messenger DMs come in 'messaging' array
                for m in entry.get("messaging", []) or []:
                    if m.get("message", {}).get("text"):
                        msgs_to_process.append({
                            "channel": "facebook_dm", "sender_id": m.get("sender", {}).get("id"),
                            "sender_name": "", "body": m["message"]["text"],
                            "message_id": m["message"].get("mid"),
                        })
            elif obj == "instagram":
                for ch in entry.get("changes", []):
                    v = ch.get("value", {})
                    if ch.get("field") == "comments":
                        msgs_to_process.append({
                            "channel": "instagram_comment", "sender_id": (v.get("from") or {}).get("id"),
                            "sender_name": (v.get("from") or {}).get("username", ""),
                            "body": v.get("text", ""), "message_id": v.get("id"),
                        })
                for m in entry.get("messaging", []) or []:
                    if m.get("message", {}).get("text"):
                        msgs_to_process.append({
                            "channel": "instagram_dm", "sender_id": m.get("sender", {}).get("id"),
                            "sender_name": "", "body": m["message"]["text"],
                            "message_id": m["message"].get("mid"),
                        })

        mode = os.environ.get("AI_REPLY_MODE", "draft").lower()  # "draft" | "auto_faq" | "auto"
        for m in msgs_to_process:
            # Find or create lead by sender_id+channel
            lead = await db.leads.find_one({"social_id": m["sender_id"], "channel": m["channel"]})
            if not lead:
                lead_id = str(uuid.uuid4()); now = datetime.now(timezone.utc).isoformat()
                lead = {
                    "id": lead_id, "name": m.get("sender_name") or f"{m['channel']} user",
                    "phone": m["sender_id"] if m["channel"] == "whatsapp" else "",
                    "social_id": m["sender_id"], "channel": m["channel"],
                    "source": m["channel"], "language": _detect_lang(m["body"]),
                    "priority": "medium", "stage": "new",
                    "created_at": now, "updated_at": now, "last_activity_at": now,
                }
                await db.leads.insert_one(lead)
            # Store inbound message
            await db.messages.insert_one({
                "id": str(uuid.uuid4()), "lead_id": lead["id"], "direction": "inbound",
                "channel": m["channel"], "body": m["body"], "external_id": m["message_id"],
                "status": "received", "created_at": datetime.now(timezone.utc).isoformat(),
            })
            # AI draft
            history = await db.messages.find({"lead_id": lead["id"]}).sort("created_at", -1).to_list(10)
            ai = await ai_classify_and_draft(list(reversed(history)), m["body"],
                                             lead.get("name", ""), lead.get("course", ""))
            draft_doc = {
                "id": str(uuid.uuid4()), "lead_id": lead["id"], "channel": m["channel"],
                "incoming_body": m["body"], "incoming_id": m["message_id"],
                "category": ai["category"], "is_faq": ai["is_faq"],
                "draft_reply": ai["draft_reply"], "language": ai["language"],
                "confidence": ai["confidence"], "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Auto-send when in auto_faq mode & FAQ matched, or full auto
            send_now = (mode == "auto") or (mode == "auto_faq" and ai["is_faq"])
            if send_now:
                try:
                    if m["channel"] == "whatsapp":
                        await _send_whatsapp_text(m["sender_id"], ai["draft_reply"])
                    elif m["channel"] == "instagram_dm":
                        await _send_ig_dm(m["sender_id"], ai["draft_reply"])
                    elif m["channel"] == "facebook_dm":
                        await _send_fb_dm(m["sender_id"], ai["draft_reply"])
                    elif m["channel"] == "facebook_comment":
                        await _reply_fb_comment(m["message_id"], ai["draft_reply"])
                    draft_doc["status"] = "auto_sent"
                    await db.messages.insert_one({
                        "id": str(uuid.uuid4()), "lead_id": lead["id"], "direction": "outbound",
                        "channel": m["channel"], "body": ai["draft_reply"],
                        "status": "sent (AI auto)", "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as e:
                    draft_doc["status"] = "pending"; draft_doc["send_error"] = str(e)
            await db.ai_drafts.insert_one(draft_doc)
        return {"status": "ok", "processed": len(msgs_to_process)}

    @router.get("/drafts")
    async def list_drafts(user=Depends(get_current_user)):
        docs = await db.ai_drafts.find({"status": "pending"}).sort("created_at", -1).to_list(200)
        out = []
        for d in docs:
            d.pop("_id", None)
            lead = await db.leads.find_one({"id": d["lead_id"]}, {"_id": 0, "name": 1, "phone": 1, "channel": 1, "course": 1})
            d["lead"] = lead or {}
            out.append(d)
        return out

    @router.post("/drafts/{draft_id}/approve")
    async def approve_draft(draft_id: str, payload: dict, user=Depends(get_current_user)):
        d = await db.ai_drafts.find_one({"id": draft_id})
        if not d: raise HTTPException(404, "Draft not found")
        body = payload.get("body") or d["draft_reply"]
        lead = await db.leads.find_one({"id": d["lead_id"]})
        ch = d["channel"]
        try:
            if ch == "whatsapp":
                await _send_whatsapp_text(lead["social_id"] or lead.get("phone", ""), body)
            elif ch == "instagram_dm":
                await _send_ig_dm(lead["social_id"], body)
            elif ch == "facebook_dm":
                await _send_fb_dm(lead["social_id"], body)
            elif ch == "facebook_comment" or ch == "instagram_comment":
                await _reply_fb_comment(d["incoming_id"], body)
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(500, f"Send failed: {e}")
        await db.messages.insert_one({
            "id": str(uuid.uuid4()), "lead_id": d["lead_id"], "direction": "outbound",
            "channel": ch, "body": body, "status": "sent (approved)",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.ai_drafts.update_one({"id": draft_id}, {"$set": {"status": "approved", "sent_body": body}})
        await add_activity(d["lead_id"], f"{ch}_sent", f"Reply sent on {ch}: {body[:60]}", user)
        return {"ok": True}

    @router.post("/drafts/{draft_id}/reject")
    async def reject_draft(draft_id: str, user=Depends(get_current_user)):
        await db.ai_drafts.update_one({"id": draft_id}, {"$set": {"status": "rejected"}})
        return {"ok": True}

    @router.get("/status")
    async def status(user=Depends(get_current_user)):
        return {
            "whatsapp": bool(os.environ.get("WHATSAPP_ACCESS_TOKEN") and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")),
            "facebook": bool(os.environ.get("FB_PAGE_ACCESS_TOKEN")),
            "instagram": bool(os.environ.get("IG_BUSINESS_ACCOUNT_ID") and os.environ.get("FB_PAGE_ACCESS_TOKEN")),
            "ai": bool(os.environ.get("EMERGENT_LLM_KEY")),
            "mode": os.environ.get("AI_REPLY_MODE", "draft"),
            "webhook_url": "{your_backend_url}/api/meta/webhook",
            "verify_token_set": bool(os.environ.get("META_VERIFY_TOKEN")),
        }

    return router
