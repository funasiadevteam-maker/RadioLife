"""Phase 36d — Shoppable action cards bound to episode playback windows.

Card types: save_coupon, buy_ticket, book_appointment, get_directions,
                          request_callback, join_giveaway, add_to_wallet, share_clip.

Listener fetches cards active in the current playback window. When a card is
backed by an `offer_id`, "Save coupon" funnels into the Phase 17 offer system
with `attribution_source="podcast_action_card"` + `episode_id` for funnel
visibility — without touching the Phase 18 attribution writer.
"""
from __future__ import annotations
import logging, uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.podcast_action_cards")

COL                = "podcast_action_cards"
ALLOWED = ("save_coupon", "buy_ticket", "book_appointment", "get_directions",
                  "request_callback", "join_giveaway", "add_to_wallet", "share_clip")


def _now(): return datetime.now(timezone.utc)
def _gen(p): return f"{p}_{uuid.uuid4().hex[:14]}"


async def create_card(db, *, episode_id: str,
                                          owner_user_id: Optional[str] = None,
                                          creator_id: Optional[str] = None,
                                          body: dict) -> dict:
    """Insert a new action-card row.

    Phase P2 hygiene rename — `owner_user_id` is the new canonical field
    (the value is the authenticated user's `user_id`; the field was misnamed
    `creator_id` historically). For backward compatibility:
      • Both kwargs are accepted; `owner_user_id` wins if both supplied.
      • Each persisted row carries BOTH keys with identical values so
        legacy readers that key off `creator_id` keep working until they
        migrate. Aliasing layer removed in a subsequent release cycle.
    """
    uid = owner_user_id or creator_id
    if not uid:
        raise ValueError("owner_user_id is required")
    ct = body.get("card_type")
    if ct not in ALLOWED:
        raise ValueError(f"card_type must be one of {ALLOWED}")
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep: raise LookupError("episode_not_found")
    s = float(body.get("start_time_seconds") or 0)
    e = float(body.get("end_time_seconds") or 0)
    if e <= s: raise ValueError("end_time_seconds must be > start_time_seconds")
    row = {
        "id":                                   _gen("pac"),
        "episode_id":                    episode_id,
        "channel_id":                    ep.get("channel_id"),
        # Phase 19 Part C — `creator_id` alias DROPPED. New rows carry only
        # `owner_user_id`. Legacy rows still have `creator_id`; ownership
        # check in patch_card falls back to it.
        "owner_user_id":             uid,
        "card_type":                       ct,
        "title":                                (body.get("title") or "")[:120],
        "description":                  (body.get("description") or "")[:400],
        "start_time_seconds":     s,
        "end_time_seconds":         e,
        "offer_id":                          body.get("offer_id"),
        "product_id":                    body.get("product_id"),
        "appointment_service_id": body.get("appointment_service_id"),
        "event_id":                          body.get("event_id"),
        "destination_url":             (body.get("destination_url") or "")[:500],
        "active":                              bool(body.get("active", True)),
        "created_at":                    _now(), "updated_at": _now(),
    }
    await db[COL].insert_one(row); row.pop("_id", None)
    return row


async def list_cards_for_creator(db, *, episode_id: str) -> list:
    rows = await db[COL].find({"episode_id": episode_id},
                                                          {"_id": 0}).sort("start_time_seconds", 1
                                                                                          ).to_list(200)
    return rows


async def list_active_cards_at_time(db, *, episode_id: str,
                                                                          current_seconds: float) -> list:
    rows = await db[COL].find({"episode_id": episode_id, "active": True,
                                                          "start_time_seconds": {"$lte": current_seconds},
                                                          "end_time_seconds":     {"$gte": current_seconds}},
                                                        {"_id": 0}).to_list(20)
    return rows


async def patch_card(db, *, card_id: str, episode_id: str,
                                          owner_user_id: Optional[str] = None,
                                          creator_id: Optional[str] = None,
                                          body: dict) -> dict:
    """See create_card docstring — same alias rules apply to ownership check."""
    uid = owner_user_id or creator_id
    if not uid:
        raise ValueError("owner_user_id is required")
    card = await db[COL].find_one({"id": card_id, "episode_id": episode_id})
    if not card: raise LookupError("card_not_found")
    # Accept either field on stored row (legacy rows have only `creator_id`).
    row_owner = card.get("owner_user_id") or card.get("creator_id")
    if row_owner != uid: raise PermissionError("not_owner")
    upd = {}
    for k in ("title", "description", "destination_url", "active",
                      "start_time_seconds", "end_time_seconds", "card_type",
                      "offer_id", "product_id", "appointment_service_id", "event_id"):
        if k in body: upd[k] = body[k]
    if upd.get("card_type") and upd["card_type"] not in ALLOWED:
        raise ValueError(f"card_type must be one of {ALLOWED}")
    upd["updated_at"] = _now()
    await db[COL].update_one({"id": card_id}, {"$set": upd})
    return {**card, **upd, "_id": None, "id": card_id}


async def save_offer_via_card(db, *, card_id: str, user_id: str
                                                              ) -> dict:
    """Click-through: stamps Phase 17 saved_offers with the podcast attribution
    source + episode_id. Does NOT modify the Phase 17 service code; just writes
    the standard saved-offer row with extra attribution fields."""
    card = await db[COL].find_one({"id": card_id})
    if not card or not card.get("offer_id"):
        raise LookupError("card_or_offer_missing")
    row = {
        "id":                            _gen("usf"),
        "user_id":                    user_id,
        "offer_id":                  card["offer_id"],
        "saved_at":                  _now(),
        "redeemed_at":          None,
        "attribution_source": "podcast_action_card",
        "attribution_card_id": card["id"],
        "attribution_episode_id": card.get("episode_id"),
        "attribution_channel_id": card.get("channel_id"),
    }
    await db.saved_offers.insert_one(row); row.pop("_id", None)
    return row
