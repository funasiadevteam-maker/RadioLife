// Phase R.1 — RadioLife overlay.  Renders the RadioLife screen on top
// of the legacy shell when variant=`radiolife` AND the current path maps
// to a RadioLife screen.  Legacy DOM stays underneath (unhurt).
//
// Advantages:
//   * Toggle flips instantly (no re-mount of legacy tree).
//   * Legacy code stays 100% untouched — the overlay uses `position: fixed`.
//   * Falling back to legacy for unmapped paths = trivial (just render null).
import React from "react";
import { useLocation } from "react-router-dom";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useAuth } from "@/AuthContext";
import AppShellRadioLife from "./layout/AppShellRadioLife";
import HomeRadioLife from "./screens/HomeRadioLife";
import ListenRadioLife from "./screens/ListenRadioLife";
import NowPlayingRadioLife from "./screens/NowPlayingRadioLife";
import DiscoverRadioLife from "./screens/DiscoverRadioLife";
import GamingRadioLife from "./screens/GamingRadioLife";
import ProfileRadioLife from "./screens/ProfileRadioLife";
import RewardsWalletRadioLife from "./screens/RewardsWalletRadioLife";
import RedeemCouponRadioLife from "./screens/RedeemCouponRadioLife";
import RestaurantDetailRadioLife from "./screens/RestaurantDetailRadioLife";
// Phase R.2 — `/pay` now renders the real scan-to-pay ScanEntry
// component (AD.7 shipped).  The legacy coming-soon placeholder
// was deleted.
import ScanEntry from "@/pages/scan/ScanEntry";
import OnboardingRadioLife from "./screens/OnboardingRadioLife";
// Phase B — Podcast listener screens.
import PodcastsRadioLife from "./screens/PodcastsRadioLife";
import PodcastDetailRadioLife from "./screens/PodcastDetailRadioLife";
// Phase C — Trivia landing + room.
import TriviaRadioLife from "./screens/TriviaRadioLife";
import TriviaRoomRadioLife from "./screens/TriviaRoomRadioLife";
// Super Marketplace Phase A — Shop.
import ShopRadioLife from "./screens/ShopRadioLife";
import ShopBusinessRadioLife from "./screens/ShopBusinessRadioLife";
import SellOnRadioLife from "./screens/SellOnRadioLife";
// Phase B — Restaurant pickup, orders, merchant.
import ShopMenuRadioLife from "./screens/ShopMenuRadioLife";
import CheckoutMenuRadioLife from "./screens/CheckoutMenuRadioLife";
import ShopOrdersRadioLife from "./screens/ShopOrdersRadioLife";
import MerchantDashRadioLife from "./screens/MerchantDashRadioLife";
import MerchantMenuRadioLife from "./screens/MerchantMenuRadioLife";
import MerchantSubscribeRadioLife from "./screens/MerchantSubscribeRadioLife";
// Phase C — service bookings.
import ShopServicesRadioLife from "./screens/ShopServicesRadioLife";
import ShopBookingsRadioLife from "./screens/ShopBookingsRadioLife";
import MerchantServicesRadioLife from "./screens/MerchantServicesRadioLife";
// Phase D — ecommerce products, product orders, loyalty.
import ShopProductsRadioLife from "./screens/ShopProductsRadioLife";
import ShopProductDetailRadioLife from "./screens/ShopProductDetailRadioLife";
import ShopCartRadioLife from "./screens/ShopCartRadioLife";
import CheckoutCartRadioLife from "./screens/CheckoutCartRadioLife";
import ShopMyMembershipsRadioLife from "./screens/ShopMyMembershipsRadioLife";
import MerchantTicketScanRadioLife from "./screens/MerchantTicketScanRadioLife";
import ShopProductOrdersRadioLife from "./screens/ShopProductOrdersRadioLife";
import MerchantProductsRadioLife from "./screens/MerchantProductsRadioLife";
import LoyaltyRadioLife from "./screens/LoyaltyRadioLife";
// Phase E — merchant gift cards.
import ShopGiftCardsRadioLife from "./screens/ShopGiftCardsRadioLife";
import MerchantGiftCardsRadioLife from "./screens/MerchantGiftCardsRadioLife";
// Phase E — memberships.
import ShopMembershipsRadioLife from "./screens/ShopMembershipsRadioLife";
import MerchantMembershipsRadioLife from "./screens/MerchantMembershipsRadioLife";
import MerchantEarningsRadioLife from "./screens/MerchantEarningsRadioLife";
// Phase E — packages.
import ShopPackagesRadioLife from "./screens/ShopPackagesRadioLife";
import MerchantPackagesRadioLife from "./screens/MerchantPackagesRadioLife";
// Phase E — events.
import ShopEventsRadioLife from "./screens/ShopEventsRadioLife";
import MerchantEventsRadioLife from "./screens/MerchantEventsRadioLife";
// Phase 2 Checkout — Saved Cards wallet.
import WalletCardsRadioLife from "./screens/WalletCardsRadioLife";
// Coupons at Checkout — merchant self-serve codes.
import MerchantCouponsRadioLife from "./screens/MerchantCouponsRadioLife";
// QR Scan-to-Pay.
import ScanPayRadioLife from "./screens/ScanPayRadioLife";
import MerchantScanRadioLife from "./screens/MerchantScanRadioLife";
// Promoted Specials.
import MerchantSpecialsRadioLife from "./screens/MerchantSpecialsRadioLife";
// Phase F — AI ordering concierge.
import ConciergeRadioLife from "./screens/ConciergeRadioLife";

const NO_NAV_PATHS = [/^\/pay(\b|\/)/, /^\/radio\/station\//,
                              /^\/business\//, /^\/coupon\//];
const BARE_PATHS = [/^\/login(\b|\/)/, /^\/onboarding(\b|\/)/];

export function screenFor(pathname) {
  if (pathname === "/" || pathname === "/home") return HomeRadioLife;
  if (pathname === "/radio") return ListenRadioLife;
  if (pathname === "/shop") return ShopRadioLife;
  if (pathname === "/sell") return SellOnRadioLife;
  if (pathname === "/shop/checkout/menu") return CheckoutMenuRadioLife;
  if (pathname === "/shop/checkout/cart") return CheckoutCartRadioLife;
  if (pathname === "/shop/wallet/cards") return WalletCardsRadioLife;
  if (pathname === "/shop/orders") return ShopOrdersRadioLife;
  if (pathname === "/shop/cart") return ShopCartRadioLife;
  if (pathname === "/shop/memberships") return ShopMyMembershipsRadioLife;
  if (pathname === "/shop/product-orders") return ShopProductOrdersRadioLife;
  if (pathname === "/shop/loyalty") return LoyaltyRadioLife;
  if (pathname === "/shop/bookings") return ShopBookingsRadioLife;
  if (pathname === "/shop/merchant") return MerchantDashRadioLife;
  if (pathname === "/shop/merchant/menu") return MerchantMenuRadioLife;
  if (pathname === "/shop/merchant/services") return MerchantServicesRadioLife;
  if (pathname === "/shop/merchant/products") return MerchantProductsRadioLife;
  if (pathname === "/shop/merchant/giftcards") return MerchantGiftCardsRadioLife;
  if (pathname === "/shop/merchant/memberships") return MerchantMembershipsRadioLife;
  if (pathname === "/shop/merchant/earnings") return MerchantEarningsRadioLife;
  if (pathname === "/shop/merchant/packages") return MerchantPackagesRadioLife;
  if (pathname === "/shop/merchant/events") return MerchantEventsRadioLife;
  if (pathname === "/shop/merchant/coupons") return MerchantCouponsRadioLife;
  if (pathname === "/shop/scan-pay") return ScanPayRadioLife;
  if (pathname === "/shop/concierge") return ConciergeRadioLife;
  if (pathname === "/shop/merchant/scan") return MerchantScanRadioLife;
  if (pathname === "/shop/merchant/specials") return MerchantSpecialsRadioLife;
  if (pathname === "/shop/merchant/tickets") return MerchantTicketScanRadioLife;
  if (pathname === "/shop/merchant/subscribe") return MerchantSubscribeRadioLife;
  if (pathname.startsWith("/shop/menu/")) return ShopMenuRadioLife;
  if (pathname.startsWith("/shop/services/")) return ShopServicesRadioLife;
  if (pathname.startsWith("/shop/products/")) {
    const parts = pathname.split("/").filter(Boolean); // [shop, products, bizId, (productId)]
    if (parts.length >= 4) return ShopProductDetailRadioLife;
    return ShopProductsRadioLife;
  }
  if (pathname.startsWith("/shop/giftcards/")) return ShopGiftCardsRadioLife;
  if (pathname.startsWith("/shop/memberships/")) return ShopMembershipsRadioLife;
  if (pathname.startsWith("/shop/packages/")) return ShopPackagesRadioLife;
  if (pathname.startsWith("/shop/events/")) return ShopEventsRadioLife;
  if (pathname.startsWith("/shop/")) return ShopBusinessRadioLife;
  if (pathname === "/discover") return DiscoverRadioLife;
  if (pathname === "/play") return GamingRadioLife;
  if (pathname === "/wallet") return RewardsWalletRadioLife;
  if (pathname === "/profile") return ProfileRadioLife;
  if (pathname === "/pay") return ScanEntry;
  // Phase B — podcasts.
  if (pathname === "/podcasts") return PodcastsRadioLife;
  if (pathname.startsWith("/podcasts/")) return PodcastDetailRadioLife;
  // Phase C — trivia landing + multiplayer room.
  if (pathname === "/trivia") return TriviaRadioLife;
  if (pathname.startsWith("/trivia/rooms/") &&
        !pathname.startsWith("/trivia/rooms/create"))
    return TriviaRoomRadioLife;
  if (pathname.startsWith("/radio/station/")) return NowPlayingRadioLife;
  if (pathname.startsWith("/coupon/")) return RedeemCouponRadioLife;
  if (pathname.startsWith("/business/")) {
    const seg = pathname.slice("/business/".length);
    const reserved = ["login", "register", "redeem", "campaigns", "ads"];
    if (!reserved.some((r) => seg === r || seg.startsWith(r + "/"))) {
      return RestaurantDetailRadioLife;
    }
  }
  if (pathname === "/login" || pathname === "/onboarding") return OnboardingRadioLife;
  return null;
}

export default function RadioLifeOverlay() {
  const variant = useDesignVariant();
  const { user } = useAuth();
  const { pathname } = useLocation();

  // Shop now renders IN-SHELL (inside the legacy AppShell, keeping the left
  // sidebar + top bar) via <ShopInShell> routes in App.js. So the overlay
  // only takes over when the user has explicitly switched to the RadioLife
  // "new look".  In legacy mode the shop lives inside the classic shell.
  if (variant !== "radiolife") return null;
  const shopRoute = pathname === "/shop" || pathname.startsWith("/shop/") || pathname === "/sell";
  const Screen = screenFor(pathname);
  if (!Screen) return null;

  const isBare = BARE_PATHS.some((r) => r.test(pathname));
  // For non-bare RadioLife screens, only overlay for authenticated users.
  if (!isBare && !user) return null;

  const hideNav = NO_NAV_PATHS.some((r) => r.test(pathname));
  return (
    <div
      className="fixed inset-0 z-[80] overflow-y-auto"
      data-testid="rl-overlay">
      <AppShellRadioLife showBottomNav={!hideNav && !isBare} bare={isBare} wide={shopRoute} desktop={shopRoute}>
        <Screen />
      </AppShellRadioLife>
    </div>
  );
}
