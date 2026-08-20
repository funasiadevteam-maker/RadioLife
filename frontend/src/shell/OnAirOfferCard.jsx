// Contextual on-air offer (§6.6) — docked ABOVE the player, only while
// audio is playing. Surfaces a nearby merchant offer for the current
// station + user geo. Kept for Premium (this is the radio×digital bundle
// unit; only rotating promos were removed from the player).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, X, MapPin } from "lucide-react";
import axios from "axios";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useGeoStore } from "@/store/useGeoStore";

export default function OnAirOfferCard() {
  const playing = usePlayerStore((s) => s.playing);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const channelName = usePlayerStore((s) => s.activeChannelName);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const city = useGeoStore((s) => s.city);
  const navigate = useNavigate();
  const [offer, setOffer] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  const station = importedStation?.name || channelName || null;

  useEffect(() => {
    if (!playing || offer) return;
    const params = new URLSearchParams({ limit: "6" });
    if (city) params.set("city", city);
    axios.get(`${API}/offers/nearby?${params.toString()}`, { withCredentials: true })
      .then((r) => {
        const items = r.data?.items || [];
        if (items.length) setOffer(items[Math.floor(Math.random() * items.length)]);
      })
      .catch(() => { /* no offers nearby — card stays hidden */ });
  }, [playing, city, offer]);

  if (!playing || podcastEpisode || !station || !offer || dismissed) return null;

  const merchant = offer.title || "A local spot";
  const deal = offer.discount_label || offer.offer_type || "offer";

  return (
    <div data-testid="player-contextual-offer"
      className="rl-card px-3.5 py-2.5 flex items-center gap-3 mb-2 max-w-3xl mx-auto pointer-events-auto">
      <span className="shrink-0 inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded"
        style={{ background: "color-mix(in srgb, var(--accent-gold) 16%, transparent)", color: "var(--accent-gold)" }}>
        <MapPin size={10} /> On air
      </span>
      <div className="min-w-0 flex-1 text-sm truncate">
        <span className="text-text-secondary">On </span>
        <span className="font-bold text-text-primary">{station}</span>
        <span className="text-text-secondary"> — </span>
        <span className="font-bold text-text-primary">{merchant}</span>
        <span className="text-text-secondary"> · {deal} near you</span>
      </div>
      <button onClick={() => navigate("/shop")} data-testid="player-offer-claim"
        className="shrink-0 inline-flex items-center gap-1.5 bg-accent-gold text-black font-black rounded-full h-8 px-3 text-xs hover:brightness-110 transition">
        <Coins size={13} /> Claim offer
      </button>
      <button onClick={() => setDismissed(true)} data-testid="player-offer-dismiss" aria-label="Dismiss offer"
        className="shrink-0 w-7 h-7 grid place-items-center rounded-full text-text-secondary hover:text-text-primary">
        <X size={15} />
      </button>
    </div>
  );
}
