"""Marketplace Menu API — merchant menu builder (CRUD + AI/file import)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user
from services.marketplace import now, new_id
from services.membership_entitlements import OptionGroupModel, normalize_option_groups

router = APIRouter(prefix="/api/merchant/marketplace/menu", tags=["marketplace-menu"])


async def _my_business(db, user) -> Dict[str, Any]:
    p = await db.marketplace_profiles.find_one({"owner_user_id": user.get("user_id")})
    if not p:
        raise HTTPException(404, {"code": "no_marketplace_profile"})
    return p


def _clean(it: Dict[str, Any]) -> Dict[str, Any]:
    it.pop("_id", None)
    for k in ("created_at", "updated_at"):
        v = it.get(k)
        if hasattr(v, "isoformat"):
            it[k] = v.isoformat()
    return it


class MenuItemBody(BaseModel):
    section: str = Field("Menu", max_length=60)
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=300)
    price_cents: int = Field(..., ge=0, le=1_000_000)
    image_url: Optional[str] = None
    bigpoints: Optional[int] = Field(None, ge=0, le=100000)
    available: bool = True
    option_groups: List[OptionGroupModel] = Field(default_factory=list)
    direct_price_cents: Optional[int] = Field(None, ge=0, le=1_000_000)


def _menu_doc(body: MenuItemBody) -> Dict[str, Any]:
    d = body.model_dump()
    d["option_groups"] = normalize_option_groups(body.option_groups)
    return d


@router.get("")
async def list_menu(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    items = [_clean(i) async for i in db.menu_items.find(
        {"business_id": p["business_id"]}).sort("sort", 1)]
    return {"items": items, "count": len(items)}


@router.post("/items")
async def create_item(body: MenuItemBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    n = await db.menu_items.count_documents({"business_id": p["business_id"]})
    item_id = new_id("mi")
    doc = {"item_id": item_id, "business_id": p["business_id"], "sort": n,
           **_menu_doc(body), "created_at": now(), "updated_at": now()}
    await db.menu_items.insert_one(dict(doc))
    return {"ok": True, "item": _clean(doc)}


@router.patch("/items/{item_id}")
async def update_item(item_id: str, body: MenuItemBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.menu_items.update_one(
        {"item_id": item_id, "business_id": p["business_id"]},
        {"$set": {**_menu_doc(body), "updated_at": now()}})
    if res.matched_count == 0:
        raise HTTPException(404, {"code": "item_not_found"})
    it = await db.menu_items.find_one({"item_id": item_id})
    return {"ok": True, "item": _clean(it)}


@router.delete("/items/{item_id}")
async def delete_item(item_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    res = await db.menu_items.delete_one(
        {"item_id": item_id, "business_id": p["business_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, {"code": "item_not_found"})
    return {"ok": True}


class BulkBody(BaseModel):
    items: List[MenuItemBody]
    replace: bool = False


@router.post("/items/bulk")
async def bulk_items(body: BulkBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_business(db, user)
    if not body.items:
        raise HTTPException(400, {"code": "no_items"})
    if body.replace:
        await db.menu_items.delete_many({"business_id": p["business_id"]})
    base = 0 if body.replace else await db.menu_items.count_documents(
        {"business_id": p["business_id"]})
    docs = []
    for i, it in enumerate(body.items):
        docs.append({"item_id": new_id("mi"), "business_id": p["business_id"],
                     "sort": base + i, **_menu_doc(it),
                     "created_at": now(), "updated_at": now()})
    if docs:
        await db.menu_items.insert_many([dict(d) for d in docs])
    return {"ok": True, "inserted": len(docs)}


class AiImportBody(BaseModel):
    source_type: str = Field(..., description="image|pdf|url")
    url: Optional[str] = None
    file_base64: Optional[str] = None
    filename: Optional[str] = None


@router.post("/import/ai")
async def import_ai(body: AiImportBody, request: Request, user: dict = Depends(current_user)):
    """Parse a menu via AI — returns a PREVIEW list (not yet saved)."""
    db = request.app.state.db
    await _my_business(db, user)
    from services import menu_import as mi
    try:
        if body.source_type == "image":
            if not body.file_base64:
                raise HTTPException(400, {"code": "file_required"})
            items = await mi.import_from_image(body.file_base64)
        elif body.source_type == "pdf":
            if not body.file_base64:
                raise HTTPException(400, {"code": "file_required"})
            items = await mi.import_from_pdf(body.file_base64)
        elif body.source_type == "url":
            if not body.url:
                raise HTTPException(400, {"code": "url_required"})
            items = await mi.import_from_url(body.url)
        else:
            raise HTTPException(400, {"code": "bad_source_type"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, {"code": "ai_import_failed", "detail": str(e)[:200]})
    return {"ok": True, "items": items, "count": len(items)}


class FileImportBody(BaseModel):
    file_base64: str
    filename: str = "menu.xlsx"


@router.post("/import/file")
async def import_file(body: FileImportBody, request: Request, user: dict = Depends(current_user)):
    """Parse an Excel/CSV of products — returns a PREVIEW list (not yet saved)."""
    db = request.app.state.db
    await _my_business(db, user)
    from services import menu_import as mi
    try:
        items = mi.import_from_spreadsheet(body.file_base64, body.filename)
    except Exception as e:
        raise HTTPException(400, {"code": "file_parse_failed", "detail": str(e)[:200]})
    return {"ok": True, "items": items, "count": len(items)}


@router.post("/items/{item_id}/photo")
async def upload_photo(item_id: str, request: Request, user: dict = Depends(current_user)):
    """Merchant uploads a photo (base64) for a menu item."""
    db = request.app.state.db
    p = await _my_business(db, user)
    it = await db.menu_items.find_one({"item_id": item_id, "business_id": p["business_id"]})
    if not it:
        raise HTTPException(404, {"code": "item_not_found"})
    body = await request.json()
    b64 = body.get("file_base64")
    if not b64:
        raise HTTPException(400, {"code": "file_required"})
    from services import menu_photos as mp
    try:
        url = mp.save_base64(item_id, b64, body.get("ext", "png"))
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    await db.menu_items.update_one({"item_id": item_id},
                                   {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


@router.post("/items/{item_id}/photo/ai")
async def ai_photo(item_id: str, request: Request, user: dict = Depends(current_user)):
    """Generate an AI dish photo (Nano Banana) for a menu item."""
    db = request.app.state.db
    p = await _my_business(db, user)
    it = await db.menu_items.find_one({"item_id": item_id, "business_id": p["business_id"]})
    if not it:
        raise HTTPException(404, {"code": "item_not_found"})
    from services import menu_photos as mp
    try:
        url = await mp.generate_ai(item_id, name=it.get("name", ""),
                                   description=it.get("description") or "",
                                   section=it.get("section") or "")
    except Exception as e:
        raise HTTPException(502, {"code": "ai_photo_failed", "detail": str(e)[:200]})
    await db.menu_items.update_one({"item_id": item_id},
                                   {"$set": {"image_url": url, "updated_at": now()}})
    return {"ok": True, "image_url": url}


__all__ = ["router"]
