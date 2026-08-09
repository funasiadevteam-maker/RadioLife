"""Phase K.7c — Per-instance game thumbnail auto-generation.

Public entry points:

    fire_thumbnail_task(db, campaign_id, *, force=False) -> None
        Schedules a background asyncio task that generates a unique
        cinematic thumbnail for the game and persists it on the
        `game_campaigns` row.  Non-blocking — safe to call right after
        `insert_one(doc)` so the caller can return immediately.

    generate_thumbnail_sync(db, campaign_id, *, force=False) -> dict
        Synchronous variant used by the backfill script.

Per-instance prompt is built from `title + template + prize titles +
sponsor name`.  Falls back gracefully to the K.7 per-type generic image
when generation fails (so cards never render blank).
"""
from __future__ import annotations
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger("bigfm.game_thumbnails")

STATIC_DIR = Path("/app/backend/static/game_thumbnails")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

TYPE_FALLBACK = {
    "tpl_spin_wheel": "/api/static/landing_images/game_spin_wheel.png",
    "spin_wheel":          "/api/static/landing_images/game_spin_wheel.png",
    "tpl_quiz":              "/api/static/landing_images/game_music_trivia.png",
    "trivia":                  "/api/static/landing_images/game_music_trivia.png",
    "tpl_scratch":          "/api/static/landing_images/game_scratch_card.png",
    "tpl_lucky_draw":  "/api/static/landing_images/game_lucky_draw.png",
    "tpl_predict":          "/api/static/landing_images/game_predict_win.png",
    "tpl_lyric":              "/api/static/landing_images/game_lyric_hunt.png",
}

_BRAND_SUFFIX = ("Dark cinematic premium photography, neon magenta + cyan + "
                              "deep purple RadioLife brand palette, soft depth of field, "
                              "no text or logos visible. Square 1:1 frame.")


def _slug(s: str) -> str:
    s = (s or "").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "game"


def _type_token(template_id: Optional[str]) -> str:
    if not template_id:
        return "game"
    t = template_id.lower()
    if "spin" in t:        return "spin wheel"
    if "scratch" in t:    return "scratch card"
    if "quiz" in t or "trivia" in t:  return "trivia quiz"
    if "lyric" in t:        return "lyric hunt"
    if "predict" in t:    return "prediction"
    if "lucky" in t or "draw" in t:  return "lucky draw"
    return "game"


def _build_prompt(*, title: str, template_id: Optional[str],
                              prize_titles: list, sponsor_name: Optional[str]) -> str:
    gtype = _type_token(template_id)
    prize_str = ""
    if prize_titles:
        # Truncate to 3 prizes for prompt sanity
        joined = ", ".join(p for p in prize_titles[:3] if p)
        if joined:
            prize_str = f", themed around the prize: {joined}"
    sponsor = (f" sponsored by {sponsor_name}"
                        if sponsor_name and sponsor_name.lower() != "house"
                        else "")
    return (f"Cinematic editorial photograph evoking the game '{title}'"
                  f"{sponsor} — a {gtype}{prize_str}. {_BRAND_SUFFIX}")


def _fallback_for(template_id: Optional[str]) -> str:
    if not template_id:
        return "/api/static/landing_images/game_default.png"
    return (TYPE_FALLBACK.get(template_id)
                  or TYPE_FALLBACK.get(template_id.replace("tpl_", ""))
                  or "/api/static/landing_images/game_default.png")


async def _resolve_prize_titles(db, campaign_id: str) -> list:
    out: list = []
    async for p in db.game_prizes.find(
            {"campaign_id": campaign_id}, {"title": 1}).limit(3):
        if p.get("title"):
            out.append(p["title"])
    return out


async def _resolve_sponsor(db, campaign_id: str) -> Optional[str]:
    doc = await db.game_campaigns.find_one(
        {"_id": campaign_id}, {"sponsor_name": 1, "business_id": 1}) or {}
    if doc.get("sponsor_name"):
        return doc["sponsor_name"]
    biz_id = doc.get("business_id")
    if biz_id:
        biz = await db.businesses.find_one({"_id": biz_id},
                                                                    {"name": 1}) or {}
        return biz.get("name")
    return None


async def generate_thumbnail_sync(db, campaign_id: str, *,
                                                                  force: bool = False) -> dict:
    """Generates AND persists a per-instance thumbnail.  Returns the
    full result dict including the resulting URL or fallback."""
    camp = await db.game_campaigns.find_one({"_id": campaign_id}) \
              or await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not camp:
        return {"ok": False, "reason": "campaign_not_found"}
    existing = camp.get("thumbnail_url") or ""
    template_id = camp.get("template_id") or camp.get("template_type")
    is_generic = (existing.startswith("/api/static/landing_images/game_")
                              and existing != _fallback_for(template_id))
    # Skip if already has a non-generic per-instance thumbnail.
    already_per_instance = (existing
                                                  and existing.startswith("/api/static/game_thumbnails/"))
    if already_per_instance and not force:
        return {"ok": True, "skipped": "already_set",
                      "url": existing}

    title = camp.get("title") or "RadioLife Game"
    sponsor = await _resolve_sponsor(db, campaign_id)
    prize_titles = await _resolve_prize_titles(db, campaign_id)
    prompt = _build_prompt(title=title, template_id=template_id,
                                                  prize_titles=prize_titles,
                                                  sponsor_name=sponsor)

    fname = f"{_slug(title)}_{campaign_id[-8:]}.png"
    disk = STATIC_DIR / fname
    api_path = f"/api/static/game_thumbnails/{fname}"

    if not disk.exists() or force:
        try:
            from services.openai_image_provider import generate_image
            raw = await generate_image(prompt, size="1024x1024",
                                                                quality="standard")
            disk.write_bytes(raw)
            log.info("[game_thumb] generated %s (%d KB) for camp=%s",
                            fname, len(raw) // 1024, campaign_id)
        except Exception as e:
            # Persist the generic fallback so the card never renders blank.
            fallback = _fallback_for(template_id)
            await db.game_campaigns.update_one(
                {"_id": campaign_id},
                {"$set": {"thumbnail_url": fallback,
                              "thumbnail_status": "fallback",
                              "thumbnail_error": str(e)[:200]}})
            log.warning("[game_thumb] gen failed camp=%s err=%s → fallback",
                                  campaign_id, e)
            return {"ok": False, "url": fallback,
                          "fallback": True, "error": str(e)[:200]}

    await db.game_campaigns.update_one(
        {"_id": campaign_id},
        {"$set": {"thumbnail_url": api_path,
                      "thumbnail_status": "generated",
                      "thumbnail_prompt": prompt[:400]}})
    # Also fan-out onto the base `games` row if one matches by title.
    return {"ok": True, "url": api_path}


def fire_thumbnail_task(db, campaign_id: str, *, force: bool = False) -> None:
    """Schedule background generation.  Non-blocking.  Safe to call
    immediately after game_campaigns.insert_one()."""
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(generate_thumbnail_sync(db, campaign_id, force=force))
    except Exception as e:
        log.warning("[game_thumb] could not schedule task camp=%s err=%s",
                            campaign_id, e)


__all__ = [
    "fire_thumbnail_task", "generate_thumbnail_sync",
    "TYPE_FALLBACK", "_fallback_for",
]
