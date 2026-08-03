# Phase 41 Session 1 — Spec (user decisions locked)

> Captured during Phase 41 P3 interrupt (2026-06-07). DO NOT execute yet —
> dispatch happens after Phase 42 audit + radio P0 + home redesign land.

## User-locked decisions (override prior open Qs)

| # | Decision | Source |
|---|---|---|
| 1 | **Stripe Connect Express**: already configured ✅ | user |
| 2 | **Below-floor visibility**: show accrued $$ + auto-generate FB / TikTok / Instagram social-share CTAs (platform-aware formatting) | user |
| 3 | **Rollover**: withheld balances roll forward up to **12 months**, then reset to zero | user |
| 4 | **Payout cadence**: 30 days post month-end | user |
| 5 | **Multi-page per user**: YES (implicit) — drop the `user_id` single-row constraint, use `(user_id, page_type)` compound key | user |
| 6 | **Existing podcast_creators**: opt-in to social promotion (not auto-migrated to multi-page status) | user |
| 7 | **Cross-page follower portability**: NO — explicit per-page follow required | user |

## Implications for Session 1 implementation

- Add `accrued_lifetime_cents` + `accrued_lifetime_since` to creator dashboard payload (decay rule: zero out at 12-month mark from `accrued_lifetime_since`).
- Payout cron: shift from "1st of next month" to "30 days after month-end" — runs nightly, looking for payouts whose `withheld_since + 30d <= today`.
- Schema migration: drop unique constraint on `podcast_creators.user_id`; add compound unique on `(user_id, page_type)`. Existing podcast rows survive (one per user, page_type='podcast').
- Existing podcasters opting into social promotion: new `social_promotion_opt_in: bool` flag on `podcast_creators`; surfaces an "Enable social pages" CTA on the creator dashboard.
- Follow API: `POST /api/creators/:id/follow` writes one row per (user_id, creator_id) — no auto-fan-out across a creator's other pages.

## Auto-share CTA spec (Phase 41 Session 6)

Below-floor creator dashboard renders 3 share buttons:

| Platform | Format |
|---|---|
| **Facebook** | "I'm building my BigFM station 📻 — {hours}/500 listening hrs this month → $X.YZ earned. Tune in: {/r/<slug>}" |
| **TikTok** | Short caption variant (≤150 chars): "{hours}/500 hrs · ${creator_cents/100} earned · BigFM is paying me to be your DJ. Listen 👇 {/r/<slug>}" |
| **Instagram** | Story-card variant with branded gradient + accrued $$ overlay (image generated on demand via Pillow) |

All share text strings live in `services/creator_share_copy.py` so they're A/B-testable later.

## Dispatch order (after radio P0 + home + news prefs + Phase 42 audit close)
Session 1 → Session 2 → … → Session 7. See `phase41_audit_and_plan.md` for the full session breakdown.
