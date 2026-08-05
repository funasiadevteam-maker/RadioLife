// Phase 15a — responsive shell. Picks Desktop/Tablet/Mobile based on
// viewport. Existing routes render inside via `children`. 15b polishes
// each route; 15a only ships the chrome.
import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Home, Radio as RadioIcon, Gamepad2, Brain, Wallet as WalletIcon,
  Map as MapIcon, BadgeCheck, Podcast, User as UserIcon,
  Bell, Search, ChevronLeft, ChevronRight, MoreHorizontal,
  Sparkles, Mic, Megaphone, ShieldCheck,
  Newspaper, Users as UsersIcon,
  Globe2,  // Phase 42-A — Live Radio nav icon
  Trophy,  // Phase 42-E1.2 — Predict & Win nav icon
} from "lucide-react";

import { useViewport } from "./useViewport";
import { useKeyboardShortcuts } from "./useKeyboardShortcuts";
import { MiniPlayer, Chip } from "./primitives";
// Phase LEGACY.1 — mobile-only premium/ad strip (renders above mini-player).
import MobilePremiumStrip from "./MobilePremiumStrip";
import { useAuth } from "@/AuthContext";
import { useRoleNav } from "@/lib/roleNav";  // Phase 19a — role-aware nav
// Phase R.1 — Design variant toggle (legacy ↔ RadioLife).
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
// Phase 15d — geo store + city chip (lazy-load to keep bundle lean).
import { useGeoStore } from "@/store/useGeoStore";
import CityChip from "@/components/CityChip";
// Phase 41 S1.8 — category-grouped channel discovery footer. Mounted
// inside each <main> so it scrolls naturally at the bottom of any page
// that PageFrame deems "framed" (listener routes only). Component
// self-gates via location → returns null on excluded routes.
import ChannelCategoryFooter from "@/components/ChannelCategoryFooter";
// Phase 41 S2.C.1 — notifications bell + dropdown.
import NotificationBell from "@/components/NotificationBell";

// Helper exported for tests + RootGate.
export function isMarketingPath(pathname) {
  return MARKETING_ROUTES.some((r) => r.test(pathname));
}

// Routes that should NOT be wrapped in shell chrome (auth flows etc).
// Phase 19a Part 3 — admin + advertiser surfaces ARE wrapped now so the
// sidebar persists; users were losing navigation context after clicking
// any admin sub-page.
const BARE_ROUTES = [
  /^\/login(\b|\/)/, /^\/onboarding(\b|\/)/, /^\/auth(\b|\/)/,
  /^\/dev\/styleguide(\b|\/)/,
  // Phase 41 S4.A — In-Store Business TV Display is a kiosk; no shell chrome.
  /^\/tv(\b|\/)/,
];

// Phase 15c — marketing routes own their own MarketingShell.
// Exported so RootGate + tests can introspect.
// Phase LAND.v2 (2026-08-02) — `/l/v2` alternative landing is also
// self-contained (no AppShell chrome, no MiniPlayer).
export const MARKETING_ROUTES = [
  /^\/about(\b|\/)/, /^\/for-business(\b|\/)/, /^\/for-advertisers(\b|\/)/,
  /^\/pricing(\b|\/)/, /^\/legal(\b|\/)/,
  /^\/l\/v2(\b|\/)/,
];

const PRIMARY_NAV = [
  { key: "home",     label: "Home",       icon: Home,        path: "/" },
  { key: "radio",    label: "Radio",      icon: RadioIcon,   path: "/radio" },
  { key: "play",     label: "Play & Win", icon: Gamepad2,    path: "/play" },
  { key: "trivia",   label: "Trivia",     icon: Brain,       path: "/trivia" },
  { key: "wallet",   label: "Wallet",     icon: WalletIcon,  path: "/wallet" },
];
const SECONDARY_NAV = [
  // Phase 41 P1 — News + Community surfaced in the sidebar nav. News
  // is the AI News Radio + /news headlines surface (shipped Phase 40);
  // Community is the user-station discovery + Create-My-Radio funnel
  // (shipped Phase 41 S1).
  // Phase 42-A2 — "Live Radio" nav entry retired; everything lives
  // under the unified "Radio" tab (RadioDiscover home).  Imported
  // stations browse + station detail are now reached via /radio/browse
  // and /radio/station/:id respectively.
  // Phase 42-E1.2 — Predict & Win surfaced between News and Community.
  { key: "news",        label: "News",            icon: Newspaper,   path: "/news" },
  { key: "predict",  label: "Predict & Win", icon: Trophy,      path: "/predict-win" },
  { key: "community", label: "Community",  icon: UsersIcon,   path: "/community" },
  { key: "passport",  label: "Passport",   icon: BadgeCheck,  path: "/passport" },
  { key: "map",       label: "Map",        icon: MapIcon,     path: "/map" },
  { key: "podcasts",  label: "Podcasts",   icon: Podcast,     path: "/podcasts" },
];

// Phase 19a — role-gated entries. Each section is rendered only if the
// caller's role capability flag is true. NO listener-visible change.
const STUDIO_NAV = [
  { key: "highlights", label: "Highlights", icon: Sparkles,    path: "/highlights" },
  { key: "studio",      label: "Creator Studio", icon: Mic,    path: "/creator" },
];
const BIZ_NAV = [
  { key: "advertiser", label: "Advertiser", icon: Megaphone,  path: "/advertiser" },
];
const ADMIN_NAV = [
  { key: "admin",                       label: "Admin Home",                  icon: ShieldCheck, path: "/admin" },
  { key: "admin-users",                 label: "User Management",             icon: ShieldCheck, path: "/admin/users" },
  { key: "admin-podcasts-apps",     label: "Podcast Applications",  icon: ShieldCheck, path: "/admin/podcasts/applications" },
  { key: "admin-podcasts-channels", label: "Podcast Channels",      icon: ShieldCheck, path: "/admin/podcasts/channels" },
];

// Phase ADMOD.1 — Ad Manager (or admin) domain-scoped nav.
const AD_MANAGER_NAV = [
  { key: "ad-review",  label: "Ad Review", icon: ShieldCheck, path: "/admin/ad-review" },
];

// Mobile bottom tabs (5 visible + overflow drawer).
const MOBILE_TABS = PRIMARY_NAV;

export default function AppShell({ children }) {
  const { pathname } = useLocation();
  const vp = useViewport();
  const { user } = useAuth();
  const bareAuth      = BARE_ROUTES.some((r) => r.test(pathname));
  const isMarketing   = isMarketingPath(pathname);
  // Phase 15c — anon hitting `/` sees marketing Landing (which mounts its
  // own MarketingShell); don't double-wrap with the listener chrome.
  const isAnonRoot    = pathname === "/" && !user;
  const bare = bareAuth || isMarketing || isAnonRoot;
  // Hook must respect bare routes — typing `/` inside an admin form
  // shouldn't be intercepted by the in-shell focus-search handler.
  useKeyboardShortcuts({ enabled: !bare && vp.layout === "desktop" });

  // Phase 15d — bootstrap geo on shell mount. Idempotent (no-op if loading).
  // Phase 18b polish: also re-bootstrap whenever the auth user changes so
  // the "around <city>" header switches from anon IP geo to the user's home
  // market the instant they finish login (was previously stuck on Dallas).
  const bootstrapGeo = useGeoStore((s) => s.bootstrap);
  const geoReady     = useGeoStore((s) => s.ready);
  useEffect(() => { if (!geoReady) bootstrapGeo(); }, [geoReady, bootstrapGeo]);
  useEffect(() => {
    if (user?.user_id) bootstrapGeo();
  }, [user?.user_id, bootstrapGeo]);

  // Hotfix: a server-side ingress may inject `#emergent-badge` post-hydration.
  // CSS in index.css hides it; this MutationObserver removes the node entirely
  // so it can't intercept clicks, get measured by tests, or leak into the
  // accessibility tree.
  useEffect(() => {
    if (typeof window === "undefined" || typeof MutationObserver === "undefined") return;
    const kill = (el) => { try { el.remove(); } catch (_) { /* noop */ } };
    document.querySelectorAll(
      '#emergent-badge, a#emergent-badge, [id^="emergent-badge"]'
    ).forEach(kill);
    const obs = new MutationObserver((muts) => {
      for (const m of muts) {
        m.addedNodes && m.addedNodes.forEach((n) => {
          if (n.nodeType !== 1) return;
          if (n.id && n.id.startsWith("emergent-badge")) kill(n);
          n.querySelectorAll &&
            n.querySelectorAll('[id^="emergent-badge"]').forEach(kill);
        });
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    return () => obs.disconnect();
  }, []);

  if (bare) return <>{children}</>;

  if (vp.layout === "desktop") return <DesktopShell>{children}</DesktopShell>;
  if (vp.layout === "tablet")  return <TabletShell>{children}</TabletShell>;
  return <MobileShell>{children}</MobileShell>;
}

// ─── Desktop (≥1024) ────────────────────────────────────────────────────
const SIDEBAR_COLLAPSED_KEY = "bigfm.sidebar.collapsed";  // Phase 19a Part 3

function DesktopShell({ children }) {
  const { pathname } = useLocation();
  // Phase ADMIN.NAV.1 — on /admin/* routes, hide the primary shell
  // Sidebar so the unified AdminSidebar (fixed left:0 220px) is the
  // sole nav rail.  Content area gains a left offset equal to the
  // admin sidebar width for pages that don't render AdminSubNav.
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
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      } catch (_) { /* private mode etc. — ignore */ }
      return next;
    });
  };
  return (
    <div data-testid="shell-desktop"
            data-sidebar-collapsed={collapsed ? "true" : "false"}
            data-admin-route={isAdminRoute ? "true" : "false"}
            className="min-h-screen bg-bg-base text-text-primary font-sans
                            flex flex-col">
      <div className="flex flex-1 overflow-hidden">
        {!isAdminRoute && (
          <Sidebar collapsed={collapsed} onToggle={onToggle} />
        )}
        <div className="flex-1 flex flex-col overflow-hidden"
                    style={isAdminRoute ? { paddingLeft: 220 } : undefined}>
          <TopBar />
          {/* Phase P — responsive horizontal padding scales with viewport
              so ultra-wide monitors (1440+) get breathing room instead of
              edge-to-edge content. Pages retain their own max-w wrappers. */}
          <main className="flex-1 overflow-y-auto px-8 xl:px-12 2xl:px-20
                                  py-6 animate-fade-up pb-32">
            {children}
            <ChannelCategoryFooter />
          </main>
        </div>
      </div>
      <PersistentPlayer />
    </div>
  );
}

function Sidebar({ collapsed, onToggle }) {
  const { pathname } = useLocation();
  const { canCreator, canAdvertiser, canAdmin, canAdReview } = useRoleNav();  // Phase 19a + ADMOD.1
  const w = collapsed ? 64 : 240;
  return (
    <aside
      data-testid="shell-sidebar"
      style={{ width: w }}
      className="shrink-0 border-r border-white/[0.06] bg-bg-elevated
                        flex flex-col transition-[width] duration-200 ease-out150"
    >
      <div className="h-16 flex items-center justify-between px-3 border-b
                            border-white/[0.06]">
        {!collapsed && (
          <div className="font-display font-bold text-lg tracking-display-tight">
            RadioLife<span className="text-accent-electric">.app</span>
          </div>
        )}
        <button
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={onToggle}
          data-testid="sidebar-toggle"
          className="w-8 h-8 grid place-items-center text-text-secondary
                            hover:text-white rounded-token-md hover:bg-white/5
                            transition-colors duration-150"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {PRIMARY_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
        <div className="mt-4 mb-1.5 px-2 text-[10px] font-mono uppercase
                              tracking-widest text-text-secondary">
          {collapsed ? "" : "More"}
        </div>
        {SECONDARY_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
        {/* Phase 19a — role-gated nav sections. */}
        {(canCreator || canAdvertiser || canAdmin || canAdReview) && (
          <div className="mt-4 mb-1.5 px-2 text-[10px] font-mono uppercase
                                          tracking-widest text-text-secondary">
            {collapsed ? "" : "Tools"}
          </div>
        )}
        {canCreator && STUDIO_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
        {canAdvertiser && BIZ_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
        {/* Phase ADMOD.1 — Ad Review section for ad_manager users.
                Admin sees this too (canAdmin implies canAdReview via roleNav). */}
        {canAdReview && !canAdmin && !collapsed && (
          <Link to="/admin/ad-review"
                    data-testid="sidebar-ad-review-section-header"
                    className="mt-4 mb-1.5 px-2 text-[10px] font-mono
                                        uppercase tracking-widest
                                        text-text-secondary hover:text-accent-warm
                                        cursor-pointer block transition-colors
                                        duration-150">
            Ad Review →
          </Link>
        )}
        {canAdReview && AD_MANAGER_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
        {/* Phase 19a Part 4 — clickable Admin section header.  Gives the
            user an obvious way back to /admin from any admin sub-page. */}
        {canAdmin && !collapsed && (
          <Link to="/admin"
                    data-testid="sidebar-admin-section-header"
                    className="mt-4 mb-1.5 px-2 text-[10px] font-mono
                                        uppercase tracking-widest
                                        text-text-secondary hover:text-accent-warm
                                        cursor-pointer block transition-colors
                                        duration-150">
            Admin →
          </Link>
        )}
        {canAdmin && ADMIN_NAV.map((n) => (
          <NavItem key={n.key} {...n} collapsed={collapsed}
                          active={pathname === n.path} />
        ))}
      </nav>
      <div className="border-t border-white/[0.06] p-2">
        <NavItem key="profile" label="Profile" icon={UserIcon}
                      path="/profile" collapsed={collapsed} />
        {!collapsed && (
          <div data-testid="funasia-footer"
               className="px-3 pt-2 text-[10px] text-text-secondary">
            part of{" "}
            <a href="https://funasianetwork.com" target="_blank" rel="noreferrer"
               data-testid="funasia-footer-link"
               className="underline hover:text-white">funasianetwork.com</a>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavItem({ label, icon: Icon, path, collapsed, active }) {
  const slug = (label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return (
    <Link to={path} data-testid={`nav-${slug}`}
            className={[
                "flex items-center gap-3 px-3 h-10 rounded-token-md",
                "transition-colors duration-150 ease-out150",
                active ? "bg-accent-electric/15 text-accent-electric"
                              : "text-text-secondary hover:text-white hover:bg-white/[0.04]",
              ].join(" ")}>
      <Icon size={18} />
      {!collapsed && <span className="font-medium text-sm">{label}</span>}
    </Link>
  );
}

function TopBar() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const onSubmit = (e) => {
    e.preventDefault();
    const v = q.trim();
    if (!v) return;
    navigate(`/search?q=${encodeURIComponent(v)}`);
  };
  return (
    <header data-testid="shell-topbar"
                className="h-16 shrink-0 border-b border-white/[0.06] bg-bg-base
                                px-8 xl:px-12 2xl:px-20 flex items-center gap-4">
      <form onSubmit={onSubmit} role="search"
                className="relative flex-1 max-w-md"
                data-testid="topbar-search-form">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2
                                                    text-text-secondary pointer-events-none" />
        <input
          type="text"
          placeholder="Search stations, shows, games…"
          data-testid="search-input"
          data-shortcut-target="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="w-full pl-9 pr-3 h-10 rounded-full bg-bg-elevated
                            border border-white/[0.06] text-sm focus:outline-none
                            focus:border-accent-electric/40 transition-colors
                            duration-150"
        />
      </form>
      <Chip tone="electric" data-testid="topbar-daypart">
        Lunch Rush · ends 2 PM
      </Chip>
      <CityChip />
      <TryNewLookToggle />
      <button type="button" data-testid="topbar-bell"
                  aria-label="Notifications"
                  className="w-10 h-10 grid place-items-center rounded-full
                                  text-text-secondary hover:text-white
                                  hover:bg-white/5 transition-colors duration-150"
                  style={{ display: "none" }}>
        <Bell size={18} />
      </button>
      <NotificationBell />
      <Link to="/profile" data-testid="topbar-profile"
                className="w-9 h-9 rounded-full bg-gradient-to-br
                                from-accent-electric to-accent-magenta" />
    </header>
  );
}

function PersistentPlayer() {
  return (
    <motion.div
      initial={{ y: 80, opacity: 0 }}
      animate={{ y: 0,  opacity: 1 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      data-testid="persistent-player"
      className="fixed bottom-0 inset-x-0 z-30 px-6 pb-4 pointer-events-none"
    >
      <div className="pointer-events-auto">
        <MiniPlayer />
      </div>
    </motion.div>
  );
}

// Phase R.1 — "Try new look ✨" toggle.  Only visible when authenticated.
function TryNewLookToggle() {
  const { user } = useAuth();
  const variant = useDesignVariantStore((s) => s.variant);
  const toggle = useDesignVariantStore((s) => s.toggle);
  if (!user) return null;
  const active = variant === "radiolife";
  return (
    <button
      type="button"
      onClick={toggle}
      data-testid="try-new-look-toggle"
      aria-pressed={active}
      title={active ? "Switch back to the classic RadioLife design"
                          : "Try the new RadioLife design"}
      className={[
        "h-9 px-3 rounded-full border text-[11px] font-semibold uppercase",
        "tracking-widest transition-all duration-150",
        "flex items-center gap-1.5 whitespace-nowrap",
        active
          ? "text-white border-transparent shadow-md shadow-pink-500/30"
          : "text-text-secondary border-white/[0.08] hover:text-white hover:border-white/20 hover:bg-white/5",
      ].join(" ")}
      style={active ? { background: "linear-gradient(135deg, #A020F0, #EC4899)" } : undefined}>
      <Sparkles size={12} />
      {active ? "RadioLife ON" : "Try new look"}
    </button>
  );
}

// ─── Tablet (768–1023) ──────────────────────────────────────────────────
function TabletShell({ children }) {
  return (
    <div data-testid="shell-tablet"
            className="min-h-screen bg-bg-base text-text-primary font-sans">
      <div className="flex">
        <aside data-testid="shell-iconrail"
                    className="w-16 border-r border-white/[0.06] bg-bg-elevated
                                    min-h-screen flex flex-col items-center py-4 gap-2">
          {[...PRIMARY_NAV, ...SECONDARY_NAV].map((n) => (
            <IconRailItem key={n.key} {...n} />
          ))}
        </aside>
        <main className="flex-1 px-6 py-5 pb-28 animate-fade-up">
          {children}
          <ChannelCategoryFooter />
        </main>
      </div>
      <PersistentPlayer />
    </div>
  );
}

function IconRailItem({ icon: Icon, label, path }) {
  const { pathname } = useLocation();
  const active = pathname === path;
  return (
    <Link to={path} aria-label={label}
            data-testid={`rail-${label.toLowerCase()}`}
            className={[
                "w-10 h-10 grid place-items-center rounded-token-md",
                "transition-colors duration-150 ease-out150",
                active ? "bg-accent-electric/15 text-accent-electric"
                              : "text-text-secondary hover:text-white hover:bg-white/[0.04]",
              ].join(" ")}>
      <Icon size={18} />
    </Link>
  );
}

// ─── Mobile (<768) ──────────────────────────────────────────────────────
function MobileShell({ children }) {
  const [overflow, setOverflow] = useState(false);
  return (
    <div data-testid="shell-mobile"
            className="min-h-screen bg-bg-base text-text-primary font-sans
                            pb-40">
      {/* Phase R.1 — floating toggle on mobile too (mobile has no TopBar) */}
      <div className="fixed top-3 right-3 z-30">
        <TryNewLookToggle />
      </div>
      <main className="px-4 py-4 animate-fade-up">
        {children}
        <ChannelCategoryFooter />
      </main>
      <div className="fixed bottom-20 inset-x-0 z-30 px-3">
        <MobilePremiumStrip />
        <div className="mt-1.5">
          <MiniPlayer />
        </div>
      </div>
      <nav data-testid="shell-bottom-tabs"
              className="fixed bottom-0 inset-x-0 h-16 z-40
                              bg-bg-elevated/95 backdrop-blur-glass
                              border-t border-white/[0.06]
                              grid grid-cols-6 items-center px-1">
        {MOBILE_TABS.map((t) => <BottomTab key={t.key} {...t} />)}
        <button
          type="button"
          data-testid="bottom-tab-more"
          aria-label="More"
          onClick={() => setOverflow((v) => !v)}
          className="flex flex-col items-center justify-center h-full gap-0.5
                            text-text-secondary hover:text-white"
        >
          <MoreHorizontal size={20} />
          <span className="text-[10px] font-medium">More</span>
        </button>
      </nav>
      <AnimatePresence>
        {overflow && (
          <motion.div
            initial={{ y: 200, opacity: 0 }}
            animate={{ y: 0,   opacity: 1 }}
            exit={{    y: 200, opacity: 0 }}
            transition={{ duration: 0.2 }}
            data-testid="mobile-overflow-drawer"
            className="fixed bottom-16 inset-x-0 z-50 bg-bg-elevated/95
                              backdrop-blur-glass border-t border-white/[0.06]
                              p-4 grid grid-cols-4 gap-2"
          >
            {SECONDARY_NAV.concat([{ key: "profile", label: "Profile",
                                                      icon: UserIcon, path: "/profile" }])
                                  .map((n) => (
              <Link key={n.key} to={n.path}
                        onClick={() => setOverflow(false)}
                        data-testid={`overflow-${n.label.toLowerCase()}`}
                        className="flex flex-col items-center gap-1 py-2
                                          rounded-token-md hover:bg-white/5
                                          text-text-secondary hover:text-white
                                          transition-colors duration-150">
                <n.icon size={20} />
                <span className="text-[11px] font-medium">{n.label}</span>
              </Link>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function BottomTab({ label, icon: Icon, path }) {
  const { pathname } = useLocation();
  const active = pathname === path;
  return (
    <Link to={path}
            data-testid={`tab-${label.toLowerCase()}`}
            className={[
                "flex flex-col items-center justify-center h-full gap-0.5",
                active ? "text-accent-electric"
                              : "text-text-secondary",
              ].join(" ")}>
      <Icon size={20} />
      <span className="text-[10px] font-medium">{label}</span>
    </Link>
  );
}

