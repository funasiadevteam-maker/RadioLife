"""Index Exchange SSP adapter — Phase 4.5 stub."""
from typing import Optional


class Adapter:
    name = "index_exchange"

    def __init__(self, endpoint_url: str = "", bidder_id: str = "",
                  secret: str = "", timeout_ms: int = 200, partner_id: str = "index_exchange"):
        self.endpoint_url = endpoint_url; self.bidder_id = bidder_id
        self.secret = secret; self.timeout_ms = timeout_ms; self.partner_id = partner_id

    async def bid(self, bid_request: dict, headers: dict) -> Optional[dict]:
        return None
