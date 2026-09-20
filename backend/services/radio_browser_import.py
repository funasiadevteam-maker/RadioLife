"""Phase 42-A — Radio Browser import + auto-categorization service.

Pulls live-radio station metadata from the public Radio Browser API
(https://api.radio-browser.info/), normalizes it into the FUUSIC
`imported_radio_stations` schema, rule-classifies into categories, and
upserts via the `external_station_uuid` primary key.

Etiquette:
    User-Agent: FUUSIC/1.0 (https://bigfantv.com)   (per RB ToS)
    Mirror rotation: de1 / at1 / fi1 / nl1 — DNS round-robin.
                                  If one mirror fails (DNS / 5xx) we fall back
                                  to the next in the list.
    Click tracking: GET https://<mirror>/url/<uuid> is fire-and-forget
                                  when a user actually plays a stream so the
                                  upstream votes / click_trend stay accurate.

Cron orchestration:
    `radio_import_loop(app)` — long-running asyncio task started from
    server.py startup (mirrors the existing predict_win_sweeper pattern).
    Daily full sync (24h default) + hourly health-check on the top
    500-by-votes.  Idempotent.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("bigfm.live_radio.import")

# Radio Browser etiquette.
RADIO_BROWSER_USER_AGENT = "FUUSIC/1.0 (https://bigfantv.com)"
RADIO_BROWSER_MIRRORS = [
    "https://de1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://fi1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]

DEFAULT_IMPORT_INTERVAL_HOURS = float(
    os.environ.get("RADIO_IMPORT_INTERVAL_HOURS", "24"))
DEFAULT_HEALTH_INTERVAL_HOURS = float(
    os.environ.get("RADIO_HEALTH_INTERVAL_HOURS", "1"))
DEFAULT_TOP_FETCH_LIMIT = int(
    os.environ.get("RADIO_IMPORT_TOP_LIMIT", "5000"))
HEALTH_CHECK_TOP_N = int(
    os.environ.get("RADIO_HEALTH_TOP_N", "500"))


# ──────────────────────── Category classifier ────────────────────────
# Ordered category list used by the consumer rail.  `slug` is the
# canonical id; `label` is the human-facing string; `aliases` is the set
# of raw RB tag tokens that map to this category.
CATEGORIES: List[Dict[str, Any]] = [
    {"slug": "bollywood",    "label": "Bollywood",
      "aliases": {"bollywood", "hindi film", "hindi music",
                          "indian pop", "filmi"}},
    {"slug": "punjabi",        "label": "Punjabi",
      "aliases": {"punjabi", "bhangra", "punjabi pop", "desi"}},
    {"slug": "hindi",            "label": "Hindi",
      "aliases": {"hindi", "indian hindi"}},
    {"slug": "news",                "label": "News",
      "aliases": {"news", "talk", "current affairs", "world news"}},
    {"slug": "talk",                  "label": "Talk",
      "aliases": {"talk", "talkshow", "podcast"}},
    {"slug": "sports",            "label": "Sports",
      "aliases": {"sports", "cricket", "football", "soccer", "nfl"}},
    {"slug": "devotional",    "label": "Devotional",
      "aliases": {"devotional", "bhajan", "kirtan", "qawwali", "gospel",
                          "religious", "spiritual"}},
    {"slug": "pop",                  "label": "Pop",
      "aliases": {"pop", "top 40", "top40", "hits", "chart"}},
    {"slug": "rock",                "label": "Rock",
      "aliases": {"rock", "classic rock", "alt rock", "indie rock"}},
    {"slug": "edm",                  "label": "EDM",
      "aliases": {"edm", "electronic", "house", "techno", "trance", "dance"}},
    {"slug": "classical",      "label": "Classical",
      "aliases": {"classical", "orchestra", "symphony", "opera"}},
    {"slug": "jazz",                "label": "Jazz",
      "aliases": {"jazz", "smooth jazz", "blues"}},
]
LANGUAGE_CATEGORY_MAP = {
    # ISO-639 1-letter / RB language string → category slug.
    "hi":      "hindi",
    "hindi":  "hindi",
    "pa":      "punjabi",
    "punjabi": "punjabi",
    "bn":      "bollywood",   # Bengali → Bollywood-adjacent in our taxonomy.
    "ta":      "bollywood",
    "te":      "bollywood",
    "ur":      "bollywood",
}
COUNTRY_CATEGORY_HINT = {
    # Country code → low-confidence regional default category.
    "IN":  ("bollywood", 0.30),
    "PK":  ("bollywood", 0.30),
    "AE":  ("pop",            0.20),
    "SA":  ("pop",            0.20),
}


# ──────────────────────── Helpers ────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _imported_id_for(rb_uuid: str) -> str:
    return f"imp_{rb_uuid.replace('-', '')[:18]}"


def _parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def _norm_language(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [s.strip().lower() for s in re.split(r"[,;]", raw) if s.strip()]


def _coerce_int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_bool(v: Any) -> bool:
    return bool(v) and str(v).lower() not in {"0", "false", "no"}


def normalize_station(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map a single Radio Browser station row into FUUSIC's schema.
    Returns `None` for rows we can't import (missing UUID, blank stream
    URL, etc.)."""
    rb_uuid = (raw.get("stationuuid") or "").strip()
    url = (raw.get("url_resolved") or raw.get("url") or "").strip()
    name = (raw.get("name") or "").strip()
    if not rb_uuid or not url or not name:
        return None
    tags_raw = raw.get("tags") or ""
    tags_json = _parse_tags(tags_raw)
    language_codes = _norm_language(raw.get("languagecodes") or "")
    return {
        "id":                                       _imported_id_for(rb_uuid),
        "provider":                            "radiobrowser",
        "external_station_uuid": rb_uuid,
        "change_uuid":                      (raw.get("changeuuid") or "").strip() or None,
        "server_uuid":                      (raw.get("serveruuid") or "").strip() or None,
        "name":                                  name,
        "url":                                      (raw.get("url") or "").strip(),
        "url_resolved":                    url,
        "homepage":                          (raw.get("homepage") or "").strip() or None,
        "favicon":                              (raw.get("favicon") or "").strip() or None,
        "tags_raw":                            tags_raw,
        "tags_json":                          tags_json,
        "country":                              (raw.get("country") or "").strip() or None,
        "country_code":                  (raw.get("countrycode") or "").strip().upper() or None,
        "iso_3166_2":                      (raw.get("iso_3166_2") or "").strip() or None,
        "state":                                  (raw.get("state") or "").strip() or None,
        "city":                                    None,    # RB does not surface city directly
        "language":                          (raw.get("language") or "").strip().lower() or None,
        "language_codes":              language_codes,
        "codec":                                  (raw.get("codec") or "").strip().lower() or None,
        "bitrate":                              _coerce_int(raw.get("bitrate")),
        "hls":                                      _coerce_bool(raw.get("hls")),
        "votes":                                  _coerce_int(raw.get("votes")),
        "click_count":                      _coerce_int(raw.get("clickcount")),
        "click_trend":                      _coerce_int(raw.get("clicktrend")),
        "last_check_ok":                  _coerce_bool(raw.get("lastcheckok")),
        "last_check_time":              raw.get("lastchecktime"),
        "last_check_ok_time":      raw.get("lastcheckoktime"),
        "ssl_error":                          _coerce_int(raw.get("ssl_error")),
        "geo_lat":                              raw.get("geo_lat"),
        "geo_long":                          raw.get("geo_long"),
        "has_extended_info":          _coerce_bool(raw.get("has_extended_info")),
        # FUUSIC-side augmentations.
        "stream_health_status": "unknown",
        "active":                                  True,
        "imported_at":                      _now(),
        "updated_at":                        _now(),
    }


def categorize_station(s: Dict[str, Any]) -> List[Tuple[str, float, str]]:
    """Rule-based classifier.  Returns a list of
    `(category_slug, confidence, source)` rows."""
    out: List[Tuple[str, float, str]] = []
    tag_set = set(s.get("tags_json") or [])
    name = (s.get("name") or "").lower()
    langs = set(s.get("language_codes") or [])
    if s.get("language"):
        langs.add(s["language"])

    # RB tag matches (highest confidence).
    for cat in CATEGORIES:
        if cat["aliases"] & tag_set:
            out.append((cat["slug"], 0.90, "rb_tag"))

    # Name keyword reinforcement.
    name_hits: Dict[str, float] = {}
    if "news" in name: name_hits["news"] = 0.70
    if "talk" in name: name_hits["talk"] = 0.65
    if "rock" in name: name_hits["rock"] = 0.55
    if "edm" in name or " dance" in name: name_hits["edm"] = 0.55
    if "jazz" in name: name_hits["jazz"] = 0.55
    if "classical" in name or "symphony" in name:
        name_hits["classical"] = 0.55
    if "bollywood" in name: name_hits["bollywood"] = 0.80
    if "punjabi" in name or "bhangra" in name:
        name_hits["punjabi"] = 0.80
    if "hindi" in name: name_hits["hindi"] = 0.70
    if "devotional" in name or "bhajan" in name:
        name_hits["devotional"] = 0.70
    if "sport" in name or "cricket" in name:
        name_hits["sports"] = 0.65
    for cat, conf in name_hits.items():
        # Only add if not already present from a tag match.
        if not any(c[0] == cat for c in out):
            out.append((cat, conf, "name_keyword"))

    # Language → category mapping.
    for lang in langs:
        cat = LANGUAGE_CATEGORY_MAP.get(lang)
        if cat and not any(c[0] == cat for c in out):
            out.append((cat, 0.55, "language_code"))

    # Country default (lowest confidence).
    cc = (s.get("country_code") or "").upper()
    hint = COUNTRY_CATEGORY_HINT.get(cc)
    if hint:
        cat, conf = hint
        if not any(c[0] == cat for c in out):
            out.append((cat, conf, "country_default"))
    return out


# ──────────────────────── Radio Browser client ───────────────────────
async def _fetch_via_mirror(client: httpx.AsyncClient, path: str,
                                                          params: Optional[Dict[str, Any]] = None
                                                          ) -> Optional[List[Dict[str, Any]]]:
    """Try each mirror in order; first 200 wins."""
    last_err = None
    for mirror in RADIO_BROWSER_MIRRORS:
        try:
            r = await client.get(f"{mirror}{path}", params=params,
                                                      headers={"User-Agent": RADIO_BROWSER_USER_AGENT,
                                                                          "Accept": "application/json"},
                                                      timeout=30.0)
            if r.status_code == 200:
                return r.json()
            last_err = f"{mirror}: HTTP {r.status_code}"
        except Exception as e:
            last_err = f"{mirror}: {type(e).__name__}: {e}"
            continue
    logger.warning("[radio-import] all mirrors failed: %s", last_err)
    return None


async def fetch_all_stations(country_code: Optional[str] = None,
                                                      limit: int = DEFAULT_TOP_FETCH_LIMIT
                                                      ) -> List[Dict[str, Any]]:
    """Top-voted stations globally OR scoped to a country.  Sorted by
    votes descending.  Single-page fetch (capped at `limit`).  For the
    full catalog see `fetch_all_stations_paginated` (Phase 42-A2)."""
    params: Dict[str, Any] = {
        "limit": str(limit),
        "order": "votes",
        "reverse": "true",
        "hidebroken": "true",   # RB-side filter for last-check-failures
    }
    path = "/json/stations/search"
    if country_code:
        params["countrycode"] = country_code.upper()
    async with httpx.AsyncClient() as client:
        data = await _fetch_via_mirror(client, path, params)
    return data or []


# ─────────────── Phase 42-A2 — Paginated full-catalog walker ──────────
# Walks the entire Radio Browser catalog by stepping offset by `page_size`
# until a short page (< page_size) or an empty page comes back.  Honors
# the `state_doc_id` flag for cooperative cancellation + writes live
# chunk-progress so the admin status endpoint can render a progress bar.
PAGINATED_PAGE_SIZE = 10000            # RB tolerates up to 10k per call
PAGINATED_BACKPRESSURE_SEC = 1.0   # 1 req/sec per RB etiquette
MAX_PAGES_SAFETY = 20                      # 200K hard cap


async def fetch_all_stations_paginated(
        db, *,
        page_size: int = PAGINATED_PAGE_SIZE,
        max_pages: int = MAX_PAGES_SAFETY,
        cancel_state_id: str = "last_full_sync",
        progress_state_id: str = "last_full_sync",
        run_id: Optional[str] = None,
        ) -> List[Dict[str, Any]]:
    """Yield-all paginated walk.  Returns the full concatenated list.
    Updates `radio_import_state[{progress_state_id}].chunk_progress` after
    each chunk so admins can poll progress."""
    out: List[Dict[str, Any]] = []
    started_at = _now()
    offset = 0
    pages = 0
    async with httpx.AsyncClient() as client:
        while pages < max_pages:
            # Cancellation check.
            try:
                st = await db.radio_import_state.find_one({"_id": cancel_state_id})
                if st and st.get("cancel_requested"):
                    logger.info("[radio-import] cancel requested at offset=%d", offset)
                    break
            except Exception:
                pass
            params = {
                "limit": str(page_size),
                "offset": str(offset),
                "order": "votes",
                "reverse": "true",
                "hidebroken": "true",
            }
            try:
                data = await _fetch_via_mirror(client, "/json/stations/search", params)
            except Exception as e:
                logger.warning("[radio-import] page fetch failed at offset=%d: %s",
                                            offset, e)
                break
            chunk = data or []
            pages += 1
            out.extend(chunk)
            offset += page_size
            # Live progress write.
            try:
                await db.radio_import_state.update_one(
                    {"_id": progress_state_id},
                    {"$set": {"chunk_progress": {
                                "run_id": run_id,
                                "current_offset": offset,
                                "processed": len(out),
                                "page_size": page_size,
                                "page_count": pages,
                                "last_chunk_size": len(chunk),
                                "in_flight": True,
                                "started_at": started_at,
                                "updated_at": _now(),
                            }}},
                    upsert=True)
            except Exception:
                pass
            logger.info("[radio-import] paginated chunk pg=%d offset=%d "
                                    "received=%d running_total=%d",
                                    pages, offset, len(chunk), len(out))
            # Short page = end of catalog.
            if len(chunk) < page_size:
                break
            await asyncio.sleep(PAGINATED_BACKPRESSURE_SEC)
    # Mark progress in_flight=False so the admin UI knows it ended.
    try:
        await db.radio_import_state.update_one(
            {"_id": progress_state_id},
            {"$set": {"chunk_progress.in_flight": False,
                          "chunk_progress.finished_at": _now()}})
    except Exception:
        pass
    return out


async def health_check_station(client: httpx.AsyncClient,
                                                            url_resolved: str) -> str:
    """HEAD → fall back to a small ranged GET (some streams reject HEAD).
    Returns one of `ok | down | ssl_error | rate_limited`."""
    try:
        r = await client.head(url_resolved, timeout=5.0,
                                                  follow_redirects=True,
                                                  headers={"User-Agent": RADIO_BROWSER_USER_AGENT})
        if r.status_code == 429:
            return "rate_limited"
        if 200 <= r.status_code < 400:
            return "ok"
        # Some streams reject HEAD with 405 / 501.  Try a small GET.
        if r.status_code in (405, 501):
            r2 = await client.get(url_resolved, timeout=5.0,
                                                      follow_redirects=True,
                                                      headers={"Range": "bytes=0-1023",
                                                                          "User-Agent": RADIO_BROWSER_USER_AGENT})
            if r2.status_code < 400:
                return "ok"
        return "down"
    except httpx.ConnectError as e:
        msg = str(e).lower()
        if "ssl" in msg or "cert" in msg:
            return "ssl_error"
        return "down"
    except Exception:
        return "down"


async def send_click_track(rb_uuid: str) -> None:
    """Fire-and-forget click ping per RB etiquette.  Never raises."""
    try:
        async with httpx.AsyncClient() as client:
            for mirror in RADIO_BROWSER_MIRRORS:
                try:
                    await client.get(f"{mirror}/json/url/{rb_uuid}",
                                                  headers={"User-Agent": RADIO_BROWSER_USER_AGENT},
                                                  timeout=5.0)
                    return
                except Exception:
                    continue
    except Exception:
        pass


# ──────────────────────── DB sync ─────────────────────────────────────
async def dedupe_and_upsert(db, stations: List[Dict[str, Any]]) -> Dict[str, int]:
    created = 0
    updated = 0
    for s in stations:
        existing = await db.imported_radio_stations.find_one(
            {"external_station_uuid": s["external_station_uuid"]})
        if existing:
            # Preserve our augmentations.
            patch = {**s,
                          "active": existing.get("active", True),
                          "stream_health_status": existing.get(
                              "stream_health_status", "unknown"),
                          "imported_at": existing.get("imported_at", s["imported_at"]),
                          "updated_at": _now()}
            await db.imported_radio_stations.update_one(
                {"external_station_uuid": s["external_station_uuid"]},
                {"$set": patch})
            updated += 1
        else:
            await db.imported_radio_stations.insert_one({**s, "_id": s["id"]})
            created += 1
    return {"created": created, "updated": updated}


async def apply_categories(db, stations: List[Dict[str, Any]]) -> int:
    """Re-categorize each station; replace its existing category rows."""
    total = 0
    now = _now()
    for s in stations:
        await db.radio_station_categories.delete_many(
            {"station_id": s["id"], "source_provider": "radiobrowser"})
        cats = categorize_station(s)
        for cat, conf, src in cats:
            rid = _new_id("rsc")
            await db.radio_station_categories.insert_one({
                "_id": rid, "id": rid,
                "station_id": s["id"],
                "category": cat,
                "confidence_score": conf,
                "source": src,
                "source_provider": "radiobrowser",
                "created_at": now,
            })
            total += 1
    return total


# ──────────────────────── Orchestration ───────────────────────────────
async def import_daily_full_sync(db, *,
                                                                country_code: Optional[str] = None,
                                                                limit: int = DEFAULT_TOP_FETCH_LIMIT,
                                                                trigger: str = "scheduled",
                                                                full_catalog: bool = False,
                                                                ) -> Dict[str, Any]:
    """Pull → normalize → categorize → upsert.  Logs one row to
    `radio_import_logs`.

    Phase 42-A2: when `full_catalog=True`, walks the entire Radio Browser
    catalog with offset pagination instead of taking the top-N voted
    page.  Skips rows whose `lastcheckok=False` AND have never been
    successfully checked (`lastcheckoktime` is null/empty) — i.e., we
    keep stations that worked at some point in the past."""
    run_id = _new_id("rblg")
    started = _now()
    error: Optional[str] = None
    fetched = 0
    filtered_never_working = 0
    normalized: List[Dict[str, Any]] = []
    # Clear stale cancel flag at the start of every run.
    try:
        await db.radio_import_state.update_one(
            {"_id": "last_full_sync"},
            {"$set": {"cancel_requested": False, "active_run_id": run_id}},
            upsert=True)
    except Exception:
        pass
    try:
        if full_catalog:
            raw = await fetch_all_stations_paginated(
                db, run_id=run_id)
        else:
            raw = await fetch_all_stations(country_code=country_code, limit=limit)
        fetched = len(raw)
        for r in raw:
            # Phase 42-A2 filter — skip stations that never worked.
            ok_now = _coerce_bool(r.get("lastcheckok"))
            ok_ever = (r.get("lastcheckoktime") or "").strip()
            if not ok_now and not ok_ever:
                filtered_never_working += 1
                continue
            n = normalize_station(r)
            if n:
                normalized.append(n)
    except Exception as e:
        error = f"fetch: {e}"
        logger.exception("[radio-import] fetch failed")

    upsert_counts = {"created": 0, "updated": 0}
    category_count = 0
    try:
        if normalized:
            upsert_counts = await dedupe_and_upsert(db, normalized)
            category_count = await apply_categories(db, normalized)
    except Exception as e:
        error = (error or "") + f"; upsert: {e}"
        logger.exception("[radio-import] upsert failed")

    ended = _now()
    log_doc = {
        "_id": run_id, "id": run_id,
        "provider": "radiobrowser",
        "endpoint": "/json/stations/search",
        "country_code": country_code,
        "limit": limit,
        "full_catalog": full_catalog,
        "records_fetched": fetched,
        "records_normalized": len(normalized),
        "records_filtered_never_working": filtered_never_working,
        "records_created": upsert_counts["created"],
        "records_updated": upsert_counts["updated"],
        "categories_assigned": category_count,
        "errors_json": [error] if error else [],
        "trigger": trigger,
        "started_at": started,
        "ended_at": ended,
        "duration_ms": int((ended - started).total_seconds() * 1000),
        "ok": (error is None and fetched > 0),
    }
    try:
        await db.radio_import_logs.insert_one(log_doc)
        await db.radio_import_state.update_one(
            {"_id": "last_full_sync"},
            {"$set": {"_id": "last_full_sync",
                          "completed_at": ended,
                          "fetched": fetched,
                          "ok": log_doc["ok"],
                          "active_run_id": None,
                          "cancel_requested": False}},
            upsert=True)
    except Exception as e:
        logger.warning("[radio-import] log insert failed: %s", e)
    try:
        from services.radio_policy import apply_language_policy
        lang_pol = await apply_language_policy(db)
        logger.info("[radio-import] language policy: %s", lang_pol)
    except Exception as e:  # noqa: BLE001
        logger.warning("[radio-import] language policy failed: %s", e)
    logger.info(f"[radio-import] cycle={run_id[:18]} fetched={fetched} "
                          f"filtered_never_working={filtered_never_working} "
                          f"created={upsert_counts['created']} "
                          f"updated={upsert_counts['updated']} "
                          f"categories={category_count} ok={log_doc['ok']}")
    return log_doc


async def health_check_top_stations(db, *,
                                                                          limit: int = HEALTH_CHECK_TOP_N
                                                                          ) -> Dict[str, int]:
    """HEAD/GET probe the top-N-by-votes active rows.  Updates each
    station's `stream_health_status` + `last_health_check_at`."""
    counts = {"ok": 0, "down": 0, "ssl_error": 0, "rate_limited": 0}
    cur = db.imported_radio_stations.find(
        {"active": True}).sort("votes", -1).limit(limit)
    rows = [r async for r in cur]
    async with httpx.AsyncClient() as client:
        for s in rows:
            url = s.get("url_resolved")
            if not url:
                continue
            status = await health_check_station(client, url)
            counts[status] = counts.get(status, 0) + 1
            await db.imported_radio_stations.update_one(
                {"_id": s["_id"]},
                {"$set": {"stream_health_status": status,
                                  "last_health_check_at": _now()}})
    return counts


# ──────────────────────── Index bootstrap ───────────────────────────
async def ensure_42a_indexes(db) -> Dict[str, bool]:
    await db.imported_radio_stations.create_index(
        "external_station_uuid", unique=True)
    await db.imported_radio_stations.create_index(
        [("country_code", 1), ("active", 1)])
    await db.imported_radio_stations.create_index(
        [("language", 1), ("active", 1)])
    await db.imported_radio_stations.create_index(
        [("tags_json", 1), ("active", 1)])
    await db.imported_radio_stations.create_index(
        [("active", 1), ("votes", -1)])
    await db.imported_radio_stations.create_index(
        [("active", 1), ("click_trend", -1)])
    await db.radio_station_categories.create_index(
        [("station_id", 1), ("source_provider", 1)])
    await db.radio_station_categories.create_index(
        [("category", 1), ("confidence_score", -1)])
    # TTL 30d on import logs.
    try:
        existing = await db.radio_import_logs.index_information()
        if "started_at_1" in existing and "ttl_radio_import_30d" not in existing:
            await db.radio_import_logs.drop_index("started_at_1")
    except Exception:
        pass
    await db.radio_import_logs.create_index(
        "started_at", expireAfterSeconds=30 * 24 * 3600,
        name="ttl_radio_import_30d")
    return {"imported_radio_stations": True,
                  "radio_station_categories": True,
                  "radio_import_logs": True}


# ──────────────────────── Cron loop ─────────────────────────────────
async def radio_import_loop(app) -> None:
    """Long-running asyncio task.  Daily full sync + hourly health check.

    Mirrors the existing `predict_win_sweeper.sweeper_loop` pattern:
    infinite `while True` with try/except, sleep + jitter, app lifecycle
    survives a single bad cycle.
    """
    full_interval_s = int(DEFAULT_IMPORT_INTERVAL_HOURS * 3600)
    health_interval_s = int(DEFAULT_HEALTH_INTERVAL_HOURS * 3600)
    db = app.state.db
    logger.info(f"[radio-import] loop starting "
                          f"(full_sync_every={DEFAULT_IMPORT_INTERVAL_HOURS}h, "
                          f"health_check_every={DEFAULT_HEALTH_INTERVAL_HOURS}h)")

    # If we have no record of a recent successful sync, run one now.
    state = await db.radio_import_state.find_one({"_id": "last_full_sync"})
    last_completed = state.get("completed_at") if state else None
    needs_initial_sync = True
    if isinstance(last_completed, datetime):
        last_completed_aw = (last_completed if last_completed.tzinfo
                                              else last_completed.replace(tzinfo=timezone.utc))
        if (_now() - last_completed_aw) < timedelta(hours=DEFAULT_IMPORT_INTERVAL_HOURS):
            needs_initial_sync = False
    if needs_initial_sync:
        try:
            await asyncio.sleep(8)   # let the rest of bootstrap settle
            await import_daily_full_sync(db, trigger="startup")
        except Exception as e:
            logger.warning("[radio-import] initial sync failed: %s", e)

    # Hourly health check loop.  Daily full sync is a separate counter.
    cycles_since_full_sync = 0
    cycles_per_full_sync = max(1, full_interval_s // health_interval_s)
    while True:
        try:
            await asyncio.sleep(health_interval_s)
            await health_check_top_stations(db)
            cycles_since_full_sync += 1
            if cycles_since_full_sync >= cycles_per_full_sync:
                await import_daily_full_sync(db, trigger="scheduled")
                cycles_since_full_sync = 0
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("[radio-import] loop iteration error: %s", e)
