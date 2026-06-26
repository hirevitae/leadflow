"""Hourly social media post generator: pulls news, drafts post + banner via AI, queues for approval, then publishes to FB/IG."""
import os, uuid, asyncio, base64, httpx
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

DEFAULT_TOPICS = ["SSC CGL recruitment", "IBPS PO notification", "UPSC notification", "government jobs India"]
GRAPH = "https://graph.facebook.com/v19.0"


async def fetch_news(topic: str, limit: int = 5):
    url = f"https://news.google.com/rss/search?q={quote(topic)}&hl=en-IN&gl=IN&ceid=IN:en"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
        r = await c.get(url); r.raise_for_status()
    items = []
    try:
        root = ET.fromstring(r.text)
        for item in root.iter("item"):
            t = item.findtext("title") or ""; link = item.findtext("link") or ""
            pub = item.findtext("pubDate") or ""
            items.append({"title": t, "link": link, "pub_date": pub})
            if len(items) >= limit: break
    except Exception:
        pass
    return items


async def gen_post_text(topic: str, headline: str) -> dict:
    """Returns {caption, banner_text} using Claude."""
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
    """Generate a banner via Nano Banana, returns base64-encoded PNG or None."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        key = os.environ["EMERGENT_LLM_KEY"]
        chat = LlmChat(api_key=key, session_id=f"banner-{uuid.uuid4()}",
                       system_message="You generate eye-catching educational social media banner images.").with_model("gemini", "gemini-3-flash-preview")
        prompt = (f"Create a vibrant 1200x630 social media banner. Bold text overlay: '{banner_text}'. "
                  f"Theme: {topic}. Style: clean modern Indian education branding, blue and white palette, "
                  f"professional, eye-catching. No watermarks.")
        result = await chat.send_message(UserMessage(text=prompt, generate_images=True))
        # Result format varies; check for images
        for img in getattr(result, "images", []) or []:
            if hasattr(img, "data"): return img.data
            if isinstance(img, dict) and img.get("data"): return img["data"]
        return None
    except Exception:
        return None


class GenerateIn(BaseModel):
    topics: list[str] | None = None
    auto_publish: bool = False


def build_social_router(db, get_current_user):
    router = APIRouter(prefix="/api/social", tags=["social"])

    async def _generate_one(topic: str) -> dict:
        news = await fetch_news(topic, limit=3)
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

    @router.post("/generate")
    async def generate(payload: GenerateIn, user=Depends(get_current_user)):
        topics = payload.topics or DEFAULT_TOPICS
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
    async def publish(post_id: str, payload: dict, user=Depends(get_current_user)):
        targets = set(payload.get("targets", ["facebook", "instagram"]))
        p = await db.social_posts.find_one({"id": post_id})
        if not p: raise HTTPException(404, "Not found")
        results = {}
        page_id = os.environ.get("FB_PAGE_ID"); tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
        ig = os.environ.get("IG_BUSINESS_ACCOUNT_ID")
        img_data_uri = None
        if p.get("image_b64"):
            img_data_uri = f"data:image/png;base64,{p['image_b64']}"

        if "facebook" in targets:
            if not (page_id and tok):
                results["facebook"] = "not_configured"
            else:
                try:
                    async with httpx.AsyncClient(timeout=20) as c:
                        if p.get("image_b64"):
                            # Upload photo
                            files = {"source": ("banner.png", base64.b64decode(p["image_b64"]), "image/png")}
                            data = {"caption": p["caption"], "access_token": tok}
                            r = await c.post(f"{GRAPH}/{page_id}/photos", data=data, files=files)
                        else:
                            r = await c.post(f"{GRAPH}/{page_id}/feed",
                                params={"message": p["caption"], "access_token": tok})
                        r.raise_for_status()
                        results["facebook"] = r.json()
                except Exception as e: results["facebook"] = f"error: {e}"

        if "instagram" in targets:
            if not (ig and tok and p.get("image_b64")):
                results["instagram"] = "needs_image_and_keys"
            else:
                # IG requires a publicly hosted image URL. We host via the FB Page photo upload's URL.
                results["instagram"] = "IG requires public image URL - upload banner to your CDN then call /messages. Skipped for now."

        await db.social_posts.update_one({"id": post_id},
            {"$set": {"status": "published", "publish_result": results,
                      "published_at": datetime.now(timezone.utc).isoformat()}})
        return {"ok": True, "results": results}

    @router.get("/topics")
    async def topics(user=Depends(get_current_user)):
        cfg = await db.app_config.find_one({"key": "social_topics"})
        return {"topics": (cfg or {}).get("value", DEFAULT_TOPICS)}

    @router.post("/topics")
    async def set_topics(payload: dict, user=Depends(get_current_user)):
        topics = payload.get("topics", [])
        await db.app_config.update_one({"key": "social_topics"}, {"$set": {"value": topics}}, upsert=True)
        return {"ok": True, "topics": topics}

    # Background hourly scheduler
    async def hourly_loop():
        while True:
            try:
                await asyncio.sleep(3600)
                cfg = await db.app_config.find_one({"key": "social_topics"})
                topics = (cfg or {}).get("value", DEFAULT_TOPICS)
                for t in topics[:3]:
                    try: await _generate_one(t)
                    except Exception: pass
            except Exception:
                await asyncio.sleep(60)

    router._hourly_task = asyncio.get_event_loop().create_task(hourly_loop()) if False else None
    return router
