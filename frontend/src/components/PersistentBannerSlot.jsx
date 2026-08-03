/** Phase 42-E1.1 — Persistent banner ad slot.
 *
 *  Sibling of the legacy 12-slot `BannerAdSlot.jsx` (which keeps serving
 *  existing pages — Home, Wallet, Radio, Community, etc.).  This new
 *  component is built around the spec's `placement` taxonomy and the
 *  `/api/banner-ads/*` endpoint.
 *
 *  Props:
 *      placement: one of "miniplayer", "commute_map",
 *                              "predict_win_list", "news_local", "generic"
 *      className: optional CSS class
 *      style:        optional inline style overrides
 *
 *  Behavior:
 *      - On mount → POST /api/banner-ads/request with placement + geo.
 *      - On render → POST /api/banner-ads/impression with the token.
 *      - On click → POST /api/banner-ads/click and open click_url.
 *      - Premium users → never request (provider returns has_ad:false).
 *      - Auto-refresh every 90s.
 *      - If no ad returned → renders null (slot hides).
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API, useAuth } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";

const REFRESH_MS = 90 * 1000;

function isPremiumUser(user) {
  if (!user) return false;
  if (user.is_premium) return true;
  const status = (user.subscription_status || "").toLowerCase();
  return status === "active" || status === "premium"
              || status === "trial" || status === "trialing";
}

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
function resolveImg(u) {
  if (!u) return null;
  return u.startsWith("http") ? u : `${BACKEND_URL}${u}`;
}

export default function PersistentBannerSlot({
  placement,
  className = "",
  style: styleOverride,
}) {
  const { user } = useAuth();
  const city = useGeoStore((s) => s.city);
  const country = useGeoStore((s) => s.country);
  const [ad, setAd] = useState(null);
  const [loading, setLoading] = useState(true);
  const impressionLogged = useRef(false);

  const fetchAd = useCallback(async () => {
    if (isPremiumUser(user)) {
      setAd(null);
      setLoading(false);
      return;
    }
    try {
      impressionLogged.current = false;
      const r = await axios.post(`${API}/banner-ads/request`,
                                                            { placement, geo: { city, country } },
                                                            { withCredentials: true });
      if (r.data?.has_ad) {
        setAd(r.data.ad);
      } else {
        setAd(null);
      }
    } catch (_) {
      setAd(null);
    }
    setLoading(false);
  }, [placement, city, country, user]);

  useEffect(() => {
    fetchAd();
    const t = setInterval(fetchAd, REFRESH_MS);
    return () => clearInterval(t);
  }, [fetchAd]);

  // Log impression once when the ad becomes visible.
  useEffect(() => {
    if (!ad || impressionLogged.current) return;
    impressionLogged.current = true;
    (async () => {
      try {
        await axios.post(`${API}/banner-ads/impression`,
                                          { impression_token: ad.impression_token,
                                            placement },
                                          { withCredentials: true });
      } catch (_) { /* silent */ }
    })();
  }, [ad, placement]);

  if (loading || !ad) return null;

  const onClick = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/banner-ads/click`,
                                        { impression_token: ad.impression_token },
                                        { withCredentials: true });
    } catch (_) { /* fire-and-forget */ }
    const url = ad.click_url || "/premium";
    if (url.startsWith("/")) {
      window.location.assign(url);
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  const imgUrl = resolveImg(ad.image_url);
  return (
    <a
      data-testid={`persistent-banner-${placement}`}
      data-banner-source={ad.source}
      data-banner-campaign-id={ad.campaign_id || ""}
      href={ad.click_url || "/premium"}
      onClick={onClick}
      className={className}
      style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "6px 10px", borderRadius: 8,
        background: "rgba(0, 217, 255, 0.06)",
        border: "1px solid rgba(0, 217, 255, 0.18)",
        textDecoration: "none", color: "#cbd5e1",
        position: "relative", overflow: "hidden",
        maxWidth: 360, fontSize: 12,
        cursor: "pointer",
        ...(styleOverride || {}),
      }}
    >
      <span style={{
        position: "absolute", top: 2, right: 4,
        fontSize: 8, color: "rgba(255,255,255,0.4)",
        fontFamily: "monospace", letterSpacing: 0.5,
      }}>AD</span>
      {imgUrl && (
        <img src={imgUrl} alt=""
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                  style={{ height: 30, width: "auto", flexShrink: 0,
                              borderRadius: 4 }} />
      )}
      <span style={{ flex: 1, fontWeight: 500, color: "#fff",
                                  overflow: "hidden", textOverflow: "ellipsis",
                                  whiteSpace: "nowrap" }}>
        {ad.cta_text || "Sponsored"}
      </span>
    </a>
  );
}
