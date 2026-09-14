// Dining Club — meal pass: restaurant reveal + single-use QR to present in-store.
import React, { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import QRCode from "react-qr-code";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ChevronLeft, MapPin, Navigation, Clock, Loader2, CheckCircle2 } from "lucide-react";
import { diningApi, DINE, money, errCode } from "./diningApi";
import { Shell, GhostBtn } from "./DiningHome";

export default function DiningPass() {
  const nav = useNavigate();
  const { orderId } = useParams();
  const [sp] = useSearchParams();
  const sessionId = sp.get("session_id");
  const queryOrder = sp.get("order_id") || orderId;
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let stop = false, tries = 0;
    const run = async () => {
      try {
        if (sessionId) {
          const r = await diningApi.checkoutStatus(sessionId);
          if (r.status === "paid") { const p = await diningApi.pass(r.order_id); if (!stop) { setData(p); setStatus("ready"); } return; }
          if (!stop && tries++ < 20) setTimeout(run, 2000); else if (!stop) setStatus("pending");
          return;
        }
        const p = await diningApi.pass(queryOrder);
        if (!stop) { setData(p); setStatus(p?.order?.status === "paid" ? "ready" : "pending"); }
      } catch (e) { if (!stop) { toast.error(errCode(e)); setStatus("error"); } }
    };
    run();
    return () => { stop = true; };
  }, [sessionId, queryOrder]);

  const r = data?.restaurant, meal = data?.meal, qr = data?.qr;

  return (
    <Shell>
      <button onClick={() => nav("/dining")} className="flex items-center gap-1 mb-6 text-sm" style={{ color: DINE.muted }} data-testid="pass-back">
        <ChevronLeft size={16} /> Dining Club
      </button>

      {status === "loading" || status === "pending" ? (
        <div className="text-center py-20" data-testid="pass-pending">
          <Loader2 className="animate-spin mx-auto mb-4" color={DINE.cyan} size={32} />
          <p style={{ color: DINE.muted }}>{status === "pending" ? "Confirming your payment…" : "Loading your pass…"}</p>
        </div>
      ) : status === "error" ? (
        <p className="text-center py-20" style={{ color: DINE.muted }}>Couldn't load this pass.</p>
      ) : (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} data-testid="pass-ready">
          <div className="flex items-center justify-center gap-2 mb-2">
            <CheckCircle2 color={DINE.cyan} size={18} />
            <span className="text-[11px] font-mono uppercase" style={{ color: DINE.cyan, letterSpacing: "0.16em" }}>Meal confirmed</span>
          </div>
          <h1 className="text-4xl font-black text-center mb-6" style={{ color: DINE.text }} data-testid="pass-restaurant">{r?.name}</h1>

          <div className="rounded-3xl p-6 mb-6 flex flex-col items-center" style={{ background: "#ffffff", border: `1px solid ${DINE.border}` }}>
            <span className="text-[11px] font-mono uppercase mb-3" style={{ color: "#6b7280", letterSpacing: "0.14em" }}>Show this at the counter</span>
            {qr?.qr_token ? <QRCode value={qr.qr_token} size={196} bgColor="#ffffff" fgColor="#0a0c18" data-testid="pass-qr" /> : null}
            <span className="mt-3 font-black text-lg" style={{ color: "#0a0c18" }}>{meal?.title || "Chef's selected meal"} · {money(data?.order?.amount_cents)}</span>
          </div>

          <div className="rounded-3xl p-6" style={{ background: DINE.card, border: `1px solid ${DINE.border}` }}>
            <Row icon={<MapPin size={16} color={DINE.pink} />} text={r?.address} />
            {r?.distance_miles != null && <Row icon={<Navigation size={16} color={DINE.cyan} />} text={`${r.distance_miles} miles away`} />}
            {r?.hours && <Row icon={<Clock size={16} color={DINE.gold} />} text={r.hours} />}
          </div>

          {r?.lat && r?.lng && (
            <div className="mt-4">
              <GhostBtn testid="pass-directions" onClick={() => window.open(`https://maps.google.com/?q=${r.lat},${r.lng}`, "_blank")}>
                <Navigation size={16} /> Get directions
              </GhostBtn>
            </div>
          )}
          <p className="text-center text-xs mt-4" style={{ color: DINE.muted }}>Single-use QR — valid until redeemed by the restaurant.</p>
        </motion.div>
      )}
    </Shell>
  );
}

function Row({ icon, text }) {
  if (!text) return null;
  return <div className="flex items-center gap-3 py-1.5" style={{ color: DINE.text }}>{icon}<span className="text-sm">{text}</span></div>;
}
