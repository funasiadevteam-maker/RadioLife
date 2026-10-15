"""FUUSIC Social V2 — Unified Following Resolver.

Aggregates every "who/what does this user follow" relationship that already
lives in the DB into ONE grouped view. It does NOT create a new follow table
— it reads the existing sources of truth:

  • people / creators / advisors → `social_follows` (one-way user follows),
                                    classified via advisor_profiles / owned
                                    stations / podcast_creators
  • businesses                   → `user_business_relations` (kind=follow)
  • stations / hosts             → `station_followers`
  • clubs                        → `dream_club_members`

Blocked users are always excluded.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _person_public(u: dict) -> dict:
    return {
        "user_id": u.get("user_id"),
        "name": u.get("name") or (u.get("email") or "").split("@")[0] or "Listener",
        "avatar_url": u.get("picture") or u.get("avatar_url"),
        "city": u.get("city") or u.get("market"),
    }


async def _blocked_ids(db, uid: str) -> set[str]:
    out: set[str] = set()
    async for b in db.social_blocks.find(
            {"$or": [{"blocker": uid}, {"blocked": uid}]}):
        out.add(b["blocked"] if b["blocker"] == uid else b["blocker"])
    return out


async def _following_user_ids(db, uid: str) -> list[dict]:
    """Raw one-way user follows (people/creators/advisors), newest first."""
    rows: list[dict] = []
    async for f in db.social_follows.find({"follower": uid}).sort("created_at", -1):
        rows.append(f)
    return rows


async def resolve_following(db, uid: str) -> dict:
    """Return the grouped following graph + a total count."""
    blocked = await _blocked_ids(db, uid)

    # ── People / creators / advisors (one-way user follows) ──────────
    follows = await _following_user_ids(db, uid)
    target_ids = [f["target"] for f in follows
                  if f.get("target") and f["target"] not in blocked]
    since_map = {f["target"]: _iso(f.get("created_at")) for f in follows}

    users: dict[str, dict] = {}
    async for u in db.users.find({"user_id": {"$in": target_ids}}):
        users[u["user_id"]] = u

    # Classify each followed user.
    advisor_ids: set[str] = set()
    async for a in db.advisor_profiles.find(
            {"user_id": {"$in": target_ids}}, {"user_id": 1, "status": 1}):
        if a.get("status") in (None, "approved", "active"):
            advisor_ids.add(a["user_id"])
    creator_ids: set[str] = set()
    async for st in db.community_radio_stations.find(
            {"owner_user_id": {"$in": target_ids}}, {"owner_user_id": 1}):
        creator_ids.add(st["owner_user_id"])
    async for pc in db.podcast_creators.find(
            {"user_id": {"$in": target_ids}}, {"user_id": 1}):
        creator_ids.add(pc["user_id"])

    people, creators, advisors = [], [], []
    for tid in target_ids:
        u = users.get(tid)
        if not u:
            continue
        item = {**_person_public(u), "following_since": since_map.get(tid)}
        if tid in advisor_ids:
            item["type"] = "advisor"
            advisors.append(item)
        elif tid in creator_ids:
            item["type"] = "creator"
            creators.append(item)
        else:
            item["type"] = "person"
            people.append(item)

    # ── Businesses (user_business_relations kind=follow) ─────────────
    businesses: list[dict] = []
    try:
        from services.business_profile_service import list_relations
        rel = await list_relations(db, user={"user_id": uid}, kind="follow",
                                   limit=200, offset=0)
        for b in (rel.get("items") or []):
            businesses.append({
                "business_id": b.get("business_id") or b.get("merchant_id") or b.get("id"),
                "name": b.get("name") or b.get("public_name") or "Business",
                "avatar_url": b.get("logo_url") or b.get("cover_url") or b.get("image"),
                "category": b.get("category") or b.get("business_type"),
                "type": "business",
                "following_since": _iso(b.get("followed_at")),
            })
    except Exception:
        pass

    # ── Stations / hosts (station_followers → community OR 50k+ catalog) ──
    stations: list[dict] = []
    st_rows = []
    async for sf in db.station_followers.find({"user_id": uid}):
        st_rows.append(sf)
    st_ids = [r["station_id"] for r in st_rows if r.get("station_id")]
    st_since = {r["station_id"]: _iso(r.get("followed_at")) for r in st_rows}
    comm: dict[str, dict] = {}
    if st_ids:
        async for s in db.community_radio_stations.find(
                {"station_id": {"$in": st_ids}}):
            comm[s.get("station_id")] = s
    # Imported-catalog fallback for any followed station without a community page
    # and without a stored snapshot (legacy rows).
    missing = [r["station_id"] for r in st_rows
               if r.get("station_id") and r["station_id"] not in comm
               and not r.get("station_snapshot")]
    imp_map: dict[str, dict] = {}
    if missing:
        async for im in db.imported_radio_stations.find({"id": {"$in": missing}}):
            imp_map[im.get("id")] = im
    for r in st_rows:
        sid = r.get("station_id")
        if not sid:
            continue
        s = comm.get(sid)
        if s:
            stations.append({
                "station_id": sid, "slug": s.get("slug"),
                "name": s.get("name") or s.get("slug"),
                "avatar_url": s.get("cover_image_url"),
                "category": s.get("page_type") or "station", "type": "station",
                "station_kind": "community", "following_since": st_since.get(sid),
            })
            continue
        snap = r.get("station_snapshot") or {}
        im = imp_map.get(sid)
        if not snap and im:
            snap = {"name": im.get("name"), "logo": im.get("favicon"),
                    "slug": im.get("flagship_slug"), "country": im.get("country"),
                    "kind": "imported", "category": im.get("country") or "station"}
        if snap:
            stations.append({
                "station_id": sid, "slug": snap.get("slug"),
                "name": snap.get("name") or sid,
                "avatar_url": snap.get("logo"),
                "category": snap.get("category") or snap.get("country") or "station",
                "type": "station", "station_kind": snap.get("kind") or "imported",
                "following_since": st_since.get(sid),
            })

    # ── Clubs (dream_club_members → dream_clubs) ─────────────────────
    clubs: list[dict] = []
    club_rows = []
    async for m in db.dream_club_members.find({"user_id": uid}):
        club_rows.append(m)
    slugs = [m["slug"] for m in club_rows if m.get("slug")]
    club_since = {m["slug"]: _iso(m.get("joined_at") or m.get("created_at"))
                  for m in club_rows}
    if slugs:
        async for c in db.dream_clubs.find({"_id": {"$in": slugs}}):
            clubs.append({
                "club_slug": c["_id"], "name": c.get("name") or c["_id"],
                "avatar_url": c.get("cover_url") or c.get("image_url"),
                "category": "club", "type": "club",
                "following_since": club_since.get(c["_id"]),
            })

    total = (len(people) + len(creators) + len(advisors)
             + len(businesses) + len(stations) + len(clubs))
    return {
        "count": total,
        "people": people,
        "creators": creators,
        "advisors": advisors,
        "businesses": businesses,
        "stations": stations,
        "clubs": clubs,
    }


async def following_summary(db, uid: str) -> dict:
    """Lightweight counts for the header stat (no full serialization)."""
    blocked = await _blocked_ids(db, uid)
    users = 0
    async for f in db.social_follows.find({"follower": uid}, {"target": 1}):
        if f.get("target") and f["target"] not in blocked:
            users += 1
    biz = await db.user_business_relations.count_documents(
        {"user_id": uid, "kind": "follow"})
    st = await db.station_followers.count_documents({"user_id": uid})
    clubs = await db.dream_club_members.count_documents({"user_id": uid})
    return {"count": users + biz + st + clubs, "people": users,
            "businesses": biz, "stations": st, "clubs": clubs}


__all__ = ["resolve_following", "following_summary"]
