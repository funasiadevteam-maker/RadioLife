/** Phase 42 S2 — BannerAdSlot v3 (12-slot inventory, mobile-aware,
 *  anti-adjacent rotation).
 *
 *  Adds on top of v2:
 *   - mobile_size: backend may return null `size` (desktop-hidden) or
 *     null `mobile_size` (mobile-hidden); component honors both.
 *   - mobile_only flag for sticky-bottom-only slots.
 *   - Sends `?recent=` so backend can avoid repeating variants adjacent
 *     to ones already served on the same page-load (session-level
 *     deduplication via a module-scoped Set).
 */
import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

const DIMS = {
  "970x250": { w: 970, h: 250 },
  "970x90":  { w: 970, h: 90  },
  "728x90":  { w: 728, h: 90  },
  "336x280": { w: 336, h: 280 },
  "320x100": { w: 320, h: 100 },
  "320x50":  { w: 320, h: 50  },
  "300x600": { w: 300, h: 600 },
  "300x250": { w: 300, h: 250 },
  "250x250": { w: 250, h: 250 },
  "160x600": { w: 160, h: 600 },
};

// Phase 42 S2 — page-load-scoped Set of variant indices already shown,
// so the backend's anti-adjacent dedup has a meaningful `recent` hint.
// Reset whenever the visible pathname changes.
const _recentVariants = { path: null, set: new Set() };
function _resetRecentIfPathChanged(pageRoute) {
  if (_recentVariants.path !== pageRoute) {
    _recentVariants.path = pageRoute;
    _recentVariants.set = new Set();
  }
}

let _adsenseLoaded = false;
function loadAdSense() {
  if (_adsenseLoaded || typeof window === "undefined") return;
  _adsenseLoaded = true;
  const s = document.createElement("script");
  s.async = true;
  s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js";
  s.crossOrigin = "anonymous";
  document.head.appendChild(s);
}

// Phase 42 S2 — viewport-aware. Mobile breakpoint at 1024px (tablet+
// uses desktop layout; phones use mobile).
function useIsMobile(breakpoint = 1024) {
  const [m, setM] = useState(() =>
    typeof window === "undefined" ? false : window.innerWidth < breakpoint);
  useEffect(() => {
    const onR = () => setM(window.innerWidth < breakpoint);
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, [breakpoint]);
  return m;
}

export default function BannerAdSlot({ slotKey, pageRoute, className,
                                        style: styleOverride }) {
  const [data, setData]    = useState(null);
  const [loading, setLoad] = useState(true);
  const ref                 = useRef(null);
  const beaconFiredRef      = useRef(false);
  const isMobile            = useIsMobile();

  useEffect(() => {
    let cancel = false;
    _resetRecentIfPathChanged(pageRoute);
    (async () => {
      try {
        const recentCsv = Array.from(_recentVariants.set).join(",");
        const r = await axios.get(`${API}/ads/banner/decision`,
          { params: { slot_key: slotKey, page_route: pageRoute,
                       recent: recentCsv },
            withCredentials: true });
        if (cancel) return;
        if (typeof r.data?.variant_idx === "number") {
          _recentVariants.set.add(r.data.variant_idx);
        }
        setData(r.data);
        if (r.data?.source === "adsense") loadAdSense();
      } catch (e) { /* silent */ }
      if (!cancel) setLoad(false);
    })();
    return () => { cancel = true; };
  }, [slotKey, pageRoute]);

  useEffect(() => {
    if (!data || !ref.current || beaconFiredRef.current) return;
    if (data.source !== "direct" && data.source !== "house") return;
    if (!data.impression_pixel) return;
    let timer = null;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
        timer = setTimeout(() => {
          if (beaconFiredRef.current) return;
          beaconFiredRef.current = true;
          const img = new Image();
          img.src = `${API.replace(/\/api$/, "")}${data.impression_pixel}`;
        }, 1000);
      } else if (timer) { clearTimeout(timer); timer = null; }
    }, { threshold: [0, 0.5, 1.0] });
    io.observe(ref.current);
    return () => { io.disconnect(); if (timer) clearTimeout(timer); };
  }, [data]);

  // Phase 42 S2 — pick the right size for the viewport.
  const sizeKey = isMobile
    ? (data?.mobile_size || data?.size)
    : (data?.size || data?.mobile_size);
  // Hide entirely when:
  //  - slot is mobile_only and we're on desktop
  //  - slot has no desktop `size` and we're on desktop
  //  - slot has no mobile_size and we're on mobile
  if (data) {
    if (data.mobile_only && !isMobile) return null;
    if (!data.mobile_only && !data.size && !isMobile) return null;
    if (isMobile && !data.mobile_size) return null;
  }
  const dims  = DIMS[sizeKey] || DIMS["300x250"];
  const style = { width: "100%", maxWidth: dims.w,
                   aspectRatio: `${dims.w}/${dims.h}`,
                   borderRadius: 8, overflow: "hidden", margin: "8px 0",
                   ...(styleOverride || {}) };

  if (loading) {
    return (
      <div data-testid={`bannerad-skeleton-${slotKey}`}
           style={{ ...style, background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.05)" }}
           className={className} />
    );
  }

  if (!data || data.source === "none") return null;

  if (data.source === "adsense") {
    return (
      <div data-testid={`bannerad-adsense-${slotKey}`}
           ref={ref} style={style} className={className}>
        <ins className="adsbygoogle"
             style={{ display: "block", width: dims.w, height: dims.h }}
             data-ad-client={data.client_id}
             data-ad-slot={data.slot_id}
             data-ad-format="auto"
             data-full-width-responsive="true" />
      </div>
    );
  }

  const onClick = async () => {
    if (data.source !== "direct") return;
    try {
      await axios.post(`${API}/ads/banner/click`,
        { impression_id: (data.impression_pixel || "").split("/").pop(),
          click_url: data.click_url },
        { withCredentials: true });
    } catch (_) { /* fire-and-forget */ }
  };

  const isHouse = data.source === "house";
  return (
    <a data-testid={`bannerad-${data.source}-${slotKey}`}
       data-banner-source={data.source} data-banner-size={sizeKey}
       href={data.click_url || "/premium"} onClick={onClick}
       ref={ref}
       style={{ ...style, display: "flex", alignItems: "center",
                justifyContent: "center", textDecoration: "none", color: "#fff",
                background: isHouse
                  ? "linear-gradient(135deg, #00d9ff22, #ff007e22)"
                  : "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.06)", position: "relative" }}
       className={className}>
      <span style={{ position: "absolute", top: 4, right: 6,
                      fontSize: 9, fontFamily: "monospace",
                      color: "rgba(255,255,255,0.4)", letterSpacing: 0.5 }}>AD</span>
      {data.creative_image_url ? (
        <img src={data.creative_image_url} alt=""
              style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
      ) : (
        <div style={{ textAlign: "center", padding: 12 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{data.headline || "RadioLife"}</div>
          {data.sub_text && (
            <div style={{ fontSize: 12, color: "#cbd5e1", marginTop: 4 }}>
              {data.sub_text}
            </div>
          )}
        </div>
      )}
    </a>
  );
}
