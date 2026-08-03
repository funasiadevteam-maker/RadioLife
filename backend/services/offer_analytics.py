"""
Phase 17b — Offer analytics, A/B variants, org rollup, payouts.

Pure helpers — REST routes glue these to FastAPI.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List

STAGES = ("impression", "save", "scan", "redeem")
DEFAULT_PLATFORM_CUT = 0.05   # 5 % of cash redemption value
BIGCOIN_USD_RATE      = 0.01   # 1 BigCoin = $0.01


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided Wilson score interval for a Bernoulli proportion."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def assign_variant(user_id: str, offer_id: str,
                          variants: list[dict]) -> dict:
    """Sticky deterministic hash-bucket assignment by weight."""
    active = [v for v in (variants or []) if v.get("status", "active") == "active"
                  and (v.get("weight") or 0) > 0]
    if not active:
        return {"slug": "control"}
    total = sum(int(v["weight"]) for v in active)
    if total <= 0:
        return active[0]
    digest = hashlib.sha1(f"{user_id}::{offer_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % total
    running = 0
    for v in active:
        running += int(v["weight"])
        if bucket < running:
            return v
    return active[-1]


async def track_event(db, *, offer_id: str, stage: str, user_id: Optional[str],
                              venue_id: Optional[str] = None,
                              channel: Optional[str] = None,
                              ip_hash: Optional[str] = None,
                              variant_slug: Optional[str] = None) -> None:
    if stage not in STAGES:
        return
    await db.offer_events.insert_one({
        "id":             "evt_" + hashlib.sha1(
                                  f"{offer_id}{stage}{user_id}{datetime.now(timezone.utc).timestamp()}"
                                  .encode()).hexdigest()[:12],
        "offer_id":      offer_id,
        "venue_id":     venue_id,
        "user_id":       user_id,
        "stage":          stage,
        "channel":        channel,
        "ip_hash":       ip_hash,
        "variant_slug": variant_slug,
        "timestamp":    datetime.now(timezone.utc),
    })


def _day_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


async def funnel_for_offer(db, *, offer_id: str,
                                    frm: datetime, to: datetime,
                                    variant_slug: Optional[str] = None) -> dict:
    """Aggregate 4-stage funnel + per-day buckets."""
    match = {"offer_id": offer_id, "timestamp": {"$gte": frm, "$lt": to}}
    if variant_slug:
        match["variant_slug"] = variant_slug
    cur = db.offer_events.find(match)
    counts = {s: 0 for s in STAGES}
    buckets: dict[str, dict] = {}
    async for ev in cur:
        stage = ev.get("stage")
        if stage not in counts:
            continue
        counts[stage] += 1
        day = _day_iso(ev["timestamp"])
        b = buckets.setdefault(day, {"day": day, **{s: 0 for s in STAGES}})
        b[stage] += 1
    imps      = counts["impression"]
    saves     = counts["save"]
    scans     = counts["scan"]
    redeems = counts["redeem"]
    save_rate    = (saves / imps) if imps else 0.0
    scan_rate    = (scans / saves) if saves else 0.0
    redeem_rate = (redeems / scans) if scans else 0.0
    # Top drop-off — pair with largest absolute drop.
    pairs = [
        ("impression", "save",   imps,   saves),
        ("save",        "scan",   saves, scans),
        ("scan",        "redeem", scans, redeems),
    ]
    if any(b > 0 for _, _, b, _ in pairs):
        a, b_label, a_n, b_n = max(pairs, key=lambda p: (p[2] - p[3]) if p[2] else 0)
        drop_pct = ((a_n - b_n) / a_n * 100) if a_n else 0
        if drop_pct >= 30 and a_n > 0:
            tips = {
                "impression→save":  "Try a sharper headline or larger discount.",
                "save→scan":          "Add a reminder push 1 hr before expiry.",
                "scan→redeem":     "Likely a venue-side scan error; check the scanner UX.",
            }
            top_drop = {"from": a, "to": b_label,
                              "drop_pct": round(drop_pct, 1),
                              "hint":     tips[f"{a}→{b_label}"]}
        else:
            top_drop = None
    else:
        top_drop = None
    payload = {
        "impressions":   imps,
        "saves":           saves,
        "scans":           scans,
        "redeems":        redeems,
        "save_rate":      round(save_rate,    4),
        "scan_rate":      round(scan_rate,    4),
        "redeem_rate":   round(redeem_rate, 4),
        "time_buckets": sorted(buckets.values(), key=lambda b: b["day"]),
        "top_drop":       top_drop,
        "from":             frm.isoformat(),
        "to":                to.isoformat(),
    }
    # Phase 17c — boost eligibility based on the top_drop signal.
    try:
        from services.offer_boost import compute_boost_eligibility
        payload["boost_eligible"] = compute_boost_eligibility(payload)
    except Exception:
        payload["boost_eligible"] = False
    return payload


async def variant_results(db, *, offer_id: str,
                                  frm: datetime, to: datetime,
                                  variants: list[dict]) -> dict:
    """Per-variant funnel + Wilson CI on redeem-rate vs impressions.

    A challenger is the auto-winner if (a) >= 300 impressions, AND
    (b) its CI lower bound > control's CI upper bound on the
    redeem-per-impression rate."""
    items: list[dict] = []
    control = None
    for v in variants or []:
        f = await funnel_for_offer(db, offer_id=offer_id, frm=frm, to=to,
                                                  variant_slug=v["slug"])
        n = f["impressions"]
        succ = f["redeems"]
        lo, hi = wilson_ci(succ, n)
        item = {
            "slug":         v["slug"],
            "headline":   v.get("headline"),
            "weight":      v.get("weight"),
            "status":     v.get("status", "active"),
            "impressions": n,
            "saves":         f["saves"],
            "scans":         f["scans"],
            "redeems":      f["redeems"],
            "redeem_rate": f["redeem_rate"],
            "ci_lo":         round(lo, 4),
            "ci_hi":         round(hi, 4),
        }
        items.append(item)
        if v["slug"] == "control":
            control = item
    # Auto-winner detection.
    winner = None
    if control:
        for it in items:
            if it["slug"] == "control":
                continue
            if (it["impressions"] >= 300
                  and it["ci_lo"]  > control["ci_hi"]):
                winner = it["slug"]
                break
    return {"variants": items, "auto_winner_slug": winner}


# ─── Org rollup ─────────────────────────────────────────────────────
async def org_rollup(db, *, org_id: str, since: datetime,
                              rh = None) -> dict:
    """Aggregate redemptions + offers + live trivia rooms across all
    venues linked to the org."""
    venues = await db.venues.find({"parent_org_id": org_id,
                                              "active":          True}).to_list(50)
    venue_ids = [v["id"] for v in venues]
    if not venue_ids:
        return {"venues": [], "total_redemptions": 0,
                  "total_rooms": 0, "best_offer": None}
    redeems = await db.coupons.count_documents({
        "venue_id":     {"$in": venue_ids},
        "redeemed_at": {"$gte": since},
    })
    # Live rooms — count from in-memory hub if provided.
    live_rooms = 0
    if rh is not None:
        for room in rh.all_rooms().values():
            if (getattr(room, "venue_id", None) in venue_ids
                  and getattr(room, "phase", "") != "done"):
                live_rooms += 1
    # Per-venue mini-stats.
    venue_cards = []
    best_offer = None
    best_offer_redeems = -1
    best_venue_id  = None
    best_venue_red = -1
    total_revenue  = 0.0
    for v in venues:
        per_venue_coupons = await db.coupons.find({
            "venue_id":     v["id"],
            "redeemed_at": {"$gte": since},
        }).to_list(5000)
        r          = len(per_venue_coupons)
        v_revenue = sum(float(c.get("discount_value") or 0) for c in per_venue_coupons)
        total_revenue += v_revenue
        top_offer = await db.offers.find_one(
            {"venue_id": v["id"], "status": "active"},
            sort=[("issued_count", -1)],
        )
        if top_offer and (top_offer.get("redeemed_count") or 0) > best_offer_redeems:
            best_offer = {"id": top_offer["id"], "title": top_offer["title"],
                              "venue_id": v["id"], "redeemed": top_offer.get("redeemed_count", 0)}
            best_offer_redeems = top_offer.get("redeemed_count") or 0
        if r > best_venue_red:
            best_venue_red = r
            best_venue_id  = v["id"]
        venue_cards.append({
            "id":               v["id"],
            "name":              v["name"],
            "market":             v.get("market"),
            "redeems":         r,
            "revenue_usd":   round(v_revenue, 2),
            "top_offer_title": top_offer["title"] if top_offer else None,
        })
    return {
        "venues":              venue_cards,
        "total_venues":       len(venues),
        "total_redemptions": redeems,
        "total_revenue_usd": round(total_revenue, 2),
        "total_rooms":       live_rooms,
        "best_offer":         best_offer,
        "best_venue_id":    best_venue_id,
        "since":               since.isoformat(),
    }


# ─── Demo seed for Phase 17b ────────────────────────────────────────
async def seed_demo_org(db) -> dict:
    """Idempotent: ensure `org_karak_chain` exists with two venues
    (Dubai + Frisco) linked under it.  Re-runs cleanly on each boot."""
    owner = await db.users.find_one({"email": "admin@bigfm.dubai"})
    if not owner:
        return {"skipped": "owner-not-seeded-yet"}
    org_id = "org_karak_chain"
    await db.venue_orgs.update_one(
        {"id": org_id},
        {"$set": {
            "id":               org_id,
            "name":              "Karak Chain",
            "owner_user_id":   owner["user_id"],
            "logo_url":          None,
            "primary_color":   "#FF2D8A",
        },
          "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    # Ensure Dubai venue is linked.
    await db.venues.update_one(
        {"id": "venue_demo_karak"},
        {"$set": {"parent_org_id": org_id}},
    )
    # Ensure Frisco sibling venue exists & is linked.
    frisco = await db.venues.find_one({"id": "venue_demo_karak_frisco"})
    if not frisco:
        await db.venues.insert_one({
            "id":               "venue_demo_karak_frisco",
            "name":              "Demo Karak Cafe — Frisco",
            "owner_user_id":   owner["user_id"],
            "market":             "dfw",
            "address":           "1234 Main St, Frisco, TX",
            "lat":                33.1507,
            "lng":                -96.8236,
            "hours":              {},
            "phone":              None,
            "website":            None,
            "plan_tier":         "growth",
            "logo_url":          None,
            "primary_color":   "#FF2D8A",
            "business_id":      None,
            "active":             True,
            "parent_org_id":   org_id,
            "created_at":        datetime.now(timezone.utc),
        })
        # Also seed staff membership so the owner can see it.
        await db.venue_staff.insert_one({
            "id":          "vstaff_frisco_seed",
            "venue_id":   "venue_demo_karak_frisco",
            "user_id":    owner["user_id"],
            "role":        "owner",
            "created_at": datetime.now(timezone.utc),
        })
    else:
        await db.venues.update_one(
            {"id": "venue_demo_karak_frisco"},
            {"$set": {"parent_org_id": org_id}},
        )
    return {"org_id": org_id, "ok": True}
async def payout_summary(db, *, venue_id: str, since: datetime,
                                  until: datetime,
                                  platform_cut: float = DEFAULT_PLATFORM_CUT) -> dict:
    """Aggregate cash-equivalent redemptions + BigCoin liability over a period."""
    coupons = await db.coupons.find({
        "venue_id":     venue_id,
        "redeemed_at": {"$gte": since, "$lt": until},
    }).to_list(5000)
    cash_count = 0
    cash_value  = 0.0
    big_award  = 0.0       # BigCoin awarded to users
    daily: dict[str, dict] = {}
    for c in coupons:
        v = float(c.get("discount_value") or 0)
        cash_count += 1
        cash_value  += v
        big_award  += v * 0.5   # platform mocks 50% of cash value as BigCoin awarded
        day = _day_iso(c["redeemed_at"])
        b = daily.setdefault(day, {"day": day, "redemptions": 0,
                                                "value_usd": 0.0, "bigcoin_usd": 0.0})
        b["redemptions"] += 1
        b["value_usd"]    += v
        b["bigcoin_usd"]  += v * 0.5 * BIGCOIN_USD_RATE * 100   # rough scale for display
    platform_share = round(cash_value * platform_cut, 2)
    payout = round(cash_value - platform_share, 2)
    return {
        "period":                              {"from": since.isoformat(), "to": until.isoformat()},
        "bigcoin_liability_usd":              round(big_award * BIGCOIN_USD_RATE * 100, 2),
        "cash_redemptions_count":           cash_count,
        "cash_redemptions_value_usd":      round(cash_value, 2),
        "ad_spend_net_usd":                  0.0,
        "ad_spend_note":                     "Tracking arrives in Phase 18.",
        "platform_cut_pct":                   round(platform_cut * 100, 2),
        "net_platform_revenue_share_usd": platform_share,
        "expected_payout_to_venue_usd":   payout,
        "time_buckets":                      sorted(daily.values(), key=lambda b: b["day"]),
    }
