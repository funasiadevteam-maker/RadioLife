"""Phase 12d — Admin Integrations status + probe routes.

Lives under `/api/admin/integrations/*`. The legacy GAM admin routes
remain at `/api/admin/ads/integrations/gam`; we keep both surfaces.

Exposes:
  GET  /api/admin/integrations/status
  GET  /api/admin/integrations/maps/probe
  POST /api/admin/integrations/gam/probe
  GET  /api/admin/integrations/sendgrid/quota
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_admin
from services import integration_health as ih
from services import delivery as delivery_svc

logger = logging.getLogger("bigfm.integrations")

admin_integrations_router = APIRouter(prefix="/api/admin/integrations",
                                                          tags=["admin_integrations"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


@admin_integrations_router.get("/status")
async def integrations_status(request: Request,
                                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    snapshot = await ih.get_all_health(db)
    return {"as_of": _now().isoformat(), "items": snapshot}


# ─── Maps probe (re-runs the 4-API probe in services.maps_client) ─────
@admin_integrations_router.get("/maps/probe")
async def maps_probe(request: Request,
                              _u: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        from services.maps_client import (get_maps_client,
                                                            MockMapsClient)
    except ImportError:
        raise HTTPException(500, "maps_client import failed")
    client = get_maps_client(db)
    if isinstance(client, MockMapsClient):
        api_health = {}
        await ih.record_call(db, "maps", success=False,
                                     error="mock_client_active",
                                     detail={"api_health": api_health,
                                                "client": client.name})
        await ih.recompute_mode(db, "maps")
        return {"as_of": _now().isoformat(),
                  "client": client.name,
                  "api_health": api_health,
                  "mode_after_probe": "mock"}
    api_health = await client.probe_apis()
    any_ok = any(v == "ok" for v in api_health.values())
    all_ok = api_health and all(v == "ok" for v in api_health.values())
    success = bool(all_ok)
    await ih.record_call(
        db, "maps", success=success,
        error=None if success else ("partial_403" if any_ok
                                                 else "all_failed"),
        detail={"api_health": api_health,
                  "client": getattr(client, "name", "google")})
    await ih.recompute_mode(db, "maps")
    return {"as_of": _now().isoformat(),
              "client": getattr(client, "name", "google"),
              "api_health": api_health,
              "mode_after_probe": (await ih.get_health(db, "maps"))["mode"]}


# ─── GAM probe ─────────────────────────────────────────────────────────
@admin_integrations_router.post("/gam/probe")
async def gam_probe(request: Request,
                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    from services import gam_client as gc

    out = await gc.test_connection(db)
    # Distinguish: creds OK + no_line_items → degraded; creds OK + ok → live;
    # creds missing → mock.
    if not out.get("ok"):
        await ih.record_call(db, "gam", success=False,
                                     error=str(out.get("reason"))[:200],
                                     detail=out)
        mode = await ih.recompute_mode(db, "gam")
        return {"as_of": _now().isoformat(),
                  "result": out, "mode_after_probe": mode}
    # Soap reachable. Check line-item availability via the existing
    # backfill helper using a synthetic ctx — empty result means "creds
    # work, but no inventory" → degraded.
    fake_user = {"user_id": "probe", "preference_vector": {}}
    fake_session = {"_id": "probe", "session_id": "probe"}
    fake_ctx = {"market": "dubai", "daypart": "all",
                  "channel_slug": "probe"}
    bid = await gc.call_gam_for_backfill(db, user=fake_user,
                                                       session=fake_session,
                                                       ctx=fake_ctx)
    if bid is None:
        await ih.record_call(
            db, "gam", success=False,
            error="no_matching_line_item",
            detail={**out, "note": (
                "GAM SOAP reachable but no line items "
                "trafficked — see human checklist")})
        mode = await ih.recompute_mode(db, "gam")
        return {"as_of": _now().isoformat(),
                  "result": out, "line_items": "none_trafficked",
                  "mode_after_probe": mode}
    await ih.record_call(db, "gam", success=True,
                                 detail={**out, "line_items": "ok"})
    mode = await ih.recompute_mode(db, "gam")
    return {"as_of": _now().isoformat(),
              "result": out, "line_items": "ok",
              "mode_after_probe": mode}


# ─── SendGrid quota viewer ────────────────────────────────────────────
@admin_integrations_router.get("/sendgrid/quota")
async def sendgrid_quota(request: Request,
                                    _u: dict = Depends(require_admin)):
    db = request.app.state.db
    quota = await delivery_svc.get_sendgrid_quota_snapshot(db)
    return {"as_of": _now().isoformat(), **quota}


# ─── Phase 13e — Apple SIWA / APNs probes + test push ──────────────────
@admin_integrations_router.post("/apple_siwa/probe")
async def apple_siwa_probe(request: Request,
                                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    from services import apple_siwa as siwa
    out = await siwa.probe()
    await ih.record_call(db, "apple_siwa", success=bool(out.get("ok")),
                                  error=out.get("error"),
                                  detail={k: v for k, v in out.items()
                                              if k != "ok"})
    mode = await ih.recompute_mode(db, "apple_siwa")
    return {"as_of": _now().isoformat(), "result": out,
              "mode_after_probe": mode}


@admin_integrations_router.post("/apple_apns/probe")
async def apple_apns_probe(request: Request,
                                          _u: dict = Depends(require_admin)):
    db = request.app.state.db
    from services import apns
    out = await apns.probe()
    await ih.record_call(db, "apple_apns", success=bool(out.get("ok")),
                                  error=out.get("error"),
                                  detail={k: v for k, v in out.items()
                                              if k != "ok"})
    mode = await ih.recompute_mode(db, "apple_apns")
    return {"as_of": _now().isoformat(), "result": out,
              "mode_after_probe": mode}


@admin_integrations_router.post("/apple_apns/test")
async def apple_apns_test(request: Request,
                                        admin: dict = Depends(require_admin)):
    """Send a 'BigFM connection test' push to the admin's own registered
    APNs-native tokens (sandbox env). Returns per-token results."""
    db = request.app.state.db
    from services import apns
    if not apns.is_configured():
        return {"sent": 0, "results": [],
                  "note": "APNs not configured — set APPLE_TEAM_ID / "
                                "APPLE_KEY_ID / APPLE_KEY_PATH / APPLE_BUNDLE_ID."}
    cur = db.user_push_tokens.find({
        "user_id": admin["user_id"], "active": True,
        "device_type": "apns_native"})
    results = []
    async for t in cur:
        r = await apns.send_push(
            device_token=t["expo_push_token"],
            title="BigFM connection test",
            body="If you see this, APNs direct is live in sandbox.",
            deep_link="/")
        results.append({"token_tail": t["expo_push_token"][-6:],
                              **r})
    return {"sent": len(results), "env": apns.apns_env(),
              "results": results}
