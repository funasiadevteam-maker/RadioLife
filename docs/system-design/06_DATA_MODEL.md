# 06 — Data Model (MongoDB)

MongoDB accessed via Motor (async) through the `db` singleton in `core/db.py`. One database
(`DB_NAME`); collections are created/indexed lazily at startup by `ensure_*_indexes(db)` seeders.

> This is a **representative** map of the most important collections grouped by domain, not an
> exhaustive schema. The app has hundreds of collections across ~240 route modules. Treat each
> route/service as the authority for its own collection's exact shape. Never return raw documents —
> serialize (map `_id → id`, drop raw `ObjectId`). See `02_BACKEND_DESIGN.md`.

## Identity & preferences

| Collection | Notable fields / purpose |
|-----------|--------------------------|
| `users` | account, `role` (admin/…), bcrypt password, `is_premium`/subscription, `theme`, `accent`, `theme_schedule`, `enabled_features`, `onboarded_*`, `subscription.stripe_customer_id`, Fun AI prefs & memory |
| sessions | server-side session tokens (cookie `bigfm_session` / Bearer); 7-day TTL |
| `app_settings` | admin-tunable config docs, e.g. `fun_ai_radio_policy`, `fun_ai_news` (sponsor), feature defaults |
| `system_config` | runtime knobs (e.g. preroll hop cooldown, mid-roll cadence) |
| `platform_settings` | soft-launch / business-setup-mode flags |

## Fun AI / radio / audio

| Collection | Purpose |
|-----------|---------|
| `fun_ai_sessions` | each voice session (user, surface, mode, personality, voice_seconds) |
| `fun_ai_sponsor_events` | sponsor-break impressions (placement, listener) |
| `rj_sponsored_reads`, `rj_sponsored_read_plays` | paid RJ spot inventory + play/impression ledger (budget decrement, reporting) |
| `news_articles` | the news corpus feeding Interactive News |
| `channels`, flagship/imported stations, `station_*` | station catalog (flagship + 50k imported), tracks, artwork, claims, favourites, analytics |
| `tracks` | uploaded/catalog audio + tags |

## Social

| Collection | Purpose |
|-----------|---------|
| `dreams`, `dream_similar`, `dream_comments`, `dream_reactions`, `dream_saves`, `dream_reports` | Dreams & Guidance core |
| `dream_clubs`, `dream_club_members`, `dream_clusters`/themes, `cluster_follows`, `dream_alerts`, `compat_cards` | clubs, clusters, alerts, compatibility |
| `advisor_profiles`, `advisor_services`, `reading_bookings`, `advisor_reviews`, `ai_readings`, `daily_readings` | advisor marketplace + AI readings |
| `dream_live_sessions`, `dream_live_questions` | live advisor Q&A (LiveKit, mocked) |
| `social_notifications`, follows, feed prefs | notifications, following graph, feed modes |

## Commerce / marketplace

| Collection | Purpose |
|-----------|---------|
| businesses / merchant profiles | storefronts (approved/draft), categories |
| `products`, services, menus, `marketplace_orders` | catalog + orders |
| memberships, `user_gift_cards`, gift card SKUs | subscriptions & gift cards |
| dining: `dining_*`, `dining_payouts` | Premium Dining Club (credits, orders, QR, payouts) |
| `bar_game_unlocks`, `bar_game_plays`, `bar_game_skins`, `bar_game_free_claims` | bar games |
| `coupons`, scan-to-pay, ticket codes | coupons, payments, redemption |

## Games & rewards

| Collection | Purpose |
|-----------|---------|
| games_v2 campaigns, plays, winners, leaderboards | spin/scratch/trivia/predict-&-win |
| BigPoints/BigCoin wallet + ledger, streaks | rewards currency, daily streak bonus (+10/day cap +70) |
| predict_win_* | prediction game lifecycle |

## Advertising

| Collection | Purpose |
|-----------|---------|
| `rail_wallets`, `rail_wallet_txns`, `rail_alerts`, `rail_events` | right-rail ad wallet + second-price auction + outbid alerts |
| banner / preroll / midstream ad inventory, `home_ad_events` | display + audio ads, Home analytics |
| `partner_merchants`, `partner_offers`, `partner_reward_events`, `partner_conversions`, `partner_jobs`, `partner_invoices` | Partner API v1 entities (`/api/v1`) |
| `creative_assets`, `api_parent_campaigns`, `campaign_line_items` | Partner API creative library + multi-format campaigns |

## Payments & payouts

| Collection | Purpose |
|-----------|---------|
| `vendor_accounts` | Stripe Connect connected accounts (merchant/advisor payouts) |
| billing / subscription docs | Premium/trial, invoices, dunning |
| platform fee config | `/admin/platform-fees` (default 15%, merchant 5%) |

## Soft launch / waitlist

| Collection | Purpose |
|-----------|---------|
| `consumer_waitlist` | referral waitlist (ref codes, tiers, teasers) |
| `preview_tokens` | preview-as-customer bypass tokens |
| `soft_launch_claims` | "{N} months free" business claims |
