"""Fun AI RadioProgrammingPolicyService — the compliance / decision layer.

Fun AI (the model) is NEVER the final authority on what radio actions are
permitted. Every radio request that comes out of a conversation is validated
here against configurable, jurisdiction-aware programming rules.

Guardrails that preserve FUUSIC's noninteractive radio model:
  • Exact on-demand song/artist selection is DENIED by default.
  • Third-party live stations: their song sequence is locked — Fun AI may only
    switch stations, never re-order their stream.
  • FUUSIC-managed stations: format / genre / mood / energy / language changes
    and station switches are permitted; skips are rate-limited.

The policy doc lives in ``app_settings`` (``fun_ai_radio_policy``) so admins can
tune it without code changes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_POLICY_ID = "fun_ai_radio_policy"

DEFAULT_POLICY = {
    "on_demand_allowed": False,
    "managed_allowed_actions": ["format_change", "mood_change", "energy_change",
                                "language_change", "station_preference",
                                "change_station", "skip", "record_feedback"],
    "third_party_allowed_actions": ["change_station", "record_feedback"],
    "skip_per_hour": 6,
    "jurisdiction": "US-noninteractive",
}

# Eligible FUUSIC-managed programming options Fun AI may steer toward.
FORMATS = {
    "energy": ["chill", "easy", "upbeat", "high_energy"],
    "mood": ["relaxed", "feelgood", "romantic", "focus", "party"],
    "genre": ["pop", "retro", "hindi_retro", "bollywood", "rock", "electronic",
              "arabic", "classical"],
    "language": ["english", "hindi", "hinglish", "punjabi", "arabic"],
}

ON_DEMAND_ACTIONS = {"play_exact_song", "play_song", "on_demand", "queue_song",
                     "play_artist_sequence"}
SEQUENCE_ACTIONS = {"format_change", "mood_change", "energy_change",
                    "language_change", "station_preference", "skip"}
_FIELD = {"format_change": "genre", "mood_change": "mood", "energy_change": "energy",
          "language_change": "language", "station_preference": "station"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_policy(db) -> dict:
    doc = await db.app_settings.find_one({"_id": _POLICY_ID}) or {}
    return {**DEFAULT_POLICY, **(doc.get("policy") or {})}


async def set_policy(db, policy: dict) -> dict:
    clean = {k: policy[k] for k in (policy or {}) if k in DEFAULT_POLICY}
    merged = {**DEFAULT_POLICY, **clean}
    await db.app_settings.update_one(
        {"_id": _POLICY_ID},
        {"$set": {"policy": merged, "updated_at": _now().isoformat()}}, upsert=True)
    return merged


async def resolve_station_type(db, station: dict) -> str:
    """Managed (FUUSIC channel) vs third_party (imported global station)."""
    if (station or {}).get("type"):
        return station["type"].lower()
    slug = (station or {}).get("slug") or (station or {}).get("id")
    if not slug:
        return "managed"
    if await db.channels.find_one({"slug": slug}):
        return "managed"
    imp = await db.imported_radio_stations.find_one({"slug": slug})
    if imp:
        return "managed" if imp.get("flagship_slug") else "third_party"
    return "managed"


async def _skips_last_hour(db, user_id: str) -> int:
    since = (_now() - timedelta(hours=1)).isoformat()
    return await db.fun_ai_radio_actions.count_documents(
        {"user_id": user_id, "action": "skip", "allowed": True, "at": {"$gte": since}})


async def evaluate(db, *, user_id: str, action: str, params: dict,
                   station: dict) -> dict:
    """Return a structured, deterministic decision. Never raises on a denial."""
    policy = await get_policy(db)
    action = (action or "").strip().lower()
    params = params or {}
    station = station or {}
    station_type = await resolve_station_type(db, station)
    name = station.get("name") or "this station"

    def deny(code, reason, alternative=None, alt_action=None):
        return {"allowed": False, "code": code, "reason": reason,
                "alternative": alternative, "alternative_action": alt_action,
                "action": action, "station_type": station_type}

    def allow(code, applied=None, permitted_next=None, target=None):
        return {"allowed": True, "code": code, "applied": applied or {},
                "permitted_next": permitted_next, "target": target,
                "reason": None, "action": action, "station_type": station_type}

    # 1) Exact on-demand song — never permitted under noninteractive radio.
    if action in ON_DEMAND_ACTIONS and not policy["on_demand_allowed"]:
        want = (params.get("song") or params.get("artist")
                or params.get("value") or "that exact track")
        return deny(
            "ON_DEMAND_NOT_PERMITTED",
            f"FUUSIC is interactive radio, not on-demand streaming, so I can't play "
            f"'{want}' on demand — but I can find you an eligible station or format.",
            alternative="Offer a matching radio format or station instead.",
            alt_action="suggest_format_or_station")

    allowed_actions = (policy["managed_allowed_actions"] if station_type == "managed"
                       else policy["third_party_allowed_actions"])

    # 2) Third-party live stations — their song sequence is locked.
    if station_type == "third_party" and action in SEQUENCE_ACTIONS:
        return deny(
            "THIRD_PARTY_SEQUENCE_LOCKED",
            f"{name} is a live third-party broadcast, so I can't change its song "
            "sequence. I can switch you to another station, though.",
            alternative="Switch to a different station.",
            alt_action="change_station")

    if action not in allowed_actions:
        return deny("ACTION_NOT_ALLOWED",
                    "That change isn't available for this station right now.")

    # 3) Skip — policy-limited per hour.
    if action == "skip":
        recent = await _skips_last_hour(db, user_id)
        if recent >= int(policy["skip_per_hour"]):
            return deny(
                "SKIP_LIMIT_REACHED",
                "You've reached the skip limit for now — that keeps us within radio "
                "rules. I can keep the music going or switch stations.",
                alternative="Keep listening or change station.",
                alt_action="change_station")
        return allow("SKIP_OK", permitted_next="advance_programming")

    # 4) Format / mood / energy / language / station preference (managed).
    if action in _FIELD:
        field = _FIELD[action]
        value = (params.get("value") or params.get(field) or "").strip().lower()
        return allow("CHANGE_OK", applied=({field: value} if value else {}),
                     permitted_next="apply_programming_directive")

    if action == "change_station":
        return allow("STATION_SWITCH_OK",
                     target=(params.get("target") or params.get("station")
                             or params.get("value")))

    if action == "record_feedback":
        return allow("FEEDBACK_OK", applied={"feedback": params.get("value")})

    return deny("UNKNOWN_ACTION", "I'm not sure how to do that on the radio.")
