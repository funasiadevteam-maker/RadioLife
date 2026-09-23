"""Seed sample self-serve banner campaigns for the demo business directory.

Generates a per-business 600x500 banner by compositing the business name +
a category tagline + a CTA pill over a category-themed FUUSIC background
(11 AI-generated backgrounds, one per category bucket), then seeds an
active `banner_ad_campaigns` row (advertiser_id="house_sample_ads",
is_sample=True) so the advertiser rail rotation has rich, on-brand variety.

Idempotent: skips any business that already has a house sample banner, and
upserts by a deterministic _id so re-runs don't duplicate.

Run: python -m scripts.seed_sample_banners   (from /app/backend)
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

W, H = 600, 500
STATIC_DIR = Path("/app/backend/static/banners/samples")
CACHE_DIR = Path("/tmp/sample_banner_bg")

_BASE = ("https://static.prod-images.emergentagent.com/jobs/"
         "c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/")

CAT_IMAGES = {
    "restaurant":    _BASE + "1a045544c7f310068dd027a97f88dd025951a8030f95076e4b5d15b6b81eb459.jpeg",
    "fast_food":     _BASE + "c20dcbe8705d001f130d79ef2646196754e5b216038a2cef4f568e5ac52a6123.jpeg",
    "cafe":          _BASE + "d86981828c0dee87886fc8d7f4c9c616b1986b87cf375cffb9b6aeb8147413a4.jpeg",
    "dessert":       _BASE + "534a384fda369f9812d5e379ae85e3f26785db76a91fdd71efd790f711ec0e0c.jpeg",
    "fitness":       _BASE + "072cb68f8845244ba73282ed45022da128a8f875eb7bf9534579a4298a603084.jpeg",
    "beauty":        _BASE + "4a6ecc980bd7ab402f8a73cd3c119ec91c78a70d6a49147beede8673605473a3.jpeg",
    "retail":        _BASE + "3f1c258822a15c36479a1598d2d33ff0a8f72efeaf006c3506c548270f4d6e22.jpeg",
    "grocery":       _BASE + "6c3e0c433de11017af96ee4297f8944840bddd50c9537e379d46040b4f8d9f11.jpeg",
    "nightlife":     _BASE + "fbd25e57c1ad3106d5be004524713043c4b3feecb5df816737b7a34fcaddf983.jpeg",
    "entertainment": _BASE + "f7e266fb247f3ae426ff62e423621d46f5fa00a87cf3688a76143a5c3564dc77.jpeg",
    "health":        _BASE + "1027c0fa20f95ef12bebe1032f5c36e27717820d7b2833cf8c7d260b17bf718a.jpeg",
}

# raw business category -> bucket (bucket must be a CAT_IMAGES key)
BUCKET = {
    "restaurant": "restaurant", "food & dining": "restaurant",
    "fast_food": "fast_food",
    "cafe": "cafe",
    "dessert": "dessert",
    "fitness": "fitness", "gym": "fitness",
    "salon": "beauty", "beauty": "beauty", "beauty & spa": "beauty",
    "retail": "retail", "mall": "retail",
    "grocery": "grocery", "gas_station": "grocery",
    "bar": "nightlife", "club": "nightlife",
    "movie": "entertainment", "theater": "entertainment",
    "dentist": "health",
}

TAGLINE = {
    "restaurant": "Dine in or order takeaway",
    "fast_food": "Grab a quick bite today",
    "cafe": "Freshly brewed, every day",
    "dessert": "Treat yourself to something sweet",
    "fitness": "Start your fitness journey",
    "beauty": "Look and feel your best",
    "retail": "Shop the latest in store",
    "grocery": "Your everyday essentials",
    "nightlife": "Where your night begins",
    "entertainment": "Book your seats now",
    "health": "Care you can trust",
}

RAIL_SLOTS = ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3",
              "inline_mpu_1", "top_billboard"]

CYAN = (0, 217, 255)
GOLD = (255, 215, 0)
PINK = (255, 45, 149)
WHITE = (255, 255, 255)
GREY = (176, 182, 197)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "store"


def _font(path, size):
    return ImageFont.truetype(path, size)


def _fetch_bg(bucket: str) -> Image.Image:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{bucket}.jpeg"
    if not p.exists():
        r = requests.get(CAT_IMAGES[bucket], timeout=30)
        r.raise_for_status()
        p.write_bytes(r.content)
    return Image.open(p).convert("RGB")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize to fully cover w x h, crop centered."""
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _wrap(draw, text, font, max_w, max_lines=2):
    words = (text or "").split()
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = wd
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    # Ellipsis the last line if we ran out of room.
    if len(lines) == max_lines and words:
        joined = " ".join(lines)
        if draw.textlength(joined, font=font) < draw.textlength(text, font=font):
            last = lines[-1]
            while draw.textlength(last + "…", font=font) > max_w and len(last) > 3:
                last = last[:-1]
            lines[-1] = last + "…"
    return lines[:max_lines]


def render_banner(name: str, bucket: str, city: str) -> bytes:
    bg = _cover(_fetch_bg(bucket), W, H)
    img = bg.copy()
    d = ImageDraw.Draw(img, "RGBA")

    # Top scrim (for eyebrow) + strong bottom scrim (for name block).
    d.rectangle([0, 0, W, 88], fill=(10, 12, 24, 150))
    for i in range(H):
        if i < H * 0.42:
            continue
        t = (i - H * 0.42) / (H - H * 0.42)
        a = int(30 + t * 215)
        d.line([(0, i), (W, i)], fill=(6, 8, 18, a))
    # Neon accent bars.
    d.rectangle([0, 0, W, 6], fill=PINK)
    d.rectangle([0, 82, W, 88], fill=(0, 217, 255, 180))

    # Eyebrow.
    eyebrow = "N O W   O N   F U U S I C"
    d.text((28, 30), eyebrow, font=_font(FONT_BOLD, 20), fill=CYAN)

    pad = 34
    y = H - pad
    # CTA pill (bottom-left) + FUUSIC wordmark (bottom-right).
    cta = "TAP TO EXPLORE  →"
    cta_font = _font(FONT_BOLD, 22)
    cw = d.textlength(cta, font=cta_font)
    pill_h = 46
    d.rounded_rectangle([pad, y - pill_h, pad + cw + 40, y],
                        radius=23, fill=PINK)
    d.text((pad + 20, y - pill_h + 11), cta, font=cta_font, fill=WHITE)
    wm = "FUUSIC"
    wm_font = _font(FONT_BOLD, 24)
    d.text((W - pad - d.textlength(wm, font=wm_font), y - 34),
           wm, font=wm_font, fill=(216, 180, 254))
    y -= (pill_h + 22)

    # City.
    if city:
        cf = _font(FONT_REG, 22)
        d.ellipse([pad, y - 18, pad + 10, y - 8], fill=CYAN)
        d.text((pad + 20, y - 24), city, font=cf, fill=GREY)
        y -= 32

    # Tagline (gold).
    tag = TAGLINE.get(bucket, "Now on FUUSIC")
    tf = _font(FONT_REG, 26)
    d.text((pad, y - 30), tag, font=tf, fill=GOLD)
    y -= 40

    # Name (bold, up to 2 lines, bottom-anchored).
    nf = _font(FONT_BOLD, 46)
    lines = _wrap(d, name, nf, W - pad * 2, max_lines=2)
    line_h = 52
    ny = y - line_h * len(lines)
    for ln in lines:
        d.text((pad, ny), ln, font=nf, fill=WHITE)
        ny += line_h

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    # Businesses with a hand-made (non-auto) house sample banner — leave those
    # custom creatives untouched. Auto ones (this script) always regenerate.
    already = set()
    async for c in db.banner_ad_campaigns.find(
            {"advertiser_id": "house_sample_ads"}, {"business_id": 1, "_id": 1}):
        if c.get("business_id") and not str(c["_id"]).startswith("bcamp_sample_auto_"):
            already.add(c["business_id"])

    try:
        from services.object_storage import get_storage
        storage = get_storage()
    except Exception as e:
        storage = None
        print("object storage unavailable (local-only):", e)

    made = skipped = failed = 0
    slot_i = 0
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    end_iso = (now + timedelta(days=180)).isoformat()

    async for b in db.businesses.find({}):
        bid = b.get("business_id")
        name = (b.get("name") or "").strip()
        cat = (b.get("category") or "").strip().lower()
        city = (b.get("city") or "").strip()
        if not bid or not name:
            skipped += 1
            continue
        if name.upper().startswith(("TEST", "QA")):
            skipped += 1
            continue
        if bid in already:
            skipped += 1
            continue
        bucket = BUCKET.get(cat, "retail")
        try:
            png = render_banner(name, bucket, city)
            fname = f"{bid}.jpg"
            (STATIC_DIR / fname).write_bytes(png)
            key = f"static/banners/samples/{fname}"
            if storage:
                try:
                    storage.upload_bytes(key=key, data=png,
                                         content_type="image/jpeg")
                except Exception:
                    pass
            slug = b.get("slug") or _slug(name)
            slot = RAIL_SLOTS[slot_i % len(RAIL_SLOTS)]
            slot_i += 1
            cid = "bcamp_sample_auto_" + bid
            doc = {
                "_id": cid, "campaign_id": cid,
                "advertiser_id": "house_sample_ads",
                "advertiser_name": name, "sponsor_name": name,
                "business_id": bid,
                "slot_keys": [slot],
                "creative_image_url": f"/api/static/banners/samples/{fname}",
                "click_url": f"/business/{slug}",
                "start_date": now_iso, "end_date": end_iso,
                "daily_budget": 25.0, "total_budget": 250.0,
                "status": "active", "targeting_json": {},
                "frequency_cap_per_user_per_day": 1000,
                "weight": 1,
                "created_at": now_iso,
                "approved_at": now_iso, "approved_by": "seed_sample_banners",
                "rejected_reason": None, "stripe_session_id": None,
                "is_sample": True, "source": "seed_sample_banners",
                "category_bucket": bucket,
            }
            await db.banner_ad_campaigns.update_one(
                {"_id": cid}, {"$set": doc}, upsert=True)
            made += 1
        except Exception as e:
            failed += 1
            print("  FAIL", bid, name, "->", e)

    print(f"\nDONE — created/updated {made}, skipped {skipped}, failed {failed}")
    print(f"Sample banner campaigns now total: "
          f"{await db.banner_ad_campaigns.count_documents({'advertiser_id': 'house_sample_ads'})}")


if __name__ == "__main__":
    asyncio.run(main())
