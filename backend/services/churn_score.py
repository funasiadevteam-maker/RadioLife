"""Phase 12b — Churn risk scoring.

Pure-compute module.  Takes a user_id and the live `db` handle and
returns a `{score, band, signals, computed_at, expires_at}` dict.

Signals (weighted heuristic, total = 100):
    days_since_last_play:    0..40  pts   (heaviest)
    listening_trend_drop:    0..15  pts   (last 7d vs prior 7d)
    subscription_state:      0..25  pts   (canceled / past_due / active)
    engagement_recency:      0..10  pts   (game_sessions + coupons activity)
    social_activity:         0..10  pts   (lobby_messages / lobby_joins)

Bands:
    0..25   healthy
    26..50  cooling
    51..75  at_risk
    76..100 dormant
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("bigfm.churn")

SCORE_TTL = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def band_for_score(score: int) -> str:
    if score <= 25: return "healthy"
    if score <= 50: return "cooling"
    if score <= 75: return "at_risk"
    return "dormant"


async def _days_since_last_play(db, user_id: str) -> float | None:
    doc = await db.playback_logs.find_one(
        {"user_id": user_id, "event": "play_start"},
        sort=[("timestamp", -1)], projection={"timestamp": 1})
    if not doc or not doc.get("timestamp"):
        return None
    ts = doc["timestamp"]
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (_now() - ts).total_seconds() / 86400.0)


async def _listening_trend(db, user_id: str) -> dict:
    """Returns {last_7d_min, prior_7d_min, drop_ratio}."""
    now = _now()
    last_start = now - timedelta(days=7)
    prior_start = now - timedelta(days=14)
    pipe_last = [
        {"$match": {"user_id": user_id,
                       "timestamp": {"$gte": last_start}}},
        {"$group": {"_id": None,
                       "m": {"$sum": "$minutes_credited"}}},
    ]
    pipe_prior = [
        {"$match": {"user_id": user_id,
                       "timestamp": {"$gte": prior_start, "$lt": last_start}}},
        {"$group": {"_id": None,
                       "m": {"$sum": "$minutes_credited"}}},
    ]
    last_doc = await db.listening_heartbeats.aggregate(pipe_last).to_list(1)
    prior_doc = await db.listening_heartbeats.aggregate(pipe_prior).to_list(1)
    last = int(last_doc[0]["m"]) if last_doc else 0
    prior = int(prior_doc[0]["m"]) if prior_doc else 0
    drop = 0.0
    if prior > 0:
        drop = max(0.0, (prior - last) / prior)
    elif last == 0:
        drop = 1.0  # nothing in either window — drop is total
    return {"last_7d_min": last, "prior_7d_min": prior, "drop_ratio": drop}


async def _engagement_recency_days(db, user_id: str) -> dict:
    """Recency in days for game / coupon / lobby activity (None if never)."""
    out = {"game": None, "coupon": None, "lobby": None}
    # game
    g = await db.game_sessions.find_one(
        {"user_id": user_id}, sort=[("created_at", -1)],
        projection={"created_at": 1})
    if g and g.get("created_at"):
        ts = g["created_at"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        out["game"] = (_now() - ts).total_seconds() / 86400.0
    # coupon
    c = await db.coupons.find_one(
        {"user_id": user_id}, sort=[("claimed_at", -1)],
        projection={"claimed_at": 1})
    if c and c.get("claimed_at"):
        ts = c["claimed_at"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        out["coupon"] = (_now() - ts).total_seconds() / 86400.0
    # lobby message
    m = await db.lobby_messages.find_one(
        {"user_id": user_id}, sort=[("created_at", -1)],
        projection={"created_at": 1})
    if m and m.get("created_at"):
        ts = m["created_at"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        out["lobby"] = (_now() - ts).total_seconds() / 86400.0
    return out


async def compute_score(db, user_id: str) -> dict:
    """Routes to v1 or v2 based on env `BIGFM_CHURN_MODEL` (default v1).
    Both paths return the same shape; v2 attaches `model_version: "v2"`."""
    import os as _os
    model = (_os.environ.get("BIGFM_CHURN_MODEL") or "v1").lower()
    if model == "v2":
        out = await _compute_score_v2(db, user_id)
        out["model_version"] = "v2"
        return out
    out = await _compute_score_v1(db, user_id)
    out["model_version"] = "v1"
    return out


async def _compute_score_v1(db, user_id: str) -> dict:
    """Returns the full churn payload for a user. Pure compute, no write."""
    user = await db.users.find_one({"user_id": user_id},
                                                {"subscription": 1,
                                                  "is_premium": 1, "created_at": 1})
    if not user:
        raise ValueError(f"user not found: {user_id}")

    signals: dict = {}

    # 1. Days since last play  (0..40 pts)
    dslp = await _days_since_last_play(db, user_id)
    signals["days_since_last_play"] = (
        round(dslp, 1) if dslp is not None else None)
    if dslp is None:
        # Never played → use account age, capped at 30 days for scoring
        created = user.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        account_age_days = (_now() - created).total_seconds() / 86400.0 \
                                  if created else 999
        # never-played user with old account ≈ dormant
        play_pts = min(40, int(account_age_days * 1.5))
    else:
        # 0d → 0pts, 30d+ → 40pts (linear)
        play_pts = min(40, int(dslp * 40 / 30))
    signals["play_recency_pts"] = play_pts

    # 2. Listening trend (0..15 pts)
    trend = await _listening_trend(db, user_id)
    signals["listening_trend"] = trend
    trend_pts = int(trend["drop_ratio"] * 15)
    signals["listening_trend_pts"] = trend_pts

    # 3. Subscription state (0..25 pts)
    sub = user.get("subscription") or {}
    status = sub.get("status") or ("active" if user.get("is_premium")
                                              else "none")
    if status == "active":
        sub_pts = 0
    elif status == "trialing":
        sub_pts = 5
    elif status == "past_due":
        sub_pts = 20
    elif status in ("canceled", "incomplete_expired", "unpaid"):
        sub_pts = 25
    else:  # "none" / never paid
        sub_pts = 8
    signals["subscription_status"] = status
    signals["subscription_pts"] = sub_pts

    # 4. Engagement recency (0..10 pts) — min recency across game/coupon
    eng = await _engagement_recency_days(db, user_id)
    signals["engagement_days"] = eng
    candidates = [v for v in (eng["game"], eng["coupon"]) if v is not None]
    eng_recency = min(candidates) if candidates else None
    if eng_recency is None:
        eng_pts = 10
    elif eng_recency <= 3:
        eng_pts = 0
    elif eng_recency <= 14:
        eng_pts = 4
    else:
        eng_pts = 10
    signals["engagement_pts"] = eng_pts

    # 5. Social activity (0..10 pts)
    social_days = eng.get("lobby")
    if social_days is None:
        social_pts = 7
    elif social_days <= 3:
        social_pts = 0
    elif social_days <= 14:
        social_pts = 4
    else:
        social_pts = 8
    signals["social_pts"] = social_pts

    total = min(100, play_pts + trend_pts + sub_pts + eng_pts + social_pts)
    return {
        "user_id": user_id,
        "score": total,
        "band": band_for_score(total),
        "signals": signals,
        "computed_at": _now(),
        "expires_at": _now() + SCORE_TTL,
    }


async def ensure_churn_indexes(db) -> None:
    await db.churn_scores.create_index("user_id", unique=True)
    await db.churn_scores.create_index("band")
    try:
        await db.churn_scores.create_index("expires_at",
                                                          expireAfterSeconds=0)
    except Exception:
        pass


# ─── Phase 13c — Churn v2 (logistic-regression-lite) ─────────────────
# Hand-tuned weights, no learned model. Features normalized to 0..1
# then dot-producted with the weights, run through sigmoid, scaled to
# 0..100. The bands stay identical to v1 so downstream code never
# breaks.
_V2_WEIGHTS = {
    "days_since_last_play_30d":      4.0,   # heavy positive churn signal
    "subscription_past_due":         2.5,
    "subscription_canceled_7d":      3.0,
    "subscription_active":          -2.0,
    "playback_decline_7v14":         2.0,
    "lobby_inactivity_7d":           1.0,
    "game_inactivity_7d":            1.0,
    "coupon_inactivity_30d":         0.8,
    "low_ambassador_level":          0.6,
    "low_friend_count":              0.5,
}
_V2_BIAS = -3.5


def _sigmoid(x: float) -> float:
    import math
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


async def _compute_score_v2(db, user_id: str) -> dict:
    user = await db.users.find_one(
        {"user_id": user_id},
        {"subscription": 1, "is_premium": 1, "created_at": 1,
          "ambassador_level": 1, "friend_ids": 1})
    if not user:
        raise ValueError(f"user not found: {user_id}")

    # Feature gathering
    dslp = await _days_since_last_play(db, user_id)
    trend = await _listening_trend(db, user_id)
    eng = await _engagement_recency_days(db, user_id)
    sub = user.get("subscription") or {}
    status = sub.get("status") or ("active" if user.get("is_premium")
                                              else "none")
    canceled_at = sub.get("canceled_at")
    canceled_within_7d = False
    if canceled_at:
        from datetime import datetime as _dt
        ca = (canceled_at if isinstance(canceled_at, _dt)
                  else _dt.fromisoformat(
                      str(canceled_at).replace("Z", "+00:00")))
        if ca.tzinfo is None: ca = ca.replace(tzinfo=timezone.utc)
        canceled_within_7d = (_now() - ca).days <= 7

    feats = {
        "days_since_last_play_30d":
            min(1.0, (dslp or 30.0) / 30.0),
        "subscription_past_due": 1.0 if status == "past_due" else 0.0,
        "subscription_canceled_7d":
            1.0 if (canceled_within_7d
                          or status in ("canceled", "incomplete_expired",
                                             "unpaid")) else 0.0,
        "subscription_active": 1.0 if status == "active" else 0.0,
        "playback_decline_7v14":
            max(0.0, min(1.0, float(trend.get("drop_ratio") or 0.0))),
        "lobby_inactivity_7d":
            min(1.0, ((eng.get("lobby") or 30) / 14.0)),
        "game_inactivity_7d":
            min(1.0, ((eng.get("game") or 30) / 14.0)),
        "coupon_inactivity_30d":
            min(1.0, ((eng.get("coupon") or 60) / 30.0)),
        "low_ambassador_level":
            max(0.0, 1.0 - (int(user.get("ambassador_level") or 0)
                                    / 5.0)),
        "low_friend_count":
            max(0.0, 1.0 - (len(user.get("friend_ids") or []) / 10.0)),
    }
    z = _V2_BIAS + sum(_V2_WEIGHTS[k] * v for k, v in feats.items())
    prob = _sigmoid(z)
    score = int(round(prob * 100))
    return {
        "user_id": user_id,
        "score": score,
        "band": band_for_score(score),
        "signals": {**feats,
                          "subscription_status": status,
                          "days_since_last_play":
                              round(dslp, 1) if dslp is not None else None,
                          "model": "v2",
                          "logit_z": round(z, 3),
                          "prob_churn": round(prob, 4)},
        "computed_at": _now(),
        "expires_at": _now() + SCORE_TTL,
    }


# Override placeholder so we don't accidentally double-define
async def _ensure_churn_indexes_dummy(db) -> None:
    return None


async def get_or_recompute(db, user_id: str, *, force: bool = False) -> dict:
    """Returns the cached score if fresh, else recomputes + upserts."""
    if not force:
        existing = await db.churn_scores.find_one({"user_id": user_id})
        if existing:
            exp = existing.get("expires_at")
            if isinstance(exp, datetime):
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > _now():
                    existing.pop("_id", None)
                    return existing
    payload = await compute_score(db, user_id)
    await db.churn_scores.update_one(
        {"user_id": user_id}, {"$set": payload}, upsert=True)
    return payload


async def recompute_all(db, *, batch_size: int = 200) -> dict:
    """Daily sweep: recompute churn score for every active user."""
    total = 0; errors = 0
    async for u in db.users.find({}, {"user_id": 1}):
        try:
            await get_or_recompute(db, u["user_id"], force=True)
            total += 1
        except Exception as e:
            errors += 1
            logger.warning(f"churn recompute failed user={u.get('user_id')}: {e}")
    return {"recomputed": total, "errors": errors}


async def churn_distribution(db) -> dict:
    """Histogram by band + top 50 at-risk/dormant users."""
    pipe = [{"$group": {"_id": "$band", "count": {"$sum": 1}}}]
    bands = {"healthy": 0, "cooling": 0, "at_risk": 0, "dormant": 0}
    async for r in db.churn_scores.aggregate(pipe):
        bands[r["_id"] or "healthy"] = int(r["count"])
    # Top 50 at-risk + dormant (highest scores first)
    top = []
    cur = (db.churn_scores
                .find({"band": {"$in": ["at_risk", "dormant"]}})
                .sort("score", -1).limit(50))
    async for d in cur:
        d.pop("_id", None)
        top.append(d)
    return {"bands": bands, "top_at_risk": top,
              "total_scored": sum(bands.values())}
