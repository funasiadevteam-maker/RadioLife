"""Jurisdiction-based sales tax for FUUSIC Marketplace orders (origin-based
on the store's location). A configurable rate table (tax_rules) resolves the
most-specific active rule for a store's country → state → county → city, and an
optional AI helper pre-fills rates. Merchants remain responsible for filing and
remitting the taxes they collect."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
TAX_MODEL = ("gemini", "gemini-2.5-flash")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_tax_id() -> str:
    return f"tax_{uuid.uuid4().hex[:12]}"


def norm_key(s: Optional[str]) -> Optional[str]:
    v = (s or "").strip().lower()
    return v or None


async def resolve_tax_rate(db, jurisdiction: Dict[str, Any]) -> Dict[str, Any]:
    """Most-specific active tax rule for a store jurisdiction (origin-based)."""
    j = jurisdiction or {}
    country = norm_key(j.get("country"))
    state = norm_key(j.get("state"))
    county = norm_key(j.get("county"))
    city = norm_key(j.get("city"))
    empty = {"rate_percent": 0.0, "label": None, "rule_id": None, "jurisdiction": j}
    if not country:
        return empty
    best, best_score = None, -1
    async for r in db.tax_rules.find({"active": True, "country_key": country}):
        rs, rc, rct = r.get("state_key"), r.get("county_key"), r.get("city_key")
        if rs and rs != state:
            continue
        if rc and rc != county:
            continue
        if rct and rct != city:
            continue
        score = (1 if rs else 0) + (1 if rc else 0) + (1 if rct else 0)
        if score > best_score:
            best, best_score = r, score
    if not best:
        best = await db.tax_rules.find_one({"active": True, "country_key": "*"})
    if not best:
        return empty
    return {"rate_percent": float(best.get("rate_percent", 0) or 0),
            "label": best.get("label"), "rule_id": best.get("rule_id"), "jurisdiction": j}


def calculate_tax(taxable_base_cents: int, rate_percent: float) -> int:
    return int(round(max(0, int(taxable_base_cents or 0)) * float(rate_percent or 0) / 100.0))


async def ai_estimate_rate(country: str, state: Optional[str] = None,
                           county: Optional[str] = None, city: Optional[str] = None) -> Dict[str, Any]:
    """Ask the LLM for a typical combined sales-tax / VAT rate for a jurisdiction."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    system = (
        "You are a sales-tax rate assistant. Given a jurisdiction, return ONLY JSON "
        '{"rate_percent": <number>, "label": "<short label>"} for the TOTAL combined '
        "sales tax / VAT rate a merchant typically charges there (country VAT/GST, or US "
        "state+county+city combined). Use general knowledge; if unsure use the standard "
        "country rate. A single number, never a range.")
    parts = ", ".join([p for p in [city, county, state, country] if p]) or country
    chat = (LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"tax_{uuid.uuid4().hex}",
                    system_message=system).with_model(*TAX_MODEL))
    resp = await chat.send_message(UserMessage(text=f"Jurisdiction: {parts}"))
    text = resp if isinstance(resp, str) else getattr(resp, "content", str(resp))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    data = json.loads(m.group(0)) if m else {}
    rate = float(data.get("rate_percent", 0) or 0)
    return {"rate_percent": max(0.0, min(rate, 40.0)),
            "label": (data.get("label") or f"{parts} tax")[:80]}


async def ensure_tax_indexes(db) -> None:
    await db.tax_rules.create_index("rule_id", unique=True)
    await db.tax_rules.create_index([
        ("country_key", 1), ("state_key", 1), ("county_key", 1), ("city_key", 1)])


__all__ = ["resolve_tax_rate", "calculate_tax", "ai_estimate_rate",
           "ensure_tax_indexes", "new_tax_id", "norm_key"]
