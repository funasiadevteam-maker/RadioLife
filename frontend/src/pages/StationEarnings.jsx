/** Phase 41 Session 6.A — Creator Earnings dashboard tab.
 *
 * Rendered inside `StationPage.jsx` for the station owner. Sibling
 * to the Analytics tab. Single round-trip to
 * `/api/stations/{slug}/earnings?window=…` powers the dashboard;
 * Stripe Connect status is fetched once on mount via a dedicated
 * endpoint and refreshed after the (MOCKED) onboarding flow.
 *
 * Stripe Connect + payout requests are MOCKED in this session —
 * marked clearly in the UI ("MOCKED" pill on the CTAs).
 */
import React, { useCallback, useEffect, useState, useMemo } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid,
} from "recharts";
import {
  DollarSign, RefreshCw, ArrowUpRight, ArrowDownRight,
  Wallet, CheckCircle2, AlertCircle, ExternalLink,
  CreditCard, Coins, Megaphone, Mic2, Heart, Briefcase,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const WINDOWS = [
  { key: "7d",  label: "7 days"  },
  { key: "30d", label: "30 days" },
  { key: "90d", label: "90 days" },
  { key: "all", label: "All-time" },
];

const SOURCE_LABELS = {
  banner_impression:    "Banner ads",
  audio_ad_completion:  "Audio ads",
  premium_listen:       "Premium listens",
  tip:                  "Tips",
  direct_deal:          "Direct deals",
};

const SOURCE_COLORS = {
  banner_impression:    "#00d9ff",
  audio_ad_completion:  "#a78bfa",
  premium_listen:       "#10b981",
  tip:                  "#fb7185",
  direct_deal:          "#fbbf24",
};

const SOURCE_ICONS = {
  banner_impression:   <Megaphone size={11} />,
  audio_ad_completion: <Mic2      size={11} />,
  premium_listen:      <Coins     size={11} />,
  tip:                 <Heart     size={11} />,
  direct_deal:         <Briefcase size={11} />,
};

function fmtMoney(cents, currency = "USD") {
  if (cents === undefined || cents === null) return "$0.00";
  const sign = cents < 0 ? "-" : "";
  const dollars = Math.abs(cents) / 100;
  if (dollars >= 100_000) return `${sign}$${(dollars / 1000).toFixed(1)}K`;
  return `${sign}$${dollars.toFixed(2)}`;
}

export default function StationEarnings({ slug }) {
  const [data, setData]       = useState(null);
  const [connect, setConnect] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState(null);
  const [window_, setWindow]  = useState("7d");
  const [busy, setBusy]       = useState(false);

  const load = useCallback(async (selected) => {
    setLoading(true); setErr(null);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/earnings`,
        { params: { window: selected },
          withCredentials: true });
      setData(r.data);
    } catch (e) {
      setErr(e.response?.data?.detail?.code || "error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  const loadConnect = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/me/stripe_connect/status`,
        { withCredentials: true });
      setConnect(r.data || null);
    } catch { setConnect(null); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (!cancelled) { load(window_); loadConnect(); }
    });
    return () => { cancelled = true; };
  }, [load, loadConnect, window_]);

  const onConnect = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/me/stripe_connect/onboard`, {},
        { withCredentials: true });
      const url = r.data?.onboarding_url;
      toast.message("MOCKED Stripe Connect onboarding started",
        { description: "In production this would open Stripe's hosted onboarding. For this MVP we'll flip the status to active automatically." });
      // Dev shim: flip to active so the payout CTA exercises.
      await axios.post(`${API}/me/stripe_connect/activate`, {},
        { withCredentials: true });
      await loadConnect();
      // Open the mock URL in a new tab for visual confirmation
      if (url) window.open(url, "_blank", "noopener");
    } catch (e) {
      toast.error("Could not start onboarding");
    }
    setBusy(false);
  };

  const onRequestPayout = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/me/payout/request`, {},
        { withCredentials: true });
      toast.success(`MOCKED payout requested · ${fmtMoney(r.data.amount_cents)}`,
        { description: "Recorded as a pending row — no real Stripe transfer initiated." });
      await load(window_);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code === "stripe_connect_not_active") {
        toast.error("Connect Stripe first");
      } else if (code === "no_pending_balance") {
        toast.message("Nothing to pay out yet");
      } else {
        toast.error("Payout request failed");
      }
    }
    setBusy(false);
  };

  const headline = data?.headline || {};
  const bySource = useMemo(() => data?.by_source || [], [data]);
  const recent   = data?.recent_ledger || [];
  const connectActive = connect?.stripe_connect_status === "active";
  const connectPending = connect?.stripe_connect_status === "pending";

  const chartData = useMemo(() => bySource.map((s) => ({
    label:         SOURCE_LABELS[s.source_type] || s.source_type,
    source_type:   s.source_type,
    gross_dollars:   (s.gross_cents   || 0) / 100,
    creator_dollars: (s.creator_cents || 0) / 100,
    house_dollars:   ((s.gross_cents || 0) - (s.creator_cents || 0)) / 100,
  })), [bySource]);

  return (
    <div data-testid="station-earnings"
         data-window={window_}
         style={{ marginTop: 28 }}>
      <div style={{ display: "flex", alignItems: "center",
                     justifyContent: "space-between", flexWrap: "wrap",
                     gap: 12, marginBottom: 18 }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
          <DollarSign size={20} color="#10b981" />
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff",
                         margin: 0 }}>
            Earnings
          </h2>
          <span data-testid="earnings-mock-pill"
                title="Stripe Connect + payouts are mocked in this session"
                style={{ display: "inline-flex", alignItems: "center", gap: 4,
                          fontSize: 10, padding: "2px 8px", borderRadius: 999,
                          background: "rgba(251,146,60,0.15)", color: "#fb923c",
                          border: "1px solid rgba(251,146,60,0.35)",
                          fontWeight: 700, letterSpacing: "0.04em",
                          textTransform: "uppercase" }}>
            <AlertCircle size={10} /> MOCKED
          </span>
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <WindowChips active={window_} onChange={setWindow} />
          <button data-testid="earnings-refresh"
                  onClick={() => load(window_)}
                  disabled={loading}
                  title="Refresh"
                  style={{ background: "rgba(255,255,255,0.04)",
                            color: "#cbd5e1",
                            border: "1px solid rgba(255,255,255,0.08)",
                            padding: 8, borderRadius: 6, cursor: "pointer",
                            opacity: loading ? 0.5 : 1 }}>
            <RefreshCw size={13} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      <ConnectBanner connect={connect} onConnect={onConnect}
                       onRequestPayout={onRequestPayout}
                       headline={headline} busy={busy}
                       active={connectActive} pending={connectPending} />

      {err && (
        <div data-testid="earnings-error"
             style={{ padding: 14, borderRadius: 10,
                       background: "rgba(239,68,68,0.08)",
                       border: "1px solid rgba(239,68,68,0.3)",
                       color: "#fca5a5", fontSize: 13 }}>
          Failed to load earnings ({err}).
        </div>
      )}

      <div data-testid="earnings-kpi-row"
           style={{ display: "grid", gap: 12, marginBottom: 16,
                     gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        <KPI testId="kpi-total-earned"
             icon={<Wallet size={14} color="#10b981" />}
             label={`Earned (${window_})`}
             value={fmtMoney(headline.total_creator_cents)}
             loading={loading}
             sub={`${headline.ledger_row_count || 0} ledger rows · 70/30 split`} />
        <KPI testId="kpi-pending-payout"
             icon={<CreditCard size={14} color="#fb923c" />}
             label="Pending payout"
             value={fmtMoney(headline.pending_payout_cents)}
             loading={loading}
             sub={connectActive ? "Ready to request" : "Stripe Connect required"} />
        <KPI testId="kpi-lifetime"
             icon={<ArrowUpRight size={14} color="#00d9ff" />}
             label="Lifetime earnings"
             value={fmtMoney(headline.lifetime_creator_cents)}
             loading={loading}
             sub="Across every window" />
      </div>

      <div style={{ display: "grid", gap: 16,
                     gridTemplateColumns: "minmax(0, 2fr) minmax(220px, 1fr)" }}>
        <SourceBreakdownChart chartData={chartData} loading={loading}
                              window_={window_} />
        <BySourceList items={bySource} loading={loading} />
      </div>

      <LedgerTable rows={recent} loading={loading} />

      <style>{`
        @keyframes spin { from {transform:rotate(0)} to {transform:rotate(360deg)} }
        .spin { animation: spin 1s linear infinite; }
        @keyframes skel { 0% {background-position: 200% 0} 100% {background-position: -200% 0} }
      `}</style>
    </div>
  );
}

function WindowChips({ active, onChange }) {
  return (
    <div data-testid="earnings-window-chips"
         style={{ display: "inline-flex",
                   background: "rgba(255,255,255,0.04)", borderRadius: 8,
                   padding: 3, gap: 2 }}>
      {WINDOWS.map((w) => (
        <button key={w.key}
                data-testid={`earnings-window-${w.key}`}
                data-active={active === w.key ? "true" : "false"}
                onClick={() => onChange(w.key)}
                style={{ padding: "5px 10px", borderRadius: 6,
                          background: active === w.key
                            ? "rgba(16,185,129,0.18)"
                            : "transparent",
                          color: active === w.key ? "#10b981" : "#9aa3af",
                          border: active === w.key
                            ? "1px solid rgba(16,185,129,0.4)"
                            : "1px solid transparent",
                          fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
          {w.label}
        </button>
      ))}
    </div>
  );
}

function ConnectBanner({ connect, onConnect, onRequestPayout, headline,
                          busy, active, pending }) {
  const pendingPayout = headline.pending_payout_cents || 0;
  return (
    <div data-testid="earnings-connect-banner"
         data-connect-status={connect?.stripe_connect_status || "none"}
         style={{ padding: 14, marginBottom: 16, borderRadius: 10,
                   background: active
                     ? "rgba(16,185,129,0.06)"
                     : "rgba(0,217,255,0.05)",
                   border: `1px solid ${active
                     ? "rgba(16,185,129,0.25)"
                     : "rgba(0,217,255,0.2)"}`,
                   display: "grid",
                   gridTemplateColumns: "1fr auto",
                   gap: 12, alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {active
          ? <CheckCircle2 size={18} color="#10b981" />
          : <CreditCard   size={18} color="#00d9ff" />}
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
            {active
              ? "Stripe Connect linked"
              : pending
                ? "Stripe Connect onboarding pending"
                : "Connect Stripe to receive payouts"}
          </div>
          <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 2 }}>
            {active
              ? `Account ${connect?.stripe_connect_account_id?.slice(0, 18) || ""}… · MOCKED`
              : "MOCKED — flips to 'active' after the placeholder onboarding URL."}
          </div>
        </div>
      </div>
      <div style={{ display: "inline-flex", gap: 8 }}>
        {!active && (
          <button data-testid="earnings-connect-stripe-cta"
                  onClick={onConnect} disabled={busy}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6,
                            background: "#00d9ff", color: "#0b0b0b",
                            border: "none", padding: "8px 14px",
                            borderRadius: 6, fontSize: 12, fontWeight: 700,
                            cursor: busy ? "wait" : "pointer",
                            opacity: busy ? 0.6 : 1 }}>
            <ExternalLink size={12} />
            Connect Stripe
          </button>
        )}
        <button data-testid="earnings-request-payout-cta"
                onClick={onRequestPayout}
                disabled={!active || pendingPayout <= 0 || busy}
                title={!active
                  ? "Connect Stripe first"
                  : pendingPayout <= 0
                    ? "No pending balance"
                    : "Request payout (MOCKED)"}
                style={{ display: "inline-flex", alignItems: "center", gap: 6,
                          background: (active && pendingPayout > 0)
                            ? "rgba(16,185,129,0.18)"
                            : "rgba(255,255,255,0.04)",
                          color: (active && pendingPayout > 0)
                            ? "#10b981" : "#6b7280",
                          border: `1px solid ${(active && pendingPayout > 0)
                            ? "rgba(16,185,129,0.4)"
                            : "rgba(255,255,255,0.08)"}`,
                          padding: "8px 14px", borderRadius: 6,
                          fontSize: 12, fontWeight: 700,
                          cursor: (active && pendingPayout > 0)
                            ? "pointer" : "not-allowed" }}>
          <DollarSign size={12} />
          Request payout
        </button>
      </div>
    </div>
  );
}

function KPI({ testId, icon, label, value, loading, sub }) {
  return (
    <div data-testid={testId}
         data-loading={loading ? "true" : "false"}
         style={{ padding: 14, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 96 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6,
                     marginBottom: 6 }}>
        {icon}
        <span style={{ fontSize: 11, color: "#9aa3af",
                          textTransform: "uppercase",
                          letterSpacing: "0.06em", fontWeight: 600 }}>
          {label}
        </span>
      </div>
      {loading ? (
        <Skel w={88} h={28} />
      ) : (
        <div data-testid={`${testId}-value`}
             style={{ fontSize: 26, fontWeight: 800, color: "#fff",
                       lineHeight: 1.1 }}>
          {value}
        </div>
      )}
      {sub && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#6b7280" }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function SourceBreakdownChart({ chartData, loading, window_ }) {
  return (
    <div data-testid="earnings-source-chart"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 280 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                     alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>
          Earnings by source ({window_})
        </div>
        <div style={{ fontSize: 11, color: "#9aa3af" }}>
          your share + house cut
        </div>
      </div>
      {loading ? (
        <Skel w={"100%"} h={220} />
      ) : chartData.length === 0 ? (
        <div data-testid="earnings-source-chart-empty"
             style={{ height: 220, display: "grid", placeItems: "center",
                       color: "#9aa3af", fontSize: 12 }}>
          No earnings in this window yet.
        </div>
      ) : (
        <div style={{ height: 220, width: "100%" }}>
          <ResponsiveContainer>
            <BarChart data={chartData}
                      margin={{ top: 4, right: 16, bottom: 0, left: -8 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)"
                             strokeDasharray="3 4" vertical={false} />
              <XAxis dataKey="label" stroke="#6b7280" fontSize={10}
                     tickLine={false}
                     axisLine={{ stroke: "rgba(255,255,255,0.05)" }} />
              <YAxis stroke="#6b7280" fontSize={10}
                     tickLine={false}
                     axisLine={{ stroke: "rgba(255,255,255,0.05)" }}
                     width={42}
                     tickFormatter={(v) => `$${v.toFixed(0)}`} />
              <Tooltip
                contentStyle={{ background: "#111", border: "1px solid #2a2a2a",
                                  borderRadius: 6, fontSize: 12, color: "#fff" }}
                labelStyle={{ color: "#9aa3af" }}
                formatter={(v, n) =>
                  [`$${Number(v).toFixed(2)}`,
                    n === "creator_dollars" ? "Your share"
                  : n === "house_dollars"   ? "House cut"
                  : "Gross"]} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#9aa3af" }} />
              <Bar dataKey="creator_dollars" stackId="a"
                   fill="#10b981" name="Your share" />
              <Bar dataKey="house_dollars"   stackId="a"
                   fill="rgba(255,255,255,0.12)" name="House cut" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function BySourceList({ items, loading }) {
  return (
    <div data-testid="earnings-by-source-list"
         style={{ padding: 16, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   minHeight: 280 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                     marginBottom: 12 }}>
        Per-source breakdown
      </div>
      {loading ? (
        <div style={{ display: "grid", gap: 8 }}>
          {[1,2,3,4].map((i) => <Skel key={i} w={"100%"} h={36} />)}
        </div>
      ) : items.length === 0 ? (
        <div data-testid="earnings-by-source-empty"
             style={{ color: "#9aa3af", fontSize: 12 }}>
          No revenue routed to your station yet.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          {items.map((s) => (
            <div key={s.source_type}
                 data-testid={`earnings-by-source-${s.source_type}`}
                 style={{ display: "grid",
                           gridTemplateColumns: "1fr auto",
                           alignItems: "center", padding: 8, borderRadius: 6,
                           background: "rgba(255,255,255,0.03)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: SOURCE_COLORS[s.source_type] || "#fff",
                                  display: "inline-flex", alignItems: "center" }}>
                  {SOURCE_ICONS[s.source_type] || null}
                </span>
                <div>
                  <div style={{ fontSize: 12, color: "#fff", fontWeight: 600 }}>
                    {SOURCE_LABELS[s.source_type] || s.source_type}
                  </div>
                  <div style={{ fontSize: 10, color: "#9aa3af" }}>
                    {s.count} row{s.count === 1 ? "" : "s"}
                  </div>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#10b981" }}>
                  {fmtMoney(s.creator_cents)}
                </div>
                <div style={{ fontSize: 10, color: "#6b7280" }}>
                  gross {fmtMoney(s.gross_cents)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LedgerTable({ rows, loading }) {
  return (
    <div data-testid="earnings-ledger-table"
         style={{ marginTop: 16, padding: 0, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   overflow: "hidden" }}>
      <div style={{ padding: "14px 16px", fontSize: 13, fontWeight: 700,
                     color: "#fff",
                     borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        Recent ledger ({rows.length})
      </div>
      {loading ? (
        <div style={{ padding: 14, display: "grid", gap: 6 }}>
          {[1,2,3,4,5].map((i) => <Skel key={i} w={"100%"} h={24} />)}
        </div>
      ) : rows.length === 0 ? (
        <div data-testid="earnings-ledger-empty"
             style={{ padding: 20, fontSize: 12, color: "#9aa3af",
                       textAlign: "center" }}>
          No ledger entries in this window yet.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse",
                            fontSize: 12 }}>
            <thead>
              <tr style={{ color: "#9aa3af", fontWeight: 600 }}>
                <Th>When</Th>
                <Th>Source</Th>
                <Th align="right">Gross</Th>
                <Th align="right">Your share</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.source_ref}
                    data-testid={`ledger-row-${r.source_ref}`}
                    data-status={r.status}
                    style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                  <Td><span style={{ color: "#9aa3af" }}>
                    {fmtDate(r.occurred_at)}</span></Td>
                  <Td>
                    <span style={{ display: "inline-flex", alignItems: "center",
                                       gap: 6 }}>
                      <span style={{ color: SOURCE_COLORS[r.source_type] }}>
                        {SOURCE_ICONS[r.source_type]}
                      </span>
                      {SOURCE_LABELS[r.source_type] || r.source_type}
                    </span>
                  </Td>
                  <Td align="right"><span style={{ color: "#cbd5e1" }}>
                    {fmtMoney(r.gross_amount_cents, r.currency)}</span></Td>
                  <Td align="right"><span style={{ color: "#10b981",
                                                       fontWeight: 700 }}>
                    {fmtMoney(r.creator_amount_cents, r.currency)}</span></Td>
                  <Td>
                    <StatusChip status={r.status} />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({ children, align }) {
  return <th style={{ textAlign: align || "left",
                        padding: "10px 12px",
                        fontSize: 10, letterSpacing: "0.06em",
                        textTransform: "uppercase" }}>{children}</th>;
}
function Td({ children, align }) {
  return <td style={{ textAlign: align || "left",
                        padding: "8px 12px",
                        color: "#cbd5e1" }}>{children}</td>;
}

function StatusChip({ status }) {
  const map = {
    recorded: { bg: "rgba(0,217,255,0.12)", fg: "#00d9ff",  label: "Recorded" },
    paid_out: { bg: "rgba(16,185,129,0.15)", fg: "#10b981", label: "Paid out" },
    reversed: { bg: "rgba(239,68,68,0.12)", fg: "#ef4444",  label: "Reversed" },
  };
  const s = map[status] || map.recorded;
  return (
    <span style={{ display: "inline-block",
                    padding: "2px 8px", borderRadius: 999,
                    background: s.bg, color: s.fg,
                    fontSize: 10, fontWeight: 700,
                    letterSpacing: "0.04em", textTransform: "uppercase" }}>
      {s.label}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(undefined,
      { month: "short", day: "numeric" }) + " · "
      + d.toLocaleTimeString(undefined,
          { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function Skel({ w, h }) {
  return (
    <div aria-hidden style={{
      width: typeof w === "number" ? `${w}px` : w,
      height: typeof h === "number" ? `${h}px` : h,
      borderRadius: 6,
      background: "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 100%)",
      backgroundSize: "200% 100%",
      animation: "skel 1.4s linear infinite",
    }} />
  );
}
