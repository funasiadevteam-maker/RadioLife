// Phase T (2026-07-28) — Admin sidebar restructured into 5 logical
// super-groups (Home & Analytics / Ad Monetization / Content /
// Users & Businesses / System) with a new "★ Pinned" section at the
// top backed by the per-admin nav-pins endpoints
// (GET/POST/DELETE /api/admin/nav/pin[s]).
//
// Preserved from earlier phases:
//   • All item testids (`adnav-…`) so existing tests still pass.
//   • Badge polling via `GET /api/admin/nav-counts` (60s, pause when
//     tab hidden).
//   • ad_manager role scoping (limited to Home & Ad Monetization).
//   • ADMIN_SIDEBAR_WIDTH export for AppShell offsetting.
//   • Return-home CTA + Admin Console header.
//
// New in Phase T:
//   • Pinned section (loaded on mount + reloaded via
//     `bigfm:admin-pins-changed` window event dispatched by
//     AdminPageHeader when the user pins/unpins).
//   • Sidebar-level Search trigger dispatches
//     `bigfm:admin-search-open` (handled by AdminGlobalSearch).
//   • Group open/closed state persisted per super-group in
//     `bigfm_admin_nav_expanded` (backwards-compatible key).
import { useState, useEffect, useMemo, useCallback } from "react";
import { Link, useLocation } from "react-router-dom";
import axios from "axios";
import { useAuth } from "@/AuthContext";
import {
  ChevronRight, LayoutDashboard, Users, Megaphone, Sparkles,
  Settings, ArrowLeft, ShieldCheck, Star, Search, X,
} from "lucide-react";


const LS_KEY = "bigfm_admin_nav_expanded";
const NAV_COUNTS_POLL_MS = 60_000;
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

// ─── Item testid → nav_counts key mapping ──────────────────────
const BADGE_TESTID_MAP = {
  "adnav-ads-review":              "ad_review_pending",
  "adnav-ads-cqueue":              "banner_reviews_pending",
  "adnav-ads-aqueue":              "banner_reviews_pending",
  "adnav-merchants-list":     "merchant_applications_pending",
  "adnav-merchants-refunds": "refunds_pending",
  "adnav-radio-claims":         "station_claims_pending",
  "adnav-podcasts-apps":       "podcast_apps_pending",
};

// ─── 5 super-group hierarchy (Phase T) ─────────────────────
const SECTIONS = [
  {
    key: "home-analytics",
    label: "Home & Analytics",
    icon: LayoutDashboard,
    items: [
      { to: "/admin",                     label: "Admin Home",       testid: "adnav-overview-home" },
      { to: "/admin/qa",                 label: "QA Dashboard",    testid: "adnav-overview-qa" },
      { to: "/admin/health",         label: "System Health",    testid: "adnav-overview-health" },
      { to: "/admin/revenue/live", label: "Revenue (Live)",   testid: "adnav-overview-revenue-live" },
      { to: "/admin/analytics",     label: "Analytics",             testid: "adnav-ops-analytics" },
      { to: "/admin/retention",     label: "Retention",             testid: "adnav-ops-retention" },
      { to: "/admin/location-intel", label: "Location Intel", testid: "adnav-cq-loc-intel" },
    ],
  },
  {
    key: "ad-monetization",
    label: "Ad Monetization",
    icon: Megaphone,
    items: [
      { to: "/admin/ad-review",                    label: "Ad Review Queue",       testid: "adnav-ads-review" },
      { to: "/admin/campaigns/queue",          label: "Campaigns Queue",       testid: "adnav-ads-cqueue" },
      { to: "/admin/advertiser/campaigns",  label: "Advertiser Queue",       testid: "adnav-ads-aqueue" },
      { to: "/admin/advertiser/analytics",  label: "Advertiser Analytics", testid: "adnav-ads-aanalytics" },
      { to: "/admin/ads/auction-log",          label: "Auction Log",             testid: "adnav-ads-auction" },
      { to: "/admin/ads/revenue",                  label: "Ads Revenue",             testid: "adnav-ads-revenue" },
      { to: "/admin/predict-win/campaigns",  label: "Predict & Win (Manage)", testid: "adnav-pw-campaigns" },
      { to: "/admin/predict-win/self-serve", label: "Predict & Win (Self)",    testid: "adnav-pw-self-serve" },
      { to: "/admin/games-approval",         label: "Games Approval",         testid: "adnav-games-approval" },
      { to: "/admin/games-analytics",         label: "Games Analytics",         testid: "adnav-games-analytics" },
      { to: "/admin/games-inventory",         label: "Games Inventory",         testid: "adnav-games-inventory" },
      { to: "/admin/subscriptions",             label: "Subscriptions",             testid: "adnav-billing-subs" },
    ],
  },
  {
    key: "content",
    label: "Content",
    icon: Sparkles,
    items: [
      { to: "/admin/flagship-stations",       label: "Flagship Stations", testid: "adnav-radio-flagship" },
      { to: "/admin/radio/claims",               label: "Radio Claims",       testid: "adnav-radio-claims" },
      { to: "/admin/bulk-upload",                 label: "Bulk Upload",         testid: "adnav-radio-bulk-upload" },
      { to: "/admin/podcasts/applications", label: "Podcast Apps",       testid: "adnav-podcasts-apps" },
      { to: "/admin/podcasts/channels",         label: "Podcast Channels", testid: "adnav-podcasts-channels" },
      { to: "/admin/rj-quality",                   label: "RJ Quality",           testid: "adnav-podcasts-rjq" },
      { to: "/admin/rj-personas",                 label: "RJ Personas",         testid: "adnav-podcasts-rj-personas" },
      { to: "/admin/voices",                           label: "Voices",                 testid: "adnav-cq-voices" },
      { to: "/admin/imaging",                         label: "Imaging",               testid: "adnav-cq-imaging" },
      { to: "/admin/moderation/tracks",         label: "Tracks (UGC)",     testid: "adnav-cq-moderation" },
      { to: "/admin/personas/safety",             label: "Persona Safety",   testid: "adnav-cq-persona" },
      { to: "/admin/news",                             label: "News Radio",         testid: "adnav-cq-news" },
    ],
  },
  {
    key: "users-businesses",
    label: "Users & Businesses",
    icon: Users,
    items: [
      { to: "/admin/users",                     label: "Users",              testid: "adnav-users-list" },
      { to: "/admin/users/audit-log",   label: "Audit Log",         testid: "adnav-users-audit" },
      { to: "/admin/merchants",             label: "Merchants",          testid: "adnav-merchants-list" },
      { to: "/admin/commissions",         label: "Commissions",      testid: "adnav-merchants-commissions" },
      { to: "/admin/refunds",                 label: "Refunds",              testid: "adnav-merchants-refunds" },
      { to: "/admin/payouts",                 label: "Payouts",              testid: "adnav-merchants-payouts" },
      { to: "/admin/disputes",               label: "Disputes",            testid: "adnav-merchants-disputes" },
      { to: "/admin/points",                   label: "Points & Rewards", testid: "adnav-points-ledger" },
    ],
  },
  {
    key: "system",
    label: "System",
    icon: Settings,
    items: [
      { to: "/admin/safety",             label: "Safety",             testid: "adnav-ops-safety" },
      { to: "/admin/integrations", label: "Integrations", testid: "adnav-ops-integrations" },
    ],
  },
];

const SIDEBAR_WIDTH = 220;


function _readExpanded() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) {
      const path = typeof window !== "undefined"
                                        ? window.location.pathname : "";
      const initial = {};
      for (const s of SECTIONS) {
        if (s.items.some((i) => path === i.to
                                    || (i.to !== "/admin" && path.startsWith(i.to)))) {
          initial[s.key] = true;
        }
      }
      if (!Object.keys(initial).length) initial["home-analytics"] = true;
      return initial;
    }
    return JSON.parse(raw) || {};
  } catch (_e) { return { "home-analytics": true }; }
}


export default function AdminSidebar() {
  const { user } = useAuth();
  const location = useLocation();
  const isAdminRoute = location.pathname.startsWith("/admin");
  const isAdminUser    = user && (user.role === "admin"
                                                                  || user.role === "ad_manager");

  const [expanded,  setExpanded]  = useState(_readExpanded);
  const [navCounts, setNavCounts] = useState({});
  const [pins,        setPins]        = useState([]);

  const toggle = useCallback((key) => {
    setExpanded((cur) => {
      const next = { ...cur, [key]: !cur[key] };
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)); }
      catch (_e) { /* private-mode etc. */ }
      return next;
    });
  }, []);

  // Auto-expand the super-group containing the currently active route.
  useEffect(() => {
    if (!isAdminRoute) return;
    setExpanded((cur) => {
      let changed = false;
      const next = { ...cur };
      for (const s of SECTIONS) {
        if (!next[s.key] && s.items.some(
                (i) => location.pathname === i.to
                            || (i.to !== "/admin" && location.pathname.startsWith(i.to)))) {
          next[s.key] = true;
          changed = true;
        }
      }
      if (!changed) return cur;
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)); }
      catch (_e) { /* ignore */ }
      return next;
    });
  }, [location.pathname, isAdminRoute]);

  // Phase ADMIN.NAV.2 — poll nav-counts every 60s, pause when hidden.
  useEffect(() => {
    if (!isAdminRoute || !isAdminUser) return;
    let timer = null;
    let cancelled = false;
    const fetchCounts = async () => {
      try {
        const r = await axios.get(`${API}/admin/nav-counts`,
                                                                { withCredentials: true });
        if (!cancelled) setNavCounts(r.data || {});
      } catch (_e) { /* silent */ }
    };
    const start = () => {
      if (timer) return;
      fetchCounts();
      timer = setInterval(fetchCounts, NAV_COUNTS_POLL_MS);
    };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => (document.hidden ? stop() : start());
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVis);
      stop();
    };
  }, [isAdminRoute, isAdminUser]);

  // Phase T — pinned section load + refresh on custom event.
  const loadPins = useCallback(async () => {
    if (!isAdminRoute || !isAdminUser) return;
    try {
      const r = await axios.get(`${API}/admin/nav/pins`,
                                                              { withCredentials: true });
      setPins(r.data?.items || []);
    } catch (_e) { setPins([]); }
  }, [isAdminRoute, isAdminUser]);
  useEffect(() => { loadPins(); }, [loadPins]);
  useEffect(() => {
    const h = () => loadPins();
    window.addEventListener("bigfm:admin-pins-changed", h);
    return () => window.removeEventListener("bigfm:admin-pins-changed", h);
  }, [loadPins]);

  const unpin = async (route) => {
    try {
      await axios.delete(`${API}/admin/nav/pin${route}`,
                                                    { withCredentials: true });
      loadPins();
    } catch (_e) { /* ignore */ }
  };

  const active = (to) => location.pathname === to
    || (to !== "/admin" && location.pathname.startsWith(to));

  const visibleSections = useMemo(() => {
    if (user?.role === "ad_manager") {
      return [
        SECTIONS.find((s) => s.key === "home-analytics"),
        SECTIONS.find((s) => s.key === "ad-monetization"),
      ].filter(Boolean);
    }
    return SECTIONS;
  }, [user?.role]);

  if (!isAdminRoute || !isAdminUser) return null;

  const openSearch = () => {
    window.dispatchEvent(new CustomEvent("bigfm:admin-search-open"));
  };

  return (
    <aside data-testid="admin-sidebar"
              style={{position: "fixed", top: 0, left: 0, bottom: 0,
                              width: SIDEBAR_WIDTH,
                              background: "#0a0a0f",
                              borderRight: "1px solid rgba(255,255,255,0.06)",
                              padding: "16px 0 40px",
                              overflowY: "auto", zIndex: 40,
                              display: "flex", flexDirection: "column"}}>
      {/* Return-home CTA */}
      <Link to="/" data-testid="admin-sidebar-return-home"
                style={{display: "flex", alignItems: "center", gap: 8,
                            margin: "0 12px 10px", padding: "10px 14px",
                            background: "linear-gradient(135deg, #F72585, #B5179E)",
                            borderRadius: 10, color: "#fff", textDecoration: "none",
                            fontWeight: 700, fontSize: 13, letterSpacing: 0.2}}>
        <ArrowLeft size={14} /> Return to Home
      </Link>

      {/* Cmd/Ctrl+K search trigger */}
      <button type="button" onClick={openSearch}
                      data-testid="admin-sidebar-search-trigger"
                      style={{display: "flex", alignItems: "center", gap: 8,
                                      margin: "0 12px 12px", padding: "8px 12px",
                                      background: "rgba(255,255,255,0.04)",
                                      border: "1px solid rgba(255,255,255,0.08)",
                                      borderRadius: 10, color: "#94a3b8",
                                      fontSize: 12, cursor: "pointer",
                                      justifyContent: "flex-start"}}>
        <Search size={12} />
        <span style={{flex: 1, textAlign: "left"}}>Search…</span>
        <span style={{fontFamily: "monospace", fontSize: 10,
                                    padding: "1px 5px", borderRadius: 4,
                                    background: "rgba(255,255,255,0.06)"}}>⌘K</span>
      </button>

      <div style={{padding: "0 20px 6px", fontSize: 10,
                            letterSpacing: 1.5, color: "#666",
                            textTransform: "uppercase", fontFamily: "monospace"}}>
        <ShieldCheck size={11} style={{display: "inline",
                                                                          verticalAlign: "middle",
                                                                          marginRight: 4}} />
        Admin Console
      </div>

      <nav style={{marginTop: 8, display: "flex", flexDirection: "column",
                                gap: 2}}>
        {/* Pinned section */}
        {pins.length > 0 && (
          <div data-testid="adnav-section-pinned"
                    style={{display: "flex", flexDirection: "column",
                                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                                    paddingBottom: 8, marginBottom: 4}}>
            <div style={{display: "flex", alignItems: "center", gap: 8,
                                      padding: "8px 14px",
                                      color: "#f59e0b",
                                      fontSize: 12, fontWeight: 700,
                                      letterSpacing: 0.2, textTransform: "uppercase",
                                      fontFamily: "monospace"}}>
              <Star size={12} fill="#f59e0b" />
              <span>Pinned</span>
              <span style={{marginLeft: "auto", color: "#666",
                                        fontSize: 10}}>{pins.length}</span>
            </div>
            <div style={{display: "flex", flexDirection: "column",
                                      padding: "2px 0 4px 12px", gap: 1}}>
              {pins.map((p) => {
                const isActive = active(p.route);
                return (
                  <div key={p.route}
                            data-testid={`adnav-pin-${p.route}`}
                            style={{display: "flex", alignItems: "center",
                                            gap: 4}}>
                    <Link to={p.route}
                                aria-current={isActive ? "page" : undefined}
                                style={{
                                  flex: 1,
                                  display: "flex", alignItems: "center", gap: 6,
                                  padding: "6px 14px",
                                  fontSize: 12,
                                  color: isActive ? "#f59e0b" : "#cbd5e1",
                                  fontWeight: isActive ? 700 : 500,
                                  textDecoration: "none",
                                  borderLeft: isActive
                                    ? "2px solid #f59e0b"
                                    : "2px solid transparent",
                                  background: isActive
                                    ? "rgba(245,158,11,0.08)" : "transparent",
                                }}>
                      <span style={{flex: 1, overflow: "hidden",
                                                textOverflow: "ellipsis",
                                                whiteSpace: "nowrap"}}>
                        {p.label || p.route}
                      </span>
                    </Link>
                    <button type="button" onClick={() => unpin(p.route)}
                                    data-testid={`adnav-pin-remove-${p.route}`}
                                    title="Remove from pinned"
                                    style={{background: "transparent", border: "none",
                                                    color: "#64748b", cursor: "pointer",
                                                    padding: "0 6px"}}>
                      <X size={11} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 5 super-groups */}
        {visibleSections.map((s) => {
          const isOpen = !!expanded[s.key];
          const isAncestorActive = s.items.some((i) => active(i.to));
          const sectionBadge = s.items.reduce((sum, i) => {
            const key = BADGE_TESTID_MAP[i.testid];
            return sum + (key ? (navCounts[key] || 0) : 0);
          }, 0);
          return (
            <div key={s.key} data-testid={`adnav-section-${s.key}`}
                        style={{display: "flex", flexDirection: "column"}}>
              <button type="button"
                              onClick={() => toggle(s.key)}
                              data-testid={`adnav-section-toggle-${s.key}`}
                              aria-expanded={isOpen}
                              style={{
                                display: "flex", alignItems: "center", gap: 8,
                                width: "100%", padding: "8px 14px",
                                background: isAncestorActive
                                                              ? "rgba(247,37,133,0.05)" : "transparent",
                                border: "none", cursor: "pointer",
                                color: isAncestorActive ? "#f472b6" : "#cbd5e1",
                                fontSize: 12, fontWeight: 700,
                                textAlign: "left", letterSpacing: 0.2,
                                textTransform: "uppercase", fontFamily: "monospace",
                              }}>
                <s.icon size={12} />
                <span style={{flex: 1}}>{s.label}</span>
                {sectionBadge > 0 && !isOpen && (
                  <span data-testid={`adnav-section-badge-${s.key}`}
                              style={{
                                display: "inline-flex", alignItems: "center",
                                justifyContent: "center",
                                minWidth: 18, height: 16, padding: "0 5px",
                                borderRadius: 8,
                                fontSize: 10, fontFamily: "monospace",
                                fontWeight: 800,
                                background: "#F72585",
                                color: "#fff",
                                lineHeight: "16px",
                              }}>
                    {sectionBadge > 99 ? "99+" : sectionBadge}
                  </span>
                )}
                <ChevronRight size={12}
                                            style={{transform: isOpen
                                                                    ? "rotate(90deg)" : "rotate(0deg)",
                                                            transition: "transform 150ms"}} />
              </button>
              {isOpen && (
                <div style={{display: "flex", flexDirection: "column",
                                          padding: "2px 0 6px 12px", gap: 1}}>
                  {s.items.map((it) => {
                    const isActive = active(it.to);
                    const badgeKey = BADGE_TESTID_MAP[it.testid];
                    const badgeCount = badgeKey ? (navCounts[badgeKey] || 0) : 0;
                    return (
                      <Link key={it.to} to={it.to}
                                    data-testid={it.testid}
                                    aria-current={isActive ? "page" : undefined}
                                    style={{
                                      display: "flex", alignItems: "center", gap: 6,
                                      padding: "6px 14px",
                                      fontSize: 12,
                                      color: isActive ? "#F72585" : "#94a3b8",
                                      fontWeight: isActive ? 700 : 500,
                                      textDecoration: "none",
                                      borderLeft: isActive
                                                                      ? "2px solid #F72585"
                                                                      : "2px solid transparent",
                                      background: isActive
                                                                      ? "rgba(247,37,133,0.08)"
                                                                      : "transparent",
                                      transition: "all 120ms",
                                    }}>
                        <span style={{flex: 1}}>{it.label}</span>
                        {badgeCount > 0 && (
                          <span data-testid={`adnav-badge-${it.testid}`}
                                      style={{
                                        display: "inline-flex", alignItems: "center",
                                        justifyContent: "center",
                                        minWidth: 18, height: 16, padding: "0 5px",
                                        borderRadius: 8,
                                        fontSize: 10, fontFamily: "monospace",
                                        fontWeight: 800,
                                        background: badgeCount > 9
                                                                                    ? "#F72585"
                                                                                    : "#fb923c",
                                        color: "#fff",
                                        lineHeight: "16px",
                                      }}>
                            {badgeCount > 99 ? "99+" : badgeCount}
                          </span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}


// Exposed so AppShell can offset content by the exact sidebar width.
export const ADMIN_SIDEBAR_WIDTH = SIDEBAR_WIDTH;
