// Phase AD.3 bundle — Auction Transparency Panel.
// Route: /advertiser/dashboard/auction-insights
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Search, ArrowUpRight, TrendingUp, AlertTriangle,
  ChevronDown, CheckCircle2,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


const REASON_STYLES = {
  higher_cpm:                          { label: "Higher CPM",              color: "text-amber-400 bg-amber-500/15 border-amber-500/30" },
  targeting_mismatch:            { label: "Targeting mismatch", color: "text-blue-400 bg-blue-500/15 border-blue-500/30" },
  wallet_exhausted:                { label: "Wallet drained",        color: "text-red-400 bg-red-500/15 border-red-500/30" },
  priority_boost_lower:      { label: "Lower boost",              color: "text-fuchsia-400 bg-fuchsia-500/15 border-fuchsia-500/30" },
  disqualified_creative:  { label: "Creative issue",          color: "text-slate-400 bg-slate-500/15 border-slate-500/30" },
};

const AD_TYPE_LABEL = {
  banner:                                          "Banner",
  advertiser_pw_sponsorship:  "PW Sponsorship",
  pw_sponsorship:                            "PW Sponsorship",
  notification:                              "Notification",
  coupon_campaign:                        "Coupon",
};


export default function AdvertiserAuctionInsights() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser } = useAdvertiser() || {};
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [flash, setFlash] = useState(null);

  const load = useCallback(async () => {
    if (!advertiser) return;
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/advertiser/${advertiser.advertiser_id}/auction-insights?hours=${hours}`,
        { withCredentials: true });
      setData(r.data);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }, [advertiser, hours]);

  useEffect(() => { load(); }, [load]);

  const boost = async (row) => {
    setBusyId(row.event_id);
    setFlash(null);
    try {
      // Suggested bid = winner_bid + 1¢ (never below current bid).
      const target = Math.max(row.bid_cents + 1, row.winner_bid_cents + 1);
      const r = await axios.post(
        `${API}/advertiser/${advertiser.advertiser_id}/auction-insights/boost`,
        { ad_type: row.ad_type, campaign_id: row.campaign_id,
          new_bid_cents: target },
        { withCredentials: true });
      setFlash({
        event_id: row.event_id,
        message: r.data.requires_reapproval
          ? `Bid raised ${row.bid_cents}¢ → ${target}¢. Change > 20% — sent back to admin review.`
          : `Bid raised ${row.bid_cents}¢ → ${target}¢. Live immediately.`,
      });
      load();
    } catch (err) {
      setFlash({
        event_id: row.event_id,
        error: true,
        message: err?.response?.data?.detail?.code || err.message,
      });
    } finally { setBusyId(null); }
  };

  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const card = light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  const totals = useMemo(() => {
    if (!data?.items) return null;
    return {
      losses:              data.items.length,
      shortfall_avg:  Math.round((data.items.reduce((s, r) => s + r.shortfall_cents, 0)
                                                        / Math.max(1, data.items.length))),
      by_reason:        data.by_reason || {},
    };
  }, [data]);

  if (!advertiser) return <div className={`${bg} p-8 min-h-screen`}>
    <div className={muted}>Loading…</div></div>;

  return (
    <div className="space-y-6" data-testid="auction-insights-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Auction Transparency
          </div>
          <h1 className="text-3xl font-black inline-flex items-center gap-2 mt-1">
            <Search className="w-7 h-7 text-amber-500" />
            Auction Insights
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            The last {hours}h of auctions your campaigns entered — with
            exactly why you lost and a one-tap fix.
          </p>
        </div>
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))}
                        data-testid="auction-insights-window"
                        className={light
                          ? "px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
                          : "px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700"}>
          <option value={24}>Last 24 hours</option>
          <option value={72}>Last 3 days</option>
          <option value={168}>Last 7 days</option>
          <option value={720}>Last 30 days</option>
        </select>
      </div>

      {loading ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading auction log…
        </div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm">
          {String(error)}
        </div>
      ) : (
        <>
          {/* Reason summary chips */}
          {totals && Object.keys(totals.by_reason || {}).length > 0 && (
            <div className="flex flex-wrap gap-2"
                        data-testid="auction-insights-reason-chips">
              {Object.entries(totals.by_reason).map(([r, c]) => {
                const st = REASON_STYLES[r] || REASON_STYLES.higher_cpm;
                return (
                  <div key={r}
                              data-testid={`auction-insights-reason-${r}`}
                              className={`px-3 py-1.5 rounded-full text-[11px] font-mono border ${st.color}`}>
                    {st.label} · <span className="font-black">{c}</span>
                  </div>
                );
              })}
            </div>
          )}

          {(data?.items || []).length === 0 ? (
            <div className={`rounded-2xl px-6 py-14 text-center ${card}`}
                        data-testid="auction-insights-empty">
              <CheckCircle2 className={`w-10 h-10 mx-auto mb-3 ${muted}`} />
              <div className="font-black">No auction losses in this window.</div>
              <p className={`text-sm mt-1 ${muted}`}>
                You&rsquo;re winning every slot you entered.  Consider
                launching more campaigns to expand reach.
              </p>
            </div>
          ) : (
            <div className={`rounded-2xl overflow-hidden ${card}`}
                        data-testid="auction-insights-table">
              <div className={`hidden md:grid grid-cols-[110px,110px,140px,110px,120px,120px,140px] gap-3 px-4 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                              light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                            : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
                <div>Ad type</div><div>Slot</div><div>Reason</div>
                <div>Your bid</div><div>Winner bid</div><div>Shortfall</div>
                <div>Action</div>
              </div>
              {data.items.map((row, i) => {
                const st = REASON_STYLES[row.reason] || REASON_STYLES.higher_cpm;
                const showBoost = row.reason === "higher_cpm"
                                                    || row.reason === "priority_boost_lower";
                return (
                  <div key={row.event_id}
                                data-testid={`auction-insights-row-${i}`}
                                className={`grid md:grid-cols-[110px,110px,140px,110px,120px,120px,140px] gap-3 px-4 py-3 items-center text-xs ${
                                                            light ? "border-b border-slate-100 last:border-0"
                                                                          : "border-b border-slate-800 last:border-0"}`}>
                    <div className="font-mono">{AD_TYPE_LABEL[row.ad_type] || row.ad_type}</div>
                    <div className="font-mono truncate opacity-70">{row.slot_id}</div>
                    <div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-black tracking-widest border ${st.color}`}>
                        {st.label}
                      </span>
                    </div>
                    <div className="font-mono">{row.bid_cents}¢</div>
                    <div className="font-mono font-black">{row.winner_bid_cents}¢</div>
                    <div className="font-mono text-amber-500 inline-flex items-center gap-1">
                      <TrendingUp size={11} /> +{row.shortfall_cents}¢
                    </div>
                    <div>
                      {showBoost && row.campaign_id ? (
                        <button onClick={() => boost(row)}
                                        disabled={busyId === row.event_id}
                                        data-testid={`auction-insights-boost-${row.event_id}`}
                                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-black bg-amber-500 text-slate-900 hover:bg-amber-400 disabled:opacity-40">
                          {busyId === row.event_id
                            ? <Loader2 size={11} className="animate-spin" />
                            : <ArrowUpRight size={11} />}
                          Boost +{Math.max(1, row.winner_bid_cents - row.bid_cents + 1)}¢
                        </button>
                      ) : (
                        <span className={`text-[10px] ${muted}`}>—</span>
                      )}
                      {flash?.event_id === row.event_id && (
                        <div className={`mt-1 text-[10px] font-mono ${flash.error ? "text-red-400" : "text-emerald-400"}`}
                                    data-testid={`auction-insights-boost-result-${row.event_id}`}>
                          {flash.error && <AlertTriangle size={10} className="inline mr-1" />}
                          {flash.message}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
