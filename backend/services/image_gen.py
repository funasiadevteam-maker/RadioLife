"""Phase C — OpenAI gpt-image-1 station artwork generator.

Provider chain (per the Phase C brief, OpenAI-only update):
    1. OpenAI gpt-image-1 (primary) via emergentintegrations
    2. deterministic gradient fallback (final — no image saved)

Cache strategy:
    - SHA256(prompt + model + size) → key.  Re-generating the same
      prompt returns the cached file instantly with zero API cost.
    - On-disk cache lives at /app/backend/static/station_artwork/.
    - Mongo `image_gen_cache` keeps the prompt → file_name mapping
      so we can dedupe across stations even when slugs differ.

Rate-limiting:
    - 5 generations / rolling hour for free tier.
    - 20 / rolling hour for premium.
    - Tracked in `image_gen_rate_log` (per-user, TTL-indexed).

The image bytes are returned by the Emergent OpenAI wrapper as PNG;
we re-encode to WebP for ~80% smaller payloads on the wire.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from PIL import Image

log = logging.getLogger("bigfm.image_gen")

ART_DIR = Path("/app/backend/static/station_artwork")
ART_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_PREFIX = "/api/static/station_artwork"

# Per-tier hourly quota.  Caps are intentionally generous — the
# bottleneck is OpenAI's per-org RPM, not our budget.
RATE_LIMITS = {"free": 5, "premium": 20, "admin": 100}
RATE_WINDOW = timedelta(hours=1)

DEFAULT_MODEL = "gpt-image-1"
DEFAULT_SIZE  = "1024x1024"


# ─── Prompt-hash cache key ──────────────────────────────────────────────
def cache_key(prompt: str, *, model: str = DEFAULT_MODEL,
                  size: str = DEFAULT_SIZE) -> str:
    h = hashlib.sha256(f"{model}|{size}|{prompt}".encode("utf-8")).hexdigest()
    return h[:24]    # 24 hex chars is plenty for collision avoidance


def cache_file(key: str) -> Path:
    return ART_DIR / f"{key}.webp"


def public_url(key: str) -> str:
    return f"{PUBLIC_PREFIX}/{key}.webp"


# ─── Rate-limit gate ────────────────────────────────────────────────────
async def check_rate_limit(db: Any, user_id: str, tier: str) -> tuple[bool, int, int]:
    """Returns (allowed, used_in_window, limit).  Caller is expected to
       handle the 429 response; we just enumerate counts here so the
       error message can be specific."""
    if not user_id:
        return True, 0, RATE_LIMITS.get(tier, 5)
    limit = RATE_LIMITS.get(tier or "free", RATE_LIMITS["free"])
    cutoff = datetime.now(timezone.utc) - RATE_WINDOW
    used = await db.image_gen_rate_log.count_documents({
        "user_id": user_id, "ts": {"$gte": cutoff},
    })
    return used < limit, used, limit


async def record_gen(db: Any, user_id: str, model: str, station_slug: str) -> None:
    """Drop a row on every successful or attempted generation so the
       sliding window stays honest."""
    if not user_id:
        return
    await db.image_gen_rate_log.insert_one({
        "user_id": user_id, "model": model,
        "station_slug": station_slug,
        "ts": datetime.now(timezone.utc),
    })


# ─── OpenAI provider ────────────────────────────────────────────────────
async def _generate_via_openai(prompt: str, *, model: str = DEFAULT_MODEL,
                                  size: str = DEFAULT_SIZE) -> Optional[bytes]:
    """Generate an image via OpenAI gpt-image-1.

    Provider chain (Phase 42-E2.4):
        1. `OPENAI_IMAGE_API_KEY` (dedicated, user-supplied) via direct
            OpenAI SDK — preferred when set so we don't burn through the
            shared Emergent LLM budget on artwork.
        2. `EMERGENT_LLM_KEY` via the emergentintegrations wrapper —
            legacy fallback (still useful for dev when no dedicated key
            is configured).
    """
    # ── 1. Direct OpenAI SDK with the dedicated image key ────────────
    if os.environ.get("OPENAI_IMAGE_API_KEY"):
        try:
            from services.openai_image_provider import generate_image
            return await generate_image(prompt, size=size, model=model,
                                                                  quality="standard")
        except Exception as e:
            log.error("[image_gen] direct OpenAI provider failed: %s: %s",
                              type(e).__name__, e)
            # Fall through to emergent wrapper as a safety net.

    # ── 2. Emergent universal-key wrapper (legacy) ─────────────────
    api_key = (os.environ.get("EMERGENT_LLM_KEY")
                  or os.environ.get("OPENAI_API_KEY") or "")
    if not api_key:
        log.warning("[image_gen] no api key in env; cannot generate")
        return None
    try:
        from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
    except Exception as e:
        log.error("[image_gen] emergentintegrations import failed: %s", e)
        return None
    try:
        image_gen = OpenAIImageGeneration(api_key=api_key)
        images = await image_gen.generate_images(
            prompt=prompt, model=model, number_of_images=1,
        )
        if not images:
            log.warning("[image_gen] empty image list for prompt[:60]=%s",
                              prompt[:60])
            return None
        return images[0]   # raw bytes
    except Exception as e:
        log.error("[image_gen] openai call failed: %s: %s", type(e).__name__, e)
        return None


# ─── Save helper — PNG/JPEG → WebP, square-cropped ─────────────────
def _encode_webp(raw: bytes, *, max_side: int = 1024,
                  out: Optional[Path] = None) -> Optional[Path]:
    """Decode arbitrary image bytes → centre-crop to square → resize to
       at-most ``max_side`` px → write as WebP.  Returns the on-disk path."""
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if w != h:
            s = min(w, h)
            left = (w - s) // 2; top = (h - s) // 2
            img = img.crop((left, top, left + s, top + s))
        if img.width > max_side:
            img = img.resize((max_side, max_side), Image.LANCZOS)
        if out is None:
            return None
        img.save(out, format="WEBP", quality=82, method=6)
        return out
    except Exception as e:
        log.error("[image_gen] webp encode failed: %s", e)
        return None


# ─── Public generate() — applies cache, calls provider, persists  ───
async def generate(db: Any, *, prompt: str, user_id: str = "",
                                  station_slug: str = "",
                                  tier: str = "free",
                                  bypass_rate_limit: bool = False
                                  ) -> dict[str, Any]:
    """Top-level entry point.  Returns:
       {ok, url, key, prompt, source, cached, error?}.

       ``source`` ∈ {"openai", "cached", "gradient_fallback"}.

       Callers (routes, scripts) handle the response shape directly —
       no exceptions thrown for normal failure paths.
    """
    key = cache_key(prompt)
    fp  = cache_file(key)
    # 1. Disk-level dedupe.  Cheap; ~0ms.
    if fp.is_file() and fp.stat().st_size > 0:
        return {"ok": True, "url": public_url(key), "key": key,
                  "prompt": prompt, "source": "cached", "cached": True}

    # 2. Rate-limit (only when called with a user_id — backfill scripts
    # pass empty user_id and skip the gate).
    if user_id and not bypass_rate_limit:
        allowed, used, limit = await check_rate_limit(db, user_id, tier)
        if not allowed:
            return {"ok": False, "error": "rate_limited",
                      "used": used, "limit": limit,
                      "source": "gradient_fallback", "cached": False}

    # 3. Call OpenAI.
    raw = await _generate_via_openai(prompt)
    if user_id:
        await record_gen(db, user_id, DEFAULT_MODEL, station_slug)
    if not raw:
        return {"ok": False, "error": "provider_failed",
                  "source": "gradient_fallback", "cached": False}

    # 4. Persist to disk as WebP.
    written = _encode_webp(raw, out=fp)
    if not written:
        return {"ok": False, "error": "encode_failed",
                  "source": "gradient_fallback", "cached": False}
    return {"ok": True, "url": public_url(key), "key": key,
              "prompt": prompt, "source": "openai", "cached": False}


# ─── Upload helper for user-supplied images ─────────────────────────
def persist_uploaded_bytes(raw: bytes, *, slug: str) -> Optional[dict]:
    """Sanitize + re-encode a user-uploaded image, write to disk, return
       {url, key}.  Caller validates MIME + size before calling."""
    # Slug-based key keeps owner uploads predictable (one per station,
    # overwritten when the owner uploads a new one).
    safe_slug = "".join(c for c in slug if c.isalnum() or c in "-_")[:64] or "x"
    key = f"upload-{safe_slug}"
    out = ART_DIR / f"{key}.webp"
    written = _encode_webp(raw, out=out)
    if not written:
        return None
    return {"url": public_url(key), "key": key}
