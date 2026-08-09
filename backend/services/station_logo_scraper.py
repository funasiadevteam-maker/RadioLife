"""Phase K.10 — Station logo scraper (OG image / icon discovery).

Fallback chain extension: when a station has neither `image_url` nor a
working `favicon`, scrape its homepage for an Open-Graph / Twitter /
apple-touch-icon image BEFORE falling through to AI generation.
Saves both OpenAI budget and shows the station's actual branding.

Public entry points
-------------------
    fetch_logo_from_website(homepage_url) -> bytes | None
    persist_scraped_logo(db, station_doc, raw_bytes) -> str | None
    scrape_and_persist(db, station_doc) -> dict
"""
from __future__ import annotations
import io
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

log = logging.getLogger("bigfm.station_logo_scraper")

LOGOS_DIR = Path("/app/backend/storage/station_logos_scraped")
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

UA = "RadioLifeLogoBot/1.0 (+https://bigfantv.com)"
DEFAULT_TIMEOUT = 5.0
MIN_PX = 80      # below this the asset is too low-quality to cache.
TARGET_PX = 512  # resized for the radio-card surface.

# Compiled meta extractor — keeps us free of bs4 dependency.
_META_OG = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?property\s*=\s*["\']og:image(?::secure_url)?["\']'
    r'[^>]*?content\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_META_TW = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?name\s*=\s*["\']twitter:image["\']'
    r'[^>]*?content\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_APPLE = re.compile(
    r'<link\s+(?:[^>]*?\s+)?rel\s*=\s*["\']apple-touch-icon[^"\']*["\']'
    r'[^>]*?href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_ICON_HI = re.compile(
    r'<link\s+(?:[^>]*?\s+)?rel\s*=\s*["\']icon["\'][^>]*?'
    r'sizes\s*=\s*["\'](?:192x192|180x180|256x256)["\'][^>]*?'
    r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_LINK_SHORT = re.compile(
    r'<link\s+(?:[^>]*?\s+)?rel\s*=\s*["\'](?:shortcut\s+)?icon["\']'
    r'[^>]*?href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _candidates_from_html(html: str, base_url: str) -> list[str]:
    """Returns candidate image URLs in priority order, absolute."""
    out: list[str] = []
    for rx in (_META_OG, _META_TW, _LINK_APPLE, _LINK_ICON_HI, _LINK_SHORT):
        m = rx.search(html)
        if m:
            out.append(urljoin(base_url, m.group(1).strip()))
    # Always include /favicon.ico at the root as a last-chance fallback.
    p = urlparse(base_url)
    if p.scheme and p.netloc:
        out.append(f"{p.scheme}://{p.netloc}/favicon.ico")
    # Dedupe while preserving order.
    seen, uniq = set(), []
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        uniq.append(u)
    return uniq


async def _download_image(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    try:
        r = await client.get(url, timeout=DEFAULT_TIMEOUT,
                                            headers={"User-Agent": UA})
    except httpx.HTTPError as e:
        log.debug("[logo_scrape] download fail %s err=%s", url, e)
        return None
    if r.status_code != 200:
        return None
    ct = (r.headers.get("content-type") or "").lower()
    if "image" not in ct and not url.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".svg")):
        return None
    body = r.content
    if not body or len(body) < 200:   # < 200 bytes is almost certainly junk
        return None
    return body


def _validate_and_normalize(raw: bytes) -> Optional[bytes]:
    """Drop images smaller than MIN_PX or otherwise unreadable.
    Resize to TARGET_PX and re-encode as WebP for cache compactness."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        return None
    w, h = img.size
    if min(w, h) < MIN_PX:
        return None
    # Square-crop centered then resize.
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.convert("RGBA") if img.mode in ("P", "RGBA") else img.convert("RGB")
    img = img.resize((TARGET_PX, TARGET_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="WEBP", quality=82, method=4)
    return buf.getvalue()


async def fetch_logo_from_website(homepage_url: str,
                                                                            timeout: float = DEFAULT_TIMEOUT
                                                                            ) -> Optional[bytes]:
    """Returns normalized WebP bytes or None.  See module docstring."""
    if not homepage_url or not homepage_url.startswith("http"):
        return None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                                              headers={"User-Agent": UA}) as client:
        try:
            r = await client.get(homepage_url)
        except httpx.HTTPError as e:
            log.debug("[logo_scrape] homepage GET fail %s err=%s",
                              homepage_url, e)
            return None
        if r.status_code != 200:
            return None
        html = r.text[:200_000]  # cap HTML parsing to first 200 KB
        base_url = str(r.url)
        for cand in _candidates_from_html(html, base_url):
            raw = await _download_image(client, cand)
            if not raw:
                continue
            norm = _validate_and_normalize(raw)
            if norm:
                log.info("[logo_scrape] OK %s ← %s", homepage_url, cand)
                return norm
    return None


def _persist_to_disk(station_id: str, raw: bytes) -> str:
    fname = f"{station_id}.webp"
    (LOGOS_DIR / fname).write_bytes(raw)
    return f"/api/static/station_logos_scraped/{fname}"


async def scrape_and_persist(db, station_doc: dict) -> dict:
    """Run the full chain for ONE station: try the scraper, persist on
    success, mark the attempt either way.  Returns a structured dict
    for the caller / backfill script."""
    from datetime import datetime, timezone
    sid = station_doc.get("id") or station_doc.get("_id")
    homepage = (station_doc.get("homepage")
                          or station_doc.get("homepage_url") or "").strip()
    now = datetime.now(timezone.utc)
    if not homepage:
        await db.imported_radio_stations.update_one(
            {"id": sid},
            {"$set": {"logo_scrape_last_attempt": now,
                          "logo_scrape_last_status": "no_homepage"}})
        return {"ok": False, "reason": "no_homepage", "station_id": sid}
    raw = await fetch_logo_from_website(homepage)
    if not raw:
        await db.imported_radio_stations.update_one(
            {"id": sid},
            {"$set": {"logo_scrape_last_attempt": now,
                          "logo_scrape_last_status": "no_logo_found"}})
        return {"ok": False, "reason": "no_logo_found", "station_id": sid,
                      "homepage": homepage}
    api_path = _persist_to_disk(sid, raw)
    await db.imported_radio_stations.update_one(
        {"id": sid},
        {"$set": {"image_url":          api_path,
                      "image_source":      "scraped",
                      "logo_scrape_last_attempt": now,
                      "logo_scrape_last_status": "ok"}})
    log.info("[logo_scrape] persisted sid=%s url=%s bytes=%d",
                    sid, api_path, len(raw))
    return {"ok": True, "station_id": sid, "image_url": api_path,
                  "source": "scraped", "homepage": homepage}


__all__ = [
    "fetch_logo_from_website", "scrape_and_persist",
    "MIN_PX", "TARGET_PX",
]
