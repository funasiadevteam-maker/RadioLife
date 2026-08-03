"""Phase 9a — Commute REST endpoints + Maps system status."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, require_admin
from services.commute import (
    list_saved_locations, create_saved_location, update_saved_location,
    delete_saved_location, route_preview, start_commute, heartbeat_commute,
    end_commute, get_active_commute, get_driving_state, list_history,
    activate_commute_unlock_rule,
)
from services.maps_client import (
    get_maps_client, ensure_maps_indexes, seed_mock_places, CATEGORIES,
    probe_and_decide_client,
)

logger = logging.getLogger("bigfm.commute_routes")

commute_router = APIRouter(prefix="/api/commute", tags=["commute"])
system_router = APIRouter(prefix="/api/system", tags=["system_meta"])


# ─── helpers ────────────────────────────────────────────────────────────
def _parse_point(d: dict, name: str) -> dict:
    if not isinstance(d, dict) or "lat" not in d or "lng" not in d:
        raise HTTPException(400, f"{name}.lat_and_lng_required")
    try:
        return {"lat": float(d["lat"]), "lng": float(d["lng"]),
                  "label": d.get("label")}
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name}.invalid_coords")


# ─── Saved locations ────────────────────────────────────────────────────
@commute_router.get("/saved_locations")
async def list_locations(request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    return {"items": await list_saved_locations(db, user["user_id"])}


@commute_router.post("/saved_locations")
async def create_location(request: Request, body: dict,
                                 user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await create_saved_location(
            db, user["user_id"],
            label=body.get("label", ""),
            address=body.get("address"),
            lat=body.get("lat"), lng=body.get("lng"),
            is_default_origin=bool(body.get("is_default_origin", False)),
            is_default_destination=bool(body.get("is_default_destination", False)))
    except ValueError as e:
        raise HTTPException(400, str(e))


@commute_router.patch("/saved_locations/{loc_id}")
async def patch_location(loc_id: str, request: Request, body: dict,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await update_saved_location(db, user["user_id"], loc_id, body)
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@commute_router.delete("/saved_locations/{loc_id}")
async def del_location(loc_id: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await delete_saved_location(db, user["user_id"], loc_id)
    return {"ok": True}


# ─── Route preview + commute lifecycle ──────────────────────────────────
@commute_router.post("/route_preview")
async def post_route_preview(request: Request, body: dict,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    origin = _parse_point(body.get("origin") or {}, "origin")
    destination = _parse_point(body.get("destination") or {}, "destination")
    return await route_preview(db, origin=origin, destination=destination,
                                       departure_time=body.get("departure_time"))


@commute_router.post("/start")
async def post_start_commute(request: Request, body: dict,
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    origin = _parse_point(body.get("origin") or {}, "origin")
    destination = _parse_point(body.get("destination") or {}, "destination")
    try:
        return await start_commute(
            db, user["user_id"],
            origin=origin, destination=destination,
            mode=body.get("mode", "driver"),
            label=body.get("label", "other"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@commute_router.post("/{commute_id}/heartbeat")
async def post_commute_heartbeat(commute_id: str, request: Request,
                                              body: Optional[dict] = None,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    body = body or {}
    try:
        return await heartbeat_commute(
            db, user["user_id"], commute_id,
            current_lat=body.get("current_lat"),
            current_lng=body.get("current_lng"),
            eta_remaining_s=body.get("eta_remaining_s"))
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@commute_router.post("/{commute_id}/end")
async def post_commute_end(commute_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await end_commute(db, user["user_id"], commute_id,
                                          abandon=False)
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@commute_router.post("/{commute_id}/abandon")
async def post_commute_abandon(commute_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        return await end_commute(db, user["user_id"], commute_id,
                                          abandon=True)
    except ValueError as e:
        msg = str(e)
        if msg == "not_found":
            raise HTTPException(404, msg)
        raise HTTPException(400, msg)


@commute_router.get("/active")
async def get_active(request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    return {"active": await get_active_commute(db, user["user_id"])}


@commute_router.get("/history")
async def get_commute_history(request: Request,
                                       limit: int = Query(20, ge=1, le=100),
                                       user: dict = Depends(current_user)):
    db = request.app.state.db
    return {"items": await list_history(db, user["user_id"], limit=limit)}


@commute_router.get("/me/driving_state")
async def me_driving_state(request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    return await get_driving_state(db, user["user_id"])


# ─── Places ─────────────────────────────────────────────────────────────
@commute_router.get("/nearby_places")
async def nearby_places(request: Request,
                              lat: float = Query(...),
                              lng: float = Query(...),
                              radius: int = Query(2000, ge=100, le=20000),
                              categories: Optional[str] = Query(None),
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    client = get_maps_client(db)
    cats = ([c.strip() for c in categories.split(",")]
              if categories else list(CATEGORIES))
    items = await client.nearby_places({"lat": lat, "lng": lng}, radius, cats)
    return {"items": items}


@commute_router.get("/{commute_id}/places_along_route")
async def places_along_route_endpoint(
        commute_id: str, request: Request,
        radius: int = Query(2000, ge=100, le=20000),
        categories: Optional[str] = Query(None),
        max_detour_minutes: int = Query(8, ge=1, le=60),
        user: dict = Depends(current_user)):
    db = request.app.state.db
    row = await db.commute_sessions.find_one(
        {"commute_id": commute_id, "user_id": user["user_id"]})
    if not row:
        raise HTTPException(404, "commute_not_found")
    client = get_maps_client(db)
    cats = ([c.strip() for c in categories.split(",")]
              if categories else list(CATEGORIES))
    items = await client.places_along_route(
        row["route_polyline"], radius, cats, max_detour_minutes)
    return {"items": items, "categories_in": cats}


# ─── System integrations + maps cache admin ─────────────────────────────
@system_router.get("/integrations")
async def system_integrations(request: Request,
                                       _u: dict = Depends(require_admin)):
    """Phase 9a — admin view of integration statuses.  Tells you at a
    glance which integrations are live vs mocked vs unset.

    Phase 9a Addendum: surfaces the Maps auth mode (api_key vs
    service_account vs mock), the resolved service-account email (safe
    to log), and per-API health captured at boot probe.
    """
    app = request.app
    maps = get_maps_client(app.state.db)
    probe = getattr(app.state, "maps_probe", None) or {}
    wallet_probe = getattr(app.state, "wallet_probe", None) or {}
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_elabs = bool(os.environ.get("ELEVENLABS_API_KEY"))
    has_stripe = bool(os.environ.get("STRIPE_SECRET_KEY"))
    has_gmaps_key = bool(os.environ.get("GOOGLE_MAPS_API_KEY"))
    sa_path = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    has_gmaps_sa = bool(sa_path and os.path.exists(sa_path))
    has_wallet_issuer = bool(
        (os.environ.get("GOOGLE_WALLET_ISSUER_ID") or "").strip())
    maps_mode = probe.get("mode") or (
        "live" if (has_gmaps_key or has_gmaps_sa) else "mock")
    return {"items": [
        {"name": "MapsClient",
          "implementation": maps.name,
          "configured": bool(has_gmaps_key or has_gmaps_sa),
          "env_key": "GOOGLE_MAPS_API_KEY",
          "auth_mode": probe.get("auth_mode") or getattr(maps, "auth_mode", "mock"),
          "auth_email": probe.get("auth_email") or getattr(maps, "auth_email", None),
          "api_health": probe.get("api_health") or {},
          "mode": maps_mode},
        {"name": "OpenAI", "implementation": "OpenAI",
          "configured": has_openai, "env_key": "OPENAI_API_KEY",
          "mode": "live" if has_openai else "unset"},
        {"name": "ElevenLabs", "implementation": "ElevenLabs",
          "configured": has_elabs, "env_key": "ELEVENLABS_API_KEY",
          "mode": "live" if has_elabs else "unset"},
        {"name": "Stripe", "implementation": "Stripe",
          "configured": has_stripe, "env_key": "STRIPE_SECRET_KEY",
          "mode": "test" if has_stripe else "unset"},
        # Phase 9c — Google Wallet (real if SA + Wallet API + issuer
        # configured, otherwise stub fallback that still mints save URLs
        # for UI testing).
        {"name": "GoogleWallet",
          "implementation": wallet_probe.get("client", "GoogleWalletClient"),
          "configured": bool(has_gmaps_sa and has_wallet_issuer),
          "env_key": "GOOGLE_WALLET_ISSUER_ID",
          "mode": wallet_probe.get("mode", "stub"),
          "auth_email": wallet_probe.get("auth_email"),
          "api_health": wallet_probe.get("api_health"),
          "issuer_id": wallet_probe.get("issuer_id"),
          "error": wallet_probe.get("error")},
    ]}


@commute_router.post("/admin/maps/verify_credentials")
async def admin_maps_verify_credentials(request: Request,
                                                      _u: dict = Depends(require_admin)):
    """Phase 9a Addendum — admin live re-probe of the configured Maps
    Platform credentials.  Useful after enabling a previously-disabled
    API on the GCP project (no backend restart needed).  Returns the
    fresh client/auth/api_health snapshot and updates app.state for
    /api/system/integrations.
    """
    app = request.app
    # Force a re-probe.  The factory has already chosen the live client
    # at boot — if it was swapped out for Mock, we re-instantiate the
    # live client here so we can probe again from scratch.
    from services.maps_client import (
        _load_service_account_creds, GoogleMapsClient, MockMapsClient,
    )
    import services.maps_client as _maps_mod
    api_key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    sa_creds, sa_email = _load_service_account_creds()
    if api_key:
        _maps_mod._singleton = GoogleMapsClient(app.state.db, api_key=api_key)
    elif sa_creds is not None:
        _maps_mod._singleton = GoogleMapsClient(
            app.state.db, sa_credentials=sa_creds, sa_email=sa_email)
    else:
        _maps_mod._singleton = MockMapsClient(app.state.db)
    probe_res = await probe_and_decide_client(app.state.db, app=app)
    app.state.maps_probe = probe_res
    return probe_res


@commute_router.get("/admin/maps_cache/stats")
async def maps_cache_stats(request: Request,
                                  _u: dict = Depends(require_admin)):
    db = request.app.state.db
    maps = get_maps_client(db)
    n_rows = await db.maps_cache.count_documents({})
    return {
        "client": maps.name,
        "cache_rows": n_rows,
        "hits": getattr(maps, "_cache_hits", 0),
        "misses": getattr(maps, "_cache_misses", 0),
        "real_calls": getattr(maps, "_real_calls", 0),
    }


@commute_router.post("/admin/maps_seed/import_dubai")
async def admin_maps_seed_dubai(request: Request,
                                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await seed_mock_places(db, force=True)


@commute_router.post("/admin/maps_seed/import_dfw")
async def admin_maps_seed_dfw(request: Request,
                                        _u: dict = Depends(require_admin)):
    db = request.app.state.db
    return await seed_mock_places(db, force=True)


# ═══════════════════════════════════════════════════════════════════════
# Phase 9b — Route-targeted opportunities
# ═══════════════════════════════════════════════════════════════════════
@commute_router.get("/{commute_id}/opportunities")
async def get_commute_opportunities(commute_id: str, request: Request,
                                                  user: dict = Depends(current_user),
                                                  only_upcoming: bool = True):
    """Listener-facing — what route-targeted ads/games are coming up?"""
    from services.route_ad_engine import list_opportunities_for_commute
    db = request.app.state.db
    items = await list_opportunities_for_commute(
        db, commute_id=commute_id, user_id=user["user_id"],
        only_upcoming=only_upcoming)
    return {"items": items, "commute_id": commute_id}


# Standalone router for route-ad opportunity engagement.  Mounted on
# server.py under /api/route_ads.
from fastapi import APIRouter
route_ads_router = APIRouter(prefix="/api/route_ads",
                                       tags=["route_ads"])


@route_ads_router.get("/{opp_id}/reason_codes")
async def get_reason_codes(opp_id: str, request: Request,
                                  user: dict = Depends(current_user)):
    """Powers the radio player's "Why this ad?" modal."""
    from services.route_ad_engine import get_opp_reason_codes
    db = request.app.state.db
    row = await get_opp_reason_codes(db, opp_id=opp_id)
    if not row:
        raise HTTPException(404, "not_found")
    return row


@route_ads_router.post("/{opp_id}/engage")
async def post_engage_opp(opp_id: str, request: Request, body: dict,
                                user: dict = Depends(current_user)):
    """Listener engaged with a route opportunity.

    body: { engagement_type: "clicked"|"saved"|"played"|"dismissed" }
    """
    from services.route_ad_engine import mark_opp_engagement
    db = request.app.state.db
    etype = (body or {}).get("engagement_type", "clicked")
    try:
        out = await mark_opp_engagement(
            db, opp_id=opp_id, user_id=user["user_id"],
            engagement_type=etype)
    except ValueError as e:
        msg = str(e)
        if msg == "invalid_engagement_type":
            raise HTTPException(
                400,
                "invalid_engagement_type. "
                "Allowed: ['clicked', 'saved', 'played', 'dismissed']")
        raise HTTPException(400, msg)
    if not out:
        raise HTTPException(404, "not_found")
    return out


@route_ads_router.get("/admin/decision_log")
async def admin_route_ad_decision_log(request: Request,
                                                   _u: dict = Depends(require_admin),
                                                   commute_id: Optional[str] = None,
                                                   since: Optional[str] = None,
                                                   limit: int = 100):
    """Admin debug — last N decisions.  Optionally filter by commute or
    by ISO `since` timestamp."""
    from datetime import datetime as _dt
    db = request.app.state.db
    q: dict = {}
    if commute_id:
        q["commute_id"] = commute_id
    if since:
        try:
            q["ts"] = {"$gte": _dt.fromisoformat(since.replace("Z", "+00:00"))}
        except Exception:
            raise HTTPException(400, "invalid_since")
    cur = (db.route_ad_decision_log.find(q)
              .sort("ts", -1).limit(int(min(max(limit, 1), 500))))
    items = []
    async for r in cur:
        items.append({
            "decision_id": r.get("_id"),
            "user_id": r.get("user_id"),
            "commute_id": r.get("commute_id"),
            "decision": r.get("decision"),
            "opp_id": r.get("opp_id"),
            "competing_opps_count": r.get("competing_opps_count"),
            "ts": (r["ts"].isoformat()
                      if hasattr(r.get("ts"), "isoformat") else r.get("ts")),
        })
    return {"items": items, "count": len(items)}


# ═══════════════════════════════════════════════════════════════════════
# Phase 9b.1 — Read-only visibility into the pending_rj_extras queue +
# the commute-arrival cooldown clock.  Useful for QA, support debugging,
# and future tooling.  No write endpoints — the only producers are
# `enqueue_commute_arrival_rj_extra` (called from /commute/end) and the
# RJ segment-builder consumer.
# ═══════════════════════════════════════════════════════════════════════
rj_extras_router = APIRouter(prefix="/api/rj", tags=["rj_extras"])


def _serialize_extra(x: dict) -> dict:
    return {
        "extra_id": x.get("extra_id"),
        "kind": x.get("kind"),
        "payload": x.get("payload") or {},
        "queued_at": (x["created_at"].isoformat()
                          if hasattr(x.get("created_at"), "isoformat")
                          else x.get("created_at")),
        "expires_at": (x["expires_at"].isoformat()
                            if hasattr(x.get("expires_at"), "isoformat")
                            else x.get("expires_at")),
    }


@rj_extras_router.get("/me/pending_extras")
async def me_pending_extras(request: Request,
                                      user: dict = Depends(current_user)):
    """Returns the listener's current `pending_rj_extras` queue + the
    cooldown clock for commute-arrival mentions.  Read-only."""
    db = request.app.state.db
    u = await db.users.find_one(
        {"user_id": user["user_id"]},
        {"pending_rj_extras": 1, "last_commute_arrival_mention_at": 1})
    items = [_serialize_extra(x) for x in
                 ((u or {}).get("pending_rj_extras") or [])]
    last_mention = (u or {}).get("last_commute_arrival_mention_at")
    return {
        "user_id": user["user_id"],
        "items": items,
        "count": len(items),
        "last_commute_arrival_mention_at": (
            last_mention.isoformat()
            if hasattr(last_mention, "isoformat") else last_mention),
        "commute_arrival_cooldown_minutes": 30,
    }


admin_rj_router = APIRouter(prefix="/api/admin/rj", tags=["admin_rj"])


@admin_rj_router.get("/pending_extras")
async def admin_pending_extras(request: Request,
                                          _u: dict = Depends(require_admin),
                                          user_id: str = ""):
    """Admin variant — read any user's queue + cooldown clock."""
    if not user_id:
        raise HTTPException(400, "user_id_required")
    db = request.app.state.db
    u = await db.users.find_one(
        {"user_id": user_id},
        {"pending_rj_extras": 1, "last_commute_arrival_mention_at": 1})
    if not u:
        raise HTTPException(404, "user_not_found")
    items = [_serialize_extra(x) for x in
                 (u.get("pending_rj_extras") or [])]
    last_mention = u.get("last_commute_arrival_mention_at")
    return {
        "user_id": user_id,
        "items": items,
        "count": len(items),
        "last_commute_arrival_mention_at": (
            last_mention.isoformat()
            if hasattr(last_mention, "isoformat") else last_mention),
        "commute_arrival_cooldown_minutes": 30,
    }


__all__ = ["commute_router", "system_router", "route_ads_router",
              "rj_extras_router", "admin_rj_router"]
