"""FUUSIC Social V2 — Phase 4/5.

  • Group Carts      — a shared cart friends fill together, then one Stripe
                       checkout for the whole basket ("Shop Together").
  • AI Discovery     — people you may know (friends-of-friends, AI-annotated
                       reasons), suggested live shows, trending moments/clips.
  • Translation      — on-demand LLM translation of any caption/comment/chat
                       with a per-language cache.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from core.origins import resolve_origin
from routes.social_v2 import _friend_ids, _user_public, _users_map

router = APIRouter(prefix="/api/social", tags=["social_discovery"])

LANGS = [
    {"code": "en", "label": "English"}, {"code": "hi", "label": "हिन्दी"},
    {"code": "ar", "label": "العربية"}, {"code": "ur", "label": "اردو"},
    {"code": "es", "label": "Español"}, {"code": "fr", "label": "Français"},
    {"code": "ta", "label": "தமிழ்"}, {"code": "ml", "label": "മലയാളം"},
]
LANG_LABELS = {l["code"]: l["label"] for l in LANGS}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _stripe():
    import stripe
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")
    return stripe


async def _llm_text(system: str, prompt: str, session: str) -> Optional[str]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=prompt))
        return raw if isinstance(raw, str) else str(raw)
    except Exception:
        return None


async def ensure_phase45_indexes(db) -> None:
    await db.group_carts.create_index([("members", 1), ("created_at", -1)],
                                      name="gc_members")
    await db.group_carts.create_index("owner_id", name="gc_owner")
    await db.translation_cache.create_index("key", unique=True, name="tc_key")


# ═══════════════════════════ Group Carts ═══════════════════════════
class CartBody(BaseModel):
    name: str = Field("Group cart", max_length=100)
    members: list[str] = Field(default_factory=list)


class CartItemBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    price_cents: int = Field(..., ge=0, le=100_000_00)
    image_url: Optional[str] = None
    qty: int = Field(1, ge=1, le=99)


def _cart_public(c: dict, members: list[dict], viewer: str) -> dict:
    items = c.get("items") or []
    total = sum(int(i.get("price_cents") or 0) * int(i.get("qty") or 1) for i in items)
    return {"cart_id": c["_id"], "name": c.get("name"), "owner_id": c.get("owner_id"),
            "is_owner": c.get("owner_id") == viewer, "members": members,
            "items": items, "item_count": len(items), "total_cents": total,
            "status": c.get("status"), "created_at": _iso(c.get("created_at"))}


@router.post("/carts")
async def create_cart(body: CartBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)
    members = list({uid, *[m for m in body.members if m in friends]})
    cid = f"cart_{uuid.uuid4().hex[:16]}"
    doc = {"_id": cid, "owner_id": uid, "name": body.name.strip() or "Group cart",
           "members": members, "items": [], "status": "open", "created_at": _now()}
    await db.group_carts.insert_one(doc)
    for m in members:
        if m != uid:
            await db.social_notifications.insert_one({
                "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": m, "type": "cart_invite",
                "cart_id": cid, "from": uid, "title": doc["name"], "read": False,
                "created_at": _now()})
    mem = list((await _users_map(db, members)).values())
    return _cart_public(doc, mem, uid)


@router.get("/carts")
async def list_carts(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    rows, ids = [], set()
    async for c in db.group_carts.find(
            {"members": uid, "status": "open"}).sort("created_at", -1).limit(30):
        rows.append(c)
        ids.update(c.get("members") or [])
    umap = await _users_map(db, list(ids))
    return {"items": [_cart_public(c, [umap[m] for m in (c.get("members") or []) if m in umap], uid) for c in rows]}


async def _cart_or_404(db, cid: str, uid: str) -> dict:
    c = await db.group_carts.find_one({"_id": cid})
    if not c:
        raise HTTPException(404, {"code": "cart_not_found"})
    if uid not in (c.get("members") or []):
        raise HTTPException(403, {"code": "not_a_member"})
    return c


@router.get("/carts/{cid}")
async def get_cart(cid: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _cart_or_404(db, cid, user["user_id"])
    mem = list((await _users_map(db, c.get("members") or [])).values())
    return _cart_public(c, mem, user["user_id"])


@router.post("/carts/{cid}/items")
async def add_cart_item(cid: str, body: CartItemBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _cart_or_404(db, cid, user["user_id"])
    item = {"item_id": f"ci_{uuid.uuid4().hex[:12]}", "title": body.title.strip(),
            "price_cents": int(body.price_cents), "image_url": body.image_url,
            "qty": int(body.qty), "added_by": user["user_id"],
            "added_by_name": _user_public(await db.users.find_one({"user_id": user["user_id"]})).get("name")}
    await db.group_carts.update_one({"_id": cid}, {"$push": {"items": item}})
    c = await db.group_carts.find_one({"_id": cid})
    mem = list((await _users_map(db, c.get("members") or [])).values())
    return _cart_public(c, mem, user["user_id"])


@router.delete("/carts/{cid}/items/{item_id}")
async def remove_cart_item(cid: str, item_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    await _cart_or_404(db, cid, user["user_id"])
    await db.group_carts.update_one({"_id": cid}, {"$pull": {"items": {"item_id": item_id}}})
    c = await db.group_carts.find_one({"_id": cid})
    mem = list((await _users_map(db, c.get("members") or [])).values())
    return _cart_public(c, mem, user["user_id"])


class CartCheckoutBody(BaseModel):
    origin_url: Optional[str] = None


@router.post("/carts/{cid}/checkout")
async def checkout_cart(cid: str, body: CartCheckoutBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await _cart_or_404(db, cid, user["user_id"])
    items = c.get("items") or []
    total = sum(int(i.get("price_cents") or 0) * int(i.get("qty") or 1) for i in items)
    if not items or total <= 0:
        raise HTTPException(400, {"code": "empty_cart"})
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    line_items = [{"price_data": {"currency": "usd",
                   "product_data": {"name": i.get("title")},
                   "unit_amount": int(i.get("price_cents") or 0)},
                   "quantity": int(i.get("qty") or 1)} for i in items]
    session = stripe.checkout.Session.create(
        mode="payment", line_items=line_items,
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "group_cart", "cart_id": cid, "by": user["user_id"]})
    return {"ok": True, "checkout_url": session.url, "session_id": session.id,
            "total_cents": total}


# ═══════════════════════════ AI Discovery ══════════════════════════
@router.get("/discover")
async def discover(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    friends = await _friend_ids(db, uid)

    # Pending outgoing requests to exclude.
    pending: set[str] = set()
    async for f in db.social_friendships.find(
            {"status": "pending", "$or": [{"user_a": uid}, {"user_b": uid}]}):
        pending.add(f["user_b"] if f["user_a"] == uid else f["user_a"])

    # Friends-of-friends → mutual-count ranked candidates.
    mutual: dict[str, int] = {}
    for f in list(friends)[:40]:
        async for ff in db.social_friendships.find(
                {"status": "accepted", "$or": [{"user_a": f}, {"user_b": f}]}):
            other = ff["user_b"] if ff["user_a"] == f else ff["user_a"]
            if other == uid or other in friends or other in pending:
                continue
            mutual[other] = mutual.get(other, 0) + 1
    ranked = sorted(mutual, key=lambda k: mutual[k], reverse=True)[:8]

    # Fallback: recently-active public posters if graph is sparse.
    if len(ranked) < 4:
        async for m in db.social_moments.find(
                {"visibility": "public"}).sort("created_at", -1).limit(30):
            oid = m["user_id"]
            if oid != uid and oid not in friends and oid not in pending and oid not in ranked:
                ranked.append(oid)
            if len(ranked) >= 8:
                break

    umap = await _users_map(db, ranked)
    people = []
    for pid in ranked:
        if pid not in umap:
            continue
        mc = mutual.get(pid, 0)
        reason = f"{mc} mutual friend{'s' if mc != 1 else ''}" if mc else "Active in your city"
        people.append({**umap[pid], "mutual_friends": mc, "reason": reason})

    # AI-annotated reasons (best-effort, single call).
    if people:
        names = "; ".join(f"{p['name']} ({p['mutual_friends']} mutuals)" for p in people[:6])
        ai = await _llm_text(
            "You write ONE short, warm, non-cheesy line (<=90 chars) telling a user why "
            "these people are worth connecting with on a social radio app. No emojis, no lists.",
            f"People suggested: {names}.", f"disc_{uid}")
        headline = (ai or "People you might vibe with").strip().split("\n")[0][:120]
    else:
        headline = "Add a few friends to unlock personalized suggestions."

    # Suggested live shows + trending moments/clips.
    shows = []
    async for s in db.live_shows.find({"status": "live"}).sort("started_at", -1).limit(5):
        host = _user_public(await db.users.find_one({"user_id": s["host_id"]}))
        shows.append({"show_id": s["_id"], "title": s.get("title"),
                      "business_name": s.get("business_name"), "host": host})
    moments = []
    async for m in db.social_moments.find(
            {"visibility": "public"}).sort("like_count", -1).limit(6):
        au = _user_public(await db.users.find_one({"user_id": m["user_id"]}))
        moments.append({"moment_id": m["_id"], "caption": m.get("caption"),
                        "media_url": m.get("media_url"), "media_type": m.get("media_type"),
                        "context": m.get("context"), "author": au,
                        "like_count": int(m.get("like_count") or 0)})
    clips = []
    async for c in db.live_clips.find({}).sort("created_at", -1).limit(6):
        clips.append({"clip_id": c["_id"], "title": c.get("title"),
                      "caption": c.get("caption"), "business_name": c.get("business_name"),
                      "products": c.get("products") or []})
    return {"headline": headline, "people": people, "shows": shows,
            "moments": moments, "clips": clips}


# ═══════════════════════════ Translation ═══════════════════════════
class TranslateBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    target_lang: str = "en"


@router.get("/translate/langs")
async def translate_langs(user: dict = Depends(current_user)):
    return {"langs": LANGS}


@router.post("/translate")
async def translate(body: TranslateBody, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    lang = body.target_lang if body.target_lang in LANG_LABELS else "en"
    key = hashlib.sha1(f"{lang}|{body.text}".encode()).hexdigest()
    cached = await db.translation_cache.find_one({"key": key})
    if cached:
        return {"translated": cached["translated"], "target_lang": lang,
                "label": LANG_LABELS[lang], "cached": True}
    out = await _llm_text(
        f"You are a translator. Translate the user's text into {LANG_LABELS[lang]} "
        f"({lang}). Return ONLY the translation, no quotes, no notes, preserve tone.",
        body.text, f"tr_{key[:10]}")
    translated = (out or body.text).strip()
    await db.translation_cache.update_one(
        {"key": key}, {"$set": {"key": key, "target_lang": lang,
                                "translated": translated, "created_at": _now()}},
        upsert=True)
    return {"translated": translated, "target_lang": lang,
            "label": LANG_LABELS[lang], "cached": False}


__all__ = ["router", "ensure_phase45_indexes"]
