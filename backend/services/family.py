"""Phase 6 — Family plan seat manager.

Each premium_family billing root holds a seat pool (default 5). Members are
linked via `users.family_root_user_id` and inherit `is_premium=true` with
`premium_source="family_seat"` while attached. Removing a seat or revoking
the root's subscription cascades to immediate `is_premium=false` for seats.

Seat add/remove is a pure Mongo state change — no Stripe charge fires
(family plan is a flat 5-seat price). Stripe billing on the root is
handled by the normal change_plan flow.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("bigfm.family")

INVITE_TTL_DAYS = 7


async def ensure_family_indexes(db) -> None:
    await db.family_invites.create_index("token", unique=True)
    await db.family_invites.create_index([("root_user_id", 1), ("status", 1)])
    await db.family_invites.create_index("expires_at",
                                           expireAfterSeconds=INVITE_TTL_DAYS * 86400)
    await db.users.create_index("family_root_user_id", sparse=True)


async def family_state(db, root_user_id: str) -> dict:
    """Returns the family billing state visible to the root user."""
    root = await db.users.find_one({"user_id": root_user_id},
                                       {"family_seats_total": 1, "family_seats_used": 1,
                                        "subscription": 1, "_id": 0}) or {}
    seats_total = int(root.get("family_seats_total") or 0)
    seats_used = int(root.get("family_seats_used") or 0)
    members = []
    if seats_total:
        cur = db.users.find({"family_root_user_id": root_user_id},
                              {"user_id": 1, "email": 1, "name": 1, "_id": 0})
        async for u in cur:
            members.append({k: u.get(k) for k in ("user_id", "email", "name")})
    pending = []
    if seats_total:
        cur = db.family_invites.find({"root_user_id": root_user_id, "status": "pending"},
                                         {"_id": 0})
        async for inv in cur:
            pending.append({"token": inv["token"], "email": inv.get("email"),
                              "invited_at": inv["invited_at"].isoformat() if inv.get("invited_at") else None,
                              "expires_at": inv["expires_at"].isoformat() if inv.get("expires_at") else None})
    return {
        "is_family_root": seats_total > 0,
        "seats_total": seats_total, "seats_used": seats_used,
        "seats_remaining": max(0, seats_total - seats_used),
        "members": members, "pending_invites": pending,
    }


async def invite_family_member(db, root_user_id: str, email: str) -> dict:
    root = await db.users.find_one({"user_id": root_user_id},
                                       {"family_seats_total": 1, "family_seats_used": 1,
                                        "subscription": 1, "_id": 0})
    if not root:
        raise ValueError("root user not found")
    seats_total = int(root.get("family_seats_total") or 0)
    seats_used = int(root.get("family_seats_used") or 0)
    if seats_total < 2:
        raise ValueError("not on a family plan")
    if seats_used >= seats_total:
        raise ValueError("seat_cap_reached")
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("email required")
    # If a pending invite already exists for this email + root, return it
    existing = await db.family_invites.find_one({
        "root_user_id": root_user_id, "email": email, "status": "pending",
    })
    if existing:
        return {"token": existing["token"], "email": email,
                "expires_at": existing["expires_at"].isoformat(),
                "already_invited": True}
    token = "fam_" + secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    await db.family_invites.insert_one({
        "_id": token, "token": token, "root_user_id": root_user_id,
        "email": email, "status": "pending",
        "invited_at": now,
        "expires_at": now + timedelta(days=INVITE_TTL_DAYS),
    })
    return {"token": token, "email": email,
            "expires_at": (now + timedelta(days=INVITE_TTL_DAYS)).isoformat(),
            "already_invited": False}


async def accept_family_invite(db, accepting_user: dict, token: str) -> dict:
    inv = await db.family_invites.find_one({"token": token})
    if not inv:
        raise ValueError("invite not found")
    if inv.get("status") != "pending":
        raise ValueError(f"invite is {inv.get('status')}")
    now = datetime.now(timezone.utc)
    expires_at = inv.get("expires_at")
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < now:
        await db.family_invites.update_one({"token": token},
                                              {"$set": {"status": "expired"}})
        raise ValueError("invite expired")
    uid = accepting_user["user_id"]
    if uid == inv["root_user_id"]:
        raise ValueError("cannot accept your own invite")
    # User must not already be a member
    if accepting_user.get("family_root_user_id"):
        raise ValueError("already on a family plan")
    # Atomic seat increment + write membership
    res = await db.users.find_one_and_update(
        {"user_id": inv["root_user_id"],
         "$expr": {"$lt": [{"$ifNull": ["$family_seats_used", 0]},
                              {"$ifNull": ["$family_seats_total", 0]}]}},
        {"$inc": {"family_seats_used": 1}},
    )
    if not res:
        await db.family_invites.update_one({"token": token},
                                              {"$set": {"status": "cap_reached"}})
        raise ValueError("seats_full")
    await db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "family_root_user_id": inv["root_user_id"],
            "is_premium": True,
            "premium_tier": "premium",
            "premium_source": "family_seat",
            "family_joined_at": now,
        }},
    )
    await db.family_invites.update_one(
        {"token": token},
        {"$set": {"status": "accepted",
                   "accepted_by_user_id": uid,
                   "accepted_at": now}},
    )
    return {"ok": True, "root_user_id": inv["root_user_id"],
            "user_id": uid, "accepted_at": now.isoformat()}


async def remove_family_member(db, root_user_id: str,
                                  member_user_id: str) -> dict:
    member = await db.users.find_one({"user_id": member_user_id},
                                          {"family_root_user_id": 1,
                                           "premium_source": 1, "_id": 0})
    if not member:
        raise ValueError("member not found")
    if member.get("family_root_user_id") != root_user_id:
        raise ValueError("not your family member")
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"user_id": member_user_id},
        {"$set": {
            "is_premium": False,
            "premium_tier": None,
            "premium_source": None,
            "family_root_user_id": None,
            "family_removed_at": now,
        }},
    )
    await db.users.update_one(
        {"user_id": root_user_id},
        {"$inc": {"family_seats_used": -1}},
    )
    return {"ok": True, "removed_user_id": member_user_id}


async def cascade_family_revoke(db, root_user_id: str) -> int:
    """When the billing root cancels for non-payment, revoke all seat members.
    Returns number of members revoked."""
    now = datetime.now(timezone.utc)
    res = await db.users.update_many(
        {"family_root_user_id": root_user_id, "is_premium": True},
        {"$set": {
            "is_premium": False, "premium_tier": None,
            "premium_source": None, "family_root_user_id": None,
            "family_removed_at": now,
            "family_removal_reason": "root_subscription_canceled",
        }},
    )
    await db.users.update_one(
        {"user_id": root_user_id},
        {"$set": {"family_seats_used": 0}},
    )
    if res.modified_count:
        logger.info(f"[family] cascade-revoked {res.modified_count} seats from root={root_user_id}")
    return res.modified_count
