// P1 — Admin FPK coupon-cap dashboard at /admin/fpk-caps.
// Shows per-game, per-discount-tier daily caps vs issued-today vs
// remaining, with a live countdown to the UTC-midnight reset.
import { useEffect, useState } from "react";
import axios from "axios";
import { Loader2, RefreshCw, Ticket } from "lucide-react";
import { CouponScarcityStrip } from "@/components/CouponScarcityStrip";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function Bar({ issued, cap }) {
  const pct = cap ? Math.min(100, Math.round((issued / cap) * 100)) : 0;
  const hot = pct >= 80;
  return (
    <div className="h-2 rounded-full bg-slate-800 overflow-hidden w-full">
      <div className="h-full rounded-full transition-all"
           style={{ width: `${pct}%`, background: hot ? "#ef4444" : "#0aa54b" }} />
    </div>
  );
}

export default function FpkCouponCaps() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/admin/fpk/coupon-caps`)
      .then((r) => { setData(r.data); setError(null); })
      .catch((e) => setError(e?.response?.data?.detail || e.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="fpk-caps-page">
      <div className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-[10px] font-black uppercase tracking-widest text-emerald-400">Admin · FPK</div>
            <h1 className="text-3xl font-black tracking-tight flex items-center gap-2">
              <Ticket className="w-7 h-7" /> Coupon cap dashboard
            </h1>
            <p className="text-sm text-slate-400 mt-1">Per-day coupon issuance across all FPK sponsored games.</p>
          </div>
          <button onClick={load} disabled={loading} data-testid="fpk-caps-refresh"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 text-sm font-black disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />} Refresh
          </button>
        </div>

        {error ? (
          <div className="mt-6 rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm" data-testid="fpk-caps-error">
            {String(error)}
          </div>
        ) : !data ? (
          <div className="mt-8 flex items-center gap-2 text-slate-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
        ) : (
          <>
            {/* Totals */}
            <div className="mt-6 rounded-2xl bg-slate-900/70 border border-white/10 p-5 flex items-center justify-between gap-4 flex-wrap" data-testid="fpk-caps-totals">
              <div className="flex gap-8">
                <Stat label="Daily cap" value={data.totals.daily_cap ?? "∞"} />
                <Stat label="Issued today" value={data.totals.issued_today} />
                <Stat label="Remaining" value={data.totals.remaining_today ?? "∞"} accent />
              </div>
              <CouponScarcityStrip remaining={data.totals.remaining_today} resetsAt={data.resets_at}
                                   accent="#0aa54b" testId="fpk-caps-scarcity" />
            </div>

            {/* Per game */}
            <div className="mt-6 space-y-4">
              {data.games.map((g) => (
                <div key={g.campaign_id} className="rounded-2xl bg-slate-900/70 border border-white/10 p-5" data-testid={`fpk-game-${g.campaign_id}`}>
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="font-black text-lg">{g.title}</div>
                    <div className="text-xs text-slate-400 font-mono">
                      {g.issued_today}/{g.daily_cap ?? "∞"} issued
                      {g.remaining_today !== null && <span className="ml-2 text-emerald-400">· {g.remaining_today} left</span>}
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {g.tiers.map((t) => (
                      <div key={t.prize_id} className="rounded-xl bg-slate-950/60 border border-white/5 p-3" data-testid={`fpk-tier-${t.prize_id}`}>
                        <div className="flex items-center justify-between">
                          <div className="font-black text-emerald-400">{t.percent_off}% off</div>
                          <div className="text-[11px] font-mono text-slate-400">
                            {t.issued_today}/{t.daily_cap ?? "∞"}
                          </div>
                        </div>
                        <div className="mt-2"><Bar issued={t.issued_today} cap={t.daily_cap || 0} /></div>
                        <div className="mt-1.5 text-[11px] text-slate-500">
                          {t.remaining_today !== null ? `${t.remaining_today} left today` : "Unlimited today"}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">{label}</div>
      <div className={`text-2xl font-black ${accent ? "text-emerald-400" : ""}`}>{value}</div>
    </div>
  );
}
