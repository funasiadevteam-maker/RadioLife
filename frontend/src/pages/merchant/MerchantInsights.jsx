// Phase S — Merchant Insights (foot-traffic view).
// Standalone route at /merchant/insights inside MerchantShell.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useMerchant } from "@/pages/merchant/MerchantShell";
import { Loader2, Activity, Users, MapPin, Clock, Calendar,
                 TrendingUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function MerchantInsights() {
  const { merchant, light } = useMerchant();
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState(null);

  const bizId = merchant?.business_id
                || merchant?.merchant_id
                || merchant?.id;

  const load = useCallback(async (refresh = false) => {
    if (!bizId) return;
    setBusy(true);
    setErr(null);
    try {
      const q = new URLSearchParams({ days: String(days) });
      if (refresh) q.set("refresh", "true");
      const { data: d } = await axios.get(
        `${API}/merchant/${bizId}/location-intel/foot-traffic?${q}`,
        { withCredentials: true });
      setData(d);
    } catch (e) {
      const code = e?.response?.data?.detail?.code
                        || e?.response?.data?.detail
                        || e.message;
      setErr(code);
      if (code !== "business_has_no_location")
        toast.error(`Load insights: ${code}`);
    } finally {
      setBusy(false);
    }
  }, [bizId, days]);

  useEffect(() => { load(false); }, [load]);

  const bg = light ? "bg-white" : "bg-slate-900/60";
  const border = light ? "border-slate-200" : "border-slate-800";
  const textDim = light ? "text-slate-600" : "text-slate-400";

  const maxHod = data?.hour_of_day_histogram
    ? Math.max(1, ...data.hour_of_day_histogram) : 1;
  const maxDow = data?.day_of_week_histogram
    ? Math.max(1, ...data.day_of_week_histogram) : 1;

  return (
    <div data-testid="merchant-insights-page">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-5">
        <div>
          <div className={`text-[10px] font-mono uppercase tracking-widest ${
              light ? "text-cyan-600" : "text-cyan-400"}`}>
            Phase S · Location Intelligence
          </div>
          <h1 className="mt-1 text-2xl md:text-3xl xl:text-4xl font-black tracking-tight
                                      inline-flex items-center gap-2">
            <MapPin className={`w-6 h-6 xl:w-8 xl:h-8 ${
                light ? "text-cyan-600" : "text-cyan-400"}`} />
            Foot-traffic insights
          </h1>
          {data && (
            <div className={`mt-1 text-sm ${textDim}`}>
              {data.business_name} · {data.business_city}
              {" · within "}
              {data.nearby_radius_meters}m of your location
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <select value={days}
                          onChange={(e) => setDays(parseInt(e.target.value, 10))}
                          data-testid="merchant-insights-days"
                          className={`px-3 py-1.5 rounded-full text-xs border ${border} ${
                              light ? "bg-white text-slate-900"
                                        : "bg-slate-900 text-slate-100"}`}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button onClick={() => load(true)}
                          disabled={busy}
                          data-testid="merchant-insights-refresh"
                          className="px-3 py-1.5 rounded-full text-xs font-bold bg-cyan-500 text-slate-950
                                                hover:bg-cyan-400 disabled:opacity-50">
            {busy ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {err === "business_has_no_location" ? (
        <div className={`rounded-2xl border ${border} ${bg} p-8 text-center`}
                  data-testid="merchant-insights-no-location">
          <MapPin className="w-8 h-8 mx-auto text-amber-500" />
          <div className="mt-3 font-bold">No location on file for this business.</div>
          <div className={`text-xs mt-1 ${textDim}`}>
            Add your primary location under Profile → Address to unlock
            foot-traffic insights.
          </div>
        </div>
      ) : busy && !data ? (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading insights…
        </div>
      ) : !data ? (
        <div className={`rounded-2xl border ${border} ${bg} p-6 text-sm ${textDim}`}
                  data-testid="merchant-insights-empty">
          Insights unavailable right now.
        </div>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"
                    data-testid="merchant-insights-kpis">
            <MiniKpi Icon={Activity} label="Nearby pings"
                            value={data.nearby_pings_count}
                            tint="text-cyan-400" light={light}
                            testid="merchant-insights-kpi-pings" />
            <MiniKpi Icon={Users} label="Unique users"
                            value={data.unique_nearby_users}
                            tint="text-emerald-400" light={light}
                            testid="merchant-insights-kpi-users" />
            <MiniKpi Icon={TrendingUp} label="Scan-to-pay txns"
                            value={data.scan_to_pay_txns_count}
                            tint="text-amber-400" light={light}
                            testid="merchant-insights-kpi-txns" />
            <MiniKpi Icon={TrendingUp} label="Linked from pings"
                            value={data.scan_to_pay_conversions_from_nearby_pings}
                            tint="text-fuchsia-400" light={light}
                            testid="merchant-insights-kpi-linked"
                            hint={`≤ ${data.conversion_window_minutes} min after ping`} />
          </div>

          {/* Histograms + clusters */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
            <div className={`rounded-2xl border ${border} ${bg} p-4`}
                      data-testid="merchant-insights-hod">
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-4 h-4 text-cyan-500" />
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
                  Hour of day
                </div>
              </div>
              <div className="grid grid-cols-12 gap-1 items-end h-32">
                {data.hour_of_day_histogram.map((n, h) => (
                  <div key={h} className="flex flex-col items-center gap-1"
                            data-testid={`merchant-insights-hod-${h}`}>
                    <div className="w-full rounded-t bg-cyan-500/70 relative"
                              style={{ height: `${(n / maxHod) * 100}%`,
                                            minHeight: n ? "2px" : "0" }}>
                    </div>
                    <div className={`text-[9px] font-mono ${textDim} tabular-nums`}>
                      {String(h).padStart(2, "0")}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className={`rounded-2xl border ${border} ${bg} p-4`}
                      data-testid="merchant-insights-dow">
              <div className="flex items-center gap-2 mb-3">
                <Calendar className="w-4 h-4 text-cyan-500" />
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
                  Day of week
                </div>
              </div>
              <div className="grid grid-cols-7 gap-1 items-end h-32">
                {data.day_of_week_histogram.map((n, d) => (
                  <div key={d} className="flex flex-col items-center gap-1"
                            data-testid={`merchant-insights-dow-${d}`}>
                    <div className="w-full rounded-t bg-fuchsia-500/70"
                              style={{ height: `${(n / maxDow) * 100}%`,
                                            minHeight: n ? "2px" : "0" }} />
                    <div className={`text-[10px] font-mono ${textDim}`}>
                      {DOW_LABELS[d]}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Top clusters */}
          <div className={`rounded-2xl border ${border} ${bg} p-4`}
                    data-testid="merchant-insights-clusters">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold mb-3">
              Top dwelling clusters
            </div>
            {!data.top_dwelling_locations?.length ? (
              <div className={`text-xs ${textDim}`}>
                No repeat dwell clusters yet.  Come back when foot traffic picks up.
              </div>
            ) : (
              <div className="space-y-2">
                {data.top_dwelling_locations.map((c, i) => (
                  <div key={i} className="flex items-center gap-3 text-xs"
                            data-testid={`merchant-insights-cluster-${i}`}>
                    <div className="tabular-nums text-cyan-400 font-bold w-8">
                      #{i + 1}
                    </div>
                    <div className="font-mono text-slate-400">
                      {c.lat.toFixed(3)}, {c.lng.toFixed(3)}
                    </div>
                    <div className={`ml-auto tabular-nums font-bold ${
                        light ? "text-slate-900" : "text-slate-100"}`}>
                      {c.count} pings
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function MiniKpi({ Icon, label, value, tint, testid, light, hint }) {
  return (
    <div className={`rounded-2xl border ${
        light ? "bg-white border-slate-200 shadow-sm"
                  : "bg-slate-900/60 border-slate-800"} p-4`}
              data-testid={testid}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
          {label}
        </div>
        <Icon className={`w-4 h-4 ${tint}`} />
      </div>
      <div className={`text-2xl xl:text-3xl font-black tabular-nums ${tint}`}>
        {value}
      </div>
      {hint && (
        <div className={`text-[10px] font-mono mt-1 ${
            light ? "text-slate-500" : "text-slate-500"}`}>
          {hint}
        </div>
      )}
    </div>
  );
}
