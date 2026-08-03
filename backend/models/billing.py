"""Billing / subscription / Stripe checkout models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    """Frontend sends only the plan_id and the origin URL. NEVER the price."""
    plan_id: str = "premium_annual"
    currency: Optional[str] = None  # optional override; backend re-validates
    origin_url: str  # window.location.origin from the frontend


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


class CheckoutStatusResponse(BaseModel):
    session_id: str
    status: str  # 'open' | 'complete' | 'expired'
    payment_status: str  # 'paid' | 'unpaid' | 'no_payment_required'
    amount_total: float
    currency: str
    plan_id: Optional[str] = None
    is_premium: bool
    premium_tier: Optional[str] = None


class SubscriptionOut(BaseModel):
    is_premium: bool
    premium_tier: Optional[str] = None
    plan: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    reward_multiplier: float = 1.0


class PricingPlanOut(BaseModel):
    plan_id: str
    name: str
    description: str
    currency: str
    amount: float
    amount_display: str  # "$12.00", "AED 36.00", "₹999"
    interval: str  # "annual"
    features: list[str]
    is_premium: bool


class PricingConfigOut(BaseModel):
    mode: str  # 'test' | 'live'
    currency: str
    country_hint: Optional[str] = None
    plans: list[PricingPlanOut]
    test_banner: Optional[str] = None
