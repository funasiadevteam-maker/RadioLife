"""Category Spotlight — a per-impression bid auction. A merchant bids
`bid_cents` per impression to rank at the top of ONE category's search
results; higher bid = higher position. Impressions are billed against a
PREPAID budget (topped up via Stripe hosted Checkout); when the budget can no
longer cover the next impression the bid auto-pauses ('depleted'). Active
bidders also get the Promoted badge + the Promoted-near-you rail."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Set


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _eligible(b: Dict[str, Any]) -> bool:
    return int(b.get("budget_cents", 0)) >= int(b.get("bid_cents", 0)) > 0


async def active_bids_for(db, category: str) -> List[Dict[str, Any]]:
    """Live, funded bids for a category — best (highest) bid first."""
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
    Atomic: the conditional $inc only fires while budget covers the bid, so
    concurrent shop reads never double-bill or drive the budget negative."""
    for b in bids:
        bid = int(b.get("bid_cents", 0))
        if bid <= 0:
            continue
        r = await db.category_bids.update_one(
            {"bid_id": b["bid_id"], "budget_cents": {"$gte": bid}},
            {"$inc": {"spent_cents": bid, "impressions": 1, "budget_cents": -bid},
             "$set": {"updated_at": _now()}})
        if r.modified_count:
            await db.category_bids.update_one(
                {"bid_id": b["bid_id"], "status": "active", "budget_cents": {"$lt": bid}},
                {"$set": {"status": "depleted"}})


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
