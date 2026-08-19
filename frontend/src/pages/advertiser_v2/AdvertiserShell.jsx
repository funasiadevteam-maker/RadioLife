// Phase AD.1 — Advertiser dashboard shell (mimics MerchantShell pattern).
// Left sidebar + <Outlet /> for nested pages.  Auth-gated + tolerant of the
// "no advertiser yet" state (redirects to /advertiser/apply).

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Link, Outlet, NavLink, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import {
  LayoutDashboard, Megaphone, Wallet, BarChart3, Settings, LogOut,
  ChevronRight, Loader2, Menu, X, AlertTriangle, Gamepad2,
  Users, ScanLine, Ticket, Image as ImageIcon, BellRing, Trophy, Flame, Headphones,
  Sparkles, Radio, MapPin, Store, Target,
  Search, KeyRound, Rocket,
} from "lucide-react";

import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const AdvertiserCtx = createContext(null);
export const useAdvertiser = () => useContext(AdvertiserCtx);

const NAV = [
  { path: "/advertiser/dashboard/overview",              label: "Overview",              Icon: LayoutDashboard },
  { path: "/advertiser/dashboard/campaigns",            label: "Campaigns",            Icon: Megaphone },
  { path: "/advertiser/dashboard/banner-campaigns", label: "Banner Campaigns", Icon: ImageIcon, testid: "advertiser-nav-banner-campaigns" },
  { path: "/advertiser/dashboard/notification-campaigns", label: "Notification Campaigns", Icon: BellRing },
  { path: "/advertiser/dashboard/predict-win-sponsorships", label: "Predict & Win Sponsorships", Icon: Trophy },
  { path: "/advertiser/dashboard/flagship-boosts", label: "Flagship Boosts", Icon: Flame },
  { path: "/advertiser/dashboard/podcast-completion", label: "Podcast Completion", Icon: Headphones },
  { path: "/advertiser/dashboard/trivia-sponsorships", label: "Trivia Sponsorships", Icon: Sparkles },
  { path: "/advertiser/dashboard/rj-sponsored-reads", label: "AI-RJ Reads", Icon: Radio },
  { path: "/advertiser/dashboard/location-boosts", label: "Location Boosts", Icon: MapPin },
  { path: "/advertiser/dashboard/marketplace-slots", label: "Marketplace Slots", Icon: Store },
  { path: "/advertiser/dashboard/takeover-hours", label: "Takeover Hours", Icon: Radio, testid: "advertiser-nav-takeover-hours" },
  { path: "/advertiser/dashboard/retargeting", label: "Retargeting", Icon: Target, testid: "advertiser-nav-retargeting" },
  { path: "/advertiser/dashboard/sponsored-games", label: "Sponsored games", Icon: Gamepad2 },
  { path: "/advertiser/dashboard/coupon-campaigns", label: "Coupon campaigns", Icon: Ticket },
  { path: "/advertiser/dashboard/scan",                        label: "Scan / Redeem",  Icon: ScanLine, requires: "can_redeem" },
  { path: "/advertiser/dashboard/staff",                      label: "Staff",                    Icon: Users,      requires: "can_invite_staff" },
  { path: "/advertiser/dashboard/budget",                    label: "Budget",                    Icon: Wallet },
  { path: "/advertiser/dashboard/auction-insights", label: "Auction Insights", Icon: Search },
  { path: "/advertiser/dashboard/analytics",              label: "Analytics",              Icon: BarChart3 },
  { path: "/advertiser/dashboard/profile",                    label: "Profile",                    Icon: Settings },
  { path: "/advertiser/dashboard/api",                        label: "API & Keys",            Icon: KeyRound, testid: "advertiser-nav-api" },
  { path: "/advertiser/dashboard/api-checkout",              label: "API Checkout",          Icon: Rocket, testid: "advertiser-nav-api-checkout" },
];

export default function AdvertiserShell() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading, logout } = useAuth();
  const navigate = useNavigate();
  const [search] = useSearchParams();

  const [advertisers, setAdvertisers] = useState([]);
  const [roleByAdvertiser, setRoleByAdvertiser] = useState({});    // AD.6 — {adv_id: role}
  const [activeId, setActiveId] = useState(search.get("advertiser_id") || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login?next=/advertiser/dashboard/overview"); return; }
    (async () => {
      try {
        const [{ data: mine }, rolesResp] = await Promise.all([
          axios.get(`${API}/ad1/advertiser/mine`),
          // AD.6 — fetch effective role for each advertiser (staff visibility)
          axios.get(`${API}/advertiser-app/me/roles`).catch(() => ({ data: { items: [] } })),
        ]);
        const merged = [...(mine.items || [])];
        // Add advertisers where user is staff-only (not owner) so they can access the app.
        const staffOnly = (rolesResp.data.items || [])
          .filter((r) => !merged.some((m) => m.advertiser_id === r.advertiser_id));
        merged.push(...staffOnly.map((r) => ({
          advertiser_id: r.advertiser_id, name: r.name,
          status: r.status, logo_url: r.logo_url, is_staff_only: true,
        })));
        setAdvertisers(merged);
        const roleMap = {};
        for (const r of (rolesResp.data.items || [])) {
          if (r.role) roleMap[r.advertiser_id] = r.role;
        }
        setRoleByAdvertiser(roleMap);
        if (merged.length === 0) {
          navigate("/advertiser/apply");
          return;
        }
        if (!activeId && merged.length > 0) {
          setActiveId(merged[0].advertiser_id);
        }
      } catch (err) {
        setError(err?.response?.data?.detail?.code || err.message);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, authLoading]);

  const active = useMemo(
    () => (advertisers || []).find((a) => a.advertiser_id === activeId) || null,
    [advertisers, activeId]);

  if (authLoading || loading) {
    return (
      <div className={`${light ? "bg-white" : "bg-slate-950"} min-h-screen flex items-center justify-center`}
                data-testid="advertiser-shell-loading">
        <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
      </div>
    );
  }
  if (error) {
    return (
      <div className={`${light ? "bg-white text-slate-900" : "bg-slate-950 text-white"} min-h-screen p-8`}
                data-testid="advertiser-shell-error">
        <div className="max-w-md mx-auto text-center mt-16">
          <AlertTriangle className="w-10 h-10 mx-auto text-amber-500" />
          <h2 className="text-xl font-bold mt-3">Something went wrong</h2>
          <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>{error}</p>
        </div>
      </div>
    );
  }
  if (!active) return null;

  const activeRole = roleByAdvertiser[active.advertiser_id] || (
    active.is_staff_only ? null :   // fallback below
    (active.owner_user_id === user.user_id ? "owner" : null));
  // Permission set derived from role — mirrors backend ROLE_PERMISSIONS.
  const permissions = new Set();
  if (activeRole === "owner" || activeRole === "admin" || activeRole === "manager") {
    ["can_invite_staff","can_edit_profile","can_redeem","can_view_analytics",
      "can_view_scan_history","can_manage_campaigns"].forEach((p) => permissions.add(p));
  } else if (activeRole === "redemption_staff") {
    ["can_redeem","can_view_scan_history"].forEach((p) => permissions.add(p));
  } else if (activeRole === "analytics_only") {
    permissions.add("can_view_analytics");
  } else {
    // fallback: assume owner for legacy (no /me/roles hit)
    ["can_invite_staff","can_edit_profile","can_redeem","can_view_analytics",
      "can_view_scan_history","can_manage_campaigns"].forEach((p) => permissions.add(p));
  }
  const visibleNav = NAV.filter((n) => !n.requires || permissions.has(n.requires));

  const contextValue = { advertisers, active, activeRole, permissions,
                                                setActiveId, refresh: () => window.location.reload() };

  return (
    <AdvertiserCtx.Provider value={contextValue}>
      <div className={`${light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white"} min-h-screen`}
                data-testid="advertiser-shell">
        <div className="lg:flex">
          {/* Sidebar */}
          <aside className={`${light ? "bg-white border-r border-slate-200" :
                                                                    "bg-slate-900 border-r border-slate-800"} 
                                        w-60 hidden lg:flex flex-col fixed inset-y-0 left-0 z-30`}
                          data-testid="advertiser-shell-sidebar">
            <div className="px-6 py-5 border-b border-inherit">
              <div className="text-xs uppercase tracking-widest font-mono text-amber-500">RadioLife Ads</div>
              <div className="font-bold text-lg mt-1 truncate" data-testid="advertiser-shell-name">
                {active.name}
              </div>
              <StatusPill status={active.status} />
            </div>
            <nav className="flex-1 py-3 px-2">
              {visibleNav.map(({ path, label, Icon, testid }) => (
                <NavLink key={path} to={path}
                                data-testid={testid || `advertiser-nav-${label.toLowerCase().replace(/[^a-z0-9]+/g,'-')}`}
                                className={({ isActive }) => `flex items-center gap-3 px-4 py-2 rounded-lg text-sm font-medium mb-0.5 transition
                                  focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 ${light ? "focus-visible:ring-offset-white" : "focus-visible:ring-offset-slate-900"} ${
                                  isActive
                                    ? "bg-amber-500/15 text-amber-500"
                                    : light ? "text-slate-700 hover:bg-slate-100"
                                                    : "text-slate-300 hover:bg-slate-800"
                                }`}>
                  <Icon className="w-4 h-4" /> {label}
                </NavLink>
              ))}
            </nav>
            <button onClick={logout}
                            data-testid="advertiser-shell-logout"
                            className={`m-3 px-4 py-2 rounded-lg text-sm inline-flex items-center gap-2 transition
                                        focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                                light ? "text-slate-600 hover:bg-slate-100" : "text-slate-400 hover:bg-slate-800"
                            }`}>
              <LogOut className="w-4 h-4" /> Sign out
            </button>
          </aside>

          {/* Mobile top bar */}
          <div className={`lg:hidden sticky top-0 z-40 ${
                                light ? "bg-white border-b border-slate-200" :
                                              "bg-slate-900 border-b border-slate-800"
                              } px-4 py-3 flex items-center justify-between`}>
            <div>
              <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">RadioLife Ads</div>
              <div className="font-bold text-sm">{active.name}</div>
            </div>
            <button onClick={() => setMobileOpen(!mobileOpen)}
                            data-testid="advertiser-shell-mobile-menu"
                            className="p-2 rounded-lg hover:bg-slate-800/20">
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
          {mobileOpen && (
            <div className={`lg:hidden ${light ? "bg-white" : "bg-slate-900"} px-4 py-3`}
                        data-testid="advertiser-shell-mobile-nav">
              {visibleNav.map(({ path, label, Icon, testid }) => (
                <NavLink key={path} to={path} onClick={() => setMobileOpen(false)}
                                data-testid={testid ? `${testid}-mobile` : `advertiser-nav-mobile-${label.toLowerCase().replace(/[^a-z0-9]+/g,'-')}`}
                                className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm ${
                                  isActive ? "bg-amber-500/15 text-amber-500" :
                                                        (light ? "text-slate-700" : "text-slate-300")
                                }`}>
                  <Icon className="w-4 h-4" /> {label}
                </NavLink>
              ))}
            </div>
          )}

          {/* Main content — Phase P: widened for desktop (1440+) */}
          <main className="lg:ml-60 flex-1 min-h-screen">
            <div className="max-w-7xl xl:max-w-[1400px] mx-auto p-6 sm:p-8 xl:p-10">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </AdvertiserCtx.Provider>
  );
}

function StatusPill({ status }) {
  const map = {
    draft:                        { text: "Draft",                                bg: "bg-slate-500/15 text-slate-400" },
    pending_approval:  { text: "Pending admin approval", bg: "bg-amber-500/15 text-amber-500" },
    active:                      { text: "Active",                              bg: "bg-emerald-500/15 text-emerald-500" },
    suspended:              { text: "Suspended",                    bg: "bg-red-500/15 text-red-400" },
    rejected:                  { text: "Rejected",                        bg: "bg-red-500/15 text-red-400" },
  };
  const p = map[status] || map.draft;
  return (
    <div className={`mt-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${p.bg}`}
                data-testid={`advertiser-status-${status}`}>
      {p.text}
    </div>
  );
}
