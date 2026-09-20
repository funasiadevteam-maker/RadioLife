"""FUUSIC Social V2 — Phase 3: FUUSIC LIVE (video livestream commerce).

A business (or any host) goes live, pins products/offers, and viewers buy them
mid-stream via Stripe checkout — all on the shared /api/social contract.

Video transport reuses `services.livekit_client` (mock-mode by default in
preview; real A/V needs LIVEKIT_* creds + a native build). The commerce,
pinned-product, presence and live-chat layers work fully without live video.
"""
from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional
from core.origins import resolve_origin
from routes.social_v2 import _user_public, _users_map
from services import livekit_client
from services.object_storage import get_storage

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
    await _ensure_clip_image(db, doc)
    return {**_clip_public(doc),
            "image_url": _clip_image_url(request, clip_id),
            "share_path": f"/api/social/liveshows/clips/{clip_id}/share"}


def _clip_public(c: dict) -> dict:
    return {"clip_id": c["_id"], "show_id": c.get("show_id"),
            "title": c.get("title"), "caption": c.get("caption"),
            "offset_sec": c.get("offset_sec"), "products": c.get("products") or [],
            "business_name": c.get("business_name"),
            "created_at": _iso(c.get("created_at"))}


# ─────────────── Clip Sharing (branded share card + OG) ────────────
_F_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
_F_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
_F_NAR = "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf"


def _base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host") or request.url.netloc)
    return f"{proto}://{host}"


def _clip_image_url(request: Request, clip_id: str) -> str:
    return f"{_base_url(request)}/api/social/liveshows/clips/{clip_id}/image.png"


def _font(path, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size=size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and words:
        lines[-1] = lines[-1].rstrip(".") + "…"
    return lines


def _clean(s: Optional[str]) -> str:
    """Strip emoji/symbols the Liberation fonts can't render (avoids tofu boxes)."""
    import re
    if not s:
        return ""
    s = re.sub(r"[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u27BF\u2B00-\u2BFF"
               r"\uFE0F\u200D\u2022]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _compose_clip_card(clip: dict) -> bytes:
    from PIL import Image, ImageDraw
    W, H = 1200, 630
    img = Image.new("RGB", (W, H))
    c0, c1 = (46, 16, 101), (190, 24, 93)  # violet → rose
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        row = (int(c0[0] * (1 - t) + c1[0] * t), int(c0[1] * (1 - t) + c1[1] * t),
               int(c0[2] * (1 - t) + c1[2] * t))
        for x in range(W):
            px[x, y] = row
    d = ImageDraw.Draw(img)
    gold, white, soft = (251, 191, 36), (255, 255, 255), (245, 224, 235)
    d.text((70, 66), "FUUSIC LIVE  ·  HIGHLIGHT", font=_font(_F_NAR, 28), fill=gold)
    y = 150
    for ln in _wrap(d, _clean(clip.get("title")) or "Live highlight", _font(_F_BOLD, 66), W - 140, 2):
        d.text((70, y), ln, font=_font(_F_BOLD, 66), fill=white)
        y += 78
    y += 6
    for ln in _wrap(d, _clean(clip.get("caption")), _font(_F_REG, 34), W - 140, 2):
        d.text((70, y), ln, font=_font(_F_REG, 34), fill=soft)
        y += 46
    prods = clip.get("products") or []
    if prods:
        cy = 470
        cx = 70
        for p in prods[:3]:
            label = f"{_clean(p.get('title'))}  ${int(p.get('price_cents') or 0) / 100:.0f}"
            tw = d.textlength(label, font=_font(_F_BOLD, 26))
            d.rounded_rectangle([cx, cy, cx + tw + 40, cy + 52], radius=26,
                                fill=(255, 255, 255, 255))
            d.text((cx + 20, cy + 12), label, font=_font(_F_BOLD, 26), fill=(76, 29, 149))
            cx += int(tw) + 60
            if cx > W - 200:
                break
    if clip.get("business_name"):
        d.text((70, H - 58), f"by {clip['business_name']}", font=_font(_F_NAR, 26),
               fill=(214, 211, 232))
    d.text((W - 360, H - 58), "Watch & shop on FUUSIC", font=_font(_F_NAR, 24),
           fill=(196, 181, 253))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _storage_read(key: str) -> Optional[bytes]:
    try:
        st = get_storage()
        if not st.exists(key=key):
            return None
        h = st.head(key=key)
        size = int((h or {}).get("size") or 0)
        return st.open_range(key=key, start=0, end=size - 1) if size > 0 else None
    except Exception:
        return None


def _clip_key(clip_id: str) -> str:
    return f"social/clips/{clip_id}.png"


async def _ensure_clip_image(db, clip: dict) -> Optional[str]:
    key = _clip_key(clip["_id"])
    try:
        st = get_storage()
        if st.exists(key=key):
            return key
        st.upload_bytes(key=key, data=_compose_clip_card(clip), content_type="image/png")
        await db.live_clips.update_one({"_id": clip["_id"]},
                                       {"$set": {"image_key": key}})
        return key
    except Exception:
        return None


@router.get("/{sid}/clips")
async def list_clips(sid: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = []
    async for c in db.live_clips.find({"show_id": sid}).sort("created_at", -1).limit(30):
        rows.append({**_clip_public(c),
                     "image_url": _clip_image_url(request, c["_id"]),
                     "share_path": f"/api/social/liveshows/clips/{c['_id']}/share"})
    return {"items": rows}


@router.get("/clips/feed")
async def clips_feed(request: Request, user: dict = Depends(current_user)):
    """Global shoppable-clip discovery feed (newest across all shows)."""
    db = request.app.state.db
    rows = []
    async for c in db.live_clips.find({}).sort("created_at", -1).limit(30):
        rows.append({**_clip_public(c),
                     "image_url": _clip_image_url(request, c["_id"]),
                     "share_path": f"/api/social/liveshows/clips/{c['_id']}/share"})
    return {"items": rows}


@router.get("/clips/{clip_id}")
async def clip_detail(clip_id: str, request: Request,
                      user: Optional[dict] = Depends(current_user_optional)):
    """PUBLIC clip detail — powers the shareable /clips/<id> page."""
    db = request.app.state.db
    c = await db.live_clips.find_one({"_id": clip_id})
    if not c:
        raise HTTPException(404, {"code": "clip_not_found"})
    return {**_clip_public(c),
            "image_url": _clip_image_url(request, clip_id),
            "share_path": f"/api/social/liveshows/clips/{clip_id}/share"}


@router.get("/clips/{clip_id}/image.png")
async def clip_image(clip_id: str, request: Request):
    db = request.app.state.db
    c = await db.live_clips.find_one({"_id": clip_id})
    if not c:
        raise HTTPException(404, {"code": "clip_not_found"})
    key = c.get("image_key") or _clip_key(clip_id)
    data = _storage_read(key)
    if data is None:
        await _ensure_clip_image(db, c)
        data = _storage_read(key)
    if data is None:
        raise HTTPException(404, {"code": "image_unavailable"})
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400, "
                                              "stale-while-revalidate=604800"})


@router.get("/clips/{clip_id}/share")
async def clip_share_ssr(clip_id: str, request: Request):
    """SSR OG landing for a shared clip. Crawlers read the meta; browsers
    are redirected to the SPA clip page at /clips/<id>."""
    db = request.app.state.db
    base = _base_url(request)
    spa = f"{base}/clips/{clip_id}"
    c = await db.live_clips.find_one({"_id": clip_id})
    if not c:
        return RedirectResponse(spa, status_code=302)
    img = _clip_image_url(request, clip_id)
    landing = f"{base}/api/social/liveshows/clips/{clip_id}/share"
    title = f"{c.get('title')} — FUUSIC Live"
    desc = c.get("caption") or "A shoppable highlight from FUUSIC Live."
    import html as _h
    e = _h.escape
    out = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(landing)}">
<meta property="og:type" content="video.other">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name" content="FUUSIC">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:image" content="{e(img)}">
<link rel="canonical" href="{e(landing)}">
<style>body{{margin:0;background:#0d0a24;color:#fff;font-family:system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}img{{max-width:640px;width:100%;border-radius:20px;box-shadow:0 18px 60px rgba(0,0,0,.5)}}</style>
<script>(function(){{try{{var ua=navigator.userAgent||"";var bot=/facebookexternalhit|twitterbot|whatsapp|telegrambot|slackbot|linkedinbot|discordbot|preview|googlebot|bingbot|applebot|pinterest/i.test(ua);if(!bot)window.location.replace("{e(spa)}");}}catch(x){{}}}})();</script>
</head><body><img src="{e(img)}" alt="{e(title)}"></body></html>"""
    return HTMLResponse(out)


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
