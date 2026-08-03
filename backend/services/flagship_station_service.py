"""Phase FUN.1 — Flagship (FunAsia Network) station service.

Adds flagship-station surfacing on top of the existing
`imported_radio_stations` collection.  Purely additive — sets a few
new fields on flagship rows, never rewrites existing schema.

New fields on flagship rows:
    is_flagship            (bool)         — always True for FUN.1 seeded rows
    flagship_priority     (int)             — higher first (default 100)
    flagship_categories (list[str])   — `home` · `talk` · `music` · `south_asian` etc.
    flagship_slug           (str)             — stable short slug for testids + URLs
    flagship_since          (datetime)   — when it was flagged
    flagship_by              (str)             — admin user_id who set it
    playable_status       (str)             — healthy · pending · unreachable
    last_health_check_at (datetime)
    health_error              (str, optional)
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("bigfm.flagship")


def _now(): return datetime.now(timezone.utc)


# ─── Ordered flagship station manifest (drives seeding + reads) ──
FLAGSHIP_MANIFEST = [
    # UAE stations
    {"slug": "talk-1003-uae", "name": "Talk 100.3 UAE",
      "homepage": "https://talk1003.ae", "frequency": "100.3 FM Dubai",
      "categories": ["home", "talk", "news", "conversation", "uae"],
      "languages": ["english", "hindi"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "UAE's #1 English/Hindi talk radio.",
      "search_terms": ["talk", "1003", "news"],
      "priority": 200,
      "known_stream": "https://funasia.streamguys1.com/live-3"},
    {"slug": "luv-1071-uae", "name": "Luv 107.1 UAE",
      "homepage": "https://luv1071.com", "frequency": "107.1 FM Dubai",
      "categories": ["home", "music", "pop", "hot_ac", "top_40", "90s", "uae"],
      "languages": ["english"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Dubai's #1 hit music station.",
      "search_terms": ["luv", "1071", "pop", "top 40"],
      "priority": 200,
      "known_stream": "https://funasia.streamguys1.com/live2"},
    {"slug": "big-1062-uae", "name": "Big 106.2 UAE",
      "homepage": "https://funasia.net", "frequency": "106.2 FM Dubai",
      "categories": ["home", "music", "south_asian", "bollywood", "uae"],
      "languages": ["hindi"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Dubai's biggest Bollywood + Hindi music station.",
      "search_terms": ["big", "1062", "bollywood", "hindi"],
      "priority": 200,
      "known_stream": "https://funasia.streamguys1.com/live-1"},
    {"slug": "beat-978-uae", "name": "Beat 97.8",
      "homepage": "https://funasia.net", "frequency": "97.8 FM",
      "categories": ["home", "music", "south_asian", "uae"],
      "languages": ["hindi"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Beats that move you — Hindi hits, non-stop.",
      "search_terms": ["beat", "978", "hindi"],
      "priority": 180,
      "known_stream": "https://funasia.streamguys1.com/beat"},
    {"slug": "big-melodies", "name": "Big Melodies",
      "homepage": "https://funasia.net/melodies",
      "frequency": "Web · UAE",
      "categories": ["home", "music", "south_asian", "bollywood", "oldies", "uae"],
      "languages": ["hindi"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Classic Bollywood melodies from the golden era.",
      "search_terms": ["melodies", "big", "old bollywood"],
      "priority": 150,
      "known_stream": "https://funasia.streamguys1.com/melodies"},
    {"slug": "urban-beat", "name": "Urban Beat",
      "homepage": "https://funasia.net/urban",
      "frequency": "Web · UAE",
      "categories": ["home", "music", "hip_hop", "rnb", "urban"],
      "languages": ["english"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Fresh urban tracks — hip-hop, R&B, and more.",
      "search_terms": ["urban", "hip hop", "rnb"],
      "priority": 150,
      "known_stream": "https://funasia.streamguys1.com/urban"},
    {"slug": "luv-legends", "name": "Luv Legends",
      "homepage": "https://funasia.net/luvlegends",
      "frequency": "Web · UAE",
      "categories": ["home", "music", "pop", "oldies", "classic"],
      "languages": ["english"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "The greatest hits of the 70s, 80s, and 90s.",
      "search_terms": ["luv", "legends", "oldies"],
      "priority": 150,
      "known_stream": "https://funasia.streamguys1.com/legends"},
    {"slug": "beat-anthems", "name": "Beat Anthems",
      "homepage": "https://funasia.net/beatanthems",
      "frequency": "Web · UAE",
      "categories": ["home", "music", "dance", "anthems", "party"],
      "languages": ["english"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Dance floor anthems, all day long.",
      "search_terms": ["beat", "anthems", "dance"],
      "priority": 150,
      "known_stream": "https://funasia.streamguys1.com/anthems"},
    {"slug": "chilled-luv", "name": "Chilled Luv",
      "homepage": "https://funasia.net/chilled",
      "frequency": "Web · UAE",
      "categories": ["home", "music", "chill", "lounge"],
      "languages": ["english"], "country": "United Arab Emirates",
      "country_code": "AE", "city": "Dubai",
      "description": "Chill vibes for your lounge moments.",
      "search_terms": ["chilled", "luv", "lounge"],
      "priority": 150,
      "known_stream": "https://funasia.streamguys1.com/chilled"},
    # US / Dallas stations
    {"slug": "radio-sangam-dallas", "name": "Radio Sangam",
      "homepage": "https://funasia.net/sangam", "frequency": "104.9 HD · Dallas",
      "categories": ["home", "music", "talk", "south_asian", "telugu", "dallas", "us"],
      "languages": ["telugu"], "country": "United States",
      "country_code": "US", "city": "Dallas",
      "description": "Dallas's Telugu music + talk community.",
      "search_terms": ["sangam", "telugu"],
      "priority": 160,
      "known_stream": "https://funasia.streamguys1.com/sangam"},
    {"slug": "radio-caravan-dallas", "name": "Radio Caravan",
      "homepage": "https://funasia.net/caravan", "frequency": "104.9 HD · Dallas",
      "categories": ["home", "music", "talk", "south_asian", "hindi", "urdu", "dallas", "us"],
      "languages": ["hindi", "urdu"], "country": "United States",
      "country_code": "US", "city": "Dallas",
      "description": "Dallas's Hindi + Urdu music + talk community.",
      "search_terms": ["caravan", "hindi", "urdu"],
      "priority": 160,
      "known_stream": "https://funasia.streamguys1.com/caravan"},
    {"slug": "funasia-fm-dallas", "name": "FunAsia FM Dallas (KZMP)",
      "homepage": "https://funasia.net", "frequency": "104.9 FM / AM 700 · Dallas",
      "categories": ["home", "music", "talk", "south_asian", "bollywood", "hindi", "urdu", "dallas", "us"],
      "languages": ["hindi", "urdu"], "country": "United States",
      "country_code": "US", "city": "Dallas",
      "description": "Dallas's flagship FunAsia — Bollywood + desi talk.",
      "search_terms": ["funasia", "kzmp", "dallas"],
      "priority": 180,
      "known_stream": "https://funasia.streamguys1.com/live-1"},
]


def _make_id(slug: str) -> str:
    """Deterministic id for FUN.1 seeded rows so re-seeding is idempotent."""
    return f"imp_fun_{slug.replace('-', '_')}"


def _fallback_favicon(name: str) -> str:
    """UI-Avatars generated placeholder — always renders."""
    import urllib.parse as _p
    q = _p.quote(name)
    return f"https://ui-avatars.com/api/?name={q}&size=256&background=8b5cf6&color=fff&bold=true&font-size=0.4"


# ─── Radio Browser lookup ─────────────────────────────────────
async def _radio_browser_lookup(name: str) -> Optional[dict]:
    """Best-effort fetch of favicon + resolved stream from Radio Browser."""
    try:
        import urllib.parse as _p
        url = f"https://de1.api.radio-browser.info/json/stations/byname/{_p.quote(name)}"
        async with httpx.AsyncClient(timeout=6.0,
                                          headers={"User-Agent": "BigFM/1.0"}) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            if not data:
                return None
            # Prefer entries that have both favicon + resolved url.
            for d in data:
                if d.get("favicon") and d.get("url_resolved"):
                    return d
            return data[0]
    except Exception as e:
        logger.warning("[flagship] radio_browser lookup failed for %s: %s", name, e)
        return None


# ─── Seeding ─────────────────────────────────────────────────
async def seed_funasia_flagships(db) -> dict:
    """Idempotent seeding.  Safe to call on every server boot."""
    stats = {"processed": 0, "inserted": 0, "updated": 0,
                    "favicons_fetched": 0, "stream_urls_missing": 0,
                    "stream_urls_resolved": 0}
    now = _now()
    for spec in FLAGSHIP_MANIFEST:
        stats["processed"] += 1
        station_id = _make_id(spec["slug"])
        rb = await _radio_browser_lookup(spec["name"])
        favicon = (rb or {}).get("favicon") or _fallback_favicon(spec["name"])
        url_resolved = ((rb or {}).get("url_resolved")
                                          or spec.get("known_stream"))
        if favicon and not favicon.startswith("https://ui-avatars.com"):
            stats["favicons_fetched"] += 1
        if url_resolved:
            stats["stream_urls_resolved"] += 1
        else:
            stats["stream_urls_missing"] += 1

        existing = await db.imported_radio_stations.find_one({"id": station_id})
        base_doc = {
            "id":                          station_id,
            "provider":              "funasia_flagship_seed",
            "name":                      spec["name"],
            "homepage":              spec["homepage"],
            "url":                        url_resolved or "",
            "url_resolved":       url_resolved or "",
            "favicon":                favicon,
            "tags_raw":              ",".join(spec["categories"]),
            "tags_json":            spec["categories"],
            "country":                spec["country"],
            "country_code":      spec["country_code"],
            "city":                        spec["city"],
            "language":              " ".join(spec["languages"]),
            "language_codes":  spec["languages"],
            "codec":                    "mp3",
            "bitrate":                128,
            "hls":                        False,
            "active":                    True,
            "description":        spec["description"],
            "frequency":            spec["frequency"],
            # Flagship extension.
            "is_flagship":                        True,
            "flagship_slug":                    spec["slug"],
            "flagship_priority":            spec["priority"],
            "flagship_categories":       spec["categories"],
            "flagship_search_terms":  spec.get("search_terms") or [],
            "flagship_since":                  now,
            "flagship_by":                        "system_seed",
            "updated_at":                        now,
            "playable_status":               ("pending" if not url_resolved
                                                                          else (existing or {}).get(
                                                                                          "playable_status") or "pending"),
        }
        if not existing:
            base_doc.update({"imported_at": now,
                                              "last_check_ok": None,
                                              "last_check_time": None})
            # Set external_station_uuid — use Radio Browser's when we have it,
            # otherwise synthesize a stable per-slug UUID to satisfy the existing
            # unique non-sparse index (which treats "missing" as null).
            # Always use a stable synthetic UUID to avoid colliding with any
            # pre-existing row imported from Radio Browser under the same
            # station's real stationuuid.  We still record Radio Browser's
            # UUID separately for reference.
            base_doc["external_station_uuid"] = f"bigfm-fun1-{spec['slug']}"
            _rb_uuid = (rb or {}).get("stationuuid")
            if _rb_uuid:
                base_doc["radio_browser_uuid"] = _rb_uuid
            await db.imported_radio_stations.insert_one(base_doc)
            stats["inserted"] += 1
        else:
            # Preserve existing image_url / claim_status / etc. — only set
            # flagship fields + refresh favicon/stream if we found better.
            update_fields = {
                "is_flagship":                     True,
                "flagship_slug":                  spec["slug"],
                "flagship_priority":            spec["priority"],
                "flagship_categories":       spec["categories"],
                "flagship_search_terms":  spec.get("search_terms") or [],
                "flagship_since":                (existing.get("flagship_since") or now),
                "flagship_by":                        (existing.get("flagship_by") or "system_seed"),
                "description":                    spec["description"],
                "frequency":                        spec["frequency"],
                "city":                                    spec["city"],
                "updated_at":                        now,
            }
            if url_resolved and not existing.get("url_resolved"):
                update_fields["url_resolved"] = url_resolved
                update_fields["url"] = url_resolved
            if favicon and (not existing.get("favicon") or
                                              str(existing.get("favicon")).startswith(
                                                    "https://ui-avatars.com")):
                update_fields["favicon"] = favicon
            await db.imported_radio_stations.update_one(
                {"id": station_id}, {"$set": update_fields})
            stats["updated"] += 1
    logger.info(
        "[flagship_seed] processed=%d inserted=%d updated=%d "
        "favicons_fetched=%d stream_urls_resolved=%d stream_urls_missing=%d",
        stats["processed"], stats["inserted"], stats["updated"],
        stats["favicons_fetched"], stats["stream_urls_resolved"],
        stats["stream_urls_missing"])
    return stats


# ─── Read APIs ──────────────────────────────────────────────
def _clean(d: dict) -> dict:
    if not d:
        return d
    out = {k: v for k, v in d.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def list_flagships(db, *,
                                                    category: Optional[str] = None,
                                                    matches_language: Optional[str] = None,
                                                    matches_city: Optional[str] = None,
                                                    limit: int = 50) -> list[dict]:
    q: dict = {"is_flagship": True}
    if category:
        q["flagship_categories"] = category.lower()
    if matches_language:
        q["language_codes"] = matches_language.lower()
    if matches_city:
        q["city"] = matches_city
    docs = await db.imported_radio_stations.find(q).sort([
        ("flagship_priority", -1), ("name", 1)
    ]).to_list(limit)
    return [_clean(d) for d in docs]


async def get_flagship_by_slug(db, slug: str) -> Optional[dict]:
    d = await db.imported_radio_stations.find_one(
        {"is_flagship": True, "flagship_slug": slug})
    return _clean(d)


async def set_flagship(db, *, station_id: str, priority: int,
                                            categories: list, admin_user_id: str) -> dict:
    r = await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"is_flagship":              True,
                          "flagship_priority":       int(priority),
                          "flagship_categories": list(categories or []),
                          "flagship_since":           _now(),
                          "flagship_by":                 admin_user_id,
                          "updated_at":                 _now()}})
    if r.matched_count == 0:
        raise LookupError("station_not_found")
    return {"ok": True, "station_id": station_id}


async def unset_flagship(db, *, station_id: str, admin_user_id: str) -> dict:
    r = await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"is_flagship": False, "flagship_by": admin_user_id,
                          "updated_at": _now()}})
    if r.matched_count == 0:
        raise LookupError("station_not_found")
    return {"ok": True, "station_id": station_id}


# ─── Search priority sort ───────────────────────────────────
def sort_with_flagship_priority(items: list, key_flagship: str = "is_flagship",
                                                                          key_priority: str = "flagship_priority") -> list:
    """Stable-sort helper: flagship rows first (highest priority first)."""
    return sorted(
        items,
        key=lambda d: (0 if d.get(key_flagship) else 1,
                                      -(int(d.get(key_priority) or 0)) if d.get(key_flagship) else 0),
    )


async def search_flagships_by_query(db, *, query: str, limit: int = 5) -> list[dict]:
    """Case-insensitive name / tag / language match on flagship rows only.
    Used to pin flagship results at the top of the global search endpoint."""
    if not query or not query.strip():
        return []
    q = query.strip().lower()
    docs = await db.imported_radio_stations.find({
        "is_flagship": True,
        "$or": [
            {"name":                        {"$regex": q, "$options": "i"}},
            {"tags_json":              {"$in": [q]}},
            {"flagship_categories": {"$in": [q]}},
            {"flagship_search_terms": {"$in": [q]}},
            {"language_codes":     {"$in": [q]}},
        ],
    }).sort([("flagship_priority", -1)]).to_list(limit)
    return [_clean(d) for d in docs]


# ─── Stream health check cron ───────────────────────────────
async def _probe_stream(url: str) -> tuple[str, Optional[str]]:
    """Returns (status, error?).  status ∈ healthy · unreachable."""
    if not url:
        return ("pending", "no_stream_url")
    try:
        async with httpx.AsyncClient(timeout=5.0,
                                          follow_redirects=True,
                                          headers={"User-Agent": "BigFM-HealthCheck/1.0",
                                                            "Range": "bytes=0-1024",
                                                            "Icy-MetaData": "1"}) as c:
            r = await c.get(url)
            if r.status_code in (200, 206, 302, 301):
                return ("healthy", None)
            return ("unreachable", f"http_{r.status_code}")
    except Exception as e:
        return ("unreachable", str(e)[:120])


async def health_check_all_flagships(db) -> dict:
    """Iterate all flagship rows, probe each stream in parallel, update
    `playable_status` + `last_health_check_at` + `health_error`."""
    import asyncio as _aio
    stats = {"total": 0, "healthy": 0, "unreachable": 0, "pending": 0,
                    "results": []}
    now = _now()

    stations = await db.imported_radio_stations.find(
        {"is_flagship": True}).to_list(50)

    async def _probe_and_update(d):
        status, err = await _probe_stream(d.get("url_resolved") or "")
        await db.imported_radio_stations.update_one(
            {"id": d["id"]},
            {"$set": {"playable_status":            status,
                              "last_health_check_at":  now,
                              "health_error":              err}})
        if status == "unreachable":
            await db.flagship_alerts.insert_one({
                "alert_id":     f"fla_{secrets.token_hex(6)}",
                "station_id": d.get("id"),
                "name":            d.get("name"),
                "status":          status,
                "error":            err,
                "created_at": now,
                "resolved":     False,
            })
            try:
                from services.mailgun_client import send_email as _send
                await _send(
                    to_email=os.environ.get("FLAGSHIP_ALERT_EMAIL",
                                                                    "admin@bigfm.dubai"),
                    subject=f"[BigFM Flagship ALERT] {d.get('name')} unreachable",
                    text=f"Stream {d.get('url_resolved')} returned: {err}\n\nPlease investigate.")
            except Exception:
                pass
        return {"station_id": d.get("id"), "name": d.get("name"),
                        "status": status, "error": err}

    stats["total"] = len(stations)
    results = await _aio.gather(*[_probe_and_update(d) for d in stations],
                                                                    return_exceptions=False)
    for r in results:
        stats[r["status"]] = stats.get(r["status"], 0) + 1
        stats["results"].append(r)
    logger.info(
        "[flagship_health] total=%d healthy=%d unreachable=%d pending=%d",
        stats["total"], stats["healthy"], stats["unreachable"],
        stats.get("pending", 0))
    return stats


# ─── indexes ─────────────────────────────────────────────
async def ensure_flagship_indexes(db) -> None:
    try:
        await db.imported_radio_stations.create_index(
            [("is_flagship", 1), ("flagship_priority", -1)])
        await db.imported_radio_stations.create_index("flagship_slug",
                                                                                                                    sparse=True)
        await db.flagship_alerts.create_index("alert_id", unique=True)
        await db.flagship_alerts.create_index([("resolved", 1),
                                                                                            ("created_at", -1)])
    except Exception as e:
        logger.warning("[flagship] ensure_indexes: %s", e)
