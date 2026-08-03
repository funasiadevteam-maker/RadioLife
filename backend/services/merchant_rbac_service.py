"""Phase MER.2 — Merchant Staff RBAC helper.

Central role→permission map + resolver helpers used by all merchant
route files.  Existing owner check remains authoritative — this file
ADDS staff-role permission granting alongside it.
"""
from __future__ import annotations

from typing import Optional
from fastapi import HTTPException


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "can_invite_staff", "can_edit_profile", "can_create_links",
        "can_refund", "can_view_analytics", "can_redeem_coupons",
        "can_edit_hours", "can_view_payouts", "can_manage_stripe",
        "can_view_transactions",
    },
    "manager": {
        "can_invite_staff", "can_edit_profile", "can_create_links",
        "can_refund", "can_view_analytics", "can_redeem_coupons",
        "can_edit_hours", "can_view_payouts", "can_view_transactions",
    },
    "cashier": {
        "can_redeem_coupons", "can_view_analytics_limited",
    },
    "marketing": {
        "can_create_links", "can_view_analytics", "can_view_transactions",
    },
    "analytics_only": {
        "can_view_analytics", "can_view_payouts", "can_view_transactions",
    },
}

STAFF_ROLES = {"manager", "cashier", "marketing", "analytics_only"}


def _is_admin(user: dict) -> bool:
    return bool(user.get("role") == "admin" or user.get("is_admin"))


async def get_user_role_for_merchant(db, *, user: dict,
                                                                            merchant_id: Optional[str] = None,
                                                                            biz: Optional[dict] = None) -> Optional[str]:
    """Return `owner`, `admin`, one of STAFF_ROLES, or None.

    Priority:  admin > owner > staff (active) > None
    """
    if _is_admin(user):
        return "admin"
    if biz is None:
        biz = await db.businesses.find_one({"$or": [
            {"business_id": merchant_id}, {"_id": merchant_id}]})
        if not biz:
            return None
    uid = user.get("user_id")
    if biz.get("owner_user_id") == uid:
        return "owner"
    for s in (biz.get("staff_users") or []):
        if s.get("user_id") == uid and s.get("active", True):
            r = s.get("role")
            if r in STAFF_ROLES:
                return r
    return None


def permissions_for_role(role: Optional[str]) -> set[str]:
    if not role:
        return set()
    if role == "admin":
        # Admin god mode — union of all role perms
        out: set[str] = set()
        for perms in ROLE_PERMISSIONS.values():
            out |= perms
        return out
    return set(ROLE_PERMISSIONS.get(role) or set())


async def resolve_merchant_with_role(db, *, merchant_id: str, user: dict,
                                                                            permission: Optional[str] = None,
                                                                            allow_any_staff: bool = False,
                                                                            owner_only: bool = False) -> tuple[dict, str]:
    """Load merchant + verify user can access it (raises 403 otherwise).

    Access rules:
      - `permission=None, allow_any_staff=False, owner_only=False`
                                              → OWNER or ADMIN only (backwards-compat default)
      - `permission="can_xyz"`
                                              → OWNER, ADMIN, or a staff role that includes the perm
      - `allow_any_staff=True`
                                              → OWNER, ADMIN, or ANY active staff role (used for the
                                                Overview endpoint where every role can peek at KPIs)
      - `owner_only=True`
                                              → OWNER or ADMIN only (explicit)

    Returns (biz_doc, role).
    """
    biz = await db.businesses.find_one({"$or": [
        {"business_id": merchant_id}, {"_id": merchant_id}]})
    if not biz:
        raise HTTPException(404, "merchant_not_found")

    role = await get_user_role_for_merchant(db, user=user, biz=biz)
    if role is None:
        raise HTTPException(403, {"code": "not_merchant_member",
                                                          "detail": "You don\u2019t have access to this merchant."})

    if owner_only and role not in ("owner", "admin"):
        raise HTTPException(403, {"code": "owner_only",
                                                          "detail": "Only the owner or an admin can perform this action."})

    if permission:
        perms = permissions_for_role(role)
        if permission not in perms:
            raise HTTPException(403, {"code": "missing_permission",
                                                              "detail": f"Your role ({role}) is missing {permission}."})
    elif not allow_any_staff and role not in ("owner", "admin"):
        # Default: owner-only when no permission specified
        raise HTTPException(403, {"code": "owner_only",
                                                          "detail": "Only the owner or an admin can perform this action."})
    return biz, role


__all__ = [
    "ROLE_PERMISSIONS", "STAFF_ROLES",
    "get_user_role_for_merchant",
    "permissions_for_role",
    "resolve_merchant_with_role",
]
