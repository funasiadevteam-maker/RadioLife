"""Phase L — M5 Radio Takeover Hour.

An advertiser rents an entire 60-minute hour on a single station,
all stations in a region, or all stations globally.  During the
hour, listeners see a "Presented by {advertiser}" branded overlay,
hear 4 sponsored AI-RJ reads at the top of each 15-min block,
featured deals bubble to the top of the marketplace panel, and
listeners who accumulate >= threshold_listen_seconds get a bonus
awarded once (BigCoin OR USD voucher).

Reuses:
    * Phase D  persona catalog (`rj_personas` + persona.voice_id)
    * Phase D  script -> TTS -> Tigris pipeline (`_synthesize_audio`,
      `_upload_to_storage`, `key_rj`) via same helper we used in
      Phase I (`rj_sponsored_read_service._tts_render_upload`
      shape — copied here to keep the service self-contained since
      we render 4 audios in a single confirm-payment call).
    * ADMOD.1 `ad_moderation_service.moderate_creative_text` for the
      overlay text + all 4 rj_scripts (same gate as Phase I).
    * Phase G  Stripe prepay + refund pattern.
    * Phase F  sweeper pattern (`scheduled -> live` when
      `start_at <= now < end_at`, `live -> completed` when
      `end_at <= now`).
    * Phase H  BigCoin award primitive (PointsService) + Phase H
      voucher mint primitive (offers + coupons insert) for the
      bonus giveaway.

Money model (priciest ad product):
    media_cost   = advertiser-picked base (min $50)
    platform_fee = 40% of media_cost
    total_cost   = media + fee
    admin approval when total >= $500 (50000 cents)
    cancellation refuses (409) if status == "live"

Idempotency:
    * listener sessions unique per (takeover_id, session_id)
    * bonus awards unique per (takeover_id, user_id)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.m5_takeover_hour")

# ── Constants ─────────────────────────────────────────────────────
PLATFORM_FEE_PCT              = 40
ADMIN_APPROVAL_THRESHOLD      = 50_000        # $500
MIN_MEDIA_COST_CENTS          = 5_000         # $50 floor
DEFAULT_BONUS_THRESHOLD_SEC   = 1200          # 20 min
HOUR_DURATION_SECONDS         = 3600
BLOCK_COUNT                   = 4             # blocks at 0/15/30/45
BLOCK_INTERVAL_SECONDS        = 900           # 15 min
BLOCK_TRIGGER_WINDOW_SEC      = 15            # return audio when within +/- 15s
MAX_FEATURED_DEALS            = 5
STATUSES = {"draft", "pending_moderation", "pending_admin",
            "active", "live", "completed", "cancelled", "rejected"}
STATION_SCOPES = {"single", "region", "global"}


# ── Helpers ───────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _aware(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _shape(t: Dict[str, Any]) -> Dict[str, Any]:
    if not t:
        return t
    out = dict(t)
    out.pop("_id", None)
    for k in ("start_at", "end_at", "created_at", "activated_at",
              "went_live_at", "completed_at", "cancelled_at",
              "submitted_at", "rendered_at", "paid_at", "decided_at",
              "rejected_at"):
        if k in out and isinstance(out[k], datetime):
            out[k] = _iso(out[k])
    return out


async def ensure_takeover_hour_indexes(db) -> None:
    try:
        await db.takeover_hours.create_index("id", unique=True,
                                             name="th_id_uniq")
        await db.takeover_hours.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="th_adv_status")
        await db.takeover_hours.create_index(
            [("status", 1), ("start_at", 1)], name="th_status_start")
        await db.takeover_hours.create_index(
            [("station_scope", 1), ("station_id", 1), ("start_at", 1)],
            name="th_scope_station_start")
        await db.takeover_hours.create_index(
            [("station_scope", 1), ("region_code", 1), ("start_at", 1)],
            name="th_scope_region_start")

        await db.takeover_hour_listener_sessions.create_index(
            "id", unique=True, name="ths_id_uniq")
        await db.takeover_hour_listener_sessions.create_index(
            [("takeover_id", 1), ("session_id", 1)],
            unique=True, name="ths_take_sess_uniq")
        await db.takeover_hour_listener_sessions.create_index(
            [("takeover_id", 1), ("user_id", 1)],
            name="ths_take_user")

        await db.takeover_hour_bonus_awards.create_index(
            "id", unique=True, name="thba_id_uniq")
        await db.takeover_hour_bonus_awards.create_index(
            [("takeover_id", 1), ("user_id", 1)],
            unique=True, name="thba_take_user_uniq")
        logger.info("[m5_takeover] indexes ready")
    except Exception as e:
        logger.warning("[m5_takeover] index setup failed: %s", e)


# ── Money helpers ─────────────────────────────────────────────────
def _compute_costs(media_cost_cents: int) -> Dict[str, int]:
    media = max(int(media_cost_cents), MIN_MEDIA_COST_CENTS)
    fee = (media * PLATFORM_FEE_PCT) // 100
    total = media + fee
    return {"media_cost_cents": media,
            "platform_fee_cents": fee,
            "total_cost_cents": total,
            "admin_approval_required":
                total >= ADMIN_APPROVAL_THRESHOLD}


# ── Stripe helpers (test-mode) ────────────────────────────────────
async def _charge_prepayment(*, amount_cents: int, takeover_id: str,
                             advertiser_business_id: str) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=int(amount_cents),
            currency="usd",
            payment_method_types=["card"],
            payment_method="pm_card_visa",
            confirm=True,
            metadata={
                "bigfm_flow":            "m5_takeover_hour_prepay",
                "bigfm_takeover_id":     takeover_id,
                "bigfm_advertiser_id":   advertiser_business_id,
            },
            idempotency_key=f"m5_th_prepay_{takeover_id}")
        return {"payment_intent_id": intent.id,
                "amount_cents": int(amount_cents),
                "status": intent.status}
    except Exception as e:
        logger.exception("[m5_takeover] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund(*, payment_intent_id: str, refund_cents: int,
                  takeover_id: str) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        r = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "m5_takeover_refund",
                      "bigfm_takeover_id": takeover_id},
            idempotency_key=f"m5_th_refund_{takeover_id}_{secrets.token_hex(3)}")
        return {"refund_id": r.id,
                "amount_cents": int(refund_cents),
                "status": r.status}
    except Exception as e:
        logger.exception("[m5_takeover] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


# ── LLM draft (auto) ─────────────────────────────────────────────
async def _llm_draft_block(*, persona: Dict[str, Any],
                           block_index: int, advertiser_name: str,
                           tagline: Optional[str],
                           overall_theme: Optional[str]) -> str:
    fallback = (
        f"Presented by {advertiser_name}. "
        f"{tagline or f'{advertiser_name} is bringing you the vibe.'} "
        f"You are on the {advertiser_name} takeover on BigFM — "
        f"stay locked in.")
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return fallback
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        system = (
            f"You are drafting one of 4 short radio host reads for a "
            f"1-hour advertiser takeover.  Voice: "
            f"{persona.get('name') or 'a BigFM host'} — "
            f"{persona.get('persona_prompt') or 'upbeat, warm, conversational'}. "
            f"MUST open with 'Presented by {advertiser_name}'.  "
            f"Keep total spoken length 12-18 seconds (35-55 words).  "
            f"No emoji, no stage directions.")
        block_hints = ["opening ident", "mid-hour cheer",
                       "half-hour recap", "final push + CTA"]
        hint = block_hints[block_index] if 0 <= block_index < 4 else "read"
        user = (
            f"Advertiser: {advertiser_name}.\n"
            f"Tagline: {tagline or '—'}.\n"
            f"Hour theme: {overall_theme or '—'}.\n"
            f"Block position (0-3): {block_index} — {hint}.\n"
            f"Language: {persona.get('language') or 'en'}.\n"
            f"Write the read now, starting with "
            f"'Presented by {advertiser_name}'.")
        chat = (LlmChat(api_key=api_key,
                        session_id=f"m5_th_{_gen('drft')[:8]}",
                        system_message=system)
                .with_model("openai", "gpt-4o-mini"))
        resp = await chat.send_message(UserMessage(text=user))
        text = (resp or "").strip()
        if not text.lower().startswith(f"presented by {advertiser_name}".lower()):
            text = f"Presented by {advertiser_name}. {text}"
        return text[:600]
    except Exception as e:
        logger.warning("[m5_takeover] LLM draft failed: %s — fallback", e)
        return fallback


# ── TTS render helper (mirrors Phase I) ──────────────────────────
async def _tts_render_upload(*, persona: Dict[str, Any],
                             script: str) -> Dict[str, Any]:
    from services.rj_persona_service import (
        _synthesize_audio, _upload_to_storage,
        _gen as _persona_gen)
    from services.object_storage import key_rj
    provider = persona.get("voice_provider") or "elevenlabs"

    def _blocking():
        local_path = _synthesize_audio(
            script=script,
            voice_id=persona["voice_id"],
            voice_provider=provider,
            language=persona.get("language") or "en",
            personality=persona.get("personality") or "energetic")
        duration = None
        try:
            import subprocess
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", str(local_path)],
                stderr=subprocess.STDOUT, timeout=8)
            duration = float(out.decode().strip())
        except Exception:
            pass
        seg_id = _persona_gen("thblk")
        key = key_rj(seg_id)
        audio_url = _upload_to_storage(local_path, key)
        try:
            from services.object_storage import get_storage
            if get_storage().backend_name != "local":
                Path(local_path).unlink(missing_ok=True)
        except Exception:
            pass
        return {"audio_url": audio_url,
                "storage_key": key,
                "duration_seconds": duration,
                "voice_provider": provider}
    return await asyncio.to_thread(_blocking)


# ── CRUD ─────────────────────────────────────────────────────────
def _validate_duration(start_at: datetime, end_at: datetime) -> None:
    diff = (end_at - start_at).total_seconds()
    # 60-min duration, +/- 1 sec tolerance.
    if abs(diff - HOUR_DURATION_SECONDS) > 1:
        raise ValueError(
            f"duration_must_be_60_min:got={int(diff)}s")


def _validate_scope(scope: str, station_id: Optional[str],
                    region_code: Optional[str]) -> None:
    if scope not in STATION_SCOPES:
        raise ValueError(f"invalid_station_scope:{scope}")
    if scope == "single" and not station_id:
        raise ValueError("station_id_required_for_single_scope")
    if scope == "region" and not region_code:
        raise ValueError("region_code_required_for_region_scope")


async def create_takeover_hour(db, *, advertiser_business_id: str,
                               body: Dict[str, Any],
                               created_by_user_id: str
                               ) -> Dict[str, Any]:
    scope = (body.get("station_scope") or "").strip()
    station_id = (body.get("station_id") or "").strip() or None
    region_code = ((body.get("region_code") or "").strip().lower()
                   or None)
    _validate_scope(scope, station_id, region_code)

    start_at = _aware(body.get("start_at"))
    end_at = _aware(body.get("end_at"))
    if not start_at or not end_at:
        raise ValueError("start_at_and_end_at_required")
    _validate_duration(start_at, end_at)

    persona_id = (body.get("rj_persona_id") or "").strip()
    if not persona_id:
        raise ValueError("rj_persona_id_required")
    persona = await db.rj_personas.find_one({"id": persona_id})
    if not persona:
        raise ValueError("persona_not_found")

    rj_scripts_in = body.get("rj_scripts") or []
    if not isinstance(rj_scripts_in, list) or not rj_scripts_in:
        raise ValueError("at_least_one_rj_script_required")
    # Normalise to 4 blocks, auto-draft missing.
    advertiser_name = (body.get("advertiser_name") or "").strip()
    if not advertiser_name:
        raise ValueError("advertiser_name_required")
    tagline = (body.get("tagline") or "").strip() or None
    overall_theme = (body.get("overall_theme") or "").strip() or None

    scripts: List[Dict[str, Any]] = []
    provided_by_idx: Dict[int, Dict[str, Any]] = {}
    for s in rj_scripts_in:
        try:
            idx = int(s.get("block_index"))
        except Exception:
            continue
        if 0 <= idx < BLOCK_COUNT:
            provided_by_idx[idx] = s

    for i in range(BLOCK_COUNT):
        entry = provided_by_idx.get(i)
        if entry and (entry.get("script_text") or "").strip():
            txt = entry["script_text"].strip()
        else:
            txt = await _llm_draft_block(
                persona=persona,
                block_index=i,
                advertiser_name=advertiser_name,
                tagline=tagline,
                overall_theme=overall_theme)
        scripts.append({"block_index": i,
                        "script_text": txt[:800],
                        "audio_url": None,
                        "storage_key": None,
                        "duration_seconds": None})

    overlay = body.get("branded_overlay") or {}
    branded_overlay = {
        "advertiser_name": advertiser_name,
        "tagline": tagline,
        "logo_url": (overlay.get("logo_url") or "").strip() or None,
        "cta_url":  (overlay.get("cta_url") or "").strip() or None,
        "badge_color":
            (overlay.get("badge_color") or "").strip() or None,
    }

    featured_refs_in = body.get("featured_deal_refs") or []
    featured_refs: List[Dict[str, Any]] = []
    for r in featured_refs_in[:MAX_FEATURED_DEALS]:
        st = (r.get("source_type") or "").strip()
        si = (r.get("source_id") or "").strip()
        if st and si:
            featured_refs.append({"source_type": st, "source_id": si})

    bg = body.get("bonus_giveaway") or {}
    bonus_giveaway = {
        "threshold_listen_seconds":
            int(bg.get("threshold_listen_seconds")
                or DEFAULT_BONUS_THRESHOLD_SEC),
        "prize_type":
            (bg.get("prize_type") or "").strip() or None,
        "prize_amount":
            int(bg.get("prize_amount") or 0),
        "max_winners":
            int(bg.get("max_winners") or 0),  # 0 = unlimited
    }

    # Spec: at least 1 featured deal OR bonus giveaway.
    if (not featured_refs
            and not (bonus_giveaway["prize_type"]
                     and bonus_giveaway["prize_amount"])):
        raise ValueError(
            "at_least_one_featured_deal_or_bonus_required")

    if bonus_giveaway["prize_type"]:
        if bonus_giveaway["prize_type"] not in ("bc", "usd_voucher"):
            raise ValueError("invalid_prize_type")
        if bonus_giveaway["prize_amount"] <= 0:
            raise ValueError("invalid_prize_amount")

    media_cost = int(body.get("media_cost_cents")
                     or MIN_MEDIA_COST_CENTS)
    costs = _compute_costs(media_cost)

    listener_reach = int(body.get("listener_reach_estimate") or 0)
    if listener_reach <= 0:
        listener_reach = 500 if scope == "single" else (
            5000 if scope == "region" else 25000)

    now = _now()
    takeover_id = _gen("mth")
    doc = {
        "_id": takeover_id,
        "id":  takeover_id,
        "advertiser_business_id": advertiser_business_id,
        "station_scope": scope,
        "station_id":    station_id,
        "region_code":   region_code,
        "start_at":      start_at,
        "end_at":        end_at,
        "rj_persona_id": persona_id,
        "rj_persona_name": persona.get("name"),
        "rj_scripts":    scripts,
        "branded_overlay": branded_overlay,
        "featured_deal_refs": featured_refs,
        "bonus_giveaway":  bonus_giveaway,
        "media_cost_cents":     costs["media_cost_cents"],
        "platform_fee_cents":   costs["platform_fee_cents"],
        "total_cost_cents":     costs["total_cost_cents"],
        "cost_cents":           costs["total_cost_cents"],
        "admin_approval_required": costs["admin_approval_required"],
        "listener_reach_estimate": listener_reach,
        "actual_listeners_delivered": 0,
        "bonus_awards_delivered":     0,
        "status": "draft",
        "moderation_result": None,
        "stripe_prepayment_transaction_id": None,
        "stripe_payment_intent_id": None,
        "stripe_refund_id": None,
        "refunded_amount_cents": 0,
        "created_by_user_id": created_by_user_id,
        "created_at":  now,
        "submitted_at": None,
        "paid_at":      None,
        "activated_at": None,
        "went_live_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "cancel_reason": None,
        "admin_notes": None,
        "decided_by_user_id": None,
        "decided_at": None,
        "rejected_at": None,
    }
    await db.takeover_hours.insert_one(doc)
    return _shape(doc)


async def submit_takeover_hour(db, *, takeover_id: str,
                               advertiser_business_id: str
                               ) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if t["status"] != "draft":
        raise ValueError(f"takeover_{t['status']}")

    from services.ad_moderation_service import moderate_creative_text
    texts = [t["branded_overlay"].get("advertiser_name") or "",
             t["branded_overlay"].get("tagline") or ""]
    for s in t["rj_scripts"]:
        texts.append(s.get("script_text") or "")
    texts = [x for x in texts if x]
    mod = await moderate_creative_text(texts)

    now = _now()
    if mod.get("flagged") or mod.get("action_taken") == "flagged":
        await db.takeover_hours.update_one(
            {"id": takeover_id},
            {"$set": {"status": "rejected",
                      "moderation_result": mod,
                      "cancel_reason": "moderation_flagged",
                      "rejected_at": now}})
        row = await db.takeover_hours.find_one({"id": takeover_id})
        return _shape(row)

    await db.takeover_hours.update_one(
        {"id": takeover_id},
        {"$set": {"status": "pending_moderation",
                  "moderation_result": mod,
                  "submitted_at": now}})
    row = await db.takeover_hours.find_one({"id": takeover_id})
    return _shape(row)


async def confirm_payment(db, *, takeover_id: str,
                          advertiser_business_id: str
                          ) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if t["status"] != "pending_moderation":
        raise ValueError(f"takeover_{t['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(t["total_cost_cents"]),
        takeover_id=takeover_id,
        advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_mth")
    now = _now()
    await db.payment_transactions_v2.insert_one({
        "_id": tx_id,
        "transaction_id": tx_id,
        "stripe_payment_intent_id": charge["payment_intent_id"],
        "flow":               "m5_takeover_hour_prepay",
        "event_source":       "takeover_hour_prepay",
        "advertiser_id":      advertiser_business_id,
        "bigfm_takeover_id":  takeover_id,
        "amount_cents":       int(t["total_cost_cents"]),
        "application_fee_cents": int(t["platform_fee_cents"]),
        "merchant_net_cents": 0,
        "currency": "usd",
        "status":   "posted",
        "created_at": now,
    })

    # Render all 4 blocks now — 40% platform fee justifies the cost
    # of committing to ElevenLabs render before knowing final status.
    persona = await db.rj_personas.find_one({"id": t["rj_persona_id"]})
    if not persona:
        raise ValueError("persona_gone_missing")

    rendered_scripts: List[Dict[str, Any]] = []
    render_failed = False
    for s in t["rj_scripts"]:
        try:
            tts = await _tts_render_upload(
                persona=persona, script=s["script_text"])
            rendered_scripts.append({**s,
                                     "audio_url": tts["audio_url"],
                                     "storage_key": tts.get("storage_key"),
                                     "duration_seconds":
                                        tts.get("duration_seconds")})
        except Exception as e:
            logger.exception("[m5_takeover] block %s render failed: %s",
                             s.get("block_index"), e)
            render_failed = True
            break

    if render_failed:
        # Refund + reject.
        try:
            r = await _refund(payment_intent_id=charge["payment_intent_id"],
                              refund_cents=int(t["total_cost_cents"]),
                              takeover_id=takeover_id)
            await db.takeover_hours.update_one(
                {"id": takeover_id},
                {"$set": {"status": "rejected",
                          "cancel_reason": "tts_render_failed",
                          "stripe_refund_id": r["refund_id"],
                          "refunded_amount_cents": r["amount_cents"],
                          "rejected_at": _now()}})
        except Exception:
            pass
        raise ValueError("tts_render_failed")

    # Decide the new status.  If start_at <= now < end_at, we can
    # skip straight to live.  Else scheduled -> active (waiting for
    # sweeper).  If admin_approval_required, everything waits in
    # pending_admin until admin approves.
    now = _now()
    start_at = _aware(t["start_at"])
    end_at = _aware(t["end_at"])
    if t.get("admin_approval_required"):
        new_status = "pending_admin"
    elif start_at and start_at <= now < end_at:
        new_status = "live"
    else:
        new_status = "active"

    upd = {
        "status": new_status,
        "rj_scripts": rendered_scripts,
        "stripe_payment_intent_id": charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at": now,
        "rendered_at": now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    if new_status == "live":
        upd["activated_at"] = now
        upd["went_live_at"] = now
    await db.takeover_hours.update_one({"id": takeover_id}, {"$set": upd})

    row = await db.takeover_hours.find_one({"id": takeover_id})

    # Dispatch scheduled notification if we auto-activated.
    if new_status in ("active", "live"):
        try:
            from services.notification_trigger_dispatcher import (
                dispatch_event)
            await dispatch_event(
                db, event_name="takeover_scheduled",
                user_id=t.get("created_by_user_id"),
                payload={"takeover_id": takeover_id,
                         "advertiser_business_id":
                            advertiser_business_id,
                         "start_at": _iso(t["start_at"]),
                         "end_at":   _iso(t["end_at"]),
                         "auto_approved": True})
        except Exception as e:
            logger.warning("[m5_takeover] dispatch_event failed: %s", e)

    return {"takeover": _shape(row),
            "charge": charge,
            "transaction_id": tx_id}


async def list_takeover_hours(db, *,
                              advertiser_business_id: Optional[str] = None,
                              status: Optional[str] = None,
                              limit: int = 100
                              ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows = []
    async for d in db.takeover_hours.find(q).sort(
            "created_at", -1).limit(limit):
        rows.append(_shape(d))
    return rows


async def get_takeover_hour(db, *, takeover_id: str,
                            advertiser_business_id: Optional[str] = None
                            ) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if advertiser_business_id and \
            t["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    return _shape(t)


async def cancel_takeover_hour(db, *, takeover_id: str,
                               advertiser_business_id: str,
                               reason: str = "advertiser_cancelled"
                               ) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if t["status"] == "live":
        # Cannot refund a live hour.
        raise ValueError("cannot_cancel_live_takeover")
    if t["status"] not in ("draft", "pending_moderation",
                           "pending_admin", "active"):
        raise ValueError(f"takeover_{t['status']}")

    # Full refund of total_cost_cents when we've charged.
    refund: Optional[Dict[str, Any]] = None
    total = int(t.get("total_cost_cents") or 0)
    if t.get("stripe_payment_intent_id") and total > 0:
        refund = await _refund(
            payment_intent_id=t["stripe_payment_intent_id"],
            refund_cents=total,
            takeover_id=takeover_id)
    upd = {
        "status": "cancelled",
        "cancel_reason": reason,
        "cancelled_at": _now(),
    }
    if refund:
        upd["stripe_refund_id"] = refund["refund_id"]
        upd["refunded_amount_cents"] = refund["amount_cents"]
    await db.takeover_hours.update_one(
        {"id": takeover_id}, {"$set": upd})
    row = await db.takeover_hours.find_one({"id": takeover_id})
    return {"takeover": _shape(row), "refund": refund}


# ── Admin ────────────────────────────────────────────────────────
async def admin_list(db, *, status: Optional[str] = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows = []
    async for d in db.takeover_hours.find(q).sort(
            "created_at", -1).limit(limit):
        rows.append(_shape(d))
    return rows


async def admin_approve(db, *, takeover_id: str,
                        admin_user_id: str,
                        admin_notes: Optional[str] = None
                        ) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["status"] != "pending_admin":
        raise ValueError(f"takeover_{t['status']}")
    now = _now()
    start_at = _aware(t["start_at"])
    end_at = _aware(t["end_at"])
    new_status = ("live"
                  if start_at and start_at <= now < end_at
                  else "active")
    upd = {"status": new_status,
           "activated_at": now,
           "decided_by_user_id": admin_user_id,
           "decided_at": now,
           "admin_notes": (admin_notes or "").strip() or None}
    if new_status == "live":
        upd["went_live_at"] = now
    await db.takeover_hours.update_one(
        {"id": takeover_id}, {"$set": upd})

    try:
        from services.notification_trigger_dispatcher import (
            dispatch_event)
        await dispatch_event(
            db, event_name="takeover_scheduled",
            user_id=t.get("created_by_user_id"),
            payload={"takeover_id": takeover_id,
                     "advertiser_business_id":
                        t["advertiser_business_id"],
                     "start_at": _iso(t["start_at"]),
                     "end_at":   _iso(t["end_at"]),
                     "auto_approved": False})
    except Exception as e:
        logger.warning("[m5_takeover] dispatch_event failed: %s", e)

    row = await db.takeover_hours.find_one({"id": takeover_id})
    return _shape(row)


async def admin_reject(db, *, takeover_id: str,
                       admin_user_id: str,
                       admin_notes: str) -> Dict[str, Any]:
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["status"] not in ("pending_admin", "pending_moderation"):
        raise ValueError(f"takeover_{t['status']}")

    refund: Optional[Dict[str, Any]] = None
    total = int(t.get("total_cost_cents") or 0)
    if t.get("stripe_payment_intent_id") and total > 0:
        refund = await _refund(
            payment_intent_id=t["stripe_payment_intent_id"],
            refund_cents=total,
            takeover_id=takeover_id)
    now = _now()
    upd = {"status": "cancelled",
           "cancel_reason": "admin_rejected",
           "admin_notes": (admin_notes or "").strip() or None,
           "decided_by_user_id": admin_user_id,
           "decided_at": now,
           "cancelled_at": now}
    if refund:
        upd["stripe_refund_id"] = refund["refund_id"]
        upd["refunded_amount_cents"] = refund["amount_cents"]
    await db.takeover_hours.update_one(
        {"id": takeover_id}, {"$set": upd})
    row = await db.takeover_hours.find_one({"id": takeover_id})
    return {"takeover": _shape(row), "refund": refund}


# ── Sweeper ──────────────────────────────────────────────────────
async def sweep_takeover_hours(db) -> Dict[str, Any]:
    """Flips status: active -> live when start_at<=now<end_at,
    live -> completed when end_at<=now."""
    now = _now()
    r1 = await db.takeover_hours.update_many(
        {"status": "active",
         "start_at": {"$lte": now},
         "end_at":   {"$gt": now}},
        {"$set": {"status": "live", "went_live_at": now}})
    r2 = await db.takeover_hours.update_many(
        {"status": "live", "end_at": {"$lte": now}},
        {"$set": {"status": "completed", "completed_at": now}})
    return {"activated": r1.modified_count,
            "completed": r2.modified_count,
            "swept_at": _iso(now)}


# ── Listener runtime ─────────────────────────────────────────────
def _current_block_index(start_at: datetime,
                         now: Optional[datetime] = None) -> int:
    now = now or _now()
    seconds = int((now - start_at).total_seconds())
    if seconds < 0:
        return -1
    idx = seconds // BLOCK_INTERVAL_SECONDS
    return max(0, min(BLOCK_COUNT - 1, idx))


def _block_audio_if_due(t: Dict[str, Any],
                        session_last_played_block: Optional[int],
                        now: Optional[datetime] = None
                        ) -> Optional[Dict[str, Any]]:
    """Returns the block audio if we're within the trigger window
    of a block boundary AND the session hasn't played this block
    yet."""
    now = now or _now()
    start_at = _aware(t["start_at"])
    end_at = _aware(t["end_at"])
    if not (start_at and end_at and start_at <= now < end_at):
        return None
    idx = _current_block_index(start_at, now)
    boundary = start_at + timedelta(seconds=idx * BLOCK_INTERVAL_SECONDS)
    delta_from_boundary = abs((now - boundary).total_seconds())
    if delta_from_boundary > BLOCK_TRIGGER_WINDOW_SEC:
        return None
    if (session_last_played_block is not None
            and session_last_played_block >= idx):
        return None
    scripts = t.get("rj_scripts") or []
    if idx >= len(scripts):
        return None
    s = scripts[idx]
    if not s.get("audio_url"):
        return None
    return {"block_index": idx,
            "audio_url": s["audio_url"],
            "duration_seconds": s.get("duration_seconds")}


async def find_current_takeover(db, *, station_id: Optional[str],
                                region_code: Optional[str]
                                ) -> Optional[Dict[str, Any]]:
    """Picks the single takeover that is currently `live` and matches
    the requested context.  Priority: single(station_id) >
    region(region_code) > global."""
    now = _now()
    q_common = {"status": "live",
                "start_at": {"$lte": now},
                "end_at": {"$gt": now}}
    if station_id:
        t = await db.takeover_hours.find_one(
            {**q_common, "station_scope": "single",
             "station_id": station_id})
        if t:
            return t
    if region_code:
        t = await db.takeover_hours.find_one(
            {**q_common, "station_scope": "region",
             "region_code": region_code.lower()})
        if t:
            return t
    return await db.takeover_hours.find_one(
        {**q_common, "station_scope": "global"})


async def get_current_takeover_response(db, *,
                                        station_id: Optional[str],
                                        region_code: Optional[str],
                                        user_id: Optional[str] = None,
                                        session_id: Optional[str] = None
                                        ) -> Optional[Dict[str, Any]]:
    t = await find_current_takeover(
        db, station_id=station_id, region_code=region_code)
    if not t:
        return None
    start_at = _aware(t["start_at"])
    idx = _current_block_index(start_at)

    # Check session for last-played block to compute due-audio.
    session_last_played = None
    if session_id:
        sess = await db.takeover_hour_listener_sessions.find_one({
            "takeover_id": t["id"], "session_id": session_id})
        if sess:
            session_last_played = sess.get("last_played_block_index")
    due = _block_audio_if_due(t, session_last_played)

    return {
        "takeover_id":  t["id"],
        "advertiser_business_id": t["advertiser_business_id"],
        "advertiser_name":
            (t["branded_overlay"] or {}).get("advertiser_name"),
        "branded_overlay":  t["branded_overlay"],
        "station_scope":    t["station_scope"],
        "station_id":        t.get("station_id"),
        "region_code":      t.get("region_code"),
        "start_at":          _iso(t["start_at"]),
        "end_at":            _iso(t["end_at"]),
        "current_block_index": idx,
        "block_audio_url_if_due": due,
        "featured_deal_refs": t.get("featured_deal_refs") or [],
        "bonus_giveaway":    t.get("bonus_giveaway") or {},
    }


async def _award_bonus_bigcoin(db, *, takeover_id: str,
                               user_id: str,
                               points: int) -> Dict[str, Any]:
    from services.points_service import PointsService
    result = await PointsService(db).award(
        user_id=user_id,
        source="takeover_hour_bonus",
        source_id=takeover_id,
        delta=int(points),
        idempotency_key=f"mth_bonus_{takeover_id}_{user_id}",
        metadata={"takeover_id": takeover_id,
                  "note": "M5 takeover hour listen bonus"},
        enforce_caps=False)
    return {"ok": result.ok,
            "wallet_item_id": result.entry_id,
            "wallet_item_type": "takeover_bonus_bigcoin",
            "balance_after": result.balance_after}


async def _award_bonus_voucher(db, *, takeover_id: str,
                               user_id: str, amount_cents: int,
                               advertiser_business_id: str,
                               advertiser_name: str
                               ) -> Dict[str, Any]:
    now = _now()
    coupon_id = _gen("cpn_mth")
    code = (secrets.token_urlsafe(8).upper()
            .replace("_", "").replace("-", "")[:10])
    offer_id = f"ofr_mth_{takeover_id[:12]}"
    if not await db.offers.find_one({"offer_id": offer_id}):
        try:
            await db.offers.insert_one({
                "_id":            offer_id,
                "offer_id":       offer_id,
                "business_id":    advertiser_business_id,
                "title":          (f"{advertiser_name} takeover "
                                   f"listen bonus")[:100],
                "discount_percent": 0,
                "offer_type":     "dollar_off",
                "amount_cents":   int(amount_cents),
                "campaign_source": "m5_takeover_hour",
                "created_at":     now,
            })
        except Exception:
            pass
    doc = {
        "_id":               coupon_id,
        "coupon_id":         coupon_id,
        "code":              code,
        "user_id":           user_id,
        "offer_id":          offer_id,
        "status":            "saved",
        "amount_cents":      int(amount_cents),
        "source":            "m5_takeover_hour",
        "takeover_id":       takeover_id,
        "created_at":        now,
    }
    await db.coupons.insert_one(doc)
    return {"ok": True,
            "wallet_item_id": coupon_id,
            "wallet_item_type": "takeover_bonus_voucher",
            "coupon_code": code}


async def listener_ping(db, *, takeover_id: str,
                        user_id: Optional[str],
                        session_id: str,
                        station_id: Optional[str] = None,
                        ping_seconds: int = 30
                        ) -> Dict[str, Any]:
    """Accumulates listen seconds for (takeover, session).  Awards
    the bonus exactly once per (takeover, user) when
    cumulative_listen_seconds >= threshold_listen_seconds."""
    if not session_id:
        raise ValueError("session_id_required")
    t = await db.takeover_hours.find_one({"id": takeover_id})
    if not t:
        raise ValueError("takeover_not_found")
    if t["status"] != "live":
        raise ValueError(f"takeover_{t['status']}")

    now = _now()
    ping_seconds = max(1, min(int(ping_seconds), 120))

    # Upsert the session, incrementing cumulative_listen_seconds.
    upd = {
        "$setOnInsert": {
            "_id": _gen("ths"),
            "takeover_id": takeover_id,
            "session_id":  session_id,
            "station_id":  station_id,
            "listen_started_at": now,
            "bonus_awarded": False,
            "last_played_block_index": None,
        },
        "$set":    {"last_ping_at": now,
                    "user_id":       user_id},
        "$inc":    {"cumulative_listen_seconds": ping_seconds},
    }
    await db.takeover_hour_listener_sessions.update_one(
        {"takeover_id": takeover_id, "session_id": session_id},
        upd, upsert=True)
    sess = await db.takeover_hour_listener_sessions.find_one(
        {"takeover_id": takeover_id, "session_id": session_id})

    # Update actual_listeners_delivered on first ping (upsert case).
    if int(sess.get("cumulative_listen_seconds") or 0) == ping_seconds:
        await db.takeover_hours.update_one(
            {"id": takeover_id},
            {"$inc": {"actual_listeners_delivered": 1}})

    bonus = t.get("bonus_giveaway") or {}
    threshold = int(bonus.get("threshold_listen_seconds")
                    or DEFAULT_BONUS_THRESHOLD_SEC)
    result: Dict[str, Any] = {
        "takeover_id": takeover_id,
        "cumulative_listen_seconds":
            int(sess.get("cumulative_listen_seconds") or 0),
        "threshold_listen_seconds": threshold,
        "bonus_awarded":  False,
    }

    if not user_id or not bonus.get("prize_type"):
        return result

    if sess.get("bonus_awarded"):
        result["bonus_awarded"] = True
        result["bonus_award_note"] = "session_already_awarded"
        return result

    # Try to atomically mark the (takeover, user) as awarded via the
    # unique index on takeover_hour_bonus_awards.
    if result["cumulative_listen_seconds"] >= threshold:
        # Optional max_winners cap.
        max_w = int(bonus.get("max_winners") or 0)
        if max_w > 0:
            delivered = int(t.get("bonus_awards_delivered") or 0)
            if delivered >= max_w:
                result["bonus_award_note"] = "max_winners_reached"
                return result
        award_id = _gen("thba")
        award_doc = {
            "_id":                    award_id,
            "id":                     award_id,
            "takeover_id":            takeover_id,
            "user_id":                user_id,
            "session_id":             session_id,
            "listen_seconds_at_award":
                result["cumulative_listen_seconds"],
            "prize_type":             bonus["prize_type"],
            "prize_amount":           int(bonus.get("prize_amount") or 0),
            "wallet_item_id":         None,
            "wallet_item_type":       None,
            "awarded_at":             now,
        }
        try:
            await db.takeover_hour_bonus_awards.insert_one(award_doc)
        except Exception:
            # Duplicate — user already got the bonus.  Mark session
            # and return.
            await db.takeover_hour_listener_sessions.update_one(
                {"takeover_id": takeover_id, "session_id": session_id},
                {"$set": {"bonus_awarded": True}})
            result["bonus_awarded"] = True
            result["bonus_award_note"] = "already_awarded"
            return result

        # Mint the actual prize.
        try:
            if bonus["prize_type"] == "bc":
                minted = await _award_bonus_bigcoin(
                    db, takeover_id=takeover_id, user_id=user_id,
                    points=int(bonus.get("prize_amount") or 0))
            else:
                minted = await _award_bonus_voucher(
                    db, takeover_id=takeover_id, user_id=user_id,
                    amount_cents=int(bonus.get("prize_amount") or 0),
                    advertiser_business_id=t["advertiser_business_id"],
                    advertiser_name=(t.get("branded_overlay") or {})
                        .get("advertiser_name") or "BigFM sponsor")
            await db.takeover_hour_bonus_awards.update_one(
                {"id": award_id},
                {"$set": {
                    "wallet_item_id": minted.get("wallet_item_id"),
                    "wallet_item_type": minted.get("wallet_item_type"),
                }})
        except Exception as e:
            logger.exception("[m5_takeover] mint failed: %s", e)
            minted = {"wallet_item_id": None,
                      "wallet_item_type": None,
                      "error": str(e)}
        await db.takeover_hour_listener_sessions.update_one(
            {"takeover_id": takeover_id, "session_id": session_id},
            {"$set": {"bonus_awarded": True}})
        await db.takeover_hours.update_one(
            {"id": takeover_id},
            {"$inc": {"bonus_awards_delivered": 1}})

        # Dispatch notification.
        try:
            from services.notification_trigger_dispatcher import (
                dispatch_event)
            await dispatch_event(
                db, event_name="takeover_bonus_awarded",
                user_id=user_id,
                payload={
                    "takeover_id": takeover_id,
                    "advertiser_business_id":
                        t["advertiser_business_id"],
                    "prize_type":   bonus["prize_type"],
                    "prize_amount": int(bonus.get("prize_amount") or 0),
                    "wallet_item_id": minted.get("wallet_item_id"),
                })
        except Exception as e:
            logger.warning(
                "[m5_takeover] bonus dispatch failed: %s", e)

        result["bonus_awarded"] = True
        result["bonus_minted"] = {
            "wallet_item_id": minted.get("wallet_item_id"),
            "wallet_item_type": minted.get("wallet_item_type"),
            "prize_type":   bonus["prize_type"],
            "prize_amount": int(bonus.get("prize_amount") or 0),
        }
    return result


async def record_block_played(db, *, takeover_id: str,
                              session_id: str,
                              block_index: int) -> Dict[str, Any]:
    """Optional: called by player after playing a block audio so the
    next `/current` poll doesn't return the same audio."""
    await db.takeover_hour_listener_sessions.update_one(
        {"takeover_id": takeover_id, "session_id": session_id},
        {"$set": {"last_played_block_index": int(block_index)}},
        upsert=False)
    return {"ok": True, "block_index": int(block_index)}


__all__ = [
    "ensure_takeover_hour_indexes",
    "create_takeover_hour", "submit_takeover_hour",
    "confirm_payment", "list_takeover_hours",
    "get_takeover_hour", "cancel_takeover_hour",
    "admin_list", "admin_approve", "admin_reject",
    "sweep_takeover_hours",
    "find_current_takeover", "get_current_takeover_response",
    "listener_ping", "record_block_played",
    "PLATFORM_FEE_PCT", "HOUR_DURATION_SECONDS", "BLOCK_COUNT",
]
