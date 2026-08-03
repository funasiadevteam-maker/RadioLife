import React, { useState } from "react";
import { saveToWallet } from "./playApi";

/* ============================================================================
   WinReveal — result screen for any Play & Win game (replaces ResultBanner)
   ----------------------------------------------------------------------------
   Props:
     outcome     : the server response from resolvePlay()
                   { won, prizeTitle, playId, coupon: { code, redeemUrl } | null }
     onPlayAgain : () => void
     accent      : the game's accent color (optional)

   Self-contained: inline styles + one scoped <style> for confetti/hover.
   The coupon was already issued by the server on resolve; "Save to Wallet"
   pins it to the listener's Wallet (idempotent server-side).
   ============================================================================ */

const FONT = "'DM Sans','Segoe UI',system-ui,sans-serif";
const DISPLAY = "'Syne','DM Sans',system-ui,sans-serif";
const PINK = "#F72585";
const CONFETTI = [PINK, "#FF8500", "#4361EE", "#2DD4A7", "#FFC83D", "#7B61FF"];

const pieces = Array.from({ length: 18 }, (_, i) => (
  <span key={i} className="wr-piece" style={{
    left: `${(i / 18) * 100}%`,
    background: CONFETTI[i % CONFETTI.length],
    animationDelay: `${(i % 9) * 0.1}s`,
    animationDuration: `${1.7 + (i % 4) * 0.35}s`,
  }} />
));

export default function WinReveal({ outcome, onPlayAgain, accent = PINK }) {
  const [wallet, setWallet] = useState("idle"); // idle | saving | saved | error
  const [copied, setCopied] = useState(false);
  const code = outcome?.coupon?.code;
  const redeemUrl = outcome?.coupon?.redeemUrl;

  const copy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch { /* clipboard blocked — ignore */ }
  };

  const save = async () => {
    if (wallet === "saving" || wallet === "saved") return;
    setWallet("saving");
    try {
      await saveToWallet(outcome.playId);
      setWallet("saved");
    } catch {
      setWallet("error");
    }
  };

  // ---- LOSS ----
  if (!outcome?.won) {
    return (
      <div style={wrap}>
        <div style={{ fontSize: 54 }}>😅</div>
        <div style={{ fontFamily: DISPLAY, fontSize: 24, fontWeight: 800 }}>So close!</div>
        <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 14, maxWidth: 260 }}>
          Keep listening — your next win could be one play away.
        </div>
        <button onClick={onPlayAgain} style={primaryBtn(accent)}>Try Again</button>
      </div>
    );
  }

  // ---- WIN ----
  return (
    <div style={{ ...wrap, position: "relative", overflow: "hidden", paddingTop: 16 }}>
      <style>{`
        .wr-confetti{position:absolute;inset:0;pointer-events:none;overflow:hidden;}
        .wr-piece{position:absolute;top:-16px;width:8px;height:14px;border-radius:2px;opacity:.9;
          animation-name:wrfall;animation-timing-function:linear;animation-iteration-count:1;}
        @keyframes wrfall{0%{transform:translateY(-20px) rotate(0)}
          100%{transform:translateY(380px) rotate(440deg);opacity:0}}
        .wr-btn:hover{filter:brightness(1.08);}
        .wr-chip:hover{filter:brightness(1.1);}
      `}</style>
      <div className="wr-confetti">{pieces}</div>

      <div style={{ fontSize: 54 }}>🎉</div>
      <div style={{ fontFamily: DISPLAY, fontSize: 13, letterSpacing: 2, color: accent, textTransform: "uppercase" }}>
        You won
      </div>
      <div style={{ fontFamily: DISPLAY, fontSize: 28, fontWeight: 800, lineHeight: 1.1 }}>
        {outcome.prizeTitle}
      </div>

      {code && (
        <div className="wr-chip" onClick={copy} title="Tap to copy" style={codeChip(accent)}>
          <span style={{ fontFamily: "monospace", fontSize: 18, letterSpacing: 2, fontWeight: 700 }}>{code}</span>
          <span style={{ fontSize: 11, opacity: 0.8, letterSpacing: 0.5 }}>
            {copied ? "COPIED ✓" : "TAP TO COPY"}
          </span>
        </div>
      )}

      <button
        className="wr-btn"
        onClick={save}
        disabled={wallet === "saved"}
        style={primaryBtn(wallet === "saved" ? "#2DD4A7" : accent, wallet === "saving")}
      >
        {wallet === "idle" && "💾  Save to Wallet"}
        {wallet === "saving" && "Saving…"}
        {wallet === "saved" && "Saved to Wallet ✓"}
        {wallet === "error" && "↻  Retry save"}
      </button>
      {wallet === "error" && (
        <div style={{ color: "#ff6b6b", fontSize: 12 }}>Couldn't save — tap retry.</div>
      )}

      {redeemUrl && (
        <a href={redeemUrl} target="_blank" rel="noreferrer"
           style={{ color: "rgba(255,255,255,0.7)", fontSize: 13, textDecoration: "underline" }}>
          View &amp; redeem details →
        </a>
      )}

      <button className="wr-btn" onClick={onPlayAgain} style={ghostBtn}>Play Again</button>
    </div>
  );
}

/* ---------------- styles ---------------- */
const wrap = {
  display: "flex", flexDirection: "column", alignItems: "center",
  gap: 12, textAlign: "center", color: "#fff", fontFamily: FONT, padding: 8,
};

const primaryBtn = (color, busy) => ({
  border: "none", cursor: busy ? "default" : "pointer", marginTop: 4,
  padding: "13px 30px", borderRadius: 999, fontFamily: DISPLAY,
  fontSize: 15, fontWeight: 800, letterSpacing: 0.3, color: "#fff",
  background: `linear-gradient(135deg, ${color}, ${color}cc)`,
  boxShadow: `0 8px 22px ${color}66`, opacity: busy ? 0.7 : 1,
});

const ghostBtn = {
  border: "1px solid rgba(255,255,255,0.25)", background: "transparent",
  color: "#fff", padding: "9px 22px", borderRadius: 999, cursor: "pointer",
  fontFamily: FONT, fontSize: 14,
};

const codeChip = (accent) => ({
  cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
  padding: "12px 26px", borderRadius: 12, border: `1.5px dashed ${accent}`,
  background: `${accent}18`, color: "#fff",
});
