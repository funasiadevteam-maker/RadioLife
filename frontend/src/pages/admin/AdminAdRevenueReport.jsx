// Admin — Home Audio V2 ad-revenue report (Phase COMPANION.1). Compares
// listening time against the ad funnel (audio, native, sponsored station,
// companion, display) with an estimated-revenue proxy + a per-variant split.
import React, { useEffect, useState } from "react";
import axios from "axios";
import {
  BarChart3, Headphones, Radio, Sparkles, Megaphone, Image as ImageIcon,
  Coins, TrendingUp,
} from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const pct = (r) => `${Math.round((r || 0) * 100)}%`;

function Metric({ icon: Icon, label, big, sub, tint = "text-cyan-300", testid }) {
  return (
    <div className="rounded-2xl bg-slate-900 border border-slate-800 p-4" data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-slate-400 mb-2">
        <Icon className={`w-3.5 h-3.5 ${tint}`} /> {label}
      </div>
      <div className={`text-2xl font-black ${tint}`}>{big}</div>
      {sub && <div className="text-xs text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

export default function AdminAdRevenueReport() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    axios.get(`${API}/admin/ad-revenue/home-report`, { params: { days }, withCredentials: true })
      .then((r) => { if (!cancel) setData(r.data); })
      .catch(() => { if (!cancel) setData(null); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [days]);

  return (
    <div className="min-h-screen bg-slate-950 text-white px-4 py-8" data-testid="admin-ad-revenue">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-purple-400" />
            <h1 className="text-xl font-black">Home Ad Revenue</h1>
          </div>
          <div className="flex gap-1" data-testid="report-range">
            {[1, 7, 30].map((d) => (
              <button key={d} onClick={() => setDays(d)}
                data-testid={`report-range-${d}`}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                  days === d ? "bg-purple-600 border-purple-500 text-white"
                             : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"}`}>
                {d}d
              </button>
            ))}
          </div>
        </div>
        <p className="text-sm text-slate-400 mb-6">
          Audio-first Home monetization: how listening time converts into ad
          engagement and estimated revenue.
        </p>

        {loading ? (
          <div className="text-slate-400 text-sm">Loading report…</div>
        ) : !data ? (
          <div className="text-rose-400 text-sm">Could not load report.</div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <Metric icon={Headphones} label="Listening" tint="text-emerald-300"
                big={`${(data.listening.hours || 0).toLocaleString()}h`}
                sub={`${(data.listening.minutes || 0).toLocaleString()} min`}
                testid="report-listening" />
              <Metric icon={Coins} label="Est. revenue" tint="text-amber-300"
                big={money(data.estimated_revenue_cents)}
                sub={`${money(data.estimated_revenue_per_listening_hour_cents)}/listening hr`}
                testid="report-revenue" />
              <Metric icon={TrendingUp} label="Conversions" tint="text-fuchsia-300"
                big={(data.conversions || 0).toLocaleString()}
                sub="attributed" testid="report-conversions" />
              <Metric icon={Headphones} label="Audio ads" tint="text-cyan-300"
                big={(data.audio_ads.impressions || 0).toLocaleString()}
                sub={`${pct(data.audio_ads.completion_rate)} completed`}
                testid="report-audio" />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <Metric icon={Sparkles} label="Native offer" tint="text-amber-300"
                big={(data.native.impressions || 0).toLocaleString()}
                sub={`${pct(data.native.ctr)} CTR · ${data.native.clicks} clicks`}
                testid="report-native" />
              <Metric icon={Radio} label="Sponsored station" tint="text-sky-300"
                big={(data.sponsored_station.impressions || 0).toLocaleString()}
                sub={`${pct(data.sponsored_station.start_rate)} start · ${data.sponsored_station.starts} starts`}
                testid="report-sponsored" />
              <Metric icon={Megaphone} label="Companion" tint="text-rose-300"
                big={(data.companion.impressions || 0).toLocaleString()}
                sub={`${pct(data.companion.ctr)} CTR · ${data.companion.clicks} clicks`}
                testid="report-companion" />
              <Metric icon={ImageIcon} label="Display banner" tint="text-slate-300"
                big={(data.display.impressions || 0).toLocaleString()}
                sub={`${pct(data.display.ctr)} CTR · ${data.display.clicks} clicks`}
                testid="report-display" />
            </div>

            <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5 mb-4" data-testid="report-variant">
              <h3 className="text-sm font-bold text-white mb-1">Audio V2 vs legacy Home</h3>
              <p className="text-xs text-slate-400 mb-3">{data.variant_note}</p>
              <div className="space-y-2">
                {Object.keys(data.by_variant || {}).length === 0 ? (
                  <div className="text-xs text-slate-500">No Home ad events in this window yet.</div>
                ) : Object.entries(data.by_variant).map(([variant, events]) => (
                  <div key={variant} className="flex items-start justify-between gap-3 text-xs border-t border-slate-800 pt-2">
                    <span className="font-mono font-bold text-purple-300">{variant}</span>
                    <span className="text-slate-400 text-right">
                      {Object.entries(events).map(([e, n]) => `${e.replace(/_/g, " ")}: ${n}`).join(" · ")}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <p className="text-[11px] text-slate-500">
              {data.listening.note} Estimated revenue uses house CPM assumptions
              (audio {data.cpm_assumptions_cents.audio}¢, native {data.cpm_assumptions_cents.native}¢,
              sponsored {data.cpm_assumptions_cents.sponsored_station}¢, display {data.cpm_assumptions_cents.display}¢,
              companion {data.cpm_assumptions_cents.companion}¢ per 1000).
            </p>
          </>
        )}
      </div>
    </div>
  );
}
