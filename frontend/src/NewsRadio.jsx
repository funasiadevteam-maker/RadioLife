/** Phase 40 Session 2 — /radio/news standalone news radio player.
 *  Reads /api/news_radio/queue, plays each item's audio sequentially
 *  (when available) or shows text-only segments.
 *
 *  Phase 42-F.2 — adds a top-of-page banner when the queue is in
 *  text-only mode (TTS provider paused / unavailable).  Anonymous
 *  visitors no longer get a generic "Could not load" error — the queue
 *  endpoint accepts unauthenticated callers in F.2.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Radio, ArrowLeft, Volume2, Info } from "lucide-react";
import { API } from "@/AuthContext";

export default function NewsRadio() {
  const [items, setItems] = useState([]);
  const [idx,   setIdx]   = useState(0);
  const [empty, setEmpty] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState("audio");  // "audio" | "text"
  const [tts,  setTts]  = useState(null);

  useEffect(() => {
    let cancel = false;
    let tries = 0;
    const load = async () => {
      try {
        const r = await axios.get(`${API}/news_radio/queue`,
                                  { params: { limit: 6 }, withCredentials: true });
        if (cancel) return;
        if (r.data?.items?.length) {
          setItems(r.data.items);
          setMode(r.data.mode || "text");
          setTts(r.data.tts || null);
          setEmpty(null);
          setLoading(false);
          return;
        }
        // Cold cache: kick off generation ONCE, then poll until scripts land.
        if (tries === 0) {
          axios.post(`${API}/news_radio/trigger-batch`, null,
                     { params: { top_n: 6 }, withCredentials: true }).catch(() => {});
        }
        tries += 1;
        if (tries <= 6) {
          setEmpty("Preparing today's news summaries — this takes a few seconds…");
          setLoading(false);
          setTimeout(load, 5000);
        } else {
          setEmpty(r.data?.retry_hint || "No news summaries available right now.");
          setLoading(false);
        }
      } catch (e) {
        if (!cancel) { setEmpty("Could not load news radio queue."); setLoading(false); }
      }
    };
    load();
    return () => { cancel = true; };
  }, []);

  const current = items[idx];
  const showTextModeBanner = mode === "text" && items.length > 0;

  return (
    <div data-testid="news-radio-page"
         style={{ maxWidth: 760, margin: "0 auto", padding: 24, color: "#fff" }}>
      <Link to="/news" data-testid="news-radio-back"
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     color: "#9aa3af", textDecoration: "none",
                     fontSize: 13, marginBottom: 18 }}>
        <ArrowLeft size={14} /> Back to news
      </Link>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 18px" }}>
        <Radio size={22} color="#00d9ff" /> RadioLife News Radio
      </h1>

      {showTextModeBanner && (
        <div data-testid="news-radio-mode-banner"
             data-mode={mode}
             style={{ display: "flex", alignItems: "center", gap: 10,
                      background: "rgba(245,158,11,0.10)",
                      border: "1px solid rgba(245,158,11,0.40)",
                      color: "#fbbf24",
                      padding: "12px 16px", borderRadius: 10,
                      marginBottom: 16, fontSize: 13 }}>
          <Info size={16} />
          <span>
            <b>Audio generation paused</b> — News Radio is running in text
            mode while we re-validate the TTS provider. Headlines below
            are read-along; pre-recorded audio will return once Phase H&prime; ships.
          </span>
        </div>
      )}

      {loading ? (
        <div style={{ color: "#9aa3af", padding: 40 }}>Loading queue…</div>
      ) : empty ? (
        <div data-testid="news-radio-empty"
             style={{ background: "rgba(245,158,11,0.1)",
                      border: "1px dashed #f59e0b", color: "#f59e0b",
                      padding: 20, borderRadius: 10 }}>
          {empty}
        </div>
      ) : (
        <>
          <div data-testid="news-radio-now-playing"
               style={{ background: "#1f2937", padding: 22,
                        borderRadius: 14, marginBottom: 18,
                        borderLeft: "3px solid #00d9ff" }}>
            <div style={{ fontSize: 11, color: "#00d9ff",
                          fontFamily: "monospace", letterSpacing: 1,
                          marginBottom: 8 }}>
              NOW PLAYING · {idx + 1} of {items.length}
            </div>
            {current.audio_url && (
              <div data-testid="news-radio-audio-badge"
                   style={{ display: "inline-flex", alignItems: "center", gap: 6,
                            background: "rgba(0,217,255,0.12)",
                            border: "1px solid rgba(0,217,255,0.35)",
                            color: "#00d9ff", padding: "3px 10px",
                            borderRadius: 999, fontSize: 11,
                            fontFamily: "monospace", marginBottom: 10 }}>
                <Volume2 size={12} /> LISTEN · shared for 48h
              </div>
            )}
            <h2 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 12px",
                          lineHeight: 1.4 }}>
              {current.title}
            </h2>
            <p style={{ color: "#cbd5e1", fontSize: 14, lineHeight: 1.7,
                        margin: "0 0 14px" }}>
              {current.summary_script}
            </p>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "center", fontSize: 12,
                          fontFamily: "monospace", color: "#9aa3af" }}>
              <span>{current.source_name}</span>
              <span>~{current.duration_estimate_sec}s</span>
            </div>
            {current.audio_url ? (
              <audio data-testid="news-radio-audio"
                              src={`${API.replace(/\/api$/, "")}${current.audio_url}`}
                              autoPlay controls
                              onEnded={() => setIdx(i => Math.min(i + 1, items.length - 1))}
                              style={{ width: "100%", marginTop: 14 }} />
            ) : (
              <div data-testid="news-radio-text-only"
                   style={{ display: "flex", alignItems: "center", gap: 8,
                            background: "rgba(245,158,11,0.08)",
                            color: "#f59e0b", padding: "8px 12px",
                            borderRadius: 8, marginTop: 14, fontSize: 12 }}>
                <Volume2 size={14} /> Text mode — tap Next when you&apos;ve finished reading.
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button data-testid="news-radio-prev"
                    disabled={idx === 0}
                    onClick={() => setIdx(i => Math.max(0, i - 1))}
                    style={{ flex: 1, background: "rgba(255,255,255,0.05)",
                             color: "#fff", border: "1px solid rgba(255,255,255,0.1)",
                             padding: "10px 14px", borderRadius: 8,
                             cursor: idx === 0 ? "not-allowed" : "pointer",
                             opacity: idx === 0 ? 0.4 : 1 }}>
              ← Previous
            </button>
            <button data-testid="news-radio-next"
                    disabled={idx >= items.length - 1}
                    onClick={() => setIdx(i => Math.min(items.length - 1, i + 1))}
                    style={{ flex: 1, background: "#00d9ff", color: "#0b0b0b",
                             border: "none", padding: "10px 14px",
                             borderRadius: 8, fontWeight: 600,
                             cursor: idx >= items.length - 1 ? "not-allowed" : "pointer",
                             opacity: idx >= items.length - 1 ? 0.4 : 1 }}>
              Next →
            </button>
          </div>

          <div style={{ marginTop: 20, color: "#9aa3af", fontSize: 12 }}>
            Up next:
            <ul style={{ marginTop: 8, paddingLeft: 18 }}>
              {items.slice(idx + 1, idx + 4).map((it, i) => (
                <li key={it.news_id} data-testid={`news-radio-upnext-${i}`}
                    style={{ marginBottom: 4, display: "flex",
                             alignItems: "center", gap: 6 }}>
                  {it.audio_url && (
                    <Volume2 size={12} style={{ color: "#00d9ff", flexShrink: 0 }} />
                  )}
                  <span>{it.title}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
