/** Sub-Phase E3 — Predict & Win TV kiosk.
 *
 * Route: `/tv/predict-win/:pairing_code`  (UNAUTHENTICATED — outside
 * the ProtectedRoute wrapper in App.js).
 *
 * Full-screen 16:9 kiosk layout.  Polls `/api/tv/predict-win/{code}`
 * every 5s.  Renders:
 *   • Header: business logo + name + city + verified chip
 *   • Center-left: prediction question + answer options with live
 *      community-pick percentages (large bars).
 *   • Right side: QR code + "Scan to pick your team" CTA + countdown.
 *   • Bottom: top prize preview + "No purchase necessary" disclaimer.
 *   • Post-resolve: WINNER banner overlay highlighting the winning option.
 */
/* eslint-disable react-hooks/set-state-in-effect, react-hooks/purity */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import { PartyPopper, ShieldCheck, Tv2, Clock, QrCode,
                  Sparkles, MapPin } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const POLL_DEFAULT_SEC = 5;
const PALETTE = ["#00d9ff", "#a78bfa", "#fbbf24", "#f87171", "#22c55e"];

function fmtCountdown(secs) {
  if (secs == null) return "—";
  if (secs <= 0) return "00:00";
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
}

export default function PredictWinKiosk() {
  const { pairing_code: rawCode } = useParams();
  const code = (rawCode || "").toUpperCase();
  const [state, setState] = useState(null);
  const [err, setErr] = useState(null);
  const [tick, setTick] = useState(0);
  const fullscreenRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/tv/predict-win/${encodeURIComponent(code)}`);
      setState(r.data); setErr(null);
    } catch (e) {
      const d = e.response?.data?.detail;
      setErr(d?.code || e.response?.status || "error");
    }
  }, [code]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const refresh = (state?.refresh_after_sec) || POLL_DEFAULT_SEC;
    const t = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, refresh * 1000);
    return () => clearInterval(t);
  }, [load, state?.refresh_after_sec]);

  // Local countdown tick (separate from the 5s poll).
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Browser-bar autopop fullscreen on first click.
  useEffect(() => {
    function onClick() {
      if (fullscreenRef.current) return;
      try {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
        fullscreenRef.current = true;
      } catch (_) { /* no-op */ }
    }
    document.addEventListener("click", onClick, { once: true });
    return () => document.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    document.title = state?.sponsor?.name
      ? `${state.sponsor.name} · RadioLife Predict & Win`
      : "RadioLife Predict & Win · TV";
  }, [state?.sponsor?.name]);

  if (err === "tv_pairing_not_found") {
    return <ErrorScreen title="Pairing code not found"
                                    code={code}
                                    message="Have your venue owner generate a fresh pairing code." />;
  }
  if (err) {
    return <ErrorScreen title="Unable to load kiosk" code={code}
                                    message="Polling failed.  Check the venue's internet connection." />;
  }
  if (!state) {
    return <ErrorScreen title="Loading…" code={code}
                                    message="Reaching the RadioLife kiosk service." />;
  }

  // Use the local tick to smooth the displayed countdown between
  // server polls — re-derive every second from the last known
  // lock_seconds_remaining and the elapsed wall-clock.
  const apparentLockSec = (() => {
    const base = state.campaign?.lock_seconds_remaining;
    if (base == null) return null;
    // Decrease by 1s per local tick since the last successful poll.
    // We track an arbitrary starting tick when the state landed.
    return Math.max(0, base - (tick % 6));   // resets each poll cycle
  })();

  return (
    <div data-testid="predict-win-kiosk"
            data-pairing-code={code}
            style={kioskRoot(state.sponsor?.cover_color)}>
      <KioskHeader state={state}/>
      <KioskBody state={state}
                      apparentLockSec={apparentLockSec}/>
      <KioskFooter state={state}/>
      {state.resolution && <WinnerOverlay state={state}/>}
      <style>{kioskKeyframes}</style>
    </div>
  );
}

function KioskHeader({ state }) {
  const sp = state.sponsor || {};
  return (
    <div data-testid="kiosk-header"
            style={{ display: "grid",
                        gridTemplateColumns: "auto 1fr auto",
                        gap: "clamp(16px, 2vw, 36px)",
                        alignItems: "center",
                        padding: "clamp(16px, 2vw, 32px)",
                        borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
      <div data-testid="kiosk-sponsor-logo"
              style={{ width: "clamp(72px, 7vw, 120px)",
                          height: "clamp(72px, 7vw, 120px)",
                          borderRadius: "clamp(12px, 1vw, 22px)",
                          background: sp.logo_url
                            ? `url(${sp.logo_url}) center/cover`
                            : "rgba(255,255,255,0.06)",
                          border: "1px solid rgba(255,255,255,0.1)",
                          display: "flex", alignItems: "center",
                          justifyContent: "center" }}>
        {!sp.logo_url && <Tv2 size={42} color="rgba(255,255,255,0.4)" />}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: "clamp(11px, 0.85vw, 16px)",
                                fontFamily: "monospace", letterSpacing: 3,
                                color: "rgba(255,255,255,0.65)",
                                textTransform: "uppercase",
                                marginBottom: 8 }}>
          Predict &amp; Win · Live at the venue
        </div>
        <h1 data-testid="kiosk-sponsor-name"
                style={{ fontSize: "clamp(28px, 3.5vw, 64px)",
                            fontWeight: 800, lineHeight: 0.98, margin: 0 }}>
          {sp.name || "RadioLife"}
        </h1>
        <div style={{ display: "flex", gap: 14, marginTop: 14,
                                flexWrap: "wrap", alignItems: "center",
                                color: "rgba(255,255,255,0.75)",
                                fontSize: "clamp(13px, 1.05vw, 20px)" }}>
          {sp.city && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <MapPin size={14}/> {sp.city}
            </span>)}
          {sp.verified && (
            <span data-testid="kiosk-verified-chip"
                      style={{ display: "inline-flex", alignItems: "center",
                                  gap: 4, color: "#00d9ff", fontWeight: 700,
                                  background: "rgba(0,217,255,0.12)",
                                  border: "1px solid rgba(0,217,255,0.4)",
                                  padding: "3px 12px", borderRadius: 999,
                                  fontSize: 12, textTransform: "uppercase" }}>
              <ShieldCheck size={12}/> Verified
            </span>)}
        </div>
      </div>
      <CountdownBlock state={state}/>
    </div>);
}

function CountdownBlock({ state }) {
  const lock = state.campaign?.lock_seconds_remaining;
  const status = state.campaign?.status;
  const locked = lock != null && lock <= 0;
  return (
    <div data-testid="kiosk-countdown"
            data-locked={locked ? "true" : "false"}
            data-status={status || ""}
            style={{ textAlign: "right" }}>
      <div style={{ fontSize: "clamp(10px, 0.8vw, 14px)",
                              letterSpacing: 3, fontFamily: "monospace",
                              color: "rgba(255,255,255,0.6)",
                              textTransform: "uppercase",
                              marginBottom: 4 }}>
        {state.resolution ? "Resolved" : (locked ? "Picks locked" : "Picks lock in")}
      </div>
      <div style={{ fontSize: "clamp(32px, 3.6vw, 68px)",
                              fontFamily: "monospace", fontWeight: 800,
                              color: locked ? "#fbbf24" : "#00d9ff",
                              lineHeight: 1 }}>
        {fmtCountdown(lock)}
      </div>
    </div>);
}

function KioskBody({ state, apparentLockSec }) {
  const dist = state.distribution || [];
  const maxPct = Math.max(0, ...dist.map((d) => d.pct || 0));
  return (
    <div data-testid="kiosk-body"
            style={{ display: "grid",
                        gridTemplateColumns: "2fr 1fr",
                        gap: "clamp(20px, 2.5vw, 56px)",
                        padding: "clamp(20px, 2vw, 40px)",
                        flex: 1, minHeight: 0 }}>
      <div data-testid="kiosk-question-pane" style={{ minWidth: 0 }}>
        <div style={{ fontSize: "clamp(14px, 1.05vw, 22px)",
                                fontFamily: "monospace", letterSpacing: 2,
                                color: "rgba(255,255,255,0.6)",
                                textTransform: "uppercase",
                                marginBottom: 12 }}>
          {state.campaign?.event_label || "Tonight's prediction"}
        </div>
        <h2 data-testid="kiosk-question"
              style={{ fontSize: "clamp(28px, 3.4vw, 64px)",
                          fontWeight: 800, lineHeight: 1.05,
                          marginBottom: "clamp(20px, 2vw, 40px)" }}>
          {state.question?.prompt || "Make your pick"}
        </h2>
        <div style={{ display: "grid", gap: "clamp(8px, 1vw, 16px)" }}>
          {dist.map((d, i) => (
            <OptionBar key={d.option_id} d={d} index={i} maxPct={maxPct}
                                resolved={!!state.resolution}
                                winningOptionId={state.resolution?.winning_option_id}/>
          ))}
        </div>
        <div style={{ ...muted, marginTop: 18 }}
                data-testid="kiosk-total-entries">
          {state.total_entries} picks locked in so far.
        </div>
      </div>
      <div data-testid="kiosk-qr-pane"
              style={{ display: "flex", flexDirection: "column",
                          gap: 14, alignItems: "stretch" }}>
        {state.qr_payload_url && (
          <div style={{ background: "rgba(255,255,255,0.06)",
                                  border: "1px solid rgba(0,217,255,0.4)",
                                  padding: "clamp(16px, 1.6vw, 32px)",
                                  borderRadius: "clamp(16px, 1.4vw, 28px)",
                                  textAlign: "center" }}>
            <div style={{ fontSize: "clamp(12px, 0.95vw, 18px)",
                                    letterSpacing: 2, fontFamily: "monospace",
                                    color: "#00d9ff", textTransform: "uppercase",
                                    marginBottom: 12 }}>
              <QrCode size={14} style={{verticalAlign:"-2px"}}/> Scan to pick
            </div>
            <div style={{ background: "#fff", padding: 14,
                                    borderRadius: "clamp(10px, 1vw, 18px)",
                                    display: "inline-block", lineHeight: 0 }}>
              <QRCode value={state.qr_payload_url}
                          size={Math.round(Math.min(window.innerWidth, window.innerHeight) * 0.16) || 220}
                          bgColor="#fff" fgColor="#0b0b0b"
                          data-testid="kiosk-qr-code"
                          style={{ width: "clamp(160px, 14vw, 260px)",
                                      height: "clamp(160px, 14vw, 260px)" }}/>
            </div>
            <div style={{ marginTop: 12, fontSize: 13,
                                    color: "rgba(255,255,255,0.7)" }}>
              Aim your phone at this QR — locks at countdown.
            </div>
          </div>)}
        {state.prize_summary && (
          <div data-testid="kiosk-prize-summary"
                  style={{ background: "rgba(251,191,36,0.06)",
                              border: "1px solid rgba(251,191,36,0.3)",
                              padding: "clamp(14px, 1.4vw, 24px)",
                              borderRadius: 16, textAlign: "left" }}>
            <div style={{ fontSize: 11, letterSpacing: 2,
                                    fontFamily: "monospace", color: "#fbbf24",
                                    textTransform: "uppercase", marginBottom: 8 }}>
              <Sparkles size={12} style={{verticalAlign:"-2px"}}/> Tonight's prize
            </div>
            <div style={{ fontSize: "clamp(20px, 1.7vw, 30px)",
                                    fontWeight: 800,
                                    marginBottom: 4 }}>
              {state.prize_summary.title}
            </div>
            <div style={{ ...muted, fontSize: 14 }}>
              {state.prize_summary.value_amount} {state.prize_summary.value_currency || ""}
            </div>
          </div>)}
      </div>
    </div>);
}

function OptionBar({ d, index, maxPct, resolved, winningOptionId }) {
  const isWinner = resolved && d.option_id === winningOptionId;
  const color = PALETTE[index % PALETTE.length];
  const pct = Math.max(2, d.pct || 0);
  return (
    <div data-testid={`kiosk-option-${d.option_id}`}
            data-pct={d.pct}
            data-winner={isWinner ? "true" : "false"}
            style={{ background: "rgba(255,255,255,0.05)",
                        border: isWinner
                          ? `2px solid ${color}`
                          : "1px solid rgba(255,255,255,0.06)",
                        borderRadius: 16, padding: "clamp(14px, 1.4vw, 24px)",
                        position: "relative", overflow: "hidden",
                        animation: isWinner ? "kiosk-winner 2s ease-in-out infinite" : "none" }}>
      <div style={{ position: "absolute", inset: 0,
                              background: `linear-gradient(90deg, ${color}28, transparent ${pct}%)`,
                              opacity: 0.8 }} />
      <div style={{ position: "relative",
                              display: "flex", justifyContent: "space-between",
                              alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: "clamp(20px, 2vw, 36px)",
                                fontWeight: 800 }}>
          {d.label}
          {isWinner && (
            <span style={{ marginLeft: 12, color, fontSize: 14,
                                      textTransform: "uppercase", letterSpacing: 2 }}>
              <PartyPopper size={14} style={{verticalAlign:"-2px"}}/> Winner
            </span>)}
        </div>
        <div style={{ fontFamily: "monospace",
                                fontSize: "clamp(20px, 1.8vw, 32px)",
                                fontWeight: 800, color }}>
          {Math.round(d.pct || 0)}%
        </div>
      </div>
      <div style={{ position: "relative", height: 10, marginTop: 10,
                              background: "rgba(255,255,255,0.04)",
                              borderRadius: 999, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%",
                                background: color, borderRadius: 999,
                                transition: "width 1s ease-out" }}/>
      </div>
    </div>);
}

function KioskFooter({ state }) {
  return (
    <div data-testid="kiosk-footer"
            style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "center", gap: 12,
                        padding: "clamp(14px, 1.4vw, 28px)",
                        borderTop: "1px solid rgba(255,255,255,0.06)",
                        color: "rgba(255,255,255,0.65)",
                        fontSize: "clamp(11px, 0.95vw, 16px)" }}>
      <div data-testid="kiosk-no-purchase-disclaimer" style={{ maxWidth: "70%" }}>
        <ShieldCheck size={13} style={{ verticalAlign: "-2px",
                                                            marginRight: 6 }} />
        <strong>No purchase necessary.</strong>{" "}
        {state.compliance?.no_purchase_necessary_text
          || "All entries are free.  Open to legal residents."}
        {" · "}
        <a data-testid="kiosk-terms-link"
            href={`${window.location.origin}/terms/predict-win`}
            style={{ color: "#00d9ff" }}>Full terms</a>
      </div>
      <div data-testid="kiosk-meta"
              style={{ fontFamily: "monospace", letterSpacing: 1 }}>
        Polls every {state.refresh_after_sec || POLL_DEFAULT_SEC}s
        {" · "}{state.tv_display?.pairing_code}
      </div>
    </div>);
}

function WinnerOverlay({ state }) {
  const wo = state.resolution?.winning_option || {};
  return (
    <div data-testid="kiosk-winner-overlay"
            style={{ position: "absolute", top: "20%", left: "10%",
                        right: "10%", padding: 36,
                        background: "rgba(34,197,94,0.18)",
                        backdropFilter: "blur(12px)",
                        border: "2px solid rgba(34,197,94,0.6)",
                        borderRadius: 28, textAlign: "center",
                        animation: "kiosk-winner-overlay 1.6s ease-out 1",
                        pointerEvents: "none" }}>
      <PartyPopper size={56} color="#22c55e"
                              style={{ marginBottom: 14 }}/>
      <div style={{ fontSize: 18, letterSpacing: 3, fontFamily: "monospace",
                              color: "#22c55e", textTransform: "uppercase",
                              marginBottom: 8 }}>
        Winning pick
      </div>
      <div style={{ fontSize: "clamp(36px, 3.6vw, 84px)",
                              fontWeight: 800, lineHeight: 1 }}>
        {wo.label || state.resolution?.winning_option_id}
      </div>
      <div style={{ marginTop: 14, color: "rgba(255,255,255,0.75)",
                              fontSize: 15 }}>
        Winners credited to wallets on the RadioLife app.
      </div>
    </div>);
}

function ErrorScreen({ title, message, code }) {
  return (
    <div data-testid="kiosk-error-screen"
            style={{ minHeight: "100vh", display: "grid",
                        placeItems: "center", color: "#fff",
                        background: "#05080d", padding: 40,
                        textAlign: "center",
                        fontFamily: "Inter, system-ui" }}>
      <div>
        <div style={{ fontSize: 36, fontWeight: 800, marginBottom: 12 }}>
          {title}
        </div>
        <div style={{ color: "#9aa3af", maxWidth: 520 }}>{message}</div>
        {code && (
          <div style={{ marginTop: 18, fontFamily: "monospace",
                                  color: "#9aa3af", fontSize: 12 }}>
            pairing-code: {code}
          </div>)}
      </div>
    </div>);
}

const kioskRoot = (color) => ({
  minHeight: "100vh", width: "100%",
  background: color
    ? `linear-gradient(135deg, ${color}1f, #05080d 60%)`
    : "linear-gradient(135deg, #00d9ff1f, #05080d 60%)",
  color: "#fff", fontFamily: "Inter, system-ui",
  display: "grid", gridTemplateRows: "auto 1fr auto",
  position: "relative", overflow: "hidden",
});
const muted = { color: "rgba(255,255,255,0.55)", fontSize: 13 };
const kioskKeyframes = `
@keyframes kiosk-winner {
  0%, 100% { transform: scale(1); }
  50%        { transform: scale(1.01); }
}
@keyframes kiosk-winner-overlay {
  0%   { opacity: 0; transform: scale(0.92) translateY(20px); }
  100% { opacity: 1; transform: scale(1) translateY(0); }
}
`;
