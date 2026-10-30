"""Games → Appearance — admin-managed art/label/colour/icon/visibility/order
for the game-hub tiles, shared by the web and mobile hubs.

A canonical catalog (DEFAULT_GAMES) maps each logical game to its per-platform
tile key (web_key / mobile_key).  Admin overrides live in `game_appearance`
keyed by the canonical key; both clients fetch /api/games/appearance and merge
the override onto their own tile by matching web_key / mobile_key.

Images come from object storage (upload) or AI generation (Gemini Nano Banana
via EMERGENT_LLM_KEY); both are written to /app/backend/static/game_art and
served at the stable /api/static/game_art/... prefix (object storage fallback).
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import (APIRouter, Depends, File, HTTPException, Request,
                                  UploadFile)
from pydantic import BaseModel, Field

from auth import current_user, require_admin

logger = logging.getLogger("bigfm")
router = APIRouter(prefix="/api", tags=["game-appearance"])

ART_ROOT = "/app/backend/static/game_art"
ART_PREFIX = "/api/static/game_art"

# Concept icons — each client maps these to its own icon library.
CONCEPT_ICONS = ["wheel", "gift", "music", "mic", "question", "dice", "slot",
                              "grid", "text", "cube", "cards", "trophy", "star",
                              "sparkles", "rocket", "flame"]

# Canonical catalog. web_key / mobile_key match the hardcoded tile keys in
# PlayAndWin.js (web) and app/(tabs)/games.tsx (mobile).
DEFAULT_GAMES = [
    {"key": "spin", "kind": "house", "label": "Spin & Win", "color": "#a855f7",
      "icon": "wheel", "web_key": "spin_win", "mobile_key": "spin"},
    {"key": "scratch", "kind": "house", "label": "Scratch & Win",
      "color": "#6366F1", "icon": "gift", "web_key": "scratch_win",
      "mobile_key": "scratch"},
    {"key": "trivia", "kind": "house", "label": "Music Trivia",
      "color": "#f59e0b", "icon": "music", "web_key": "trivia",
      "mobile_key": "trivia"},
    {"key": "quiz", "kind": "house", "label": "Quiz Rush", "color": "#ef4444",
      "icon": "question", "web_key": "quiz", "mobile_key": None},
    {"key": "lyric", "kind": "house", "label": "Guess the Lyric",
      "color": "#0ea5e9", "icon": "mic", "web_key": None,
      "mobile_key": "lyric"},
    {"key": "predict", "kind": "house", "label": "Predict & Win",
      "color": "#14b8a6", "icon": "trophy", "web_key": "predict",
      "mobile_key": None},
    {"key": "dice", "kind": "house", "label": "Lucky Dice", "color": "#f97316",
      "icon": "dice", "web_key": "lucky_dice", "mobile_key": None},
    # Branded / sponsored templates (db.game_templates template_ids).
    {"key": "tpl_spin_wheel", "kind": "template", "label": "Spin Wheel",
      "color": "#ff2d95", "icon": "wheel", "web_key": "tpl_spin_wheel",
      "mobile_key": "tpl_spin_wheel"},
    {"key": "tpl_scratch_card", "kind": "template", "label": "Scratch Card",
      "color": "#6366F1", "icon": "gift", "web_key": "tpl_scratch_card",
      "mobile_key": "tpl_scratch_card"},
    {"key": "tpl_quiz", "kind": "template", "label": "Quiz", "color": "#f59e0b",
      "icon": "question", "web_key": "tpl_quiz", "mobile_key": "tpl_quiz"},
    {"key": "tpl_slot_machine", "kind": "template", "label": "Slots",
      "color": "#3b82f6", "icon": "slot", "web_key": "tpl_slot_machine",
      "mobile_key": "tpl_slot_machine"},
    {"key": "tpl_memory_match", "kind": "template", "label": "Memory Match",
      "color": "#14b8a6", "icon": "grid", "web_key": "tpl_memory_match",
      "mobile_key": "tpl_memory_match"},
    {"key": "tpl_word_puzzle", "kind": "template", "label": "Word Puzzle",
      "color": "#8b5cf6", "icon": "text", "web_key": "tpl_word_puzzle",
      "mobile_key": "tpl_word_puzzle"},
    {"key": "tpl_mystery_box", "kind": "template", "label": "Mystery Box",
      "color": "#f97316", "icon": "cube", "web_key": "tpl_mystery_box",
      "mobile_key": "tpl_mystery_box"},
    {"key": "tpl_pick_a_card", "kind": "template", "label": "Pick a Card",
      "color": "#0ea5e9", "icon": "cards", "web_key": "tpl_pick_a_card",
      "mobile_key": "tpl_pick_a_card"},
]
_BY_KEY = {g["key"]: g for g in DEFAULT_GAMES}


def _now():
    return datetime.now(timezone.utc)


def _merge(default: dict, ov: Optional[dict]) -> dict:
    ov = ov or {}
    icon = ov.get("icon") or default["icon"]
    if icon not in CONCEPT_ICONS:
        icon = default["icon"]
    return {
        "key": default["key"],
        "kind": default["kind"],
        "web_key": default["web_key"],
        "mobile_key": default["mobile_key"],
        "label": (ov.get("label") or "").strip() or default["label"],
        "color": ov.get("color") or default["color"],
        "icon": icon,
        "image_url": ov.get("image_url") or None,
        "hidden": bool(ov.get("hidden")),
        "order": ov.get("order") if isinstance(ov.get("order"), int) else None,
        "is_overridden": bool(ov),
    }


async def _merged_list(db) -> list:
    overrides = {o["key"]: o
                          async for o in db.game_appearance.find({}, {"_id": 0})}
    rows = [_merge(g, overrides.get(g["key"])) for g in DEFAULT_GAMES]
    # Stable sort: explicit order first (ascending), then catalog order.
    idx = {g["key"]: i for i, g in enumerate(DEFAULT_GAMES)}
    rows.sort(key=lambda r: (r["order"] if r["order"] is not None else 10_000,
                                            idx[r["key"]]))
    return rows


def _store_bytes(game_key: str, data: bytes, content_type: str) -> str:
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
              "image/webp": "webp", "image/gif": "gif"}.get(
                  (content_type or "").lower(), "png")
    rel = f"{game_key}/{uuid.uuid4().hex[:12]}.{ext}"
    # Object storage is the canonical, deployment-safe sink. The matching
    # /api/static/game_art mount serves these via Tigris fallback on a local
    # miss, so the returned URL stays valid across stateless deploys.
    from services.object_storage import get_storage
    get_storage().upload_bytes(key=f"static/game_art/{rel}", data=data,
                                                  content_type=content_type or "image/png")
    return f"{ART_PREFIX}/{rel}"


# ── models ───────────────────────────────────────────────────────────
class AppearanceBody(BaseModel):
    label: Optional[str] = Field(None, max_length=60)
    color: Optional[str] = Field(None, max_length=16)
    icon: Optional[str] = None
    image_url: Optional[str] = None
    hidden: Optional[bool] = None


class ReorderBody(BaseModel):
    keys: list[str]


class GenerateBody(BaseModel):
    prompt: str = Field(min_length=3, max_length=400)


# ── admin endpoints ──────────────────────────────────────────────────
@router.get("/admin/game-appearance")
async def admin_list(request: Request, admin: dict = Depends(require_admin)):
    db = request.app.state.db
    return {"games": await _merged_list(db), "icons": CONCEPT_ICONS}


@router.put("/admin/game-appearance/{key}")
async def admin_upsert(key: str, body: AppearanceBody, request: Request,
                                      admin: dict = Depends(require_admin)):
    if key not in _BY_KEY:
        raise HTTPException(404, {"status": "unknown_game"})
    db = request.app.state.db
    patch = {"updated_at": _now(), "updated_by": admin["user_id"]}
    if body.label is not None: patch["label"] = body.label.strip()
    if body.color is not None: patch["color"] = body.color
    if body.icon is not None:
        if body.icon not in CONCEPT_ICONS:
            raise HTTPException(400, {"status": "bad_icon"})
        patch["icon"] = body.icon
    if body.image_url is not None: patch["image_url"] = body.image_url or None
    if body.hidden is not None: patch["hidden"] = bool(body.hidden)
    await db.game_appearance.update_one(
        {"key": key}, {"$set": patch, "$setOnInsert": {"key": key}},
        upsert=True)
    ov = await db.game_appearance.find_one({"key": key}, {"_id": 0})
    return {"ok": True, "game": _merge(_BY_KEY[key], ov)}


@router.post("/admin/game-appearance/reorder")
async def admin_reorder(body: ReorderBody, request: Request,
                                        admin: dict = Depends(require_admin)):
    db = request.app.state.db
    for i, key in enumerate(body.keys):
        if key in _BY_KEY:
            await db.game_appearance.update_one(
                {"key": key},
                {"$set": {"order": i, "updated_at": _now()},
                  "$setOnInsert": {"key": key}}, upsert=True)
    return {"ok": True, "games": await _merged_list(db)}


@router.post("/admin/game-appearance/{key}/image")
async def admin_upload_image(key: str, request: Request,
                                                  file: UploadFile = File(...),
                                                  admin: dict = Depends(require_admin)):
    if key not in _BY_KEY:
        raise HTTPException(404, {"status": "unknown_game"})
    data = await file.read()
    if not data:
        raise HTTPException(400, {"status": "empty_file"})
    if len(data) > 6 * 1024 * 1024:
        raise HTTPException(400, {"status": "file_too_large", "max_mb": 6})
    url = _store_bytes(key, data, file.content_type or "image/png")
    db = request.app.state.db
    await db.game_appearance.update_one(
        {"key": key},
        {"$set": {"image_url": url, "updated_at": _now(),
                          "updated_by": admin["user_id"]},
          "$setOnInsert": {"key": key}}, upsert=True)
    return {"ok": True, "image_url": url}


@router.post("/admin/game-appearance/{key}/generate")
async def admin_generate_image(key: str, body: GenerateBody, request: Request,
                                                      admin: dict = Depends(require_admin)):
    if key not in _BY_KEY:
        raise HTTPException(404, {"status": "unknown_game"})
    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(503, {"status": "image_gen_unconfigured"})
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=api_key,
                                  session_id=f"gameart-{key}-{uuid.uuid4().hex[:8]}",
                                  system_message="You generate vibrant square app "
                                                              "game-tile artwork. No text, no "
                                                              "watermark, centered subject.")
        chat.with_model("gemini", "gemini-3.1-flash-image-preview") \
               .with_params(modalities=["image", "text"])
        prompt = (f"Game tile artwork for a mobile game called "
                        f"'{_BY_KEY[key]['label']}'. {body.prompt.strip()}. "
                        f"Bold, playful, high-contrast, square composition.")
        _text, images = await chat.send_message_multimodal_response(
            UserMessage(text=prompt))
    except Exception as e:
        logger.warning("[game_appearance] AI generate failed: %s", e)
        raise HTTPException(502, {"status": "generation_failed"})
    if not images:
        raise HTTPException(502, {"status": "no_image_returned"})
    img = images[0]
    data = base64.b64decode(img["data"])
    url = _store_bytes(key, data, img.get("mime_type", "image/png"))
    db = request.app.state.db
    await db.game_appearance.update_one(
        {"key": key},
        {"$set": {"image_url": url, "updated_at": _now(),
                          "updated_by": admin["user_id"]},
          "$setOnInsert": {"key": key}}, upsert=True)
    return {"ok": True, "image_url": url}


@router.delete("/admin/game-appearance/{key}/image")
async def admin_clear_image(key: str, request: Request,
                                                admin: dict = Depends(require_admin)):
    if key not in _BY_KEY:
        raise HTTPException(404, {"status": "unknown_game"})
    db = request.app.state.db
    await db.game_appearance.update_one(
        {"key": key}, {"$set": {"image_url": None, "updated_at": _now()}})
    return {"ok": True}


# ── public endpoint (both clients) ───────────────────────────────────
@router.get("/games/appearance")
async def public_appearance(request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = await _merged_list(db)
    return {"games": [r for r in rows if not r["hidden"]],
                  "icons": CONCEPT_ICONS}
