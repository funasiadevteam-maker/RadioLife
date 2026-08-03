"""Phase 13a — A/B testing helpers for lifecycle campaigns.

When a campaign carries a non-empty `variants` array:
  variants: [
    { slug: "A", weight: 60,
      template_overrides: { email_subject, email_body,
                                  push_title, push_body, deep_link } },
    { slug: "B", weight: 40, template_overrides: {...} },
    ...
  ]

`pick_variant(campaign, user_id)` returns the chosen variant DICT
(or `None` for legacy single-template campaigns). Selection is:
  - deterministic: `hash(f"{campaign_id}:{user_id}")` mod total_weight,
  - sticky: persisted to `ab_assignments` on first pick so a user
    always sees the same variant for the lifetime of the campaign
    (even if weights are tweaked later).
"""
from __future__ import annotations
import hashlib
import math
from datetime import datetime, timezone
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stable_index(campaign_id: str, user_id: str, total_weight: int) -> int:
    """Stable mapping (campaign, user) → integer in [0, total_weight)."""
    seed = f"{campaign_id}:{user_id}".encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    n = int.from_bytes(digest[:8], "big", signed=False)
    return n % max(1, total_weight)


def normalize_variants(variants: list[dict]) -> list[dict]:
    """Strip / validate / default variant rows. Returns the cleaned list
    (preserves order). Raises ValueError on malformed input."""
    if not variants:
        return []
    seen: set[str] = set()
    out: list[dict] = []
    for v in variants:
        slug = (v.get("slug") or "").strip()
        if not slug:
            raise ValueError("variant slug required")
        if slug in seen:
            raise ValueError(f"duplicate variant slug: {slug}")
        seen.add(slug)
        w = v.get("weight")
        try:
            w_int = int(w) if w is not None else 1
        except (TypeError, ValueError) as e:
            raise ValueError(f"variant {slug}: weight not int") from e
        if w_int <= 0:
            raise ValueError(f"variant {slug}: weight must be > 0")
        overrides = v.get("template_overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError(f"variant {slug}: template_overrides must be dict")
        # Only allow the documented keys to keep the surface tight.
        allowed_keys = {"email_subject", "email_body",
                              "push_title", "push_body", "deep_link"}
        clean = {k: v_ for k, v_ in overrides.items() if k in allowed_keys}
        out.append({"slug": slug, "weight": w_int,
                       "template_overrides": clean})
    return out


def _pick_by_weight(variants: list[dict], idx: int) -> dict:
    """Given a stable idx in [0, total_weight), return the variant
    whose cumulative weight band contains idx."""
    cum = 0
    for v in variants:
        cum += int(v["weight"])
        if idx < cum:
            return v
    return variants[-1]  # safety — should be unreachable


async def pick_variant(db, *, campaign: dict, user_id: str) -> Optional[dict]:
    """Return the chosen variant dict (with slug + template_overrides),
    or None if the campaign has no variants (legacy path).

    Sticky: on first pick we persist `{campaign_id, user_id,
    variant_slug, assigned_at}` to `ab_assignments`; subsequent calls
    return the same variant even if the campaign weights are edited
    later."""
    variants = campaign.get("variants") or []
    if not variants:
        return None
    cid = campaign.get("id") or campaign.get("_id")
    if not cid:
        return None
    # Check sticky assignment first.
    existing = await db.ab_assignments.find_one(
        {"campaign_id": cid, "user_id": user_id})
    if existing and existing.get("variant_slug"):
        slug = existing["variant_slug"]
        for v in variants:
            if v.get("slug") == slug:
                return v
        # variant removed → re-roll (rare).
    total = sum(int(v.get("weight", 0)) for v in variants)
    if total <= 0:
        return None
    idx = _stable_index(cid, user_id, total)
    chosen = _pick_by_weight(variants, idx)
    await db.ab_assignments.update_one(
        {"campaign_id": cid, "user_id": user_id},
        {"$setOnInsert": {
            "campaign_id": cid, "user_id": user_id,
            "variant_slug": chosen["slug"], "assigned_at": _now()}},
        upsert=True)
    return chosen


def apply_overrides(base_template: dict,
                              overrides: dict | None) -> dict:
    """Returns a fresh dict = base merged with non-empty override keys."""
    out = dict(base_template or {})
    for k, v in (overrides or {}).items():
        if v not in (None, ""):
            out[k] = v
    return out


# ─── Stats: 2-proportion z-test for conversion-rate winner detection ──
def two_proportion_z(n_a: int, x_a: int, n_b: int, x_b: int) -> dict:
    """Returns `{p_value, z, p_a, p_b}`. p_value is two-sided.

    No external scipy dep — closed-form `erfc` from `math`.
    """
    if min(n_a, n_b) <= 0:
        return {"p_value": 1.0, "z": 0.0, "p_a": 0.0, "p_b": 0.0}
    p_a = x_a / n_a
    p_b = x_b / n_b
    p_pool = (x_a + x_b) / (n_a + n_b)
    denom = math.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    if denom == 0:
        return {"p_value": 1.0, "z": 0.0, "p_a": p_a, "p_b": p_b}
    z = (p_b - p_a) / denom
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return {"p_value": p_value, "z": z, "p_a": p_a, "p_b": p_b}


MIN_SEND_PER_VARIANT = 200
P_VALUE_SIGNIFICANT = 0.05


async def ensure_ab_indexes(db) -> None:
    await db.ab_assignments.create_index(
        [("campaign_id", 1), ("user_id", 1)], unique=True)
    await db.ab_assignments.create_index("campaign_id")
