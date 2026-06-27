"""Integration Settings Management Module.
DB-backed, encrypted, admin-managed third-party credentials.
Config priority: Database -> backend/.env -> empty. .env values auto-migrate to DB on first startup.
Secrets are Fernet-encrypted at rest and always masked in API responses.
"""
import os
import time
import base64
import hashlib
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
GRAPH_DEFAULT_VERSION = "v23.0"


# ---------------- Provider schema ----------------
PROVIDERS = {
    "whatsapp": {
        "label": "WhatsApp Cloud API",
        "description": "Send WhatsApp messages to leads via Meta Cloud API.",
        "fields": [
            {"key": "phone_number_id", "label": "Phone Number ID", "secret": False},
            {"key": "business_account_id", "label": "Business Account ID", "secret": False},
            {"key": "access_token", "label": "Access Token", "secret": True},
            {"key": "verify_token", "label": "Verify Token", "secret": True},
            {"key": "api_version", "label": "API Version", "secret": False, "default": GRAPH_DEFAULT_VERSION},
        ],
        "required": ["phone_number_id", "access_token"],
    },
    "facebook": {
        "label": "Facebook Page",
        "description": "Publish posts and reply to messages on your Facebook Page.",
        "fields": [
            {"key": "page_id", "label": "Page ID", "secret": False},
            {"key": "page_access_token", "label": "Page Access Token", "secret": True},
        ],
        "required": ["page_id", "page_access_token"],
    },
    "instagram": {
        "label": "Instagram",
        "description": "Publish and message from your Instagram Business account.",
        "fields": [
            {"key": "ig_business_account_id", "label": "Instagram Business Account ID", "secret": False},
            {"key": "fb_page_access_token", "label": "Facebook Page Access Token", "secret": True},
        ],
        "required": ["ig_business_account_id", "fb_page_access_token"],
    },
    "email": {
        "label": "Email (Resend)",
        "description": "Send transactional emails to leads through Resend.",
        "fields": [
            {"key": "api_key", "label": "API Key", "secret": True},
            {"key": "sender_email", "label": "Sender Email", "secret": False},
        ],
        "required": ["api_key", "sender_email"],
    },
    "ai": {
        "label": "AI Provider",
        "description": "LLM provider for AI drafting, summaries and content.",
        "fields": [
            {"key": "provider", "label": "Provider", "secret": False, "default": "Emergent",
             "options": ["Emergent", "OpenAI", "Gemini", "Claude", "Groq"]},
            {"key": "api_key", "label": "API Key", "secret": True},
            {"key": "model_name", "label": "Model Name", "secret": False, "default": "gpt-4o-mini"},
        ],
        "required": ["api_key"],
    },
}

# Map provider/key -> legacy .env variable for one-time migration & fallback
ENV_MAP = {
    ("whatsapp", "phone_number_id"): "WHATSAPP_PHONE_NUMBER_ID",
    ("whatsapp", "access_token"): "WHATSAPP_ACCESS_TOKEN",
    ("whatsapp", "verify_token"): "META_VERIFY_TOKEN",
    ("whatsapp", "business_account_id"): "WHATSAPP_BUSINESS_ACCOUNT_ID",
    ("facebook", "page_id"): "FB_PAGE_ID",
    ("facebook", "page_access_token"): "FB_PAGE_ACCESS_TOKEN",
    ("instagram", "ig_business_account_id"): "IG_BUSINESS_ACCOUNT_ID",
    ("instagram", "fb_page_access_token"): "FB_PAGE_ACCESS_TOKEN",
    ("email", "api_key"): "RESEND_API_KEY",
    ("email", "sender_email"): "SENDER_EMAIL",
    ("ai", "api_key"): "EMERGENT_LLM_KEY",
}


# ---------------- Encryption ----------------
def _fernet() -> Fernet:
    secret = os.environ["JWT_SECRET"].encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt_value(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def mask_value(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••••••" + value[-4:]


def _field_meta(provider: str, key: str):
    for f in PROVIDERS[provider]["fields"]:
        if f["key"] == key:
            return f
    return None


def _default_for(provider: str, key: str):
    f = _field_meta(provider, key)
    return f.get("default", "") if f else ""


# ---------------- Config loader (DB -> .env -> default) ----------------
async def get_value(db, provider: str, key: str):
    doc = await db.integration_settings.find_one({"provider": provider, "setting_key": key})
    if doc and doc.get("setting_value"):
        return decrypt_value(doc["setting_value"]) if doc.get("is_encrypted") else doc["setting_value"]
    env_name = ENV_MAP.get((provider, key))
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return _default_for(provider, key) or None


async def get_creds(db, provider: str) -> dict:
    out = {}
    for f in PROVIDERS[provider]["fields"]:
        out[f["key"]] = await get_value(db, provider, f["key"])
    return out


async def is_configured(db, provider: str) -> bool:
    for key in PROVIDERS[provider]["required"]:
        if not await get_value(db, provider, key):
            return False
    return True


# ---------------- .env -> DB migration (one-time) ----------------
async def migrate_env_to_db(db):
    if await db.integration_settings.count_documents({}) > 0:
        return  # DB already has settings; never touch .env again
    now = datetime.now(timezone.utc).isoformat()
    migrated = 0
    for (provider, key), env_name in ENV_MAP.items():
        val = os.environ.get(env_name)
        if not val:
            continue
        f = _field_meta(provider, key)
        secret = bool(f and f.get("secret"))
        await db.integration_settings.update_one(
            {"provider": provider, "setting_key": key},
            {"$set": {
                "provider": provider, "setting_key": key,
                "setting_value": encrypt_value(val) if secret else val,
                "is_encrypted": secret, "status": "needs_verification",
                "last_verified_at": None, "created_by": "system:.env-migration",
                "updated_by": "system:.env-migration", "created_at": now, "updated_at": now,
            }},
            upsert=True,
        )
        migrated += 1
    # ai provider/model defaults if EMERGENT key migrated
    if migrated and os.environ.get("EMERGENT_LLM_KEY"):
        for key, val in (("provider", "Emergent"), ("model_name", "gpt-4o-mini")):
            await db.integration_settings.update_one(
                {"provider": "ai", "setting_key": key},
                {"$set": {"provider": "ai", "setting_key": key, "setting_value": val,
                          "is_encrypted": False, "status": "needs_verification",
                          "created_by": "system:.env-migration", "updated_by": "system:.env-migration",
                          "created_at": now, "updated_at": now}},
                upsert=True,
            )
    if migrated:
        logger.info(f"Integration settings: migrated {migrated} value(s) from .env to DB")


# ---------------- Provider meta (status / health) ----------------
async def _get_meta(db, provider: str) -> dict:
    doc = await db.integration_meta.find_one({"provider": provider})
    if doc:
        doc.pop("_id", None)
        return doc
    return {"provider": provider, "status": None, "last_verified_at": None,
            "response_time_ms": None, "last_error": None}


async def _set_meta(db, provider: str, **fields):
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.integration_meta.update_one({"provider": provider}, {"$set": fields}, upsert=True)


async def _provider_status(db, provider: str) -> str:
    meta = await _get_meta(db, provider)
    if not await is_configured(db, provider):
        return "not_configured"
    return meta.get("status") or "needs_verification"


# ---------------- Audit log ----------------
async def _audit(db, provider, action, old_value, new_value, user, ip):
    await db.integration_audit_logs.insert_one({
        "provider": provider, "action": action,
        "old_value": mask_value(old_value or ""), "new_value": mask_value(new_value or ""),
        "updated_by": (user or {}).get("email", "unknown"), "ip_address": ip or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------- Connection tests ----------------
async def _test_whatsapp(c):
    pid = c.get("phone_number_id"); tok = c.get("access_token")
    ver = c.get("api_version") or GRAPH_DEFAULT_VERSION
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(f"https://graph.facebook.com/{ver}/{pid}",
                          params={"fields": "verified_name,display_phone_number"},
                          headers={"Authorization": f"Bearer {tok}"})
    if r.status_code == 200:
        return True, f"Connected: {r.json().get('verified_name', pid)}"
    return False, r.text[:300]


async def _test_facebook(c):
    pid = c.get("page_id"); tok = c.get("page_access_token")
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(f"https://graph.facebook.com/{GRAPH_DEFAULT_VERSION}/{pid}",
                          params={"fields": "name,id", "access_token": tok})
    if r.status_code == 200:
        return True, f"Page: {r.json().get('name', pid)}"
    return False, r.text[:300]


async def _test_instagram(c):
    igb = c.get("ig_business_account_id"); tok = c.get("fb_page_access_token")
    async with httpx.AsyncClient(timeout=15) as cli:
        r = await cli.get(f"https://graph.facebook.com/{GRAPH_DEFAULT_VERSION}/{igb}",
                          params={"fields": "username", "access_token": tok})
    if r.status_code == 200:
        return True, f"IG: @{r.json().get('username', igb)}"
    return False, r.text[:300]


async def _test_email(c):
    import resend
    key = c.get("api_key"); sender = c.get("sender_email")
    resend.api_key = key
    params = {"from": sender, "to": [sender], "subject": "LeadFlow test email",
              "html": "<p>Your Resend integration is working. ✅</p>"}
    import asyncio
    result = await asyncio.to_thread(resend.Emails.send, params)
    if result and result.get("id"):
        return True, f"Test email sent (id {result['id']})"
    return False, "No id returned from Resend"


async def _test_ai(c):
    provider = (c.get("provider") or "Emergent").lower()
    key = c.get("api_key"); model = c.get("model_name") or "gpt-4o-mini"
    if provider == "emergent":
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id="integration-test",
                       system_message="Reply with exactly: Hello World").with_model("openai", "gpt-4o-mini")
        out = await chat.send_message(UserMessage(text="Say hello world"))
        return (True, f"Response: {str(out)[:60]}") if out else (False, "Empty response")
    async with httpx.AsyncClient(timeout=20) as cli:
        if provider == "openai":
            r = await cli.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
        elif provider == "groq":
            r = await cli.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
        elif provider == "gemini":
            r = await cli.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key})
        elif provider == "claude":
            r = await cli.post("https://api.anthropic.com/v1/messages",
                               headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                        "content-type": "application/json"},
                               json={"model": model or "claude-3-haiku-20240307", "max_tokens": 5,
                                     "messages": [{"role": "user", "content": "hi"}]})
        else:
            return False, f"Unknown provider {provider}"
    if r.status_code in (200, 201):
        return True, f"{provider} key valid"
    return False, r.text[:300]


TESTERS = {"whatsapp": _test_whatsapp, "facebook": _test_facebook,
           "instagram": _test_instagram, "email": _test_email, "ai": _test_ai}


# ---------------- Router ----------------
def build_integrations_router(db, get_current_user, require_admin):
    router = APIRouter(prefix="/api/admin/integrations", tags=["integrations"])

    async def _provider_payload(provider: str) -> dict:
        spec = PROVIDERS[provider]
        meta = await _get_meta(db, provider)
        fields_out = []
        for f in spec["fields"]:
            raw = await get_value(db, provider, f["key"])
            fields_out.append({
                "key": f["key"], "label": f["label"], "secret": f.get("secret", False),
                "options": f.get("options"),
                "value": (mask_value(raw) if f.get("secret") else (raw or "")) if raw else "",
                "configured": bool(raw),
            })
        return {
            "provider": provider, "label": spec["label"], "description": spec["description"],
            "fields": fields_out,
            "status": await _provider_status(db, provider),
            "last_verified_at": meta.get("last_verified_at"),
            "last_error": meta.get("last_error"),
            "response_time_ms": meta.get("response_time_ms"),
            "updated_by": meta.get("updated_by"),
            "updated_at": meta.get("updated_at"),
        }

    @router.get("")
    async def list_integrations(user=Depends(get_current_user)):
        require_admin(user)
        return [await _provider_payload(p) for p in PROVIDERS]

    @router.post("")
    async def save_integration(payload: dict, request: Request, user=Depends(get_current_user)):
        require_admin(user)
        provider = payload.get("provider")
        if provider not in PROVIDERS:
            raise HTTPException(400, "Unknown provider")
        values = payload.get("values", {})
        now = datetime.now(timezone.utc).isoformat()
        ip = request.client.host if request.client else ""
        changed = 0
        for f in PROVIDERS[provider]["fields"]:
            key = f["key"]
            if key not in values:
                continue
            new_val = (values.get(key) or "").strip()
            if new_val == "":
                continue  # blank = leave unchanged (use Reset/Rotate to clear)
            old_raw = await get_value(db, provider, key)
            secret = f.get("secret", False)
            await db.integration_settings.update_one(
                {"provider": provider, "setting_key": key},
                {"$set": {
                    "provider": provider, "setting_key": key,
                    "setting_value": encrypt_value(new_val) if secret else new_val,
                    "is_encrypted": secret, "updated_by": user.get("email"), "updated_at": now,
                }, "$setOnInsert": {"created_by": user.get("email"), "created_at": now}},
                upsert=True,
            )
            await _audit(db, provider, "update", old_raw, new_val, user, ip)
            changed += 1
        await _set_meta(db, provider, status="needs_verification", updated_by=user.get("email"))
        return {"ok": True, "changed": changed, **(await _provider_payload(provider))}

    @router.post("/test")
    async def test_integration(payload: dict, request: Request, user=Depends(get_current_user)):
        require_admin(user)
        provider = payload.get("provider")
        if provider not in PROVIDERS:
            raise HTTPException(400, "Unknown provider")
        if not await is_configured(db, provider):
            await _set_meta(db, provider, status="not_configured")
            raise HTTPException(400, "Not configured")
        creds = await get_creds(db, provider)
        start = time.perf_counter()
        try:
            ok, detail = await TESTERS[provider](creds)
        except Exception as e:
            ok, detail = False, str(e)[:300]
        ms = int((time.perf_counter() - start) * 1000)
        status = "connected" if ok else "invalid"
        await _set_meta(db, provider, status=status,
                        last_verified_at=datetime.now(timezone.utc).isoformat() if ok else None,
                        response_time_ms=ms, last_error=None if ok else detail)
        await _audit(db, provider, "test", None, status, user,
                     request.client.host if request.client else "")
        return {"ok": ok, "status": status, "detail": detail, "response_time_ms": ms}

    @router.post("/rotate-secret")
    async def rotate_secret(payload: dict, request: Request, user=Depends(get_current_user)):
        require_admin(user)
        provider = payload.get("provider"); key = payload.get("key")
        if provider not in PROVIDERS:
            raise HTTPException(400, "Unknown provider")
        old_raw = await get_value(db, provider, key)
        await db.integration_settings.delete_one({"provider": provider, "setting_key": key})
        await _set_meta(db, provider, status="needs_verification")
        await _audit(db, provider, "rotate", old_raw, None, user,
                     request.client.host if request.client else "")
        return {"ok": True}

    @router.delete("/{provider}")
    async def reset_integration(provider: str, request: Request, user=Depends(get_current_user)):
        require_admin(user)
        if provider not in PROVIDERS:
            raise HTTPException(400, "Unknown provider")
        await db.integration_settings.delete_many({"provider": provider})
        await db.integration_meta.delete_one({"provider": provider})
        await _audit(db, provider, "reset", None, None, user,
                     request.client.host if request.client else "")
        return {"ok": True}

    @router.get("/health")
    async def health(user=Depends(get_current_user)):
        require_admin(user)
        rows = []
        for p in PROVIDERS:
            meta = await _get_meta(db, p)
            rows.append({
                "provider": p, "label": PROVIDERS[p]["label"],
                "status": await _provider_status(db, p),
                "last_verified_at": meta.get("last_verified_at"),
                "response_time_ms": meta.get("response_time_ms"),
                "last_error": meta.get("last_error"),
            })
        return rows

    @router.get("/audit")
    async def audit_logs(user=Depends(get_current_user)):
        require_admin(user)
        docs = await db.integration_audit_logs.find({}).sort("created_at", -1).to_list(200)
        for d in docs:
            d.pop("_id", None)
        return docs

    return router
