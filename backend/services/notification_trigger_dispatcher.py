"""Phase AD.12 bundle — Notification Trigger Recipes.

Advertisers pick a pre-baked event to gate their notification campaign
on (e.g., "notify me the first time this user saves any coupon").  The
dispatcher listens for those events and mints deliveries for matching
LIVE campaigns.

Recipes are a fixed registry — new recipes require a backend hook so
the dispatcher can subscribe.  The `custom` escape-hatch remains
available in the wizard for advertisers who want to type a raw event
name.

Upstream emitter wiring status (Phase B · 2026-07-27)
--------------------------------------------------
- coupon_saved                              WIRED — routes/ads_public.py action_save_coupon
- predict_win_correct                  WIRED — services/predict_win_award_pipeline.py
- first_login                                  WIRED — auth.py login() + google exchange (Phase A)
- station_played_5x                      WIRED — routes/listener_sessions.py listen_join() (Phase A)
- flagship_played_first_time      WIRED — routes/preroll_ads.py preroll_request() (Phase A)
- game_win_high_value                    WIRED — services/games_v2_winners_redemptions.py record_winner() (Phase A)
- coupon_expiring_24h                  WIRED — services/coupon_expiring_scanner.py hourly sweep (Phase A)
- podcast_completed                      WIRED — services/podcast_progress_service.py record_progress() @ 90% (Phase B)
- bill_split_invited                    WIRED — services/bill_split_service.py create_split() (Phase E)
- bill_split_share_paid                WIRED — services/bill_split_service.py pay_share() (Phase E)
- flagship_boost_bid_submitted    WIRED — services/flagship_boost_service.py submit_bid() (Phase F)
- flagship_boost_bid_won              WIRED — services/flagship_boost_service.py approve_bid() (Phase F)
- flagship_boost_bid_lost            WIRED — services/flagship_boost_service.py approve_bid()/reject_bid() (Phase F)
- podcast_completion_awarded    WIRED — services/podcast_completion_award_pipeline.py on_podcast_completed() (Phase G)
- trivia_prize_won                    WIRED — services/trivia_sponsor_award_pipeline.py on_trivia_room_done() (Phase H)
- rj_sponsored_read_approved  WIRED — services/rj_sponsored_read_service.py on approve/auto-approve (Phase I)
- location_boost_matched        WIRED — services/location_boost_service.record_impression() (Phase J)
- wallet_top_up                              TODO — needs user-side wallet-topup endpoint (BLOCKED)
- merchant_visit_nearby                TODO — needs geofence / visit-detection event (BLOCKED)

Each TODO can be trivially added by calling
`dispatch_event(db, event_name="...", user_id=...)` from the relevant
service; the dispatcher is silent-on-error so a broken hook can never
break upstream flows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.trigger_dispatcher")


# ─── Recipe registry ────────────────────────────────────────────
# `id`             : advertiser-facing identifier (also the event name).
# `event_name`  : internal emitter event name (matches `id`).
# `default_delay_minutes`: notification fires this many minutes AFTER
#                                    the trigger event.  0 = immediate.
RECIPES: List[Dict[str, Any]] = [
    {"id": "coupon_saved",
      "label": "Coupon saved",
      "description": "Fires when a user saves any coupon in the wallet.",
      "event_name": "coupon_saved",
      "category":  "wallet",
      "default_delay_minutes": 0},
    {"id": "coupon_expiring_24h",
      "label": "Coupon expiring in 24 hours",
      "description": "Reminds a user their saved coupon expires in the next 24h.",
      "event_name": "coupon_expiring_24h",
      "category":  "wallet",
      "default_delay_minutes": 0},
    {"id": "podcast_completed",
      "label": "Podcast episode completed",
      "description": "Fires when a user completes any podcast episode (≥95%).",
      "event_name": "podcast_completed",
      "category":  "listening",
      "default_delay_minutes": 5},
    {"id": "station_played_5x",
      "label": "Station played 5 times",
      "description": "Fires when a user's play-count on ANY station crosses 5.",
      "event_name": "station_played_5x",
      "category":  "listening",
      "default_delay_minutes": 0},
    {"id": "wallet_top_up",
      "label": "Wallet top-up",
      "description": "Fires when a user tops up their BigFM wallet.",
      "event_name": "wallet_top_up",
      "category":  "wallet",
      "default_delay_minutes": 0},
    {"id": "first_login",
      "label": "First login (new user)",
      "description": "Fires on a user's very first login.",
      "event_name": "first_login",
      "category":  "onboarding",
      "default_delay_minutes": 60},
    {"id": "flagship_played_first_time",
      "label": "Flagship station — first play",
      "description": "Fires the first time a user tunes into any flagship station.",
      "event_name": "flagship_played_first_time",
      "category":  "listening",
      "default_delay_minutes": 0},
    {"id": "predict_win_correct",
      "label": "Predict & Win — correct pick",
      "description": "Fires when a user calls a market correctly on Predict & Win.",
      "event_name": "predict_win_correct",
      "category":  "games",
      "default_delay_minutes": 0},
    {"id": "merchant_visit_nearby",
      "label": "Nearby merchant visit",
      "description": "Fires when a user is detected near a partner merchant location.",
      "event_name": "merchant_visit_nearby",
      "category":  "geo",
      "default_delay_minutes": 0},
    {"id": "game_win_high_value",
      "label": "High-value game win",
      "description": "Fires when a user wins ≥100 points in any game session.",
      "event_name": "game_win_high_value",
      "category":  "games",
      "default_delay_minutes": 0},
    {"id": "bill_split_invited",
      "label": "Bill split — invited",
      "description": "Fires when the initiator sends someone a split-the-bill invite.",
      "event_name": "bill_split_invited",
      "category":  "commerce",
      "default_delay_minutes": 0},
    {"id": "bill_split_share_paid",
      "label": "Bill split — share paid",
      "description": "Fires when a user pays their share of a split bill; `completed` is true on the last share.",
      "event_name": "bill_split_share_paid",
      "category":  "commerce",
      "default_delay_minutes": 0},
    {"id": "flagship_boost_bid_submitted",
      "label": "Flagship boost — bid submitted",
      "description": "Confirmation to the advertiser that their boost bid was received.",
      "event_name": "flagship_boost_bid_submitted",
      "category":  "advertiser",
      "default_delay_minutes": 0},
    {"id": "flagship_boost_bid_won",
      "label": "Flagship boost — bid won",
      "description": "Advertiser's boost bid was approved by admin and their activation is scheduled/live.",
      "event_name": "flagship_boost_bid_won",
      "category":  "advertiser",
      "default_delay_minutes": 0},
    {"id": "flagship_boost_bid_lost",
      "label": "Flagship boost — bid lost",
      "description": "Advertiser's boost bid was outbid or rejected.",
      "event_name": "flagship_boost_bid_lost",
      "category":  "advertiser",
      "default_delay_minutes": 0},
    {"id": "podcast_completion_awarded",
      "label": "Podcast completion — reward awarded",
      "description": "User finished a sponsored podcast episode and earned points or a voucher.",
      "event_name": "podcast_completion_awarded",
      "category":  "podcasts",
      "default_delay_minutes": 0},
    {"id": "trivia_prize_won",
      "label": "Trivia — sponsored prize won",
      "description": "User finished a sponsored trivia room in a winning rank; prize is available in wallet.",
      "event_name": "trivia_prize_won",
      "category":  "games",
      "default_delay_minutes": 0},
    {"id": "rj_sponsored_read_approved",
      "label": "AI-RJ sponsored read — approved",
      "description": "Advertiser's sponsored AI-RJ read passed moderation and is live on-air.",
      "event_name": "rj_sponsored_read_approved",
      "category":  "advertiser",
      "default_delay_minutes": 0},
    {"id": "location_boost_matched",
      "label": "Location-boost ad — user in geofence",
      "description": "User's ping fell inside an active location-boost campaign's geofence and a matching creative was served.",
      "event_name": "location_boost_matched",
      "category":  "geo",
      "default_delay_minutes": 0},
    {"id": "takeover_scheduled",
      "label": "Radio Takeover Hour — scheduled",
      "description": "Advertiser's Radio Takeover Hour has been approved / auto-activated and is scheduled to go live at start_at.",
      "event_name": "takeover_scheduled",
      "category":  "advertiser",
      "default_delay_minutes": 0},
    {"id": "takeover_bonus_awarded",
      "label": "Radio Takeover Hour — listener bonus awarded",
      "description": "Listener stayed tuned through a Radio Takeover Hour for the threshold duration and earned the bonus prize.",
      "event_name": "takeover_bonus_awarded",
      "category":  "rewards",
      "default_delay_minutes": 0},
    # ── Phase R — News Radio Expansion ──
    {"id": "news_alert_breaking",
      "label": "News — breaking alert",
      "description": "Fires when an admin promotes a news headline to breaking; broadcasts to region-matching listeners.",
      "event_name": "news_alert_breaking",
      "category":  "news",
      "default_delay_minutes": 0},
    {"id": "news_bulletin_ready",
      "label": "News — bulletin generated",
      "description": "Fires to the admin who generated a news bulletin, confirming that LLM script + TTS audio are ready to publish.",
      "event_name": "news_bulletin_ready",
      "category":  "news",
      "default_delay_minutes": 0},
]

RECIPE_IDS = {r["id"] for r in RECIPES}


def recipes_for_api() -> List[Dict[str, Any]]:
    # Phase C.0 field-name harmonisation: publish BOTH `id` and `key` so
    # existing callers (`id`) and new callers (`key`) both work.  The
    # value is identical — `key` is a pure alias.
    return [{**r, "key": r["id"]} for r in RECIPES]


def is_valid_recipe(trigger_type: Optional[str]) -> bool:
    if not trigger_type:
        return False
    return trigger_type in RECIPE_IDS


# ─── Event dispatcher ───────────────────────────────────────────
async def dispatch_event(db, *, event_name: str, user_id: Optional[str],
                                                  payload: Optional[Dict[str, Any]] = None
                                                  ) -> Dict[str, Any]:
    """Called by upstream emitters when a trigger event happens.
    Finds LIVE trigger-based notification campaigns matching this
    event_name and mints deliveries via the AD.12 pipeline.  Silent
    on error — a broken trigger must NEVER block the upstream flow."""
    if not event_name or not user_id:
        return {"minted": 0}
    try:
        from services import ad12_notification_service as _svc
        from services.commission_service import calculate_platform_fee
    except Exception:
        return {"minted": 0}
    now = datetime.now(timezone.utc)
    minted = 0
    try:
        # Load the user record once for targeting.
        user = await db.users.find_one({"user_id": user_id})
        if not user:
            return {"minted": 0}
        # Find LIVE trigger-based campaigns matching this event.
        cursor = db.notification_campaigns.find({
            "status": "live",
            "delivery_schedule": "trigger_based",
            "trigger_type": event_name,
        })
        async for c in cursor:
            if not await _svc._matches_targeting(user, c):
                continue
            max_d = c.get("max_deliveries")
            if max_d and int(c.get("delivered_count") or 0) >= int(max_d):
                continue
            delivery_id = _svc._gen("dlv")
            try:
                await db.notification_deliveries.insert_one({
                    "_id":                                          delivery_id,
                    "delivery_id":                          delivery_id,
                    "user_id":                                    user_id,
                    "notification_campaign_id":      c["notification_campaign_id"],
                    "advertiser_id":                        c["advertiser_id"],
                    "sponsoring_merchant_id":          c.get("sponsoring_merchant_id"),
                    "title":                                      c["title"],
                    "body":                                        c["body"],
                    "cta_text":                                c.get("cta_text"),
                    "target_url":                            c["target_url"],
                    "icon_url":                                c.get("icon_url"),
                    "image_url":                              c.get("image_url"),
                    "channel":                                  c.get("channel", "in_app"),
                    "delivered_at":                        now,
                    "opened_at":                              None,
                    "clicked_at":                            None,
                    "dismissed_at":                        None,
                    "billed":                                    False,
                    "triggered_by_event":              event_name,
                    "triggered_payload":                payload or {},
                })
            except Exception:
                continue                # duplicate = already delivered.
            # Fire billing (reuse the AD.12 billing path).
            async def _fee_calc(db, *, business_category, transaction_type,
                                                        gross_cents):
                return await calculate_platform_fee(
                    db, business_category=business_category,
                    transaction_type=transaction_type,
                    gross_cents=gross_cents)
            try:
                await _svc._bill_delivery(
                    db, delivery_id=delivery_id, campaign=c,
                    user_id=user_id,
                    commission_service_calc=_fee_calc)
            except Exception:
                logger.warning("[trigger] billing failed for %s", delivery_id)
            minted += 1
        return {"minted": minted, "event_name": event_name}
    except Exception:
        logger.exception("[trigger] dispatch failed for %s", event_name)
        return {"minted": minted, "event_name": event_name,
                      "error": "internal"}


__all__ = [
    "RECIPES",
    "RECIPE_IDS",
    "recipes_for_api",
    "is_valid_recipe",
    "dispatch_event",
]
