/**
 * Phase 41 S2.C.2 — Community Live Heat Ribbon.
 *
 * Top of `/community` page (between Now Playing and Featured). Shows
 * up to 3 stations currently with the most live listeners. Hidden if
 * the API returns empty.
 *
 * Polls every 30s with visibility-aware pause. Reserves ~120px height
 * during initial load so the page doesn't jump.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Activity, Radio as RadioIcon } from "lucide-react";
import { API } from "@/AuthContext";

const POLL_INTERVAL_MS = 30 * 1000;
const RIBBON_LIMIT     = 3;

function Card({ s }) {
  return (
    <Link to={`/r/${encodeURIComponent(s.slug)}`}
          data-testid={`live-heat-card-${s.slug}`}
          style={{
            display: "flex", alignItems: "center", gap: 10,
            flex: 1, minWidth: 0, height: 84,
            padding: 12, borderRadius: 12,
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
            color: "inherit", textDecoration: "none",
            transition: "border-color 150ms ease, background 150ms ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "rgba(0,217,255,0.4)";
            e.currentTarget.style.background  = "rgba(255,255,255,0.06)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
            e.currentTarget.style.background  = "rgba(255,255,255,0.04)";
          }}>
      <div style={{ width: 56, height: 56, borderRadius: 10, flexShrink: 0,
                     background: s.cover_image_url
                                ? `center/cover no-repeat url(${s.cover_image_url})`
                                : s.cover_color || "#00d9ff",
                     display: "grid", placeItems: "center" }}>
        {!s.cover_image_url && <RadioIcon size={22} color="rgba(0,0,0,0.45)" />}
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontWeight: 600, color: "#fff", fontSize: 14,
                       whiteSpace: "nowrap", overflow: "hidden",
                       textOverflow: "ellipsis" }}>
          {s.name}
        </div>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 4,
                       marginTop: 4, color: "#10b981", fontSize: 12,
                       fontWeight: 500 }}>
          <Activity size={12} />
          <span data-testid={`live-heat-count-${s.slug}`}>
            {s.listener_count}
          </span>
          <span style={{ color: "#9aa3af", fontWeight: 400 }}>
            listening now
          </span>
        </div>
      </div>
    </Link>
  );
}

function Skeleton() {
  return (
    <div data-testid="live-heat-skeleton"
         style={{ display: "flex", gap: 10, marginBottom: 18 }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ flex: 1, height: 84, borderRadius: 12,
                                 background: "rgba(255,255,255,0.03)" }} />
      ))}
    </div>
  );
}

export default function LiveHeatRibbon() {
  const [stations, setStations] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/community/live_now?limit=${RIBBON_LIMIT}`);
      setStations(r.data?.stations || []);
    } catch {
      setStations([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    Promise.resolve().then(() => { if (!cancelled) load(); });
    const tick = () => {
      if (!cancelled && document.visibilityState === "visible") load();
    };
    timer = setInterval(tick, POLL_INTERVAL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [load]);

  // Hide the ribbon entirely when nothing is live.
  if (stations !== null && stations.length === 0) return null;

  return (
    <section data-testid="live-heat-ribbon"
             style={{ marginBottom: 18 }}>
      <header style={{ display: "flex", alignItems: "center", gap: 8,
                        marginBottom: 8 }}>
        <Activity size={14} color="#10b981" />
        <h3 style={{ fontSize: 13, fontWeight: 600, color: "#fff",
                       textTransform: "uppercase",
                       letterSpacing: "0.06em", margin: 0 }}>
          Live right now
        </h3>
      </header>
      {stations === null ? (
        <Skeleton />
      ) : (
        <div data-testid="live-heat-grid"
             style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {stations.map((s) => (
            <div key={s.slug} style={{ flex: "1 1 200px", minWidth: 200,
                                         maxWidth: "100%" }}>
              <Card s={s} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
