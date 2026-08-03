"""Phase 5 game routes — REMOVED in Phase 8a, with a thin GET shim.

`GET /api/games/state` used to power the Wallet → Games tab.  The mutation
endpoints (spin/play, trivia/start, ...) still return HTTP 410 with a
`moved_to` hint, but the catalogue GET now proxies to the Phase 8a
`/api/games_v2/play_and_win` data so the Wallet UI keeps working.

Empty catalogue → `{items: [], total: 0}` (never 500).
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request

from auth import current_user
# Phase Ω — Deploy hardening: share the global Motor client from
# `core.db` (which is wrapped in try/except with a localhost fallback)
# instead of constructing a fresh one at module-import time.  A fresh
# `AsyncIOMotorClient(mongodb+srv://...)` blows up if SRV DNS is
# unreachable, crashing uvicorn boot before K8s readiness probes fire.
from core.db import db as _db

logger = logging.getLogger("bigfm.games")

games_router = APIRouter(prefix="/api/games", tags=["games-legacy"])


def _gone(request: Request, replacement: str, hint: str = ""):
    from fastapi.responses import JSONResponse
    body = {
        "moved_to": replacement,
        "phase":     "8a",
        "detail":
            "Phase 5 endpoints were retired in Phase 8a — the entire game "
            "framework is now /api/games_v2/* with template + campaign + "
            "prize + redemption rules + compliance + analytics models. "
            "See PRD §Phase 8a.",
    }
    if hint: body["hint"] = hint
    return JSONResponse(status_code=410, content=body)


# Map games_v2 template_ids → legacy icons / wallet-tab game_ids.
_TPL_TO_ICON = {
    "tpl_spin_wheel":   "🎡",
    "tpl_quiz":           "🧠",
    "tpl_scratch_card": "🎁",
    "tpl_word_puzzle":  "🔤",
    "tpl_memory_match": "🧩",
    "tpl_slot_machine": "🎰",
    "tpl_mystery_box":  "📦",
}


@games_router.get("/state")
async def games_state(user: dict = Depends(current_user)):
    """Wallet → Games tab catalogue.  Empty-array on cold DB, never 500."""
    try:
        rows = await _db.game_campaigns.find({
            "status": {"$in": ["active", "live"]},
        }, sort=[("created_at", -1)]).to_list(50)
    except Exception as e:
        logger.warning("games/state catalogue read failed: %s", e)
        rows = []
    items = []
    for r in rows:
        tpl = r.get("template_id") or ""
        items.append({
            "game_id":             r.get("campaign_id") or r.get("id"),
            "campaign_id":       r.get("campaign_id") or r.get("id"),
            "template_id":       tpl,
            "title":               r.get("title")    or "Untitled game",
            "description":      r.get("description") or "",
            "icon":                _TPL_TO_ICON.get(tpl, "🎮"),
            "sponsor_name":   r.get("sponsor_name"),
            "available":         True,
            "daily_limit":       None,
            "played_today":     0,
            "cooldown_remaining_sec": 0,
        })
    return {"items": items, "total": len(items),
              "play_surface": "/play-and-win"}


@games_router.post("/spin/play")
async def spin_play_410(request: Request):
    return _gone(request, "/api/games_v2/campaigns/cmp_house_spin/start",
                       hint="Daily spin is now a platform-funded campaign. "
                              "POST start → submit → claim_to_wallet.")


@games_router.post("/trivia/start")
async def trivia_start_410(request: Request):
    return _gone(request, "/api/games_v2/campaigns/cmp_house_trivia/start")


@games_router.post("/trivia/answer")
async def trivia_answer_410(request: Request):
    return _gone(request, "/api/games_v2/sessions/{session_id}/submit",
                       hint="Pass {answer_idx: int} in the submit body.")


@games_router.post("/lyric/start")
async def lyric_start_410(request: Request):
    return _gone(request, "/api/games_v2/campaigns/cmp_house_lyric/start")


@games_router.post("/lyric/answer")
async def lyric_answer_410(request: Request):
    return _gone(request, "/api/games_v2/sessions/{session_id}/submit")
