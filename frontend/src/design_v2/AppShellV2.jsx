// New Look V2 shell — premium dark cinematic chrome (integrated top nav +
// sticky player dock). Reuses the existing audio engine (MiniPlayer +
// GlobalAudio), companion, notifications and variant switcher. Only the
// visual composition is new. Bare/marketing/admin routes render untouched.
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Home, Headphones, ShoppingBag, Gamepad2, Users, Coins, ChevronDown,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useThemeStore } from "@/theme/useTheme";
import { useGeoStore } from "@/store/useGeoStore";
import { useShellSummary } from "@/shell/useShellData";
import { MiniPlayer } from "@/shell/primitives";
import OnAirOfferCard from "@/shell/OnAirOfferCard";
import VariantSwitcher from "@/shell/VariantSwitcher";
import NotificationBell from "@/components/NotificationBell";
import { isMarketingPath } from "@/shell/AppShellB";
import "./newlookv2.css";

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
      <main className="flex-1 px-4 sm:px-6 xl:px-12 pt-6 pb-40">
        {children}
      </main>
      <PlayerDockV2 />
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
      className="nlv2-glass-strong sticky top-0 z-40 flex items-center gap-4 px-4 sm:px-6 xl:px-10 h-[68px]">
      {/* Brand */}
      <Link to="/" className="flex flex-col leading-none shrink-0">
        <span className="font-black text-lg tracking-tight">
          Radio<span className="nlv2-grad">Life</span>
        </span>
        <span className="hidden lg:block text-[9.5px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>
          Listen · Earn · Shop · Play · Social
        </span>
      </Link>

      {/* Center nav */}
      <nav className="flex-1 flex items-center justify-center gap-1 sm:gap-2 overflow-x-auto nlv2-scroll">
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
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <Link to="/wallet" data-testid="nlv2-bigpoints-pill"
          className="hidden sm:inline-flex items-center gap-1.5 h-9 pl-2.5 pr-3 rounded-full"
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
    </header>
  );
}

function PlayerDockV2() {
  return (
    <div data-testid="nlv2-player-dock" className="fixed bottom-0 inset-x-0 z-30 px-4 sm:px-6 pb-4 pointer-events-none">
      <div className="pointer-events-auto max-w-[1400px] mx-auto">
        <OnAirOfferCard />
        <MiniPlayer />
      </div>
    </div>
  );
}
