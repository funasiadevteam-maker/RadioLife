"""
Phase 16-prep — Channel thumbnail service.

Generates movie-poster-collage artwork for every channel via Google
Gemini's Nano Banana image model (`gemini-2.5-flash-image-preview`)
through the Emergent universal key. Files land under
`/app/backend/static/channel_thumbnails/<slug>.webp` and the channels
collection is backfilled with `thumbnail_url` + `thumbnail_prompt`
plus an idempotent `_channel_thumbnails_v1` sentinel.

Public surface:
    THUMBNAIL_PROMPTS              — slug → prompt dict (13 channels)
    ensure_thumbnails(db)          — boot-time idempotent generator
    regenerate_one(db, slug, prompt=None) — admin re-roll
    public_url(slug)               — URL string for the channels API
"""
from __future__ import annotations
import asyncio
import base64
import io
import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image

logger = logging.getLogger("bigfm.thumbnails")

THUMB_DIR = Path("/app/backend/static/channel_thumbnails")
THUMB_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_PREFIX = "/api/static/channel_thumbnails"
MIGRATION_FLAG = "_channel_thumbnails_v1"

# Movie-poster-collage prompts — one per channel slug. Each ends with the
# `no text` directive because text-in-image generation almost always
# hallucinates garbled letters; the channel name will be overlaid in CSS.
THUMBNAIL_PROMPTS: dict[str, str] = {
    "vip_lounge": (
        "Luxury movie-poster collage: champagne flutes, gold velvet booth, "
        "neon 'VIP' sign (only the letters V-I-P, decorative, blurred), "
        "silhouette of a saxophonist, deep purple and gold palette, subtle "
        "film grain, cinematic lighting, premium nightlife aesthetic, "
        "square composition, no text other than V-I-P sign"),
    "premium_mehfil": (
        "Classical Indian poetry mehfil collage: oil lamps, sitars, vintage "
        "Lucknow miniature painting style, gold leaf, deep maroon and emerald, "
        "urdu calligraphy ornaments (non-readable decorative shapes only), "
        "candlelit warmth, square composition, no text"),
    "bollywood_mehfil": (
        "Bollywood movie-poster collage: glittery dance floor, neon Hindi "
        "film-style title cards (decorative only, no real text), saree "
        "dupatta sweep, dholki silhouette, hot pink + electric blue + gold "
        "palette, retro 90s Bollywood vibe, square composition, no text"),
    "party_dubai": (   # Party Mix (channel id legacy)
        "EDM party movie-poster collage: laser beams, confetti, raised hands "
        "silhouette, glowing DJ booth, cyan + magenta + UV purple, high "
        "contrast, energetic motion blur, festival main-stage feel, square "
        "composition, no text"),
    "late_night_drive": (
        "Nighttime highway movie-poster collage: car taillights streaking, "
        "rain on windshield, city skyline blur, lone driver silhouette, "
        "deep blue + amber palette, lo-fi cinematic mood, neo-noir aesthetic, "
        "square composition, no text"),
    "punjabi_beats": (
        "Punjabi bhangra movie-poster collage: dhol drums, turban silhouettes "
        "mid-dance, mustard yellow + electric green + crimson, sarson fields "
        "blur, gold jewelry sparkle, high-energy folk-festival vibe, square "
        "composition, no text"),
    "morning_masala": (
        "Sunrise breakfast movie-poster collage: steaming chai cup, "
        "newspaper, parathas, golden-hour sun rays, warm orange + cream + "
        "green palette, cozy domestic morning feel, soft watercolor edges, "
        "square composition, no text"),
    "devotional_hour": (
        "Sacred devotional collage: brass diya lamps, marigold garlands, "
        "lotus, soft incense smoke, deep saffron + ivory + maroon, temple "
        "bell silhouette, serene reverent mood, painterly style, square "
        "composition, no text"),
    "retro_lounge": (
        "Retro 70s/80s movie-poster collage: vinyl record stack, vintage "
        "cassette tape, palm-tree neon sign, sunset gradient orange-pink-"
        "purple, disco ball glint, Miami Vice aesthetic, square composition, "
        "no text"),
    "workout_wala": (
        "High-intensity workout movie-poster collage: dumbbell silhouette, "
        "sweat-drip motion lines, treadmill blur, glowing red + electric "
        "yellow palette, gym-floor neon, gritty performance-poster feel, "
        "square composition, no text"),
    "diamond_room": (
        "Hip-hop / rap movie-poster collage: diamond grills sparkle, gold "
        "chain layers, blacked-out luxury car, smoke wisps, midnight black "
        "+ diamond white + neon teal accent, modern trap-aesthetic poster, "
        "square composition, no text"),
    # Phase 15d.1 — regional variants (city-text removed Phase 41 P1).
    # Visuals must NOT identify any specific city — no landmarks, no
    # storefront signage, no city skylines. Branding is BigFM + channel
    # name only, overlaid in CSS by the frontend.
    "dfw_bollywood_drive": (
        "Bollywood highway movie-poster collage: empty open highway "
        "vanishing point at sunset, saree sweep mid-twirl, neon Hindi "
        "film-style title-card SHAPES (decorative shapes only, NO letters, "
        "NO words, NO writing, NO signage), generic highway shoulder "
        "without buildings, hot pink + saffron + sunset orange + cobalt "
        "blue palette, glamour-cinema lighting, square composition. "
        "ABSOLUTELY NO text, NO city names, NO landmarks, NO real-world "
        "storefronts, NO billboards, NO street signs, NO recognizable "
        "skyline or tower silhouettes"),
    "dfw_garba_nights": (
        "Gujarati Garba night movie-poster collage: dandiya sticks crossed, "
        "lehenga whirl mid-spin, marigold strings overhead, glowing "
        "festival lanterns on a clean dark backdrop (no buildings, no "
        "storefronts), deep navy + saffron + emerald + warm gold palette, "
        "festival lantern glow, painterly movement, square composition. "
        "ABSOLUTELY NO text, NO city names, NO storefronts, NO street "
        "signs, NO signage with letters of any kind"),
}


def public_url(slug: str) -> str:
    """Public URL the frontend embeds in <img src>."""
    return f"{PUBLIC_PREFIX}/{slug}.webp"


def _file_path(slug: str) -> Path:
    return THUMB_DIR / f"{slug}.webp"


async def _generate_image_bytes(prompt: str) -> bytes | None:
    """Call Gemini Nano Banana once, return raw PNG bytes from the model
       (or None on failure)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        logger.warning("[thumbnails] EMERGENT_LLM_KEY not set; cannot generate")
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        logger.error("[thumbnails] emergentintegrations import failed: %s", e)
        return None
    try:
        chat = (LlmChat(api_key=api_key,
                                  session_id=f"thumb-{prompt[:20].replace(' ', '')}",
                                  system_message="You generate 1024x1024 channel artwork.")
                      .with_model("gemini", "gemini-2.5-flash-image")
                      .with_params(modalities=["image", "text"]))
        msg = UserMessage(text=prompt)
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            logger.warning("[thumbnails] no image returned for prompt[:60]=%s",
                                  prompt[:60])
            return None
        return base64.b64decode(images[0]["data"])
    except Exception as e:
        logger.error("[thumbnails] gemini call failed: %s", e)
        return None


def _save_as_webp(image_bytes: bytes, slug: str) -> Path | None:
    """Convert returned PNG/JPEG bytes to webp on disk (smaller, sharper)."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        # Centre-crop to square if the model didn't return a square.
        w, h = img.size
        if w != h:
            side = min(w, h)
            left = (w - side) // 2
            top  = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
        # Downscale to 1024 max (the model sometimes returns 1024, sometimes 2048).
        if img.width > 1024:
            img = img.resize((1024, 1024), Image.LANCZOS)
        out = _file_path(slug)
        img.save(out, format="WEBP", quality=82, method=6)
        return out
    except Exception as e:
        logger.error("[thumbnails] webp encode failed for %s: %s", slug, e)
        return None


async def _generate_one(slug: str, prompt: str) -> Path | None:
    raw = await _generate_image_bytes(prompt)
    if not raw:
        return None
    return _save_as_webp(raw, slug)


async def ensure_thumbnails(db) -> dict:
    """Boot-time idempotent. Walks THUMBNAIL_PROMPTS. For each channel that
       (a) exists in DB and (b) hasn't been backfilled (no MIGRATION_FLAG),
       generate the image and stamp `thumbnail_url` + `thumbnail_prompt`."""
    out = {"generated": 0, "skipped": 0, "failed": 0, "failed_slugs": []}
    for slug, prompt in THUMBNAIL_PROMPTS.items():
        ch = await db.channels.find_one({"_id": slug})
        if not ch:
            out["skipped"] += 1
            continue
        already_on_disk = _file_path(slug).exists()
        already_stamped = bool(ch.get(MIGRATION_FLAG))
        if already_on_disk and already_stamped and ch.get("thumbnail_url"):
            out["skipped"] += 1
            continue
        if not already_on_disk:
            logger.info("[thumbnails] generating slug=%s prompt[:60]=%s",
                              slug, prompt[:60])
            written = await _generate_one(slug, prompt)
            if not written:
                out["failed"] += 1
                out["failed_slugs"].append(slug)
                continue
        url = public_url(slug)
        await db.channels.update_one(
            {"_id": slug},
            {"$set": {
                "thumbnail_url":   url,
                "thumbnail_prompt": prompt,
                MIGRATION_FLAG:     True,
            }},
        )
        out["generated"] += 1
    logger.info("[thumbnails] ensure_thumbnails done: %s", out)
    return out


async def regenerate_one(db, channel_id: str, prompt_override: str | None = None) -> dict:
    """Admin re-roll. Uses the saved `thumbnail_prompt` if no override given
       (so the admin can just re-roll the same prompt to get a fresh variant)."""
    ch = await db.channels.find_one({"_id": channel_id})
    if not ch:
        return {"ok": False, "error": "channel_not_found"}
    prompt = (prompt_override
                    or ch.get("thumbnail_prompt")
                    or THUMBNAIL_PROMPTS.get(channel_id))
    if not prompt:
        return {"ok": False, "error": "no_prompt_available"}
    # Force regeneration — delete the file first so the encoder writes fresh.
    fp = _file_path(channel_id)
    try:
        if fp.exists(): fp.unlink()
    except Exception: pass
    written = await _generate_one(channel_id, prompt)
    if not written:
        return {"ok": False, "error": "generation_failed"}
    url = public_url(channel_id)
    await db.channels.update_one(
        {"_id": channel_id},
        {"$set": {"thumbnail_url": url, "thumbnail_prompt": prompt,
                        MIGRATION_FLAG: True}},
    )
    return {"ok": True, "thumbnail_url": url, "thumbnail_prompt": prompt}
