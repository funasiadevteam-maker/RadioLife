"""Phase 23 Session 1.5 — Pydantic models for the 2 NEW game collections.

Scoped to new primitives only. Does NOT redefine existing games_v2
collections (game_templates, game_campaigns, game_prizes, game_sessions,
game_compliance_settings, etc.) — those remain plain dicts in the existing
service layer, per the audit doc decision.

Use these models for response shaping + light validation; storage layer
writes plain dicts that match these shapes (matches existing codebase
convention).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


GAME_WINNER_STATUSES = {
    "pending_wallet_save",  # winner row exists, user hasn't saved to wallet yet
    "in_wallet",            # user saved to wallet, awaiting redemption
    "redeemed",             # staff scan succeeded
    "expired",              # past prize expiration without redemption
    "voided",               # admin override (fraud / dispute / etc.)
}

GAME_REDEMPTION_STATUSES = {
    "success",
    "staff_rejected",
    "expired",
    "already_redeemed",
    "fraud_block",
}


class GameWinner(BaseModel):
    """Canonical record of a win event. Immutable `prize_snapshot_json`
    protects the user against post-win prize edits by the advertiser."""
    winner_id: str
    game_campaign_id: str
    game_session_id: str
    user_id: str
    prize_id: str
    prize_snapshot_json: dict[str, Any]
    wallet_item_id: Optional[str] = None
    won_at: datetime
    status: str = "pending_wallet_save"
    voided_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GameRedemption(BaseModel):
    """Audit-log of every redemption attempt (success or rejection).
    Separate from `user_wallet_items.redeemed_at` (which is an inline flag);
    this collection retains failures + fraud blocks for compliance review."""
    redemption_id: str
    winner_id: str
    wallet_item_id: str
    business_id: Optional[str] = None
    redemption_code: str          # the QR token / promo code presented
    staff_user_id: Optional[str] = None
    redeemed_at: datetime
    status: str
    staff_note: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lng: Optional[float] = None
    client_metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
