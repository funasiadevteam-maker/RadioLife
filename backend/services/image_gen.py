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

from PIL import Image, ImageDraw, ImageFont

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


def _upload_durable(fp: Path, *, sub: str = "station_artwork") -> None:
    """Best-effort durable copy of a just-written WebP to object storage,
    using the exact key convention the `TigrisFallbackStaticFiles` reader
    expects (`static/<sub>/<file>`). Skips the write when the object is
    already present. Never raises — a durable-write miss must not fail
    generation; it just means no cross-redeploy persistence."""
    try:
        from services.object_storage import get_storage
        st = get_storage()
        key = f"static/{sub}/{fp.name}"
        if st.exists(key=key):
            return
        st.upload_bytes(key=key, data=fp.read_bytes(), content_type="image/webp")
    except Exception as e:
        log.warning("[image_gen] durable upload failed for %s: %s", fp.name, e)


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
        _upload_durable(fp)   # opportunistic backfill to durable storage
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
    _upload_durable(fp)   # survive production redeploys
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
    _upload_durable(out)   # survive production redeploys
    return {"url": public_url(key), "key": key}



# ═══════════════════════════════════════════════════════════════════
# Flagship badge compositing — draws a crisp station name + dial title
# band over an AI-generated background so the text is ALWAYS legible
# (gpt-image-1 garbles letters, so we render them ourselves in Pillow).
# The result is a single durable WebP (disk cache + object-store).
# ═══════════════════════════════════════════════════════════════════

_FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int):
    for p in _FONT_BOLD_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fit_and_wrap(draw, text: str, max_w: int, start_size: int,
                  min_size: int, max_lines: int = 2):
    """Return (font, lines) for `text` fitted within `max_w` across at
    most `max_lines`, shrinking the font until it fits.  Falls back to a
    truncated single fit with an ellipsis at the smallest size."""
    text = " ".join((text or "").split()) or "Radio"
    for size in range(start_size, min_size - 1, -4):
        font = _load_font(size)
        lines, cur, ok = [], "", True
        for word in text.split():
            trial = (cur + " " + word).strip()
            if not cur or draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
                if len(lines) >= max_lines:
                    ok = False
                    break
        if ok and cur:
            lines.append(cur)
        if ok and lines and all(draw.textlength(ln, font=font) <= max_w for ln in lines):
            return font, lines
    # Smallest-size fallback: hard-truncate with an ellipsis.
    font = _load_font(min_size)
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if not cur or draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    lines = lines[:max_lines] or [text]
    while lines and draw.textlength(lines[-1] + "…", font=font) > max_w and len(lines[-1]) > 1:
        lines[-1] = lines[-1][:-1]
    if len(" ".join(lines)) < len(text):
        lines[-1] = lines[-1].rstrip() + "…"
    return font, lines


def composite_badge_bytes(base_raw: bytes, *, name: str, dial: str = "",
                          size: int = 1024) -> Optional[bytes]:
    """Overlay a station name + dial title band onto `base_raw`.
    Returns WebP bytes, or None on failure (caller falls back to the
    plain background)."""
    try:
        img = Image.open(io.BytesIO(base_raw)).convert("RGB")
        w, h = img.size
        if w != h:
            s = min(w, h)
            left = (w - s) // 2
            top = (h - s) // 2
            img = img.crop((left, top, left + s, top + s))
        if img.width != size:
            img = img.resize((size, size), Image.LANCZOS)
        W = H = size
        base = img.convert("RGBA")

        # Bottom scrim for legibility — transparent → near-opaque ink.
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        band = int(H * 0.46)
        top_y = H - band
        for i in range(band):
            a = int(220 * (i / band) ** 1.5)
            sd.line([(0, top_y + i), (W, top_y + i)], fill=(6, 8, 22, a))
        base = Image.alpha_composite(base, scrim)
        draw = ImageDraw.Draw(base)

        pad = int(W * 0.075)
        max_text_w = W - 2 * pad
        name = (name or "Radio").strip() or "Radio"
        dial = (dial or "").strip()

        nf, nlines = _fit_and_wrap(draw, name, max_text_w, 92, 46, 2)
        n_asc, n_desc = nf.getmetrics()
        line_h = int((n_asc + n_desc) * 1.02)
        name_block_h = line_h * len(nlines)

        dial_text = dial.upper()
        pill_pad_x, pill_pad_y = 24, 12
        dial_h = 0
        df = None
        dw = 0
        if dial_text:
            df = _load_font(40)
            dw = draw.textlength(dial_text, font=df)
            d_asc, d_desc = df.getmetrics()
            dial_h = (d_asc + d_desc) + 2 * pill_pad_y
        gap = 24 if dial_text else 0
        total_h = dial_h + gap + name_block_h
        y = H - pad - total_h

        # Accent dial pill.
        if dial_text:
            accent = (245, 197, 66)
            draw.rounded_rectangle([pad, y, pad + dw + 2 * pill_pad_x, y + dial_h],
                                   radius=dial_h // 2, fill=accent)
            draw.text((pad + pill_pad_x, y + pill_pad_y), dial_text,
                      font=df, fill=(24, 18, 6))
            y += dial_h + gap

        # Station name with a dark stroke for crisp edges.
        for ln in nlines:
            draw.text((pad, y), ln, font=nf, fill=(255, 255, 255),
                      stroke_width=3, stroke_fill=(6, 8, 22))
            y += line_h

        out = base.convert("RGB")
        buf = io.BytesIO()
        out.save(buf, format="WEBP", quality=88, method=6)
        return buf.getvalue()
    except Exception as e:
        log.error("[image_gen] badge composite failed: %s", e)
        return None


def _flagship_art_key(station_id: str, name: str, dial: str) -> str:
    h = hashlib.sha256(
        f"flg|{station_id}|{name}|{dial}".encode("utf-8")).hexdigest()[:20]
    return f"flg-{h}"


def _read_base_bytes(key: str) -> Optional[bytes]:
    """Read a cached background WebP from disk; fall back to durable
    object storage when the local file is absent (fresh container)."""
    fp = cache_file(key)
    try:
        if fp.is_file() and fp.stat().st_size > 0:
            return fp.read_bytes()
    except Exception:
        pass
    try:
        import tempfile
        from services.object_storage import get_storage
        fd, tmp = tempfile.mkstemp(prefix="flgbase_")
        os.close(fd)
        get_storage().download(key=f"static/station_artwork/{key}.webp", local_path=tmp)
        data = Path(tmp).read_bytes()
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return data or None
    except Exception:
        return None


async def generate_flagship_art(db: Any, *, prompt: str, name: str, dial: str,
                                station_id: str, user_id: str = "",
                                tier: str = "free") -> dict[str, Any]:
    """Generate a no-text AI background, then overlay the station name +
    dial as a legible title band.  Returns the same shape as `generate()`
    plus a `badge` flag.  Falls back to the plain background if
    compositing fails."""
    result = await generate(db, prompt=prompt, user_id=user_id,
                            station_slug=station_id, tier=tier,
                            bypass_rate_limit=not user_id)
    if not result.get("ok"):
        return result
    base_raw = _read_base_bytes(result["key"])
    if not base_raw:
        return {**result, "badge": False}
    badged = composite_badge_bytes(base_raw, name=name, dial=dial)
    if not badged:
        return {**result, "badge": False}
    bkey = _flagship_art_key(station_id, name, dial)
    out = cache_file(bkey)
    try:
        out.write_bytes(badged)
    except Exception as e:
        log.warning("[image_gen] flagship disk write failed: %s", e)
    try:
        from services.object_storage import get_storage
        get_storage().upload_bytes(key=f"static/station_artwork/{bkey}.webp",
                                    data=badged, content_type="image/webp")
    except Exception as e:
        log.warning("[image_gen] flagship durable upload failed: %s", e)
    return {"ok": True, "url": public_url(bkey), "key": bkey,
            "source": result.get("source", "openai"), "badge": True,
            "cached": result.get("cached", False)}
