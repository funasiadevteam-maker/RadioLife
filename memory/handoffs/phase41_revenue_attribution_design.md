# Phase 41 — Revenue Attribution Math (Design Doc)

> **Status**: DESIGN ONLY. Implementation lands in Phase 41 Session 6.
> **Anchor**: HEAD `a35b4d1` · commit 107.

## 0. User-locked tier table (from Phase 41 Session 0 brief)

```
< 500 hrs / month         → NO payout (status='withheld', revenue still attributed)
500   – 2,000 hrs         → 40% creator / 60% platform
2,000 – 10,000 hrs        → 50% creator / 50% platform   (base tier)
10,000 – 50,000 hrs       → 55% creator / 45% platform
> 50,000 hrs              → 60% creator / 40% platform
```

Admin-editable via `creator_revenue_share_tiers` (see §4). Floor is the
**500-hour minimum**; ceiling is the **60% creator share**.

---

## 1. What counts as "listening time"

A `creator_listening_minute` is recorded when ALL of the following are true:

1. Listener is on a **non-admin station** owned by an approved creator
   (`community_radio_stations.owner_user_id ≠ NULL`, page_type ∈
   {`personal_radio`, `business_radio`, `influencer_radio`,
   `community_radio`, `event_radio`}).
2. Audio is actively playing (front-end heartbeat every 30s confirms
   `playing=true`).
3. Listener is **not** the creator themselves (`listener_user_id ≠
   owner_user_id` — fraud guard).
4. Minute has not yet been credited (idempotent via composite key
   `(listener_user_id, station_id, minute_bucket_iso)`).

Storage: rolling aggregate, not raw rows.

```python
class CreatorListeningMinute(BaseDocument):
    creator_user_id:  str  # owner of the station
    station_id:       str
    listener_user_id: str  # for fraud detection only
    minute_bucket_iso: str # "2026-06-07T14:32:00Z" — minute resolution
    counted_at:       datetime  # for cron sweeps
```

Composite unique index: `(creator_user_id, station_id, listener_user_id,
minute_bucket_iso)`. Idempotency comes from this index, not from
application code.

Daily roll-up cron at `00:30 UTC` computes per-creator hours and writes:

```python
class CreatorDailyAggregate(BaseDocument):
    creator_user_id:    str
    date_iso:           str   # "2026-06-07"
    total_minutes:      int
    unique_listeners:   int
    top_listener_share: float # 0.0–1.0 — fraud guard signal
```

Index: `(creator_user_id, date_iso)` unique.

---

## 2. What counts as "attributed revenue"

Three independent streams roll up to a single creator monthly bucket.

### 2.1 Ad revenue
- Each ad impression already records `session.channel_id` (or
  `station_id` once we wire it).
- If `station_id` resolves to a creator-owned station → credit the
  station's `owner_user_id`.
- Settlement timing: at month-end, sum `ad_impressions.revenue_cents`
  WHERE delivered between `[month_start, month_end)` AND
  `station.owner_user_id IS NOT NULL`.

### 2.2 Conversion revenue (30-day attribution window)
- Coupons saved, games played, premium subscriptions started **while
  the listener was on a creator-owned station** within the 30 days
  preceding the conversion.
- Attribution rule: **last-touch within 30 days**. If a listener has
  consumed multiple creator stations in the window, credit goes to the
  station playing at the moment of conversion (or the most-recent
  station if conversion happened off-platform within the window).
- Source signal: existing `coupon_saves`, `game_plays`,
  `billing_events.subscribed_at` tables already have a `session_id`
  column from Phase 22+.

### 2.3 Tip / direct support (Phase 41M — not in MVP)
Reserved field on `creator_payouts.tip_revenue_cents` for future.

---

## 3. Monthly payout cron — pseudocode

```python
# Runs at 01:00 UTC on the 1st of each month (UTC anchored).
async def monthly_payout_cron(db, month_start: date):
    month_end = month_start + relativedelta(months=1)
    creators = db.podcast_creators.find({"application_status": "approved"})
    async for c in creators:
        cid = c["user_id"]

        # 1) Aggregate listening hours for the month.
        total_min = await db.creator_daily_aggregate.aggregate([
            {"$match": {"creator_user_id": cid,
                        "date_iso": {"$gte": month_start.isoformat(),
                                     "$lt":  month_end.isoformat()}}},
            {"$group": {"_id": None, "min": {"$sum": "$total_minutes"}}}
        ]).to_list(1)
        hours = (total_min[0]["min"] / 60.0) if total_min else 0.0

        # 2) Sum revenue (ad + conversion) for the month.
        revenue_cents = (
            await sum_ad_revenue(db, cid, month_start, month_end) +
            await sum_conversion_revenue(db, cid, month_start, month_end))

        # 3) Determine tier.
        tier = await db.creator_revenue_share_tiers.find_one({
            "active": True,
            "min_listening_hours": {"$lte": hours},
            "$or": [{"max_listening_hours": {"$gt": hours}},
                    {"max_listening_hours": None}],  # null = unbounded ceiling
        })
        creator_pct = (tier or {}).get("creator_share_pct", 0)
        creator_cents  = int(round(revenue_cents * creator_pct / 100))
        platform_cents = revenue_cents - creator_cents

        # 4) 500-hour floor → withhold but still record.
        status = "pending" if hours >= 500 else "withheld"

        # 5) Fraud guard — single-listener > 50% of hours.
        fraud_flag = await check_top_listener_share(db, cid, month_start, month_end)
        if fraud_flag > 0.5:
            status = "fraud_review"

        await db.creator_payouts.insert_one({
            "payout_id":      uuid.uuid4().hex,
            "creator_user_id": cid,
            "month":          month_start.isoformat(),
            "listening_hours": hours,
            "tier_id":        (tier or {}).get("tier_id"),
            "creator_share_pct":  creator_pct,
            "revenue_cents":  revenue_cents,
            "creator_cents":  creator_cents,
            "platform_cents": platform_cents,
            "status":         status,
            "fraud_top_listener_share": fraud_flag,
            "created_at":     datetime.now(timezone.utc),
            "stripe_transfer_id": None,
        })

        # 6) If status=pending → schedule Stripe Connect transfer.
        if status == "pending" and creator_cents > 0:
            await schedule_stripe_transfer(c, payout_id)
```

---

## 4. `creator_revenue_share_tiers` collection

Admin-editable, seeded at startup if empty:

```python
DEFAULT_TIERS = [
    {"tier_id": "tier_floor",     "min_listening_hours": 0,      "max_listening_hours": 500,
     "creator_share_pct": 0,  "platform_share_pct": 0,  "active": True,
     "note": "Below-floor — earnings withheld until 500 hrs / month."},
    {"tier_id": "tier_starter",   "min_listening_hours": 500,    "max_listening_hours": 2000,
     "creator_share_pct": 40, "platform_share_pct": 60, "active": True},
    {"tier_id": "tier_base",      "min_listening_hours": 2000,   "max_listening_hours": 10000,
     "creator_share_pct": 50, "platform_share_pct": 50, "active": True},
    {"tier_id": "tier_growth",    "min_listening_hours": 10000,  "max_listening_hours": 50000,
     "creator_share_pct": 55, "platform_share_pct": 45, "active": True},
    {"tier_id": "tier_pro",       "min_listening_hours": 50000,  "max_listening_hours": None,
     "creator_share_pct": 60, "platform_share_pct": 40, "active": True},
]
```

**Seed policy**: idempotent — `update_one({"tier_id": …},
{"$setOnInsert": doc}, upsert=True)`. Admins can edit `creator_share_pct`
via `/api/admin/revenue_share/tiers`. Audit each change to
`creator_revenue_share_tier_audit`.

**Tier lookup formula** validated against the spec:

| Hours | Tier returned | Creator pct | Spec match |
|---|---|---|---|
| 0   | tier_floor   |  0% | ✅ withheld below 500 |
| 250 | tier_floor   |  0% | ✅ withheld below 500 |
| 500 | tier_starter | 40% | ✅ floor of payable range |
| 1,500 | tier_starter | 40% | ✅ |
| 2,000 | tier_base | 50% | ✅ base tier |
| 5,000 | tier_base | 50% | ✅ |
| 10,000 | tier_growth | 55% | ✅ |
| 30,000 | tier_growth | 55% | ✅ |
| 50,000 | tier_pro | 60% | ✅ |
| 100,000 | tier_pro | 60% | ✅ ceiling |

Boundary convention: `min ≤ hours < max`. Match the lower edge of each
tier; `max=null` = unbounded ceiling.

---

## 5. Below-floor creator UX

When `status='withheld'`, the creator dashboard shows:

```
"You earned $147.32 in attributed revenue this month, but payouts
unlock at 500 listening hours/month. You're at 327 hours — 173 to go.
Your earnings are safely held and will be released when you cross
the threshold next month."
```

Withheld amounts **do not roll forward** to subsequent months in MVP.
Phase 41M decision: should rolled-forward "lifetime earned"
accumulation be added? Defer.

---

## 6. Fraud detection placeholder

Single-listener concentration > 50% in any monthly window → status
flipped to `fraud_review` (manual admin clearance required).

This is intentionally weak in MVP — it catches the obvious case (creator
listening to their own station via a second account, or a single fan
bot-listening). Phase 41M will add device-fingerprint clustering + IP
diversity scoring.

---

## 7. Stripe payout pathway (Session 6 implementation note)

Reuse `services/stripe_client.py`:

```python
from services.stripe_client import create_express_account, create_account_link
# Already shipped + tested in Phase 36e.
```

Creator must complete Stripe Connect Express onboarding before any
payout is initiated. Until they do, `status` stays `pending` and a
banner in the dashboard prompts onboarding.

For payouts: use `stripe.Transfer.create(...)` to the connected
account, store `stripe_transfer_id` on the payout row. Webhook
`transfer.paid` flips `status` to `paid`. Webhook `transfer.failed`
flips to `failed` and notifies admin.

---

## 8. Open questions for user review

1. **Stripe Connect onboarding gating**: should creators be REQUIRED to
   complete Stripe before publishing their station, or just before
   getting paid? Recommend gating at first publish (lower friction).
2. **Rolled-forward withheld balances**: see §5. Yes/no?
3. **Fraud-review SLA**: 7 days? 14? Phase 41M will harden but MVP
   needs a default. Recommend 7 days.
4. **Below-floor visibility**: should the creator see their attributed
   $$ even if withheld, or only when they cross 500 hrs? Recommend
   showing it — motivates effort.

---

## 9. Validation against user-locked spec

| Spec rule | Encoded where | Pass |
|---|---|---|
| < 500 hrs → no payout | `tier_floor` row + `status='withheld'` branch | ✅ |
| 500–2,000 hrs → 40% | `tier_starter` | ✅ |
| 2,000–10,000 → 50% (base) | `tier_base` | ✅ |
| 10,000–50,000 → 55% | `tier_growth` | ✅ |
| > 50,000 → 60% | `tier_pro` with `max=null` | ✅ |
| Admin-editable | `creator_revenue_share_tiers` + `/api/admin/revenue_share/tiers` | ✅ |
| Idempotent seed | `$setOnInsert` upsert | ✅ |
| Below-floor message | UX copy in §5 | ✅ |

---

## 10. Implementation checklist (carried into Session 6)

- [ ] Create `creator_listening_minute` collection + unique index
- [ ] Create `creator_daily_aggregate` collection + daily cron at 00:30 UTC
- [ ] Create `creator_revenue_share_tiers` collection + seed cron
- [ ] Create `creator_payouts` collection
- [ ] Implement `monthly_payout_cron` at 01:00 UTC 1st-of-month
- [ ] Wire Stripe Connect Express onboarding into creator dashboard
- [ ] Admin endpoint to edit tiers (audit logged)
- [ ] Creator dashboard chart: hours + revenue + tier indicator
- [ ] Frontend below-floor messaging
- [ ] Pytest: synthetic listener log → assertion that hour totals + tier
      selection + payout math match expected output (test fixtures)
