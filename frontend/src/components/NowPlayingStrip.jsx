/** Phase 42 S2.3 — "Now playing on community radio" strip.
 *
 *  32px-tall band that sits at the very top of the PageFrame. Polls
 *  /api/community/now_playing every 30s (visibility-aware — pauses on
 *  tab blur). Click routes to the station detail page.
 *
 *  When no public stations have listeners yet, shows a fallback CTA
 *  that routes to /radio/create.
 *
 *  NOT an ad — no "AD" label, brand-native dark gradient.
 */
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Radio } from "lucide-react";
import { API } from "@/AuthContext";

const STRIP_HEIGHT = 32;
const POLL_MS = 30000;

export default function NowPlayingStrip() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/community/now_playing`,
                                  { withCredentials: true });
      setData(r.data);
    } catch (_) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    let timer = null;
    const start = () => {
      if (timer) return;
      timer = setInterval(load, POLL_MS);
    };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => (document.hidden ? stop() : (load(), start()));
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      document.removeEventListener("visibilitychange", onVis);
      stop();
    };
  }, [load]);

  // Reserve 32px even before data resolves — zero CLS.
  const baseStyle = {
    height: STRIP_HEIGHT, lineHeight: `${STRIP_HEIGHT}px`,
    width: "100%", display: "flex", alignItems: "center",
    justifyContent: "space-between",
    padding: "0 14px",
    background: "linear-gradient(90deg, rgba(0,217,255,0.10) 0%, rgba(255,0,126,0.10) 100%), #0b0b0b",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    color: "#cbd5e1", fontSize: 12,
    cursor: "pointer", userSelect: "none",
    overflow: "hidden",
  };

  if (!data) {
    return (
      <div data-testid="now-playing-strip-skeleton" style={baseStyle} />
    );
  }

  const station = data.station;
  if (!station) {
    return (
      <div data-testid="now-playing-strip-fallback"
            role="button"
            onClick={() => navigate("/radio/create")}
            style={baseStyle}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8,
                         overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          <Radio size={13} color="#00d9ff" />
          {data.fallback_message || "Start your own community radio →"}
        </span>
        <span style={{ color: "#00d9ff", fontWeight: 600 }}>create now →</span>
      </div>
    );
  }

  return (
    <div data-testid="now-playing-strip"
          data-station-slug={station.slug}
          role="button"
          onClick={() => navigate(`/r/${station.slug}`)}
          style={baseStyle}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 8,
                       overflow: "hidden", textOverflow: "ellipsis",
                       whiteSpace: "nowrap", minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 14 }}>🎵</span>
        <span style={{ color: "#fff", fontWeight: 600,
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap" }}>{station.name}</span>
        <span style={{ color: "#9aa3af" }}>·</span>
        <span style={{ color: "#9aa3af" }}>
          {station.listener_count} listener{station.listener_count === 1 ? "" : "s"}
        </span>
      </span>
      <span style={{ color: "#00d9ff", fontWeight: 600,
                       marginLeft: 12, whiteSpace: "nowrap" }}>
        tap to join →
      </span>
    </div>
  );
}
