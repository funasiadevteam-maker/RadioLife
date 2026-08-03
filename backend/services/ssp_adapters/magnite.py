"""Magnite SSP adapter — Phase 4.5 stub (no real bids until partner creds)."""
from typing import Optional


class Adapter:
    name = "magnite"

    def __init__(self, endpoint_url: str = "", bidder_id: str = "",
                  secret: str = "", timeout_ms: int = 200, partner_id: str = "magnite"):
        self.endpoint_url = endpoint_url
        self.bidder_id = bidder_id
        self.secret = secret
        self.timeout_ms = timeout_ms
        self.partner_id = partner_id

    async def bid(self, bid_request: dict, headers: dict) -> Optional[dict]:
        # Real implementation would POST bid_request to self.endpoint_url with
        # OpenRTB 2.5 headers, parse the BidResponse, return the highest bid.
        # Requires real Magnite partner credentials — return None until configured.
        return None
