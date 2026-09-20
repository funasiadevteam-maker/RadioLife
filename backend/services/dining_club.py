"""FUUSIC Premium Dining Club — core engine (Phase 1 backend).

A 30-day, Premium-only restaurant meal membership. The customer picks how many
meals/week (3-14) and only Veg / Non-Veg; FUUSIC randomly assigns the
restaurant via an EQUAL-PROBABILITY wheel (server decides the winner, one
optional reroll). Each redeemed meal is a fixed $9.99.

Reuses existing infra — does NOT rebuild:
  • Premium              → services.premium_gate.is_premium_or_trial / billing_service.grant_premium
  • BigPoints            → services.bigcoin.award
  • Payments             → emergentintegrations Stripe checkout (same as routes/billing.py)
  • Secure RNG           → secrets.SystemRandom (same primitive as games_v2 spin)

Fairness contract (LOCKED): once the final candidate set of N (≤10) restaurants
is chosen, EVERY restaurant has identical probability. No sponsored/bid/spend
weighting ever touches the winner draw.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from services import bigcoin

logger = logging.getLogger("bigfm.dining")

# ── Program defaults (all admin-configurable via dining_programs) ──────
PROGRAM_ID = "default"
DEFAULTS = {
    "program_id": PROGRAM_ID,
    "meal_price_cents": 999,          # fixed $9.99 per redeemed meal
    "access_fee_cents": 0,            # 30-day Dining Club access fee (Premium => $0)
    "platform_fee_cents": 100,        # kept by platform per redeemed meal (restaurant net = meal - fee)
    "min_meals_week": 3,
    "max_meals_week": 14,
    "term_days": 30,
    "grants_per_term": 4,             # 4 weekly grants inside a 30-day term
    "grant_interval_days": 7,
    "credit_ttl_days": 30,            # each credit expires 30 days from ITS issuance
    "reroll_limit": 1,                # one optional reroll per selection session
    "candidate_size": 10,
    "min_viable_restaurants": 1,
    "max_radius_miles": 5.0,
    "session_ttl_minutes": 30,
    "abandon_cooldown_minutes": 10,   # anti-reroll-abuse: wait before a new session
    "meal_periods": ["LUNCH", "DINNER"],
    "premium_required": True,
    "premium_plan_id": "premium_annual",
    "qr_ttl_minutes": 240,
}

# Default per-location coordinate (used when the customer shares no location).
DEFAULT_MARKET = {"market": "dubai", "lat": 25.2048, "lng": 55.2708}

CREDIT_STATUSES = {"AVAILABLE", "RESERVED", "REDEEMED", "RELEASED",
                   "EXPIRED", "REFUNDED", "LOCKED_PREMIUM_REQUIRED"}


# ── small helpers ──────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> Any:
    if isinstance(dt, datetime):
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()
    return dt


def _aware(dt: Any) -> Optional[datetime]:
    if not isinstance(dt, datetime):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(9)}"


def _day(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%d")


def _haversine_miles(lat1, lng1, lat2, lng2) -> float:
    try:
        r = 3958.8
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dl = math.radians(lng2 - lng1)
        a = (math.sin(dphi / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
        return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception:
        return 0.0


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        out[k] = _iso(v) if isinstance(v, datetime) else v
    return out


# ── indexes / bootstrap ────────────────────────────────────────────────
async def ensure_dining_indexes(db) -> None:
    await db.dining_meal_credits.create_index(
        [("customer_id", 1), ("status", 1), ("expires_at", 1)],
        name="dining_credit_fifo")
    await db.dining_subscriptions.create_index(
        [("customer_id", 1), ("status", 1)], name="dining_sub_customer")
    await db.dining_subscriptions.create_index(
        [("status", 1), ("next_grant_at", 1)], name="dining_sub_grant_due")
    await db.dining_locations.create_index(
        [("status", 1), ("market", 1)], name="dining_loc_market")
    await db.dining_capacity.create_index(
        [("location_id", 1), ("date", 1), ("key", 1)],
        unique=True, name="dining_capacity_slot")
    await db.dining_selection_sessions.create_index(
        [("customer_id", 1), ("status", 1)], name="dining_session_customer")
    await db.dining_redemptions.create_index(
        [("qr_token", 1)], unique=True, name="dining_redemption_qr")
    await get_program(db)  # materialise config + qr secret
    logger.info("Dining Club indexes ready")


# ── program config ─────────────────────────────────────────────────────
async def get_program(db) -> dict:
    p = await db.dining_programs.find_one({"program_id": PROGRAM_ID})
    if not p:
        p = dict(DEFAULTS)
        p["qr_secret"] = secrets.token_urlsafe(32)
        p["created_at"] = _now()
        p["updated_at"] = _now()
        await db.dining_programs.insert_one(dict(p))
    else:
        changed = False
        for k, v in DEFAULTS.items():
            if k not in p:
                p[k] = v
                changed = True
        if "qr_secret" not in p:
            p["qr_secret"] = secrets.token_urlsafe(32)
            changed = True
        if changed:
            await db.dining_programs.update_one(
                {"program_id": PROGRAM_ID}, {"$set": p})
    return p


async def patch_program(db, patch: dict) -> dict:
    allowed = set(DEFAULTS.keys())
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    if clean:
        clean["updated_at"] = _now()
        await db.dining_programs.update_one(
            {"program_id": PROGRAM_ID}, {"$set": clean}, upsert=True)
    return await get_program(db)


def public_program(p: dict) -> dict:
    """Program view without the QR signing secret."""
    return {k: v for k, v in _clean(p).items() if k != "qr_secret"}


# ── meal-credit ledger (per-credit expiry + FIFO) ──────────────────────
async def _lock_or_unlock_for_premium(db, customer_id: str, is_premium: bool) -> None:
    """Carried-forward credits require active Premium (spec §47)."""
    if is_premium:
        await db.dining_meal_credits.update_many(
            {"customer_id": customer_id, "status": "LOCKED_PREMIUM_REQUIRED",
             "expires_at": {"$gt": _now()}},
            {"$set": {"status": "AVAILABLE"}})
    else:
        await db.dining_meal_credits.update_many(
            {"customer_id": customer_id, "status": "AVAILABLE"},
            {"$set": {"status": "LOCKED_PREMIUM_REQUIRED"}})


async def expire_credits(db, customer_id: Optional[str] = None) -> int:
    q = {"status": {"$in": ["AVAILABLE", "LOCKED_PREMIUM_REQUIRED"]},
         "expires_at": {"$lte": _now()}}
    if customer_id:
        q["customer_id"] = customer_id
    r = await db.dining_meal_credits.update_many(q, {"$set": {"status": "EXPIRED"}})
    return r.modified_count


async def credit_summary(db, customer_id: str, is_premium: bool) -> dict:
    await expire_credits(db, customer_id)
    await _lock_or_unlock_for_premium(db, customer_id, is_premium)
    now = _now()
    soon = now + timedelta(days=4)
    available = await db.dining_meal_credits.count_documents(
        {"customer_id": customer_id, "status": "AVAILABLE", "expires_at": {"$gt": now}})
    expiring = await db.dining_meal_credits.count_documents(
        {"customer_id": customer_id, "status": "AVAILABLE",
         "expires_at": {"$gt": now, "$lte": soon}})
    locked = await db.dining_meal_credits.count_documents(
        {"customer_id": customer_id, "status": "LOCKED_PREMIUM_REQUIRED"})
    reserved = await db.dining_meal_credits.count_documents(
        {"customer_id": customer_id, "status": "RESERVED"})
    return {"available": available, "expiring_soon": expiring,
            "locked": locked, "reserved": reserved}


async def list_credits(db, customer_id: str, limit: int = 100) -> list[dict]:
    rows = await db.dining_meal_credits.find(
        {"customer_id": customer_id}).sort("issued_at", -1).limit(limit).to_list(limit)
    return [_clean(r) for r in rows]


async def _reserve_oldest_credit(db, customer_id: str, session_id: str) -> Optional[dict]:
    """FIFO: reserve the AVAILABLE credit that expires soonest (atomic)."""
    now = _now()
    doc = await db.dining_meal_credits.find_one_and_update(
        {"customer_id": customer_id, "status": "AVAILABLE",
         "expires_at": {"$gt": now}},
        {"$set": {"status": "RESERVED", "reserved_session_id": session_id,
                  "reserved_at": now}},
        sort=[("expires_at", 1)], return_document=True)
    return doc


async def _release_credit(db, credit_id: str) -> None:
    await db.dining_meal_credits.update_one(
        {"credit_id": credit_id, "status": "RESERVED"},
        {"$set": {"status": "AVAILABLE"},
         "$unset": {"reserved_session_id": "", "reserved_at": ""}})


# ── subscription + weekly grants ───────────────────────────────────────
async def get_subscription(db, customer_id: str) -> Optional[dict]:
    return await db.dining_subscriptions.find_one(
        {"customer_id": customer_id, "status": {"$in": ["active", "expired"]}},
        sort=[("created_at", -1)])


async def _issue_grant(db, sub: dict, program: dict) -> dict:
    now = _now()
    qty = int(sub["meals_per_week"])
    ttl = int(program["credit_ttl_days"])
    grant_id = _gen("dgrant")
    credit_ids = []
    docs = []
    for _ in range(qty):
        cid = _gen("dcred")
        credit_ids.append(cid)
        docs.append({
            "credit_id": cid, "grant_id": grant_id,
            "subscription_id": sub["subscription_id"], "customer_id": sub["customer_id"],
            "issued_at": now, "expires_at": now + timedelta(days=ttl),
            "status": "AVAILABLE", "reserved_session_id": None})
    if docs:
        await db.dining_meal_credits.insert_many(docs)
    await db.dining_weekly_grants.insert_one({
        "grant_id": grant_id, "subscription_id": sub["subscription_id"],
        "customer_id": sub["customer_id"], "issued_at": now,
        "quantity": qty, "credit_ids": credit_ids})
    return {"grant_id": grant_id, "quantity": qty, "credit_ids": credit_ids}


async def create_subscription(db, *, customer_id: str, meals_per_week: int,
                              veg_default: str, program: dict,
                              stripe_session_id: Optional[str] = None) -> dict:
    """Activate a 30-day membership and issue the FIRST weekly grant now."""
    now = _now()
    term = int(program["term_days"])
    interval = int(program["grant_interval_days"])
    sub = {
        "subscription_id": _gen("dsub"), "customer_id": customer_id,
        "status": "active", "meals_per_week": int(meals_per_week),
        "veg_default": veg_default, "meal_period": "ANY_MEAL_PERIOD",
        "started_at": now, "term_ends_at": now + timedelta(days=term),
        "grants_issued": 0, "grants_per_term": int(program["grants_per_term"]),
        "next_grant_at": now + timedelta(days=interval),
        "stripe_session_id": stripe_session_id,
        "created_at": now, "updated_at": now}
    await db.dining_subscriptions.insert_one(dict(sub))
    grant = await _issue_grant(db, sub, program)
    await db.dining_subscriptions.update_one(
        {"subscription_id": sub["subscription_id"]},
        {"$set": {"grants_issued": 1}})
    sub["grants_issued"] = 1
    return {"subscription": _clean(sub), "first_grant": grant}


async def issue_due_grants(db) -> int:
    """Sweeper — issue any weekly grants that have come due (spec §43)."""
    program = await get_program(db)
    interval = int(program["grant_interval_days"])
    now = _now()
    issued = 0
    async for sub in db.dining_subscriptions.find(
            {"status": "active", "next_grant_at": {"$lte": now}}):
        if _aware(sub.get("term_ends_at")) and _aware(sub["term_ends_at"]) <= now:
            await db.dining_subscriptions.update_one(
                {"subscription_id": sub["subscription_id"]},
                {"$set": {"status": "expired", "updated_at": now}})
            continue
        if int(sub.get("grants_issued") or 0) >= int(sub.get("grants_per_term") or 4):
            continue
        await _issue_grant(db, sub, program)
        await db.dining_subscriptions.update_one(
            {"subscription_id": sub["subscription_id"]},
            {"$inc": {"grants_issued": 1},
             "$set": {"next_grant_at": now + timedelta(days=interval),
                      "updated_at": now}})
        issued += 1
    return issued


# ── merchant / location / capacity ─────────────────────────────────────
def _cap_key(meal_period: str, veg: str) -> str:
    return f"{meal_period}:{veg}"


async def _capacity_left(db, location_id: str, day: str, meal_period: str,
                         veg: str, loc: dict) -> int:
    default = int((loc.get("capacity") or {}).get(_cap_key(meal_period, veg)) or 0)
    row = await db.dining_capacity.find_one(
        {"location_id": location_id, "date": day, "key": _cap_key(meal_period, veg)})
    used = int((row or {}).get("used") or 0)
    return max(0, default - used)


async def _consume_capacity(db, location_id: str, day: str, meal_period: str,
                            veg: str) -> None:
    await db.dining_capacity.update_one(
        {"location_id": location_id, "date": day, "key": _cap_key(meal_period, veg)},
        {"$inc": {"used": 1}}, upsert=True)


async def _location_supports(loc: dict, veg: str) -> bool:
    return bool(loc.get("veg_available")) if veg == "VEG" else bool(loc.get("nonveg_available"))


# ── candidate generation + EQUAL-PROBABILITY winner draw ───────────────
async def _eligible_locations(db, *, veg: str, meal_period: str, lat: float,
                              lng: float, program: dict,
                              exclude_ids: Optional[set] = None) -> list[dict]:
    exclude_ids = exclude_ids or set()
    day = _day()
    radius = float(program["max_radius_miles"])
    out = []
    async for loc in db.dining_locations.find({"status": "ACTIVE"}):
        if loc["location_id"] in exclude_ids:
            continue
        merch = await db.dining_merchants.find_one(
            {"merchant_id": loc["merchant_id"]},
            {"status": 1, "cuisine": 1, "restaurant_class": 1})
        if not merch or merch.get("status") != "ACTIVE":
            continue
        if not await _location_supports(loc, veg):
            continue
        if day in (loc.get("blackout_dates") or []):
            continue
        dist = _haversine_miles(lat, lng, loc.get("lat", lat), loc.get("lng", lng))
        if dist > radius:
            continue
        if await _capacity_left(db, loc["location_id"], day, meal_period, veg, loc) <= 0:
            continue
        loc["_distance"] = round(dist, 2)
        loc["cuisine"] = merch.get("cuisine")
        loc["restaurant_class"] = merch.get("restaurant_class")
        out.append(loc)
    return out


def _draw_winner(candidate_ids: list[str]) -> tuple[str, dict]:
    """Uniform pick — every id has 1/N probability (CSPRNG). Returns
    (winner_id, audit)."""
    n = len(candidate_ids)
    rng = secrets.SystemRandom()
    idx = rng.randrange(n)
    audit = {"n": n, "index": idx, "probability": round(1.0 / n, 6),
             "rng": "secrets.SystemRandom", "drawn_at": _now().isoformat(),
             "nonce": secrets.token_hex(8)}
    return candidate_ids[idx], audit


async def _build_candidate_set(db, *, session: dict, attempt: int,
                               exclude_ids: set, program: dict) -> Optional[dict]:
    eligible = await _eligible_locations(
        db, veg=session["veg_preference"], meal_period=session["meal_type"],
        lat=session["lat"], lng=session["lng"], program=program,
        exclude_ids=exclude_ids)
    if len(eligible) < int(program["min_viable_restaurants"]):
        return None
    rng = secrets.SystemRandom()
    rng.shuffle(eligible)
    chosen = eligible[: int(program["candidate_size"])]
    ids = [c["location_id"] for c in chosen]
    winner_id, audit = _draw_winner(ids)
    set_id = _gen("dcset")
    await db.dining_candidate_sets.insert_one({
        "set_id": set_id, "session_id": session["session_id"],
        "customer_id": session["customer_id"], "attempt": attempt,
        "restaurant_ids": ids, "winner_restaurant_id": winner_id,
        "audit": audit, "created_at": _now()})
    return {"set_id": set_id, "restaurant_ids": ids,
            "winner_restaurant_id": winner_id, "count": len(ids), "audit": audit}


# ── selection session state machine ────────────────────────────────────
def _pre_spin_summary(eligible: list[dict], radius: float) -> dict:
    """Non-identifying aggregate shown BEFORE the spin (spec §12)."""
    cuisines = sorted({(l.get("cuisine") or "").title() for l in eligible if l.get("cuisine")})
    classes = sorted({l.get("restaurant_class") for l in eligible if l.get("restaurant_class")})
    return {"restaurants_available": len(eligible),
            "within_miles": radius, "cuisine_mix": cuisines[:6],
            "class_mix": classes}


async def start_session(db, *, customer_id: str, veg: str, meal_period: str,
                        lat: Optional[float], lng: Optional[float],
                        program: dict) -> dict:
    if veg not in ("VEG", "NON_VEG"):
        raise ValueError("veg_preference must be VEG or NON_VEG")
    if meal_period not in program["meal_periods"] + ["ANY"]:
        raise ValueError("invalid_meal_period")
    now = _now()
    # anti-abuse: one active session per customer; cooldown after abandon (§64/§65)
    active = await db.dining_selection_sessions.find_one(
        {"customer_id": customer_id,
         "status": {"$in": ["STARTED", "FIRST_RESULT", "REROLL_REQUESTED", "FINAL_RESULT"]},
         "expires_at": {"$gt": now}})
    if active:
        return {"session": _clean(active), "resumed": True}
    last_abandon = await db.dining_selection_sessions.find_one(
        {"customer_id": customer_id, "status": "ABANDONED"},
        sort=[("updated_at", -1)])
    if last_abandon:
        cd = int(program["abandon_cooldown_minutes"])
        la = _aware(last_abandon.get("updated_at"))
        if la and (now - la) < timedelta(minutes=cd):
            wait = cd - int((now - la).total_seconds() // 60)
            raise PermissionError(f"cooldown_active:{max(1, wait)}")
    lat = lat if lat is not None else DEFAULT_MARKET["lat"]
    lng = lng if lng is not None else DEFAULT_MARKET["lng"]
    eligible = await _eligible_locations(
        db, veg=veg, meal_period=meal_period, lat=lat, lng=lng, program=program)
    if len(eligible) < int(program["min_viable_restaurants"]):
        raise LookupError("not_enough_options")
    session = {
        "session_id": _gen("dsess"), "customer_id": customer_id,
        "veg_preference": veg, "meal_type": meal_period,
        "lat": lat, "lng": lng, "market": DEFAULT_MARKET["market"],
        "attempt_count": 0, "reroll_limit": int(program["reroll_limit"]),
        "first_candidate_set_id": None, "first_result_restaurant_id": None,
        "second_candidate_set_id": None, "second_result_restaurant_id": None,
        "accepted_restaurant_id": None, "reserved_credit_id": None,
        "status": "STARTED", "created_at": now, "updated_at": now,
        "expires_at": now + timedelta(minutes=int(program["session_ttl_minutes"]))}
    await db.dining_selection_sessions.insert_one(dict(session))
    out = _clean(session)
    out["pre_spin"] = _pre_spin_summary(eligible, float(program["max_radius_miles"]))
    return {"session": out, "resumed": False}


async def _load_active_session(db, customer_id: str, session_id: str) -> dict:
    s = await db.dining_selection_sessions.find_one(
        {"session_id": session_id, "customer_id": customer_id})
    if not s:
        raise LookupError("session_not_found")
    if _aware(s.get("expires_at")) and _aware(s["expires_at"]) <= _now():
        await db.dining_selection_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "EXPIRED", "updated_at": _now()}})
        raise TimeoutError("session_expired")
    return s


async def _restaurant_public(db, location_id: str) -> Optional[dict]:
    loc = await db.dining_locations.find_one({"location_id": location_id})
    if not loc:
        return None
    merch = await db.dining_merchants.find_one({"merchant_id": loc["merchant_id"]})
    offer = await db.dining_meal_offers.find_one(
        {"location_id": location_id, "active": True})
    return {
        "restaurant_id": location_id,
        "name": (merch or {}).get("name") or loc.get("name"),
        "logo_url": (merch or {}).get("logo_url"),
        "cuisine": (merch or {}).get("cuisine"),
        "restaurant_class": (merch or {}).get("restaurant_class"),
        "address": loc.get("address"), "lat": loc.get("lat"), "lng": loc.get("lng"),
        "distance_miles": loc.get("_distance"),
        "service_window": loc.get("hours"),
        "todays_meal": {"title": (offer or {}).get("customer_title")
                        or "Chef's selected meal",
                        "description": (offer or {}).get("customer_description")}}


async def spin(db, *, customer_id: str, session_id: str, method: str,
               program: dict) -> dict:
    """Produce a result (method 'wheel' or 'random' — identical fairness).
    First call = attempt 1 (FIRST_RESULT); after a reroll = attempt 2 (FINAL)."""
    s = await _load_active_session(db, customer_id, session_id)
    now = _now()
    if s["status"] in ("STARTED",):
        attempt = 1
    elif s["status"] == "REROLL_REQUESTED":
        attempt = 2
    else:
        raise ValueError(f"cannot_spin_in_status:{s['status']}")

    exclude: set = set()
    if attempt == 2:
        # New set of 10; exclude the first winner + prior candidates (spec §21)
        first_set = await db.dining_candidate_sets.find_one(
            {"set_id": s.get("first_candidate_set_id")})
        if first_set:
            exclude = set(first_set.get("restaurant_ids") or [])

    result = await _build_candidate_set(
        db, session=s, attempt=attempt, exclude_ids=exclude, program=program)
    if not result:
        # Second set could not exclude enough; retry excluding only first winner.
        if attempt == 2 and s.get("first_result_restaurant_id"):
            result = await _build_candidate_set(
                db, session=s, attempt=attempt,
                exclude_ids={s["first_result_restaurant_id"]}, program=program)
    if not result:
        raise LookupError("not_enough_options")

    winner = await _restaurant_public(db, result["winner_restaurant_id"])
    fields = {"attempt_count": attempt, "updated_at": now, "method": method}
    if attempt == 1:
        fields.update({"status": "FIRST_RESULT",
                       "first_candidate_set_id": result["set_id"],
                       "first_result_restaurant_id": result["winner_restaurant_id"]})
    else:
        fields.update({"status": "FINAL_RESULT",
                       "second_candidate_set_id": result["set_id"],
                       "second_result_restaurant_id": result["winner_restaurant_id"]})
    await db.dining_selection_sessions.update_one(
        {"session_id": session_id}, {"$set": fields})
    try:
        winner_index = result["restaurant_ids"].index(result["winner_restaurant_id"])
    except ValueError:
        winner_index = 0
    mid = await _merchant_id_for_location(db, result["winner_restaurant_id"])
    await emit_dining_event(db, merchant_id=mid, event_type="restaurant.selected",
                            data={"session_id": session_id, "attempt": attempt,
                                  "location_id": result["winner_restaurant_id"]})
    return {"session_id": session_id, "attempt": attempt,
            "status": fields["status"], "candidate_count": result["count"],
            "segments": result["count"], "winner_index": winner_index,
            "can_reroll": attempt == 1, "winner": winner,
            "meal_price_cents": int(program["meal_price_cents"])}


async def reroll(db, *, customer_id: str, session_id: str) -> dict:
    s = await _load_active_session(db, customer_id, session_id)
    if s["status"] != "FIRST_RESULT":
        raise ValueError(f"cannot_reroll_in_status:{s['status']}")
    await db.dining_selection_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "REROLL_REQUESTED", "updated_at": _now()}})
    return {"session_id": session_id, "status": "REROLL_REQUESTED",
            "rerolls_left": 0}


async def abandon(db, *, customer_id: str, session_id: str) -> dict:
    s = await _load_active_session(db, customer_id, session_id)
    if s.get("reserved_credit_id"):
        await _release_credit(db, s["reserved_credit_id"])
    await db.dining_selection_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "ABANDONED", "reserved_credit_id": None,
                  "updated_at": _now()}})
    return {"session_id": session_id, "status": "ABANDONED"}


async def accept(db, *, customer_id: str, session_id: str, program: dict) -> dict:
    """Accept the revealed restaurant → reserve a credit + create a pending
    $9.99 order. Capacity is re-checked; if it vanished, no charge (§36)."""
    s = await _load_active_session(db, customer_id, session_id)
    if s["status"] not in ("FIRST_RESULT", "FINAL_RESULT"):
        raise ValueError(f"cannot_accept_in_status:{s['status']}")
    winner_id = (s["second_result_restaurant_id"] if s["status"] == "FINAL_RESULT"
                 else s["first_result_restaurant_id"])
    loc = await db.dining_locations.find_one({"location_id": winner_id})
    if not loc:
        raise LookupError("restaurant_unavailable")
    day = _day()
    if await _capacity_left(db, winner_id, day, s["meal_type"],
                            s["veg_preference"], loc) <= 0:
        raise ConnectionError("availability_changed")  # offer system re-spin
    credit = await _reserve_oldest_credit(db, customer_id, session_id)
    if not credit:
        raise ValueError("no_available_credit")
    order_id = _gen("dord")
    now = _now()
    await db.dining_orders.insert_one({
        "order_id": order_id, "session_id": session_id, "customer_id": customer_id,
        "credit_id": credit["credit_id"], "location_id": winner_id,
        "meal_period": s["meal_type"], "veg_preference": s["veg_preference"],
        "amount_cents": int(program["meal_price_cents"]), "status": "pending",
        "stripe_session_id": None, "created_at": now, "updated_at": now})
    await db.dining_selection_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "ACCEPTED", "accepted_restaurant_id": winner_id,
                  "reserved_credit_id": credit["credit_id"],
                  "order_id": order_id, "updated_at": now}})
    mid = await _merchant_id_for_location(db, winner_id)
    await emit_dining_event(db, merchant_id=mid, event_type="restaurant.accepted",
                            data={"order_id": order_id, "location_id": winner_id,
                                  "amount_cents": int(program["meal_price_cents"])})
    return {"session_id": session_id, "status": "ACCEPTED", "order_id": order_id,
            "credit_id": credit["credit_id"], "restaurant_id": winner_id,
            "amount_cents": int(program["meal_price_cents"])}


# ── signed single-use QR ───────────────────────────────────────────────
def _sign_qr(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


async def _issue_qr(db, *, order: dict, program: dict) -> dict:
    now = _now()
    exp = now + timedelta(minutes=int(program["qr_ttl_minutes"]))
    redemption_id = _gen("dredm")
    day = _day()
    payload = f"{redemption_id}.{order['credit_id']}.{order['location_id']}.{order['customer_id']}.{day}"
    sig = _sign_qr(program["qr_secret"], payload)
    qr_token = f"{redemption_id}.{sig}"
    await db.dining_redemptions.insert_one({
        "redemption_id": redemption_id, "order_id": order["order_id"],
        "customer_id": order["customer_id"], "credit_id": order["credit_id"],
        "location_id": order["location_id"], "meal_period": order["meal_period"],
        "veg_preference": order["veg_preference"], "day": day,
        "qr_token": qr_token, "signature": sig, "status": "ISSUED",
        "issued_at": now, "expires_at": exp, "redeemed_at": None})
    return {"redemption_id": redemption_id, "qr_token": qr_token,
            "expires_at": _iso(exp)}


async def finalize_paid_order(db, *, order: dict, program: dict,
                              stripe_session_id: Optional[str] = None,
                              stripe_charge_id: Optional[str] = None) -> dict:
    """Mark an order paid → issue the QR (idempotent). The restaurant is NOT paid
    here — the net share ($8.99) is transferred to its Stripe Connect account on
    QR redemption (see _settle_redemption)."""
    if order.get("status") == "paid":
        existing = await db.dining_redemptions.find_one({"order_id": order["order_id"]})
        return {"order_id": order["order_id"], "status": "paid",
                "qr": _clean(existing)}
    await db.dining_orders.update_one(
        {"order_id": order["order_id"]},
        {"$set": {"status": "paid", "stripe_session_id": stripe_session_id,
                  "stripe_charge_id": stripe_charge_id,
                  "paid_at": _now(), "updated_at": _now()}})
    qr = await _issue_qr(db, order=order, program=program)
    mid = await _merchant_id_for_location(db, order["location_id"])
    await emit_dining_event(db, merchant_id=mid, event_type="payment.completed",
                            data={"order_id": order["order_id"],
                                  "amount_cents": int(order.get("amount_cents") or 0)})
    await emit_dining_event(db, merchant_id=mid, event_type="qr.issued",
                            data={"order_id": order["order_id"],
                                  "redemption_id": qr["redemption_id"]})
    return {"order_id": order["order_id"], "status": "paid", "qr": qr}


async def get_pass(db, *, customer_id: str, order_id: str) -> Optional[dict]:
    order = await db.dining_orders.find_one(
        {"order_id": order_id, "customer_id": customer_id})
    if not order:
        return None
    redm = await db.dining_redemptions.find_one({"order_id": order_id})
    restaurant = await _restaurant_public(db, order["location_id"])
    return {"order": _clean(order), "restaurant": restaurant,
            "qr": _clean(redm) if order.get("status") == "paid" else None}


# ── merchant redemption (validates + single-use) ───────────────────────
async def redeem_qr(db, *, qr_token: str, program: dict,
                    merchant_location_id: Optional[str] = None) -> dict:
    redm = await db.dining_redemptions.find_one({"qr_token": qr_token})
    if not redm:
        raise LookupError("invalid_qr")
    if merchant_location_id and redm["location_id"] != merchant_location_id:
        raise PermissionError("wrong_location")
    if redm["status"] == "REDEEMED":
        raise ValueError("already_redeemed")
    if _aware(redm.get("expires_at")) and _aware(redm["expires_at"]) <= _now():
        await db.dining_redemptions.update_one(
            {"redemption_id": redm["redemption_id"]}, {"$set": {"status": "EXPIRED"}})
        raise TimeoutError("qr_expired")
    # verify signature
    payload = f"{redm['redemption_id']}.{redm['credit_id']}.{redm['location_id']}.{redm['customer_id']}.{redm['day']}"
    if not hmac.compare_digest(_sign_qr(program["qr_secret"], payload), redm["signature"]):
        raise PermissionError("bad_signature")
    # atomic single-use flip
    res = await db.dining_redemptions.find_one_and_update(
        {"redemption_id": redm["redemption_id"], "status": "ISSUED"},
        {"$set": {"status": "REDEEMED", "redeemed_at": _now()}},
        return_document=True)
    if not res:
        raise ValueError("already_redeemed")
    await db.dining_meal_credits.update_one(
        {"credit_id": redm["credit_id"]},
        {"$set": {"status": "REDEEMED", "redeemed_at": _now()}})
    await _consume_capacity(db, redm["location_id"], redm["day"],
                            redm["meal_period"], redm["veg_preference"])
    # small BigPoints reward for redeeming (reuse existing engine)
    try:
        await bigcoin.award(db, redm["customer_id"], 20, "dining_redeem",
                            metadata={"redemption_id": redm["redemption_id"]})
    except Exception:
        pass
    # Settle the restaurant's share ($8.99) via Stripe Connect transfer on redemption.
    settlement = await _settle_redemption(db, redm=redm, program=program)
    mid = await _merchant_id_for_location(db, redm["location_id"])
    loc = await db.dining_locations.find_one({"location_id": redm["location_id"]})
    left = await _capacity_left(db, redm["location_id"], redm["day"],
                                redm["meal_period"], redm["veg_preference"], loc or {})
    await emit_dining_event(db, merchant_id=mid, event_type="redeemed",
                            data={"redemption_id": redm["redemption_id"],
                                  "location_id": redm["location_id"],
                                  "credit_id": redm["credit_id"], **settlement})
    if left <= 0:
        await emit_dining_event(db, merchant_id=mid, event_type="capacity.sold_out",
                                data={"location_id": redm["location_id"],
                                      "meal_period": redm["meal_period"],
                                      "veg_preference": redm["veg_preference"]})
    elif left <= 3:
        await emit_dining_event(db, merchant_id=mid, event_type="capacity.low",
                                data={"location_id": redm["location_id"], "left": left,
                                      "meal_period": redm["meal_period"],
                                      "veg_preference": redm["veg_preference"]})
    return {"redemption_id": redm["redemption_id"], "status": "REDEEMED",
            "credit_id": redm["credit_id"], "location_id": redm["location_id"],
            **settlement}


# ══════════ Stripe Connect payout on redemption (spec §40) ═════════════
async def get_session_view(db, *, customer_id: str, session_id: str) -> Optional[dict]:
    """Resume view for an in-progress selection (used by the app to rehydrate
    the wheel/reveal after navigation or reload)."""
    s = await db.dining_selection_sessions.find_one(
        {"session_id": session_id, "customer_id": customer_id})
    if not s:
        return None
    out = {"session_id": s["session_id"], "status": s["status"],
           "veg_preference": s.get("veg_preference"),
           "meal_period": s.get("meal_period"),
           "attempt": int(s.get("attempt_count") or 0),
           "can_reroll": s["status"] == "FIRST_RESULT",
           "pre_spin": s.get("pre_spin")}
    result_id = s.get("second_result_restaurant_id") or s.get("first_result_restaurant_id")
    if s["status"] in ("FIRST_RESULT", "FINAL_RESULT") and result_id:
        out["winner"] = await _restaurant_public(db, result_id)
        prog = await get_program(db)
        out["meal_price_cents"] = int(prog["meal_price_cents"])
    if s["status"] == "ACCEPTED":
        order = await db.dining_orders.find_one({"session_id": session_id})
        if order:
            out["order_id"] = order["order_id"]
    return out


async def _settle_redemption(db, *, redm: dict, program: dict) -> dict:
    """On QR redemption, transfer the restaurant's net ($8.99) to its connected
    account, retaining the platform fee ($1). Records a dining_payouts ledger row.
    If the merchant hasn't finished Stripe Connect onboarding, the payout is
    ledgered as pending (nothing lost) rather than failing the redemption."""
    order = await db.dining_orders.find_one({"order_id": redm["order_id"]})
    gross = int((order or {}).get("amount_cents") or program["meal_price_cents"])
    fee = int(program.get("platform_fee_cents") or 100)
    net = max(0, gross - fee)
    loc = await db.dining_locations.find_one(
        {"location_id": redm["location_id"]}, {"merchant_id": 1})
    merchant = (await db.dining_merchants.find_one(
        {"merchant_id": (loc or {}).get("merchant_id")})) if loc else None
    payout = {"payout_id": _gen("dpay"), "redemption_id": redm["redemption_id"],
              "order_id": redm["order_id"],
              "merchant_id": (merchant or {}).get("merchant_id"),
              "location_id": redm["location_id"], "gross_cents": gross,
              "platform_fee_cents": fee, "net_cents": net, "currency": "usd",
              "stripe_transfer_id": None, "created_at": _now()}
    acct = (merchant or {}).get("stripe_account_id")
    charge = (order or {}).get("stripe_charge_id")
    if acct and net > 0:
        try:
            from services import stripe_connect_service as scs
            tr = await scs.create_transfer(
                amount_cents=net, destination_account_id=acct,
                source_transaction=charge,
                transfer_group=f"dining_{redm['order_id']}",
                metadata={"redemption_id": redm["redemption_id"],
                          "order_id": redm["order_id"]},
                idempotency_key=f"dining_transfer_{redm['redemption_id']}")
            payout["stripe_transfer_id"] = tr["transfer_id"]
            payout["status"] = "transferred"
        except Exception as e:  # noqa: BLE001
            payout["status"] = "transfer_failed"
            payout["error"] = str(e)[:200]
    else:
        payout["status"] = "pending_no_connect" if not acct else "pending_no_charge"
    await db.dining_payouts.insert_one(payout)
    return {"gross_cents": gross, "platform_fee_cents": fee, "net_cents": net,
            "settlement": payout["status"],
            "stripe_transfer_id": payout.get("stripe_transfer_id")}


# ══════════ merchant self-serve (Phase 2) ═════════════════════════════
async def _merchant_id_for_location(db, location_id: str) -> Optional[str]:
    loc = await db.dining_locations.find_one(
        {"location_id": location_id}, {"merchant_id": 1})
    return (loc or {}).get("merchant_id")


async def create_owned_merchant(db, *, owner_user_id: str, name: str, cuisine: str,
                                restaurant_class: str,
                                stripe_account_id: Optional[str] = None) -> dict:
    existing = await db.dining_merchants.find_one({"owner_user_id": owner_user_id})
    if existing:
        return _clean(existing)
    doc = {"merchant_id": _gen("dmerch"), "owner_user_id": owner_user_id,
           "name": name, "cuisine": (cuisine or "").lower(),
           "restaurant_class": restaurant_class or "FAST_CASUAL", "status": "ACTIVE",
           "participation_fee_cents": 50000, "billing_frequency": "monthly",
           "logo_url": None, "stripe_account_id": stripe_account_id,
           "stripe_onboarding_status": "not_started", "created_at": _now()}
    await db.dining_merchants.insert_one(dict(doc))
    return _clean(doc)


async def get_owned_merchant(db, owner_user_id: str) -> Optional[dict]:
    return await db.dining_merchants.find_one({"owner_user_id": owner_user_id})


async def set_merchant_connect(db, *, merchant_id: str, stripe_account_id: str,
                               status: str) -> None:
    await db.dining_merchants.update_one(
        {"merchant_id": merchant_id},
        {"$set": {"stripe_account_id": stripe_account_id,
                  "stripe_onboarding_status": status, "updated_at": _now()}})


async def add_location(db, *, merchant_id: str, name: str, address: str,
                       lat: Optional[float], lng: Optional[float],
                       veg_available: bool, nonveg_available: bool,
                       hours: str = "11:00–22:00") -> dict:
    doc = {"location_id": _gen("dloc"), "merchant_id": merchant_id, "name": name,
           "status": "ACTIVE", "address": address, "market": DEFAULT_MARKET["market"],
           "lat": lat if lat is not None else DEFAULT_MARKET["lat"],
           "lng": lng if lng is not None else DEFAULT_MARKET["lng"],
           "veg_available": bool(veg_available), "nonveg_available": bool(nonveg_available),
           "hours": hours, "blackout_dates": [], "capacity": {}, "created_at": _now()}
    await db.dining_locations.insert_one(dict(doc))
    return _clean(doc)


async def update_location(db, *, merchant_id: str, location_id: str, patch: dict):
    allowed = {"name", "address", "lat", "lng", "veg_available", "nonveg_available",
               "hours", "blackout_dates", "status"}
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    if not clean:
        return await db.dining_locations.find_one(
            {"location_id": location_id, "merchant_id": merchant_id})
    return await db.dining_locations.find_one_and_update(
        {"location_id": location_id, "merchant_id": merchant_id},
        {"$set": clean}, return_document=True)


async def set_capacity(db, *, merchant_id: str, location_id: str, capacity: dict) -> bool:
    clean = {k: max(0, int(v)) for k, v in (capacity or {}).items()}
    r = await db.dining_locations.update_one(
        {"location_id": location_id, "merchant_id": merchant_id},
        {"$set": {"capacity": clean}})
    return r.matched_count > 0


async def set_meals(db, *, merchant_id: str, location_id: str, meals: list) -> list:
    """Set/rotate the daily Veg/Non-Veg meal offers for a location."""
    await db.dining_meal_offers.update_many(
        {"location_id": location_id, "merchant_id": merchant_id},
        {"$set": {"active": False}})
    out = []
    for m in meals or []:
        if m.get("veg_preference") not in ("VEG", "NON_VEG"):
            continue
        doc = {"offer_id": _gen("doff"), "location_id": location_id,
               "merchant_id": merchant_id, "veg_preference": m["veg_preference"],
               "meal_period": m.get("meal_period", "LUNCH"),
               "customer_title": m.get("customer_title") or "Chef's selected meal",
               "customer_description": m.get("customer_description"),
               "active": True, "updated_at": _now()}
        await db.dining_meal_offers.insert_one(dict(doc))
        out.append(_clean(doc))
    return out


async def merchant_view(db, owner_user_id: str) -> Optional[dict]:
    m = await get_owned_merchant(db, owner_user_id)
    if not m:
        return None
    locs = [_clean(l) for l in await db.dining_locations.find(
        {"merchant_id": m["merchant_id"]}).to_list(100)]
    offers = [_clean(o) for o in await db.dining_meal_offers.find(
        {"merchant_id": m["merchant_id"], "active": True}).to_list(200)]
    return {"merchant": _clean(m), "locations": locs, "meals": offers}


async def merchant_analytics(db, merchant_id: str) -> dict:
    locs = [l["location_id"] async for l in db.dining_locations.find(
        {"merchant_id": merchant_id}, {"location_id": 1})]
    lset = set(locs)
    appearances = wins = 0
    async for cs in db.dining_candidate_sets.find(
            {}, {"restaurant_ids": 1, "winner_restaurant_id": 1}):
        for rid in cs.get("restaurant_ids") or []:
            if rid in lset:
                appearances += 1
        if cs.get("winner_restaurant_id") in lset:
            wins += 1
    accepts = await db.dining_selection_sessions.count_documents(
        {"accepted_restaurant_id": {"$in": locs}})
    redemptions = await db.dining_redemptions.count_documents(
        {"location_id": {"$in": locs}, "status": "REDEEMED"})
    agg = await db.dining_payouts.aggregate([
        {"$match": {"location_id": {"$in": locs}}},
        {"$group": {"_id": None, "gross": {"$sum": "$gross_cents"},
                    "net": {"$sum": "$net_cents"}, "fee": {"$sum": "$platform_fee_cents"},
                    "n": {"$sum": 1}}}]).to_list(1)
    p = agg[0] if agg else {}
    return {"locations": len(locs), "appearances": appearances, "wins": wins,
            "acceptances": accepts, "redemptions": redemptions,
            "acceptance_rate": round(accepts / wins, 3) if wins else 0,
            "reroll_rejection_rate": round((wins - accepts) / wins, 3) if wins else 0,
            "earnings": {"gross_cents": int(p.get("gross") or 0),
                         "net_cents": int(p.get("net") or 0),
                         "platform_fee_cents": int(p.get("fee") or 0),
                         "meals_settled": int(p.get("n") or 0)}}


# ══════════ restaurant-facing webhooks (Phase 4, spec §77-78) ══════════
DINING_EVENTS = ["restaurant.selected", "restaurant.accepted", "payment.completed",
                 "qr.issued", "redeemed", "capacity.low", "capacity.sold_out"]


def _wh_sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


async def _deliver_dining_webhook(url: str, secret: str, event: dict) -> None:
    import json
    import httpx
    body = json.dumps(event, default=str)
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            await c.post(url, content=body, headers={
                "Content-Type": "application/json",
                "X-FUUSIC-Dining-Signature": _wh_sign(secret, body),
                "X-FUUSIC-Event": event["type"]})
    except Exception:
        pass


async def emit_dining_event(db, *, merchant_id: Optional[str], event_type: str,
                            data: dict) -> None:
    if not merchant_id:
        return
    import asyncio as _a
    now = _now()
    async for wh in db.dining_webhooks.find(
            {"merchant_id": merchant_id, "status": "active", "events": event_type}):
        ev = {"id": _gen("devt"), "type": f"dining.{event_type}",
              "created": now.isoformat(), "merchant_id": merchant_id, "data": data}
        _a.create_task(_deliver_dining_webhook(wh["url"], wh["secret"], ev))
        await db.dining_webhook_deliveries.insert_one({
            "delivery_id": _gen("dwd"), "webhook_id": wh["webhook_id"],
            "merchant_id": merchant_id, "event_type": ev["type"], "url": wh["url"],
            "event": ev, "ts": now})


async def register_dining_webhook(db, *, merchant_id: str, url: str,
                                  events: list) -> dict:
    evs = [e for e in (events or []) if e in DINING_EVENTS] or list(DINING_EVENTS)
    doc = {"webhook_id": _gen("dwh"), "merchant_id": merchant_id, "url": url,
           "events": evs, "secret": "dwhsec_" + secrets.token_urlsafe(24),
           "status": "active", "created_at": _now()}
    await db.dining_webhooks.insert_one(dict(doc))
    return _clean(doc)


async def list_dining_webhooks(db, merchant_id: str) -> list:
    return [_clean(w) for w in await db.dining_webhooks.find(
        {"merchant_id": merchant_id}).to_list(100)]


async def delete_dining_webhook(db, merchant_id: str, webhook_id: str) -> bool:
    r = await db.dining_webhooks.delete_one(
        {"webhook_id": webhook_id, "merchant_id": merchant_id})
    return r.deleted_count > 0


__all__ = [
    "PROGRAM_ID", "DEFAULTS", "DINING_EVENTS", "ensure_dining_indexes",
    "get_program", "patch_program", "public_program",
    "credit_summary", "list_credits", "expire_credits",
    "get_subscription", "create_subscription", "issue_due_grants",
    "start_session", "spin", "reroll", "abandon", "accept",
    "finalize_paid_order", "get_pass", "redeem_qr",
    "_reserve_oldest_credit", "_release_credit",
    "create_owned_merchant", "get_owned_merchant", "set_merchant_connect",
    "add_location", "update_location", "set_capacity", "set_meals",
    "merchant_view", "merchant_analytics",
    "register_dining_webhook", "list_dining_webhooks", "delete_dining_webhook",
    "emit_dining_event",
]
