// Phase S — Admin Location Intelligence dashboard (legacy dark).
// Leaflet heatmap + KPI cards + Regions table + Geofence effectiveness table.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, MapPin, RefreshCw, ArrowLeft, Activity,
  Users, Target, Compass, Clock, TrendingUp,
} from "lucide-react";
import { MapContainer, TileLayer, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

// Dubai bounding box — matches the fixture data.  Admin can pan; the
// endpoint will requery on next explicit refresh.
const DEFAULT_BOUNDS = {
  sw_lat: 24.9, sw_lng: 54.9, ne_lat: 25.5, ne_lng: 55.6,
};

export default function AdminLocationIntel() {
  const [days, setDays] = useState(30);
  const [bounds, setBounds] = useState(DEFAULT_BOUNDS);
  const [summary, setSummary] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [regions, setRegions] = useState(null);
  const [gfx, setGfx] = useState(null);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState(null);

  const load = useCallback(async (refresh = false) => {
    setBusy(true);
    setErr(null);
    const p = new URLSearchParams({ days: String(days) });
    if (refresh) p.set("refresh", "true");
    const b = new URLSearchParams({
      sw_lat: bounds.sw_lat, sw_lng: bounds.sw_lng,
      ne_lat: bounds.ne_lat, ne_lng: bounds.ne_lng,
      days: String(days),
    });
    if (refresh) b.set("refresh", "true");
    try {
      const [s, h, r, g] = await Promise.all([
        axios.get(`${API}/admin/location-intel/summary?${p}`,
                          { withCredentials: true }),
        axios.get(`${API}/admin/location-intel/heatmap?${b}`,
                          { withCredentials: true }),
        axios.get(`${API}/admin/location-intel/regions/rank?${p}&limit=20`,
                          { withCredentials: true }),
        axios.get(`${API}/admin/location-intel/geofence-effectiveness?${p}`,
                          { withCredentials: true }),
      ]);
      setSummary(s.data);
      setHeatmap(h.data);
      setRegions(r.data);
      setGfx(g.data);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code
              || e?.response?.data?.detail
              || e.message);
    } finally {
      setBusy(false);
    }
  }, [days, bounds]);

  useEffect(() => { load(false); }, [load]);

  const mapCenter = useMemo(() => {
    if (heatmap?.cells?.[0])
      return [heatmap.cells[0].lat, heatmap.cells[0].lng];
    return [(bounds.sw_lat + bounds.ne_lat) / 2,
                (bounds.sw_lng + bounds.ne_lng) / 2];
  }, [heatmap, bounds]);

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-loc-intel-page">
      <div className="max-w-7xl xl:max-w-[1600px] mx-auto p-6 sm:p-8">
        <AdminPageHeader
          title="Location Intelligence"
          subtitle="Geospatial analytics · heatmaps · geofence effectiveness."
          Icon={MapPin}
          tint="text-cyan-500"
          pinLabel="Location Intel"
          breadcrumbs={[{ label: "Home & Analytics" },
                                          { label: "Location Intel" }]} />

        {/* Controls */}
        <div className="mt-5 mb-5 flex items-center gap-2 flex-wrap"
                  data-testid="admin-loc-intel-controls">
          <label className="text-xs text-slate-400 inline-flex items-center gap-2">
            Days
            <select value={days}
                            onChange={(e) => setDays(parseInt(e.target.value, 10))}
                            data-testid="admin-loc-intel-days"
                            className="px-2 py-1 rounded-full text-xs bg-slate-900 border border-slate-800">
              <option value={7}>Last 7</option>
              <option value={30}>Last 30</option>
              <option value={60}>Last 60</option>
              <option value={90}>Last 90</option>
            </select>
          </label>
          <button onClick={() => load(true)}
                          disabled={busy}
                          data-testid="admin-loc-intel-refresh"
                          className="ml-auto inline-flex items-center gap-2 px-4 py-1.5 rounded-full
                                          bg-cyan-500 text-slate-950 text-xs font-bold
                                          hover:bg-cyan-400 disabled:opacity-50">
            {busy ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <RefreshCw className="w-3 h-3" />}
            Refresh
          </button>
        </div>

        {err && (
          <div className="mb-4 rounded-2xl bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-400"
                    data-testid="admin-loc-intel-error">
            {String(err)}
          </div>
        )}

        {/* KPI Hero row */}
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6"
                  data-testid="admin-loc-intel-kpis">
          <KpiCard label="Total pings" value={summary?.total_pings ?? "—"}
                        Icon={Activity} tint="text-cyan-400"
                        testid="admin-loc-intel-kpi-pings" />
          <KpiCard label="Unique users" value={summary?.unique_users_pinged ?? "—"}
                        Icon={Users} tint="text-emerald-400"
                        testid="admin-loc-intel-kpi-users" />
          <KpiCard label="Geofence matches" value={summary?.geofence_matches ?? "—"}
                        Icon={Target} tint="text-amber-400"
                        testid="admin-loc-intel-kpi-geofence" />
          <KpiCard label="Top city" value={summary?.top_city || "—"}
                        Icon={Compass} tint="text-fuchsia-400"
                        testid="admin-loc-intel-kpi-topcity" />
          <KpiCard label="Peak hour"
                        value={summary?.most_active_hour != null
                                  ? `${String(summary.most_active_hour).padStart(2, "0")}:00`
                                  : "—"}
                        Icon={Clock} tint="text-purple-400"
                        testid="admin-loc-intel-kpi-hour" />
          <KpiCard label="Avg dist to merchant"
                        value={summary?.avg_distance_to_merchant_m != null
                                  ? `${Math.round(summary.avg_distance_to_merchant_m)} m` : "—"}
                        Icon={TrendingUp} tint="text-orange-400"
                        testid="admin-loc-intel-kpi-dist" />
        </div>

        {/* Heatmap */}
        <div className="rounded-2xl bg-slate-900/60 border border-slate-800 overflow-hidden mb-6"
                  data-testid="admin-loc-intel-map-card">
          <div className="p-3 flex items-center gap-2">
            <MapPin className="w-4 h-4 text-cyan-500" />
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
              Heatmap · {heatmap?.total_pings ?? 0} pings across {heatmap?.unique_cells ?? 0} cells
            </div>
            {heatmap?.cached && (
              <span className="ml-auto text-[10px] font-mono text-slate-600">served from cache</span>
            )}
          </div>
          <div className="h-[420px]" data-testid="admin-loc-intel-map">
            <MapContainer center={mapCenter} zoom={10}
                                      style={{ height: "100%", width: "100%",
                                                    background: "#0f172a" }}
                                      data-testid="admin-loc-intel-map-container">
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution="&copy; OSM contributors" />
              {(heatmap?.cells || []).map((c) => {
                const r = Math.max(4, Math.min(28, 4 + Math.log2(c.count + 1) * 5));
                return (
                  <CircleMarker key={`${c.lat},${c.lng}`}
                                            center={[c.lat, c.lng]}
                                            radius={r}
                                            pathOptions={{
                                              color: "#06b6d4",
                                              fillColor: "#06b6d4",
                                              fillOpacity: 0.45, weight: 1 }}>
                    <Tooltip direction="top" opacity={0.9}>
                      {c.count} pings @ {c.lat},{c.lng}
                    </Tooltip>
                  </CircleMarker>
                );
              })}
            </MapContainer>
          </div>
          {heatmap?.sources && (
            <div className="p-3 border-t border-slate-800 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-mono text-slate-500">
              {Object.entries(heatmap.sources).map(([k, v]) => (
                <div key={k}
                          data-testid={`admin-loc-intel-source-${k}`}>
                  <span className="text-slate-400">{k}:</span>{" "}
                  <span className="text-cyan-400 tabular-nums font-bold">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Regions rank + Geofence tables side-by-side at xl+ */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
          {/* Regions rank */}
          <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                    data-testid="admin-loc-intel-regions">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold mb-3">
              Regions by ping density
            </div>
            {!regions?.items?.length ? (
              <div className="text-xs text-slate-500">No regions yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                      <th className="text-left px-2 py-1">Region</th>
                      <th className="text-right px-2 py-1">Pings</th>
                      <th className="text-right px-2 py-1">Users</th>
                      <th className="text-right px-2 py-1">Geofences</th>
                    </tr>
                  </thead>
                  <tbody>
                    {regions.items.map((r, i) => (
                      <tr key={i} className="border-t border-slate-800"
                              data-testid={`admin-loc-intel-region-row-${i}`}>
                        <td className="px-2 py-1.5">
                          <div className="font-medium">{r.city || "Unlabeled"}</div>
                          <div className="text-[10px] font-mono text-slate-500">
                            {r.centroid.lat}, {r.centroid.lng}
                          </div>
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-cyan-400 font-bold">{r.ping_count}</td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-emerald-400">{r.unique_users}</td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-amber-400">{r.active_geofences}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Geofence effectiveness */}
          <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                    data-testid="admin-loc-intel-geofences">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold mb-3">
              Geofence effectiveness (Phase J campaigns)
            </div>
            {!gfx?.items?.length ? (
              <div className="text-xs text-slate-500">No campaigns yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                      <th className="text-left px-2 py-1">Campaign</th>
                      <th className="text-right px-2 py-1">Area (km²)</th>
                      <th className="text-right px-2 py-1">Imp.</th>
                      <th className="text-right px-2 py-1">Users</th>
                      <th className="text-right px-2 py-1">CTR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gfx.items.slice(0, 12).map((c, i) => (
                      <tr key={c.campaign_id} className="border-t border-slate-800"
                              data-testid={`admin-loc-intel-gfx-row-${c.campaign_id}`}>
                        <td className="px-2 py-1.5">
                          <div className="font-medium truncate max-w-xs">
                            {c.display_name || "(untitled)"}
                          </div>
                          <div className="text-[10px] font-mono text-slate-500 truncate">
                            {c.advertiser_business_id} · {c.status}
                          </div>
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-fuchsia-400">
                          {c.geofence_area_sq_km}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-cyan-400 font-bold">
                          {c.impressions_delivered}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-emerald-400">
                          {c.unique_users_reached}
                        </td>
                        <td className="px-2 py-1.5 tabular-nums text-right text-slate-400">
                          {c.ctr_estimate == null ? "—" : (c.ctr_estimate * 100).toFixed(2) + "%"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ label, value, Icon, tint, testid }) {
  return (
    <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950
                              border border-slate-800 p-4"
              data-testid={testid}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
          {label}
        </div>
        <Icon className={`w-4 h-4 ${tint || "text-slate-400"}`} />
      </div>
      <div className="text-2xl xl:text-3xl font-black tabular-nums truncate">
        {value}
      </div>
    </div>
  );
}
