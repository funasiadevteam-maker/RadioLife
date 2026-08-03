// Phase 36c Stage 4 polish — per-tile connection-quality pill.
//
// Renders a tiny ●-prefixed pill in the top-right of a participant tile.
//   score >= 0.75  → Good (green)
//   0.40-0.74      → Fair (amber)
//   < 0.40         → Poor (red)
//
// `usePollConnectionQuality(sid, active)` polls
// `GET /api/podcasts/recording-sessions/{sid}/connection-quality` every
// `POLL_INTERVAL_MS` while `active` is true and returns
// `{ byParticipantId: { pid: { score, rtt_ms, jitter_ms, packet_loss_pct } } }`.
//
// Hook stops polling automatically when `active` is false (caller is
// expected to flip it once the session moves to status="completed").

import React, {useEffect, useRef, useState} from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const POLL_INTERVAL_MS = 5000;

export const QUALITY_BANDS = {
  GOOD: {label: "Good", color: "#22c55e",
              bg: "rgba(34,197,94,0.15)", border: "rgba(34,197,94,0.45)"},
  FAIR:  {label: "Fair", color: "#f59e0b",
              bg: "rgba(245,158,11,0.15)", border: "rgba(245,158,11,0.45)"},
  POOR: {label: "Poor", color: "#ef4444",
              bg: "rgba(239,68,68,0.15)", border: "rgba(239,68,68,0.45)"},
  UNKNOWN: {label: "—", color: "#71717a",
                      bg: "rgba(113,113,122,0.12)",
                      border: "rgba(113,113,122,0.35)"},
};

// Inclusive lower bounds matching the dispatch spec exactly:
//   >= 0.75 → Good, >= 0.40 → Fair, < 0.40 → Poor.
export function scoreToBand(score) {
  if (score == null || Number.isNaN(score)) return QUALITY_BANDS.UNKNOWN;
  if (score >= 0.75) return QUALITY_BANDS.GOOD;
  if (score >= 0.40) return QUALITY_BANDS.FAIR;
  return QUALITY_BANDS.POOR;
}

export function usePollConnectionQuality(sid, active) {
  const [byPid, setByPid] = useState({});
  const timerRef = useRef(null);
  useEffect(() => {
    if (!sid || !active) {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
      return undefined;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await axios.get(
          `${API}/podcasts/recording-sessions/${sid}/connection-quality`,
          {withCredentials: true});
        if (cancelled) return;
        const map = {};
        for (const p of (r?.data?.participants || [])) {
          map[p.participant_id] = {
            score:                     p?.last?.score ?? p.avg_score ?? null,
            rtt_ms:                    p?.last?.rtt_ms ?? null,
            jitter_ms:               p?.last?.jitter_ms ?? null,
            packet_loss_pct: p?.last?.packet_loss_pct ?? null,
            samples:                 p?.samples ?? 0,
          };
        }
        setByPid(map);
      } catch (_) { /* poll is best-effort */ }
    };
    tick();
    timerRef.current = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [sid, active]);
  return byPid;
}

export default function ConnectionQualityPill({score, rtt_ms, jitter_ms,
                                                                                   packet_loss_pct,
                                                                                   testid}) {
  const band = scoreToBand(score);
  const tooltip = (score == null)
    ? "No quality samples yet"
    : `RTT ${rtt_ms ?? "—"}ms · jitter ${jitter_ms ?? "—"}ms · `
        + `loss ${packet_loss_pct != null ? packet_loss_pct.toFixed(1) : "—"}%`;
  return (
    <span data-testid={testid || "connection-quality-pill"}
              data-band={band.label.toLowerCase()}
              title={tooltip}
              style={{display: "inline-flex", alignItems: "center", gap: 4,
                          fontSize: 10, fontWeight: 700, letterSpacing: 0.3,
                          padding: "2px 8px", borderRadius: 999,
                          background: band.bg, color: band.color,
                          border: `1px solid ${band.border}`,
                          textTransform: "uppercase"}}>
      <span style={{width: 6, height: 6, borderRadius: "50%",
                                background: band.color, display: "inline-block"}} />
      {band.label}
    </span>
  );
}
