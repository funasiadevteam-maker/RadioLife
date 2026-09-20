"""RadioLife Social V2 — DREAMS & GUIDANCE (Phase 1, shared backend).

A reflective community layer inside Social V2:

  share a dream (named or anonymous) → discover similar dreams → comment →
  AI reflection (safety-framed) → verified-advisor input → optional paid
  private reading.

Reuses the shared foundations — Social identity + friend graph
(`routes.social_v2._friend_ids`), Stripe (env-driven, same pattern as
marketplace service bookings), the Emergent LLM key for AI reflection, and
the admin/RBAC session. NOT a standalone fortune-telling app: positioned as
reflection · entertainment · spiritual guidance, never medical / legal /
financial advice, and no result is guaranteed.

All consumer routes are /api/social/dreams/*  ·  admin routes /api/admin/dreams/*.
"""
from __future__ import annotations
from core.origins import resolve_origin

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional, require_admin
from routes.social_v2 import _friend_ids, _user_public

router = APIRouter(prefix="/api/social/dreams", tags=["dreams_guidance"])
admin_router = APIRouter(prefix="/api/admin/dreams", tags=["dreams_guidance_admin"])

TERMS_VERSION = "1.0"

MOODS = ["Happy", "Scary", "Confusing", "Peaceful", "Sad", "Exciting",
         "Strange", "Other"]
TAGS = ["Flying", "Falling", "Water", "Animals", "Family", "Death", "Work",
        "Love", "Travel", "Religious/Spiritual", "Recurring", "Lucid",
        "Nightmare", "Other"]
REACTIONS = ["relate", "interesting", "comforting", "dreamed_too"]

# Distinct advisor identity categories — spiritual/entertainment kept separate
# from licensed health professionals. NEVER one generic "Expert" badge.
SPIRITUAL_CATEGORIES = ["spiritual_advisor", "dream_interpreter", "astrologer",
                        "tarot_reader", "numerologist"]
LICENSED_CATEGORIES = ["licensed_sleep", "licensed_mental_health"]
ADVISOR_CATEGORIES = SPIRITUAL_CATEGORIES + LICENSED_CATEGORIES
CATEGORY_LABELS = {
    "spiritual_advisor": "Verified Spiritual Advisor",
    "dream_interpreter": "Dream Interpreter",
    "astrologer": "Astrologer",
    "tarot_reader": "Tarot Reader",
    "numerologist": "Numerologist",
    "licensed_sleep": "Licensed Sleep Professional",
    "licensed_mental_health": "Licensed Mental Health Professional",
}

DELIVERY_TYPES = ["written", "voice", "video_recorded", "live_video", "live_audio"]

DISCLAIMER_GLOBAL = (
    "RadioLife's spiritual, astrology, tarot, numerology and dream features are "
    "provided for entertainment, reflection and general informational purposes. "
    "They are not medical, mental-health, legal or financial advice and no result "
    "or prediction is guaranteed.")
DISCLAIMER_BOOKING = (
    "Advisor opinions and interpretations are the advisor's own. RadioLife does not "
    "guarantee the accuracy, outcome or predictive value of spiritual, astrology, "
    "tarot, numerology or dream-reading services.")
AI_HEADER = ("This is one possible interpretation, not a factual diagnosis or "
             "prediction.")

# Lightweight distress signal → always append a supportive, non-diagnostic note.
_DISTRESS = ("suicide", "kill myself", "self harm", "self-harm", "end my life",
             "want to die", "hurt myself")

DEFAULT_FLAGS = {
    "_id": "guidance_flags",
    "dream_sharing_enabled": True,
    "dream_ai_enabled": True,
    "advisor_marketplace_enabled": True,
    "paid_readings_enabled": True,
    "licensed_professional_services_enabled": True,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _extract_themes_bg(db, dream_id: str) -> None:
    """Background: tag a freshly shared dream with normalized themes (clusters)."""
    try:
        from routes.dream_clusters import extract_and_store_themes
        await extract_and_store_themes(db, dream_id)
    except Exception:
        pass


async def award_social_share(db, user_id: str, source_id: str) -> int:
    """+1 BigPoint whenever a user shares something in the social section.

    Idempotent per share (unique idempotency_key) and gated by the
    `social_share` earn-rule daily cap so it can't be farmed.
    """
    try:
        from services.points_service import PointsService
        r = await PointsService(db).award(
            user_id=user_id, source="social_share", source_id=source_id,
            delta=1, idempotency_key=f"social_share:{source_id}",
            metadata={"section": "social"})
        try:  # sharing also counts toward the daily streak habit
            from services.points_service import touch_daily_streak
            await touch_daily_streak(db, user_id)
        except Exception:
            pass
        return 1 if (r.ok and not r.idempotency_hit and not r.capped) else 0
    except Exception:
        return 0


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _stripe():
    import stripe
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")
    return stripe


async def _flags(db) -> dict:
    doc = await db.guidance_flags.find_one({"_id": "guidance_flags"})
    return doc or DEFAULT_FLAGS


async def _require_flag(db, name: str):
    if not (await _flags(db)).get(name, False):
        raise HTTPException(403, {"code": "feature_disabled", "flag": name})


# ───────────────────────── Bootstrap ───────────────────────────────
async def ensure_dreams_indexes(db) -> None:
    await db.dreams.create_index([("visibility", 1), ("created_at", -1)], name="dr_feed")
    await db.dreams.create_index([("user_id", 1), ("created_at", -1)], name="dr_mine")
    await db.dreams.create_index("status", name="dr_status")
    await db.dream_similar.create_index([("dream_id", 1), ("user_id", 1)],
                                        unique=True, name="ds_uniq")
    await db.dream_reactions.create_index([("dream_id", 1), ("user_id", 1), ("kind", 1)],
                                          unique=True, name="drx_uniq")
    await db.dream_comments.create_index([("dream_id", 1), ("created_at", 1)],
                                         name="dc_room_time")
    await db.dream_saves.create_index([("user_id", 1), ("created_at", -1)], name="dsv_mine")
    await db.dream_reports.create_index([("status", 1), ("created_at", -1)], name="drep_q")
    await db.advisor_profiles.create_index("advisor_id", unique=True, name="adv_id")
    await db.advisor_profiles.create_index("user_id", unique=True, sparse=True, name="adv_user")
    await db.advisor_profiles.create_index([("status", 1), ("category", 1)], name="adv_q")
    await db.advisor_services.create_index([("advisor_id", 1), ("active", 1)], name="advsvc")
    await db.reading_bookings.create_index([("user_id", 1), ("created_at", -1)], name="rb_mine")
    await db.reading_bookings.create_index([("advisor_id", 1), ("created_at", -1)], name="rb_adv")
    await db.reading_bookings.create_index("booking_id", unique=True, name="rb_id")
    await db.advisor_reviews.create_index([("advisor_id", 1), ("created_at", -1)], name="arv")
    await db.guidance_flags.update_one(
        {"_id": "guidance_flags"}, {"$setOnInsert": DEFAULT_FLAGS}, upsert=True)


# ───────────────────────── Config / consent ────────────────────────
@router.get("/config")
async def get_config(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    flags = await _flags(db)
    consent = await db.guidance_consent.find_one({"_id": user["user_id"]})
    return {
        "flags": {k: v for k, v in flags.items() if k != "_id"},
        "consent_needed": not (consent and consent.get("terms_version") == TERMS_VERSION),
        "terms_version": TERMS_VERSION,
        "moods": MOODS, "tags": TAGS, "reactions": REACTIONS,
        "advisor_categories": [{"key": c, "label": CATEGORY_LABELS[c],
                                "licensed": c in LICENSED_CATEGORIES}
                               for c in ADVISOR_CATEGORIES],
        "disclaimers": {"global": DISCLAIMER_GLOBAL, "booking": DISCLAIMER_BOOKING,
                        "ai_header": AI_HEADER},
    }


@router.get("/streak")
async def my_streak(request: Request, user: dict = Depends(current_user)):
    """Current daily-habit streak (🔥). Increments by sharing OR reading."""
    from services.points_service import get_streak
    return await get_streak(request.app.state.db, user["user_id"])



@router.post("/consent")
async def accept_consent(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.guidance_consent.update_one(
        {"_id": user["user_id"]},
        {"$set": {"terms_version": TERMS_VERSION, "accepted_at": _now()}}, upsert=True)
    return {"ok": True, "terms_version": TERMS_VERSION}


# ───────────────────────── Dream serialization ─────────────────────
def _dream_public(d: dict, viewer_uid: str, author: Optional[dict] = None,
                  detail: bool = False) -> dict:
    mine = d.get("user_id") == viewer_uid
    anon = bool(d.get("anonymous"))
    if anon and not mine:
        who = {"name": "Anonymous Dreamer", "avatar_url": None,
               "user_id": None, "anonymous": True}
    else:
        pub = author or {}
        who = {"name": pub.get("name") or "Dreamer",
               "avatar_url": pub.get("avatar_url"),
               "user_id": d.get("user_id"), "anonymous": anon}
    out = {
        "dream_id": d["_id"], "title": d.get("title"),
        "description": d.get("description") if detail else (d.get("description") or "")[:220],
        "mood": d.get("mood"), "tags": d.get("tags") or [],
        "dream_date": d.get("dream_date"), "visibility": d.get("visibility"),
        "author": who, "mine": mine,
        "similar_count": int(d.get("similar_count", 0)),
        "comment_count": int(d.get("comment_count", 0)),
        "advisor_response_count": int(d.get("advisor_response_count", 0)),
        "reaction_counts": d.get("reaction_counts") or {},
        "ai_reflection": d.get("ai_reflection") if detail else bool(d.get("ai_reflection")),
        "created_at": _iso(d.get("created_at")),
    }
    return out


# ───────────────────────── Dream sharing ───────────────────────────
class DreamBody(BaseModel):
    title: Optional[str] = Field(None, max_length=140)
    description: str = Field(..., min_length=1, max_length=4000)
    mood: Optional[str] = None
    tags: list[str] = []
    dream_date: Optional[str] = None
    visibility: str = "friends"          # only_me | friends | public
    anonymous: bool = False


@router.post("")
async def share_dream(body: DreamBody, request: Request,
                      background_tasks: BackgroundTasks,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "dream_sharing_enabled")
    if body.visibility not in ("only_me", "friends", "public"):
        raise HTTPException(400, {"code": "bad_visibility"})
    did = f"dm_{uuid.uuid4().hex[:16]}"
    doc = {
        "_id": did, "user_id": user["user_id"],
        "title": (body.title or "").strip() or None,
        "description": body.description.strip(),
        "mood": body.mood if body.mood in MOODS else None,
        "tags": [t for t in (body.tags or []) if t in TAGS][:8],
        "dream_date": body.dream_date,
        "visibility": body.visibility,
        "anonymous": bool(body.anonymous),
        "similar_count": 0, "comment_count": 0, "advisor_response_count": 0,
        "reaction_counts": {}, "ai_reflection": None,
        "status": "active", "report_count": 0,
        "created_at": _now(), "updated_at": _now()}
    await db.dreams.insert_one(doc)
    background_tasks.add_task(_extract_themes_bg, db, did)
    pts = await award_social_share(db, user["user_id"], f"dream:{did}")
    out = _dream_public(doc, user["user_id"], _user_public(user), detail=True)
    out["points_awarded"] = pts
    return out


@router.get("")
async def dream_feed(request: Request, scope: str = "discover",
                     mood: Optional[str] = None, tag: Optional[str] = None,
                     user: dict = Depends(current_user)):
    """scope: discover (public + friends') | friends | mine."""
    db = request.app.state.db
    uid = user["user_id"]
    q: dict = {"status": "active"}
    if scope == "mine":
        q["user_id"] = uid
    elif scope == "friends":
        friends = await _friend_ids(db, uid)
        q["user_id"] = {"$in": list(friends)}
        q["visibility"] = {"$in": ["friends", "public"]}
    else:  # discover
        friends = await _friend_ids(db, uid)
        q["$or"] = [{"visibility": "public"},
                    {"visibility": "friends", "user_id": {"$in": list(friends) + [uid]}},
                    {"user_id": uid}]
    if mood in MOODS:
        q["mood"] = mood
    if tag in TAGS:
        q["tags"] = tag
    rows: list[dict] = []
    author_ids: set[str] = set()
    async for d in db.dreams.find(q).sort("created_at", -1).limit(60):
        rows.append(d)
        if not d.get("anonymous") or d.get("user_id") == uid:
            author_ids.add(d["user_id"])
    authors: dict[str, dict] = {}
    if author_ids:
        async for u in db.users.find({"user_id": {"$in": list(author_ids)}}):
            authors[u["user_id"]] = _user_public(u)
    return {"items": [_dream_public(d, uid, authors.get(d["user_id"])) for d in rows]}


async def _dream_or_404(db, dream_id: str) -> dict:
    d = await db.dreams.find_one({"_id": dream_id})
    if not d or d.get("status") != "active":
        raise HTTPException(404, {"code": "dream_not_found"})
    return d


def _can_view(d: dict, uid: str, friends: set[str]) -> bool:
    if d["user_id"] == uid:
        return True
    vis = d.get("visibility")
    if vis == "public":
        return True
    if vis == "friends":
        return d["user_id"] in friends
    return False


@router.post("/{dream_id}/similar")
async def had_similar(dream_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    d = await _dream_or_404(db, dream_id)
    try:
        await db.dream_similar.insert_one(
            {"_id": f"{dream_id}:{uid}", "dream_id": dream_id, "user_id": uid,
             "created_at": _now()})
        await db.dreams.update_one({"_id": dream_id}, {"$inc": {"similar_count": 1}})
        d = await db.dreams.find_one({"_id": dream_id})
    except Exception:
        pass  # idempotent — already recorded
    return {"ok": True, "similar_count": int(d.get("similar_count", 0)), "my_similar": True}


class CommentBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=800)
    reaction: Optional[str] = None       # optional supportive tag


@router.post("/{dream_id}/comments")
async def add_comment(dream_id: str, body: CommentBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    d = await _dream_or_404(db, dream_id)
    friends = await _friend_ids(db, uid)
    if not _can_view(d, uid, friends):
        raise HTTPException(403, {"code": "not_visible"})
    pub = _user_public(user)
    cid = f"dc_{uuid.uuid4().hex[:16]}"
    await db.dream_comments.insert_one({
        "_id": cid, "dream_id": dream_id, "user_id": uid, "name": pub["name"],
        "avatar_url": pub["avatar_url"], "text": body.text.strip()[:800],
        "reaction": body.reaction if body.reaction in REACTIONS else None,
        "is_advisor": False, "advisor_category": None, "created_at": _now()})
    await db.dreams.update_one({"_id": dream_id}, {"$inc": {"comment_count": 1}})
    return {"ok": True, "id": cid}


class ReactBody(BaseModel):
    kind: str


@router.post("/{dream_id}/react")
async def react_dream(dream_id: str, body: ReactBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    if body.kind not in REACTIONS:
        raise HTTPException(400, {"code": "bad_reaction"})
    await _dream_or_404(db, dream_id)
    key = f"reaction_counts.{body.kind}"
    existing = await db.dream_reactions.find_one(
        {"dream_id": dream_id, "user_id": uid, "kind": body.kind})
    if existing:
        await db.dream_reactions.delete_one({"_id": existing["_id"]})
        await db.dreams.update_one({"_id": dream_id}, {"$inc": {key: -1}})
        active = False
    else:
        await db.dream_reactions.insert_one(
            {"_id": f"drx_{uuid.uuid4().hex[:14]}", "dream_id": dream_id,
             "user_id": uid, "kind": body.kind, "created_at": _now()})
        await db.dreams.update_one({"_id": dream_id}, {"$inc": {key: 1}})
        active = True
    d = await db.dreams.find_one({"_id": dream_id})
    return {"ok": True, "active": active, "reaction_counts": d.get("reaction_counts") or {}}


@router.post("/{dream_id}/save")
async def save_dream(dream_id: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    await _dream_or_404(db, dream_id)
    await db.dream_saves.update_one(
        {"_id": f"{dream_id}:{user['user_id']}"},
        {"$set": {"dream_id": dream_id, "user_id": user["user_id"], "created_at": _now()}},
        upsert=True)
    return {"ok": True, "saved": True}


@router.delete("/{dream_id}/save")
async def unsave_dream(dream_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.dream_saves.delete_one({"_id": f"{dream_id}:{user['user_id']}"})
    return {"ok": True, "saved": False}


class ReportBody(BaseModel):
    reason: str = Field(..., max_length=400)


@router.post("/{dream_id}/report")
async def report_dream(dream_id: str, body: ReportBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _dream_or_404(db, dream_id)
    await db.dream_reports.insert_one({
        "_id": f"rep_{uuid.uuid4().hex[:14]}", "dream_id": dream_id,
        "reporter_id": user["user_id"], "reason": body.reason.strip()[:400],
        "kind": "dream", "status": "open", "created_at": _now()})
    await db.dreams.update_one({"_id": dream_id}, {"$inc": {"report_count": 1}})
    return {"ok": True}


@router.delete("/{dream_id}")
async def delete_dream(dream_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    res = await db.dreams.update_one(
        {"_id": dream_id, "user_id": user["user_id"]},
        {"$set": {"status": "deleted", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "dream_not_found"})
    return {"ok": True}


# ───────────────────────── AI reflection ───────────────────────────
AI_SYSTEM = (
    "You are RadioLife's Dream Reflection guide. You offer gentle, reflective, "
    "symbolic and cultural readings of dreams for entertainment and self-reflection. "
    "You are NOT a doctor or therapist. You must NEVER diagnose any psychiatric or "
    "sleep illness, never state supernatural explanations as verified fact, never "
    "predict death or future events as certainty, never give medical/legal/financial "
    "advice, and never encourage dangerous actions. Use hedged, humble language like "
    "'Some traditions interpret...', 'One possible symbolic reading...', 'You may want "
    "to reflect on...'. Never write 'This definitely means'. If the dream hints at real "
    "distress or self-harm, do NOT diagnose — gently suggest speaking with a licensed "
    "professional or a trusted person. Respond with STRICT JSON only (no markdown), "
    "shape: {\"symbolic_readings\": [str, str, str], \"themes\": [str], "
    "\"questions_to_consider\": [str, str], \"gentle_note\": str}. Keep each string "
    "warm and under 220 characters.")


def _fallback_reflection() -> dict:
    return {
        "symbolic_readings": [
            "Some traditions read dreams as the mind gently processing recent feelings.",
            "One possible symbolic reading is that the imagery reflects something you're weighing.",
        ],
        "themes": ["reflection"],
        "questions_to_consider": [
            "What feeling stayed with you after waking?",
            "Is there anything in waking life this dream might be echoing?"],
        "gentle_note": "This is a reflection for exploration, not a prediction or diagnosis.",
    }


@router.post("/{dream_id}/reflect")
async def ai_reflect(dream_id: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "dream_ai_enabled")
    uid = user["user_id"]
    d = await _dream_or_404(db, dream_id)
    friends = await _friend_ids(db, uid)
    if not _can_view(d, uid, friends):
        raise HTTPException(403, {"code": "not_visible"})

    text = f"{(d.get('title') or '').strip()}\n\n{d.get('description', '')}".strip()
    lower = text.lower()
    distress = any(k in lower for k in _DISTRESS)

    key = os.environ.get("EMERGENT_LLM_KEY")
    reflection = None
    if key:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(api_key=key, session_id=f"dream_{dream_id}",
                           system_message=AI_SYSTEM).with_model("anthropic", "claude-sonnet-4-6")
            raw = await chat.send_message(UserMessage(
                text=f"Reflect on this dream (mood: {d.get('mood') or 'unspecified'}; "
                     f"tags: {', '.join(d.get('tags') or []) or 'none'}):\n\n{text}"))
            s = raw if isinstance(raw, str) else str(raw)
            a, b = s.find("{"), s.rfind("}")
            if a != -1 and b != -1:
                reflection = json.loads(s[a:b + 1])
        except Exception:
            reflection = None
    if not isinstance(reflection, dict) or "symbolic_readings" not in reflection:
        reflection = _fallback_reflection()

    reflection["header"] = AI_HEADER
    reflection["disclaimer"] = DISCLAIMER_GLOBAL
    if distress:
        reflection["safety_note"] = (
            "It sounds like this dream may be tied to something painful. Dreams alone "
            "can't establish a diagnosis — if you're feeling distressed, please consider "
            "talking with a licensed professional or someone you trust.")
    reflection["generated_at"] = _now().isoformat()
    await db.dreams.update_one({"_id": dream_id},
                               {"$set": {"ai_reflection": reflection, "updated_at": _now()}})
    return {"ok": True, "ai_reflection": reflection}


# ───────────────────────── Saved dreams ────────────────────────────
@router.get("/me/saved")
async def my_saved(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    ids: list[str] = []
    async for s in db.dream_saves.find({"user_id": uid}).sort("created_at", -1).limit(60):
        ids.append(s["dream_id"])
    if not ids:
        return {"items": []}
    friends = await _friend_ids(db, uid)
    rows = []
    authors: dict[str, dict] = {}
    async for d in db.dreams.find({"_id": {"$in": ids}, "status": "active"}):
        if _can_view(d, uid, friends):
            rows.append(d)
    aids = [d["user_id"] for d in rows if not d.get("anonymous") or d["user_id"] == uid]
    if aids:
        async for u in db.users.find({"user_id": {"$in": aids}}):
            authors[u["user_id"]] = _user_public(u)
    return {"items": [_dream_public(d, uid, authors.get(d["user_id"])) for d in rows]}


# ───────────────────────── Advisor: serialization ──────────────────
def _advisor_public(a: dict, services: Optional[list] = None,
                    for_self: bool = False) -> dict:
    out = {
        "advisor_id": a["advisor_id"], "display_name": a.get("display_name"),
        "category": a.get("category"),
        "category_label": CATEGORY_LABELS.get(a.get("category")),
        "licensed": a.get("category") in LICENSED_CATEGORIES,
        "bio": a.get("bio"), "languages": a.get("languages") or [],
        "experience_years": a.get("experience_years"),
        "photo_url": a.get("photo_url"),
        "badges": a.get("badges") or {"identity_verified": False,
                                      "spiritual_approved": False,
                                      "professional_license_verified": False},
        "rating": round(float(a.get("rating", 0)), 1), "review_count": int(a.get("review_count", 0)),
        "status": a.get("status"),
    }
    if services is not None:
        out["services"] = services
    if for_self:
        out["credentials"] = a.get("credentials")
    return out


def _service_public(s: dict) -> dict:
    return {"service_id": s["service_id"], "advisor_id": s["advisor_id"],
            "title": s.get("title"), "delivery": s.get("delivery"),
            "price_cents": int(s.get("price_cents", 0)),
            "duration_min": s.get("duration_min"),
            "delivery_hours": s.get("delivery_hours"),
            "description": s.get("description"), "active": bool(s.get("active", True))}


# ───────────────────────── Advisor: marketplace ────────────────────
@router.get("/advisors")
async def list_advisors(request: Request, category: Optional[str] = None,
                        q: Optional[str] = None,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "advisor_marketplace_enabled")
    query: dict = {"status": "approved"}
    if category in ADVISOR_CATEGORIES:
        query["category"] = category
    if q and len(q.strip()) >= 2:
        query["display_name"] = {"$regex": q.strip(), "$options": "i"}
    featured_ids: set = set()
    try:
        from routes.dream_ads import active_featured_advisor_ids
        featured_ids = await active_featured_advisor_ids(db, "advisors")
    except Exception:
        pass
    items = []
    async for a in db.advisor_profiles.find(query).sort("rating", -1).limit(60):
        pub = _advisor_public(a)
        pub["featured"] = a["advisor_id"] in featured_ids
        items.append(pub)
    items.sort(key=lambda x: 0 if x.get("featured") else 1)  # featured first, stable
    return {"items": items, "categories": [
        {"key": c, "label": CATEGORY_LABELS[c], "licensed": c in LICENSED_CATEGORIES}
        for c in ADVISOR_CATEGORIES]}


@router.get("/advisors/me")
async def my_advisor(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await db.advisor_profiles.find_one({"user_id": user["user_id"]})
    if not a:
        return {"advisor": None}
    svcs = [_service_public(s) async for s in
            db.advisor_services.find({"advisor_id": a["advisor_id"]})]
    return {"advisor": _advisor_public(a, services=svcs, for_self=True)}


class AdvisorApplyBody(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=80)
    category: str
    bio: str = Field(..., min_length=10, max_length=1000)
    languages: list[str] = []
    experience_years: Optional[int] = Field(None, ge=0, le=80)
    photo_url: Optional[str] = None
    credentials: Optional[str] = Field(None, max_length=600)


@router.post("/advisors/apply")
async def apply_advisor(body: AdvisorApplyBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "advisor_marketplace_enabled")
    if body.category not in ADVISOR_CATEGORIES:
        raise HTTPException(400, {"code": "bad_category"})
    existing = await db.advisor_profiles.find_one({"user_id": user["user_id"]})
    if existing and existing.get("status") not in ("rejected",):
        raise HTTPException(409, {"code": "already_applied",
                                  "status": existing.get("status")})
    aid = existing["advisor_id"] if existing else f"adv_{uuid.uuid4().hex[:14]}"
    doc = {
        "advisor_id": aid, "user_id": user["user_id"],
        "display_name": body.display_name.strip(), "category": body.category,
        "bio": body.bio.strip(), "languages": body.languages[:6],
        "experience_years": body.experience_years,
        "photo_url": body.photo_url or _user_public(user).get("avatar_url"),
        "credentials": (body.credentials or "").strip() or None,
        "badges": {"identity_verified": False, "spiritual_approved": False,
                   "professional_license_verified": False},
        "rating": 0.0, "review_count": 0, "status": "under_review",
        "created_at": _now(), "updated_at": _now()}
    await db.advisor_profiles.update_one({"advisor_id": aid}, {"$set": doc}, upsert=True)
    return {"ok": True, "advisor": _advisor_public(doc, for_self=True)}


class ServiceBody(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    delivery: str = "written"
    price_cents: int = Field(..., ge=0, le=5_000_000)
    duration_min: int = Field(30, ge=5, le=240)
    delivery_hours: int = Field(24, ge=0, le=336)
    description: Optional[str] = Field(None, max_length=600)
    active: bool = True


async def _my_approved_advisor(db, uid: str) -> dict:
    a = await db.advisor_profiles.find_one({"user_id": uid})
    if not a:
        raise HTTPException(404, {"code": "not_an_advisor"})
    if a.get("status") != "approved":
        raise HTTPException(403, {"code": "advisor_not_approved", "status": a.get("status")})
    return a


@router.post("/advisors/me/services")
async def create_service(body: ServiceBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _my_approved_advisor(db, user["user_id"])
    if body.delivery not in DELIVERY_TYPES:
        raise HTTPException(400, {"code": "bad_delivery"})
    sid = f"advsvc_{uuid.uuid4().hex[:12]}"
    doc = {"service_id": sid, "advisor_id": a["advisor_id"], **body.model_dump(),
           "created_at": _now(), "updated_at": _now()}
    await db.advisor_services.insert_one(dict(doc))
    return {"ok": True, "service": _service_public(doc)}


@router.delete("/advisors/me/services/{service_id}")
async def delete_service(service_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _my_approved_advisor(db, user["user_id"])
    await db.advisor_services.delete_one(
        {"service_id": service_id, "advisor_id": a["advisor_id"]})
    return {"ok": True}


@router.get("/advisors/{advisor_id}")
async def advisor_detail(advisor_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await db.advisor_profiles.find_one({"advisor_id": advisor_id, "status": "approved"})
    if not a:
        raise HTTPException(404, {"code": "advisor_not_found"})
    svcs = [_service_public(s) async for s in
            db.advisor_services.find({"advisor_id": advisor_id, "active": True})]
    reviews = []
    async for r in db.advisor_reviews.find({"advisor_id": advisor_id}
                                           ).sort("created_at", -1).limit(20):
        reviews.append({"user_name": r.get("user_name"), "rating": r.get("rating"),
                        "comment": r.get("comment"), "created_at": _iso(r.get("created_at"))})
    out = _advisor_public(a, services=svcs)
    out["reviews"] = reviews
    out["disclaimer"] = DISCLAIMER_BOOKING if not out["licensed"] else None
    try:  # ad analytics: count a unique profile view against any active promo
        from routes.dream_ads import record_advisor_view
        await record_advisor_view(db, advisor_id, user["user_id"])
    except Exception:
        pass
    return out


# ─────────────── Advisor: public response to a public dream ─────────
class AdvisorResponseBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=1200)


@router.post("/{dream_id}/advisor-response")
async def advisor_respond(dream_id: str, body: AdvisorResponseBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _my_approved_advisor(db, user["user_id"])
    d = await _dream_or_404(db, dream_id)
    if d.get("visibility") != "public":
        raise HTTPException(403, {"code": "public_dreams_only"})
    pub = _user_public(user)
    cid = f"dc_{uuid.uuid4().hex[:16]}"
    await db.dream_comments.insert_one({
        "_id": cid, "dream_id": dream_id, "user_id": user["user_id"],
        "name": a.get("display_name") or pub["name"], "avatar_url": a.get("photo_url"),
        "text": body.text.strip()[:1200], "reaction": None,
        "is_advisor": True, "advisor_id": a["advisor_id"],
        "advisor_category": a.get("category"), "created_at": _now()})
    await db.dreams.update_one({"_id": dream_id},
                               {"$inc": {"comment_count": 1, "advisor_response_count": 1}})
    return {"ok": True, "id": cid}


# ───────────────────────── Paid private readings ───────────────────
class BookingBody(BaseModel):
    advisor_id: str
    service_id: str
    dream_id: Optional[str] = None
    question: Optional[str] = Field(None, max_length=1500)
    origin_url: Optional[str] = None


@router.post("/bookings/checkout")
async def book_reading(body: BookingBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_flag(db, "paid_readings_enabled")
    a = await db.advisor_profiles.find_one(
        {"advisor_id": body.advisor_id, "status": "approved"})
    if not a:
        raise HTTPException(404, {"code": "advisor_not_found"})
    if a.get("category") in LICENSED_CATEGORIES:
        await _require_flag(db, "licensed_professional_services_enabled")
    svc = await db.advisor_services.find_one(
        {"service_id": body.service_id, "advisor_id": body.advisor_id, "active": True})
    if not svc:
        raise HTTPException(404, {"code": "service_not_found"})
    fee = int(svc.get("price_cents", 0))
    bid = f"rb_{uuid.uuid4().hex[:16]}"
    promo_id = None
    try:  # attribute this booking to the advisor's active Featured promotion
        from routes.dream_ads import active_promo_id_for
        promo_id = await active_promo_id_for(db, body.advisor_id, "advisors")
    except Exception:
        promo_id = None
    booking = {
        "_id": bid, "booking_id": bid, "advisor_id": body.advisor_id,
        "advisor_name": a.get("display_name"), "advisor_category": a.get("category"),
        "user_id": user["user_id"], "user_name": _user_public(user)["name"],
        "service_id": body.service_id, "service_title": svc.get("title"),
        "delivery": svc.get("delivery"), "price_cents": fee,
        "dream_id": body.dream_id, "promo_id": promo_id,
        "question": (body.question or "").strip() or None,
        "status": "pending_payment", "payment_status": "pending",
        "session_id": None, "response": None,
        "terms_version": TERMS_VERSION,
        "created_at": _now(), "updated_at": _now()}
    if fee <= 0:
        booking["status"] = "paid"
        booking["payment_status"] = "paid"
        await db.reading_bookings.insert_one(dict(booking))
        return {"ok": True, "booking_id": bid, "status": "paid", "checkout_url": None}
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{a.get('display_name')} — {svc.get('title')}"},
                     "unit_amount": fee}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "dream_reading", "booking_id": bid,
                  "advisor_id": body.advisor_id})
    booking["session_id"] = session.id
    await db.reading_bookings.insert_one(dict(booking))
    return {"ok": True, "booking_id": bid, "status": "pending_payment",
            "checkout_url": session.url, "session_id": session.id}


def _booking_public(b: dict, viewer: str) -> dict:
    return {"booking_id": b["booking_id"], "advisor_id": b.get("advisor_id"),
            "advisor_name": b.get("advisor_name"),
            "advisor_category": b.get("advisor_category"),
            "advisor_category_label": CATEGORY_LABELS.get(b.get("advisor_category")),
            "user_name": b.get("user_name"),
            "service_title": b.get("service_title"), "delivery": b.get("delivery"),
            "price_cents": int(b.get("price_cents", 0)), "dream_id": b.get("dream_id"),
            "question": b.get("question"), "status": b.get("status"),
            "payment_status": b.get("payment_status"),
            "response": b.get("response"),
            "reviewed": bool(b.get("reviewed")),
            "created_at": _iso(b.get("created_at"))}


@router.get("/bookings")
async def my_readings(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    items = [_booking_public(b, uid) async for b in
             db.reading_bookings.find({"user_id": uid}).sort("created_at", -1).limit(50)]
    return {"items": items}


@router.get("/bookings/{booking_id}/status")
async def booking_status(booking_id: str, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    b = await db.reading_bookings.find_one(
        {"booking_id": booking_id, "user_id": user["user_id"]})
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    if b.get("payment_status") != "paid" and b.get("session_id"):
        stripe = _stripe()
        if stripe.api_key:
            try:
                sess = stripe.checkout.Session.retrieve(b["session_id"])
                if sess.get("payment_status") == "paid" or sess.get("status") == "complete":
                    await db.reading_bookings.update_one(
                        {"booking_id": booking_id, "payment_status": {"$ne": "paid"}},
                        {"$set": {"payment_status": "paid", "status": "paid",
                                  "stripe_payment_intent": sess.get("payment_intent"),
                                  "updated_at": _now()}})
                    b = await db.reading_bookings.find_one({"booking_id": booking_id})
            except Exception:
                pass
    return {"status": b.get("status"), "payment_status": b.get("payment_status"),
            "booking": _booking_public(b, user["user_id"])}


class ReviewBody(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=600)


@router.post("/bookings/{booking_id}/review")
async def review_reading(booking_id: str, body: ReviewBody, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    b = await db.reading_bookings.find_one(
        {"booking_id": booking_id, "user_id": user["user_id"]})
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    if b.get("status") != "delivered":
        raise HTTPException(400, {"code": "not_delivered"})
    if b.get("reviewed"):
        raise HTTPException(409, {"code": "already_reviewed"})
    await db.advisor_reviews.insert_one({
        "_id": f"arv_{uuid.uuid4().hex[:14]}", "advisor_id": b["advisor_id"],
        "booking_id": booking_id, "user_id": user["user_id"],
        "user_name": b.get("user_name"), "rating": body.rating,
        "comment": (body.comment or "").strip() or None, "verified": True,
        "created_at": _now()})
    await db.reading_bookings.update_one({"booking_id": booking_id},
                                         {"$set": {"reviewed": True}})
    # recompute advisor rating
    total, count = 0, 0
    async for r in db.advisor_reviews.find({"advisor_id": b["advisor_id"]}):
        total += int(r.get("rating", 0)); count += 1
    if count:
        await db.advisor_profiles.update_one(
            {"advisor_id": b["advisor_id"]},
            {"$set": {"rating": total / count, "review_count": count}})
    return {"ok": True}


# ───────────────────────── Advisor inbox ───────────────────────────
@router.get("/advisor/bookings")
async def advisor_inbox(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _my_approved_advisor(db, user["user_id"])
    items = [_booking_public(b, user["user_id"]) async for b in
             db.reading_bookings.find(
                 {"advisor_id": a["advisor_id"], "payment_status": "paid"}
             ).sort("created_at", -1).limit(60)]
    return {"items": items}


class DeliverBody(BaseModel):
    response_text: str = Field(..., min_length=1, max_length=6000)
    voice_url: Optional[str] = None


@router.post("/advisor/bookings/{booking_id}/deliver")
async def deliver_reading(booking_id: str, body: DeliverBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _my_approved_advisor(db, user["user_id"])
    b = await db.reading_bookings.find_one(
        {"booking_id": booking_id, "advisor_id": a["advisor_id"]})
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    if b.get("payment_status") != "paid":
        raise HTTPException(400, {"code": "not_paid"})
    await db.reading_bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {"status": "delivered", "updated_at": _now(),
                  "response": {"text": body.response_text.strip(),
                               "voice_url": body.voice_url,
                               "delivered_at": _now().isoformat()}}})
    # Settle advisor payout (idempotent, never blocks delivery).
    try:
        from routes.dream_payouts import settle_booking_payout
        await settle_booking_payout(db, await db.reading_bookings.find_one(
            {"booking_id": booking_id}))
    except Exception:
        pass
    return {"ok": True}


# ─────────────── Single dream detail (declared last so the literal ───
# /advisors, /bookings, /me/* GET routes above win over /{dream_id}) ──
@router.get("/{dream_id}")
async def dream_detail(dream_id: str, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    d = await _dream_or_404(db, dream_id)
    friends = await _friend_ids(db, uid)
    if not _can_view(d, uid, friends):
        raise HTTPException(403, {"code": "not_visible"})
    author = None
    if not d.get("anonymous") or d["user_id"] == uid:
        au = await db.users.find_one({"user_id": d["user_id"]})
        author = _user_public(au) if au else None
    comments: list[dict] = []
    async for c in db.dream_comments.find({"dream_id": dream_id}).sort("created_at", 1).limit(200):
        comments.append({"id": c["_id"], "user_id": c["user_id"], "name": c.get("name"),
                         "avatar_url": c.get("avatar_url"), "text": c.get("text"),
                         "reaction": c.get("reaction"), "is_advisor": bool(c.get("is_advisor")),
                         "advisor_category": c.get("advisor_category"),
                         "advisor_category_label": (CATEGORY_LABELS.get(c.get("advisor_category"))
                                                    if c.get("is_advisor") else None),
                         "created_at": _iso(c.get("created_at"))})
    my_similar = await db.dream_similar.find_one({"dream_id": dream_id, "user_id": uid})
    my_reacts = [r["kind"] async for r in
                 db.dream_reactions.find({"dream_id": dream_id, "user_id": uid})]
    saved = await db.dream_saves.find_one({"_id": f"{dream_id}:{uid}"})
    out = _dream_public(d, uid, author, detail=True)
    out["comments"] = comments
    out["my_similar"] = bool(my_similar)
    out["my_reactions"] = my_reacts
    out["saved"] = bool(saved)
    return out


# ═══════════════════════════ ADMIN ═════════════════════════════════
@admin_router.get("/flags")
async def admin_get_flags(request: Request, user: dict = Depends(require_admin)):
    db = request.app.state.db
    f = await _flags(db)
    return {k: v for k, v in f.items() if k != "_id"}


class FlagsBody(BaseModel):
    dream_sharing_enabled: Optional[bool] = None
    dream_ai_enabled: Optional[bool] = None
    advisor_marketplace_enabled: Optional[bool] = None
    paid_readings_enabled: Optional[bool] = None
    licensed_professional_services_enabled: Optional[bool] = None


@admin_router.patch("/flags")
async def admin_set_flags(body: FlagsBody, request: Request,
                          user: dict = Depends(require_admin)):
    db = request.app.state.db
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        await db.guidance_flags.update_one({"_id": "guidance_flags"},
                                           {"$set": patch}, upsert=True)
    f = await _flags(db)
    return {k: v for k, v in f.items() if k != "_id"}


@admin_router.get("/applications")
async def admin_applications(request: Request, status: Optional[str] = None,
                             user: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if status:
        q["status"] = status
    items = []
    async for a in db.advisor_profiles.find(q).sort("created_at", -1).limit(100):
        row = _advisor_public(a, for_self=True)
        row["user_id"] = a.get("user_id")
        row["credentials"] = a.get("credentials")
        items.append(row)
    return {"items": items}


class ApproveBody(BaseModel):
    identity_verified: bool = True
    spiritual_approved: bool = False
    professional_license_verified: bool = False


@admin_router.post("/advisors/{advisor_id}/approve")
async def admin_approve(advisor_id: str, body: ApproveBody, request: Request,
                        user: dict = Depends(require_admin)):
    db = request.app.state.db
    a = await db.advisor_profiles.find_one({"advisor_id": advisor_id})
    if not a:
        raise HTTPException(404, {"code": "advisor_not_found"})
    # Guardrail: only licensed categories may carry the professional license badge.
    lic = a.get("category") in LICENSED_CATEGORIES
    badges = {"identity_verified": bool(body.identity_verified),
              "spiritual_approved": bool(body.spiritual_approved),
              "professional_license_verified": bool(body.professional_license_verified) and lic}
    await db.advisor_profiles.update_one(
        {"advisor_id": advisor_id},
        {"$set": {"status": "approved", "badges": badges, "updated_at": _now()}})
    return {"ok": True, "badges": badges,
            "note": None if lic else "professional_license_verified ignored (non-licensed category)"}


class RejectBody(BaseModel):
    note: Optional[str] = Field(None, max_length=400)


@admin_router.post("/advisors/{advisor_id}/reject")
async def admin_reject(advisor_id: str, body: RejectBody, request: Request,
                       user: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.advisor_profiles.update_one(
        {"advisor_id": advisor_id},
        {"$set": {"status": "rejected", "reject_note": body.note, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "advisor_not_found"})
    return {"ok": True}


@admin_router.post("/advisors/{advisor_id}/suspend")
async def admin_suspend(advisor_id: str, request: Request,
                        user: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.advisor_profiles.update_one(
        {"advisor_id": advisor_id},
        {"$set": {"status": "suspended", "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "advisor_not_found"})
    return {"ok": True}


@admin_router.get("/reports")
async def admin_reports(request: Request, status: str = "open",
                        user: dict = Depends(require_admin)):
    db = request.app.state.db
    items = []
    async for r in db.dream_reports.find({"status": status}
                                         ).sort("created_at", -1).limit(100):
        d = await db.dreams.find_one({"_id": r["dream_id"]})
        items.append({"report_id": r["_id"], "dream_id": r["dream_id"],
                      "reason": r.get("reason"), "reporter_id": r.get("reporter_id"),
                      "created_at": _iso(r.get("created_at")),
                      "dream": ({"title": d.get("title"),
                                 "description": d.get("description"),
                                 "owner_user_id": d.get("user_id"),  # admin can identify anon owner
                                 "anonymous": d.get("anonymous"),
                                 "status": d.get("status")} if d else None)})
    return {"items": items}


@admin_router.post("/dreams/{dream_id}/remove")
async def admin_remove_dream(dream_id: str, request: Request,
                             user: dict = Depends(require_admin)):
    db = request.app.state.db
    await db.dreams.update_one({"_id": dream_id},
                               {"$set": {"status": "removed", "updated_at": _now()}})
    await db.dream_reports.update_many({"dream_id": dream_id, "status": "open"},
                                       {"$set": {"status": "actioned"}})
    return {"ok": True}


@admin_router.post("/reports/{report_id}/dismiss")
async def admin_dismiss_report(report_id: str, request: Request,
                               user: dict = Depends(require_admin)):
    db = request.app.state.db
    await db.dream_reports.update_one({"_id": report_id},
                                      {"$set": {"status": "dismissed"}})
    return {"ok": True}


__all__ = ["router", "admin_router", "ensure_dreams_indexes", "seed_dreams_demo"]


# ───────────────────────── Demo seed ───────────────────────────────
_DEMO_ADVISORS = [
    {"email": "stella.moon@bigfm.dubai", "name": "Stella Moon",
     "category": "dream_interpreter",
     "bio": "Dream interpreter blending Jungian symbolism with gentle, grounded reflection. "
            "I help you explore what recurring images might be echoing in your waking life.",
     "languages": ["English", "Arabic"], "experience_years": 9,
     "badges": {"identity_verified": True, "spiritual_approved": True,
                "professional_license_verified": False},
     "rating": 4.8, "review_count": 132,
     "services": [
         {"title": "30-min Written Dream Reading", "delivery": "written",
          "price_cents": 2900, "duration_min": 30, "delivery_hours": 24,
          "description": "Share your dream + questions; I'll reflect back symbolic themes within 24h."},
         {"title": "Live Video Dream Session", "delivery": "live_video",
          "price_cents": 7900, "duration_min": 45, "delivery_hours": 0,
          "description": "A private 45-min live conversation exploring your dream."}]},
    {"email": "orion.reads@bigfm.dubai", "name": "Orion",
     "category": "tarot_reader",
     "bio": "Tarot reader focused on reflection and decision-clarity — never fear or guarantees. "
            "Traditional symbolism paired with open questions for you to consider.",
     "languages": ["English"], "experience_years": 6,
     "badges": {"identity_verified": True, "spiritual_approved": True,
                "professional_license_verified": False},
     "rating": 4.6, "review_count": 88,
     "services": [
         {"title": "3-Card Reflection Reading", "delivery": "written",
          "price_cents": 1900, "duration_min": 20, "delivery_hours": 12,
          "description": "A past-present-future style spread with a reflective write-up."}]},
    {"email": "layla.stars@bigfm.dubai", "name": "Layla Nour",
     "category": "astrologer",
     "bio": "Astrologer offering entertainment-first chart reflections and theme readings. "
            "For self-exploration, never guaranteed prediction.",
     "languages": ["English", "Hindi"], "experience_years": 12,
     "badges": {"identity_verified": True, "spiritual_approved": True,
                "professional_license_verified": False},
     "rating": 4.9, "review_count": 210,
     "services": [
         {"title": "Birth Chart Themes (Written)", "delivery": "written",
          "price_cents": 3900, "duration_min": 40, "delivery_hours": 48,
          "description": "A written reflection on your chart's themes and seasons."}]},
    {"email": "dr.sana.sleep@bigfm.dubai", "name": "Dr. Sana Rahman",
     "category": "licensed_sleep",
     "bio": "Licensed sleep professional. I offer general, educational guidance on sleep and "
            "dreaming. Public answers are educational only — not a diagnosis or treatment.",
     "languages": ["English", "Arabic"], "experience_years": 15,
     "credentials": "Sleep Medicine — DHA License (demo)",
     "badges": {"identity_verified": True, "spiritual_approved": False,
                "professional_license_verified": True},
     "rating": 4.7, "review_count": 54,
     "services": [
         {"title": "Sleep & Dreams Education Call", "delivery": "live_audio",
          "price_cents": 5900, "duration_min": 30, "delivery_hours": 0,
          "description": "A general educational call about sleep hygiene and dreaming. Not medical treatment."}]},
]

_DEMO_DREAMS = [
    {"advisor_email": None, "title": "Endless staircase",
     "description": "I kept climbing a staircase that never ended. Every landing looked the same "
                    "and I felt calm but curious, like I was meant to keep going.",
     "mood": "Strange", "tags": ["Recurring", "Travel"], "visibility": "public",
     "anonymous": False, "similar": 41},
    {"advisor_email": None, "title": "",
     "description": "I was flying over my childhood neighbourhood at sunset. It felt peaceful and "
                    "I could see everyone I love waving up at me.",
     "mood": "Peaceful", "tags": ["Flying", "Family"], "visibility": "public",
     "anonymous": True, "similar": 27},
    {"advisor_email": None, "title": "The tide came in",
     "description": "Water slowly filled a room I was in but I wasn't scared. I just floated and "
                    "watched the light move on the ceiling.",
     "mood": "Confusing", "tags": ["Water"], "visibility": "public",
     "anonymous": False, "similar": 63},
]


async def seed_dreams_demo(db, hash_password) -> dict:
    """Idempotent: demo advisors (+ backing login users), services, public dreams."""
    import uuid as _uuid
    now = _now()
    created_advisors = 0
    advisor_by_email: dict[str, dict] = {}
    for spec in _DEMO_ADVISORS:
        u = await db.users.find_one({"email": spec["email"]})
        if not u:
            uid = f"user_{_uuid.uuid4().hex[:16]}"
            await db.users.insert_one({
                "user_id": uid, "email": spec["email"], "name": spec["name"],
                "picture": None, "auth_provider": "email",
                "password_hash": hash_password(os.environ.get("SEED_ADVISOR_PW", "Advisor123!")),
                "role": "user", "onboarding_complete": True,
                "city": "Dubai", "created_at": now, "last_login_at": None})
            u = await db.users.find_one({"user_id": uid})
        uid = u["user_id"]
        adv = await db.advisor_profiles.find_one({"user_id": uid})
        if not adv:
            aid = f"adv_{_uuid.uuid4().hex[:14]}"
            adv = {"advisor_id": aid, "user_id": uid, "display_name": spec["name"],
                   "category": spec["category"], "bio": spec["bio"],
                   "languages": spec["languages"], "experience_years": spec["experience_years"],
                   "photo_url": None, "credentials": spec.get("credentials"),
                   "badges": spec["badges"], "rating": spec["rating"],
                   "review_count": spec["review_count"], "status": "approved",
                   "created_at": now, "updated_at": now}
            await db.advisor_profiles.insert_one(dict(adv))
            for svc in spec["services"]:
                await db.advisor_services.insert_one({
                    "service_id": f"advsvc_{_uuid.uuid4().hex[:12]}",
                    "advisor_id": aid, **svc, "active": True,
                    "created_at": now, "updated_at": now})
            created_advisors += 1
        advisor_by_email[spec["email"]] = {"user_id": uid, "advisor_id": adv["advisor_id"]}

    # Public demo dreams (authored by the first spiritual advisor account so the
    # feed isn't empty; anonymous ones hide identity to users, not to Admin).
    author = advisor_by_email.get(_DEMO_ADVISORS[0]["email"], {})
    author_uid = author.get("user_id")
    created_dreams = 0
    if author_uid:
        for spec in _DEMO_DREAMS:
            marker = spec["description"][:40]
            if await db.dreams.find_one({"user_id": author_uid,
                                         "description": {"$regex": f"^{marker[:20]}"}}):
                continue
            did = f"dm_{_uuid.uuid4().hex[:16]}"
            await db.dreams.insert_one({
                "_id": did, "user_id": author_uid,
                "title": spec["title"] or None, "description": spec["description"],
                "mood": spec["mood"], "tags": spec["tags"],
                "dream_date": None, "visibility": spec["visibility"],
                "anonymous": spec["anonymous"], "similar_count": spec["similar"],
                "comment_count": 0, "advisor_response_count": 0, "reaction_counts": {},
                "ai_reflection": None, "status": "active", "report_count": 0,
                "created_at": now, "updated_at": now})
            created_dreams += 1
    return {"advisors": created_advisors, "dreams": created_dreams}
