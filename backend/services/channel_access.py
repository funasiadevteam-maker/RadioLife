"""Phase 10c — Exclusive Channel Gating.

Single source of truth for "can this user start this channel?".  Reused
by `/api/radio/start`, `/api/radio/switch_channel`, lobby creation, and
the `GET /api/channels` listing endpoint.

Access tiers (stored on `channels.exclusivity_tier`):
  free               — always allow
  premium            — allow if user.is_premium
  ambassador_l3      — allow if user current ambassador level >= 3
                       OR user has an active `user_ambassador_unlocks`
                       row with unlock_kind="exclusive_channel" + ref=<slug>
  ambassador_l4      — same, level >= 4
  ambassador_l5      — same, level >= 5
  exclusive_unlock   — allow only if user has a non-expired row in
                       `user_ambassador_unlocks` matching channel
                       `unlock_required_id`.

`check_channel_access(db, user, channel) -> AccessResult` is the public
API.  It accepts an optional `cache` dict so a single HTTP roundtrip
doesn't re-query Mongo for every channel in a listing page.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional


# Tier ordering — higher number = stricter
_AMB_TIER_TO_LEVEL = {
    "ambassador_l3": 3,
    "ambassador_l4": 4,
    "ambassador_l5": 5,
}
_LEVEL_NAMES = {
    1: "Listener", 2: "Regular", 3: "Insider",
    4: "Ambassador", 5: "Diamond Ambassador",
}
_AMB_LEVEL_MIN_POINTS = {1: 0, 2: 100, 3: 500, 4: 2000, 5: 10000}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt):
    """Coerce a datetime (naive or aware) to UTC for safe comparison."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _ok(reason: str, **extra) -> dict:
    return {"allowed": True, "reason": reason,
              "required_tier": None, "current_tier": None,
              "unlock_message": None, "cta": None,
              "upgrade_path": None, **extra}


def _deny(reason: str, *, required_tier: Optional[str],
            current_tier: Optional[str],
            unlock_message: str, cta: Optional[dict],
            upgrade_path: str, **extra) -> dict:
    return {"allowed": False, "reason": reason,
              "required_tier": required_tier,
              "current_tier": current_tier,
              "unlock_message": unlock_message,
              "cta": cta, "upgrade_path": upgrade_path, **extra}


async def _load_request_state(db, user: dict, cache: Optional[dict]):
    """Lazy-load the per-request state (ambassador level + active unlocks)
    so a channel listing of N rows hits Mongo at most twice total."""
    if cache is None:
        cache = {}
    if "ambassador_state" not in cache:
        uid = (user or {}).get("user_id")
        if uid:
            st = await db.user_ambassador_state.find_one({"user_id": uid})
        else:
            st = None
        cache["ambassador_state"] = st or {}
    if "active_unlocks" not in cache:
        uid = (user or {}).get("user_id")
        if uid:
            cur = db.user_ambassador_unlocks.find(
                {"user_id": uid,
                  "$or": [{"expires_at": {"$gt": _now()}},
                            {"expires_at": None}]})
            cache["active_unlocks"] = [u async for u in cur]
        else:
            cache["active_unlocks"] = []
    return cache


def _has_channel_unlock(active_unlocks: list, channel_slug: str) -> bool:
    """True if user has a non-expired `exclusive_channel` unlock for this slug."""
    now = _now()
    for u in active_unlocks:
        if u.get("unlock_kind") != "exclusive_channel":
            continue
        if u.get("ref") != channel_slug:
            continue
        exp = _to_utc(u.get("expires_at"))
        if exp and exp <= now:
            continue
        return True
    return False


def _has_named_unlock(active_unlocks: list, unlock_id: str) -> bool:
    """True if user has a non-expired row whose `ref` OR `unlock_id`
    matches the supplied id (loose match so existing rows that key by
    `ref` keep working)."""
    now = _now()
    for u in active_unlocks:
        if u.get("ref") != unlock_id and u.get("unlock_id") != unlock_id:
            continue
        exp = _to_utc(u.get("expires_at"))
        if exp and exp <= now:
            continue
        return True
    return False


async def check_channel_access(db, user: dict, channel: dict, *,
                                          cache: Optional[dict] = None) -> dict:
    """Return an AccessResult dict.  See module docstring for fields.

    `user` is the authenticated user dict (must include `user_id`,
    `is_premium`).  Anonymous callers may pass `None` — they only get
    `free` channels.  `channel` is a row from the `channels` collection.
    """
    tier = (channel or {}).get("exclusivity_tier") or "free"
    slug = (channel or {}).get("_id") or (channel or {}).get("slug")
    name = (channel or {}).get("name") or slug
    gating_message = (channel or {}).get("gating_message")

    if tier == "free":
        return _ok("free_channel")

    if not user:
        # Anonymous → block anything non-free
        return _deny(
            "anonymous_user",
            required_tier=tier, current_tier=None,
            unlock_message=gating_message
                or "Sign in to access this channel.",
            cta={"label": "Sign in", "href": "/login"},
            upgrade_path="premium")

    if tier == "premium":
        if user.get("is_premium"):
            return _ok("premium_active")
        return _deny(
            "premium_required",
            required_tier="premium", current_tier="free",
            unlock_message=gating_message
                or f"{name} is a Premium channel. Upgrade to unlock.",
            cta={"label": "Upgrade to Premium", "href": "/pricing"},
            upgrade_path="premium")

    cache = await _load_request_state(db, user, cache)
    state = cache.get("ambassador_state") or {}
    unlocks = cache.get("active_unlocks") or []
    # Schema drift — some rows use `level`, newer ones `current_level`.
    current_level = int(state.get("current_level")
                                or state.get("level") or 1)
    current_points = int(state.get("points") or 0)

    if tier in _AMB_TIER_TO_LEVEL:
        required_level = _AMB_TIER_TO_LEVEL[tier]
        if current_level >= required_level:
            return _ok("ambassador_level_ok",
                         current_tier=f"ambassador_l{current_level}")
        # Honor a temporary `exclusive_channel` unlock too
        if _has_channel_unlock(unlocks, slug):
            return _ok("ambassador_unlock_active",
                         current_tier=f"ambassador_l{current_level}")
        next_level_pts = _AMB_LEVEL_MIN_POINTS.get(required_level, 0)
        pts_needed = max(0, next_level_pts - current_points)
        level_name = _LEVEL_NAMES.get(required_level, f"Level {required_level}")
        return _deny(
            "ambassador_level_required",
            required_tier=tier,
            current_tier=f"ambassador_l{current_level}",
            unlock_message=(
                gating_message
                or f"Reach {level_name} (L{required_level}) to unlock {name}."),
            cta={"label": f"Earn {pts_needed} more ambassador points",
                  "href": "/passport",
                  "points_needed": pts_needed,
                  "current_points": current_points,
                  "required_points": next_level_pts,
                  "required_level": required_level,
                  "required_level_name": level_name},
            upgrade_path="earn_badges")

    if tier == "exclusive_unlock":
        unlock_id = (channel or {}).get("unlock_required_id")
        if not unlock_id:
            # Misconfigured channel — treat as locked but tell the operator
            return _deny(
                "exclusive_unlock_misconfigured",
                required_tier=tier, current_tier=None,
                unlock_message=(
                    gating_message
                    or "This channel is currently unavailable."),
                cta=None, upgrade_path="specific_unlock")
        if (_has_named_unlock(unlocks, unlock_id)
            or _has_channel_unlock(unlocks, slug)):
            return _ok("exclusive_unlock_active")
        return _deny(
            "exclusive_unlock_required",
            required_tier=tier, current_tier=f"ambassador_l{current_level}",
            unlock_message=(
                gating_message
                or f"{name} requires a special unlock to access."),
            cta={"label": "How to unlock?", "href": "/passport",
                  "unlock_required_id": unlock_id},
            upgrade_path="specific_unlock")

    # Unknown tier — fail closed but make it obvious in logs
    return _deny(
        f"unknown_tier:{tier}",
        required_tier=tier, current_tier=None,
        unlock_message=(
            gating_message
            or "This channel is currently unavailable."),
        cta=None, upgrade_path="specific_unlock")


def access_to_403_detail(result: dict, channel: dict) -> dict:
    """Convert an AccessResult to a stable 403 detail body.  Frontend
    binds on `code` (kept matching the legacy `premium_required` shape
    where possible) so it can render the gate without translation."""
    if result.get("upgrade_path") == "premium":
        code = "premium_required"
    elif result.get("upgrade_path") == "earn_badges":
        code = "ambassador_level_required"
    elif result.get("upgrade_path") == "specific_unlock":
        code = "exclusive_unlock_required"
    else:
        code = "access_denied"
    return {
        "code": code,
        "channel": channel.get("_id") or channel.get("slug"),
        "channel_name": channel.get("name"),
        "message": result.get("unlock_message"),
        "required_tier": result.get("required_tier"),
        "current_tier": result.get("current_tier"),
        "upgrade_path": result.get("upgrade_path"),
        "cta": result.get("cta"),
        "reason": result.get("reason"),
    }


# ─── Demo seed — 2 exclusive channels ─────────────────────────────────
PHASE10C_EXCLUSIVE_SEEDS = [
    {
        "_id": "vip_lounge",
        "slug": "vip_lounge",
        "name": "VIP Lounge",
        "tagline": "For Insiders, by Insiders",
        "description": "An ambassador-exclusive channel with deep cuts, rare remixes, and longer DJ sets. Earn your way in.",
        "cover_color": "#F5D76E",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.6},
                            {"language": "english", "weight": 0.4}],
        "allowed_genres": ["bollywood", "pop", "indie", "retro"],
        "allowed_moods": ["uplifting", "romantic", "energetic", "chill"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "monika_dubai", "role": "primary"},
                    {"voice_key": "aarti_morning", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "retro", "mood_match",
                            "current_hit", "regional", "wildcard"],
            "cycle_length": 6,
        },
        "default_for_time": ["evening", "late_night"],
        "sort_order": 50,
        "active": True,
        "market": "dubai",
        "exclusivity_tier": "ambassador_l3",
        "gating_message": ("Reach Insider (L3) to unlock the VIP Lounge "
                             "— premium music for premium ears."),
    },
    {
        "_id": "diamond_room",
        "slug": "diamond_room",
        "name": "Diamond Room",
        "tagline": "The top floor",
        "description": "Diamond Ambassadors only. The most curated mix on BigFM, served by Aarti & Kabir.",
        "cover_color": "#B9F2FF",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.5},
                            {"language": "english", "weight": 0.5}],
        "allowed_genres": ["bollywood", "pop", "indie", "retro", "electronic"],
        "allowed_moods": ["uplifting", "romantic", "energetic"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "aarti_morning", "role": "primary"},
                    {"voice_key": "kabir_hindi", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "wildcard", "retro", "current_hit",
                            "mood_match", "regional"],
            "cycle_length": 6,
        },
        "default_for_time": ["evening", "late_night"],
        "sort_order": 51,
        "active": True,
        "market": "dubai",
        "exclusivity_tier": "ambassador_l5",
        "gating_message": "Diamond Ambassadors only.",
    },
]


async def seed_exclusive_channels(db) -> dict:
    """Idempotent.  Adds the demo exclusive channels and backfills
    `exclusivity_tier="free"` on every existing channel that doesn't
    have the field yet."""
    created = 0
    for ch in PHASE10C_EXCLUSIVE_SEEDS:
        doc = {**ch, "updated_at": _now()}
        existing = await db.channels.find_one({"_id": ch["_id"]})
        if existing:
            # Don't blast operator overrides — only set fields that are
            # actually missing on the existing row.
            patch = {k: v for k, v in doc.items()
                        if existing.get(k) in (None, "") and k != "_id"}
            if patch:
                await db.channels.update_one(
                    {"_id": ch["_id"]}, {"$set": patch})
            # Always ensure the exclusivity_tier matches the seed unless
            # operator has explicitly overridden via admin endpoint —
            # tracked via `exclusivity_tier_locked` (operator opt-in).
            if not existing.get("exclusivity_tier_locked"):
                await db.channels.update_one(
                    {"_id": ch["_id"]},
                    {"$set": {"exclusivity_tier": ch["exclusivity_tier"],
                                "gating_message": ch["gating_message"]}})
        else:
            doc["created_at"] = doc["updated_at"]
            await db.channels.insert_one(doc)
            created += 1
    # Backfill existing channels with default tier="free"
    backfill = await db.channels.update_many(
        {"exclusivity_tier": {"$exists": False}},
        {"$set": {"exclusivity_tier": "free"}})
    # Legacy `premium_only=True` rows should be `exclusivity_tier=premium`
    # so we have a single source of truth.  Don't overwrite operator-set
    # tiers (denoted by `exclusivity_tier_locked`).
    promote = await db.channels.update_many(
        {"premium_only": True,
          "exclusivity_tier": "free",
          "exclusivity_tier_locked": {"$ne": True}},
        {"$set": {"exclusivity_tier": "premium"}})
    return {"created": created,
              "backfilled_free": backfill.modified_count,
              "promoted_premium": promote.modified_count,
              "total_exclusive_seeds": len(PHASE10C_EXCLUSIVE_SEEDS)}


__all__ = [
    "check_channel_access", "access_to_403_detail",
    "seed_exclusive_channels", "PHASE10C_EXCLUSIVE_SEEDS",
]
