"""Configurable social post generator: pulls news from configured sources/keywords, drafts post + banner via AI, queues for approval, publishes to FB/IG. Includes an optional background scheduler."""
import os, uuid, asyncio, base64, httpx, logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_SOURCES = ["https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"]
DEFAULT_KEYWORDS = ["SSC CGL recruitment", "IBPS PO notification", "UPSC notification", "government jobs India"]
GRAPH = "https://graph.facebook.com/v19.0"


async def fetch_news(topic: str, sources: list, limit: int = 5):
    items = []
    for src in (sources or DEFAULT_SOURCES):
        url = src.replace("{q}", quote(topic)) if "{q}" in src else src
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
                r = await c.get(url); r.raise_for_status()
            root = ET.fromstring(r.text)
            for item in root.iter("item"):
                t = item.findtext("title") or ""; link = item.findtext("link") or ""
                pub = item.findtext("pubDate") or ""
                items.append({"title": t, "link": link, "pub_date": pub})
                if len(items) >= limit:
                    break
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


async def gen_post_text(topic: str, headline: str) -> dict:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ["EMERGENT_LLM_KEY"]
        sys_msg = ("You write punchy social media posts for an Indian education academy. "
                   "Output exactly two lines:\nLINE1_CAPTION: <100-160 char engaging caption with 3-4 relevant hashtags>\n"
                   "LINE2_BANNER: <max 8 word bold banner headline for an image overlay>")
        chat = LlmChat(api_key=key, session_id=f"post-{uuid.uuid4()}", system_message=sys_msg).with_model("anthropic", "claude-sonnet-4-6")
        out = await chat.send_message(UserMessage(text=f"Topic: {topic}\nNews headline: {headline}\n\nWrite the post."))
        s = str(out)
        cap, ban = "", ""
        for line in s.splitlines():
            if line.startswith("LINE1_CAPTION:"): cap = line.split(":", 1)[1].strip()
            elif line.startswith("LINE2_BANNER:"): ban = line.split(":", 1)[1].strip()
        if not cap: cap = headline + " #govtjobs #recruitment #studywithus"
        if not ban: ban = topic.upper()
        return {"caption": cap, "banner_text": ban}
    except Exception as e:
        return {"caption": f"{headline}\n\n#govtjobs #recruitment #competitiveexams", "banner_text": topic.upper(), "error": str(e)}


async def gen_banner_image(banner_text: str, topic: str) -> str | None:
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ["EMERGENT_LLM_KEY"]
        chat = LlmChat(api_key=key, session_id=f"banner-{uuid.uuid4()}",
                       system_message="You generate eye-catching educational social media banner images.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
        prompt = (f"Create a vibrant 1200x630 social media banner. Bold text overlay: '{banner_text}'. "
                  f"Theme: {topic}. Style: clean modern Indian education branding, blue and white palette, "
                  f"professional, eye-catching. No watermarks.")
        _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
        if images:
            img = images[0]
            return img.get("data") if isinstance(img, dict) else getattr(img, "data", None)
        return None
    except Exception as e:
        logger.error(f"gen_banner_image failed: {e}")
        return None


class GenerateIn(BaseModel):
    topics: list[str] | None = None
    auto_publish: bool = False


def build_social_router(db, get_current_user, get_creds):
    router = APIRouter(prefix="/api/social", tags=["social"])

    async def _content_cfg() -> dict:
        doc = await db.app_config.find_one({"key": "content_config"})
        cfg = (doc or {}).get("value") or {}
        return {
            "search_keywords": cfg.get("search_keywords") or DEFAULT_KEYWORDS,
            "search_sources": cfg.get("search_sources") or DEFAULT_SOURCES,
            "interval_hours": int(cfg.get("interval_hours", 1) or 1),
            "enabled": bool(cfg.get("enabled", False)),
            "auto_publish": bool(cfg.get("auto_publish", False)),
            "last_run": cfg.get("last_run"),
        }

    async def _generate_one(topic: str) -> dict:
        cfg = await _content_cfg()
        news = await fetch_news(topic, cfg["search_sources"], limit=3)
        headline = news[0]["title"] if news else f"Latest update on {topic}"
        text = await gen_post_text(topic, headline)
        image_b64 = await gen_banner_image(text["banner_text"], topic)
        doc = {
            "id": str(uuid.uuid4()), "topic": topic, "headline": headline,
            "news_link": news[0]["link"] if news else "",
            "caption": text["caption"], "banner_text": text["banner_text"],
            "image_b64": image_b64, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.social_posts.insert_one(doc)
        d = {**doc}; d.pop("_id", None)
        return d

    async def _public_base_url() -> str:
        cfg = await db.app_config.find_one({"key": "public_base_url"})
        return (cfg or {}).get("value", "")

    async def _do_publish(p: dict, targets: set, base: str = "", user: dict = None) -> dict:
        results = {}
        fb = await get_creds(db, "facebook")
        igc = await get_creds(db, "instagram")
        page_id = fb.get("page_id"); tok = fb.get("page_access_token")
        ig_id = igc.get("ig_business_account_id"); ig_tok = igc.get("fb_page_access_token") or tok
        if not base:
            base = await _public_base_url()
        image_url = f"{base}/api/social/image/{p['id']}" if (base and p.get("image_b64")) else None

        if "facebook" in targets:
            if not (page_id and tok):
                results["facebook"] = "not_configured"
            else:
                try:
                    async with httpx.AsyncClient(timeout=25) as c:
                        if p.get("image_b64"):
                            files = {"source": ("banner.png", base64.b64decode(p["image_b64"]), "image/png")}
                            data = {"caption": p["caption"], "access_token": tok}
                            r = await c.post(f"{GRAPH}/{page_id}/photos", data=data, files=files)
                        else:
                            r = await c.post(f"{GRAPH}/{page_id}/feed",
                                             params={"message": p["caption"], "access_token": tok})
                        r.raise_for_status()
                        results["facebook"] = {"status": "published", **r.json()}
                except Exception as e:
                    results["facebook"] = f"error: {getattr(e, 'response', None) and e.response.text or e}"

        if "instagram" in targets:
            if not (ig_id and ig_tok):
                results["instagram"] = "not_configured"
            elif not image_url:
                results["instagram"] = "needs_image"  # IG requires a public image; generate a banner first
            else:
                try:
                    async with httpx.AsyncClient(timeout=40) as c:
                        cr = await c.post(f"{GRAPH}/{ig_id}/media",
                                          params={"image_url": image_url, "caption": p["caption"], "access_token": ig_tok})
                        cr.raise_for_status()
                        creation_id = cr.json().get("id")
                        pub = await c.post(f"{GRAPH}/{ig_id}/media_publish",
                                           params={"creation_id": creation_id, "access_token": ig_tok})
                        pub.raise_for_status()
                        results["instagram"] = {"status": "published", **pub.json()}
                except Exception as e:
                    results["instagram"] = f"error: {getattr(e, 'response', None) and e.response.text or e}"

        now = datetime.now(timezone.utc).isoformat()
        await db.social_posts.update_one({"id": p["id"]},
            {"$set": {"status": "published", "publish_result": results, "published_at": now}})
        await db.social_publish_history.insert_one({
            "id": str(uuid.uuid4()), "post_id": p["id"], "topic": p.get("topic"),
            "caption": (p.get("caption") or "")[:200], "targets": list(targets),
            "results": results, "published_by": (user or {}).get("name", "system"),
            "published_at": now})
        return results

    @router.post("/generate")
    async def generate(payload: GenerateIn, user=Depends(get_current_user)):
        cfg = await _content_cfg()
        topics = payload.topics or cfg["search_keywords"]
        out = []
        for t in topics[:6]:
            try: out.append(await _generate_one(t))
            except Exception as e: out.append({"topic": t, "error": str(e)})
        return {"generated": len(out), "posts": out}

    @router.get("/posts")
    async def list_posts(status: str = "pending", user=Depends(get_current_user)):
        docs = await db.social_posts.find({"status": status}).sort("created_at", -1).to_list(200)
        for d in docs: d.pop("_id", None)
        return docs

    @router.patch("/posts/{post_id}")
    async def edit_post(post_id: str, payload: dict, user=Depends(get_current_user)):
        upd = {k: v for k, v in payload.items() if k in {"caption", "banner_text"}}
        res = await db.social_posts.find_one_and_update({"id": post_id}, {"$set": upd}, return_document=True)
        if not res: raise HTTPException(404, "Not found")
        res.pop("_id", None); return res

    @router.post("/posts/{post_id}/regenerate")
    async def regen(post_id: str, user=Depends(get_current_user)):
        old = await db.social_posts.find_one({"id": post_id})
        if not old: raise HTTPException(404, "Not found")
        new = await _generate_one(old["topic"])
        await db.social_posts.update_one({"id": post_id}, {"$set": {"status": "regenerated"}})
        return new

    @router.post("/posts/{post_id}/reject")
    async def reject(post_id: str, user=Depends(get_current_user)):
        await db.social_posts.update_one({"id": post_id}, {"$set": {"status": "rejected"}})
        return {"ok": True}

    @router.post("/posts/{post_id}/publish")
    async def publish(post_id: str, payload: dict, request: Request, user=Depends(get_current_user)):
        targets = set(payload.get("targets", ["facebook", "instagram"]))
        p = await db.social_posts.find_one({"id": post_id})
        if not p: raise HTTPException(404, "Not found")
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        base = f"{proto}://{host}"
        await db.app_config.update_one({"key": "public_base_url"},
                                       {"$set": {"key": "public_base_url", "value": base}}, upsert=True)
        results = await _do_publish(p, targets, base=base, user=user)
        return {"ok": True, "results": results}

    @router.get("/image/{post_id}")
    async def post_image(post_id: str):
        p = await db.social_posts.find_one({"id": post_id})
        if not p or not p.get("image_b64"):
            raise HTTPException(404, "No image")
        data = base64.b64decode(p["image_b64"])
        mime = "image/jpeg" if p["image_b64"].startswith("/9j/") else "image/png"
        return Response(content=data, media_type=mime)

    @router.get("/history")
    async def publish_history(user=Depends(get_current_user)):
        docs = await db.social_publish_history.find({}).sort("published_at", -1).to_list(200)
        for d in docs: d.pop("_id", None)
        return docs

    @router.get("/topics")
    async def topics(user=Depends(get_current_user)):
        cfg = await _content_cfg()
        return {"topics": cfg["search_keywords"]}

    @router.post("/topics")
    async def set_topics(payload: dict, user=Depends(get_current_user)):
        kws = payload.get("topics", [])
        doc = await db.app_config.find_one({"key": "content_config"})
        val = (doc or {}).get("value") or {}
        val["search_keywords"] = kws
        await db.app_config.update_one({"key": "content_config"}, {"$set": {"value": val}}, upsert=True)
        return {"ok": True, "topics": kws}

    # ---- Background scheduler (interval-driven, toggleable from Settings) ----
    async def scheduler_loop():
        while True:
            try:
                await asyncio.sleep(60)
                cfg = await _content_cfg()
                if not cfg["enabled"]:
                    continue
                interval = max(1, cfg["interval_hours"]) * 3600
                last = cfg.get("last_run")
                if last:
                    try:
                        last_ts = datetime.fromisoformat(last)
                        if (datetime.now(timezone.utc) - last_ts).total_seconds() < interval:
                            continue
                    except Exception:
                        pass
                posts = []
                for t in (cfg["search_keywords"] or DEFAULT_KEYWORDS)[:5]:
                    try: posts.append(await _generate_one(t))
                    except Exception: pass
                doc = await db.app_config.find_one({"key": "content_config"})
                val = (doc or {}).get("value") or {}
                val["last_run"] = datetime.now(timezone.utc).isoformat()
                await db.app_config.update_one({"key": "content_config"}, {"$set": {"value": val}}, upsert=True)
                if cfg["auto_publish"]:
                    for p in posts:
                        try: await _do_publish(p, {"facebook", "instagram"})
                        except Exception: pass
            except Exception:
                await asyncio.sleep(60)

    def start_scheduler():
        return asyncio.create_task(scheduler_loop())

    router.start_scheduler = start_scheduler
    return router
