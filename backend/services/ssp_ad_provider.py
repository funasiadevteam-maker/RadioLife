"""Sub-Phase 42-B2 — SSP/VAST waterfall provider stub.

When `select_ad_for_play` has zero local ads that match the user's
targeting + frequency/grace caps, we fall back to a configured SSP
provider chain.  Phase 42 v2 will wire real demand (AdsWizz, Triton,
Magnite).  For now everything is MOCKED — but the architecture, the
return-shape, and the chain ordering all already match the live spec.

Env knobs (all optional):
    SSP_PROVIDER_CHAIN          comma-list, default "mocked"
                                                    e.g. "adswizz,triton,mocked"
    SSP_MOCK_ENABLED                "true"/"false" — default true
    SSP_MOCK_FILL_RATE            0.0-1.0 — default 1.0 (always fills)
    SSP_MOCK_AUDIO_URL            override the synthetic audio MP3
                                                    used by the mocked provider
"""
from __future__ import annotations

import logging
import os
import random
from typing import Optional, Dict, Any, Protocol, List

log = logging.getLogger("bigfm.preroll_ssp")


class SSPProvider(Protocol):
    """All SSP providers expose the same `request_ad` coroutine.  Each
    returns a dict that mirrors the local-ad selection shape (so the
    waterfall can splice the response without callers needing to know
    which path it came from), OR None when the provider has no fill."""
    name: str

    async def request_ad(self, *,
                                                  station_id: str,
                                                  station_meta: Dict[str, Any],
                                                  user_ctx: Dict[str, Any],
                                                  country_code: Optional[str],
                                                  language: Optional[str]) -> Optional[Dict[str, Any]]:
        ...   # pragma: no cover


# ────────────────────────── Mocked ──────────────────────────
DEFAULT_MOCK_AUDIO_URL = "https://www.kozco.com/tech/piano2-CoolEdit.mp3"


class MockedSSPProvider:
    """Returns a synthetic VAST-shaped response.  Configurable fill rate
    so the tester can simulate no-fill scenarios."""
    name = "ssp_mocked"

    async def request_ad(self, *,
                                                  station_id: str,
                                                  station_meta: Dict[str, Any],
                                                  user_ctx: Dict[str, Any],
                                                  country_code: Optional[str],
                                                  language: Optional[str]) -> Optional[Dict[str, Any]]:
        if os.environ.get("SSP_MOCK_ENABLED", "true").lower() != "true":
            return None
        try:
            fill_rate = float(os.environ.get("SSP_MOCK_FILL_RATE", "1.0"))
        except ValueError:
            fill_rate = 1.0
        if random.random() > fill_rate:
            return None
        # Synthetic VAST creative — never has an offer / companion.  This
        # mirrors the realistic case where SSP demand is generic brand
        # awareness, not RadioLife-managed couponed ads.
        return {
            "ad_id": "ssp_mock_creative_001",
            "name": "House sponsor",
            "type": "audio",
            "audio_url": (os.environ.get("SSP_MOCK_AUDIO_URL")
                                        or DEFAULT_MOCK_AUDIO_URL),
            "duration_sec": 10,
            "advertiser_name": "Brand Network (via SSP)",
            "attached_offer_id": None,
            "companion_image_url": None,
            "companion_cta_text": None,
            "companion_cta_url": None,
            "source": self.name,
            "source_provider": "mocked",
            "vast_xml": None,
        }


# ────────────────────── Real-SSP placeholders ──────────────────────
class _DeferredProvider:
    """Base for providers whose live integration is gated by Phase 42 v2.

    They register in the chain so admins see the architecture, but they
    `raise NotImplementedError` if anyone actually calls them — which
    in practice they don't, because the chain config defaults to
    `mocked` only."""
    name = "ssp_deferred"

    async def request_ad(self, **kwargs):
        raise NotImplementedError(
            f"{self.name} live SSP integration is deferred to Phase 42 v2. "
            "Set SSP_PROVIDER_CHAIN=mocked to use the mocked provider.")


class AdsWizzSSPProvider(_DeferredProvider):
    name = "ssp_adswizz"


class TritonSSPProvider(_DeferredProvider):
    name = "ssp_triton"


class MagniteSSPProvider(_DeferredProvider):
    name = "ssp_magnite"


# ────────────────────────── Chain ──────────────────────────
_PROVIDER_REGISTRY = {
    "mocked":  MockedSSPProvider,
    "adswizz": AdsWizzSSPProvider,
    "triton":  TritonSSPProvider,
    "magnite": MagniteSSPProvider,
}


def _resolve_chain() -> List[SSPProvider]:
    raw = os.environ.get("SSP_PROVIDER_CHAIN", "mocked")
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    out: List[SSPProvider] = []
    for p in parts:
        cls = _PROVIDER_REGISTRY.get(p)
        if cls is None:
            log.warning("[ssp] unknown provider in chain: %s — skipping", p)
            continue
        out.append(cls())
    return out


async def request_ssp_ad(*, station_id: str,
                                                      station_meta: Dict[str, Any],
                                                      user_ctx: Dict[str, Any],
                                                      country_code: Optional[str],
                                                      language: Optional[str]) -> Optional[Dict[str, Any]]:
    """Walks the configured provider chain in order.  First non-null
    response wins; on `NotImplementedError` we log + move on so a
    misconfigured deferred provider doesn't block the chain."""
    chain = _resolve_chain()
    for prov in chain:
        try:
            r = await prov.request_ad(
                station_id=station_id,
                station_meta=station_meta,
                user_ctx=user_ctx,
                country_code=country_code,
                language=language)
            if r:
                # Annotate with the provider name so the waterfall caller
                # can write it to the impression row.
                r.setdefault("source", prov.name)
                return r
        except NotImplementedError as nie:
            log.info("[ssp] provider %s deferred — %s", prov.name, nie)
            continue
        except Exception as e:
            log.warning("[ssp] provider %s raised: %s — falling through",
                                  prov.name, e)
            continue
    return None
