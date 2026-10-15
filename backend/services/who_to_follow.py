"""FUUSIC Social — interest-based "Who to Follow" suggestions.

Recommends People, Creators, Radio Stations, Businesses, Clubs and Advisors
using the user's interests, location and social graph. Every suggestion carries
a plain-language `reason` ("3 mutual connections", "Popular in Dubai",
"Because you're into Tarot") so we never imply a relationship that doesn't
exist. Excludes already-followed / blocked / dismissed / self entities.

Reads existing follow sources — it does NOT create a new follow table.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _avatar(name: str) -> str:
    n = re.sub(r"\s+", "%20", (name or "FUUSIC").strip()[:24])
    return (f"https://ui-avatars.com/api/?name={n}&size=256"
            "&background=8b5cf6&color=fff&bold=true&font-size=0.4")


async def _exclusions(db, uid: str) -> dict:
    """Everything that must NOT be suggested, by category."""
    blocked: set[str] = set()
    async for b in db.social_blocks.find({"$or": [{"blocker": uid}, {"blocked": uid}]}):
        blocked.add(b["blocked"] if b["blocker"] == uid else b["blocker"])

    following: set[str] = set()
    async for f in db.social_follows.find({"follower": uid}, {"target": 1}):
        following.add(f["target"])
    async for fr in db.social_friendships.find(
            {"$or": [{"user_a": uid}, {"user_b": uid}]}):
        following.add(fr["user_b"] if fr["user_a"] == uid else fr["user_a"])

    stations: set[str] = set()
    async for sf in db.station_followers.find({"user_id": uid}, {"station_id": 1}):
        stations.add(sf["station_id"])

    businesses: set[str] = set()
    async for r in db.user_business_relations.find(
            {"user_id": uid, "kind": "follow"}, {"business_id": 1}):
        if r.get("business_id"):
            businesses.add(r["business_id"])

    clubs: set[str] = set()
    async for m in db.dream_club_members.find({"user_id": uid}, {"slug": 1}):
        if m.get("slug"):
            clubs.add(m["slug"])

    dismissed: set[str] = set()
    async for d in db.social_suggestion_dismissals.find(
            {"user_id": uid}, {"actor_type": 1, "actor_id": 1}):
        dismissed.add(f"{d.get('actor_type')}:{d.get('actor_id')}")

    return {"blocked": blocked, "following": following, "stations": stations,
            "businesses": businesses, "clubs": clubs, "dismissed": dismissed,
            "net": (following - blocked) | {uid}}


async def _people_mutuals(db, uid: str, exc: dict, cap: int) -> list[dict]:
    """People followed by the people you follow — ranked by mutual count."""
    net = list((exc["following"] - exc["blocked"]))[:60]
    if not net:
        return []
    tally: dict[str, int] = {}
    async for f in db.social_follows.find(
            {"follower": {"$in": net}}, {"target": 1}).limit(600):
        t = f.get("target")
        if not t or t == uid or t in exc["following"] or t in exc["blocked"]:
            continue
        if f"person:{t}" in exc["dismissed"]:
            continue
        tally[t] = tally.get(t, 0) + 1
    top = sorted(tally.items(), key=lambda kv: kv[1], reverse=True)[:cap * 2]
    ids = [t for t, _ in top]
    if not ids:
        return []
    umap = {}
    async for u in db.users.find({"user_id": {"$in": ids}}):
        umap[u["user_id"]] = u
    out = []
    for tid, n in top:
        u = umap.get(tid)
        if not u:
            continue
        out.append({
            "actor_type": "person", "actor_id": tid,
            "name": u.get("name") or (u.get("email") or "").split("@")[0] or "Listener",
            "avatar_url": u.get("picture") or u.get("avatar_url") or _avatar(u.get("name")),
            "category": "Person",
            "reason": f"{n} mutual connection" + ("s" if n != 1 else ""),
            "reason_kind": "mutual", "mutuals": n,
        })
        if len(out) >= cap:
            break
    return out


async def _stations(db, uid: str, exc: dict, interests: list[str],
                    city: Optional[str], country: Optional[str], cap: int) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def _push(sid, name, logo, cat, reason, kind):
        if not sid or sid in exc["stations"] or sid in seen:
            return
        if f"station:{sid}" in exc["dismissed"]:
            return
        seen.add(sid)
        out.append({"actor_type": "station", "actor_id": sid, "name": name,
                    "avatar_url": logo or _avatar(name), "category": cat or "Radio Station",
                    "reason": reason, "reason_kind": kind})

    # 1) Stations in the user's city / country (from the 50k+ catalog).
    loc_q: dict = {"active": {"$ne": False}}
    ors = []
    if city:
        ors.append({"city": re.compile(f"^{re.escape(city)}$", re.I)})
    if country:
        ors.append({"country": re.compile(re.escape(country), re.I)})
    if ors:
        loc_q["$or"] = ors
        async for s in db.imported_radio_stations.find(loc_q).sort(
                "click_count", -1).limit(cap * 3):
            where = s.get("city") or s.get("country")
            _push(s.get("id"), s.get("name"), s.get("favicon"),
                  s.get("country"), f"Popular in {where}", "local")
            if len(out) >= cap:
                return out

    # 2) Interest / language / genre match against the catalog.
    terms = [t for t in interests if t]
    if terms and len(out) < cap:
        rx = re.compile("|".join(re.escape(t.replace("_", " ")) for t in terms), re.I)
        async for s in db.imported_radio_stations.find(
                {"active": {"$ne": False},
                 "$or": [{"tags": rx}, {"name": rx}, {"language": rx},
                         {"flagship_categories": rx}]}).limit(cap * 3):
            label = (terms[0] or "your").replace("_", " ").title()
            _push(s.get("id"), s.get("name"), s.get("favicon"), s.get("country"),
                  f"Matches your {label} interest", "interest")
            if len(out) >= cap:
                return out

    # 3) Community stations (FUUSIC-managed) by follower count.
    if len(out) < cap:
        async for s in db.community_radio_stations.find(
                {"status": {"$ne": "disabled"}}).sort("follower_count", -1).limit(cap * 2):
            if s.get("owner_user_id") == uid:
                continue
            _push(s.get("station_id"), s.get("name") or s.get("slug"),
                  s.get("cover_image_url"), "Community Station",
                  "Trending on FUUSIC", "popular")
            if len(out) >= cap:
                break
    return out


_INTEREST_TO_ADVISOR = {
    "TAROT": "tarot", "ASTROLOGY": "astrology", "DREAMS": "dream",
    "NUMEROLOGY": "numerology",
}


async def _advisors(db, uid: str, exc: dict, interests: list[str], cap: int) -> list[dict]:
    want = [v for k, v in _INTEREST_TO_ADVISOR.items() if k in set(interests)]
    out: list[dict] = []
    async for a in db.advisor_profiles.find(
            {"status": {"$in": [None, "approved", "active"]}}).limit(40):
        aid = a.get("user_id")
        if not aid or aid == uid or aid in exc["following"] or aid in exc["blocked"]:
            continue
        if f"advisor:{aid}" in exc["dismissed"]:
            continue
        cat = (a.get("category") or "").lower()
        matched = next((w for w in want if w in cat), None)
        reason = (f"Because you're into {matched.title()}" if matched
                  else "Recommended advisor")
        out.append({"actor_type": "advisor", "actor_id": aid,
                    "name": a.get("display_name") or "Advisor",
                    "avatar_url": a.get("photo_url") or _avatar(a.get("display_name")),
                    "category": (a.get("category") or "Advisor").title(),
                    "reason": reason,
                    "reason_kind": "interest" if matched else "popular",
                    "_matched": bool(matched)})
    out.sort(key=lambda x: x.get("_matched", False), reverse=True)
    for o in out:
        o.pop("_matched", None)
    return out[:cap]


async def _businesses(db, uid: str, exc: dict, city: Optional[str], cap: int) -> list[dict]:
    q: dict = {"active": {"$ne": False}}
    if city:
        q["city"] = re.compile(f"^{re.escape(city)}$", re.I)
    out: list[dict] = []
    async for b in db.businesses.find(q).limit(cap * 3):
        bid = b.get("business_id")
        if not bid or bid in exc["businesses"] or b.get("owner_user_id") == uid:
            continue
        if f"business:{bid}" in exc["dismissed"]:
            continue
        where = b.get("city") or b.get("market")
        out.append({"actor_type": "business", "actor_id": bid,
                    "name": b.get("name") or "Business",
                    "avatar_url": b.get("logo_url") or _avatar(b.get("name")),
                    "category": (b.get("category") or "Business"),
                    "reason": f"Popular in {where}" if where else "A place you may like",
                    "reason_kind": "local"})
        if len(out) >= cap:
            break
    return out


async def _clubs(db, uid: str, exc: dict, cap: int) -> list[dict]:
    out: list[dict] = []
    async for c in db.dream_clubs.find({}).limit(cap * 3):
        slug = c.get("slug") or c.get("_id")
        if not slug or slug in exc["clubs"] or f"club:{slug}" in exc["dismissed"]:
            continue
        out.append({"actor_type": "club", "actor_id": slug,
                    "name": c.get("name") or slug,
                    "avatar_url": c.get("cover_url") or c.get("image_url") or _avatar(c.get("name")),
                    "category": "Club",
                    "reason": "Join the conversation", "reason_kind": "popular"})
        if len(out) >= cap:
            break
    return out


def _interleave(buckets: list[list[dict]], limit: int) -> list[dict]:
    out, i = [], 0
    while len(out) < limit and any(i < len(b) for b in buckets):
        for b in buckets:
            if i < len(b):
                out.append(b[i])
                if len(out) >= limit:
                    break
        i += 1
    return out


async def suggest(db, uid: str, *, limit: int = 12,
                  actor_type: Optional[str] = None) -> dict:
    exc = await _exclusions(db, uid)
    u = await db.users.find_one({"user_id": uid}) or {}
    interests = list(u.get("interests") or [])
    if isinstance(u.get("onboarded_interests"), list):
        interests += u["onboarded_interests"]
    city = u.get("city") or u.get("market")
    country = u.get("country")

    per = max(3, limit // 2)
    if actor_type and actor_type != "all":
        fn = {
            "person": lambda: _people_mutuals(db, uid, exc, limit),
            "station": lambda: _stations(db, uid, exc, interests, city, country, limit),
            "advisor": lambda: _advisors(db, uid, exc, interests, limit),
            "business": lambda: _businesses(db, uid, exc, city, limit),
            "club": lambda: _clubs(db, uid, exc, limit),
        }.get(actor_type)
        items = (await fn()) if fn else []
        return {"items": items[:limit], "count": len(items[:limit])}

    buckets = [
        await _people_mutuals(db, uid, exc, per),
        await _stations(db, uid, exc, interests, city, country, per),
        await _advisors(db, uid, exc, interests, per),
        await _businesses(db, uid, exc, city, per),
        await _clubs(db, uid, exc, max(2, per // 2)),
    ]
    items = _interleave(buckets, limit)
    return {"items": items, "count": len(items)}


async def dismiss_suggestion(db, uid: str, actor_type: str, actor_id: str,
                             action: str = "not_interested") -> None:
    await db.social_suggestion_dismissals.update_one(
        {"user_id": uid, "actor_type": actor_type, "actor_id": actor_id},
        {"$set": {"action": action, "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}}, upsert=True)


__all__ = ["suggest", "dismiss_suggestion"]
