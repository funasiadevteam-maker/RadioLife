"""Sub-Phase E5 — Admin endpoints for Predexon integration.

Routes (admin-only):
    GET  /api/admin/prediction/predexon/health
    GET  /api/admin/prediction/external-markets
    POST /api/admin/prediction/import-market
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import require_admin
from services import predexon_client
from services.predexon_client import (
    list_open_markets, get_market,
    normalize_outcomes, key_loaded,
)

log = logging.getLogger("bigfm.predexon.admin")

router = APIRouter(prefix="/api/admin/prediction",
                                    tags=["predexon-admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ──────────────────── /predexon/health ────────────────────
@router.get("/predexon/health",
                          description=(
                              "Admin diagnostic — pings Predexon for 1 market to "
                              "verify the API key is loaded and the upstream is "
                              "reachable.  Returns `key_loaded` as a bool only; "
                              "the key value itself is NEVER returned."))
async def predexon_health(request: Request,
                                                      _a: dict = Depends(require_admin)):
    db = request.app.state.db
    loaded = key_loaded()
    sample_market_count = 0
    ok = False
    status_code: Optional[int] = None
    response_time_ms = 0
    error_message: Optional[str] = None
    if loaded:
        res = await list_open_markets(db, limit=1)
        ok = res.get("ok", False)
        status_code = res.get("status_code")
        response_time_ms = res.get("response_time_ms", 0)
        error_message = res.get("error_message")
        body = res.get("body") or {}
        markets = (body.get("markets") if isinstance(body, dict)
                          else body) or []
        sample_market_count = len(markets) if isinstance(markets, list) else 0
    last_log = await db.prediction_api_logs.find_one(
        {"provider_name": "predexon"}, sort=[("called_at", -1)])
    return {
        "ok": ok,
        "key_loaded": loaded,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "sample_market_count": sample_market_count,
        "error_message": error_message,
        "last_logged_at": (last_log["called_at"].isoformat()
                                              if last_log and isinstance(
                                                  last_log.get("called_at"), datetime)
                                              else None),
        "base_url": predexon_client._base(),
    }


# ──────────────────── /external-markets ────────────────────
def _ext_market_card(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Project a Predexon market into the shape the UI consumes."""
    eid = (raw.get("market_id") or raw.get("id")
                  or raw.get("external_market_id") or raw.get("ticker"))
    outcomes = normalize_outcomes(
        raw.get("outcomes") or raw.get("answer_options") or [])
    return {
        "external_market_id": str(eid) if eid is not None else None,
        "title": (raw.get("title") or raw.get("question")
                        or raw.get("name") or "Untitled market"),
        "category": (raw.get("category") or raw.get("category_slug")
                              or raw.get("event_type")),
        "outcomes": outcomes,
        "outcomes_count": len(outcomes),
        "open_time": raw.get("open_time") or raw.get("start_time")
                                or raw.get("created_at"),
        "close_time": raw.get("close_time") or raw.get("end_time")
                                  or raw.get("resolve_by"),
        "market_url": (raw.get("market_url") or raw.get("url")
                                  or raw.get("permalink")),
        "raw": {
            # Forward a tiny preview so admins can debug field mappings.
            "market_id": raw.get("market_id"),
            "id": raw.get("id"),
            "ticker": raw.get("ticker"),
            "status": raw.get("status"),
        },
    }


@router.get("/external-markets",
                          description=(
                              "Proxies a Predexon market listing.  Annotates each "
                              "row with `already_imported_as_campaign_id` so the "
                              "admin can see which markets are already linked to a "
                              "draft / scheduled / live campaign."))
async def list_external_markets(request: Request,
                                                                        category: Optional[str] = Query(None),
                                                                        limit: int = Query(20, ge=1, le=100),
                                                                        offset: int = Query(0, ge=0),
                                                                        _a: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await list_open_markets(db, category=category,
                                                                      limit=limit, offset=offset)
    if not res.get("ok"):
        raise HTTPException(502, {"code": "predexon_unavailable",
                                                                    "status_code": res.get("status_code"),
                                                                    "error": res.get("error_message")})
    body = res.get("body") or {}
    markets_raw = (body.get("markets") if isinstance(body, dict)
                                else body) or []
    if not isinstance(markets_raw, list):
        markets_raw = []
    cards: List[Dict[str, Any]] = [_ext_market_card(m) for m in markets_raw]
    cards = [c for c in cards if c["external_market_id"]]
    # Augment with already-imported lookup.
    eids = [c["external_market_id"] for c in cards]
    existing: Dict[str, str] = {}
    if eids:
        async for camp in db.predict_win_campaigns.find(
                {"external_market_id": {"$in": eids},
                  "status": {"$ne": "cancelled"},
                  "deleted_at": None},
                {"campaign_id": 1, "external_market_id": 1, "status": 1}):
            existing[camp["external_market_id"]] = camp["campaign_id"]
    for c in cards:
        c["already_imported_as_campaign_id"] = existing.get(
            c["external_market_id"])
    return {"ok": True, "items": cards, "total": len(cards),
                  "limit": limit, "offset": offset,
                  "category": category,
                  "response_time_ms": res.get("response_time_ms")}


# ──────────────────── /import-market ────────────────────
def _opt_id(i: int) -> str:
    return f"opt_{i+1}"


@router.post("/import-market",
                          description=(
                              "Imports a Predexon market as a draft Predict & Win "
                              "campaign.  Pre-populates question + answer_options "
                              "(with `external_outcome_id` on each option for "
                              "resolution-time matching), start/lock/resolve times, "
                              "and links the predexon provider.  Idempotent: "
                              "returns 409 if a non-cancelled campaign already "
                              "exists for the same `external_market_id`."))
async def import_market(payload: dict, request: Request,
                                                  admin: dict = Depends(require_admin)):
    db = request.app.state.db
    external_market_id = (payload or {}).get("external_market_id", "")
    overrides: Dict[str, Any] = (payload or {}).get("campaign_overrides") or {}
    if not external_market_id:
        raise HTTPException(400, {"code": "external_market_id_required"})

    # Idempotency check.
    dup = await db.predict_win_campaigns.find_one({
        "external_market_id": str(external_market_id),
        "status": {"$ne": "cancelled"},
        "deleted_at": None,
    })
    if dup:
        raise HTTPException(409, {"code": "already_imported",
                                                                    "campaign_id": dup["campaign_id"],
                                                                    "status": dup.get("status"),
                                                                    "approval_status": dup.get("approval_status")})

    # Fetch the market detail.  Some Predexon API tiers reject the
    # per-market detail endpoint (403); fall back to scanning the
    # public list endpoint for the matching `external_market_id`.
    res = await get_market(db, external_market_id)
    if not res.get("ok") or not res.get("body"):
        raw = None
        scanned = 0
        cap = 600   # ~30 pages of 20 — bounded scan.
        offset = 0
        page_size = 50
        while scanned < cap and raw is None:
            lres = await list_open_markets(db, limit=page_size,
                                                                              offset=offset)
            if not lres.get("ok"):
                break
            body = lres.get("body") or {}
            markets = (body.get("markets") if isinstance(body, dict)
                                  else body) or []
            if not isinstance(markets, list) or not markets:
                break
            for m in markets:
                mid = (m.get("market_id") or m.get("id")
                              or m.get("external_market_id") or m.get("ticker"))
                if str(mid) == str(external_market_id):
                    raw = m
                    break
            scanned += len(markets)
            offset += page_size
            if len(markets) < page_size:
                break
        if raw is None:
            raise HTTPException(404, {"code": "market_not_found",
                                                                        "status_code": res.get("status_code"),
                                                                        "scanned_pages": scanned})
    else:
        raw = res["body"]
    card = _ext_market_card(raw)
    if not card["outcomes"]:
        raise HTTPException(400, {"code": "no_outcomes",
                                                                    "external_market_id": external_market_id})

    # Resolve the predexon provider row.
    prov = await db.prediction_data_providers.find_one(
        {"provider_name": "predexon"})
    if not prov:
        raise HTTPException(500, {"code": "predexon_provider_not_seeded"})

    # Materialise answer_options with external_outcome_id on each.
    options: List[Dict[str, Any]] = []
    for i, o in enumerate(card["outcomes"]):
        options.append({
            "option_id": _opt_id(i),
            "label": o["label"][:80],
            "external_outcome_id": o["external_outcome_id"],
        })

    # Compose campaign doc.
    now = _now()
    start_default = now
    # Try parsing predexon close_time as our lock_time.
    def _parse(v):
        if not v:
            return None
        try:
            if isinstance(v, (int, float)):
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
            s = str(v).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except Exception:
            return None
    open_time = _parse(card["open_time"]) or start_default
    close_time = _parse(card["close_time"])
    if close_time is None or close_time <= open_time:
        # Default to 7 days from now.
        from datetime import timedelta
        close_time = open_time + timedelta(days=7)
    resolve_by = close_time + (close_time - open_time) * 0  # same as close.

    # Apply admin-supplied overrides (title / lock_time / resolve_by / question).
    title = (overrides.get("title") or card["title"] or "Predexon market")[:160]
    description = overrides.get("description")
    question_text = (overrides.get("question_text")
                                      or card["title"]
                                      or "Pick the winning outcome.")
    if overrides.get("lock_time"):
        try:
            close_time = datetime.fromisoformat(
                str(overrides["lock_time"]).replace("Z", "+00:00"))
        except Exception:
            pass
    if overrides.get("resolve_by"):
        try:
            resolve_by = datetime.fromisoformat(
                str(overrides["resolve_by"]).replace("Z", "+00:00"))
        except Exception:
            pass
    if resolve_by <= close_time:
        from datetime import timedelta
        resolve_by = close_time + timedelta(hours=2)

    campaign_id = _new_id("pwc")
    doc = {
        "_id": campaign_id,
        "campaign_id": campaign_id,
        "title": title,
        "description": (description or None),
        "event_type": overrides.get("event_type") or "general_prediction",
        "event_label": card["category"],
        "category": card["category"],
        "city": None, "region": None, "language": "en",
        "cover_image_url": None,
        "question": {
            "prompt": question_text[:600],
            "answer_options": options,
        },
        "start_time": open_time,
        "lock_time": close_time,
        "resolve_by": resolve_by,
        "winner_rules_json": {"selection_rule": "first_n_correct",
                                                          "first_n": 1, "tiebreaker": "earliest"},
        "data_provider_id": prov.get("provider_id") or prov.get("_id"),
        "compliance_settings_id": overrides.get("compliance_settings_id"),
        "external_market_id": str(external_market_id),
        "external_market_url": card.get("market_url"),
        "external_provider_snapshot": {
            "provider_name": "predexon",
            "title": card["title"], "category": card["category"],
            "imported_at": now.isoformat(),
        },
        "creator_type": "admin",
        "approval_status": "draft",
        "approval_reason": None,
        "approved_by": None, "approved_at": None,
        "rejected_by": None, "rejected_at": None,
        "status": "draft",
        "created_by": admin["user_id"],
        "created_at": now, "updated_at": now,
        "deleted_at": None,
    }
    await db.predict_win_campaigns.insert_one(doc)

    # Stamp the external market row for provenance.
    em_id = _new_id("pme")
    try:
        await db.prediction_markets_external.update_one(
            {"external_market_id": str(external_market_id),
              "provider_id": prov.get("provider_id") or prov.get("_id")},
            {"$set": {"_id": em_id, "external_market_id": str(external_market_id),
                              "provider_id": prov.get("provider_id") or prov.get("_id"),
                              "raw_market_snapshot": raw,
                              "imported_campaign_id": campaign_id,
                              "updated_at": now},
              "$setOnInsert": {"created_at": now}},
            upsert=True)
    except Exception as e:
        log.warning("[predexon] markets_external upsert failed: %s", e)
    return {"ok": True, "campaign_id": campaign_id,
                  "external_market_id": str(external_market_id),
                  "answer_options": options,
                  "lock_time": close_time.isoformat(),
                  "resolve_by": resolve_by.isoformat()}
