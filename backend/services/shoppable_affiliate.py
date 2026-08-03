"""Phase 36d Turn 2 — Affiliate API abstraction (stub).

NO external HTTP calls in this turn. This is the integration plumbing only;
real providers land in a later phase.

Day-N integration: add provider modules under
    `services/shoppable_providers/{amazon,shareasale,...}.py`
and call `register_provider("amazon", lookup_fn)` at module import. Each
`lookup_fn` takes a URL and returns either `None` (URL doesn't match) or a
dict shaped `{title, image_url, price_cents, currency}`.
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("bigfm.shoppable_affiliate")

ProviderFn = Callable[[str], Optional[dict]]
_PROVIDERS: dict[str, ProviderFn] = {}


def register_provider(name: str, fetch_fn: ProviderFn) -> None:
    """Register a provider by name. Idempotent."""
    _PROVIDERS[name] = fetch_fn
    logger.info("[shoppable_affiliate] registered provider=%s", name)


def registered_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


def lookup_product_meta(url: str) -> Optional[dict]:
    """Try each registered provider in registration order. Returns the first
    non-None result, or None if no provider matches. NEVER makes external HTTP
    calls in this turn — providers may, but none are registered yet."""
    if not url:
        return None
    for name, fn in _PROVIDERS.items():
        try:
            r = fn(url)
            if r:
                return r
        except Exception as e:
            logger.warning("[shoppable_affiliate] provider=%s failed: %s", name, e)
    return None
