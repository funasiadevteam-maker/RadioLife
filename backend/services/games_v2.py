"""Phase 8a — Gamification Marketplace engine, seeding & Phase 5 migration.

This module is the *single source of truth* for the new programmatic-game
framework.  It owns:

  • Mongo schema bootstrap (`ensure_games_v2_indexes`)
  • Template + house-campaign seeding (`seed_games_v2`)
  • Phase 5 → Phase 8a migration (`migrate_phase5_games`)
  • The award engine (probability draw + atomic inventory) used by routes
  • Wallet-item materialization on prize claim

All randomness uses `secrets.SystemRandom`; seeds (server + client) are
persisted on every session so a future audit endpoint can prove fairness.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import random
import json
import logging
import math
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import qrcode

from services.bigcoin import award as bigcoin_award

logger = logging.getLogger("bigfm.games_v2")


# =====================================================================
# Constants & template defaults
# =====================================================================
ACTIVE_GAME_TYPES = {"spin_wheel", "scratch_card", "quiz", "mystery_box"}
INACTIVE_GAME_TYPES = {"slot_machine", "memory_match", "word_puzzle"}
ALL_GAME_TYPES = ACTIVE_GAME_TYPES | INACTIVE_GAME_TYPES

PRIZE_TYPES = {
    "bigcoin", "coupon", "gift_card", "free_item", "sample",
    "ticket_entry", "badge", "exclusive_unlock", "premium_credit_days",
    "sponsor_collectible",
}

OBJECTIVES = {
    "coupon_save", "drive_visit", "brand_awareness",
    "listener_engagement", "lead_generation", "app_install",
}

BID_TYPES = {
    "per_play", "per_win", "per_save", "per_redemption",
    "flat", "platform_funded",
}

CAMPAIGN_STATUSES = {
    "draft", "pending_approval", "active",
    "paused", "rejected", "ended", "archived",
}

REDEMPTION_METHODS = {
    "in_app_wallet", "qr_code", "promo_code", "sms_link", "partner_pos",
}

UNLOCK_REASONS = {
    "milestone_30min", "milestone_60min", "listening_streak",
    "lobby_join", "ad_save", "qr_scan", "sms_link",
    "manual_admin_grant", "platform_default",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, length: int = 12) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


# =====================================================================
# Index bootstrap
# =====================================================================
async def ensure_games_v2_indexes(db):
    await db.game_templates.create_index([("template_id", 1)], unique=True)
    await db.game_templates.create_index([("active", 1), ("game_type", 1)])

    await db.game_campaigns.create_index([("campaign_id", 1)], unique=True)
    await db.game_campaigns.create_index([("status", 1), ("end_at", 1)])
    await db.game_campaigns.create_index([("advertiser_id", 1), ("status", 1)])
    await db.game_campaigns.create_index([("is_platform_funded", 1), ("status", 1)])
    await db.game_campaigns.create_index([("template_id", 1)])

    await db.game_prizes.create_index([("prize_id", 1)], unique=True)
    await db.game_prizes.create_index([("campaign_id", 1), ("active", 1)])

    await db.game_sessions.create_index([("session_id", 1)], unique=True)
    await db.game_sessions.create_index([("user_id", 1), ("campaign_id", 1)])
    await db.game_sessions.create_index([("user_id", 1), ("started_at", -1)])
    await db.game_sessions.create_index([("status", 1)])

    await db.game_inventory_ledger.create_index([("campaign_id", 1), ("ts", -1)])
    await db.game_inventory_ledger.create_index([("session_id", 1)])

    await db.game_redemption_rules.create_index([("campaign_id", 1)], unique=True)
    await db.game_compliance_settings.create_index([("campaign_id", 1)], unique=True)

    await db.user_game_unlocks.create_index(
        [("user_id", 1), ("campaign_id", 1), ("unlocked_at", -1)])
    await db.user_game_unlocks.create_index(
        [("expires_at", 1)], expireAfterSeconds=0)

    await db.game_analytics_events.create_index([("campaign_id", 1), ("ts", -1)])
    await db.game_analytics_events.create_index([("campaign_id", 1), ("event_type", 1)])
    await db.game_analytics_events.create_index([("user_id", 1), ("ts", -1)])

    await db.game_rate_limits.create_index([("ttl_at", 1)], expireAfterSeconds=0)


# =====================================================================
# Template seeding
# =====================================================================
_TEMPLATES = [
    {
        "template_id": "tpl_spin_wheel", "game_type": "spin_wheel",
        "name": "Spin Wheel",
        "description": "Classic prize wheel — listeners spin to win one of N weighted segments.",
        "preview_image_url": "/static/games/spin_preview.png",
        "default_config_json": {
            "segments": [
                {"label": "5 BigCoin", "color": "#ff2d95", "probability_weight": 40},
                {"label": "20 BigCoin", "color": "#5dbcff", "probability_weight": 25},
                {"label": "50 BigCoin", "color": "#14e29a", "probability_weight": 15},
                {"label": "100 BigCoin", "color": "#ffb547", "probability_weight": 10},
                {"label": "200 BigCoin", "color": "#a16cff", "probability_weight":  5},
                {"label": "Sponsor coupon", "color": "#ff5a6e", "probability_weight":  5},
            ],
            "spin_duration_ms": 4000, "sound_url": None,
        },
        "min_prizes": 2, "max_prizes": 12,
        "active": True, "version": 1,
    },
    {
        "template_id": "tpl_scratch_card", "game_type": "scratch_card",
        "name": "Scratch Card",
        "description": "Tap & drag to reveal the prize hidden beneath the foil.",
        "preview_image_url": "/static/games/scratch_preview.png",
        "default_config_json": {
            "cover_image_url": "/static/games/scratch_cover.png",
            "reveal_image_url": "/static/games/scratch_reveal.png",
            "scratch_threshold": 0.5,
            "prize_text_template": "You won {prize_title}!",
        },
        "min_prizes": 1, "max_prizes": 6,
        "active": True, "version": 1,
    },
    {
        "template_id": "tpl_quiz", "game_type": "quiz",
        "name": "Quiz",
        "description": "1-N multiple-choice questions; meet the threshold to win.",
        "preview_image_url": "/static/games/quiz_preview.png",
        "default_config_json": {
            "questions": [],
            "time_per_question_s": 15,
            "min_correct_to_win": 1,
            "dynamic_pool": False,    # set true for house migrated games
        },
        "min_prizes": 1, "max_prizes": 6,
        "active": True, "version": 1,
    },
    {
        "template_id": "tpl_mystery_box", "game_type": "mystery_box",
        "name": "Mystery Box",
        "description": "Pick one of N boxes — the prize is revealed on tap.",
        "preview_image_url": "/static/games/mystery_preview.png",
        "default_config_json": {
            "boxes": [
                {"label": "Box A", "image_url": "/static/games/box_a.png"},
                {"label": "Box B", "image_url": "/static/games/box_b.png"},
                {"label": "Box C", "image_url": "/static/games/box_c.png"},
            ],
            "num_boxes": 3, "reveal_animation_ms": 1200,
        },
        "min_prizes": 1, "max_prizes": 9,
        "active": True, "version": 1,
    },
    # ----- Phase 8b — slot / memory / word (activated this phase) ---------
    {"template_id": "tpl_slot_machine", "game_type": "slot_machine",
     "name": "Slot Machine",
     "description": "3-reel match-3 prize game.  Match symbols on the middle row to win — pure visual theatre over a server-decided outcome.",
     "preview_image_url": "/static/games/slot_preview.png",
     "default_config_json": {
         "reels": [
             [{"label": "🍒", "weight": 30}, {"label": "🍋", "weight": 25},
              {"label": "🍇", "weight": 20}, {"label": "⭐", "weight": 15},
              {"label": "💎", "weight": 10}],
             [{"label": "🍒", "weight": 30}, {"label": "🍋", "weight": 25},
              {"label": "🍇", "weight": 20}, {"label": "⭐", "weight": 15},
              {"label": "💎", "weight": 10}],
             [{"label": "🍒", "weight": 30}, {"label": "🍋", "weight": 25},
              {"label": "🍇", "weight": 20}, {"label": "⭐", "weight": 15},
              {"label": "💎", "weight": 10}],
         ],
         "win_combos": [{"symbols": ["💎", "💎", "💎"], "weight": 1},
                              {"symbols": ["⭐", "⭐", "⭐"], "weight": 5},
                              {"symbols": ["any", "any", "any-match-3"], "weight": 10}],
         "spin_duration_ms": 3200,
     },
     "min_prizes": 1, "max_prizes": 6,
     "active": True, "version": 1},
    {"template_id": "tpl_memory_match", "game_type": "memory_match",
     "name": "Memory Match",
     "description": "Flip pairs of branded cards to match all sets before time's up.",
     "preview_image_url": "/static/games/memory_preview.png",
     "default_config_json": {
         "grid_size": 4,          # 4×4 = 8 pairs
         "pairs": [
             {"image_url": "/static/games/memory_card_1.png", "label": "🎵"},
             {"image_url": "/static/games/memory_card_2.png", "label": "🎧"},
             {"image_url": "/static/games/memory_card_3.png", "label": "🎤"},
             {"image_url": "/static/games/memory_card_4.png", "label": "🪩"},
             {"image_url": "/static/games/memory_card_5.png", "label": "💃"},
             {"image_url": "/static/games/memory_card_6.png", "label": "🕺"},
             {"image_url": "/static/games/memory_card_7.png", "label": "🥁"},
             {"image_url": "/static/games/memory_card_8.png", "label": "🎶"},
         ],
         "time_limit_sec": 90,
         "min_correct_pairs_to_win": 6,
     },
     "min_prizes": 1, "max_prizes": 4,
     "active": True, "version": 1},
    {"template_id": "tpl_word_puzzle", "game_type": "word_puzzle",
     "name": "Word Puzzle",
     "description": "Guess the phrase one letter at a time, before strikes run out.",
     "preview_image_url": "/static/games/word_preview.png",
     "default_config_json": {
         "phrases": [
             {"phrase": "TUM HI HO", "hint": "Aashiqui 2 lead single"},
             {"phrase": "KARAK CHAI", "hint": "Dubai's favourite drink"},
             {"phrase": "FRIDAY NIGHT MEHFIL", "hint": "RadioLife channel"},
             {"phrase": "BOLLYWOOD HITS", "hint": "Music genre"},
             {"phrase": "DJ NIGHTS", "hint": "Late-week vibes"},
         ],
         "max_strikes": 6,
         "time_limit_sec": 120,
     },
     "min_prizes": 1, "max_prizes": 4,
     "active": True, "version": 1},
    # ----- Phase 23 Session 4.5b — Pick-a-Card (genuinely new) -----------
    {"template_id": "tpl_pick_a_card", "game_type": "pick_a_card",
     "name": "Pick a Card",
     "description": "Listener taps 1 of N face-down cards; chosen card flips to reveal the prize (server-decided weighted outcome).",
     "preview_image_url": "/static/games/pick_a_card_preview.png",
     "default_config_json": {
         "num_cards": 3,
         "flip_duration_ms": 550,
     },
     "min_prizes": 2, "max_prizes": 6,
     "active": True, "version": 1},
]


async def seed_games_v2(db) -> dict:
    """Idempotent: create templates that don't exist yet. Never drops them.
    Also heals legacy placeholders that were seeded inactive in 8a."""
    created = 0
    updated = 0
    for t in _TEMPLATES:
        # First, plain upsert (won't touch existing fields)
        res = await db.game_templates.update_one(
            {"template_id": t["template_id"]},
            {"$setOnInsert": {**t, "created_at": _now()}},
            upsert=True,
        )
        if res.upserted_id:
            created += 1
            continue
        # Phase 23 Session 4.5b: the legacy slot/memory/word_puzzle
        # heal-active block was REMOVED so the listener-facing hide
        # survives across backend reboots.  Those three templates are
        # now intentionally `active=False` in production; existing
        # campaigns of those types still play via the GAME_DISPATCH
        # router on the frontend.  Heal only the empty-config rows
        # without re-activating them.
        if t["template_id"] in (
                "tpl_slot_machine", "tpl_memory_match", "tpl_word_puzzle"):
            res2 = await db.game_templates.update_one(
                {"template_id": t["template_id"],
                 "default_config_json": {}},
                {"$set": {"default_config_json": t["default_config_json"],
                            "description": t["description"]}},
            )
            if res2.modified_count: updated += 1
    return {"templates_created": created, "templates_updated": updated,
            "templates_total": len(_TEMPLATES)}


# =====================================================================
# Phase 5 → Phase 8a migration (idempotent)
# =====================================================================
HOUSE_SPIN_ID = "cmp_house_spin"
HOUSE_TRIVIA_ID = "cmp_house_trivia"
HOUSE_LYRIC_ID = "cmp_house_lyric"
MIGRATION_FLAG_DOC = {"_id": "phase5_migration_complete"}


async def _rename_phase5_legacy(db) -> list[str]:
    """Move legacy Phase 5 collections out of the way so Phase 8a can take
    over the `game_sessions` / `games` collection names with a clean schema.
    Safe to call before *anything* else; doesn't depend on templates."""
    coll_names = await db.list_collection_names()
    pairs = [
        ("games", "games_legacy_phase5"),
        ("game_sessions", "game_sessions_legacy_phase5"),
    ]
    renamed = []
    for src, dst in pairs:
        if dst in coll_names and src in coll_names:
            # Both exist (we re-seeded earlier).  Drop the empty new one.
            if await db[src].count_documents({}) == 0:
                await db[src].drop()
                continue
            # New one has real data — leave alone, skip rename
            continue
        if src in coll_names and dst not in coll_names:
            try:
                await db[src].rename(dst)
                renamed.append(dst)
            except Exception as e:
                logger.warning(f"rename {src}->{dst} failed: {e}")
    return renamed


async def migrate_phase5_games(db, actor_user_id: str = "system") -> dict:
    """One-shot, idempotent.  Safe to re-run.

    Order of operations:
      1. Rename legacy collections aside (handled by _rename_phase5_legacy).
      2. Re-ensure indexes (now safe — Phase 8a collections are fresh).
      3. Seed templates.
      4. Create 3 platform-funded campaigns.
      5. Backfill `user_game_unlocks` (no-op in 8a since all 3 house campaigns
         are open_to_all).
    """
    summary: dict[str, Any] = {
        "legacy_renamed": [], "templates_created": 0,
        "house_campaigns_created": 0, "house_campaigns_existing": 0,
        "unlocks_backfilled": 0,
    }
    summary["legacy_renamed"] = await _rename_phase5_legacy(db)
    await ensure_games_v2_indexes(db)
    s = await seed_games_v2(db)
    summary["templates_created"] = s["templates_created"]

    house = [
        {"id": HOUSE_SPIN_ID, "template_id": "tpl_spin_wheel",
         "title": "RadioLife Daily Spin",
         "description": "Spin every 4 hours for BigCoin & sponsor perks.",
         "prizes": [
             {"title": "5 BigCoin", "prize_type": "bigcoin", "value_amount": 5,
              "probability_weight": 40, "inventory_total": 100000,
              "redemption_method": "in_app_wallet"},
             {"title": "20 BigCoin", "prize_type": "bigcoin", "value_amount": 20,
              "probability_weight": 25, "inventory_total": 50000,
              "redemption_method": "in_app_wallet"},
             {"title": "50 BigCoin", "prize_type": "bigcoin", "value_amount": 50,
              "probability_weight": 15, "inventory_total": 20000,
              "redemption_method": "in_app_wallet"},
             {"title": "100 BigCoin", "prize_type": "bigcoin", "value_amount": 100,
              "probability_weight": 10, "inventory_total": 10000,
              "redemption_method": "in_app_wallet"},
             {"title": "200 BigCoin", "prize_type": "bigcoin", "value_amount": 200,
              "probability_weight":  5, "inventory_total":  5000,
              "redemption_method": "in_app_wallet"},
             {"title": "Karak Cafe 10% off", "prize_type": "coupon",
              "value_amount": 1000, "value_currency": "AED",
              "probability_weight": 5, "inventory_total": 5000,
              "redemption_method": "qr_code",
              "description": "Show QR at any Karak Cafe location"},
         ],
         "config_overrides": None},
        {"id": HOUSE_TRIVIA_ID, "template_id": "tpl_quiz",
         "title": "RadioLife Music Trivia",
         "description": "Test your music knowledge — up to 3 plays per day.",
         "prizes": [
             {"title": "10 BigCoin (correct)", "prize_type": "bigcoin",
              "value_amount": 10, "probability_weight": 100,
              "inventory_total": 999999, "max_per_user": 0,
              "redemption_method": "in_app_wallet"},
         ],
         "config_overrides": {"min_correct_to_win": 1, "dynamic_pool": True,
                                "dynamic_source": "tracks",
                                "time_per_question_s": 15}},
        {"id": HOUSE_LYRIC_ID, "template_id": "tpl_quiz",
         "title": "RadioLife Lyric Hunt",
         "description": "Complete the lyric in 4 tries — up to 3 plays per day.",
         "prizes": [
             {"title": "15 BigCoin (correct)", "prize_type": "bigcoin",
              "value_amount": 15, "probability_weight": 100,
              "inventory_total": 999999, "max_per_user": 0,
              "redemption_method": "in_app_wallet"},
         ],
         "config_overrides": {"min_correct_to_win": 1, "dynamic_pool": True,
                                "dynamic_source": "lyric_puzzles",
                                "time_per_question_s": 15}},
    ]
    for h in house:
        existing = await db.game_campaigns.find_one({"campaign_id": h["id"]})
        if existing:
            summary["house_campaigns_existing"] += 1
            # Phase 8a.1 — make house campaigns immortal (no end_at).
            # Heal already-seeded house campaigns that had end_at = now+365d.
            if existing.get("end_at") is not None:
                await db.game_campaigns.update_one(
                    {"campaign_id": h["id"]},
                    {"$set": {"end_at": None, "updated_at": _now()}},
                )
            continue
        tpl = await db.game_templates.find_one({"template_id": h["template_id"]})
        cfg = dict(tpl.get("default_config_json") or {})
        if h.get("config_overrides"):
            cfg.update(h["config_overrides"])
        await db.game_campaigns.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "advertiser_id": None, "business_id": None,
            "template_id": h["template_id"], "title": h["title"],
            "description": h["description"],
            "sponsor_name": "RadioLife", "sponsor_logo_url": "/static/bigfm_logo.png",
            "brand_colors_json": {"primary": "#ff2d95", "secondary": "#0a0a0b"},
            "game_config_json": cfg,
            "objective": "listener_engagement",
            "budget_cents": None,
            "bid_type": "platform_funded", "bid_amount_cents": 0,
            "start_at": _now() - timedelta(days=1),
            # Phase 8a.1 — house campaigns are IMMORTAL (no expiry).
            "end_at": None,
            "targeting_json": {"open_to_all": True},
            "status": "active",
            "is_platform_funded": True, "funded_source": "phase5_migration",
            "created_by_user_id": actor_user_id,
            "created_at": _now(), "updated_at": _now(),
            "approved_by_user_id": "system",
            "approved_at": _now(),
            "open_to_all": True,        # listener gating: any user can play
            "rejection_reason": None,
        })
        # prizes
        for p in h["prizes"]:
            pid = _new_id("prz")
            await db.game_prizes.insert_one({
                "_id": pid, "prize_id": pid,
                "campaign_id": h["id"],
                "prize_type": p["prize_type"],
                "title": p["title"],
                "description": p.get("description"),
                "value_amount": p["value_amount"],
                "value_currency": p.get("value_currency"),
                "probability_weight": int(p["probability_weight"]),
                "inventory_total": int(p["inventory_total"]),
                "inventory_remaining": int(p["inventory_total"]),
                "max_per_user": int(p.get("max_per_user") or 0),
                "redemption_method": p["redemption_method"],
                "requires_location": False,
                "requires_staff_validation": False,
                "expiration_policy_json": {"days_after_award": 30, "hard_expiry_at": None},
                "linked_offer_id": None, "linked_badge_id": None,
                "active": True, "created_at": _now(),
            })
        # redemption rules
        await db.game_redemption_rules.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "one_time_use": True, "requires_qr": False,
            "requires_location": False, "requires_staff_validation": False,
            "expiration_days": 30,
            "terms_url": None,
            "odds_disclosure_text":
                "Odds vary by prize tier. No purchase necessary.",
            "no_purchase_necessary_text":
                "No purchase necessary; void where prohibited.",
            "age_restriction": None,
            "geo_restrictions_json": {"allowed_countries": ["*"]},
            "created_at": _now(), "updated_at": _now(),
        })
        await db.game_compliance_settings.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "terms_text": "Standard RadioLife platform terms.",
            "odds_disclosure": "Odds vary by prize tier.",
            "no_purchase_necessary_text":
                "No purchase necessary; void where prohibited.",
            "age_restriction": None,
            "geo_restrictions_json": {"allowed_countries": ["*"]},
            "approval_status": "approved", "approved_by": "system",
            "approved_at": _now(), "rejection_notes": None,
        })
        summary["house_campaigns_created"] += 1

    # --- 5) Backfill user unlocks ----------------------------------------
    # All 3 house campaigns are open_to_all in 8a, so no unlocks needed
    # for migration.  This stub is here so 8b/8c retain the same semantics.
    return summary


# =====================================================================
# Extra always-on platform ("house") games — playable by every listener.
# Reuses existing templates + generic player.  Idempotent on boot.
# =====================================================================
EXTRA_HOUSE_GAMES = [
    {"id": "cmp_house_scratch", "template_id": "tpl_scratch_card",
     "title": "RadioLife Scratch & Win",
     "description": "Scratch the foil to reveal instant BigCoin. Play daily!",
     "prizes": [
         {"title": "5 BigCoin", "prize_type": "bigcoin", "value_amount": 5,
          "probability_weight": 45, "inventory_total": 100000, "redemption_method": "in_app_wallet"},
         {"title": "25 BigCoin", "prize_type": "bigcoin", "value_amount": 25,
          "probability_weight": 30, "inventory_total": 40000, "redemption_method": "in_app_wallet"},
         {"title": "75 BigCoin", "prize_type": "bigcoin", "value_amount": 75,
          "probability_weight": 18, "inventory_total": 15000, "redemption_method": "in_app_wallet"},
         {"title": "150 BigCoin", "prize_type": "bigcoin", "value_amount": 150,
          "probability_weight": 7, "inventory_total": 6000, "redemption_method": "in_app_wallet"},
     ]},
    {"id": "cmp_house_mystery", "template_id": "tpl_mystery_box",
     "title": "RadioLife Mystery Box",
     "description": "Pick a box and reveal a surprise BigCoin prize.",
     "prizes": [
         {"title": "10 BigCoin", "prize_type": "bigcoin", "value_amount": 10,
          "probability_weight": 50, "inventory_total": 80000, "redemption_method": "in_app_wallet"},
         {"title": "40 BigCoin", "prize_type": "bigcoin", "value_amount": 40,
          "probability_weight": 30, "inventory_total": 30000, "redemption_method": "in_app_wallet"},
         {"title": "120 BigCoin", "prize_type": "bigcoin", "value_amount": 120,
          "probability_weight": 20, "inventory_total": 10000, "redemption_method": "in_app_wallet"},
     ]},
    {"id": "cmp_house_memory", "template_id": "tpl_memory_match",
     "title": "RadioLife Memory Match",
     "description": "Match all the pairs before time runs out to win BigCoin.",
     "prizes": [
         {"title": "30 BigCoin", "prize_type": "bigcoin", "value_amount": 30,
          "probability_weight": 100, "inventory_total": 999999, "max_per_user": 0,
          "redemption_method": "in_app_wallet"},
     ]},
    {"id": "cmp_house_word", "template_id": "tpl_word_puzzle",
     "title": "RadioLife Word Puzzle",
     "description": "Guess the phrase before your strikes run out. Win BigCoin!",
     "prizes": [
         {"title": "25 BigCoin", "prize_type": "bigcoin", "value_amount": 25,
          "probability_weight": 100, "inventory_total": 999999, "max_per_user": 0,
          "redemption_method": "in_app_wallet"},
     ]},
]


async def seed_extra_house_games(db, actor_user_id: str = "system") -> dict:
    """Idempotent — seed 4 additional always-on platform games so every
    listener has more to play in production.  Safe to call on every boot."""
    summary = {"created": 0, "existing": 0}
    for h in EXTRA_HOUSE_GAMES:
        existing = await db.game_campaigns.find_one({"campaign_id": h["id"]})
        if existing:
            summary["existing"] += 1
            if existing.get("end_at") is not None:
                await db.game_campaigns.update_one(
                    {"campaign_id": h["id"]}, {"$set": {"end_at": None, "updated_at": _now()}})
            continue
        tpl = await db.game_templates.find_one({"template_id": h["template_id"]})
        if not tpl:
            continue
        cfg = dict(tpl.get("default_config_json") or {})
        await db.game_campaigns.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "advertiser_id": None, "business_id": None,
            "template_id": h["template_id"], "title": h["title"],
            "description": h["description"],
            "sponsor_name": "RadioLife", "sponsor_logo_url": "/static/bigfm_logo.png",
            "brand_colors_json": {"primary": "#F26B2A", "secondary": "#FBF5EC"},
            "game_config_json": cfg,
            "objective": "listener_engagement",
            "budget_cents": None,
            "bid_type": "platform_funded", "bid_amount_cents": 0,
            "start_at": _now() - timedelta(days=1), "end_at": None,
            "targeting_json": {"open_to_all": True},
            "status": "active",
            "is_platform_funded": True, "funded_source": "extra_house_games",
            "created_by_user_id": actor_user_id,
            "created_at": _now(), "updated_at": _now(),
            "approved_by_user_id": "system", "approved_at": _now(),
            "open_to_all": True, "rejection_reason": None,
        })
        for p in h["prizes"]:
            pid = _new_id("prz")
            await db.game_prizes.insert_one({
                "_id": pid, "prize_id": pid, "campaign_id": h["id"],
                "prize_type": p["prize_type"], "title": p["title"],
                "description": p.get("description"),
                "value_amount": p["value_amount"], "value_currency": p.get("value_currency"),
                "probability_weight": int(p["probability_weight"]),
                "inventory_total": int(p["inventory_total"]),
                "inventory_remaining": int(p["inventory_total"]),
                "max_per_user": int(p.get("max_per_user") or 0),
                "redemption_method": p["redemption_method"],
                "requires_location": False, "requires_staff_validation": False,
                "expiration_policy_json": {"days_after_award": 30, "hard_expiry_at": None},
                "linked_offer_id": None, "linked_badge_id": None,
                "active": True, "created_at": _now(),
            })
        await db.game_redemption_rules.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "one_time_use": True, "requires_qr": False,
            "requires_location": False, "requires_staff_validation": False,
            "expiration_days": 30, "terms_url": None,
            "odds_disclosure_text": "Odds vary by prize tier. No purchase necessary.",
            "no_purchase_necessary_text": "No purchase necessary; void where prohibited.",
            "age_restriction": None, "geo_restrictions_json": {"allowed_countries": ["*"]},
            "created_at": _now(), "updated_at": _now(),
        })
        await db.game_compliance_settings.insert_one({
            "_id": h["id"], "campaign_id": h["id"],
            "terms_text": "Standard RadioLife platform terms.",
            "odds_disclosure": "Odds vary by prize tier.",
            "no_purchase_necessary_text": "No purchase necessary; void where prohibited.",
            "age_restriction": None, "geo_restrictions_json": {"allowed_countries": ["*"]},
            "approval_status": "approved", "approved_by": "system",
            "approved_at": _now(), "rejection_notes": None,
        })
        summary["created"] += 1
    return summary


# =====================================================================
# Award engine
# =====================================================================
def _weighted_pick(weights: list[int], rng) -> int:
    total = sum(weights)
    if total <= 0:
        return -1
    threshold = rng.uniform(0, total)
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if threshold < acc:
            return i
    return len(weights) - 1


async def _atomic_claim_prize(db, prize: dict, session_id: str) -> bool:
    """Decrement inventory_remaining by 1 iff still > 0.  Returns True iff
    we held the lock — caller is responsible for awarding."""
    res = await db.game_prizes.update_one(
        {"prize_id": prize["prize_id"], "inventory_remaining": {"$gt": 0}},
        {"$inc": {"inventory_remaining": -1}},
    )
    if res.modified_count == 1:
        await db.game_inventory_ledger.insert_one({
            "_id": _new_id("led"), "campaign_id": prize["campaign_id"],
            "prize_id": prize["prize_id"], "delta": -1,
            "session_id": session_id, "reason": "award",
            "inventory_after": max(0, int(prize["inventory_remaining"]) - 1),
            "ts": _now(),
        })
        return True
    return False


async def _generate_dynamic_quiz_question(db, source: str, user_id: str) -> dict:
    """Replicates Phase 5 dynamic question generation for migrated quiz
    campaigns (dynamic_pool=True).  Stored on the session, validated on submit."""
    import random
    if source == "tracks":
        track = None
        async for t in db.tracks.aggregate([{"$sample": {"size": 1}}]):
            track = t
            break
        if not track:
            raise ValueError("no tracks available for trivia")
        qtype = random.choice(["artist", "era", "language"])
        correct = track.get(qtype) or track.get("artist") or "Unknown"
        distractors = []
        async for t2 in db.tracks.aggregate([
                {"$match": {qtype: {"$ne": correct}}},
                {"$sample": {"size": 8}}]):
            v = t2.get(qtype)
            if v and v not in distractors:
                distractors.append(v)
            if len(distractors) >= 3:
                break
        while len(distractors) < 3:
            distractors.append(f"{correct}-alt-{len(distractors)}")
        options = distractors + [correct]
        random.shuffle(options)
        return {
            "prompt": {"artist": "Who is the artist of this song?",
                          "era": "Which decade is this song from?",
                          "language": "What language is this song in?"}[qtype],
            "options": options,
            "correct_idx": options.index(correct),
            "track": {"title": track.get("title"),
                         "artist": track.get("artist")},
        }
    if source == "lyric_puzzles":
        puzzle = None
        async for p in db.lyric_puzzles.aggregate([
                {"$match": {"active": True}},
                {"$sample": {"size": 1}}]):
            puzzle = p
            break
        if not puzzle:
            raise ValueError("no lyric puzzles available")
        distractors = []
        async for d in db.lyric_puzzles.aggregate([
                {"$match": {"_id": {"$ne": puzzle["_id"]},
                                "language": puzzle.get("language")}},
                {"$sample": {"size": 3}}]):
            distractors.append(d["next_phrase"])
        while len(distractors) < 3:
            distractors.append(f"… [decoy {len(distractors)}]")
        options = distractors + [puzzle["next_phrase"]]
        random.shuffle(options)
        return {
            "prompt": f"Complete this lyric: \"{puzzle['first_half']}\"",
            "options": options,
            "correct_idx": options.index(puzzle["next_phrase"]),
            "song": puzzle.get("song"),
            "artist": puzzle.get("artist"),
            "language": puzzle.get("language"),
        }
    raise ValueError(f"unknown dynamic source: {source}")


async def start_session(db, user: dict, campaign_id: str,
                            source_context: Optional[dict] = None,
                            client_seed: Optional[str] = None) -> dict:
    """Create a game_session row + return render config for the client."""
    if user.get("driving_mode_on"):
        raise ValueError("driving_mode_active")
    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        raise ValueError("campaign_not_found")
    if campaign.get("status") != "active":
        raise ValueError(f"campaign_not_active:{campaign.get('status')}")
    now = _now()
    sa = campaign.get("start_at")
    ea = campaign.get("end_at")
    if sa and (sa.tzinfo is None and sa.replace(tzinfo=timezone.utc) > now or
                  sa.tzinfo is not None and sa > now):
        raise ValueError("campaign_not_started")
    if ea and (ea.tzinfo is None and ea.replace(tzinfo=timezone.utc) < now or
                  ea.tzinfo is not None and ea < now):
        raise ValueError("campaign_ended")

    # Eligibility — open_to_all OR a valid unlock
    if not campaign.get("open_to_all"):
        unlock = await db.user_game_unlocks.find_one({
            "user_id": user["user_id"], "campaign_id": campaign_id,
            "played": False,
            "$or": [{"expires_at": None},
                       {"expires_at": {"$gt": now}}],
        })
        if not unlock:
            raise ValueError("not_unlocked")
    # max_per_user (overall completed sessions)
    template = await db.game_templates.find_one({"template_id": campaign["template_id"]})
    if template and template.get("game_type") in ALL_GAME_TYPES:
        prizes = await db.game_prizes.find(
            {"campaign_id": campaign_id, "active": True}).to_list(50)
        max_per_user = max((int(p.get("max_per_user") or 0) for p in prizes), default=0)
        if max_per_user > 0:
            played = await db.game_sessions.count_documents({
                "user_id": user["user_id"], "campaign_id": campaign_id,
                "status": {"$in": ["completed", "claimed"]},
            })
            if played >= max_per_user:
                raise ValueError("max_per_user_reached")
    # Phase 8a.1 — TRUE sliding-window rate limit: at most 30 starts per
    # (user, campaign) within any rolling 60-minute interval.  The earlier
    # implementation was a fixed window keyed off the doc's TTL, which
    # made stale buckets fire false positives when prior runs left state.
    bucket_key = f"{user['user_id']}|{campaign_id}|start"
    one_hour_ago = now - timedelta(hours=1)
    bucket = await db.game_rate_limits.find_one({"_id": bucket_key})
    recent = []
    if bucket:
        for t in (bucket.get("timestamps") or []):
            if isinstance(t, datetime) and (t.tzinfo and t > one_hour_ago
                                                  or not t.tzinfo
                                                  and t.replace(tzinfo=timezone.utc) > one_hour_ago):
                recent.append(t)
    if len(recent) >= 30:
        raise ValueError("rate_limited")
    recent.append(now)
    await db.game_rate_limits.replace_one(
        {"_id": bucket_key},
        {"_id": bucket_key, "timestamps": recent,
         "ttl_at": now + timedelta(hours=1, minutes=5)},
        upsert=True,
    )

    session_id = _new_id("gs", 16)
    server_seed = secrets.token_hex(16)
    if not client_seed:
        client_seed = secrets.token_hex(8)

    render_config: dict = {}
    template_id = campaign["template_id"]
    cfg = dict(campaign.get("game_config_json") or {})
    extra_session: dict = {}
    game_type = (template or {}).get("game_type")
    if game_type == "quiz":
        if cfg.get("dynamic_pool"):
            # Phase Stabilization (Mobile games P0) — coerce empty-pool
            # errors from the dynamic generator into the unified
            # `no_questions_available` ValueError so the route turns it
            # into a 503 with the friendly listener-facing message.
            try:
                q = await _generate_dynamic_quiz_question(
                    db, cfg.get("dynamic_source", "tracks"), user["user_id"])
            except ValueError as ve:
                msg = str(ve)
                if msg.startswith("no ") or "available" in msg:
                    logger.warning(
                        "[games_v2] dynamic trivia campaign %s — "
                        "empty source pool: %s",
                        campaign_id, msg)
                    raise ValueError("no_questions_available")
                raise
            extra_session["dynamic_question"] = q
            # Phase 8a.1 — NEVER include `correct_idx` in the listener payload.
            render_config = {
                "type": "quiz",
                "time_per_question_s": cfg.get("time_per_question_s", 15),
                "min_correct_to_win": cfg.get("min_correct_to_win", 1),
                "questions": [{
                    "prompt": q["prompt"], "options": q["options"],
                    "track": q.get("track"),
                    "song": q.get("song"), "artist": q.get("artist"),
                    "language": q.get("language"),
                }],
            }
        else:
            qlist = cfg.get("questions") or []
            # Phase Stabilization (Mobile games P0) — never create a
            # broken trivia session with zero playable questions. The
            # listener UI shows "Q1 / 0" which is a dead-end. Surface a
            # typed 503 so the client can render a friendly "trivia
            # being prepared" empty state instead.
            if not qlist:
                logger.warning(
                    "[games_v2] trivia campaign %s has 0 questions — "
                    "refusing to create a broken session",
                    campaign_id)
                raise ValueError("no_questions_available")
            # Phase 8a.1 — strip `correct_idx` from each question; server
            # holds the truth in `extra_session["correct_indices"]`.
            render_config = {
                "type": "quiz",
                "time_per_question_s": cfg.get("time_per_question_s", 15),
                "min_correct_to_win": cfg.get("min_correct_to_win", 1),
                "questions": [{"prompt": q.get("prompt"),
                                  "options": q.get("options")}
                                for q in qlist],
            }
            extra_session["correct_indices"] = [int(q.get("correct_idx", 0))
                                                       for q in qlist]
    elif game_type == "spin_wheel":
        # Phase 8a.1 — strip `probability_weight` + `prize_id` from each
        # segment.  The wheel is purely visual; the server picks the prize.
        safe_segments = [{"label": s.get("label"),
                                "color": s.get("color"),
                                "idx": i}
                              for i, s in enumerate(cfg.get("segments") or [])]
        render_config = {
            "type": "spin_wheel",
            "segments": safe_segments,
            "spin_duration_ms": cfg.get("spin_duration_ms", 4000),
        }
    elif game_type == "scratch_card":
        # Phase 8a.1 — `reveal_image_url` is a generic foil background
        # (NOT the actual prize art).  We still surface it so the canvas
        # has something to reveal; the actual prize title/value only
        # arrives on the `submit` response.
        render_config = {
            "type": "scratch_card",
            "cover_image_url": cfg.get("cover_image_url"),
            "reveal_image_url": cfg.get("reveal_image_url"),
            "scratch_threshold": cfg.get("scratch_threshold", 0.5),
        }
    elif game_type == "mystery_box":
        # Phase 8a.1 — strip `prize_id` from each box; boxes are
        # interchangeable visually and the server picks the prize.
        safe_boxes = [{"label": b.get("label"),
                            "image_url": b.get("image_url"),
                            "idx": i}
                          for i, b in enumerate(cfg.get("boxes") or [])]
        render_config = {
            "type": "mystery_box",
            "boxes": safe_boxes,
            "num_boxes": cfg.get("num_boxes", 3),
            "reveal_animation_ms": cfg.get("reveal_animation_ms", 1200),
        }
    elif game_type == "slot_machine":
        # Phase 8b — server pre-decides reel positions using server_seed.
        # The client animates and lands on the same positions; only winning
        # via the inventory-aware lottery (set in submit_session) actually
        # awards a prize.
        rng_seed = int(server_seed[:8], 16)
        slot_rng = __import__("random").Random(rng_seed)
        reels = cfg.get("reels") or []
        positions = []
        for r in reels:
            total_w = sum(int(s.get("weight") or 1) for s in r)
            roll = slot_rng.uniform(0, max(total_w, 1))
            acc = 0
            picked = 0
            for i, s in enumerate(r):
                acc += int(s.get("weight") or 1)
                if roll < acc:
                    picked = i
                    break
            positions.append(picked)
        # Strip weights from the public payload (compliance leak protection)
        safe_reels = [[{"label": s.get("label"), "image_url": s.get("image_url")}
                            for s in r] for r in reels]
        extra_session["slot_positions"] = positions
        render_config = {
            "type": "slot_machine",
            "reels": safe_reels,
            "positions": positions,
            "spin_duration_ms": cfg.get("spin_duration_ms", 3200),
        }
    elif game_type == "memory_match":
        # Phase 8b — server shuffles the deck using server_seed; client
        # plays it back.  We DON'T tell the client the position of each
        # pair until submit (we just send the indices in a shuffled order).
        rng_seed = int(server_seed[:8], 16)
        mm_rng = __import__("random").Random(rng_seed)
        pairs = cfg.get("pairs") or []
        grid_size = int(cfg.get("grid_size") or 4)
        n_pairs = (grid_size * grid_size) // 2
        chosen = pairs[:n_pairs]
        # Build a deck of (pair_idx, card_idx) tuples and shuffle
        deck = []
        for i, p in enumerate(chosen):
            deck.append({"pair_idx": i, "label": p.get("label"),
                            "image_url": p.get("image_url")})
            deck.append({"pair_idx": i, "label": p.get("label"),
                            "image_url": p.get("image_url")})
        mm_rng.shuffle(deck)
        extra_session["memory_deck"] = deck
        render_config = {
            "type": "memory_match",
            "grid_size": grid_size,
            "deck": deck,
            "time_limit_sec": cfg.get("time_limit_sec", 90),
            "min_correct_pairs_to_win": cfg.get("min_correct_pairs_to_win",
                                                          max(1, n_pairs // 2)),
        }
    elif game_type == "word_puzzle":
        # Phase 8b — server picks a phrase using server_seed; client gets
        # underscores + hint.  Guesses validated on submit (one body call
        # per guess if you want letter-by-letter; the test path sends the
        # final attempted_phrase).
        rng_seed = int(server_seed[:8], 16)
        wp_rng = __import__("random").Random(rng_seed)
        phrases = cfg.get("phrases") or []
        picked = wp_rng.choice(phrases) if phrases else {"phrase": "BIGFM", "hint": ""}
        phrase_str = (picked.get("phrase") or "").upper()
        masked = "".join(["_" if c.isalpha() else c for c in phrase_str])
        extra_session["target_phrase"] = phrase_str
        render_config = {
            "type": "word_puzzle",
            "masked": masked,
            "hint": picked.get("hint", ""),
            "max_strikes": int(cfg.get("max_strikes", 6)),
            "time_limit_sec": cfg.get("time_limit_sec", 120),
        }
    elif game_type == "pick_a_card":
        # Phase 23 Session 7c — N face-down cards.  Client passes back
        # `choice` (card index) at submit time; the eligibility check is
        # trivial (any pick wins), the actual prize comes from the
        # standard inventory-aware lottery in submit_session.  We pin
        # a `winning_card_idx` via server_seed so admin auditing can
        # reconstruct what the listener saw.
        num_cards = max(2, min(6,
            int(cfg.get("num_cards") or cfg.get("card_count") or 3)))
        rng_seed = int(server_seed[:8], 16)
        pc_rng = __import__("random").Random(rng_seed)
        extra_session["pick_a_card_num"]              = num_cards
        extra_session["pick_a_card_winning_idx"] = pc_rng.randrange(num_cards)
        render_config = {
            "type": "pick_a_card",
            "num_cards": num_cards,
            "flip_duration_ms": cfg.get("flip_duration_ms", 550),
        }
    else:
        raise ValueError(f"unsupported_game_type:{game_type}")

    await db.game_sessions.insert_one({
        "_id": session_id, "session_id": session_id,
        "user_id": user["user_id"], "campaign_id": campaign_id,
        "template_id": template_id,
        "source_context": source_context or {},
        "started_at": now, "completed_at": None,
        "result": None, "prize_id": None, "wallet_item_id": None,
        "client_seed": client_seed, "server_seed": server_seed,
        "status": "in_progress",
        "claimed_at": None, "redeemed_at": None,
        **extra_session,
    })

    # Analytics
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": campaign_id,
        "user_id": user["user_id"], "event_type": "start",
        "source_context_json": source_context or {},
        "metadata_json": {"session_id": session_id, "template_id": template_id},
        "ts": now,
    })
    return {
        "session_id": session_id,
        "campaign_id": campaign_id,
        "template_id": template_id,
        "client_seed": client_seed,
        "render_config": render_config,
    }


async def submit_session(db, user: dict, session_id: str,
                            payload: dict) -> dict:
    """Server resolves prize using inventory-aware weighted draw."""
    sess = await db.game_sessions.find_one({"session_id": session_id})
    if not sess or sess["user_id"] != user["user_id"]:
        raise ValueError("session_not_found")
    if sess["status"] != "in_progress":
        raise ValueError(f"session_already:{sess['status']}")
    campaign = await db.game_campaigns.find_one(
        {"campaign_id": sess["campaign_id"]})
    if not campaign:
        raise ValueError("campaign_missing")
    template = await db.game_templates.find_one(
        {"template_id": sess["template_id"]})
    game_type = (template or {}).get("game_type")
    now = _now()

    # Quiz: deterministic gate before lottery
    quiz_eligible = True
    quiz_meta: dict = {}
    if game_type == "quiz":
        cfg = campaign.get("game_config_json") or {}
        min_correct = int(cfg.get("min_correct_to_win", 1))
        if cfg.get("dynamic_pool"):
            q = sess.get("dynamic_question") or {}
            correct_idx = int(q.get("correct_idx", -1))
            answer_idx = int((payload or {}).get("answer_idx", -1))
            correct = answer_idx == correct_idx
            quiz_meta = {"correct_idx": correct_idx,
                          "chosen_idx": answer_idx, "correct": correct}
            quiz_eligible = bool(correct)
        else:
            correct_indices = sess.get("correct_indices") or []
            answers = (payload or {}).get("answers") or []
            score = sum(1 for i, a in enumerate(answers)
                            if i < len(correct_indices) and int(a) == correct_indices[i])
            quiz_meta = {"score": score,
                          "total": len(correct_indices),
                          "min_correct": min_correct}
            quiz_eligible = score >= min_correct
    elif game_type == "slot_machine":
        # Phase 8b — eligibility = the server-picked positions hit a win combo.
        # `slot_positions` was pinned at start.  Win combos use literal labels
        # OR the special `any-match-3` rule (all three labels equal).
        positions = sess.get("slot_positions") or []
        reels = (campaign.get("game_config_json") or {}).get("reels") or []
        symbols = []
        for r_idx, p_idx in enumerate(positions):
            r = reels[r_idx] if r_idx < len(reels) else []
            symbols.append(r[p_idx].get("label") if p_idx < len(r) else None)
        combos = (campaign.get("game_config_json") or {}).get("win_combos") or []
        is_win = False
        if symbols and len(set(symbols)) == 1:
            is_win = True
        else:
            for combo in combos:
                target = combo.get("symbols") or []
                if "any-match-3" in target and len(set(symbols)) == 1:
                    is_win = True; break
                if target == symbols:
                    is_win = True; break
        quiz_meta = {"symbols": symbols, "win_combo_hit": is_win}
        quiz_eligible = is_win
    elif game_type == "memory_match":
        # Phase 8b — client sends `pairs_found` + `time_spent_sec`.
        pairs_found = int((payload or {}).get("pairs_found") or 0)
        time_spent = float((payload or {}).get("time_spent_sec") or 0)
        cfg = campaign.get("game_config_json") or {}
        min_pairs = int(cfg.get("min_correct_pairs_to_win", 1))
        time_limit = int(cfg.get("time_limit_sec", 90))
        within_time = time_spent <= time_limit + 5  # small grace
        quiz_meta = {"pairs_found": pairs_found, "time_spent": time_spent,
                      "min_required": min_pairs, "within_time": within_time}
        quiz_eligible = pairs_found >= min_pairs and within_time
    elif game_type == "word_puzzle":
        # Phase 8b — client sends `attempted_phrase` + `strikes_used`.
        target = (sess.get("target_phrase") or "").upper().strip()
        attempt = ((payload or {}).get("attempted_phrase") or "").upper().strip()
        strikes = int((payload or {}).get("strikes_used") or 0)
        max_strikes = int((campaign.get("game_config_json") or {}).get("max_strikes", 6))
        solved = attempt == target
        quiz_meta = {"target": target, "attempted": attempt,
                      "strikes": strikes, "max_strikes": max_strikes,
                      "solved": solved}
        quiz_eligible = solved and strikes <= max_strikes

    # Award lottery if eligible
    result = "lose"
    prize_picked: Optional[dict] = None
    bigcoin_earned = 0
    if quiz_eligible:
        rng = secrets.SystemRandom()
        # Re-derive a hash from server_seed + client_seed for verifiable
        # fairness (we still use SystemRandom for the actual selection so
        # repeated rolls re-weight properly).
        prizes = await db.game_prizes.find(
            {"campaign_id": sess["campaign_id"], "active": True,
             "inventory_remaining": {"$gt": 0}}
        ).to_list(50)
        if prizes:
            # Up to 5 retries in case the picked prize gets sniped
            for _ in range(5):
                weights = [int(p["probability_weight"]) for p in prizes]
                idx = _weighted_pick(weights, rng)
                if idx < 0:
                    break
                claim = await _atomic_claim_prize(db, prizes[idx], session_id)
                if claim:
                    prize_picked = prizes[idx]
                    result = "win"
                    break
                # Refresh inventory snapshot
                prizes = await db.game_prizes.find(
                    {"campaign_id": sess["campaign_id"], "active": True,
                     "inventory_remaining": {"$gt": 0}}
                ).to_list(50)
                if not prizes:
                    break

    # BigCoin prizes auto-credit on submit (no manual claim required)
    if prize_picked and prize_picked["prize_type"] == "bigcoin":
        amt = int(prize_picked["value_amount"])
        await bigcoin_award(db, user["user_id"], amt, "game_win",
                                metadata={"campaign_id": sess["campaign_id"],
                                          "session_id": session_id,
                                          "prize_id": prize_picked["prize_id"]})
        bigcoin_earned = amt

    update = {
        "completed_at": now, "result": result,
        "prize_id": prize_picked["prize_id"] if prize_picked else None,
        "status": "completed",
        "quiz_meta": quiz_meta,
    }
    await db.game_sessions.update_one({"session_id": session_id},
                                          {"$set": update})

    # Analytics
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": sess["campaign_id"],
        "user_id": user["user_id"],
        "event_type": "win" if result == "win" else "lose",
        "source_context_json": sess.get("source_context") or {},
        "metadata_json": {"session_id": session_id,
                            "prize_id": (prize_picked or {}).get("prize_id"),
                            **quiz_meta},
        "ts": now,
    })

    # Mark unlock used (if any)
    await db.user_game_unlocks.update_many(
        {"user_id": user["user_id"], "campaign_id": sess["campaign_id"],
         "played": False},
        {"$set": {"played": True, "played_at": now}},
    )

    # Phase 23 Session 1.5 — record canonical winner row (idempotent).
    # The post-win callback hook.  Errors here are logged but do NOT
    # fail the play submission; backfill script can repair gaps.
    if result == "win" and prize_picked:
        try:
            from services.games_v2_winners_redemptions import record_winner
            await record_winner(db, session_id, source="submit_session_hook")
        except Exception as exc:  # noqa: BLE001
            logger.warning("phase23 record_winner hook failed "
                                "session=%s err=%s", session_id, exc)

    return {
        "session_id": session_id,
        "result": result,
        "prize": _public_prize_view(prize_picked) if prize_picked else None,
        "bigcoin_earned": bigcoin_earned,
        "quiz_meta": quiz_meta,
        "share_text": (f"I just won {prize_picked['title']} on RadioLife!"
                            if prize_picked else
                            "Better luck next time on RadioLife Play & Win!"),
        "server_seed": sess["server_seed"],
        "client_seed": sess["client_seed"],
    }


def _public_prize_view(p: dict) -> dict:
    return {
        "prize_id": p["prize_id"], "title": p["title"],
        "description": p.get("description"),
        "prize_type": p["prize_type"],
        "value_amount": p.get("value_amount"),
        "value_currency": p.get("value_currency"),
        "redemption_method": p["redemption_method"],
    }


async def claim_to_wallet(db, user: dict, session_id: str) -> dict:
    sess = await db.game_sessions.find_one({"session_id": session_id})
    if not sess or sess["user_id"] != user["user_id"]:
        raise ValueError("session_not_found")
    if sess["status"] == "claimed" and sess.get("wallet_item_id"):
        wi = await db.user_wallet_items.find_one({"_id": sess["wallet_item_id"]})
        return {"already_claimed": True, "wallet_item": _wallet_item_view(wi)}
    if sess["status"] != "completed" or sess["result"] != "win":
        raise ValueError("not_a_win")
    prize = await db.game_prizes.find_one({"prize_id": sess["prize_id"]})
    if not prize:
        raise ValueError("prize_missing")
    now = _now()
    # Bigcoin: already credited on submit, no wallet item needed
    if prize["prize_type"] == "bigcoin":
        await db.game_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "claimed", "claimed_at": now}})
        return {"already_claimed": False, "wallet_item": None,
                "bigcoin_credited": int(prize["value_amount"])}
    wallet_item_id = _new_id("wi", 14)
    rules = await db.game_redemption_rules.find_one(
        {"campaign_id": sess["campaign_id"]}) or {}
    expires_at = now + timedelta(days=int(rules.get("expiration_days", 30)))
    doc = {
        "_id": wallet_item_id, "user_id": user["user_id"],
        "item_type": prize["prize_type"], "source": "game_win",
        "campaign_id": sess["campaign_id"],
        "prize_id": prize["prize_id"], "session_id": session_id,
        "title": prize["title"], "description": prize.get("description"),
        "value_amount": prize.get("value_amount"),
        "value_currency": prize.get("value_currency"),
        "redemption_method": prize["redemption_method"],
        "status": "active",
        "expires_at": expires_at,
        "created_at": now,
        "qr_token": None, "qr_image_base64": None, "redeemed_at": None,
        # Phase 23 Session 6 — provenance + CouponTools fields.
        "redemption_source": "internal",
        "coupontools_coupon_id":  None,
        "coupontools_url":              None,
        "coupontools_qr_url":      None,
    }

    # Phase 23 Session 8 — CouponTools removed.  All wallet items
    # carry `redemption_source="internal"`; the schema fields
    # `coupontools_*` are left nullable for backwards compat with rows
    # written before the removal but are never populated.
    await db.user_wallet_items.insert_one(doc)
    await db.game_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "claimed", "claimed_at": now,
                   "wallet_item_id": wallet_item_id}})
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": sess["campaign_id"],
        "user_id": user["user_id"], "event_type": "save_to_wallet",
        "metadata_json": {"session_id": session_id,
                            "wallet_item_id": wallet_item_id}, "ts": now,
    })
    return {"already_claimed": False, "wallet_item": _wallet_item_view(doc)}


def _wallet_item_view(wi: Optional[dict]) -> Optional[dict]:
    if not wi:
        return None
    out = {k: v for k, v in wi.items() if k != "_id"}
    out["wallet_item_id"] = wi.get("_id")
    for tk in ("expires_at", "created_at", "redeemed_at"):
        if isinstance(out.get(tk), datetime):
            out[tk] = out[tk].isoformat()
    return out


def _make_qr_png_b64(payload: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def generate_qr(db, user: dict, wallet_item_id: str,
                          public_base_url: str) -> dict:
    wi = await db.user_wallet_items.find_one({"_id": wallet_item_id})
    if not wi or wi.get("user_id") != user["user_id"]:
        raise ValueError("wallet_item_not_found")
    if wi.get("redeemed_at"):
        raise ValueError("already_redeemed")
    if wi.get("redemption_method") not in ("qr_code", "partner_pos"):
        raise ValueError("not_qr_redeemable")
    if wi.get("qr_token"):
        # idempotent: return existing
        return {"qr_token": wi["qr_token"],
                "qr_image_base64": wi.get("qr_image_base64"),
                "redeem_url": f"{public_base_url}/api/games_v2/redeem/{wi['qr_token']}"}
    token = "gqr_" + secrets.token_urlsafe(18)
    redeem_url = f"{public_base_url}/api/games_v2/redeem/{token}"
    b64 = _make_qr_png_b64(redeem_url)
    await db.user_wallet_items.update_one(
        {"_id": wallet_item_id},
        {"$set": {"qr_token": token, "qr_image_base64": b64,
                   "qr_generated_at": _now()}},
    )
    return {"qr_token": token, "qr_image_base64": b64, "redeem_url": redeem_url}


async def redeem_qr(db, qr_token: str, redeemer_actor: str = "partner") -> dict:
    """Atomic single-use redemption.  Raises a distinct error when the QR
    is unknown vs already redeemed so the audit layer can attribute
    replay vs not_found correctly."""
    res = await db.user_wallet_items.find_one_and_update(
        {"qr_token": qr_token, "redeemed_at": None},
        {"$set": {"redeemed_at": _now(),
                   "redeemed_by_actor": redeemer_actor,
                   "status": "redeemed"}},
        return_document=True,
    )
    # Motor returns the OLD doc by default; we re-fetch to get the updated values
    if not res:
        # Distinguish "never existed" from "already redeemed" for the audit
        existing = await db.user_wallet_items.find_one(
            {"qr_token": qr_token}, {"_id": 1, "campaign_id": 1})
        if existing:
            raise ValueError("already_redeemed")
        raise ValueError("qr_not_found")
    fresh = await db.user_wallet_items.find_one({"qr_token": qr_token})
    sess_id = (fresh or {}).get("session_id")
    if sess_id:
        await db.game_sessions.update_one(
            {"session_id": sess_id},
            {"$set": {"redeemed_at": _now(), "status": "claimed"}})
    if fresh:
        await db.game_analytics_events.insert_one({
            "_id": _new_id("evt"), "campaign_id": fresh.get("campaign_id"),
            "user_id": fresh.get("user_id"), "event_type": "redeem",
            "metadata_json": {"qr_token": qr_token,
                                "wallet_item_id": fresh.get("_id")},
            "ts": _now(),
        })
    return {"ok": True, "wallet_item": _wallet_item_view(fresh)}


# =====================================================================
# Advertiser builder helpers
# =====================================================================
def validate_prizes(prizes: list[dict], template: dict) -> None:
    if not prizes:
        raise ValueError("at_least_one_prize_required")
    if len(prizes) < int(template.get("min_prizes") or 1):
        raise ValueError(f"need_min_{template['min_prizes']}_prizes")
    if len(prizes) > int(template.get("max_prizes") or 12):
        raise ValueError(f"max_{template['max_prizes']}_prizes")
    weights = [int(p.get("probability_weight") or 0) for p in prizes]
    if sum(weights) != 100:
        raise ValueError(f"weights_must_sum_to_100_got_{sum(weights)}")
    for p in prizes:
        if int(p.get("inventory_total") or 0) <= 0:
            raise ValueError("inventory_must_be_positive")
        if p.get("prize_type") not in PRIZE_TYPES:
            raise ValueError(f"invalid_prize_type:{p.get('prize_type')}")
        if p.get("redemption_method") not in REDEMPTION_METHODS:
            raise ValueError(f"invalid_redemption_method:{p.get('redemption_method')}")


def validate_compliance(c: dict) -> None:
    for f in ("terms_text", "odds_disclosure",
                  "no_purchase_necessary_text"):
        if not c.get(f):
            raise ValueError(f"compliance.{f}_required")


async def public_play_and_win(db, user: dict) -> dict:
    """Lists sections for the /play-and-win page."""
    uid = user["user_id"]
    now = _now()
    # Unlocked: campaigns open-to-all OR with a valid unlock doc
    unlocks = await db.user_game_unlocks.find(
        {"user_id": uid, "played": False,
         "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]}
    ).to_list(50)
    unlock_campaign_ids = {u["campaign_id"] for u in unlocks}
    open_campaigns = await db.game_campaigns.find({
        "status": "active",
        "open_to_all": True,
        "$and": [
            {"$or": [{"start_at": None}, {"start_at": {"$lte": now}}]},
            {"$or": [{"end_at": None}, {"end_at": {"$gt": now}}]},
        ],
    }).sort([("is_platform_funded", -1), ("created_at", -1)]).to_list(100)
    unlocked_for_you = []
    expiring_soon = []
    seen: set = set()
    for c in open_campaigns:
        if c["campaign_id"] in seen: continue
        seen.add(c["campaign_id"])
        view = await _campaign_public_view(db, c)
        unlocked_for_you.append(view)
        if c.get("end_at") and (
            (c["end_at"].tzinfo and c["end_at"] - now < timedelta(hours=24))
            or (not c["end_at"].tzinfo
                  and c["end_at"].replace(tzinfo=timezone.utc) - now < timedelta(hours=24))
        ):
            expiring_soon.append(view)
    # Unlock-required ones
    if unlock_campaign_ids:
        un_camps = await db.game_campaigns.find({
            "campaign_id": {"$in": list(unlock_campaign_ids)},
            "status": "active",
        }).to_list(50)
        for c in un_camps:
            if c["campaign_id"] in seen: continue
            seen.add(c["campaign_id"])
            unlocked_for_you.append(await _campaign_public_view(db, c))
    # Played history
    played_cur = db.game_sessions.find(
        {"user_id": uid,
          "status": {"$in": ["completed", "claimed"]}}
    ).sort("started_at", -1).limit(20)
    played_history = []
    async for s in played_cur:
        # Hotfix — `started_at` is occasionally stored as a string
        # (legacy rows from before the schema was normalized).  Coerce
        # to a defensive ISO formatter and wrap the whole row in
        # try/except so one malformed session can't 500 the page.
        try:
            sa = s.get("started_at")
            if hasattr(sa, "isoformat"):
                started_iso = sa.isoformat()
            elif isinstance(sa, str):
                started_iso = sa
            else:
                started_iso = None
            played_history.append({
                "session_id": s["session_id"],
                "campaign_id": s["campaign_id"],
                "result": s.get("result"),
                "prize_id": s.get("prize_id"),
                "started_at": started_iso,
                "status": s.get("status"),
                "wallet_item_id": s.get("wallet_item_id"),
            })
        except Exception as e:
            logger.warning(
                "[play_and_win] skipping malformed session "
                "session_id=%s err=%s",
                (s or {}).get("session_id"), e)
            continue
    return {
        "unlocked_for_you": unlocked_for_you,
        "sponsored_near_you": [],     # Phase 9 — empty for 8a
        "expiring_soon": expiring_soon,
        "played_history": played_history,
        "driving_mode_on": bool(user.get("driving_mode_on")),
    }


async def save_for_later_unlock(db, user: dict, campaign_id: str,
                                       hours: int = 72) -> dict:
    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        raise ValueError("campaign_not_found")
    if campaign.get("status") != "active":
        raise ValueError(f"campaign_not_active:{campaign.get('status')}")
    now = _now()
    expires = now + timedelta(hours=hours)
    existing = await db.user_game_unlocks.find_one({
        "user_id": user["user_id"], "campaign_id": campaign_id,
        "played": False,
    })
    if existing:
        await db.user_game_unlocks.update_one(
            {"_id": existing["_id"]},
            {"$set": {"expires_at": expires,
                       "saved_for_later": True,
                       "saved_at": now}})
        return {"unlock_id": existing["_id"],
                "saved_for_later": True,
                "expires_at": expires.isoformat(),
                "extended": True}
    unlock_id = _new_id("ulk")
    await db.user_game_unlocks.insert_one({
        "_id": unlock_id, "unlock_id": unlock_id,
        "user_id": user["user_id"], "campaign_id": campaign_id,
        "unlock_reason": "save_for_later",
        "saved_for_later": True, "saved_at": now,
        "unlocked_at": now, "expires_at": expires,
        "played": False, "played_at": None,
    })
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": campaign_id,
        "user_id": user["user_id"], "event_type": "save_for_later",
        "metadata_json": {"unlock_id": unlock_id, "hours": hours}, "ts": now,
    })
    return {"unlock_id": unlock_id,
            "saved_for_later": True,
            "expires_at": expires.isoformat(),
            "extended": False}


async def _campaign_public_view(db, c: dict) -> dict:
    prizes = await db.game_prizes.find(
        {"campaign_id": c["campaign_id"], "active": True}
    ).to_list(20)
    # Don't leak probability_weight in the public payload
    top_prize_title = None
    if prizes:
        top = max(prizes, key=lambda p: int(p.get("value_amount") or 0))
        top_prize_title = top.get("title")
    return {
        "campaign_id": c["campaign_id"],
        "template_id": c["template_id"],
        "title": c["title"],
        "description": c.get("description"),
        "sponsor_name": c.get("sponsor_name") or "RadioLife",
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "brand_colors_json": c.get("brand_colors_json") or {},
        "top_prize_title": top_prize_title,
        "prize_count": len(prizes),
        "is_platform_funded": bool(c.get("is_platform_funded")),
        "open_to_all": bool(c.get("open_to_all")),
        "end_at": c["end_at"].isoformat() if c.get("end_at") else None,
    }


__all__ = [
    "ensure_games_v2_indexes", "seed_games_v2",
    "migrate_phase5_games", "seed_extra_house_games", "start_session", "submit_session",
    "claim_to_wallet", "generate_qr", "redeem_qr",
    "public_play_and_win", "validate_prizes", "validate_compliance",
    "save_for_later_unlock",
    # Phase 8b
    "generate_public_slug", "ensure_public_slug",
    "pick_game_announce_candidate", "log_rj_game_mention",
    "issue_partner_token", "revoke_partner_token", "validate_partner_token",
    "check_partner_token_status",
    "save_uploaded_asset", "ASSET_MIME_WHITELIST", "ASSET_MAX_BYTES",
    "ASSET_MAX_DIM",
    "ACTIVE_GAME_TYPES", "INACTIVE_GAME_TYPES", "PRIZE_TYPES",
    "OBJECTIVES", "BID_TYPES", "CAMPAIGN_STATUSES", "REDEMPTION_METHODS",
    "UNLOCK_REASONS",
    "HOUSE_SPIN_ID", "HOUSE_TRIVIA_ID", "HOUSE_LYRIC_ID",
]


# ====================================================================
# Phase 8b — public slug + game-announce candidate + partner tokens
# + asset upload
# ====================================================================
import bcrypt as _bcrypt  # noqa: E402  — kept inline to minimize churn
import re as _re          # noqa: E402
from pathlib import Path as _Path  # noqa: E402

ASSETS_DIR = _Path(__file__).resolve().parent.parent / "storage" / "game_assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
ASSET_MIME_WHITELIST = {"image/png", "image/jpeg", "image/webp"}
ASSET_MAX_BYTES = 2 * 1024 * 1024            # 2 MB
ASSET_MAX_DIM = 2048                            # 2048 × 2048


def _slugify(s: str) -> str:
    s = _re.sub(r"[^a-zA-Z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:32] or "campaign"


async def generate_public_slug(db, campaign_id: str, title: str) -> str:
    """Stable URL-safe slug.  Format: `<title-slug>-<6-hex>`.
    Tries up to 5 random suffixes before falling back to the bare campaign_id."""
    base = _slugify(title)
    for _ in range(5):
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"
        clash = await db.game_campaigns.find_one(
            {"public_slug": candidate}, {"_id": 1})
        if not clash:
            return candidate
    return campaign_id


async def ensure_public_slug(db, campaign_id: str) -> Optional[str]:
    """Generate-once + persist on the campaign + create the landing-page doc.
    Called on first `approve`.  Idempotent."""
    c = await db.game_campaigns.find_one(
        {"campaign_id": campaign_id},
        {"public_slug": 1, "title": 1, "_id": 0})
    if not c:
        return None
    if c.get("public_slug"):
        return c["public_slug"]
    slug = await generate_public_slug(db, campaign_id, c.get("title") or "")
    await db.game_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"public_slug": slug, "updated_at": _now()}},
    )
    await db.game_landing_pages.update_one(
        {"slug": slug},
        {"$setOnInsert": {
            "_id": slug, "slug": slug,
            "campaign_id": campaign_id,
            "qr_code_url": f"/play/{slug}/qr.png",
            "sms_shortlink": f"bigfm.link/{slug}",     # scaffold
            "landing_page_config_json": {},
            "active": True, "created_at": _now(),
        }},
        upsert=True,
    )
    return slug


# ---------------------------------------------------------------------
# RJ game-announce candidate selector (Phase 8b)
# ---------------------------------------------------------------------
RJ_MENTION_COOLDOWN_SEC = 30 * 60


async def pick_game_announce_candidate(db, user: dict,
                                              now: Optional[datetime] = None
                                              ) -> Optional[dict]:
    """Returns a small dict the player can use to render an action card.
    Honours frequency cap: at most 1 mention every 30 minutes of listening
    per user (tracked via `rj_game_mentions_log`)."""
    now = now or _now()
    last = await db.rj_game_mentions_log.find_one(
        {"user_id": user["user_id"]},
        sort=[("ts", -1)])
    if last:
        last_ts = last["ts"]
        if isinstance(last_ts, datetime) and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        if (now - last_ts).total_seconds() < RJ_MENTION_COOLDOWN_SEC:
            return None
    # Priority 1: unplayed unlock
    unlock = await db.user_game_unlocks.find_one({
        "user_id": user["user_id"], "played": False,
        "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]
    }, sort=[("unlocked_at", -1)])
    if unlock:
        c = await db.game_campaigns.find_one(
            {"campaign_id": unlock["campaign_id"], "status": "active"})
        if c:
            return _announce_view(c, source="unlock")
    # Priority 2: sponsored open-to-all campaigns matching user's pref
    pref = (user.get("preference_vector") or {})
    target_channels = pref.get("genres") or []
    cur = db.game_campaigns.find({
        "status": "active", "open_to_all": True,
        "is_platform_funded": False,
        "$or": [{"end_at": None}, {"end_at": {"$gt": now}}],
    }).limit(20)
    sponsored = []
    async for c in cur:
        sponsored.append(c)
    if sponsored:
        return _announce_view(random.choice(sponsored), source="sponsored")
    # Priority 3: house games user hasn't played today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    played_today = set()
    async for s in db.game_sessions.find(
            {"user_id": user["user_id"],
             "started_at": {"$gte": today_start},
             "campaign_id": {"$in": [HOUSE_SPIN_ID, HOUSE_TRIVIA_ID,
                                            HOUSE_LYRIC_ID]}},
            {"campaign_id": 1, "_id": 0}):
        played_today.add(s["campaign_id"])
    fresh_house = [cid for cid in (HOUSE_SPIN_ID, HOUSE_TRIVIA_ID,
                                              HOUSE_LYRIC_ID) if cid not in played_today]
    if fresh_house:
        cid = random.choice(fresh_house)
        c = await db.game_campaigns.find_one({"campaign_id": cid})
        if c: return _announce_view(c, source="house")
    return None


def _announce_view(c: dict, *, source: str) -> dict:
    return {
        "campaign_id": c["campaign_id"],
        "title": c["title"],
        "sponsor_name": c.get("sponsor_name") or "RadioLife",
        "sponsor_logo_url": c.get("sponsor_logo_url"),
        "brand_colors_json": c.get("brand_colors_json") or {},
        "description": c.get("description") or "",
        "template_id": c["template_id"],
        "public_slug": c.get("public_slug"),
        "cta_short": "Play & win — tap to start",
        "source": source,
    }


async def log_rj_game_mention(db, user_id: str, campaign_id: str,
                                     segment_id: Optional[str] = None,
                                     source_context: Optional[dict] = None) -> dict:
    """Records the RJ-announce impression for both the frequency cap and
    the campaign's analytics counter."""
    now = _now()
    doc_id = _new_id("rjm")
    await db.rj_game_mentions_log.insert_one({
        "_id": doc_id, "user_id": user_id, "campaign_id": campaign_id,
        "segment_id": segment_id, "ts": now,
        "source_context": source_context or {},
    })
    await db.game_analytics_events.insert_one({
        "_id": _new_id("evt"), "campaign_id": campaign_id,
        "user_id": user_id, "event_type": "impression",
        "source_context_json": {"source": "rj_announce", **(source_context or {})},
        "metadata_json": {"mention_id": doc_id, "segment_id": segment_id},
        "ts": now,
    })
    return {"mention_id": doc_id, "ts": now.isoformat()}


# ---------------------------------------------------------------------
# Partner-token gating (Phase 8b)
# ---------------------------------------------------------------------
async def ensure_partner_tokens_indexes(db):
    await db.partner_tokens.create_index([("partner_token_id", 1)], unique=True)
    await db.partner_tokens.create_index([("partner_business_id", 1)])
    await db.redemption_audit_log.create_index([("ts", -1)])
    await db.redemption_audit_log.create_index([("partner_token_id", 1), ("ts", -1)])
    await db.redemption_audit_log.create_index([("campaign_id", 1), ("ts", -1)])
    await db.redemption_audit_log.create_index([("outcome", 1), ("ts", -1)])
    await db.game_landing_pages.create_index([("slug", 1)], unique=True)
    await db.rj_game_mentions_log.create_index([("user_id", 1), ("ts", -1)])


async def issue_partner_token(db, partner_business_id: str,
                                     scopes: list[str],
                                     issued_by_user_id: str) -> dict:
    """Returns the raw secret ONE TIME — the DB only ever sees the bcrypt hash."""
    raw = "ptk_" + secrets.token_urlsafe(28)
    secret_hash = _bcrypt.hashpw(raw.encode("utf-8"),
                                       _bcrypt.gensalt(rounds=10)).decode("utf-8")
    pid = _new_id("ptkid")
    now = _now()
    await db.partner_tokens.insert_one({
        "_id": pid, "partner_token_id": pid,
        "partner_business_id": partner_business_id,
        "secret_hash": secret_hash,
        "scopes": scopes or ["redeem_campaigns"],
        "created_at": now, "revoked_at": None,
        "last_used_at": None,
        "issued_by_user_id": issued_by_user_id,
    })
    return {"partner_token_id": pid, "raw_secret": raw,
            "scopes": scopes, "warning": "Store this secret now — it will not be shown again."}


async def revoke_partner_token(db, partner_token_id: str) -> bool:
    res = await db.partner_tokens.update_one(
        {"partner_token_id": partner_token_id, "revoked_at": None},
        {"$set": {"revoked_at": _now()}},
    )
    return res.modified_count == 1


async def validate_partner_token(db, raw_secret: str,
                                       required_scope: str = "redeem_campaigns"
                                       ) -> Optional[dict]:
    """Returns the partner_tokens row if valid + scope present, else None.

    For audit purposes call `check_partner_token_status` instead, which
    distinguishes revoked tokens from invalid tokens."""
    row, status = await check_partner_token_status(db, raw_secret,
                                                            required_scope=required_scope)
    return row if status == "valid" else None


async def check_partner_token_status(db, raw_secret: str,
                                            required_scope: str = "redeem_campaigns"
                                            ) -> tuple[Optional[dict], str]:
    """Returns (row, status). `status` is one of:
       - 'valid'   — token matches, not revoked, scope present
       - 'revoked' — token matches but revoked_at is set
       - 'invalid' — empty / wrong prefix / no match / scope missing
    """
    if not raw_secret or not raw_secret.startswith("ptk_"):
        return None, "invalid"
    # We can't index by hash → scan ALL tokens (small set in 8b).  At
    # scale this would use a secret_id prefix lookup; deferred to 8c.
    cur = db.partner_tokens.find({}).limit(500)
    async for row in cur:
        try:
            if _bcrypt.checkpw(raw_secret.encode("utf-8"),
                                  row["secret_hash"].encode("utf-8")):
                if row.get("revoked_at") is not None:
                    return row, "revoked"
                if required_scope and required_scope not in (row.get("scopes") or []):
                    return None, "invalid"
                await db.partner_tokens.update_one(
                    {"_id": row["_id"]},
                    {"$set": {"last_used_at": _now()}},
                )
                return row, "valid"
        except Exception:
            continue
    return None, "invalid"


async def write_redemption_audit(db, *, qr_token_prefix: str,
                                       partner_token_id: Optional[str],
                                       outcome: str, reason: Optional[str],
                                       ip: Optional[str] = None,
                                       user_agent: Optional[str] = None,
                                       campaign_id: Optional[str] = None,
                                       wallet_item_id: Optional[str] = None
                                       ) -> None:
    aud_id = _new_id("aud")
    await db.redemption_audit_log.insert_one({
        "_id": aud_id, "audit_id": aud_id,
        "qr_token_prefix": qr_token_prefix,
        "partner_token_id": partner_token_id,
        "campaign_id": campaign_id,
        "wallet_item_id": wallet_item_id,
        "outcome": outcome, "reason": reason,
        "ts": _now(), "ip": ip, "user_agent": user_agent,
    })


# ---------------------------------------------------------------------
# Asset upload (Phase 8b)
# ---------------------------------------------------------------------
async def save_uploaded_asset(db, *, filename: str, content_type: str,
                                     data: bytes,
                                     uploaded_by_user_id: str) -> dict:
    """Validate MIME + size + dim then write to /storage/game_assets/<uuid>.<ext>.
    Returns {url, asset_id}."""
    if content_type not in ASSET_MIME_WHITELIST:
        raise ValueError(f"unsupported_mime:{content_type}")
    if len(data) > ASSET_MAX_BYTES:
        raise ValueError(f"file_too_large:{len(data)}")
    # Dim validation
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        if max(w, h) > ASSET_MAX_DIM:
            raise ValueError(f"dim_too_large:{w}x{h}")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"invalid_image:{e}")
    ext = {"image/png": "png", "image/jpeg": "jpg",
             "image/webp": "webp"}[content_type]
    asset_id = _new_id("gasset")
    fname = f"{asset_id}.{ext}"
    path = ASSETS_DIR / fname
    with open(path, "wb") as f:
        f.write(data)
    url = f"/api/games_v2/assets/{fname}"
    await db.game_uploaded_assets.insert_one({
        "_id": asset_id, "asset_id": asset_id,
        "filename": fname, "content_type": content_type,
        "size_bytes": len(data), "width": w, "height": h,
        "url": url,
        "uploaded_by_user_id": uploaded_by_user_id,
        "uploaded_at": _now(),
    })
    return {"asset_id": asset_id, "url": url,
            "width": w, "height": h, "size_bytes": len(data)}
