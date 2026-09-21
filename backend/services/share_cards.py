"""Win-to-Share cards — a branded PNG a user can post to Facebook / Instagram
after a win (referral bonus or a game prize). Rendered with Pillow at the
1200×630 OG ratio, persisted to object storage (Tigris in prod), and served
back through a public proxy so link-preview scrapers can fetch it."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from services.object_storage import get_storage

FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

W, H = 1200, 630


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _center(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
            y: int, fill, max_w: int = W - 120) -> None:
    text = (text or "").strip()
    if not text:
        return
    # Simple ellipsis truncation so a long line never runs off the card.
    while draw.textlength(text, font=font) > max_w and len(text) > 4:
        text = text[:-2]
    if draw.textlength((text or ""), font=font) > max_w:
        text = text[:-1] + "…"
    tw = draw.textlength(text, font=font)
    draw.text(((W - tw) / 2, y), text, font=font, fill=fill)


def render_win_card_png(title: str, prize: str, subtitle: str = "") -> bytes:
    img = Image.new("RGB", (W, H), "#0b0c16")
    d = ImageDraw.Draw(img)
    # Vertical purple→pink→dark gradient.
    top = (24, 16, 46)
    bot = (11, 12, 22)
    for i in range(H):
        t = i / H
        d.line([(0, i), (W, i)],
               fill=(int(top[0] + (bot[0] - top[0]) * t),
                     int(top[1] + (bot[1] - top[1]) * t),
                     int(top[2] + (bot[2] - top[2]) * t)))
    # Accent bar.
    d.rectangle([0, 0, W, 10], fill=(168, 85, 247))
    _center(d, "FUUSIC", _font(FONT_BOLD, 56), 74, (216, 180, 254))
    _center(d, title or "I just won on FUUSIC!", _font(FONT_BOLD, 48), 190, (255, 255, 255))
    if prize:
        _center(d, prize, _font(FONT_BOLD, 108), 268, (236, 72, 153))
    if subtitle:
        _center(d, subtitle, _font(FONT_REG, 36), 430, (206, 206, 220))
    _center(d, "Play together · win together", _font(FONT_REG, 30), 548, (150, 150, 170))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def create_share_card(db, *, user_id: str, kind: str, title: str,
                            prize: str = "", subtitle: str = "") -> dict:
    card_id = f"scard_{uuid.uuid4().hex[:16]}"
    key = f"social/share_cards/{card_id}.png"
    png = render_win_card_png(title, prize, subtitle)
    try:
        get_storage().upload_bytes(key=key, data=png, content_type="image/png")
    except Exception:
        # Record the doc anyway; the image proxy degrades to 404 if missing.
        pass
    doc = {"_id": card_id, "user_id": user_id, "kind": kind, "title": title,
           "prize": prize, "subtitle": subtitle, "storage_key": key,
           "created_at": datetime.now(timezone.utc)}
    await db.share_cards.insert_one(doc)
    return doc
