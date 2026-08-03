"""Phase K.7 — Marketing assets read endpoint.

`GET /api/marketing/assets` returns a `{key → image_url}` map for every
asset in `marketing_assets`.  Used by the landing page sections and the
game cards to look up their AI-generated artwork.

Anonymous-safe.  Cache for 60 seconds on the client.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api/marketing", tags=["marketing"])


@router.get("/assets")
async def list_marketing_assets(request: Request,
                                                                category: str | None = None,
                                                                response: Response = None) -> dict:
    db = request.app.state.db
    q: dict = {}
    if category:
        q["category"] = category
    items = [d async for d in db.marketing_assets.find(q,
                              {"_id": 0, "key": 1, "category": 1,
                                "image_url": 1, "updated_at": 1})]
    # Build a fast `{key: url}` lookup for the SPA.
    by_key = {it["key"]: it.get("image_url") for it in items}
    if response is not None:
        response.headers["Cache-Control"] = "public, max-age=60"
    return {"count": len(items), "items": items, "by_key": by_key}
