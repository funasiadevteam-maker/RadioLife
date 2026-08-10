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
import ShopOrdersRadioLife from "./screens/ShopOrdersRadioLife";
import MerchantDashRadioLife from "./screens/MerchantDashRadioLife";
import MerchantMenuRadioLife from "./screens/MerchantMenuRadioLife";
import MerchantSubscribeRadioLife from "./screens/MerchantSubscribeRadioLife";
// Phase C — service bookings.
import ShopServicesRadioLife from "./screens/ShopServicesRadioLife";
import ShopBookingsRadioLife from "./screens/ShopBookingsRadioLife";
import MerchantServicesRadioLife from "./screens/MerchantServicesRadioLife";

const NO_NAV_PATHS = [/^\/pay(\b|\/)/, /^\/radio\/station\//,
                              /^\/business\//, /^\/coupon\//];
const BARE_PATHS = [/^\/login(\b|\/)/, /^\/onboarding(\b|\/)/];

function screenFor(pathname) {
  if (pathname === "/" || pathname === "/home") return HomeRadioLife;
  if (pathname === "/radio") return ListenRadioLife;
  if (pathname === "/shop") return ShopRadioLife;
  if (pathname === "/sell") return SellOnRadioLife;
  if (pathname === "/shop/orders") return ShopOrdersRadioLife;
  if (pathname === "/shop/bookings") return ShopBookingsRadioLife;
  if (pathname === "/shop/merchant") return MerchantDashRadioLife;
  if (pathname === "/shop/merchant/menu") return MerchantMenuRadioLife;
  if (pathname === "/shop/merchant/services") return MerchantServicesRadioLife;
  if (pathname === "/shop/merchant/subscribe") return MerchantSubscribeRadioLife;
  if (pathname.startsWith("/shop/menu/")) return ShopMenuRadioLife;
  if (pathname.startsWith("/shop/services/")) return ShopServicesRadioLife;
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

  // Shop / Sell are RadioLife-only surfaces — always overlay them so
  // customers land straight in the Shop without flipping the design toggle.
  const shopRoute = pathname === "/shop" || pathname.startsWith("/shop/") || pathname === "/sell";
  if (variant !== "radiolife" && !shopRoute) return null;
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
      <AppShellRadioLife showBottomNav={!hideNav && !isBare} bare={isBare}>
        <Screen />
      </AppShellRadioLife>
    </div>
  );
}
