"""Phase 36d Turn 2 — Shoppable cards: CRUD + click-proxy with IP-hash tracking.

Two collections:
    `podcast_shoppable_cards` — one row per card; attached to exactly one of
        episode_id OR magic_clip_id.
    `shoppable_card_clicks`   — one row per click-proxy hit (IP-hashed).

Storage:
    Tigris key prefix `shoppable_cards/{card_id}.{ext}` (image).
    Local fallback: `/app/backend/static/shoppable_cards/{card_id}.{ext}` served
    via the existing `/api/static/shoppable_cards` StaticFiles mount.

IP hashing: reuses the existing `services.podcast_guests._ip_hash` scheme
(sha256, 32-char hex prefix). DO NOT introduce a new salt.
"""
from __future__ import annotations
import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("bigfm.shoppable_cards")

COL_CARDS  = "podcast_shoppable_cards"
COL_CLICKS = "shoppable_card_clicks"

LOCAL_DIR = Path("/app/backend/static/shoppable_cards")
LOCAL_DIR.mkdir(parents=True, exist_ok=True)
DESCRIPTION_MAX  = 280
RATE_WINDOW_MIN  = 30  # one click per IP-hash per card per 30 minutes


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen() -> str:
    return f"shc_{uuid.uuid4().hex[:14]}"


def ip_hash(ip: Optional[str]) -> str:
    """Same scheme as services.podcast_guests._ip_hash."""
    return hashlib.sha256((ip or "0.0.0.0").encode("utf-8")).hexdigest()[:32]


def ua_hash(ua: Optional[str]) -> str:
    return hashlib.sha256((ua or "").encode("utf-8")).hexdigest()[:32]


def image_url_for(card_id: str, ext: str, storage_key: Optional[str],
                                  storage_backend: str = "local") -> str:
    """Returns a stable URL for the card image.
    - If Tigris-backed, returns the tigris public URL the storage backend
      exposes via get_signed_url (long-lived).
    - Otherwise serves locally via the static mount."""
    if storage_key and storage_backend == "tigris":
        try:
            from services import object_storage as obs
            st = obs.get_storage()
            # 30-day signed url is fine for product imagery.
            return st.get_signed_url(key=storage_key, expires_in=30 * 24 * 3600)
        except Exception:
            pass
    return f"/api/static/shoppable_cards/{card_id}.{ext}"


def _validate_anchor(episode_id: Optional[str], magic_clip_id: Optional[str]):
    has_ep = bool(episode_id)
    has_mc = bool(magic_clip_id)
    if has_ep == has_mc:
        raise ValueError("exactly one of episode_id or magic_clip_id must be set")


async def create_card(db, *, owner_creator_id: str,
                                          episode_id: Optional[str] = None,
                                          magic_clip_id: Optional[str] = None,
                                          title: str,
                                          product_url: str,
                                          price_cents: Optional[int] = None,
                                          currency: str = "USD",
                                          description: str = "",
                                          display_order: int = 0,
                                          image_bytes: Optional[bytes] = None,
                                          image_ext: Optional[str] = None) -> dict:
    _validate_anchor(episode_id, magic_clip_id)
    cid = _gen()
    storage_key: Optional[str] = None
    backend = "local"
    if image_bytes and image_ext:
        ext = image_ext.lstrip(".").lower() or "png"
        local_path = LOCAL_DIR / f"{cid}.{ext}"
        local_path.write_bytes(image_bytes)
        # Tigris-first upload with local fallback (mirrors ad_creatives pattern).
        try:
            from services import object_storage as obs
            st = obs.get_storage()
            if st.backend_name == "tigris":
                key = f"shoppable_cards/{cid}.{ext}"
                st.upload(local_path=str(local_path), key=key,
                                  content_type=f"image/{ext}")
                storage_key = key
                backend = "tigris"
        except Exception as e:
            logger.warning("[shoppable_cards] tigris upload failed (kept local): %s", e)
        image_url = image_url_for(cid, ext, storage_key, backend)
    else:
        image_url = ""
    row = {
        "id":                       cid,
        "owner_creator_id":  owner_creator_id,
        "episode_id":           episode_id,
        "magic_clip_id":     magic_clip_id,
        "title":                   (title or "")[:120],
        "image_url":          image_url,
        "image_ext":          image_ext,
        "storage_key_image": storage_key,
        "product_url":      (product_url or "")[:1000],
        "price_cents":       int(price_cents) if price_cents is not None else None,
        "currency":            (currency or "USD")[:8].upper(),
        "description":      (description or "")[:DESCRIPTION_MAX],
        "display_order":   int(display_order or 0),
        "active":                True,
        "created_at":         _now(),
        "updated_at":         _now(),
    }
    await db[COL_CARDS].insert_one(row)
    row.pop("_id", None)
    return row


async def list_cards(db, *, episode_id: Optional[str] = None,
                                          magic_clip_id: Optional[str] = None,
                                          include_inactive: bool = False) -> list:
    filt: dict = {}
    if episode_id and not magic_clip_id:
        filt["episode_id"] = episode_id
    elif magic_clip_id and not episode_id:
        filt["magic_clip_id"] = magic_clip_id
    else:
        raise ValueError("exactly one of episode_id or magic_clip_id must be set")
    if not include_inactive:
        filt["active"] = True
    rows = await db[COL_CARDS].find(filt, {"_id": 0}).sort(
        "display_order", 1).to_list(200)
    return rows


async def patch_card(db, *, card_id: str, owner_creator_id: str,
                                        body: dict) -> dict:
    card = await db[COL_CARDS].find_one({"id": card_id})
    if not card:
        raise LookupError("card_not_found")
    if (card.get("owner_creator_id") != owner_creator_id
              and body.get("_admin_bypass") is not True):
        raise PermissionError("not_owner")
    upd: dict = {}
    for k in ("title", "product_url", "currency", "description"):
        if k in body:
            upd[k] = str(body[k])[:1000 if k == "product_url" else
                                                  DESCRIPTION_MAX if k == "description" else 120]
    if "price_cents" in body:
        upd["price_cents"] = (int(body["price_cents"])
                                              if body["price_cents"] is not None else None)
    if "display_order" in body:
        upd["display_order"] = int(body["display_order"] or 0)
    if "active" in body:
        upd["active"] = bool(body["active"])
    if not upd:
        raise ValueError("no editable fields supplied")
    upd["updated_at"] = _now()
    await db[COL_CARDS].update_one({"id": card_id}, {"$set": upd})
    out = await db[COL_CARDS].find_one({"id": card_id}, {"_id": 0})
    return out


async def soft_delete(db, *, card_id: str, owner_creator_id: str) -> bool:
    card = await db[COL_CARDS].find_one({"id": card_id})
    if not card:
        raise LookupError("card_not_found")
    if card.get("owner_creator_id") != owner_creator_id:
        raise PermissionError("not_owner")
    await db[COL_CARDS].update_one(
        {"id": card_id},
        {"$set": {"active": False, "updated_at": _now()}})
    return True


async def record_click(db, *, card_id: str, ip: Optional[str],
                                            user_agent: Optional[str],
                                            referrer: Optional[str],
                                            user_id: Optional[str]) -> tuple[Optional[dict], bool]:
    """Returns (card, is_duplicate). Duplicate clicks (same card + ip_hash
    within RATE_WINDOW_MIN) are still recorded but flagged `duplicate=true`
    so analytics can de-dupe."""
    card = await db[COL_CARDS].find_one({"id": card_id})
    if not card:
        return None, False
    ih = ip_hash(ip)
    cutoff = _now() - timedelta(minutes=RATE_WINDOW_MIN)
    dup = await db[COL_CLICKS].find_one({
        "card_id":      card_id,
        "ip_hash":     ih,
        "clicked_at": {"$gte": cutoff},
        })
    is_duplicate = dup is not None
    doc = {
        "id":                 f"clk_{uuid.uuid4().hex[:14]}",
        "card_id":         card_id,
        "episode_id":   card.get("episode_id"),
        "magic_clip_id": card.get("magic_clip_id"),
        "user_id":         user_id,
        "referrer":       (referrer or "")[:500],
        "user_agent_hash": ua_hash(user_agent),
        "ip_hash":       ih,
        "duplicate":   is_duplicate,
        "clicked_at": _now(),
    }
    await db[COL_CLICKS].insert_one(doc)
    return card, is_duplicate


async def ensure_indexes(db):
    await db[COL_CARDS].create_index([("episode_id", 1), ("active", 1),
                                                                      ("display_order", 1)])
    await db[COL_CARDS].create_index([("magic_clip_id", 1), ("active", 1),
                                                                      ("display_order", 1)])
    await db[COL_CARDS].create_index([("id", 1)], unique=True)
    await db[COL_CARDS].create_index([("owner_creator_id", 1)])
    await db[COL_CLICKS].create_index([("card_id", 1), ("clicked_at", -1)])
    await db[COL_CLICKS].create_index([("card_id", 1), ("ip_hash", 1),
                                                                      ("clicked_at", -1)])
