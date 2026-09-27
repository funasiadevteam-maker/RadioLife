// Phase MER.1 — Merchant Portal Shell (desktop-first, both variants).
//
// Provides:
//    - Left sidebar (240 px on desktop, top drawer on mobile)
//    - Auth-gate: redirects to /merchant/apply if the current user has
//        no merchant, or /merchant/status if the merchant isn't approved.
//    - MerchantContext with the current merchant fetched via /api/merchant/mine
//
// Used as a React Router layout route — inner pages render via <Outlet/>.
import { createContext, useContext, useEffect, useState } from "react";
import { Link, Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import axios from "axios";
import {
  LayoutDashboard, CreditCard, ArrowLeftRight, Wallet,
  Store, Zap, Settings, LogOut, Menu, X, ChevronRight,
  ExternalLink, AlertTriangle, ScanLine, Users,
  Gift, UtensilsCrossed, Trophy, MapPin,
  Rocket, Eye, LayoutGrid, ArrowRight, Sparkles, Megaphone, Radio,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


const MerchantCtx = createContext(null);
export const useMerchant = () => useContext(MerchantCtx);


// Phase MER.2 — nav items now filtered by role permission
// Phase MER.3 — added Gift Cards + Prepaid Meals under Payment Links.
const NAV_ITEMS = [
  { path: "/merchant/dashboard",          label: "Overview",              Icon: LayoutDashboard, perm: null },
  { path: "/merchant/payment-links",  label: "Payment Links",    Icon: CreditCard,          perm: "can_create_links" },
  { path: "/merchant/gift-cards",        label: "Gift Cards",          Icon: Gift,                        perm: "can_create_links" },
  { path: "/merchant/prepaid-meals",  label: "Meal Packs",          Icon: UtensilsCrossed, perm: "can_create_links" },
  { path: "/merchant/games",              label: "Games",                    Icon: Trophy,                  perm: "can_create_links" },
  { path: "/merchant/sponsor-games",  label: "Sponsor Games",  Icon: Sparkles,              perm: "can_create_links" },
  { path: "/merchant/advertise",        label: "Advertise",            Icon: Megaphone,          perm: "can_create_links" },
  { path: "/merchant/rail-sponsor",  label: "Rail Sponsor",      Icon: Radio,                    perm: "can_create_links" },
  { path: "/payouts",                          label: "Payments & Payouts", Icon: Wallet,          perm: null },
  { path: "/merchant/transactions",    label: "Transactions",      Icon: ArrowLeftRight,  perm: "can_view_transactions" },
  { path: "/merchant/insights",          label: "Insights",              Icon: MapPin,                  perm: null },
  { path: "/merchant/payouts",              label: "Payouts",                Icon: Wallet,                  perm: "can_view_payouts" },
  { path: "/merchant/cashier",              label: "Cashier",                Icon: ScanLine,              perm: "can_redeem_coupons" },
  { path: "/merchant/staff",                label: "Staff",                    Icon: Users,                    perm: "can_invite_staff" },
  { path: "/merchant/profile",              label: "Profile",                Icon: Store,                    perm: "can_edit_profile" },
  { path: "/merchant/stripe",                label: "Stripe Connect",  Icon: Zap,                        perm: "can_manage_stripe" },
  { path: "/merchant/settings",            label: "Settings",              Icon: Settings,              perm: null },
];


export default function MerchantShell() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading, logout } = useAuth();
  const navigate = useNavigate();
  const [merchant, setMerchant] = useState(null);
  const [role, setRole] = useState(null);
  const [permissions, setPermissions] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    (async () => {
      if (!user) {
        navigate("/login?next=/merchant/dashboard", { replace: true });
        return;
      }
      try {
        const { data } = await axios.get(`${API}/merchant/mine`,
                                                                        { withCredentials: true });
        let items = data.items || [];
        // Phase MER.2 — also fetch merchants where the user is a staff member.
        // /merchant/mine returns only owned merchants; a cashier of another
        // merchant needs the staff-membership fallback.
        if (items.length === 0) {
          try {
            const { data: staffData } = await axios.get(
              `${API}/merchant/mine/as-staff`,
              { withCredentials: true });
            items = staffData.items || [];
          } catch (_) { /* endpoint may not exist yet */ }
        }
        if (items.length === 0) {
          navigate("/merchant/apply", { replace: true }); return;
        }
        // Phase PORTAL.0 — honour the workspace chosen via the switcher so
        // multi-merchant users land on the right store (defaults to first).
        let m = items[0];
        try {
          const activeId = window.localStorage.getItem("bigfm_active_workspace");
          if (activeId) {
            const match = items.find((it) => it.merchant_id === activeId);
            if (match) m = match;
          }
        } catch (_) { /* ignore */ }
        setMerchant(m);
        const status = m.merchant_status;
        if (m.owner_user_id === user.user_id
                && (status === "draft" || status === "submitted"
                        || status === "rejected")) {
          navigate(`/merchant/status?merchant_id=${m.merchant_id}`,
                              { replace: true });
          return;
        }
        // Phase MER.2 — resolve current user's role for RBAC-aware sidebar
        try {
          const { data: r } = await axios.get(
            `${API}/merchant/${m.merchant_id}/me/role`,
            { withCredentials: true });
          setRole(r.role);
          setPermissions(new Set(r.permissions || []));
        } catch (_) {
          setRole("owner");
          setPermissions(new Set());
        }
      } catch (e) {
        setError(e?.response?.data?.detail || e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [authLoading, user, navigate]);

  if (loading) {
    return (
      <div className={light ? "min-h-screen bg-purple-50 flex items-center justify-center"
                                          : "min-h-screen bg-slate-950 flex items-center justify-center"}>
        <div className={`animate-pulse text-sm font-bold uppercase tracking-widest ${
          light ? "text-purple-600" : "text-cyan-400"
        }`}>Loading portal…</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className={light ? "min-h-screen bg-purple-50 flex items-center justify-center p-6"
                                          : "min-h-screen bg-slate-950 flex items-center justify-center p-6"}>
        <div className={light ? "bg-white rounded-3xl p-6 max-w-md text-center border border-slate-100"
                                            : "bg-slate-900 rounded-3xl p-6 max-w-md text-center border border-slate-800"}>
          <AlertTriangle className={light ? "text-rose-500 mx-auto mb-3" : "text-rose-400 mx-auto mb-3"} size={28}/>
          <div className={`text-lg font-black mb-1 ${light ? "text-slate-900" : "text-white"}`}>
            Couldn&apos;t load portal
          </div>
          <div className={`text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>{error}</div>
        </div>
      </div>
    );
  }
  if (!merchant) return null;

  const ctx = { merchant, role, permissions, light,
                              hasPerm: (p) => permissions.has(p),
                              refresh: async () => {
    const { data } = await axios.get(`${API}/merchant/mine`,
                                                                    { withCredentials: true });
    if (data.items?.[0]) setMerchant(data.items[0]);
  } };

  return (
    <MerchantCtx.Provider value={ctx}>
      <div className={light ? "min-h-screen bg-purple-50" : "min-h-screen bg-slate-950"}
                data-testid="merchant-shell" data-variant={variant}>
        {/* Mobile top-bar */}
        <div className={`lg:hidden sticky top-0 z-30 flex items-center justify-between px-4 h-14 ${
          light ? "bg-white border-b border-slate-100"
                  : "bg-slate-900 border-b border-slate-800"
        }`}>
          <button onClick={() => setMobileOpen(true)}
                        data-testid="merchant-shell-mobile-open"
                        className={light ? "text-slate-700" : "text-slate-200"}>
            <Menu size={22}/>
          </button>
          <div className={`text-sm font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"
          }`}>{merchant.name}</div>
          <div className="w-8"/>
        </div>

        <div className="flex">
          <Sidebar light={light} merchant={merchant}
                              permissions={permissions} role={role}
                              onLogout={() => {
            logout?.();
            navigate("/login");
          }} />

          {/* Mobile drawer */}
          {mobileOpen && (
            <>
              <div onClick={() => setMobileOpen(false)}
                        className="lg:hidden fixed inset-0 z-40 bg-black/60"/>
              <div className={`lg:hidden fixed left-0 top-0 bottom-0 z-50 w-[85%] max-w-[300px] ${
                light ? "bg-white" : "bg-slate-900"
              }`}>
                <div className="flex items-center justify-between px-5 h-14">
                  <div className={`text-sm font-black ${
                    light ? "text-slate-900" : "text-white"
                  }`}>Menu</div>
                  <button onClick={() => setMobileOpen(false)}
                                data-testid="merchant-shell-mobile-close"
                                className={light ? "text-slate-500" : "text-slate-400"}>
                    <X size={20}/>
                  </button>
                </div>
                <SidebarInner light={light} merchant={merchant}
                                          permissions={permissions} role={role}
                                          onLogout={() => { logout?.(); navigate("/login"); }}
                                          onNav={() => setMobileOpen(false)}/>
              </div>
            </>
          )}

          <main className="flex-1 min-w-0" data-testid="merchant-shell-main">
            {variant === "new_look_v2" && (
              <PortalBandV2 merchant={merchant}
                                          onSwitch={() => navigate("/portal")} />
            )}
            <Outlet />
          </main>
        </div>
      </div>
    </MerchantCtx.Provider>
  );
}


// V2 Business-Portal band — premium header connecting the merchant dashboard
// to the New Look V2 public site. Presentation only; data/permissions shared.
function PortalBandV2({ merchant, onSwitch }) {
  const checks = [
    !!merchant?.name,
    !!merchant?.logo_url,
    !!merchant?.stripe_charges_enabled,
    !!merchant?.stripe_payouts_enabled,
  ];
  const pct = Math.round((checks.filter(Boolean).length / checks.length) * 100);
  const stripeReady = merchant?.stripe_charges_enabled && merchant?.stripe_payouts_enabled;
  const setupHref = stripeReady ? "/merchant/profile" : "/merchant/stripe";
  return (
    <div className="relative overflow-hidden border-b border-white/10"
              data-testid="merchant-portal-band-v2"
              style={{ background: "linear-gradient(120deg,#0b0f1e 0%,#1a1038 55%,#2a1148 100%)" }}>
      <div className="absolute -top-16 -right-10 w-64 h-64 rounded-full blur-3xl opacity-30"
                style={{ background: "radial-gradient(circle,#a855f7,transparent 70%)" }} />
      <div className="relative px-6 lg:px-10 py-5 flex items-center gap-5 flex-wrap">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-purple-300">FUUSIC</span>
            <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-200">
              <Sparkles size={9} /> Soft Launch
            </span>
            <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full text-slate-950"
                        style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
              6 Months Free
            </span>
          </div>
          <div className="text-xl lg:text-2xl font-black text-white truncate"
                    data-testid="merchant-portal-band-name">{merchant?.name}</div>
          <div className="mt-2 flex items-center gap-3 max-w-md">
            <div className="flex-1 h-2 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${pct}%`,
                          background: "linear-gradient(90deg,#06b6d4,#a855f7)" }} />
            </div>
            <span className="text-xs font-black text-cyan-300 tabular-nums whitespace-nowrap"
                        data-testid="merchant-portal-band-readiness">{pct}% ready</span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Link to={setupHref} data-testid="merchant-portal-complete-setup"
                      className="inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-sm font-black"
                      style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)", color: "#fff" }}>
            <Rocket size={14} /> Complete Setup
          </Link>
          <Link to="/merchant/profile" data-testid="merchant-portal-preview-store"
                      className="inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-sm font-bold text-white bg-white/10 hover:bg-white/15 border border-white/10">
            <Eye size={14} /> Preview My Store
          </Link>
          <button type="button" onClick={onSwitch} data-testid="merchant-portal-switch-workspace"
                        className="inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-sm font-bold text-white bg-white/10 hover:bg-white/15 border border-white/10">
            <LayoutGrid size={14} /> Switch Workspace
          </button>
        </div>
      </div>
    </div>
  );
}


function Sidebar({ light, merchant, permissions, role, onLogout }) {
  return (
    <aside className={`hidden lg:flex flex-col w-[240px] shrink-0 sticky top-0 h-screen ${
      light ? "bg-white border-r border-slate-100"
              : "bg-slate-900 border-r border-slate-800"
    }`} data-testid="merchant-shell-sidebar">
      <SidebarInner light={light} merchant={merchant}
                              permissions={permissions} role={role} onLogout={onLogout}/>
    </aside>
  );
}


function SidebarInner({ light, merchant, permissions, role, onLogout, onNav }) {
  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const logoUrl = merchant.logo_url
    ? (merchant.logo_url.startsWith("http")
          ? merchant.logo_url : backendBase + merchant.logo_url)
    : null;
  const tierLabel = merchant.stripe_charges_enabled
                                    && merchant.stripe_payouts_enabled ? "ACTIVE"
                                : merchant.stripe_charges_enabled ? "RESTRICTED"
                                : "SETUP";
  const tierColor = tierLabel === "ACTIVE"
      ? (light ? "bg-emerald-100 text-emerald-700"
                      : "bg-emerald-500/15 text-emerald-300")
      : tierLabel === "RESTRICTED"
      ? (light ? "bg-amber-100 text-amber-700"
                      : "bg-amber-500/15 text-amber-300")
      : (light ? "bg-slate-100 text-slate-600"
                      : "bg-slate-500/15 text-slate-400");

  return (
    <>
      {/* Merchant header */}
      <div className={`px-4 py-5 ${
        light ? "border-b border-slate-100" : "border-b border-slate-800"
      }`} data-testid="merchant-shell-sidebar-header">
        <div className="flex items-center gap-3">
          {logoUrl ? (
            <img src={logoUrl} alt={merchant.name} className="w-11 h-11 rounded-xl object-cover"/>
          ) : (
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center text-sm font-black ${
              light ? "bg-purple-100 text-purple-700"
                      : "bg-cyan-500/15 text-cyan-300"
            }`}>{(merchant.name || "?").charAt(0).toUpperCase()}</div>
          )}
          <div className="min-w-0 flex-1">
            <div className={`text-sm font-black tracking-tight truncate ${
              light ? "text-slate-900" : "text-white"
            }`} data-testid="merchant-shell-name">{merchant.name}</div>
            <div className={`text-[9px] font-bold uppercase tracking-widest ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>Merchant portal</div>
          </div>
        </div>
        <div className={`inline-flex mt-3 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest ${tierColor}`}
                  data-testid="merchant-shell-tier">
          {tierLabel}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS
          .filter((item) => {
            // Overview + Settings always visible.  Others gated by permission.
            if (!item.perm) return true;
            // If permissions haven't loaded yet (empty Set), fall back to
            // showing all — the endpoint call will still 403 if unauthorised.
            if (!permissions || permissions.size === 0) return true;
            return permissions.has(item.perm);
          })
          .map((item) => (
          <NavLink key={item.path} to={item.path}
                        end
                        data-testid={`merchant-nav-${item.path.replace(/\//g, "-").replace(/^-/, "")}`}
                        onClick={onNav}
                        className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold ${
                          isActive
                            ? (light ? "bg-purple-100 text-purple-700"
                                          : "bg-cyan-500/15 text-cyan-300")
                            : (light ? "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                                          : "text-slate-400 hover:bg-slate-800 hover:text-slate-200")
                        }`}>
            <item.Icon size={16}/>
            <span className="flex-1">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className={`px-3 py-3 space-y-1 ${
        light ? "border-t border-slate-100" : "border-t border-slate-800"
      }`}>
        <Link to="/" data-testid="merchant-shell-back-home"
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold ${
                      light ? "text-slate-600 hover:bg-slate-50"
                              : "text-slate-400 hover:bg-slate-800"
                    }`}>
          <ExternalLink size={12}/> Explore FUUSIC
        </Link>
        <button onClick={onLogout} data-testid="merchant-shell-logout"
                      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold ${
                        light ? "text-rose-600 hover:bg-rose-50"
                                : "text-rose-400 hover:bg-rose-500/10"
                      }`}>
          <LogOut size={12}/> Sign out
        </button>
      </div>
    </>
  );
}
