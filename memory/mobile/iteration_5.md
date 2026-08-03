# Phase 11.4 Fix Battery — Iteration 5

## Fixes Implemented

### Fix 1: Auth guard hydration race on direct-URL loads
- **Root cause**: `expo-secure-store` on web silently fails — `setItemAsync` is a no-op. Token never persisted to `localStorage`. On page reload, `loadToken()` returns null → `refresh()` hits 401 → user=null → redirect to /login.
- **Solution**: Platform-aware storage in `client.ts` — `localStorage` for web, `SecureStore` for native. Added `AuthGatedStack` wrapper in `_layout.tsx` that blocks Stack rendering until `loading` is false.
- **Files**: `mobile/src/api/client.ts`, `mobile/app/_layout.tsx`

### Fix 2: Wallet → "Browse Local Offers" CTA
- Added `browseOffersCta` styled card below Saved Coupons section in OverviewTab
- Routes to `/coupons` on tap
- **File**: `mobile/app/(tabs)/wallet.tsx`

### Fix 3: Wallet "Saved Coupons" rows tappable + enhanced
- Added business name (`couponBiz`), offer title/code, colored status dots (green/purple/red), expiry date
- Fallback `coupon_id || id` for legacy data
- `activeOpacity={0.7}` for touch feedback
- Routes to `/coupon/${cId}` on tap
- **File**: `mobile/app/(tabs)/wallet.tsx`

### Fix 4: Commute entry point in radio header
- Added `car-outline` Ionicons button between play-and-win and logout in radio header
- testID: `nav-commute`
- Routes to `/commute` on tap
- **File**: `mobile/app/(tabs)/radio.tsx`

## Verification
- Direct URL `/coupons` → stays on coupons (PASS)
- Direct URL `/commute` → stays on commute (PASS)
- Wallet "Browse Local Offers" CTA visible and tappable
- Wallet saved coupon rows tappable with status badges
- Commute icon visible in radio header (5th icon from left)
- All screenshots captured and verified
