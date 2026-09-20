"""RadioLife Social V2 — DREAM CLUSTERS + COMPATIBILITY.

Clusters: Claude maps each shared dream to normalized themes (Falling,
Being Chased, Water …); the Clusters view groups public dreams by theme so
people instantly find others who dreamed the same thing.

Compatibility: a PLAYFUL, entertainment-only score between two people based
on their shared dream themes + star signs. Never a real relationship claim.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user, current_user_optional
from routes.social_v2 import _friend_ids, _user_public
from routes.dreams_guidance import _dream_public

router = APIRouter(prefix="/api/social", tags=["dream_clusters"])

DISCLAIMER = ("Playful and AI-generated for entertainment only — not a real "
              "compatibility, psychological or relationship assessment.")

# Normalized dream-theme taxonomy (key -> label). Kept small + universal.
THEMES = [
    ("falling", "Falling"), ("being_chased", "Being Chased"),
    ("flying", "Flying"), ("teeth", "Teeth Falling Out"),
    ("water", "Water & Ocean"), ("tests", "Exams & Tests"),
    ("naked", "Unprepared / Exposed"), ("late", "Running Late"),
    ("lost", "Lost or Searching"), ("death", "Death & Endings"),
    ("house", "Houses & Rooms"), ("animals", "Animals"),
    ("travel", "Travel & Journeys"), ("money", "Money & Work"),
    ("romance", "Love & Reunion"), ("family", "Family"),
    ("nature", "Nature & Sky"), ("supernatural", "Supernatural"),
    ("conflict", "Conflict & Fear"), ("rebirth", "Rebirth & Hope"),
]
THEME_LABELS = {k: v for k, v in THEMES}
THEME_KEYS = [k for k, _ in THEMES]

_THEME_SYSTEM = (
    "You label dreams with themes for a social app. Given a dream, pick the 1-4 "
    "BEST-matching theme keys from this fixed list (return keys only, no new ones): "
    + ", ".join(THEME_KEYS)
    + ". Return ONLY compact JSON, no markdown: {\"themes\": [\"key\", ...]}.")

_COMPAT_SYSTEM = (
    "You write SHORT, playful, uplifting 'dream compatibility' blurbs for a social "
    "app — pure entertainment, like a magazine quiz. Rules: (1) never claim it is a "
    "real relationship, psychological or medical assessment; (2) be warm, kind and "
    "light; (3) never predict breakups, health or the future. Return ONLY compact "
    "JSON: {\"headline\": str, \"blurb\": str, \"shared_note\": str}.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


async def _llm(system: str, prompt: str, session: str) -> Optional[dict]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=prompt))
        s = raw if isinstance(raw, str) else str(raw)
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            return json.loads(s[a:b + 1])
    except Exception:
        return None
    return None


def _keyword_themes(text: str) -> list:
    """Cheap fallback if the LLM is unavailable."""
    t = (text or "").lower()
    hits = []
    table = {
        "falling": ["fall", "falling", "cliff"], "being_chased": ["chase", "chased", "running from"],
        "flying": ["fly", "flying", "float"], "teeth": ["teeth", "tooth"],
        "water": ["ocean", "sea", "water", "flood", "wave", "river", "swim"],
        "tests": ["exam", "test", "school", "class"], "naked": ["naked", "undressed"],
        "late": ["late", "missed", "train", "flight"], "lost": ["lost", "searching", "maze"],
        "death": ["death", "died", "dying", "funeral"], "house": ["house", "room", "home"],
        "animals": ["dog", "cat", "snake", "bird", "animal"], "travel": ["travel", "journey", "road", "car"],
        "money": ["money", "work", "job", "boss"], "romance": ["love", "kiss", "ex", "reunion"],
        "family": ["mother", "father", "family", "child"], "nature": ["sky", "forest", "mountain", "star"],
        "supernatural": ["ghost", "spirit", "magic", "demon"], "conflict": ["fight", "afraid", "fear", "scared"],
        "rebirth": ["light", "hope", "born", "new"],
    }
    for key, words in table.items():
        if any(w in t for w in words):
            hits.append(key)
    return hits[:4]


async def extract_and_store_themes(db, dream_id: str) -> list:
    """Best-effort: assign normalized themes to a dream (called in background)."""
    d = await db.dreams.find_one({"_id": dream_id})
    if not d or d.get("themes"):
        return (d or {}).get("themes", [])
    text = f"{d.get('title') or ''}\n{d.get('description') or ''}".strip()
    res = await _llm(_THEME_SYSTEM, f"Dream:\n{text}", f"themes_{dream_id}")
    themes = []
    if isinstance(res, dict):
        themes = [k for k in (res.get("themes") or []) if k in THEME_KEYS]
    if not themes:
        themes = _keyword_themes(text)
    themes = themes[:4]
    await db.dreams.update_one({"_id": dream_id}, {"$set": {"themes": themes}})
    try:  # cluster alerts: ping followers of these themes (skip the author)
        if d.get("visibility") == "public" and themes:
            await _fanout_cluster_alerts(db, d, themes)
    except Exception:
        pass
    return themes


async def _fanout_cluster_alerts(db, dream: dict, themes: list) -> None:
    author = dream.get("user_id")
    notified: set = set()
    for t in themes:
        async for f in db.cluster_follows.find({"theme": t}).limit(500):
            uid = f.get("user_id")
            if not uid or uid == author or uid in notified:
                continue
            notified.add(uid)
            aid = f"al_{uuid.uuid4().hex[:14]}"
            await db.dream_alerts.insert_one({
                "_id": aid, "user_id": uid, "type": "cluster", "theme": t,
                "theme_label": THEME_LABELS.get(t, t), "dream_id": dream["_id"],
                "title": dream.get("title") or "A new dream", "read": False,
                "created_at": _now()})


async def _my_theme_follows(db, uid: str) -> set:
    return {f["theme"] async for f in db.cluster_follows.find({"user_id": uid})}


async def ensure_clusters_ai_indexes(db) -> None:
    await db.dreams.create_index([("themes", 1)], name="dreams_themes")
    await db.cluster_follows.create_index([("theme", 1)], name="cf_theme")
    await db.cluster_follows.create_index([("user_id", 1)], name="cf_user")
    await db.dream_alerts.create_index([("user_id", 1), ("read", 1),
                                        ("created_at", -1)], name="alerts_user")
    await db.compat_cards.create_index("card_id", unique=True, name="compat_card")
    # Backfill themes for a handful of public dreams that don't have any yet.
    cursor = db.dreams.find(
        {"status": "active", "visibility": "public",
         "themes": {"$exists": False}}).limit(40)
    ids = [d["_id"] async for d in cursor]
    for did in ids:
        try:
            await extract_and_store_themes(db, did)
        except Exception:
            pass


# ───────────────────────────── Clusters ────────────────────────────
@router.get("/clusters")
async def clusters(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    pipeline = [
        {"$match": {"status": "active", "visibility": "public",
                    "themes": {"$exists": True, "$ne": []}}},
        {"$unwind": "$themes"},
        {"$group": {"_id": "$themes", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    counts = {row["_id"]: row["count"] async for row in db.dreams.aggregate(pipeline)}
    follows = await _my_theme_follows(db, user["user_id"])
    out = []
    for key in sorted(counts, key=lambda k: counts[k], reverse=True):
        if key not in THEME_LABELS:
            continue
        samples = []
        async for d in db.dreams.find(
                {"status": "active", "visibility": "public", "themes": key}
        ).sort("similar_count", -1).limit(3):
            author = None
            if not d.get("anonymous"):
                au = await db.users.find_one({"user_id": d["user_id"]})
                author = _user_public(au) if au else None
            samples.append(_dream_public(d, user["user_id"], author))
        out.append({"theme": key, "label": THEME_LABELS[key],
                    "count": counts[key], "following": key in follows,
                    "samples": samples})
    return {"clusters": out}


@router.get("/clusters/{theme}")
async def cluster_dreams(theme: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    if theme not in THEME_LABELS:
        raise HTTPException(404, {"code": "unknown_theme"})
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    q = {"status": "active", "themes": theme,
         "$or": [{"visibility": "public"},
                 {"visibility": "friends", "user_id": {"$in": list(friends) + [uid]}},
                 {"user_id": uid}]}
    rows = []
    author_ids = set()
    async for d in db.dreams.find(q).sort("created_at", -1).limit(60):
        rows.append(d)
        if not d.get("anonymous") or d.get("user_id") == uid:
            author_ids.add(d["user_id"])
    authors = {}
    if author_ids:
        async for u in db.users.find({"user_id": {"$in": list(author_ids)}}):
            authors[u["user_id"]] = _user_public(u)
    return {"theme": theme, "label": THEME_LABELS[theme],
            "following": theme in await _my_theme_follows(db, uid),
            "items": [_dream_public(d, uid, authors.get(d["user_id"])) for d in rows]}


# ─────────────────────── Cluster follows + alerts ──────────────────
@router.post("/clusters/{theme}/follow")
async def follow_cluster(theme: str, request: Request,
                         user: dict = Depends(current_user)):
    if theme not in THEME_LABELS:
        raise HTTPException(404, {"code": "unknown_theme"})
    db = request.app.state.db
    await db.cluster_follows.update_one(
        {"_id": f"{theme}:{user['user_id']}"},
        {"$set": {"theme": theme, "user_id": user["user_id"], "created_at": _now()}},
        upsert=True)
    return {"ok": True, "following": True}


@router.delete("/clusters/{theme}/follow")
async def unfollow_cluster(theme: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.cluster_follows.delete_one({"_id": f"{theme}:{user['user_id']}"})
    return {"ok": True, "following": False}


@router.get("/alerts")
async def my_alerts(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    items = []
    async for a in db.dream_alerts.find(
            {"user_id": user["user_id"]}).sort("created_at", -1).limit(50):
        items.append({"id": a["_id"], "type": a.get("type"), "theme": a.get("theme"),
                      "theme_label": a.get("theme_label"), "dream_id": a.get("dream_id"),
                      "title": a.get("title"), "read": bool(a.get("read")),
                      "created_at": _iso(a.get("created_at"))})
    unread = await db.dream_alerts.count_documents(
        {"user_id": user["user_id"], "read": False})
    return {"items": items, "unread": unread}


@router.get("/alerts/unread_count")
async def alerts_unread(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return {"unread": await db.dream_alerts.count_documents(
        {"user_id": user["user_id"], "read": False})}


class AlertReadBody(BaseModel):
    alert_id: Optional[str] = None


@router.post("/alerts/read")
async def alerts_read(body: AlertReadBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"user_id": user["user_id"]}
    if body.alert_id:
        q["_id"] = body.alert_id
    await db.dream_alerts.update_many(q, {"$set": {"read": True}})
    return {"ok": True}


# ─────────────────────────── Compatibility ─────────────────────────
async def _user_themes(db, uid: str) -> list:
    themes: dict = {}
    async for d in db.dreams.find(
            {"user_id": uid, "themes": {"$exists": True, "$ne": []}}
    ).sort("created_at", -1).limit(40):
        for t in d.get("themes", []):
            themes[t] = themes.get(t, 0) + 1
    return sorted(themes, key=lambda k: themes[k], reverse=True)


async def _user_sign(db, uid: str) -> Optional[str]:
    r = await db.ai_readings.find_one(
        {"user_id": uid, "type": "horoscope"}, sort=[("created_at", -1)])
    return r.get("subject") if r else None


@router.get("/compatibility/candidates")
async def compat_candidates(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    items = []
    if friends:
        async for u in db.users.find({"user_id": {"$in": list(friends)}}).limit(60):
            pub = _user_public(u)
            items.append({"user_id": u["user_id"], "name": pub.get("name"),
                          "avatar_url": pub.get("avatar_url")})
    return {"items": items, "note": "Pick a friend to see your playful dream match."}


class CompatBody(BaseModel):
    target_user_id: str


@router.post("/compatibility")
async def compatibility(body: CompatBody, request: Request,
                        user: dict = Depends(current_user)):
    return await _compute_compat(request.app.state.db, user["user_id"],
                                 body.target_user_id)


async def _compute_compat(db, uid: str, target_id: str) -> dict:
    if target_id == uid:
        raise HTTPException(400, {"code": "cannot_match_self"})
    target = await db.users.find_one({"user_id": target_id})
    if not target:
        raise HTTPException(404, {"code": "user_not_found"})
    my_themes = await _user_themes(db, uid)
    their_themes = await _user_themes(db, target_id)
    shared = [t for t in my_themes if t in their_themes]
    my_sign = await _user_sign(db, uid)
    their_sign = await _user_sign(db, target_id)
    import hashlib
    seed = int(hashlib.md5("|".join(sorted([uid, target_id]))
                           .encode()).hexdigest(), 16)
    base = 55 + (seed % 26)
    score = min(99, base + 4 * len(shared))
    me = _user_public(await db.users.find_one({"user_id": uid}))
    them = _user_public(target)
    prompt = (
        f"Person A ({me.get('name')}) star sign {my_sign or 'unknown'}, dream themes "
        f"{[THEME_LABELS.get(t, t) for t in my_themes[:5]] or 'none yet'}. "
        f"Person B ({them.get('name')}) star sign {their_sign or 'unknown'}, dream themes "
        f"{[THEME_LABELS.get(t, t) for t in their_themes[:5]] or 'none yet'}. "
        f"Shared themes: {[THEME_LABELS.get(t, t) for t in shared] or 'none'}. "
        f"Their playful dream-match score is {score}/100. Write a fun, kind blurb.")
    res = await _llm(_COMPAT_SYSTEM, prompt, f"compat_{uid}_{target_id}")
    if not isinstance(res, dict):
        res = {"headline": f"{score}% dream sync ✨",
               "blurb": ("Your dream worlds share a gentle, curious energy — a fun "
                         "match to explore stories together."),
               "shared_note": ("You both wander similar dreamscapes."
                               if shared else "Two different dream worlds, equally magical.")}
    return {"score": score,
            "headline": res.get("headline") or f"{score}% dream sync",
            "blurb": res.get("blurb"),
            "shared_note": res.get("shared_note"),
            "shared_themes": [THEME_LABELS.get(t, t) for t in shared],
            "my_sign": my_sign, "their_sign": their_sign,
            "target": {"user_id": target["user_id"],
                       "name": them.get("name"), "avatar_url": them.get("avatar_url")},
            "label": "PLAYFUL · entertainment only", "disclaimer": DISCLAIMER}


@router.post("/compatibility/share")
async def compatibility_share(body: CompatBody, request: Request,
                              user: dict = Depends(current_user)):
    """Persist a match as a shareable public card (+1 BigPoint for sharing)."""
    db = request.app.state.db
    res = await _compute_compat(db, user["user_id"], body.target_user_id)
    me = _user_public(await db.users.find_one({"user_id": user["user_id"]}))
    card_id = f"mc_{uuid.uuid4().hex[:14]}"
    await db.compat_cards.insert_one({
        "_id": card_id, "card_id": card_id, "owner_id": user["user_id"],
        "owner_name": me.get("name"), "target_name": res["target"]["name"],
        "score": res["score"], "headline": res["headline"], "blurb": res["blurb"],
        "shared_note": res["shared_note"], "shared_themes": res["shared_themes"],
        "my_sign": res["my_sign"], "their_sign": res["their_sign"],
        "public": True, "created_at": _now()})
    pts = 0
    try:
        from routes.dreams_guidance import award_social_share
        pts = await award_social_share(db, user["user_id"], f"compat:{card_id}")
    except Exception:
        pts = 0
    return {"card_id": card_id, "path": f"/dreams/match/{card_id}",
            "points_awarded": pts, **res}


@router.get("/compatibility/card/{card_id}")
async def compat_card(card_id: str, request: Request,
                      user: Optional[dict] = Depends(current_user_optional)):
    """Public, no-login view of a shared match card."""
    db = request.app.state.db
    c = await db.compat_cards.find_one({"card_id": card_id, "public": True})
    if not c:
        raise HTTPException(404, {"code": "card_not_found"})
    return {"card_id": card_id, "owner_name": c.get("owner_name"),
            "target_name": c.get("target_name"), "score": c.get("score"),
            "headline": c.get("headline"), "blurb": c.get("blurb"),
            "shared_note": c.get("shared_note"),
            "shared_themes": c.get("shared_themes") or [],
            "my_sign": c.get("my_sign"), "their_sign": c.get("their_sign"),
            "label": "PLAYFUL · entertainment only", "disclaimer": DISCLAIMER,
            "created_at": _iso(c.get("created_at"))}


__all__ = ["router", "ensure_clusters_ai_indexes", "extract_and_store_themes",
           "THEME_LABELS"]
