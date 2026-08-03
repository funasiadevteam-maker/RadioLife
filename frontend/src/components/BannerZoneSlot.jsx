// Phase AD.11 — Zone-based banner slot for the customer surface.
//
// Distinct from the legacy `<BannerSlot id="top_banner" />` (Phase 42
// S1) — this component takes a `zone` prop matching the AD.11 zone
// enum (landing_hero | browse_row | station_detail | now_playing |
// wallet | games | bottom_bar) and drives the AD.11 auction endpoint.
//
// - Fetches /api/banner/serve on mount + on country change
// - Fires /api/banner/impression when the slot is ≥50% in viewport
//    (IntersectionObserver).  Dedup'd per (session, banner, zone) by
//    the backend within a 5-minute window.  Backend also enforces a
//    session-zone frequency cap (3 impressions per session per zone).
// - Fires /api/banner/click on tap → opens target_url in a new tab.
// - Fallback: if no banner returned or fetch errors (e.g. ad-block),
//    renders `null` (no gap, no placeholder).
// - Impression + click posts are wrapped in `.catch(() => {})` so an
//    ad-blocker never crashes the customer render.
// - `data-ad-slot="ad11-{zone}"` on the outer element for our own
//    analytics + external ad-block reporters.
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useGeoStore } from "@/store/useGeoStore";
import SafeImage from "@/components/SafeImage";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const SESSION_KEY = "bigfm_banner_session";

function _getSessionId() {
  try {
    let sid = window.sessionStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = "sess_" + Math.random().toString(36).slice(2, 14);
      window.sessionStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  } catch (_e) { return "sess_ephemeral"; }
}


export default function BannerZoneSlot({ zone, className = "", style = {} }) {
  const country = useGeoStore((s) => s.country);
  const [banner, setBanner] = useState(null);
  const [failed, setFailed] = useState(false);
  const [impressed, setImpressed] = useState(false);
  const containerRef = useRef(null);
  const sid = _getSessionId();

  useEffect(() => {
    const params = new URLSearchParams({ zone, session_id: sid });
    if (country) params.set("country", country.toUpperCase());
    axios.get(`${API}/banner/serve?${params}`)
      .then((r) => setBanner(r.data.banner || null))
      .catch(() => { setBanner(null); setFailed(true); });
  }, [zone, country, sid]);

  useEffect(() => {
    if (!banner || impressed) return;
    const el = containerRef.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.intersectionRatio >= 0.5) {
          axios.post(`${API}/banner/impression`, {
            banner_id: banner.banner_id, zone,
            session_id: sid,
          }).catch(() => { /* ad-blocked — silent no-op */ });
          setImpressed(true);
          io.disconnect();
        }
      }
    }, { threshold: [0.5] });
    io.observe(el);
    return () => io.disconnect();
  }, [banner, impressed, zone, sid]);

  const onClick = (e) => {
    if (!banner) return;
    axios.post(`${API}/banner/click`, {
      banner_id: banner.banner_id, zone, session_id: sid,
    }).catch(() => { /* ad-blocked — silent no-op */ });
    try { window.open(banner.target_url, "_blank", "noopener,noreferrer"); }
    catch (_e) { /* pop-up blocked */ }
    e.preventDefault();
  };

  // No creative available (auction empty or ad-block) → render null
  // per product spec.  No empty box / no "Sponsored" placeholder.
  if (!banner || failed) return null;

  const zoneStyle = {
    landing_hero:      { aspectRatio: "1200 / 400", maxWidth: 1200 },
    station_detail:  { aspectRatio: "970 / 250",    maxWidth: 970 },
    games:                    { aspectRatio: "970 / 250",    maxWidth: 970 },
    browse_row:          { aspectRatio: "728 / 200",    maxWidth: 728 },
    wallet:                  { aspectRatio: "728 / 90",      maxWidth: 728 },
    now_playing:        { aspectRatio: "320 / 180",    maxWidth: 320 },
    bottom_bar:          { aspectRatio: "728 / 90",      maxWidth: 728 },
  }[zone] || { maxWidth: 728 };

  return (
    <a href={banner.target_url}
          ref={containerRef}
          onClick={onClick}
          data-testid={`banner-slot-${zone}`}
          data-ad-slot={`ad11-${zone}`}
          data-banner-id={banner.banner_id}
          className={`block mx-auto my-4 rounded-xl overflow-hidden
                                shadow-lg hover:opacity-95 hover:scale-[1.01]
                                transition duration-150 relative ${className}`}
          style={{ ...zoneStyle, ...style, width: "100%" }}
          target="_blank"
          rel="noopener noreferrer sponsored">
      <SafeImage src={`${process.env.REACT_APP_BACKEND_URL}${banner.creative_url}`}
                                data-testid={`banner-slot-${zone}-image`}
                                alt={banner.cta_text || "Advertisement"}
                                fallbackKind="ad"
                                fallbackText={banner.cta_text || banner.brand_name || ""}
                                style={{ width: "100%", height: "100%",
                                                    objectFit: "cover", display: "block" }} />
      <span data-testid={`banner-slot-${zone}-sponsored`}
                  className="absolute top-1.5 right-2 text-[9px] font-mono
                                    uppercase tracking-widest bg-black/60 text-white/90
                                    px-1.5 py-0.5 rounded-sm">
        Sponsored
      </span>
      {banner.cta_text && (
        <span data-testid={`banner-slot-${zone}-cta`}
                    className="absolute bottom-2 right-2 px-3 py-1.5 rounded-full
                                      bg-amber-500 text-slate-900 text-xs font-black
                                      shadow-lg shadow-amber-500/40">
          {banner.cta_text} →
        </span>
      )}
    </a>
  );
}
