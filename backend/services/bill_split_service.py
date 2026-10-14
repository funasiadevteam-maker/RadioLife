"""Phase E — AD.7.1 Split-the-bill service.

Composes the AD.7 Stripe primitives to split a single merchant bill
across 2-8 payers, each of whom pays their own share on their own
payment method.  The merchant ends up receiving the exact same total
(minus the same aggregate application fee) as if a single payer had
tapped the QR.

Key mechanics:

1.  Split creation NEVER touches Stripe — it just persists the
      `bill_splits` doc + `bill_split_shares` rows with opaque invite
      tokens.  30-min expiry from creation.
2.  Claim = auth'd user attaches themselves to a share (writes user_id).
      Idempotent for the same user; 409 if another user already claimed.
3.  Pay = the claiming user creates a Stripe PaymentIntent for THEIR
      share amount only.  The application_fee_amount is prorated across
      shares (last-paid share absorbs rounding).  Each paid share writes
      a row to `scan_to_pay_transactions` with `flow="ad7_split_share"`
      so merchant reconciliation stays uniform.
4.  When every share is paid, the parent split flips to `completed`
      and the `bill_split_share_paid` trigger fires with
      `completed: true` on the LAST share's payment.

Expiration is checked at read (share reads bump expired rows on the
fly) AND swept hourly from the AD.12 boot loop.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from services.points_service import PointsService
from services.commission_service import calculate_platform_fee
from services.currency_util import currency_for_business

logger = logging.getLogger("bigfm.bill_split")

MAX_SHARES = 8
MIN_SHARES = 2
DEFAULT_MIN_SHARE_CENTS = 100
SPLIT_TTL_MINUTES = 30
INVITE_TOKEN_LEN = 32

STATUS_ACTIVE_SPLIT = {"pending", "partial"}
STATUS_ACTIVE_SHARE = {"invited", "claimed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    """Coerce a datetime to UTC-aware.  Mongo can return naive datetimes
    depending on the codec settings; comparing those against
    `datetime.now(timezone.utc)` throws `TypeError`."""
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _gen_token() -> str:
    # urlsafe, 32 chars, 192 bits of entropy.
    return secrets.token_urlsafe(24)[:INVITE_TOKEN_LEN]


async def ensure_bill_split_indexes(db) -> None:
    try:
        await db.bill_splits.create_index("initiator_user_id",
                                                                              name="bs_initiator")
        await db.bill_splits.create_index([("status", 1), ("created_at", -1)],
                                                                              name="bs_status_recent")
        await db.bill_splits.create_index("expires_at", sparse=True,
                                                                              name="bs_expiry")
        await db.bill_split_shares.create_index("invite_token",
                                                                                          unique=True,
                                                                                          name="bss_token_uniq")
        await db.bill_split_shares.create_index(
            [("split_id", 1), ("status", 1)], name="bss_split_status")
        await db.bill_split_shares.create_index(
            [("user_id", 1), ("status", 1)], sparse=True,
            name="bss_user_status")
    except Exception as e:
        logger.warning("[bill_split] index setup: %s", e)


# ── Serialisation helpers ──────────────────────────────────────
def _shape_share_public(s: Dict[str, Any],
                                                include_token: bool = False,
                                                include_user_id: bool = True) -> Dict[str, Any]:
    """Public shape — never leaks other users' payment_intent_id or
    Stripe internals.  `invite_token` only present when the caller
    holds it.  `user_id` is stripped when the caller is unauth'd (or
    reading via a public-token path) so anonymous invite holders can't
    identify who claimed a share."""
    out = {
        "share_id":                    s.get("id"),
        "split_id":                    s.get("split_id"),
        "share_amount_cents":  int(s.get("share_amount_cents") or 0),
        "status":                        s.get("status"),
        "display_name":            s.get("display_name"),
        "claimed_at":              _iso(s.get("claimed_at")),
        "paid_at":                    _iso(s.get("paid_at")),
    }
    if include_user_id:
        out["user_id"] = s.get("user_id")
    if include_token:
        out["invite_token"] = s.get("invite_token")
    return out


def _shape_split(sp: Dict[str, Any], shares: List[Dict[str, Any]],
                                *, viewer_user_id: Optional[str] = None,
                                include_all_tokens: bool = False,
                                merchant_summary: Optional[Dict[str, Any]] = None
                                ) -> Dict[str, Any]:
    frontend_base = _frontend_base()
    invite_urls: Dict[str, str] = {}
    shaped_shares: List[Dict[str, Any]] = []
    for s in shares:
        # Show the invite token to (a) the initiator, or (b) callers
        # asking with a token, or (c) the claimant of that share.
        show_tok = (include_all_tokens
                              or (viewer_user_id and viewer_user_id
                                    == sp.get("initiator_user_id"))
                              or (viewer_user_id and viewer_user_id
                                    == s.get("user_id")))
        row = _shape_share_public(s, include_token=bool(show_tok))
        shaped_shares.append(row)
        if show_tok:
            invite_urls[s["id"]] = f"{frontend_base}/split/{s['invite_token']}"
    out = {
        "split_id":                        sp.get("id"),
        "initiator_user_id":      sp.get("initiator_user_id"),
        "merchant_id":                sp.get("merchant_id"),
        "location_id":                sp.get("location_id"),
        "total_amount_cents":    int(sp.get("total_amount_cents") or 0),
        "currency":                      sp.get("currency"),
        "description":                sp.get("description"),
        "status":                          sp.get("status"),
        "qr_token":                      sp.get("qr_token"),
        "created_at":                  _iso(sp.get("created_at")),
        "expires_at":                  _iso(sp.get("expires_at")),
        "completed_at":              _iso(sp.get("completed_at")),
        "cancel_reason":            sp.get("cancel_reason"),
        "application_fee_cents": int(sp.get("stripe_application_fee_cents") or 0),
        "shares":                          shaped_shares,
        "invite_urls":                invite_urls,
    }
    if merchant_summary:
        out["merchant"] = merchant_summary
    return out


def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _frontend_base() -> str:
    return (os.environ.get("FRONTEND_URL")
                    or os.environ.get("REACT_APP_BACKEND_URL")
                    or "https://app.bigfm.dev").rstrip("/")


async def _merchant_summary(db, merchant_id: str) -> Optional[Dict[str, Any]]:
    biz = await db.businesses.find_one({"business_id": merchant_id},
                                                                              {"business_id": 1,
                                                                                "business_name": 1,
                                                                                "name": 1,
                                                                                "category_id": 1,
                                                                                "category": 1,
                                                                                "logo_url": 1,
                                                                                "currency": 1,
                                                                                "country": 1,
                                                                                "city": 1,
                                                                                "market": 1})
    if not biz:
        return None
    return {
        "merchant_id":      biz.get("business_id"),
        "business_name":  biz.get("business_name") or biz.get("name"),
        "logo_url":          biz.get("logo_url"),
        "category":          biz.get("category_id") or biz.get("category"),
        "currency":          currency_for_business(biz),
    }


# ── expiration ─────────────────────────────────────────────────
async def _expire_if_due(db, split_doc: Dict[str, Any]) -> Dict[str, Any]:
    """If the split is expired and still active with unpaid shares,
    flip the status + expire the still-active shares in place.  Returns
    the refreshed split doc."""
    if not split_doc:
        return split_doc
    exp = _aware(split_doc.get("expires_at"))
    if isinstance(exp, datetime) and exp <= _now() \
            and split_doc.get("status") in STATUS_ACTIVE_SPLIT:
        now = _now()
        await db.bill_split_shares.update_many(
            {"split_id": split_doc["id"],
              "status": {"$in": list(STATUS_ACTIVE_SHARE)}},
            {"$set": {"status": "expired", "expired_at": now}})
        new_status = "expired"
        # If any share was already paid, keep as "partial" instead —
        # the paid share is real money.
        n_paid = await db.bill_split_shares.count_documents(
            {"split_id": split_doc["id"], "status": "paid"})
        if n_paid > 0:
            new_status = "partial"
        await db.bill_splits.update_one(
            {"id": split_doc["id"]},
            {"$set": {"status": new_status, "expired_at": now}})
        split_doc["status"] = new_status
        split_doc["expired_at"] = now
    return split_doc


async def sweep_expired_splits(db) -> Dict[str, Any]:
    """Hourly cron entry point — flips expired active splits."""
    now = _now()
    scanned = 0
    updated = 0
    async for sp in db.bill_splits.find(
                {"status": {"$in": list(STATUS_ACTIVE_SPLIT)},
                  "expires_at": {"$lte": now}}).limit(500):
        scanned += 1
        before_status = sp.get("status")
        sp2 = await _expire_if_due(db, sp)
        if sp2.get("status") != before_status:
            updated += 1
    return {"scanned": scanned, "updated": updated,
                    "ran_at": now.isoformat()}


# ── CREATE ─────────────────────────────────────────────────────
async def create_split(db, *, initiator_user_id: str, body: Dict[str, Any]
                                              ) -> Dict[str, Any]:
    merchant_id = (body.get("merchant_id") or "").strip()
    if not merchant_id:
        raise ValueError("merchant_id_required")
    total = int(body.get("total_amount_cents") or 0)
    if total <= 0:
        raise ValueError("invalid_total")
    shares_in = body.get("shares") or []
    if not isinstance(shares_in, list) \
            or not (MIN_SHARES <= len(shares_in) <= MAX_SHARES):
        raise ValueError("invalid_share_count")

    biz = await db.businesses.find_one({"business_id": merchant_id})
    if not biz:
        raise ValueError("merchant_not_found")
    scan = biz.get("scan_to_pay") or {}
    min_share = int(scan.get("min_share_cents") or DEFAULT_MIN_SHARE_CENTS)

    shares_norm: List[Dict[str, Any]] = []
    running = 0
    for i, s in enumerate(shares_in):
        amt = int(s.get("share_amount_cents") or 0)
        if amt <= 0:
            raise ValueError("share_amount_zero")
        if amt < min_share:
            raise ValueError("share_below_min")
        shares_norm.append({
            "share_amount_cents": amt,
            "display_name": (s.get("display_name") or f"Guest {i+1}").strip()[:80],
        })
        running += amt
    if running != total:
        raise ValueError("shares_sum_mismatch")

    now = _now()
    expires_at = now + timedelta(minutes=SPLIT_TTL_MINUTES)
    split_id = _gen("bsplit")
    currency = (body.get("currency")
                              or currency_for_business(biz)).lower()

    # Precompute the intended aggregate application fee — the same
    # commission the merchant would owe on a single-payer flow.
    commission = await calculate_platform_fee(
        db, merchant_id=merchant_id,
        category=biz.get("category_id") or biz.get("category") or "other",
        transaction_type="scan_to_pay",
        amount_cents=total, write_audit=False)
    total_app_fee = int(commission["commission_cents"])

    split_doc = {
        "_id":                                              split_id,
        "id":                                                split_id,
        "initiator_user_id":                    initiator_user_id,
        "merchant_id":                              merchant_id,
        "location_id":                              (body.get("location_id")
                                                                    or scan.get("location_id")),
        "total_amount_cents":                  total,
        "currency":                                    currency,
        "description":                              (body.get("description")
                                                                    or "").strip()[:200] or None,
        "qr_token":                                    body.get("qr_token"),
        "status":                                        "pending",
        "created_at":                                now,
        "expires_at":                                expires_at,
        "completed_at":                            None,
        "expired_at":                                None,
        "cancel_reason":                          None,
        "stripe_application_fee_cents": total_app_fee,
        "fee_applied_cents":                    0,
    }
    await db.bill_splits.insert_one(split_doc)

    share_docs: List[Dict[str, Any]] = []
    for s in shares_norm:
        sid = _gen("bsshr")
        share_docs.append({
            "_id":                                sid,
            "id":                                  sid,
            "split_id":                      split_id,
            "user_id":                        None,
            "invite_token":              _gen_token(),
            "share_amount_cents":  s["share_amount_cents"],
            "status":                          "invited",
            "display_name":              s["display_name"],
            "claimed_at":                  None,
            "paid_at":                        None,
            "expired_at":                  None,
            "payment_intent_id":      None,
            "payment_transaction_id": None,
            "share_fee_cents":          0,     # filled at pay time
            "created_at":                  now,
        })
    if share_docs:
        await db.bill_split_shares.insert_many(share_docs)

    # Fire per-share `bill_split_invited` trigger — the initiator's own
    # share ISN'T notified (they don't need a nudge for themselves).
    try:
        import asyncio as _aio
        from services.notification_trigger_dispatcher import dispatch_event
        for s in share_docs:
            _aio.create_task(dispatch_event(
                db, event_name="bill_split_invited",
                user_id=None,
                payload={"split_id":            split_id,
                                  "share_id":            s["id"],
                                  "invite_token":  s["invite_token"],
                                  "merchant_id":      merchant_id,
                                  "share_amount_cents": s["share_amount_cents"],
                                  "total_amount_cents": total,
                                  "expires_at":      _iso(expires_at)}))
    except Exception as _e:
        logger.warning("[bill_split] invite dispatch failed: %s", _e)

    merchant_summary = await _merchant_summary(db, merchant_id)
    return _shape_split(split_doc, share_docs,
                                              viewer_user_id=initiator_user_id,
                                              merchant_summary=merchant_summary)


# ── READ ───────────────────────────────────────────────────────
async def get_split(db, *, split_id: str,
                                      viewer_user_id: Optional[str] = None
                                      ) -> Optional[Dict[str, Any]]:
    sp = await db.bill_splits.find_one({"id": split_id})
    if not sp:
        return None
    sp = await _expire_if_due(db, sp)
    # Access gate: initiator OR any claimed share holder.
    if viewer_user_id and viewer_user_id != sp.get("initiator_user_id"):
        n = await db.bill_split_shares.count_documents(
            {"split_id": split_id, "user_id": viewer_user_id})
        if n == 0:
            return {"forbidden": True}
    shares = [s async for s in
                        db.bill_split_shares.find({"split_id": split_id})
                        .sort("created_at", 1)]
    ms = await _merchant_summary(db, sp.get("merchant_id"))
    return _shape_split(sp, shares, viewer_user_id=viewer_user_id,
                                              merchant_summary=ms)


async def get_by_token(db, *, invite_token: str) -> Optional[Dict[str, Any]]:
    share = await db.bill_split_shares.find_one(
        {"invite_token": invite_token})
    if not share:
        return None
    sp = await db.bill_splits.find_one({"id": share["split_id"]})
    if not sp:
        return None
    sp = await _expire_if_due(db, sp)
    # Refresh share state after expiration sweep.
    share = await db.bill_split_shares.find_one(
        {"invite_token": invite_token})
    ms = await _merchant_summary(db, sp.get("merchant_id"))
    # Return the target share (with token) + a redacted list of other
    # shares (display_name + status only — no user_id / tokens).
    all_shares = [s async for s in
                                db.bill_split_shares.find({"split_id": sp["id"]})
                                .sort("created_at", 1)]
    others = []
    for s in all_shares:
        if s["id"] == share["id"]:
            continue
        others.append({
            "share_id":                    s["id"],
            "share_amount_cents":  int(s.get("share_amount_cents") or 0),
            "status":                        s.get("status"),
            "display_name":            s.get("display_name"),
        })
    return {
        "split": {
            "split_id":                      sp["id"],
            "merchant_id":                sp.get("merchant_id"),
            "total_amount_cents":    int(sp.get("total_amount_cents") or 0),
            "currency":                      sp.get("currency"),
            "description":                sp.get("description"),
            "status":                          sp.get("status"),
            "created_at":                  _iso(sp.get("created_at")),
            "expires_at":                  _iso(sp.get("expires_at")),
            "completed_at":              _iso(sp.get("completed_at")),
        },
        "share":              _shape_share_public(share, include_token=True,
                                                                                          include_user_id=False),
        "other_shares": others,
        "merchant":        ms,
    }


async def list_mine(db, *, user_id: str, status: Optional[str] = None,
                                      limit: int = 50) -> List[Dict[str, Any]]:
    """My splits — either as initiator OR as a claimant.  Newest first."""
    # 1) Initiator side.
    q_init: Dict[str, Any] = {"initiator_user_id": user_id}
    if status:
        q_init["status"] = status
    ids_init = set()
    async for sp in db.bill_splits.find(q_init).sort("created_at", -1) \
                                                                                .limit(limit):
        ids_init.add(sp["id"])
    # 2) Claimant side (any share belonging to me).
    ids_claim = set()
    async for sh in db.bill_split_shares.find({"user_id": user_id}) \
                                                                              .sort("created_at", -1).limit(limit):
        ids_claim.add(sh["split_id"])
    all_ids = ids_init | ids_claim
    if not all_ids:
        return []
    q2: Dict[str, Any] = {"id": {"$in": list(all_ids)}}
    if status:
        q2["status"] = status
    out: List[Dict[str, Any]] = []
    async for sp in db.bill_splits.find(q2).sort("created_at", -1) \
                                                                                .limit(limit):
        sp = await _expire_if_due(db, sp)
        shares = [s async for s in
                            db.bill_split_shares.find({"split_id": sp["id"]})
                            .sort("created_at", 1)]
        ms = await _merchant_summary(db, sp.get("merchant_id"))
        row = _shape_split(sp, shares, viewer_user_id=user_id,
                                                merchant_summary=ms)
        row["role"] = ("initiator"
                                        if sp.get("initiator_user_id") == user_id
                                        else "participant")
        out.append(row)
    return out


# ── CLAIM ──────────────────────────────────────────────────────
async def claim_share(db, *, invite_token: str, user_id: str
                                              ) -> Dict[str, Any]:
    share = await db.bill_split_shares.find_one(
        {"invite_token": invite_token})
    if not share:
        raise ValueError("share_not_found")
    sp = await db.bill_splits.find_one({"id": share["split_id"]})
    if not sp:
        raise ValueError("split_not_found")
    sp = await _expire_if_due(db, sp)
    if sp.get("status") in ("expired", "cancelled"):
        raise ValueError(f"split_{sp['status']}")
    if share.get("status") in ("paid", "expired", "cancelled"):
        raise ValueError(f"share_{share['status']}")
    # Idempotent for the same user.
    if share.get("user_id") == user_id:
        return {"ok": True, "already_claimed": True,
                        "share": _shape_share_public(share, include_token=True)}
    if share.get("user_id") and share["user_id"] != user_id:
        # Different user already holds this token.
        raise ValueError("share_taken")
    now = _now()
    await db.bill_split_shares.update_one(
        {"id": share["id"], "user_id": None},
        {"$set": {"user_id": user_id, "status": "claimed",
                          "claimed_at": now}})
    share = await db.bill_split_shares.find_one({"id": share["id"]})
    return {"ok": True, "already_claimed": False,
                    "share": _shape_share_public(share, include_token=True)}


# ── PAY ────────────────────────────────────────────────────────
async def _remaining_fee_for_share(db, sp: Dict[str, Any],
                                                                            share: Dict[str, Any]) -> int:
    """Prorate: `share_fee = round(total_fee * share_amount / total_amount)`.
    LAST-PAID share absorbs rounding — so if this share's payment would
    close the split, return whatever fee remains."""
    total_fee = int(sp.get("stripe_application_fee_cents") or 0)
    total = int(sp.get("total_amount_cents") or 0)
    share_amt = int(share.get("share_amount_cents") or 0)
    if total <= 0 or total_fee <= 0:
        return 0
    # Count still-unpaid shares (excluding this one).
    other_unpaid = await db.bill_split_shares.count_documents(
        {"split_id": sp["id"],
          "id": {"$ne": share["id"]},
          "status": {"$in": ["invited", "claimed"]}})
    if other_unpaid == 0:
        # This is the last unpaid share — absorb remainder.
        already_applied = int(sp.get("fee_applied_cents") or 0)
        return max(0, total_fee - already_applied)
    # Standard prorate.
    return int(round(total_fee * share_amt / total))


async def pay_share(db, *, share_id: str, user_id: str,
                                          payment_method_id: Optional[str] = None
                                          ) -> Dict[str, Any]:
    share = await db.bill_split_shares.find_one({"id": share_id})
    if not share:
        raise ValueError("share_not_found")
    if share.get("user_id") != user_id:
        raise ValueError("not_share_owner")
    if share.get("status") == "paid":
        # Idempotent — return the existing tx info.
        return {"ok": True, "already_paid": True,
                        "transaction_id": share.get("payment_transaction_id")}
    if share.get("status") in ("expired", "cancelled"):
        raise ValueError(f"share_{share['status']}")

    sp = await db.bill_splits.find_one({"id": share["split_id"]})
    sp = await _expire_if_due(db, sp)
    if sp.get("status") in ("expired", "cancelled"):
        raise ValueError(f"split_{sp['status']}")

    merchant_id = sp["merchant_id"]
    biz = await db.businesses.find_one({"business_id": merchant_id})
    stripe_acct = biz.get("stripe_account_id") if biz else None
    if not stripe_acct or not (biz or {}).get("stripe_charges_enabled"):
        raise ValueError("merchant_stripe_missing")

    share_fee = await _remaining_fee_for_share(db, sp, share)
    share_amt = int(share["share_amount_cents"])
    tx_id = _gen("stx")
    now = _now()

    intent_id = None
    client_secret = None
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=share_amt,
            currency=(sp.get("currency") or "aed").lower(),
            automatic_payment_methods={
                "enabled": True, "allow_redirects": "never"},
            on_behalf_of=stripe_acct,
            transfer_data={"destination": stripe_acct},
            application_fee_amount=share_fee,
            payment_method=payment_method_id,
            confirm=bool(payment_method_id),
            capture_method="automatic",
            metadata={
                "bigfm_flow":                    "ad7_split_share",
                "bigfm_split_id":            sp["id"],
                "bigfm_share_id":            share_id,
                "bigfm_merchant_id":      merchant_id,
                "bigfm_customer_user_id": user_id,
                "bigfm_scan_to_pay_id": tx_id,
            },
            idempotency_key=f"bsplitshare_{share_id}")
        intent_id      = intent.id
        client_secret = intent.client_secret
    except Exception as e:
        logger.exception("[bill_split] Stripe intent create failed")
        raise ValueError(f"stripe_error:{e}")

    # Write a scan_to_pay_transactions row so merchant reports stay
    # uniform.  We tag it flow="ad7_split_share".
    doc = {
        "_id":                                            tx_id,
        "transaction_id":                        tx_id,
        "flow":                                          "ad7_split_share",
        "user_id":                                      user_id,
        "merchant_id":                            merchant_id,
        "location_id":                            sp.get("location_id"),
        "cashier_user_id":                    None,
        "subtotal_cents":                        share_amt,
        "tip_cents":                                0,
        "tax_cents":                                0,
        "total_cents":                            share_amt,
        "points_redeemed":                    0,
        "points_value_cents":              0,
        "points_lock_entry_id":          None,
        "card_charged_cents":              share_amt,
        "points_earned_awarded":          0,
        "points_earn_entry_id":          None,
        "stripe_payment_intent_id":  intent_id,
        "stripe_connected_account_id": stripe_acct,
        "application_fee_cents":          int(share_fee),
        "merchant_net_cents":              max(0, share_amt - int(share_fee)),
        "status":                                      ("authorized"
                                                                    if intent_id else "pending"),
        "qr_token":                                  sp.get("qr_token"),
        "created_at":                              now,
        "authorized_at":                        now,
        "captured_at":                            None,
        "refunded_at":                            None,
        "bill_split_id":                        sp["id"],
        "bill_split_share_id":            share_id,
        "settings_snapshot":                {},
    }
    await db.scan_to_pay_transactions.insert_one(doc)

    # Mark the share paid + link to the transaction.
    await db.bill_split_shares.update_one(
        {"id": share_id},
        {"$set": {"status": "paid", "paid_at": now,
                          "payment_intent_id": intent_id,
                          "payment_transaction_id": tx_id,
                          "share_fee_cents": int(share_fee)}})

    # Update parent split.  Bump fee_applied_cents + flip status.
    n_paid = await db.bill_split_shares.count_documents(
        {"split_id": sp["id"], "status": "paid"})
    n_total = await db.bill_split_shares.count_documents(
        {"split_id": sp["id"]})
    completed_now = (n_paid >= n_total)
    updates = {"$inc": {"fee_applied_cents": int(share_fee)},
                          "$set": {"status": ("completed"
                                                                        if completed_now else "partial")}}
    if completed_now:
        updates["$set"]["completed_at"] = now
    await db.bill_splits.update_one({"id": sp["id"]}, updates)

    # Dispatch trigger: bill_split_share_paid to initiator + payer.
    try:
        import asyncio as _aio
        from services.notification_trigger_dispatcher import dispatch_event
        payload = {
            "split_id":                    sp["id"],
            "share_id":                    share_id,
            "merchant_id":            merchant_id,
            "share_amount_cents": share_amt,
            "total_amount_cents": int(sp.get("total_amount_cents") or 0),
            "completed":                completed_now,
            "shares_paid":            n_paid,
            "shares_total":          n_total,
        }
        # Payer notification (private receipt).
        _aio.create_task(dispatch_event(
            db, event_name="bill_split_share_paid",
            user_id=user_id, payload={**payload, "role": "payer"}))
        # Initiator notification (per share + on completion).
        if sp.get("initiator_user_id") \
                and sp["initiator_user_id"] != user_id:
            _aio.create_task(dispatch_event(
                db, event_name="bill_split_share_paid",
                user_id=sp["initiator_user_id"],
                payload={**payload, "role": "initiator"}))
    except Exception as _e:
        logger.warning("[bill_split] paid dispatch failed: %s", _e)

    return {
        "ok":                              True,
        "transaction_id":        tx_id,
        "client_secret":        client_secret,
        "requires_action":  bool(client_secret) and not payment_method_id,
        "application_fee_cents":  int(share_fee),
        "merchant_net_cents":        max(0, share_amt - int(share_fee)),
        "completed":                completed_now,
    }


# ── CANCEL ─────────────────────────────────────────────────────
async def cancel_split(db, *, split_id: str, initiator_user_id: str,
                                                reason: Optional[str] = None
                                                ) -> Dict[str, Any]:
    sp = await db.bill_splits.find_one({"id": split_id})
    if not sp:
        raise ValueError("split_not_found")
    if sp.get("initiator_user_id") != initiator_user_id:
        raise ValueError("initiator_only")
    if sp.get("status") in ("completed", "cancelled", "expired"):
        raise ValueError(f"split_{sp['status']}")
    n_paid = await db.bill_split_shares.count_documents(
        {"split_id": split_id, "status": "paid"})
    if n_paid > 0:
        raise ValueError("has_paid_shares")
    now = _now()
    await db.bill_split_shares.update_many(
        {"split_id": split_id,
          "status": {"$in": list(STATUS_ACTIVE_SHARE)}},
        {"$set": {"status": "cancelled", "cancelled_at": now}})
    await db.bill_splits.update_one(
        {"id": split_id},
        {"$set": {"status": "cancelled", "completed_at": now,
                          "cancel_reason": (reason or "initiator_cancelled")}})
    return {"ok": True, "status": "cancelled"}


__all__ = [
    "ensure_bill_split_indexes", "sweep_expired_splits",
    "create_split", "get_split", "get_by_token",
    "list_mine", "claim_share", "pay_share", "cancel_split",
    "MAX_SHARES", "MIN_SHARES",
]
