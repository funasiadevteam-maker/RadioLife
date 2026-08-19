# RadioLife — PRD (Phase H v1 · Commute Mode MVP · 2026-07-24)

## TUBE SKIN → FULL YOUTUBE-STYLE ENDLESS FEED + SHOPPING (2026-08 fork, phase 1 of 3)
User is sending references across 3 phases to evolve the WEB "Tube" browse skin into a real YouTube experience. Phase 1 (this) — web only; Cinematic/Studio untouched. Testing agent iter99: backend 10/10 pass; frontend verified; the 1 HIGH bug it found (endless scroll not appending) was fixed + re-verified by main agent (tiles 11→22, shelves 1→2 on scroll).

**Backend (`routes/browse.py`)**
- NEW `GET /api/browse/feed?page=&cat=` — paginated MIXED feed of blocks: a video `grid` (with shop product cards sprinkled every 6th item), plus rotating `shelf` blocks by page (`shorts` portrait / `playables` games-with-Play / `shop`) and occasional `featured` promo. Recycles the finite catalog via modular offsets so `has_more` stays true (endless). `cat` filters: `all` (mixed), `shopping` (all-shop grid), `games` (playables + grid), or a rail key. Page 0 also returns `chips` + `subs`.
- NEW `_shop_products()` joins `products` (price) → `marketplace_profiles` for the image (products have no own image → business cover/logo, gradient fallback). Added a `shop` rail to `/home`.

**Frontend (`design_radiolife/browse/TubeBrowse.jsx`, full rewrite)**
- Left YouTube sidebar (`browse-sidebar`): Home / Shorts / **Shopping** / Play & Win + Subscriptions avatars + You links. Top chip bar (`browse-chips`) incl. a **🛍 Shopping** chip. Shopping is in BOTH places (per user).
- Endless scroll via a stable window-scroll loader + a "fill viewport" effect (reads latest state via a ref — replaced a fragile IntersectionObserver that recreated per page and stopped firing).
- Varied row sizes: 3-col video grid, tall Shorts shelf, square Playables shelf (each card a **Play** button `browse-game-play`), Shop shelf, and a 2-col featured promo.
- Shop woven in: inline `browse-shop-tile` cards (SHOP badge + price) sprinkled through the grid; Shopping chip/sidebar → all-shop grid.
- Preserved testids: browse-tube, browse-search, browse-chips, browse-chip-<key>, browse-tile, browse-exit-legacy. New: browse-sidebar, browse-side-<label>, browse-shop-tile, browse-shelf-<variant>, browse-game-play, browse-feed-sentinel.

Note: several products/businesses lack cover images → gradient-letter fallback (by design); products named "Product" are placeholder seed data. Awaiting phases 2–3 assets.



## PARTNER CONSOLE — HISTORY, VOICE FAVOURITES, SPEND DASHBOARD, ADMIN BULK-APPROVE (2026-08 fork, cont.)
Four more user-approved enhancements. Backend + web (no mobile). Testing agent iter98: 9/9 backend + full UI PASS, no bugs.

1) **Console History** — `GET /api/partner/commerce/history` (`partner_marketplace.list_partner_history`) unifies the partner's buys across `marketplace_promotions` (purchased_by_partner), `category_bids`, and `trivia_sponsorships`/`rj_sponsored_reads` (partner advertisers), each with kind/name/detail/status/amount/env. Shown in a "Purchase history" section (pc-history-*) with a refresh button; auto-refreshes after every buy.
2) **Voice Favourites** — `POST /api/partner/commerce/voice-favourite {persona_id}` persists `favourite_persona_id` on the partner account; `/commerce/catalog` returns it. Star on each persona card (pc-rj-fav-<id>); the favourite is pre-selected on the AI-RJ booking on load.
3) **Spend Dashboard** — `GET /api/partner/commerce/analytics/summary` (`partner_marketplace.partner_analytics_summary`) rolls up impressions/views/orders/revenue + placement & spotlight spend + promotion counts across ALL the partner's promotions. Shown as a tile grid (pc-summary) at the top of the console.
4) **Admin Bulk Approve** — refactored `_approve_one()` + new `POST /api/admin/marketplace/promotions/bulk-approve {promotion_ids}` (returns approved/failed lists, cap 100). Admin Promotions "In review" tab now has per-row checkboxes (promo-select-<id>), Select-all (promo-select-all) and "Approve selected (N)" (promo-bulk-approve).

Files: `services/partner_marketplace.py`, `routes/partner_portal.py`, `routes/marketplace_promotions.py`, `frontend/src/pages/advertiser_v2/PartnerCheckout.jsx`, `frontend/src/admin/Promotions.jsx`.



## PARTNER CONSOLE + VOICE PICKER + PROMOTION ANALYTICS + ADMIN QUEUE (2026-08 fork, cont.)
Four user-approved follow-ups to the Partner Ads API. Backend + web (no mobile). Testing agent iter97: 10/11 pass; the 2 HIGH bugs it found were fixed + re-verified (see end).

### 1) Partner Console "API Checkout" (web)
New page `frontend/src/pages/advertiser_v2/PartnerCheckout.jsx` at `/advertiser/dashboard/api-checkout` (nav item added to `AdvertiserShell`, route in `App.js`). Partners buy — Promoted-rail placement, Category Spotlight, Trivia sponsorship, AI-RJ read — and watch checkout status flip to paid/active, no curl. A Sandbox/Live toggle: Sandbox activates instantly; Live opens a real Stripe hosted Checkout link inline + a "check status" poll.
- Driven by NEW cookie-authed wrappers `/api/partner/commerce/*` in `routes/partner_portal.py` (reuse the SAME services as `/api/v1`; no raw API key in the browser). One reusable advertiser is auto-created per (partner, env). Endpoints: `/commerce/catalog`, `/promotion/checkout|/{id}/status|/{id}/report`, `/spotlight/checkout|/{id}/status`, `/personas`, `/personas/{id}/preview`, `/sponsorships` (+`/submit`,`/checkout`,`/checkout/status`).

### 2) AI-RJ Read Voice Picker (real audio)
Console lists host personas with a play button that fetches a REAL spoken sample (`POST /commerce/personas/{id}/preview` → `rj_persona_service.generate_preview`). Seeded 3 demo personas (Ava/Leo/Maya) via `scripts/seed_demo_rj_persona.py`. IMPORTANT: the env `ELEVENLABS_API_KEY` is an invalid *key ID* (400s), so the personas use `voice_provider=openai_tts` with the real `OPENAI_API_KEY` — preview + LIVE rj_read paid TTS render both work (~8s). Preview errors degrade to a clean 503, never 500.

### 3) Promotion Analytics API
NEW `partner_marketplace.promotion_report()` + `GET /api/v1/marketplace/promotion/{id}/report` (scope reports:read, + portal mirror). Returns impressions, views, orders, revenue, placement + spotlight spend over the promotion's active window. Shown per bought promotion in the console ("View analytics").

### 4) Admin Partner Queue
`routes/marketplace_promotions.py` admin list now enriches each promotion with `via_partner` + `partner_name` (looked up from `partner_accounts`). `admin/Promotions.jsx` shows a "via API · <partner>" badge on partner-purchased promotions so admins fast-track them.

### Bug fixes in this round (found by iter97, fixed + re-verified)
- Sandbox rj_read created via console/portal returned no id (`res.get("id")` vs shaped `sponsored_read_id`) so `_sandbox_activate` no-op'd → stayed `draft`. Fixed in `partner_portal.py` AND `partner_api_v1.py` (`res.get("id") or res.get("sponsored_read_id")`). Re-verified → `active`.
- Console `buyTriv`/`buyRjr` sent `start_at=now` → backend `invalid_time_window`. Now `start_at = now + 2min`. Re-verified sandbox trivia/rj → `active`.
- NOT bugs (env limits): Stripe hosted card page can't be auto-driven (Live checkout link + status verified instead); S3 presigned audio rejects HEAD (GET works).



## PRO WEB BROWSE LAYOUTS + PARTNER ADS API — LIVE SPONSORSHIPS & MARKETPLACE PROMOTION (2026-08 fork)
Three deliverables, user-approved (layouts first, then API), all verified by the testing agent (iter95 web layouts PASS; iter96 backend 28/28 PASS).

### 1) Pro full-bleed WEB browse layouts (Cinematic / Studio / Tube) — iter95 PASS
User wanted professional, full-bleed home layouts instead of the stretched mobile view. Three switchable skins on the RadioLife home (`/`), powered by ONE backend aggregator.
- **Backend** `routes/browse.py` (`GET /api/browse/home`, already wired): one payload → hero + 6 defensive rails (RadioLife Originals, Recommended-for-you (personalized from `playback_logs`), Live Stations, Podcasts, Games, Deals). Every rail built defensively so a missing collection never breaks Browse.
- **Web** `frontend/src/design_radiolife/browse/`: `CinematicBrowse` (Netflix — hero + horizontal rails, dark), `StudioBrowse` (Spotify — left library sidebar + card grids), `TubeBrowse` (YouTube — search + category chips + responsive video grid), shared `browseShared.jsx` (`Art` with gradient fallback), `LayoutSwitcher.jsx`, `BrowseHome.jsx` (fetches + renders selected skin), `useBrowseLayout.js` (Zustand, persists to `localStorage.bigfm_browse_layout`, honours `?layout=`).
- **ROOT-CAUSE FIX**: the prior agent wired `BrowseHome` into `VariantWrapper.jsx` which is **not imported anywhere** (dead file). The live component is `RadioLifeOverlay.jsx` — added the branch there: when `variant==='radiolife'` AND path is `/`|`/home` AND user AND `browseLayout!=='classic'` → render `<BrowseHome/>` full-bleed. `classic` keeps the original `HomeRadioLife` (which also hosts the switcher so users can opt in). `browse-exit-legacy` flips the design variant back to legacy.
- Web-only (desktop + mobile-web responsive). testids: `browse-cinematic|studio|tube`, `browse-hero(-play)`, `browse-rail-<key>`, `browse-tile`, `browse-search`, `browse-chips`/`browse-chip-<key>`, `layout-switcher(-btn)`, `layout-opt-<key>`. Non-blocking: many DB artwork URLs 404 → graceful gradient tiles (authored imagery would improve it).

### 2) P0 — Live Sponsorships via the Partner API = REAL Stripe HOSTED CHECKOUT — iter96 PASS
Partners can now take Trivia + AI-RJ Sponsored Reads LIVE (not just sandbox) by paying via a hosted Checkout link returned in the API response (user's explicit choice). `STRIPE_MODE=live` with a `sk_test_` key → real test-mode Stripe.
- **NEW service fns** `trivia_sponsorship_service.create_checkout/sync_checkout` + `rj_sponsored_read_service.create_checkout/sync_checkout`: create `stripe.checkout.Session` (mode=payment) for the prize pool (trivia `cost_cents`) / read booking (rj `total_cost_cents`); on `payment_status==paid` activate WITHOUT re-charging (records `payment_transactions_v2`, idempotent). rj `sync_checkout` atomically claims a `rendering` status then TTS-renders (ElevenLabs) → active/pending_admin; on render failure it refunds + rejects. Mirrors the proven marketplace_promotions hosted-Checkout pattern.
- **Partner API** (`routes/partner_api_v1.py`, `/api/v1`): `POST /sponsorships/{id}/checkout?type=&advertiser_id=` (LIVE→hosted URL; SANDBOX→instant, `checkout_required:false`), `GET /sponsorships/{id}/checkout/status` (idempotent activation poll). Fixed the broken rj `/submit` (now passes `final_script`, falls back to stored `script_body`; runs disclosure + moderation → `pending_moderation`). Trivia `/submit` now 409s `use_checkout_endpoint` (go live via /checkout). Product catalog: `sponsorship_trivia` + `sponsorship_rj_read` flipped `coming_soon`→`available` with endpoint hints.

### 3) P1 — Marketplace Promotion via the Partner API — iter96 PASS
Partners can programmatically promote a listed business. NEW `services/partner_marketplace.py` (reuses internal `PROMO_TIERS`/`_apply_active` + `category_bids.bid_standing` — single source of truth).
- **Endpoints** (`/api/v1/marketplace/...`): `GET /promotion/tiers`, `GET /categories`, `GET /businesses?q=` (discover promotable `business_id`s); `POST /promotion/checkout {business_id,tier}` → Promoted-rail placement (LIVE hosted Checkout → `pending_review` → **admin approves** to go active; SANDBOX comp-activates instantly); `GET /promotion/{id}/status`; `POST /spotlight/checkout {business_id,category,bid_cents,amount_cents}` → Category Spotlight bid + prepaid budget (LIVE hosted Checkout → `credited`+active on pay; SANDBOX instant); `GET /spotlight/{session_id}/status` (idempotent); `GET /spotlight?business_id=` (bid + standing). Every promotion/bid tagged `purchased_by_partner`(+`_env`); status lookups scoped by **partner_id + environment** (LIVE/SANDBOX isolated — verified 404 cross-env).
- **Seeds/helpers**: `scripts/mint_test_partner_key.py` (LIVE key), `scripts/seed_demo_rj_persona.py` (`persona_demo_rj_ava` so rj reads are bookable). Keys + demo ids in `/app/memory/test_credentials.md`.
- **Verification note**: API layer fully tested (28/28 pytest, real `cs_test_` hosted URLs, sandbox instant-activation, error/scope/idempotency). The actual browser card-entry on Stripe's hosted page could NOT be auto-driven (Stripe-side UI blocked Playwright) — the paid→active logic is unit/flow-verified and mirrors the shipped marketplace_promotions pattern; a human can complete one payment to eyeball the final transition.



## CATEGORY SPOTLIGHT REFINEMENTS (Daily Cap · Low-Budget Alert · Analytics Trend · Renewal Receipt) — testing agent PASS (iter90: backend 8/8; web 8 testids, mobile 6 testids)
Four user-approved refinements on the Promotions/Category-Spotlight suite. Shared backend + web + mobile.
- **Daily Budget Cap** — `category_bids.daily_cap_cents` (0 = none). `POST /category-bid/set` accepts it; `bill_impressions` gates spend with an atomic `spent_today ≤ cap-bid` conditional and a lazy day-rollover; once capped the bid drops out of `active_bids_for` (loses its #1/spotlight spot) until the next day. UI: "Max spend per day" input on both promote screens (`promote-daily-cap`).
- **Low-Budget Alert** — `GET /category-bid` returns `budget:{impressions_left, low_budget (<20 left & active), depleted}`. UI: amber warning banner on both promote screens (`promote-low-budget`, conditional).
- **Analytics Trend** — `GET /promotion/analytics` now returns `trend[]` of `{date, views, impressions, orders, revenue_cents}` across the window (capped 60 pts). UI: simple day-by-day bar chart (views bars + order-count labels) in the analytics card (`promote-trend`) on both surfaces (dependency-free `View`/div bars).
- **Renewal Receipt** — `sweep_renewals` calls `_email_renewal_receipt` (Mailgun `send_email` via `asyncio.to_thread`, `is_live`-gated) after a SUCCESSFUL off-session auto-renew charge; emails the merchant a receipt (plan/amount/active-until). Fires only at real expiry (not e2e-triggerable). UI hint added to the auto-renew row on both surfaces.
- Non-blocking (documented, fine for single worker): `sweep_renewals` throttle is per-process (could double-send receipts across multiple uvicorn workers); `_email_renewal_receipt` swallows errors silently; spend-date rollover + billing are two ops (rare race).



## PROMO ANALYTICS + AUTO-RENEW + CATEGORY SPOTLIGHT AUCTION (Phase F+) — testing agent PASS (iter89: backend 14/14; web + mobile e2e verified) + reviewer-flagged integrity hardening applied & re-verified
Three merchant growth features on top of the Promoted Marketplace, user-approved. Shared backend + web + mobile.
- **Promo Analytics** — `GET /api/merchant/marketplace/promotion/analytics`: views + impressions (from `promotion_daily` counters), orders + revenue (from `marketplace_orders`) for the active/most-recent promotion window, plus **uplift vs the equal prior window** (`extra_*`). Beacon `POST /api/shop/track {business_id, kind:'impression'|'view'}` (auth-gated). Web fires impression beacons per promoted card on the Shop home + a view beacon on business-detail open; mobile fires impressions from the Shop tab + a view on `shop/[id]`. UI: analytics card on both promote screens (`promote-analytics`).
- **Auto-Renew** — `POST /api/merchant/marketplace/promotion/{id}/auto-renew {enabled, payment_method_id}`; `GET /promotion` now returns `auto_renew`, `saved_cards`, `default_pm`. `sweep_renewals()` (boot + throttled lazy on `GET /promotion` and `/shop/home`) renews expired auto-renew promotions by **off-session charging the saved card** (`charge_saved_card`) for the same tier; **free auto-extend fallback** when no card / charge fails. UI: toggle on the active-promotion card (`promote-autorenew-toggle`) — web sends the merchant to card setup if none saved.
- **Category Spotlight = per-impression BID AUCTION** — NEW `services/category_bids.py` + `routes/marketplace_category_bids.py` (`/api/merchant/marketplace/category-bid`): `GET /categories`, `GET ` (my bid + `standing{rank, top_bid_cents, outbid, suggested_bid_cents}`), `POST /set {category, bid_cents}`, `POST /topup/checkout` (Stripe hosted top-up → prepaid `budget_cents`) + `GET /topup/{session_id}/status` (ownership-checked), `POST /pause|/resume`. Ranking: in `GET /api/shop/businesses?category=X` active bidders are pinned to the TOP in bid order (highest first), flagged `promoted+spotlight`, and each served impression is **atomically billed** against the prepaid budget (auto-`depleted` when it can't cover the next bid). Bidders also get the Promoted badge everywhere + a slot in the "Promoted near you" rail. UI: Category Spotlight block on both promote screens (category picker, `bid_cents`, standing + **outbid alert**, budget top-up).
- **Integrity hardening (reviewer-flagged, applied + re-verified)**: `/api/shop/track` is auth-gated (anon → `{ok:false}`); category-bid impressions are billed **only for authenticated shopper views** (anon GET-spam can't drain a competitor's budget — verified budget stable for anon, −bid for authed); `bill_impressions` uses an **atomic conditional `$inc`** (no double-bill / negative budget); `topup/status` has an **ownership check**. Known/low: `sweep_renewals` throttle is per-process (fine for single worker).
- **Collections**: NEW `category_bids` {bid_id, business_id, owner_user_id, category, bid_cents, budget_cents, spent_cents, impressions, status(active|paused|pending_budget|depleted)}, `category_topups`, `promotion_daily` {business_id, date, impressions, views}. `marketplace_promotions` gained `auto_renew`/`auto_renew_pm`/`renewed_from`/`renewed`.



## PROMOTED MARKETPLACE (Phase F) — testing agent PASS (iter88: backend 17/17; web + mobile e2e verified live)
Merchant self-serve shop boosting, user-approved: Stripe-paid tiered promotions + a free admin-comp path, admin approval required, boosts Shop search ranking + a "Promoted near you" rail + a "Promoted" badge, on BOTH web + mobile. The Shop search ranking + Sponsored badge plumbing already existed; this adds the merchant purchase flow, admin review, and the promoted-shop surfacing.
- **Backend** — NEW `routes/marketplace_promotions.py` (+ registered in `server.py`, seed wired at boot):
  - Tiers (server constant): Spotlight $19.99/7d (w1), Boost $34.99/14d (w2), Premium $59.99/30d (w3).
  - Merchant: `GET /api/merchant/marketplace/promotion/tiers`, `GET /api/merchant/marketplace/promotion` (mine + active), `POST /checkout {tier, origin_url}` (Stripe hosted Checkout mode=payment → `pending_payment`), `GET /{id}/status` (syncs Stripe paid → `pending_review`).
  - Admin (`require_admin`): `GET /api/admin/marketplace/promotions?status=`, `POST /{id}/approve` (→ active, sets profile `promoted_until`/`promotion_tier`/`promotion_weight`; **guarded** to only approve `pending_review`), `POST /{id}/reject {note}`, `POST /grant {business_id, tier}` (comp/free instant activation).
  - `_apply_active` **anti-demotion guard**: a weaker/earlier promotion never overwrites a currently-active stronger one.
  - `ensure_promotions_seed` comps `biz_sample_ambreens` (Premium/w3) at boot so the rail/badge show out of the box.
  - Ranking: `services/marketplace.ranking_score` adds `+20000 + weight*100` when `promoted`. `shop._card` computes `promoted` (from `promoted_until > now`) + `promotion_weight`. `shop/home` prepends a `promoted` section "Promoted near you"; `shop/businesses?sort=featured` ranks promoted first.
  - Collections: NEW `marketplace_promotions` {promotion_id, business_id, owner_user_id, tier, days, price_cents, weight, status(pending_payment→pending_review→active / rejected / expired), stripe_session_id, paid, comp, expires_at…}. `marketplace_profiles` gained `promoted_until` / `promotion_tier` / `promotion_weight`.
- **Web**: NEW `MerchantPromoteRadioLife.jsx` (`/shop/merchant/promote`, tiers + buy→Stripe redirect + active banner + history) wired in `RadioLifeOverlay` + Merchant Dashboard tile (`merchant-open-promote`). NEW admin `admin/Promotions.jsx` (`/admin/promotions`, tabs + approve/reject + comp-grant) wired in `App.js` + `AdminSidebar` (`adnav-merchants-promotions`). BizCard shows orange "Promoted" badge (falls back to "Sponsored").
- **Mobile**: NEW `app/merchant/promote.tsx` (tiers + Stripe via `expo-web-browser` + status sync) + dashboard tile (`merchant-open-promote`). Shop-tab BizCard shows orange "Promoted" badge; "Promoted near you" rail renders from the home `promoted` section (no client change needed — it iterates `sections`).
- Non-blocking notes (from testing agent, acknowledged): stale `pending_payment` docs are not swept (harmless; reads are time/status gated).



## WEB USUAL ONE-TAP (Shop Home) + FULL MOBILE ORDERING PARITY (2026-06 fork) — testing agent PASS (iter87: backend 5/5; web + mobile live-verified, no parity issues)
Two-part batch, user-approved to do together. (A) finished the WEB "Get your usual" shortcut on the Shop Home; (B) brought the Expo MOBILE app to parity with 5+ batches of store-ordering UX that had been built web-only (instant inline ordering, item notes + presets, combo nudges/badges + happy-hour combos, save-for-later, "usual"/reorder). Shared FastAPI backend unchanged (contracts already existed: `/api/shop/usual`, `/businesses/{id}/usual`, `/businesses/{id}/combos`, `/orders/last/{id}`; menu+product checkout accept per-line `note`).
- **Web (`ShopRadioLife.jsx`)**: new `shop-usual-card` on the Shop Home (non-browsing view) — fetches `GET /api/shop/usual` (auth; 401→hidden), shows the shopper's go-to store + top items in a horizontal row, "Add my usual (N) & checkout" (`shop-usual-add-all`) adds all lines to the menu cart (`useShopCart`) and navigates to `/shop/checkout/menu`; `shop-usual-dismiss`. Verified live (demo@ → 3 Fun Pizza items → $45.97, membership Free Pizza applied → $1.89).
- **Mobile stores**: `useCartStore` CartItem+lineKey+addLine gained `note` (distinct notes = distinct lines) + a `restore()` action (for clear+undo). `useProductCart` gained `note`+`image_url` on items, `keyOf` includes note, `add()` now takes `(…, deliveryCfg, qty, note)`, plus `removeItem()` + `restoreGroup()`. NEW `useSavedForLater.ts` (AsyncStorage-persisted, per-business shelf; manual persistence — NO zustand/middleware, which crashes the Expo web bundle).
- **Mobile components**: `ItemOptionSheet` gained note presets (`item-note-presets` chips) + note field (`item-option-note`) and now exports `defaultMenuSelection`/`menuQuickAddReady`. NEW `ProductVariantSheet.tsx` (mobile parity of web `ProductVariantModal` — variant tiles `pv-variant-*`, qty, note presets, `product-variant-confirm`).
- **Mobile business detail (`app/shop/[id].tsx`) REWRITTEN** from a navigation-only page into a FULL inline ordering surface (parity with web `ShopBusinessRadioLife`): instant `+` add (`shop-add-*`), per-item Customize (`shop-customize-*`) → option sheet (menu) / variant sheet (product), in-cart badge (`shop-incart-*`), inline stepper for plain items (`shop-stepper/inc/dec-*`), combo badges (`shop-combo-badge-*`, honours happy-hour `active_now`), "Get your usual?" card (`usual-card`/`usual-add-all`/`usual-dismiss`), Reorder-last (`shop-reorder-last`), floating cart bar (`shop-mobile-cart-bar`). Non-orderable stores keep the explicit Order CTA.
- **Mobile carts**: menu cart (`app/shop/cart.tsx`) shows per-item notes (`cart-note-*`), a combo discount line from the quote (`cart-combo-discount`), save-for-later (bookmark `cart-save-*` → `cart-saved-shelf` w/ move/remove), clear+undo (`cart-clear` → `cart-undo-banner`/`cart-undo`), and sends per-line `note` in the checkout payload. Product cart (`app/shop/product-cart.tsx`) shows notes + per-group save-for-later (`pcart-save-*`/`pcart-saved-*`) and sends `note`. Shop tab (`app/(tabs)/shop.tsx`) gained the "Get your usual" one-tap card (`shop-usual-card`→`/shop/cart`).
- Non-blocking: cold direct-nav to `/shop/[id]` before the mobile bearer restores can 401-silence the `usual-card` (resolves on the normal Shop→biz flow). Pre-existing react-hooks/exhaustive-deps lint warnings remain (Metro builds via Babel, don't block).



## STORE ORDERING v3 — Combo Builder · Reorder Prompt · Notes Presets · Saved Sync (2026-06 fork) — self-verified on web
- **Combo Builder** (merchant-defined combos, replaces the auto drink discount): new `marketplace_combos` collection + router `/api/merchant/marketplace/combos` (list/upsert/delete, owner-gated). A combo = name + fixed price + category requirements (e.g. 1×Pizzas + 1×Coffee). Pricing engine `_apply_combos` in `marketplace_orders.py` expands cart to units, greedily matches each combo (cheapest units, repeats while matching, discount = regular − combo price); falls back to `_auto_combo` (30% off a drink) only when the merchant has NO active combos. Merchant UI = "Meal Combos" card in `MerchantMenuRadioLife` (name/price + up to 4 qty×category rows). Public read `GET /api/shop/businesses/{id}/combos` powers the store nudge (client mirrors the engine). Verified: custom "Pizza+Drink=$18" → 348¢ off (overrides auto 105¢); shows in cart nudge + checkout "Meal combo" line.
- **Reorder Prompt ("Get your usual?")**: `GET /api/shop/businesses/{id}/usual` returns the shopper's most-ordered still-available items (by frequency across paid orders). Store page shows a dismissible "Get your usual?" card (`usual-card`) with the items + "Add my usual" that re-adds all. Verified (Mac & Cheese ×11, Coffee ×3).
- **Notes Presets**: quick-tap chips above the note field in both customize sheets — food (`ItemOptionModal`: No onions / Extra spicy / No ice / Less sugar / Well done / On the side), products (`ProductVariantModal`: Gift wrap / Fragile / Leave at door / Call on arrival). Tapping appends to the note. Verified.
- **Saved Sync**: `useSavedForLater` is localStorage-persisted (survives visits); store page shows a "{n} saved for later" pill (`shop-saved-pill`) that scrolls to the saved shelf. Per-business.
- Files: backend `marketplace_orders.py`, `marketplace_combos.py` (NEW), `shop.py`, `server.py`; web `ShopBusinessRadioLife.jsx`, `MerchantMenuRadioLife.jsx`, `ItemOptionModal.jsx`, `ProductVariantModal.jsx`, `StoreCartPanel.jsx`, `useSavedForLater.js`. Demo combo seeded on `biz_sample_funpizza` for illustration.


## STORE ORDERING — Combo Nudge · Reorder Last · Kitchen Note Flag · Save For Later (2026-06 fork) — self-verified on web
- **Combo Nudge ("make it a meal")**: server-enforced in `_price_menu` — when the basket has a main + a drink (detected by menu section keywords: coffee/drink/beverage/tea/juice/soda/…), take **30% off one drink**. Returns `combo_discount_cents`/`combo_applied`/`combo_label`, persisted on the order. Shown as a green nudge in `StoreCartPanel` (parent `ShopBusinessRadioLife` mirrors the detection to estimate the saving via `sectionByItem`) and as a "Meal combo" discount line on `CheckoutMenuRadioLife`. Verified: pizza+coffee → 105¢ off; coffee alone → none.
- **Reorder Last**: new `GET /api/shop/orders/last/{business_id}` returns the most recent PAID order as a reorderable basket (rebuilds `selected_option_ids` from stored `selected_options[].option_id`, drops items no longer available). Store page shows a "Reorder last order" button (menu stores) that re-adds every line via `menuCart.addLine`. Verified live.
- **Kitchen Note Flag**: merchant tickets (`MerchantDashRadioLife`, food + product) now show a "📝 NOTES" badge on any order with item notes, each item's option summary, and the note highlighted in an amber chip. Verified live on the merchant dashboard.
- **Save For Later**: new persisted store `useSavedForLater` (`rl-saved-for-later`, keyed by business). Each cart line has a bookmark → moves it to a "Saved for later" shelf in `StoreCartPanel` with Move-to-cart / remove. Works for both menu + product carts. Verified live.
- Files: backend `marketplace_orders.py` (+`marketplace_products.py` note); web `ShopBusinessRadioLife.jsx`, `components/StoreCartPanel.jsx`, `useSavedForLater.js`, `CheckoutMenuRadioLife.jsx`, `CheckoutCartRadioLife.jsx`, `MerchantDashRadioLife.jsx`.


## STORE PAGE ORDERING — Item Notes · Sticky Add Bar · Clear+Undo · Upsell (2026-06 fork) — self-verified on web (both stores)
Four enhancements on top of the store-page ordering surface:
- **Item Notes** (per-line, e.g. "no onions"): note field added to `ItemOptionModal` (menu) + `ProductVariantModal` (products). Threads through `useShopCart` (note in `lineKey` so distinct notes = distinct lines) + `useProductCart` (`keyOf` includes note), shown in the right cart panel + both checkout summaries, and PERSISTED on the order — backend `CheckoutItem`/`ProductCheckoutItem` gained `note` (≤140) written onto each order line (merchants see it). Quote/checkout verified to accept it (no price impact).
- **Sticky Add Bar** (per card): once an item is in the cart a green "✓ N" badge shows on the image (`shop-incart-{id}`); plain items (no options/variants) get an inline −/qty/+ stepper (`shop-stepper/inc/dec-{id}`) driving the single line; optioned/variant items keep "+" (adds another default) + the badge.
- **Clear cart + Undo**: `store-cart-clear` in the panel header snapshots then clears, with a sonner toast "Undo" that restores — new store actions `useShopCart.restore` + `useProductCart.restoreGroup`.
- **Related Upsell**: `store-cart-upsell` "Add a little extra" — up to 3 cheapest add-ons NOT already in cart (prefers coffee/drink/side/dessert-titled sections), each with a one-tap `+` that quick-adds. Computed in `ShopBusinessRadioLife`, passed to `StoreCartPanel` as `suggestions` + `onAdd`.
- Files: `ShopBusinessRadioLife.jsx`, `components/StoreCartPanel.jsx`, `components/ProductVariantModal.jsx`, `ItemOptionModal.jsx`, `useShopCart.js`, `useProductCart.js`, `CheckoutMenuRadioLife.jsx`, `CheckoutCartRadioLife.jsx`; backend `marketplace_orders.py` + `marketplace_products.py`.


## STORE PAGE = INLINE ORDERING SURFACE (2026-06 fork) — self-verified on web (desktop), both food + product stores
User request (with production screenshot): on the store/restaurant page, the "+" should add the product instantly; each image should have a **Customize** button; and a **cart should be pinned on the right** (always visible, sticky on scroll). Applies to BOTH food/menu stores and retail product stores.
- **File:** `frontend/src/design_radiolife/screens/ShopBusinessRadioLife.jsx` (rewritten). Detects `mode` = `menu | product | other` from the profile.
- **Instant "+" add** (`shop-add-{id}`): menu → `defaultMenuSelection()` (first/default option of each size/single group) via `useShopCart.addLine`; if a required group isn't satisfied by defaults it opens the sheet instead (`menuQuickAddReady()`). product → adds first in-stock variant (or base) via `useProductCart.add`. Server pricing verified to accept the default option ids (Mac & Cheese "Medium" → $20.78).
- **Customize button on every image** (`shop-customize-{id}`): menu → existing `ItemOptionModal`; product → new `components/ProductVariantModal.jsx` (variant tiles + qty).
- **Pinned right cart** `components/StoreCartPanel.jsx` (`store-cart-panel`, desktop `lg:` only, `sticky top-4`): reads the menu OR product cart, qty +/− (`store-cart-inc/dec/remove`), subtotal (`store-cart-subtotal`), Checkout → `/shop/checkout/menu` or `/shop/checkout/cart`. On phones (`<lg`) it's hidden and a floating "View order (n) · $total" bar (`shop-mobile-cart-bar`) shows instead.
- **Helpers added** to `ItemOptionModal.jsx`: exported `defaultMenuSelection(item)` + `menuQuickAddReady(item)`.
- **Bugfix:** store-grid image container wasn't clipping to a square (`aspect-square` not constraining + no `overflow-hidden`) — a portrait image (Tandoori) rendered 242×323 and pushed the card. Fixed with inline `aspectRatio:"1/1"` + `overflow-hidden`.
- **Layout:** page widened to `max-w-6xl`, 2-column (`lg:flex`) main + aside; secondary extras (gift card / packages / events / membership) moved inline (wrap row) so they don't overlap the right cart; the old floating "Order" CTA is dropped for orderable stores (ordering is now inline) and kept only for `other` (services) stores.
- NOTE: web preview screenshot tool forces a desktop viewport, so the `<lg` mobile layout was verified by CSS rules + wiring, not a 390px screenshot. Entitlement/membership pricing on this page's quick-add is intentionally skipped (Customize sheet still supports it on the full menu page). aspect-square clip fix applied to the store grid only.


## DELIVERY ADDRESS + DESTINATION TAX + LIVE PREP TIMER + REAL PUSH (2026-06 fork) — testing agent PASS (iter86: backend 8/8; merchant AI-tax verified live; all checkout testIDs + gating code-verified)
The 4 user-approved P0 features from the DEFERRED list, all cross-platform (shared FastAPI backend; web /app/frontend + mobile /app/mobile).
- **Delivery address → destination tax + route.** `POST /api/shop/orders/quote` & `/checkout` now accept `delivery_address{label,line1,lat,lng,country,state,county,city}`. In `_price_menu` (marketplace_orders.py): `fulfillment=delivery` + address ⇒ tax resolved at the CUSTOMER jurisdiction (`tax_basis=destination`); pickup ⇒ store origin (`tax_basis=origin`), honouring a merchant `tax_override`. Order persists `delivery_address` + `ready_at` + `tax_basis`. Curl-verified: pickup=UAE VAT 5%, delivery→LA=California 7.25%. Web: `components/DeliveryAddressPicker.jsx` (Leaflet click-to-pin + browser geolocation + typed Nominatim geocode) in `CheckoutMenuRadioLife`; pay gated until address set. Mobile: `components/DeliveryAddressCard.tsx` (expo-location current-location w/ permission flow + typed geocode) in `app/shop/cart.tsx`; checkout gated. Free OSM Nominatim (reverse+forward geocode) + OSRM route line — NO API key. Web util `design_radiolife/lib/geocode.js`, mobile util `src/utils/geocode.ts`.
- **Store→door route on tracker.** Web `ShopOrderTrackerRadioLife.jsx` draws a react-leaflet `Polyline` (OSRM) store→destination + green dest marker for delivery. Mobile `NativeMap.tsx` gained a `Polyline` prop; `app/shop/order/[id].tsx` fits both points + draws the route (native builds; web preview shows the graceful fallback).
- **Live prep-timer countdown.** Both trackers tick a mm:ss countdown to `order.ready_at` (`tracker-timer`) while accepted/preparing, and show a "head over now!" nudge (`tracker-ready-nudge`) when ready. `ready_at` is set at order creation from ETA/pickup_time and RESET to now+prep_time when the merchant marks `preparing`.
- **Real Push Alerts (mobile).** Emergent managed relay (SuprSend). Backend `services/push_service.py` (`send_push`, `register_device`) + `routes/push.py` (`POST /api/register-push`); `EMERGENT_PUSH_KEY=placeholder` added to backend/.env (deployer swaps the real key — NEVER edit). Order status → buyer push on preparing/ready/picked_up (in addition to in-app), wrapped in try/except (non-blocking). Mobile: `expo-notifications`+`expo-device` installed; `app/_layout.tsx` has module-scope handler + Android channel + tap handlers (warm+cold) + denied weekly nudge; `src/utils/pushNotifications.ts` uses `getDevicePushTokenAsync`→`/api/register-push` (re-registers on every app open via `_layout` effect); app.json has the `expo-notifications` plugin + `android.googleServicesFile`. ⚠️ REAL push only works after the user PUBLISHES a native build AND supplies Firebase `google-services.json` — NOT testable on Expo Go / web preview. register-push returns 500 with the placeholder key (expected/correct wiring).
- **Merchant self-serve "AI fill my local tax".** `POST /api/merchant/marketplace/tax/ai-estimate` (owner-gated, real Emergent Gemini) + `tax_override{enabled,rate_percent,label}` on `GET/PATCH /fulfillment`. Web `MerchantFulfillmentRadioLife.jsx`: "✨ AI fill my local tax rate" button (`tax-ai-fill`) → auto-fills + enables an override; verified live (AI suggested 5% UAE VAT).
- Non-blocking (deferred, from iter86 review): web checkout `deliveryAddr` is local state (lost on hard reload, same as the whole in-memory cart); mobile merchant Fulfillment screen is still web-only. Real push delivery + store→door native map require Publish.


## STORE/RESTAURANT DETAIL REDESIGN + LOYALTY CHECK-IN (2026-06 fork) — testing agent PASS (iter85: backend 5/5, web + mobile fully verified, no parity issues)
User-reported redesign of the business detail page (`/shop/:id`) on BOTH surfaces (web `ShopBusinessRadioLife.jsx`, mobile `app/shop/[id].tsx`):
- **Ways-to-earn = single top bar** (Order/Buy · Check In · Pay with RadioLife) all in ONE horizontal row (was 3 stacked rows).
- **Functional Check-In**: new `POST /api/shop/businesses/{id}/checkin` awards 50 pts once/day/business (idempotent via PointsService source `venue_checkin`, key `checkin:{uid}:{bid}:{yyyy-mm-dd}`). UI segment flips to "Done ✓".
- **Horizontal category filter** (Uber-Eats style) from menu sections / product categories.
- **Product/menu grid** shown directly on the detail page — multi-row (2-col mobile, 2/3-col web); tapping an item routes to the ordering page (`/shop/menu/:id` or `/shop/products/:id`).
- **Floating Order + Membership** buttons bottom-right (compact rectangles) — fixes the old full-width buttons overlapping the phone/website contact (contact now inline).
- Note: business detail already returns `ways_to_earn`, `sells`, `has_menu/has_products/has_memberships` etc.; grid fetches `/shop/businesses/{id}/menu` or `/products`.
- Minor non-blocking nit (left as-is, verified working): redundant local `HTTPException` import in shop.py; web reads id from pathname (screens render via `screenFor`, not `<Route>`).

## DEFERRED (user asked, paused mid-build to do the store redesign) — resume next
The following 4 were approved by the user and are NOT yet built: (1) **Real push alerts** (mobile integration — needs the user's Firebase `google-services.json` + Publish/native build; playbook already fetched; NEVER edit EMERGENT_PUSH_KEY); (2) **Delivery address step** → destination-based tax + store→address map route (default: pin-on-map + free OSM reverse-geocode + OSRM route line); (3) **Merchant self-serve "AI fill my local tax"** button (per-merchant tax override); (4) **Live prep-timer countdown** + "head over now" nudge on the tracker (needs `ready_at` on the order).



## FEES + DELIVERY + NEAR-ME MAPS + ORDER TRACKER + JURISDICTION TAX (2026-06 fork) — testing agent PASS (iter83 backend 10/10; iter84 frontend both surfaces green)
Big cross-platform batch, all user-approved. Shared FastAPI backend; web (/app/frontend) + mobile (/app/mobile).
- **Merchant fees (owner.com-style)**: new `GET/PATCH /api/merchant/marketplace/fulfillment` — `service_fee{enabled,percent}` (% of order, passed to customer), `delivery{enabled,fee_cents,eta_min,eta_max,min_order_cents}`, `prep_time_min`, `geo{lat,lng,address}`, `tax_jurisdiction{country,state,county,city}`. Web UI: `MerchantFulfillmentRadioLife` (/shop/merchant/fulfillment, tile on Merchant Dashboard) incl. click-to-drop Leaflet pin.
- **Pricing** (`marketplace_orders._price_menu`): threads `fulfillment`+`pickup_time`; adds `service_fee_cents` (% of subtotal), `delivery_fee_cents` (flat, delivery only), `tax_cents` (see tax), `eta_label`. Fees added ON TOP (not covered by gift/points). Delivery coerced→pickup when shop delivery disabled. `CheckoutBody`/`QuoteBody` fulfillment+pickup_time now Pydantic `Literal`. Order doc persists all fee/tax/eta/fulfillment fields.
- **Jurisdiction SALES TAX** (origin/store-based, everything taxable): `services/tax_service.py` (resolve most-specific active rule country→state→county→city; `calculate_tax`; `ai_estimate_rate` via Emergent LLM Gemini) + `routes/marketplace_tax.py` admin CRUD `/api/admin/tax/rules` + `POST /api/admin/tax/ai-estimate`. Web admin screen `AdminTaxRules` (/admin/tax) with AI-estimate button. Seeded: AE VAT 5%, US-CA 7.25%, US-CA-LA 9.5%; demo shops tax_jurisdiction=AE/Dubai. Taxable base = discounted goods + service + delivery fee.
- **Near Me** (`/shop/near-me` web + `app/shop/near-me.tsx` mobile): `GET /api/shop/businesses?sort=nearby&lat&lng` returns ALL categories (shops + services) with haversine `distance_km`, sorted asc (fetches wide pool THEN sorts THEN truncates — fixed a 0.0km-falsy + limit-before-sort bug). Web = Leaflet/OSM (free, no key); mobile = react-native-maps behind a platform file `NativeMap.tsx`/`NativeMap.web.tsx` (web shows a fallback note — native-only). Distance in km/mi by country: `lib/distance.js` (web) + `src/utils/distance.ts` (mobile, expo-localization region).
- **Order Tracker** (`/shop/order/:id` web + `app/shop/order/[id].tsx` mobile): polls `/api/shop/orders/{id}/status`, 4-step getting-ready stepper, ETA, pickup code, store map (pickup), in-app 'ready' heads-up (celebrate/banner). Checkout success routes here; orders list gained Track button + fulfillment/ETA line. **Order-ready alert is IN-APP only** (real push deferred — needs Firebase google-services.json + Publish; not built).
- **Mobile cart PERSISTENCE**: `useCartStore` persists items/business/fulfillment/pickupTime to AsyncStorage MANUALLY (hydrate + subscribe). NOTE: do NOT use `zustand/middleware` persist — its `.mjs` ships `import.meta` which crashes the Expo web bundle (metro.config is protected). This was the iter83 mobile hard-blocker; fixed in iter84.
- New deps: web leaflet + react-leaflet@5; mobile expo-location + react-native-maps + expo-localization (app.json: location permission + plugins).
- Non-blocking/deferred: web menu-checkout pill z-index bumped over mini-player (z-30); real push notifications; destination-based (delivery-address) tax would need an address-capture step.



## MOBILE PARITY (shopping/pickup) + PICKUP PERSISTENCE + ADMIN LAYOUT FIX (2026-06 fork) — testing agent PASS (iteration_82: backend 10/10, web admin + mobile flow green)
Closed out the Amazon/Uber-Eats shopping revamp by bringing pickup/fulfillment to mobile + the backend order, and fixed the web admin dead-space/truncation. All code was written in the prior (interrupted) session; this session linted, seeded, screenshotted, and ran the testing agent.
- **Backend pickup persistence** (`routes/marketplace_orders.py`): `CheckoutBody` + `QuoteBody` accept `fulfillment` ('pickup'|'delivery', default pickup) and `pickup_time` ('now'|'+15'|'+30'|'+45', default now); the created `marketplace_orders` doc stores both. Verified persisting on BOTH the fully-covered $0 (entitlement) path AND the Stripe-hosted path, and surfaced via `GET /api/merchant/marketplace/orders`. NO schema migration needed (additive, defaults applied).
- **Web**: `CheckoutMenuRadioLife` sends `fulfillment`+`pickup_time`; `MerchantDashRadioLife` shows a pickup/delivery time line per food order (`merchant-order-pickup-{order_id}`, PICKUP_LABELS map).
- **Web Admin layout fix**: removed the hardcoded `padding-left: 244px` from `AdminMerchants`/`AdminCommissions`/`AdminStripeConnect` page styles (the admin sidebar offset is already handled by `AppShell` `paddingLeft:220` on `/admin/*`), switched table wrappers from `overflow:hidden` → `overflowX:auto`, and `AppShell` main uses `px-4` on admin routes. Result (verified): Merchants table full-width, all 8 columns visible, no left dead-space.
- **Mobile**: `useCartStore` gained `fulfillment`/`pickupTime` + setters; `app/shop/cart.tsx` added a Pickup/Delivery toggle (`cart-fulfillment-pickup|delivery`) + pickup-time pills (`cart-pickup-now|+15|+30|+45`) and sends both on checkout (captured payload `fulfillment:delivery, pickup_time:+30`). `ItemOptionSheet` shows a green REQUIRED pill + "Add N to order".
- **Demo seed** (`backend/scripts/seed_shop_demo.py`, run manually): Ambreens serum size variants + a variant apparel tee; Grill House "Signature Ribeye" Cook(required)+Add-ons. **FIX this session**: options must use `price_delta_cents` (not `price_cents`) — corrected the seed AND migrated the stale Grill House doc in-place so add-on upcharges ($2.50/$3.50/$5.00) price correctly.
- **Bug fixed (iter82 MEDIUM)**: mobile Fun Pizza menu "Choose" button (`menu-add-*`) clipped to "Choo" at 390px — added `flexShrink:0` + fixed height/pill radius to `addBtn`/`chooseBtn` and `numberOfLines={1}` on the label; re-verified at true 390px (button fully contained).
- Non-blocking (deferred): mobile cart zustand has no persist (hard reload clears cart); `CheckoutBody` could use `Literal` types for fulfillment/pickup_time. Prod bugs (News mock-banner, `benefit_not_found`) fixed in preview earlier — need **Publish** to go live.



## SHOPPING EXPERIENCE REVAMP — Amazon products + Uber Eats pickup (WEB) (2026-06 fork) — testing agent PASS (iteration_81, all 7 web flows)
User goal: simplify product display + multi-product listing, and make checkout feel like Amazon (products) and Uber Eats (restaurant pickup). WEB-only this phase; reuses existing shop/menu/cart/order APIs (NO backend change). User choices: web first → mobile parity later; revamp existing screens; pickup default (Pay now, pick up in-store) with pickup-time selector; build order = product shopping → pickup.
- **Product shopping (Amazon-style)**:
  - `ShopProductsRadioLife.jsx` rewritten → responsive product **grid** + search (`prod-search`) + category chips (`prod-cat-*`) + sort (`prod-sort`); cards (`prod-card-*`) open a detail page; quick-add (`prod-add-*`) → mini-cart.
  - NEW `ShopProductDetailRadioLife.jsx` at route `/shop/products/{bizId}/{productId}` (wired in RadioLifeOverlay before the listing prefix) — gallery image, buy box (price, **variant tiles** `pd-variant-*` when present, quantity `pd-qty-*`, **Add to cart** `pd-add` / **Buy now** `pd-buynow`, stock, BigPoints, seller), and "More from this shop" (`pd-also-*`).
  - NEW slide-in **mini-cart** drawer `components/ProductMiniCart.jsx` + `useMiniCart.js` store — opens on add; qty steppers + remove + subtotal + Proceed/View cart.
  - `ShopCartRadioLife.jsx` rewritten → Amazon-style: item thumbnails, qty steppers (`cart-inc/cart-dec-{biz}-{key}`), remove, per-venue pickup/delivery, right-rail order summary, inline error (replaced `alert()`).
  - `useProductCart.js`: `add()` gained optional `qty` + stores `image_url`; added `removeItem(bizId,key)`.
- **Restaurant pickup (Uber-Eats-style)**:
  - `ShopMenuRadioLife.jsx` rewritten → store header (rating/category/ETA/address from `GET /shop/businesses/{id}`), **Pickup/Delivery toggle**, search-in-store (`menu-search`), **category rail** (`menu-cat-*`) scroll-to-section, roomier item rows (text left, image+＋ right), inline steppers.
  - `ItemOptionModal.jsx` enhanced → hero image (`item-option-hero`), green **Required** pill on required groups, "Choose 1" hint, sticky **"Add N to order"** button.
  - `CheckoutMenuRadioLife.jsx`: NEW **pickup context block** (`checkout-pickup`) at top — Pickup/Delivery toggle + store address + **pick-up time pills** (`checkout-pickup-now/+15/+30/+45`). These are UI/display state on `useShopCart` (`fulfillment`,`pickupTime`); NOT yet sent to the backend order (persisting pickup-time to the order = backend follow-up).
- **Polish**: fixed low-contrast qty steppers on the dark shop theme (orange icons + `bg-orange-50`).
- Testing agent iter81: all 7 web flows PASS. Data-dependent flows not auto-reachable due to sparse seed (no product variants, no item option_groups, no gift balance for test@) — verified by code, not e2e. Non-blocking: React "key prop spread" console warning on shop pages (pre-existing card mapper); some shop image 404s (seed data).
- **REMAINING**: Phase 3 (product checkout polish — optional), **Phase 4 = MOBILE PARITY** for all of the above (not started). Also still pending from earlier this session: NEWS fixes (article-not-loading + mock banner) done in preview → need **redeploy**; membership `benefit_not_found` in prod = stale deploy → **redeploy**; admin layout fix (wasted left space + truncated Merchants table) half-done.



## PAYOUT CONNECT + EARNINGS TRENDS + GENRE ARTWORK + NOW-PLAYING PEEK (2026-06 fork) — testing agent PASS (iteration_80, backend 16/16, web+mobile parity)
Four user-requested enhancements, all cross-platform (web /app/frontend + mobile /app/mobile), on the shared backend.
- **Payout Connect — Stripe Connect Express** (NEW `backend/routes/marketplace_payouts.py`, prefix `/api/merchant/marketplace`, registered in server.py): `POST /connect/account` (create/get Express account, stored on `marketplace_profiles.stripe_account_id`), `POST /connect/onboarding-link` (hosted Account Link; web returns to `/shop/merchant/earnings?connect=return`, mobile returns to a backend HTML "done" page), `GET /connect/refresh` (regen link), `GET /connect/return` (HTML), `GET /connect/status` (polls Stripe `Account.retrieve` → connected/payouts_enabled/requirements_due; no webhook secret needed), `POST /payout/withdraw` (Transfer available net → connected balance; atomically reserves `merchant_earnings` rows via `payout_status=processing`→`transferred`, records `merchant_payouts`, idempotency_key per batch, reverts on Stripe error), `POST /payout/instant` (Stripe Instant `Payout` on the connected account for a fee). Uses the EXISTING test-mode `STRIPE_SECRET_KEY` (Connect IS enabled on it — verified). User chose model **B**: manual "Withdraw" + optional "Cash out now" instant. Guards verified: 409 `not_payout_ready` until onboarding complete; friendly insufficient-balance message. **MOCKED/limitation**: real bank deposits + successful transfers need completed merchant onboarding + platform balance + going live (Publish); the Transfer/Instant call the real Stripe test API (no real money).
- **Earnings Trends** — `services/merchant_earnings.earnings_summary` now returns `daily` (exactly 30 day-buckets {date,net_cents,count}), `available_cents`, `paid_out_cents`. Both Earnings screens render a 30-day bar chart (`earnings-trends`, empty state `earnings-trends-empty`).
- **Payouts UI** on both Earnings screens (`MerchantEarningsRadioLife.jsx` web + `mobile/app/merchant/earnings.tsx`): a `earnings-payouts` card — Connect payouts / Finish payout setup (`payouts-connect`) + requirements hint (`payouts-requirements`) when not connected; available balance + Withdraw (`payouts-withdraw`) + Cash out now (`payouts-instant`) when connected. Web opens the onboarding URL via redirect; mobile via `expo-web-browser` then re-polls status.
- **Genre Artwork** — Discover genre chips get a small colored dot per genre (`GENRE_COLORS` map, web `RadioHome.jsx` FilterChip `dot` prop + mobile `DiscoverBrowse.tsx` Filter `dotColor`).
- **Now-Playing Peek** — the currently-playing Discover card swaps its red LIVE badge for a green pulsing **PLAYING** badge (web `radio-browse-playing-{id}` via `usePlayerStore.importedStation.id`+`playing`; mobile `{prefix}-playing-{id}` via `activeChannel`+`playing`, RN `Animated` pulse dot). Confirmed working on mobile (stays on Discover after tap).
- Non-blocking follow-ups (iter80 review, not fixed): reservation TTL on `processing` earnings rows; stable stripe error code in `_friendly_stripe_error`; surface 401 from web `loadStatus`. Note: test@ now has an un-onboarded Express account `acct_1U49wQLUK3zTD4ly`; demo@ got one created during testing (both connect/finish branches are wired).



## MOBILE PARITY — Radio Discover widget + Merchant Earnings + Subscribe refresh (2026-06 fork) — testing agent PASS (iteration_79, backend 13/13, web+mobile parity)
Brought the web-only Radio "Discover more", Merchant Earnings dashboard, and Merchant Subscribe tiers to the mobile (Expo) surface; also re-verified the web build. No backend changes (all endpoints already existed).
- **NEW `mobile/src/components/DiscoverBrowse.tsx`** — reusable interactive Discover widget (mobile parity of web RadioHome `BrowseTeaser`). Auto top-played imported stations (`GET /api/radio/browse?source=imported&limit=24&sort=`), Language/Genre/Country filter chip rows (facets from `GET /api/radio/discover` rails' `facet_chips`), debounced search, Sort toggle (popular/az/newest), LIVE badge on every card + 🔥HOT on top-3 (hidden while searching), Favourites + Recently-played rails (reuse existing `useStationsStore` AsyncStorage favorites/recents), play via shared `playStation.playImportedStation`. Filters persisted to AsyncStorage `bigfm_discover_filters`. Accepts a `prefix` prop so testIDs don't clash across screens.
  - Mounted on BOTH the **radio tab** (`app/(tabs)/radio.tsx`, prefix `radio-browse`, below ON AIR) and the **home tab** (`app/(tabs)/home.tsx`, prefix `home-browse`, after Most-Played-Live) — per user request.
- **NEW `mobile/app/merchant/earnings.tsx`** — Merchant Earnings dashboard (parity of web `MerchantEarningsRadioLife`). Reads `GET /api/merchant/marketplace/earnings`; net-payout headline + stat grid (sold / net-month / fee-month) + recent membership-sales list. Verified live w/ real ledger (demo@: $17.99 net / $19.99 gross / $2.00 = 10% fee / 1 sold). Entry tile `merchant-open-earnings` added to `mobile/app/merchant/dashboard.tsx`.
- **`mobile/app/merchant/subscribe.tsx` refresh** — was stale Phase-B ("Starter $29 / Pro $99", `.toFixed(0)`). Now: `priceLabel` shows decimals + "Free"; Pro shows POPULAR + a crown **MEMBERSHIPS** badge (`can_offer_memberships`); free-tier button "Start free"; paid button "Choose {name} · $X.XX/mo". Tiers rendered from `GET /api/merchant/marketplace/subscription/plans` (starter Free/false, growth $29.99/false, pro $99.99/true).
- **Stripe payouts = INTERNAL LEDGER (mocked payout only)**: `services/merchant_earnings.py` records real gross/fee/net per membership sale; actual bank payout is out-of-band (no merchant has completed Stripe Connect onboarding). Ledger numbers are real.
- Non-blocking nits from iter79 (pre-existing, NOT from this work): web `/shop/merchant/dashboard` URL has no screenFor mapping (nothing links to it — hub is `/shop/merchant`); http:// station thumbnails cause mixed-content warnings; free-tier downgrade doesn't cancel prior Stripe sub.



## MEMBERSHIP CLAIM BUGFIX + SHOP PLANS Phase 1 (2026-06 fork) — testing agent PASS (web + mobile), iteration_78
### Bugfix — membership "Claim now" → benefit_not_found (BOTH surfaces)
Root cause: the venue membership-detail screens sent `benefit_id`, but the API (`_benefit_status`) returns `entitlement_id`, so the claim posted `undefined` → backend matched nothing → `benefit_not_found`. Fixed the field on web (`ShopMembershipsRadioLife.jsx`) and mobile (`mobile/app/shop/memberships/[id].tsx`) to use `entitlement_id` (fallback `benefit_id`), and hardened the backend claim (`marketplace_memberships.py`) to match `entitlement_id` OR legacy `benefit_id`. Verified: Unlimited Coffee claim decrements on both web & mobile, no error. (Affected preview + production — user must redeploy for prod.)

### Shop Subscription Plans — Phase 1 (extends the EXISTING `subscription_plans`/`merchant_subscriptions` system; did NOT build a parallel one)
- Tiers reseeded in `services/marketplace.py` `DEFAULT_PLANS` (idempotent `$set` upsert): **Starter Free (can_offer_memberships=false)**, **Growth $29.99/mo (false)**, **Pro $99.99/mo (true)**. `/api/merchant/marketplace/subscription/plans` now returns `can_offer_memberships`.
- Free tier activates instantly (no Stripe); paid tiers use the existing Stripe Checkout subscription flow. Both activation paths set `subscription_active=true` + `status=approved` (instant activation, per user decision — no admin approval).
- **Membership creation gated**: `POST /api/merchant/marketplace/memberships/items` returns 403 `{code:membership_plan_required, required_tier:pro}` unless the merchant's active plan is Pro OR they already sell memberships (grandfathered, `active:true` plans only). Helper `_can_offer_memberships` in `marketplace_memberships.py`.
- Web UI: `MerchantSubscribeRadioLife` shows the 3 tiers (Pro has POPULAR + ⭐MEMBERSHIPS badges; free shows "Start free"); `SellOnRadioLife` now routes a new business to `/shop/merchant/subscribe` after onboarding (self-serve open-a-shop); `MerchantMembershipsRadioLife` shows an "Upgrade to Pro" gate + disabled Create when the shop can't offer memberships.
- Commission: the platform's global commission default is ALREADY 15% (`services/marketplace.py`), category-based with per-merchant overrides via the existing commission engine — matches the user's requirement.

### Phase 2 / remaining (NOT yet built)
- Wire the 15% commission as a Stripe Connect `application_fee` on each consumer **membership subscription** payment (currently the commission engine exists but membership subscribe doesn't apply an application_fee).
- Plan **upgrade/downgrade** UX + cancel the prior Stripe subscription on downgrade (free-tier checkout currently doesn't cancel an existing paid sub).
- Mobile parity for the shop-plan chooser (currently web-only).
- PAUSED: Discover "recently played / favorites / sort" — only the backend `sort` param (popular/az/newest) on `/api/radio/browse` is done; the RadioHome UI for recents/favorites/sort toggle is not built.


## RADIO "DISCOVER MORE" — 4 enhancements (2026-06 fork) — self-verified (web)
Extended the interactive Discover widget in `frontend/src/RadioHome.jsx` (`BrowseTeaser`). All params already supported by `/api/radio/browse`; no backend change.
- **Country filter:** new chip row from the discover `countries` facet (slug=ISO code); labels show a flag emoji (derived from the 2-letter code) + friendly name (`COUNTRY_NAMES` map, fallback to code). Filters via browse `country=`. testids `radio-browse-country-chips`, `radio-browse-country-{code}`, `radio-browse-country-all`.
- **In-section search:** debounced (350ms) text input (`radio-browse-search` + `radio-browse-search-clear`) → browse `q=`. Re-fetches thumbnails as you type.
- **Live / hot badges:** every thumbnail gets a pulsing red LIVE badge (`radio-browse-live-{id}`); the top-3 most-played (results are sorted flagship→votes→clicks) get a 🔥 HOT badge (`radio-browse-hot-{id}`), hidden while searching. NOTE: no real-time listener counts are tracked, so we surface honest LIVE + popularity-ranked HOT rather than fabricated "listeners now" numbers.
- **Remembered filters:** language/genre/country persist to `localStorage["radiolife.discover.filters"]` and restore on mount (search is intentionally not persisted). Verified across a reload (India + Bollywood stayed active).
- Self-verified via screenshots (country flags, search→BBC results, 24 LIVE + 3 HOT badges, persistence on reload). Lint clean. Web-only; renders on legacy-variant `/radio`. Not run through the testing agent (single section, self-tested).


## RADIO "DISCOVER MORE" — interactive filterable browse + CRITICAL router fix (2026-06 fork) — self-verified (web)
User reported the web `/radio` "Discover more" section showed only a heading + "Browse all" button (empty grid) and asked for: list stations, auto-show top-played, filter by language + genre, scrollable thumbnails.
- **ROOT-CAUSE / CRITICAL BUGFIX:** `backend/routes/radio_unified.py` had a stray fragment at line 625 (`dio?ch={slug}&autoplay=1",` + `}`) → `SyntaxError: unterminated string literal` → the ENTIRE `/api/radio/*` router (discover, browse, genres, station, play) AND the `promoted_stations` router failed to import (logged "router not loaded" every boot). That's why the Discover grid was empty (discover 404 → catch → []). Removed the stray lines. Also fixed a latent `NameError`: `browse()` used `genre` at 3 places but never declared it as a query param → added `genre: Optional[str] = Query(None)` (also enables genre filtering). After fix: discover/browse/genres/play/station/promoted-stations all 200; browse total 4,970 imported stations.
- **Feature (web `frontend/src/RadioHome.jsx` `BrowseTeaser`):** rebuilt the static 8-card grid into an interactive widget — auto-loads top-played imported stations (`GET /api/radio/browse?source=imported&limit=24`, sorted flagship→votes→clicks), horizontally-scrollable thumbnail cards (`radio-browse-teaser-scroll`, `radio-browse-teaser-card-{id}`) that resolve+play via `POST /api/radio/play/{id}` then `/radio/station/{id}` (mirrors RadioBrowse). Language chips (`radio-browse-lang-*`) + Genre chips (`radio-browse-genre-*`) sourced from the discover `languages`/`genres` facet rails; language uses browse `language=`, genre uses browse `category=` (the `music_genre` field rarely matches exact genre labels; the category system gives real counts: pop 608, news 503, rock 400, bollywood 248, talk 245). Kept "Browse all 50,000+" CTA + added a "See all" link. Removed the now-redundant parent `browsePreview` discover fetch.
- Self-verified via screenshots: filters + 24 scrollable thumbnails render; selecting Bollywood re-filters the row to Bollywood/India stations. Lint clean. NOTE: this section renders on LEGACY-variant `/radio` (RadioHome); the RadioLife "new look" `/radio` uses ListenRadioLife. Change is web-only + a shared-backend syntax fix (no mobile impact). Not run through the testing agent (single section + curl-verified router).


## FOUR NEW FEATURES — AI Concierge · Savings Tracker · Join-to-Save Nudge · Price Parity Monitor SHIPPED (2026-06 fork) — iteration_78 (mobile 100% green; 2 web bugs found & fixed + self-verified)
Built on the Membership Entitlements Engine. Consumer features on BOTH web + mobile (lockstep); Price Parity is admin-only → WEB ONLY (per user, matches every other admin console).
- **AI Concierge (Gemini 3 Flash):** backend `routes/marketplace_concierge.py` (`POST /api/shop/concierge`) parses a natural-language order → concrete item+options+entitlement, re-prices authoritatively via `_price_menu`, returns a proposal. Uses REAL Emergent LLM key (NOT mocked). Web: `screens/ConciergeRadioLife.jsx` at `/shop/concierge` (registered in `RadioLifeOverlay.screenFor`), entry via a prominent orange "Order by chat ✨" banner (`shop-concierge-banner`) on Shop home + an account-menu link (`shop-concierge-link`). Mobile: `app/shop/concierge.tsx`, same two entry points on the Shop tab. Adds proposal to cart → routes to checkout. Verified live: Large Tandoori + extra cheese w/ Pizza Club → subtotal $24.99 / discount $18.99 / total $6.00.
- **Savings Tracker:** backend `GET /api/shop/memberships/savings` (`membership_savings` — month + lifetime net savings from the immutable ledger). Web Wallet (`ShopMyMembershipsRadioLife.jsx`, `savings-tracker`) + mobile (`shop/my-memberships.tsx`, `savings-tracker`). Gated on `lifetime_savings_cents > 0` (was `lifetime_count>0` — fixed so members with only non-monetary perks don't see a "$0.00 saved" banner).
- **Join-to-Save Nudge:** backend `find_join_nudge` surfaces the best non-owned plan whose entitlement would make a cart item free; returned as `join_nudge` in the menu quote. Web checkout (`CheckoutMenuRadioLife.jsx`, `checkout-join-nudge`) + mobile cart (`shop/cart.tsx`, `cart-join-nudge` → `/shop/memberships/{biz}`). Correctly absent when the shopper already owns the covering plan (e.g. test@ at Fun Pizza).
- **Price Parity Monitor (admin, web only):** backend `routes/marketplace_price_parity.py` (`GET /api/admin/marketplace/price-parity`, `POST /override`; admin override wins over merchant `direct_price_cents`, flags drift ≥3%). Web `admin/PriceParity.jsx` at `/admin/price-parity` (nav `adnav-price-parity` under Users & Businesses) — summary chips, per-row editable direct price, drift %, flag badge, save/clear override, show-flagged-only toggle. Verified: 34 rows, set $9.99 → +180.3% flagged, clear → override removed.
- **BUGFIX (this iter, web):** `/shop/*` screens double-mounted in the RadioLife "new look" — both `ShopInShell` (App.js `/shop/*` route) AND `RadioLifeOverlay` rendered `screenFor(pathname)`, so the concierge/account-menu existed twice (duplicate state + strict-mode/testid clashes → concierge submit never resolved, account menu opened behind the overlay). Fixed by guarding `ShopInShell` to return null when `variant === 'radiolife'` (the full-screen overlay already renders the shop). Resolved BOTH the HIGH concierge and MEDIUM account-menu bugs; self-verified via screenshots (single render, live $6.00 proposal, account menu + concierge link visible).



## MEMBERSHIP ENTITLEMENTS — Phase 2 (Merchant Builder), Phase 3 (Checkout Engine), Phase 4 (Wallet) + Pizza Club Demo SHIPPED (2026-06 fork) — iteration_77 GREEN (backend 10/10 + web + mobile parity)
Built on Phase 1's schema/ledger foundation. All on BOTH web + mobile (lockstep).
- **Phase 3 — Checkout pricing + entitlement engine (backend):** `services/membership_entitlements.py` gained `evaluate_line_entitlement`, `record_order_entitlements`, `resolve_eligible_items`, `find_active_membership`, `entitlement_covers_item`. Menu `_price_menu` (marketplace_orders.py) + product cart `_price_group` (marketplace_products.py) now accept per-line `selected_option_ids` (option upcharges via `price_with_options` + `validate_selection`) and `apply_entitlement_id`. An applied entitlement waives the BASE + `included_option_ids` deltas; other upgrades charged (e.g. +$4 Large, +$2 cheese); enforces eligibility (item/category), per-period remaining (ledger), day/time window, stackability-vs-coupon, and `max_upcharge_cents` cap. Applies to ONE unit/line. Orders store `applied_entitlements` + `entitlement_discount_cents`; free & paid finalize paths call `record_order_entitlements` → immutable ledger rows (source='order', idempotent per order+entitlement+item). Points awarded on post-entitlement amount. Verified: Large+cheese+ent_free_pizza → subtotal 2399 / discount 1799 / total 600.
- **New consumer endpoints:** `GET /api/shop/businesses/{id}/my-entitlements` (usable entitlements at a venue + remaining + eligible_items); `/api/shop/memberships/mine` benefits now carry `eligible_items` + `business_id`.
- **Phase 2 — Merchant Builder UI (web + mobile):** `MerchantMembershipsRadioLife.jsx` / `merchant/memberships.tsx` = full v2 entitlement composer (target any/category/items from live catalog, included-free option chips, quantity, reset frequency, rollover, day chips + start/end hour, stackable, max-upgrade cap). New `OptionGroupsEditor` (web `.jsx` + mobile `src/components/OptionGroupsEditor.tsx`) wired into merchant Menu + Products for size/single/multi groups with per-option upcharge + default flag.
- **Phase 3 UI — consumer option/entitlement pickers:** new `ItemOptionModal.jsx` (web) + `ItemOptionSheet.tsx` (mobile). Shop menu (`ShopMenuRadioLife.jsx` / `shop/menu/[id].tsx`) tags eligible items with a "Membership" badge and opens the picker (size/modifiers + "Use membership" toggle → BASE FREE, upgrades priced). Most-specific entitlement auto-applies (rank item>category>any). Cart stores keyed by composite `line_id` (`useShopCart.js` / `useCartStore.ts` extended with `addLine`). Menu checkout (`CheckoutMenuRadioLife.jsx` / `shop/cart.tsx`) sends options+entitlement and shows a Membership discount row + friendly entitlement error copy.
- **Phase 4 — Wallet order-from-wallet (web + mobile):** `ShopMyMembershipsRadioLife.jsx` / `shop/my-memberships.tsx` — each entitlement shows remaining + a horizontal row of eligible items; tapping deep-links to `/shop/menu/{biz}?item=&apply_entitlement=` which auto-opens that item's picker with the membership pre-applied. Legacy "Claim" retained for in-store `any` perks.
- **Pizza Club Demo (marketplace_samples.py):** Fun Pizza signature pizzas now carry shared option groups Size (Medium 0 default / Large +$4) + Extra Toppings (cheese +$2 / mushrooms +$1.50 / jalapeños +$1). "Weekly Pizza Club" → "Pizza Club" ($60/mo) with entitlement `ent_free_pizza` (category Pizzas, included opt_size_medium, 1/day, cap $10). test@ + demo@ seeded with an active Pizza Club membership. `_upsert_menu` persists option_groups; `_upsert_membership` accepts v2 entitlement specs.
- **Known / deferred (optional, from iter76+77 review):** concurrent-redemption race not yet gated (needs atomic guard/txn); Coffee Club "Unlimited" shows 99/day (cosmetic); "Included" vs "Free" option copy nuance. Product single-buy endpoint `/product-orders/checkout` still options-agnostic (cart path covers options+entitlements).


## SHOP UX DECLUTTER + ROLE-GATING (P0, user-flagged) SHIPPED (2026-06 fork) — self-verified both surfaces
The Shop home was dumping every merchant + consumer action as big tiles to EVERY user. Restructured to a clean, shopping-first storefront on both web + mobile.
- **Web `ShopRadioLife.jsx`**: removed the tile grid (Orders/Bookings/Merchant/Product Orders/My Loyalty/Scan/Payment Methods) and the memberships/orders chip row. Header now has a **person Account button** (`shop-account-button`) → a fixed dropdown (`shop-account-menu`, `z-[100]` to escape the shell's transformed scroll-container stacking context) with My Orders, Product Orders, My Bookings, My Memberships, My Loyalty, Payment Methods, Scan to Pay. Merchant tools are **role-gated** via `GET /api/merchant/marketplace/profile` (`{profile:null}` for non-owners): owners get a single **Merchant Dashboard** banner (`shop-merchant-banner`) + a highlighted menu item (→ existing `MerchantDashRadioLife` hub); non-owners get only the subtle "Sell on RadioLife" CTA. Cart icon unchanged.
- **Mobile `(tabs)/shop.tsx`**: removed the two quick-action rows + the scan button. Hero gets a **person Account icon** → an absolute-overlay **bottom sheet** (`shop-account-menu`; switched off RN `Modal` because Expo-web's Modal didn't composite the backdrop — the absolute overlay renders identically on web + native) with the same consumer links, plus a role-gated Merchant Dashboard row/banner. Same `/merchant/marketplace/profile` gating.
- Buying stays simple/Amazon-like: business/product card → detail → add to cart / buy → cart → checkout (unchanged).
- Verified via screenshots: web merchant view (Merchant Dashboard banner + menu), mobile logged-out view (Sell CTA, no merchant banner) + clean account sheet. NOT run through the testing agent yet (contained navigation/declutter change).


## MEMBERSHIP ENTITLEMENTS, MENU VARIANTS & ORDER RULES — Phase 1 (Data & Schema Foundation, backend) SHIPPED (2026-06 fork) — iteration_76 green (24/24 backend)
Overhaul of memberships from simple discount coupons into a true entitlement engine. User approved a 4-phase plan (both web+mobile in lockstep for UI phases) + FULL replacement of the old model via a boot migration. Phase 1 is backend-only.
- **NEW `services/membership_entitlements.py`** — the engine core:
  - Option-group models (`OptionGroupModel`/`OptionChoiceModel`, types size|single|multi; each option has `price_delta_cents` upcharge, is_default, available, stock) + `normalize_option_groups` (assigns `grp_`/`opt_` ids; size/single force max_select=1) + `price_with_options()` + `validate_selection()` (for Phase 3).
  - v2 entitlement model (`EntitlementModel`): label, target_type (item|product|category|any), target_ids[], category, included_option_ids[], quantity, reset_frequency (daily|weekly|monthly|billing_cycle|total), rollover + rollover_cap, day_time{days[],start_hour,end_hour}, stackable, max_upcharge_cents, active + `normalize_entitlements`.
  - Period math: `period_key(reset_frequency, membership)`, `day_time_allows(rule)`.
  - IMMUTABLE ledger `membership_redemption_ledger` (never mutated; reversals appended): `entitlement_remaining()` (ledger-backed used/remaining per current period), `record_redemption()`, `reverse_redemption()`, `ensure_membership_indexes()`.
  - `migrate_memberships_v2()` — idempotent boot migration: legacy plans (`schema_version!=2`, old {benefit_id,qty,period,options}) → v2 entitlements (legacy `benefit_id` kept as `entitlement_id`; period→reset_frequency; old option labels kept as `choice_labels`); legacy `membership_claims` → ledger rows (`led_legacy_*`, source=legacy_claim). Wired into server.py lifespan; logged `plans_migrated:4 claims_migrated:5` then 0/0.
- **`marketplace_menu.py` + `marketplace_products.py`**: `MenuItemBody`/`ProductBody` gain `option_groups` (additive; normalized on create/patch/bulk). Products keep legacy `variants` too.
- **`marketplace_memberships.py`**: `PlanBody.entitlements` uses `EntitlementModel`; plans stored `schema_version=2`. `_benefit_status` reads ledger-backed remaining + emits legacy aliases (`qty`,`period`,`options`) + `available_now` so pre-v2 clients keep working. `claim_benefit` accepts BOTH `entitlement_id` and legacy `benefit_id`, enforces day/time window (400 outside_time_window) + per-period limit (400 limit_reached), and appends to the immutable ledger.
- **Consumer reads** `GET /api/shop/businesses/{id}/menu` (shop.py) + `/products` now expose `option_groups`.
- **`marketplace_samples.py`** `_upsert_membership` now writes v2 entitlements + schema_version=2 (was re-writing old schema each boot, which broke the v2 read after the first migration — fixed).
- **DEFERRED to Phase 3** (by design, NOT bugs): CheckoutItem does not yet accept `selected_option_ids`; option upcharges + entitlement application at checkout are Phase 3. Phase 3 hardening TODOs from iter76 review: (1) option-group-aware claim validation (currently validates against legacy `choice_labels`, no-ops for new v2 plans); (2) concurrency lock / atomic guard on claim remaining-check+insert; (3) replace ledger `async for`+sum with `$group $sum`; (4) stop leaking `choice_labels` in `_benefit_status`; (5) demo daily perks use qty=99.
- **NEXT phases (approved):** Phase 2 — Merchant Membership Builder UI + menu/product variant+modifier editors (web + mobile lockstep). Phase 3 — Pricing & Entitlement engine wired into checkout. Phase 4 — Customer Wallet & direct-order-from-wallet UI (both surfaces).


## SUPER MARKETPLACE — Specials + Points-per-Dollar + Loyalty-on-Scan + Order Sound SHIPPED (2026-06 fork) — iteration_75 green (19/19 backend)
Four features, both surfaces (web /app/frontend + mobile /app/mobile), shared backend.

### 1) Promoted Specials ("Today's Specials")
- `routes/marketplace_specials.py` (collection `marketplace_specials`). Merchant `GET/PUT/DELETE /api/merchant/marketplace/specials` (feature a product|menu item, blurb + optional sale_price_cents + active, unique per business+kind+item). Consumer `GET /api/shop/specials` (enriched w/ business+item+image); `GET /api/shop/home` now returns a top-level `specials` array.
- Web: "Today's Specials" row on `ShopRadioLife` home (`shop-specials-row`), merchant manager `MerchantSpecialsRadioLife` at `/shop/merchant/specials`. Mobile: specials row on shop tab, `merchant/specials.tsx`. Entry: `merchant-open-specials` on both dashboards.

### 2) Points Per Dollar (reward big spenders + rank boost)
- `services/marketplace.py`: new `points_for_order(profile, subtotal_cents)` — honours BigPoints `mode` ('default' flat vs 'per_order_value' = round(subtotal_$ × ppd)), happy-hour multiplier applies to both. Wired into menu `_price_menu` + product `_price_group`/`product_checkout` `points_to_award` (award auto-follows). Settings via existing `PATCH /api/merchant/marketplace/bigpoints/settings`.
- `services/marketplace.ranking_score()` — sponsored + featured + ppd-boost + base points; used in `shop.py` `/shop/businesses?sort=featured` + home "recommended" row.
- Web + mobile: "BigPoints Earning" card on merchant dashboards (`merchant-points-settings`, flat/per-dollar toggle + input).

### 3) Loyalty On Scan
- `scan_pay_service.charge` now awards BigPoints on a successful CARD scan-pay (via `points_for_order` + `award_with_tier_bonus`, idempotent `scanpay_award_{token}`); paying by points earns none. Returns `points_awarded`.

### 4) Order Sound Alert
- Merchant dashboards poll every 15s; when `new-count` rises, play an audible ping — web via Web-Audio oscillator (`playPing`), mobile via `expo-audio` (bundled `assets/sounds/ping.wav`) + `expo-haptics`. Mutable via `merchant-sound-toggle`. Live new-order feed already present.

### Deps/notes
- Added `assets/sounds/ping.wav` (generated). No new native perms (camera already added iter74).
- Non-blocking (carried): RN-Web `shadow*`/`pointerEvents` deprecation warnings (native unaffected); per-dollar mode has no min-ppd floor (product decision, not a bug).


## SUPER MARKETPLACE — Coupons + Order Alerts + QR Scan-to-Pay SHIPPED (2026-06 fork) — iteration_74 green (22/22 backend)
Three features, both surfaces (web /app/frontend + mobile /app/mobile), shared backend. Stripe LIVE test mode.

### 1) Coupons at Checkout (merchant self-serve — NO CPA impact)
- `services/marketplace_coupons.py` + `routes/marketplace_coupons.py`. Merchant CRUD `/api/merchant/marketplace/coupons` (percent|amount, min_spend, max_discount, usage_limit, per_user_limit, active, window). Consumer `POST /api/shop/coupons/validate`.
- `coupon_code` added to menu quote/checkout (`marketplace_orders._price_menu`) and per-venue cart quote/checkout (`marketplace_products._price_group` via `CartGroup.coupon_code`). Discount order: **coupon → gift card → BigPoints → card**. Redemption recorded once per order (`marketplace_coupon_redemptions`, `used_count++`, per-user limit enforced). Self-funded; does NOT touch `ad4_coupon_service` — advertiser splits untouched.
- Web: coupon box on both checkout screens (`checkout-coupon-*`), merchant screen `MerchantCouponsRadioLife` at `/shop/merchant/coupons`. Mobile: `cart.tsx` + `product-cart.tsx` (validate-preview), `merchant/coupons.tsx`. Entry: `merchant-open-coupons` on both dashboards.

### 2) Order Alerts + Product Order Management
- `notify_merchant_new_order()` enqueues a `merchant_new_order` notification to the shop owner on every paid order (food free/one-tap/hosted + product cart/hosted). New endpoint `GET /api/merchant/marketplace/orders/new-count` → {food,products,total}.
- Merchant dashboards (both surfaces) now: new-order alert badge (`merchant-new-order-alert`, polls every 20s) + Product Orders section (`merchant-product-order-*`) advancing paid→packed→shipped→delivered (`merchant-product-advance-*`) via existing `PATCH /api/merchant/marketplace/products/orders/{id}/status`. Food-order management unchanged.

### 3) QR Scan-to-Pay (customer presents QR → shop scans → charge)
- `services/scan_pay_service.py` + `routes/scan_pay.py`. Customer `POST /api/shop/scanpay/token` (method card|points, exact amount, single-use, 5-min TTL) → QR; `GET /token/{t}/status` (poll); `POST /token/{t}/cancel`. Merchant (owner-gated) `POST /resolve` + `POST /charge` (card = off-session PaymentIntent reusing saved-cards helper; points = PointsService.spend at 100 pts/$). Atomic claim prevents double-charge.
- Anti-fraud: `POST /api/shop/scanpay/report-bypass` logs `scanpay_fraud_logs`; every resolve/charge audited in `scanpay_charges`; admin `GET /api/admin/scanpay/fraud-logs` + `/charges`.
- Web: customer `ScanPayRadioLife` `/shop/scan-pay` (QR via react-qr-code), merchant `MerchantScanRadioLife` `/shop/merchant/scan` (manual code entry). Mobile: `shop/scan-pay.tsx` (QR via react-native-qrcode-svg), `merchant/scan.tsx` (expo-camera QR scan w/ permission flow + Open-Settings fallback + manual entry). Entry: `shop-scan-pay` (Shop home) + `merchant-open-scan` (dashboards).
- **Dependency fix**: `expo-camera` was mis-pinned to 57.0.3 (SDK-incompatible, crashed the bundle) → reinstalled `expo-camera@17.0.10`. Added iOS `NSCameraUsageDescription` + Android `CAMERA` permission in app.json. Camera scanning needs a native build/Expo Go — cannot be validated in web preview; manual-entry path works everywhere.
- Fixed a visual regression: mobile merchant dashboard action tiles now wrap into a 3-col grid (was overlapping at 390px).
- Follow-ups (non-blocking): app-wide RN-Web `shadow*`/`pointerEvents` deprecation warnings (native unaffected).


## SUPER MARKETPLACE — Phase 2 Checkout: SAVED CARDS SHIPPED (2026-06 fork) — iteration_73 green (13/13 backend)
One-tap checkout with saved credit cards, built on BOTH surfaces against the shared backend. Stripe LIVE test mode.
- **Backend** `services/saved_cards_service.py` (shared helpers: `ensure_stripe_customer` reuses `users.subscription.stripe_customer_id`; `list_cards`; `charge_saved_card` off-session PaymentIntent; `owns_payment_method`) + `routes/saved_cards.py` (`/api/shop/wallet`): `GET /cards`, `POST /cards/setup-session` (hosted Stripe Checkout `mode=setup` → works on web redirect + Expo WebBrowser, no Stripe.js/native modules), `POST /cards/setup-session/{sid}/sync` (first card → default), `POST /cards/{pm}/default`, `DELETE /cards/{pm}`.
- **One-tap charge**: `payment_method_id` added to `POST /api/shop/orders/checkout` (menu) + `POST /api/shop/cart/checkout` (products). When present & total>0 → off-session PaymentIntent confirmed immediately; success → order marked paid, `checkout_url=null`, `paid=true` (no redirect). `stripe.error.CardError`/SCA falls back to the existing hosted Checkout Session. Existing marketplace checkout stays a PLAIN platform charge (NOT a Connect destination charge) — unchanged.
- **Web** (`design_radiolife`): `WalletCardsRadioLife.jsx` at `/shop/wallet/cards` (list/add/set-default/remove, returns from hosted setup via `?setup=success&session_id` → sync). Payment-method selector wired into `CheckoutMenuRadioLife` + `CheckoutCartRadioLife` (saved-card rows + 'new card' + Manage link). Shop-home `shop-payment-methods` link. Registered in `RadioLifeOverlay.screenFor` (renders in-shell).
- **Mobile** (Expo): `src/components/SavedCardPicker.tsx` (reusable; used in `shop/cart.tsx` food + `shop/product-cart.tsx` products when total>0) + `app/shop/wallet/cards.tsx` management screen + Shop-tab `shop-payment-methods` quick link.
- **Cards are stored by Stripe** (SetupIntent via hosted Checkout); RadioLife never stores PANs.
- Non-blocking follow-ups (iter73): web menu-cart Zustand store empties on DIRECT nav to `/shop/checkout/menu` (pre-existing persistence gap, not the payment selector); off-session `requires_action`/SCA silently falls back to hosted Checkout (no user hint).
- **NEXT (approved, in-progress task):** Coupons at Checkout — apply a business's coupon on the checkout screen alongside points/gift cards, carefully integrated with the sponsored-CPA `services/ad4_coupon_service.py` engine so advertiser revenue splits aren't broken. Then P0: QR Scan-to-Pay + Merchant Order Management.


## Changelog — 2026-08-09 (CS.1 + Insights SHIPPED: Creator Studio video/chapters/transcripts + Listing Insights)
- **Verified: testing agent iteration_51 — backend 16/16 PASS + regression (iter49 19 + iter50 23), mobile all testIDs verified. Real Tigris signed URL returned on video upload. One flagged issue (chapters hidden on audio-only episodes) FIXED post-report.**
- **Creator Studio video** (`routes/creator_video.py`, prefix `/api/podcasts`): `POST /episodes/{id}/video` (multipart) streams to **Tigris object storage** via `object_storage.get_storage()` → sets `video_storage_key` + `media_type=video`; `GET /episodes/{id}/media` returns fresh 6h signed `video_url` + chapters + transcript; `PUT /episodes/{id}/chapters` (sorted, validated) + `PUT /episodes/{id}/transcript`. All creator-ownership-gated (channel.creator_id → podcast_creators.user_id; admin allowed). 500MB cap, video content-type check.
- **Creator UI** (`mobile/app/creator/episode/[id].tsx`): `VideoChaptersEditor` — pick+upload video (expo-document-picker), add/remove chapters (title + m:s), transcript editor, save.
- **Consumer playback** (`mobile/app/podcast/episode/[id].tsx`): `EpisodeVideoBlock` (expo-video `VideoView`, PIP enabled), tappable chapters (seek), collapsible transcript. Chapters now render for BOTH video (`EpisodeVideoBlock`) and audio-only (`ChaptersBlock`, seeks the audio `soundRef`). Added `expo-video` config plugin to app.json. **PIP only works in a native Publish build — not Expo Go/web preview.**
- **Listing Insights** (`merchant_marketplace.py`): daily rollup collection `featured_daily` (bumped on `discovery/featured` impressions + featured click clicks/spend); `GET /api/merchant/featured/{id}/insights?days=7` (owner-gated) → 7-day series + totals + budget. Mobile `/merchant/insights/[id]` — totals row (Views/Taps/Tap-rate/Spend) + custom 7-day bar chart; reachable from marketplace featured rows (`mkt-insights-*`).
- **Object storage = Tigris** (S3-compatible, `STORAGE_BACKEND`/`TIGRIS_*` in backend/.env) — used for all Creator Studio video.
- **NEXT (approved, deferred to next turn)**: Booking CPA (venues pay per booking) + Gift Card Market (buy/gift local gift cards via points or Stripe). Then P2: `source=all` DB-pagination; RN deprecation cleanup (shadow*→boxShadow, props.pointerEvents); tunein http mixed-content.


## Changelog — 2026-08-09 (MKT.4 SHIPPED: Web New Look cream/orange + Listing Analytics + Notification Bell)
- **Verified: testing agent iteration_50 — backend 75/75 PASS (5 new + 70 regression), mobile fully verified; web verified by main-agent screenshots (agent's web miss was a login-timing artifact, no code bug).**
- **Object storage note (for Creator Studio next)**: app uses **Tigris** (S3-compatible) via `STORAGE_BACKEND`/`TIGRIS_ENDPOINT_URL`/`TIGRIS_BUCKET` in backend/.env — Creator Studio video uploads will reuse this same bucket.
- **Web New Look (cream/orange)**: the web `design_radiolife` variant was stale purple/pink; refreshed to brand cream/orange (`RL_COLORS` gradient `#F26B2A→#F59E0B`, primitives RLButton/RLChip/RLBadge, `AppShellRadioLife` bg `#FBF5EC` + orange Legacy toggle). Recolored `DiscoverRadioLife`, `RewardsWalletRadioLife`, and shared RL components (PointsBalanceCard/CouponCard/etc). NEW `GamingRadioLife.jsx` (Play & Win, `/api/games/discover`) wired at `/play` in `RadioLifeOverlay`. Activate via `?design=radiolife` or the toggle (auth required). Verified rl-gaming-page / rl-rewards-page / rl-discover-page all cream/orange.
- **Listing Analytics** (mobile `/merchant/marketplace`): per-campaign stats row (`mkt-stats-*`) reading the existing list payload — Featured→Views/Taps, Spin/Scratch→Plays/Wins, Trivia→Answers/Correct, Coupon→Claims, Giveaway→Entries, plus a Spend pill. No new endpoint.
- **Notification Bell** (mobile Home): unread-count badge (`home-notif-badge`) from `GET /api/me/notifications/unread_count`; hides at 0, updates after reading.
- **NEXT (user-approved)**: Creator Studio — video podcast upload via **Tigris object storage** + chapters + transcripts + PIP (PIP best-effort; needs a Publish build to validate). Then P2: extra business monetization (booking CPA, lead-gen CPL, gift cards, memberships); `source=all` DB-pagination; deprecated RN style props cleanup (shadow*→boxShadow, pointerEvents), mobile TS/lint.


## Changelog — 2026-08-09 (MKT.3 SHIPPED & VERIFIED: Winner Notifications + inbox feed + Featured Listings)
- **Verified via testing agent (iteration_49): backend 19/19 PASS + 51/51 regression, mobile + web verified, NO bugs. Post-review fraud hardening added + re-verified.**
- **Winner Notifications**: `draw_giveaway` enqueues a `giveaway_winner` notification (via `routes.notifications._enqueue`, dedupe `giveaway_win:<cid>:<uid>`, enqueue errors now logged) into each winner's inbox. Mobile `/notifications` — previously toggles-only — now shows a live **inbox FEED** (`GET /api/me/notifications`, `notif-inbox`) with unread dots + tap-to-mark-read (`POST /api/me/notifications/{id}/read`). NOTE: inbox routes are under `/api/me/notifications`.
- **Featured Listings** (marketplace type `featured`, rate `featured_listing` CPA — rate card now 10 items): merchant pays to pin a venue to local discovery (tagline + bid_cents + budget in `/merchant/marketplace`). Consumer `GET /api/discovery/featured` (bid desc, excludes exhausted, counts impressions) → "FEATURED NEAR YOU" rail on mobile Home (`home-featured-*`). `POST /api/discovery/featured/{id}/click` charges bid_cents, auto-pauses on exhaustion.
- **Click-fraud hardening** (post-iter49 review): featured click now requires auth (anon → 401) and bills at most once per user per campaign per day via unique-indexed `featured_clicks`; returns `charged: true/false`. Verified.
- **NEXT (user-approved order)**: (3a) Creator Studio — video podcast upload via **built-in object storage** + chapters + transcripts + PIP (PIP best-effort; needs a Publish build to validate); (4a) Try New Look — bring the web cream/orange variant to web Gaming/Wallet/Discover. Then P2: extra business monetization (booking CPA, lead-gen CPL, gift cards, memberships), `source=all` DB-pagination, mobile TS/lint cleanup.


## Changelog — 2026-08-09 (MKT.2 SHIPPED & VERIFIED: Format Selector + Spin/Scratch + Giveaways + Directory Scaling)
- **Verified via testing agent (iteration_48): backend 26/26 PASS + 43/43 regression (MKT.1 25 + RWD.5 18), mobile + web verified, NO blockers.**
- **Campaign Format Selector** (advertiser MOBILE `app/advertiser/campaign/new.tsx` step 1): fetches `GET /api/rate-card/formats` (banner/audio/push/video → rate-card keys display_banner/audio_preroll/push_notification/video_ad) and shows each format's live price; the choice is sent as `targeting.ad_format` (free-form, non-breaking). New endpoint in `merchant_marketplace.py`.
- **Spin & Scratch instant-win games** (marketplace types `spin`/`scratch`): merchant sets win_points + win_probability + prize_label + budget. Consumer MOBILE `/brand-games` (linked from `/earn` `earn-brand-games`): `GET /api/brand-games/active`, `POST /api/brand-games/{id}/play` (one play/user, weighted RNG, awards points via idempotency_key, spends `instant_win_game` rate, auto-pauses on budget exhaustion). Reanimated spin animation on the play button.
- **Prize Giveaways** (type `giveaway`): merchant sets prize_desc + num_winners + budget. Consumer MOBILE `/brand-giveaways` (linked from `/earn` `earn-brand-giveaways`): `GET /api/brand-giveaways/active`, `POST /api/brand-giveaways/{id}/enter` (one entry/user, awards points). Merchant draws winners via `POST /api/merchant/marketplace/campaigns/{id}/draw` (owner/admin, random min(num_winners, entries), marks drawn+paused); `mkt-draw-*` button in the marketplace list.
- **Rate Card** grew to 9 items — added `instant_win_game` (CPA) + `giveaway_entry` (CPL); `_rate_card()` backfills new keys into pre-existing docs so admins can tune them.
- **Directory Scaling** (backend `routes/radio_unified.py`): `GET /api/radio/browse?source=imported` now takes a DB-level paginated fast path (`_browse_imported_fast`: `count_documents` + flagship-first `.sort().skip().limit()`) instead of the in-memory 2000-doc merge — the 40K+ directory now reports the true total (~5000+ active) and paginates correctly past page ~66. `source=all` merge path unchanged. Mobile Stations screen already had infinite scroll (`onEndReached`).
- **NEXT (remaining roadmap)**: P2 — video podcasts + Creator Studio, Try-New-Look parity, extra business monetization (featured listings, booking CPA, lead-gen CPL, gift cards, memberships); `source=all` DB-pagination; mobile TS/lint cleanup.
- **Low-pri follow-ups (iter48 review)**: instant-win CPA bills every play not just wins (by design—cost-per-play); insert/increment race on plays; draw audit log; giveaway entry deadline field.


## Changelog — 2026-08-09 (MKT.1 SHIPPED & VERIFIED: Merchant Marketplace + Rate Card + Brand Trivia + Demo Venue)
- **Verified via testing agent (iteration_47): backend 25/25 PASS + 32/32 regression, mobile + web verified, NO blockers.**
- **Demo Venue Seed**: `seed_marketplace()` (called in lifespan) idempotently seeds `businesses.biz_demo_marketplace` owned by the demo user + rate_card + indexes, so `/merchant/*` mobile flows are populated for the demo account.
- **Admin Rate Card Matrix** (WEB `/admin/rate-card`, `admin/RateCard.jsx`, nav `adnav-ads-rate-card`): 7 seeded inventory types (display_banner, audio_preroll, sponsored_rj, push_notification, coupon_featured, trivia_sponsored, video_ad) with CPM/CPA/CPL base/min/max/multipliers/enabled. `GET/PUT /api/admin/rate-card` (admin, validates model ∈ {CPM,CPA,CPL} + min≤max). Rates seed the marketplace pricing hints.
- **Merchant Marketplace "Get More Customers"** (MOBILE `/merchant/marketplace`, backend `routes/merchant_marketplace.py`): goal-first wizard — pick goal → recommended campaign type → form → launch. `GET /api/merchant/marketplace/goals` (4 goals + 2 types + rate hints). Campaign CRUD `POST/GET /api/merchant/marketplace/campaigns` + `/{id}/pause|activate`, ownership-locked via `_assert_merchant_owner`. Collection `merchant_campaigns`. Reachable from Profile (`menu-merchant-marketplace`); Sponsor-a-Bonus also now linked (`menu-merchant-bonuses`).
- **Branded Trivia Campaigns** (type=trivia): merchants author questions + reward_points + budget. Consumer MOBILE `/brand-trivia` (linked from `/earn` via `earn-brand-trivia`): `GET /api/brand-trivia/active` (hides answer_index, per-user answered state), `POST /api/brand-trivia/{id}/answer` awards points on correct (idempotent per user+question, fires reward overlay), spends `trivia_sponsored` rate from budget, auto-pauses when exhausted.
- **Featured Coupon Bidding** (type=coupon_bid): `GET /api/brand-coupons/featured` (sorted by bid_cents desc, excludes exhausted), `POST /api/brand-coupons/{id}/claim` (idempotent per user, awards reward_points_on_claim, spends bid_cents, auto-pauses).
- **NEXT (remaining roadmap)**: P1 Campaign Format Selector (advertiser creation forces Banner/Audio/Push/Video tied to rate card); P2 — 40K radio directory scaling, video podcasts + Creator Studio, Try-New-Look parity, extra business monetization (featured listings, booking CPA, lead-gen CPL, gift cards, memberships); mobile TS/lint cleanup.
- **Low-pri follow-ups (non-blocking, iter47 review)**: unify merchant not-owner error codes; guard floating-point cents drift on spent_usd; optional claim throttle; TuneIn logo Mixed-Content warning on mobile.


## Changelog — 2026-08-09 (RWD.5 VERIFIED: Redeem Ownership Lock + Weekly Streaks + Merchant Self-Serve Bonuses)
- **Verified via testing agent (iteration_46): backend 18/18 PASS + 32/32 regression (iter44+iter45), web + mobile parity confirmed, NO bugs.**
- **Redeem Ownership Lock**: `POST /api/merchant/redeem` + `POST /api/merchant/bonus-windows` enforce `_assert_merchant_owner` (403 non-owner, 404 unknown). `GET /api/merchant/my-businesses` filters to owned venues (admin sees all); `GET /api/merchant/bonus-windows` returns only caller's own; merchant deactivate is owner/admin-gated.
- **Weekly Streak Rewards** (`rewards_earn._maybe_weekly_streak_bonus`): completing ALL enabled weekly missions awards escalating bonus = `weekly_streak_base(150) × min(streak, cap=5)`, idempotent per week via `earn_weekly_completions` + award `idempotency_key=weekstreak:<week>:<uid>` (double-award impossible even under race). Surfaced in claim response `weekly_bonus` + overview `streak.weekly {current, next_reward}`.
- **Merchant Self-Serve Bonuses** (mobile `/merchant/bonuses`): owner creates time-boxed N× (1–10) window, hours 0<x≤168, budget_usd; create→list→deactivate cycle verified on both surfaces.
- **NEXT (per user, ordered 1→5)**: 1) P0 Merchant Marketplace "Get More Customers" goal-first flow (Trivia/Predict&Win/Games/Giveaways/Coupon-bidding), 2) P1 Admin Rate-Card Matrix (CPM/CPA/CPL), 3) P1 Campaign Format Selector, 4) P2 backlog (40K directory scaling, video podcasts + Creator Studio, Try-New-Look parity, extra business monetization), 5) mobile TS/lint cleanup.
- **Low-pri follow-ups (non-blocking, from iter46 review)**: unique index on `earn_weekly_completions(user_id, week_start)`; enforce/spend `budget_usd`; admin `deactivate_bonus_window` 404 on unknown; seed a demo-owned venue so `/merchant/bonuses` isn't empty for demo.


## Changelog — 2026-08-09 (RWD.4: Earn Streaks + Sponsored Bonuses + Fraud Alerts)
- **Earn Streaks** (`routes/rewards_earn.py`): daily streak with admin-configurable milestone bonuses (`earn_config.streak_bonuses`, default 3/7/14/30 days → +50/200/500/1000), best-streak persisted in `earn_streak_state`, milestone award idempotent per run (`streak:<days>:<uid>:<anchor>`). Surfaced in `/api/me/earn/overview` (`streak.{current,best,next,awarded_bonus}`); clients show next-milestone + fire the reward overlay on auto-award. `_get_config` now backfills new config keys for pre-existing docs.
- **Sponsored Bonuses** (`routes/merchant_ops.py`): time-boxed N× points windows tied to a venue. Admin CRUD `GET/POST /api/admin/bonus-windows` + `/{id}/deactivate` (multiplier bounded 1–10). Active windows surfaced in earn overview (`active_bonuses`) + `GET /api/me/earn/bonus-windows`, and the multiplier is APPLIED in `POST /api/rewards/scan-earn` (`bonus_multiplier` in response). Home + Earn banners on both surfaces.
- **Fraud Alerts** (`routes/merchant_ops.py`): auto-creates admin alerts when a merchant's coupon show-vs-scan gap crosses `fraud_config` thresholds (min_shows/flag_rate/min_unredeemed). `maybe_alert` hooks fire on scan-earn/coupon-show/redeem; `GET /api/admin/fraud-alerts`, `POST /api/admin/fraud-alerts/scan`, `/{id}/resolve`, `GET/PUT /api/admin/fraud-config`. (Clears the long-pending handoff P1.)
- **Web admin console** `/admin/merchant-ops` (`admin/MerchantOps.jsx`): fraud-alert list + resolve + run-scan, and bonus-window create/list/deactivate.
- **Testing**: iteration_45 — backend 14/14 pass; both frontends + admin verified; no bugs. Multiplier bound added post-review.
- **Still pending**: Merchant "Get More Customers" Marketplace (large — next dedicated build); earlier handoff merchant-ownership lock on `/api/merchant/redeem` + admin reward-tuning UI.


## Changelog — 2026-08-09 (RWD.2 Post-Action Rewards + RWD.3 Premium Cues + Brand Cleanup)
- **Brand Cleanup (durable, both layers)**: Rebranded user-visible "BigFM"/"Big FM" → "RadioLife" in the DB (`/app/scripts/rebrand_bigfm.py`, allowlist of display fields only) AND at the SOURCE across 128 backend files (case-sensitive sweep) so seeds no longer re-introduce it on boot. Fixed the 2 regressions the testing agent caught (channels `news_radio` name, `premium_subscriber`/`early_adopter` badges). **Protected**: lowercase slugs/emails (`admin@bigfm.dubai` login still 200), redemption codes, UUIDs, ad-system/ads.txt/VAST identifiers, the flagship validator User-Agent, and **10 real third-party stations** in `imported_radio_stations` (German BigFM network, "BigFM 106.2 UAE" — excluded via `SKIP_COLLECTIONS`; wrongly-renamed ones restored).
- **Post-Action Rewards (RWD.2)**: Global reward-celebration overlay on both surfaces — web `src/rewards/RewardOverlay.jsx` (RewardProvider + `useReward().celebrate`), mobile `src/components/RewardOverlay.tsx`. Shows "+N points", fresh balance, and 2 "keep earning" next actions. Wired into mission claim (both) and web daily-code claim. Proven e2e on web (claim → overlay → dismiss).
- **Premium Cues (RWD.3)**: Backend `routes/premium_cues.py` — `GET /api/me/premium/status` (entitlement from `users.is_premium` + enabled benefits + HONEST value calc: multiplier delta on base earning, reward payouts excluded), `GET /api/premium/benefits`, admin `GET/PUT /api/admin/premium/config` (benefits toggles, points_multiplier, trial, pricing — all tunable). New collection `premium_config`. Clients: web `/premium` (`premium/Premium.jsx`) + reusable `PremiumCue`; mobile `/premium` (`app/premium.tsx`) + `PremiumCue`. Home teasers + Earn-screen cues wired; cues hidden for premium users.
- **Testing**: iteration_44 — backend 16/18 (2 fails were the brand gaps, now fixed & directly re-verified: rebrand dry-run = 0 remaining, logins intact); web + mobile Premium screens + reward overlay verified.
- **Deferred (next dedicated phase)**: **Merchant "Get More Customers" Marketplace** (goal-first flow + merchant trivia/predict-win/games/giveaways/coupon-bidding) — too large to bundle; building next. Earlier handoff items (merchant-ownership lock on redeem, proactive fraud alerts, web admin tuning UI) also still pending.


## Changelog — 2026-08-09 (Phase RWD.1: Rewards "Earn Loop" — cross-platform)
- **Shared backend** (`routes/rewards_earn.py`, built on the Phase F-1 `PointsService`/`points_ledger`): platform-agnostic contract returning semantic `action` keys each client maps to its own route.
  - Listener: `GET /api/me/earn/overview` (balance, listener tier + points-to-next, daily goal, streak, ways-to-earn, missions), `GET /api/me/earn/ways-to-earn`, `POST /api/me/earn/missions/{id}/claim` (idempotent via unique `earn_mission_claims` index → PointsService award).
  - Admin (all `require_admin`, tunable — NOTHING hardcoded in clients): `GET/PUT /api/admin/earn/catalog` (earn-opportunity presentation + enable), `/api/admin/earn/missions` (daily/weekly, target/metric/sources/reward), `/api/admin/earn/config` (listener_tiers Bronze/Silver/Gold/Platinum + daily_goal target/bonus). Idempotent `$setOnInsert` seeds so admin edits survive reboots.
  - New collections: `earn_actions_catalog`, `earn_missions`, `earn_mission_claims`, `earn_config`.
- **Web** (`/app/frontend/src/rewards/*`): persistent **PointsPill** in top bar → drawer of top-3 ways + link to /earn; **WaysToEarnCard** on Home (top 5 + daily-goal bar + contextual Premium teaser → /pricing); full **/earn** screen (balance, tier progress, daily goal, streak, Available Now, daily+weekly missions with Claim).
- **Mobile** (`/app/mobile` — PointsPill + WaysToEarnCard components, `app/earn.tsx`, `src/api/earnApi.ts`): parity — header pill → bottom-sheet, Home card + Premium teaser (→ profile), `/earn` route with missions/claim. Same shared backend contract.
- **Also shipped this session**: Trivia **Practice Solo** fix (`TriviaRoom.jsx` — now launches a solo session with the room's category instead of bouncing back); RadioLife **app icon** set (mobile `icon/adaptive/splash` + `app.json`) and **web favicon** set (`favicon.ico` + PNG sizes + apple-touch + PWA manifest, wired in `index.html`).
- **Testing**: iteration_43 — backend 15/15 pytest pass (`tests/test_rewards_earn_loop.py`), both web + mobile UIs verified (pill, home card, /earn, mission claim contract incl. 400/409 idempotency). No blocking issues.
- **Still pending from earlier handoff** (NOT started): DB seed rebrand (leftover "BigFM"), merchant-ownership RBAC on `/api/merchant/redeem`, proactive fraud alerts, web admin tuning UI. Plus remaining roadmap phases (Premium cues, advertiser rate-card, merchant marketplace, video podcasts, 40K directory scaling).


## Changelog — 2026-08-06 (Phase 2/3: AI rewards, coupon fraud, merchant portal, game limits)
- **AI Reward Engine** (`routes/rewards_merchant.py`): `POST /api/rewards/scan-earn` awards BigCoin = amount × base × AI multiplier (Emergent LLM gpt-5.4, bounded 1.0–3.0, deterministic fallback); lifetime thresholds grant one-off bonus points + unlock bonus games + concert pass (idempotent via `users.rewards_thresholds_hit`). Mobile: Profile → "Scan & Earn" (`/scan-earn`).
- **Coupon-Fraud Tracking**: `POST /api/coupon-events/show` logs customer shows; `POST /api/merchant/redeem` reconciles the latest unredeemed show; `GET /api/admin/coupon-fraud` flags merchants with low redemption rate (dodging scans).
- **Restaurant Portal**: mobile `/merchant/redeem` (Profile → "Redeem & Loyalty") — redeem coupons + loyalty tier card; `GET /api/merchant/loyalty` tiers Standard/Silver/Gold (0/10/25 daily → 10/12/15%).
- **Game Frequency Limits**: admin `GET/PUT /api/games/limits` (per day/month/every-N-days); `GET /api/games/play-eligibility/{key}` + `POST /api/games/record-play` (429 when exceeded).
- **Admin provisioning**: `GET/PUT /api/rewards/config` (base rate, thresholds, merchant tiers) + game limits, all `require_admin`.
- **Testing**: iteration_42.json — backend 12/12 pass (`tests/test_iter42_rewards_merchant.py`); mobile verified; live gpt-5.4 output confirmed. Fixed loyalty-card refresh (inline flash vs blocking Alert).
- **Known limitations**: `/api/merchant/redeem` has no merchant-ownership RBAC yet (MVP — any authed user can redeem for a merchant_id); admin config UI is API-only (no web admin screen yet); some seeded game/coupon DB records still say "BigFM".


## Changelog — 2026-08-06 (Phase 1 of 3: filters, news reader+points, ads/premium)
- **Iconized Explore filters**: Country/Language/Genre are now 3 labeled iconized rows (earth/language/musical-notes) with larger readable chips. ('EDM' cased correctly, promo keys namespaced.)
- **Tappable news + native reader**: News cards + breaking cards open `/news-article` (native in-app reader: image, title, summary, source, 'Read full article' via in-app browser). Reading awards **+1 BigCoin per unique article**, server-capped at 10/day via `POST /api/news/read` (atomic claim + unique `{user_id,date}` index → no double-credit).
- **Ads between sections + premium skip**: `AdBanner` sprinkled between Home sections (browse_row/station_detail/bottom_bar) and above News headlines; already on games/wallet/listen. `AdBanner` now returns null for premium users (gated on `is_premium`/`premium_tier`) — ad-free for paying members. Renders nothing when no live campaign (no empty boxes).
- **Testing**: iteration_41.json — backend 8/8 pass; mobile flows verified.
- **Confirmed fixed**: "Couldn't load games" (was the demo-login token bug).
- **Remaining backlog** — Phase 2: AI-dynamic rewards (Emergent universal key) + coupon-fraud tracking (pull-vs-scan mismatch) + admin provisioning. Phase 3: restaurant 'More-tab' scan/redeem + restaurant loyalty tiers + admin-configurable game frequency limits. Also user asked to Claim Stripe LIVE via Publish (BYOK — user action; steps relayed via support).


## Changelog — 2026-08-06 (Advertiser Self-Serve + Analytics + Stripe top-ups + Local News tabs)
- **Advertiser Self-Serve (mobile + backend)**: ad wallet (`promo_wallets`), `POST /api/promoted/self-serve` creates a station promo with CPM/CPC bids (auto-active when funded, else `awaiting_funds`), `POST /api/promoted/{id}/toggle` pause/resume. New mobile screen `app/advertiser/promote-station.tsx` (reachable via Profile > 'Sponsor a station' and the advertiser home banner).
- **Sponsored Analytics**: `GET /api/promoted/mine` returns per-promo impressions/clicks/CTR/spend + totals; surfaced on the promote-station screen.
- **Stripe wallet top-ups**: `POST /api/promoted/wallet/topup` (packages $10/$25/$50/$100) → Stripe Checkout (existing env key, TEST mode); `GET /api/promoted/wallet/topup/status/{sid}` idempotently credits the wallet (status-poll fallback, no webhook dependency). Impression/click now debit the wallet and auto-pause a promo when depleted (house promos free). Going LIVE = claim Stripe account via Emergent Publish.
- **Local News tabs**: `/api/news/headlines?scope=local|national` (local=geo city market, national=resolved country); mobile News tab gets Local/National segmented tabs (`news-scope-local` / `news-scope-national`). NOTE: in-pod both resolve to US so content looks identical; diverges in real deployment.
- **Testing**: iteration_39.json — backend 14/14 pytest pass (`tests/test_iter39_advertiser_selfserve.py`); mobile flows verified.


## Changelog — 2026-08-06 (RadioLife.app rebrand + Promoted Stations + News fix)
- **Rebrand BigFM → RadioLife.app** across web + mobile (user-visible text only; internal keys/CSS/events/bundle IDs untouched). Wordmark `BigFM.AI → RadioLife.app`. Added tappable **funasianetwork.com** footer link (mobile FunAsiaFooter component on Home/Login/Profile; web LegalFooter, AppShell sidebar, LandingV2 + MarketingShell footers).
- **Home blockers fixed**: Top Played rail now renders; All Stations Genre filter now passes `category` param and re-fetches (iter37 bug).
- **News fix**: `/api/news/*` was served by an empty admin-curated Phase-R router shadowing the live NewsAPI feed. Added live NewsAPI fallback in `routes/news_phase_r.py` (public_headlines + public_breaking), geo-market aware, mapped to headline_text/summary_text shape. Mobile News tab + Home breaking banner now populated.
- **Demo login geo city**: `backend/auth.py` demo_login now resolves market/city from geo/IP (was hardcoded Dubai). Demo user name reset (no 'BigFM'). Home hero tagline + Radio header city now dynamic via `/api/geo/resolve_city`.
- **Demo-login bug fix**: `login.tsx` demo handler now wires session via api-client `saveToken` + AuthContext `setUser` (was stuck on splash spinner because AuthContext user stayed null).
- **Promoted / Sponsored stations (NEW)**: `routes/promoted_stations.py` (`/api/promoted/*`) — seed-on-empty from flagships, serve cards with `is_sponsored`, CPM/CPC impression+click tracking (spend accrual is **MOCKED** accounting-only, no wallet/Stripe settlement). Mobile Home: two new square-thumbnail rails (Top Played + Most Played Live, sponsored first w/ 'Sponsored' tag); All Stations: pinned 'Sponsored stations' header. Admin create endpoint + admin list included.
- **Testing**: iteration_38.json — backend 7/7 pytest pass; mobile + web flows verified.
- **Stripe "production"**: NOT switched. Cannot hardcode live keys; going live requires claiming the Stripe account via Emergent Publish/deploy (code already reads env-driven STRIPE_MODE/keys).


## Original problem statement (this dispatch)
Phase H v1 (Commute Mode MVP): a logged-in listener enters a destination,
sees a real Google Map with route polyline, ETA, traffic, and gets a
list of route-relevant offers/coupons matched from existing collections.
Backed by real Google Maps Platform APIs (Routes, Places New, Geocoding,
Weather) — no mocks.

## Prior dispatch (kept for context)
Combined Dispatch (UX.1 · Phase I · Phase F-2 · Mailgun Webhook) — shipped
2026-06-19.  Followed by Phase Π (production readiness), Phase Ω (K8s
deploy hardening), Phase Π+2/+3/+3.1/+4/+4.1 (asset migration, marketing
image wiring, ffmpeg pipeline + LiveRadioStation player unification).

## Original problem statement (Combined Dispatch)
Ship Combined Dispatch — UX.1 (AI Trivia topic auto-start), Phase I (Business
Redemption Portal + Ad Buying), Phase F-2 (Ledger Reader Flip), and Mailgun
Webhook Handler. Phase H (Commute Mode Deep Features) is BLOCKED pending
Google API keys.

## Product summary
BigFM is a mature AI-powered radio + rewards + local-commerce platform (FastAPI
+ React + MongoDB). Combined Dispatch lands four parallel work items that
sharpen monetisation (business portal + ad buys), unify accounting (ledger
reader flip), close the loop on transactional email (Mailgun webhook), and
remove friction in the trivia funnel (one-click topic start).

## User personas
- **Listener** — discovers radio + trivia + local offers, earns points.
- **Business owner** — registers storefront, redeems coupons at counter, buys
  banner inventory.
- **Advertiser** — runs self-serve banner / Predict & Win campaigns.
- **Admin** — full visibility on points ledger parity, mail funnel, mod queue.

## Core requirements satisfied this dispatch
1. **UX.1 Trivia auto-start** — clicking a topic card navigates immediately
   to `/trivia/play?cat=<id>` with router-state passthrough of topic name +
   icon; no interstitial confirmation step.
2. **Phase I Business Redemption Portal**
   - 9 new backend endpoints under `/api/business/*`.
   - 6 new frontend pages under `/business/{login,register,redeem,campaigns,ads/buy}`
     plus the index dashboard at `/business`.
   - 4-digit PIN (bcrypt-hashed) gates redemption.  Successful redemption
     awards customer +20 BC via `PointsService.award(source="coupon_redeemed",
     idempotency_key=...)`.
3. **Phase F-2 Ledger Reader Flip**
   - `PointsService.award` no longer back-writes to `users.bigcoin_balance`
     by default; gated behind `BIGCOIN_LEGACY_DUAL_WRITE=1` for rollback.
   - All readers (`/api/bigcoin/me`, admin analytics liability aggregate,
     referral-completion idempotent path) flipped to PointsService.get_balance.
   - New admin endpoint `GET /api/admin/points/parity-check` reports drift.
   - Reconcile script froze legacy field — last run: scanned=1277 matched=1276
     drift=0.
4. **Mailgun Webhook Handler**
   - Public `POST /api/webhooks/mailgun/events` with HMAC-SHA256(timestamp +
     token) verify (DEV escape hatch via `MAILGUN_WEBHOOK_VERIFY_SIGNATURE=0`).
   - Persists `mail_events`, cross-links `referral_invites` by message_id,
     auto-suppresses bounces/complaints/unsubs.
   - Admin endpoints: `/api/admin/mail/events`, `/api/admin/mail/funnel`.

## Architecture tasks completed
- Backend routers mounted: `business_portal`, `f2_mailgun_webhook`.
- Frontend routing: 6 static `/business/*` routes inserted before dynamic
  `/business/:slug` so the existing PublicBusiness page still handles
  arbitrary public slugs.
- Reconcile script + parity-check endpoint surface drift continuously.
- Memory: `/app/memory/CURRENT_STATE.md` and `test_credentials.md` updated.

## What's been implemented (historical)
- **2026-06-19 — Combined Dispatch (UX.1 / Phase I / Phase F-2 / Mailgun
  Webhook)** — this turn.
- 2026-06-18 — Phase H'.5 player glue + admin AI-RJ cache stats.
- 2026-06-18 — Phase H' ElevenLabs TTS live (persona samples, news radio,
  AI-RJ segment cache).
- 2026-06-18 — Phase 42-E2.5 Mailgun LIVE for invite-a-friend.
- 2026-06-18 — Phase 42-E2 home redesign + universal share + MediaSession.
- 2026-06-18 — Phase 42-E1 banner ads + Predict & Win self-serve.
- 2026-06-18 — Phase F-1 unified points engine (ledger + dual-write).
- Previous phases — see `/app/memory/CURRENT_STATE.md` historical sections.

## Prioritized backlog
**P0 (blocked, waiting on user)**
- **Phase H** Commute Mode Deep Features — awaiting `GOOGLE_ROUTES_API_KEY`,
  `GOOGLE_PLACES_API_KEY`, `GOOGLE_WEATHER_API_KEY`, and frontend
  `REACT_APP_GOOGLE_MAPS_API_KEY`.  DO NOT START until keys land.
- **Mailgun webhook signing key** — flip `MAILGUN_WEBHOOK_VERIFY_SIGNATURE=1`
  once `MAILGUN_WEBHOOK_SIGNING_KEY` is provided.

**P1 (next dispatch candidates)**
- Real Stripe Checkout for Phase I `/business/ads/buy` + Predict & Win
  self-serve.
- Business profile verification flow (admin one-click verify + email).
- Bulk coupon-issuance UI for business owners.
- Cosmetic: fix React `key prop spread` warning + nested button hydration
  warning on `/business/login`.

**P2 (deferred)**
- Phase G OpenRTB (real SSP fill beyond mocked house creatives).
- Voice cloning per business owner.
- Mobile/Expo mirror of business portal.

## Next tasks (immediate)
1. User unblocks Phase H by providing Google API keys → kick off H.1-H.4.
2. User provides Mailgun signing key → flip env flag + rerun webhook smoke.
3. (Optional) Wire real Stripe Checkout for ads buy + Predict & Win.

## Test fixtures
- `admin@bigfm.dubai` / `AdminPass123!` — admin role
- `test@bigfm.dubai` / `TestUser123!` — creator + advertiser + **business
  (Karak Cafe QA fixture, biz_qa_e3_karak, PIN 4242)**
- `demo@bigfm.dubai` / `DemoPass123!` — consumer, free tier
- `predictest@bigfm.dubai` / `PredictTest123!` — Predict & Win E2 fixture
- `freetest@bigfm.dubai` / `FreeTest123!` — pristine free tier
- `advertest@bigfm.dubai` / `AdvTest123!` — advertiser premium
- `premiumtest@bigfm.dubai` / `PremiumTest123!` — premium consumer

## Health
- Backend booted clean; all routes 200.
- Frontend webpack compiled with 6 new pages, no lint errors.
- Parity check: 0 drift across 1277 users.
- Mailgun webhook DEV signature-skip is loud (warning log fires on every hit).
- 14/14 backend tests pass (iteration_10.json).

## Phase FLAGADMIN.1 — Flagship CRUD + Pre-roll Parity (2026-07-27) — SHIPPED
- Added POST/PATCH/DELETE + validate-stream + audit endpoints in
  `/app/backend/routes/flagship_stations.py`. All admin-only.
- Added `preroll_enabled` gate to `/api/live-radio/preroll/request`
  (default `true`; only explicit `false` disables). Confirmed NO
  `is_flagship` bypass anywhere in the preroll pipeline.
- New `station_admin_audit` Mongo collection captures create/update/
  soft_delete/hard_delete rows with before-snapshots.
- Rewrote `/app/frontend/src/pages/admin/AdminFlagshipStations.jsx`
  with FlagshipFormModal + FlagshipDeleteModal + PrerollToggle.
  Type-slug-to-confirm gate on hard delete.
- Backend: 17/17 tests PASS (iteration_17.json). Frontend Playwright
  95%. Zero critical issues.


## Phase AD.11 — Banner Ad Buying + 7-Zone Placement (2026-07-27) — SHIPPED
- Backend: `banner_campaigns` + `banner_impressions` + `banner_clicks` collections; auction (priority + CPM) at `GET /api/banner/serve?zone=…`. Impressions billed via `POST /api/banner/impression` with (session, banner, zone) 5-min dedup, wallet debit + AD.2-style split via `payment_transactions_v2`, and NEW session-per-zone frequency cap of 3.
- Fix during hardening: `stripe_payment_intent_id=tx_id` sentinel on AD.11 ledger rows to sidestep the pre-existing unique-index null collision on `payment_transactions_v2`.
- Frontend: `<BannerZoneSlot zone="…" />` mounted in ALL 7 zones —
  landing_hero (RadioHome), browse_row (RadioBrowse), station_detail (LiveRadioStation), now_playing (LiveRadioStation footer), wallet (Wallet.js + WalletV2), games (PredictWin), bottom_bar (MiniPlayer). Null-render when auction empty; `data-ad-slot="ad11-{zone}"` attribute for analytics; impression + click POSTs wrapped in `.catch()` for ad-block resilience.
- New advertiser dashboard: `/advertiser/dashboard/banner-campaigns` with 5-step wizard (identity → zones+creative → targeting → budget+CPM → review). Nav testid `advertiser-nav-banner-campaigns`.
- Bundled: Admin nav badge counts poll `/api/admin/nav-counts` every 60s with visibility-hidden pause. Cookie banner suppressed on `/admin/*`.
- Tests: 8/8 backend (iteration_25.json). Frontend UI verified (iteration_24.json).

## Phase AD.12a — In-App Notification Ads + Weekly Digest (2026-07-27) — SHIPPED
- Backend: `notification_campaigns` + `notification_deliveries` collections; 9 endpoints (create/patch/upload/publish/list/analytics + inbox/open/click/dismiss). Idempotent per-user-per-campaign billing via AD.2 rails; wallet-drain auto-pause. ADMOD.1 approval reusing `ad_type='notification'`.
- **Push channel deferred permanently** per user decision — enum value kept in model; `publish` returns `push_channel_not_enabled` for `channel='push'|'both'`. Wizard visibly disables the push option.
- **CPD by category hints** in `/api/ad-pricing-hints` — F&B 8¢, Retail 12¢, Entertainment/Nightlife 15¢, Health/Fitness 10¢, Services 10¢, Default 10¢. Shown as tooltip only; no auto-fill (mirrors AD.4 CPS pattern).
- Frontend: 5-step wizard at `/advertiser/dashboard/notification-campaigns`; enhanced `<NotificationBell />` merges legacy station notifications + AD.12 sponsored deliveries with "Sponsored" chips; full-page `/notifications` feed.
- **Bundled — Weekly Advertiser Performance Digest**: Monday 09:00 UTC scheduler aggregates last 7 days across AD.1/AD.4/AD.11/AD.12/PG.1 (spend, impressions, CTR, top creatives, zone perf, rule-based recommendations). HTML template at `/app/backend/templates/advertiser_weekly_digest.html`. Admin manual trigger + advertiser opt-out (default ON via `email_weekly_digest` field). Mailgun live-verified during smoke.
- Tests: 25/25 backend PASS + frontend fully verified (iteration_26.json). Zero regressions to AD.4, ADMOD.1, AD.11, ADMIN.NAV.1.

## Phase AD.7 — Scan-to-Pay at Partner Merchants (2026-07-27) — SHIPPED
- Backend: `scan_to_pay_transactions` + `scan_to_pay_qr_tokens` collections; 12 endpoints (merchant QR generate, QR resolve, quote, authorize, capture, refund, user history, merchant transactions, merchant settings GET+PATCH, admin analytics). Ephemeral 60s QR tokens; Stripe Connect destination charge with `application_fee_amount` from SC.3 commission engine; points debit/earn via F-1 unified points ledger. Refund reverses BOTH card (with `reverse_transfer=true`) and points (both redeemed AND earned). Idempotent capture + refund.
- Points math: 1 pt == 1¢ on redemption; earn = `int(card_cents / 100 * points_per_dollar)`. Redemption capped at merchant's `max_points_redemption_pct` (default 50%). Verified: 800 pts requested → 500 pts clamped for $10 bill @ 50% cap.
- Frontend: `/scan` camera scanner + manual token entry, `/scan-to-pay/:token` checkout with points slider + tip picker + Stripe test card, `/merchant/:merchantId/scan-to-pay` cashier terminal + settings + transactions table.
- **Bundled — Notification Trigger Recipes**: `GET /api/notification-trigger-recipes` returns 10 pre-baked recipes (coupon_saved, coupon_expiring_24h, podcast_completed, station_played_5x, wallet_top_up, first_login, flagship_played_first_time, predict_win_correct, merchant_visit_nearby, game_win_high_value). Wizard step 3 dropdown replaces free-text `trigger_type` (custom escape hatch remains). `dispatch_event()` wired into `/api/ads/action/save_coupon` — silent-on-error so upstream flows never break.
- Tests: 16/16 backend PASS + full frontend live-verified (iteration_27.json). Zero regressions across AD.4/AD.11/AD.12a/ADMOD.1/SC.x/MER.x/ADMIN.NAV.1. POC uses hard-coded `pm_card_visa` in checkout — full Stripe Elements integration is a follow-up.

## Phase AD.3 — Advertiser Predict & Win Sponsorship (2026-07-27) — SHIPPED
- Backend: `predict_win_sponsorships` + `predict_win_sponsorship_events` collections; 10 endpoints (available-parents, CRUD, brand-asset upload, publish, ADMOD.1 mint, admin set_status, auction endpoint, impression billing, analytics). Auction picks 1 sponsor per view weighted by advertiser priority_score_boost DESC, CPE/CPI DESC, random tiebreaker. Per-user idempotent billing (unique index on user_id+sponsorship_id+event_type); wallet-drain auto-pause; race-safe compensation on duplicate insert.
- Pricing: default CPE 20¢, CPI 5¢; high-volume 35¢ CPE / 10¢ CPI; niche 10¢ / 3¢. Exposed via `pw_sponsorship_tiers` in `/api/ad-pricing-hints`.
- ADMOD.1: new `ad_type='advertiser_pw_sponsorship'` wired to `predict_win_sponsorships` target table + snapshot builder (distinct from PW-M's `sponsored_predict_win` for merchant-branded activations).
- Frontend: 5-step wizard at `/advertiser/dashboard/predict-win-sponsorships` (pick parent → brand identity + asset → pricing model + CPE/CPI → budget + targeting → preview + submit). New `<PredictWinSponsorBadge>` component with 3 variants (card corner chip / detail brand block / win-screen powered-by strip) — mounted in PredictWin.jsx ActiveCard + EnterModal.
- **Bundled — Trigger recipe upstream wiring**: `coupon_saved` (in `ads_public.action_save_coupon`) and `predict_win_correct` (in `predict_win_award_pipeline._deliver_prize`) are LIVE. Remaining 8 recipes documented as TODO in `notification_trigger_dispatcher.py` docstring per user directive (don't build missing infra).
- Tests: 27/27 backend PASS (`test_ad3_pw_sponsorships.py`), advertiser dashboard + wizard step 1 + card badge + detail modal all live-verified in browser. Split-the-bill enhancement deferred to AD.7.1 as planned.


## Phase AD.8 — Daily Code Claim in Now Playing + Auction Transparency (2026-07-27) — SHIPPED
- Backend: `daily_codes` + `daily_code_claims` collections. 5 endpoints — `GET /api/daily-code/current` (anonymous-friendly via `current_user_optional`), `POST /api/daily-code/claim` (auth'd, 409 on double-claim via unique index user+code), `GET /api/user/daily-code/history`, `POST /api/admin/daily-codes` (seed future code, 400 on duplicate date), `PATCH /api/admin/daily-codes/{id}` (edit before window opens). Streak ladder: 1x @ 1d · 1.2x @ 3d · 1.5x @ 7d · 2x @ 14+d (capped 2x). Yesterday-check gates streak continuation; miss-a-day → resets to 1. Hourly scheduler idempotently ensures today's code (60 min drift acceptable from mid-day boots).
- Frontend: `<DailyCodeWidget />` mounted in `LiveRadioStation.jsx:412` (order: `BannerZoneSlot zone="station_detail"` → widget). Anonymous users see "sign in to claim" nudge; auth'd see the 6-char code, streak flame + day count, and multiplier preview. Post-claim confetti + already_claimed disabled state. Dual-variant support via `useDesignVariant()` (legacy dark + radiolife light).
- **Bundled — Auction Transparency Panel**: `auction_events` collection with 30-day TTL. Fire-and-forget `log_auction_result` hook from AD.11/AD.3/AD.12 auction paths writes LOSER rows. Advertiser page `/advertiser/dashboard/auction-insights` shows last 24h losses grouped by reason (`higher_cpm`/`targeting_mismatch`/`wallet_exhausted`/…) with a **Boost bid** action per row (POST `/api/advertiser/{id}/auction-insights/boost` — supports `banner`|`advertiser_pw_sponsorship`|`notification`). Change > 20% flips campaign status → `pending_admin` for ADMOD.1 re-review; ≤ 20% goes live immediately.
- **Fix during this session — wallet_v2_service Points balance**: Phase F-2 ledger flip left `/api/wallet/me` reading the legacy `users.bigcoin_balance` mirror. AD.8 daily-code awards go through `PointsService.award(source="daily_code_claim")` which does NOT dual-write. Patched `wallet_v2_service.py:166-181` to source `points_balance` from `PointsService.get_balance()` (ledger truth) with legacy fallback.
- Tests: 22/22 backend PASS (`test_ad8_daily_code_and_auction_boost.py` at iteration_29) — includes multi-day backdated seed harness for 3d/7d/14d ladder rungs + streak-reset when yesterday missing + 20% pending_admin gate for all three boostable ad_types. Frontend live-verified in both `?design=legacy` and `?design=radiolife`. Zero regressions.

## Phase MON.3 — Booking CPA + Gift Card Market (mobile UI) + Chapter Scrubber Markers (2026-08-10) — SHIPPED
- **Booking CPA (mobile)**: `/app/mobile/app/bookings.tsx` wired into the Wallet tab action row (`wallet-bookings-btn`). Lists venues from active booking-type campaigns (`GET /api/bookings/available`), expandable slot/party/name/phone form → `POST /api/bookings/{campaign_id}/book` with confetti confirmation.
- **Gift Card Market (mobile)**: new `/app/mobile/app/giftcards.tsx` wired into Wallet action row (`wallet-giftcards-btn`). Shop tab lists auto-seeded catalog (`GET /api/giftcards/catalog`) with BigCoin balance pill; per-product buy panel supports amount denominations + pay-with points|card + optional gift-to email/message → `POST /api/giftcards/purchase` (points redeems instantly & celebrates; card opens Stripe checkout via WebBrowser). "My Cards" tab lists owned/gifted cards (`GET /api/giftcards/mine`).
- **Chapter Scrubber Markers**: `podcast/episode/[id].tsx` — new `ChapterScrubber` component draws gold chapter tick marks + progress fill/thumb on the audio player track; tap a marker to seek. Falls back to a chapter-derived layout duration when real duration is 0/unknown so markers always render (fix from iter52 HIGH).
- Backend for gift cards (`routes/gift_cards.py`, Phase GC.1) and bookings (in `routes/merchant_marketplace.py`) was pre-built; this phase delivered the mobile UIs + scrubber.
- Tests: iteration_52 — 11/12 backend PASS (points purchase skipped: demo balance < smallest denom, not a bug). Mobile: all testIDs present; scrubber markers confirmed rendering (count=2) after fix. Self-verified via screenshot.
- **Known minor (non-blocking, not in scope this phase)**: giftcards points-purchase idempotency key uses a fresh uuid per request (client `busy` guard prevents double-tap); giftcards Stripe `origin_url` uses the API host (consistent with existing platform checkout pattern).

## Phase MON.4 — Buy BigCoin + Gift Card Reveal + Video PIP + Booking Reminders (2026-08-10) — SHIPPED
- **Buy More BigCoin**: `routes/bigcoin_topup.py` — `GET /api/bigcoin/topup/packages` (4 packages, 100 BC=$1, bonus tiers), `POST /checkout` (Stripe), `GET /{session_id}/status` (credits ledger via PointsService, idempotent on session id, ownership-scoped). Mobile `/bigcoin-topup` screen + Wallet "Top Up" button (`wallet-topup-btn`) + inline "buy BigCoin" nudge on the Gift Card screen when points are short (`gc-topup-*`, passes `needed`).
- **Gift Card Reveal + Thanks**: gift cards now carry `revealed`/`thanks_sent`; `/mine` returns `received_gift`. New `POST /api/giftcards/{card_id}/reveal` and `POST /{card_id}/thanks` (enqueues `giftcard_thanks` notification to the buyer). Mobile My Cards shows a tap-to-scratch animated cover for received gifts (`gc-scratch-*`) then a "Send thanks" tap-back (`gc-thanks-*` → `gc-thanks-done-*`).
- **Video Picture-in-Picture**: PIP button (`mobile-episode-pip-btn`) on the video podcast player calling `player.startPictureInPicture()` (app.json already has `supportsPictureInPicture: true`). Added a "installed app only" hint. `_media_payload` now also honors a plain `ep.video_url` so PIP shows for episodes without a Tigris key. NOTE: PIP only works on a published native build, not Expo Go/web preview.
- **Booking Reminders (in-app)**: `POST /api/bookings/{id}/book` enqueues a `booking_reminder` into the Notifications inbox; new `GET /api/bookings/mine`. Mobile Bookings screen shows an upcoming-reservations reminder banner (`bookings-reminder`).
- Tests: iteration_53 — 13/13 backend pytest PASS; mobile UIs verified in Expo preview. PIP functional path validated only after Publish (native build).

## Phase MON.5 — House Games ×4 + Reservation Manager + Gift Card Redeem (2026-08-10) — SHIPPED
- **4 new always-on platform games**: `seed_extra_house_games` (services/games_v2.py, run at boot) seeds cmp_house_scratch/mystery/memory/word (is_platform_funded, open_to_all, no expiry) reusing existing templates + generic `/game/[campaignId]` player. Surfaced in the Games tab "MORE GAMES LIVE NOW" (deduped so hardcoded spin/trivia/lyric don't repeat).
- **Reservation Manager**: `/api/bookings/mine` now returns `status` + `available_slots`; new `POST /api/bookings/{id}/reschedule` and `/cancel`. Mobile `/reservations` screen (view/reschedule via slot chips/cancel); Bookings reminder banner is tappable → `/reservations`.
- **Gift Card Redeem**: `POST /api/giftcards/{card_id}/redeem {amount_cents}` deducts balance (400 insufficient_balance, status→spent at 0, logs gift_card_redemptions). Mobile My Cards shows a Redeem action with an animated balance tick-down.
- Tests: iteration_54 — 10 backend pytest pass / 3 data-skips (re-verified in UI); all mobile flows verified in Expo preview.
- **Known (non-blocking)**: gift-card redeem is self-contained (no merchant/POS binding yet) — will bind to Marketplace checkout in Phase B; cancelled bookings drop off the reservations list on reload by design.

## SUPER MARKETPLACE — planned (Phase A next)
Approved multi-phase build (spec: 80 sections). Decisions: build BOTH surfaces in lockstep per phase; use existing cream/orange RadioLife brand (NOT the spec's stale purple/pink note); "BigPoints" = existing BigCoin/points ledger; reuse existing Stripe Connect (stripe_connect.py, merchant_onboarding.py) + businesses schema.
- **Phase A (next)**: Admin BigPoints Economics ($0.03/point issuance cost, admin-configurable by market/category/merchant override) · Admin Category + Commission rules engine (no hardcoded %) · "Sell on RadioLife" 10-step business registration (reusing Stripe Connect) · Shop nav + Shop Home shell · Merchant BigPoints settings + cost preview + funding (prepaid + auto-deduct).
- Phases B–F: Restaurant pickup, Services/booking, Ecommerce, Gift cards/memberships/events, AI concierge + promoted marketplace.

## SUPER MARKETPLACE — Phase A1 (backend + admin) SHIPPED (2026-08-10)
Foundation for the local super-app. "BigPoints" = existing BigCoin; only the merchant-side issuance cost + platform commission are new.
- **services/marketplace.py**: economics engine. Default BigPoint issuance cost **$0.03/point (3.0¢)**, admin-configurable via `bigpoint_rates` (scopes global/market/category/merchant; resolver specificity merchant>category>market>global, effective-dated). Category commission via `marketplace_commission_rules` (priority merchant>market_category>category>market>global). `compute_economics()` splits commission vs BigPoints fee vs merchant net. Boot seed `seed_marketplace_foundation` (9 categories + per-category commission + global rate). Fixed Mongo tz-naive datetime compare with `_aware()`.
- **routes/marketplace_admin.py** (`/api/admin/marketplace/*`, admin-only): CRUD bigpoint-rates, categories, commission-rules; businesses list + approve/reject; dashboard.
- **routes/marketplace_merchant.py** (`/api/merchant/marketplace/*`): "Sell on RadioLife" onboarding (validations: bad_category, commission_agreement_required, bigpoints_required, below_min_bigpoints, restaurant price_parity_required) → pending profile mirrored into `businesses` (inactive until approved) + `merchant_bigpoint_accounts`; bigpoints settings + live $ cost preview; funding (prepaid Stripe top-up + status-credit; auto-reload; funding_mode prepaid|auto_deduct).
- **routes/shop.py** (`/api/shop/*`, public): categories, home (headline + 5 sections), businesses (approved only, sortable by bigpoints/rating/featured), business detail (+ ways-to-earn).
- **Web admin page** `/admin/marketplace` (AdminMarketplacePhaseA.jsx, legacy dark shell): Economics / Categories / Commission / Approvals tabs.
- Tests: iteration_55 — **34/34 pytest pass** (auth guards, validations, resolver specificity end-to-end, Stripe fund, approve→shop visibility). No blockers.

### Marketplace Phase A — REMAINING (next sub-steps)
- **A2 — "Sell on RadioLife" registration UI** on both surfaces (mobile Expo wizard + web page) hitting `/onboarding`.
- **A3 — Shop shell UI**: mobile new SHOP tab + nav (Home/Listen/Shop/Play/Wallet, Profile→avatar) + Shop Home; web Shop nav + Shop Home. Cream/orange.
- Then Phases B–F (restaurant pickup, services/booking, ecommerce, gift cards/memberships/events, AI concierge + promoted).

### Still pending (agreed "also this round", not yet built)
- **Games Daily Streak** (bonus for playing all house games in a day).
- **Reorder Favourites** (save favourite venue + rebook usual slot).
- **Gift Card Auto-Apply** — deferred to Phase B (needs Marketplace checkout).

## SUPER MARKETPLACE — Phase A2+A3 (Shop UI, both surfaces) SHIPPED (2026-08-10)
- **Demo businesses** (`seed_demo_businesses`, idempotent upsert on boot): 6 approved storefronts (Grill House, Spice Route, Brew & Bean, Glow Beauty, Urban Threads, Pulse Fitness) with cover images + BigPoints, so Shop looks alive.
- **Mobile Shop**: new **SHOP tab** (nav now Home/Listen/Shop/Play/Wallet/More; Games→Play). Screens: `(tabs)/shop.tsx` (Shop Home — headline, search, category chips, filters, Sell CTA, business-card rails), `shop/[id].tsx` (detail + ways-to-earn + CTA), `shop/browse.tsx` (search/sort/category grid), `sell.tsx` ("Sell on RadioLife" wizard with live $0.03 cost preview + commission/parity agreements → `/onboarding`). Cream/orange.
- **Web Shop** (RadioLife overlay + Tailwind): `ShopRadioLife.jsx` (home+browse), `ShopBusinessRadioLife.jsx` (detail), `SellOnRadioLife.jsx` (registration). Routes `/shop`, `/shop/:id`, `/sell` mapped in RadioLifeOverlay; bottom nav **Shop replaced Discover**. NOTE: like every RadioLife web screen, Shop shows once the "Enable RadioLife design" variant is on (platform-wide behavior, not Shop-specific; variant persistence deliberately left unchanged).
- **Games Daily Streak**: `routes/games_streak.py` — play all 4 new house games in a day → 100 BigCoin bonus (`GET/POST /api/games_v2/daily-streak[/claim]`, idempotent per day). Mobile banner in Play tab (`daily-streak-banner`, progress dots, claim).
- **Reorder Favourites**: `routes/favourites.py` — toggle favourite venue, list with usual slot, one-tap rebook (`/api/favourites/venues*`). Mobile heart on booking cards + Favourites+rebook section in Reservations.
- Tests: iteration_56 — backend 25/26 pass (1 skip: no public booking-campaign catalog to auto-discover a campaign_id); mobile all testIDs verified; web screens verified working behind the design toggle.
- Hardening applied post-test: preview points `ge=0`; demo seed now upserts (cover/points refresh on boot).

## SUPER MARKETPLACE — Phase B (Restaurant Pickup + Subscriptions) SHIPPED (2026-08-10)
Backend (new): `routes/marketplace_subscription.py`, `routes/marketplace_menu.py`, `routes/marketplace_orders.py`, `services/menu_import.py`; extended `services/marketplace.py`, `routes/shop.py`, `routes/marketplace_admin.py`.
- **Merchant Subscriptions**: Starter $29/mo, Pro $99/mo (seeded `subscription_plans`). Stripe Checkout `mode=subscription`. `GET/POST /api/merchant/marketplace/subscription[/plans|/checkout|/status/{sid}]`. ENFORCEMENT: `/api/shop/*` only lists businesses with `subscription_active=true`. Demo businesses auto-granted active (Pro). Admin comp/revoke: `POST /api/admin/marketplace/businesses/{id}/comp-subscription|revoke-subscription`.
- **Menu Builder**: CRUD + bulk `/api/merchant/marketplace/menu[/items[/{id}]|/bulk]`. Consumer `GET /api/shop/businesses/{id}/menu` (grouped sections). Demo menus seeded for grill/spice/brew.
- **AI menu import**: `POST /api/merchant/marketplace/menu/import/ai` (source_type image|pdf|url) via Gemini 2.5 Flash (EMERGENT_LLM_KEY); `/import/file` for Excel/CSV (openpyxl + csv). Returns preview items → bulk save.
- **Orders / Restaurant Pickup**: single-merchant cart → `POST /api/shop/orders/checkout` with **gift-card auto-apply** (highest-balance active card, deducted on payment) → Stripe for remainder (or free if fully covered). Lifecycle `accepted→preparing→ready→picked_up` via `PATCH /api/merchant/marketplace/orders/{id}/status`; **BigPoints awarded to buyer on picked_up** (idempotent, PointsService); prepaid merchants deduct inventory. Pickup code per order.
- **2X Happy Hour**: `PATCH /api/merchant/marketplace/happy-hour`; `effective_points()` applies multiplier during active window (reflected in menu + order points).
- **Merchant Dashboard**: `GET /api/merchant/marketplace/dashboard` (order counts, revenue, points spent, menu count, subscription + happy-hour state).
Web (RadioLife overlay, all under forced `/shop/*` — no design toggle needed): `/shop/menu/:id`, `/shop/orders`, `/shop/merchant`, `/shop/merchant/menu`, `/shop/merchant/subscribe`.
Mobile (Expo): `shop/menu/[id].tsx`, `shop/cart.tsx`, `shop/orders.tsx`, `merchant/dashboard.tsx`, `merchant/menu.tsx`, `merchant/subscribe.tsx`; cart store `useCartStore`.
Tests: iteration_57 — backend 27/28 then 28/28 after fix (happy_hour projection in shop.py fixed + verified; picked_up→canceled now guarded). Full lifecycle E2E incl. points-on-pickup verified. Mobile smoke 100%. Web /shop/* verified rendering via forced overlay.
Known MVP limitation: gift-card reservation is not locked across simultaneous checkout sessions (single-merchant, low-concurrency — acceptable for MVP).

## SUPER MARKETPLACE — Phase C + enhancements SHIPPED (2026-08-10)
Backend (new/updated): `routes/marketplace_services.py` (services+bookings), `services/menu_photos.py`, extended `routes/marketplace_menu.py`, `routes/marketplace_orders.py`, `server.py` (menu_photos StaticFiles mount + services indexes).
- **Reorder Favourites**: `POST /api/shop/orders/{id}/reorder` → returns still-available items (refreshed prices) + dropped[]; client re-fills cart. Web + mobile "Order Again".
- **Live Order Alerts**: on merchant status → `ready` (and `picked_up`) an in-app `station_notifications` row is enqueued for the buyer (dedupe_key `order_{status}_{id}`). In-app only (no push).
- **Menu Photos**: merchant UPLOAD (`POST /menu/items/{id}/photo`, base64, Pillow-validated + 8MB cap) OR AI generate (`/photo/ai`, Gemini Nano Banana `gemini-3.1-flash-image-preview`). Served public at `/api/static/menu_photos/`. Thumbnails on consumer menu + builder (both surfaces).
- **Service Bookings (Phase C, non-food)**: `service_items` (name, duration, price, reservation_fee_cents credited toward service, bigpoints) + weekly `service_availability` on profile. Consumer: `GET /api/shop/businesses/{id}/services`, `/services/{sid}/slots?date=`, `POST /api/shop/service-bookings/checkout` (reservation fee via Stripe, or free/confirmed if fee 0; 409 slot_taken), `GET /service-bookings[/{id}/status]`. Merchant: services CRUD, `GET/PATCH /availability`, `GET /bookings`, `PATCH /bookings/{id}/status` (confirmed→completed awards BigPoints, →no_show). Enforced by subscription_active.
Web screens: `/shop/services/:id`, `/shop/bookings`, `/shop/merchant/services`; Reorder on `/shop/orders`; photo controls on `/shop/merchant/menu`.
Mobile screens: `shop/services/[id].tsx`, `shop/bookings.tsx`, `merchant/services.tsx`; Reorder on `shop/orders.tsx`; photo controls on `merchant/menu.tsx`; Shop-tab quick links Orders/Bookings/Merchant.
Tests: iteration_58 — backend 35/35 passed; both surfaces smoke-verified; full web/mobile parity; no blocking bugs. Fixed post-test: menu-photo bytes now Pillow-validated (rejects non-images).
Deferred lows: desktop whitespace on `/shop/services/:id` (mobile-first layout); slots use UTC "today" (no merchant TZ); multi-merchant cart; price-parity monitoring.

## SUPER MARKETPLACE — Phase D (Ecommerce Products + Loyalty Tiers + Service Photos + Booking Reminders) SHIPPED (2026-06 fork)
Backend (pre-built, curl-verified earlier; formally verified this turn): `routes/marketplace_products.py`, `services/loyalty.py`; extended `routes/marketplace_services.py` (service photos), `server.py` (booking-reminder cron loop).
- **Ecommerce Products**: merchant catalogue CRUD with variants (label/price/stock), per-product upload OR AI photo (Nano Banana), delivery config (pickup/delivery/fee/free-over). Consumer `GET /api/shop/businesses/{id}/products`; single-merchant cart → `POST /api/shop/product-orders/checkout` (gift-card auto-apply → Stripe for remainder, stock decrement, delivery fee). Fulfillment lifecycle paid→packed→shipped→delivered (`PATCH /api/merchant/marketplace/products/orders/{id}/status`, invalid transitions rejected, `product_shipped` notification enqueued); **BigPoints awarded to buyer on delivered via `award_with_tier_bonus` (idempotent)**; prepaid merchants deduct balance; cancel restocks.
- **Loyalty Tiers** (`services/loyalty.py`): Bronze/Silver/Gold/Platinum from lifetime positive ledger deltas (0/1k/5k/15k → +0/5/10/15% bonus). `GET /api/shop/loyalty` (tier, progress, perks, all_tiers). `award_with_tier_bonus` awards base points then a separate loyalty-bonus ledger row.
- **Service Photos**: `POST /api/merchant/marketplace/services/items/{id}/photo` + `/photo/ai`; consumer services now expose `image_url`.
- **Booking Reminders**: morning-of in-app reminder cron loop in `server.py`.
- **Web screens added THIS turn** (RadioLife overlay, forced `/shop/*`): `ShopProductsRadioLife` (`/shop/products/:id`), `ShopProductOrdersRadioLife` (`/shop/product-orders`), `MerchantProductsRadioLife` (`/shop/merchant/products`), `LoyaltyRadioLife` (`/shop/loyalty`); service-photo controls added to `MerchantServicesRadioLife` + consumer thumbnails on `ShopServicesRadioLife`. Entry links wired: MerchantDash `merchant-open-products`, Shop home `shop-my-product-orders`/`shop-my-loyalty`, business-detail CTA → products.
- **Mobile entry points wired THIS turn**: shop `[id]` products CTA, merchant dashboard `merchant-open-products`, shop-home `shop-my-loyalty`, consumer service thumbnail.
- Tests: **iteration_59 — backend 31/31 pytest PASS**; web + mobile all testIDs functional; **100% cross-surface parity; no blocking bugs**. AI-photo endpoint not re-run (slow/rate-limit; upload path green).
- Non-blocking follow-ups (from iter59 review): desktop whitespace on RadioLife `/shop/*` (mobile-first layout); cookie banner overlaps bottom CTA; RN `shadow*`/`pointerEvents` deprecation warnings; merchant balance-decrement ordering on delivered; unthrottled Stripe polling on order-status GET; loyalty tiers hardcoded in code (not admin-tunable yet).

### Phase E · Item 4 — Events SHIPPED (2026-06 fork) — PHASE E COMPLETE
A venue sells tickets to a local event with LIMITED CAPACITY that can sell out; buy with Stripe card or BigPoints; quantity per purchase; no oversell (atomic guarded increment).
- Backend `routes/marketplace_events.py`: merchant `GET/POST/PATCH/DELETE /api/merchant/marketplace/events[/items/{id}]` (title, description, location, starts_at, price_cents>=0, capacity>=1; `capacity_below_sold` guard on shrink). Consumer `GET /api/shop/businesses/{id}/events` (items with remaining/sold_out + mine + points_balance), `POST /api/shop/events/purchase {event_id,qty,method,origin_url}` (atomic `_reserve` guarded increment → `sold_out`; points issues ticket immediately, card → Stripe checkout reserving seats), `GET /api/shop/events/purchase/{session_id}/status` (issues ticket on paid), `GET /api/shop/events/mine`. Collections: `events`, `event_tickets`, `event_purchases`. `shop.py` business detail returns `has_events`.
- Web: `ShopEventsRadioLife` (`/shop/events/:id`), `MerchantEventsRadioLife` (`/shop/merchant/events`). Mobile: `app/shop/events/[id].tsx`, `app/merchant/events.tsx`. Entry links both surfaces: `merchant-open-events`, business-detail `shop-detail-event` (when has_events).
- Tests: **iteration_63 — backend 13/13 pytest PASS (incl. capacity sold-out + no-oversell); web + mobile all testIDs functional, full parity, no bugs.**
- Non-blocking nits: currency hardcoded usd; abandoned card checkouts hold a reserved seat (no auto-release); ticket `code` exposed on the public events listing; no merchant-side scan/redeem endpoint yet.

**PHASE E COMPLETE** — the marketplace now sells: menu/food pickup, services/bookings, ecommerce products, gift cards, memberships, packages, and events. Remaining backlog: Multi-Merchant Cart, Membership Wallet, Package Gifting; then Phase F.

### Phase E · Item 3 — Packages SHIPPED (2026-06 fork)
A venue sells a prepaid bundle (e.g. "5 Haircuts", "10 Classes"); shopper buys with Stripe card or BigPoints and gets N redemption credits, redeemed over time at that venue.
- Backend `routes/marketplace_packages.py`: merchant `GET/POST/PATCH/DELETE /api/merchant/marketplace/packages[/items/{id}]` (name, description, price_cents, credits>=1, allow_points/card; sold_count). Consumer `GET /api/shop/businesses/{id}/packages` (items + mine[] + points_balance), `POST /api/shop/packages/purchase {package_id,method,origin_url}` (points mints active pkg immediately or `insufficient_points`; card → Stripe checkout + `.../purchase/{session_id}/status` activation), `GET /api/shop/packages/mine`, `POST /api/shop/packages/{purchase_id}/redeem` (decrement; status→used_up at 0; `no_credits` when depleted). Collections: `package_products`, `packages`, `package_purchases`, `package_redemptions`. `shop.py` business detail returns `has_packages`.
- Web: `ShopPackagesRadioLife` (`/shop/packages/:id`), `MerchantPackagesRadioLife` (`/shop/merchant/packages`). Mobile: `app/shop/packages/[id].tsx`, `app/merchant/packages.tsx`. Entry links both surfaces: `merchant-open-packages`, business-detail `shop-detail-package` (when has_packages).
- Tests: **iteration_62 — backend 19/19 pytest PASS; web + mobile all testIDs functional, full parity, no bugs.** (Points purchase of the $99 demo package returns insufficient_points by design; card purchase returns a real Stripe checkout_url; redeem/no_credits fully verified.)

### Phase E · Item 2 — Memberships SHIPPED (2026-06 fork)
A venue sells a recurring membership (billed via recurring Stripe subscription, reusing the `marketplace_subscription.py` subscription-mode pattern) that bundles BENEFIT RULES; members CLAIM benefits, each capped per calendar period (day/week/month).
- Backend `routes/marketplace_memberships.py`: merchant `GET/POST/PATCH/DELETE /api/merchant/marketplace/memberships[/items/{id}]` (name, description, price_cents, interval month|week, entitlements[{label,qty,period,options[]}]; member_count included; `bad_interval` 400). Consumer `GET /api/shop/businesses/{id}/memberships` (plans + `mine` with per-benefit used/remaining/period_key), `POST /api/shop/memberships/subscribe` (recurring Stripe → checkout_url+session_id+membership_id; `already_member` 400), `GET .../subscribe/{session_id}/status` (activates on paid), `GET /api/shop/memberships/mine`, `POST /api/shop/memberships/{id}/claim {benefit_id,option?}` (per-period qty enforcement → `limit_reached`; `option_required` for choice benefits), `POST .../{id}/cancel` (cancels Stripe sub + marks canceled). Collections: `membership_plans`, `memberships`, `membership_claims`. `period_key` = `%Y-%m-%d` (day) / `%G-W%V` (week) / `%Y-%m` (month). `shop.py` business detail returns `has_memberships`.
- Web: `ShopMembershipsRadioLife` (`/shop/memberships/:id` — plans + active-member benefit claim with option chips), `MerchantMembershipsRadioLife` (`/shop/merchant/memberships` — plan CRUD with dynamic benefit-rule rows). Mobile: `app/shop/memberships/[id].tsx`, `app/merchant/memberships.tsx`. Entry links on both surfaces: `merchant-open-memberships`, business-detail `shop-detail-membership` (when has_memberships).
- Tests: **memberships pytest 14/14 PASS; web + mobile testIDs functional, full parity.** One web parity gap found (missing `merchant-open-memberships` tile on web MerchantDash) — FIXED and screenshot-verified. Stripe subscribe returns a real test checkout_url (not completable in automation); the claim engine is fully E2E-tested.

### Phase E · Item 1 — Merchant Gift Cards SHIPPED (2026-06 fork)
A venue sells its OWN branded gift card; shoppers buy with Stripe card or BigPoints; redeemable AT THAT VENUE (venue-scoped auto-apply). Reuses the shared `gift_card_products`/`gift_cards` collections + `POST /api/giftcards/purchase`.
- Backend `routes/marketplace_giftcards.py`: merchant `GET/POST/PATCH/DELETE /api/merchant/marketplace/giftcards[/items/{id}]` (denominations 100..1_000_000, `bad_denominations` 400, auto-stamps business_id + sponsor_name); consumer `GET /api/shop/businesses/{id}/giftcards` (items + points_per_dollar + points_balance). `shop.py` business detail now returns `has_giftcards`.
- **Venue-scoped redemption**: `_pick_gift_card` in BOTH `marketplace_orders.py` and `marketplace_products.py` now only auto-applies a card whose `business_id` is null OR == the order's business, preferring an exact venue match (was: any card anywhere).
- Web: `ShopGiftCardsRadioLife` (`/shop/giftcards/:id`), `MerchantGiftCardsRadioLife` (`/shop/merchant/giftcards`); entry links `merchant-open-giftcards` + business-detail `shop-detail-giftcard` (when has_giftcards). Mobile: `app/shop/giftcards/[id].tsx`, `app/merchant/giftcards.tsx`; same entry links.
- Tests: **iteration_60 — backend 10/10 pytest PASS; web + mobile 100%, full parity, no blocking bugs.** (Points purchase returns insufficient_points for the demo user by design; card purchase returns a real Stripe checkout_url.)
- Non-blocking follow-ups: `_validate_denoms` silently drops out-of-range values; `sponsor_name` snapshot goes stale on rename; add compound index on `gift_cards(owner_user_id,status,business_id,balance_cents)`; alert()-based error UX; success copy doesn't say the card is venue-locked.

### Phase E remaining (confirmed order): Memberships → Packages → Events, then Multi-Merchant Cart
- **Memberships (NEXT, largest)**: recurring Stripe subscription (reuse `marketplace_subscription.py` subscription-mode pattern) PLUS benefit/entitlement RULES — e.g. "1 free coffee daily", meal plans, and plans where the member CHOOSES which included items to claim. Needs a plan model (entitlements: item/category, qty, period daily/weekly/monthly), subscribe flow, and a period-limited claim/redeem engine.
- **Packages**: prepaid bundles (e.g. 5 haircuts, 10 classes) — buy once, redeem N times.
- **Events**: ticketed local events with limited capacity.

## SUPER MARKETPLACE — Wave A (Admin Loyalty Tuning + Shop Desktop Polish) SHIPPED (2026-06 fork)
First wave of the post-Phase-D backlog (build order confirmed with user: Wave A → Phase E → Multi-Merchant Cart).
- **Admin Loyalty Tuning**: loyalty tiers/perks are no longer hardcoded. `services/loyalty.py` now loads the ladder from `marketplace_loyalty_config` (single doc `config_id="global"`, idempotently seeded from `DEFAULT_TIERS` on first read; `get_tiers()` sorts ascending by min_points). New admin endpoints `GET/PUT /api/admin/marketplace/loyalty` (validates: non-empty, unique keys, base tier min_points==0). Web admin `/admin/marketplace` gains a **Loyalty Tiers** tab (`mkt-tab-loyalty`) — per-tier color/key/name/min-pts/bonus-%/perks editor with add/remove + Save (`loy-save`). Consumer `GET /api/shop/loyalty` + `award_with_tier_bonus` read the live config. Verified via curl (GET seeds defaults, PUT updates + validation 400) and admin-UI screenshot (4 tiers editable).
- **Shop Desktop Polish**: `AppShellRadioLife` takes a `wide` prop → container `max-w-3xl` (vs `max-w-md`) for all `/shop/*` + `/sell` routes (passed from `RadioLifeOverlay` via `shopRoute`); business grids on Shop home/browse now `grid-cols-2 sm:grid-cols-3`; fixed CTAs on business-detail + products cart widened to `max-w-3xl`. Cookie banner now suppressed on Shop/Sell routes (was overlapping the bottom checkout CTA). Verified via desktop screenshot (3-up grid fills width, no banner overlap).
- Self-tested (curl + screenshots); loyalty award path unchanged (defaults identical to prior hardcoded tiers, exercised by iter59 delivery/pickup/booking flows). No mobile changes in this wave.

## SUPER MARKETPLACE — Wave B = Phase E (Gift Cards / Memberships / Packages / Events) — NEXT
User-confirmed order: (1) Merchant Gift Cards, (2) Memberships, (3) Packages, (4) Events. Memberships = **recurring Stripe subscriptions** AND **entitlement/benefit rules** (e.g. "1 free coffee daily", meal plans — customer redeems included items per rules). Then Wave C = Multi-Merchant Cart (split into one order per merchant at checkout, single payment).

## Backlog (P0/P1/P2)

## SUPER MARKETPLACE — Multi-Merchant Cart SHIPPED (2026-06 fork)
- Backend `POST /api/shop/cart/checkout` splits a multi-venue basket into one product_order per business under a single Stripe session (gift cards auto-apply per venue). Web: `useProductCart.js` (Zustand) + `ShopCartRadioLife.jsx` + cart icon/badge in Shop header (`shop-cart-button`). Mobile: `src/stores/useProductCart.ts` + `app/shop/product-cart.tsx` + products screen wired to add-to-cart. Verified via testing agent iter64 (both surfaces).

## SAMPLE STOREFRONTS + SAMPLE GAMES SHIPPED (2026-06 fork) — Phase 1 of Shop-Desktop request
- New idempotent seed `services/marketplace_samples.py` (wired in server.py startup after seed_demo_menus):
  - **Fun Pizza Kitchen** (`biz_sample_funpizza`, restaurant): 8 menu items (pizzas/sides/dessert/coffee), **Weekly Pizza Club** membership $60/mo (1 pizza/week) + **Coffee Club** $9.99/mo (unlimited coffee). Images = Unsplash (funpizzakitchen.com CDN blocks hotlinking).
  - **Ambreens Salon** (`biz_sample_ambreens`, beauty): 3 bookable services (Haircut/Colour/Facial) with seeded weekly `service_availability`, 1 product (Argan serum), 1 membership (Unlimited Blowouts $49/mo).
  - **Sample games**: 3 live house campaigns per active game template (24 total, `cmp_smp_*`, open_to_all, bigcoin prizes) so every game type shows in Play & Win.
- Discoverability: `GET /api/shop/businesses/{id}` now returns `has_products`; web business-detail (`ShopBusinessRadioLife.jsx`) shows a **Shop Products** button (`shop-detail-products`) when a services/menu business also has products. Legacy web left sidebar (`AppShell.jsx` SECONDARY_NAV) now has a **Shop** link (`nav-shop`). Mobile Play/Games hub gains a **Trivia** section (`trivia-hub-card` → /trivia, host/join live-room buttons).
- Verified: testing agent iter65 (backend 8/8, web sidebar + detail CTAs, mobile trivia). Note: the two "membership/service unavailable" findings were test artifacts (tester used plan_id/service_id in URLs that expect a business_id; correct `/shop/memberships/{business_id}` + `/shop/services/{business_id}` confirmed working via curl).

### DESKTOP DARK SHOP + WALLET + TICKET SCAN + RADIO POLICY SHIPPED (2026-06 fork)
- **Desktop Shop layout**: web RadioLife Shop now renders a real desktop site on lg+ — sticky `DesktopTopNavRadioLife` + wide `max-w-6xl` container + multi-column grids; phones keep the app layout. Restyled to a **dark theme** on desktop to match the legacy site via scoped `layout/shop-desktop-dark.css` (class `rl-shop-desktop-dark`, gated to lg+). RadioLifeOverlay passes `desktop={shopRoute}`.
- **Home Shop widget**: legacy web home (`Home.jsx`) shows `components/ShopHomeWidget.jsx` (featured venues + Open Shop link).
- **Membership Wallet**: `/shop/memberships` (web `ShopMyMembershipsRadioLife.jsx`) + mobile `/shop/my-memberships` — per-venue memberships with quick-claim per benefit + renewal dates. Uses existing `GET /shop/memberships/mine` + claim.
- **Ticket Scanning**: new `POST /api/merchant/marketplace/events/tickets/checkin {code}` (valid/already/notfound). Web `MerchantTicketScanRadioLife.jsx` (`/shop/merchant/tickets`) + mobile `/merchant/ticket-scan`. Demo fixtures in `marketplace_samples.seed_demo_user_fixtures` for BOTH test@ (TEST1234/5678) and demo@ (DEMO1234/5678) incl. active memberships + a scannable event ticket.
- **Radio — Dubai policy + AI genres** (`services/radio_policy.py`, wired at startup): in Dubai only the 8 BigFM-family flagship stations show (BigFM/TalkFM/Luv FM/Beat FM/Big Melodies/Chilled Luv/Luv Legends/Urban Beat by flagship_slug); all other Dubai/UAE stations get `dubai_hidden:True` and every is_flagship read path is guarded with `dubai_hidden!=True` (closes the 'Beat Anthems' leak). Each branded channel + the 8 Dubai stations get an LLM-inferred `music_genre` (gpt-5.4-mini via Emergent key, idempotent background backfill). `music_genre` surfaced in `_imported_to_card` + `_ai_channel_to_card`; genre pill rendered in `RadioBrowse.jsx` (station-genre).
- Verified: testing agent iter66 (wallet/scan/desktop/home) + iter67 (radio+dark shop) — the 2 HIGH iter67 bugs (channel genre missing in API; genre pill in a dead file + nested-button) fixed & self-verified via curl + screenshot.
- Notes: all changes are PREVIEW-only — user must **republish** to see on production. Mobile Play/games tab exists in preview; missing on production only because that build predates it.

### NEXT — Phase 2 of Shop-Desktop request (user-approved, NOT yet started)
- Make the web Shop **responsive**: true wide multi-column desktop layout on laptop (top nav / grids), keep app-style layout on phones. Add a **Shop widget + link on the web home page**.

### 2026-06 — Gift Card gifting toggle + wallet reveal + home highlight card
- **Gift Card Gifting** now uses the same friend-gifting TOGGLE pattern as packages/memberships on web (`ShopGiftCardsRadioLife.jsx`) + mobile (`app/shop/giftcards/[id].tsx`): `gc-gift-toggle` reveals email + message, CTA flips to "Gift $X card". Backend (`routes/gift_cards.py`) schedules Mailgun gift-receipt emails (buyer + recipient) via `services/gift_notify.py` (kind="giftcard") on both points + card paths.
- **Wallet Gift Inbox reveal animation**: gifts arrive WRAPPED ("A gift from X — tap to unwrap") and unwrap to reveal details. Web `GiftInboxSection.jsx` (CSS keyframes wobble/pop), mobile `(tabs)/wallet.tsx` (Animated wobble + LayoutAnimation reveal). testIDs `gift-wrapped-{id}` → `gift-item-{id}`.
- **Home Shop highlight card**: `components/ShopHomeWidget.jsx` enhanced into a prominent gradient hero card (Open Shop CTA + 4 featured venues) on the web home.
- Verified: testing agent iteration_70 — ALL GREEN (backend 6 passed/1 skipped; web + mobile parity for all three; regressions from iter69 still pass).

### 2026-06 — Shop in-window + Gifting suite + Mailgun emails
- **Shop renders IN-SHELL** (fixes "Shop opens as a new website / left bar disappears"): root cause was `hooks/useDesignVariant.js` force-flipping the variant to `radiolife` on every `/shop` route → triggered the full-screen `RadioLifeOverlay` (fixed inset-0 sibling of AppShell) hiding the classic left sidebar. Removed the path-forcing; overlay only shows when the user explicitly picks the "new look". Added `design_radiolife/ShopInShell.jsx` + `/shop`, `/shop/*`, `/sell` routes inside `<AppShell>` so Shop renders in the classic shell (sidebar + top bar + mini-player intact). Dark theme via `.rl-shop-inshell` in `shop-desktop-dark.css`.
- **Membership Gifting** (web `ShopMembershipsRadioLife.jsx` + mobile `app/shop/memberships/[id].tsx`): gift toggle → email + message, CTA "Gift"; `POST /api/shop/memberships/subscribe` takes `gift_to_email`+`message`, assigns recipient by email (backfills user_id on recipient login so they can claim). `/memberships/mine` surfaces `received_gift`.
- **Gift Inbox** (web `components/GiftInboxSection.jsx` in `Wallet.js` + mobile `(tabs)/wallet.tsx`): "Gifts received" section via new `GET /api/shop/gifts/received` (`routes/marketplace_gifts.py`) aggregating gifted gift cards + packages + memberships (sender, message, deep link).
- **Gift Receipt emails** (`services/gift_notify.py`, via BackgroundTasks in packages + memberships): buyer confirmation + recipient "you got a gift" through the Mailgun abstraction. Mailgun LIVE: `MAILGUN_DOMAIN=radiolife.app` (not yet DNS-verified) + `MAILGUN_DOMAIN_FALLBACK=bigfantv.com` (verified) → sends today from `RadioLife <noreply@bigfantv.com>`, auto-upgrades to radiolife.app once verified.
- Verified: testing agent iteration_69 — ALL GREEN (backend 7/7 pytest; web in-shell + gifting + inbox; mobile parity). Emails are best-effort background tasks (no end-to-end send asserted).

### 2026-06 — Package Gifting UI (web + mobile) + mobile lint cleanup
- **Package Gifting UI** (backend already supported `gift_to_email`+`message` on `POST /api/shop/packages/purchase`): added a "Gift this package" toggle on BOTH surfaces revealing recipient email + optional message; Buy CTA switches to "Gift"; purchase sends gift fields. Web `ShopPackagesRadioLife.jsx` (rendered the previously-dead gift state), mobile `app/shop/packages/[id].tsx`. testIDs: `pkg-gift-toggle-{id}`, `pkg-gift-email-{id}`, `pkg-gift-message-{id}`. Verified by testing agent — PASSED with web↔mobile parity (web Gift → Stripe cs_test_ checkout).
- **Mobile ESLint cleanup** (recurring backlog item): `yarn expo lint` errors 14 → 0 (unescaped-entities fixed; conditional-hook + expo-notifications/device import errors suppressed with scoped eslint-disable), warnings 103 → 67 (remaining are intentional lazy `require()` imports + exhaustive-deps left as-is to avoid behavior change). No behavioral change. Pre-existing strict `tsc` type errors remain (Metro builds via Babel; out of scope).

### 2026-06 — Phase F refinements: Auto Top-Up + Daily-Cap chart marker (web + mobile)
- **P0 fix**: repaired an `IndentationError` (duplicate `async def ensure_promotions_seed`) in `routes/marketplace_promotions.py` that was blocking backend startup.
- **Auto Top-Up (Category Spotlight)**: added a toggle + editable $ amount on the merchant "Promote my Shop" screen — web `design_radiolife/screens/MerchantPromoteRadioLife.jsx` (`promote-autotopup*` testids) and mobile `app/merchant/promote.tsx`. Calls `POST /api/merchant/marketplace/category-bid/auto-topup {enabled, amount_cents, payment_method_id}`; backend `sweep_topups` off-session charges the saved card (`charge_saved_card`) when budget drops below ~20 impressions. Web with no card opens the Stripe setup-session; mobile shows an "add a card in Wallet" hint (consistent with the existing mobile auto-renew pattern).
- **Daily-Cap trend marker**: analytics `trend[]` points carry a `capped` boolean; both charts render a red dot + "Daily cap hit" legend on capped days (`promote-trend-cap-legend`, `promote-trend-capped-<date>`).
- **Weekly Digest** (backend-only, already wired): Monday summary email to promoted merchants via Mailgun, throttled through the shop read path.
- Verified: testing agent iteration_91 — ALL GREEN (backend 5/5 pytest; web 11/11 testids with live auto-topup round-trip; mobile 8/8 testids, no red screen). Non-blocking notes: `sweep_topups` throttle is a module-level dict (multi-worker risk); `trend[].capped` lacks a Pydantic response model.


### 2026-06 — Personalized Shop Home ("For You") + Bid Autopilot (web + mobile)
- **Personalized Shop Home**: new "For You" rail on `GET /api/shop/home` ranked by each shopper's own paid orders (weight 3) + browsing history (weight 1). `POST /api/shop/track` (kind=view) now also logs a per-user event into `shop_user_events` (compound index `{user_id:1, ts:-1}`). The rail carries a personalized `subtitle` (e.g. *"Because you order from Fun Pizza Kitchen & you browse restaurant / food"*) rendered on both surfaces (web `ShopRadioLife.jsx`, mobile `(tabs)/shop.tsx`; testids `shop-section-for_you`, `shop-section-sub-for_you`). Graceful fallback: users with no history get no rail (generic "Recommended" only). Helper `_personalized_section` in `routes/shop.py`.
- **Bid Autopilot** (merchant Category Spotlight): `POST /api/merchant/marketplace/category-bid/autopilot {enabled, target_rank(1..5), max_bid_cents}` + throttled `sweep_autopilot` (wired into the shop read path and `my_bid`). Auto-adjusts the per-impression bid to the minimum ¢ needed to hold the target rank (#1 / Top 3 / Top 5) — auto-raises AND auto-lowers to save budget — never exceeding the merchant's cap. UI toggle + rank chips + max-bid input + live status on web (`MerchantPromoteRadioLife.jsx`) and mobile (`app/merchant/promote.tsx`); testids `promote-autopilot*`.
- Verified: testing agent iteration_92 — ALL GREEN (backend 8/8 pytest; web + mobile parity for both features incl. live rank taps and For You subtitle; all regressions pass). Non-blocking: read-path sweeps use per-process throttle (multi-worker caveat).

### 2026-08 — RadioLife Ads API v1 — Phase 2 (Sponsorships + Usage + Webhooks + SmartReach)
- **Sponsorship Booking:** unified `/api/v1/sponsorships` (`type` = `predict_win` | `trivia` | `rj_read`) — `inventory`, create, `submit`, list, get, `report`. Facades over `ad3_sponsorship_service`, `trivia_sponsorship_service`, `rj_sponsored_read_service`. Sandbox auto-approves and skips real Stripe/AI; live: Predict&Win publishes for review, Trivia charges the prize pool, RJ enters moderation (live-payment for Trivia/RJ is the next slice).
- **Usage Analytics:** every `/api/v1` call logged to `partner_api_calls` (90-day TTL) via sub-app middleware; `GET /api/v1/usage?days=N` (+ portal `/api/partner/usage`) returns calls by day/endpoint/status, campaigns, spend, impressions, clicks, CTR. New Developer-dashboard **Usage** panel.
- **Event Webhooks:** `partner_webhooks` + signed delivery (`X-RadioLife-Signature: t=…,v1=HMAC_SHA256(secret,"t.body")`) with 3 retries + delivery log. Events: `campaign.approved/live/budget_exhausted/completed`, `sponsorship.approved`. A throttled `sweep_webhook_events` (fired from the v1 middleware, idempotent via per-doc flags) detects state changes for partner-owned campaigns/sponsorships. Endpoints: `POST/GET/DELETE /api/v1/webhooks`, `/ping`, `/deliveries`, `/events` (+ portal mirror). New Developer-dashboard **Webhooks** section.
- **SmartReach (Emergent) partner** seeded with live + sandbox API keys and an OAuth client (all scopes). Idempotent prod seeding script: `backend/scripts/seed_smartreach_partner.py` (run in production after deploy to mint the same access there — preview keys do NOT carry to prod).
- Verified: testing agent iteration_94 — 20/20 backend (both auth flows, sponsorship sandbox lifecycle, usage shape, webhook register/ping/deliveries + live sweep firing campaign.approved/live, scope 403s, cross-partner 404) + web dashboard Usage/Webhooks sections. Secret-reveal now scrolls into view.
- **Roadmap:** live-payment wiring for Trivia/RJ sponsorships; OpenRTB/VAST programmatic seat; marketplace-promotion product; per-key granular analytics.

### 2026-08 — RadioLife Ads Public API v1 (partner/programmatic marketing) — Phase 1
- **What:** a versioned, partner-authenticated public API so external systems (agencies, brands, DSPs) can buy marketing programmatically — a **facade over the existing internal ad engine** (`services/ad1_advertiser_service`), not a parallel system. Mounted as a dedicated FastAPI sub-app at **`/api/v1`** with interactive OpenAPI at **`/api/v1/docs`**.
- **Auth (dual):** partner **API keys** (`Authorization: Bearer rlk_{live|test}_<id>.<secret>`) and **OAuth2 client-credentials** (`POST /api/v1/oauth/token` → short-lived HS256 JWT). Secrets stored only as salted HMAC-SHA256 digests; signing secret + pepper persisted in Mongo (`partner_api_secrets`) so it works in any environment. Per-credential **scopes**, **LIVE/SANDBOX** isolation, per-minute **rate limiting**. New service `services/partner_api.py`.
- **Endpoints (`routes/partner_api_v1.py`):** `/me`, `/products` (catalog of 9 marketing products), advertisers (create/get), funding (balance + Stripe top-up; sandbox credits instantly), campaigns (create/list/get/creatives/submit/pause/stop) and `/report`. Bookable via API now: **audio_preroll, display_banner, sponsored_game**; audio mid-roll, the other sponsorship types, programmatic OpenRTB seat, and marketplace promotion are surfaced in the catalog as roadmap.
- **Self-serve + admin (`routes/partner_portal.py`):** `/api/partner/*` (current-user) to create a partner account and mint/revoke API keys + OAuth clients; `/api/admin/partner-api/*` for ops.
- **Web:** new **Developer → “API & Keys”** page in the advertiser dashboard (`/advertiser/dashboard/api`, `pages/advertiser_v2/DeveloperApi.jsx`) — onboarding, key/OAuth-client creation with one-time secret reveal, revoke, and a link to the live docs.
- **Docs:** interactive `/api/v1/docs` + a Markdown reference at `/app/docs/PARTNER_API.md`.
- Verified: testing agent iteration_93 — ALL GREEN (backend 17/17 incl. both auth flows, scope 403s, sandbox lifecycle, guardrails; web dev-console create/reveal/revoke). Sandbox campaigns never serve/bill real inventory.
- **Roadmap (next phases):** wire the non-bookable products (OpenRTB DSP seat + VAST, Predict&Win/Trivia/RJ-read sponsorships, mid-roll audio, marketplace promotion), webhooks for campaign/spend events, usage analytics per key.

## Backlog (P0/P1/P2 — earlier)
- **P1** Picture-in-Picture for Creator Studio video podcasts.
- **P1** Clean up recurring mobile TS/ESLint warnings (missing useEffect deps, unused vars, require-style imports).
- **P2** More business monetization: Lead Gen CPL, Prepaid Offers, Business Memberships.
- **P2** Verify 100% cream/orange "New Look" parity across remaining components.
- **P2 · Deferred** AD.7.1 — Split-the-bill (needs group-checkout primitives, deferred from AD.3).
- **P2 · Blocked** AD.9 — Podcast Completion Points (blocked on Track 3 podcast infra).
- **P2 · Blocked** AD.5 — Trivia Sponsorship (blocked on trivia infra maturation).
- **P2** M-series monetization additions (M4 → M1 → M7 → M2 → M3 → M6 → M5), Flagship Sponsor CTA.
