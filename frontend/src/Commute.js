// Phase 9a — Commute page (web).
// Leaflet map (OSM tiles) + route-preview/active-commute toggle + saved
// locations + nearby places along the route.  No Google Maps key needed
// for the map render itself — only the polyline geometry comes from the
// MapsClient backend.
import { useEffect, useRef, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { decode as decodePolyline } from "@googlemaps/polyline-codec";
import { MapContainer, TileLayer, Polyline, Marker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Toaster, toast } from "sonner";
import { ChevronLeft, Loader2, MapPin, Navigation, Wind, Cloud,
            Zap, Plus, Trash2, Coffee, Utensils, Beer, ShoppingCart,
            Dumbbell, Star, ChevronRight, X, Home, Briefcase, Sun,
            CloudRain, CloudSnow, Thermometer, Sparkles, Info } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import CommuteCoachmark from "@/components/CommuteCoachmark";
// Phase F-1 side-fix — Commute referenced <BannerAdSlot/> without
// importing it.  Importing the existing component (every other page
// uses it the same way) resolves the runtime ReferenceError.
import BannerAdSlot from "@/components/BannerAdSlot";
// Phase 42-E1.1 — persistent banner ad slot (new placement taxonomy).
import PersistentBannerSlot from "@/components/PersistentBannerSlot";
// Phase 42-E1.4 — resolved-geo source for the initial map center.
// Previously hardcoded to Dubai (25.20, 55.27); now read from the same
// useGeoStore the rest of the app uses, with a known-cities centroid
// table for fallback.  Last-resort default is Dallas (matches the
// backend geo `dfw` fallback from services/geo.py).
import { useGeoStore } from "@/store/useGeoStore";

const MARKET_CENTROIDS = {
  dubai:           [25.20, 55.27],
  new_york:    [40.7128, -74.0060],
  london:        [51.5074, -0.1278],
  mumbai:       [19.0760, 72.8777],
  los_angeles: [34.0522, -118.2437],
  dfw:             [32.7767, -96.7970],     // Dallas
  global:        [32.7767, -96.7970],     // Same as DFW — no specific city.
};
function centroidForMarket(market) {
  return MARKET_CENTROIDS[market] || MARKET_CENTROIDS.dfw;
}
import "./Commute.css";

// Override Leaflet's default broken icon URL (CRA can't resolve via require)
const _mkIcon = (color) => L.divIcon({
  html: `<div class="leaflet-pin" style="background:${color}"></div>`,
  className: "leaflet-divicon-wrap",
  iconSize: [22, 22], iconAnchor: [11, 22],
});
const _originIcon = _mkIcon("#14e29a");
const _destIcon = _mkIcon("#ff2d95");

const CATEGORIES = [
  { id: "restaurant", label: "Restaurants", icon: Utensils },
  { id: "cafe",       label: "Cafés",       icon: Coffee },
  { id: "fast_food",  label: "Fast food",   icon: Utensils },
  { id: "bar",        label: "Bars",        icon: Beer },
  { id: "mall",       label: "Malls",       icon: ShoppingCart },
  { id: "gym",        label: "Gyms",        icon: Dumbbell },
];

const WEATHER_ICONS = {
  clear: Sun, cloudy: Cloud, rain: CloudRain, thunderstorm: CloudRain,
  snow: CloudSnow, haze: Cloud, hot: Sun, cold: Thermometer,
};


function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!points || points.length < 2) return;
    map.fitBounds(points, { padding: [30, 30], maxZoom: 14 });
  }, [points, map]);
  return null;
}


export default function Commute() {
  const { user, loading: authLoading } = useAuth();
  // Phase 42-E1.4 — pull resolved market from the geo store so the
  // map opens centred on the user's actual city, not the previous
  // hardcoded Dubai default.
  const geoMarket  = useGeoStore((s) => s.market);
  const geoCity      = useGeoStore((s) => s.city);
  const mapCenter = centroidForMarket(geoMarket);
  const [savedLocs, setSavedLocs] = useState([]);
  const [originLatLng, setOriginLatLng] = useState(null);
  const [destLatLng, setDestLatLng] = useState(null);
  const [originText, setOriginText] = useState("");
  const [destText, setDestText] = useState("");
  const [mode, setMode] = useState("driver");
  const [label, setLabel] = useState("home_to_work");
  const [preview, setPreview] = useState(null);
  const [activeCmt, setActiveCmt] = useState(null);
  const [nearby, setNearby] = useState([]);
  const [activeCategory, setActiveCategory] = useState("restaurant");
  const [loading, setLoading] = useState(false);
  // Phase 9b — route-targeted opportunities ("Coming up")
  const [opps, setOpps] = useState([]);
  // Phase 18 — first-visit coachmark for the commute page.
  const [introSeen, setIntroSeen] = useState(() => {
    try { return localStorage.getItem("commute_intro_seen") === "true"; }
    catch { return true; }
  });
  const dismissIntro = () => {
    try { localStorage.setItem("commute_intro_seen", "true"); } catch (_e) {}
    setIntroSeen(true);
  };
  const heartbeatRef = useRef(null);

  const loadSaved = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/commute/saved_locations`);
      setSavedLocs(r.data.items || []);
    } catch (_e) { /* */ }
  }, []);

  const loadActive = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/commute/active`);
      setActiveCmt(r.data.active);
    } catch (_e) { /* */ }
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    loadSaved();
    loadActive();
  }, [authLoading, user, loadSaved, loadActive]);

  // Heartbeat poller while a commute is active
  useEffect(() => {
    if (!activeCmt) return;
    if (heartbeatRef.current) clearInterval(heartbeatRef.current);
    heartbeatRef.current = setInterval(async () => {
      try {
        await axios.post(
          `${API}/commute/${activeCmt.commute_id}/heartbeat`, {});
      } catch (_e) { /* */ }
    }, 60000);
    return () => clearInterval(heartbeatRef.current);
  }, [activeCmt]);

  // Load nearby places for the active commute
  useEffect(() => {    if (!activeCmt) { setNearby([]); return; }
    (async () => {
      try {
        const r = await axios.get(
          `${API}/commute/${activeCmt.commute_id}/places_along_route`,
          {params: {radius: 3000, categories: activeCategory,
                       max_detour_minutes: 10}});
        setNearby(r.data.items || []);
      } catch (_e) { /* */ }
    })();
  }, [activeCmt, activeCategory]);

  // Phase 9b — load route-targeted opportunities for the active commute.
  // Polled every 30s so the strip refreshes as opps go from "valid_from"
  // window into "valid_until" window during the drive.
  useEffect(() => {
    if (!activeCmt) { setOpps([]); return; }
    let mounted = true;
    const fetchOpps = async () => {
      try {
        const r = await axios.get(
          `${API}/commute/${activeCmt.commute_id}/opportunities`);
        if (!mounted) return;
        setOpps((r.data.items || []).filter(
          (o) => !o.selected && o.engagement_type !== "dismissed"));
      } catch (_e) { /* */ }
    };
    fetchOpps();
    const id = setInterval(fetchOpps, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, [activeCmt]);

  const dismissOpp = async (oppId) => {
    try {
      await axios.post(`${API}/route_ads/${oppId}/engage`,
                             {engagement_type: "dismissed"});
      setOpps((prev) => prev.filter((o) => o.opp_id !== oppId));
    } catch (_e) {
      toast.error("Couldn't dismiss");
    }
  };

  const handlePickSaved = (id, isOrigin) => {
    const loc = savedLocs.find((l) => l.loc_id === id);
    if (!loc) return;
    if (isOrigin) {
      setOriginLatLng({lat: loc.lat, lng: loc.lng});
      setOriginText(loc.label);
    } else {
      setDestLatLng({lat: loc.lat, lng: loc.lng});
      setDestText(loc.label);
    }
  };

  const previewRoute = async () => {
    if (!originLatLng || !destLatLng) {
      toast.error("Pick or geocode an origin and destination first");
      return;
    }
    setLoading(true);
    try {
      const r = await axios.post(`${API}/commute/route_preview`,
                                          {origin: originLatLng,
                                            destination: destLatLng});
      setPreview(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Preview failed");
    } finally { setLoading(false); }
  };

  const startCommute = async () => {
    if (!originLatLng || !destLatLng) {
      toast.error("Need origin + destination");
      return;
    }
    setLoading(true);
    try {
      const r = await axios.post(`${API}/commute/start`,
                                          {origin: originLatLng,
                                            destination: destLatLng,
                                            mode, label});
      setActiveCmt(r.data);
      setPreview(null);
      toast.success("Commute started");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Start failed");
    } finally { setLoading(false); }
  };

  const endCommute = async (abandon = false) => {
    if (!activeCmt) return;
    try {
      const url = `${API}/commute/${activeCmt.commute_id}/${abandon ? "abandon" : "end"}`;
      const r = await axios.post(url);
      if (!abandon && r.data?.milestone) {
        toast.success("Commute complete — game unlock awarded!");
      } else if (abandon) {
        toast.info("Commute abandoned");
      } else {
        toast.success("Commute complete");
      }
      setActiveCmt(null);
      setPreview(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't end commute");
    }
  };

  const geocode = async (text, isOrigin) => {
    try {
      // Use the saved-location create endpoint to do a fast geocode then
      // delete it; cheap and re-uses the server's MapsClient.
      const r = await axios.post(`${API}/commute/saved_locations`,
                                          {label: `__tmp_${Date.now()}`,
                                            address: text});
      const loc = r.data;
      // Optimistically use coords; quietly delete the tmp pin
      axios.delete(`${API}/commute/saved_locations/${loc.loc_id}`).catch(() => {});
      const p = {lat: loc.lat, lng: loc.lng};
      isOrigin ? setOriginLatLng(p) : setDestLatLng(p);
    } catch (e) {
      toast.error("Could not geocode address");
    }
  };

  const addSavedLocation = async (label, address) => {
    if (!label || !address) return;
    try {
      await axios.post(`${API}/commute/saved_locations`, {label, address});
      loadSaved();
      toast.success("Saved");
    } catch (_e) { toast.error("Save failed"); }
  };

  const decodedPreviewPoints = preview?.route?.polyline_encoded
    ? decodePolyline(preview.route.polyline_encoded, 5) : null;
  const decodedActivePoints = activeCmt?.route_polyline
    ? decodePolyline(activeCmt.route_polyline, 5) : null;
  const drawnPoints = decodedActivePoints || decodedPreviewPoints || null;

  if (authLoading) return <div className="paw-loading"><Loader2 size={28} className="spin" /></div>;
  if (!user) return <div className="paw-loading">Please sign in</div>;

  return (
    <div className="commute-shell" data-testid="commute-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      {/* Phase 18 — explainer hero (always visible at top). */}
      <CommuteExplainerHero />

      {/* Phase 42 S1 — banner ad slot (Commute). */}
      <BannerAdSlot slotKey="top_leaderboard" pageRoute="/commute" />
      {/* Phase 42-E1.1 — persistent commute-map banner (new placement). */}
      <div style={{ display: "flex", justifyContent: "center",
                                  margin: "10px 0" }}>
        <PersistentBannerSlot placement="commute_map" />
      </div>

      {/* Phase 18 — 3-step coachmark on first visit (portal to body so
            no transformed ancestor breaks position:fixed). */}
      <CommuteCoachmark
        open={!introSeen}
        onDismiss={dismissIntro} />

      <header className="commute-header">
        <Link to="/" className="paw-back"><ChevronLeft size={14} /> back</Link>
        <h1><Navigation size={20} /> Commute</h1>
        <p className="sub">Live ETA, traffic, weather & nearby places along your drive.</p>
      </header>

      <div className="commute-grid">
        <aside className="commute-side">
          {!activeCmt && (
            <div className="commute-form" data-testid="commute-form">
              <h3>Plan your commute</h3>
              <div className="cf-row">
                <label className="mono dim">FROM</label>
                <div className="cf-input-row">
                  <input className="lead-input" data-testid="origin-input"
                            value={originText}
                            onChange={(e) => setOriginText(e.target.value)}
                            placeholder="Address or pick saved" />
                  <button className="ghost-btn" data-testid="origin-geocode-btn"
                            onClick={() => geocode(originText, true)}
                            disabled={!originText}>geocode</button>
                </div>
                {savedLocs.length > 0 && (
                  <div className="cf-chips" data-testid="origin-chips">
                    {savedLocs.map((l) => (
                      <button key={l.loc_id} className="cf-chip"
                                  onClick={() => handlePickSaved(l.loc_id, true)}>
                        {l.label === "Home" ? <Home size={11} />
                          : l.label === "Work" ? <Briefcase size={11} />
                          : <MapPin size={11} />} {l.label}
                      </button>))}
                  </div>
                )}
              </div>
              <div className="cf-row">
                <label className="mono dim">TO</label>
                <div className="cf-input-row">
                  <input className="lead-input" data-testid="dest-input"
                            value={destText}
                            onChange={(e) => setDestText(e.target.value)}
                            placeholder="Address or pick saved" />
                  <button className="ghost-btn" data-testid="dest-geocode-btn"
                            onClick={() => geocode(destText, false)}
                            disabled={!destText}>geocode</button>
                </div>
                {savedLocs.length > 0 && (
                  <div className="cf-chips" data-testid="dest-chips">
                    {savedLocs.map((l) => (
                      <button key={l.loc_id} className="cf-chip"
                                  onClick={() => handlePickSaved(l.loc_id, false)}>
                        {l.label === "Home" ? <Home size={11} />
                          : l.label === "Work" ? <Briefcase size={11} />
                          : <MapPin size={11} />} {l.label}
                      </button>))}
                  </div>
                )}
              </div>
              <div className="cf-row-inline">
                <select className="leads-filter" data-testid="mode-select"
                           value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="driver">Driver</option>
                  <option value="passenger">Passenger</option>
                  <option value="transit">Transit</option>
                </select>
                <select className="leads-filter" data-testid="label-select"
                           value={label} onChange={(e) => setLabel(e.target.value)}>
                  <option value="commute">Commute</option>
                  <option value="home_to_work">Home → Work</option>
                  <option value="work_to_home">Work → Home</option>
                  <option value="lunch_run">Lunch run</option>
                  <option value="errand">Errand</option>
                  <option value="club_night">Club night</option>
                  <option value="concert">Concert</option>
                  <option value="movie_night">Movie night</option>
                  <option value="devotional">Devotional</option>
                  <option value="school_run">School run</option>
                  <option value="airport">Airport</option>
                  <option value="gym">Gym</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div className="cf-actions">
                <button className="ghost-btn"
                          onClick={previewRoute}
                          disabled={loading || !originLatLng || !destLatLng}
                          data-testid="preview-route-btn">
                  {loading ? <Loader2 size={12} className="spin" /> : null}
                  Preview route
                </button>
                <button className="lead-submit"
                          onClick={startCommute}
                          disabled={loading || !originLatLng || !destLatLng}
                          data-testid="start-commute-btn">
                  {loading ? <Loader2 size={14} className="spin" /> : <Navigation size={14} />}
                  Start commute
                </button>
              </div>
              {preview && (
                <div className="preview-chips" data-testid="route-preview-chips">
                  <ChipETA seconds={preview.route.duration_in_traffic_seconds} />
                  <ChipTraffic status={preview.route.traffic_status} />
                  <ChipWeather w={preview.weather} />
                  <ChipDist meters={preview.route.distance_meters} />
                </div>
              )}
            </div>
          )}

          {activeCmt && (
            <div className="active-commute-card" data-testid="active-commute-card">
              <div className="ac-eyebrow mono">ACTIVE COMMUTE</div>
              <div className="ac-eta">
                {formatDuration(activeCmt.route_duration_in_traffic_s)}
              </div>
              <div className="ac-chips">
                <ChipTraffic status={activeCmt.traffic_status} />
                <ChipWeather w={activeCmt.weather_snapshot} />
                <ChipDist meters={activeCmt.route_distance_m} />
              </div>
              {activeCmt.mode === "driver" && (
                <div className="driving-banner" data-testid="driving-banner">
                  <Zap size={13} /> Driving mode is on. Game cards will save
                  for later.{" "}
                  <Link to="/play-and-win">Open Play &amp; Win →</Link>
                </div>
              )}
              {opps.length > 0 && (
                <div className="opps-strip" data-testid="opps-strip">
                  <div className="opps-strip-eyebrow mono">
                    <Sparkles size={11} /> COMING UP
                  </div>
                  <div className="opps-list">
                    {opps.slice(0, 3).map((o) => (
                      <RouteOppCard
                        key={o.opp_id}
                        opp={o}
                        onDismiss={() => dismissOpp(o.opp_id)} />
                    ))}
                  </div>
                </div>
              )}
              <div className="nearby-tabs" data-testid="nearby-tabs">
                {CATEGORIES.map((c) => {
                  const Icon = c.icon;
                  return (
                    <button key={c.id} className="nearby-tab"
                                data-active={c.id === activeCategory}
                                onClick={() => setActiveCategory(c.id)}
                                data-testid={`nearby-cat-${c.id}`}>
                      <Icon size={12} /> {c.label}
                    </button>
                  );
                })}
              </div>
              <div className="nearby-list" data-testid="nearby-list">
                {nearby.length === 0
                  ? <div className="leads-empty">Nothing nearby right now.</div>
                  : nearby.slice(0, 10).map((p) => (
                      <div key={p.place_id} className="nearby-row"
                              data-testid={`nearby-row-${p.place_id}`}>
                        <div className="nr-info">
                          <div className="nr-name">{p.name}</div>
                          <div className="dim small">
                            {p.address} ·{" "}
                            +{Math.round(p.extra_drive_time_seconds / 60)} min detour
                          </div>
                        </div>
                        {p.rating && (
                          <span className="status-pill mono">
                            <Star size={9} /> {p.rating}
                          </span>
                        )}
                      </div>
                    ))}
              </div>
              <div className="ac-actions">
                <button className="ghost-btn"
                          onClick={() => endCommute(true)}
                          data-testid="abandon-btn">
                  Abandon
                </button>
                <button className="lead-submit"
                          onClick={() => endCommute(false)}
                          data-testid="end-commute-btn">
                  End commute
                </button>
              </div>
            </div>
          )}

          <SavedLocationsPanel locs={savedLocs}
                                          reload={loadSaved}
                                          onAdd={addSavedLocation} />
        </aside>

        <main className="commute-map-wrap" data-testid="commute-map-wrap">
          {/* Phase 42-E1.4 — resolved-city label, replaces the Dubai
                      header that used to leak even for US/UK listeners. */}
          {geoCity && geoCity.toLowerCase() !== "global" && (
            <div data-testid="commute-resolved-city"
                      data-market={geoMarket}
                      style={{ position: "absolute", top: 10, left: 10,
                                  zIndex: 500, background: "rgba(11,11,18,0.85)",
                                  border: "1px solid rgba(0,217,255,0.25)",
                                  color: "#22d3ee", padding: "4px 10px",
                                  borderRadius: 999, fontSize: 11,
                                  fontWeight: 600, letterSpacing: 0.5,
                                  pointerEvents: "none" }}>
              <MapPin size={10} style={{ verticalAlign: "-1px",
                                                                    marginRight: 4 }} />
              {geoCity}
            </div>
          )}
          <MapContainer key={`map-${geoMarket}`} center={mapCenter} zoom={11}
                              className="commute-leaflet"
                              data-testid="commute-leaflet"
                              scrollWheelZoom={true}>
            <TileLayer
              attribution='&copy; <a href="https://osm.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {drawnPoints && (
              <>
                <Polyline positions={drawnPoints}
                              pathOptions={{color: "#ff2d95", weight: 5,
                                              opacity: 0.85}} />
                <Marker position={drawnPoints[0]} icon={_originIcon} />
                <Marker position={drawnPoints[drawnPoints.length - 1]}
                          icon={_destIcon} />
                <FitBounds points={drawnPoints} />
              </>
            )}
          </MapContainer>
        </main>
      </div>
    </div>
  );
}


function SavedLocationsPanel({ locs, reload, onAdd }) {
  const [adding, setAdding] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newAddr, setNewAddr] = useState("");
  const del = async (id) => {
    try {
      await axios.delete(`${API}/commute/saved_locations/${id}`);
      reload();
    } catch (_e) { /* */ }
  };
  return (
    <div className="saved-locs-panel" data-testid="saved-locs-panel">
      <div className="panel-toolbar">
        <h3><MapPin size={16} /> Saved locations</h3>
        <button className="ghost-btn" onClick={() => setAdding(!adding)}
                   data-testid="add-saved-btn">
          <Plus size={12} /> add
        </button>
      </div>
      {adding && (
        <div className="cf-row" data-testid="add-saved-form">
          <input className="lead-input" placeholder="Label (e.g. Gym)"
                    value={newLabel} onChange={(e) => setNewLabel(e.target.value)}
                    data-testid="new-saved-label" />
          <input className="lead-input" placeholder="Address"
                    value={newAddr} onChange={(e) => setNewAddr(e.target.value)}
                    data-testid="new-saved-address" />
          <button className="lead-submit"
                    onClick={async () => {
                      await onAdd(newLabel, newAddr);
                      setNewLabel(""); setNewAddr(""); setAdding(false);
                    }}
                    disabled={!newLabel || !newAddr}
                    data-testid="new-saved-submit">
            Save
          </button>
        </div>
      )}
      {locs.length === 0
        ? <div className="leads-empty">No saved locations yet.</div>
        : <div className="saved-loc-list">
            {locs.map((l) => (
              <div key={l.loc_id} className="saved-loc-row"
                       data-testid={`saved-loc-row-${l.loc_id}`}>
                {l.label === "Home" ? <Home size={13} />
                  : l.label === "Work" ? <Briefcase size={13} />
                  : <MapPin size={13} />}
                <div className="sl-info">
                  <div className="sl-label">{l.label}</div>
                  <div className="dim small">{l.formatted_address || `${l.lat.toFixed(3)}, ${l.lng.toFixed(3)}`}</div>
                </div>
                <button className="ghost-btn danger"
                          onClick={() => del(l.loc_id)}>
                  <Trash2 size={11} />
                </button>
              </div>))}
          </div>}
    </div>
  );
}


function ChipETA({ seconds }) {
  return (
    <span className="commute-chip eta-chip">
      <Navigation size={11} />
      <span className="mono">{formatDuration(seconds)}</span>
    </span>
  );
}

function ChipTraffic({ status }) {
  const colorMap = {light: "var(--paw-green)", moderate: "var(--paw-amber)",
                          heavy: "var(--paw-danger)", unknown: "var(--paw-text-muted)"};
  return (
    <span className="commute-chip" style={{color: colorMap[status] || "var(--paw-text)"}}>
      <Wind size={11} />
      <span className="mono">{status?.toUpperCase()}</span>
    </span>
  );
}

function ChipWeather({ w }) {
  if (!w) return null;
  const Icon = WEATHER_ICONS[w.condition] || Cloud;
  return (
    <span className="commute-chip">
      <Icon size={11} />
      <span className="mono">{Math.round(w.temp_c)}°C · {w.condition}</span>
    </span>
  );
}

function ChipDist({ meters }) {
  return (
    <span className="commute-chip">
      <MapPin size={11} />
      <span className="mono">{(meters / 1000).toFixed(1)} km</span>
    </span>
  );
}

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "—";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}


// Phase 9b — single route-targeted opportunity card with kind chip,
// score, reason snippet, and a "Why this?" reveal.  Each card emits
// data-testid="route-opp-{kind}" so the testing agent can pick them
// up deterministically.
const KIND_META = {
  geo_proximity:      {icon: MapPin,    label: "Near route"},
  weather_triggered:  {icon: CloudRain, label: "Weather"},
  daypart_triggered:  {icon: Sun,       label: "Daypart"},
  traffic_triggered:  {icon: Wind,      label: "Traffic"},
  destination_arrival:{icon: Navigation,label: "Arriving"},
};
function RouteOppCard({ opp, onDismiss }) {
  const meta = KIND_META[opp.kind] || {icon: Sparkles, label: opp.kind};
  const Icon = meta.icon;
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="opp-card" data-testid={`route-opp-${opp.kind}`}>
      <div className="opp-card-head">
        <span className="opp-kind-pill"><Icon size={10} /> {meta.label}</span>
        <button className="opp-dismiss"
                  data-testid={`opp-dismiss-${opp.opp_id}`}
                  onClick={onDismiss} aria-label="Dismiss"><X size={11} /></button>
      </div>
      <div className="opp-title">{opp.campaign_title}</div>
      {opp.sponsor_name && <div className="opp-sponsor dim small">by {opp.sponsor_name}</div>}
      <div className="opp-chips">
        {opp.distance_from_route_m != null && (
          <span className="commute-chip">
            <MapPin size={10} />
            <span className="mono">
              {opp.distance_from_route_m < 1000
                ? `${Math.round(opp.distance_from_route_m)}m off-route`
                : `${(opp.distance_from_route_m / 1000).toFixed(1)}km off-route`}
            </span>
          </span>
        )}
        {opp.extra_drive_time_seconds != null && opp.extra_drive_time_seconds > 0 && (
          <span className="commute-chip">
            <Navigation size={10} />
            <span className="mono">+{Math.round(opp.extra_drive_time_seconds / 60)}m detour</span>
          </span>
        )}
        <span className="commute-chip score-chip">
          <Sparkles size={10} />
          <span className="mono">{Math.round((opp.score || 0) * 100)}</span>
        </span>
      </div>
      <button className="why-this-link" type="button"
                onClick={() => setExpanded((v) => !v)}
                data-testid={`opp-why-${opp.opp_id}`}>
        <Info size={11} /> Why this?
      </button>
      {expanded && (
        <ul className="opp-reasons" data-testid={`opp-reasons-${opp.opp_id}`}>
          {(opp.reason_codes || []).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── Phase 18 — exportable explainer hero (used inside Commute + tested
// directly to avoid the heavy map-bound parent render in jest).
export function CommuteExplainerHero() {
  return (
    <section data-testid="commute-explainer-hero"
                className="rounded-2xl border border-white/[0.08]
                                bg-bg-glass p-6 mx-4 mt-4 relative overflow-hidden">
      <div className="absolute -top-12 -right-12 w-72 h-72 rounded-full opacity-25"
            style={{ background:
              "radial-gradient(closest-side, var(--accent-electric), transparent)" }} />
      <div className="relative space-y-3 max-w-3xl">
        <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
          COMMUTE COMPANION
        </div>
        <h1 className="font-display font-bold text-4xl sm:text-5xl
                              tracking-display-tight"
            data-testid="commute-hero-headline">
          Drive smarter with FUUSIC.
        </h1>
        <p className="text-text-secondary text-sm sm:text-base max-w-2xl">
          Set your destination and we'll surface lunch deals, coffee
          stops, and events along your route — synced to your music
          and the time of day.
        </p>
        <ul className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-3 text-xs">
          <li className="flex items-start gap-2" data-testid="commute-hero-bullet-lunch">
            <Utensils size={14} className="text-accent-magenta mt-0.5 flex-shrink-0" />
            <span>Lunch deals 12–2 PM near your route</span>
          </li>
          <li className="flex items-start gap-2" data-testid="commute-hero-bullet-rain">
            <CloudRain size={14} className="text-accent-electric mt-0.5 flex-shrink-0" />
            <span>Rainy-day comfort-food picks</span>
          </li>
          <li className="flex items-start gap-2" data-testid="commute-hero-bullet-friday">
            <Sparkles size={14} className="text-accent-gold mt-0.5 flex-shrink-0" />
            <span>Friday-night events on your way home</span>
          </li>
        </ul>
        <button
          type="button"
          data-testid="commute-hero-cta"
          onClick={() => {
            const el = document.querySelector('[data-testid="origin-input"]');
            if (el) el.focus();
          }}
          className="mt-3 px-4 py-2 rounded-full bg-accent-electric text-bg-base
                            font-display font-bold text-sm tracking-display-tight
                            hover:scale-105 transition-transform inline-flex items-center gap-2">
          <Navigation size={14} /> Start a commute
        </button>
      </div>
    </section>
  );
}

