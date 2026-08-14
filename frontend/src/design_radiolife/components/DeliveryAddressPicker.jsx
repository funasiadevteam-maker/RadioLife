// Delivery address picker (web) — click the map to drop a pin, use my location,
// or type an address. Resolves to a jurisdiction (for destination tax) + lat/lng.
import React, { useState } from "react";
import { MapContainer, TileLayer, CircleMarker, useMapEvents, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin, Navigation, Search } from "lucide-react";
import { reverseGeocode, forwardGeocode } from "../lib/geocode";

function ClickToPin({ onPick }) {
  useMapEvents({
    click: async (e) => {
      const geo = await reverseGeocode(e.latlng.lat, e.latlng.lng);
      onPick(geo || { label: `${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}`, lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

function Recenter({ lat, lng }) {
  const map = useMap();
  React.useEffect(() => { if (lat != null && lng != null) map.setView([lat, lng], 15); }, [lat, lng, map]);
  return null;
}

export default function DeliveryAddressPicker({ value, onChange }) {
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState(null);
  const center = value && value.lat != null ? [value.lat, value.lng] : [25.2048, 55.2708]; // default Dubai

  const useMyLocation = () => {
    setErr(null);
    if (!navigator.geolocation) { setErr("Location isn't available. Type your address."); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(async (pos) => {
      const geo = await reverseGeocode(pos.coords.latitude, pos.coords.longitude);
      onChange(geo || { label: "My location", lat: pos.coords.latitude, lng: pos.coords.longitude });
      setBusy(false);
    }, () => { setErr("Couldn't get your location. Type your address instead."); setBusy(false); }, { enableHighAccuracy: false, timeout: 8000 });
  };

  const findTyped = async () => {
    const q = typed.trim();
    if (!q) return;
    setErr(null); setBusy(true);
    const geo = await forwardGeocode(q);
    if (!geo) setErr("Address not found. Add a city/country.");
    else onChange(geo);
    setBusy(false);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="checkout-delivery-address">
      <div className="flex items-center gap-2 mb-2">
        <MapPin size={18} className="text-orange-600" />
        <div className="font-bold text-slate-900 text-sm">Delivery address</div>
      </div>
      <div className="flex gap-2 mb-2">
        <button onClick={useMyLocation} disabled={busy} data-testid="delivery-use-location"
          className="flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-full px-3.5 py-2 text-xs disabled:opacity-60">
          <Navigation size={13} />Use my location
        </button>
        <div className="flex-1 flex gap-2">
          <input value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === "Enter" && findTyped()}
            placeholder="Street, city, country" data-testid="delivery-address-input"
            className="flex-1 rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-sm" />
          <button onClick={findTyped} disabled={busy} data-testid="delivery-address-find"
            className="flex items-center gap-1 bg-slate-900 text-white font-black rounded-full px-3 text-xs"><Search size={13} />Find</button>
        </div>
      </div>
      <div className="rounded-xl overflow-hidden border border-slate-200" style={{ height: 180 }} data-testid="delivery-map">
        <MapContainer center={center} zoom={13} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
          <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <ClickToPin onPick={onChange} />
          {value && value.lat != null && (
            <>
              <CircleMarker center={[value.lat, value.lng]} radius={9} pathOptions={{ color: "#ea580c", fillColor: "#ea580c", fillOpacity: 0.85 }} />
              <Recenter lat={value.lat} lng={value.lng} />
            </>
          )}
        </MapContainer>
      </div>
      {value && value.lat != null ? (
        <div className="mt-2" data-testid="delivery-address-label">
          <div className="text-sm font-bold text-slate-900 line-clamp-2">{value.label || value.line1}</div>
          <div className="text-xs text-slate-500 mt-0.5">{[value.city, value.state, value.country].filter(Boolean).join(", ")} · tax charged at your location</div>
        </div>
      ) : <div className="mt-2 text-xs text-slate-500">Tap the map to drop a pin, use your location, or type an address.</div>}
      {err && <div className="mt-2 text-xs font-semibold text-rose-600" data-testid="delivery-address-error">{err}</div>}
    </div>
  );
}
