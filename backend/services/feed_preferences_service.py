"""FUUSIC — My Feed Preferences.

Per-followed-entity frequency control, applied server-side in
`social_feed.build_feed` BEFORE ranking (user preferences always win over AI).

Modes:
  all_updates      — show every eligible post (still ranked/safety-filtered)
  daily_highlights — collapse the entity's posts into a grouped daily digest
  live_only        — only live / upcoming-live activity from the entity
  mute             — remove ordinary updates from the feed (stays followed)

Preferences are keyed by (user_id, actor_type, actor_id). When a user has not
explicitly set a mode, a per-category default applies.
"""
from __future__ import annotations

from datetime import datetime, timezone

VALID_MODES = {"all_updates", "daily_highlights", "live_only", "mute"}
VALID_ACTOR_TYPES = {"person", "friend", "station", "business",
                     "creator", "advisor", "club"}

# Admin-configurable defaults per actor category (users' explicit choices win).
CATEGORY_DEFAULTS = {
    "friend": "all_updates",
    "person": "all_updates",
    "station": "daily_highlights",
    "business": "daily_highlights",
    "creator": "daily_highlights",
    "advisor": "daily_highlights",
    "club": "all_updates",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes(db) -> None:
    try:
        await db.feed_preferences.create_index(
            [("user_id", 1), ("actor_type", 1), ("actor_id", 1)], unique=True)
    except Exception:
        pass


async def get_pref_map(db, uid: str) -> dict:
    """(actor_type, actor_id) -> explicitly-set frequency_mode."""
    out: dict = {}
    async for p in db.feed_preferences.find({"user_id": uid}):
        m = p.get("frequency_mode")
        if m in VALID_MODES:
            out[(p.get("actor_type"), p.get("actor_id"))] = m
    return out


def effective_mode(pref_map: dict, actor_type: str, actor_id: str) -> str:
    m = pref_map.get((actor_type, actor_id))
    if m in VALID_MODES:
        return m
    return CATEGORY_DEFAULTS.get(actor_type, "all_updates")


async def set_pref(db, uid: str, actor_type: str, actor_id: str,
                   frequency_mode: str) -> dict:
    await db.feed_preferences.update_one(
        {"user_id": uid, "actor_type": actor_type, "actor_id": actor_id},
        {"$set": {"frequency_mode": frequency_mode, "explicitly_set": True,
                  "updated_at": _now()},
         "$setOnInsert": {"user_id": uid, "actor_type": actor_type,
                          "actor_id": actor_id, "notification_mode": None}},
        upsert=True)
    return {"actor_type": actor_type, "actor_id": actor_id,
            "frequency_mode": frequency_mode, "explicitly_set": True}


async def list_following_entities(db, uid: str) -> dict:
    """Followed people / stations / businesses with display info, grouped by
    category, each annotated with its current effective frequency mode."""
    pref_map = await get_pref_map(db, uid)

    friends: set = set()
    async for fr in db.social_friendships.find(
            {"status": "accepted", "$or": [{"user_a": uid}, {"user_b": uid}]}):
        friends.add(fr["user_b"] if fr["user_a"] == uid else fr["user_a"])

    def _enrich(actor_type, actor_id, name, avatar):
        return {
            "actor_type": actor_type, "actor_id": actor_id,
            "name": name or "Unknown", "avatar_url": avatar,
            "frequency_mode": effective_mode(pref_map, actor_type, actor_id),
            "explicitly_set": (actor_type, actor_id) in pref_map,
        }

    people: list = []
    foll: list = []
    async for f in db.social_follows.find({"follower": uid}, {"target": 1}):
        if f.get("target"):
            foll.append(f["target"])
    if foll:
        async for u in db.users.find({"user_id": {"$in": foll}}):
            nm = u.get("name") or (u.get("email") or "").split("@")[0] or "Listener"
            people.append(_enrich("person", u["user_id"], nm,
                                  u.get("picture") or u.get("avatar_url")))

    stations: list = []
    st_ids: list = []
    async for sf in db.station_followers.find({"user_id": uid}, {"station_id": 1}):
        if sf.get("station_id"):
            st_ids.append(sf["station_id"])
    if st_ids:
        async for s in db.community_radio_stations.find(
                {"station_id": {"$in": st_ids}}):
            stations.append(_enrich("station", s["station_id"],
                                    s.get("name") or s.get("slug"),
                                    s.get("cover_image_url")))

    businesses: list = []
    bids: list = []
    async for r in db.user_business_relations.find(
            {"user_id": uid, "kind": "follow", "active": {"$ne": False}},
            {"merchant_id": 1}):
        if r.get("merchant_id"):
            bids.append(r["merchant_id"])
    if bids:
        async for b in db.businesses.find({"business_id": {"$in": bids}}):
            businesses.append(_enrich("business", b["business_id"], b.get("name"),
                                      b.get("logo_url") or b.get("cover_image_url")))

    return {"people": people, "stations": stations, "businesses": businesses,
            "defaults": CATEGORY_DEFAULTS, "modes": sorted(VALID_MODES)}


__all__ = ["VALID_MODES", "VALID_ACTOR_TYPES", "CATEGORY_DEFAULTS",
           "ensure_indexes", "get_pref_map", "effective_mode", "set_pref",
           "list_following_entities"]
