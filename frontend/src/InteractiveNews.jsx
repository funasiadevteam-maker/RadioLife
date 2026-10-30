/** FUUSIC Interactive News — Phase 1 pilot + program modes.
 *  "Your News. Your Questions. Your AI Anchor."
 *
 *  Radio-first: pick a program mode (Morning Briefing, News in 2 Minutes,
 *  Continuous, Deep Dive, Local, Global), press Play and the verified news
 *  program runs end to end. Tap "Talk to Fun AI" to ask the Grok voice anchor
 *  follow-ups — the anchor follows the same mode, the program ducks while you
 *  talk and resumes after. Falls back to the plain program when voice is off.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Radio, ArrowLeft, Play, Pause, Mic, Volume2, Megaphone, ExternalLink, Search, Bookmark, BookmarkCheck, X } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useThemeStore } from "@/theme/useTheme";
import TalkToFunAI from "@/FunAI/TalkToFunAI";
import RjPersonalityPicker from "@/FunAI/RjPersonalityPicker";
import FunAiMemory from "@/FunAI/FunAiMemory";

const STATIC_BASE = API.replace(/\/api$/, "");

const FALLBACK_MODES = [
  { id: "morning_briefing", label: "Morning Briefing", blurb: "~5–10 min top stories" },
  { id: "news_in_2", label: "News in 2 Minutes", blurb: "Fast headline rundown" },
  { id: "continuous", label: "Continuous News", blurb: "Rolling, non-stop news" },
  { id: "deep_dive", label: "Deep Dive", blurb: "One topic, in depth", topic_required: true },
  { id: "local", label: "Local News", blurb: "News for your market" },
  { id: "global", label: "Global News", blurb: "World & international" },
];

export default function InteractiveNews() {
  const { user } = useAuth();
  const theme = useThemeStore((s) => s.theme);
  const dark = theme !== "light";

  const [modes, setModes] = useState(FALLBACK_MODES);
  const [mode, setMode] = useState("morning_briefing");
  const [appliedTopic, setAppliedTopic] = useState("");
  const [topicInput, setTopicInput] = useState("");

  const [program, setProgram] = useState([]);
  const [modeLabel, setModeLabel] = useState("Morning Briefing");
  const [anchorHint, setAnchorHint] = useState("");
  const [sponsor, setSponsor] = useState(null);
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [talkOpen, setTalkOpen] = useState(false);
  const [follows, setFollows] = useState([]);

  // Sponsor breaks — seamless, disclosed ad spots woven into the program.
  const [breaks, setBreaks] = useState([]);
  const [activeBreak, setActiveBreak] = useState(null);
  const playedBreaksRef = useRef(new Set());
  const afterBreakRef = useRef(null);

  const audioRef = useRef(null);
  const loadIdRef = useRef(0);

  // Mode list from backend (keeps a single source of truth).
  useEffect(() => {
    axios.get(`${API}/fun-ai/config`, { withCredentials: true })
      .then((r) => { if (r.data?.modes?.length) setModes(r.data.modes); })
      .catch(() => {});
  }, []);

  const load = useCallback((m, topic) => {
    const myId = ++loadIdRef.current;
    setLoading(true); setEmpty(null);
    let tries = 0;
    const run = async () => {
      try {
        const r = await axios.get(`${API}/fun-ai/news/briefing`,
          { params: { mode: m, topic: topic || undefined }, withCredentials: true });
        if (myId !== loadIdRef.current) return; // a newer load superseded this one
        setSponsor(r.data?.sponsor || null);
        setVoiceAvailable(!!r.data?.voice_available);
        setModeLabel(r.data?.mode_label || m);
        setAnchorHint(r.data?.anchor_hint || "");
        if (r.data?.topic && m === "deep_dive") setTopicInput(r.data.topic);
        if (r.data?.program?.length) {
          setProgram(r.data.program); setIdx(0); setPlaying(false);
          setBreaks(r.data?.breaks || []);
          playedBreaksRef.current = new Set();
          afterBreakRef.current = null;
          setActiveBreak(null);
          try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_e) { /* noop */ }
          setEmpty(null); setLoading(false); return;
        }
        setProgram([]);
        if (tries === 0) {
          axios.post(`${API}/news_radio/trigger-batch`, null,
                     { params: { top_n: 8 }, withCredentials: true }).catch(() => {});
        }
        tries += 1;
        if (tries <= 6) {
          setEmpty("Preparing today's news program — this takes a few seconds…");
          setLoading(false);
          setTimeout(() => { if (myId === loadIdRef.current) run(); }, 5000);
        } else {
          setEmpty(r.data?.retry_hint || "No news is available right now.");
          setLoading(false);
        }
      } catch (e) {
        if (myId === loadIdRef.current) { setEmpty("Could not load the news program."); setLoading(false); }
      }
    };
    run();
  }, []);

  useEffect(() => { load(mode, appliedTopic); }, [mode, appliedTopic, load]);

  const current = program[idx];
  const isDeepDive = mode === "deep_dive";

  const loadFollows = useCallback(() => {
    axios.get(`${API}/fun-ai/follows`, { withCredentials: true })
      .then((r) => setFollows(r.data?.follows || [])).catch(() => {});
  }, []);
  useEffect(() => { if (user) loadFollows(); }, [user, loadFollows]);

  const norm = (s) => (s || "").trim().toLowerCase();
  const currentFollow = current && follows.find((f) => norm(f.topic) === norm(current.title));

  const toggleFollow = async () => {
    if (!current) return;
    if (currentFollow) {
      await axios.delete(`${API}/fun-ai/follows/${currentFollow.id}`, { withCredentials: true }).catch(() => {});
    } else {
      await axios.post(`${API}/fun-ai/follows`,
        { topic: current.title, title: current.title }, { withCredentials: true }).catch(() => {});
    }
    loadFollows();
  };

  const removeFollow = async (id) => {
    await axios.delete(`${API}/fun-ai/follows/${id}`, { withCredentials: true }).catch(() => {});
    loadFollows();
  };

  const openFollow = (topic) => { setTopicInput(topic); setMode("deep_dive"); setAppliedTopic(topic); };

  // Duck the program while the voice panel is open; resume after.
  useEffect(() => {
    const a = audioRef.current;
    if (talkOpen) { try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_e) { /* noop */ } }
    if (!a) return;
    if (talkOpen) a.pause();
    else if (playing && !activeBreak) a.play().catch(() => {});
  }, [talkOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const a = audioRef.current;
    if (!a || !current) return;
    if (playing && !talkOpen && !activeBreak) a.play().catch(() => {});
    else a.pause();
  }, [playing, idx, current, talkOpen, activeBreak]);

  const palette = useMemo(() => dark ? {
    fg: "#e8eef6", sub: "#9aa3af", card: "#141b26",
    line: "rgba(0,217,255,0.22)", soft: "rgba(0,217,255,0.06)", chip: "#0f1620",
  } : {
    fg: "#0b1220", sub: "#64748b", card: "#ffffff",
    line: "rgba(2,132,199,0.22)", soft: "rgba(2,132,199,0.05)", chip: "#f1f5f9",
  }, [dark]);
  const accent = "#00b8d9";

  // ── Sponsor break orchestration ──────────────────────────────────────
  const findBreak = useCallback((pred) =>
    breaks.find((b) => !playedBreaksRef.current.has(b.id) && pred(b)), [breaks]);

  const startBreak = useCallback((b, after) => {
    playedBreaksRef.current.add(b.id);
    afterBreakRef.current = after || null;
    setActiveBreak(b);
    axios.post(`${API}/fun-ai/news/break-event`,
      { break_id: String(b.id), kind: "impression", placement: b.placement,
        sponsored_read_id: b.sponsored_read_id || undefined },
      { withCredentials: true }).catch(() => {});
  }, []);

  const finishBreak = useCallback(() => {
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_e) { /* noop */ }
    const after = afterBreakRef.current;
    afterBreakRef.current = null;
    setActiveBreak(null);
    if (after) after();
  }, []);

  // Read text-only sponsor breaks aloud (the RJ/browser voice); paid spots play
  // their recorded audio via the <audio> element rendered in the break card.
  useEffect(() => {
    if (!activeBreak || activeBreak.audio_url) return;
    let done = false;
    let fallback = null;
    const text = activeBreak.text || "";
    const end = () => { if (!done) { done = true; finishBreak(); } };
    try {
      const synth = window.speechSynthesis;
      if (synth && text) {
        synth.cancel();
        const u = new SpeechSynthesisUtterance(text);
        u.onend = end; u.onerror = end;
        synth.speak(u);
      }
    } catch (_e) { /* fall through to timer */ }
    const words = Math.max(1, text.split(/\s+/).filter(Boolean).length);
    const secs = Math.min(30, Math.max(5, Math.round(words / 2.5) + 1));
    fallback = setTimeout(end, secs * 1000);
    return () => { done = true; if (fallback) clearTimeout(fallback); };
  }, [activeBreak, finishBreak]);

  const handleSegmentEnded = useCallback(() => {
    if (activeBreak) { finishBreak(); return; }
    const k = idx;
    const isLast = k >= program.length - 1;
    const advance = () => setIdx(Math.min(k + 1, program.length - 1));
    if (!isLast) {
      const mid = findBreak((b) => b.placement === "mid" && b.after_index === k);
      if (mid) { startBreak(mid, advance); return; }
      advance(); return;
    }
    const closing = findBreak((b) => b.placement === "closing");
    if (closing) { startBreak(closing, () => setPlaying(false)); return; }
    setPlaying(false);
  }, [activeBreak, finishBreak, idx, program.length, findBreak, startBreak]);

  const togglePlay = useCallback(() => {
    if (activeBreak) { setPlaying((p) => !p); return; }
    if (playing) { setPlaying(false); return; }
    const opening = idx === 0 ? findBreak((b) => b.placement === "opening") : null;
    if (opening) { startBreak(opening, () => setPlaying(true)); return; }
    setPlaying(true);
  }, [activeBreak, playing, idx, findBreak, startBreak]);

  const selectMode = (id) => {
    if (id === mode) return;
    setMode(id);
    if (id !== "deep_dive") { setAppliedTopic(""); }
  };

  const runDeepDive = () => setAppliedTopic(topicInput.trim());

  return (
    <div data-testid="interactive-news-page"
         style={{ maxWidth: 760, margin: "0 auto", padding: 24, color: palette.fg }}>
      <Link to="/radio/news" data-testid="interactive-news-back"
            style={{ display: "inline-flex", alignItems: "center", gap: 6,
                     color: palette.sub, textDecoration: "none", fontSize: 13, marginBottom: 16 }}>
        <ArrowLeft size={14} /> Back to News Radio
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <div style={{ width: 42, height: 42, borderRadius: 12, display: "grid", placeItems: "center",
                      background: palette.soft, border: `1px solid ${palette.line}` }}>
          <Radio size={22} color={accent} />
        </div>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, lineHeight: 1.1 }}>
            FUUSIC Interactive News
          </h1>
          <div style={{ fontSize: 13, color: palette.sub }}>
            Your News. Your Questions. Your AI Anchor.
          </div>
        </div>
      </div>

      {/* Program mode selector — single-row horizontal scroller */}
      <div data-testid="interactive-news-modes"
           style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 6, marginBottom: 6 }}>
        {modes.map((m) => {
          const on = m.id === mode;
          return (
            <button key={m.id} data-testid={`interactive-news-mode-${m.id}`}
                    onClick={() => selectMode(m.id)} title={m.blurb}
                    style={{ flexShrink: 0, whiteSpace: "nowrap", cursor: "pointer",
                             padding: "8px 14px", borderRadius: 999, fontSize: 13, fontWeight: 700,
                             border: `1px solid ${on ? accent : palette.line}`,
                             background: on ? accent : palette.chip,
                             color: on ? "#04121a" : palette.fg }}>
              {m.label}
            </button>
          );
        })}
      </div>
      {anchorHint && (
        <div style={{ fontSize: 12, color: palette.sub, marginBottom: 14, lineHeight: 1.5 }}>
          {anchorHint}
        </div>
      )}

      {/* Deep Dive topic */}
      {isDeepDive && (
        <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
          <input data-testid="interactive-news-deepdive-topic"
                 value={topicInput} onChange={(e) => setTopicInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") runDeepDive(); }}
                 placeholder="Topic to go deep on (e.g. AI data centers)"
                 style={{ flex: 1, padding: "10px 12px", borderRadius: 10, fontSize: 14,
                          border: `1px solid ${palette.line}`, background: palette.chip,
                          color: palette.fg }} />
          <button data-testid="interactive-news-deepdive-go" onClick={runDeepDive}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6, background: accent,
                           color: "#04121a", border: "none", borderRadius: 10, padding: "10px 16px",
                           fontWeight: 800, cursor: "pointer" }}>
            <Search size={15} /> Go
          </button>
        </div>
      )}

      {/* Sponsor acknowledgement — clearly disclosed, separate from news */}
      {sponsor?.enabled && sponsor?.sponsor_name && (
        <div data-testid="interactive-news-sponsor"
             style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14,
                      background: palette.soft, border: `1px dashed ${palette.line}`,
                      color: palette.fg, padding: "10px 14px", borderRadius: 10, fontSize: 13 }}>
          <Megaphone size={16} color={accent} />
          <span>
            <b style={{ textTransform: "uppercase", fontSize: 10, letterSpacing: 1,
                        color: palette.sub, marginRight: 6 }}>Sponsored</b>
            {sponsor.opening_line || `FUUSIC Interactive News is sponsored by ${sponsor.sponsor_name}.`}
          </span>
        </div>
      )}

      {/* Following — saved stories Fun AI opens with next time */}
      {follows.length > 0 && (
        <div data-testid="interactive-news-following" style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
                        color: palette.sub, marginBottom: 6 }}>Following</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {follows.map((f) => (
              <span key={f.id} data-testid={`follow-chip-${f.id}`}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6,
                             background: palette.chip, border: `1px solid ${palette.line}`,
                             borderRadius: 999, padding: "6px 10px", fontSize: 12 }}>
                <button onClick={() => openFollow(f.topic)} title="Deep dive this story"
                        style={{ background: "transparent", border: "none", color: palette.fg,
                                 cursor: "pointer", padding: 0, fontSize: 12, maxWidth: 220,
                                 overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {f.title}
                </button>
                <button data-testid={`follow-remove-${f.id}`} onClick={() => removeFollow(f.id)}
                        aria-label="Unfollow"
                        style={{ background: "transparent", border: "none", color: palette.sub,
                                 cursor: "pointer", padding: 0, display: "inline-flex" }}>
                  <X size={13} />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Player */}
      <div style={{ background: palette.card, borderRadius: 16,
                    border: `1px solid ${palette.line}`, padding: 20 }}>
        {loading && !program.length ? (
          <div style={{ color: palette.sub, padding: 16 }}>Loading {modeLabel}…</div>
        ) : empty ? (
          <div data-testid="interactive-news-empty"
               style={{ color: "#f59e0b", background: "rgba(245,158,11,0.10)",
                        border: "1px dashed #f59e0b", padding: 16, borderRadius: 10 }}>
            {empty}
          </div>
        ) : activeBreak ? (
          <div data-testid="interactive-news-break" data-break-kind={activeBreak.kind}
               style={{ padding: 4 }}>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1.5,
                          color: accent, fontWeight: 800, marginBottom: 8 }}>
              <Megaphone size={12} style={{ display: "inline", marginRight: 6, verticalAlign: "-1px" }} />
              {activeBreak.label || "Sponsored"}
            </div>
            <div style={{ fontSize: 12, color: palette.sub, marginBottom: 10 }}>
              {activeBreak.disclosure || "A word from our sponsor"}
            </div>
            <p data-testid="interactive-news-break-text"
               style={{ fontSize: 16, lineHeight: 1.6, color: palette.fg, margin: "0 0 16px" }}>
              {activeBreak.text}
            </p>
            {activeBreak.audio_url && (
              <audio data-testid="interactive-news-break-audio" autoPlay
                     src={`${STATIC_BASE}${activeBreak.audio_url}`}
                     onEnded={finishBreak} onError={finishBreak} style={{ display: "none" }} />
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, display: "inline-flex", alignItems: "center", gap: 8,
                            fontSize: 12, color: palette.sub }}>
                <Volume2 size={14} color={accent} /> Sponsor break — your news resumes right after.
              </div>
              <button data-testid="interactive-news-break-skip" onClick={finishBreak}
                      style={{ background: palette.soft, color: palette.fg,
                               border: `1px solid ${palette.line}`, borderRadius: 10,
                               padding: "9px 16px", fontWeight: 700, cursor: "pointer" }}>
                Skip →
              </button>
            </div>
          </div>
        ) : current ? (
          <>
            <div style={{ fontSize: 11, color: accent, fontFamily: "monospace",
                          letterSpacing: 1, marginBottom: 8 }}>
              {modeLabel.toUpperCase()} · {idx + 1} of {program.length}
            </div>
            <h2 data-testid="interactive-news-segment"
                style={{ fontSize: 18, fontWeight: 700, margin: "0 0 10px", lineHeight: 1.4 }}>
              {current.title}
            </h2>
            <p style={{ color: palette.sub, fontSize: 14, lineHeight: 1.7, margin: "0 0 12px" }}>
              {current.summary}
            </p>
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12,
                          fontFamily: "monospace", color: palette.sub, marginBottom: 12, flexWrap: "wrap" }}>
              <span>{current.source_name}</span>
              <span>~{current.duration_estimate_sec}s</span>
              {current.url && (
                <a href={current.url} target="_blank" rel="noreferrer"
                   data-testid="interactive-news-source"
                   style={{ display: "inline-flex", alignItems: "center", gap: 4,
                            color: accent, textDecoration: "none" }}>
                  <ExternalLink size={12} /> View source
                </a>
              )}
            </div>

            {current.audio_url ? (
              <audio ref={audioRef} data-testid="interactive-news-audio"
                     src={`${STATIC_BASE}${current.audio_url}`}
                     onEnded={handleSegmentEnded} controls style={{ width: "100%" }} />
            ) : (
              <div data-testid="interactive-news-text-only"
                   style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12,
                            color: "#f59e0b", background: "rgba(245,158,11,0.08)",
                            padding: "8px 12px", borderRadius: 8 }}>
                <Volume2 size={14} /> Text mode — use Next when you've finished reading.
              </div>
            )}

            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button data-testid="interactive-news-play"
                      onClick={togglePlay}
                      style={{ flex: 1, display: "inline-flex", alignItems: "center",
                               justifyContent: "center", gap: 8, background: accent,
                               color: "#04121a", border: "none", borderRadius: 10,
                               padding: "11px 14px", fontWeight: 800, cursor: "pointer" }}>
                {playing ? <Pause size={16} /> : <Play size={16} />}
                {playing ? "Pause" : "Play news"}
              </button>
              <button data-testid="interactive-news-next"
                      onClick={handleSegmentEnded} disabled={idx >= program.length - 1}
                      style={{ background: palette.soft, color: palette.fg,
                               border: `1px solid ${palette.line}`, borderRadius: 10,
                               padding: "11px 16px", fontWeight: 600,
                               cursor: idx >= program.length - 1 ? "not-allowed" : "pointer",
                               opacity: idx >= program.length - 1 ? 0.4 : 1 }}>
                Next →
              </button>
            </div>

            <button data-testid="interactive-news-follow" onClick={toggleFollow}
                    style={{ marginTop: 10, width: "100%", display: "inline-flex",
                             alignItems: "center", justifyContent: "center", gap: 8,
                             background: palette.soft,
                             color: currentFollow ? accent : palette.fg,
                             border: `1px solid ${currentFollow ? accent : palette.line}`,
                             borderRadius: 10, padding: "10px 14px", fontWeight: 700,
                             cursor: "pointer" }}>
              {currentFollow ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
              {currentFollow ? "Following this story" : "Follow this story"}
            </button>
          </>
        ) : null}
      </div>

      {/* Talk to Fun AI */}
      <div style={{ marginTop: 18 }}>
        {user && <FunAiMemory dark={dark} accent={accent} testIdPrefix="inews-memory" />}
        <RjPersonalityPicker dark={dark} accent={accent} testIdPrefix="inews-rj-personality" />
        {voiceAvailable ? (
          <button data-testid="interactive-news-talk-btn"
                  onClick={() => { if (!user) { window.location.href = "/login"; return; } setTalkOpen(true); }}
                  disabled={talkOpen}
                  style={{ width: "100%", display: "inline-flex", alignItems: "center",
                           justifyContent: "center", gap: 10, padding: "14px 18px",
                           borderRadius: 14, border: `1px solid ${palette.line}`,
                           background: "linear-gradient(90deg,#00b8d9,#7c5cff)",
                           color: "#fff", fontWeight: 800, fontSize: 15,
                           cursor: talkOpen ? "default" : "pointer", opacity: talkOpen ? 0.6 : 1 }}>
            <Mic size={18} /> Talk to Fun AI about {modeLabel}
          </button>
        ) : (
          <div data-testid="interactive-news-voice-unavailable"
               style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
                        borderRadius: 12, border: `1px dashed ${palette.line}`,
                        background: palette.soft, color: palette.sub, fontSize: 13 }}>
            <Mic size={16} /> Voice anchor is warming up — the news program still plays above.
          </div>
        )}
        {voiceAvailable && (
          <div style={{ fontSize: 11, color: palette.sub, textAlign: "center", marginTop: 8 }}>
            Microphone is used only while you're talking. Fun AI is an AI assistant.
          </div>
        )}
      </div>

      {talkOpen && (
        <TalkToFunAI dark={dark} mode={mode} topic={isDeepDive ? appliedTopic : undefined}
                     modeLabel={modeLabel} onFollow={loadFollows}
                     onClose={() => setTalkOpen(false)} onStatusChange={() => {}} />
      )}
    </div>
  );
}
