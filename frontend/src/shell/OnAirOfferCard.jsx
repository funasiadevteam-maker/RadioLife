// Contextual on-air companion (§6.6 + Phase COMPANION.1) — docked ABOVE
// the player while audio is playing.
//
//   • SYNCED mode: when an audio ad (mid-roll) with a companion offer is
//     playing, we surface THAT campaign's offer — claimable (save to
//     wallet / visit) without leaving the audio. Fires companion_*
//     analytics against the existing attribution funnel.
//   • FALLBACK mode: otherwise, a nearby merchant offer for the current
//     station + user geo (the radio×digital bundle unit; kept for Premium).
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, X, MapPin, Sparkles, ShoppingBag, ExternalLink } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useGeoStore } from "@/store/useGeoStore";

function fireHomeEvent(event, extra) {
  try {
    axios.post(`${API}/shell/home-events`,
      { event, surface: "web", kind: "companion", ...extra },
      { withCredentials: true }).catch(() => {});
  } catch (_e) { /* noop */ }
}

// ─── SYNCED companion (driven by the currently-playing audio ad) ──────
function SyncedCompanion({ companion }) {
  const setActiveCompanion = usePlayerStore((s) => s.setActiveCompanion);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const firedRef = useRef(null);

  useEffect(() => {
    if (companion && firedRef.current !== companion.impression_id) {
      firedRef.current = companion.impression_id;
      setSaved(false);
      fireHomeEvent("companion_impression",
        { campaign_id: companion.impression_id, business_id: companion.offer_id });
    }
  }, [companion]);

  const sponsor = companion.advertiser_name || companion.name || "Sponsored";
  const headline = companion.cta_text || companion.name || "Featured offer";

  const onClaim = async () => {
    fireHomeEvent("companion_click",
      { campaign_id: companion.impression_id, business_id: companion.offer_id });
    // Preferred: save the attached offer to the wallet without interrupting audio.
    if (companion.offer_id && companion.impression_id) {
      setSaving(true);
      try {
        const r = await axios.post(
          `${API}/live-radio/preroll/${companion.impression_id}/save-to-wallet`,
          {}, { withCredentials: true });
        setSaved(true);
        toast.success("Saved to your wallet", {
          description: r.data?.idempotent
            ? "Already saved earlier — no duplicates."
            : "Find it under Wallet → Coupons.",
        });
      } catch (_e) {
        toast.error("Sign in to save offers to your wallet.");
      } finally { setSaving(false); }
      return;
    }
    if (companion.cta_url) window.open(companion.cta_url, "_blank", "noopener");
  };

  return (
    <div data-testid="player-companion"
      data-impression-id={companion.impression_id || ""}
      className="rl-card px-3.5 py-2.5 flex items-center gap-3 mb-2 max-w-3xl mx-auto pointer-events-auto
                  border border-accent-gold/30">
      {companion.image_url ? (
        <img src={companion.image_url} alt="" data-testid="player-companion-image"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
          className="shrink-0 w-11 h-11 rounded-token-sm object-cover" />
      ) : (
        <span className="shrink-0 w-11 h-11 rounded-token-sm grid place-items-center bg-accent-gold/15">
          <Sparkles size={16} className="text-accent-gold" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest text-accent-gold">
          <Sparkles size={9} /> Sponsored offer
        </span>
        <div className="text-sm font-bold text-text-primary truncate">{headline}</div>
        <div className="text-xs text-text-secondary truncate">{sponsor} · playing now</div>
      </div>
      <button onClick={onClaim} disabled={saving || saved}
        data-testid="player-companion-claim" data-saved={saved}
        className="shrink-0 inline-flex items-center gap-1.5 bg-accent-gold text-black font-black rounded-full h-8 px-3 text-xs hover:brightness-110 disabled:opacity-60 transition">
        {companion.offer_id
          ? (<><ShoppingBag size={13} /> {saved ? "Saved ✓" : saving ? "Saving…" : "Save offer"}</>)
          : (<><ExternalLink size={13} /> Learn more</>)}
      </button>
    </div>
  );
}

export default function OnAirOfferCard() {
  const playing = usePlayerStore((s) => s.playing);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const channelName = usePlayerStore((s) => s.activeChannelName);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeCompanion = usePlayerStore((s) => s.activeCompanion);
  const city = useGeoStore((s) => s.city);
  const navigate = useNavigate();
  const [offer, setOffer] = useState(null);
  const [dismissed, setDismissed] = useState(false);

  const station = importedStation?.name || channelName || null;

  // Geo-offer fallback fetch. Declared unconditionally (Rules of Hooks);
  // it no-ops while a synced audio-ad companion is active.
  useEffect(() => {
    if (activeCompanion) return;
    if (!playing || offer) return;
    const params = new URLSearchParams({ limit: "6" });
    if (city) params.set("city", city);
    axios.get(`${API}/offers/nearby?${params.toString()}`, { withCredentials: true })
      .then((r) => {
        const items = r.data?.items || [];
        if (items.length) setOffer(items[Math.floor(Math.random() * items.length)]);
      })
      .catch(() => { /* no offers nearby — card stays hidden */ });
  }, [playing, city, offer, activeCompanion]);

  // SYNCED companion takes priority over the geo fallback and shows even
  // for podcast/AI audio when an audio ad is mid-flight.
  if (activeCompanion) {
    return <SyncedCompanion companion={activeCompanion} />;
  }

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
