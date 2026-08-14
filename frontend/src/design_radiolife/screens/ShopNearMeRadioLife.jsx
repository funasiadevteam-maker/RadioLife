// RadioLife Shop — "Near Me": shops & services around the user on a live map.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { ChevronLeft, Navigation, MapPin, Coins, Bike } from "lucide-react";
import { API } from "@/AuthContext";
import { formatDistance } from "@/lib/distance";

const DUBAI = { lat: 25.2048, lng: 55.2708 };

function Recenter({ lat, lng }) {
  const map = useMap();
  useEffect(() => { if (lat != null) map.setView([lat, lng], map.getZoom()); }, [lat, lng, map]);
  return null;
}

export default function ShopNearMeRadioLife() {
  const navigate = useNavigate();
  const [coords, setCoords] = useState(null);
  const [usingDefault, setUsingDefault] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [cat, setCat] = useState("all");
  const [denied, setDenied] = useState(false);

  const useMyLocation = useCallback(() => {
    if (!navigator.geolocation) { setCoords(DUBAI); setUsingDefault(true); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => { setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setUsingDefault(false); },
      () => { setDenied(true); setCoords(DUBAI); setUsingDefault(true); },
      { enableHighAccuracy: false, timeout: 8000 },
    );
  }, []);

  useEffect(() => { useMyLocation(); }, [useMyLocation]);

  const load = useCallback(async () => {
    if (!coords) return;
    setLoading(true);
    try {
      const r = await axios.get(`${API}/shop/businesses`, {
        params: { sort: "nearby", lat: coords.lat, lng: coords.lng, limit: 40 },
      });
      setItems(r.data.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [coords]);
  useEffect(() => { load(); }, [load]);

  const cats = useMemo(() => {
    const set = new Map();
    items.forEach((b) => { if (b.category) set.set(b.category, true); });
    return ["all", ...Array.from(set.keys())];
  }, [items]);
  const filtered = useMemo(
    () => (cat === "all" ? items : items.filter((b) => b.category === cat)),
    [items, cat]);
  const mapped = filtered.filter((b) => b.geo);

  return (
    <div className="pb-24" data-testid="rl-near-me-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="near-me-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Near You</h1>
      </div>

      {coords && (
        <div className="px-4 mt-3">
          <div className="rounded-2xl overflow-hidden border border-slate-200" style={{ height: 260 }} data-testid="near-me-map">
            <MapContainer center={[coords.lat, coords.lng]} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
              <Recenter lat={coords.lat} lng={coords.lng} />
              <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <CircleMarker center={[coords.lat, coords.lng]} radius={8} pathOptions={{ color: "#2563eb", fillColor: "#2563eb", fillOpacity: 0.9 }}>
                <Popup>You are here</Popup>
              </CircleMarker>
              {mapped.map((b) => (
                <CircleMarker key={b.business_id} center={[b.geo.lat, b.geo.lng]} radius={9}
                  pathOptions={{ color: "#ea580c", fillColor: "#ea580c", fillOpacity: 0.85 }}>
                  <Popup>
                    <div className="font-black text-slate-900">{b.public_name}</div>
                    <div className="text-xs text-slate-500 capitalize">{b.subcategory || b.category}</div>
                    <button onClick={() => navigate(`/shop/${b.business_id}`)} className="mt-1 text-orange-600 font-bold text-xs">Open →</button>
                  </Popup>
                </CircleMarker>
              ))}
            </MapContainer>
          </div>
        </div>
      )}

      {usingDefault && (
        <div className="px-4 mt-2 text-xs font-bold text-slate-500 flex items-center gap-1" data-testid="near-me-default-note">
          <MapPin size={13} className="text-orange-600" />
          {denied ? "Location blocked — showing Dubai. " : "Showing Dubai. "}
          <button onClick={useMyLocation} className="text-orange-600 font-black" data-testid="near-me-use-location">Use my location</button>
        </div>
      )}

      <div className="px-4 mt-3 flex gap-2 overflow-x-auto pb-1" data-testid="near-me-cats">
        {cats.map((c) => (
          <button key={c} onClick={() => setCat(c)} data-testid={`near-me-cat-${c}`}
            className={`shrink-0 px-3.5 h-9 rounded-full text-xs font-black capitalize whitespace-nowrap border ${cat === c ? "bg-orange-600 text-white border-orange-600" : "bg-slate-100 text-slate-600 border-slate-200"}`}>
            {c === "all" ? "All" : c}
          </button>
        ))}
      </div>

      <div className="px-4 mt-3 space-y-2" data-testid="near-me-list">
        {loading && <div className="text-center text-slate-400 py-8 text-sm">Finding places near you…</div>}
        {!loading && filtered.length === 0 && <div className="text-center text-slate-400 py-8 text-sm">No places found nearby.</div>}
        {filtered.map((b) => (
          <Link key={b.business_id} to={`/shop/${b.business_id}`} data-testid={`near-me-biz-${b.business_id}`}
            className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-2.5 hover:border-orange-300 transition-colors">
            <img src={b.cover_url} alt="" className="w-16 h-16 rounded-xl object-cover bg-slate-100" />
            <div className="min-w-0 flex-1">
              <div className="font-black text-slate-900 truncate">{b.public_name}</div>
              <div className="text-xs text-slate-500 capitalize truncate">{b.subcategory || b.category}</div>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="inline-flex items-center gap-1 bg-amber-100 text-amber-800 text-[10px] font-black px-2 py-0.5 rounded-full">₿ Earn {b.default_bigpoints}</span>
                {b.delivery_enabled && <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 text-[10px] font-black px-2 py-0.5 rounded-full"><Bike size={10} />Delivery</span>}
              </div>
            </div>
            {b.distance_km != null && (
              <div className="text-center" data-testid={`near-me-dist-${b.business_id}`}>
                <Navigation size={13} className="text-orange-600 mx-auto" />
                <div className="text-xs font-black text-orange-600 mt-0.5">{formatDistance(b.distance_km)}</div>
              </div>
            )}
          </Link>
        ))}
      </div>

      {!coords && (
        <div className="px-4 mt-8 text-center">
          <Coins size={36} className="mx-auto text-slate-300" />
          <p className="text-slate-500 mt-3 text-sm">Getting your location…</p>
        </div>
      )}
    </div>
  );
}
