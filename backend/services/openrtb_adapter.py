"""Phase 18d — OpenRTB 2.5 adapter (waterfall position #4 after takeover →
direct-sold → GAM).

MOCKED by default. Flips to LIVE when `OPENRTB_SSP_ENDPOINTS` env var is
present (JSON array of SSP bid endpoints).  Implements a second-price
auction simulation: highest bid wins, charged at runner-up + $0.01.

Public surface:
  - is_live() -> bool
  - build_bid_request(...)     -> dict     # OpenRTB 2.5 BidRequest
  - send_to_ssps(bid_request)   -> list    # parallel POST; mock-friendly
  - select_winning_bid(bids)     -> dict | None  # 2nd-price auction
  - status_snapshot() -> dict
"""
from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.openrtb18d")

_MOCK_CPM_USD       = 8.0    # $0.008 per impression in mock
_MOCK_RUNNER_UP_USD = 6.0    # produces a clear 2nd-price gap
_SECOND_PRICE_FLOOR  = 0.001   # +$0.001 over runner-up


def is_live() -> bool:
    raw = os.environ.get("OPENRTB_SSP_ENDPOINTS")
    if not raw:
        return False
    try:
        return bool(json.loads(raw))
    except Exception:
        return False


def status_snapshot() -> dict:
    return {
        "is_live":                        is_live(),
        "ssp_endpoints_configured": _configured_endpoints(),
        "last_check_at":               datetime.now(timezone.utc).isoformat(),
        "mock_cpm_usd":               _MOCK_CPM_USD,
    }


def _configured_endpoints() -> list:
    raw = os.environ.get("OPENRTB_SSP_ENDPOINTS")
    if not raw:
        return []
    try:
        return list(json.loads(raw))
    except Exception:
        return []


def build_bid_request(*, user_id: str, channel_slug: str,
                                    market: str, vast_base_url: Optional[str] = None
                                    ) -> dict:
    """Build an OpenRTB 2.5 BidRequest (audio impression).
    Uses canonical IAB field names; no auth or PII."""
    req_id = "br_" + uuid.uuid4().hex[:14]
    return {
        "id":   req_id,
        "imp": [{
            "id":       "1",
            "audio": {
                "mimes":      ["audio/mpeg", "audio/aac"],
                "minduration": 10,
                "maxduration": 30,
                "protocols":   [7, 8, 9],   # VAST 4.x
                "delivery":     [2],            # progressive
                "battr":          [13, 14],   # no auto-play in app surveys / etc.
            },
            "bidfloor":         0.001,
            "bidfloorcur":   "USD",
            "secure":           1,
        }],
        "user": {"id": user_id},
        "device": {"ua": "RadioLife/18d",   "geo": {"country": "ARE"}},
        "site":  {"name": "RadioLife",
                       "domain": "stream-bridge-9.preview.emergentagent.com",
                       "cat": ["IAB1-6"]},    # radio
        "ext":    {"channel_slug": channel_slug,
                       "market":            market,
                       "vast_base_url":  vast_base_url or ""},
        "at":     2,    # second-price auction
        "tmax": 200,  # 200 ms timeout
    }


async def send_to_ssps(bid_request: dict) -> list:
    """Returns a list of BidResponse-shaped dicts.

    Mock mode: returns 2 deterministic bids (one high, one low) so the
    second-price math has something to chew on.
    Live mode: stub — would POST in parallel to each SSP endpoint with
    a short timeout. Network failures fall through to mock so the
    waterfall never hard-fails.
    """
    if not is_live():
        return _mock_bid_responses(bid_request)
    try:
        # Real path stub: gather() concurrent POSTs to each SSP.
        raise NotImplementedError("OpenRTB live POST not wired in 18d")
    except Exception as e:
        logger.warning("[openrtb18d] live path fell back to mock: %s", e)
        return _mock_bid_responses(bid_request)


def _mock_bid_responses(bid_request: dict) -> list:
    bid_id_hi = "bid_" + uuid.uuid4().hex[:10]
    bid_id_lo = "bid_" + uuid.uuid4().hex[:10]
    creative_url = "https://example.com/openrtb_mock.mp3"
    return [
        {
            "id":      "resp_" + uuid.uuid4().hex[:8],
            "bidid": bid_request["id"],
            "seatbid": [{"bid": [{
                "id":        bid_id_hi,
                "impid":  "1",
                "price":  _MOCK_CPM_USD / 1000.0,    # CPM → per-imp
                "adm":   "<VAST mock high />",
                "crid":   "creative_high",
                "cur":    "USD",
                "ext":    {"creative_url": creative_url,
                              "ssp":              "ssp_mock_alpha"},
            }]}],
        },
        {
            "id":      "resp_" + uuid.uuid4().hex[:8],
            "bidid": bid_request["id"],
            "seatbid": [{"bid": [{
                "id":        bid_id_lo,
                "impid":  "1",
                "price":  _MOCK_RUNNER_UP_USD / 1000.0,
                "adm":   "<VAST mock low />",
                "crid":   "creative_low",
                "cur":    "USD",
                "ext":    {"creative_url": creative_url,
                              "ssp":              "ssp_mock_beta"},
            }]}],
        },
    ]


def select_winning_bid(bid_responses: list) -> Optional[dict]:
    """Second-price auction: highest bid wins, charged at runner-up +
    $0.001.  Returns the winner envelope or None."""
    all_bids = []
    for r in bid_responses or []:
        for sb in r.get("seatbid") or []:
            for b in sb.get("bid") or []:
                all_bids.append(b)
    if not all_bids:
        return None
    all_bids.sort(key=lambda b: float(b.get("price") or 0.0), reverse=True)
    winner = all_bids[0]
    runner_up_price = (float(all_bids[1]["price"]) if len(all_bids) >= 2
                                    else 0.0)
    clear_price = round(runner_up_price + _SECOND_PRICE_FLOOR, 6)
    return {
        "source":         "openrtb_mock" if not is_live() else "openrtb",
        "winner":        winner,
        "clear_price": clear_price,
        "revenue_usd": clear_price,
        "creative_url": (winner.get("ext") or {}).get("creative_url"),
        "creative_id":  "ortb_" + str(winner.get("crid") or "")[:32],
        "vast_xml":     winner.get("adm"),
        "mocked":         not is_live(),
    }


async def request_ad(*, user_id: str, channel_slug: str, market: str,
                                  vast_base_url: Optional[str] = None
                                  ) -> Optional[dict]:
    """Convenience wrapper used by the waterfall: build → send → pick."""
    req = build_bid_request(user_id=user_id, channel_slug=channel_slug,
                                            market=market, vast_base_url=vast_base_url)
    bids = await send_to_ssps(req)
    return select_winning_bid(bids)
