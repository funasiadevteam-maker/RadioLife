# Mobile Commit Log

## Iteration 1–3 — Phases 36f + U + 39M.1
- Creator-side podcast, Home/News tabs, RadioLife light-mode theme, SafeImage, MiniPlayer, forgot-password, now-playing
- See prior entries

## Iteration 4 — Phase 39M.2: Wallet + Coupons + Scan-to-Pay
- **Commit**: 4d97fa14370c5d62b5536c0419af367cd8177ea3
- **Date**: 2026-08-03
- **Changes**:
  - **NEW** `app/scan-to-pay.tsx` — Native camera QR scanner (expo-camera on native, manual fallback on web). Handles permission denied, 5s timeout → manual entry, torch toggle, center scan-window with corner brackets.
  - **NEW** `app/pay-checkout/[token].tsx` — Full payment checkout: merchant header (SafeImage), bill items, BigCoin points slider, tip presets (No tip / AED 1 / AED 2 / AED 5), live quote re-computation, Pay button → authorize+capture, "Split with a friend" → creates invite + native share sheet, receipt confirmation with BigCoin earned.
  - **NEW** `app/my-splits.tsx` — Split-payment sessions list with filter chips (All/Pending/Paid/Expired), per-split card with merchant, total, status pill, progress bar, participant list with paid/unpaid state.
  - **UPDATED** `app/(tabs)/wallet.tsx` — Added "Scan to Pay", "My Splits", "Deals" action buttons below balance card. Fixed hardcoded dark-mode colors (headerTitle, balanceAmount, streak text) for light mode.
  - **UPDATED** `app/coupon/[id].tsx` — Enhanced with T&Cs section, "Redeem Now" button (only for active unredeemed coupons), merchant address + "Get Directions" (opens Google Maps), fixed QR code colors for light mode.
  - **UPDATED** `app/_layout.tsx` — Registered 3 new routes: scan-to-pay, pay-checkout/[token], my-splits.
  - **INSTALLED** `expo-camera@16.1.6`
- **Backend endpoints used**:
  - `GET /api/bigcoin/me` — balance, tier, streak
  - `GET /api/commerce/coupons/me` — user's coupons
  - `GET /api/wallet/items` — wallet items
  - `GET /api/scan-to-pay/qr/{token}` — resolve QR bill
  - `POST /api/scan-to-pay/quote` — compute payment quote
  - `POST /api/scan-to-pay/authorize` — authorize payment
  - `POST /api/scan-to-pay/capture` — capture payment
  - `POST /api/scan-to-pay/splits` — create split
  - `GET /api/scan-to-pay/splits/mine` — user's splits
  - `POST /api/commerce/coupons/{id}/redeem` — redeem coupon
- **Test results**: 22/22 pass (5 suites)
- **Backend changes**: NONE
- **Frontend changes**: NONE
- **Screenshots**: Wallet (balance + actions), Scan-to-Pay (web manual entry), My Splits (real split data), Coupon Detail (QR code + offer), Pay Checkout (error handling for invalid token)

## Iteration 5 — Phase 39M.3: Play & Win + Predict & Win
- **Commit**: f4c0e1d69bb7c9bb284ead9c60e26f519a889240
- **Date**: 2026-08-03
- **Changes**:
  - Added Games tab to tab bar (replaced Podcasts position)
  - Created Games Hub with featured card, quick games grid, discover campaigns, predict shortcut
  - Created Spin Wheel screen with SVG animated wheel
  - Created Music Trivia screen with question/answer flow
  - Created Guess the Lyric screen with lyric completion flow
  - Created Campaign Game screen for Spin & Win / Scratch & Win discover games
  - Created Predict & Win screen with Active/My Picks/Won Rewards tabs
  - Created Enter Modal with option picker, confidence slider, submit flow
  - Handled 410 (deprecated) legacy endpoints gracefully
  - Installed @react-native-community/slider
- **Files modified**:
  - app/(tabs)/_layout.tsx (added Games tab)
  - app/_layout.tsx (registered game routes)
  - app/(tabs)/games.tsx (NEW)
  - app/games/spin.tsx (NEW)
  - app/games/trivia-game.tsx (NEW)
  - app/games/lyric-game.tsx (NEW)
  - app/games/predict.tsx (NEW)
  - app/games/campaign/[campaignId].tsx (NEW)
- **Web files referenced**:
  - frontend/src/pages/play/PlayDiscover.jsx
  - frontend/src/pages/play/GamePlay.jsx
  - frontend/src/PredictWin.jsx
  - frontend/src/components/playApi.js
  - frontend/src/Wallet.js
