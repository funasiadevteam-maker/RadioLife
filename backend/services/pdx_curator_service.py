"""Phase PDX.1 — Predexon auto-import curator service.

Runs on a scheduler (default every 60 min).  Each tick:

1. For each of the 4 configured categories, calls Predexon with the
   category's fetch strategy (tag or search filter).
2. Client-side filters / dedupes / sorts by `total_volume_usd` desc.
3. Inserts new `predict_win_campaigns` rows (idempotent by
   `external_market_id`) with `creator_type="admin_auto"`,
   `import_source="pdx_curator"`, and points_reward clamped to [10, 100].
4. Runs `ensure_minimum_active(20)` — backfills from `us_politics` (deep
   pool) if the 4-category pull didn't meet the floor.
5. Runs `retire_stale_auto_imports()` on the daily tick.

All auto-imports are `approval_status="approved"` + `status="scheduled"`
so listeners see them immediately; the existing sweeper resolves them
via the Predexon resolution endpoint when their `lock_time` passes.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from config.pdx_categories import (
    BACKFILL_ORDER, CATEGORY_BY_SLUG, PDX_CATEGORIES,
    POINTS_MAX, POINTS_MIN,
    derive_points, polymarket_url_for,
)
from services import predexon_client
from services.predexon_client import normalize_outcomes

log = logging.getLogger("bigfm.pdx_curator")

# ─── Config helpers ────────────────────────────────────────────────
SYSTEM_SETTINGS_ID = "pdx_curator"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "_id":                     SYSTEM_SETTINGS_ID,
    "enabled":              True,
    "interval_min":     60,
    "target_min":         20,
    "target_max":         40,
    # Populated at write-time.
    "updated_at":         None,
    "last_run_at":       None,
    "last_run_summary": None,
}

# 10 s spacing between Predexon calls to stay under the 429 threshold.
INTER_CALL_SLEEP_SEC = 10.0

# Upper bound on backfill iterations.  Prevents an infinite loop if
# Predexon returns fewer rows than we ask for.
MAX_BACKFILL_ITERATIONS = 6

STALE_AUTO_IMPORT_HOURS = 48


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _opt_id(i: int) -> str:
    return f"opt_{i+1}"


async def get_settings(db) -> Dict[str, Any]:
    """Read the singleton config row, seeding defaults if absent."""
    doc = await db.system_settings.find_one({"_id": SYSTEM_SETTINGS_ID})
    if doc:
        # Merge defaults for any newly-added keys.
        merged = {**DEFAULT_SETTINGS, **doc}
        return merged
    seed = {**DEFAULT_SETTINGS, "updated_at": _now()}
    try:
        await db.system_settings.insert_one(seed)
    except Exception as e:
        log.debug("[pdx-curator] settings seed race: %s", e)
    return await db.system_settings.find_one({"_id": SYSTEM_SETTINGS_ID}) or seed


async def update_settings(db, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a partial update to the curator settings.  Only the keys
    listed here can be written from the admin API."""
    ALLOWED = {"enabled", "interval_min", "target_min", "target_max"}
    to_set: Dict[str, Any] = {"updated_at": _now()}
    for k, v in (patch or {}).items():
        if k not in ALLOWED:
            continue
        if k == "enabled":
            to_set[k] = bool(v)
        elif k == "interval_min":
            iv = int(v)
            to_set[k] = max(5, min(1440, iv))
        elif k == "target_min":
            iv = int(v)
            to_set[k] = max(1, min(60, iv))
        elif k == "target_max":
            iv = int(v)
            to_set[k] = max(1, min(200, iv))
    await db.system_settings.update_one(
        {"_id": SYSTEM_SETTINGS_ID},
        {"$set": to_set,
          "$setOnInsert": {**DEFAULT_SETTINGS,
                                          "updated_at": to_set["updated_at"]}},
        upsert=True)
    return await get_settings(db)


async def is_enabled(db) -> bool:
    s = await get_settings(db)
    return bool(s.get("enabled", True))


# ─── Predexon fetch helpers ────────────────────────────────────────
async def _predexon_list(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One Predexon call → list of raw markets (empty on any error)."""
    full = {"status": "open", **params}
    r = await predexon_client._request(  # noqa: SLF001 — internal by design
        db, "GET", "/v2/polymarket/markets", params=full)
    if not r.get("ok"):
        log.warning("[pdx-curator] predexon list failed status=%s params=%s err=%s",
                              r.get("status_code"), params, r.get("error_message"))
        return []
    body = r.get("body") or {}
    m = body.get("markets") if isinstance(body, dict) else []
    return m if isinstance(m, list) else []


def _step_matches(step: Dict[str, Any], m: Dict[str, Any]) -> bool:
    """Apply the post-fetch filters declared on a FetchStep."""
    tags_lc = [str(t).lower() for t in (m.get("tags") or [])]
    title_lc = (m.get("title") or "").lower()

    req_tag = step.get("require_any_tag") or []
    if req_tag:
        req_lc = [str(t).lower() for t in req_tag]
        if not any(any(rq in t for t in tags_lc) for rq in req_lc):
            return False

    req_title = step.get("require_any_title") or []
    if req_title:
        if not any(str(rt).lower() in title_lc for rt in req_title):
            return False

    excl_tag = step.get("exclude_any_tag") or []
    if excl_tag:
        excl_lc = [str(t).lower() for t in excl_tag]
        for e in excl_lc:
            if any(e in t for t in tags_lc):
                return False
    return True


async def fetch_category_pool(db, category_slug: str,
                                                              *, sleep_between: float = INTER_CALL_SLEEP_SEC,
                                                              ) -> List[Dict[str, Any]]:
    """Run all fetch-steps for a category, dedupe by `market_id`, sort by
    volume desc.  Returns the raw Predexon market dicts."""
    spec = CATEGORY_BY_SLUG.get(category_slug)
    if not spec:
        return []
    pool: Dict[str, Dict[str, Any]] = {}
    for i, step in enumerate(spec["steps"]):
        params: Dict[str, Any] = {"limit": int(step.get("limit", 50))}
        if step.get("tag"):
            params["tags"] = step["tag"]
        if step.get("search"):
            params["search"] = step["search"]
        rows = await _predexon_list(db, params)
        for m in rows:
            mid = m.get("market_id") or m.get("id") or m.get("condition_id")
            if not mid:
                continue
            if not _step_matches(step, m):
                continue
            # Prefer the row we saw first (usually higher volume from step 0).
            if mid not in pool:
                pool[mid] = m
        if i + 1 < len(spec["steps"]):
            await asyncio.sleep(sleep_between)
    ranked = list(pool.values())
    ranked.sort(key=lambda r: float(r.get("total_volume_usd") or 0),
                          reverse=True)
    return ranked


# ─── DB persistence ────────────────────────────────────────────────
async def _resolve_provider_id(db) -> str:
    row = await db.prediction_data_providers.find_one(
        {"provider_name": "predexon"})
    if row:
        return row.get("provider_id") or row.get("_id")
    return "pdp_predexon"


def _parse_iso(v) -> Optional[datetime]:
    if v is None:
        return None
    try:
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _campaign_doc_from_market(
        m: Dict[str, Any], *,
        category_slug: str,
        points_reward: int,
        provider_id: str) -> Dict[str, Any]:
    """Materialise ONE market into a predict_win_campaigns row shape."""
    now = _now()
    outcomes = normalize_outcomes(m.get("outcomes") or [])
    options: List[Dict[str, Any]] = []
    for i, o in enumerate(outcomes):
        options.append({
            "option_id":              _opt_id(i),
            "label":                     (o.get("label") or f"Option {i+1}")[:80],
            "external_outcome_id": o.get("external_outcome_id") or "",
        })

    start = _parse_iso(m.get("start_time")) or _parse_iso(m.get("created_time")) or now
    lock  = _parse_iso(m.get("end_time")) or _parse_iso(m.get("close_time"))
    if lock is None or lock <= start:
        lock = start + timedelta(days=7)
    resolve_by = lock + timedelta(hours=2)

    campaign_id = _new_id("pwc")
    title = (m.get("title") or m.get("event_title") or "Predexon market")[:160]
    question_text = (m.get("title") or "Pick the winning outcome.")[:600]
    market_id = str(m.get("market_id") or m.get("id") or m.get("condition_id"))

    return {
        "_id":                       campaign_id,
        "campaign_id":     campaign_id,
        "title":                    title,
        "description":       (m.get("description") or None),
        "event_type":         "general_prediction",
        "event_label":       "predexon",
        "category":            m.get("event_slug") or None,
        # Phase PDX.1 additions ↓
        "category_slug":  category_slug,
        "points_reward": max(POINTS_MIN, min(POINTS_MAX, int(points_reward))),
        "imported_at":       now,
        "import_source":  "pdx_curator",
        # ↑ Phase PDX.1 additions
        "city":                     None,
        "region":                 None,
        "language":             "en",
        "cover_image_url": m.get("image_url"),
        "question": {
            "prompt":                    question_text,
            "answer_options": options,
        },
        "start_time":         start,
        "lock_time":           lock,
        "resolve_by":         resolve_by,
        "winner_rules_json": {
            "selection_rule": "first_n_correct",
            "first_n":                1,
            "tiebreaker":       "earliest",
        },
        "data_provider_id":    provider_id,
        "compliance_settings_id": None,
        "external_market_id":     market_id,
        "external_market_url":  polymarket_url_for(m.get("market_slug")),
        "external_provider_snapshot": {
            "provider_name":  "predexon",
            "title":                     m.get("title"),
            "tags":                       m.get("tags") or [],
            "total_volume_usd": m.get("total_volume_usd"),
            "imported_at":       now.isoformat(),
        },
        # Approval flow — auto-approved so listeners see them
        # immediately (they still respect lock/resolve gates).
        "creator_type":       "admin_auto",
        "approval_status": "approved",
        "approval_reason": "pdx_curator_auto_import",
        "approved_by":       "pdx_curator",
        "approved_at":       now,
        "rejected_by":       None,
        "rejected_at":       None,
        "status":                   "scheduled",
        "created_by":         "pdx_curator",
        "created_at":         now,
        "updated_at":         now,
        "deleted_at":         None,
        # Merchant Predict & Win (PW-M.1) — auto-eligible so merchants
        # can immediately activate imported markets.
        "merchant_eligible": True,
    }


async def _dedupe_and_persist(
        db, raw_events: List[Dict[str, Any]],
        *, category_slug: str, default_points: int,
        provider_id: str,
        max_to_insert: int,
) -> Dict[str, int]:
    """Insert up to `max_to_insert` new campaign rows.  Returns
    `{created, skipped_existing, errored}` counts."""
    stats = {"created": 0, "skipped_existing": 0, "errored": 0}
    for m in raw_events[:max(max_to_insert * 3, max_to_insert)]:
        if stats["created"] >= max_to_insert:
            break
        market_id = str(m.get("market_id") or m.get("id")
                                  or m.get("condition_id") or "")
        if not market_id:
            stats["errored"] += 1
            continue
        # Idempotency check — same pattern as the existing admin importer.
        try:
            dup = await db.predict_win_campaigns.find_one({
                "external_market_id": market_id,
                "status": {"$ne": "cancelled"},
                "deleted_at": None,
            })
        except Exception as e:
            log.warning("[pdx-curator] dup check failed for %s: %s", market_id, e)
            dup = None
        if dup:
            stats["skipped_existing"] += 1
            continue
        try:
            points = derive_points(default_points,
                                                        m.get("total_volume_usd"))
            doc = _campaign_doc_from_market(
                m,
                category_slug=category_slug,
                points_reward=points,
                provider_id=provider_id)
            if not doc["question"]["answer_options"]:
                stats["errored"] += 1
                continue
            await db.predict_win_campaigns.insert_one(doc)
            stats["created"] += 1
        except Exception as e:
            log.exception("[pdx-curator] insert failed market=%s: %s",
                                        market_id, e)
            stats["errored"] += 1
    return stats


# ─── Public: per-category import ───────────────────────────────────
async def import_top_events_by_category(
        db, category_slug: str, *, limit: Optional[int] = None,
        sleep_between: float = INTER_CALL_SLEEP_SEC,
) -> Dict[str, Any]:
    """Fetch → filter → persist one category.  Returns import stats."""
    spec = CATEGORY_BY_SLUG.get(category_slug)
    if not spec:
        return {"error": "unknown_category", "created": 0,
                      "skipped_existing": 0, "errored": 0}
    target = limit if isinstance(limit, int) and limit > 0 else spec["take_top"]
    provider_id = await _resolve_provider_id(db)
    pool = await fetch_category_pool(db, category_slug,
                                                                      sleep_between=sleep_between)
    stats = await _dedupe_and_persist(
        db, pool,
        category_slug=category_slug,
        default_points=spec["default_points"],
        provider_id=provider_id,
        max_to_insert=target)
    stats["category_slug"] = category_slug
    stats["pool_size"] = len(pool)
    return stats


# ─── Backfill + retire ─────────────────────────────────────────────
async def _count_active_auto(db) -> int:
    return await db.predict_win_campaigns.count_documents({
        "creator_type": "admin_auto",
        "status": {"$in": ["scheduled", "live"]},
        "approval_status": "approved",
        "lock_time": {"$gt": _now()},
        "deleted_at": None,
    })


async def ensure_minimum_active(
        db, *, target_min: int = 20, target_max: int = 40,
        sleep_between: float = INTER_CALL_SLEEP_SEC,
) -> Dict[str, Any]:
    """If <target_min active auto-imports, pull additional events from
    the BACKFILL_ORDER (us_politics first — deepest pool) until we cross
    the threshold OR reach the target_max upper bound OR run out of
    Predexon rows."""
    active_before = await _count_active_auto(db)
    if active_before >= target_min:
        return {"backfilled": 0, "active_before": active_before,
                      "active_after": active_before,
                      "reached_target": True}
    need = target_min - active_before
    cap  = max(0, target_max - active_before)
    need = min(need, cap)
    total_created = 0
    for _round in range(MAX_BACKFILL_ITERATIONS):
        if need <= 0:
            break
        made_progress = False
        for slug in BACKFILL_ORDER:
            if need <= 0:
                break
            per_call = min(need, 6)
            stats = await import_top_events_by_category(
                db, slug, limit=per_call, sleep_between=sleep_between)
            created = int(stats.get("created", 0))
            total_created += created
            need -= created
            if created > 0:
                made_progress = True
        if not made_progress:
            # Predexon's pool exhausted for this cycle.
            break
    active_after = await _count_active_auto(db)
    return {
        "backfilled":         total_created,
        "active_before": active_before,
        "active_after":   active_after,
        "reached_target": active_after >= target_min,
    }


async def retire_stale_auto_imports(db) -> Dict[str, Any]:
    """Mark auto-imported events with `status=cancelled` if their event
    time passed >STALE_AUTO_IMPORT_HOURS ago without resolution."""
    cutoff = _now() - timedelta(hours=STALE_AUTO_IMPORT_HOURS)
    res = await db.predict_win_campaigns.update_many(
        {
            "creator_type": "admin_auto",
            "status":              {"$in": ["scheduled", "live", "locked"]},
            "lock_time":       {"$lt": cutoff},
            "deleted_at":     None,
        },
        {"$set": {
            "status":            "cancelled",
            "cancelled_at":  _now(),
            "cancel_reason": "pdx_curator_stale",
            "updated_at":     _now(),
        }},
    )
    return {"retired": int(getattr(res, "modified_count", 0) or 0)}


# ─── Orchestration ────────────────────────────────────────────────
async def run_curator_tick(db, *,
                                                          sleep_between: float = INTER_CALL_SLEEP_SEC,
                                                          run_retire: bool = False,
                                                          ) -> Dict[str, Any]:
    """One full tick: 4 categories → backfill → optional retire."""
    tick_start = _now()
    settings = await get_settings(db)
    if not settings.get("enabled", True):
        return {"skipped": True, "reason": "curator_disabled",
                      "tick_started_at": tick_start.isoformat()}
    per_category: Dict[str, Dict[str, Any]] = {}
    for i, cat in enumerate(PDX_CATEGORIES):
        try:
            stats = await import_top_events_by_category(
                db, cat["slug"], sleep_between=sleep_between)
        except Exception as e:
            log.exception("[pdx-curator] category %s tick failed: %s",
                                        cat["slug"], e)
            stats = {"category_slug": cat["slug"], "created": 0,
                            "skipped_existing": 0, "errored": 1,
                            "error": str(e)[:200]}
        per_category[cat["slug"]] = stats
        if i + 1 < len(PDX_CATEGORIES):
            await asyncio.sleep(sleep_between)
    backfill = await ensure_minimum_active(
        db,
        target_min=int(settings.get("target_min", 20)),
        target_max=int(settings.get("target_max", 40)),
        sleep_between=sleep_between)
    retire: Optional[Dict[str, Any]] = None
    if run_retire:
        try:
            retire = await retire_stale_auto_imports(db)
        except Exception as e:
            log.warning("[pdx-curator] retire step failed: %s", e)
            retire = {"retired": 0, "error": str(e)[:200]}
    tick_end = _now()
    active_total = await _count_active_auto(db)
    summary = {
        "tick_started_at":  tick_start.isoformat(),
        "tick_ended_at":    tick_end.isoformat(),
        "duration_sec":       round((tick_end - tick_start).total_seconds(), 2),
        "per_category":     per_category,
        "backfill":                 backfill,
        "retire":                     retire,
        "active_auto_total": active_total,
    }
    # Persist the last run.
    try:
        await db.system_settings.update_one(
            {"_id": SYSTEM_SETTINGS_ID},
            {"$set": {"last_run_at":         tick_end,
                              "last_run_summary": summary,
                              "updated_at":         tick_end}},
            upsert=True)
    except Exception as e:
        log.warning("[pdx-curator] last_run persist failed: %s", e)
    imported = sum(int((v or {}).get("created", 0))
                                for v in per_category.values())
    log.info(
        "Phase PDX.1 tick: imported=%d (sports=%d stocks=%d politics=%d games=%d), "
        "backfilled=%d active_total=%d duration=%.1fs",
        imported,
        int((per_category.get("sports_top") or {}).get("created", 0)),
        int((per_category.get("stocks_top") or {}).get("created", 0)),
        int((per_category.get("us_politics") or {}).get("created", 0)),
        int((per_category.get("national_games") or {}).get("created", 0)),
        int((backfill or {}).get("backfilled", 0)),
        active_total,
        summary["duration_sec"],
    )
    return summary


# ─── Scheduler entry-point ────────────────────────────────────────
async def background_curator_loop(db, *, initial_delay_sec: float = 5.0) -> None:
    """Long-running background task.  Kicks one tick almost immediately
    on boot, then loops at the configured cadence.

    Safe to cancel — every `await` between ticks is on `asyncio.sleep`,
    so the loop yields to the cancel promptly."""
    log.info("[pdx-curator] scheduler started (initial_delay=%.1fs)",
                    initial_delay_sec)
    # Small initial delay so the deferred-boot chain isn't racing us
    # for the Predexon rate-limit budget.
    try:
        await asyncio.sleep(initial_delay_sec)
    except asyncio.CancelledError:
        return
    day_counter = 0
    while True:
        try:
            settings = await get_settings(db)
            if not settings.get("enabled", True):
                # Paused via admin UI — poll the flag every 5 min.
                await asyncio.sleep(300)
                continue
            interval_min = max(5, int(settings.get("interval_min", 60)))
            # Run retire once every ~24 hours = every (24*60)/interval ticks.
            run_retire = day_counter % max(1, (24 * 60) // interval_min) == 0
            await run_curator_tick(db, run_retire=run_retire)
            day_counter += 1
            await asyncio.sleep(interval_min * 60)
        except asyncio.CancelledError:
            log.info("[pdx-curator] scheduler cancelled")
            return
        except Exception as e:
            log.exception("[pdx-curator] scheduler loop error: %s", e)
            # Cool off for 2 min before retrying.
            try:
                await asyncio.sleep(120)
            except asyncio.CancelledError:
                return


# ─── Indexes ──────────────────────────────────────────────────────
async def ensure_pdx_curator_indexes(db) -> None:
    """Idempotent index creation.  Called once at deferred-boot time."""
    try:
        await db.predict_win_campaigns.create_index(
            [("creator_type", 1), ("status", 1), ("lock_time", 1)],
            name="idx_pdx_curator_active")
    except Exception as e:
        log.debug("[pdx-curator] index idempotent skip: %s", e)
    try:
        await db.predict_win_campaigns.create_index(
            [("category_slug", 1), ("status", 1)],
            name="idx_pdx_category")
    except Exception as e:
        log.debug("[pdx-curator] index2 idempotent skip: %s", e)
    try:
        await db.system_settings.create_index(
            [("_id", 1)], name="idx_settings_id", unique=True)
    except Exception as e:
        log.debug("[pdx-curator] system_settings index skip: %s", e)


async def backfill_existing_campaigns_points(db) -> Dict[str, int]:
    """One-shot migration: set default `points_reward=25` and
    `import_source="admin_manual"` on any existing campaign row missing
    those fields.  Preserves rows already carrying the values."""
    res1 = await db.predict_win_campaigns.update_many(
        {"points_reward": {"$exists": False}},
        {"$set": {"points_reward": 25}})
    res2 = await db.predict_win_campaigns.update_many(
        {"import_source": {"$exists": False}},
        {"$set": {"import_source": "admin_manual"}})
    return {
        "points_backfilled":  int(getattr(res1, "modified_count", 0) or 0),
        "source_backfilled": int(getattr(res2, "modified_count", 0) or 0),
    }


__all__ = [
    "DEFAULT_SETTINGS", "SYSTEM_SETTINGS_ID",
    "get_settings", "update_settings", "is_enabled",
    "import_top_events_by_category",
    "ensure_minimum_active", "retire_stale_auto_imports",
    "run_curator_tick", "background_curator_loop",
    "ensure_pdx_curator_indexes",
    "backfill_existing_campaigns_points",
]
