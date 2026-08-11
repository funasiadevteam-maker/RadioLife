# RadioLife — E-commerce & Merchant Marketplace Roadmap
(Captured from user requests — June 2026. Source of truth for this initiative.)

## Reported bug (P0)
- Placed 2 orders in the **demo account on production (radiolife.app)** — neither reached a checkout/credit-card step.
- Backend `/api/shop/product-orders/checkout` + `/api/shop/cart/checkout` DO return a Stripe `checkout_url`; suspected client-side redirect gap or $0 order via gift-card auto-apply. Reproduce in preview.

## Phase 1 — Fix + core checkout  ✅ DONE (2026-06, food/menu flow) — iteration_71 green
- **Bug fixed**: food checkout no longer silently covers the order with a gift card → it now always reaches a payment step. Root cause: `use_gift_card` defaulted to `true` and auto-applied.
- Backend `marketplace_orders.py`: `use_gift_card` now opt-in; added **BigPoints redemption** (100 pts = $1) with idempotent `_redeem_points`; added `POST /api/shop/orders/quote` live price breakdown; `/checkout` returns Stripe `checkout_url` unless gift+points fully cover.
- Web: new **`CheckoutMenuRadioLife`** screen at `/shop/checkout/menu` (gift-card toggle + points slider + live total + pay-by-card / place-order); menu page now routes there. Persistent **cart icon in the top bar** (`AppShell` `ShopCartButton`, reflects menu + product carts).
- Auto-award points already on paid orders (unchanged).
- REMAINING in Phase 1 (follow-up): apply the same explicit gift/points checkout to **products/cart** flow and **mobile** menu checkout (mobile still uses its own direct flow). Coupons-at-checkout deferred to Phase 5 wiring.
- Test seed: test@bigfm.dubai has a $10 Fun Pizza gift card (`gc_test_funpizza`) + 500 points for QA.

## Phase 1 — original spec
- Ensure checkout always reaches payment (redirect to Stripe or points path).
- Persistent **cart icon in the top bar** with item count, across the shop (and sprinkled entry points).
- Real checkout screen: pay by **card** or **points**; **points reduce cart total** (partial redemption via business `points_per_dollar`); prompt to **apply available coupons/points for that business** (online + in-store).
- **Auto-award BigPoints** on successful checkout.

## Phase 2 — Saved cards & wallet (STRIPE INTEGRATION — use integration_expert)
- Billing address; add card; **save card** to Stripe customer; **default card** when multiple; "Save this card for next time / add to wallet?" prompt on every transaction.
- Customer pays by saved card or points at customer site.

## Phase 3 — Merchant order management
- Shop owner **new-order alert** (in-app + email).
- Order status workflow: **Preparing → Ready to ship → Shipped** (delivery) OR **Ready for pickup** (pickup).

## Phase 4 — QR pay + anti-fraud
- Customer shows QR to **pay by points or card**; shop (shop role) **scans to charge** (off-session PaymentIntent on saved card OR points debit). Builds on existing scan-to-pay / pay-checkout / merchant scan.
- **Fraud capture**: flag when a store gives a direct discount **without scanning** the QR (commission evasion) — reconciliation/anomaly logic.

## Phase 5 — Merchant promotion, specials & advertising ("Promoted marketplace")
- Shop owner sets **points-per-dollar** (exists) — a higher rate **boosts organic ranking/promotion**.
- **Specials/offers** creation; **automatic recommendations** by the system.
- **Promote items** (self-serve) to push sales.
- **PPC upgrade / bid for higher priority** via ad spend (builds on existing advertiser/campaign + AdBanner/BannerZoneSlot infra).
- **"Today's Specials"** rows on the web home for shops offering specials; **multiple rows** on shop home; shopping widgets **sprinkled across all pages**.
- Product **auto-highlighting across pages** driven by **sales velocity + paid campaigns**.

## Notes
- Stripe test key already in environment (no key from user needed).
- Existing infra to reuse: advertiser campaigns, AdBanner, BannerZoneSlot, points_per_dollar per business, coupons, gift-card auto-apply, multi-merchant cart, scan-to-pay/pay-checkout, merchant marketplace routes.
