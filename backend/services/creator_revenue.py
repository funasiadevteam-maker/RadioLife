"""Phase 41 Session 6.A — Creator revenue share helpers.

Math is kept deliberately simple in this MVP (flat 70/30 split,
`CREATOR_REV_SHARE_PCT` env-tunable). The richer tier system from
`/app/memory/handoffs/phase41_revenue_attribution_design.md` (5-tier,
500-hour floor, monthly cron) will land in a follow-up — the ledger
schema is forward-compatible with that math.

Public helpers:

  - `compute_split(gross_amount_cents)`
       → returns `(creator_amount_cents, house_cut_cents)`.

  - `write_ledger_row(db, *, station, owner_user_id, source_type,
                       source_ref, gross_amount_cents,
                       attribution_metadata=None, occurred_at=None,
                       currency="USD")`
       → upserts a `creator_earnings_ledger` document idempotently
         keyed on `source_ref`. Used by attribution writers in
         banner_ads, listener_sessions, the admin direct-deal route,
         and the future Stripe webhook tip handler. Returns the
         inserted doc OR the existing one on dup-key.

  - `compute_earnings(db, *, owner_user_id, station_slug=None,
                       start=None, end=None)`
       → composite payload for the owner-facing dashboard.

  - `ensure_creator_revenue_indexes(db)` — startup index bootstrap.

PREMIUM_LISTEN_RATE_PER_MIN_CENTS controls the MOCKED_PRORATA flat
credit per premium minute. Real pro-rata pool math lands later once
we have actual subscription-revenue numbers to allocate.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

log = logging.getLogger("bigfm.creator_revenue")

CREATOR_REV_SHARE_PCT = int(os.environ.get("CREATOR_REV_SHARE_PCT", "70"))
PREMIUM_LISTEN_RATE_PER_MIN_CENTS = float(
    os.environ.get("PREMIUM_LISTEN_RATE_PER_MIN_CENTS", "0.05"))  # 0.05¢/min
TIP_PLATFORM_FEE_PCT = int(os.environ.get("TIP_PLATFORM_FEE_PCT", "10"))

VALID_SOURCE_TYPES = {
    "banner_impression",
    "audio_ad_completion",
    "premium_listen",
    "tip",
    "direct_deal",
}
LEDGER_STATUSES = ("recorded", "paid_out", "reversed")


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


def compute_split(gross_amount_cents: int,
                    *, share_pct: Optional[int] = None) -> tuple[int, int]:
    """Returns (creator_amount, house_cut). Integer cents. Rounding
    favours the house by 0.5¢ at most (truncation)."""
    pct = share_pct if share_pct is not None else CREATOR_REV_SHARE_PCT
    if gross_amount_cents <= 0:
        return 0, 0
    creator = (gross_amount_cents * pct) // 100
    house   = gross_amount_cents - creator
    return creator, house


async def write_ledger_row(db, *, station: dict, owner_user_id: str,
                              source_type: str, source_ref: str,
                              gross_amount_cents: int,
                              attribution_metadata: Optional[dict] = None,
                              occurred_at: Optional[datetime] = None,
                              currency: str = "USD",
                              share_pct: Optional[int] = None,
                              status: str = "recorded") -> Optional[dict]:
    """Idempotent upsert keyed on `source_ref`. Returns the inserted/
    existing doc, or None on validation failure (logged + swallowed —
    we never block the caller's primary event)."""
    if source_type not in VALID_SOURCE_TYPES:
        log.warning("[ledger] invalid source_type=%s", source_type)
        return None
    if not source_ref:
        log.warning("[ledger] empty source_ref skipped")
        return None
    creator_amount, house_cut = compute_split(gross_amount_cents,
                                                share_pct=share_pct)
    occurred = occurred_at or _now()
    doc = {
        "_id":                 source_ref,
        "source_ref":          source_ref,
        "station_id":          station.get("station_id"),
        "station_slug":        station.get("slug"),
        "owner_user_id":       owner_user_id,
        "source_type":         source_type,
        "gross_amount_cents":  int(gross_amount_cents),
        "house_cut_cents":     int(house_cut),
        "creator_amount_cents": int(creator_amount),
        "currency":            currency,
        "share_pct":           share_pct if share_pct is not None
                                                else CREATOR_REV_SHARE_PCT,
        "occurred_at":         occurred,
        "status":              status,
        "payout_id":           None,
        "attribution_metadata": attribution_metadata or {},
        "created_at":          _now(),
    }
    try:
        await db.creator_earnings_ledger.insert_one(doc)
        return doc
    except Exception as e:
        # Duplicate key → already recorded; fetch & return.
        existing = await db.creator_earnings_ledger.find_one(
            {"_id": source_ref})
        if existing:
            return existing
        log.warning("[ledger] insert failed (%s): %s", source_type, e)
        return None


async def credit_premium_listen(db, *, station: dict, listener_user_id: str,
                                 session_token: str, duration_sec: int) -> None:
    """Called from listener_sessions.leave AFTER archiving. Skips when:
      - the station has no owner
      - the listener is the owner themselves
      - duration_sec is implausibly short (<10s)
      - listener_user_id is None (anonymous)
    """
    if duration_sec is None or duration_sec < 10:
        return
    if not listener_user_id:
        return
    if not station:
        return
    owner = station.get("owner_user_id")
    if not owner or owner == listener_user_id:
        return
    # Premium-only credit. MOCKED_PRORATA — flat per-minute rate until
    # we have a real subscription-pool to allocate from.
    user = await db.users.find_one({"user_id": listener_user_id})
    if not user or not user.get("is_premium"):
        return
    minutes = duration_sec / 60.0
    gross_cents = int(round(minutes * PREMIUM_LISTEN_RATE_PER_MIN_CENTS))
    if gross_cents <= 0:
        return
    source_ref = f"pl_{session_token}"
    await write_ledger_row(
        db, station=station, owner_user_id=owner,
        source_type="premium_listen",
        source_ref=source_ref,
        gross_amount_cents=gross_cents,
        attribution_metadata={
            "listener_user_id": listener_user_id,
            "duration_sec":     duration_sec,
            "mock":             "MOCKED_PRORATA flat per-minute credit",
        })


# ---- dashboard aggregations -----------------------------------------
async def compute_earnings(db, *, owner_user_id: str,
                              station_slug: Optional[str] = None,
                              start: Optional[datetime] = None,
                              end: Optional[datetime] = None,
                              recent_limit: int = 50) -> dict:
    end = end or _now()
    match: dict = {"owner_user_id": owner_user_id}
    if station_slug:
        match["station_slug"] = station_slug
    if start is not None:
        match["occurred_at"] = {"$gte": start, "$lt": end}
    else:
        match["occurred_at"] = {"$lt": end}

    # Headline totals
    pipeline_totals = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "gross":    {"$sum": "$gross_amount_cents"},
            "creator":  {"$sum": "$creator_amount_cents"},
            "house":    {"$sum": "$house_cut_cents"},
            "count":    {"$sum": 1},
        }},
    ]
    tot = await db.creator_earnings_ledger.aggregate(pipeline_totals).to_list(1)
    headline = tot[0] if tot else {
        "gross": 0, "creator": 0, "house": 0, "count": 0}

    # Per-source breakdown
    src_pipe = [
        {"$match": match},
        {"$group": {
            "_id":     "$source_type",
            "gross":   {"$sum": "$gross_amount_cents"},
            "creator": {"$sum": "$creator_amount_cents"},
            "count":   {"$sum": 1},
        }},
        {"$sort": {"creator": -1}},
    ]
    by_source: list = []
    async for r in db.creator_earnings_ledger.aggregate(src_pipe):
        by_source.append({
            "source_type": r["_id"],
            "gross_cents":   r.get("gross", 0),
            "creator_cents": r.get("creator", 0),
            "count":         r.get("count", 0),
        })

    # Per-station breakdown (only meaningful when station_slug is None)
    by_station: list = []
    if not station_slug:
        st_pipe = [
            {"$match": match},
            {"$group": {
                "_id": {"slug": "$station_slug", "id": "$station_id"},
                "gross":   {"$sum": "$gross_amount_cents"},
                "creator": {"$sum": "$creator_amount_cents"},
                "count":   {"$sum": 1},
            }},
            {"$sort": {"creator": -1}},
            {"$limit": 20},
        ]
        async for r in db.creator_earnings_ledger.aggregate(st_pipe):
            k = r.get("_id") or {}
            by_station.append({
                "station_slug": k.get("slug"),
                "station_id":   k.get("id"),
                "gross_cents":   r.get("gross", 0),
                "creator_cents": r.get("creator", 0),
                "count":         r.get("count", 0),
            })

    # Pending payout = creator_amount where status='recorded'
    pending_match = dict(match)
    pending_match["status"] = "recorded"
    pending = await db.creator_earnings_ledger.aggregate([
        {"$match": pending_match},
        {"$group": {"_id": None,
                    "creator": {"$sum": "$creator_amount_cents"}}},
    ]).to_list(1)
    pending_cents = pending[0].get("creator", 0) if pending else 0

    # Lifetime — ignores the window filter
    life_match = {"owner_user_id": owner_user_id}
    if station_slug:
        life_match["station_slug"] = station_slug
    life = await db.creator_earnings_ledger.aggregate([
        {"$match": life_match},
        {"$group": {"_id": None,
                    "creator": {"$sum": "$creator_amount_cents"}}},
    ]).to_list(1)
    lifetime_cents = life[0].get("creator", 0) if life else 0

    # Recent rows
    cur = db.creator_earnings_ledger.find(match).sort(
        [("occurred_at", -1)]).limit(recent_limit)
    rows: list = []
    async for r in cur:
        r.pop("_id", None)
        oc = r.get("occurred_at")
        ca = r.get("created_at")
        rows.append({
            "source_ref":           r.get("source_ref"),
            "station_slug":         r.get("station_slug"),
            "source_type":          r.get("source_type"),
            "gross_amount_cents":   r.get("gross_amount_cents", 0),
            "house_cut_cents":      r.get("house_cut_cents", 0),
            "creator_amount_cents": r.get("creator_amount_cents", 0),
            "currency":             r.get("currency", "USD"),
            "status":               r.get("status", "recorded"),
            "occurred_at":          (oc.isoformat()
                                       if isinstance(oc, datetime) else oc),
            "created_at":           (ca.isoformat()
                                       if isinstance(ca, datetime) else ca),
            "attribution_metadata": r.get("attribution_metadata") or {},
        })

    return {
        "window_starts_at": (start.isoformat() if start else None),
        "window_ends_at":   end.isoformat(),
        "headline": {
            "total_creator_cents":  headline.get("creator", 0),
            "total_gross_cents":    headline.get("gross", 0),
            "total_house_cents":    headline.get("house", 0),
            "ledger_row_count":     headline.get("count", 0),
            "pending_payout_cents": pending_cents,
            "lifetime_creator_cents": lifetime_cents,
            "currency":             "USD",
        },
        "by_source":     by_source,
        "by_station":    by_station,
        "recent_ledger": rows,
        "config": {
            "share_pct": CREATOR_REV_SHARE_PCT,
        },
    }


async def ensure_creator_revenue_indexes(db) -> dict:
    created = []
    try:
        # Idempotent: source_ref is unique sparse so writes don't dupe.
        await db.creator_earnings_ledger.create_index(
            "source_ref", unique=True, sparse=True,
            name="cel_source_ref_uq")
        created.append("cel_source_ref_uq")
    except Exception as e:
        log.warning("[ledger] index source_ref: %s", e)
    try:
        await db.creator_earnings_ledger.create_index(
            [("owner_user_id", 1), ("occurred_at", -1)],
            name="cel_owner_time")
        created.append("cel_owner_time")
    except Exception as e:
        log.warning("[ledger] index owner_time: %s", e)
    try:
        await db.creator_earnings_ledger.create_index(
            [("station_slug", 1), ("occurred_at", -1)],
            name="cel_slug_time")
        created.append("cel_slug_time")
    except Exception as e:
        log.warning("[ledger] index slug_time: %s", e)
    try:
        await db.payout_requests.create_index(
            [("user_id", 1), ("created_at", -1)],
            name="pr_user_time")
        created.append("pr_user_time")
    except Exception as e:
        log.warning("[ledger] index payout: %s", e)
    return {"created": created}
