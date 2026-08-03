/**
 * Phase 39 Session 2 — Listener-facing Persona Library + AI RJ Chat.
 *
 * Route: /personas (mounted in App.js).  Listener bearer required.
 *
 * Renders the 10 launch personas as cards. Each card shows the archetype,
 * description, language pills, daypart pills, a 🎧 button to play the
 * 8-second sample clip, and a "Select as my RJ" button. The currently
 * selected persona is ringed and badged.
 *
 * Clicking "Chat" on any card opens a push-to-talk modal that hits
 * POST /api/personas/chat — text in → text + audio out, last 5 turns
 * retained per modal session.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle2, Headphones, MessageSquare, X, Send,
                  Loader2, Sparkles, Sliders, Lock } from "lucide-react";
// Phase 42-E2.2 — Universal share on each persona card.
import ShareButton from "@/components/ShareButton";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Per-archetype accent colors (Phase 39 design palette).
const ACCENT_BY_DAYPART = {
  early_morning:  "#f59e0b",  morning_drive: "#f59e0b",
  lunch:                "#10b981",  afternoon:        "#ea580c",
  evening_drive: "#ea580c",  nightlife:        "#6366f1",
  late_night:      "#6366f1",  weekend:          "#ec4899",
  all_day:            "#3b82f6",  evening:            "#8b5cf6",
};


function pickAccent(persona) {
  const dp = (persona.daypart_affinity || [])[0] || "all_day";
  return ACCENT_BY_DAYPART[dp] || "#3b82f6";
}


export default function PersonaLibrary() {
  const [personas, setPersonas]              = useState([]);
  const [loading, setLoading]                  = useState(true);
  const [selectedId, setSelectedId]      = useState(null);
  const [busy, setBusy]                            = useState(null); // persona_id being acted on
  const [chatOpen, setChatOpen]              = useState(null); // persona obj or null
  const samplePlayerRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const [lib, me] = await Promise.all([
          axios.get(`${API}/personas/library`,
                              { withCredentials: true }),
          axios.get(`${API}/personas/me`,
                              { withCredentials: true }),
        ]);
        setPersonas(lib.data?.personas || []);
        setSelectedId(me.data?.selected_persona_id || null);
      } catch (e) {
        toast.error("Couldn't load personas — please try again.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const playSample = (persona) => {
    if (!persona.sample_clip_url) {
      toast.error("Sample not ready yet for this persona.");
      return;
    }
    if (samplePlayerRef.current) {
      samplePlayerRef.current.pause();
      samplePlayerRef.current = null;
    }
    const audio = new Audio(persona.sample_clip_url);
    samplePlayerRef.current = audio;
    audio.play().catch((e) => toast.error("Couldn't play sample."));
  };

  const select = async (persona) => {
    setBusy(persona.persona_id);
    try {
      await axios.post(`${API}/personas/select`,
                                      { persona_id: persona.persona_id },
                                      { withCredentials: true });
      setSelectedId(persona.persona_id);
      toast.success(`${persona.display_name} is now your AI RJ.`);
    } catch (e) {
      toast.error(e.response?.data?.detail?.code === "persona_unavailable"
                              ? "That persona isn't available right now."
                              : "Couldn't update your persona.");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div data-testid="persona-library-loading"
                  style={{ padding: 40, textAlign: "center", color: "#9aa3af" }}>
        <Loader2 size={28} className="animate-spin" />
        <div style={{ marginTop: 8 }}>Loading your AI RJ lineup…</div>
      </div>
    );
  }

  return (
    <div data-testid="persona-library-page"
            style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px" }}>
      <header style={{ marginBottom: 24 }}>
        <h1 data-testid="persona-library-title"
                style={{ fontSize: 28, fontWeight: 700, color: "#fff",
                              marginBottom: 6,
                              display: "flex", alignItems: "center", gap: 10 }}>
          <Sparkles size={24} color="#f59e0b" />
          Choose Your AI RJ
        </h1>
        <p style={{ color: "#9aa3af", fontSize: 14, margin: 0 }}>
          Pick a personality.  They'll intro your songs, banter, and
          chat with you in the studio.  You can switch any time.
        </p>
      </header>

      <PersonaSliders />

      <div data-testid="persona-grid"
              style={{ display: "grid", gap: 16,
                          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
        {personas.map((p) => {
          const accent      = pickAccent(p);
          const isSelected = selectedId === p.persona_id;
          return (
            <div key={p.persona_id}
                    data-testid={`persona-card-${p.persona_id}`}
                    style={{
                      background: "#1f2937",
                      borderRadius: 12,
                      padding: 16,
                      border: isSelected
                        ? `2px solid ${accent}`
                        : "1px solid rgba(255,255,255,0.06)",
                      position: "relative",
                    }}>
              {isSelected && (
                <span data-testid={`persona-selected-badge-${p.persona_id}`}
                            style={{
                              position: "absolute", top: 12, right: 12,
                              background: accent, color: "#0b0b0b",
                              padding: "3px 8px", borderRadius: 6,
                              fontSize: 11, fontWeight: 600,
                              display: "inline-flex", alignItems: "center", gap: 3
                            }}>
                  <CheckCircle2 size={12} /> Selected
                </span>
              )}
              <div style={{ color: accent, fontSize: 11,
                                      letterSpacing: 1, marginBottom: 4 }}>
                {(p.archetype || "").replace(/_/g, " ").toUpperCase()}
              </div>
              <h3 style={{ color: "#fff", fontSize: 18, fontWeight: 700,
                                      margin: "0 0 8px" }}>
                {p.display_name}
              </h3>
              <p style={{ color: "#d1d5db", fontSize: 13,
                                  lineHeight: 1.4, margin: "0 0 12px",
                                  minHeight: 56 }}>
                {p.description}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6,
                                      marginBottom: 14 }}>
                {(p.language_mix || []).map((l) => (
                  <span key={l} style={{
                    fontSize: 11, color: "#9aa3af",
                    background: "rgba(255,255,255,0.04)",
                    padding: "2px 8px", borderRadius: 10,
                  }}>{l}</span>
                ))}
                {(p.daypart_affinity || []).slice(0, 2).map((d) => (
                  <span key={d} style={{
                    fontSize: 11, color: accent,
                    background: `${accent}1A`,
                    padding: "2px 8px", borderRadius: 10,
                  }}>{d.replace(/_/g, " ")}</span>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button
                  data-testid={`persona-sample-btn-${p.persona_id}`}
                  onClick={() => playSample(p)}
                  style={btnStyle("ghost", accent)}>
                  <Headphones size={14} /> Sample
                </button>
                <button
                  data-testid={`persona-chat-btn-${p.persona_id}`}
                  onClick={() => setChatOpen(p)}
                  style={btnStyle("ghost", accent)}>
                  <MessageSquare size={14} /> Chat
                </button>
                {/* Phase 42-E2.2 — share this persona */}
                <ShareButton
                  compact
                  featureType="persona"
                  contentId={p.persona_id}
                  title={`${p.display_name} on BigFM`}
                  text={`Meet ${p.display_name} — ${p.archetype?.replace(/_/g, " ")} on BigFM. Tap to chat:`} />
                <button
                  data-testid={`persona-select-btn-${p.persona_id}`}
                  onClick={() => select(p)}
                  disabled={busy === p.persona_id || isSelected}
                  style={{ ...btnStyle("primary", accent),
                                  opacity: (busy === p.persona_id || isSelected)
                                                ? 0.6 : 1,
                                  marginLeft: "auto" }}>
                  {busy === p.persona_id ? "..."
                      : isSelected ? "Selected" : "Select"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {chatOpen && (
        <PersonaChatModal persona={chatOpen}
                                          onClose={() => setChatOpen(null)} />
      )}
    </div>
  );
}


function PersonaSliders() {
  const [trial, setTrial] = React.useState(null);
  const [values, setValues] = React.useState({ humor: 5, energy: 5, slang: 5 });
  // Phase 42-D2 — trial endpoint now returns a structured `state`
  // (started / already_active / already_consumed / upgrade_required).
  // We render the 3 button states from that field exclusively — no
  // more catch-block fishing for `detail.code`.
  const [busy, setBusy] = React.useState(false);
  const debounce = React.useRef(null);
  React.useEffect(() => {
    (async () => {
      try {
        const t = await axios.get(`${API}/billing/trial_status`,
                                                          { withCredentials: true });
        setTrial(t.data);
        const m = await axios.get(`${API}/personas/me`,
                                                          { withCredentials: true });
        // Settings may be on user profile, fetch trial_status carries premium info.
        const ps = m.data?.persona_settings
                            || t.data?.persona_settings;
        if (ps) setValues({ humor: ps.humor ?? 5,
                                                energy: ps.energy ?? 5,
                                                slang: ps.slang ?? 5 });
      } catch (e) { /* silent */ }
    })();
  }, []);
  const enabled = trial?.is_premium_or_trial === true;
  const onChange = (k, v) => {
    setValues((cur) => ({ ...cur, [k]: Number(v) }));
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      try {
        await axios.post(`${API}/personas/settings`,
                                          { ...values, [k]: Number(v) },
                                          { withCredentials: true });
        toast.success("Saved");
      } catch (e) {
        if (e.response?.status === 403) toast.error("Premium required");
      }
    }, 500);
  };
  const startTrial = async () => {
    if (busy) return;
    setBusy(true);
    try {
      // Phase 42-D2 — Always-200 structured response.
      const r = await axios.post(`${API}/billing/start_premium_trial`, {},
                                                          { withCredentials: true });
      const data = r.data || {};
      const state = data.state;
      if (state === "started") {
        toast.success("7-day free trial started — sliders unlocked!");
      } else if (state === "already_active") {
        toast.success("Trial already active — sliders unlocked.");
      } else if (state === "already_consumed") {
        toast.message("Your free trial has been used. Upgrade to Premium to keep customising.");
      } else if (state === "upgrade_required") {
        toast.message("Premium upgrade required to unlock these controls.");
      }
      // Re-pull canonical entitlement.
      const t = await axios.get(`${API}/billing/trial_status`,
                                                          { withCredentials: true });
      setTrial({ ...t.data, last_state: state });
    } catch (e) {
      toast.error("Could not check trial state. Please try again.");
    } finally {
      setBusy(false);
    }
  };
  // Phase 42-D2 — decide which CTA to render under the overlay.
  // - upgrade_required (free, eligible) → "Start Free Trial"
  // - already_consumed                            → "Upgrade to Premium" → /pricing
  // - already_active / started               → no overlay (enabled=true above)
  // - unknown                                              → default "Start Free Trial"
  const trialState = trial?.last_state;
  const subStatus = (trial?.subscription_status || "").toLowerCase();
  const showConsumed = trialState === "already_consumed"
                                                || (subStatus === "free" && trial?.trial_started_at);
  const labelFor = (v) => v <= 2 ? "Subtle" : v >= 8 ? "Wild" : "Balanced";
  const sliders = [
    { key: "humor",  label: "Humor"  },
    { key: "energy", label: "Energy" },
    { key: "slang",  label: "Slang"  },
  ];
  return (
    <section data-testid="persona-sliders-section"
                    data-entitlement={enabled ? "enabled" : showConsumed ? "consumed" : "trial_eligible"}
                    style={{ background: "#1f2937", borderRadius: 12,
                                padding: 16, marginBottom: 18,
                                position: "relative" }}>
      <h2 style={{ color: "#fff", fontSize: 14, margin: "0 0 12px",
                              display: "flex", alignItems: "center", gap: 6 }}>
        <Sliders size={14} /> Customize your AI RJ
      </h2>
      {sliders.map((s) => (
        <div key={s.key} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between",
                                  color: "#d1d5db", fontSize: 12, marginBottom: 4 }}>
            <span>{s.label}</span>
            <span style={{ color: enabled ? "#10b981" : "#6b7280",
                                          fontFamily: "monospace" }}>
              {values[s.key]} — {labelFor(values[s.key])}
            </span>
          </div>
          <input type="range" min={0} max={10} step={1}
                      data-testid={`persona-slider-${s.key}`}
                      value={values[s.key]} disabled={!enabled}
                      onChange={(e) => onChange(s.key, e.target.value)}
                      style={{ width: "100%", accentColor: "#10b981",
                                  opacity: enabled ? 1 : 0.4 }} />
        </div>
      ))}
      {!enabled && (
        <div data-testid="persona-sliders-trial-cta"
                data-cta-mode={showConsumed ? "consumed" : "trial"}
                style={{ position: "absolute", inset: 0,
                            background: "rgba(15,23,42,0.85)",
                            display: "flex", flexDirection: "column",
                            alignItems: "center", justifyContent: "center",
                            borderRadius: 12, gap: 8 }}>
          <Lock size={20} color="#f59e0b" />
          <div style={{ color: "#fff", fontWeight: 700 }}>
            {showConsumed
              ? "Trial already used"
              : "✨ Premium — start 7-day free trial"}
          </div>
          {showConsumed ? (
            <a href="/pricing"
                  data-testid="persona-sliders-upgrade-link"
                  style={{ background: "#f59e0b", color: "#0b0b0b",
                              border: "none", padding: "8px 16px",
                              borderRadius: 6, fontWeight: 600,
                              cursor: "pointer", textDecoration: "none" }}>
              Upgrade to Premium
            </a>
          ) : (
            <button data-testid="persona-sliders-start-trial"
                            onClick={startTrial}
                            disabled={busy}
                            style={{ background: "#10b981", color: "#0b0b0b",
                                        border: "none", padding: "8px 16px",
                                        borderRadius: 6, fontWeight: 600,
                                        cursor: "pointer",
                                        opacity: busy ? 0.6 : 1 }}>
              {busy ? "Checking…" : "Start Free Trial"}
            </button>
          )}
        </div>
      )}
      {enabled && trial?.trial_ends_at && (
        <div data-testid="persona-sliders-trial-active-badge"
                  style={{ marginTop: 8, fontSize: 11,
                              color: "#10b981", fontFamily: "monospace" }}>
          ✓ Trial active until {new Date(trial.trial_ends_at).toLocaleDateString()}
        </div>
      )}
    </section>
  );
}


function btnStyle(kind, accent) {
  const base = {
    fontSize: 13, padding: "6px 10px", borderRadius: 6,
    display: "inline-flex", alignItems: "center", gap: 4,
    border: "1px solid rgba(255,255,255,0.08)",
    cursor: "pointer",
    transition: "background 120ms ease",
  };
  if (kind === "primary") {
    return { ...base, background: accent, color: "#0b0b0b",
                  fontWeight: 600, border: `1px solid ${accent}` };
  }
  return { ...base, background: "transparent", color: "#d1d5db" };
}


function PersonaChatModal({ persona, onClose }) {
  const [input, setInput]          = useState("");
  const [turns, setTurns]          = useState([]);  // [{role, text, audio_url?}]
  const [busy, setBusy]              = useState(false);
  const audioRef = useRef(null);
  const accent = pickAccent(persona);

  const send = async () => {
    if (!input.trim() || busy) return;
    const listenerLine = { role: "listener", text: input.trim() };
    setTurns((prev) => [...prev, listenerLine].slice(-5));
    setBusy(true);
    setInput("");
    try {
      const r = await axios.post(`${API}/personas/chat`,
                                              { persona_id: persona.persona_id,
                                                  listener_input_text: listenerLine.text },
                                              { withCredentials: true });
      const reply = {
        role: "persona",
        text: r.data.response_text,
        audio_url: r.data.response_audio_url,
      };
      setTurns((prev) => [...prev, reply].slice(-5));
      if (reply.audio_url) {
        if (audioRef.current) audioRef.current.pause();
        const a = new Audio(reply.audio_url);
        audioRef.current = a;
        a.play().catch(() => {});
      }
    } catch (e) {
      toast.error("Chat failed — try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="persona-chat-modal-backdrop"
            onClick={onClose}
            style={{ position: "fixed", inset: 0,
                        background: "rgba(0,0,0,0.72)", zIndex: 1100,
                        display: "flex", alignItems: "center",
                        justifyContent: "center", padding: 16 }}>
      <div data-testid="persona-chat-modal"
              onClick={(e) => e.stopPropagation()}
              style={{ background: "#111827", borderRadius: 12,
                          padding: 20, maxWidth: 520, width: "100%",
                          border: `1px solid ${accent}`,
                          maxHeight: "85vh", display: "flex",
                          flexDirection: "column" }}>
        <header style={{ display: "flex", alignItems: "center",
                                  justifyContent: "space-between",
                                  marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: accent, letterSpacing: 1,
                                      textTransform: "uppercase" }}>
              Chat with
            </div>
            <h2 style={{ color: "#fff", fontSize: 18, fontWeight: 700,
                                    margin: 0 }}>{persona.display_name}</h2>
          </div>
          <button data-testid="persona-chat-close"
                          onClick={onClose}
                          style={{ background: "transparent",
                                      border: "none", color: "#9aa3af",
                                      cursor: "pointer" }}>
            <X size={20} />
          </button>
        </header>

        <div data-testid="persona-chat-turns"
                style={{ flex: 1, overflowY: "auto",
                            background: "#0b0b0b", borderRadius: 8,
                            padding: 12, marginBottom: 14, minHeight: 220 }}>
          {turns.length === 0 && (
            <div style={{ color: "#6b7280", fontSize: 13,
                                    fontStyle: "italic" }}>
              Say hi, ask about the music, or ask for a song mood.
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i}
                    data-testid={`persona-chat-turn-${i}`}
                    style={{ marginBottom: 10,
                                textAlign: t.role === "listener" ? "right" : "left" }}>
              <div style={{
                display: "inline-block",
                background: t.role === "listener"
                  ? "rgba(255,255,255,0.08)"
                  : `${accent}1A`,
                color: t.role === "listener" ? "#d1d5db" : "#fff",
                padding: "8px 12px", borderRadius: 8,
                maxWidth: "80%", fontSize: 13, lineHeight: 1.4,
                whiteSpace: "pre-wrap",
              }}>{t.text}</div>
            </div>
          ))}
          {busy && (
            <div data-testid="persona-chat-thinking"
                    style={{ color: accent, fontSize: 12,
                                marginTop: 6, fontStyle: "italic" }}>
              {persona.display_name} is thinking…
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <input data-testid="persona-chat-input"
                      type="text" value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && send()}
                      placeholder={`Ask ${persona.display_name}…`}
                      disabled={busy}
                      style={{ flex: 1, padding: "8px 12px",
                                  borderRadius: 6, background: "#1f2937",
                                  border: "1px solid rgba(255,255,255,0.08)",
                                  color: "#fff", fontSize: 14 }} />
          <button data-testid="persona-chat-send"
                          onClick={send} disabled={busy || !input.trim()}
                          style={{ ...btnStyle("primary", accent),
                                      opacity: (busy || !input.trim()) ? 0.5 : 1 }}>
            <Send size={14} /> Send
          </button>
        </div>
      </div>
    </div>
  );
}
