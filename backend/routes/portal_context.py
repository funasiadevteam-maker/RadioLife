"""Phase PORTAL.0 — Unified access context (AccessResolver source of truth).

Read-only aggregation of the current user's platform role + ALL merchant /
advertiser memberships, per-workspace permissions, launch/setup status and
the recommended post-login destination.

Design-agnostic by contract: the backend never knows or cares which UI
variant (legacy / classic_b / radiolife / new_look_v2) is active. This
endpoint reuses existing collections (`businesses`, `merchant_locations`,
`advertiser_staff`) and the shared merchant RBAC map — NO new business
logic, NO new permissions. The frontend PortalRoleRouter + WorkspaceSwitcher
consume it; presentation is chosen per active design variant on the client.

    GET /api/portal/context
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from auth import current_user
from services.merchant_rbac_service import permissions_for_role, STAFF_ROLES

logger = logging.getLogger("bigfm.portal")
router = APIRouter(prefix="/api", tags=["portal"])

# Merchant statuses that mean "not yet live" → land on the status/setup screen.
PRE_APPROVAL = {"draft", "stripe_onboarding_pending", "verification_pending",
                                "submitted", "rejected"}

# Auto-routing priority when a user belongs to several workspaces
# (lower number = higher priority).
_PRIORITY = {"admin": 0, "owner": 1, "manager": 2, "marketing": 3,
                          "analytics_only": 4, "cashier": 5, "advertiser": 6}


def _biz_id(b: dict) -> str:
    return b.get("business_id") or b.get("_id")


def _merchant_route(role: str, status: str | None, mid: str) -> str:
    """Design-independent route semantics (no /v2/* variants)."""
    if role == "cashier":
        return "/merchant/cashier"
    if role in ("owner", "manager") and status in PRE_APPROVAL:
        return f"/merchant/status?merchant_id={mid}"
    return "/merchant/dashboard"


@router.get("/portal/context")
async def portal_context(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user.get("user_id")
    is_admin = user.get("role") == "admin" or bool(user.get("is_admin"))

    workspaces: list[dict] = []

    # ── Platform admin ────────────────────────────────────────────
    if is_admin:
        workspaces.append({
            "type":              "admin",
            "id":                  "platform",
            "name":              "RadioLife Admin",
            "logo_url":        None,
            "role":              "admin",
            "permissions":  sorted(permissions_for_role("admin")),
            "status":          "active",
            "route":            "/admin",
        })

    # ── Owned merchants ───────────────────────────────────────────
    owned_ids: set[str] = set()
    async for b in db.businesses.find({"owner_user_id": uid}):
        mid = _biz_id(b)
        owned_ids.add(mid)
        status = b.get("merchant_status") or "draft"
        loc_count = await db.merchant_locations.count_documents(
            {"merchant_id": mid, "active": True})
        workspaces.append({
            "type":                                "merchant",
            "id":                                    mid,
            "name":                                b.get("name"),
            "logo_url":                          b.get("logo_url"),
            "role":                                "owner",
            "permissions":                    sorted(permissions_for_role("owner")),
            "merchant_status":              status,
            "onboarding_step":              b.get("onboarding_step") or 1,
            "locations_count":              loc_count,
            "stripe_charges_enabled": bool(b.get("stripe_charges_enabled")),
            "status":                              status,
            "route":                                _merchant_route("owner", status, mid),
        })

    # ── Merchants where the user is active staff ──────────────────
    async for b in db.businesses.find(
            {"staff_users": {"$elemMatch": {"user_id": uid, "active": True}}}):
        mid = _biz_id(b)
        if mid in owned_ids:
            continue
        row = next((s for s in (b.get("staff_users") or [])
                                if s.get("user_id") == uid and s.get("active", True)), None)
        role = (row or {}).get("role")
        if role not in STAFF_ROLES:
            continue
        status = b.get("merchant_status") or "active"
        workspaces.append({
            "type":                    "merchant",
            "id":                        mid,
            "name":                    b.get("name"),
            "logo_url":              b.get("logo_url"),
            "role":                    role,
            "permissions":        sorted(permissions_for_role(role)),
            "merchant_status":  status,
            "staff_user_id":      (row or {}).get("staff_user_id"),
            "status":                  status,
            "route":                    _merchant_route(role, status, mid),
        })

    # ── Advertiser memberships (best-effort; schema may vary) ─────
    try:
        async for a in db.advertiser_staff.find({"user_id": uid}):
            if a.get("active") is False:
                continue
            adv_id = a.get("advertiser_id")
            adv = (await db.advertisers.find_one({"advertiser_id": adv_id})
                          if adv_id else None) or {}
            workspaces.append({
                "type":                "advertiser",
                "id":                    adv_id,
                "name":                adv.get("name") or "Advertiser",
                "logo_url":          adv.get("logo_url"),
                "role":                a.get("role") or "advertiser",
                "permissions":    [],
                "status":              "active",
                "route":                "/advertiser",
            })
    except Exception:
        logger.debug("[portal] advertiser aggregation skipped", exc_info=True)

    # ── Recommended post-login destination ────────────────────────
    ranked = sorted(workspaces, key=lambda w: _PRIORITY.get(w.get("role"), 9))
    recommended_route = ranked[0]["route"] if ranked else "/"
    recommended_workspace_id = ranked[0]["id"] if ranked else None
    needs_choice = len(ranked) > 1

    return {
        "user": {
            "user_id": uid,
            "email":      user.get("email"),
            "name":      user.get("name") or user.get("display_name"),
            "role":      user.get("role") or "user",
        },
        "platform_admin":                    is_admin,
        "workspaces":                          workspaces,
        "workspace_count":                len(workspaces),
        "recommended_route":              recommended_route,
        "recommended_workspace_id": recommended_workspace_id,
        "needs_workspace_choice":      needs_choice,
        "preview_access": is_admin or any(
            w["type"] == "merchant"
            and w.get("merchant_status") in ("approved", "active")
            for w in workspaces),
    }


__all__ = ["router"]
