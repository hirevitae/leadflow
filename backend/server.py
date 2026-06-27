from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import bcrypt
import jwt
import asyncio
import resend
from meta_integrations import _send_whatsapp_text, _send_whatsapp_template, fetch_meta_templates
from integrations_admin import build_integrations_router, migrate_env_to_db, get_creds, is_configured, get_value as get_integration_value
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, status, UploadFile, File
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import pandas as pd
import io

# ---------------- App / DB ----------------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="LeadFlow CRM")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
PIPELINE_STAGES = ["new", "contacted", "interested", "demo_scheduled", "negotiation", "enrolled", "lost"]
LEAD_COLUMNS = ["name", "phone", "email", "course", "source", "language", "priority", "notes", "stage"]
VALID_LANGS = {"english", "hindi"}
VALID_PRIORITIES = {"low", "medium", "high"}


# ---------------- Auth Helpers ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user.pop("password_hash", None)
        user.pop("_id", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=7 * 24 * 3600, path="/",
    )


# ---------------- Models ----------------
class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str = "counsellor"


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LeadIn(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    course: Optional[str] = None
    source: Optional[str] = "manual"
    language: str = "english"
    notes: Optional[str] = None
    priority: str = "medium"  # low/medium/high


class LeadUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    course: Optional[str] = None
    source: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None
    stage: Optional[str] = None


class StageChange(BaseModel):
    stage: str


class MessageIn(BaseModel):
    body: str
    template: Optional[str] = None


class CallIn(BaseModel):
    language: str = "english"  # english/hindi
    script_id: Optional[str] = None


class NoteIn(BaseModel):
    text: str


class BulkWhatsAppIn(BaseModel):
    stage: str
    template_id: str


class WhatsAppTemplateIn(BaseModel):
    template_name: str
    language: str = "en"
    params: List[str] = []


class BulkWhatsAppTemplateIn(BaseModel):
    stage: str
    template_name: str
    language: str = "en"
    params: List[str] = []


class BulkCallsIn(BaseModel):
    stage: str
    language: str = "english"


class TaskIn(BaseModel):
    title: str
    due_date: str  # ISO string
    lead_id: Optional[str] = None


class TaskUpdate(BaseModel):
    done: Optional[bool] = None
    title: Optional[str] = None
    due_date: Optional[str] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: str = "counsellor"


class AssignIn(BaseModel):
    owner_id: str


class EmailIn(BaseModel):
    subject: str
    body: str


class TeamSettingsIn(BaseModel):
    round_robin: bool


class ContentConfigIn(BaseModel):
    search_keywords: List[str] = []
    search_sources: List[str] = []
    interval_hours: int = 1
    enabled: bool = False
    auto_publish: bool = False


class TemplatesConfigIn(BaseModel):
    whatsapp_templates: List[dict] = []
    call_scripts: dict = {}


# ---------------- Templates / Scripts ----------------
WHATSAPP_TEMPLATES = [
    {"id": "intro_en", "lang": "english", "name": "Introduction",
     "body": "Hi {name}, this is LeadFlow Academy. We saw your interest in {course}. Can we share details?"},
    {"id": "intro_hi", "lang": "hindi", "name": "परिचय",
     "body": "नमस्ते {name} जी, मैं LeadFlow Academy से बात कर रहा हूँ। आपने {course} में रुचि दिखाई थी, क्या हम जानकारी भेज सकते हैं?"},
    {"id": "demo_en", "lang": "english", "name": "Demo Invite",
     "body": "Hi {name}, would you like to attend a free demo class for {course} this week?"},
    {"id": "demo_hi", "lang": "hindi", "name": "डेमो आमंत्रण",
     "body": "नमस्ते {name}, क्या आप इस हफ्ते {course} की मुफ्त डेमो क्लास में भाग लेना चाहेंगे?"},
    {"id": "followup_en", "lang": "english", "name": "Follow-up",
     "body": "Hi {name}, just checking in. Do you have any questions about {course}?"},
    {"id": "followup_hi", "lang": "hindi", "name": "फ़ॉलो-अप",
     "body": "नमस्ते {name}, क्या {course} के बारे में कोई सवाल है?"},
]

AI_CALL_SCRIPTS = {
    "english": "Hello {name}, this is Asha from LeadFlow Academy. I'm calling to follow up on your interest in {course}. Do you have a couple of minutes to discuss?",
    "hindi": "नमस्ते {name} जी, मैं LeadFlow Academy से आशा बोल रही हूँ। आपकी {course} में रुचि के बारे में बात करनी थी। क्या आपके पास दो मिनट हैं?",
}

AI_CALL_RESPONSES = [
    "Customer: Yes, please tell me more.",
    "AI: Great! Our course runs for 12 weeks with live sessions and projects.",
    "Customer: What is the fee structure?",
    "AI: The total fee is INR 25,000 with easy EMI options available.",
    "Customer: Can I get a demo class first?",
    "AI: Absolutely. I will share a demo invite on WhatsApp right away.",
]

DEFAULT_NEWS_SOURCES = ["https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"]
DEFAULT_CONTENT_CONFIG = {
    "search_keywords": ["SSC CGL recruitment", "IBPS PO notification", "UPSC notification", "government jobs India"],
    "search_sources": DEFAULT_NEWS_SOURCES,
    "interval_hours": 1, "enabled": False, "auto_publish": False,
}


# ---------------- Config Helpers (DB-backed, live editable) ----------------
async def get_config(key: str, default):
    doc = await db.app_config.find_one({"key": key})
    return doc.get("value", default) if doc else default


async def set_config(key: str, value):
    await db.app_config.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)


async def get_templates() -> list:
    return await get_config("whatsapp_templates", WHATSAPP_TEMPLATES)


async def get_call_scripts() -> dict:
    return await get_config("call_scripts", AI_CALL_SCRIPTS)


async def _get_team_settings() -> dict:
    return await get_config("team_settings", {"round_robin": False, "rr_index": 0})


async def _assign_owner(creator: dict):
    s = await _get_team_settings()
    if not s.get("round_robin"):
        return creator["id"], creator["name"]
    counsellors = await db.users.find({"role": "counsellor"}).sort("created_at", 1).to_list(500)
    if not counsellors:
        return creator["id"], creator["name"]
    idx = int(s.get("rr_index", 0)) % len(counsellors)
    chosen = counsellors[idx]
    s["rr_index"] = idx + 1
    await set_config("team_settings", s)
    return chosen["id"], chosen["name"]


def require_admin(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")


# ---------------- Auth Endpoints ----------------
@api_router.post("/auth/register", response_model=UserPublic)
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id, "email": email, "name": payload.name,
        "password_hash": hash_password(payload.password),
        "role": "counsellor",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id, email)
    set_auth_cookie(response, token)
    return UserPublic(id=user_id, email=email, name=payload.name, role="counsellor")


@api_router.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user["id"], email)
    set_auth_cookie(response, token)
    return {"id": user["id"], "email": user["email"], "name": user["name"],
            "role": user.get("role", "counsellor"), "token": token}


@api_router.post("/auth/logout")
async def logout(response: Response, _user=Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    return UserPublic(**user)


# ---------------- Lead Endpoints ----------------
def _lead_doc_to_out(d: dict) -> dict:
    d.pop("_id", None)
    return d


@api_router.get("/leads")
async def list_leads(stage: Optional[str] = None, q: Optional[str] = None,
                     user=Depends(get_current_user)):
    query = {}
    if user.get("role") != "admin":
        query["owner_id"] = user["id"]
    if stage and stage in PIPELINE_STAGES:
        query["stage"] = stage
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"course": {"$regex": q, "$options": "i"}},
        ]
    leads = await db.leads.find(query).sort([("interest_score", -1), ("created_at", -1)]).to_list(1000)
    return [_lead_doc_to_out(d) for d in leads]


@api_router.post("/leads")
async def create_lead(payload: LeadIn, user=Depends(get_current_user)):
    lead_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    owner_id, owner_name = await _assign_owner(user)
    doc = {
        "id": lead_id, **payload.model_dump(),
        "stage": "new", "owner_id": owner_id, "owner_name": owner_name,
        "created_at": now, "updated_at": now, "last_activity_at": now,
    }
    await db.leads.insert_one(doc)
    await _add_activity(lead_id, "lead_created", f"Lead created by {user['name']}", user)
    return _lead_doc_to_out(doc)


@api_router.get("/leads/template.xlsx")
async def download_template(user=Depends(get_current_user)):
    sample = pd.DataFrame([
        {"name": "Rahul Sharma", "phone": "+919876543210", "email": "rahul@example.com",
         "course": "Data Science", "source": "instagram", "language": "hindi",
         "priority": "high", "notes": "Met at career fair", "stage": "new"},
        {"name": "Priya Iyer", "phone": "+919812345678", "email": "priya@example.com",
         "course": "Full Stack Web", "source": "website", "language": "english",
         "priority": "medium", "notes": "", "stage": "new"},
    ], columns=LEAD_COLUMNS)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        sample.to_excel(w, sheet_name="leads", index=False)
        ws = w.sheets["leads"]
        for i, col in enumerate(LEAD_COLUMNS):
            ws.set_column(i, i, max(len(col) + 4, 16))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="leads_template.xlsx"'},
    )


@api_router.get("/leads/export.xlsx")
async def export_leads(user=Depends(get_current_user)):
    leads = await db.leads.find({}).sort("created_at", -1).to_list(10000)
    rows = []
    for l in leads:
        rows.append({
            "name": l.get("name", ""), "phone": l.get("phone", ""),
            "email": l.get("email", "") or "", "course": l.get("course", "") or "",
            "source": l.get("source", "") or "", "language": l.get("language", "english"),
            "priority": l.get("priority", "medium"), "notes": l.get("notes", "") or "",
            "stage": l.get("stage", "new"), "owner": l.get("owner_name", ""),
            "created_at": l.get("created_at", ""),
        })
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df.to_excel(w, sheet_name="leads", index=False)
        ws = w.sheets["leads"]
        for i, col in enumerate(df.columns):
            ws.set_column(i, i, max(len(col) + 4, 18))
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="leads_export_{stamp}.xlsx"'},
    )


@api_router.post("/leads/bulk-import")
async def bulk_import(file: UploadFile = File(...), user=Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(400, "No file provided")
    name = file.filename.lower()
    content = await file.read()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content), dtype=str)
        elif name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            raise HTTPException(400, "Unsupported file type. Upload .xlsx, .xls or .csv")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    if "name" not in df.columns or "phone" not in df.columns:
        raise HTTPException(400, "File must contain at least 'name' and 'phone' columns")

    created, skipped, duplicates, errors = 0, 0, 0, []
    now = datetime.now(timezone.utc).isoformat()
    existing_phones = set(await db.leads.distinct("phone"))
    seen_phones = set()
    docs = []
    for idx, row in df.iterrows():
        try:
            nm = str(row.get("name", "")).strip()
            ph = str(row.get("phone", "")).strip()
            if not nm or not ph or nm.lower() == "nan" or ph.lower() == "nan":
                skipped += 1
                continue
            if ph in existing_phones or ph in seen_phones:
                duplicates += 1
                continue
            seen_phones.add(ph)
            lang = str(row.get("language", "english")).strip().lower() or "english"
            if lang not in VALID_LANGS:
                lang = "english"
            prio = str(row.get("priority", "medium")).strip().lower() or "medium"
            if prio not in VALID_PRIORITIES:
                prio = "medium"
            stage = str(row.get("stage", "new")).strip().lower() or "new"
            if stage not in PIPELINE_STAGES:
                stage = "new"

            def _cell(key):
                v = row.get(key, "")
                if v is None:
                    return ""
                s = str(v).strip()
                return "" if s.lower() == "nan" else s

            owner_id, owner_name = await _assign_owner(user)
            doc = {
                "id": str(uuid.uuid4()), "name": nm, "phone": ph,
                "email": _cell("email") or None,
                "course": _cell("course") or None,
                "source": (_cell("source") or "import").lower(),
                "language": lang, "priority": prio,
                "notes": _cell("notes") or None,
                "stage": stage,
                "owner_id": owner_id, "owner_name": owner_name,
                "created_at": now, "updated_at": now, "last_activity_at": now,
            }
            docs.append(doc)
        except Exception as e:
            errors.append({"row": int(idx) + 2, "error": str(e)})

    if docs:
        await db.leads.insert_many(docs)
        acts = [{
            "id": str(uuid.uuid4()), "lead_id": d["id"], "kind": "lead_created",
            "text": f"Imported by {user['name']}",
            "user_id": user["id"], "user_name": user["name"],
            "created_at": now,
        } for d in docs]
        if acts:
            await db.activities.insert_many(acts)
        created = len(docs)

    return {"created": created, "skipped": skipped, "duplicates": duplicates, "errors": errors, "total_rows": int(len(df))}


@api_router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, user=Depends(get_current_user)):
    doc = await db.leads.find_one({"id": lead_id})
    if not doc:
        raise HTTPException(404, "Lead not found")
    return _lead_doc_to_out(doc)


@api_router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, payload: LeadUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "stage" in update and update["stage"] not in PIPELINE_STAGES:
        raise HTTPException(400, "Invalid stage")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.leads.find_one_and_update({"id": lead_id}, {"$set": update}, return_document=True)
    if not res:
        raise HTTPException(404, "Lead not found")
    if "stage" in update:
        await _add_activity(lead_id, "stage_changed", f"Stage moved to {update['stage']}", user)
    return _lead_doc_to_out(res)


@api_router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, user=Depends(get_current_user)):
    r = await db.leads.delete_one({"id": lead_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Lead not found")
    await db.messages.delete_many({"lead_id": lead_id})
    await db.calls.delete_many({"lead_id": lead_id})
    await db.activities.delete_many({"lead_id": lead_id})
    await db.tasks.delete_many({"lead_id": lead_id})
    return {"ok": True}


@api_router.post("/leads/{lead_id}/stage")
async def change_stage(lead_id: str, payload: StageChange, user=Depends(get_current_user)):
    if payload.stage not in PIPELINE_STAGES:
        raise HTTPException(400, "Invalid stage")
    now = datetime.now(timezone.utc).isoformat()
    res = await db.leads.find_one_and_update(
        {"id": lead_id},
        {"$set": {"stage": payload.stage, "updated_at": now, "last_activity_at": now}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Lead not found")
    await _add_activity(lead_id, "stage_changed", f"Stage moved to {payload.stage}", user)
    return _lead_doc_to_out(res)


# ---------------- Activity Helper ----------------
async def _add_activity(lead_id: str, kind: str, text: str, user: dict):
    now = datetime.now(timezone.utc).isoformat()
    await db.activities.insert_one({
        "id": str(uuid.uuid4()), "lead_id": lead_id, "kind": kind,
        "text": text, "user_id": user["id"], "user_name": user["name"],
        "created_at": now,
    })
    await db.leads.update_one({"id": lead_id}, {"$set": {"last_activity_at": now}})


@api_router.get("/leads/{lead_id}/activities")
async def list_activities(lead_id: str, user=Depends(get_current_user)):
    docs = await db.activities.find({"lead_id": lead_id}).sort("created_at", -1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    return docs


@api_router.post("/leads/{lead_id}/notes")
async def add_note(lead_id: str, payload: NoteIn, user=Depends(get_current_user)):
    if not await db.leads.find_one({"id": lead_id}):
        raise HTTPException(404, "Lead not found")
    await _add_activity(lead_id, "note", payload.text, user)
    return {"ok": True}


# ---------------- WhatsApp (Mock) ----------------
@api_router.get("/whatsapp/templates")
async def list_templates(user=Depends(get_current_user)):
    return await get_templates()


@api_router.get("/leads/{lead_id}/messages")
async def list_messages(lead_id: str, user=Depends(get_current_user)):
    docs = await db.messages.find({"lead_id": lead_id}).sort("created_at", 1).to_list(1000)
    for d in docs:
        d.pop("_id", None)
    return docs


@api_router.post("/leads/{lead_id}/messages")
async def send_message(lead_id: str, payload: MessageIn, user=Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    now = datetime.now(timezone.utc).isoformat()
    body = payload.body.replace("{name}", lead.get("name") or "").replace("{course}", lead.get("course") or "your course")
    status, provider_id = "sent (mock)", None
    if await is_configured(db, "whatsapp"):
        creds = await get_creds(db, "whatsapp")
        try:
            resp = await _send_whatsapp_text(lead["phone"], body, creds.get("phone_number_id"), creds.get("access_token"), creds.get("api_version"))
            provider_id = (resp.get("messages") or [{}])[0].get("id")
            status = "sent"
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            raise HTTPException(502, f"WhatsApp send failed: {e}")
    msg = {
        "id": str(uuid.uuid4()), "lead_id": lead_id, "direction": "outbound",
        "channel": "whatsapp", "body": body, "template": payload.template,
        "status": status, "provider_id": provider_id, "created_at": now,
    }
    await db.messages.insert_one(msg)
    await _add_activity(lead_id, "whatsapp_sent", f"WhatsApp: {body[:60]}", user)
    # Auto-advance to contacted if still new
    if lead.get("stage") == "new":
        await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "contacted"}})
    msg.pop("_id", None)
    return msg


# ---------------- WhatsApp Meta-approved Templates (real Cloud API) ----------------
@api_router.get("/whatsapp/meta-templates")
async def whatsapp_meta_templates(user=Depends(get_current_user)):
    if not await is_configured(db, "whatsapp"):
        raise HTTPException(400, "WhatsApp not configured in Settings → Integrations")
    wa = await get_creds(db, "whatsapp")
    waba = wa.get("business_account_id")
    if not waba:
        raise HTTPException(400, "Set the WhatsApp Business Account ID in Settings → Integrations")
    try:
        tpls = await fetch_meta_templates(waba, wa.get("access_token"), wa.get("api_version"))
    except Exception as e:
        logger.error(f"Meta template fetch failed: {e}")
        raise HTTPException(502, f"Failed to fetch templates from Meta: {e}")
    out = []
    for t in tpls:
        body = next((c.get("text", "") for c in t.get("components", []) if c.get("type") == "BODY"), "")
        out.append({"name": t.get("name"), "language": t.get("language"),
                    "status": t.get("status"), "category": t.get("category"),
                    "body": body, "param_count": body.count("{{")})
    return out


def _fill_params(params, lead):
    return [(p or "").replace("{name}", lead.get("name") or "").replace("{course}", lead.get("course") or "") for p in params]


@api_router.post("/leads/{lead_id}/whatsapp-template")
async def send_lead_whatsapp_template(lead_id: str, payload: WhatsAppTemplateIn, user=Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not await is_configured(db, "whatsapp"):
        raise HTTPException(400, "WhatsApp not configured. Add real Meta credentials in Settings → Integrations")
    wa = await get_creds(db, "whatsapp")
    params = _fill_params(payload.params, lead)
    try:
        resp = await _send_whatsapp_template(lead["phone"], payload.template_name, payload.language, params,
                                             wa.get("phone_number_id"), wa.get("access_token"), wa.get("api_version"))
        provider_id = (resp.get("messages") or [{}])[0].get("id")
    except Exception as e:
        logger.error(f"WhatsApp template send failed: {e}")
        raise HTTPException(502, f"WhatsApp template send failed: {e}")
    now = datetime.now(timezone.utc).isoformat()
    body_repr = f"[Template: {payload.template_name}]" + (" " + " | ".join(params) if params else "")
    msg = {
        "id": str(uuid.uuid4()), "lead_id": lead_id, "direction": "outbound",
        "channel": "whatsapp", "body": body_repr, "template": payload.template_name,
        "type": "template", "status": "sent", "provider_id": provider_id, "created_at": now,
    }
    await db.messages.insert_one(msg)
    await _add_activity(lead_id, "whatsapp_sent", f"WhatsApp template: {payload.template_name}", user)
    if lead.get("stage") == "new":
        await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "contacted"}})
    msg.pop("_id", None)
    return msg


# ---------------- AI Calls (Mock) ----------------
@api_router.get("/leads/{lead_id}/calls")
async def list_calls(lead_id: str, user=Depends(get_current_user)):
    docs = await db.calls.find({"lead_id": lead_id}).sort("created_at", -1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    return docs


@api_router.post("/leads/{lead_id}/calls")
async def trigger_call(lead_id: str, payload: CallIn, user=Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    now = datetime.now(timezone.utc).isoformat()
    scripts = await get_call_scripts()
    lang = payload.language if payload.language in scripts else "english"
    opening = scripts[lang].replace("{name}", lead.get("name") or "").replace("{course}", lead.get("course") or "the course")
    transcript = [{"speaker": "AI", "text": opening}]
    for line in AI_CALL_RESPONSES:
        speaker, text = line.split(":", 1)
        transcript.append({"speaker": speaker.strip(), "text": text.strip()})
    call_doc = {
        "id": str(uuid.uuid4()), "lead_id": lead_id, "language": lang,
        "status": "completed (mock)", "duration_sec": 92,
        "transcript": transcript,
        "summary": f"AI follow-up call about {lead.get('course', 'the course')}. Customer asked about fees and demo class.",
        "outcome": "interested",
        "created_at": now,
    }
    await db.calls.insert_one(call_doc)
    await _add_activity(lead_id, "ai_call", f"AI call ({lang}) — outcome: interested", user)
    # Auto-advance stage from new/contacted to interested
    if lead.get("stage") in ("new", "contacted"):
        await db.leads.update_one({"id": lead_id}, {"$set": {"stage": "interested"}})
    call_doc.pop("_id", None)
    return call_doc


# ---------------- Bulk Outreach ----------------
@api_router.post("/bulk/whatsapp")
async def bulk_whatsapp(payload: BulkWhatsAppIn, user=Depends(get_current_user)):
    if payload.stage not in PIPELINE_STAGES:
        raise HTTPException(400, "Invalid stage")
    templates = await get_templates()
    template = next((t for t in templates if t["id"] == payload.template_id), None)
    if not template:
        raise HTTPException(400, "Invalid template")
    leads = await db.leads.find({"stage": payload.stage}).to_list(5000)
    now = datetime.now(timezone.utc).isoformat()
    configured = await is_configured(db, "whatsapp")
    wa = await get_creds(db, "whatsapp") if configured else {}
    sent, failed = 0, 0
    for lead in leads:
        body = template["body"].replace("{name}", lead.get("name") or "").replace("{course}", lead.get("course") or "your course")
        status, provider_id = "sent (mock)", None
        if configured:
            try:
                resp = await _send_whatsapp_text(lead["phone"], body, wa.get("phone_number_id"), wa.get("access_token"), wa.get("api_version"))
                provider_id = (resp.get("messages") or [{}])[0].get("id")
                status = "sent"
            except Exception as e:
                logger.error(f"Bulk WhatsApp send failed for {lead['id']}: {e}")
                status = "failed"; failed += 1
        await db.messages.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead["id"], "direction": "outbound",
            "channel": "whatsapp", "body": body, "template": template["id"],
            "status": status, "provider_id": provider_id, "created_at": now,
        })
        await _add_activity(lead["id"], "whatsapp_sent", f"Bulk WhatsApp: {body[:60]}", user)
        if status != "failed":
            if lead.get("stage") == "new":
                await db.leads.update_one({"id": lead["id"]}, {"$set": {"stage": "contacted"}})
            sent += 1
    return {"ok": True, "sent": sent, "failed": failed, "stage": payload.stage}


@api_router.post("/bulk/whatsapp-template")
async def bulk_whatsapp_template(payload: BulkWhatsAppTemplateIn, user=Depends(get_current_user)):
    if payload.stage not in PIPELINE_STAGES:
        raise HTTPException(400, "Invalid stage")
    if not await is_configured(db, "whatsapp"):
        raise HTTPException(400, "WhatsApp not configured. Add real Meta credentials in Settings → Integrations")
    wa = await get_creds(db, "whatsapp")
    leads = await db.leads.find({"stage": payload.stage}).to_list(5000)
    now = datetime.now(timezone.utc).isoformat()
    sent, failed = 0, 0
    for lead in leads:
        params = _fill_params(payload.params, lead)
        try:
            resp = await _send_whatsapp_template(lead["phone"], payload.template_name, payload.language, params,
                                                 wa.get("phone_number_id"), wa.get("access_token"), wa.get("api_version"))
            provider_id = (resp.get("messages") or [{}])[0].get("id")
            status = "sent"
        except Exception as e:
            logger.error(f"Bulk WhatsApp template failed for {lead['id']}: {e}")
            status = "failed"; provider_id = None; failed += 1
        body_repr = f"[Template: {payload.template_name}]" + (" " + " | ".join(params) if params else "")
        await db.messages.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead["id"], "direction": "outbound",
            "channel": "whatsapp", "body": body_repr, "template": payload.template_name,
            "type": "template", "status": status, "provider_id": provider_id, "created_at": now,
        })
        await _add_activity(lead["id"], "whatsapp_sent", f"Bulk template: {payload.template_name}", user)
        if status != "failed":
            if lead.get("stage") == "new":
                await db.leads.update_one({"id": lead["id"]}, {"$set": {"stage": "contacted"}})
            sent += 1
    return {"ok": True, "sent": sent, "failed": failed, "stage": payload.stage}


@api_router.post("/bulk/calls")
async def bulk_calls(payload: BulkCallsIn, user=Depends(get_current_user)):
    if payload.stage not in PIPELINE_STAGES:
        raise HTTPException(400, "Invalid stage")
    scripts = await get_call_scripts()
    lang = payload.language if payload.language in scripts else "english"
    leads = await db.leads.find({"stage": payload.stage}).to_list(5000)
    now = datetime.now(timezone.utc).isoformat()
    called = 0
    for lead in leads:
        opening = scripts[lang].replace("{name}", lead.get("name") or "").replace("{course}", lead.get("course") or "the course")
        transcript = [{"speaker": "AI", "text": opening}]
        for line in AI_CALL_RESPONSES:
            speaker, text = line.split(":", 1)
            transcript.append({"speaker": speaker.strip(), "text": text.strip()})
        await db.calls.insert_one({
            "id": str(uuid.uuid4()), "lead_id": lead["id"], "language": lang,
            "status": "completed (mock)", "duration_sec": 92, "transcript": transcript,
            "summary": f"AI follow-up call about {lead.get('course', 'the course')}. Customer asked about fees and demo class.",
            "outcome": "interested", "created_at": now,
        })
        await _add_activity(lead["id"], "ai_call", f"Bulk AI call ({lang}) — outcome: interested", user)
        if lead.get("stage") in ("new", "contacted"):
            await db.leads.update_one({"id": lead["id"]}, {"$set": {"stage": "interested"}})
        called += 1
    return {"ok": True, "called": called, "stage": payload.stage}


# ---------------- Tasks (Follow-ups) ----------------
@api_router.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    query = {} if user.get("role") == "admin" else {"owner_id": user["id"]}
    docs = await db.tasks.find(query).sort("due_date", 1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    return docs


@api_router.post("/tasks")
async def create_task(payload: TaskIn, user=Depends(get_current_user)):
    lead_name = None
    if payload.lead_id:
        lead = await db.leads.find_one({"id": payload.lead_id})
        lead_name = lead.get("name") if lead else None
    doc = {
        "id": str(uuid.uuid4()), **payload.model_dump(),
        "lead_name": lead_name,
        "done": False, "owner_id": user["id"], "owner_name": user["name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.patch("/tasks/{task_id}")
async def update_task(task_id: str, payload: TaskUpdate, user=Depends(get_current_user)):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    res = await db.tasks.find_one_and_update({"id": task_id}, {"$set": update}, return_document=True)
    if not res:
        raise HTTPException(404, "Task not found")
    res.pop("_id", None)
    return res


@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user=Depends(get_current_user)):
    r = await db.tasks.delete_one({"id": task_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Task not found")
    return {"ok": True}


# ---------------- Team / Users (Admin) ----------------
@api_router.get("/users")
async def list_users(user=Depends(get_current_user)):
    require_admin(user)
    docs = await db.users.find({}).sort("created_at", 1).to_list(500)
    return [{"id": d["id"], "email": d["email"], "name": d["name"],
             "role": d.get("role", "counsellor")} for d in docs]


@api_router.post("/users")
async def create_user(payload: UserCreate, user=Depends(get_current_user)):
    require_admin(user)
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    role = payload.role if payload.role in ("admin", "counsellor") else "counsellor"
    uid = str(uuid.uuid4())
    await db.users.insert_one({
        "id": uid, "email": email, "name": payload.name,
        "password_hash": hash_password(payload.password), "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"id": uid, "email": email, "name": payload.name, "role": role}


@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user=Depends(get_current_user)):
    require_admin(user)
    if user_id == user["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    r = await db.users.delete_one({"id": user_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}


@api_router.post("/leads/{lead_id}/assign")
async def assign_lead(lead_id: str, payload: AssignIn, user=Depends(get_current_user)):
    require_admin(user)
    owner = await db.users.find_one({"id": payload.owner_id})
    if not owner:
        raise HTTPException(404, "User not found")
    res = await db.leads.find_one_and_update(
        {"id": lead_id},
        {"$set": {"owner_id": owner["id"], "owner_name": owner["name"],
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Lead not found")
    await _add_activity(lead_id, "assigned", f"Lead assigned to {owner['name']}", user)
    return _lead_doc_to_out(res)


# ---------------- Email Channel (Resend) ----------------
@api_router.get("/leads/{lead_id}/emails")
async def list_emails(lead_id: str, user=Depends(get_current_user)):
    docs = await db.emails.find({"lead_id": lead_id}).sort("created_at", -1).to_list(500)
    for d in docs:
        d.pop("_id", None)
    return docs


@api_router.post("/leads/{lead_id}/email")
async def send_lead_email(lead_id: str, payload: EmailIn, user=Depends(get_current_user)):
    lead = await db.leads.find_one({"id": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.get("email"):
        raise HTTPException(400, "This lead has no email address")
    em = await get_creds(db, "email")
    api_key = em.get("api_key")
    if not api_key:
        raise HTTPException(400, "Email not configured. Set it in Settings → Integrations")
    sender = em.get("sender_email") or "onboarding@resend.dev"
    html = payload.body.replace("{name}", lead.get("name", "")).replace("\n", "<br>")
    resend.api_key = api_key
    params = {"from": sender, "to": [lead["email"]], "subject": payload.subject, "html": html}
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.error(f"Resend send failed: {e}")
        raise HTTPException(502, f"Email send failed: {e}")
    now = datetime.now(timezone.utc).isoformat()
    rec = {
        "id": str(uuid.uuid4()), "lead_id": lead_id, "to": lead["email"],
        "subject": payload.subject, "body": payload.body,
        "provider_id": (result or {}).get("id"), "status": "sent", "created_at": now,
    }
    await db.emails.insert_one(dict(rec))
    await _add_activity(lead_id, "email_sent", f"Email: {payload.subject[:60]}", user)
    return {"ok": True, "id": rec["id"]}


# ---------------- Settings / Config ----------------
@api_router.get("/integrations/status")
async def integrations_status(user=Depends(get_current_user)):
    return {
        "whatsapp": await is_configured(db, "whatsapp"),
        "meta_verify": bool(await get_integration_value(db, "whatsapp", "verify_token")),
        "facebook": await is_configured(db, "facebook"),
        "instagram": await is_configured(db, "instagram"),
        "email": await is_configured(db, "email"),
        "llm": await is_configured(db, "ai"),
    }


@api_router.get("/config/content")
async def get_content_config(user=Depends(get_current_user)):
    return await get_config("content_config", DEFAULT_CONTENT_CONFIG)


@api_router.put("/config/content")
async def update_content_config(payload: ContentConfigIn, user=Depends(get_current_user)):
    require_admin(user)
    cur = await get_config("content_config", DEFAULT_CONTENT_CONFIG)
    val = payload.model_dump()
    val["interval_hours"] = max(1, int(val.get("interval_hours", 1)))
    if not val.get("search_sources"):
        val["search_sources"] = DEFAULT_NEWS_SOURCES
    if not val.get("search_keywords"):
        val["search_keywords"] = DEFAULT_CONTENT_CONFIG["search_keywords"]
    val["last_run"] = cur.get("last_run")
    await set_config("content_config", val)
    return val


@api_router.get("/config/templates")
async def get_templates_config(user=Depends(get_current_user)):
    return {"whatsapp_templates": await get_templates(), "call_scripts": await get_call_scripts()}


@api_router.put("/config/templates")
async def update_templates_config(payload: TemplatesConfigIn, user=Depends(get_current_user)):
    require_admin(user)
    if payload.whatsapp_templates:
        seen = {}
        for t in payload.whatsapp_templates:
            seen[t.get("id")] = t
        await set_config("whatsapp_templates", list(seen.values()))
    if payload.call_scripts:
        await set_config("call_scripts", payload.call_scripts)
    return {"whatsapp_templates": await get_templates(), "call_scripts": await get_call_scripts()}


@api_router.get("/config/team")
async def get_team_config(user=Depends(get_current_user)):
    return await _get_team_settings()


@api_router.put("/config/team")
async def update_team_config(payload: TeamSettingsIn, user=Depends(get_current_user)):
    require_admin(user)
    cur = await _get_team_settings()
    cur["round_robin"] = payload.round_robin
    await set_config("team_settings", cur)
    return cur


# ---------------- Analytics ----------------
@api_router.get("/analytics/overview")
async def analytics_overview(user=Depends(get_current_user)):
    total = await db.leads.count_documents({})
    stages = {}
    for s in PIPELINE_STAGES:
        stages[s] = await db.leads.count_documents({"stage": s})
    enrolled = stages["enrolled"]
    lost = stages["lost"]
    closed = enrolled + lost
    conv_rate = round((enrolled / total) * 100, 1) if total else 0.0
    win_rate = round((enrolled / closed) * 100, 1) if closed else 0.0

    # source breakdown
    src_pipeline = [{"$group": {"_id": "$source", "count": {"$sum": 1}}}]
    sources_raw = await db.leads.aggregate(src_pipeline).to_list(100)
    sources = [{"source": (s["_id"] or "unknown"), "count": s["count"]} for s in sources_raw]

    # activity counts
    msg_count = await db.messages.count_documents({})
    call_count = await db.calls.count_documents({})

    # daily new leads (last 14 days)
    daily = []
    today = datetime.now(timezone.utc).date()
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        prefix = day.isoformat()
        c = await db.leads.count_documents({"created_at": {"$regex": f"^{prefix}"}})
        daily.append({"date": prefix, "count": c})

    return {
        "total_leads": total, "stages": stages, "conv_rate": conv_rate,
        "win_rate": win_rate, "sources": sources,
        "whatsapp_sent": msg_count, "ai_calls": call_count, "daily": daily,
    }


# ---------------- Startup ----------------
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.leads.create_index("stage")
    await db.leads.create_index("created_at")
    await db.messages.create_index("lead_id")
    await db.calls.create_index("lead_id")
    await db.activities.create_index("lead_id")
    await db.app_config.create_index("key", unique=True)
    await db.integration_settings.create_index([("provider", 1), ("setting_key", 1)], unique=True)
    await db.integration_meta.create_index("provider", unique=True)
    await migrate_env_to_db(db)

    try:
        if hasattr(social_router, "start_scheduler"):
            social_router.start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler start failed: {e}")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@leadflow.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": admin_email, "name": "Admin",
            "password_hash": hash_password(admin_password), "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Seeded admin: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# Health
@api_router.get("/")
async def root():
    return {"app": "LeadFlow CRM", "ok": True}


app.include_router(api_router)

from meta_integrations import build_meta_router
app.include_router(build_meta_router(db, get_current_user, _add_activity))

from social_posts import build_social_router
social_router = build_social_router(db, get_current_user)
app.include_router(social_router)

app.include_router(build_integrations_router(db, get_current_user, require_admin))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
