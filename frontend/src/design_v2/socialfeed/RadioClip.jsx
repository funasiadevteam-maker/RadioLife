// FUUSIC — Radio clip card player + Clip & Share modal.
// Station daily highlights + listener 30s clips render as an audio card;
// station highlights also expose a "Clip & Share" action.
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  Play, Pause, Scissors, Radio, X, Loader2, Check, Globe, Users, ChevronDown, AlertCircle,
} from "lucide-react";
import { fireConfetti } from "./confetti";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const WAVE = [30, 55, 80, 45, 90, 60, 35, 70, 95, 50, 65, 40, 85, 55, 75, 45, 60, 88, 42, 68, 52, 78, 38, 62];

export function RadioClipPlayer({ item, t, onClip }) {
  const meta = item.meta || {};
  const ref = useRef(null);
  const [playing, setPlaying] = useState(false);
  const toggle = () => {
    const a = ref.current;
    if (!a) return;
    if (a.paused) { a.play().catch(() => {}); setPlaying(true); }
    else { a.pause(); setPlaying(false); }
  };
  const isStation = meta.clip_kind === "station_highlight";
  const dur = meta.duration_sec || 30;
  return (
    <div style={{ margin: "0 14px 10px", borderRadius: 14, border: `1px solid ${t.border}`, background: t.cardAlt, padding: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button onClick={toggle} data-testid="rc-play" aria-label={playing ? "Pause" : "Play"} className="sf-press"
          style={{ width: 46, height: 46, borderRadius: 999, border: "none", cursor: "pointer", background: t.accentGrad, display: "grid", placeItems: "center", flexShrink: 0 }}>
          {playing ? <Pause size={20} color="#fff" fill="#fff" /> : <Play size={20} color="#fff" fill="#fff" />}
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <Radio size={13} color={t.accent} />
            <span className="sf-clamp2" style={{ fontSize: 12, fontWeight: 700, color: t.text2 }}>
              {meta.station_name}{meta.show_name ? ` · ${meta.show_name}` : ""}
            </span>
          </div>
          <div className={playing ? "rc-wave rc-wave-on" : "rc-wave"} style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 22 }}>
            {WAVE.map((h, i) => (
              <span key={i} style={{ flex: 1, height: `${h}%`, background: t.accent, opacity: 0.5, borderRadius: 2, "--i": i }} />
            ))}
          </div>
        </div>
        <span style={{ fontSize: 11.5, fontWeight: 800, color: t.muted, flexShrink: 0 }}>0:{String(dur).padStart(2, "0")}</span>
      </div>
      <audio ref={ref} src={item.media_url} onEnded={() => setPlaying(false)} preload="none" />
      {isStation && meta.station_id && (
        <button onClick={() => onClip && onClip()} data-testid="rc-clipshare" className="sf-press"
          style={{ marginTop: 10, width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "9px", borderRadius: 11, border: `1px solid ${t.accent}`, background: "transparent", color: t.accent, fontWeight: 800, fontSize: 13, cursor: "pointer" }}>
          <Scissors size={15} /> Clip & Share
        </button>
      )}
    </div>
  );
}

const AUDS = [
  { k: "public", label: "Public", Icon: Globe },
  { k: "friends", label: "Friends", Icon: Users },
];

export function ClipShareModal({ t, station, onClose, onPosted }) {
  const [elig, setElig] = useState(null);
  const [start, setStart] = useState(0);
  const [comment, setComment] = useState("");
  const [audience, setAudience] = useState("public");
  const [audOpen, setAudOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState(null);
  const audioRef = useRef(null);
  const idemRef = useRef(`clip_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/stations/${station.id}/clip-eligibility`, { withCredentials: true })
      .then((r) => { if (alive) setElig(r.data); })
      .catch(() => { if (alive) setElig({ allowed: false, reason: "Couldn't check clip permission." }); });
    return () => { alive = false; };
  }, [station.id]);

  const maxStart = Math.max(0, (elig?.buffer_seconds || 300) - 30);
  const preview = () => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = start;
    a.play().catch(() => {});
    setTimeout(() => { try { a.pause(); } catch (_e) {} }, 30000);
  };
  const share = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(`${API}/radio/clips/share`, {
        station_id: station.id, start_offset: start, duration_seconds: 30,
        comment: comment.trim(), visibility: audience, show_name: station.show_name,
        idempotency_key: idemRef.current,
      }, { withCredentials: true });
      setDone(true);
      try { fireConfetti(); } catch (_e) { /* noop */ }
      setTimeout(() => onPosted && onPosted(), 700);
    } catch (e) {
      setErr(e?.response?.data?.detail?.message || "Couldn't share your clip — tap Share to retry.");
    } finally { setBusy(false); }
  };

  const Aud = AUDS.find((a) => a.k === audience) || AUDS[0];
  const mm = Math.floor(start / 60), ss = String(Math.floor(start % 60)).padStart(2, "0");
  return (
    <div data-testid="clipshare-modal" onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(8,11,22,.6)", backdropFilter: "blur(4px)", display: "grid", placeItems: "center", padding: 14 }}>
      <div onClick={(e) => e.stopPropagation()} className="sf-fade-in"
        style={{ width: "100%", maxWidth: 480, background: t.card, border: `1px solid ${t.border}`, borderRadius: 20, boxShadow: t.shadow, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: `1px solid ${t.border}` }}>
          <span style={{ fontWeight: 900, fontSize: 16, color: t.text }}>Clip a Moment</span>
          <button onClick={onClose} data-testid="clipshare-close" className="sf-press" style={{ width: 32, height: 32, borderRadius: 999, border: "none", background: t.chip, color: t.text2, cursor: "pointer", display: "grid", placeItems: "center" }}><X size={18} /></button>
        </div>

        {done ? (
          <div style={{ padding: "44px 20px", textAlign: "center" }}>
            <span style={{ width: 60, height: 60, borderRadius: 999, display: "inline-grid", placeItems: "center", background: t.accentSoft, marginBottom: 12 }}><Check size={30} color={t.accent} /></span>
            <div style={{ fontWeight: 800, fontSize: 17, color: t.text }}>Clip shared to your wall!</div>
          </div>
        ) : elig === null ? (
          <div style={{ padding: 40, textAlign: "center", color: t.text2 }}><Loader2 size={20} className="sf-spin" /></div>
        ) : !elig.allowed ? (
          <div style={{ padding: 20 }}>
            <div style={{ display: "flex", gap: 8, color: t.text2, fontSize: 13.5, marginBottom: 14 }}>
              <AlertCircle size={16} color={t.gold} /> {elig.reason || "This station hasn't enabled clip sharing."}
            </div>
            <button data-testid="clipshare-sharestation" onClick={onClose} className="sf-press"
              style={{ width: "100%", padding: "11px", borderRadius: 12, border: "none", background: t.accentGrad, color: "#fff", fontWeight: 800, cursor: "pointer" }}>
              Share the Station instead
            </button>
          </div>
        ) : (
          <div style={{ padding: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              {station.logo && <img src={station.logo} alt="" style={{ width: 40, height: 40, borderRadius: 10, objectFit: "cover" }} />}
              <div>
                <div style={{ fontWeight: 800, fontSize: 14, color: t.text }}>{station.name}</div>
                <div style={{ fontSize: 12, color: t.muted }}>Choose your 30-second moment</div>
              </div>
            </div>

            {/* waveform + start slider */}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 42, marginBottom: 6 }}>
              {WAVE.map((h, i) => (
                <span key={i} style={{ flex: 1, height: `${h}%`, background: t.accent, opacity: (i / WAVE.length >= start / (elig.buffer_seconds || 300) && i / WAVE.length <= (start + 30) / (elig.buffer_seconds || 300)) ? 0.9 : 0.3, borderRadius: 2 }} />
              ))}
            </div>
            <input type="range" min={0} max={maxStart} step={1} value={start}
              data-testid="clipshare-start" onChange={(e) => setStart(Number(e.target.value))}
              style={{ width: "100%", accentColor: t.accent }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: t.muted, marginBottom: 10 }}>
              <span>Start {mm}:{ss}</span><span>30s window</span>
            </div>

            <button onClick={preview} data-testid="clipshare-preview" className="sf-press"
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 14px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer", marginBottom: 12 }}>
              <Play size={14} color={t.accent} /> Play Preview
            </button>
            <audio ref={audioRef} src={elig.buffer_audio_url} preload="none" />

            <textarea value={comment} onChange={(e) => setComment(e.target.value)} data-testid="clipshare-comment"
              placeholder="Add your comment… what made this moment great?" rows={3}
              style={{ width: "100%", resize: "vertical", padding: 12, borderRadius: 12, border: `1px solid ${t.border}`, background: t.cardAlt, color: t.text, fontSize: 14, outline: "none", marginBottom: 10 }} />

            <div style={{ position: "relative", marginBottom: 12 }}>
              <button onClick={() => setAudOpen((v) => !v)} data-testid="clipshare-audience" className="sf-press"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.chip, color: t.text, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
                <Aud.Icon size={14} color={t.accent} /> {Aud.label} <ChevronDown size={14} />
              </button>
              {audOpen && (
                <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, width: 180, background: t.card, border: `1px solid ${t.border}`, borderRadius: 12, boxShadow: t.shadow, padding: 6, zIndex: 10 }}>
                  {AUDS.map((a) => (
                    <button key={a.k} data-testid={`clipshare-aud-${a.k}`} onClick={() => { setAudience(a.k); setAudOpen(false); }} className="sf-press"
                      style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "left", background: audience === a.k ? t.accentSoft : "transparent", border: "none", borderRadius: 9, padding: "9px 10px", cursor: "pointer", fontWeight: 700, fontSize: 13, color: t.text }}>
                      <a.Icon size={15} color={t.accent} /> {a.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {err && (
              <div data-testid="clipshare-error" style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, padding: "8px 11px", borderRadius: 10, background: `${t.live}18`, color: t.live, fontSize: 12.5, fontWeight: 600 }}>
                <AlertCircle size={15} /> {err}
              </div>
            )}

            <button onClick={share} disabled={busy} data-testid="clipshare-submit" className="sf-press"
              style={{ width: "100%", padding: "12px", borderRadius: 999, border: "none", background: t.accentGrad, color: "#fff", fontWeight: 800, cursor: "pointer", opacity: busy ? 0.6 : 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
              {busy ? <><Loader2 size={15} className="sf-spin" /> Sharing…</> : <><Scissors size={16} /> Share to My Wall</>}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
