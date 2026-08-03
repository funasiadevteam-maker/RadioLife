# BigFM — Employee Test Matrix (10-person internal test)

Each employee runs this matrix end-to-end on their own account.  Tap the
🐛 Feedback button (bottom-right, employee/admin only) to log anything
that surprises you — bug / suggestion / praise / other.  Screenshot
attachment is supported via the in-modal Camera button.

Account setup
-----------------
* Admin grants you `is_employee=true` → you log in once → see the
   welcome modal → +500 BC, +3 badges (First Hour, First Share, First
   Prediction), +1 city stamp (Dallas) all auto-seeded.

---

## 1. Signup + login

| # | Step | Expected |
|--|--|--|
| 1.1 | Sign up at `/signup` with `e1_tester_<n>@bigfantv.com` / 12-char password | Welcome screen, +50 BC seeded |
| 1.2 | Logout, login again | Lands on `/` (Home dashboard) |
| 1.3 | Forgot password flow | Real Mailgun reset email lands in inbox |

## 2. Listen flows

| # | Step | Expected |
|--|--|--|
| 2.1 | Pick one BigFM AI channel from Home | Pre-roll ad plays (3 in a row by default) → music starts within 5s |
| 2.2 | Listen for 5-7 songs straight | AI-RJ segment auto-injects after the 3rd song (cadence=3) |
| 2.3 | Continue another 4 songs | Mid-stream audio ad (J.5) injects between songs 6-7 (cadence=4) — premium users skip this |
| 2.4 | Switch to an imported Radio Browser station | Stream loads in <8s |
| 2.5 | Hit pause → resume | Plays from same spot |
| 2.6 | Lock phone / switch tab | MediaSession controls show in OS lock screen |

## 3. Predict & Win

| # | Step | Expected |
|--|--|--|
| 3.1 | `/predict-win` → pick today's featured event → submit prediction | Confirmation toast, entry locked |
| 3.2 | Admin force-resolves the event | Winner gets +X BC awarded via PointsService, sees notification |

## 4. Games

| # | Step | Expected |
|--|--|--|
| 4.1 | Trivia at `/trivia` → click any topic | UX.1 — session starts immediately, no interstitial |
| 4.2 | Answer 10 questions | Score + tier-up notification if applicable |
| 4.3 | Spin-the-wheel game (`/play-and-win`) | Lands on a payout slot, BC awarded |

## 5. Sharing + invites

| # | Step | Expected |
|--|--|--|
| 5.1 | Share a station via the Share button | OG card preview loads; clipboard fallback works on mobile |
| 5.2 | Invite a friend via `/wallet` (real email) | Real Mailgun delivery — friend gets invite email; Mailgun webhook fires `delivered` event |

## 6. Wallet + Passport

| # | Step | Expected |
|--|--|--|
| 6.1 | `/wallet` shows BC balance | Matches `/api/me/points` exactly |
| 6.2 | `/passport` shows badges + stamps | First Hour, First Share, First Prediction, Dallas stamp all visible |
| 6.3 | Leaderboard | You appear; tier matches your lifetime BC |

## 7. Business Portal (assign 1-2 employees)

| # | Step | Expected |
|--|--|--|
| 7.1 | `/business/register` → fill out, set PIN | Redirected to `/business` dashboard, verified=false |
| 7.2 | Click "Launch your first coupon · 50% OFF" | 100 voucher codes minted; share URL displayed; CTA disappears |
| 7.3 | Open the share URL in incognito | Public offer page renders, code is claimable |
| 7.4 | Switch back to employee role, paste a claimed code into `/business/redeem` → enter PIN | Redemption success, customer credited +20 BC |

## 8. Premium subscription (Stripe test mode)

| # | Step | Expected |
|--|--|--|
| 8.1 | `/billing` → Subscribe to Premium → Stripe Checkout with **test card 4242 4242 4242 4242** | Redirects to `/billing/success`, sub status flips to active |
| 8.2 | Listen for 10 songs | NO pre-roll, NO mid-stream ad |
| 8.3 | Cancel subscription from `/billing` | Takes effect at period end; you keep Premium until then |

## 9. Tips (Phase J.4)

| # | Step | Expected |
|--|--|--|
| 9.1 | Tip the BigFM House Personas Pool 100 BC | Sender debited 100, pool credited 90, platform fee 10 |
| 9.2 | Receive a tip from another employee | Receiver balance bumps, mini toast |
| 9.3 | Try to tip yourself | 400 `cannot_tip_yourself` |

## 10. Feedback widget

| # | Step | Expected |
|--|--|--|
| 10.1 | Hit the 🐛 Feedback fab on any page | Modal opens, 4 categories pickable |
| 10.2 | Capture screenshot → submit "bug" | Toast "feedback logged"; admin sees the entry under `/api/admin/feedback?status=open` |
| 10.3 | Switch role to admin → mark resolved | Status flips to `resolved` with your resolution note |

---

## Severity grading for `bug` category

* **P0** — Crash / data loss / payment failure / auth lock-out.
* **P1** — Feature broken but workaround exists.
* **P2** — Visual / copy / minor UX glitch.
* **P3** — Suggestion or polish.

Tag at the start of your text, e.g.:

> **[P1]** Mid-stream ad cuts off the next song's intro by ~2s.

---

_Last updated: 2026-06-19 (Phase Π)_
