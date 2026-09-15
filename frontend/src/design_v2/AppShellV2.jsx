// New Look V2 shell — premium dark cinematic chrome (integrated top nav +
// sticky player dock). Reuses the existing audio engine (MiniPlayer +
// GlobalAudio), companion, notifications and variant switcher. Only the
// visual composition is new. Bare/marketing/admin routes render untouched.
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Home, Headphones, ShoppingBag, Gamepad2, Users, Coins, ChevronDown,
  CreditCard,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useThemeStore } from "@/theme/useTheme";
import { useGeoStore } from "@/store/useGeoStore";
import { useShellSummary } from "@/shell/useShellData";
import { MiniPlayer } from "@/shell/primitives";
import OnAirOfferCard from "@/shell/OnAirOfferCard";
import VariantSwitcher from "@/shell/VariantSwitcher";
import NotificationBell from "@/components/NotificationBell";
import BannerAdSlot from "@/components/BannerAdSlot";
import { isMarketingPath } from "@/shell/AppShellB";
import "./newlookv2.css";

// One shared frame width for the whole V2 surface — header, page content
// and player dock all align to these exact left/right edges so every tab
// looks identical (fixes the "one screen left, one centered" mismatch).
const CONTAINER = "max-w-[1440px] mx-auto w-full px-4 sm:px-6 xl:px-10";

function railPageRoute(pathname) {
  if (pathname === "/") return "/home";
  if (pathname.startsWith("/listen")) return "/channels";
  if (pathname.startsWith("/shop")) return "/shop";
  if (pathname.startsWith("/play")) return "/play";
  if (pathname.startsWith("/community")) return "/community";
  return "/home";
}

const BARE_ROUTES = [
  /^\/login(\b|\/)/, /^\/onboarding(\b|\/)/, /^\/auth(\b|\/)/,
  /^\/dev\/styleguide(\b|\/)/, /^\/tv(\b|\/)/,
];

const NAV = [
  { key: "home", label: "Home", icon: Home, path: "/" },
  { key: "listen", label: "Listen", icon: Headphones, path: "/listen" },
  { key: "shop", label: "Shop", icon: ShoppingBag, path: "/shop" },
  { key: "play", label: "Play", icon: Gamepad2, path: "/play-and-win" },
  { key: "social", label: "Social", icon: Users, path: "/community" },
];

// Mobile bottom tab bar — Pay sits in the middle as a raised money button
// (scan-to-pay is a revenue surface). Social/Rewards/Profile live in the
// top bar on mobile.
const MOBILE_NAV = [
  { key: "home", label: "Home", icon: Home, path: "/" },
  { key: "listen", label: "Listen", icon: Headphones, path: "/listen" },
  { key: "pay", label: "Pay", icon: CreditCard, path: "/pay", center: true },
  { key: "shop", label: "Shop", icon: ShoppingBag, path: "/shop" },
  { key: "play", label: "Play", icon: Gamepad2, path: "/play-and-win" },
];

export default function AppShellV2({ children }) {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const bare = BARE_ROUTES.some((r) => r.test(pathname))
    || isMarketingPath(pathname)
    || (pathname === "/" && !user)
    || pathname.startsWith("/admin");

  const hydrateTheme = useThemeStore((s) => s.hydrate);
  const bootstrapGeo = useGeoStore((s) => s.bootstrap);
  const geoReady = useGeoStore((s) => s.ready);
  useEffect(() => { hydrateTheme(); }, [hydrateTheme]);
  useEffect(() => { if (!geoReady) bootstrapGeo(); }, [geoReady, bootstrapGeo]);

  if (bare) return <>{children}</>;

  return (
    <div data-testid="shell-v2" className="nlv2 flex flex-col">
      <ShellV2Header />
      <main className="flex-1 pt-6 pb-52 lg:pb-40">
        <div className={`${CONTAINER} flex gap-6 xl:gap-8 items-start`}>
          <div className="flex-1 min-w-0">{children}</div>
          <RightRailV2 />
        </div>
      </main>
      <PlayerDockV2 />
      <BottomNavV2 />
    </div>
  );
}

function ShellV2Header() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const summary = useShellSummary();
  const [points, setPoints] = useState(null);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/bigcoin/me`, { withCredentials: true })
      .then((r) => { if (!cancel) setPoints(r.data?.balance); })
      .catch(() => {});
    return () => { cancel = true; };
  }, []);

  const isActive = (path) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
  const name = user?.first_name || (user?.name || "").split(" ")[0] || "there";
  const isPremium = !!summary?.is_premium;
  const balance = (points ?? 2450).toLocaleString();

  return (
    <header data-testid="shell-v2-header"
      className="nlv2-glass-strong sticky top-0 z-40 h-[68px]">
      <div className={`${CONTAINER} flex items-center gap-4 h-full`}>
      {/* Brand */}
      <Link to="/" className="flex flex-col leading-none shrink-0">
        <span className="font-black text-lg tracking-tight">
          Radio<span className="nlv2-grad">Life</span>
        </span>
        <span className="hidden lg:block text-[9.5px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>
          Listen · Earn · Shop · Play · Social
        </span>
      </Link>

      {/* Center nav — desktop only. Mobile uses the bottom tab bar. */}
      <nav className="hidden lg:flex flex-1 items-center justify-center gap-1 sm:gap-2 overflow-x-auto nlv2-scroll">
        {NAV.map(({ key, label, icon: Icon, path }) => {
          const active = isActive(path);
          return (
            <Link key={key} to={path} data-testid={`nlv2-nav-${key}`}
              className={`relative shrink-0 flex flex-col items-center gap-0.5 px-3 sm:px-4 py-1.5 rounded-xl transition-colors ${active ? "text-white" : "text-[#8b96b8] hover:text-white"}`}>
              <Icon size={18} />
              <span className="text-[11px] font-bold">{label}</span>
              {active && <span className="nlv2-underline" />}
            </Link>
          );
        })}
      </nav>

      {/* Right cluster */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0 ml-auto">
        <Link to="/community" data-testid="nlv2-top-social" title="Social"
          className="lg:hidden w-9 h-9 rounded-full grid place-items-center text-[#8b96b8] hover:text-white">
          <Users size={18} />
        </Link>
        <Link to="/wallet" data-testid="nlv2-bigpoints-pill"
          className="inline-flex items-center gap-1.5 h-9 pl-2 pr-2.5 sm:pr-3 rounded-full"
          style={{ background: "linear-gradient(135deg, rgba(245,197,99,0.18), rgba(245,158,11,0.10))", border: "1px solid rgba(245,197,99,0.35)" }}>
          <Coins size={15} className="text-[#f5c563]" />
          <span className="font-mono text-sm font-black text-[#f5c563]">{balance}</span>
        </Link>
        <NotificationBell />
        <VariantSwitcher />
        <Link to="/profile" data-testid="nlv2-avatar" className="flex items-center gap-2">
          <span className="w-9 h-9 rounded-full grid place-items-center text-white font-black shrink-0"
            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {name.slice(0, 1).toUpperCase()}
          </span>
          <span className="hidden xl:flex flex-col leading-tight">
            <span className="text-[13px] font-bold">Hi, {name}</span>
            <span className="text-[10px] font-semibold" style={{ color: isPremium ? "#f5c563" : "#8b96b8" }}>
              {isPremium ? "Premium" : "Free"}
            </span>
          </span>
          <ChevronDown size={13} className="hidden xl:block text-[#8b96b8]" />
        </Link>
      </div>
      </div>
    </header>
  );
}

function RightRailV2() {
  const { pathname } = useLocation();
  const summary = useShellSummary();
  const isPremium = !!summary?.is_premium;
  const pageRoute = railPageRoute(pathname);
  const RAIL_SLOTS = ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"];
  return (
    <aside data-testid="nlv2-right-rail"
      className="hidden xl:flex flex-col gap-4 w-[300px] shrink-0 sticky top-[84px]">
      <div className="text-[10px] font-mono uppercase tracking-widest px-1" style={{ color: "#6b7392" }}>
        Sponsored
      </div>
      {!isPremium && RAIL_SLOTS.map((k, i) => (
        <div key={k} data-testid={`nlv2-rail-ad-${i + 1}`}
          className="nlv2-glass rounded-2xl p-2 flex justify-center">
          <BannerAdSlot slotKey={k} pageRoute={pageRoute} />
        </div>
      ))}
      <Link to="/premium" data-testid="nlv2-rail-promo"
        className="nlv2-glass rounded-2xl p-4 block transition hover:brightness-110">
        <div className="text-[10px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>
          {isPremium ? "Premium" : "Upgrade"}
        </div>
        <div className="mt-1 font-black text-sm text-white">
          {isPremium ? "You're Ad-Free" : "Go Ad-Free"}
        </div>
        <div className="mt-1 text-[11px] leading-snug" style={{ color: "#a8b0cc" }}>
          {isPremium
            ? "Enjoy unlimited skips and zero ads across RadioLife."
            : "Premium removes ads and unlocks unlimited skips."}
        </div>
        {!isPremium && (
          <div className="mt-3 inline-flex items-center gap-1 text-[11px] font-bold nlv2-grad">
            Get Premium →
          </div>
        )}
      </Link>
      <a href="/advertise" data-testid="nlv2-rail-advertise"
        className="text-[10px] text-center font-semibold uppercase tracking-widest px-1 hover:text-white"
        style={{ color: "#6b7392" }}>
        Advertise here →
      </a>
    </aside>
  );
}

function BottomNavV2() {
  const { pathname } = useLocation();
  const isActive = (path) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
  return (
    <nav data-testid="nlv2-bottom-nav"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 nlv2-glass-strong border-t border-white/5"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="flex items-stretch justify-around h-16 px-2">
        {MOBILE_NAV.map(({ key, label, icon: Icon, path, center }) => {
          const active = isActive(path);
          if (center) {
            return (
              <Link key={key} to={path} data-testid={`nlv2-tab-${key}`}
                className="flex flex-col items-center justify-end -mt-5 pb-1">
                <span className="w-14 h-14 rounded-full grid place-items-center shadow-lg"
                  style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)", boxShadow: "0 6px 20px rgba(245,158,11,0.45)" }}>
                  <Icon size={24} className="text-black" />
                </span>
                <span className="text-[10px] font-bold mt-0.5 text-[#f5c563]">{label}</span>
              </Link>
            );
          }
          return (
            <Link key={key} to={path} data-testid={`nlv2-tab-${key}`}
              className={`flex flex-col items-center justify-center gap-0.5 flex-1 transition-colors ${active ? "text-white" : "text-[#8b96b8]"}`}>
              <Icon size={20} />
              <span className="text-[10px] font-semibold">{label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

function PlayerDockV2() {
  return (
    <div data-testid="nlv2-player-dock" className="fixed bottom-16 lg:bottom-0 inset-x-0 z-30 px-3 sm:px-6 pb-2 lg:pb-4 pointer-events-none">
      <div className="pointer-events-auto max-w-[1440px] mx-auto">
        <OnAirOfferCard />
        <MiniPlayer />
      </div>
    </div>
  );
}
