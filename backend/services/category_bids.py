"""Category Spotlight — a per-impression bid auction. A merchant bids
`bid_cents` per impression to rank at the top of ONE category's search
results; higher bid = higher position. Impressions are billed against a
PREPAID budget (topped up via Stripe hosted Checkout); when the budget can no
longer cover the next impression the bid auto-pauses ('depleted'). Active
bidders also get the Promoted badge + the Promoted-near-you rail."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Set


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return date.today().isoformat()


def _capped_today(b: Dict[str, Any]) -> bool:
    cap = int(b.get("daily_cap_cents", 0) or 0)
    return cap > 0 and b.get("spend_date") == _today() and int(b.get("spent_today", 0)) >= cap


def _eligible(b: Dict[str, Any]) -> bool:
    return int(b.get("budget_cents", 0)) >= int(b.get("bid_cents", 0)) > 0 and not _capped_today(b)


async def active_bids_for(db, category: str) -> List[Dict[str, Any]]:
    """Live, funded, not-daily-capped bids for a category — highest bid first."""
    out = [b async for b in db.category_bids.find({"category": category, "status": "active"})]
    out = [b for b in out if _eligible(b)]
    out.sort(key=lambda b: int(b.get("bid_cents", 0)), reverse=True)
    return out


async def active_bid_business_ids(db) -> Set[str]:
    ids: Set[str] = set()
    async for b in db.category_bids.find({"status": "active"}):
        if _eligible(b):
            ids.add(b.get("business_id"))
    return ids


async def bill_impressions(db, bids: List[Dict[str, Any]]):
    """Charge one impression per served bidder against its prepaid budget.
    Atomic: the conditional $inc only fires while budget covers the bid AND the
    daily cap isn't hit. Also records a per-day roll-up (spend + a `capped` flag
    on days the daily cap blocked demand) for the trend chart + weekly digest."""
    today = _today()
    for b in bids:
        bid = int(b.get("bid_cents", 0))
        if bid <= 0:
            continue
        biz = b.get("business_id")
        cap = int(b.get("daily_cap_cents", 0) or 0)
        if b.get("spend_date") != today:  # roll the daily counter over
            await db.category_bids.update_one(
                {"bid_id": b["bid_id"]}, {"$set": {"spent_today": 0, "spend_date": today}})
        filt: Dict[str, Any] = {"bid_id": b["bid_id"], "budget_cents": {"$gte": bid}}
        if cap > 0:
            filt["spent_today"] = {"$lte": cap - bid}
        r = await db.category_bids.update_one(filt,
            {"$inc": {"spent_cents": bid, "impressions": 1, "budget_cents": -bid, "spent_today": bid},
             "$set": {"updated_at": _now(), "spend_date": today}})
        if r.modified_count:
            await db.category_bid_daily.update_one(
                {"business_id": biz, "date": today},
                {"$inc": {"spent_cents": bid, "impressions": 1},
                 "$setOnInsert": {"business_id": biz, "date": today, "capped": False}}, upsert=True)
            await db.category_bids.update_one(
                {"bid_id": b["bid_id"], "status": "active", "budget_cents": {"$lt": bid}},
                {"$set": {"status": "depleted"}})
        elif cap > 0:
            # Blocked — flag the day capped only when budget could still cover it.
            fresh = await db.category_bids.find_one({"bid_id": b["bid_id"]}, {"budget_cents": 1})
            if fresh and int(fresh.get("budget_cents", 0)) >= bid:
                await db.category_bid_daily.update_one(
                    {"business_id": biz, "date": today},
                    {"$set": {"capped": True},
                     "$setOnInsert": {"business_id": biz, "date": today, "spent_cents": 0, "impressions": 0}},
                    upsert=True)


async def bid_standing(db, category: str, business_id: str) -> Dict[str, Any]:
    """Rank + outbid info for one business within a category auction."""
    bids = await active_bids_for(db, category)
    top = int(bids[0]["bid_cents"]) if bids else 0
    rank = next((i + 1 for i, b in enumerate(bids) if b.get("business_id") == business_id), None)
    mine = next((b for b in bids if b.get("business_id") == business_id), None)
    my_bid = int(mine["bid_cents"]) if mine else 0
    outbid = bool(rank and rank > 1)
    return {"competitors": len(bids), "top_bid_cents": top, "rank": rank,
            "outbid": outbid, "my_bid_cents": my_bid,
            "suggested_bid_cents": (top + 1) if (rank is None or rank > 1) else my_bid}


__all__ = ["active_bids_for", "active_bid_business_ids", "bill_impressions", "bid_standing"]
