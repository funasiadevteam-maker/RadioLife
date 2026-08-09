"""Phase J.4 — User-to-user tipping with platform fee.

Sender debits `amount_pts` via PointsService.spend; receiver credits
90% via PointsService.award; remaining 10% credits the RadioLife house
account (`platform_house`) and is logged as `platform_fee_pts` on the
tip record.

Anti-spam:
  • Min tip 10 pts, max single tip 1000 pts.
  • Daily cap per sender: 5000 pts AND 20 tips.
  • Cannot tip yourself, cannot tip admin accounts.
  • Receivers: `community_station_owner` (resolves to station.owner_user_id),
                  `persona_rj` (credits the house pool keyed by persona_id),
                  `user` (direct).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, conint

from auth import current_user

log = logging.getLogger("bigfm.tips")

router = APIRouter(tags=["tips"])

# Tunables
MIN_TIP_PTS                       = 10
MAX_TIP_PTS                       = 1000
DAILY_TIP_TOTAL_CAP    = 5000
DAILY_TIP_COUNT_CAP    = 20
PLATFORM_FEE_PCT          = 0.10
PERSONA_HOUSE_USER_ID = "user_house_persona_pool"


def _is_admin(u: dict) -> bool:
    if not u: return False
    return (u.get("role") == "admin" or u.get("is_admin")
                  or "admin" in (u.get("roles") or []))


class _SendBody(BaseModel):
    receiver_type: str = Field(..., pattern="^(community_station_owner|persona_rj|user)$")
    receiver_entity_id: str = Field(..., min_length=1, max_length=120)
    amount_pts: conint(ge=MIN_TIP_PTS, le=MAX_TIP_PTS)  # noqa: F722
    message: Optional[str] = Field(None, max_length=140)


async def _resolve_receiver(db, body: _SendBody) -> dict:
    """Returns {target_user_id, target_name, receiver_entity_id}."""
    if body.receiver_type == "user":
        u = await db.users.find_one({"user_id": body.receiver_entity_id},
                                                                  {"user_id": 1, "name": 1, "email": 1, "role": 1, "is_admin": 1, "roles": 1})
        if not u: raise HTTPException(404, "receiver_not_found")
        if _is_admin(u): raise HTTPException(400, "cannot_tip_admin")
        return {"target_user_id": u["user_id"],
                      "target_name": u.get("name") or u.get("email") or u["user_id"],
                      "receiver_entity_id": body.receiver_entity_id}

    if body.receiver_type == "community_station_owner":
        # Resolves by station_id or slug.
        st = (await db.community_stations.find_one(
                  {"$or": [{"_id": body.receiver_entity_id},
                                  {"slug": body.receiver_entity_id}]})
                  or await db.imported_radio_stations.find_one(
                  {"id": body.receiver_entity_id}))
        if not st: raise HTTPException(404, "station_not_found")
        owner = st.get("owner_user_id") or st.get("creator_user_id")
        if not owner: raise HTTPException(404, "station_has_no_owner")
        return {"target_user_id": owner,
                      "target_name": st.get("name") or st.get("title") or "Station",
                      "receiver_entity_id": st.get("_id") or st.get("id")}

    # persona_rj — credits the house pool (used to fund prize draws).
    p = await db.personas.find_one({"_id": body.receiver_entity_id})
    if not p:
        p = await db.personas.find_one({"persona_id": body.receiver_entity_id})
    if not p: raise HTTPException(404, "persona_not_found")
    return {"target_user_id": PERSONA_HOUSE_USER_ID,
                  "target_name": p.get("name") or p.get("display_name") or "Persona pool",
                  "receiver_entity_id": p.get("_id") or p.get("persona_id")}


async def _check_daily_caps(db, sender_uid: str, amount: int):
    """Raises 429 if sender exceeds daily caps."""
    since = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    cur = db.tips.find({"sender_user_id": sender_uid,
                                              "status": "completed",
                                              "created_at": {"$gte": since}})
    total = count = 0
    async for t in cur:
        total += int(t.get("amount_pts") or 0)
        count += 1
    if count >= DAILY_TIP_COUNT_CAP:
        raise HTTPException(429, {"code": "daily_tip_count_cap",
                                                          "cap": DAILY_TIP_COUNT_CAP})
    if total + amount > DAILY_TIP_TOTAL_CAP:
        raise HTTPException(429, {"code": "daily_tip_total_cap",
                                                          "cap": DAILY_TIP_TOTAL_CAP,
                                                          "spent_today": total})


@router.post("/api/tips/send")
async def send_tip(body: _SendBody, request: Request,
                                  user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    sender_uid = user["user_id"]
    if _is_admin(user):
        raise HTTPException(400, "admin_cannot_send_tips")
    target = await _resolve_receiver(db, body)
    if target["target_user_id"] == sender_uid:
        raise HTTPException(400, "cannot_tip_yourself")

    await _check_daily_caps(db, sender_uid, int(body.amount_pts))

    from services.points_service import PointsService
    svc = PointsService(db)

    # Verify balance.
    bal = int(await svc.get_balance(sender_uid) or 0)
    if bal < int(body.amount_pts):
        raise HTTPException(402, {"code": "insufficient_balance",
                                                          "balance": bal,
                                                          "required": int(body.amount_pts)})

    tip_id = f"tip_{uuid.uuid4().hex[:14]}"
    now = datetime.now(timezone.utc)
    platform_fee = int(round(int(body.amount_pts) * PLATFORM_FEE_PCT))
    receiver_credit = int(body.amount_pts) - platform_fee

    # Debit sender (idempotency key on tip id).
    debit = await svc.award(
        user_id=sender_uid, delta=-int(body.amount_pts),
        source="tip_sent",
        metadata={"tip_id": tip_id, "receiver_type": body.receiver_type,
                          "receiver_entity_id": target["receiver_entity_id"],
                          "target_user_id": target["target_user_id"]},
        idempotency_key=f"tip_debit_{tip_id}")
    if not debit.ok:
        raise HTTPException(402, {"code": "debit_failed",
                                                          "reason": debit.reason})

    # Credit receiver (90%).
    credit = await svc.award(
        user_id=target["target_user_id"], delta=receiver_credit,
        source="tip_received",
        metadata={"tip_id": tip_id, "sender_user_id": sender_uid,
                          "receiver_type": body.receiver_type,
                          "receiver_entity_id": target["receiver_entity_id"]},
        idempotency_key=f"tip_credit_{tip_id}")

    # Platform fee — house wallet (idempotent ledger row).
    fee = await svc.award(
        user_id="user_house_platform_fee",
        delta=platform_fee, source="platform_fee",
        metadata={"tip_id": tip_id, "from": sender_uid,
                          "to": target["target_user_id"]},
        idempotency_key=f"tip_fee_{tip_id}")

    doc = {
        "_id":                          tip_id,
        "sender_user_id":  sender_uid,
        "sender_name":          user.get("name") or user.get("email"),
        "receiver_user_id": target["target_user_id"],
        "receiver_type":      body.receiver_type,
        "receiver_entity_id": target["receiver_entity_id"],
        "receiver_name":      target["target_name"],
        "amount_pts":          int(body.amount_pts),
        "receiver_credit_pts": receiver_credit,
        "platform_fee_pts": platform_fee,
        "message":                  (body.message or "").strip()[:140],
        "status":                      "completed",
        "created_at":            now,
    }
    await db.tips.insert_one(doc)
    log.info("[tips] %s → %s (%s) %dpts (fee %d)",
                  sender_uid, target["target_user_id"],
                  body.receiver_type, body.amount_pts, platform_fee)
    return {"ok": True, "tip": _strip_tip(doc),
                  "sender_balance_after": int(debit.balance_after or 0),
                  "receiver_credit_ok": bool(credit.ok),
                  "platform_fee_ok": bool(fee.ok)}


def _strip_tip(doc: dict) -> dict:
    return {
        "id":                                  doc["_id"],
        "sender_user_id":          doc.get("sender_user_id"),
        "sender_name":                  doc.get("sender_name"),
        "receiver_user_id":      doc.get("receiver_user_id"),
        "receiver_type":              doc.get("receiver_type"),
        "receiver_entity_id":  doc.get("receiver_entity_id"),
        "receiver_name":              doc.get("receiver_name"),
        "amount_pts":                  int(doc.get("amount_pts") or 0),
        "receiver_credit_pts": int(doc.get("receiver_credit_pts") or 0),
        "platform_fee_pts":      int(doc.get("platform_fee_pts") or 0),
        "message":                          (doc.get("message") or "")[:140],
        "status":                              doc.get("status"),
        "created_at":                    (doc["created_at"].isoformat()
                                                          if isinstance(doc.get("created_at"),
                                                                                  datetime) else doc.get("created_at")),
    }


@router.get("/api/me/tips/sent")
async def list_my_sent_tips(request: Request,
                                                              limit: int = Query(50, ge=1, le=200),
                                                              user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    items = []
    cur = db.tips.find({"sender_user_id": user["user_id"]}
                                    ).sort("created_at", -1).limit(int(limit))
    async for d in cur:
        items.append(_strip_tip(d))
    return {"count": len(items), "items": items}


@router.get("/api/me/tips/received")
async def list_my_received_tips(request: Request,
                                                                      limit: int = Query(50, ge=1, le=200),
                                                                      user: dict = Depends(current_user)) -> dict:
    db = request.app.state.db
    items = []
    cur = db.tips.find({"receiver_user_id": user["user_id"]}
                                    ).sort("created_at", -1).limit(int(limit))
    async for d in cur:
        items.append(_strip_tip(d))
    return {"count": len(items), "items": items}


@router.get("/api/admin/tips/stats")
async def admin_tips_stats(request: Request,
                                                          period: str = Query("week"),
                                                          user: dict = Depends(current_user)) -> dict:
    if not _is_admin(user):
        raise HTTPException(403, "admin_required")
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        from datetime import timedelta
        since = since - timedelta(days=7)
    elif period == "month":
        from datetime import timedelta
        since = since - timedelta(days=30)
    elif period == "all":
        since = datetime(1970, 1, 1, tzinfo=timezone.utc)

    total_volume = 0
    total_fee = 0
    count = 0
    givers: dict[str, int] = {}
    receivers: dict[str, int] = {}
    async for t in db.tips.find({"status": "completed",
                                                                "created_at": {"$gte": since}},
                                                              {"sender_user_id": 1, "receiver_user_id": 1,
                                                                "amount_pts": 1, "platform_fee_pts": 1}):
        amt = int(t.get("amount_pts") or 0)
        fee = int(t.get("platform_fee_pts") or 0)
        total_volume += amt
        total_fee += fee
        count += 1
        s = t.get("sender_user_id")
        r = t.get("receiver_user_id")
        if s:
            givers[s] = givers.get(s, 0) + amt
        if r:
            receivers[r] = receivers.get(r, 0) + amt
    top_givers = sorted(givers.items(), key=lambda kv: -kv[1])[:10]
    top_receivers = sorted(receivers.items(), key=lambda kv: -kv[1])[:10]
    return {
        "period":              period, "since": since.isoformat(),
        "total_count":  count,
        "total_volume_pts": total_volume,
        "platform_fee_earned_pts": total_fee,
        "top_givers":      [{"user_id": uid, "total_pts": pts}
                                              for uid, pts in top_givers],
        "top_receivers": [{"user_id": uid, "total_pts": pts}
                                              for uid, pts in top_receivers],
    }
