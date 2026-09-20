// Public landing page for a share. Route: /r/:share_id (no auth required).
// Renders a playable preview + brand CTA. OG meta tags are set via Helmet-less
// document.head writes so WhatsApp/Twitter/Slack get rich previews.

import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { Play, Pause, Loader2, Radio as RadioIcon, ExternalLink } from "lucide-react";
import { Toaster } from "sonner";
import { API } from "@/AuthContext";
import BigFmBrand from "@/components/BigFmBrand";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function setOG(meta) {
  const tags = [
    ["og:title", meta.title],
    ["og:description", meta.description],
    ["og:type", "music.song"],
    ["og:url", window.location.href],
    ["og:audio", meta.audio_url],
    ["og:audio:type", "audio/mpeg"],
    ["twitter:card", "player"],
    ["twitter:title", meta.title],
    ["twitter:description", meta.description],
    ["twitter:player:stream", meta.audio_url],
    ["twitter:player:stream:content_type", "audio/mpeg"],
  ];
  for (const [prop, val] of tags) {
    if (!val) continue;
    const sel = prop.startsWith("og:") ? `meta[property="${prop}"]` : `meta[name="${prop}"]`;
    let el = document.head.querySelector(sel);
    if (!el) {
      el = document.createElement("meta");
      if (prop.startsWith("og:")) el.setAttribute("property", prop);
      else el.setAttribute("name", prop);
      document.head.appendChild(el);
    }
    el.setAttribute("content", val);
  }
  if (meta.title) document.title = meta.title;
}

export default function ShareLanding() {
  const { share_id } = useParams();
  const [meta, setMeta] = useState(null);
  const [err, setErr] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const audioRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/share/${share_id}/meta`);
        setMeta(r.data);
        setOG({
          title: `FUUSIC · ${r.data.host_names?.join(" × ") || "Radio break"}`,
          description: `${r.data.channel_name ? `From ${r.data.channel_name} · ` : ""}Listen to a ${Math.round(r.data.duration_sec)}s break from FUUSIC — Hinglish AI radio.`,
          audio_url: `${BACKEND_URL}${r.data.audio_url}`,
        });
      } catch (e) {
        setErr(e?.response?.status === 404 ? "Share not found" : "Could not load share");
      }
    })();
  }, [share_id]);

  const toggle = async () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { try { await a.play(); setPlaying(true); } catch (_e) { /* */ } }
    else { a.pause(); setPlaying(false); }
  };

  return (
    <div className="share-landing" data-testid="share-landing">
      <Toaster theme="dark" position="bottom-right" richColors />
      <div className="auth-bg" aria-hidden>
        <div className="bg-ring r1" /><div className="bg-ring r2" /><div className="bg-ring r3" />
      </div>

      <header className="share-land-head">
        <div className="auth-brand">
          <span className="brand-dot" />
          <BigFmBrand variant="inline" testId="share-brand" />
        </div>
        <span className="mono share-land-tag">LIVE · BREAK CLIP</span>
      </header>

      {err && <div className="share-land-card share-err"><p>{err}</p>
        <Link to="/" className="share-land-cta">Go to FUUSIC →</Link></div>}

      {!err && !meta && (
        <div className="share-land-card"><Loader2 className="spin" size={28} /></div>
      )}

      {meta && (
        <div className="share-land-card" data-testid="share-land-card">
          <div className="share-land-hosts">
            {(meta.host_names || []).map((n) => (
              <span key={n} className="share-land-host">{n}</span>
            ))}
            {meta.rj_format === "duo" && <span className="duo-badge mono">DUO</span>}
          </div>

          <h1 className="share-land-h1">A break from <b>{meta.channel_name || "FUUSIC"}</b></h1>

          {meta.track_title && (
            <p className="share-land-after mono">
              AFTER "{meta.track_title}"{meta.track_artist ? ` · ${meta.track_artist}` : ""}
            </p>
          )}

          <button type="button" className={`share-land-play ${playing ? "is-on" : ""}`}
                  onClick={toggle} data-testid="share-land-play"
                  aria-label={playing ? "Pause" : "Play"}>
            {playing ? <Pause size={42} fill="white" /> : <Play size={42} fill="white" style={{ marginLeft: 4 }} />}
          </button>

          <div className="share-wave">
            {Array.from({ length: 32 }).map((_, i) => (
              <span key={i} className="share-wave-bar"
                    style={{
                      animationDelay: `${i * 60}ms`,
                      height: `${playing ? 20 + Math.abs(Math.sin(i + progress)) * 28 : 6}px`,
                    }} />
            ))}
          </div>

          <audio
            ref={audioRef}
            src={`${BACKEND_URL}${meta.audio_url}`}
            preload="auto"
            onTimeUpdate={(e) => setProgress(e.target.currentTime || 0)}
            onEnded={() => setPlaying(false)}
            data-testid="share-land-audio"
          />

          <p className="share-land-blurb">
            Heard on <b>FUUSIC</b> — the AI-powered Hinglish radio
            station made for the Indian community in the UAE.
          </p>

          <Link to="/" className="share-land-cta" data-testid="share-land-cta">
            <RadioIcon size={16} /> Listen on FUUSIC <ExternalLink size={14} />
          </Link>

          <div className="share-land-foot mono">
            ~{Math.round(meta.duration_sec)}s · {(meta.view_count || 1).toLocaleString()} VIEW{meta.view_count === 1 ? "" : "S"}
          </div>
        </div>
      )}
    </div>
  );
}
