"""Unified Gift Inbox — aggregates gifts RECEIVED by the current user across
gift cards, packages, and memberships so the wallet can show one "Gifts
received" section. Read-only; redemption still happens on each type's own
endpoint (the item carries the route + action label to get there).
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from auth import current_user

router = APIRouter(prefix="/api/shop/gifts", tags=["marketplace-gifts"])


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


async def _buyer_names(db, buyer_ids: List[str]) -> Dict[str, str]:
    ids = [b for b in set(buyer_ids) if b]
    if not ids:
        return {}
    out: Dict[str, str] = {}
    async for u in db.users.find({"user_id": {"$in": ids}},
                                 {"user_id": 1, "display_name": 1, "name": 1}):
        out[u["user_id"]] = u.get("display_name") or u.get("name") or "A friend"
    return out


@router.get("/received")
async def received_gifts(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    email = (user.get("email") or "").lower().strip()
    match = {"$or": [{"owner_user_id": uid}, {"user_id": uid}]}
    if email:
        match["$or"].append({"gifted_to_email": email})

    raw: List[Dict[str, Any]] = []

    # Gift cards
    async for c in db.gift_cards.find(
            {"$or": [{"owner_user_id": uid}, {"gifted_to_email": email}] if email
             else [{"owner_user_id": uid}]}).sort("created_at", -1):
        if c.get("buyer_user_id") and c.get("buyer_user_id") != uid:
            raw.append({
                "kind": "giftcard", "id": c.get("card_id"),
                "title": c.get("sponsor_name") or "Gift card",
                "subtitle": f"${(c.get('balance_cents', 0) / 100):.0f} balance",
                "buyer_user_id": c.get("buyer_user_id"),
                "message": c.get("message"), "created_at": _iso(c.get("created_at")),
                "revealed": bool(c.get("revealed")),
                "route": "/wallet", "action": "View card",
            })

    # Packages
    p_or: List[Dict[str, Any]] = [{"user_id": uid}]
    if email:
        p_or.append({"gifted_to_email": email})
    async for pk in db.packages.find(
            {"status": {"$in": ["active", "used_up"]}, "$or": p_or}).sort("created_at", -1):
        if pk.get("is_gift") and pk.get("buyer_user_id") != uid:
            raw.append({
                "kind": "package", "id": pk.get("purchase_id"),
                "title": pk.get("name") or "Package",
                "subtitle": f"{pk.get('credits_remaining', 0)} of {pk.get('credits_total', 0)} credits left",
                "buyer_user_id": pk.get("buyer_user_id"),
                "message": pk.get("gift_message"), "created_at": _iso(pk.get("created_at")),
                "sponsor_name": pk.get("sponsor_name"),
                "route": "/wallet", "action": "View package",
            })

    # Memberships
    async for m in db.memberships.find(
            {"status": "active", "$or": p_or}).sort("created_at", -1):
        if m.get("is_gift") and m.get("buyer_user_id") != uid:
            raw.append({
                "kind": "membership", "id": m.get("membership_id"),
                "title": m.get("plan_name") or "Membership",
                "subtitle": m.get("sponsor_name") or "",
                "buyer_user_id": m.get("buyer_user_id"),
                "message": m.get("gift_message"), "created_at": _iso(m.get("created_at")),
                "sponsor_name": m.get("sponsor_name"),
                "route": "/shop/memberships", "action": "View membership",
            })

    names = await _buyer_names(db, [r["buyer_user_id"] for r in raw])
    for r in raw:
        r["from_name"] = names.get(r.get("buyer_user_id"), "A friend")
        r.pop("buyer_user_id", None)
    raw.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"items": raw, "count": len(raw)}


__all__ = ["router"]
