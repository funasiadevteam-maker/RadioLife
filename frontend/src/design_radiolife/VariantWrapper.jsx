// Phase R.1 — Variant wrapper.  When variant=`radiolife` AND the current
// pathname maps to one of the RadioLife screens, render the RadioLife
// version inside AppShellRadioLife.  Otherwise, fall through to legacy.
//
// This keeps the App.js route table stable while enabling variant-based
// conditional render at the shell level (per the R.1 brief).
import React from "react";
import { useLocation } from "react-router-dom";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useAuth } from "@/AuthContext";
import AppShellRadioLife from "./layout/AppShellRadioLife";
import HomeRadioLife from "./screens/HomeRadioLife";
import ListenRadioLife from "./screens/ListenRadioLife";
import NowPlayingRadioLife from "./screens/NowPlayingRadioLife";
import DiscoverRadioLife from "./screens/DiscoverRadioLife";
import ProfileRadioLife from "./screens/ProfileRadioLife";
import RewardsWalletRadioLife from "./screens/RewardsWalletRadioLife";
import RedeemCouponRadioLife from "./screens/RedeemCouponRadioLife";
import RestaurantDetailRadioLife from "./screens/RestaurantDetailRadioLife";
// Phase R.2 — `/pay` now renders the real scan-to-pay ScanEntry
// component (AD.7 shipped).  The legacy coming-soon placeholder
// was deleted.
import ScanEntry from "@/pages/scan/ScanEntry";
import OnboardingRadioLife from "./screens/OnboardingRadioLife";

// Screens where the bottom nav is hidden (immersive / focus screens).
const NO_NAV_PATHS = [/^\/pay(\b|\/)/, /^\/radio\/station\//,
                              /^\/business\//, /^\/coupon\//];

// Bare screens — full-bleed, own their own chrome (Onboarding).
const BARE_PATHS = [/^\/login(\b|\/)/, /^\/onboarding(\b|\/)/];

function screenFor(pathname) {
  // Exact matches
  if (pathname === "/" || pathname === "/home") return HomeRadioLife;
  if (pathname === "/radio") return ListenRadioLife;
  if (pathname === "/discover") return DiscoverRadioLife;
  if (pathname === "/wallet") return RewardsWalletRadioLife;
  if (pathname === "/profile") return ProfileRadioLife;
  if (pathname === "/pay") return ScanEntry;
  // Prefix matches
  if (pathname.startsWith("/radio/station/") || pathname === "/radio/now")
    return NowPlayingRadioLife;
  if (pathname.startsWith("/coupon/")) return RedeemCouponRadioLife;
  // Business detail — but NOT /business/login, /business/register etc.
  if (pathname.startsWith("/business/")) {
    const seg = pathname.slice("/business/".length);
    const reserved = ["login", "register", "redeem", "campaigns", "ads", ""];
    if (!reserved.some((r) => seg === r || seg.startsWith(r + "/"))) {
      return RestaurantDetailRadioLife;
    }
  }
  // Onboarding surfaces (skinned only when variant=radiolife)
  if (pathname === "/login" || pathname === "/onboarding") return OnboardingRadioLife;
  return null;
}

export default function RadioLifeVariantWrapper({ children }) {
  const variant = useDesignVariant();
  const { user } = useAuth();
  const { pathname } = useLocation();

  // Legacy path — pass children straight through.
  if (variant !== "radiolife") return children;

  // For anon users on marketing / non-listener routes: still render legacy.
  const Screen = screenFor(pathname);
  if (!Screen) return children;
  // Onboarding path — even when anon, show the re-skinned onboarding.  For
  // all OTHER RadioLife screens, require an authenticated user (otherwise
  // pass through so ProtectedRoute in App.js redirects to /login).
  const isBare = BARE_PATHS.some((r) => r.test(pathname));
  if (!isBare && !user) return children;

  const hideNav = NO_NAV_PATHS.some((r) => r.test(pathname));
  return (
    <AppShellRadioLife showBottomNav={!hideNav && !isBare} bare={isBare}>
      <Screen />
    </AppShellRadioLife>
  );
}
