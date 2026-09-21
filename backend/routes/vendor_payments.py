"""Vendor Payments — Stripe Connect marketplace layer.

Any vendor that charges customers (social professionals — sleep coaches, tarot
readers, astrologers — and business merchants) onboards a Stripe **Express**
connected account and accepts platform terms. Customer payments then use a
**direct charge** on the connected account with an `application_fee_amount`:
the platform keeps a percentage commission and the rest settles to the vendor.
Because it's a direct charge, the connected account is the merchant of record —
so refunds, disputes and chargebacks are the vendor's liability, not ours,
exactly as the vendor agrees to at signup.

Fee resolution (basis points): category fee (if configured) → global default
(admin-settable, 1500 = 15%).  Merchant category defaults to 500 (5%).
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from core.origins import resolve_origin

router = APIRouter(prefix="/api/vendor-payments", tags=["vendor-payments"])
admin_router = APIRouter(prefix="/api/admin", tags=["vendor-payments-admin"])

TERMS_VERSION = "1.0"
DEFAULT_FEE_BPS = 1500          # 15% fallback for everyone
MERCHANT_FEE_BPS = 500          # 5% for business merchants
FEE_CONFIG_ID = "platform_fees"

UAE_MARKETS = {"dubai", "uae", "abu_dhabi", "abudhabi", "sharjah", "ae"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


def _stripe():
    import stripe
    stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                      or os.environ.get("STRIPE_API_KEY") or "")
    return stripe


def _country_currency(market: Optional[str]) -> tuple[str, str]:
    """USD for US-based vendors, AED for UAE-based vendors."""
    if (market or "").strip().lower() in UAE_MARKETS:
        return "AE", "aed"
    return "US", "usd"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


# ───────────────────────── fee config ──────────────────────────────
async def get_fee_config(db) -> dict:
    doc = await db.platform_fee_config.find_one({"_id": FEE_CONFIG_ID})
    if not doc:
        doc = {"_id": FEE_CONFIG_ID, "default_bps": DEFAULT_FEE_BPS,
               "category_bps": {"merchant": MERCHANT_FEE_BPS}}
        await db.platform_fee_config.update_one(
            {"_id": FEE_CONFIG_ID}, {"$setOnInsert": doc}, upsert=True)
    doc.setdefault("default_bps", DEFAULT_FEE_BPS)
    doc.setdefault("category_bps", {})
    return doc


async def resolve_fee_bps(db, category: Optional[str]) -> int:
    """Category fee if configured, else the admin-settable global default."""
    cfg = await get_fee_config(db)
    cat = cfg.get("category_bps", {})
    if category and category in cat:
        return int(cat[category])
    return int(cfg.get("default_bps", DEFAULT_FEE_BPS))


# ─────────────────── vendor account resolution ─────────────────────
async def _eligible_vendor(db, user: dict, vendor_type: str) -> Optional[dict]:
    """Return {ref_id, category, market, display_name} the user may onboard as,
    or None if they aren't eligible for that vendor_type."""
    uid = user["user_id"]
    market = user.get("preferred_market")
    if vendor_type == "advisor":
        a = await db.advisor_profiles.find_one({"user_id": uid})
        if not a:
            return None
        return {"ref_id": a["advisor_id"], "category": a.get("category"),
                "market": market, "display_name": a.get("display_name")}
    if vendor_type == "merchant":
        b = await db.businesses.find_one(
            {"$or": [{"owner_user_id": uid}, {"owner_user_ids": uid}]})
        if not b:
            return None
        bid = b.get("business_id") or str(b.get("_id"))
        return {"ref_id": bid, "category": "merchant",
                "market": b.get("market") or market, "display_name": b.get("name")}
    return None


async def _eligibility(db, user: dict) -> list[str]:
    out = []
    if await _eligible_vendor(db, user, "advisor"):
        out.append("advisor")
    if await _eligible_vendor(db, user, "merchant"):
        out.append("merchant")
    return out


async def get_vendor_account(db, vendor_type: str, ref_id: str) -> Optional[dict]:
    return await db.vendor_accounts.find_one(
        {"vendor_type": vendor_type, "ref_id": ref_id})


def vendor_ready(va: Optional[dict]) -> bool:
    return bool(va and va.get("charges_enabled"))


async def _sync_from_stripe(db, va: dict) -> dict:
    """Refresh charges/payouts flags from Stripe."""
    stripe = _stripe()
    if not stripe.api_key or not va.get("stripe_account_id"):
        return va
    try:
        acct = stripe.Account.retrieve(va["stripe_account_id"])
    except Exception:
        return va
    charges = bool(acct.get("charges_enabled"))
    payouts = bool(acct.get("payouts_enabled"))
    submitted = bool(acct.get("details_submitted"))
    status = "complete" if (charges and submitted) else ("pending" if submitted else "not_started")
    await db.vendor_accounts.update_one(
        {"_id": va["_id"]},
        {"$set": {"charges_enabled": charges, "payouts_enabled": payouts,
                  "details_submitted": submitted, "onboarding_status": status,
                  "updated_at": _now()}})
    va.update({"charges_enabled": charges, "payouts_enabled": payouts,
               "details_submitted": submitted, "onboarding_status": status})
    return va


def _va_public(va: dict) -> dict:
    return {"vendor_account_id": va["_id"], "vendor_type": va.get("vendor_type"),
            "ref_id": va.get("ref_id"), "category": va.get("category"),
            "display_name": va.get("display_name"),
            "currency": va.get("currency"), "country": va.get("country"),
            "fee_bps": va.get("fee_bps"),
            "fee_pct": round(int(va.get("fee_bps", 0)) / 100, 2),
            "onboarding_status": va.get("onboarding_status", "not_started"),
            "charges_enabled": bool(va.get("charges_enabled")),
            "payouts_enabled": bool(va.get("payouts_enabled")),
            "details_submitted": bool(va.get("details_submitted")),
            "agreement": {
                "accepted": bool((va.get("agreement") or {}).get("accepted")),
                "version": (va.get("agreement") or {}).get("version"),
                "accepted_at": _iso((va.get("agreement") or {}).get("accepted_at")),
                "fee_bps_at_accept": (va.get("agreement") or {}).get("fee_bps_at_accept"),
            }}


# ───────────────────── checkout split helper ───────────────────────
async def connect_checkout_options(db, vendor_type: str, ref_id: str,
                                    amount_cents: int) -> Optional[dict]:
    """If the vendor is onboarded, return the Stripe Checkout Session extras for
    a DIRECT charge with a platform application fee. Returns None when the vendor
    hasn't completed payout onboarding (caller decides whether to gate or fall
    back to a plain platform charge)."""
    va = await get_vendor_account(db, vendor_type, ref_id)
    if not vendor_ready(va):
        return None
    fee_bps = int(va.get("fee_bps") or await resolve_fee_bps(db, va.get("category")))
    fee_amount = round(amount_cents * fee_bps / 10000)
    return {
        "stripe_account": va["stripe_account_id"],      # request option → direct charge
        "application_fee_amount": fee_amount,
        "currency": va.get("currency", "usd"),
        "fee_bps": fee_bps,
        "connected_account_id": va["stripe_account_id"],
    }


async def require_payout_onboarding(db) -> bool:
    cfg = await get_fee_config(db)
    return bool(cfg.get("require_payout_onboarding"))


# ───────────────────────── vendor endpoints ────────────────────────
class OnboardBody(BaseModel):
    vendor_type: str                       # advisor | merchant
    agreement_accepted: bool = False
    origin_url: Optional[str] = None
    return_path: str = "/payouts"


AGREEMENT_TEMPLATE = (
    "I agree to pay a {pct}% platform fee on each transaction, and I accept that "
    "I am solely and personally responsible for any chargebacks, refunds, or "
    "disputes. FUUSIC is not liable for chargebacks."
)


@router.get("/status")
async def connect_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    eligible = await _eligibility(db, user)
    accounts = []
    for vt in eligible:
        va = await db.vendor_accounts.find_one(
            {"owner_user_id": user["user_id"], "vendor_type": vt})
        if va:
            va = await _sync_from_stripe(db, va)
            accounts.append(_va_public(va))
        else:
            ev = await _eligible_vendor(db, user, vt)
            fee_bps = await resolve_fee_bps(db, ev.get("category"))
            _country, currency = _country_currency(ev.get("market"))
            accounts.append({"vendor_type": vt, "ref_id": ev["ref_id"],
                             "category": ev.get("category"),
                             "display_name": ev.get("display_name"),
                             "currency": currency, "fee_bps": fee_bps,
                             "fee_pct": round(fee_bps / 100, 2),
                             "onboarding_status": "not_started",
                             "charges_enabled": False, "payouts_enabled": False,
                             "details_submitted": False,
                             "agreement": {"accepted": False, "version": TERMS_VERSION}})
    return {"eligible": eligible, "accounts": accounts, "terms_version": TERMS_VERSION,
            "agreement_template": AGREEMENT_TEMPLATE}


@router.post("/onboard")
async def connect_onboard(body: OnboardBody, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    if body.vendor_type not in ("advisor", "merchant"):
        raise HTTPException(400, {"code": "bad_vendor_type"})
    ev = await _eligible_vendor(db, user, body.vendor_type)
    if not ev:
        raise HTTPException(403, {"code": "not_eligible",
                                  "detail": f"You have no {body.vendor_type} profile."})
    stripe = _stripe()
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})

    fee_bps = await resolve_fee_bps(db, ev.get("category"))
    country, currency = _country_currency(ev.get("market"))
    va = await db.vendor_accounts.find_one(
        {"owner_user_id": user["user_id"], "vendor_type": body.vendor_type})

    if not va:
        if not body.agreement_accepted:
            raise HTTPException(400, {"code": "agreement_required"})
        acct = stripe.Account.create(
            type="express", country=country, email=user.get("email") or None,
            capabilities={"card_payments": {"requested": True},
                          "transfers": {"requested": True}},
            metadata={"platform": "fuusic", "vendor_type": body.vendor_type,
                      "ref_id": ev["ref_id"], "owner_user_id": user["user_id"]})
        vid = f"va_{uuid.uuid4().hex[:16]}"
        va = {
            "_id": vid, "owner_user_id": user["user_id"],
            "vendor_type": body.vendor_type, "ref_id": ev["ref_id"],
            "category": ev.get("category"), "display_name": ev.get("display_name"),
            "country": country, "currency": currency, "fee_bps": fee_bps,
            "stripe_account_id": acct.id,
            "charges_enabled": False, "payouts_enabled": False,
            "details_submitted": False, "onboarding_status": "pending",
            "agreement": {
                "accepted": True, "version": TERMS_VERSION,
                "fee_bps_at_accept": fee_bps,
                "text": AGREEMENT_TEMPLATE.format(pct=round(fee_bps / 100, 2)),
                "accepted_at": _now(), "ip": _client_ip(request),
                "user_agent": request.headers.get("user-agent", "")[:300]},
            "created_at": _now(), "updated_at": _now()}
        await db.vendor_accounts.insert_one(dict(va))

    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    link = stripe.AccountLink.create(
        account=va["stripe_account_id"],
        refresh_url=f"{origin}{body.return_path}?connect=refresh",
        return_url=f"{origin}{body.return_path}?connect=done",
        type="account_onboarding")
    return {"ok": True, "vendor_account_id": va["_id"],
            "onboarding_url": link.url, "fee_pct": round(fee_bps / 100, 2),
            "currency": currency}


@router.post("/onboarding-link")
async def connect_refresh_link(body: OnboardBody, request: Request,
                               user: dict = Depends(current_user)):
    """Fresh AccountLink to resume onboarding (no new account, no re-consent)."""
    db = request.app.state.db
    va = await db.vendor_accounts.find_one(
        {"owner_user_id": user["user_id"], "vendor_type": body.vendor_type})
    if not va:
        raise HTTPException(404, {"code": "no_account"})
    stripe = _stripe()
    origin = resolve_origin(request, body.origin_url)
    link = stripe.AccountLink.create(
        account=va["stripe_account_id"],
        refresh_url=f"{origin}{body.return_path}?connect=refresh",
        return_url=f"{origin}{body.return_path}?connect=done",
        type="account_onboarding")
    return {"ok": True, "onboarding_url": link.url}


# ───────────────────────── admin endpoints ─────────────────────────
class FeeConfigBody(BaseModel):
    default_bps: int = Field(..., ge=0, le=5000)
    category_bps: dict = Field(default_factory=dict)
    require_payout_onboarding: bool = False


@admin_router.get("/platform-fees")
async def admin_get_fees(request: Request, _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    cfg = await get_fee_config(db)
    return {"default_bps": cfg.get("default_bps", DEFAULT_FEE_BPS),
            "default_pct": round(cfg.get("default_bps", DEFAULT_FEE_BPS) / 100, 2),
            "category_bps": cfg.get("category_bps", {}),
            "require_payout_onboarding": bool(cfg.get("require_payout_onboarding"))}


@admin_router.put("/platform-fees")
async def admin_set_fees(body: FeeConfigBody, request: Request,
                         _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    clean = {k: int(v) for k, v in (body.category_bps or {}).items()
             if isinstance(v, (int, float)) and 0 <= int(v) <= 5000}
    await db.platform_fee_config.update_one(
        {"_id": FEE_CONFIG_ID},
        {"$set": {"default_bps": int(body.default_bps), "category_bps": clean,
                  "require_payout_onboarding": bool(body.require_payout_onboarding),
                  "updated_at": _now()}}, upsert=True)
    return {"ok": True, "default_bps": int(body.default_bps), "category_bps": clean,
            "require_payout_onboarding": bool(body.require_payout_onboarding)}


@admin_router.get("/vendor-accounts")
async def admin_list_vendors(request: Request, _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    items = [_va_public(v) async for v in
             db.vendor_accounts.find().sort("created_at", -1).limit(200)]
    return {"items": items, "count": len(items)}


async def ensure_vendor_payment_indexes(db):
    await db.vendor_accounts.create_index(
        [("owner_user_id", 1), ("vendor_type", 1)], unique=True, name="va_owner_type")
    await db.vendor_accounts.create_index(
        [("vendor_type", 1), ("ref_id", 1)], name="va_type_ref")
    await get_fee_config(db)


__all__ = ["router", "admin_router", "ensure_vendor_payment_indexes",
           "resolve_fee_bps", "get_vendor_account", "vendor_ready",
           "connect_checkout_options", "require_payout_onboarding",
           "get_fee_config", "TERMS_VERSION"]
