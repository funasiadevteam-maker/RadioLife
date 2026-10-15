"""FUUSIC Social V2 — Combined Wall feed + layered ranking.

`build_feed()` returns a single, ranked, diversity-balanced wall assembled from
REAL DB records (never invented by an LLM):

  MOMENT · LIVE_VIDEO / BUSINESS_LIVE · EVENT · LISTEN_ROOM · DREAM ·
  TAROT_SHARE · CLUB_POST · STATION_ACTIVITY

Ranking is layered so a refresh is cheap:
  Stage 1  DB eligibility (respects follows / friends / blocks / visibility)
  Stage 2  fast deterministic scoring (relationship + recency + live boost)
  Stage 3  OPTIONAL cached AI rerank of the top slice — computed in the
           background and applied on later reads, so no request waits on an LLM.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

RANK_CACHE_TTL_SEC = 300           # AI rerank order freshness window
SOURCE_LIMIT = 40                  # per-source candidate cap
MAX_CANDIDATES = 200

WALL_TYPES = {"MOMENT", "LIVE_VIDEO", "BUSINESS_LIVE", "EVENT", "LISTEN_ROOM",
              "DREAM", "TAROT_SHARE", "CLUB_POST", "STATION_ACTIVITY",
              "RADIO_CLIP", "READING", "BUSINESS_POST", "SPONSORED_POST"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(v: Any) -> datetime:
    """Coerce str / naive / aware → aware UTC datetime (for scoring)."""
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return _now()
    if isinstance(v, datetime):
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
    return _now()


def _iso(v: Any) -> Optional[str]:
    """Always emit tz-aware UTC ISO so downstream string parsing is safe."""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v


def _actor_user(u: dict) -> dict:
    return {
        "kind": "user", "id": u.get("user_id"),
        "name": u.get("name") or (u.get("email") or "").split("@")[0] or "Listener",
        "avatar_url": u.get("picture") or u.get("avatar_url"),
    }


# ───────────────────────── eligibility sets ────────────────────────
async def _eligibility(db, uid: str) -> dict:
    following: set[str] = set()
    async for f in db.social_follows.find({"follower": uid}, {"target": 1}):
        if f.get("target"):
            following.add(f["target"])
    friends: set[str] = set()
    async for fr in db.social_friendships.find(
            {"status": "accepted", "$or": [{"user_a": uid}, {"user_b": uid}]}):
        friends.add(fr["user_b"] if fr["user_a"] == uid else fr["user_a"])
    blocked: set[str] = set()
    async for b in db.social_blocks.find(
            {"$or": [{"blocker": uid}, {"blocked": uid}]}):
        blocked.add(b["blocked"] if b["blocker"] == uid else b["blocker"])
    stations: set[str] = set()
    async for sf in db.station_followers.find({"user_id": uid}, {"station_id": 1}):
        if sf.get("station_id"):
            stations.add(sf["station_id"])
    clubs: set[str] = set()
    async for m in db.dream_club_members.find({"user_id": uid}, {"slug": 1}):
        if m.get("slug"):
            clubs.add(m["slug"])
    return {"following": following, "friends": friends, "blocked": blocked,
            "stations": stations, "clubs": clubs}


def _rel(actor_id: str, elig: dict) -> str:
    fr = actor_id in elig["friends"]
    fo = actor_id in elig["following"]
    if fr and fo:
        return "friend_following"
    if fr:
        return "friend"
    if fo:
        return "following"
    return "discovery"


# ───────────────────────── candidate builders ──────────────────────
async def _moments(db, uid: str, elig: dict, mode: str) -> list[dict]:
    cutoff = _now() - timedelta(days=7)
    if mode == "following":
        # INVARIANT: the owner ALWAYS sees their own posts on their wall —
        # a user never has to follow themselves. Plus followed people + friends.
        actors = list(((elig["following"] | elig["friends"]) - elig["blocked"]) | {uid})
        q = {"created_at": {"$gte": cutoff}, "user_id": {"$in": actors}}
    else:
        # For You: public posts (INCLUDING the owner's own public posts, which
        # become eligible for discovery), minus blocked authors.
        q = {"created_at": {"$gte": cutoff}, "visibility": "public",
             "user_id": {"$nin": list(elig["blocked"])}}
    rows, ids = [], set()
    async for m in db.social_moments.find(q).sort("created_at", -1).limit(SOURCE_LIMIT):
        rows.append(m)
        ids.add(m["user_id"])
    umap = {}
    async for u in db.users.find({"user_id": {"$in": list(ids)}}):
        umap[u["user_id"]] = u
    # Viewer engagement state so a refresh keeps like / save reflected.
    mom_ids = [m["_id"] for m in rows]
    liked: set = set()
    saved: set = set()
    if mom_ids:
        async for l in db.social_moment_likes.find(
                {"moment_id": {"$in": mom_ids}, "user_id": uid}, {"moment_id": 1}):
            liked.add(l["moment_id"])
        async for s in db.social_saves.find(
                {"item_id": {"$in": [f"MOMENT:{i}" for i in mom_ids]},
                 "user_id": uid}, {"item_id": 1}):
            saved.add(s["item_id"])
    out = []
    for m in rows:
        u = umap.get(m["user_id"])
        if not u:
            continue
        is_mine = m["user_id"] == uid
        actor = _actor_user(u)
        if is_mine:
            actor["kind"] = "self"
        rel = "self" if is_mine else _rel(m["user_id"], elig)
        cid = f"MOMENT:{m['_id']}"
        out.append({
            "id": cid, "type": "MOMENT",
            "created_at": _iso(m.get("created_at")), "_dt": _dt(m.get("created_at")),
            "actor": actor, "title": None, "is_mine": is_mine,
            "text": m.get("caption"), "media_url": m.get("media_url"),
            "media_type": m.get("media_type") or "photo",
            "approval_status": m.get("approval_status") or "approved",
            "cta": {"label": "Comment", "action": "open_moment", "target": m["_id"]},
            "meta": {"like_count": int(m.get("like_count") or 0),
                     "comment_count": int(m.get("comment_count") or 0),
                     "share_count": int(m.get("share_count") or 0),
                     "liked_by_me": m["_id"] in liked,
                     "saved_by_me": cid in saved,
                     "context": m.get("context")},
            "follow_relationship": rel, "candidate_source": "moments",
            "sponsored": False,
        })
    return out


async def _live_shows(db, uid: str, elig: dict, mode: str) -> list[dict]:
    out = []
    for status in ("live", "scheduled"):
        q = {"status": status}
        rows, hids = [], set()
        sort_field = "scheduled_at" if status == "scheduled" else "started_at"
        async for s in db.live_shows.find(q).sort(sort_field, -1).limit(SOURCE_LIMIT):
            rows.append(s)
            hids.add(s.get("host_id"))
        if mode == "following":
            rows = [s for s in rows
                    if _rel(s.get("host_id"), elig) != "discovery"]
        umap = {}
        async for u in db.users.find({"user_id": {"$in": list(hids)}}):
            umap[u["user_id"]] = u
        for s in rows:
            host = umap.get(s.get("host_id"))
            biz = s.get("business_name")
            actor = ({"kind": "business", "id": s.get("host_id"),
                      "name": biz, "avatar_url": s.get("cover_url")}
                     if biz else (_actor_user(host) if host else None))
            if not actor:
                continue
            is_live = status == "live"
            typ = "BUSINESS_LIVE" if (biz and is_live) else (
                "LIVE_VIDEO" if is_live else "EVENT")
            when = s.get("started_at") if is_live else s.get("scheduled_at")
            cta = ({"label": "Watch Live", "action": "open_live", "target": s["_id"]}
                   if is_live else
                   {"label": "I'm Going", "action": "open_live", "target": s["_id"]})
            out.append({
                "id": f"{typ}:{s['_id']}", "type": typ,
                "created_at": _iso(when or s.get("created_at")),
                "_dt": _dt(when or s.get("created_at")),
                "actor": actor, "title": s.get("title"),
                "text": s.get("description"), "media_url": s.get("cover_url"),
                "media_type": "video",
                "cta": cta,
                "meta": {"live": is_live, "scheduled_at": _iso(s.get("scheduled_at")),
                         "products": (s.get("pinned_products") or [])[:3]},
                "follow_relationship": _rel(s.get("host_id"), elig),
                "candidate_source": "live_shows", "sponsored": False,
            })
    return out


async def _rooms(db, uid: str, elig: dict, mode: str) -> list[dict]:
    cutoff = _now() - timedelta(minutes=10)
    rows = []
    async for r in db.listen_rooms.find(
            {"active": True, "last_active_at": {"$gte": cutoff}}
            ).sort("last_active_at", -1).limit(SOURCE_LIMIT):
        rows.append(r)
    out = []
    for r in rows:
        host_id = r.get("host_user_id")
        if host_id == uid or host_id in elig["blocked"]:
            continue
        rel = _rel(host_id, elig)
        if mode == "following" and rel == "discovery":
            continue
        out.append({
            "id": f"LISTEN_ROOM:{r['_id']}", "type": "LISTEN_ROOM",
            "created_at": _iso(r.get("last_active_at")),
            "_dt": _dt(r.get("last_active_at")),
            "actor": {"kind": "user", "id": host_id, "name": r.get("host_name"),
                      "avatar_url": (r.get("content") or {}).get("favicon")},
            "title": (r.get("content") or {}).get("name") or r.get("title"),
            "text": None,
            "media_url": (r.get("content") or {}).get("favicon"),
            "media_type": "audio",
            "cta": {"label": "Join", "action": "open_room", "target": r["_id"]},
            "meta": {"live": True,
                     "participant_count": int(r.get("participant_count") or 0)},
            "follow_relationship": rel, "candidate_source": "listen_rooms",
            "sponsored": False,
        })
    return out


async def _dreams(db, uid: str, elig: dict, mode: str) -> list[dict]:
    if mode == "following":
        actors = list((elig["following"] | elig["friends"]) - elig["blocked"])
        if not actors:
            return []
        q = {"status": "active", "user_id": {"$in": actors},
             "visibility": {"$in": ["friends", "public"]}}
    else:
        q = {"status": "active", "visibility": "public",
             "user_id": {"$nin": list(elig["blocked"] | {uid})}}
    rows, ids = [], set()
    async for d in db.dreams.find(q).sort("created_at", -1).limit(SOURCE_LIMIT):
        if d["user_id"] == uid:
            continue
        rows.append(d)
        if not d.get("anonymous"):
            ids.add(d["user_id"])
    umap = {}
    async for u in db.users.find({"user_id": {"$in": list(ids)}}):
        umap[u["user_id"]] = u
    out = []
    for d in rows:
        anon = bool(d.get("anonymous"))
        # Anonymous dreams never surface in FOLLOWING — a following-mode card
        # must be attributable to a followed/friend actor (privacy + invariant).
        if anon and mode == "following":
            continue
        actor = ({"kind": "user", "id": None, "name": "Anonymous Dreamer",
                  "avatar_url": None, "anonymous": True}
                 if anon else (_actor_user(umap[d["user_id"]])
                               if d["user_id"] in umap else None))
        if not actor:
            continue
        is_club = bool(d.get("club_slug"))
        if is_club and mode == "following" and d["club_slug"] not in elig["clubs"]:
            continue
        typ = "CLUB_POST" if is_club else "DREAM"
        out.append({
            "id": f"{typ}:{d['_id']}", "type": typ,
            "created_at": _iso(d.get("created_at")), "_dt": _dt(d.get("created_at")),
            "actor": actor, "title": d.get("title"),
            "text": (d.get("description") or "")[:240],
            "media_url": None, "media_type": None,
            "cta": {"label": "I had a similar dream", "action": "open_dream",
                    "target": d["_id"]},
            "meta": {"mood": d.get("mood"), "tags": (d.get("tags") or [])[:4],
                     "club_slug": d.get("club_slug"),
                     "similar_count": int(d.get("similar_count") or 0)},
            "follow_relationship": ("discovery" if anon
                                    else _rel(d["user_id"], elig)),
            "candidate_source": "dreams", "sponsored": False,
        })
    return out


async def _tarot(db, uid: str, elig: dict, mode: str) -> list[dict]:
    if mode == "following":
        actors = list((elig["following"] | elig["friends"]) - elig["blocked"])
        if not actors:
            return []
        q = {"type": "tarot", "public": True, "user_id": {"$in": actors}}
    else:
        q = {"type": "tarot", "public": True,
             "user_id": {"$nin": list(elig["blocked"] | {uid})}}
    rows, ids = [], set()
    async for r in db.ai_readings.find(q).sort("created_at", -1).limit(SOURCE_LIMIT):
        if r["user_id"] == uid:
            continue
        rows.append(r)
        ids.add(r["user_id"])
    umap = {}
    async for u in db.users.find({"user_id": {"$in": list(ids)}}):
        umap[u["user_id"]] = u
    out = []
    for r in rows:
        u = umap.get(r["user_id"])
        if not u:
            continue
        out.append({
            "id": f"TAROT_SHARE:{r['_id']}", "type": "TAROT_SHARE",
            "created_at": _iso(r.get("created_at")), "_dt": _dt(r.get("created_at")),
            "actor": _actor_user(u), "title": r.get("title") or "A Tarot reading",
            "text": (r.get("subject") or ""),
            "media_url": None, "media_type": None,
            "cta": {"label": "View Reading", "action": "open_tarot",
                    "target": r["_id"]},
            "meta": {"cards": (r.get("cards") or [])[:3]},
            "follow_relationship": _rel(r["user_id"], elig),
            "candidate_source": "ai_readings", "sponsored": False,
        })
    return out


async def _station_posts(db, uid: str, elig: dict, mode: str) -> list[dict]:
    if mode != "following" or not elig["stations"]:
        return []
    rows = []
    async for p in db.social_posts.find(
            {"page_id": {"$in": list(elig["stations"])},
             "approval_status": "approved",
             "deleted_at": {"$exists": False}}
            ).sort("created_at", -1).limit(SOURCE_LIMIT):
        rows.append(p)
    st_ids = list({p["page_id"] for p in rows})
    smap = {}
    async for s in db.community_radio_stations.find({"station_id": {"$in": st_ids}}):
        smap[s["station_id"]] = s
    out = []
    for p in rows:
        s = smap.get(p["page_id"])
        if not s:
            continue
        media = (p.get("media_urls") or [None])[0]
        out.append({
            "id": f"STATION_ACTIVITY:{p['_id']}", "type": "STATION_ACTIVITY",
            "created_at": _iso(p.get("created_at")), "_dt": _dt(p.get("created_at")),
            "actor": {"kind": "station", "id": s.get("station_id"),
                      "name": s.get("name") or s.get("slug"),
                      "avatar_url": s.get("cover_image_url")},
            "title": None, "text": p.get("text"),
            "media_url": media, "media_type": "photo" if media else None,
            "cta": {"label": "Listen", "action": "open_station",
                    "target": s.get("slug") or s.get("station_id")},
            "meta": {"slug": s.get("slug")},
            "follow_relationship": "following", "candidate_source": "station_posts",
            "sponsored": False,
        })
    return out


async def _radio_clips(db, uid: str, elig: dict, mode: str) -> list[dict]:
    """Radio clips in the wall — station daily HIGHLIGHTS from followed stations
    plus listener 30s CLIP & SHARE posts (own + followed/friends, or public)."""
    cutoff = _now() - timedelta(days=7)
    if mode == "following":
        actors = list(((elig["following"] | elig["friends"]) - elig["blocked"]) | {uid})
        q = {"status": "published", "broadcast_at": {"$gte": cutoff}, "$or": [
            {"kind": "station_highlight", "station_id": {"$in": list(elig["stations"])}},
            {"kind": "user_clip", "created_by": {"$in": actors}},
        ]}
    else:
        q = {"status": "published", "broadcast_at": {"$gte": cutoff}, "$or": [
            {"kind": "station_highlight"},
            {"kind": "user_clip", "visibility": "public"},
        ]}
    rows, uids = [], set()
    async for c in db.radio_clips.find(q).sort("broadcast_at", -1).limit(SOURCE_LIMIT):
        rows.append(c)
        if c.get("kind") == "user_clip" and c.get("created_by"):
            uids.add(c["created_by"])
    umap = {}
    if uids:
        async for u in db.users.find({"user_id": {"$in": list(uids)}}):
            umap[u["user_id"]] = u
    comp_ids = [f"RADIO_CLIP:{c['_id']}" for c in rows]
    liked, saved, likecounts = set(), set(), {}
    if comp_ids:
        async for l in db.social_feed_likes.find(
                {"item_id": {"$in": comp_ids}, "user_id": uid}, {"item_id": 1}):
            liked.add(l["item_id"])
        async for s in db.social_saves.find(
                {"item_id": {"$in": comp_ids}, "user_id": uid}, {"item_id": 1}):
            saved.add(s["item_id"])
        async for row in db.social_feed_likes.aggregate([
                {"$match": {"item_id": {"$in": comp_ids}}},
                {"$group": {"_id": "$item_id", "n": {"$sum": 1}}}]):
            likecounts[row["_id"]] = row["n"]
    out = []
    for c in rows:
        cid = f"RADIO_CLIP:{c['_id']}"
        if c.get("kind") == "station_highlight":
            actor = {"kind": "station", "id": c.get("station_id"),
                     "name": c.get("station_name"), "avatar_url": c.get("station_logo")}
            rel = "following" if c.get("station_id") in elig["stations"] else "discovery"
            is_mine = False
        else:
            is_mine = c.get("created_by") == uid
            u = umap.get(c.get("created_by"))
            if not u and not is_mine:
                continue
            actor = _actor_user(u) if u else {"kind": "self", "id": uid, "name": "You"}
            if is_mine:
                actor = {"kind": "self", "id": uid,
                         "name": (actor.get("name") or "You"),
                         "avatar_url": actor.get("avatar_url")}
            rel = "self" if is_mine else _rel(c.get("created_by"), elig)
        out.append({
            "id": cid, "type": "RADIO_CLIP",
            "created_at": _iso(c.get("broadcast_at") or c.get("created_at")),
            "_dt": _dt(c.get("broadcast_at") or c.get("created_at")),
            "actor": actor, "title": c.get("title"), "is_mine": is_mine,
            "text": c.get("caption") or c.get("commentary"),
            "media_url": c.get("audio_url"), "media_type": "audio",
            "cta": {"label": "Listen Live", "action": "open_station",
                    "target": c.get("station_slug") or c.get("station_id")},
            "meta": {"clip_kind": c.get("kind"),
                     "duration_sec": int(c.get("duration_sec") or 30),
                     "show_name": c.get("show_name"), "host_name": c.get("host_name"),
                     "station_name": c.get("station_name"),
                     "station_logo": c.get("station_logo"),
                     "station_slug": c.get("station_slug"),
                     "station_id": c.get("station_id"),
                     "tags": c.get("tags") or [],
                     "like_count": int(likecounts.get(cid, 0)),
                     "comment_count": int(c.get("comment_count") or 0),
                     "share_count": int(c.get("share_count") or 0),
                     "liked_by_me": cid in liked, "saved_by_me": cid in saved},
            "follow_relationship": rel, "candidate_source": "radio_clips",
            "sponsored": False,
        })
    return out


async def _readings(db, uid: str, elig: dict, mode: str) -> list[dict]:
    """PRIVATE daily readings — only ever on the owner's own (following) wall."""
    if mode != "following":
        return []
    today = _now().date().isoformat()
    out = []
    async for r in db.daily_readings.find({"user_id": uid, "date": today}).limit(6):
        rt = r.get("reading_type")
        out.append({
            "id": f"READING:{r['_id']}", "type": "READING",
            "created_at": _iso(r.get("created_at")), "_dt": _dt(r.get("created_at")),
            "actor": {"kind": "self", "id": uid, "name": "Your Daily Reading",
                      "avatar_url": None},
            "title": r.get("title"), "text": r.get("body"), "is_mine": True,
            "media_url": None, "media_type": None, "private": True,
            "cta": {"label": "My Readings", "action": "open_readings", "target": rt},
            "meta": {"reading_type": rt, "headline": r.get("headline"),
                     "card": r.get("card"), "number": r.get("number"),
                     "sign": r.get("sign"), "ai_generated": True,
                     "disclaimer": r.get("disclaimer")},
            "follow_relationship": "self", "candidate_source": "readings",
            "sponsored": False,
        })
    return out


async def _business_posts(db, uid: str, elig: dict, mode: str) -> list[dict]:
    """Organic posts from businesses the user follows (no pay-to-reach-followers)."""
    biz_ids = set()
    async for r in db.user_business_relations.find(
            {"user_id": uid, "kind": "follow", "active": {"$ne": False}},
            {"merchant_id": 1}):
        if r.get("merchant_id"):
            biz_ids.add(r["merchant_id"])
    if mode == "following":
        if not biz_ids:
            return []
        q = {"business_id": {"$in": list(biz_ids)}, "approval_status": "approved",
             "deleted_at": {"$exists": False}}
    else:
        q = {"business_id": {"$exists": True, "$ne": None},
             "approval_status": "approved", "deleted_at": {"$exists": False},
             "visibility": {"$ne": "private"}}
    rows = []
    async for p in db.social_posts.find(q).sort("created_at", -1).limit(SOURCE_LIMIT):
        if p.get("business_id"):
            rows.append(p)
    bids = list({p["business_id"] for p in rows})
    bmap = {}
    async for b in db.businesses.find({"business_id": {"$in": bids}}):
        bmap[b["business_id"]] = b
    comp = [f"BUSINESS_POST:{p['_id']}" for p in rows]
    liked, saved, lc = set(), set(), {}
    if comp:
        async for l in db.social_feed_likes.find(
                {"item_id": {"$in": comp}, "user_id": uid}, {"item_id": 1}):
            liked.add(l["item_id"])
        async for sv in db.social_saves.find(
                {"item_id": {"$in": comp}, "user_id": uid}, {"item_id": 1}):
            saved.add(sv["item_id"])
        async for row in db.social_feed_likes.aggregate([
                {"$match": {"item_id": {"$in": comp}}},
                {"$group": {"_id": "$item_id", "n": {"$sum": 1}}}]):
            lc[row["_id"]] = row["n"]
    out = []
    for p in rows:
        b = bmap.get(p["business_id"])
        if not b:
            continue
        media = (p.get("media_urls") or [None])[0]
        cid = f"BUSINESS_POST:{p['_id']}"
        out.append({
            "id": cid, "type": "BUSINESS_POST",
            "created_at": _iso(p.get("created_at")), "_dt": _dt(p.get("created_at")),
            "actor": {"kind": "business", "id": b["business_id"],
                      "name": b.get("name"),
                      "avatar_url": b.get("logo_url") or b.get("cover_image_url")},
            "title": p.get("title"), "text": p.get("text"),
            "media_url": media, "media_type": "photo" if media else None,
            "cta": {"label": p.get("cta_label") or "View Business",
                    "action": "open_business",
                    "target": b.get("slug") or b["business_id"]},
            "meta": {"business_id": b["business_id"], "category": b.get("category"),
                     "like_count": int(lc.get(cid, 0)), "comment_count": 0,
                     "share_count": 0, "liked_by_me": cid in liked,
                     "saved_by_me": cid in saved,
                     "products": (p.get("products") or [])[:3]},
            "follow_relationship": "following" if p["business_id"] in biz_ids else "discovery",
            "candidate_source": "business_posts", "sponsored": False,
        })
    return out


async def _inject_sponsored(db, uid: str, cands: list[dict]) -> list[dict]:
    """Inject labelled Sponsored business posts (reusing boosted_posts) ~1 per
    ~7 organic items. Premium users are ad-free; Hide-Ad dismissals respected."""
    u = await db.users.find_one({"user_id": uid}, {"is_premium": 1})
    if (u or {}).get("is_premium"):
        return cands
    dismissed = set()
    async for d in db.social_suggestion_dismissals.find(
            {"user_id": uid, "actor_type": "sponsored_post"}, {"actor_id": 1}):
        dismissed.add(d["actor_id"])
    now = _now()
    boosts = []
    async for bp in db.boosted_posts.find({"status": "active"}).sort("created_at", -1).limit(12):
        if bp.get("end_at") and _dt(bp["end_at"]) < now:
            continue
        if bp["post_id"] in dismissed:
            continue
        boosts.append(bp)
    if not boosts:
        return cands
    pids = [b["post_id"] for b in boosts]
    pmap = {}
    async for p in db.social_posts.find({"_id": {"$in": pids}}):
        pmap[p["_id"]] = p
    bids = list({b.get("business_id") for b in boosts if b.get("business_id")})
    bmap = {}
    async for b in db.businesses.find({"business_id": {"$in": bids}}):
        bmap[b["business_id"]] = b
    cards = []
    for bp in boosts:
        p = pmap.get(bp["post_id"])
        if not p:
            continue
        b = bmap.get(bp.get("business_id")) or {}
        media = (p.get("media_urls") or [None])[0]
        cards.append({
            "id": f"SPONSORED_POST:{bp['post_id']}", "type": "SPONSORED_POST",
            "created_at": _iso(p.get("created_at")), "actor": {
                "kind": "business", "id": bp.get("business_id"),
                "name": b.get("name") or "Sponsored",
                "avatar_url": b.get("logo_url") or b.get("cover_image_url")},
            "title": p.get("title"), "text": p.get("text"),
            "media_url": media, "media_type": "photo" if media else None,
            "cta": {"label": bp.get("cta_label") or "Learn More",
                    "action": "open_business",
                    "target": bp.get("destination") or b.get("slug") or bp.get("business_id")},
            "meta": {"business_id": bp.get("business_id"), "sponsored_label": "Sponsored",
                     "goal": bp.get("goal"), "like_count": 0, "comment_count": 0},
            "follow_relationship": "discovery", "candidate_source": "boost",
            "sponsored": True,
        })
    if not cards:
        return cands
    out, bi, FREQ = [], 0, 7
    for i, c in enumerate(cands):
        out.append(c)
        if bi < len(cards) and (i + 1) % FREQ == 0:
            out.append(cards[bi]); bi += 1
    # Sparse feed: still surface one sponsored card (but never dominate).
    if bi == 0 and cards and len(out) >= 2:
        out.insert(min(3, len(out)), cards[0])
    return out


# ───────────────────────── scoring / diversity ─────────────────────
_REL_BASE = {"self": 130, "friend_following": 100, "friend": 80,
             "following": 70, "discovery": 35}


def _score(c: dict, now: datetime) -> tuple[float, str]:
    base = _REL_BASE.get(c["follow_relationship"], 30)
    age_min = max(0.0, (now - c["_dt"]).total_seconds() / 60.0)
    recency = max(0.0, 60.0 - 0.04 * age_min)
    live = 30.0 if c.get("meta", {}).get("live") else 0.0
    pop = min(20.0, 2.0 * float(c.get("meta", {}).get("participant_count") or 0)
              + 0.5 * float(c.get("meta", {}).get("like_count") or 0))
    reason = c["follow_relationship"] + (";live" if live else "") + (";fresh" if recency > 40 else "")
    return base + recency + live + pop, reason


def _diversify(cands: list[dict]) -> list[dict]:
    """Round-robin over type buckets (each already score-sorted) so the wall
    doesn't clump 10 of one type. Falls through gracefully when a type runs out."""
    buckets: dict[str, list[dict]] = {}
    for c in cands:
        buckets.setdefault(c["type"], []).append(c)
    order = sorted(buckets.keys(),
                   key=lambda t: buckets[t][0]["score"], reverse=True)
    out: list[dict] = []
    while any(buckets[t] for t in order):
        for t in order:
            if buckets[t]:
                out.append(buckets[t].pop(0))
    return out


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_cursor(cur: Optional[str]) -> int:
    if not cur:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cur.encode()).decode()))
    except Exception:
        return 0


# ───────────────────────── AI rerank (cached, optional) ────────────
async def _cached_ai_order(db, uid: str, mode: str) -> Optional[list[str]]:
    doc = await db.social_feed_rank_cache.find_one({"_id": f"{uid}:{mode}"})
    if not doc:
        return None
    ts = _dt(doc.get("updated_at"))
    if (_now() - ts).total_seconds() > RANK_CACHE_TTL_SEC:
        return None
    return doc.get("order") or None


async def refresh_ai_order(db, uid: str, mode: str, summaries: list[dict]) -> None:
    """Background task: ask Claude to reorder the top candidates by relevance
    and cache the resulting id order. Never raises."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key or not summaries:
        return
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        lines = [f"{i}. [{s['type']}] {(s.get('title') or s.get('text') or '')[:80]}"
                 f" · from {s['actor']} · {s['rel']}" for i, s in enumerate(summaries)]
        chat = LlmChat(
            api_key=key, session_id=f"feedrank_{uid}_{mode}",
            system_message=("You rank a social feed for relevance. Return ONLY a "
                            "JSON array of the item numbers in the best order, most "
                            "engaging first. Favour friends, followed people, and "
                            "live/fresh content. Do not invent items.")
        ).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text="\n".join(lines)))
        s = raw if isinstance(raw, str) else str(raw)
        a, b = s.find("["), s.rfind("]")
        if a == -1 or b == -1:
            return
        idxs = json.loads(s[a:b + 1])
        order = [summaries[i]["id"] for i in idxs
                 if isinstance(i, int) and 0 <= i < len(summaries)]
        if order:
            await db.social_feed_rank_cache.update_one(
                {"_id": f"{uid}:{mode}"},
                {"$set": {"order": order, "updated_at": _now()}}, upsert=True)
    except Exception:
        return


def _apply_ai_order(cands: list[dict], order: list[str]) -> list[dict]:
    pos = {cid: i for i, cid in enumerate(order)}
    ranked = [c for c in cands if c["id"] in pos]
    rest = [c for c in cands if c["id"] not in pos]
    ranked.sort(key=lambda c: pos[c["id"]])
    return ranked + rest


# ───────────────────────── public build ────────────────────────────
async def build_feed(db, user: dict, *, mode: str = "following",
                     cursor: Optional[str] = None, limit: int = 20,
                     types: Optional[list[str]] = None,
                     background_tasks=None) -> dict:
    uid = user["user_id"]
    mode = mode if mode in ("following", "for_you") else "following"
    limit = max(1, min(int(limit or 20), 40))
    elig = await _eligibility(db, uid)

    cands: list[dict] = []
    for builder in (_moments, _live_shows, _rooms, _dreams, _tarot, _station_posts,
                    _radio_clips, _readings, _business_posts):
        try:
            cands.extend(await builder(db, uid, elig, mode))
        except Exception:
            continue

    if types:
        allow = {t.upper() for t in types}
        cands = [c for c in cands if c["type"] in allow]

    # De-dupe by id, keep newest.
    seen: dict[str, dict] = {}
    for c in cands:
        seen[c["id"]] = c
    cands = list(seen.values())[:MAX_CANDIDATES]

    now = _now()
    for c in cands:
        c["score"], c["ranking_reason"] = _score(c, now)
    cands.sort(key=lambda c: c["score"], reverse=True)

    # Optional cached AI rerank of the head (for_you benefits most).
    order = await _cached_ai_order(db, uid, mode)
    if order:
        cands = _apply_ai_order(cands, order)
    elif background_tasks is not None and os.environ.get("EMERGENT_LLM_KEY"):
        head = cands[:15]
        summaries = [{"id": c["id"], "type": c["type"], "title": c.get("title"),
                      "text": c.get("text"), "actor": (c["actor"] or {}).get("name"),
                      "rel": c["follow_relationship"]} for c in head]
        background_tasks.add_task(refresh_ai_order, db, uid, mode, summaries)

    cands = _diversify(cands)

    # Labelled Sponsored business posts (Premium = ad-free; respects Hide Ad).
    try:
        cands = await _inject_sponsored(db, uid, cands)
    except Exception:
        pass

    offset = _decode_cursor(cursor)
    page = cands[offset:offset + limit]
    has_more = offset + limit < len(cands)
    for c in page:
        c.pop("_dt", None)
        c.pop("score", None)
    return {
        "items": page, "mode": mode,
        "next_cursor": _encode_cursor(offset + limit) if has_more else None,
        "has_more": has_more, "total_candidates": len(cands),
    }


async def latest_feed_ts(db, user: dict, mode: str = "following") -> Optional[str]:
    """Newest candidate timestamp — powers the 'N new posts' check cheaply."""
    res = await build_feed(db, user, mode=mode, limit=1)
    items = res.get("items") or []
    return items[0]["created_at"] if items else None


# ───────────────────────── Compact Right Rail (web) ────────────────
# 5–7 compact cards mixing LIVE / upcoming EVENT / suggested FOLLOW /
# suggested STATION — contextually weighted by the current page route.
_RAIL_CTX = {
    "/shop":      {"live": 1.25, "event": 1.10, "follow": 0.85, "station": 0.95},
    "/social":    {"live": 1.10, "event": 1.00, "follow": 1.35, "station": 1.05},
    "/channels":  {"live": 1.05, "event": 0.95, "follow": 0.90, "station": 1.35},
    "/play":      {"live": 1.15, "event": 1.10, "follow": 0.90, "station": 0.90},
    "/community": {"live": 1.00, "event": 1.00, "follow": 1.20, "station": 1.05},
    "/home":      {"live": 1.20, "event": 1.05, "follow": 1.00, "station": 1.00},
}
_RAIL_BASE = {"live": 60.0, "event": 42.0, "follow": 46.0, "station": 40.0}
_RAIL_REL = {"friend_following": 1.6, "friend": 1.4, "following": 1.3}


def _diversify_rail(cards: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for c in cards:
        buckets.setdefault(c["kind"], []).append(c)
    order = sorted(buckets.keys(),
                   key=lambda k: buckets[k][0]["score"], reverse=True)
    out: list[dict] = []
    while any(buckets[k] for k in order):
        for k in order:
            if buckets[k]:
                out.append(buckets[k].pop(0))
    return out


async def build_rail(db, user: dict, *, page_route: str = "/home",
                     limit: int = 7) -> dict:
    uid = user["user_id"]
    elig = await _eligibility(db, uid)
    udoc = await db.users.find_one({"user_id": uid}, {"interests": 1})
    interests = set((udoc or {}).get("interests") or [])
    ctx = _RAIL_CTX.get(page_route, _RAIL_CTX["/home"])
    cards: list[dict] = []

    # ── Live now + upcoming (scheduled) shows ──
    hids: set[str] = set()
    live_rows, sched_rows = [], []
    async for s in db.live_shows.find({"status": "live"}).sort("started_at", -1).limit(8):
        live_rows.append(s)
        hids.add(s.get("host_id"))
    async for s in db.live_shows.find(
            {"status": "scheduled", "scheduled_at": {"$gte": _now()}}
            ).sort("scheduled_at", 1).limit(8):
        sched_rows.append(s)
        hids.add(s.get("host_id"))
    umap: dict[str, dict] = {}
    async for u in db.users.find({"user_id": {"$in": list(hids)}}):
        umap[u["user_id"]] = u

    def _host(s: dict) -> str:
        biz = s.get("business_name")
        if biz:
            return biz
        u = umap.get(s.get("host_id"))
        return (u.get("name") if u else None) or "FUUSIC Live"

    for s in live_rows:
        cards.append({
            "id": f"LIVE:{s['_id']}", "kind": "live",
            "title": s.get("title") or "Live now", "subtitle": _host(s),
            "image": s.get("cover_url"), "badge": "LIVE", "cta": "Watch",
            "to": "/social?tab=live", "sponsored": False,
            "rel": _rel(s.get("host_id"), elig),
            "_dt": _dt(s.get("started_at") or s.get("created_at")),
        })
    for s in sched_rows:
        cards.append({
            "id": f"EVENT:{s['_id']}", "kind": "event",
            "title": s.get("title") or "Upcoming show", "subtitle": _host(s),
            "image": s.get("cover_url"), "badge": "SOON", "cta": "View",
            "to": "/social?tab=live", "sponsored": False,
            "when": _iso(s.get("scheduled_at")),
            "rel": _rel(s.get("host_id"), elig),
            "_dt": _dt(s.get("scheduled_at")),
        })

    # ── Smart follow suggestions — ranked by MUTUAL CONNECTIONS + chosen
    #    INTEREST topics + category affinity, not just availability ────────
    exclude = elig["following"] | elig["friends"] | elig["blocked"] | {uid}
    cand: dict[str, dict] = {}
    async for a in db.advisor_profiles.find(
            {"status": {"$in": [None, "approved", "active"]}},
            {"user_id": 1, "headline": 1, "category": 1, "topics": 1}).limit(60):
        aid = a.get("user_id")
        if aid and aid not in exclude and aid not in cand:
            topics = set(a.get("topics") or [])
            if a.get("category"):
                topics.add(str(a["category"]).upper())
            cand[aid] = {"headline": a.get("headline"),
                         "category": a.get("category"), "topics": topics}
    if cand:
        # category affinity: categories of advisors the user already follows
        my_cats: set[str] = set()
        if elig["following"]:
            async for a in db.advisor_profiles.find(
                    {"user_id": {"$in": list(elig["following"])}}, {"category": 1}):
                if a.get("category"):
                    my_cats.add(a["category"])
        # mutual connections: people the user follows who also follow candidate
        mutual: dict[str, int] = {}
        if elig["following"]:
            async for f in db.social_follows.find(
                    {"follower": {"$in": list(elig["following"])},
                     "target": {"$in": list(cand)}}, {"target": 1}):
                mutual[f["target"]] = mutual.get(f["target"], 0) + 1
        sugg: list[dict] = []
        async for u in db.users.find({"user_id": {"$in": list(cand)}}):
            cu = u["user_id"]
            meta = cand[cu]
            mc = mutual.get(cu, 0)
            aff = 1 if (meta.get("category") and meta["category"] in my_cats) else 0
            imatch = len(interests & meta["topics"]) if interests else 0
            if mc:
                hint = f"{mc} mutual"
            elif imatch:
                hint = "Matches your interests"
            elif aff:
                hint = "Shared interest"
            else:
                hint = None
            sugg.append({
                "id": f"FOLLOW:{cu}", "kind": "follow",
                "title": u.get("name") or "Advisor",
                "subtitle": meta.get("headline") or "Advisor · Tarot & Dreams",
                "image": u.get("picture") or u.get("avatar_url"),
                "badge": "SUGGESTED", "cta": "Follow", "follow_id": cu,
                "sponsored": False, "rel": "discovery", "hint": hint, "mutual": mc,
                "boost": mc * 12.0 + aff * 8.0 + min(imatch, 2) * 10.0,
            })
        sugg.sort(key=lambda x: x["boost"], reverse=True)
        cards.extend(sugg[:6])

    # ── Suggested stations to tune into (not yet followed) ──
    st_n = 0
    async for s in db.community_radio_stations.find(
            {"station_id": {"$nin": list(elig["stations"])}}).limit(20):
        if s.get("owner_user_id") == uid:
            continue
        cards.append({
            "id": f"STATION:{s.get('station_id')}", "kind": "station",
            "title": s.get("name") or s.get("slug") or "Station",
            "subtitle": s.get("page_type") or "Community station",
            "image": s.get("cover_image_url"), "badge": "TUNE IN", "cta": "Listen",
            "to": f"/r/{s.get('slug') or s.get('station_id')}",
            "sponsored": False, "rel": "discovery",
        })
        st_n += 1
        if st_n >= 4:
            break

    # ── Contextual + relationship + recency + smart-boost scoring ──
    now = _now()
    for c in cards:
        base = _RAIL_BASE.get(c["kind"], 30.0) * ctx.get(c["kind"], 1.0)
        rb = _RAIL_REL.get(c.get("rel"), 1.0)
        rec = 0.0
        if c.get("_dt"):
            age_h = max(0.0, (now - c["_dt"]).total_seconds() / 3600.0)
            rec = max(0.0, 20.0 - age_h)
        c["score"] = base * rb + rec + c.get("boost", 0.0)
    cards.sort(key=lambda c: c["score"], reverse=True)
    cards = _diversify_rail(cards)

    # ── Paid Sponsored slot pinned to the TOP (per-area second-price auction) ──
    from services.rail_auction import sponsored_card_for_area
    sponsored = await sponsored_card_for_area(db, page_route)
    if sponsored:
        cards = [sponsored] + [c for c in cards if c["kind"] != "sponsored"]

    out = cards[:max(1, min(int(limit or 7), 7))]
    for c in out:
        c.pop("_dt", None)
        c.pop("score", None)
        c.pop("rel", None)
        c.pop("boost", None)
    return {"cards": out, "page_route": page_route}


__all__ = ["build_feed", "build_rail", "refresh_ai_order", "latest_feed_ts",
           "WALL_TYPES"]
