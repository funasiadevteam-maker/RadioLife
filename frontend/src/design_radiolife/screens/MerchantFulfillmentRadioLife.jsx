// RadioLife Merchant — Fees & Fulfillment settings (owner.com-style service
// fee pass-through, delivery fee + ETA, prep time, and store location).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { MapContainer, TileLayer, CircleMarker, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { ChevronLeft, Percent, Bike, Clock, MapPin, Check, Receipt } from "lucide-react";
import { API } from "@/AuthContext";

const DUBAI = { lat: 25.2048, lng: 55.2708 };

function LocationPicker({ lat, lng, onPick }) {
  useMapEvents({ click(e) { onPick(e.latlng.lat, e.latlng.lng); } });
  return (lat != null && lng != null)
    ? <CircleMarker center={[lat, lng]} radius={9} pathOptions={{ color: "#ea580c", fillColor: "#ea580c", fillOpacity: 0.85 }} />
    : null;
}

export default function MerchantFulfillmentRadioLife() {
  const navigate = useNavigate();
  const [sf, setSf] = useState({ enabled: false, percent: 0 });
  const [dl, setDl] = useState({ enabled: false, fee_cents: 0, eta_min: 30, eta_max: 45, min_order_cents: 0 });
  const [prep, setPrep] = useState(20);
  const [geo, setGeo] = useState({ lat: null, lng: null, address: "" });
  const [tax, setTax] = useState({ country: "", state: "", county: "", city: "" });
  const [taxOverride, setTaxOverride] = useState({ enabled: false, rate_percent: 0, label: "" });
  const [aiBusy, setAiBusy] = useState(false);
  const [aiMsg, setAiMsg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    axios.get(`${API}/merchant/marketplace/fulfillment`).then((r) => {
      setSf(r.data.service_fee || { enabled: false, percent: 0 });
      setDl(r.data.delivery || { enabled: false, fee_cents: 0, eta_min: 30, eta_max: 45, min_order_cents: 0 });
      setPrep(r.data.prep_time_min ?? 20);
      setGeo(r.data.geo || { lat: null, lng: null, address: "" });
      setTax(r.data.tax_jurisdiction || { country: "", state: "", county: "", city: "" });
      setTaxOverride(r.data.tax_override || { enabled: false, rate_percent: 0, label: "" });
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const aiFillTax = async () => {
    setAiBusy(true); setAiMsg(null);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/tax/ai-estimate`, {
        country: tax.country || null, state: tax.state || null,
        county: tax.county || null, city: tax.city || null,
      });
      setTaxOverride({ enabled: true, rate_percent: r.data.rate_percent, label: r.data.label || "Local tax" });
      setAiMsg(`AI suggests ${r.data.rate_percent}% (${r.data.label}). Review & Save.`);
    } catch (e) {
      setAiMsg(e?.response?.data?.detail?.message || "Set your store country first, then try AI.");
    } finally { setAiBusy(false); }
  };

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await axios.patch(`${API}/merchant/marketplace/fulfillment`, {
        service_fee: { enabled: !!sf.enabled, percent: Number(sf.percent) || 0 },
        delivery: {
          enabled: !!dl.enabled, fee_cents: Math.round(Number(dl.fee_cents) || 0),
          eta_min: Number(dl.eta_min) || 0, eta_max: Number(dl.eta_max) || 0,
          min_order_cents: Math.round(Number(dl.min_order_cents) || 0),
        },
        prep_time_min: Number(prep) || 0,
        geo: { lat: geo.lat, lng: geo.lng, address: geo.address || null },
        tax_jurisdiction: {
          country: tax.country || null, state: tax.state || null,
          county: tax.county || null, city: tax.city || null,
        },
        tax_override: {
          enabled: !!taxOverride.enabled,
          rate_percent: Number(taxOverride.rate_percent) || 0,
          label: taxOverride.label || null,
        },
      });
      setSaved(true);
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  if (loading) return <div className="px-4 pt-16 text-center text-slate-500">Loading settings…</div>;

  const center = geo.lat != null ? [geo.lat, geo.lng] : [DUBAI.lat, DUBAI.lng];

  return (
    <div className="pb-32" data-testid="rl-merchant-fulfillment-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="fulfillment-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Fees &amp; Fulfillment</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {/* Service fee */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="fulfillment-service-fee">
          <div className="flex items-center gap-2">
            <Percent size={18} className="text-orange-600" />
            <div className="font-black text-slate-900 flex-1">Service fee</div>
            <button onClick={() => setSf((s) => ({ ...s, enabled: !s.enabled }))} data-testid="service-fee-toggle"
              className={`w-12 h-7 rounded-full transition-colors ${sf.enabled ? "bg-orange-600" : "bg-slate-300"} relative`}>
              <span className={`absolute top-0.5 w-6 h-6 bg-white rounded-full transition-all ${sf.enabled ? "left-[22px]" : "left-0.5"}`} />
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-1">Pass part of the platform commission to the customer as a % of their order.</p>
          {sf.enabled && (
            <div className="mt-3 flex items-center gap-2">
              <input type="number" min={0} max={30} step={0.5} value={sf.percent} data-testid="service-fee-percent"
                onChange={(e) => setSf((s) => ({ ...s, percent: e.target.value }))}
                className="w-24 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black" />
              <span className="text-sm font-bold text-slate-600">% of subtotal</span>
            </div>
          )}
        </div>

        {/* Delivery */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="fulfillment-delivery">
          <div className="flex items-center gap-2">
            <Bike size={18} className="text-green-600" />
            <div className="font-black text-slate-900 flex-1">Delivery</div>
            <button onClick={() => setDl((d) => ({ ...d, enabled: !d.enabled }))} data-testid="delivery-toggle"
              className={`w-12 h-7 rounded-full transition-colors ${dl.enabled ? "bg-green-600" : "bg-slate-300"} relative`}>
              <span className={`absolute top-0.5 w-6 h-6 bg-white rounded-full transition-all ${dl.enabled ? "left-[22px]" : "left-0.5"}`} />
            </button>
          </div>
          {dl.enabled && (
            <div className="mt-3 space-y-3">
              <label className="block">
                <span className="text-xs font-black text-slate-500 uppercase tracking-wide">Delivery fee ($)</span>
                <input type="number" min={0} step={0.5} value={(dl.fee_cents / 100).toFixed(2)} data-testid="delivery-fee"
                  onChange={(e) => setDl((d) => ({ ...d, fee_cents: Math.round(Number(e.target.value) * 100) }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black" />
              </label>
              <div className="flex gap-3">
                <label className="flex-1">
                  <span className="text-xs font-black text-slate-500 uppercase tracking-wide">ETA min</span>
                  <input type="number" min={0} value={dl.eta_min} data-testid="delivery-eta-min"
                    onChange={(e) => setDl((d) => ({ ...d, eta_min: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black" />
                </label>
                <label className="flex-1">
                  <span className="text-xs font-black text-slate-500 uppercase tracking-wide">ETA max</span>
                  <input type="number" min={0} value={dl.eta_max} data-testid="delivery-eta-max"
                    onChange={(e) => setDl((d) => ({ ...d, eta_max: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black" />
                </label>
              </div>
              <label className="block">
                <span className="text-xs font-black text-slate-500 uppercase tracking-wide">Minimum order ($)</span>
                <input type="number" min={0} step={0.5} value={(dl.min_order_cents / 100).toFixed(2)} data-testid="delivery-min-order"
                  onChange={(e) => setDl((d) => ({ ...d, min_order_cents: Math.round(Number(e.target.value) * 100) }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black" />
              </label>
            </div>
          )}
        </div>

        {/* Prep time */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="fulfillment-prep">
          <div className="flex items-center gap-2">
            <Clock size={18} className="text-slate-700" />
            <div className="font-black text-slate-900 flex-1">Prep time</div>
            <input type="number" min={0} value={prep} data-testid="prep-time"
              onChange={(e) => setPrep(e.target.value)}
              className="w-20 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-black text-center" />
            <span className="text-sm font-bold text-slate-600">min</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">Used for the customer&apos;s pickup ETA.</p>
        </div>

        {/* Store location */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="fulfillment-geo">
          <div className="flex items-center gap-2 mb-2">
            <MapPin size={18} className="text-orange-600" />
            <div className="font-black text-slate-900">Store location</div>
          </div>
          <p className="text-xs text-slate-500 mb-2">Tap the map to drop your pin — powers &ldquo;near me&rdquo; discovery.</p>
          <div className="rounded-xl overflow-hidden border border-slate-200" style={{ height: 200 }} data-testid="fulfillment-map">
            <MapContainer center={center} zoom={12} style={{ height: "100%", width: "100%" }} scrollWheelZoom>
              <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <LocationPicker lat={geo.lat} lng={geo.lng}
                onPick={(lat, lng) => setGeo((g) => ({ ...g, lat: Number(lat.toFixed(5)), lng: Number(lng.toFixed(5)) }))} />
            </MapContainer>
          </div>
          <input value={geo.address || ""} onChange={(e) => setGeo((g) => ({ ...g, address: e.target.value }))}
            placeholder="Address (optional)" data-testid="geo-address"
            className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
          {geo.lat != null && <div className="text-[11px] text-slate-400 mt-1">Pin: {geo.lat}, {geo.lng}</div>}
        </div>

        {/* Sales tax jurisdiction */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="fulfillment-tax">
          <div className="flex items-center gap-2 mb-2">
            <Receipt size={18} className="text-slate-700" />
            <div className="font-black text-slate-900">Sales tax jurisdiction</div>
          </div>
          <p className="text-xs text-slate-500 mb-3">Where your store is based — tax is charged at your local rate (origin-based). Admin sets the actual rates.</p>
          <div className="grid grid-cols-2 gap-2">
            <input value={tax.country || ""} onChange={(e) => setTax((t) => ({ ...t, country: e.target.value }))}
              placeholder="Country (e.g. AE)" data-testid="tax-country"
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
            <input value={tax.state || ""} onChange={(e) => setTax((t) => ({ ...t, state: e.target.value }))}
              placeholder="State (optional)" data-testid="tax-state"
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
            <input value={tax.county || ""} onChange={(e) => setTax((t) => ({ ...t, county: e.target.value }))}
              placeholder="County (optional)" data-testid="tax-county"
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
            <input value={tax.city || ""} onChange={(e) => setTax((t) => ({ ...t, city: e.target.value }))}
              placeholder="City (optional)" data-testid="tax-city"
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
          </div>

          {/* Self-serve override + AI fill */}
          <div className="mt-4 border-t border-slate-100 pt-3">
            <button onClick={aiFillTax} disabled={aiBusy} data-testid="tax-ai-fill"
              className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white font-black rounded-full py-2.5 text-sm disabled:opacity-60">
              {aiBusy ? "Asking AI…" : "✨ AI fill my local tax rate"}
            </button>
            {aiMsg && <div className="mt-2 text-xs font-bold text-orange-600" data-testid="tax-ai-msg">{aiMsg}</div>}
            <label className="flex items-center gap-2 mt-3 cursor-pointer" data-testid="tax-override-toggle">
              <input type="checkbox" checked={!!taxOverride.enabled}
                onChange={(e) => setTaxOverride((o) => ({ ...o, enabled: e.target.checked }))}
                className="w-4 h-4 accent-orange-600" />
              <span className="text-sm font-bold text-slate-900">Use my own rate (overrides admin rules for pickup)</span>
            </label>
            {taxOverride.enabled && (
              <div className="grid grid-cols-2 gap-2 mt-2">
                <input type="number" step="0.01" value={taxOverride.rate_percent ?? 0}
                  onChange={(e) => setTaxOverride((o) => ({ ...o, rate_percent: e.target.value }))}
                  placeholder="Rate %" data-testid="tax-override-rate"
                  className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
                <input value={taxOverride.label || ""}
                  onChange={(e) => setTaxOverride((o) => ({ ...o, label: e.target.value }))}
                  placeholder="Label (e.g. VAT)" data-testid="tax-override-label"
                  className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
              </div>
            )}
            <p className="text-[11px] text-slate-400 mt-2">Delivery orders are taxed at the customer's location. AI is a convenience estimate — you remain responsible for filing & remitting.</p>
          </div>
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 max-w-md mx-auto p-4 bg-white/90 backdrop-blur border-t border-slate-200">
        <button onClick={save} disabled={saving} data-testid="fulfillment-save"
          className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3.5 disabled:opacity-60">
          {saving ? "Saving…" : saved ? <><Check size={18} />Saved</> : "Save settings"}
        </button>
      </div>
    </div>
  );
}
