"""Phase 8b — public (no-auth) endpoints for game landing pages.

Mounted at /api/public/game/{slug}.  Returns the safe campaign view +
render config exactly like /api/games_v2/campaigns/{id} but without
auth and keyed by slug.  Also serves the QR PNG.
"""
from __future__ import annotations

import base64
from typing import Optional

import qrcode
from fastapi import APIRouter, HTTPException, Request, Response
from io import BytesIO

games_v2_public_router = APIRouter(prefix="/api/public/game", tags=["games_v2_public"])


@games_v2_public_router.get("/{slug}")
async def public_landing(slug: str, request: Request):
    db = request.app.state.db
    landing = await db.game_landing_pages.find_one({"slug": slug, "active": True})
    if not landing:
        raise HTTPException(404, "landing_not_found")
    c = await db.game_campaigns.find_one(
        {"campaign_id": landing["campaign_id"], "status": "active"})
    if not c:
        raise HTTPException(404, "campaign_not_active")
    prizes = await db.game_prizes.find(
        {"campaign_id": c["campaign_id"], "active": True}
    ).to_list(20)
    # Strip leaks (mirror /campaigns/{id} projection)
    safe_prizes = [{"title": p["title"], "description": p.get("description"),
                          "prize_type": p["prize_type"],
                          "value_amount": p.get("value_amount"),
                          "value_currency": p.get("value_currency"),
                          "redemption_method": p["redemption_method"],
                          "in_stock": int(p.get("inventory_remaining") or 0) > 0}
                        for p in prizes]
    # Track impression (anonymous)
    from services.games_v2 import _new_id, _now
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"),
        "campaign_id": c["campaign_id"],
        "user_id": None,
        "event_type": "impression",
        "source_context_json": {
            "source": "public_landing",
            "slug": slug,
            "referrer": request.headers.get("referer"),
            "ua": request.headers.get("user-agent"),
        },
        "metadata_json": {"slug": slug},
        "ts": _now(),
    })
    return {
        "slug": slug,
        "campaign_id": c["campaign_id"],
        "template_id": c["template_id"],
        "title": c["title"],
        "description": c.get("description"),
        "sponsor_name": c.get("sponsor_name"),
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "brand_colors_json": c.get("brand_colors_json") or {},
        "open_to_all": bool(c.get("open_to_all")),
        "prizes": safe_prizes,
        "landing_config": landing.get("landing_page_config_json") or {},
    }


@games_v2_public_router.get("/{slug}/qr.png")
async def public_landing_qr(slug: str, request: Request):
    db = request.app.state.db
    landing = await db.game_landing_pages.find_one({"slug": slug})
    if not landing:
        raise HTTPException(404, "slug_not_found")
    # Resolve a stable public URL (frontend origin) for the QR target
    public_origin = request.headers.get("x-forwarded-host") or request.url.netloc
    scheme = "https"
    target = f"{scheme}://{public_origin}/play/{slug}"
    qr = qrcode.QRCode(version=2, box_size=10, border=2)
    qr.add_data(target)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                       headers={"Cache-Control": "public, max-age=86400"})


__all__ = ["games_v2_public_router"]
