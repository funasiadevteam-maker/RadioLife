import React, { useRef, useState } from "react";
import { Play, Pause, Check } from "lucide-react";

// Self-contained (inline-styled) so it drops into any surface. Plays a
// short sample clip per voice before you commit to switching.
export const VoicePicker = ({ voices = [], value, onChange, disabled, apiBase = "" }) => {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(null);

  const toAbs = (u) => (!u ? u : u.startsWith("http") ? u : `${apiBase}${u}`);

  const preview = (v) => {
    const url = toAbs(v.sample_url);
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    if (playing === v.voice_id) { setPlaying(null); return; }
    if (!url) return;
    const a = new Audio(url);
    audioRef.current = a;
    a.onended = () => setPlaying(null);
    a.play().then(() => setPlaying(v.voice_id)).catch(() => setPlaying(null));
  };

  return (
    <div data-testid="voice-picker" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {voices.map((v) => {
        const sel = v.voice_id === value;
        return (
          <div key={v.voice_id} data-testid={`voice-option-${v.voice_id}`}
               onClick={() => !disabled && onChange && onChange(v.voice_id)}
               style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                        borderRadius: 10, cursor: disabled ? "default" : "pointer",
                        opacity: disabled ? 0.6 : 1,
                        border: sel ? "1px solid #00d9ff" : "1px solid rgba(255,255,255,0.12)",
                        background: sel ? "rgba(0,217,255,0.10)" : "rgba(255,255,255,0.03)",
                        transition: "border-color .15s, background .15s" }}>
            <button type="button" data-testid={`voice-preview-${v.voice_id}`}
                    onClick={(e) => { e.stopPropagation(); preview(v); }}
                    aria-label={`Preview ${v.name}`}
                    style={{ width: 30, height: 30, borderRadius: 999, flexShrink: 0,
                             display: "flex", alignItems: "center", justifyContent: "center",
                             border: "1px solid rgba(0,217,255,0.4)",
                             background: "rgba(0,217,255,0.12)", color: "#00d9ff",
                             cursor: "pointer" }}>
              {playing === v.voice_id ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{v.name}</div>
              <div style={{ color: "#9aa3af", fontSize: 11 }}>{v.description}</div>
            </div>
            {sel && <Check size={16} color="#00d9ff" />}
          </div>
        );
      })}
    </div>
  );
};

export default VoicePicker;
