"""Rail Sponsorship — ad-wallet + per-area DAILY SECOND-PRICE auction.

Model
-----
• A sponsorship is a *standing bid*: a max `daily_bid_cents` the merchant will
  pay per targeted area per day, for a chosen duration, targeting any subset of
  the rail areas (social / shop / listen).
• Each area settles ONCE per day (lazily, on first rail render): the highest
  bid wins the single slot and is charged a Vickrey clearing price
  (runner-up bid + $0.01, floored at the daily floor, capped at its own bid),
  debited from the merchant's rail wallet. If the wallet can't cover it, the
  next-highest affordable bid wins.
• Raising a bid re-settles the current day immediately (refund the displaced
  winner, charge the new one) and fires an "outbid" alert.

Wallet is funded via one-time Stripe top-ups (see routes/social_v2.py).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("rail_auction")

RAIL_AREAS = ["social", "shop", "listen"]
RAIL_AREA_LABELS = {"social": "Social", "shop": "Shop", "listen": "Listen"}
RAIL_DAILY_FLOOR_CENTS = 500            # $5 / area / day minimum bid
RAIL_INCREMENT_CENTS = 1                # +$0.01 above the runner-up
RAIL_DURATIONS = {
    "1d": {"days": 1, "label": "1 day"},
    "3d": {"days": 3, "label": "3 days"},
    "7d": {"days": 7, "label": "7 days"},
}
RAIL_TOPUP_PRESETS = [2000, 5000, 10000, 25000]  # $20 / $50 / $100 / $250


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day_str(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%d")


def area_for_route(route: str) -> str:
    r = route or ""
    if r.startswith("/shop"):
        return "shop"
    if r.startswith("/channels") or r.startswith("/listen"):
        return "listen"
    return "social"  # /social, /home, /play, /community all share the social slot


# ── Wallet ──────────────────────────────────────────────────────────
async def get_wallet(db, merchant_id: str) -> dict:
    w = await db.rail_wallets.find_one({"_id": merchant_id})
    if not w:
        w = {"_id": merchant_id, "merchant_id": merchant_id,
             "balance_cents": 0, "updated_at": _now()}
        await db.rail_wallets.insert_one(w)
    return w


async def credit_wallet(db, merchant_id: str, cents: int, *,
                        kind: str = "topup", ref: Optional[str] = None,
                        sponsorship_id: Optional[str] = None) -> None:
    await get_wallet(db, merchant_id)
    await db.rail_wallets.update_one(
        {"_id": merchant_id},
        {"$inc": {"balance_cents": int(cents)}, "$set": {"updated_at": _now()}})
    await db.rail_wallet_txns.insert_one({
        "_id": "rwt_" + uuid.uuid4().hex[:12], "merchant_id": merchant_id,
        "kind": kind, "amount_cents": int(cents), "ref": ref,
        "sponsorship_id": sponsorship_id, "created_at": _now()})


async def debit_wallet(db, merchant_id: str, cents: int, *,
                       ref: Optional[str] = None,
                       sponsorship_id: Optional[str] = None) -> bool:
    r = await db.rail_wallets.update_one(
        {"_id": merchant_id, "balance_cents": {"$gte": int(cents)}},
        {"$inc": {"balance_cents": -int(cents)}, "$set": {"updated_at": _now()}})
    if not r.modified_count:
        return False
    await db.rail_wallet_txns.insert_one({
        "_id": "rwt_" + uuid.uuid4().hex[:12], "merchant_id": merchant_id,
        "kind": "charge", "amount_cents": -int(cents), "ref": ref,
        "sponsorship_id": sponsorship_id, "created_at": _now()})
    return True


# ── Alerts (in-app + best-effort email) ─────────────────────────────
async def _fire_outbid_alert(db, sp: dict, area: str,
                             winner_title: Optional[str]) -> None:
    body = (f"You've been outbid for the {RAIL_AREA_LABELS.get(area, area)} "
            f"rail slot" + (f" by \"{winner_title}\"" if winner_title else "") +
            ". Raise your bid to win it back.")
    await db.rail_alerts.insert_one({
        "_id": "ral_" + uuid.uuid4().hex[:12], "merchant_id": sp["merchant_id"],
        "sponsorship_id": sp["_id"], "area": area, "kind": "outbid",
        "title": "Outbid on the rail", "body": body, "read": False,
        "created_at": _now()})
    try:
        u = await db.users.find_one({"user_id": sp.get("sponsor_user_id")},
                                    {"email": 1, "name": 1})
        if not (u and u.get("email")):
            return
        from services.mailgun_client import send_email, is_live
        if not is_live():
            return
        html = (f"<p>Hi {u.get('name') or 'there'},</p><p>{body}</p>"
                f"<p><a href='/merchant/rail-sponsor'>Manage your bid →</a></p>")
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, lambda: send_email(
            u["email"], "You've been outbid on the FUUSIC rail", html,
            tags=["rail-outbid"]))
    except Exception as e:  # never block settlement on email
        log.debug("outbid email skipped: %s", e)


# ── Settlement ──────────────────────────────────────────────────────
async def _compute_and_charge(db, area: str, day: str) -> dict:
    """Second-price settlement for (area, day). Charges the affordable winner."""
    now = _now()
    cands: list[dict] = []
    async for s in db.rail_sponsorships.find({
            "status": "active", "target_pages": area,
            "starts_at": {"$lte": now}, "ends_at": {"$gte": now}}):
        cands.append(s)
    cands.sort(key=lambda x: (-(int(x.get("daily_bid_cents") or 0)),
                              x.get("created_at") or now))
    ranked = [{"sponsorship_id": c["_id"], "merchant_id": c["merchant_id"],
               "bid_cents": int(c.get("daily_bid_cents") or 0)} for c in cands]
    winner, clearing = None, 0
    for i, c in enumerate(cands):
        runner = int(cands[i + 1]["daily_bid_cents"]) if i + 1 < len(cands) else None
        price = (runner + RAIL_INCREMENT_CENTS) if runner is not None else RAIL_DAILY_FLOOR_CENTS
        price = max(RAIL_DAILY_FLOOR_CENTS, min(price, int(c.get("daily_bid_cents") or 0)))
        if await debit_wallet(db, c["merchant_id"], price,
                              ref=f"rail:{area}:{day}", sponsorship_id=c["_id"]):
            winner, clearing = c, price
            break  # else: can't afford → next candidate wins at its own clearing
    return {"_id": f"{area}:{day}", "area": area, "day": day,
            "winner_id": (winner or {}).get("_id"),
            "winner_merchant": (winner or {}).get("merchant_id"),
            "winner_title": (winner or {}).get("title"),
            "clearing_cents": clearing, "ranked": ranked, "created_at": now}


async def settle_area_day(db, area: str, day: Optional[str] = None) -> dict:
    """Idempotent: settle (area, day) once; fire an alert if the winner changed
    vs yesterday. Returns the settlement doc."""
    day = day or _day_str()
    key = f"{area}:{day}"
    existing = await db.rail_settlements.find_one({"_id": key})
    if existing:
        return existing
    doc = await _compute_and_charge(db, area, day)
    try:
        await db.rail_settlements.insert_one(doc)
    except Exception:  # race → someone settled first
        return await db.rail_settlements.find_one({"_id": key})
    # Yesterday's winner displaced?
    if doc.get("winner_id"):
        yday = await db.rail_settlements.find_one(
            {"_id": f"{area}:{_day_str(_now() - timedelta(days=1))}"})
        prev = (yday or {}).get("winner_id")
        if prev and prev != doc["winner_id"]:
            sp_prev = await db.rail_sponsorships.find_one(
                {"_id": prev, "status": "active"})
            if sp_prev:
                await _fire_outbid_alert(db, sp_prev, area, doc.get("winner_title"))
    return doc


async def resettle_today(db, area: str) -> dict:
    """Recompute today's winner NOW (used after a bid change). Refunds the
    displaced winner and alerts them."""
    day = _day_str()
    key = f"{area}:{day}"
    old = await db.rail_settlements.find_one({"_id": key})
    old_winner = (old or {}).get("winner_id")
    if old:
        if old.get("winner_merchant") and old.get("clearing_cents"):
            await credit_wallet(db, old["winner_merchant"], old["clearing_cents"],
                                kind="refund", ref=f"resettle:{key}",
                                sponsorship_id=old.get("winner_id"))
        await db.rail_settlements.delete_one({"_id": key})
    doc = await _compute_and_charge(db, area, day)
    await db.rail_settlements.replace_one({"_id": key}, doc, upsert=True)
    if old_winner and doc.get("winner_id") != old_winner:
        sp_prev = await db.rail_sponsorships.find_one(
            {"_id": old_winner, "status": "active"})
        if sp_prev:
            await _fire_outbid_alert(db, sp_prev, area, doc.get("winner_title"))
    return doc


async def sponsored_card_for_area(db, route: str) -> Optional[dict]:
    """The winning sponsorship for the current page's area, as a rail card."""
    area = area_for_route(route)
    st = await settle_area_day(db, area)
    wid = st.get("winner_id")
    if not wid:
        return None
    s = await db.rail_sponsorships.find_one({"_id": wid})
    if not s or s.get("status") != "active":
        return None
    return {
        "id": f"SPONSORED:{s['_id']}", "kind": "sponsored",
        "title": s.get("title") or "Featured",
        "subtitle": s.get("subtitle") or s.get("business_name") or "Sponsored",
        "image": s.get("image"), "badge": "SPONSORED",
        "cta": s.get("cta") or "View", "to": s.get("to"),
        "sponsored": True, "sponsorship_id": str(s["_id"]),
    }


async def today_status_for(db, sp: dict) -> dict:
    """Per-area featured / rank / clearing for a sponsorship (today)."""
    areas = {}
    featured_any = False
    for area in (sp.get("target_pages") or []):
        st = await settle_area_day(db, area)
        ranked = st.get("ranked") or []
        rank = next((i + 1 for i, r in enumerate(ranked)
                     if r["sponsorship_id"] == sp["_id"]), None)
        is_win = st.get("winner_id") == sp["_id"]
        featured_any = featured_any or is_win
        areas[area] = {"featured": is_win, "rank": rank,
                       "active_total": len(ranked),
                       "clearing_cents": st.get("clearing_cents") if is_win else None,
                       "top_bid_cents": ranked[0]["bid_cents"] if ranked else 0}
    return {"areas": areas, "featured_any": featured_any}
