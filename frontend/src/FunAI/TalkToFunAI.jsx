/** TalkToFunAI — voice panel for the Interactive News anchor.
 *  Owns the Grok voice session, surfaces clear voice states + a mic-active
 *  indicator, shows the live transcript, and always offers a Stop control.
 *  Reports its status up so the page can duck/resume the news program.
 */
import React, { useEffect } from "react";
import { Mic, Square, Loader2, Radio, AlertTriangle, X } from "lucide-react";
import useGrokVoice, { VOICE_STATES } from "@/FunAI/useGrokVoice";

const LABELS = {
  [VOICE_STATES.IDLE]: "Ready",
  [VOICE_STATES.AUTHORIZING]: "Starting…",
  [VOICE_STATES.CONNECTING]: "Connecting…",
  [VOICE_STATES.READY]: "Fun AI is ready — ask anything",
  [VOICE_STATES.LISTENING]: "Listening…",
  [VOICE_STATES.THINKING]: "Thinking…",
  [VOICE_STATES.SPEAKING]: "Fun AI speaking…",
  [VOICE_STATES.ERROR]: "Voice unavailable",
};

export default function TalkToFunAI({ onClose, onStatusChange, dark = true,
                                     mode, topic, modeLabel, onFollow,
                                     surface, station, onRadioAction }) {
  const { status, micActive, transcript, errorMsg, start, stop } = useGrokVoice({
    onToolEvent: (name, out) => {
      if (name === "follow_story" && onFollow) onFollow(out);
      if (name === "request_radio_action" && onRadioAction) onRadioAction(out);
    },
  });

  // Auto-start the session when the panel opens, following the chosen surface/mode.
  useEffect(() => { start({ mode, topic, surface, station }); return () => { stop(); }; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (onStatusChange) onStatusChange(status, micActive); }, [status, micActive, onStatusChange]);

  const bg = dark ? "#0b1220" : "#ffffff";
  const fg = dark ? "#e8eef6" : "#0b1220";
  const sub = dark ? "#9aa3af" : "#64748b";
  const line = dark ? "rgba(0,217,255,0.25)" : "rgba(2,132,199,0.25)";
  const accent = "#00b8d9";

  const speaking = status === VOICE_STATES.SPEAKING;
  const listening = status === VOICE_STATES.LISTENING;
  const thinking = [VOICE_STATES.THINKING, VOICE_STATES.AUTHORIZING, VOICE_STATES.CONNECTING].includes(status);
  const isError = status === VOICE_STATES.ERROR;

  const handleStop = async () => { await stop(); if (onClose) onClose(); };

  return (
    <div data-testid="talk-funai-panel"
         style={{ position: "fixed", right: 20, bottom: 20, width: 360, maxWidth: "92vw",
                  zIndex: 1000, background: bg, color: fg, borderRadius: 18,
                  border: `1px solid ${line}`, boxShadow: "0 18px 50px rgba(0,0,0,0.45)",
                  overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px",
                    borderBottom: `1px solid ${line}` }}>
        <Radio size={16} color={accent} />
        <span style={{ fontWeight: 700, fontSize: 14 }}>Talk to Fun AI</span>
        {modeLabel && (
          <span style={{ fontSize: 11, color: sub, fontFamily: "monospace" }}>· {modeLabel}</span>
        )}
        <span data-testid="talk-funai-mic"
              title={micActive ? "Microphone active" : "Microphone off"}
              style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
                       fontSize: 11, color: micActive ? "#ef4444" : sub, fontFamily: "monospace" }}>
          <span style={{ width: 8, height: 8, borderRadius: 999,
                         background: micActive ? "#ef4444" : sub,
                         boxShadow: micActive ? "0 0 0 4px rgba(239,68,68,0.18)" : "none" }} />
          {micActive ? "MIC ON" : "MIC OFF"}
        </span>
        <button data-testid="talk-funai-close" onClick={handleStop}
                aria-label="Close"
                style={{ background: "transparent", border: "none", color: sub, cursor: "pointer", padding: 2 }}>
          <X size={16} />
        </button>
      </div>

      <div style={{ padding: "16px" }}>
        <div data-testid="talk-funai-status" data-status={status}
             style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <div style={{ width: 46, height: 46, borderRadius: 999, flexShrink: 0,
                        display: "grid", placeItems: "center",
                        background: isError ? "rgba(239,68,68,0.15)" : `rgba(0,184,217,0.12)`,
                        border: `2px solid ${isError ? "#ef4444" : accent}`,
                        transform: speaking ? "scale(1.06)" : "scale(1)",
                        transition: "transform .2s ease",
                        animation: listening ? "funaiPulse 1.1s ease-in-out infinite" : "none" }}>
            {isError ? <AlertTriangle size={20} color="#ef4444" />
              : thinking ? <Loader2 size={20} color={accent} className="funai-spin" />
              : <Mic size={20} color={accent} />}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{LABELS[status] || "Ready"}</div>
            <div style={{ fontSize: 12, color: sub, lineHeight: 1.4 }}>
              {isError ? (errorMsg || "Try again, or keep listening to the program.")
                : "Interrupt any time — Fun AI will stop and listen."}
            </div>
          </div>
        </div>

        <div data-testid="talk-funai-transcript"
             style={{ maxHeight: 180, overflowY: "auto", display: "flex",
                      flexDirection: "column", gap: 8, marginBottom: 14 }}>
          {transcript.length === 0 ? (
            <div style={{ fontSize: 12, color: sub, fontStyle: "italic" }}>
              {surface === "player"
                ? "Try: “Play something more upbeat” or “What song is this?”"
                : "Try: “What's the latest technology news?” or “Tell me more about that.”"}
            </div>
          ) : transcript.map((t, i) => (
            <div key={i} style={{ fontSize: 13, lineHeight: 1.5 }}>
              <span style={{ fontWeight: 700,
                             color: t.role === "anchor" ? accent : fg }}>
                {t.role === "anchor" ? "Fun AI" : "You"}:
              </span>{" "}
              <span style={{ color: t.role === "anchor" ? fg : sub }}>{t.text}</span>
            </div>
          ))}
        </div>

        <button data-testid="talk-funai-stop" onClick={handleStop}
                style={{ width: "100%", display: "inline-flex", alignItems: "center",
                         justifyContent: "center", gap: 8, background: "#ef4444",
                         color: "#fff", border: "none", borderRadius: 10,
                         padding: "11px 14px", fontWeight: 700, cursor: "pointer" }}>
          <Square size={14} /> {surface === "player" ? "Stop & resume radio" : "Stop & resume news"}
        </button>
        <div style={{ fontSize: 10, color: sub, textAlign: "center", marginTop: 8 }}>
          {surface === "player"
            ? "Fun AI is an AI assistant. Radio changes follow FUUSIC's programming rules."
            : "Fun AI is an AI assistant. News is read from verified sources."}
        </div>
      </div>

      <style>{`
        @keyframes funaiPulse { 0%,100%{ box-shadow:0 0 0 0 rgba(0,184,217,0.35);} 50%{ box-shadow:0 0 0 8px rgba(0,184,217,0);} }
        .funai-spin { animation: funaiSpin 1s linear infinite; }
        @keyframes funaiSpin { to { transform: rotate(360deg);} }
      `}</style>
    </div>
  );
}
