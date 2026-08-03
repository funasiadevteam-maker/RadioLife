"""Mock SSP — always returns a $1.00 bid with a house ad audio URL.
Used for testing the auction loop without real partner credentials.
"""
from __future__ import annotations
import os
from typing import Optional


class Adapter:
    name = "mock_ssp"

    def __init__(self, endpoint_url: str = "", bidder_id: str = "",
                  secret: str = "", timeout_ms: int = 200, partner_id: str = "mock_ssp"):
        self.endpoint_url = endpoint_url or "https://mock.ssp.bigfm.test/bid"
        self.bidder_id = bidder_id or "bigfm-mock"
        self.secret = secret
        self.timeout_ms = timeout_ms
        self.partner_id = partner_id

    async def bid(self, bid_request: dict, headers: dict) -> Optional[dict]:
        """Always returns a $1.00 (100 cents) bid pointing at a pre-generated
        house ad creative — typically the cheapest Karak ad as a fallback."""
        imp = (bid_request.get("imp") or [{}])[0]
        # Use the existing seeded Karak ad audio as the mock SSP creative
        backend_url = os.environ.get("PUBLIC_BACKEND_URL", "")
        audio_url = f"{backend_url}/api/ads/creative/crv_cmp_karak_20off/audio" if backend_url else \
                     "https://mobile-games-v2.preview.emergentagent.com/api/ads/creative/crv_cmp_karak_20off/audio"
        return {
            "partner": self.partner_id,
            "partner_name": self.name,
            "price_cents": 100,                       # $1.00 CPM
            "audio_url": audio_url,
            "duration_sec": 18.0,
            "creative_id": f"mock_{bid_request.get('id', 'na')}",
            "click_through_url": "https://bigfm.dubai/",
            "impression_pixel": "",
            "advertiser_name": "Mock SSP House Ad",
        }
