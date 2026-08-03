"""Phase ADMOD.1 — OpenAI Moderation wrapper via the Emergent LLM key.

Uses `litellm.amoderation` routed through the Emergent integration proxy
(https://integrations.emergentagent.com/llm) so the Emergent Universal
LLM Key is accepted.  Falls back gracefully when the key is missing or
the API errors — moderation is an ASSIST, never a hard gate.

Returns a compact structured dict that gets persisted on the
`ad_creative_reviews` row so reviewers see AI signal at a glance.  Raw
payload is kept for auditability.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("bigfm.ad_moderation")

MODEL = "omni-moderation-latest"
# Reviewers see the "AI flag" badge when the highest score crosses this.
DEFAULT_FLAG_THRESHOLD = 0.35
# Emergent proxy — required when using EMERGENT_LLM_KEY (a Universal key).
EMERGENT_PROXY_BASE = os.environ.get(
    "INTEGRATION_PROXY_URL", "https://integrations.emergentagent.com") \
    + "/llm"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_result(*, error: Optional[str] = None,
                                    action: str = "skipped") -> Dict[str, Any]:
    return {
        "ran_at":                      _now_iso(),
        "model":                        MODEL,
        "flagged":                    False,
        "categories":              {},
        "category_scores":      {},
        "highest_category":  "",
        "highest_score":        0.0,
        "action_taken":          action,
        "error":                        error,
    }


def _summarize(result) -> Dict[str, Any]:
    """LiteLLM returns an OpenAIModerationResult with `categories` (dict),
    `category_scores` (dict), `flagged` (bool)."""
    categories = getattr(result, "categories", {}) or {}
    scores = getattr(result, "category_scores", {}) or {}
    if not isinstance(categories, dict):
        categories = dict(categories)
    if not isinstance(scores, dict):
        scores = dict(scores)
    highest_cat, highest = "", 0.0
    for k, v in scores.items():
        # Skip the legacy slash-named duplicates so we don't double-count.
        if "/" in k:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > highest:
            highest, highest_cat = fv, k
    flagged = bool(getattr(result, "flagged", False))
    action = "flagged" if flagged or highest >= DEFAULT_FLAG_THRESHOLD else "clean"
    return {
        "ran_at":                      _now_iso(),
        "model":                        MODEL,
        "flagged":                    bool(flagged) or highest >= DEFAULT_FLAG_THRESHOLD,
        "categories":              {k: bool(v) for k, v in categories.items()
                                                          if "/" not in k},
        "category_scores":      {k: float(v) for k, v in scores.items()
                                                          if "/" not in k
                                                          and isinstance(v, (int, float))},
        "highest_category":  highest_cat,
        "highest_score":        round(highest, 4),
        "action_taken":          action,
        "error":                        None,
    }


def _combine_texts(parts: Iterable[Optional[str]]) -> str:
    return "\n".join(p for p in parts if p and isinstance(p, str)).strip()


async def moderate_creative_text(
        parts: List[Optional[str]]) -> Dict[str, Any]:
    """Run OpenAI moderation on the combined text of a creative.

    Never raises — always returns a structured dict.  When the key is
    missing or the API errors, returns a "skipped" record so the caller
    can still persist a moderation footprint on the review row.
    """
    text = _combine_texts(parts)
    if not text:
        return _empty_result(action="empty_input")

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        logger.warning("[ad-moderation] EMERGENT_LLM_KEY missing — skipping")
        return _empty_result(error="missing_emergent_llm_key")

    try:
        # `litellm.amoderation` via the Emergent integration proxy accepts
        # the Universal Key.  OpenAI's moderation model itself is FREE.
        import litellm
        resp = await litellm.amoderation(
            input=text, model=MODEL, api_key=key,
            api_base=EMERGENT_PROXY_BASE)
        result = resp.results[0]
        out = _summarize(result)
        # Attach raw for audit — bounded size for Mongo doc safety.
        try:
            out["raw"] = resp.model_dump()
        except Exception:
            try:
                out["raw"] = dict(resp)
            except Exception:
                out["raw"] = None
        return out
    except Exception as e:  # noqa: BLE001 — graceful skip on any failure
        logger.warning("[ad-moderation] API call failed: %s", e)
        return _empty_result(error=str(e)[:200], action="error")


__all__ = ["moderate_creative_text", "MODEL", "DEFAULT_FLAG_THRESHOLD"]
