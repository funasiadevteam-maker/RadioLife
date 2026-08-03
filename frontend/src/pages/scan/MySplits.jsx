// Phase E — AD.7.1 Split-the-bill: my splits list.
// Route: /my/splits
//
// Shows the current user's splits (as initiator OR as a participant),
// filtered by status.  Includes progress bar (paid vs remaining shares)
// and quick-copy invite URLs for the initiator role.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Users, ArrowLeft, Sparkles, Copy, CheckCircle2, Clock,
  XCircle, Filter, Wallet,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";


const STATUSES = [
  { key: "",            label: "All" },
  { key: "pending",    label: "Pending" },
  { key: "partial",    label: "Partial" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
  { key: "expired",    label: "Expired" },
];


export default function MySplits() {
  const { user } = useAuth();
  const nav = useNavigate();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [state, setState] = useState({ items: null, loading: true, error: null });
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!user) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/scan-to-pay/splits/mine${status ? `?status=${status}` : ""}`,
          { withCredentials: true });
        if (!cancelled) setState({ items: r.data.items || [], loading: false });
      } catch (err) {
        if (!cancelled) setState({
          items: [], loading: false,
          error: err?.response?.data?.detail?.code || err.message });
      }
    })();
    return () => { cancelled = true; };
  }, [status, user]);

  const bg = light ? "bg-slate-50 text-slate-900"
                                        : "bg-slate-950 text-white";
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  if (!user) {
    return (
      <div className={`${bg} min-h-screen p-8`}
                data-testid="my-splits-anon">
        Please sign in to see your bill splits.
        <div className="mt-3">
          <Link to="/auth?redirect=/my/splits"
                      className="text-xs text-fuchsia-500 hover:underline">
            Sign in →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={`${bg} min-h-screen`}
              data-testid="my-splits-page"
              data-variant={variant}>
      <div className="max-w-2xl mx-auto px-4 py-6">
        <button onClick={() => nav(-1)}
                        className={`inline-flex items-center gap-1 text-xs ${muted}
                                              hover:opacity-80 mb-4`}
                        data-testid="my-splits-back">
          <ArrowLeft size={12} /> Back
        </button>

        <div className="flex items-center justify-between mb-1">
          <h1 className="text-2xl font-black inline-flex items-center gap-2">
            <Wallet size={20} className="text-fuchsia-500" />
            My splits
          </h1>
          <span className={`text-[11px] font-mono ${muted}`}>
            {state.items?.length ?? "…"} total
          </span>
        </div>
        <p className={`text-xs ${muted} mb-4`}>
          Bills you&apos;ve started or been invited to.
        </p>

        {/* Status filter */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {STATUSES.map((st) => (
            <button key={st.key || "all"}
                            onClick={() => setStatus(st.key)}
                            data-testid={`my-splits-filter-${st.key || "all"}`}
                            className={`text-[10px] font-mono uppercase tracking-widest
                                                        px-3 py-1.5 rounded-full border transition ${
                                                            status === st.key
                                                                ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-500"
                                                                : light
                                                                    ? "border-slate-200 text-slate-600 hover:bg-slate-100"
                                                                    : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
              {st.label}
            </button>
          ))}
        </div>

        {state.loading ? (
          <div className={`inline-flex items-center gap-2 ${muted}`}
                      data-testid="my-splits-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : state.error ? (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40
                                        text-red-400 text-sm"
                      data-testid="my-splits-error">
            {String(state.error)}
          </div>
        ) : state.items.length === 0 ? (
          <div className={`${card} rounded-2xl p-8 text-center`}
                      data-testid="my-splits-empty">
            <div className={`text-sm ${muted}`}>No splits yet.</div>
            <div className={`text-[11px] ${muted} mt-1`}>
              Start one from a scan-to-pay confirmation.
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {state.items.map((sp) => (
              <SplitRow key={sp.split_id} split={sp} light={light}
                                    isMine={sp.role === "initiator"} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


function SplitRow({ split, light, isMine }) {
  const paid = (split.shares || []).filter((x) => x.status === "paid").length;
  const total = (split.shares || []).length;
  const pct = total > 0 ? Math.round((paid / total) * 100) : 0;
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    pending:      light ? "text-slate-600" : "text-slate-300",
    partial:      "text-fuchsia-500",
    completed:  "text-emerald-500",
    cancelled:  "text-red-500",
    expired:      "text-amber-500",
  }[split.status] || "text-slate-400";

  const [copied, setCopied] = useState(null);
  const copyUrl = async (id, url) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(id);
      setTimeout(() => setCopied(null), 1200);
    } catch { /* ignore */ }
  };

  return (
    <div className={`${card} rounded-2xl p-4`}
              data-testid={`my-splits-row-${split.split_id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
            {isMine ? "You started" : "Invited by initiator"}
          </div>
          <div className="text-sm font-black truncate">
            {split.merchant?.business_name || split.merchant_id || "Merchant"}
          </div>
          {split.description && (
            <div className={`text-[11px] ${muted} truncate mt-0.5`}>
              {split.description}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
            {split.currency?.toUpperCase()}
          </div>
          <div className="text-lg font-black tabular-nums"
                      data-testid={`my-splits-total-${split.split_id}`}>
            {(split.total_amount_cents / 100).toFixed(2)}
          </div>
        </div>
      </div>

      {/* progress */}
      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{paid}/{total} shares paid</span>
          <span className={statusColor}
                      data-testid={`my-splits-status-${split.split_id}`}>
            {split.status?.toUpperCase()}
          </span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500
                                        transition-all"
                      style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* per-share list (only meaningful for the initiator) */}
      {isMine && (
        <div className="mt-3 space-y-1.5">
          {(split.shares || []).map((sh) => {
            const url = split.invite_urls?.[sh.share_id];
            return (
              <div key={sh.share_id}
                          className={`flex items-center justify-between text-xs
                                                    ${light ? "bg-slate-50" : "bg-slate-950/40"}
                                                    rounded px-2 py-1.5`}
                          data-testid={`my-splits-share-${sh.share_id}`}>
                <div className="min-w-0 flex-1 flex items-center gap-2">
                  <StatusIcon status={sh.status} />
                  <span className="truncate">{sh.display_name || "Guest"}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono tabular-nums">
                    {(sh.share_amount_cents / 100).toFixed(2)}
                  </span>
                  {url && sh.status !== "paid" && (
                    <button onClick={() => copyUrl(sh.share_id, url)}
                                    data-testid={`my-splits-copy-${sh.share_id}`}
                                    className={`inline-flex items-center gap-1 text-[10px]
                                                                px-2 py-1 rounded ${
                                                                    copied === sh.share_id ? "text-emerald-500"
                                                                                                            : light ? "text-slate-600 hover:bg-slate-200"
                                                                                                                        : "text-slate-300 hover:bg-slate-800/60"}`}>
                      <Copy size={10} />
                      {copied === sh.share_id ? "Copied" : "Copy"}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className={`mt-3 text-[10px] font-mono ${muted}`}>
        Created {formatTime(split.created_at)} · {isMine ? "initiator" : "payer"}
      </div>
    </div>
  );
}


function StatusIcon({ status }) {
  if (status === "paid")
    return <CheckCircle2 size={12} className="text-emerald-500" />;
  if (status === "expired")
    return <Clock size={12} className="text-amber-500" />;
  if (status === "cancelled")
    return <XCircle size={12} className="text-red-500" />;
  if (status === "claimed")
    return <Users size={12} className="text-fuchsia-500" />;
  return <Clock size={12} className="text-slate-400" />;
}
function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined,
      { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch { return iso; }
}
