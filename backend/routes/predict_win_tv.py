"""Sub-Phase E3 — Predict & Win TV kiosk surface.

Anonymous polling endpoint that backs the `/tv/predict-win/{code}`
React component.  Updates `last_seen_at` + `poll_count` on every hit
so business owners can see if their paired TV is alive.

Surfaces (all anonymous):
    GET    /api/tv/predict-win/{pairing_code}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from routes.predict_win_admin import _strip_mongo, _iso, _now

logger = logging.getLogger("bigfm.predict_win.tv")

router = APIRouter(prefix="/api/tv/predict-win", tags=["predict-win-tv"])


def _aware(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _public_qr_url(host: str, campaign_id: str, token: str) -> str:
    return (f"{host}/predict-win/checkin"
                  f"?campaign={campaign_id}&token={token}")


@router.get("/{pairing_code}",
                          description=(
                              "Public TV kiosk state for a paired Predict & Win "
                              "display.  Anonymous (no session cookie required).  "
                              "Polled by the TV browser every ~5s.  Returns the "
                              "campaign question, options with live community pick "
                              "distribution, prize summary, no-purchase-necessary "
                              "disclaimer, a fresh QR-code payload URL (so the "
                              "TV refreshes the QR as tokens rotate), and the "
                              "current resolution state (winner reveal)."))
async def get_tv_state(pairing_code: str, request: Request):
    db = request.app.state.db
    code = pairing_code.strip().upper()
    tv = await db.predict_win_tv_displays.find_one(
        {"pairing_code": code, "active": True})
    if not tv:
        raise HTTPException(404, {"code": "tv_pairing_not_found",
                                                          "message": "Pairing code not recognised."})
    campaign = await db.predict_win_campaigns.find_one(
        {"campaign_id": tv["campaign_id"]})
    if not campaign or campaign.get("deleted_at"):
        raise HTTPException(404, {"code": "campaign_not_found"})

    # Heartbeat — every poll updates last_seen and increments the counter.
    await db.predict_win_tv_displays.update_one(
        {"display_id": tv["display_id"]},
        {"$set": {"last_seen_at": _now()},
          "$inc": {"poll_count": 1}})

    # Question + options.
    question = campaign.get("question") or {}
    options = question.get("answer_options") or []
    option_index = {o["option_id"]: o for o in options}

    # Live community pick distribution (excludes void entries).
    pipeline = [
        {"$match": {"campaign_id": tv["campaign_id"],
                              "status": {"$ne": "void"}}},
        {"$group": {"_id": "$picked_option_id", "count": {"$sum": 1}}},
    ]
    by_opt: Dict[str, int] = {}
    total = 0
    async for r in db.predict_win_entries.aggregate(pipeline):
        by_opt[r["_id"]] = int(r["count"] or 0)
        total += int(r["count"] or 0)
    distribution: List[dict] = []
    for o in options:
        cnt = by_opt.get(o["option_id"], 0)
        distribution.append({
            "option_id": o["option_id"],
            "label": o["label"],
            "count": cnt,
            "pct": round((cnt / total) * 100.0, 1) if total > 0 else 0.0,
        })

    # Latest active check-in token so the TV can render a fresh QR.
    qr_payload_url: Optional[str] = None
    latest_token = None
    if campaign.get("checkin_required"):
        latest_token = await db.predict_win_checkin_tokens.find_one(
            {"campaign_id": tv["campaign_id"]},
            sort=[("issued_at", -1)])
    if latest_token:
        host = str(request.base_url).rstrip("/")
        qr_payload_url = _public_qr_url(
            host, tv["campaign_id"], latest_token["token"])

    # Prize summary (rank 1 by default).
    top_prize = await db.predict_win_prizes.find_one(
        {"campaign_id": tv["campaign_id"], "active": True},
        sort=[("rank", 1)])
    prize_summary = None
    if top_prize:
        prize_summary = {
            "title": top_prize.get("title"),
            "description": top_prize.get("description"),
            "value_amount": top_prize.get("value_amount"),
            "value_currency": top_prize.get("value_currency"),
            "image_url": top_prize.get("image_url"),
        }
    all_prizes_cur = db.predict_win_prizes.find(
        {"campaign_id": tv["campaign_id"], "active": True}).sort("rank", 1)
    all_prizes = [_strip_mongo(p) async for p in all_prizes_cur]

    # Resolution (if any).
    resolution = await db.predict_win_resolutions.find_one(
        {"campaign_id": tv["campaign_id"]})
    winning_option = None
    if resolution:
        winning_option = option_index.get(resolution["winning_option_id"])

    # Sponsor / branding from the owning station.
    station = await db.community_radio_stations.find_one(
        {"slug": tv.get("business_station_slug")})
    sponsor = None
    if station:
        bp = station.get("business_profile") or {}
        sponsor = {
            "station_slug": station.get("slug"),
            "name": bp.get("business_name") or station.get("name"),
            "logo_url": bp.get("logo_url"),
            "cover_color": station.get("cover_color"),
            "city": bp.get("city"),
            "verified": bool(bp.get("verified")),
        }

    # Compliance disclaimer + terms.
    compliance = None
    if campaign.get("compliance_settings_id"):
        compliance = await db.prediction_compliance_settings.find_one(
            {"settings_id": campaign["compliance_settings_id"]})
    no_purchase_necessary_text = (
        compliance.get("no_purchase_necessary_text") if compliance else None)
    terms_short = ("No purchase necessary. Open to legal residents only. "
                                f"Age {compliance.get('age_restriction',18) if compliance else 18}+. "
                                "See full terms on app.bigfm.")

    lock_dt = _aware(campaign.get("lock_time"))
    start_dt = _aware(campaign.get("start_time"))
    now = _now()
    lock_seconds_remaining = (
        int((lock_dt - now).total_seconds()) if lock_dt else None)
    seconds_to_start = (
        int((start_dt - now).total_seconds()) if start_dt else None)

    return {
        "campaign": {
            "campaign_id": campaign["campaign_id"],
            "title": campaign["title"],
            "description": campaign.get("description"),
            "event_type": campaign.get("event_type"),
            "event_label": campaign.get("event_label"),
            "city": campaign.get("city"),
            "status": campaign.get("status"),
            "approval_status": campaign.get("approval_status"),
            "checkin_required": bool(campaign.get("checkin_required")),
            "start_time": _iso(campaign.get("start_time")),
            "lock_time": _iso(campaign.get("lock_time")),
            "lock_seconds_remaining": (
                max(0, lock_seconds_remaining)
                if lock_seconds_remaining is not None else None),
            "seconds_to_start": (
                max(0, seconds_to_start)
                if seconds_to_start is not None else None),
        },
        "question": {
            "prompt": question.get("prompt"),
            "options": [{"option_id": o["option_id"], "label": o["label"]}
                              for o in options],
        },
        "distribution": distribution,
        "total_entries": total,
        "qr_payload_url": qr_payload_url,
        "prize_summary": prize_summary,
        "prizes": all_prizes,
        "resolution": (
            {"winning_option_id": resolution["winning_option_id"],
              "winning_option": winning_option,
              "resolved_at": _iso(resolution.get("resolved_at")),
              "result_source": resolution.get("result_source")}
            if resolution else None),
        "sponsor": sponsor,
        "compliance": {
            "no_purchase_necessary_text": no_purchase_necessary_text,
            "short_disclaimer": terms_short,
            "terms_settings_id": (
                compliance.get("settings_id") if compliance else None),
            "age_restriction": (
                compliance.get("age_restriction") if compliance else 18),
        },
        "tv_display": {
            "display_id": tv["display_id"],
            "pairing_code": tv["pairing_code"],
            "label": tv.get("label"),
        },
        "refresh_after_sec": 5,
    }
