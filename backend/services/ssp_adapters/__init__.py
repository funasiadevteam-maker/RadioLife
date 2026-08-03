"""SSP adapter interface + 5 partner stubs. Phase 4.5.

Each adapter implements `bid(bid_request, headers) -> Optional[BidResponse]`.
Only `mock_ssp` returns a live bid by default. Real partner adapters need
endpoint URLs + credentials before they can return real bids.

Adapter discovery: the `ssp_partners` Mongo collection lists enabled partners
with their `adapter_module` (e.g., "mock_ssp"). `load_adapters()` dynamically
imports each and returns instances.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol

logger = logging.getLogger("bigfm.ads.ssp")


class SSPAdapter(Protocol):
    name: str
    endpoint_url: str
    timeout_ms: int = 200

    async def bid(self, bid_request: dict, headers: dict) -> Optional[dict]: ...


def load_adapters(partner_docs: list) -> list:
    """Given Mongo `ssp_partners` docs, dynamically import each adapter and
    return ready-to-call adapter instances."""
    out = []
    for p in partner_docs:
        if not p.get("enabled"):
            continue
        mod_name = p.get("adapter_module") or "mock_ssp"
        try:
            module = __import__(f"services.ssp_adapters.{mod_name}",
                                  fromlist=["Adapter"])
            ad = module.Adapter(
                endpoint_url=p.get("endpoint_url", ""),
                bidder_id=p.get("bidder_id", ""),
                secret=p.get("secret", ""),
                timeout_ms=int(p.get("timeout_ms", 200)),
                partner_id=p.get("_id") or p.get("name"),
            )
            out.append(ad)
        except Exception as e:
            logger.warning(f"Failed to load SSP adapter {mod_name}: {e}")
    return out
