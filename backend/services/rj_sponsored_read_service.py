"""Phase I — M1 Sponsored AI-RJ Reads.

Advertisers buy short, scripted host reads that get injected between
songs in the AI-RJ segment stream on specific stations.  The read is
voiced by an existing Phase D persona's ElevenLabs voice (persona's
`voice_id`), which is why the disclosure phrase MUST be baked into
the script text itself — the persona voices it naturally, which
matches real radio and avoids audio-stitching.

Reuses:
    * Phase D  persona catalog          (`rj_personas` + persona.voice_id)
    * Phase D  persona preview pipeline (script→TTS→Tigris)
    * ADMOD.1  litellm.amoderation      (creative moderation gate)
    * Phase G  Stripe prepay + refund   (identical pattern to AD.5/AD.9)
    * Phase G  payment_transactions_v2  (audit trail row)

Money model:
    total_cost_cents  = plays_target * cost_per_play_cents
    platform_fee_cents = 30% of total_cost_cents
    stripe_charge      = total_cost_cents + platform_fee_cents
    advertiser_admin_approval required when charge ≥ $500 (50000¢).

Idempotency:
    plays are deduped per (sponsored_read_id, user_id, dedup_bucket=hour)
    via a compound unique index on `rj_sponsored_read_plays`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.m1_rj_sponsored_reads")

PLATFORM_FEE_PCT                  = 30
MIN_COST_PER_PLAY_CENTS      = 5
MIN_PLAYS_TARGET                    = 10
ADMIN_APPROVAL_THRESHOLD    = 50_000       # $500
DEDUP_BUCKET_HOURS                = 1
DISCLOSURE_PREFIXES = ("Paid sponsorship", "Sponsored by", "Presented by")

_STATUSES = {"draft", "pending_moderation", "pending_admin",
                        "active", "paused", "completed",
                        "cancelled", "rejected"}


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


def _hour_bucket(ts: Optional[datetime] = None) -> str:
    """`dedup_bucket` is a UTC hourly string.  We do a 1-hour dedup
    window per (sponsored_read, user) so a listener glued to one
    station can't rack up impressions."""
    ts = ts or _now()
    return ts.strftime("%Y-%m-%dT%H")


async def ensure_rj_sponsored_read_indexes(db) -> None:
    try:
        await db.rj_sponsored_reads.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="rjsr_adv_status")
        await db.rj_sponsored_reads.create_index(
            [("status", 1), ("station_ids", 1)],
            name="rjsr_status_station")
        await db.rj_sponsored_reads.create_index(
            [("status", 1), ("cost_per_play_cents", -1)],
            name="rjsr_status_price_desc")
        await db.rj_sponsored_read_plays.create_index(
            [("sponsored_read_id", 1),
              ("user_id", 1),
              ("dedup_bucket", 1)],
            unique=True, sparse=False,
            name="rjsrp_dedup_uniq")
        await db.rj_sponsored_read_plays.create_index(
            [("sponsored_read_id", 1), ("played_at", -1)],
            name="rjsrp_read_recent")
    except Exception as e:
        logger.warning("[m1_rjsr] index setup: %s", e)


# ── Cost math ─────────────────────────────────────────────────────
def _compute_costs(plays_target: int,
                                      cost_per_play_cents: int) -> Dict[str, int]:
    if plays_target < MIN_PLAYS_TARGET:
        raise ValueError("plays_target_below_min")
    if cost_per_play_cents < MIN_COST_PER_PLAY_CENTS:
        raise ValueError("cost_per_play_below_min")
    prize_cost = int(plays_target) * int(cost_per_play_cents)
    fee = (prize_cost * PLATFORM_FEE_PCT) // 100
    return {
        "prize_cost_cents":    prize_cost,
        "platform_fee_cents": int(fee),
        "total_cost_cents":    prize_cost + int(fee),
    }


# ── Shape helpers ─────────────────────────────────────────────────
def _shape(s: Dict[str, Any]) -> Dict[str, Any]:
    if not s:
        return {}
    return {
        "sponsored_read_id":              s.get("id"),
        "advertiser_business_id":      s.get("advertiser_business_id"),
        "persona_id":                            s.get("persona_id"),
        "persona_name":                        s.get("persona_name"),
        "station_ids":                        list(s.get("station_ids") or []),
        "any_station":                        bool(s.get("any_station")),
        "script_body":                        s.get("script_body"),
        "final_script":                      s.get("final_script"),
        "disclosure_prefix":              s.get("disclosure_prefix"),
        "audio_url":                            s.get("audio_url"),
        "duration_seconds":                s.get("duration_seconds"),
        "plays_target":                      int(s.get("plays_target") or 0),
        "plays_delivered":                int(s.get("plays_delivered") or 0),
        "cost_per_play_cents":          int(s.get("cost_per_play_cents") or 0),
        "prize_cost_cents":                int(s.get("prize_cost_cents") or 0),
        "platform_fee_cents":            int(s.get("platform_fee_cents") or 0),
        "total_cost_cents":                int(s.get("total_cost_cents") or 0),
        "remaining_budget_cents":      int(s.get("remaining_budget_cents") or 0),
        "status":                                s.get("status"),
        "moderation_result":                s.get("moderation_result"),
        "admin_notes":                        s.get("admin_notes"),
        "cancel_reason":                    s.get("cancel_reason"),
        "stripe_payment_intent_id":  s.get("stripe_payment_intent_id"),
        "stripe_refund_id":                s.get("stripe_refund_id"),
        "stripe_prepayment_transaction_id":
                    s.get("stripe_prepayment_transaction_id"),
        "refunded_amount_cents":        int(s.get("refunded_amount_cents") or 0),
        "start_at":                            _iso(s.get("start_at")),
        "end_at":                                _iso(s.get("end_at")),
        "created_at":                        _iso(s.get("created_at")),
        "submitted_at":                      _iso(s.get("submitted_at")),
        "activated_at":                      _iso(s.get("activated_at")),
        "completed_at":                      _iso(s.get("completed_at")),
        "cancelled_at":                      _iso(s.get("cancelled_at")),
        "rendered_at":                        _iso(s.get("rendered_at")),
    }


# ── Stripe (test-mode) ────────────────────────────────────────────
async def _charge_prepayment(*, amount_cents: int, sponsored_read_id: str,
                                                          advertiser_business_id: str
                                                          ) -> Dict[str, Any]:
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
                "bigfm_flow":                          "m1_rj_sponsored_read_prepay",
                "bigfm_sponsored_read_id":  sponsored_read_id,
                "bigfm_advertiser_id":          advertiser_business_id,
            },
            idempotency_key=f"m1_rjsr_prepay_{sponsored_read_id}")
        return {"payment_intent_id": intent.id,
                        "amount_cents":        int(amount_cents),
                        "status":                  intent.status}
    except Exception as e:
        logger.exception("[m1_rjsr] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund(*, payment_intent_id: str, refund_cents: int,
                              sponsored_read_id: str) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        r = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "m1_rjsr_refund",
                                "bigfm_sponsored_read_id": sponsored_read_id},
            idempotency_key=f"m1_rjsr_refund_{sponsored_read_id}")
        return {"refund_id": r.id,
                        "amount_cents": int(refund_cents),
                        "status": r.status}
    except Exception as e:
        logger.exception("[m1_rjsr] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


# ── Script draft (auto) + disclosure enforcement ─────────────────
def _script_has_disclosure(script: str, prefix: str) -> bool:
    """Enforce the mandatory disclosure phrase in the FIRST SENTENCE of
    the final script.  Prefix must appear in the first ~20 words."""
    if not script:
        return False
    first = re.split(r"(?<=[.!?])\s+", script.strip(), maxsplit=1)[0]
    first_words = " ".join(first.split()[:20]).lower()
    return prefix.strip().lower() in first_words


async def _llm_draft_script(*, persona: Dict[str, Any],
                                                        spec: Dict[str, Any],
                                                        disclosure_prefix: str) -> str:
    """Auto-draft a sponsored read script using the persona's voice +
    the advertiser's product spec (`product_name`, `key_message`,
    `cta`).  The disclosure phrase is REQUIRED in the first sentence.
    Falls back to a deterministic template if the LLM key is missing.
    """
    product = (spec.get("product_name") or "").strip() or "the sponsor"
    key_message = (spec.get("key_message") or "").strip()
    cta = (spec.get("cta") or "").strip()

    fallback = (
        f"{disclosure_prefix} from {product}. "
        f"{key_message or f'Check out {product} today.'} "
        f"{cta or 'You are listening to RadioLife.'}")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return fallback

    system = (
        f"You are drafting a 15-second radio sponsorship read voiced by "
        f"'{persona.get('name') or 'a RadioLife host'}'.  Persona style: "
        f"{persona.get('persona_prompt') or 'upbeat, conversational'}. "
        f"The FIRST SENTENCE MUST begin with '{disclosure_prefix}'. "
        "Keep total spoken length 12-18 seconds (35-55 words).  Do not "
        "use emoji.  Do not add stage directions.  End with a natural "
        "call-to-action.")
    user = (
        f"Product / advertiser: {product}.\n"
        f"Key message: {key_message or '—'}.\n"
        f"Call-to-action: {cta or '—'}.\n"
        f"Language: {persona.get('language') or 'en'}.\n"
        f"Write the read now, starting with '{disclosure_prefix}'.")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (LlmChat(api_key=api_key,
                                        session_id=f"m1_rjsr_{_gen('draft')[:8]}",
                                        system_message=system)
                        .with_model("openai", "gpt-4o-mini"))
        resp = await chat.send_message(UserMessage(text=user))
        text = (resp or "").strip()
        # Salvage: if the model forgot the disclosure, prepend it.
        if not _script_has_disclosure(text, disclosure_prefix):
            text = f"{disclosure_prefix} from {product}. {text}"
        return text[:600]
    except Exception as e:
        logger.warning("[m1_rjsr] LLM draft failed: %s — using fallback", e)
        return fallback


# ── TTS render ────────────────────────────────────────────────────
async def _tts_render_upload(*, persona: Dict[str, Any],
                                                          final_script: str) -> Dict[str, Any]:
    """Reuses Phase D's synth + Tigris upload primitives from
    `rj_persona_service`.  Runs the blocking synth call in a thread
    so we don't block the event loop."""
    from services.rj_persona_service import (
        _synthesize_audio, _upload_to_storage, _gen as _persona_gen)
    from services.object_storage import key_rj
    provider = persona.get("voice_provider") or "elevenlabs"

    def _blocking():
        local_path = _synthesize_audio(
            script=final_script,
            voice_id=persona["voice_id"],
            voice_provider=provider,
            language=persona.get("language") or "en",
            personality=persona.get("personality") or "energetic")
        # Duration best-effort.
        duration = None
        try:
            import subprocess
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(local_path)],
                stderr=subprocess.STDOUT, timeout=8)
            duration = float(out.decode().strip())
        except Exception:
            pass
        # Upload — reuse the same key_rj() namespace (already Tigris in prod).
        seg_id = _persona_gen("rjsr")
        key = key_rj(seg_id)
        audio_url = _upload_to_storage(local_path, key)
        # Best-effort cleanup of local temp when storage is remote.
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


# ── CRUD ──────────────────────────────────────────────────────────
async def create_sponsored_read(db, *,
                                                                  advertiser_business_id: str,
                                                                  body: Dict[str, Any],
                                                                  user_id: str) -> Dict[str, Any]:
    persona_id = (body.get("persona_id") or "").strip()
    if not persona_id:
        raise ValueError("persona_id_required")
    persona = await db.rj_personas.find_one({"id": persona_id})
    if not persona:
        raise ValueError("persona_not_found")
    if persona.get("status") != "active":
        raise ValueError("persona_not_active")

    station_ids = list(body.get("station_ids") or [])
    any_station = bool(body.get("any_station"))
    if not any_station and not station_ids:
        raise ValueError("station_targeting_required")

    prefix = (body.get("disclosure_prefix") or "").strip()
    if prefix not in DISCLOSURE_PREFIXES:
        raise ValueError("invalid_disclosure_prefix")

    plays_target = int(body.get("plays_target") or 0)
    cost_per_play = int(body.get("cost_per_play_cents") or 0)
    costs = _compute_costs(plays_target, cost_per_play)

    start = _aware(body.get("start_at")) or _now()
    end   = _aware(body.get("end_at"))
    if not end or end <= start:
        raise ValueError("invalid_time_window")

    # Auto-draft when the caller passes literal string "auto"; else
    # store the advertiser draft as-is (moderation runs on submit).
    raw = (body.get("script_body") or "").strip()
    if raw.lower() == "auto":
        raw = await _llm_draft_script(
            persona=persona,
            spec={"product_name":  body.get("product_name"),
                        "key_message":  body.get("key_message"),
                        "cta":                  body.get("cta")},
            disclosure_prefix=prefix)

    sr_id = _gen("rjsr")
    doc = {
        "_id":                                              sr_id,
        "id":                                                sr_id,
        "advertiser_business_id":              advertiser_business_id,
        "persona_id":                                  persona_id,
        "persona_name":                              persona.get("name"),
        "station_ids":                                station_ids,
        "any_station":                                any_station,
        "script_body":                                raw,
        "final_script":                              None,
        "disclosure_prefix":                      prefix,
        "audio_url":                                    None,
        "duration_seconds":                        None,
        "plays_target":                              plays_target,
        "plays_delivered":                        0,
        "cost_per_play_cents":                  cost_per_play,
        "prize_cost_cents":                        costs["prize_cost_cents"],
        "platform_fee_cents":                    costs["platform_fee_cents"],
        "total_cost_cents":                        costs["total_cost_cents"],
        "remaining_budget_cents":              costs["prize_cost_cents"],
        "status":                                        "draft",
        "moderation_result":                        None,
        "admin_notes":                                None,
        "start_at":                                    start,
        "end_at":                                        end,
        "created_at":                                _now(),
        "created_by_user_id":                    user_id,
        "admin_approval_required":            costs["total_cost_cents"] >= ADMIN_APPROVAL_THRESHOLD,
    }
    await db.rj_sponsored_reads.insert_one(doc)
    return _shape(doc)


async def submit_sponsored_read(db, *, sponsored_read_id: str,
                                                                  advertiser_business_id: str,
                                                                  final_script: str) -> Dict[str, Any]:
    """Advertiser finalises the copy.  Enforces disclosure in the first
    sentence, runs ADMOD.1 moderation, and either flags for admin OR
    leaves as `pending_moderation`  awaiting Stripe prepay
    (`confirm-payment`)."""
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] != "draft":
        raise ValueError(f"sponsored_read_{s['status']}")

    txt = (final_script or "").strip()
    if len(txt) < 20:
        raise ValueError("final_script_too_short")
    if not _script_has_disclosure(txt, s["disclosure_prefix"]):
        raise ValueError("disclosure_missing_in_first_sentence")

    from services.ad_moderation_service import moderate_creative_text
    mod = await moderate_creative_text([txt])

    if mod.get("flagged") or mod.get("action_taken") == "flagged":
        upd = {
            "final_script":            txt,
            "moderation_result":  mod,
            "status":                    "rejected",
            "cancel_reason":        "moderation_flagged",
            "rejected_at":            _now(),
        }
        await db.rj_sponsored_reads.update_one(
            {"id": sponsored_read_id}, {"$set": upd})
        row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
        return _shape(row)

    upd = {
        "final_script":            txt,
        "moderation_result":  mod,
        "status":                    "pending_moderation",
        "submitted_at":          _now(),
    }
    await db.rj_sponsored_reads.update_one(
        {"id": sponsored_read_id}, {"$set": upd})
    row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    return _shape(row)


async def confirm_payment(db, *, sponsored_read_id: str,
                                                    advertiser_business_id: str) -> Dict[str, Any]:
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] != "pending_moderation":
        raise ValueError(f"sponsored_read_{s['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(s["total_cost_cents"]),
        sponsored_read_id=sponsored_read_id,
        advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_rjsr")
    await db.payment_transactions_v2.insert_one({
        "_id":                                        tx_id,
        "transaction_id":                    tx_id,
        "stripe_payment_intent_id":  charge["payment_intent_id"],
        "flow":                                      "m1_rj_sponsored_read_prepay",
        "event_source":                        "rj_sponsored_read_prepay",
        "advertiser_id":                      advertiser_business_id,
        "bigfm_sponsored_read_id":    sponsored_read_id,
        "amount_cents":                        int(s["total_cost_cents"]),
        "application_fee_cents":        int(s["platform_fee_cents"]),
        "merchant_net_cents":              0,
        "currency":                                "usd",
        "status":                                    "posted",
        "created_at":                            _now(),
    })

    # TTS-render the final script now — this is what actually costs
    # ElevenLabs credits so we do it AFTER prepay clears.
    persona = await db.rj_personas.find_one({"id": s["persona_id"]})
    if not persona:
        raise ValueError("persona_gone_missing")

    try:
        tts = await _tts_render_upload(
            persona=persona, final_script=s["final_script"])
    except Exception as e:
        # Refund the just-charged prepay and mark rejected so the
        # advertiser is not billed for a failed render.
        try:
            r = await _refund(payment_intent_id=charge["payment_intent_id"],
                                              refund_cents=int(s["total_cost_cents"]),
                                              sponsored_read_id=sponsored_read_id)
            await db.rj_sponsored_reads.update_one(
                {"id": sponsored_read_id},
                {"$set": {"status": "rejected",
                                    "cancel_reason": "tts_render_failed",
                                    "stripe_refund_id": r["refund_id"],
                                    "refunded_amount_cents": r["amount_cents"],
                                    "rejected_at": _now()}})
        except Exception:
            pass
        raise ValueError(f"tts_render_failed:{e}")

    new_status = ("pending_admin"
                                if s.get("admin_approval_required")
                                else "active")
    now = _now()
    upd = {
        "status":                                          new_status,
        "audio_url":                                    tts["audio_url"],
        "storage_key":                                tts.get("storage_key"),
        "duration_seconds":                        tts.get("duration_seconds"),
        "voice_provider_used":                  tts.get("voice_provider"),
        "stripe_payment_intent_id":          charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at":                                        now,
        "rendered_at":                                now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    await db.rj_sponsored_reads.update_one(
        {"id": sponsored_read_id}, {"$set": upd})

    row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})

    # Auto-approval → dispatch the notification recipe.
    if new_status == "active":
        try:
            from services.notification_trigger_dispatcher import dispatch_event
            await dispatch_event(
                db, event_name="rj_sponsored_read_approved",
                user_id=s.get("created_by_user_id"),
                payload={"sponsored_read_id":  sponsored_read_id,
                                "advertiser_business_id": advertiser_business_id,
                                "auto_approved":  True})
        except Exception as e:
            logger.warning("[m1_rjsr] dispatch_event failed: %s", e)

    return {"sponsored_read": _shape(row),
                    "charge": charge,
                    "transaction_id": tx_id}


async def list_reads(db, *, advertiser_business_id: Optional[str] = None,
                                    status: Optional[str] = None,
                                    limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.rj_sponsored_reads.find(q).sort(
                                                        "created_at", -1).limit(limit):
        rows.append(_shape(d))
    return rows


async def get_read(db, *, sponsored_read_id: str,
                                  advertiser_business_id: Optional[str] = None
                                  ) -> Optional[Dict[str, Any]]:
    d = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not d:
        return None
    if advertiser_business_id and \
            d["advertiser_business_id"] != advertiser_business_id:
        return None
    return _shape(d)


async def cancel_read(db, *, sponsored_read_id: str,
                                          advertiser_business_id: str,
                                          reason: str = "advertiser_cancelled"
                                          ) -> Dict[str, Any]:
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] not in ("pending_moderation", "pending_admin",
                                                  "active", "paused"):
        raise ValueError(f"sponsored_read_{s['status']}")

    remaining = int(s.get("remaining_budget_cents") or 0)
    # Proportional fee refund on unspent budget.
    fee_pct = PLATFORM_FEE_PCT
    unspent_fee = (remaining * fee_pct) // 100
    refund_cents = remaining + unspent_fee
    refund: Optional[Dict[str, Any]] = None
    if s.get("stripe_payment_intent_id") and refund_cents > 0:
        refund = await _refund(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=refund_cents,
            sponsored_read_id=sponsored_read_id)
    upd = {
        "status":                          "cancelled",
        "cancel_reason":            reason,
        "cancelled_at":              _now(),
    }
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.rj_sponsored_reads.update_one(
        {"id": sponsored_read_id}, {"$set": upd})
    row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    return {"sponsored_read": _shape(row),
                    "refund": refund}


# ── Admin ─────────────────────────────────────────────────────────
async def admin_list(db, *, status: Optional[str] = None,
                                          limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.rj_sponsored_reads.find(q).sort(
                                                        "created_at", -1).limit(limit):
        rows.append(_shape(d))
    return rows


async def admin_approve(db, *, sponsored_read_id: str,
                                                admin_user_id: str,
                                                admin_notes: Optional[str] = None
                                                ) -> Dict[str, Any]:
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["status"] != "pending_admin":
        raise ValueError(f"sponsored_read_{s['status']}")
    now = _now()
    await db.rj_sponsored_reads.update_one(
        {"id": sponsored_read_id},
        {"$set": {"status":            "active",
                          "activated_at":  now,
                          "decided_by_user_id": admin_user_id,
                          "decided_at":    now,
                          "admin_notes":  (admin_notes or "").strip() or None}})
    row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})

    try:
        from services.notification_trigger_dispatcher import dispatch_event
        await dispatch_event(
            db, event_name="rj_sponsored_read_approved",
            user_id=s.get("created_by_user_id"),
            payload={"sponsored_read_id":  sponsored_read_id,
                            "advertiser_business_id": s["advertiser_business_id"],
                            "auto_approved":  False})
    except Exception as e:
        logger.warning("[m1_rjsr] dispatch_event failed: %s", e)
    return _shape(row)


async def admin_reject(db, *, sponsored_read_id: str,
                                            admin_user_id: str,
                                            admin_notes: str
                                            ) -> Dict[str, Any]:
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["status"] not in ("pending_admin", "pending_moderation"):
        raise ValueError(f"sponsored_read_{s['status']}")
    refund: Optional[Dict[str, Any]] = None
    if s.get("stripe_payment_intent_id") and \
            int(s.get("total_cost_cents") or 0) > 0:
        refund = await _refund(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=int(s["total_cost_cents"]),
            sponsored_read_id=sponsored_read_id)
    upd = {
        "status":                          "cancelled",
        "cancel_reason":            "admin_rejected",
        "admin_notes":                (admin_notes or "").strip() or None,
        "decided_by_user_id":  admin_user_id,
        "decided_at":                _now(),
        "cancelled_at":              _now(),
    }
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.rj_sponsored_reads.update_one(
        {"id": sponsored_read_id}, {"$set": upd})
    row = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    return {"sponsored_read": _shape(row),
                    "refund": refund}


# ── Listener selection + play impression ──────────────────────────
async def select_next_sponsored(db, *, station_id: str,
                                                                user_id: Optional[str]
                                                                ) -> Optional[Dict[str, Any]]:
    """Pick 0 or 1 sponsored read to inject on this station for this
    user right now.  Selection order:
        1. status == "active"
        2. station_ids contains this station_id  OR  any_station == True
        3. remaining_budget_cents  >= cost_per_play_cents
        4. now within [start_at, end_at]
        5. NOT already played for (read, user, hour-bucket)
        6. highest cost_per_play_cents first  (revenue-max)
    """
    now = _now()
    q: Dict[str, Any] = {
        "status": "active",
        "$or": [
            {"any_station": True},
            {"station_ids": station_id},
        ],
        "start_at": {"$lte": now},
        "end_at":    {"$gte": now},
        "$expr": {
            "$gte": ["$remaining_budget_cents",
                              "$cost_per_play_cents"],
        },
    }
    bucket = _hour_bucket(now)
    cur = db.rj_sponsored_reads.find(q).sort(
                    "cost_per_play_cents", -1).limit(20)
    async for s in cur:
        if user_id:
            already = await db.rj_sponsored_read_plays.find_one({
                "sponsored_read_id":  s["id"],
                "user_id":                    user_id,
                "dedup_bucket":            bucket})
            if already:
                continue
        if not s.get("audio_url"):
            continue
        # Resolve advertiser display name for the disclosure chip.
        adv_name = None
        try:
            adv = await db.advertisers.find_one(
                {"advertiser_id": s["advertiser_business_id"]},
                {"business_name": 1, "display_name": 1, "name": 1})
            if adv:
                adv_name = (adv.get("business_name") or adv.get("display_name")
                                        or adv.get("name"))
        except Exception:
            pass
        return {
            "sponsored_read_id":  s["id"],
            "audio_url":                s["audio_url"],
            "duration_seconds":  s.get("duration_seconds"),
            "disclosure_chip":    f"{s['disclosure_prefix']} · "
                                                    f"{adv_name or s.get('persona_name') or 'RadioLife sponsor'}",
            "persona_id":              s.get("persona_id"),
            "voice_id_hint":        None,          # persona knows it
            "advertiser_business_id": s["advertiser_business_id"],
            "cost_per_play_cents":  int(s["cost_per_play_cents"]),
        }
    return None


async def record_play(db, *, sponsored_read_id: str,
                                          station_id: str,
                                          user_id: Optional[str]) -> Dict[str, Any]:
    """Idempotent play impression.  Atomically decrements the budget
    and increments plays_delivered.  Returns:
        - `{"deduped": True}` if the (read, user, hour) combo already fired.
        - `{"charged": True, "remaining_budget_cents": ...}` otherwise.
    Auto-flips sponsorship to `completed` when budget drops below one
    more play's cost.
    """
    s = await db.rj_sponsored_reads.find_one({"id": sponsored_read_id})
    if not s:
        raise ValueError("sponsored_read_not_found")
    if s["status"] != "active":
        return {"deduped": True, "reason": s["status"]}
    bucket = _hour_bucket()
    play_id = _gen("rjsrp")
    try:
        await db.rj_sponsored_read_plays.insert_one({
            "_id":                          play_id,
            "id":                            play_id,
            "sponsored_read_id":  sponsored_read_id,
            "station_id":              station_id,
            "user_id":                    user_id or "anon",
            "dedup_bucket":          bucket,
            "played_at":                _now(),
        })
    except Exception:
        # Duplicate-key means we already counted this listener in this
        # hour bucket — treat as a no-op.
        return {"deduped": True}

    cost = int(s.get("cost_per_play_cents") or 0)
    # Atomic budget guard + counter increment.
    r = await db.rj_sponsored_reads.find_one_and_update(
        {"id": sponsored_read_id,
          "remaining_budget_cents": {"$gte": cost}},
        {"$inc":    {"remaining_budget_cents": -cost,
                              "plays_delivered": 1},
          "$set":    {"last_played_at": _now()}},
        return_document=True)
    if not r:
        # Budget insufficient — flip to completed.
        await db.rj_sponsored_reads.update_one(
            {"id": sponsored_read_id, "status": "active"},
            {"$set": {"status": "completed",
                              "completed_at": _now()}})
        return {"deduped": False,
                        "budget_exhausted": True,
                        "remaining_budget_cents": 0}
    remaining = int(r.get("remaining_budget_cents") or 0)
    if remaining < cost:
        await db.rj_sponsored_reads.update_one(
            {"id": sponsored_read_id, "status": "active"},
            {"$set": {"status": "completed",
                              "completed_at": _now()}})
    return {"deduped": False,
                    "charged": True,
                    "remaining_budget_cents": remaining,
                    "plays_delivered": int(r.get("plays_delivered") or 0)}


__all__ = [
    "ensure_rj_sponsored_read_indexes",
    "create_sponsored_read", "submit_sponsored_read",
    "confirm_payment", "list_reads", "get_read", "cancel_read",
    "admin_list", "admin_approve", "admin_reject",
    "select_next_sponsored", "record_play",
    "DISCLOSURE_PREFIXES", "PLATFORM_FEE_PCT",
    "MIN_COST_PER_PLAY_CENTS", "MIN_PLAYS_TARGET",
    "ADMIN_APPROVAL_THRESHOLD",
]
