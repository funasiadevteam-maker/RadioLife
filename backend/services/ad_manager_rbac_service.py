"""Phase ADMOD.1 — Ad Manager role RBAC helper.

Small dependency-style resolver: passes through admin OR ad_manager
users, 403s everyone else.  Used across `/api/ad-review/*` routes.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from auth import current_user


AD_MANAGER_ROLES = ("admin", "ad_manager")


async def require_ad_manager(user: dict = Depends(current_user)) -> dict:
    role = (user or {}).get("role")
    if role in AD_MANAGER_ROLES:
        return user
    raise HTTPException(403, {"code": "not_ad_manager_or_admin"})


def is_ad_manager(user: dict) -> bool:
    return (user or {}).get("role") in AD_MANAGER_ROLES


__all__ = ["require_ad_manager", "is_ad_manager", "AD_MANAGER_ROLES"]
