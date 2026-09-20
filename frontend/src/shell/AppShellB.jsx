// YouTube-style consumer shell (redesign). Left menu (Primary / Discover /
// Rewards / Your stations), sticky top bar + filter chips, avatar Tools
// dropdown, dual theme. Admin routes render their own minimal shell.
import React, { useEffect, useState, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home, Radio as RadioIcon, Gamepad2, Brain, Wallet as WalletIcon,
  Map as MapIcon, BadgeCheck, Podcast, User as UserIcon,
  Search, Menu, MoreHorizontal, ChevronRight, Headphones, Crown,
  Mic, Megaphone, ShieldCheck, LogOut, Settings,
  Newspaper, Users as UsersIcon, Trophy, ShoppingBag, ShoppingCart,
} from "lucide-react";

import { useViewport } from "./useViewport";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";
import { useShopCart } from "@/design_radiolife/useShopCart";
import { useProductCart } from "@/design_radiolife/useProductCart";
import { MiniPlayer } from "./primitives";
import MobilePremiumStrip from "./MobilePremiumStrip";
import { useAuth } from "@/AuthContext";
import { useRoleNav } from "@/lib/roleNav";
import { useGeoStore } from "@/store/useGeoStore";
import CityChip from "@/components/CityChip";
import ChannelCategoryFooter from "@/components/ChannelCategoryFooter";
import NotificationBell from "@/components/NotificationBell";
import HeaderMiniWallet from "./HeaderMiniWallet";
import VariantSwitcher from "./VariantSwitcher";
import ThemeToggle from "@/theme/ThemeToggle";
import BannerAdSlot from "@/components/BannerAdSlot";
import OnAirOfferCard from "./OnAirOfferCard";
import { useThemeStore } from "@/theme/useTheme";
import { useShellSummary, useShellFilter, fmtCount } from "./useShellData";

// Helper exported for tests + RootGate.
export function isMarketingPath(pathname) {
  return MARKETING_ROUTES.some((r) => r.test(pathname));
}

const BARE_ROUTES = [
  /^\/login(\b|\/)/, /^\/onboarding(\b|\/)/, /^\/auth(\b|\/)/,
  /^\/portal(\b|\/)/,
  /^\/dev\/styleguide(\b|\/)/, /^\/tv(\b|\/)/,
];

export const MARKETING_ROUTES = [
  /^\/about(\b|\/)/, /^\/for-business(\b|\/)/, /^\/for-advertisers(\b|\/)/,
  /^\/pricing(\b|\/)/, /^\/legal(\b|\/)/, /^\/l\/v2(\b|\/)/,
];

// ── Nav model (Classic-B consumer IA: Home · Listen · Shop · Play · Social) ──
const PRIMARY_NAV = [
  { key: "home",   label: "Home",   icon: Home,        path: "/" },
  { key: "listen", label: "Listen", icon: Headphones,  path: "/listen" },
  { key: "shop",   label: "Shop",   icon: ShoppingBag, path: "/shop", badge: "shop" },
  { key: "play",   label: "Play",   icon: Gamepad2,    path: "/play-and-win", badge: "games" },
  { key: "social", label: "Social", icon: UsersIcon,   path: "/community" },
];
const DISCOVER_NAV = [
  { key: "news",      label: "News",      icon: Newspaper,  path: "/news" },
  { key: "podcasts",  label: "Podcasts",  icon: Podcast,    path: "/podcasts", hideWhenEmpty: "podcasts" },
  { key: "map",       label: "Map",       icon: MapIcon,    path: "/map" },
];
const REWARDS_NAV = [
  { key: "trivia",   label: "Trivia",        icon: Brain,      path: "/trivia" },
  { key: "predict",  label: "Predict & Win", icon: Trophy,     path: "/predict-win" },
  { key: "passport", label: "Passport",      icon: BadgeCheck, path: "/passport" },
];
const MOBILE_TABS = PRIMARY_NAV;

// Light Home feed chips (Classic-B). Replaces the busy backend-driven
// chip bar. These re-scope the audio-first Home For-You rail.
const HOME_CHIPS = [
  { key: "all",      label: "All" },
  { key: "foryou",   label: "For You" },
  { key: "local",    label: "Local" },
  { key: "trending", label: "Trending" },
];

export default function AppShellB({ children }) {
  const { pathname } = useLocation();
  const vp = useViewport();
  const { user } = useAuth();
  const bareAuth      = BARE_ROUTES.some((r) => r.test(pathname));
  const isMarketing   = isMarketingPath(pathname);
  const isAnonRoot    = pathname === "/" && !user;
  const bare = bareAuth || isMarketing || isAnonRoot;
  useKeyboardShortcuts({ enabled: !bare && vp.layout === "desktop" });

  // Phase A — hydrate the user's theme (dark default) once on mount.
  const hydrateTheme = useThemeStore((s) => s.hydrate);
  useEffect(() => { hydrateTheme(); }, [hydrateTheme]);

  const bootstrapGeo = useGeoStore((s) => s.bootstrap);
  const geoReady     = useGeoStore((s) => s.ready);
  useEffect(() => { if (!geoReady) bootstrapGeo(); }, [geoReady, bootstrapGeo]);
  useEffect(() => { if (user?.user_id) bootstrapGeo(); }, [user?.user_id, bootstrapGeo]);

  // Remove any injected #emergent-badge node.
  useEffect(() => {
    if (typeof window === "undefined" || typeof MutationObserver === "undefined") return;
    const kill = (el) => { try { el.remove(); } catch (_) { /* noop */ } };
    document.querySelectorAll('#emergent-badge, a#emergent-badge, [id^="emergent-badge"]').forEach(kill);
    const obs = new MutationObserver((muts) => {
      for (const m of muts) {
        m.addedNodes && m.addedNodes.forEach((n) => {
          if (n.nodeType !== 1) return;
          if (n.id && n.id.startsWith("emergent-badge")) kill(n);
          n.querySelectorAll && n.querySelectorAll('[id^="emergent-badge"]').forEach(kill);
        });
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, []);

  if (bare) return <>{children}</>;
  if (vp.layout === "desktop") return <DesktopShell>{children}</DesktopShell>;
  if (vp.layout === "tablet")  return <MobileShell tablet>{children}</MobileShell>;
  return <MobileShell>{children}</MobileShell>;
}

// ─── Desktop (≥1024) ────────────────────────────────────────────────────
const SIDEBAR_COLLAPSED_KEY = "bigfm.sidebar.collapsed";

function DesktopShell({ children }) {
  const { pathname } = useLocation();
  const isAdminRoute = pathname.startsWith("/admin");
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return typeof window !== "undefined"
        && window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
    } catch (_) { return false; }
  });
  const onToggle = () => {
    setCollapsed((v) => {
      const next = !v;
      try { window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0"); } catch (_) { /* ignore */ }
      return next;
    });
  };
  return (
    <div data-testid="shell-desktop"
      data-sidebar-collapsed={collapsed ? "true" : "false"}
      data-admin-route={isAdminRoute ? "true" : "false"}
      className="min-h-screen bg-bg-base text-text-primary font-sans flex flex-col">
      <div className="flex flex-1 overflow-hidden">
        {!isAdminRoute && <Sidebar collapsed={collapsed} />}
        <div className="flex-1 flex flex-col overflow-hidden"
          style={isAdminRoute ? { paddingLeft: 220 } : undefined}>
          <TopBar onHamburger={onToggle} />
          {/* Value-before-advertising: no leaderboard above the audio-first
              Home (/). Kept on every other page. */}
          {!isAdminRoute && pathname !== "/" && <AdLeaderboard />}
          {!isAdminRoute && <FilterChips />}
          <main className={`flex-1 overflow-y-auto py-6 animate-fade-up pb-32 ${isAdminRoute ? "px-4" : "px-6 xl:px-10 2xl:px-16"}`}>
            {children}
            <ChannelCategoryFooter />
          </main>
        </div>
      </div>
      <PersistentPlayer />
    </div>
  );
}

function Sidebar({ collapsed }) {
  const summary = useShellSummary();
  return (
    <aside data-testid="shell-sidebar"
      style={{ width: collapsed ? 72 : 240, borderColor: "var(--line)" }}
      className="shrink-0 border-r bg-bg-elevated flex flex-col transition-[width] duration-200">
      <div style={{ borderColor: "var(--line)" }} className="border-b">
        <div className="h-16 flex items-center px-4">
          {!collapsed && (
            <Link to="/" className="font-display font-bold text-lg tracking-display-tight">
              FUUSIC<span className="text-accent-electric">.app</span>
            </Link>
          )}
        </div>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto no-scrollbar">
        {PRIMARY_NAV.map(({ key, ...n }) => (
          <NavItem key={key} {...n} collapsed={collapsed} summary={summary} />
        ))}
        <NavSection label="Discover" collapsed={collapsed} />
        {DISCOVER_NAV.map(({ key, ...n }) => (
          (n.hideWhenEmpty && !summary?.[`${n.hideWhenEmpty}_count`]) ? null
            : <NavItem key={key} {...n} collapsed={collapsed} summary={summary} />
        ))}
        <NavSection label="Rewards" collapsed={collapsed} />
        {REWARDS_NAV.map(({ key, ...n }) => (
          <NavItem key={key} {...n} collapsed={collapsed} summary={summary} />
        ))}
        {!collapsed && (summary?.flagships?.length > 0) && (
          <>
            <NavSection label={`Your stations · ★ ${summary.flagship_count} flagships`} collapsed={collapsed} />
            <YourStations items={summary.flagships} />
          </>
        )}
      </nav>
      <div style={{ borderColor: "var(--line)" }} className="border-t p-2">
        <NavItem key="profile" label="Profile" icon={UserIcon} path="/profile" collapsed={collapsed} />
        {!collapsed && (
          <div data-testid="funasia-footer" className="px-3 pt-2 text-[10px] text-text-secondary">
            part of{" "}
            <a href="https://funasianetwork.com" target="_blank" rel="noreferrer"
              data-testid="funasia-footer-link" className="underline hover:text-text-primary">funasianetwork.com</a>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavSection({ label, collapsed }) {
  if (collapsed) return <div className="mt-3 mb-1 mx-2 h-px" style={{ background: "var(--line)" }} />;
  return (
    <div className="mt-4 mb-1.5 px-3 text-[10px] font-mono uppercase tracking-widest text-text-secondary">
      {label}
    </div>
  );
}

function badgeLabel(badgeKey, summary) {
  if (!badgeKey || !summary) return null;
  if (badgeKey === "games" && summary.badges?.games) return `${summary.badges.games} live`;
  if (badgeKey === "shop" && summary.badges?.shop) return `${summary.badges.shop} offers`;
  if (badgeKey === "wallet" && summary.wallet_balance != null) return fmtCount(summary.wallet_balance);
  return null;
}

function NavItem({ label, icon: Icon, path, badge, collapsed, active: activeProp, summary }) {
  const { pathname } = useLocation();
  const active = activeProp != null ? activeProp : pathname === path;
  const slug = (label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const b = badgeLabel(badge, summary);
  return (
    <Link to={path} data-testid={`nav-${slug}`} title={collapsed ? label : undefined}
      className={[
        "flex items-center gap-3 px-3 h-10 rounded-token-md transition-colors duration-150",
        active ? "bg-accent-electric/15 text-accent-electric"
          : "text-text-primary hover:bg-[var(--bg-glass)]",
      ].join(" ")}>
      <Icon size={19} className="shrink-0" />
      {!collapsed && <span className="font-semibold text-[14.5px] flex-1 truncate">{label}</span>}
      {!collapsed && b && (
        <span data-testid={`nav-badge-${slug}`}
          className="text-[10px] font-black px-1.5 py-0.5 rounded-full border"
          style={{ color: "var(--accent-gold)", background: "color-mix(in srgb, var(--accent-gold) 12%, transparent)", borderColor: "color-mix(in srgb, var(--accent-gold) 40%, transparent)" }}>
          {b}
        </span>
      )}
    </Link>
  );
}

function YourStations({ items }) {
  return (
    <div className="mt-0.5 space-y-0.5" data-testid="nav-your-stations">
      {items.slice(0, 8).map((s) => (
        <Link key={s.slug || s.id} to={`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`}
          data-testid={`your-station-${s.slug}`}
          className="flex items-center gap-2.5 px-3 h-9 rounded-token-md text-text-secondary hover:text-text-primary hover:bg-[var(--bg-glass)] transition-colors duration-150">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${s.live ? "bg-accent-live animate-live-dot" : "bg-text-secondary/40"}`} />
          <span className="text-[13px] font-medium truncate flex-1">{s.name}</span>
        </Link>
      ))}
    </div>
  );
}

function TopBar({ onHamburger }) {
  const navigate = useNavigate();
  const summary = useShellSummary();
  const [q, setQ] = useState("");
  const onSubmit = (e) => {
    e.preventDefault();
    const v = q.trim();
    if (v) navigate(`/search?q=${encodeURIComponent(v)}`);
  };
  const count = summary?.station_count ? fmtCount(summary.station_count) : "";
  const placeholder = count
    ? `Search ${count}+ stations, restaurants, deals…`
    : "Search stations, restaurants, deals…";
  return (
    <header data-testid="shell-topbar"
      style={{ borderColor: "var(--line)" }}
      className="h-16 shrink-0 border-b bg-bg-base px-4 xl:px-6 flex items-center gap-4">
      <button type="button" onClick={onHamburger} data-testid="sidebar-toggle" aria-label="Toggle menu"
        className="w-10 h-10 grid place-items-center rounded-full text-text-secondary hover:text-text-primary hover:bg-[var(--bg-glass)] transition-colors duration-150">
        <Menu size={20} />
      </button>
      <Link to="/" className="font-display font-bold text-lg tracking-display-tight hidden lg:block">
        FUUSIC<span className="text-accent-electric">.app</span>
      </Link>
      <form onSubmit={onSubmit} role="search" className="relative flex-1 max-w-[48%] mx-auto" data-testid="topbar-search-form">
        <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-text-secondary pointer-events-none" />
        <input type="text" placeholder={placeholder} data-testid="search-input" data-shortcut-target="search"
          value={q} onChange={(e) => setQ(e.target.value)}
          style={{ borderColor: "var(--line)" }}
          className="w-full pl-10 pr-3 h-10 rounded-full bg-bg-elevated border text-sm focus:outline-none focus:border-accent-electric/50 transition-colors duration-150" />
      </form>
      <div className="flex items-center gap-1.5">
        <HeaderMiniWallet />
        <NotificationBell />
        <ThemeToggle />
        <ShopCartButton />
        <AvatarMenu />
      </div>
    </header>
  );
}

function AvatarMenu() {
  const { user, logout } = useAuth();
  const { canCreator, canAdvertiser, canAdmin, canAdReview } = useRoleNav();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const hasTools = canCreator || canAdvertiser || (canAdReview && !canAdmin) || canAdmin;
  const go = (to) => { setOpen(false); window.location.assign(to); };
  return (
    <div className="relative" ref={ref}>
      <button type="button" data-testid="topbar-profile" aria-label="Account"
        onClick={() => setOpen((v) => !v)}
        className="w-9 h-9 rounded-full bg-gradient-to-br from-accent-electric to-accent-magenta grid place-items-center text-black font-black">
        {(user?.first_name || user?.name || "U").slice(0, 1).toUpperCase()}
      </button>
      {open && (
        <div data-testid="avatar-menu" style={{ borderColor: "var(--line)" }}
          className="absolute right-0 mt-2 w-60 rl-card p-1.5 z-50">
          <MenuRow icon={UserIcon} label="Profile" onClick={() => go("/profile")} testId="menu-profile" />
          <MenuRow icon={WalletIcon} label="Wallet" onClick={() => go("/wallet")} testId="menu-wallet" />
          <MenuRow icon={Crown} label="Premium" onClick={() => go("/pricing")} testId="menu-premium" />
          <MenuRow icon={Settings} label="Settings" onClick={() => go("/profile")} testId="menu-settings" />
          {hasTools && <MenuDivider label="Tools" />}
          {canCreator && <MenuRow icon={Mic} label="Creator Studio" onClick={() => go("/creator")} testId="menu-creator" />}
          {canAdvertiser && <MenuRow icon={Megaphone} label="Advertiser" onClick={() => go("/advertiser")} testId="menu-advertiser" />}
          {canAdReview && !canAdmin && <MenuRow icon={ShieldCheck} label="Ad Review" onClick={() => go("/admin/ad-review")} testId="menu-ad-review" />}
          {canAdmin && <MenuRow icon={ShieldCheck} label="Admin console" onClick={() => go("/admin")} testId="menu-admin" />}
          <MenuDivider label="Theme" />
          <div className="px-1 py-1"><ThemeToggle className="!w-auto !h-9 px-3 gap-2" /></div>
          <MenuDivider />
          <MenuRow icon={LogOut} label="Log out" onClick={() => { setOpen(false); logout?.(); }} testId="menu-logout" />
        </div>
      )}
    </div>
  );
}

function MenuRow({ icon: Icon, label, onClick, testId }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
      className="w-full flex items-center gap-3 px-3 h-10 rounded-token-md text-text-secondary hover:text-text-primary hover:bg-[var(--bg-glass)] transition-colors duration-150 text-sm font-medium">
      <Icon size={17} /> {label}
    </button>
  );
}
function MenuDivider({ label }) {
  return (
    <div className="mt-1.5 mb-1 px-3 text-[10px] font-mono uppercase tracking-widest text-text-secondary"
      style={{ borderTop: "1px solid var(--line)", paddingTop: label ? 8 : 0 }}>
      {label || ""}
    </div>
  );
}

// ── Ad Slot 1 — leaderboard strip (real campaigns via /api/ads/banner/
// decision; house-creative fallback). Hidden for Premium and when the
// decision returns nothing (BannerAdSlot renders null → empty wrapper
// collapses).
function AdLeaderboard() {
  const { pathname } = useLocation();
  const summary = useShellSummary();
  if (summary?.is_premium) return null;
  return (
    <div data-testid="ad-leaderboard" className="flex justify-center px-4">
      <BannerAdSlot slotKey="top_leaderboard" pageRoute={pathname} />
    </div>
  );
}

// ── Filter chips (YouTube signature) ───────────────────────────────────
function FilterChips() {
  const chip = useShellFilter((s) => s.chip);
  const setChip = useShellFilter((s) => s.setChip);
  const navigate = useNavigate();
  const location = useLocation();
  const chips = HOME_CHIPS;
  const onChip = (key) => {
    setChip(key);
    // Chips drive the Home feed — bring the user there from any other page.
    if (location.pathname !== "/") navigate("/");
  };
  return (
    <div data-testid="shell-filter-chips" style={{ borderColor: "var(--line)" }}
      className="sticky top-0 z-20 bg-bg-base/95 backdrop-blur border-b flex gap-2 overflow-x-auto no-scrollbar px-4 xl:px-6 py-2.5">
      {chips.map((c) => {
        const active = chip === c.key;
        return (
          <button key={c.key} onClick={() => onChip(c.key)} data-testid={`chip-${c.key}`}
            className={[
              "shrink-0 h-9 px-3.5 rounded-full text-[13px] font-bold border transition-colors duration-150 flex items-center gap-1.5",
              active ? "bg-text-primary text-bg-base border-transparent"
                : "bg-[var(--bg-glass)] text-text-secondary hover:text-text-primary",
            ].join(" ")}
            style={active ? undefined : { borderColor: "var(--line)" }}>
            {c.label}
            {c.count != null && <span className={active ? "opacity-70" : "text-text-secondary/70"}>{fmtCount(c.count)}</span>}
          </button>
        );
      })}
    </div>
  );
}

function ShopCartButton() {
  const navigate = useNavigate();
  const menuItems = useShopCart((s) => s.items);
  const productGroups = useProductCart((s) => s.groups);
  const menuCount = menuItems.reduce((n, i) => n + i.qty, 0);
  const productCount = Object.values(productGroups || {})
    .reduce((n, g) => n + g.items.reduce((m, i) => m + i.qty, 0), 0);
  const total = menuCount + productCount;
  const go = () => navigate(menuCount > 0 ? "/shop/checkout/menu" : total > 0 ? "/shop/cart" : "/shop");
  return (
    <button type="button" onClick={go} data-testid="topbar-cart" aria-label="Cart"
      className="relative w-10 h-10 grid place-items-center rounded-full text-text-secondary hover:text-text-primary hover:bg-[var(--bg-glass)] transition-colors duration-150">
      <ShoppingCart size={18} />
      {total > 0 && (
        <span data-testid="topbar-cart-count"
          className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-accent-electric text-black text-[11px] font-black grid place-items-center">
          {total}
        </span>
      )}
    </button>
  );
}

function PersistentPlayer() {
  return (
    <motion.div initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      data-testid="persistent-player"
      className="fixed bottom-0 inset-x-0 z-30 px-6 pb-4 pointer-events-none">
      <div className="pointer-events-auto">
        <OnAirOfferCard />
        <MiniPlayer />
      </div>
    </motion.div>
  );
}

// ─── Mobile / Tablet (<1024) ────────────────────────────────────────────
function MobileShell({ children }) {
  const [drawer, setDrawer] = useState(false);
  const summary = useShellSummary();
  const navigate = useNavigate();
  const drawerSections = [
    { label: "Discover", items: DISCOVER_NAV.filter((n) => !(n.hideWhenEmpty && !summary?.[`${n.hideWhenEmpty}_count`])) },
    { label: "Rewards", items: REWARDS_NAV },
  ];
  return (
    <div data-testid="shell-mobile" className="min-h-screen bg-bg-base text-text-primary font-sans pb-40">
      <header style={{ borderColor: "var(--line)" }}
        className="sticky top-0 z-30 h-14 bg-bg-base/95 backdrop-blur border-b flex items-center gap-2 px-3">
        <button type="button" onClick={() => setDrawer(true)} data-testid="mobile-hamburger" aria-label="Menu"
          className="w-10 h-10 grid place-items-center rounded-full text-text-secondary hover:text-text-primary">
          <Menu size={20} />
        </button>
        <button type="button" onClick={() => navigate("/search")} data-testid="mobile-search"
          style={{ borderColor: "var(--line)" }}
          className="flex-1 h-9 rounded-full bg-bg-elevated border flex items-center gap-2 px-3 text-text-secondary text-sm">
          <Search size={15} /> Search…
        </button>
        <ThemeToggle />
        <HeaderMiniWallet />
      </header>
      <FilterChips />
      <main className="px-4 py-4 animate-fade-up">
        {children}
        <ChannelCategoryFooter />
      </main>
      <div className="fixed bottom-16 inset-x-0 z-30 px-3">
        <OnAirOfferCard />
        <MobilePremiumStrip />
        <div className="mt-1.5"><MiniPlayer /></div>
      </div>
      <nav data-testid="shell-bottom-tabs" style={{ borderColor: "var(--line)" }}
        className="fixed bottom-0 inset-x-0 h-16 z-40 bg-bg-elevated/95 backdrop-blur border-t grid grid-cols-5 items-center px-1">
        {MOBILE_TABS.map(({ key, ...t }) => <BottomTab key={key} {...t} />)}
      </nav>
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-black/50" onClick={() => setDrawer(false)} />
            <motion.div initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }}
              transition={{ duration: 0.2 }} data-testid="mobile-drawer"
              className="fixed top-0 left-0 bottom-0 z-50 w-72 bg-bg-elevated p-3 overflow-y-auto">
              <div className="font-display font-bold text-lg tracking-display-tight px-2 py-2">
                FUUSIC<span className="text-accent-electric">.app</span>
              </div>
              {PRIMARY_NAV.map(({ key, ...n }) => (
                <DrawerItem key={key} {...n} summary={summary} onNav={() => setDrawer(false)} />
              ))}
              {drawerSections.map((sec) => (
                <React.Fragment key={sec.label}>
                  <div className="mt-4 mb-1 px-2 text-[10px] font-mono uppercase tracking-widest text-text-secondary">{sec.label}</div>
                  {sec.items.map(({ key, ...n }) => <DrawerItem key={key} {...n} onNav={() => setDrawer(false)} />)}
                </React.Fragment>
              ))}
              {summary?.flagships?.length > 0 && (
                <>
                  <div className="mt-4 mb-1 px-2 text-[10px] font-mono uppercase tracking-widest text-text-secondary">Your stations</div>
                  <YourStations items={summary.flagships} />
                </>
              )}
              <div className="mt-4"><DrawerItem label="Profile" icon={UserIcon} path="/profile" onNav={() => setDrawer(false)} /></div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function DrawerItem({ label, icon: Icon, path, badge, summary, onNav }) {
  const b = badgeLabel(badge, summary);
  return (
    <Link to={path} onClick={onNav} data-testid={`drawer-${(label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
      className="flex items-center gap-3 px-3 h-11 rounded-token-md text-text-secondary hover:text-text-primary hover:bg-[var(--bg-glass)] transition-colors duration-150">
      <Icon size={19} /> <span className="font-semibold text-sm flex-1">{label}</span>
      {b && <span className="text-[10px] font-black text-accent-gold">{b}</span>}
    </Link>
  );
}

function BottomTab({ label, icon: Icon, path }) {
  const { pathname } = useLocation();
  const active = pathname === path;
  return (
    <Link to={path} data-testid={`tab-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
      className={["flex flex-col items-center justify-center h-full gap-0.5",
        active ? "text-accent-electric" : "text-text-secondary"].join(" ")}>
      <Icon size={20} />
      <span className="text-[10px] font-medium">{label.split(" ")[0]}</span>
    </Link>
  );
}
