"""Phase AD.6 — Advertiser Staff RBAC helper.

Mirrors `merchant_rbac_service.py` for the advertiser side.  The
`advertisers_v2` collection is extended (schemaless additive) with
`staff_users: [{staff_user_id, email, role, active, invited_at,
invited_by, accepted_at}]`.

Roles
─────
    owner                    (implicit — `advertisers_v2.owner_user_id`)
    manager              (can invite staff, redeem, view analytics)
    redemption_staff (redeem + view scan history)
    analytics_only    (view analytics only — no redemption)

Admin is god-mode across every advertiser.
"""
from __future__ import annotations

from typing import Optional
from fastapi import HTTPException


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        "can_invite_staff", "can_edit_profile", "can_redeem",
        "can_view_analytics", "can_view_scan_history", "can_manage_campaigns",
    },
    "manager": {
        "can_invite_staff", "can_edit_profile", "can_redeem",
        "can_view_analytics", "can_view_scan_history", "can_manage_campaigns",
    },
    "redemption_staff": {
        "can_redeem", "can_view_scan_history",
    },
    "analytics_only": {
        "can_view_analytics",
    },
}

STAFF_ROLES = {"manager", "redemption_staff", "analytics_only"}


def _is_admin(user: dict) -> bool:
    return bool(user.get("role") == "admin" or user.get("is_admin"))


async def get_user_role_for_advertiser(db, *, user: dict,
                                                                                          advertiser_id: Optional[str] = None,
                                                                                          adv: Optional[dict] = None) -> Optional[str]:
    """Return `owner`, `admin`, one of STAFF_ROLES, or None.

    Priority: admin > owner > active staff > None.
    """
    if _is_admin(user):
        return "admin"
    if adv is None:
        adv = await db.advertisers_v2.find_one(
            {"advertiser_id": advertiser_id})
        if not adv:
            return None
    uid = user.get("user_id")
    if adv.get("owner_user_id") == uid:
        return "owner"
    for s in (adv.get("staff_users") or []):
        if s.get("staff_user_id") == uid and s.get("active", True):
            r = s.get("role")
            if r in STAFF_ROLES:
                return r
    return None


def permissions_for_role(role: Optional[str]) -> set[str]:
    if not role:
        return set()
    if role == "admin":
        out: set[str] = set()
        for perms in ROLE_PERMISSIONS.values():
            out |= perms
        return out
    return set(ROLE_PERMISSIONS.get(role) or set())


async def resolve_advertiser_with_role(db, *, advertiser_id: str, user: dict,
                                                                                              permission: Optional[str] = None,
                                                                                              allow_any_staff: bool = False,
                                                                                              owner_only: bool = False) -> tuple[dict, str]:
    """Load advertiser + verify user can access it (raises 403 otherwise).

    Same contract as `merchant_rbac_service.resolve_merchant_with_role`.
    Returns `(advertiser_doc, role)`.
    """
    adv = await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})
    if not adv:
        raise HTTPException(404, {"code": "advertiser_not_found"})

    role = await get_user_role_for_advertiser(db, user=user, adv=adv)
    if role is None:
        raise HTTPException(403, {"code": "not_advertiser_member",
                                                          "detail": "You don\u2019t have access to this advertiser."})

    if owner_only and role not in ("owner", "admin"):
        raise HTTPException(403, {"code": "owner_only",
                                                          "detail": "Only the owner or an admin can perform this action."})

    if permission:
        perms = permissions_for_role(role)
        if permission not in perms:
            raise HTTPException(403, {"code": "missing_permission",
                                                              "detail": f"Your role ({role}) is missing {permission}."})
    elif not allow_any_staff and role not in ("owner", "admin"):
        raise HTTPException(403, {"code": "owner_only",
                                                          "detail": "Only the owner or an admin can perform this action."})
    return adv, role


async def list_user_advertisers(db, *, user: dict) -> list[dict]:
    """Return every advertiser this user can access (owner or active staff).
    Admins get everything.  Used to power the shell's advertiser switcher."""
    uid = user.get("user_id")
    if _is_admin(user):
        return await db.advertisers_v2.find({}).sort(
            [("created_at", -1)]).to_list(200)
    return await db.advertisers_v2.find({
        "$or": [
            {"owner_user_id": uid},
            {"staff_users": {"$elemMatch": {"staff_user_id": uid,
                                                                                      "active": True}}},
        ]
    }).sort([("created_at", -1)]).to_list(200)


__all__ = [
    "ROLE_PERMISSIONS", "STAFF_ROLES",
    "get_user_role_for_advertiser",
    "permissions_for_role",
    "resolve_advertiser_with_role",
    "list_user_advertisers",
]
