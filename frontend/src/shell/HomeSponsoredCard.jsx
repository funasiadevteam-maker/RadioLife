// Native local-business / offer card for the audio-first Home. Always
// visibly labelled SPONSORED, never disguised as organic personalization.
// Reuses the existing campaign / marketplace-promotion decisioning served
// by GET /api/shell/home. Fires native_offer_impression / _click analytics.
import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { API } from "@/AuthContext";
import { ChevronRight, MapPin, Coins } from "lucide-react";

export function fireHomeEvent(event, extra = {}) {
  try {
    axios.post(`${API}/shell/home-events`, { event, surface: "web", ...extra },
      { withCredentials: true }).catch(() => {});
  } catch (_e) { /* noop */ }
}

export default function HomeSponsoredCard({ offer }) {
  const navigate = useNavigate();
  const firedRef = useRef(false);
  useEffect(() => {
    if (offer && !firedRef.current) {
      firedRef.current = true;
      fireHomeEvent("native_offer_impression", {
        campaign_id: offer.campaign_id, business_id: offer.business_id, kind: offer.kind });
    }
  }, [offer]);
  if (!offer) return null;
  const go = () => {
    fireHomeEvent("native_offer_click", {
      campaign_id: offer.campaign_id, business_id: offer.business_id, kind: offer.kind });
    if (offer.to) navigate(offer.to);
  };
  return (
    <section data-testid="home-b-native-offer">
      <button type="button" onClick={go} data-testid="home-b-native-offer-card"
        className="w-full group flex items-center gap-4 rounded-token-card border border-accent-gold/25 bg-accent-gold/[0.05] p-3.5 sm:p-4 text-left hover:border-accent-gold/50 transition-colors">
        <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-token-md overflow-hidden shrink-0 bg-black/30">
          {offer.image
            ? <img src={offer.image} alt="" className="w-full h-full object-cover" />
            : <div className="w-full h-full grid place-items-center"><MapPin size={22} className="text-accent-gold" /></div>}
        </div>
        <div className="min-w-0 flex-1">
          <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded"
            style={{ background: "color-mix(in srgb, var(--accent-gold) 16%, transparent)", color: "var(--accent-gold)" }}>
            Sponsored
          </span>
          <div className="text-base sm:text-lg font-bold truncate mt-1">{offer.title}</div>
          <div className="text-sm text-text-secondary truncate">{offer.subtitle}</div>
        </div>
        <span className="shrink-0 hidden sm:inline-flex items-center gap-1.5 h-9 px-4 rounded-full bg-accent-gold text-black font-bold text-sm group-hover:brightness-110 transition">
          <Coins size={14} /> {offer.cta || "View offer"} <ChevronRight size={14} />
        </span>
        <ChevronRight size={18} className="sm:hidden shrink-0 text-accent-gold" />
      </button>
    </section>
  );
}
