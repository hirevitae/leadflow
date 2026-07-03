"""Phase 3 — Live outbound voice calling via Twilio Programmable Voice.
Turn-based conversational IVR: Twilio speech-recognition captures the lead's reply,
the knowledge-grounded AI agent answers, spoken back via ElevenLabs (fallback: Twilio <Say>).
Supports full-call recording and human handoff via <Dial>. Credentials come from the
DB-backed Integration Settings (never .env).
"""
import os
import re
import uuid
import base64
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial

from integrations_admin import get_creds, is_configured
from ai_agents import retrieve, _agent_system_prompt, _llm

logger = logging.getLogger(__name__)

MAX_AI_TURNS = 10
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel" — multilingual
SPEECH_LANG = {"english": "en-US", "hindi": "hi-IN"}
SAY_LANG = {"english": "en-US", "hindi": "hi-IN"}

HANDOFF_WORDS = ["human", "person", "agent", "representative", "someone", "manager",
                 "real person", "talk to a", "speak to a", "इंसान", "व्यक्ति", "एजेंट", "आदमी"]
END_WORDS = ["bye", "goodbye", "not interested", "no thanks", "no thank you",
             "hang up", "stop calling", "अलविदा", "नहीं चाहिए", "बाद में"]


class VoiceCallIn(BaseModel):
    language: str = "english"
    agent_id: Optional[str] = None


def _public_base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return f"{proto}://{host}"


def _matches(text: str, words) -> bool:
    t = (text or "").lower()
    return any(w in t for w in words)


def _to_e164(phone: str, default_cc: str) -> str:
    """Normalize a phone number to E.164. Uses default_cc (e.g. '+91') when no country code."""
    p = (phone or "").strip()
    if p.startswith("+"):
        return "+" + re.sub(r"\D", "", p[1:])
    digits = re.sub(r"\D", "", p)
    if digits.startswith("00"):
        return "+" + digits[2:]
    cc = re.sub(r"\D", "", default_cc or "")
    if not cc:
        return "+" + digits
    # Avoid double-prefixing if the number already includes the country code.
    if digits.startswith(cc) and len(digits) > 10:
        return "+" + digits
    digits = digits.lstrip("0")  # drop domestic trunk prefix before adding country code
    return "+" + cc + digits


def _transcript_text(transcript) -> str:
    return "\n".join(f"{t['speaker']}: {t['text']}" for t in transcript)


def build_voice_router(db, get_current_user, add_activity):
    router = APIRouter(tags=["voice"])

    async def _twilio_client():
        c = await get_creds(db, "twilio")
        return Client(c["account_sid"], c["auth_token"]), c

    async def _tts_url(base: str, text: str, language: str) -> Optional[str]:
        """Generate ElevenLabs audio, store it, return a public URL. None on failure."""
        el = await get_creds(db, "elevenlabs")
        key = el.get("api_key")
        if not key:
            return None
        voice_id = el.get("voice_id") or DEFAULT_VOICE_ID
        try:
            async with httpx.AsyncClient(timeout=25) as cli:
                r = await cli.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": key, "content-type": "application/json"},
                    json={"text": text, "model_id": "eleven_multilingual_v2"},
                )
            if r.status_code != 200:
                logger.warning(f"ElevenLabs TTS failed {r.status_code}: {r.text[:200]}")
                return None
            aid = uuid.uuid4().hex
            await db.voice_audio.insert_one({
                "id": aid, "data": base64.b64encode(r.content).decode("ascii"),
                "created_at": datetime.now(timezone.utc).isoformat()})
            return f"{base}/api/voice/audio/{aid}"
        except Exception as e:
            logger.warning(f"ElevenLabs TTS exception: {e}")
            return None

    async def _speak(resp, base: str, text: str, language: str):
        url = await _tts_url(base, text, language)
        if url:
            resp.play(url)
        else:
            resp.say(text, language=SAY_LANG.get(language, "en-US"))

    def _gather(resp, base: str, cid: str, language: str):
        g = Gather(input="speech", action=f"{base}/api/voice/twiml/turn?cid={cid}",
                   method="POST", speech_timeout="auto", language=SPEECH_LANG.get(language, "en-US"))
        resp.append(g)
        # If the caller says nothing, re-prompt once then hang up.
        resp.redirect(f"{base}/api/voice/twiml/turn?cid={cid}&silent=1", method="POST")

    async def _agent_reply(agent: dict, transcript, user_text: str, language: str, cid: str) -> str:
        from emergentintegrations.llm.chat import UserMessage
        sources = await retrieve(db, agent["id"], user_text, k=5) if agent else []
        context = "\n---\n".join(f"[{s['title']}] {s['content']}" for s in sources)
        sys = _agent_system_prompt(agent, context) if agent else (
            f"You are a helpful phone assistant. Respond only in {language}.")
        prompt = (
            f"This is a live phone call. Respond in {language} with ONE short, natural spoken "
            f"reply (max 2 sentences). Do not use any speaker labels or markdown.\n\n"
            f"Conversation so far:\n{_transcript_text(transcript)}\n\n"
            f"The customer just said: \"{user_text}\"\n\nYour reply:")
        try:
            reply = str(await _llm(sys, f"call-{cid}").send_message(UserMessage(text=prompt))).strip()
            return re.sub(r"^(AI|Assistant|Agent)\s*:\s*", "", reply)
        except Exception as e:
            logger.error(f"agent reply failed: {e}")
            return "I'm sorry, could you please repeat that?"

    async def _finalize(cid: str, agent, transcript, status="completed"):
        from emergentintegrations.llm.chat import UserMessage
        summary, outcome, score = "AI voice call completed.", "interested", None
        if transcript:
            try:
                import json
                sys = "You analyze sales call transcripts. Return STRICT JSON only."
                prompt = (f"Transcript:\n{_transcript_text(transcript)}\n\n"
                          'Return JSON: {"summary":"1-2 sentences","outcome":"interested|not_interested|callback|enrolled",'
                          '"interest_score":0-100}')
                raw = str(await _llm(sys, f"sum-{cid}").send_message(UserMessage(text=prompt)))
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    d = json.loads(m.group(0))
                    summary = d.get("summary") or summary
                    outcome = d.get("outcome") or outcome
                    score = d.get("interest_score")
            except Exception as e:
                logger.warning(f"summary failed: {e}")
        await db.calls.update_one({"id": cid}, {"$set": {
            "status": status, "summary": summary, "outcome": outcome,
            "duration_sec": max(30, len(transcript) * 12),
            "finalized": True, "updated_at": datetime.now(timezone.utc).isoformat()}})
        return summary, outcome, score

    # ---------------- Initiate (authenticated) ----------------
    @router.post("/api/leads/{lead_id}/voice-call")
    async def initiate_voice_call(lead_id: str, payload: VoiceCallIn, request: Request,
                                  user=Depends(get_current_user)):
        lead = await db.leads.find_one({"id": lead_id})
        if not lead:
            raise HTTPException(404, "Lead not found")
        if not lead.get("phone"):
            raise HTTPException(400, "Lead has no phone number")
        if not await is_configured(db, "twilio"):
            raise HTTPException(400, "Twilio is not configured. Add credentials in Settings → Integrations.")
        agent = await db.ai_agents.find_one({"id": payload.agent_id}) if payload.agent_id else None
        base = _public_base(request)
        cid = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": cid, "lead_id": lead_id, "language": payload.language,
            "agent_id": (agent or {}).get("id"), "agent_name": (agent or {}).get("name", "AI Assistant"),
            "mode": "live", "live": True, "status": "initiating", "transcript": [],
            "created_at": now,
        }
        await db.calls.insert_one(dict(doc))
        try:
            client, creds = await _twilio_client()
            to_number = _to_e164(lead["phone"], creds.get("default_country_code") or "+91")
            call = await asyncio.to_thread(
                lambda: client.calls.create(
                    to=to_number, from_=creds["phone_number"],
                    url=f"{base}/api/voice/twiml/entry?cid={cid}", method="POST",
                    status_callback=f"{base}/api/voice/status?cid={cid}", status_callback_method="POST",
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                    record=True,
                    recording_status_callback=f"{base}/api/voice/recording?cid={cid}",
                    recording_status_callback_method="POST",
                    recording_status_callback_event=["completed"],
                ))
        except Exception as e:
            msg = str(e)
            await db.calls.update_one({"id": cid}, {"$set": {"status": "failed", "summary": msg[:300], "live": False}})
            logger.error(f"Twilio call create failed: {e}")
            raise HTTPException(400, f"Could not place call: {msg[:250]}")
        await db.calls.update_one({"id": cid}, {"$set": {"call_sid": call.sid, "status": "ringing", "to_number": to_number}})
        await add_activity(lead_id, "ai_call", f"Live AI call started ({payload.language})", user)
        doc.update({"call_sid": call.sid, "status": "ringing"})
        return doc

    # ---------------- TwiML: entry (public webhook) ----------------
    @router.post("/api/voice/twiml/entry")
    async def twiml_entry(request: Request, cid: str):
        call = await db.calls.find_one({"id": cid})
        agent = await db.ai_agents.find_one({"id": call.get("agent_id")}) if call and call.get("agent_id") else None
        language = (call or {}).get("language", "english")
        base = _public_base(request)
        greeting = (agent or {}).get("greeting") or (
            "Hello! This is an AI assistant calling to follow up on your enquiry. How can I help you today?")
        resp = VoiceResponse()
        await db.calls.update_one({"id": cid}, {
            "$set": {"status": "in-progress"},
            "$push": {"transcript": {"speaker": "AI", "text": greeting}}})
        await _speak(resp, base, greeting, language)
        _gather(resp, base, cid, language)
        return Response(content=str(resp), media_type="application/xml")

    # ---------------- TwiML: conversational turn (public webhook) ----------------
    @router.post("/api/voice/twiml/turn")
    async def twiml_turn(request: Request, cid: str, silent: Optional[str] = None):
        form = await request.form()
        speech = (form.get("SpeechResult") or "").strip()
        call = await db.calls.find_one({"id": cid})
        agent = await db.ai_agents.find_one({"id": call.get("agent_id")}) if call and call.get("agent_id") else None
        language = (call or {}).get("language", "english")
        transcript = (call or {}).get("transcript", [])
        base = _public_base(request)
        resp = VoiceResponse()
        creds = await get_creds(db, "twilio")

        if silent and not speech:
            await _speak(resp, base, "Sorry, I didn't catch that. Could you please repeat?", language)
            _gather(resp, base, cid, language)
            return Response(content=str(resp), media_type="application/xml")

        if speech:
            transcript = transcript + [{"speaker": "Customer", "text": speech}]
            await db.calls.update_one({"id": cid}, {"$push": {"transcript": {"speaker": "Customer", "text": speech}}})

        # Human handoff
        if speech and _matches(speech, HANDOFF_WORDS):
            if creds.get("handoff_number"):
                line = "Sure, connecting you to a member of our team now. Please hold."
                await _speak(resp, base, line, language)
                await db.calls.update_one({"id": cid}, {
                    "$push": {"transcript": {"speaker": "AI", "text": line}},
                    "$set": {"handoff": True, "outcome": "callback"}})
                dial = Dial(record="record-from-answer")
                dial.number(creds["handoff_number"])
                resp.append(dial)
                return Response(content=str(resp), media_type="application/xml")
            line = ("I'm sorry, I can't transfer you to a colleague right now, but I'll "
                    "arrange for someone to call you back shortly. Is there anything else I can help with?")
            await _speak(resp, base, line, language)
            await db.calls.update_one({"id": cid}, {
                "$push": {"transcript": {"speaker": "AI", "text": line}},
                "$set": {"handoff_requested": True, "outcome": "callback"}})
            _gather(resp, base, cid, language)
            return Response(content=str(resp), media_type="application/xml")

        # End of conversation
        ai_turns = sum(1 for t in transcript if t["speaker"] == "AI")
        if (speech and _matches(speech, END_WORDS)) or ai_turns >= MAX_AI_TURNS:
            closing = (agent or {}).get("closing") or "Thank you for your time. Have a great day!"
            await _speak(resp, base, closing, language)
            resp.hangup()
            transcript = transcript + [{"speaker": "AI", "text": closing}]
            await db.calls.update_one({"id": cid}, {"$push": {"transcript": {"speaker": "AI", "text": closing}}})
            await _finalize(cid, agent, transcript)
            return Response(content=str(resp), media_type="application/xml")

        # Normal AI reply
        reply = await _agent_reply(agent, transcript, speech or "(silence)", language, cid)
        await db.calls.update_one({"id": cid}, {"$push": {"transcript": {"speaker": "AI", "text": reply}}})
        await _speak(resp, base, reply, language)
        _gather(resp, base, cid, language)
        return Response(content=str(resp), media_type="application/xml")

    # ---------------- Status callback (public webhook) ----------------
    @router.post("/api/voice/status")
    async def voice_status(request: Request, cid: str):
        form = await request.form()
        status = form.get("CallStatus", "")
        call = await db.calls.find_one({"id": cid})
        if call and status in ("completed", "busy", "no-answer", "failed", "canceled"):
            transcript = call.get("transcript", [])
            map_out = {"busy": "not_interested", "no-answer": "callback",
                       "failed": "not_interested", "canceled": "callback"}
            if not call.get("finalized") and transcript:
                # A conversation happened — generate an LLM summary regardless of final status.
                agent = await db.ai_agents.find_one({"id": call.get("agent_id")}) if call.get("agent_id") else None
                summary, outcome, score = await _finalize(cid, agent, transcript, status=status)
                if score is not None:
                    await db.leads.update_one({"id": call["lead_id"]}, {"$set": {"interest_score": score}})
                if status != "completed":
                    await db.calls.update_one({"id": cid}, {"$set": {"outcome": map_out.get(status, "callback")}})
            elif not call.get("finalized"):
                # No conversation (e.g. not answered) — record a status-based summary.
                await db.calls.update_one({"id": cid}, {"$set": {
                    "status": status, "outcome": map_out.get(status, "callback"),
                    "summary": f"Call {status.replace('-', ' ')} — no conversation took place."}})
            await db.calls.update_one({"id": cid}, {"$set": {"live": False}})
        return Response(status_code=204)

    # ---------------- Recording callback (public webhook) ----------------
    @router.post("/api/voice/recording")
    async def voice_recording(request: Request, cid: str):
        form = await request.form()
        url = form.get("RecordingUrl")
        if url:
            await db.calls.update_one({"id": cid}, {"$set": {
                "recording_url": url + ".mp3", "recording_sid": form.get("RecordingSid"),
                "recording_duration": form.get("RecordingDuration")}})
        return Response(status_code=204)

    # ---------------- Serve ElevenLabs audio to Twilio (public) ----------------
    @router.get("/api/voice/audio/{audio_id}")
    async def voice_audio(audio_id: str):
        doc = await db.voice_audio.find_one({"id": audio_id})
        if not doc:
            raise HTTPException(404, "Audio not found")
        return Response(content=base64.b64decode(doc["data"]), media_type="audio/mpeg")

    # ---------------- Recording playback proxy (authenticated) ----------------
    @router.get("/api/voice/calls/{cid}/recording")
    async def recording_proxy(cid: str, user=Depends(get_current_user)):
        call = await db.calls.find_one({"id": cid})
        if not call or not call.get("recording_url"):
            raise HTTPException(404, "Recording not available")
        creds = await get_creds(db, "twilio")
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(call["recording_url"], auth=(creds["account_sid"], creds["auth_token"]))
        if r.status_code != 200:
            raise HTTPException(502, "Could not fetch recording")
        return Response(content=r.content, media_type="audio/mpeg")

    return router
