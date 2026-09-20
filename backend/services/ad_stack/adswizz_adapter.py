"""Phase 42 Session 1 — AdsWizz adapter contract + Mock implementation.

Real HTTP calls are PARKED — user is mid-signup for AdsWizz. Env-driven
mode switch lets us flip to live without code changes.

  ADSTACK_ADSWIZZ_MODE=mock | live  (default: mock)
  ADSWIZZ_API_KEY        — provisioned later
  ADSWIZZ_PUBLISHER_ID   — provisioned later
  ADSWIZZ_ZONE_ID        — provisioned later
"""
from __future__ import annotations
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from typing import Optional

log = logging.getLogger("bigfm.adstack.adswizz")

MODE = os.environ.get("ADSTACK_ADSWIZZ_MODE", "mock").lower().strip()


@dataclass
class AudioAdResponse:
    ad_id:           str
    audio_url:       str
    duration_seconds: int
    advertiser_name: str
    click_url:       Optional[str]
    impression_url:  Optional[str]
    vast_xml:        Optional[str] = None

    def to_dict(self) -> dict: return asdict(self)


class AdsWizzAdapter:
    """Abstract contract — real HTTP impl lands once creds arrive."""
    async def fetch_audio_ad(self, targeting_ctx: dict
                              ) -> Optional[AudioAdResponse]:
        raise NotImplementedError


class MockAdsWizzAdapter(AdsWizzAdapter):
    """Returns a deterministic fake VAST response pointing at the house
    audio files seeded under /app/backend/static/ads/. Useful for end-to-end
    flow validation without burning real ad inventory."""
    HOUSE_CLIPS = [
        "/api/static/ads/house_premium_promo.mp3",
        "/api/static/ads/house_partner_promo.mp3",
        "/api/static/ads/house_listener_thanks.mp3",
    ]

    async def fetch_audio_ad(self, targeting_ctx: dict
                              ) -> Optional[AudioAdResponse]:
        ad_id = "adswizz_mock_" + uuid.uuid4().hex[:10]
        clip  = self.HOUSE_CLIPS[hash(ad_id) % len(self.HOUSE_CLIPS)]
        vast = f"""<?xml version="1.0" encoding="UTF-8"?>
<VAST version="4.0"><Ad id="{ad_id}"><InLine>
  <AdSystem>AdsWizzMock</AdSystem>
  <AdTitle>FUUSIC Mock Audio Ad</AdTitle>
  <Impression><![CDATA[/api/ads/audio/_impression/{ad_id}]]></Impression>
  <Creatives><Creative><Linear>
    <Duration>00:00:30</Duration>
    <MediaFiles><MediaFile delivery="progressive" type="audio/mpeg">
      <![CDATA[{clip}]]>
    </MediaFile></MediaFiles>
  </Linear></Creative></Creatives>
</InLine></Ad></VAST>"""
        return AudioAdResponse(
            ad_id=ad_id, audio_url=clip, duration_seconds=30,
            advertiser_name="House (Mock AdsWizz)",
            click_url="/premium",
            impression_url=f"/api/ads/audio/_impression/{ad_id}",
            vast_xml=vast)


def get_adswizz_adapter() -> AdsWizzAdapter:
    if MODE == "live":
        # Live adapter NOT yet implemented — user is signing up.
        log.warning("[adswizz] live mode requested but adapter not yet shipped "
                     "— falling back to mock")
    return MockAdsWizzAdapter()


def is_live() -> bool: return MODE == "live"
