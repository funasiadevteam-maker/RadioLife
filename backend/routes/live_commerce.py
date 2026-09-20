"""FUUSIC Social V2 — Phase 3: FUUSIC LIVE (video livestream commerce).

A business (or any host) goes live, pins products/offers, and viewers buy them
mid-stream via Stripe checkout — all on the shared /api/social contract.

Video transport reuses `services.livekit_client` (mock-mode by default in
preview; real A/V needs LIVEKIT_* creds + a native build). The commerce,
pinned-product, presence and live-chat layers work fully without live video.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from core.origins import resolve_origin
from routes.social_v2 import _user_public, _users_map
from services import livekit_client

router = APIRouter(prefix="/api/social/liveshows", tags=["live_commerce"])

VIEWER_ACTIVE_SEC = 45


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _stripe():
    import stripe
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")
    return stripe


async def _llm_json(system: str, prompt: str, session: str) -> Optional[dict]:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id=session,
                       system_message=system).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=prompt))
        s = raw if isinstance(raw, str) else str(raw)
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b != -1:
            return _json.loads(s[a:b + 1])
    except Exception:
        return None
    return None


def _can_manage(show: dict, uid: str) -> bool:
    return show.get("host_id") == uid or uid in (show.get("cohost_ids") or [])


async def ensure_live_commerce_indexes(db) -> None:
    await db.live_shows.create_index([("status", 1), ("started_at", -1)],
                                     name="ls_status_time")
    await db.live_shows.create_index("host_id", name="ls_host")
    await db.live_show_messages.create_index(
        [("show_id", 1), ("created_at", 1)], name="lsm_time")
    await db.live_show_viewers.create_index(
        [("show_id", 1), ("user_id", 1)], unique=True, name="lsv_uniq")
    await db.live_orders.create_index([("show_id", 1), ("created_at", -1)],
                                      name="lo_time")
    await db.live_clips.create_index([("show_id", 1), ("created_at", -1)],
                                     name="lc_show_time")
    await db.live_clips.create_index([("created_at", -1)], name="lc_time")


# ─────────────────────────── Serialization ─────────────────────────
async def _viewer_count(db, show_id: str) -> int:
    since = _now() - timedelta(seconds=VIEWER_ACTIVE_SEC)
    return await db.live_show_viewers.count_documents(
        {"show_id": show_id, "last_seen": {"$gte": since}})


def _show_public(s: dict, host: Optional[dict], viewers: int,
                 viewer: str, cohosts: Optional[list] = None) -> dict:
    return {
        "show_id": s["_id"], "host": host, "is_host": s.get("host_id") == viewer,
        "is_cohost": viewer in (s.get("cohost_ids") or []),
        "can_manage": _can_manage(s, viewer), "cohosts": cohosts or [],
        "business_name": s.get("business_name"), "title": s.get("title"),
        "description": s.get("description"), "cover_url": s.get("cover_url"),
        "status": s.get("status"), "viewer_count": viewers,
        "pinned_products": s.get("pinned_products") or [],
        "started_at": _iso(s.get("started_at")),
        "created_at": _iso(s.get("created_at")),
    }


# ─────────────────────────── Show lifecycle ────────────────────────
class ShowBody(BaseModel):
    title: str = Field(..., min_length=2, max_length=120)
    description: str = Field("", max_length=500)
    business_name: str = Field("", max_length=120)
    cover_url: Optional[str] = None


@router.get("")
async def list_shows(request: Request, status: str = "live",
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    q = {"status": status} if status in ("live", "ended", "scheduled") else {}
    rows: list[dict] = []
    hids: set[str] = set()
    async for s in db.live_shows.find(q).sort("started_at", -1).limit(40):
        rows.append(s)
        hids.add(s["host_id"])
    hosts = await _users_map(db, list(hids))
    out = []
    for s in rows:
        vc = await _viewer_count(db, s["_id"])
        out.append(_show_public(s, hosts.get(s["host_id"]), vc, user["user_id"]))
    return {"items": out, "mode": livekit_client.status()["mode"]}


@router.post("")
async def create_show(body: ShowBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    biz = body.business_name.strip()
    if not biz:
        u = await db.users.find_one({"user_id": uid}, {"name": 1, "_id": 0})
        biz = (u or {}).get("name") or "FUUSIC Live"
    sid = f"ls_{uuid.uuid4().hex[:16]}"
    room = f"liveshow_{sid}"
    doc = {"_id": sid, "host_id": uid, "business_name": biz,
           "title": body.title.strip(), "description": body.description.strip(),
           "cover_url": body.cover_url, "status": "live", "room_name": room,
           "pinned_products": [], "created_at": _now(), "started_at": _now(),
           "ended_at": None}
    await db.live_shows.insert_one(doc)
    host = _user_public(await db.users.find_one({"user_id": uid}))
    return {**_show_public(doc, host, 1, uid),
            "join_token": _token(room, uid, "host"),
            "livekit_url": livekit_client.livekit_url(),
            "mode": livekit_client.status()["mode"]}


def _token(room: str, identity: str, role: str) -> Optional[str]:
    try:
        return livekit_client.mint_room_token(
            room_name=room, identity=identity, role=role,
            permissions={"can_publish": role == "host",
                         "can_publish_video": role == "host",
                         "can_subscribe": True})
    except Exception:
        return None


async def _show_or_404(db, sid: str) -> dict:
    s = await db.live_shows.find_one({"_id": sid})
    if not s:
        raise HTTPException(404, {"code": "show_not_found"})
    return s


@router.get("/{sid}")
async def show_detail(sid: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    uid = user["user_id"]
    manage = _can_manage(s, uid)
    # Mark viewer presence (host counts too).
    await db.live_show_viewers.update_one(
        {"show_id": sid, "user_id": uid},
        {"$set": {"show_id": sid, "user_id": uid, "last_seen": _now()}},
        upsert=True)
    vc = await _viewer_count(db, sid)
    host = _user_public(await db.users.find_one({"user_id": s["host_id"]}))
    cohosts = list((await _users_map(db, s.get("cohost_ids") or [])).values())
    return {**_show_public(s, host, vc, uid, cohosts),
            "join_token": _token(s["room_name"], uid, "host" if manage else "guest"),
            "livekit_url": livekit_client.livekit_url(),
            "mode": livekit_client.status()["mode"]}


# ─────────────────────────── Co-hosting ────────────────────────────
class CohostBody(BaseModel):
    user_id: str


@router.post("/{sid}/cohosts")
async def add_cohost(sid: str, body: CohostBody, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if s["host_id"] != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    if body.user_id == s["host_id"]:
        raise HTTPException(400, {"code": "already_host"})
    await db.live_shows.update_one(
        {"_id": sid}, {"$addToSet": {"cohost_ids": body.user_id}})
    await db.social_notifications.insert_one({
        "_id": f"sn_{uuid.uuid4().hex[:14]}", "user_id": body.user_id,
        "type": "cohost_invite", "show_id": sid, "from": user["user_id"],
        "title": s.get("title"), "read": False, "created_at": _now()})
    s = await _show_or_404(db, sid)
    cohosts = list((await _users_map(db, s.get("cohost_ids") or [])).values())
    return {"ok": True, "cohosts": cohosts}


@router.delete("/{sid}/cohosts/{cid}")
async def remove_cohost(sid: str, cid: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if s["host_id"] != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    await db.live_shows.update_one({"_id": sid}, {"$pull": {"cohost_ids": cid}})
    return {"ok": True}


@router.post("/{sid}/heartbeat")
async def heartbeat(sid: str, request: Request,
                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await db.live_show_viewers.update_one(
        {"show_id": sid, "user_id": user["user_id"]},
        {"$set": {"show_id": sid, "user_id": user["user_id"], "last_seen": _now()}},
        upsert=True)
    return {"viewer_count": await _viewer_count(db, sid)}


@router.post("/{sid}/end")
async def end_show(sid: str, request: Request,
                   user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if s["host_id"] != user["user_id"]:
        raise HTTPException(403, {"code": "not_host"})
    await db.live_shows.update_one(
        {"_id": sid}, {"$set": {"status": "ended", "ended_at": _now()}})
    return {"ok": True, "status": "ended"}


# ─────────────────────────── Pinned products ───────────────────────
class ProductBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    price_cents: int = Field(..., ge=0, le=100_000_00)
    image_url: Optional[str] = None
    offer: str = Field("", max_length=80)


@router.post("/{sid}/products")
async def pin_product(sid: str, body: ProductBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if not _can_manage(s, user["user_id"]):
        raise HTTPException(403, {"code": "not_host"})
    product = {"product_id": f"prod_{uuid.uuid4().hex[:12]}",
               "title": body.title.strip(), "price_cents": int(body.price_cents),
               "image_url": body.image_url, "offer": body.offer.strip(),
               "pinned_at": _iso(_now())}
    await db.live_shows.update_one(
        {"_id": sid}, {"$push": {"pinned_products": product}})
    return product


@router.delete("/{sid}/products/{pid}")
async def unpin_product(sid: str, pid: str, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if not _can_manage(s, user["user_id"]):
        raise HTTPException(403, {"code": "not_host"})
    await db.live_shows.update_one(
        {"_id": sid}, {"$pull": {"pinned_products": {"product_id": pid}}})
    return {"ok": True}


# ─────────────────── AI highlight / shoppable clips ────────────────
class ClipBody(BaseModel):
    note: str = Field("", max_length=200)


@router.post("/{sid}/clips")
async def create_clip(sid: str, body: ClipBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    if not _can_manage(s, user["user_id"]):
        raise HTTPException(403, {"code": "not_host"})
    started = s.get("started_at") or s.get("created_at") or _now()
    if isinstance(started, datetime) and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    offset = max(0, int((_now() - started).total_seconds()))
    products = list(s.get("pinned_products") or [])
    prod_titles = ", ".join(p.get("title") for p in products[:5]) or "no products"
    ai = await _llm_json(
        "You write SHORT, punchy titles and captions for a shoppable live-shopping "
        "highlight clip. Return ONLY JSON: {\"title\": str (<=8 words), "
        "\"caption\": str (<=140 chars)}.",
        f"Live show: '{s.get('title')}' by {s.get('business_name')}. "
        f"Host note: '{body.note or 'a great moment'}'. Featured products: {prod_titles}.",
        f"clip_{sid}_{uuid.uuid4().hex[:6]}")
    title = (ai or {}).get("title") or (body.note.strip()[:60] or "Live highlight ✨")
    caption = (ai or {}).get("caption") or f"A highlight from {s.get('business_name')}'s live show."
    clip_id = f"clip_{uuid.uuid4().hex[:14]}"
    doc = {"_id": clip_id, "show_id": sid, "created_by": user["user_id"],
           "title": title, "caption": caption, "offset_sec": offset,
           "products": products, "business_name": s.get("business_name"),
           "created_at": _now()}
    await db.live_clips.insert_one(doc)
    return _clip_public(doc)


def _clip_public(c: dict) -> dict:
    return {"clip_id": c["_id"], "show_id": c.get("show_id"),
            "title": c.get("title"), "caption": c.get("caption"),
            "offset_sec": c.get("offset_sec"), "products": c.get("products") or [],
            "business_name": c.get("business_name"),
            "created_at": _iso(c.get("created_at"))}


@router.get("/{sid}/clips")
async def list_clips(sid: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = []
    async for c in db.live_clips.find({"show_id": sid}).sort("created_at", -1).limit(30):
        rows.append(_clip_public(c))
    return {"items": rows}


@router.get("/clips/feed")
async def clips_feed(request: Request, user: dict = Depends(current_user)):
    """Global shoppable-clip discovery feed (newest across all shows)."""
    db = request.app.state.db
    rows = []
    async for c in db.live_clips.find({}).sort("created_at", -1).limit(30):
        rows.append(_clip_public(c))
    return {"items": rows}


async def _create_checkout(request: Request, seller: str, product: dict,
                           metadata: dict, origin_url: Optional[str]) -> dict:
    amount = int(product.get("price_cents") or 0)
    if amount <= 0:
        return {"ok": True, "status": "free", "checkout_url": None}
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = resolve_origin(request, origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{seller} — {product.get('title')}"},
                     "unit_amount": amount}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel", metadata=metadata)
    return {"ok": True, "status": "pending", "checkout_url": session.url,
            "session_id": session.id}


class ClipCheckoutBody(BaseModel):
    product_id: str
    origin_url: Optional[str] = None


@router.post("/clips/{clip_id}/checkout")
async def clip_checkout(clip_id: str, body: ClipCheckoutBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.live_clips.find_one({"_id": clip_id})
    if not c:
        raise HTTPException(404, {"code": "clip_not_found"})
    product = next((p for p in (c.get("products") or [])
                    if p.get("product_id") == body.product_id), None)
    if not product:
        raise HTTPException(404, {"code": "product_not_found"})
    oid = f"lo_{uuid.uuid4().hex[:16]}"
    res = await _create_checkout(
        request, c.get("business_name") or "FUUSIC", product,
        {"kind": "clip_purchase", "order_id": oid, "clip_id": clip_id,
         "product_id": body.product_id}, body.origin_url)
    await db.live_orders.insert_one(
        {"_id": oid, "clip_id": clip_id, "show_id": c.get("show_id"),
         "product_id": body.product_id, "user_id": user["user_id"],
         "amount_cents": int(product.get("price_cents") or 0),
         "session_id": res.get("session_id"),
         "status": res.get("status"), "created_at": _now()})
    return {**res, "order_id": oid}


# ─────────────────────────── Live chat ─────────────────────────────
class ChatBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)


@router.get("/{sid}/messages")
async def get_messages(sid: str, request: Request, after: Optional[str] = None,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"show_id": sid}
    if after:
        try:
            q["created_at"] = {"$gt": datetime.fromisoformat(after.replace("Z", "+00:00"))}
        except ValueError:
            pass
    rows: list[dict] = []
    ids: set[str] = set()
    async for m in db.live_show_messages.find(q).sort("created_at", 1).limit(100):
        rows.append(m)
        ids.add(m["user_id"])
    authors = await _users_map(db, list(ids))
    return {"items": [{"id": m["_id"], "text": m.get("text"),
                       "author": authors.get(m["user_id"]),
                       "created_at": _iso(m.get("created_at"))} for m in rows]}


@router.post("/{sid}/messages")
async def post_message(sid: str, body: ChatBody, request: Request,
                       user: dict = Depends(current_user)):
    db = request.app.state.db
    await _show_or_404(db, sid)
    mid = f"lsm_{uuid.uuid4().hex[:14]}"
    now = _now()
    await db.live_show_messages.insert_one(
        {"_id": mid, "show_id": sid, "user_id": user["user_id"],
         "text": body.text.strip(), "created_at": now})
    author = _user_public(await db.users.find_one({"user_id": user["user_id"]}))
    return {"id": mid, "text": body.text.strip(), "author": author,
            "created_at": _iso(now)}


# ─────────────────────────── Live checkout ─────────────────────────
class CheckoutBody(BaseModel):
    product_id: str
    origin_url: Optional[str] = None


@router.post("/{sid}/checkout")
async def live_checkout(sid: str, body: CheckoutBody, request: Request,
                        user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _show_or_404(db, sid)
    product = next((p for p in (s.get("pinned_products") or [])
                    if p.get("product_id") == body.product_id), None)
    if not product:
        raise HTTPException(404, {"code": "product_not_found"})
    amount = int(product.get("price_cents") or 0)
    oid = f"lo_{uuid.uuid4().hex[:16]}"
    order = {"_id": oid, "show_id": sid, "product_id": body.product_id,
             "product_title": product.get("title"), "user_id": user["user_id"],
             "amount_cents": amount, "session_id": None,
             "status": "pending", "created_at": _now()}
    if amount <= 0:
        order["status"] = "free"
        await db.live_orders.insert_one(order)
        return {"ok": True, "order_id": oid, "status": "free", "checkout_url": None}
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "usd",
                     "product_data": {"name": f"{s.get('business_name')} — {product.get('title')}"},
                     "unit_amount": amount}, "quantity": 1}],
        success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin}/payment/cancel",
        metadata={"kind": "live_show_purchase", "order_id": oid,
                  "show_id": sid, "product_id": body.product_id})
    order["session_id"] = session.id
    await db.live_orders.insert_one(order)
    return {"ok": True, "order_id": oid, "status": "pending",
            "checkout_url": session.url, "session_id": session.id}


__all__ = ["router", "ensure_live_commerce_indexes"]
