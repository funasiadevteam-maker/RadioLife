// Phase AD.3 — Customer-facing sponsor badge for Predict & Win.
//
// Fetches /api/predict-win/{parent_id}/active-sponsorship on mount,
// renders a "Sponsored by {brand}" chip + optional brand asset + tagline,
// and fires the appropriate impression billing event once when the
// component becomes visible (IntersectionObserver 50%).
//
// Adblock resilient — impression POST wrapped in .catch(() => {}).
import { useEffect, useRef, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function PredictWinSponsorBadge({
  parentCampaignId,
  variant = "card",         // "card" | "detail" | "win_screen"
  eventType = "entry",  // matches AD.3 event_type enum
  autoFireImpression = false,
}) {
  const [sponsor, setSponsor] = useState(null);
  const containerRef = useRef(null);
  const [impressed, setImpressed] = useState(false);

  useEffect(() => {
    if (!parentCampaignId) return;
    let cancelled = false;
    axios.get(`${API}/predict-win/${parentCampaignId}/active-sponsorship`,
      { withCredentials: true })
      .then((r) => { if (!cancelled) setSponsor(r.data?.sponsorship || null); })
      .catch(() => { if (!cancelled) setSponsor(null); });
    return () => { cancelled = true; };
  }, [parentCampaignId]);

  // Only fire impression when autoFireImpression is true (e.g. on entry
  // confirmation, correct-impression surface, win screen).  The list
  // card badge is display-only — no billing.
  useEffect(() => {
    if (!autoFireImpression || !sponsor || impressed || !containerRef.current) return;
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.intersectionRatio >= 0.5) {
          axios.post(`${API}/predict-win/sponsorships/impression`, {
            sponsorship_id: sponsor.sponsorship_id,
            parent_campaign_id: parentCampaignId,
            event_type: eventType,
          }, { withCredentials: true }).catch(() => {});
          setImpressed(true);
          io.disconnect();
        }
      }
    }, { threshold: [0.5] });
    io.observe(containerRef.current);
    return () => io.disconnect();
  }, [sponsor, impressed, autoFireImpression, eventType, parentCampaignId]);

  if (!sponsor) return null;

  if (variant === "card") {
    return (
      <div ref={containerRef}
                  data-testid={`pw-sponsorship-badge-${parentCampaignId}`}
                  className="absolute top-2 right-2 z-10 inline-flex items-center gap-1
                                            px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400
                                            border border-amber-500/40 text-[9px] font-mono
                                            uppercase tracking-widest">
        Sponsored · {sponsor.brand_name}
      </div>
    );
  }

  if (variant === "detail") {
    return (
      <div ref={containerRef}
                  data-testid={`pw-sponsorship-brand-asset-${parentCampaignId}`}
                  className="flex items-center gap-3 p-3 mt-3 rounded-xl bg-amber-500/10
                                            border border-amber-500/30">
        {sponsor.brand_asset_url && (
          <img src={`${process.env.REACT_APP_BACKEND_URL}${sponsor.brand_asset_url}`}
                      alt="" className="w-10 h-10 rounded object-cover bg-slate-800/40" />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-[9px] font-mono uppercase tracking-widest text-amber-500">
            Sponsored by
          </div>
          <div className="text-sm font-black text-white truncate">
            {sponsor.brand_name}
          </div>
          {sponsor.tagline && (
            <div className="text-[11px] text-slate-400 truncate">
              {sponsor.tagline}
            </div>
          )}
        </div>
      </div>
    );
  }

  // win_screen variant
  return (
    <div ref={containerRef}
              data-testid={`pw-sponsorship-brand-asset-${parentCampaignId}`}
              className="mt-4 text-center text-xs">
      <div className="inline-flex items-center gap-2 px-3 py-2 rounded-full
                                    bg-amber-500/15 border border-amber-500/30">
        {sponsor.brand_asset_url && (
          <img src={`${process.env.REACT_APP_BACKEND_URL}${sponsor.brand_asset_url}`}
                      alt="" className="w-6 h-6 rounded object-cover" />
        )}
        <span className="text-amber-400 font-black">
          Powered by {sponsor.brand_name}
        </span>
      </div>
      {sponsor.tagline && (
        <div className="mt-1 text-[11px] text-slate-400">{sponsor.tagline}</div>
      )}
    </div>
  );
}
