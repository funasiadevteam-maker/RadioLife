// Sticky bottom "now playing" preview bar — a teaser of persistent audio.
// Clicking any control routes to Listen / sign-in (no fabricated playback).
import { useState } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2 } from "lucide-react";

export default function PublicPlayerBar({ t, onActivate }) {
  const [playing, setPlaying] = useState(false);
  return (
    <div data-testid="fpl-player" className="fpl-player"
      style={{ background: t.navBg, borderTop: `1px solid ${t.navBorder}` }}>
      <div className="fpl-shell" style={{ height: 64, display: "flex", alignItems: "center", gap: 14 }}>
        <span style={{ width: 40, height: 40, borderRadius: 10, flexShrink: 0, display: "grid",
          placeItems: "center", color: "#fff", fontWeight: 900, background: t.accentGrad }}>BF</span>
        <div style={{ minWidth: 0, width: 160 }}>
          <div style={{ fontWeight: 800, fontSize: 13.5, color: t.text, whiteSpace: "nowrap",
            overflow: "hidden", textOverflow: "ellipsis" }}>Big FM Dubai</div>
          <div style={{ fontSize: 11.5, color: t.muted }}>RJ Alex · Live preview</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
          <IconBtn t={t} Icon={SkipBack} onClick={onActivate} />
          <button data-testid="fpl-player-play" onClick={() => { setPlaying((v) => !v); onActivate(); }}
            className="fpl-press" style={{ width: 42, height: 42, borderRadius: 999, border: "none",
              cursor: "pointer", background: t.accentGrad, display: "grid", placeItems: "center" }}>
            {playing ? <Pause size={18} color="#fff" fill="#fff" /> : <Play size={18} color="#fff" fill="#fff" />}
          </button>
          <IconBtn t={t} Icon={SkipForward} onClick={onActivate} />
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 10, minWidth: 0 }} className="fpl-progress">
          <div style={{ flex: 1, height: 4, borderRadius: 999, background: t.border, overflow: "hidden" }}>
            <div style={{ width: "34%", height: "100%", background: t.accentGrad }} />
          </div>
          <Volume2 size={17} color={t.text2} />
        </div>
      </div>
      <style>{`@media (max-width:760px){ .fpl-progress{ display:none !important; } }`}</style>
    </div>
  );
}

function IconBtn({ t, Icon, onClick }) {
  return (
    <button onClick={onClick} className="fpl-press" style={{ width: 34, height: 34, borderRadius: 999,
      border: "none", background: "transparent", cursor: "pointer", color: t.text2, display: "grid",
      placeItems: "center" }}>
      <Icon size={18} />
    </button>
  );
}
