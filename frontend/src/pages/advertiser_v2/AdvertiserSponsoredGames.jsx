// Phase AD.2 — Advertiser Sponsored Games spend history + per-campaign roll-ups.
// Route: /advertiser/dashboard/sponsored-games   (inside AdvertiserShell)
import { useEffect, useState } from "react";
import axios from "axios";
import { Gamepad2, TrendingUp, PauseCircle, ArrowRight, Loader2,
                  AlertTriangle, Info } from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmtCents = (c) => (c == null ? "—" : `$${(c / 100).toFixed(2)}`);

export default function AdvertiserSponsoredGames() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser } = useAdvertiser() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!advertiser?.advertiser_id) return;
    setLoading(true);
    axios.get(`${API}/advertiser/${advertiser.advertiser_id}/game-transactions`,
                          { withCredentials: true })
      .then((r) => { setData(r.data); setError(null); })
      .catch((e) => setError(e?.response?.data?.detail?.code
                                                  || e?.response?.data?.detail
                                                  || e.message))
      .finally(() => setLoading(false));
  }, [advertiser]);

  if (!advertiser) {
    return (
      <div className={`p-8 max-w-5xl mx-auto ${light ? "text-slate-900" : "text-white"}`}
                data-testid="advertiser-sponsored-games-no-advertiser">
        <div className="text-sm">Select an advertiser to view sponsored-game spend.</div>
      </div>
    );
  }

  const cardCls = light
    ? "bg-white border border-slate-200"
    : "bg-slate-900/60 border border-slate-800";
  const mutedCls = light ? "text-slate-500" : "text-slate-400";
  const kbdCls    = light ? "text-slate-900" : "text-white";

  return (
    <div className={`p-6 lg:p-10 max-w-6xl mx-auto space-y-6 ${light ? "text-slate-900" : "text-white"}`}
              data-testid="advertiser-sponsored-games-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className={`text-[10px] font-black uppercase tracking-widest ${
            light ? "text-amber-600" : "text-amber-500"
          }`}>Phase AD.2 · Revenue split</div>
          <h1 className="mt-1 text-3xl lg:text-4xl font-black tracking-tight inline-flex items-center gap-2"
                    data-testid="advertiser-sponsored-games-title">
            <Gamepad2 className={`w-7 h-7 ${light ? "text-amber-500" : "text-amber-400"}`} />
            Sponsored games
          </h1>
          <p className={`mt-1 text-sm ${mutedCls}`}>
            Per-event CPM/CPC spend routed to merchant Stripe Connect accounts.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm py-8"
                    data-testid="advertiser-sponsored-games-loading">
          <Loader2 className="animate-spin w-4 h-4" /> Loading…
        </div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2"
                    data-testid="advertiser-sponsored-games-error">
          <AlertTriangle className="w-4 h-4" /> {String(error)}
        </div>
      ) : (
        <>
          {/* Totals strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4"
                      data-testid="advertiser-sponsored-games-totals">
            <StatCard label="Total events"
                                icon={<TrendingUp className="w-4 h-4" />}
                                value={data.totals.events}
                                light={light} testid="sg-total-events" />
            <StatCard label="Gross spend"
                                value={fmtCents(data.totals.gross_cents)}
                                light={light} accent testid="sg-total-gross" />
            <StatCard label="Merchant share"
                                value={fmtCents(data.totals.merchant_cents)}
                                light={light} testid="sg-total-merchant" />
            <StatCard label="Platform fee"
                                value={fmtCents(data.totals.platform_cents)}
                                light={light} testid="sg-total-platform" />
          </div>

          {/* Per-campaign table */}
          <div className={`${cardCls} rounded-2xl overflow-hidden`}
                      data-testid="advertiser-sponsored-games-table">
            <div className={`px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                        light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                      : "text-slate-500 bg-slate-950 border-b border-slate-800"
                                    } hidden md:grid grid-cols-[2fr,1fr,120px,110px,110px,110px]`}>
              <div>Game & Merchant</div>
              <div>Status</div>
              <div className="text-right">Events</div>
              <div className="text-right">Gross</div>
              <div className="text-right">Merchant</div>
              <div className="text-right">Platform</div>
            </div>
            {data.per_campaign.length === 0 ? (
              <div className={`py-10 text-center text-sm ${mutedCls}`}
                          data-testid="advertiser-sponsored-games-empty">
                <Info className="w-5 h-5 mx-auto mb-2 opacity-60" />
                No sponsored-game events yet. Approve a sponsored_game
                campaign linked to a merchant’s game to start billing.
              </div>
            ) : (
              data.per_campaign.map((row) => {
                const paused = row.sponsor_paused_reason === "wallet_exhausted";
                return (
                  <div key={row.game_campaign_id}
                                className={`grid md:grid-cols-[2fr,1fr,120px,110px,110px,110px] gap-3 px-5 py-4 items-center ${
                                          light ? "border-b border-slate-100"
                                                        : "border-b border-slate-800"
                                      }`}
                                data-testid={`sg-row-${row.game_campaign_id}`}>
                    <div className="min-w-0">
                      <div className={`font-semibold truncate ${kbdCls}`}>
                        {row.game_campaign_name || "(unnamed)"}</div>
                      <div className={`text-xs truncate ${mutedCls}`}>
                        {row.merchant_name || "—"} · last event {
                          row.last_event_at ? new Date(row.last_event_at).toLocaleString() : "—"
                        }
                      </div>
                    </div>
                    <div>
                      {paused ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider bg-red-500/15 text-red-400"
                                      data-testid={`sg-row-${row.game_campaign_id}-paused`}>
                          <PauseCircle className="w-3 h-3" /> Auto-paused
                        </span>
                      ) : (
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider ${
                                                          light ? "bg-emerald-500/15 text-emerald-600"
                                                                        : "bg-emerald-500/15 text-emerald-400"}`}
                                      data-testid={`sg-row-${row.game_campaign_id}-active`}>
                          Live
                        </span>
                      )}
                    </div>
                    <div className={`text-sm font-mono text-right ${kbdCls}`}>
                      {row.events} <span className={`${mutedCls} text-[10px]`}>({row.impressions}i · {row.entries}c)</span>
                    </div>
                    <div className={`text-sm font-mono text-right ${kbdCls}`}>{fmtCents(row.gross_cents)}</div>
                    <div className={`text-sm font-mono text-right ${light ? "text-emerald-600" : "text-emerald-400"}`}>{fmtCents(row.merchant_cents)}</div>
                    <div className={`text-sm font-mono text-right ${mutedCls}`}>{fmtCents(row.platform_cents)}</div>
                  </div>
                );
              })
            )}
          </div>

          {/* Recent events list */}
          {data.recent_events.length > 0 && (
            <div className={`${cardCls} rounded-2xl overflow-hidden`}
                        data-testid="advertiser-sponsored-games-recent-events">
              <div className={`px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                              light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                            : "text-slate-500 bg-slate-950 border-b border-slate-800"
                                          }`}>
                Recent events · latest {Math.min(50, data.recent_events.length)}
              </div>
              <div className="max-h-96 overflow-y-auto">
                {data.recent_events.slice(0, 50).map((ev) => (
                  <div key={ev.transaction_id}
                                className={`flex items-center justify-between gap-3 px-5 py-3 text-sm ${
                                          light ? "border-b border-slate-100" : "border-b border-slate-800"
                                      }`}
                                data-testid={`sg-event-${ev.transaction_id}`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded ${
                                                          ev.event_source === "game_impression"
                                                              ? "bg-blue-500/15 text-blue-400"
                                                              : "bg-purple-500/15 text-purple-400"
                                                        }`}>{ev.event_source.replace("game_", "")}</span>
                      <span className={`truncate ${mutedCls} text-xs font-mono`}>{ev.game_campaign_id}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs font-mono flex-shrink-0">
                      <span className={mutedCls}>{new Date(ev.created_at).toLocaleTimeString()}</span>
                      <span className={kbdCls}>{fmtCents(ev.amount_cents)}</span>
                      <ArrowRight className={`w-3 h-3 ${mutedCls}`} />
                      <span className={light ? "text-emerald-600" : "text-emerald-400"}>
                        {fmtCents(ev.merchant_net_cents)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, icon, light, accent, testid }) {
  return (
    <div className={`rounded-xl p-4 ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
              data-testid={testid}>
      <div className={`text-[10px] uppercase tracking-widest font-mono flex items-center gap-1 ${
                                  light ? "text-slate-500" : "text-slate-500"}`}>
        {icon} {label}
      </div>
      <div className={`mt-2 text-2xl font-black ${
                                  accent ? (light ? "text-amber-600" : "text-amber-400")
                                                    : (light ? "text-slate-900" : "text-white")}`}>
        {value}
      </div>
    </div>
  );
}
