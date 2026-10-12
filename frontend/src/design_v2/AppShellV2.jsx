// New Look V2 shell — premium dark cinematic chrome (integrated top nav +
// sticky player dock). Reuses the existing audio engine (MiniPlayer +
// GlobalAudio), companion, notifications and variant switcher. Only the
// visual composition is new. Bare/marketing/admin routes render untouched.
import React, { useEffect, useState, useRef, useCallback } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Home, Headphones, ShoppingBag, Gamepad2, Users, Coins, ChevronDown,
  CreditCard, Move, PanelTop, PanelBottom, PanelLeft, PanelRight,
  PictureInPicture2, Radio,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { usePlayerDock, DOCK_OPTIONS } from "@/shell/usePlayerDock";
import { useThemeStore } from "@/theme/useTheme";
import { useGeoStore } from "@/store/useGeoStore";
import { useShellSummary } from "@/shell/useShellData";
import PlayerBarV2 from "./PlayerBarV2";
import OnAirOfferCard from "@/shell/OnAirOfferCard";
import VariantSwitcher from "@/shell/VariantSwitcher";  // eslint-disable-line no-unused-vars -- moved to /admin/appearance
import NotificationBell from "@/components/NotificationBell";
import CityChip from "@/components/CityChip";
import NewCityPrompt from "@/components/NewCityPrompt";
import WorkspaceSwitcher from "@/components/portal/WorkspaceSwitcher";
// VariantSwitcher moved to the admin backend (/admin/appearance).
import BannerAdSlot from "@/components/BannerAdSlot";
import PlayerSwitchToast from "@/components/PlayerSwitchToast";
import SleepTimerEngine from "@/components/SleepTimerEngine";
import InterestOnboarding from "./InterestOnboarding";
import FeatureOnboarding from "@/components/FeatureOnboarding";
import { useFeaturePrefs } from "@/store/useFeaturePrefs";
import { useHomeView } from "@/store/useHomeView";
import SocialFeedShell from "./socialfeed/SocialFeedShell";
import HomeViewSwitcher from "./socialfeed/HomeViewSwitcher";
import { isMarketingPath } from "@/shell/AppShellB";
import { useLaunchBlocked } from "@/hooks/useLaunchStatus";
import "./newlookv2.css";

// One shared frame width for the whole V2 surface — header, page content
// and player dock all align to these exact left/right edges so every tab
// looks identical (fixes the "one screen left, one centered" mismatch).
const CONTAINER = "max-w-[1440px] mx-auto w-full px-4 sm:px-6 xl:px-10";

function railPageRoute(pathname) {
  if (pathname === "/") return "/home";
  if (pathname.startsWith("/social")) return "/social";
  if (pathname.startsWith("/listen")) return "/channels";
  if (pathname.startsWith("/shop")) return "/shop";
  if (pathname.startsWith("/play")) return "/play";
  if (pathname.startsWith("/community")) return "/community";
  return "/home";
}

const BARE_ROUTES = [
  /^\/login(\b|\/)/, /^\/onboarding(\b|\/)/, /^\/auth(\b|\/)/,
  /^\/portal(\b|\/)/,
  /^\/dev\/styleguide(\b|\/)/, /^\/tv(\b|\/)/,
];

const NAV = [
  { key: "home", label: "Home", icon: Home, path: "/" },
  { key: "social", label: "Social", icon: Users, path: "/social" },
  { key: "listen", label: "Listen", icon: Headphones, path: "/listen" },
  { key: "shop", label: "Shop", icon: ShoppingBag, path: "/shop" },
  { key: "play", label: "Play", icon: Gamepad2, path: "/play-and-win" },
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
  const { dock } = usePlayerDock();
  const launchBlocked = useLaunchBlocked();
  const bare = BARE_ROUTES.some((r) => r.test(pathname))
    || isMarketingPath(pathname)
    || (pathname === "/" && !user)
    || launchBlocked;
  const isAdmin = pathname.startsWith("/admin");

  const hydrateTheme = useThemeStore((s) => s.hydrate);
  const bootstrapGeo = useGeoStore((s) => s.bootstrap);
  const geoReady = useGeoStore((s) => s.ready);
  const bootstrapFeatures = useFeaturePrefs((s) => s.bootstrap);
  const featLoaded = useFeaturePrefs((s) => s.loaded);
  useEffect(() => { hydrateTheme(); }, [hydrateTheme]);
  useEffect(() => { if (!geoReady) bootstrapGeo(); }, [geoReady, bootstrapGeo]);
  useEffect(() => { if (user && !featLoaded) bootstrapFeatures(); },
    [user, featLoaded, bootstrapFeatures]);
  const homeView = useHomeView((s) => s.homeView);
  const bootstrapHomeView = useHomeView((s) => s.bootstrap);
  const hvLoaded = useHomeView((s) => s.loaded);
  useEffect(() => { if (user && !hvLoaded) bootstrapHomeView(); },
    [user, hvLoaded, bootstrapHomeView]);
  const socialFeedActive = !!user && (homeView === "v2" || homeView === "v3");

  // Admin routes render their own content but must clear the fixed
  // AdminSidebar (220px). Offset only on lg+ where the rail is visible.
  if (isAdmin) {
    return (
      <div className="lg:pl-[220px]" data-testid="admin-shell-offset">
        {children}
      </div>
    );
  }
  if (bare) return <>{children}</>;

  // Social Feed view (V2 light / V3 dark) — a Facebook-style activity wall
  // that replaces the cinematic V2 chrome with its own themed shell across
  // every in-app route. Classic "New Look V2" stays reachable via the
  // header view-switcher (sets homeView back to v1).
  if (socialFeedActive) {
    return (
      <SocialFeedShell>
        {children}
        {user && <InterestOnboarding />}
        {user && <FeatureOnboarding />}
        <PlayerSwitchToast />
        <SleepTimerEngine />
      </SocialFeedShell>
    );
  }

  // Desktop-only bottom clearance adapts to the player dock position so the
  // player never covers content. Mobile keeps its native full-width dock.
  const dockMainLg = {
    bottom: "lg:pb-40", top: "lg:pt-32 lg:pb-10",
    left: "lg:pb-20", right: "lg:pb-20", float: "lg:pb-20",
  }[dock] || "lg:pb-40";

  return (
    <div data-testid="shell-v2" className="nlv2 flex flex-col">
      <ShellV2Header />
      <NewCityPrompt />
      <main className={`flex-1 pt-6 pb-52 ${dockMainLg}`}>
        <div className={`${CONTAINER} flex gap-6 xl:gap-8 items-start`}>
          <div className="flex-1 min-w-0">{children}</div>
          <RightRailV2 />
        </div>
      </main>
      <PlayerDockV2 dock={dock} />
      <BottomNavV2 />
      {user && <InterestOnboarding />}
      {user && <FeatureOnboarding />}
      <PlayerSwitchToast />
      <SleepTimerEngine />
    </div>
  );
}

function ShellV2Header() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const summary = useShellSummary();
  const enabledFeatures = useFeaturePrefs((s) => s.enabled);
  const navShow = (k) => k === "home" || !enabledFeatures || enabledFeatures.includes(k);
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
        <span className="font-black text-lg tracking-tight nlv2-grad">
          FUUSIC
        </span>
        <span className="hidden lg:block text-[9.5px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>
          Listen · Connect · Play · Shop · Earn
        </span>
      </Link>

      {/* Center nav — desktop only. Mobile uses the bottom tab bar. */}
      <nav className="hidden lg:flex flex-1 items-center justify-center gap-1 sm:gap-2 overflow-x-auto nlv2-scroll">
        {NAV.filter(({ key }) => navShow(key)).map(({ key, label, icon: Icon, path }) => {
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
        <span className="hidden sm:block"><CityChip /></span>
        <Link to="/social" data-testid="nlv2-top-social" title="Social"
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
        <span className="hidden sm:block"><HomeViewSwitcher /></span>
        <WorkspaceSwitcher compact />
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

const RAIL_BADGE_TONE = {
  LIVE: "#ef4444", SOON: "#22d3ee", SUGGESTED: "#a855f7",
  "TUNE IN": "#38bdf8", SPONSORED: "#f5c563",
};

function RailCompactCard({ card, idx, track }) {
  const navigate = useNavigate();
  const [followed, setFollowed] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);
  const seen = useRef(false);
  const tone = RAIL_BADGE_TONE[card.badge] || "#a855f7";
  const isFollow = card.kind === "follow";
  const isLive = card.kind === "live";
  const isSponsored = card.kind === "sponsored";

  // Fire one impression when the card first scrolls into view.
  useEffect(() => {
    const el = ref.current;
    if (!el || !track || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting && !seen.current) {
          seen.current = true;
          track({ card_id: card.id, kind: card.kind, action: "impression",
                  sponsorship_id: card.sponsorship_id });
          obs.disconnect();
        }
      });
    }, { threshold: 0.5 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [card.id, card.kind, card.sponsorship_id, track]);

  const fireClick = () => track && track({ card_id: card.id, kind: card.kind,
    action: "click", sponsorship_id: card.sponsorship_id });
  const open = () => { fireClick(); if (card.to) navigate(card.to); };
  const onFollow = async (e) => {
    e.stopPropagation();
    if (busy || followed) return;
    fireClick();
    setBusy(true);
    try {
      await axios.post(`${API}/social/follow/${card.follow_id}`, {}, { withCredentials: true });
      setFollowed(true);
    } catch (_) { /* silent */ } finally { setBusy(false); }
  };

  return (
    <div ref={ref} data-testid={`nlv2-railside-card-${idx}`} data-rail-kind={card.kind}
      onClick={isFollow ? undefined : open}
      className={`nlv2-glass rounded-2xl p-2.5 flex items-center gap-2.5 transition ${isFollow ? "" : "cursor-pointer hover:brightness-110"}`}
      style={isSponsored ? { boxShadow: "inset 0 0 0 1.5px rgba(245,197,99,0.55)" } : undefined}>
      <div className="relative w-11 h-11 rounded-xl overflow-hidden shrink-0 grid place-items-center"
        style={{ background: "rgba(255,255,255,0.05)" }}>
        {card.image
          ? <img src={card.image} alt="" className="w-full h-full object-cover" />
          : <Radio size={16} className="text-[#8b96b8]" />}
        {isLive && (
          <span className="absolute inset-0 ring-2 ring-red-500/70 rounded-xl pointer-events-none" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <span className="inline-block text-[8px] font-black tracking-widest px-1.5 py-0.5 rounded-full"
          style={{ background: `${tone}22`, color: tone }}>{card.badge}</span>
        <div className="text-[13px] font-bold truncate mt-0.5">{card.title}</div>
        <div className="text-[10.5px] truncate" style={{ color: "#8b96b8" }}>{card.subtitle}</div>
        {card.hint && (
          <div className="text-[9.5px] font-bold mt-0.5" style={{ color: "#a855f7" }}
            data-testid={`nlv2-railside-hint-${idx}`}>{card.hint}</div>
        )}
      </div>
      {isFollow ? (
        <button type="button" data-testid={`nlv2-railside-follow-${idx}`}
          onClick={onFollow} disabled={busy || followed}
          className="text-[11px] font-black px-3 h-8 rounded-full text-white shrink-0 disabled:opacity-70"
          style={{ background: followed ? "rgba(255,255,255,0.1)" : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {followed ? "Following" : "Follow"}
        </button>
      ) : (
        <button type="button" data-testid={`nlv2-railside-cta-${idx}`} onClick={open}
          className="text-[11px] font-black px-3 h-8 rounded-full text-white shrink-0"
          style={isSponsored
            ? { background: "linear-gradient(135deg,#f5c563,#f59e0b)", color: "#1a1200" }
            : { background: "rgba(255,255,255,0.08)" }}>{card.cta}</button>
      )}
    </div>
  );
}

function RightRailV2() {
  const { pathname } = useLocation();
  const summary = useShellSummary();
  const isPremium = !!summary?.is_premium;
  const pageRoute = railPageRoute(pathname);
  const [cards, setCards] = useState([]);
  const queue = useRef([]);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/social/rail`, { params: { page_route: pageRoute, limit: 7 }, withCredentials: true })
      .then((r) => { if (!cancel) setCards(r.data?.cards || []); })
      .catch(() => { if (!cancel) setCards([]); });
    return () => { cancel = true; };
  }, [pageRoute]);

  const track = useCallback((ev) => {
    queue.current.push({ ...ev, page_route: pageRoute });
  }, [pageRoute]);

  const flush = useCallback(() => {
    if (!queue.current.length) return;
    const events = queue.current.splice(0, queue.current.length);
    axios.post(`${API}/social/rail/event`, { events }, { withCredentials: true })
      .catch(() => {});
  }, []);

  // Batch-flush analytics every 5s and on unmount / route change.
  useEffect(() => {
    const id = setInterval(flush, 5000);
    return () => { clearInterval(id); flush(); };
  }, [flush, pageRoute]);

  const shown = cards.slice(0, isPremium ? 6 : 5);

  return (
    <aside data-testid="nlv2-right-rail"
      className="hidden xl:flex flex-col gap-3 w-[300px] shrink-0 sticky top-[84px]">
      {!isPremium && (
        <>
          <div className="text-[10px] font-mono uppercase tracking-widest px-1" style={{ color: "#6b7392" }}>
            Sponsored
          </div>
          <div data-testid="nlv2-rail-ad-1" className="nlv2-glass rounded-2xl p-2 flex justify-center">
            <BannerAdSlot slotKey="right_rail_mpu_1" pageRoute={pageRoute} />
          </div>
        </>
      )}

      {shown.length > 0 && (
        <>
          <div className="text-[10px] font-mono uppercase tracking-widest px-1" style={{ color: "#6b7392" }}>
            For You
          </div>
          {shown.map((c, i) => <RailCompactCard key={c.id} card={c} idx={i} track={track} />)}
        </>
      )}

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
            ? "Enjoy 6 skips per rolling hour and zero ads across FUUSIC."
            : "Premium removes ads and unlocks 6 skips per rolling hour."}
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
  const enabledFeatures = useFeaturePrefs((s) => s.enabled);
  const navShow = (k) => k === "home" || k === "pay" || !enabledFeatures || enabledFeatures.includes(k);
  const isActive = (path) => (path === "/" ? pathname === "/" : pathname.startsWith(path));
  return (
    <nav data-testid="nlv2-bottom-nav"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 nlv2-glass-strong border-t border-white/5"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      <div className="flex items-stretch justify-around h-16 px-2">
        {MOBILE_NAV.filter(({ key }) => navShow(key)).map(({ key, label, icon: Icon, path, center }) => {
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

const DOCK_META_V2 = {
  bottom: { icon: PanelBottom, label: "Bottom" },
  top: { icon: PanelTop, label: "Top" },
  left: { icon: PanelLeft, label: "Left" },
  right: { icon: PanelRight, label: "Right" },
  float: { icon: PictureInPicture2, label: "Float" },
};

// Desktop-only control (hidden < lg) to move / float the player.
function PlayerDockMenu() {
  const { dock, setDock } = usePlayerDock();
  const [open, setOpen] = useState(false);
  return (
    <div className="hidden lg:block absolute -top-3 right-4 z-10">
      <button type="button" onClick={() => setOpen((v) => !v)} data-testid="player-dock-toggle"
        className="inline-flex items-center gap-1 h-7 px-2.5 rounded-full text-[11px] font-bold bg-black/70 border border-white/15 text-white/80 hover:text-white shadow-lg backdrop-blur">
        <Move size={12} /> Move
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-0" onClick={() => setOpen(false)} />
          <div className={`absolute ${dock === "top" ? "top-9" : "bottom-9"} right-0 z-10 w-40 rounded-xl bg-[#12101f] border border-white/12 shadow-2xl p-1`} data-testid="player-dock-menu">
            {DOCK_OPTIONS.map((opt) => {
              const M = DOCK_META_V2[opt]; const Icon = M.icon; const active = dock === opt;
              return (
                <button key={opt} type="button" data-testid={`player-dock-${opt}`}
                  onClick={() => { setDock(opt); setOpen(false); }}
                  className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-bold ${active ? "bg-amber-400/15 text-amber-300" : "text-white/70 hover:bg-white/5"}`}>
                  <Icon size={14} /> {M.label}{active && <span className="ml-auto text-[9px]">✓</span>}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function PlayerDockV2({ dock = "bottom" }) {
  // <lg: always the full-width dock above the bottom nav (mobile native).
  // lg+: honor the user's chosen dock position.
  const deskPos = {
    bottom: "lg:top-auto lg:bottom-0 lg:left-0 lg:right-0 lg:px-6 lg:pb-4",
    top: "lg:top-16 lg:bottom-auto lg:left-0 lg:right-0 lg:px-6 lg:pt-2",
    left: "lg:top-auto lg:bottom-4 lg:left-4 lg:right-auto lg:w-[460px] lg:px-0",
    right: "lg:top-auto lg:bottom-4 lg:right-4 lg:left-auto lg:w-[460px] lg:px-0",
    float: "lg:top-auto lg:bottom-6 lg:right-6 lg:left-auto lg:w-[420px] lg:px-0",
  }[dock] || "lg:top-auto lg:bottom-0 lg:left-0 lg:right-0 lg:px-6 lg:pb-4";
  const wide = dock === "bottom" || dock === "top";
  return (
    <div data-testid="nlv2-player-dock" data-dock={dock}
      className={`fixed bottom-16 inset-x-0 z-30 px-3 sm:px-6 pb-2 pointer-events-none ${deskPos}`}>
      <div className={`pointer-events-auto relative mx-auto ${wide ? "max-w-[1440px]" : "max-w-[1440px] lg:max-w-none"}`}>
        <PlayerDockMenu />
        <OnAirOfferCard />
        <PlayerBarV2 />
      </div>
    </div>
  );
}
