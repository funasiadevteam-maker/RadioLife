/** Phase 42 S1 — Banner slot component (free-tier only).
 *  Renders nothing for premium / trial users (server returns ad:null).
 *  Auto-refreshes every 30s; respects frequency caps server-side.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";
import SafeImage from "@/components/SafeImage";

const HEIGHT_BY_SLOT = {
  top_banner:  90,
  left_mid:    250,
  center_mid:  120,
  right_mid:   250,
};

export default function BannerSlot({ id, className }) {
  const [ad, setAd]   = useState(null);
  const [tier, setTier] = useState(null);

  useEffect(() => {
    let cancel = false, timer = null;
    const fetchAd = async () => {
      try {
        const r = await axios.get(`${API}/ads/banner/${id}`,
          { withCredentials: true });
        if (cancel) return;
        setAd(r.data?.ad || null);
        setTier(r.data?.tier || null);
      } catch (e) { /* silent */ }
    };
    fetchAd();
    timer = setInterval(fetchAd, 35000);  // server enforces 30s cooldown
    return () => { cancel = true; clearInterval(timer); };
  }, [id]);

  // Premium / trial / disabled / cooldown / empty → render nothing.
  if (!ad) return null;

  const onClick = async () => {
    try {
      await axios.post(`${API}/ads/banner/${id}/click`,
        { creative_id: ad.creative_id, tier },
        { withCredentials: true });
    } catch (e) { /* silent */ }
    if (ad.click_url) window.location.href = ad.click_url;
  };

  const isHouseDefault = tier === "house_default";
  return (
    <div data-testid={`banner-slot-${id}`}
         data-banner-tier={tier}
         onClick={onClick}
         style={{ width: "100%", minHeight: HEIGHT_BY_SLOT[id] || 90,
                  background: isHouseDefault
                    ? "linear-gradient(135deg, #00d9ff20, #ff007e20)"
                    : "rgba(255,255,255,0.04)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: 10, padding: 12, cursor: "pointer",
                  display: "flex", flexDirection: "column",
                  justifyContent: "center", gap: 4,
                  position: "relative", overflow: "hidden" }}
         className={className}>
      <div style={{ position: "absolute", top: 6, right: 8,
                     fontSize: 9, fontFamily: "monospace",
                     color: "rgba(255,255,255,0.4)", letterSpacing: 0.5 }}>
        AD
      </div>
      {ad.image_url ? (
        <img src={ad.image_url} alt={ad.alt_text || ""}
              style={{ maxWidth: "100%", maxHeight: HEIGHT_BY_SLOT[id] - 24,
                         objectFit: "contain", borderRadius: 6 }} />
      ) : (
        <>
          <div style={{ color: "#fff", fontWeight: 600, fontSize: 14 }}>
            {ad.headline || "FUUSIC"}
          </div>
          {ad.sub_text && (
            <div style={{ color: "#cbd5e1", fontSize: 12 }}>
              {ad.sub_text}
            </div>
          )}
          {ad.cta && (
            <div style={{ marginTop: 4, color: "#00d9ff",
                            fontSize: 12, fontWeight: 600 }}>
              {ad.cta} →
            </div>
          )}
        </>
      )}
    </div>
  );
}
