"""Phase 36d Turn 2 — Shoppable cards routes.

Public reads (`GET /episodes/.../shoppable-cards`,
`GET /magic-clips/.../shoppable-cards`, and the click proxy) are
unauthenticated. Mutations require the owning creator (or admin)."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from auth import current_user, current_user_optional
from services import podcasts as svc
from services import shoppable_cards as sc

logger = logging.getLogger("bigfm.routes.shoppable_cards")

shoppable_router = APIRouter(prefix="/api/podcasts", tags=["shoppable_cards"])

MAX_IMAGE_BYTES = 1_500_000  # 1.5 MB; same ballpark as ad_creatives images


async def _resolve_creator(db, user: dict) -> dict:
    return await svc.require_approved_creator(db, user)


async def _own_episode(db, episode_id: str, creator_id: str,
                                            user: dict) -> dict:
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise HTTPException(404, "episode_not_found")
    ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")})
    if not ch:
        raise HTTPException(404, "channel_not_found")
    if ch.get("creator_id") != creator_id and user.get("role") != "admin":
        raise HTTPException(403, "not_your_episode")
    return ep


async def _own_clip(db, clip_id: str, creator_id: str, user: dict) -> dict:
    clip = await db.podcast_magic_clips.find_one({"id": clip_id})
    if not clip:
        raise HTTPException(404, "clip_not_found")
    ep = await db.podcast_episodes.find_one({"id": clip.get("episode_id")})
    if not ep:
        raise HTTPException(404, "episode_not_found")
    ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")})
    if not ch:
        raise HTTPException(404, "channel_not_found")
    if ch.get("creator_id") != creator_id and user.get("role") != "admin":
        raise HTTPException(403, "not_your_clip")
    return clip


def _client_ip(request: Request) -> Optional[str]:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    return request.client.host if request.client else None


async def _read_image(image: Optional[UploadFile]) -> tuple[Optional[bytes], Optional[str]]:
    if not image or not image.filename:
        return None, None
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(400, f"image over {MAX_IMAGE_BYTES // 1024} KB")
    ext = (Path(image.filename).suffix or ".png").lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        raise HTTPException(400, "image must be png/jpg/webp/gif")
    return data, ext


# ── creator-side creates ────────────────────────────────────────
@shoppable_router.post("/episodes/{episode_id}/shoppable-cards", status_code=201)
async def create_for_episode(episode_id: str, request: Request,
                                                          user: dict = Depends(current_user),
                                                          title: str = Form(...),
                                                          product_url: str = Form(...),
                                                          price_cents: Optional[int] = Form(None),
                                                          currency: str = Form("USD"),
                                                          description: str = Form(""),
                                                          display_order: int = Form(0),
                                                          image: Optional[UploadFile] = File(None)):
    db = request.app.state.db
    creator = await _resolve_creator(db, user)
    await _own_episode(db, episode_id, creator["id"], user)
    img_bytes, img_ext = await _read_image(image)
    row = await sc.create_card(db,
        owner_creator_id=creator["id"], episode_id=episode_id,
        title=title, product_url=product_url, price_cents=price_cents,
        currency=currency, description=description, display_order=display_order,
        image_bytes=img_bytes, image_ext=img_ext)
    return row


@shoppable_router.post("/magic-clips/{clip_id}/shoppable-cards", status_code=201)
async def create_for_clip(clip_id: str, request: Request,
                                                  user: dict = Depends(current_user),
                                                  title: str = Form(...),
                                                  product_url: str = Form(...),
                                                  price_cents: Optional[int] = Form(None),
                                                  currency: str = Form("USD"),
                                                  description: str = Form(""),
                                                  display_order: int = Form(0),
                                                  image: Optional[UploadFile] = File(None)):
    db = request.app.state.db
    creator = await _resolve_creator(db, user)
    await _own_clip(db, clip_id, creator["id"], user)
    img_bytes, img_ext = await _read_image(image)
    row = await sc.create_card(db,
        owner_creator_id=creator["id"], magic_clip_id=clip_id,
        title=title, product_url=product_url, price_cents=price_cents,
        currency=currency, description=description, display_order=display_order,
        image_bytes=img_bytes, image_ext=img_ext)
    return row


# ── public reads ─────────────────────────────────────────────────
@shoppable_router.get("/episodes/{episode_id}/shoppable-cards")
async def list_for_episode(episode_id: str, request: Request,
                                                  user: Optional[dict] = Depends(current_user_optional),
                                                  include_inactive: bool = False):
    db = request.app.state.db
    # Only the owner (or admin) can see inactive rows.
    show_all = False
    if include_inactive and user:
        creator = await db.podcast_creators.find_one({"user_id": user.get("user_id")})
        ep = await db.podcast_episodes.find_one({"id": episode_id}) or {}
        ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")}) or {}
        if user.get("role") == "admin" or (creator and ch.get("creator_id") == creator["id"]):
            show_all = True
    rows = await sc.list_cards(db, episode_id=episode_id,
                                                      include_inactive=show_all)
    return {"items": rows, "episode_id": episode_id, "count": len(rows)}


@shoppable_router.get("/magic-clips/{clip_id}/shoppable-cards")
async def list_for_clip(clip_id: str, request: Request,
                                          user: Optional[dict] = Depends(current_user_optional),
                                          include_inactive: bool = False):
    db = request.app.state.db
    show_all = False
    if include_inactive and user:
        creator = await db.podcast_creators.find_one({"user_id": user.get("user_id")})
        clip = await db.podcast_magic_clips.find_one({"id": clip_id}) or {}
        ep = await db.podcast_episodes.find_one({"id": clip.get("episode_id")}) or {}
        ch = await db.podcast_channels.find_one({"id": ep.get("channel_id")}) or {}
        if user.get("role") == "admin" or (creator and ch.get("creator_id") == creator["id"]):
            show_all = True
    rows = await sc.list_cards(db, magic_clip_id=clip_id,
                                                      include_inactive=show_all)
    return {"items": rows, "magic_clip_id": clip_id, "count": len(rows)}


# ── creator-side mutations ──────────────────────────────────────
@shoppable_router.patch("/shoppable-cards/{card_id}")
async def patch_card(card_id: str, body: dict, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _resolve_creator(db, user)
    try:
        return await sc.patch_card(db, card_id=card_id,
                                                              owner_creator_id=creator["id"],
                                                              body={**body, "_admin_bypass": user.get("role") == "admin"})
    except LookupError:
        raise HTTPException(404, "card_not_found")
    except PermissionError:
        raise HTTPException(403, "not_owner")
    except ValueError as e:
        raise HTTPException(400, str(e))


@shoppable_router.delete("/shoppable-cards/{card_id}")
async def delete_card(card_id: str, request: Request,
                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _resolve_creator(db, user)
    try:
        ok = await sc.soft_delete(db, card_id=card_id,
                                                          owner_creator_id=creator["id"])
        return {"deleted": ok, "id": card_id, "active": False}
    except LookupError:
        raise HTTPException(404, "card_not_found")
    except PermissionError:
        raise HTTPException(403, "not_owner")


# ── click-proxy (302) ────────────────────────────────────────────
@shoppable_router.get("/shoppable-cards/{card_id}/click")
async def click_proxy(card_id: str, request: Request,
                                      user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    card, _is_dup = await sc.record_click(db,
        card_id=card_id,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
        user_id=(user or {}).get("user_id"))
    if not card or not card.get("product_url") or not card.get("active"):
        raise HTTPException(404, "card_not_found_or_inactive")
    return RedirectResponse(url=card["product_url"], status_code=302)
