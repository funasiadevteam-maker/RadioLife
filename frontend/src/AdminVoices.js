// /admin/voices — Phase 3.6 audition table for all RJ voices.
// Admin-only. Lists every voice with provider, accent, energies, assigned
// channels, and a play-button to audition the cached preview. "Regenerate"
// button lets the admin force a fresh sample.

import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, Play, Pause, RefreshCw, Loader2, Crown, Volume2,
  Filter, Globe, Sparkles, Radio as RadioIcon,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API } from "@/AuthContext";

const PROVIDER_BADGE = {
  openai_tts: { label: "OpenAI · gpt-4o-mini-tts", color: "#36e29b" },
  elevenlabs: { label: "ElevenLabs · eleven_v3", color: "#00d9ff" },
};

const ACCENT_BADGE = {
  american:       { label: "American",       color: "#ff6b9d" },
  indian_english: { label: "Indian-English", color: "#ffaa00" },
  hindi_native:   { label: "Hindi-Native",   color: "#ffd700" },
  hinglish:       { label: "Hinglish",       color: "#a78bfa" },
  punjabi:        { label: "Punjabi",        color: "#ff8a5b" },
  devotional:     { label: "Devotional",     color: "#ffb648" },
};

export default function AdminVoices() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(null);     // voice_key currently playing
  const [regenerating, setRegenerating] = useState({});
  const [filterProvider, setFilterProvider] = useState("all");
  const [filterAccent, setFilterAccent] = useState("all");
  const audioRef = useRef(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/voices`);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load voices");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const stopAudio = () => {
    const a = audioRef.current;
    if (a) { a.pause(); a.currentTime = 0; }
    setPlaying(null);
  };

  const handlePlay = (key) => {
    if (playing === key) { stopAudio(); return; }
    stopAudio();
    // Use absolute URL so audio element doesn't try relative paths
    const url = `${API}/voices/preview/${key}?t=${Date.now()}`;
    const a = new Audio(url);
    audioRef.current = a;
    setPlaying(key);
    a.onended = () => setPlaying(null);
    a.onerror = () => { toast.error("Could not play preview"); setPlaying(null); };
    a.play().catch((e) => { toast.error("Preview play failed"); setPlaying(null); });
  };

  const handleRegenerate = async (key) => {
    setRegenerating((m) => ({ ...m, [key]: true }));
    stopAudio();
    try {
      const r = await axios.post(`${API}/admin/voices/${key}/regenerate_preview`);
      if (r.data.ready) {
        toast.success(`Regenerated preview for ${key}`);
        // Auto-play the fresh sample
        setTimeout(() => handlePlay(key), 400);
      } else {
        toast.info("Generation still in progress — try again in a few seconds");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Regenerate failed");
    } finally {
      setRegenerating((m) => ({ ...m, [key]: false }));
    }
  };

  if (loading || !data) {
    return (
      <div className="admin-voices-shell">
        <div className="loading-block"><Loader2 className="spin" size={32} /></div>
      </div>
    );
  }

  const allVoices = data.voices || [];
  const visible = allVoices.filter((v) => {
    if (filterProvider !== "all" && v.provider !== filterProvider) return false;
    if (filterAccent !== "all" && v.accent_target !== filterAccent) return false;
    return true;
  });
  const accents = Array.from(new Set(allVoices.map((v) => v.accent_target))).sort();

  return (
    <div className="admin-voices-shell" data-testid="admin-voices-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="av-head">
        <Link to="/admin" className="back-link mono" data-testid="av-back-link">
          <ArrowLeft size={14} /> BACK TO ADMIN
        </Link>
        <div className="av-title">
          <Volume2 size={20} />
          <span>Voice Audition</span>
          <span className="mono dim">PHASE 3.6 · {data.total} voices</span>
        </div>
      </header>

      <section className="av-filters" data-testid="av-filters">
        <div className="av-filter-group">
          <Filter size={12} />
          <span className="mono dim">PROVIDER:</span>
          <button
            type="button"
            className={`av-chip ${filterProvider === "all" ? "is-on" : ""}`}
            onClick={() => setFilterProvider("all")}
            data-testid="filter-provider-all"
          >All</button>
          {data.providers.map((p) => (
            <button
              key={p}
              type="button"
              className={`av-chip ${filterProvider === p ? "is-on" : ""}`}
              onClick={() => setFilterProvider(p)}
              data-testid={`filter-provider-${p}`}
              style={{ "--chip-color": PROVIDER_BADGE[p]?.color || "#888" }}
            >{PROVIDER_BADGE[p]?.label || p}</button>
          ))}
        </div>
        <div className="av-filter-group">
          <Globe size={12} />
          <span className="mono dim">ACCENT:</span>
          <button
            type="button"
            className={`av-chip ${filterAccent === "all" ? "is-on" : ""}`}
            onClick={() => setFilterAccent("all")}
            data-testid="filter-accent-all"
          >All</button>
          {accents.map((a) => (
            <button
              key={a}
              type="button"
              className={`av-chip ${filterAccent === a ? "is-on" : ""}`}
              onClick={() => setFilterAccent(a)}
              data-testid={`filter-accent-${a}`}
              style={{ "--chip-color": ACCENT_BADGE[a]?.color || "#888" }}
            >{ACCENT_BADGE[a]?.label || a}</button>
          ))}
        </div>
      </section>

      <section className="av-grid" data-testid="av-grid">
        {visible.map((v) => {
          const isPlaying = playing === v.key;
          const isRegen = !!regenerating[v.key];
          const providerInfo = PROVIDER_BADGE[v.provider] || {};
          const accentInfo = ACCENT_BADGE[v.accent_target] || {};
          return (
            <div
              key={v.key}
              className={`av-card ${isPlaying ? "is-playing" : ""}`}
              data-testid={`voice-card-${v.key}`}
            >
              <div className="av-card-head">
                <div>
                  <h3 className="av-name">
                    {v.display_name}
                    {v.is_default && (
                      <span className="av-default-tag mono">DEFAULT</span>
                    )}
                  </h3>
                  <code className="av-key mono dim">{v.key}</code>
                </div>
                <div className="av-badges">
                  <span
                    className="av-badge mono"
                    style={{ background: providerInfo.color }}
                    data-testid={`voice-${v.key}-provider`}
                  >
                    {v.provider === "openai_tts" ? "OPENAI" : "11LABS"}
                  </span>
                  <span
                    className="av-badge mono"
                    style={{ background: accentInfo.color, color: "#0a0c18" }}
                    data-testid={`voice-${v.key}-accent`}
                  >
                    {accentInfo.label?.toUpperCase() || v.accent_target}
                  </span>
                </div>
              </div>

              <p className="av-persona">{v.persona}</p>

              <div className="av-meta-row">
                <div className="av-meta">
                  <span className="mono dim">ENERGIES</span>
                  <span>{v.fits_energies?.join(" · ") || "—"}</span>
                </div>
                <div className="av-meta">
                  <span className="mono dim">LANGS</span>
                  <span>{v.for_languages?.join(" · ") || "—"}</span>
                </div>
              </div>

              {v.assigned_channels?.length > 0 && (
                <div className="av-channels" data-testid={`voice-${v.key}-channels`}>
                  <span className="mono dim"><RadioIcon size={10}/> CHANNELS</span>
                  <div className="av-channel-list">
                    {v.assigned_channels.map((c) => (
                      <span key={c.slug} className={`av-channel-tag av-channel-${c.role}`}>
                        {c.name}
                        <span className="mono dim">·{c.role || "host"}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="av-actions">
                <button
                  type="button"
                  className={`av-play-btn ${isPlaying ? "is-playing" : ""}`}
                  onClick={() => handlePlay(v.key)}
                  data-testid={`voice-${v.key}-play-btn`}
                >
                  {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  {isPlaying ? "PAUSE" : "AUDITION"}
                </button>
                <button
                  type="button"
                  className="av-regen-btn"
                  onClick={() => handleRegenerate(v.key)}
                  disabled={isRegen}
                  data-testid={`voice-${v.key}-regenerate-btn`}
                  title="Re-render this voice's preview (A/B testing)"
                >
                  {isRegen
                    ? <Loader2 className="spin" size={14} />
                    : <RefreshCw size={14} />}
                  REGEN
                </button>
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}
