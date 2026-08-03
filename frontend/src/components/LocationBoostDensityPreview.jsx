// Phase S — Location Boost Density Preview.
// Mounted inside AdvertiserLocationBoosts.jsx wizard AFTER the advertiser
// picks a geofence but BEFORE they submit for payment.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Loader2, Users, MapPin, Zap, AlertCircle } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function LocationBoostDensityPreview({
  business_id, fences, days = 30, light = false,
}) {
  const [data, setData]   = useState(null);
  const [busy, setBusy]   = useState(false);
  const [err, setErr]     = useState(null);

  // Pick the FIRST radius fence for the preview.  Advertisers can toggle
  // through their fences by clicking the fence-picker chips below.
  const [fenceIdx, setFenceIdx] = useState(0);

  const radiusFences = (fences || []).filter((f) => f.type === "radius" &&
      f.center_lat != null && f.center_lng != null);
  const active = radiusFences[fenceIdx];

  const load = useCallback(async () => {
    if (!business_id || !active) { setData(null); return; }
    setBusy(true);
    setErr(null);
    try {
      const q = new URLSearchParams({
        center_lat: active.center_lat,
        center_lng: active.center_lng,
        radius_meters: Math.round(active.radius_m || active.radius_meters || 1000),
        days: String(days),
      });
      const { data: d } = await axios.get(
        `${API}/advertiser/${business_id}/location-intel/density?${q}`,
        { withCredentials: true });
      setData(d);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code
              || e?.response?.data?.detail
              || e.message);
    } finally {
      setBusy(false);
    }
  }, [business_id, active, days]);

  useEffect(() => { load(); }, [load]);

  if (!radiusFences.length) return null;

  const box = light ? "bg-white border-slate-200 shadow-sm"
                                : "bg-slate-900/60 border-slate-800";
  const dim = light ? "text-slate-600" : "text-slate-400";

  return (
    <div className={`rounded-2xl border ${box} p-4 mt-4`}
              data-testid="loc-density-preview">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <Zap className="w-4 h-4 text-cyan-400" />
        <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-500 font-bold">
          Preview reach
        </div>
        {radiusFences.length > 1 && (
          <div className="ml-auto flex items-center gap-1">
            {radiusFences.map((_, i) => (
              <button key={i} type="button"
                              data-testid={`loc-density-fence-${i}`}
                              onClick={() => setFenceIdx(i)}
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                i === fenceIdx
                                  ? "bg-cyan-500 text-slate-950"
                                  : (light ? "bg-slate-100 text-slate-500"
                                                    : "bg-slate-800 text-slate-500")}`}>
                Fence {i + 1}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className={`text-xs ${dim} mb-3 inline-flex items-center gap-1.5`}>
        <MapPin className="w-3 h-3" />
        Fence {fenceIdx + 1} of {radiusFences.length} ·{" "}
        <span className="font-mono">
          {active?.center_lat?.toFixed?.(4)}, {active?.center_lng?.toFixed?.(4)}
        </span>{" "}
        · {Math.round(active?.radius_m || active?.radius_meters || 0)} m radius · last {days} d
      </div>

      {busy ? (
        <div className={`flex items-center gap-2 text-xs ${dim}`}
                  data-testid="loc-density-loading">
          <Loader2 className="w-3 h-3 animate-spin" />
          Estimating audience …
        </div>
      ) : err ? (
        <div className="text-xs text-red-400 inline-flex items-center gap-1.5"
                  data-testid="loc-density-error">
          <AlertCircle className="w-3 h-3" />
          {String(err)}
        </div>
      ) : data ? (
        <div className="grid grid-cols-3 gap-2" data-testid="loc-density-results">
          <MiniStat label="Est. reach"
                          testid="loc-density-reach"
                          value={data.estimated_reach ?? 0}
                          hint="Unique users pinged in this fence"
                          light={light} />
          <MiniStat label="Total pings"
                          testid="loc-density-pings"
                          value={data.ping_count ?? 0}
                          hint="Ping stream volume in-fence"
                          light={light} />
          <MiniStat label="Competing boosts"
                          testid="loc-density-competing"
                          value={data.competing_campaigns_count ?? 0}
                          hint="Live campaigns overlapping this fence"
                          light={light} />
        </div>
      ) : null}

      {data && data.estimated_reach === 0 && (
        <div className="mt-3 rounded-lg bg-amber-500/10 border border-amber-500/30
                                 p-2 text-[11px] text-amber-500 inline-flex items-start gap-1.5"
                  data-testid="loc-density-zero-warning">
          <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
          No listeners have been near this fence in the last {days} days.
          Consider widening the radius or moving the center closer to a
          higher-traffic area before spending.
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, hint, testid, light }) {
  return (
    <div className={`rounded-xl px-3 py-2 border ${
        light ? "bg-slate-50 border-slate-200" : "bg-slate-950 border-slate-800"}`}
             data-testid={testid}>
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="text-xl font-black text-cyan-400 tabular-nums inline-flex items-center gap-1.5">
        <Users className="w-3 h-3" />
        {value}
      </div>
      <div className={`text-[10px] ${light ? "text-slate-500" : "text-slate-500"} mt-0.5`}>
        {hint}
      </div>
    </div>
  );
}
