/**
 * Phase CLAIM.1b — Claim Radio Hub.
 *
 * Route: `/claim-radio`
 *
 * Three sections stacked vertically:
 *   1. Browse Unclaimed Stations — infinite grid + basic filters
 *          (q / country / language / region)
 *   2. My Pending Claims — timeline of the user's submitted claims
 *   3. My Owned Stations — grid of already-approved stations (deep-link
 *          to `/owner/dashboard` for full management)
 *
 * Anonymous users see a modal blocking sections 2 + 3 with a
 * `<SignInWithGoogleButton />` as the primary CTA and an email/password
 * fallback.  Browsing (section 1) works without auth.
 *
 * Dual-design: `useDesignVariant()` swaps the surface between the dark
 * "legacy" theme and the light "radiolife" theme.  All Tailwind
 * classes ternary on `light`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast, Toaster } from "sonner";
import {
  Radio as RadioIcon, Search, Loader2, X, ShieldCheck,
  Building2, MapPin, ExternalLink, ArrowRight, Clock,
  CheckCircle2, XCircle, AlertTriangle, LogIn,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import SignInWithGoogleButton from "@/SignInWithGoogleButton";

const PAGE_LIMIT = 24;

const CLAIM_STATUS_META = {
  submitted:  { icon: Clock,          color: "amber",    label: "Submitted" },
  verifying:  { icon: Clock,          color: "cyan",      label: "Verifying" },
  approved:    { icon: CheckCircle2, color: "emerald", label: "Approved" },
  rejected:    { icon: XCircle,        color: "rose",      label: "Rejected" },
  abandoned: { icon: X,                    color: "slate",    label: "Abandoned" },
};

// ─── Sign-in modal ────────────────────────────────────────────
function ClaimSignInModal({ redirectPath, onClose, variant }) {
  const light = variant === "radiolife";
  return (
    <div data-testid="claim-hub-signin-modal"
              className={"fixed inset-0 z-[80] flex items-center justify-center p-4 " +
                                (light ? "bg-slate-900/40 backdrop-blur-sm"
                                                  : "bg-black/70 backdrop-blur-sm")}>
      <div className={"w-full max-w-[440px] rounded-2xl p-7 " + (light
                  ? "bg-white border border-slate-200 shadow-2xl"
                  : "bg-[#0a0a0c] border border-white/[0.10]")}>
        <div className="flex items-center justify-between mb-3">
          <div className={"inline-flex items-center gap-2 text-xs uppercase tracking-widest font-mono " +
                                    (light ? "text-fuchsia-600" : "text-cyan-300")}>
            <ShieldCheck size={12} /> Sign in required
          </div>
          <button onClick={onClose}
                          data-testid="claim-hub-signin-close"
                          className={"p-1.5 rounded " + (light
                            ? "text-slate-500 hover:bg-slate-100 hover:text-slate-800"
                            : "text-white/60 hover:bg-white/[0.06] hover:text-white")}>
            <X size={16} />
          </button>
        </div>
        <h2 className={"text-xl font-bold mb-2 " + (light ? "text-slate-900" : "text-white")}>
          Sign in to claim a station
        </h2>
        <p className={"text-sm mb-6 " + (light ? "text-slate-600" : "text-white/60")}>
          Station ownership is tied to your RadioLife account. Continue with
          Google or use email &amp; password.
        </p>
        <div className="mb-4">
          <SignInWithGoogleButton size="large" variant={variant}
                                                                redirectPath={redirectPath || "/claim-radio"}
                                                                data-testid="claim-hub-signin-google" />
        </div>
        <div className={"flex items-center gap-3 mb-4 text-[11px] " +
                                      (light ? "text-slate-400" : "text-white/40")}>
          <div className={"flex-grow h-px " +
                                        (light ? "bg-slate-200" : "bg-white/[0.10]")} />
          OR
          <div className={"flex-grow h-px " +
                                        (light ? "bg-slate-200" : "bg-white/[0.10]")} />
        </div>
        <Link to={`/login?next=${encodeURIComponent(redirectPath || "/claim-radio")}`}
                    data-testid="claim-hub-signin-email"
                    className={"w-full inline-flex items-center justify-center gap-2 " +
                                        "h-11 rounded-full text-sm font-semibold " +
                                        (light
                                            ? "bg-slate-900 text-white hover:bg-slate-800"
                                            : "bg-white/[0.06] text-white hover:bg-white/[0.10] border border-white/[0.10]")}>
          <LogIn size={14} /> Continue with email
        </Link>
      </div>
    </div>
  );
}


// ─── Browse Grid ──────────────────────────────────────────────
function BrowseGrid({ variant, onClaim }) {
  const light = variant === "radiolife";
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const fetchStations = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (q) p.set("q", q);
      if (country) p.set("country", country);
      p.set("page", page);
      p.set("limit", PAGE_LIMIT);
      const r = await axios.get(`${API}/stations/claimable?${p.toString()}`);
      setItems(r.data?.items || []);
      setTotal(r.data?.total || 0);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "browse_failed");
    } finally { setLoading(false); }
  }, [q, country, page]);

  useEffect(() => { fetchStations(); }, [fetchStations]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_LIMIT));

  return (
    <section data-testid="claim-hub-browse-section"
                    className={"rounded-2xl p-5 mb-6 " + (light
                      ? "bg-white border border-slate-200"
                      : "bg-white/[0.03] border border-white/[0.10]")}>
      <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
        <h2 className={"text-lg font-semibold " +
                                    (light ? "text-slate-900" : "text-white")}
                data-testid="claim-hub-browse-title">
          Browse Unclaimed Stations
          <span className={"ml-2 text-xs font-mono " +
                                        (light ? "text-slate-500" : "text-white/40")}>
            {total} available
          </span>
        </h2>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <div className={"relative flex-grow min-w-[220px] " +
                                    (light ? "text-slate-800" : "text-white")}>
          <Search size={14} className={"absolute left-3 top-1/2 -translate-y-1/2 " +
                                                                    (light ? "text-slate-400" : "text-white/40")} />
          <input type="search" value={q}
                        onChange={(e) => { setQ(e.target.value); setPage(1); }}
                        data-testid="claim-hub-browse-search"
                        placeholder="Search station name…"
                        className={"w-full pl-9 pr-3 h-10 rounded-lg text-sm " +
                                              (light
                                                  ? "bg-slate-50 border border-slate-200 focus:border-fuchsia-500 focus:outline-none"
                                                  : "bg-black/40 border border-white/[0.10] focus:border-cyan-400/50 focus:outline-none")} />
        </div>
        <input type="text" value={country} maxLength={2}
                    onChange={(e) => { setCountry(e.target.value.toUpperCase()); setPage(1); }}
                    data-testid="claim-hub-browse-country"
                    placeholder="Country (US, AE…)"
                    className={"w-[160px] px-3 h-10 rounded-lg text-sm " +
                                          (light
                                              ? "bg-slate-50 border border-slate-200 focus:border-fuchsia-500 focus:outline-none"
                                              : "bg-black/40 border border-white/[0.10] focus:border-cyan-400/50 focus:outline-none")} />
      </div>

      {loading ? (
        <div className={"flex items-center gap-3 py-10 " +
                                      (light ? "text-slate-500" : "text-white/50")}
                  data-testid="claim-hub-browse-loading">
          <Loader2 size={16} className="animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div data-testid="claim-hub-browse-empty"
                  className={"rounded-lg p-8 text-center text-sm " +
                                    (light ? "bg-slate-50 text-slate-500 border border-slate-200"
                                                      : "bg-white/[0.02] text-white/50 border border-white/[0.10]")}>
          No unclaimed stations match those filters.
        </div>
      ) : (        <ul data-testid="claim-hub-browse-grid"
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((s) => (
            <li key={s.id} data-station-id={s.id}
                      data-testid={`claim-hub-browse-card-${s.id}`}
                      className={"rounded-xl p-3 flex items-start gap-3 transition-colors " +
                                            (light
                                                ? "bg-slate-50 border border-slate-200 hover:bg-slate-100"
                                                : "bg-white/[0.02] border border-white/[0.10] hover:bg-white/[0.05]")}>
              <div className={"w-12 h-12 rounded-lg flex-shrink-0 overflow-hidden " +
                                            (light ? "bg-slate-200" : "bg-white/[0.05]")}>
                {(s.logo_url || s.favicon) && (
                  <img src={s.logo_url || s.favicon} alt=""
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                            className="w-full h-full object-cover" />
                )}
              </div>
              <div className="flex-grow min-w-0">
                <div className={"font-semibold text-sm truncate " +
                                            (light ? "text-slate-900" : "text-white")}
                          data-testid={`claim-hub-browse-name-${s.id}`}>
                  {s.name}
                </div>
                <div className={"text-[11px] flex flex-wrap gap-x-3 gap-y-0.5 mt-1 " +
                                            (light ? "text-slate-500" : "text-white/50")}>
                  {s.country && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin size={9} /> {s.country_code || s.country}
                    </span>
                  )}
                  {s.language && <span className="capitalize">{s.language}</span>}
                  {s.is_flagship && (
                    <span className={"font-mono " +
                                            (light ? "text-fuchsia-600" : "text-cyan-300")}>
                      ★ FLAGSHIP
                    </span>
                  )}
                </div>
                <button onClick={() => onClaim(s)}
                                data-testid={`claim-hub-claim-btn-${s.id}`}
                                className={"mt-2 inline-flex items-center gap-1 px-3 h-7 rounded-full text-xs font-semibold " +
                                                      (light
                                                          ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                          : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
                  Claim <ArrowRight size={11} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-5"
                  data-testid="claim-hub-browse-pager">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={page <= 1}
                          data-testid="claim-hub-browse-prev"
                          className={"px-3 h-8 rounded-full text-xs disabled:opacity-40 " +
                                                (light
                                                    ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                    : "bg-white/[0.06] text-white/70 hover:bg-white/[0.10] border border-white/[0.10]")}>
            ← Prev
          </button>
          <span className={"text-xs font-mono " +
                                        (light ? "text-slate-500" : "text-white/40")}>
            {page} / {totalPages}
          </span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                          disabled={page >= totalPages}
                          data-testid="claim-hub-browse-next"
                          className={"px-3 h-8 rounded-full text-xs disabled:opacity-40 " +
                                                (light
                                                    ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                    : "bg-white/[0.06] text-white/70 hover:bg-white/[0.10] border border-white/[0.10]")}>
            Next →
          </button>
        </div>
      )}
    </section>
  );
}


// ─── My Claims Timeline ───────────────────────────────────────
function MyClaimsSection({ variant }) {
  const light = variant === "radiolife";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/radio/claims/my`,
                                                        { withCredentials: true });
      setItems(r.data?.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <section data-testid="claim-hub-my-claims-section"
                    className={"rounded-2xl p-5 mb-6 " + (light
                      ? "bg-white border border-slate-200"
                      : "bg-white/[0.03] border border-white/[0.10]")}>
      <h2 className={"text-lg font-semibold mb-4 " +
                                  (light ? "text-slate-900" : "text-white")}>
        My Pending Claims
        <span className={"ml-2 text-xs font-mono " +
                                    (light ? "text-slate-500" : "text-white/40")}>
          {items.length}
        </span>
      </h2>
      {loading ? (
        <div className={"flex items-center gap-2 py-6 " +
                                      (light ? "text-slate-500" : "text-white/50")}>
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div data-testid="claim-hub-my-claims-empty"
                  className={"rounded-lg p-8 text-center text-sm " +
                                    (light ? "bg-slate-50 text-slate-500 border border-slate-200"
                                                      : "bg-white/[0.02] text-white/50 border border-white/[0.10]")}>
          You haven&apos;t submitted any claims yet. Browse stations above to
          start a claim.
        </div>
      ) : (
        <ol data-testid="claim-hub-my-claims-list"
                className="space-y-2">
          {items.map((c) => {
            const meta = CLAIM_STATUS_META[c.claim_status]
                                    || { icon: AlertTriangle, color: "slate", label: c.claim_status };
            const Icon = meta.icon;
            const colorMap = light ? {
              amber:      "bg-amber-100 text-amber-700 border-amber-200",
              cyan:        "bg-cyan-100 text-cyan-700 border-cyan-200",
              emerald: "bg-emerald-100 text-emerald-700 border-emerald-200",
              rose:        "bg-rose-100 text-rose-700 border-rose-200",
              slate:      "bg-slate-100 text-slate-700 border-slate-200",
            } : {
              amber:      "bg-amber-400/15 text-amber-200 border-amber-400/30",
              cyan:        "bg-cyan-400/15 text-cyan-200 border-cyan-400/30",
              emerald: "bg-emerald-400/15 text-emerald-200 border-emerald-400/30",
              rose:        "bg-rose-400/15 text-rose-200 border-rose-400/30",
              slate:      "bg-white/[0.06] text-white/60 border-white/[0.10]",
            };
            return (
              <li key={c.id} data-claim-id={c.id}
                        data-testid={`claim-hub-my-claim-row-${c.id}`}
                        className={"rounded-xl p-3 flex items-start justify-between gap-3 " +
                                              (light
                                                  ? "bg-slate-50 border border-slate-200"
                                                  : "bg-white/[0.02] border border-white/[0.10]")}>
                <div className="flex-grow min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={"inline-flex items-center gap-1 px-2 h-6 rounded-full text-[10px] font-mono border " +
                                                          colorMap[meta.color]}>
                      <Icon size={10} />
                      {meta.label.toUpperCase()}
                    </span>
                    <span className={"text-[10px] font-mono " +
                                                        (light ? "text-slate-400" : "text-white/40")}>
                      {c.id}
                    </span>
                  </div>
                  <div className={"font-semibold text-sm " +
                                              (light ? "text-slate-900" : "text-white")}>
                    <RadioIcon size={12} className="inline mr-1 mb-0.5" />
                    {c.station_name_snapshot}
                  </div>
                  <div className={"text-[11px] mt-1 " +
                                              (light ? "text-slate-500" : "text-white/50")}>
                    Submitted {new Date(c.created_at).toLocaleString()}
                  </div>
                  {c.admin_rejection_reason && (
                    <div className={"mt-2 text-xs px-2 py-1 rounded " +
                                                        (light
                                                            ? "bg-rose-50 text-rose-700 border border-rose-200"
                                                            : "bg-rose-400/[0.06] text-rose-200 border border-rose-400/20")}>
                      <strong>Reason:</strong> {c.admin_rejection_reason}
                    </div>
                  )}
                </div>
                <Link to={`/claim/station/${c.station_id}`}
                            data-testid={`claim-hub-my-claim-view-${c.id}`}
                            className={"text-[11px] flex-shrink-0 " +
                                                  (light ? "text-fuchsia-600 hover:text-fuchsia-500"
                                                                    : "text-cyan-300 hover:text-cyan-200")}>
                  View →
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}


// ─── My Owned Stations ────────────────────────────────────────
function MyStationsSection({ variant }) {
  const light = variant === "radiolife";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/stations/owner/my-stations`,
                                                        { withCredentials: true });
      setItems(r.data?.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <section data-testid="claim-hub-my-stations-section"
                    className={"rounded-2xl p-5 mb-6 " + (light
                      ? "bg-white border border-slate-200"
                      : "bg-white/[0.03] border border-white/[0.10]")}>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h2 className={"text-lg font-semibold " +
                                    (light ? "text-slate-900" : "text-white")}>
          My Owned Stations
          <span className={"ml-2 text-xs font-mono " +
                                        (light ? "text-slate-500" : "text-white/40")}>
            {items.length}
          </span>
        </h2>
        {items.length > 0 && (
          <Link to="/owner/dashboard"
                      data-testid="claim-hub-open-owner-dashboard"
                      className={"text-xs " +
                                            (light ? "text-fuchsia-600 hover:text-fuchsia-500"
                                                              : "text-cyan-300 hover:text-cyan-200")}>
            Open owner dashboard →
          </Link>
        )}
      </div>
      {loading ? (
        <div className={"flex items-center gap-2 py-6 " +
                                      (light ? "text-slate-500" : "text-white/50")}>
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div data-testid="claim-hub-my-stations-empty"
                  className={"rounded-lg p-8 text-center text-sm " +
                                    (light ? "bg-slate-50 text-slate-500 border border-slate-200"
                                                      : "bg-white/[0.02] text-white/50 border border-white/[0.10]")}>
          You don&apos;t own any stations yet. Once a claim is approved, the
          station will appear here.
        </div>
      ) : (
        <ul data-testid="claim-hub-my-stations-list"
                className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {items.map((s) => (
            <li key={s.id} data-station-id={s.id}
                      data-testid={`claim-hub-my-station-${s.id}`}
                      className={"rounded-xl p-3 flex items-start gap-3 " +
                                              (light
                                                  ? "bg-slate-50 border border-slate-200"
                                                  : "bg-white/[0.02] border border-white/[0.10]")}>
              <div className={"w-12 h-12 rounded-lg flex-shrink-0 overflow-hidden " +
                                            (light ? "bg-slate-200" : "bg-white/[0.05]")}>
                {(s.logo_url || s.favicon) && (
                  <img src={s.logo_url || s.favicon} alt=""
                            onError={(e) => { e.currentTarget.style.display = "none"; }}
                            className="w-full h-full object-cover" />
                )}
              </div>
              <div className="flex-grow min-w-0">
                <div className={"font-semibold text-sm truncate " +
                                            (light ? "text-slate-900" : "text-white")}>
                  <ShieldCheck size={11}
                                              className={"inline mr-1 " +
                                                                    (light ? "text-emerald-600" : "text-emerald-300")} />
                  {s.name}
                </div>
                <div className={"text-[11px] mt-1 flex flex-wrap gap-x-3 " +
                                            (light ? "text-slate-500" : "text-white/50")}>
                  {s.country && <span>{s.country}</span>}
                  {s.language && <span className="capitalize">{s.language}</span>}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Link to={`/owner/dashboard`}
                              data-testid={`claim-hub-manage-${s.id}`}
                              className={"inline-flex items-center gap-1 px-2.5 h-7 rounded-full text-[11px] font-semibold " +
                                                    (light
                                                        ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                        : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
                    Manage
                  </Link>
                  <Link to={`/radio/station/${s.id}`}
                              className={"inline-flex items-center gap-1 px-2.5 h-7 rounded-full text-[11px] " +
                                                    (light
                                                        ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                        : "bg-white/[0.06] text-white/80 hover:bg-white/[0.10] border border-white/[0.10]")}>
                    <ExternalLink size={10} /> View
                  </Link>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}


// ─── Main page ────────────────────────────────────────────────
export default function ClaimRadioHub() {
  const { user, loading: authLoading } = useAuth();
  const variant = useDesignVariant();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [signInFor, setSignInFor] = useState(null);   // { redirectPath }

  const light = variant === "radiolife";

  // Deep-link: /claim-radio?station=<id> triggers the claim-flow start.
  const linkedStation = searchParams.get("station");
  useEffect(() => {
    if (linkedStation && !authLoading) {
      if (!user) {
        setSignInFor({ redirectPath: `/claim/station/${linkedStation}` });
      } else {
        navigate(`/claim/station/${linkedStation}`, { replace: true });
      }
    }
  }, [linkedStation, user, authLoading, navigate]);

  const onClaim = (station) => {
    if (!user) {
      setSignInFor({ redirectPath: `/claim/station/${station.id}` });
      return;
    }
    navigate(`/claim/station/${station.id}`);
  };

  return (
    <div data-testid="claim-hub-page"
              data-variant={variant}
              className={"min-h-[100vh] " + (light
                ? "bg-slate-50 text-slate-900"
                : "bg-[#050507] text-white")}>
      <Toaster theme={light ? "light" : "dark"} richColors
                        position="top-right" />
      <div className="max-w-[1100px] mx-auto px-5 pt-8 pb-24">
        <div className="mb-6">
          <div className={"text-xs uppercase tracking-widest font-mono mb-2 " +
                                        (light ? "text-fuchsia-600" : "text-cyan-300")}>
            Phase CLAIM.1 · Station ownership
          </div>
          <h1 className={"text-3xl sm:text-4xl font-bold tracking-tight " +
                                        (light ? "text-slate-900" : "text-white")}>
            Claim your radio station on RadioLife
          </h1>
          <p className={"text-sm mt-2 max-w-prose " +
                                    (light ? "text-slate-600" : "text-white/60")}>
            Browse the imported catalog, verify your ownership, and
            unlock the owner dashboard.  Listener stats, station
            metadata edits, banner &amp; audio uploads — all in one place.
          </p>
        </div>

        <BrowseGrid variant={variant} onClaim={onClaim} />

        {user ? (
          <>
            <MyClaimsSection variant={variant} />
            <MyStationsSection variant={variant} />
          </>
        ) : (
          <div data-testid="claim-hub-anon-cta"
                    className={"rounded-2xl p-6 mb-6 text-center " +
                                          (light
                                              ? "bg-fuchsia-50 border border-fuchsia-200"
                                              : "bg-cyan-400/[0.06] border border-cyan-400/20")}>
            <p className={"text-sm mb-4 " +
                                        (light ? "text-slate-700" : "text-white/70")}>
              Sign in to see your pending claims and owned stations.
            </p>
            <button onClick={() => setSignInFor({ redirectPath: "/claim-radio" })}
                            data-testid="claim-hub-anon-signin-btn"
                            className={"inline-flex items-center gap-2 px-5 h-11 rounded-full text-sm font-semibold " +
                                                  (light
                                                      ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                      : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
              <LogIn size={14} /> Sign in
            </button>
          </div>
        )}

      </div>

      {signInFor && (
        <ClaimSignInModal
          variant={variant}
          redirectPath={signInFor.redirectPath}
          onClose={() => setSignInFor(null)} />
      )}
    </div>
  );
}
