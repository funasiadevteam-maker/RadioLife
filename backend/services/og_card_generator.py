"""Phase 42-E2.4 — Auto-generated "Now Playing on FUUSIC" share-card OG image.

Generates a 1200×630 PNG suitable for Open Graph + Twitter Card previews.

Public entry point:
    generate_share_card(title, subtitle, artwork_url=None,
                                                accent="default") -> bytes

Cache strategy:
    SHA1(title|subtitle|artwork_url|accent) → key.  Same context
    returns the cached PNG instantly.  Cache lives at
    /app/backend/storage/og_cards/<key>.png.

No external API.  Pillow only.  Designed to run in < 200 ms cold,
< 5 ms cached.
"""
from __future__ import annotations
import hashlib
import io
import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageFilter

log = logging.getLogger("bigfm.og_card")

OG_DIR = Path("/app/backend/storage/og_cards")
OG_DIR.mkdir(parents=True, exist_ok=True)

# 1200x630 is the canonical OG card size — supported by Twitter,
# Facebook, LinkedIn, Slack, Discord, WhatsApp.
WIDTH, HEIGHT = 1200, 630

# Font paths (system-installed Liberation faces — bundled with Debian).
FONT_BOLD     = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FONT_NARROW = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"

# FUUSIC dark-mode palette — keep this tight; the OG card has to read
# instantly even in a 150×80px chat preview.
BG_COLOR = (12, 16, 28)        # near-black with a subtle navy tint
FG_PRIMARY = (255, 255, 255)
FG_MUTED      = (180, 196, 218)
FG_TAGLINE = (130, 152, 184)

# Per-accent neon gradient stops.  The OG card renders a diagonal
# stripe in this colour on the left edge to visually tag the surface.
ACCENT_GRADIENTS = {
    "default":  [(0, 209, 255), (122, 92, 255)],     # electric → violet
    "magenta": [(255, 56, 187), (122, 56, 255)],   # pink → indigo
    "cyan":      [(0, 240, 255), (0, 120, 255)],
    "gold":      [(255, 198, 0), (255, 110, 0)],
    "lime":      [(178, 255, 80), (60, 209, 130)],
    "indigo":  [(90, 110, 255), (255, 75, 195)],
    "rose":      [(255, 90, 170), (255, 200, 90)],
    "amber":    [(255, 175, 0), (255, 70, 70)],
    "violet":  [(180, 120, 255), (0, 180, 255)],
    "electric": [(0, 209, 255), (0, 120, 255)],
}


def _cache_key(title: str, subtitle: str,
                          artwork_url: Optional[str], accent: str) -> str:
    raw = f"{title}|{subtitle}|{artwork_url or ''}|{accent}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    return OG_DIR / f"{key}.png"


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont,
                          max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        candidate = f"{cur} {w}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            cur = candidate
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fetch_artwork(url: str) -> Optional[Image.Image]:
    """Best-effort download of an artwork URL → PIL Image.  Supports both
    fully-qualified URLs and local `/api/static/...` paths (resolved
    against the local disk to avoid an HTTP round-trip)."""
    try:
        if url.startswith("/api/static/"):
            disk = Path("/app/backend/static") / url[len("/api/static/"):]
            if disk.is_file():
                return Image.open(disk).convert("RGB")
        # Local file path fallback.
        if url.startswith("/"):
            disk = Path(url)
            if disk.is_file():
                return Image.open(disk).convert("RGB")
        if url.startswith("http"):
            req = urllib.request.Request(url, headers={
                "User-Agent": "FUUSIC-OGCard/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
            return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        log.warning("[og_card] artwork fetch failed url=%s err=%s",
                            url, type(e).__name__)
    return None


def _draw_gradient_strip(canvas: Image.Image, stops: list[tuple[int,int,int]]
                                              ) -> None:
    """Paint a 16-pixel-wide vertical neon gradient on the left edge."""
    strip_w = 16
    grad = Image.new("RGB", (1, HEIGHT))
    c0, c1 = stops[0], stops[1]
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        r = int(c0[0] * (1 - t) + c1[0] * t)
        g = int(c0[1] * (1 - t) + c1[1] * t)
        b = int(c0[2] * (1 - t) + c1[2] * t)
        grad.putpixel((0, y), (r, g, b))
    grad = grad.resize((strip_w, HEIGHT))
    canvas.paste(grad, (0, 0))


def _draw_corner_glow(canvas: Image.Image, stops: list[tuple[int,int,int]]
                                          ) -> None:
    """Soft circular accent glow in the bottom-right — adds the
    "cinematic" feel without competing with the title."""
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    r0 = 280
    cx, cy = WIDTH - 180, HEIGHT - 120
    base = stops[0]
    for i in range(r0, 0, -8):
        alpha = int(180 * (1 - i / r0) ** 2)
        gdraw.ellipse([cx - i, cy - i, cx + i, cy + i],
                              fill=(base[0], base[1], base[2], alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=28))
    canvas.paste(glow, (0, 0), glow)


def generate_share_card(title: str, subtitle: str,
                                                artwork_url: Optional[str] = None,
                                                accent: str = "default") -> bytes:
    """Render → cache → return PNG bytes.  Idempotent per
    (title, subtitle, artwork_url, accent) tuple."""
    key = _cache_key(title, subtitle, artwork_url, accent)
    fp  = _cache_path(key)
    if fp.is_file() and fp.stat().st_size > 0:
        return fp.read_bytes()

    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    stops = ACCENT_GRADIENTS.get(accent, ACCENT_GRADIENTS["default"])

    # Background layers.
    _draw_corner_glow(canvas, stops)
    _draw_gradient_strip(canvas, stops)
    draw = ImageDraw.Draw(canvas)

    # Artwork inset (left-of-text), square 320×320 with rounded corners.
    art_x, art_y, art_size = 60, 150, 320
    art_img = _fetch_artwork(artwork_url) if artwork_url else None
    if art_img:
        art_img = art_img.resize((art_size, art_size), Image.LANCZOS)
        # Round the corners by masking.
        mask = Image.new("L", (art_size, art_size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, art_size, art_size], radius=28, fill=255)
        canvas.paste(art_img, (art_x, art_y), mask)
        text_x = art_x + art_size + 40
    else:
        text_x = 80

    text_w = WIDTH - text_x - 60   # right padding 60

    # ── FUUSIC word-mark / eyebrow ─────────────────────────────────
    eyebrow_font = _load_font(FONT_NARROW, 22)
    draw.text((text_x, 90), "BIGFM",
                  font=eyebrow_font, fill=(stops[0][0], stops[0][1], stops[0][2]))
    eyebrow2_font = _load_font(FONT_REGULAR, 22)
    draw.text((text_x + draw.textlength("BIGFM", font=eyebrow_font) + 14, 91),
                  "·  NOW PLAYING", font=eyebrow2_font, fill=FG_MUTED)

    # ── Title ───────────────────────────────────────────────────
    title_font = _load_font(FONT_BOLD, 64)
    title_lines = _wrap_text(title, title_font, text_w, draw)[:2]
    y_cursor = 160
    for line in title_lines:
        draw.text((text_x, y_cursor), line, font=title_font, fill=FG_PRIMARY)
        y_cursor += 78

    # ── Subtitle ─────────────────────────────────────────────────
    sub_font = _load_font(FONT_REGULAR, 30)
    sub_lines = _wrap_text(subtitle, sub_font, text_w, draw)[:2]
    y_cursor += 8
    for line in sub_lines:
        draw.text((text_x, y_cursor), line, font=sub_font, fill=FG_MUTED)
        y_cursor += 42

    # ── Footer tag-line ────────────────────────────────────────
    foot_font = _load_font(FONT_NARROW, 22)
    foot_y = HEIGHT - 60
    draw.text((text_x, foot_y), "▶  LISTEN ON BIGFM",
                  font=foot_font, fill=(stops[1][0], stops[1][1], stops[1][2]))
    url_font = _load_font(FONT_REGULAR, 20)
    foot_w = draw.textlength("▶  LISTEN ON BIGFM", font=foot_font)
    draw.text((text_x + foot_w + 16, foot_y + 2),
                  "·  bigfm.app", font=url_font, fill=FG_TAGLINE)

    # ── Persist + return ───────────────────────────────────────
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    raw = buf.getvalue()
    try:
        fp.write_bytes(raw)
    except Exception as e:
        log.warning("[og_card] failed to write cache file: %s", e)
    return raw
