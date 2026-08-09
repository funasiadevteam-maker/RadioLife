"""Phase 4.5 — Real OpenRTB 2.5 auction engine.

Fans out a BidRequest to all enabled SSP adapters with a 200ms timeout, runs
a second-price auction, fires win-notification, logs to `openrtb_auctions`.

Public:
- build_bid_request(user, session, ctx) → dict (OpenRTB 2.5 BidRequest)
- run_openrtb_auction(db, user, session, ctx) → ad decision dict or None
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from services.ssp_adapters import load_adapters

logger = logging.getLogger("bigfm.ads.openrtb_auction")

FLOOR_CENTS = int(os.environ.get("OPENRTB_FLOOR_CENTS", 50))      # $0.50 CPM
DEFAULT_TIMEOUT_MS = int(os.environ.get("OPENRTB_TIMEOUT_MS", 200))


def _market_to_iso_country(market: str) -> str:
    return {"dubai": "ARE", "dfw": "USA"}.get((market or "").lower(), "USA")


def build_bid_request(user: dict, session: dict, ctx: dict) -> dict:
    """Construct a minimal but spec-compliant OpenRTB 2.5 BidRequest."""
    market = (ctx.get("market") or "dubai").lower()
    return {
        "id": str(uuid.uuid4()),
        "imp": [{
            "id": "1",
            "audio": {
                "mimes": ["audio/mpeg"],
                "minduration": 15, "maxduration": 30,
                "delivery": [3],            # 3 = streaming
                "protocols": [11, 12, 13],  # 11=VAST 3 wrapper, 12=VAST 4.0, 13=VAST 4.0 wrapper
                "startdelay": 0,
                "sequence": 1,
                "linearity": 1,             # in-stream
            },
            "bidfloor": FLOOR_CENTS / 100.0,
            "bidfloorcur": "USD",
            "secure": 1,
        }],
        "site": {
            "id": "bigfm-web", "name": "RadioLife",
            "domain": "bigfm.dubai" if market == "dubai" else "funasia.ai",
            "page": ctx.get("channel_slug", ""),
        },
        "user": {
            "id": user.get("user_id"),
            "geo": {"country": _market_to_iso_country(market)},
        },
        "device": {
            "ua": ctx.get("user_agent", ""),
            "geo": {"country": _market_to_iso_country(market)},
        },
        "bcat": ["IAB7-39", "IAB14-1", "IAB23-1"],  # gambling/alcohol/political default block
        "at": 2,  # second-price auction
        "tmax": DEFAULT_TIMEOUT_MS,
        "ext": {
            "bigfm": {
                "channel_slug": ctx.get("channel_slug"),
                "daypart_slug": ctx.get("daypart"),
                "current_rj_voice": ctx.get("voice_key"),
                "market": market,
            },
        },
    }


async def _fire_win_notification(winner: dict, clearing_price: int) -> None:
    """Fire async POST to the winner's win_url with the clearing price.
    Phase 4.5 MVP: log it. Real partners require this within 100ms of decision."""
    if not winner.get("win_url"):
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(winner["win_url"],
                                      json={"price_cents": clearing_price,
                                             "bidrequest_id": winner.get("bidrequest_id")},
                                      timeout=aiohttp.ClientTimeout(total=2.0)) as r:
                _ = await r.read()
    except Exception as e:
        logger.debug(f"win-notify error: {e}")


async def run_openrtb_auction(db, *, user: dict, session: dict, ctx: dict) -> Optional[dict]:
    """Run a fan-out auction and return the winning ad decision dict (or None
    if all bids are below the floor or all adapters return no-bid)."""
    # Load enabled SSP partners
    partners = await db.ssp_partners.find({"enabled": True}).to_list(length=20)
    if not partners:
        return None
    adapters = load_adapters(partners)
    if not adapters:
        return None

    bid_request = build_bid_request(user, session, ctx)
    started = time.monotonic()

    async def _safe_bid(ad):
        try:
            return await asyncio.wait_for(
                ad.bid(bid_request, {}),
                timeout=DEFAULT_TIMEOUT_MS / 1000.0,
            )
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.debug(f"adapter {ad.name} error: {e}")
            return None

    results = await asyncio.gather(*[_safe_bid(a) for a in adapters], return_exceptions=False)
    duration_ms = int((time.monotonic() - started) * 1000)

    # Filter valid bids
    bids = [r for r in results if isinstance(r, dict) and int(r.get("price_cents") or 0) > 0]
    bids = [b for b in bids if int(b["price_cents"]) >= FLOOR_CENTS]
    if not bids:
        await db.openrtb_auctions.insert_one({
            "_id": str(uuid.uuid4()), "bidrequest_id": bid_request["id"],
            "user_id": user.get("user_id"), "session_id": session.get("_id"),
            "adapter_count": len(adapters), "bid_count": 0,
            "winner_partner": None, "winner_price_cents": 0,
            "clearing_price_cents": 0, "duration_ms": duration_ms,
            "ran_at": datetime.now(timezone.utc),
        })
        return None

    # Second-price auction
    bids.sort(key=lambda b: -int(b["price_cents"]))
    winner = bids[0]
    clearing_price = (int(bids[1]["price_cents"]) + 1) if len(bids) > 1 else FLOOR_CENTS

    await db.openrtb_auctions.insert_one({
        "_id": str(uuid.uuid4()), "bidrequest_id": bid_request["id"],
        "user_id": user.get("user_id"), "session_id": session.get("_id"),
        "adapter_count": len(adapters), "bid_count": len(bids),
        "winner_partner": winner.get("partner"),
        "winner_price_cents": int(winner["price_cents"]),
        "clearing_price_cents": int(clearing_price),
        "duration_ms": duration_ms,
        "ran_at": datetime.now(timezone.utc),
        "all_bids": [{"partner": b.get("partner"), "price_cents": int(b["price_cents"])} for b in bids],
    })

    # Fire win notification (don't block)
    asyncio.create_task(_fire_win_notification(winner, clearing_price))

    # Return ad decision shape expected by ad_decisioning.select_ad
    return {
        "decision_path": "openrtb",
        "ssp_partner": winner.get("partner"),
        "campaign": {
            "campaign_id": f"openrtb_{winner.get('partner', 'ssp')}",
            "name": f"{winner.get('partner_name', winner.get('partner','SSP'))} (programmatic)",
            "bid_cents_per_impression": int(clearing_price),
            "business_id": None,
        },
        "creative": {
            "creative_id": winner.get("creative_id") or f"rtb_{bid_request['id'][:8]}",
            "audio_path": None,  # Phase 4.5 MVP: external URL only — direct play not yet supported
            "audio_url": winner.get("audio_url"),
            "duration_sec": winner.get("duration_sec", 20),
            "click_through_url": winner.get("click_through_url"),
            "impression_pixel": winner.get("impression_pixel"),
        },
        "action_cards": [],
        "business": None,
        "auction_duration_ms": duration_ms,
    }


# ---------- Seed default SSP partners ----------
async def seed_ssp_partners(db) -> int:
    defaults = [
        {"_id": "mock_ssp", "name": "Mock SSP (testing)",
         "adapter_module": "mock_ssp", "enabled": True,
         "endpoint_url": "https://mock.ssp.bigfm.test/bid",
         "bidder_id": "bigfm-mock", "secret": "", "timeout_ms": 200},
        {"_id": "magnite", "name": "Magnite",
         "adapter_module": "magnite", "enabled": False,
         "endpoint_url": "", "bidder_id": "", "secret": "", "timeout_ms": 200},
        {"_id": "pubmatic", "name": "PubMatic",
         "adapter_module": "pubmatic", "enabled": False,
         "endpoint_url": "", "bidder_id": "", "secret": "", "timeout_ms": 200},
        {"_id": "index_exchange", "name": "Index Exchange",
         "adapter_module": "index_exchange", "enabled": False,
         "endpoint_url": "", "bidder_id": "", "secret": "", "timeout_ms": 200},
        {"_id": "openx", "name": "OpenX",
         "adapter_module": "openx", "enabled": False,
         "endpoint_url": "", "bidder_id": "", "secret": "", "timeout_ms": 200},
    ]
    now = datetime.now(timezone.utc)
    created = 0
    for d in defaults:
        r = await db.ssp_partners.update_one(
            {"_id": d["_id"]},
            {"$setOnInsert": {**d, "created_at": now, "win_count_30d": 0,
                                "bid_count_30d": 0, "avg_bid_cents": 0}},
            upsert=True,
        )
        if r.upserted_id is not None:
            created += 1
    return created


async def ensure_openrtb_indexes(db) -> None:
    await db.openrtb_auctions.create_index([("ran_at", -1)])
    await db.openrtb_auctions.create_index([("user_id", 1), ("ran_at", -1)])
    await db.ssp_partners.create_index([("enabled", 1), ("name", 1)])
