"""Phase FUN.1.1 — Reconcile flagship display names + scrape logos + scrape US stream URLs.

Idempotent.  Safe to re-run.  Outputs a JSON report with lists of
`logo_fetch_failed`, `stream_url_missing`, and `renamed`.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app/backend")

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("bigfm.fun1_1")
logging.basicConfig(level=logging.INFO)


def _now(): return datetime.now(timezone.utc)


# ─── 1. Rename display names ─────────────────────────────────
RENAMES = [
    ("big-1062-uae",             "FUUSIC 106.2"),
    ("funasia-fm-dallas",     "FunAsia 104.9 FM (Dallas)"),
]


# ─── 2. Logo scrape sources ────────────────────────────────
LOGO_SOURCES = [
    ("talk-1003-uae",           "https://talk1003.ae/",             None),
    ("luv-1071-uae",             "https://luv1071.com/",             None),
    ("big-1062-uae",             "https://big1062.com/",             None),
    ("beat-978-uae",             "https://funasia.net/",             None),
    ("beat-anthems",           None,                                              "beat-978-uae"),  # reuse Beat 97.8
    ("urban-beat",                 "https://funasia.net/",             None),
    ("chilled-luv",                 "https://funasia.net/",             None),
    ("vanakkam-fm-us",         "https://vanakkamfm.net/",       None),
    ("apna-punjab-us",         "https://apnapunjab.net/",       None),
    ("telugu-sangam-us",     "https://telugusangam.net/",   None),
    ("funasia-fm-dallas",     "https://funasia.net/",             None),
]


# ─── 3. Stream URL scrape targets ─────────────────────────────
STREAM_SOURCES = [
    ("vanakkam-fm-us",         "https://vanakkamfm.net/"),
    ("apna-punjab-us",         "https://apnapunjab.net/"),
    ("telugu-sangam-us",     "https://telugusangam.net/"),
]


# ─── Helpers ─────────────────────────────────────────────
async def fetch_html(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True,
                    headers={"User-Agent":
                              "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0 Safari/537.36"}) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.text
    except Exception as e:
        logger.warning("[fetch] %s: %s", url, e)
    return None


async def fetch_bytes(url: str, ref: Optional[str] = None) -> Optional[bytes]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; FUUSIC/1.0)"}
        if ref:
            headers["Referer"] = ref
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True,
                                                                          headers=headers) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.content
    except Exception as e:
        logger.warning("[fetch_bytes] %s: %s", url, e)
    return None


def find_og_image(html: str, base: str) -> Optional[str]:
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html, re.IGNORECASE)
    if m:
        return _abs_url(m.group(1), base)
    return None


def find_apple_touch(html: str, base: str) -> Optional[str]:
    m = re.search(
        r'<link[^>]+rel=["\']apple-touch-icon(?:-precomposed)?["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if not m:
        m = re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']apple-touch-icon',
            html, re.IGNORECASE)
    if m:
        return _abs_url(m.group(1), base)
    return None


def find_logo_img(html: str, base: str) -> Optional[str]:
    # <img> with class/id/alt containing "logo" or "brand".
    for pat in (
        r'<img[^>]+(?:class|id)=["\'][^"\']*(?:logo|brand)[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]+(?:class|id)=["\'][^"\']*(?:logo|brand)',
        r'<img[^>]+alt=["\'][^"\']*(?:logo|brand)[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return _abs_url(m.group(1), base)
    return None


def _abs_url(u: str, base: str) -> str:
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        m = re.match(r"(https?://[^/]+)", base)
        return (m.group(1) if m else "") + u
    return base.rstrip("/") + "/" + u


def find_stream_url(html: str, base: str) -> Optional[str]:
    """Search inline JS/href/src for stream candidates."""
    patterns = [
        # streamguys or funasia
        r'https?://[^\s"\']+funasia\.streamguys1\.com/[^\s"\'<>]+',
        r'https?://[^\s"\']+streamguys[^\s"\'<>]*',
        # m3u8 / m3u / pls / mp3
        r'https?://[^\s"\'<>]+\.m3u8?',
        r'https?://[^\s"\'<>]+\.pls',
        r'https?://[^\s"\'<>]+\.mp3(?:[?][^\s"\'<>]*)?',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.IGNORECASE):
            u = m.group(0)
            # Prefer stream-like URLs (skip cover images etc).
            if any(k in u.lower() for k in ("logo", "cover", "artwork", "poster")):
                continue
            return u
    # Fallback: <source src="..."> inside <audio>
    m = re.search(
        r'<audio[^>]*>[\s\S]{0,300}<source[^>]+src=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m:
        return _abs_url(m.group(1), base)
    return None


async def resolve_playlist(url: str) -> Optional[str]:
    """If url is a .m3u/.m3u8/.pls, fetch and extract the first stream URL."""
    if not url.lower().endswith((".m3u", ".m3u8", ".pls")):
        return url
    body = await fetch_bytes(url)
    if not body:
        return None
    text = body.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("http://") or line.startswith("https://"):
            return line
        if line.startswith("File1="):
            return line.split("=", 1)[1]
    return None


# ─── Storage helpers ─────────────────────────────────────
def upload_to_tigris(image_bytes: bytes, slug: str, ext: str) -> Optional[str]:
    try:
        from services.object_storage import get_storage
        storage = get_storage()
        tmp = Path(f"/tmp/flag_logo_{slug}.{ext}")
        tmp.write_bytes(image_bytes)
        key = f"flagship_logos/{slug}.{ext}"
        ct_map = {"png": "image/png", "svg": "image/svg+xml",
                        "jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "webp": "image/webp", "ico": "image/x-icon",
                        "gif": "image/gif"}
        storage.upload(local_path=str(tmp), key=key,
                                      content_type=ct_map.get(ext.lower(), "image/png"))
        tmp.unlink(missing_ok=True)
        # Return CDN-style URL — use the Tigris endpoint + bucket + key.
        endpoint = os.environ.get("TIGRIS_ENDPOINT_URL",
                                                                    "https://fly.storage.tigris.dev")
        bucket = os.environ.get("TIGRIS_BUCKET", "bigfm-storage")
        # Tigris supports both path and virtual-host style.  Use virtual-host.
        # Bucket is public by default in fly.storage.tigris.dev.
        base = endpoint.rstrip("/")
        return f"{base}/{bucket}/{key}"
    except Exception as e:
        logger.warning("[upload] %s failed: %s", slug, e)
        return None


def image_dimensions(data: bytes) -> Optional[tuple]:
    """Cheap width/height detection for PNG/JPEG/SVG.  Returns (w,h) or None."""
    if not data or len(data) < 24:
        return None
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            import struct
            w, h = struct.unpack(">II", data[16:24])
            return (w, h)
        except Exception:
            return None
    # JPEG
    if data[:2] == b"\xff\xd8":
        try:
            # scan segments
            i = 2
            while i < len(data) - 4:
                if data[i] != 0xff:
                    return None
                m = data[i + 1]
                if 0xc0 <= m <= 0xcf and m not in (0xc4, 0xc8, 0xcc):
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    return (w, h)
                seg_len = int.from_bytes(data[i + 2:i + 4], "big")
                i += 2 + seg_len
        except Exception:
            return None
    # SVG — impose "big enough"
    if b"<svg" in data[:200].lower():
        return (300, 300)   # sentinel — svg scales
    return None


# ─── Main pipeline ──────────────────────────────────────
async def run(db) -> dict:
    report = {
        "renamed":                              [],
        "logos_uploaded":              [],
        "logo_fetch_failed":            [],
        "stream_url_updated":       [],
        "stream_url_missing":         [],
    }
    now = _now()

    # 1. Renames.
    for slug, new_name in RENAMES:
        r = await db.imported_radio_stations.update_one(
            {"flagship_slug": slug},
            {"$set": {"name": new_name, "updated_at": now}})
        if r.matched_count:
            report["renamed"].append({"slug": slug, "new_name": new_name})

    # 2. Logo scrape — sequential to respect site rate limits.
    slug_to_logo_url: dict[str, str] = {}
    for slug, source_url, reuse_slug in LOGO_SOURCES:
        if reuse_slug:
            # Reuse another station's logo URL (resolved after that slug is
            # processed).  Do this in a second pass at the end.
            continue
        logger.info("[fun1_1] scraping logo for %s from %s", slug, source_url)
        html = await fetch_html(source_url) if source_url else None
        candidate = None
        if html:
            candidate = (find_og_image(html, source_url)
                                          or find_apple_touch(html, source_url)
                                          or find_logo_img(html, source_url))
            # Try /favicon.ico as last resort
            if not candidate:
                candidate = _abs_url("/favicon.ico", source_url)
        if not candidate:
            report["logo_fetch_failed"].append(slug)
            continue
        img_bytes = await fetch_bytes(candidate, ref=source_url)
        if not img_bytes or len(img_bytes) < 500:
            report["logo_fetch_failed"].append(slug)
            continue
        dim = image_dimensions(img_bytes)
        if dim and (dim[0] < 200 or dim[1] < 200) and not candidate.endswith(".svg"):
            logger.info("[fun1_1] %s logo too small (%s) → skip", slug, dim)
            report["logo_fetch_failed"].append(slug)
            continue
        # Determine ext.
        ext = "png"
        low = candidate.lower()
        for e in ("svg", "png", "jpg", "jpeg", "webp", "gif", "ico"):
            if f".{e}" in low.split("?")[0]:
                ext = e
                break
        # Content-type sniff.
        if img_bytes[:4] == b"\x89PNG":
            ext = "png"
        elif img_bytes[:2] == b"\xff\xd8":
            ext = "jpg"
        elif b"<svg" in img_bytes[:200].lower():
            ext = "svg"
        elif img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
            ext = "webp"
        cdn_url = upload_to_tigris(img_bytes, slug, ext)
        if not cdn_url:
            report["logo_fetch_failed"].append(slug)
            continue
        slug_to_logo_url[slug] = cdn_url
        report["logos_uploaded"].append({"slug": slug, "url": cdn_url,
                                                                                  "src": candidate, "dim": dim,
                                                                                  "bytes": len(img_bytes)})

    # 2b. Reuse-pass (Beat Anthems ← Beat 97.8).
    for slug, source_url, reuse_slug in LOGO_SOURCES:
        if not reuse_slug:
            continue
        if reuse_slug in slug_to_logo_url:
            slug_to_logo_url[slug] = slug_to_logo_url[reuse_slug]
            report["logos_uploaded"].append({"slug": slug,
                                                                                      "url": slug_to_logo_url[slug],
                                                                                      "reused_from": reuse_slug})
        else:
            report["logo_fetch_failed"].append(slug)

    # 2c. Persist to DB (also stamp favicon column so the FE cards pick it up).
    for slug, url in slug_to_logo_url.items():
        await db.imported_radio_stations.update_one(
            {"flagship_slug": slug},
            {"$set": {"logo_url": url, "favicon": url, "updated_at": now}})

    # 3. Stream URL scrape for 3 US stations.
    for slug, source_url in STREAM_SOURCES:
        logger.info("[fun1_1] scraping stream for %s from %s", slug, source_url)
        html = await fetch_html(source_url)
        found = None
        if html:
            candidate = find_stream_url(html, source_url)
            if candidate:
                found = await resolve_playlist(candidate)
        if found:
            await db.imported_radio_stations.update_one(
                {"flagship_slug": slug},
                {"$set": {"url_resolved":                found,
                                  "url":                              found,
                                  "playable_status":         "pending",
                                  "needs_stream_review":  False,
                                  "updated_at":                    now}})
            report["stream_url_updated"].append({"slug": slug, "url": found})
        else:
            report["stream_url_missing"].append(slug)

    return report


if __name__ == "__main__":
    async def _cli():
        db = AsyncIOMotorClient(
            os.environ.get("MONGO_URL")
        ).get_database(os.environ.get("DB_NAME", "bigfm"))
        r = await run(db)
        print(json.dumps(r, indent=2, default=str))
    asyncio.run(_cli())
