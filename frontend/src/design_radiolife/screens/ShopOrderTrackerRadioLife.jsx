// RadioLife Shop — live Order Tracker: poll status, "getting ready" stepper,
// store map, and a ready-for-pickup heads-up.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { ChevronLeft, Clock, CheckCircle2, Store, Timer, Footprints } from "lucide-react";
import { API } from "@/AuthContext";
import { routeLine } from "../lib/geocode";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const STEPS = ["accepted", "preparing", "ready", "picked_up"];
const STEP_LABELS = ["Accepted", "Preparing", "Ready", "Picked up"];
const LABELS = {
  pending_payment: "Awaiting Payment", accepted: "Order accepted",
  preparing: "Getting your order ready", ready: "Ready — head over!",
  picked_up: "Picked up · enjoy!", canceled: "Canceled",
};
const fmtClock = (ms) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

export default function ShopOrderTrackerRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/order/")[1];
  const [order, setOrder] = useState(null);
  const [geo, setGeo] = useState(null);
  const [route, setRoute] = useState(null);
  const [nowTs, setNowTs] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const prevStatus = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/shop/orders/${id}/status`);
      const o = r.data.order;
      prevStatus.current = o.status;
      setOrder(o);
      if (o.business_id) {
        axios.get(`${API}/shop/businesses/${o.business_id}`)
          .then((b) => setGeo((b.data.business || b.data).geo || null)).catch(() => {});
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!order || ["picked_up", "canceled"].includes(order.status)) return;
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [order, load]);

  // Live prep countdown — tick every second until ready.
  useEffect(() => {
    if (!order || ["ready", "picked_up", "canceled"].includes(order.status)) return;
    const t = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [order?.status]);

  // Delivery route (store → customer).
  const dest = order?.delivery_address;
  useEffect(() => {
    if (order?.fulfillment === "delivery" && geo && dest?.lat != null && dest?.lng != null) {
      routeLine({ lat: geo.lat, lng: geo.lng }, { lat: dest.lat, lng: dest.lng }).then(setRoute).catch(() => {});
    }
  }, [order?.fulfillment, geo, dest?.lat, dest?.lng]);

  if (loading) return <div className="px-4 pt-16 text-center text-slate-500">Loading order…</div>;
  if (!order) return <div className="px-4 pt-16 text-center text-slate-500">Order not found.</div>;

  const stepIdx = STEPS.indexOf(order.status);
  const isReady = order.status === "ready";
  const isDelivery = order.fulfillment === "delivery";
  const hasDest = isDelivery && dest?.lat != null && dest?.lng != null;
  const readyAt = order.ready_at ? Date.parse(order.ready_at) : null;
  const remainingMs = readyAt != null ? readyAt - nowTs : null;
  const showTimer = ["accepted", "preparing"].includes(order.status) && remainingMs != null;
  const mapCenter = geo ? (hasDest ? [(geo.lat + dest.lat) / 2, (geo.lng + dest.lng) / 2] : [geo.lat, geo.lng]) : null;

  return (
    <div className="pb-24" data-testid="rl-order-tracker-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate("/shop/orders")} data-testid="tracker-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Order Tracker</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        <div className={`rounded-2xl p-4 flex items-center gap-3 border ${isReady ? "bg-green-50 border-green-300" : "bg-orange-50 border-orange-200"}`} data-testid="tracker-status">
          {isReady ? <CheckCircle2 size={24} className="text-green-600" /> : <Clock size={24} className="text-orange-600" />}
          <div className="flex-1">
            <div className="font-black text-slate-900">{LABELS[order.status] || order.status}</div>
            {order.eta_label && order.status !== "picked_up" && (
              <div className="text-sm font-bold text-orange-600" data-testid="tracker-eta">{isDelivery ? `Arrives in ${order.eta_label}` : order.eta_label}</div>
            )}
          </div>
        </div>

        {showTimer && (
          <div className="rounded-2xl p-4 flex items-center gap-3 border border-orange-200 bg-orange-50" data-testid="tracker-timer">
            <Timer size={22} className="text-orange-600" />
            <div className="font-black text-slate-900 text-lg">
              {remainingMs > 0 ? `${isDelivery ? "Arriving" : "Ready"} in ${fmtClock(remainingMs)}` : `Almost ${isDelivery ? "there" : "ready"}…`}
            </div>
          </div>
        )}
        {isReady && (
          <div className="rounded-2xl p-4 flex items-center gap-3 border border-green-300 bg-green-50" data-testid="tracker-ready-nudge">
            <Footprints size={22} className="text-green-600" />
            <div className="font-black text-slate-900">{isDelivery ? "On its way — get ready to receive it!" : "Your order is ready — head over now!"}</div>
          </div>
        )}

        {order.status !== "canceled" && stepIdx >= 0 && (
          <div className="flex items-start justify-between px-2">
            {STEPS.map((st, idx) => (
              <React.Fragment key={st}>
                <div className="flex flex-col items-center" style={{ width: 64 }}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${idx <= stepIdx ? "bg-green-600" : "bg-slate-200"}`}>
                    {idx <= stepIdx && <CheckCircle2 size={14} className="text-white" />}
                  </div>
                  <span className={`text-[10px] font-bold mt-1.5 text-center ${idx <= stepIdx ? "text-slate-900" : "text-slate-400"}`}>{STEP_LABELS[idx]}</span>
                </div>
                {idx < STEPS.length - 1 && <div className={`flex-1 h-0.5 mt-3 ${idx < stepIdx ? "bg-green-600" : "bg-slate-200"}`} />}
              </React.Fragment>
            ))}
          </div>
        )}

        {mapCenter && (
          <div className="rounded-2xl overflow-hidden border border-slate-200" style={{ height: 200 }} data-testid="tracker-map">
            <MapContainer center={mapCenter} zoom={hasDest ? 13 : 15} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
              <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
              <CircleMarker center={[geo.lat, geo.lng]} radius={10} pathOptions={{ color: "#ea580c", fillColor: "#ea580c", fillOpacity: 0.85 }}>
                <Popup>{order.business_name}</Popup>
              </CircleMarker>
              {hasDest && (
                <CircleMarker center={[dest.lat, dest.lng]} radius={10} pathOptions={{ color: "#16a34a", fillColor: "#16a34a", fillOpacity: 0.85 }}>
                  <Popup>Delivery address</Popup>
                </CircleMarker>
              )}
              {route && route.length > 1 && <Polyline positions={route} pathOptions={{ color: "#ea580c", weight: 4 }} />}
            </MapContainer>
          </div>
        )}

        <div className="bg-white border border-slate-200 rounded-2xl p-4">
          <div className="flex items-center gap-2 font-black text-slate-900"><Store size={16} className="text-orange-600" />{order.business_name}</div>
          <div className="text-sm text-slate-500 mt-1">{(order.items || []).reduce((n, i) => n + i.qty, 0)} items · {money(order.total_cents)}</div>
          {order.service_fee_cents > 0 && <div className="text-xs text-slate-400 mt-1">Service fee {money(order.service_fee_cents)}</div>}
          {order.delivery_fee_cents > 0 && <div className="text-xs text-slate-400">Delivery fee {money(order.delivery_fee_cents)}</div>}
          {order.tax_cents > 0 && <div className="text-xs text-slate-400">{order.tax_label || "Tax"} {money(order.tax_cents)}</div>}
          <div className="inline-block mt-3 bg-slate-100 rounded-xl px-4 py-2">
            <div className="text-[9px] font-black tracking-widest text-slate-400">{isDelivery ? "ORDER CODE" : "PICKUP CODE"}</div>
            <div className="text-2xl font-black tracking-[0.25em] text-slate-900" data-testid="tracker-code">{order.pickup_code}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
