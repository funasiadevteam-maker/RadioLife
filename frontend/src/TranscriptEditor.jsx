/**
 * Phase 36b — Transcript editor + AI metadata panel.
 *
 * Route: /creator/episodes/:ep_id/edit
 *
 * Left:  utterance list with speaker labels + timestamps + per-utterance
 *          editable text. Speaker labels are renameable across all utterances.
 * Right: AI metadata panel — Title (+ 3 alternatives + Re-roll), Description,
 *          Show Notes, Chapters, SEO Keywords, Social Captions, Sponsor Reads.
 * Header: status banner ("AI is transcribing…" / "AI metadata generating…" /
 *          "Ready to publish"). MOCK-mode amber banner when AssemblyAI key absent.
 */
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { MagicClipsTab } from "@/MagicClipsTab";  // Phase 36d Turn 1
import { ShoppableCardsCreator } from "@/ShoppableCards";  // Phase 36d Turn 2
import { LightningSplitsEditor } from "@/LightningSplitsEditor";  // Phase 36d Turn 3

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmtTime = (ms) => {
  const s = Math.max(0, Math.floor((ms || 0) / 1000));
  const m = Math.floor(s / 60);
  const ss = s % 60;
  return `${m}:${String(ss).padStart(2, "0")}`;
};

export default function TranscriptEditor() {
  const { ep_id } = useParams();
  const [ep, setEp]                   = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [metadata, setMetadata]    = useState(null);
  const [mockMode, setMockMode]  = useState(false);
  const [busy, setBusy]               = useState("");
  const [tab, setTab]                  = useState("twitter");
  const [speakerRenames, setSpeakerRenames] = useState({});

  const refresh = useCallback(async () => {
    try {
      const e = await axios.get(`${API}/podcasts/episodes/${ep_id}`,
                                                {withCredentials: true});
      setEp(e.data);
    } catch (_) {}
    try {
      const t = await axios.get(`${API}/podcasts/episodes/${ep_id}/transcript`,
                                                {withCredentials: true});
      setTranscript(t.data);
    } catch (_) { setTranscript(null); }
    try {
      const h = await axios.get(`${API}/podcasts/episodes/${ep_id}/ai/history?limit=1`,
                                                {withCredentials: true});
      const latest = (h.data.history || [])[0];
      if (latest?.output_json) setMetadata(latest.output_json);
    } catch (_) {}
    try {
      const s = await axios.get(`${API}/admin/podcasts/integrations/assemblyai/status`,
                                                {withCredentials: true});
      setMockMode(!s.data.is_live);
    } catch (_) {
      // non-admin can't read the status endpoint — fall back to: assume
      // mock if transcript has a provider_note indicating mock.
      if (transcript?.provider === "mock") setMockMode(true);
    }
  }, [ep_id, transcript?.provider]);

  useEffect(() => { refresh(); }, [refresh]);
  // Poll while a transcript is in flight.
  useEffect(() => {
    if (transcript?.status === "processing" || transcript?.status === "pending") {
      const t = setTimeout(refresh, 2500);
      return () => clearTimeout(t);
    }
  }, [transcript?.status, refresh]);

  const kickTranscribe = async () => {
    setBusy("transcribing");
    try {
      await axios.post(`${API}/podcasts/episodes/${ep_id}/transcribe`, {},
                                {withCredentials: true});
      await refresh();
    } finally { setBusy(""); }
  };
  const reroll = async () => {
    setBusy("ai");
    try {
      const r = await axios.post(`${API}/podcasts/episodes/${ep_id}/ai/generate-metadata`, {},
                                            {withCredentials: true});
      setMetadata(r.data.metadata);
    } finally { setBusy(""); }
  };
  const applyAll = async () => {
    if (!metadata) return;
    setBusy("apply");
    try {
      await axios.post(`${API}/podcasts/episodes/${ep_id}/apply-metadata`, {
        title:                       metadata.title,
        description:           metadata.description,
        show_notes:           metadata.show_notes,
        chapters:                 metadata.chapters,
        social_captions:    metadata.social_captions,
        seo_keywords:        metadata.seo_keywords,
        hashtags:                 metadata.hashtags,
        sponsor_read_suggestions: metadata.sponsor_read_suggestions,
        summary_short:        metadata.summary_short,
        summary_long:         metadata.summary_long,
      }, {withCredentials: true});
      await refresh();
    } finally { setBusy(""); }
  };

  const utterances = transcript?.utterances_json || [];
  const status =
    !transcript                                         ? "no_transcript"
    : transcript.status === "processing"  ? "transcribing"
    : transcript.status === "pending"        ? "transcribing"
    : transcript.status === "completed"
        ? (metadata ? "ready" : "metadata_pending")
        : transcript.status;

  const updateUtterance = (idx, text) => {
    const next = [...utterances];
    next[idx] = {...next[idx], text};
    setTranscript({...transcript, utterances_json: next});
  };
  const saveTranscriptText = async () => {
    setBusy("save_transcript");
    try {
      // Apply any pending speaker renames inline before flattening.
      const flat = utterances.map((u) => {
        const sp = speakerRenames[u.speaker] || u.speaker;
        return `[${sp}] ${u.text}`;
      }).join("\n\n");
      await axios.patch(`${API}/podcasts/episodes/${ep_id}/transcript`,
                                  {text: flat}, {withCredentials: true});
      await refresh();
    } finally { setBusy(""); }
  };

  const speakerList = useMemo(() =>
    Array.from(new Set(utterances.map((u) => u.speaker))).filter(Boolean),
  [utterances]);

  return (
    <div data-testid="transcript-editor"
            style={{padding: 24, color: "#e7e7ea", background: "#0a0a0c",
                        minHeight: "100vh", fontFamily: "system-ui"}}>
      <Link to="/creator" style={{color: "#9aa3af", fontSize: 12,
                                                          textDecoration: "none"}}>← Back to Creator</Link>
      <h1 style={{fontSize: 24, fontWeight: 700, marginTop: 6}}>
        {ep?.title || "Episode"}
      </h1>
      <StatusBar status={status} mockMode={mockMode}
                            onKick={kickTranscribe} busy={busy} />

      <div style={{display: "grid", gridTemplateColumns: "1fr 1fr",
                            gap: 24, marginTop: 20}}>
        {/* LEFT — Transcript */}
        <section data-testid="transcript-panel"
                        style={{background: "#13131a", borderRadius: 12,
                                    padding: 18, border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{display: "flex", justifyContent: "space-between",
                                alignItems: "center", marginBottom: 12}}>
            <h2 style={{fontSize: 16, fontWeight: 700}}>Transcript</h2>
            <button data-testid="save-transcript"
                            onClick={saveTranscriptText}
                            disabled={busy === "save_transcript" || !utterances.length}
                            style={btn("ghost")}>
              {busy === "save_transcript" ? "Saving…" : "Save edits"}
            </button>
          </div>

          {speakerList.length > 0 && (
            <div data-testid="speaker-rename-row"
                    style={{display: "flex", flexWrap: "wrap", gap: 6,
                                marginBottom: 10}}>
              {speakerList.map((sp) => (
                <input key={sp} placeholder={`Speaker ${sp}`}
                          value={speakerRenames[sp] || ""}
                          onChange={(e) => setSpeakerRenames({...speakerRenames,
                                                                                              [sp]: e.target.value})}
                          style={{padding: "4px 8px", fontSize: 12, borderRadius: 6,
                                      background: "#0a0a0c", color: "#e7e7ea",
                                      border: "1px solid rgba(255,255,255,0.08)", width: 130}} />
              ))}
            </div>
          )}

          {status === "transcribing" && (
            <div data-testid="transcribing-spinner"
                    style={{color: "#fbbf24", padding: 24, textAlign: "center"}}>
              AI is transcribing… this usually takes 30-90s for a full episode.
            </div>
          )}
          {status === "no_transcript" && (
            <div data-testid="no-transcript"
                    style={{color: "#9aa3af", padding: 16, textAlign: "center"}}>
              No transcript yet. Publish this episode to auto-transcribe, or click below.
              <div style={{marginTop: 12}}>
                <button data-testid="kick-transcribe" onClick={kickTranscribe}
                                disabled={!!busy} style={btn("primary")}>
                  Start transcription
                </button>
              </div>
            </div>
          )}
          <div style={{maxHeight: 540, overflowY: "auto", marginTop: 8}}>
            {utterances.map((u, idx) => (
              <div key={idx} data-testid={`utterance-${idx}`}
                      style={{padding: 8, marginBottom: 6, borderRadius: 8,
                                  background: "rgba(255,255,255,0.02)"}}>
                <div style={{fontSize: 10, color: "#9aa3af", marginBottom: 2}}>
                  {speakerRenames[u.speaker] || `Speaker ${u.speaker}`} ·
                                {fmtTime(u.start)} - {fmtTime(u.end)}
                </div>
                <textarea value={u.text || ""}
                              onChange={(e) => updateUtterance(idx, e.target.value)}
                              style={{width: "100%", padding: 6, borderRadius: 6,
                                          background: "transparent", color: "#e7e7ea",
                                          border: "1px solid rgba(255,255,255,0.06)",
                                          fontSize: 13, minHeight: 38, resize: "vertical"}} />
              </div>
            ))}
          </div>
        </section>

        {/* RIGHT — AI metadata */}
        <section data-testid="metadata-panel"
                        style={{background: "#13131a", borderRadius: 12,
                                    padding: 18, border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{display: "flex", justifyContent: "space-between",
                                alignItems: "center", marginBottom: 12}}>
            <h2 style={{fontSize: 16, fontWeight: 700}}>AI metadata</h2>
            <div style={{display: "flex", gap: 8}}>
              <button data-testid="reroll-metadata"
                              disabled={busy === "ai" || status !== "ready" && status !== "metadata_pending"}
                              onClick={reroll} style={btn("ghost")}>
                {busy === "ai" ? "Generating…" : "Re-roll"}
              </button>
              <button data-testid="apply-selected" onClick={applyAll}
                              disabled={!metadata || busy === "apply"}
                              style={btn("primary")}>
                {busy === "apply" ? "Applying…" : "Apply & publish"}
              </button>
            </div>
          </div>

          {!metadata && status === "metadata_pending" && (
            <div data-testid="metadata-pending"
                    style={{color: "#fbbf24", padding: 12}}>
              Transcript ready — generating AI metadata…
            </div>
          )}
          {!metadata && status !== "metadata_pending" && (
            <div data-testid="metadata-empty"
                    style={{color: "#9aa3af", padding: 12}}>
              No AI metadata yet. {status === "ready" ? "Click Re-roll." : ""}
            </div>
          )}

          {metadata && (
            <>
              <Field label="Title">
                <input data-testid="md-title" value={metadata.title || ""}
                          onChange={(e) => setMetadata({...metadata, title: e.target.value})}
                          style={inp()} />
                {(metadata.title_alternatives || []).length > 0 && (
                  <div style={{display: "flex", gap: 6, marginTop: 6,
                                        flexWrap: "wrap"}}>
                    {metadata.title_alternatives.map((alt, i) => (
                      <button key={i} data-testid={`title-alt-${i}`}
                                      onClick={() => setMetadata({...metadata, title: alt})}
                                      style={chip()}>{alt}</button>
                    ))}
                  </div>
                )}
              </Field>
              <Field label="Description">
                <textarea data-testid="md-description"
                                value={metadata.description || ""}
                                onChange={(e) => setMetadata({...metadata, description: e.target.value})}
                                style={{...inp(), minHeight: 70}} />
              </Field>
              <Field label="Show notes (markdown)">
                <textarea data-testid="md-shownotes"
                                value={metadata.show_notes || ""}
                                onChange={(e) => setMetadata({...metadata, show_notes: e.target.value})}
                                style={{...inp(), minHeight: 140, fontFamily: "monospace"}} />
              </Field>
              <Field label="Chapters">
                <div data-testid="chapters-list">
                  {(metadata.chapters || []).map((c, i) => (
                    <div key={i} data-testid={`chapter-${i}`}
                            style={{display: "flex", gap: 6, marginBottom: 4,
                                        alignItems: "center"}}>
                      <span style={{fontSize: 11, color: "#9aa3af", width: 50}}>
                        {fmtTime((c.start_time_seconds || 0) * 1000)}
                      </span>
                      <input value={c.title || ""} onChange={(e) => {
                        const next = [...metadata.chapters];
                        next[i] = {...next[i], title: e.target.value};
                        setMetadata({...metadata, chapters: next});
                      }} style={inp()} />
                    </div>
                  ))}
                </div>
              </Field>
              <Field label="SEO keywords">
                <div data-testid="seo-keywords"
                        style={{display: "flex", flexWrap: "wrap", gap: 4}}>
                  {(metadata.seo_keywords || []).map((k, i) => (
                    <span key={i} style={chip()}>{k}</span>
                  ))}
                </div>
              </Field>
              <Field label="Social captions">
                <div style={{display: "flex", gap: 6, marginBottom: 6}}>
                  {["twitter", "instagram", "linkedin", "youtube"].map((t) => (
                    <button key={t} data-testid={`social-tab-${t}`}
                                    onClick={() => setTab(t)}
                                    style={{...chip(), background: tab === t ? "#f59e0b" : "transparent",
                                                color: tab === t ? "#0a0a0c" : "#e7e7ea"}}>
                      {t}
                    </button>
                  ))}
                </div>
                <textarea data-testid={`social-text-${tab}`}
                                value={(metadata.social_captions || {})[tab] || ""}
                                onChange={(e) => setMetadata({...metadata,
                                  social_captions: {...(metadata.social_captions || {}),
                                                            [tab]: e.target.value}})}
                                style={{...inp(), minHeight: 70}} />
              </Field>
              <Field label="Sponsor reads">
                {(metadata.sponsor_read_suggestions || []).map((s, i) => (
                  <div key={i} data-testid={`sponsor-${i}`}
                          style={{padding: 8, marginBottom: 6, borderRadius: 6,
                                      background: "rgba(255,255,255,0.02)"}}>
                    <div style={{fontSize: 10, color: "#9aa3af", marginBottom: 4}}>
                      {s.slot} · {s.length_seconds}s
                    </div>
                    <div style={{fontSize: 12}}>{s.script_text}</div>
                  </div>
                ))}
              </Field>
            </>
          )}
        </section>
      </div>

      {/* Phase 36d Turn 1 — Magic Clips review surface on episode page. */}
      <section data-testid="magic-clips-section"
                          style={{marginTop: 24, background: "#13131a", borderRadius: 12,
                                      padding: 18, border: "1px solid rgba(255,255,255,0.06)"}}>
        <MagicClipsTab episodeId={ep_id} isOwner={true} />
      </section>

      {/* Phase 36d Turn 2 — Shoppable cards (creator-side) on episode page. */}
      <section data-testid="shoppable-section"
                          style={{marginTop: 24, background: "#13131a", borderRadius: 12,
                                      padding: 18, border: "1px solid rgba(255,255,255,0.06)"}}>
        <ShoppableCardsCreator episodeId={ep_id} isOwner={true} />
      </section>

      {/* Phase 36d Turn 3 — Lightning splits (per-episode override). */}
      <EpisodeLightningSection ep_id={ep_id} channel_id={ep?.channel_id} />
    </div>
  );
}

function EpisodeLightningSection({ep_id, channel_id}) {
  const [useDefault, setUseDefault] = useState(true);
  const [resolved, setResolved] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const refresh = React.useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/podcasts/episodes/${ep_id}/lightning-splits`,
        {withCredentials: true});
      setResolved(r.data);
      setUseDefault(!!r.data?.inherited_from_channel);
    } catch (e) { setErr(_lsMsg(e)); }
  }, [ep_id]);
  useEffect(() => { refresh(); }, [refresh]);

  const flipToOverride = async () => {
    if (!resolved?.recipients?.length || !channel_id) return;
    setBusy(true); setErr("");
    try {
      // Pre-populate the override with the inherited recipients so the
      // creator only needs to tweak.
      await axios.put(
        `${API}/podcasts/episodes/${ep_id}/lightning-splits`,
        {recipients: resolved.recipients}, {withCredentials: true});
      setUseDefault(false);
      await refresh();
    } catch (e) { setErr(_lsMsg(e)); }
    finally { setBusy(false); }
  };
  const flipToInherit = async () => {
    setBusy(true); setErr("");
    try {
      await axios.delete(
        `${API}/podcasts/episodes/${ep_id}/lightning-splits`,
        {withCredentials: true});
      setUseDefault(true);
      await refresh();
    } catch (e) { setErr(_lsMsg(e)); }
    finally { setBusy(false); }
  };

  return (
    <section data-testid="lightning-section-episode"
                        style={{marginTop: 24, background: "#13131a", borderRadius: 12,
                                    padding: 18, border: "1px solid rgba(255,255,255,0.06)"}}>
      <h2 style={{fontSize: 16, fontWeight: 700, margin: "0 0 12px"}}>
        Lightning splits (this episode)
      </h2>
      <label style={{display: "flex", alignItems: "center", gap: 8,
                                marginBottom: 12, cursor: "pointer"}}>
        <input data-testid="lightning-use-channel-default-toggle"
                    type="checkbox" checked={useDefault} disabled={busy}
                    onChange={(e) => e.target.checked ? flipToInherit() : flipToOverride()}/>
        <span>Use channel default</span>
      </label>
      {err && (
        <div data-testid="lightning-ep-err"
                  style={{color: "#ef4444", fontSize: 12, marginBottom: 8}}>
          {err}
        </div>
      )}
      {useDefault ? (
        <div data-testid="lightning-inherited-summary"
                  style={{fontSize: 12, color: "#9aa3af", lineHeight: 1.5}}>
          {resolved?.recipients?.length ? (
            <>
              <div style={{marginBottom: 6, color: "#e7e7ea"}}>
                Inheriting {resolved.recipients.length} recipient
                {resolved.recipients.length !== 1 ? "s" : ""} from the channel default:
              </div>
              {resolved.recipients.map((r, i) => (
                <div key={i} data-testid={`lightning-inherited-row-${i}`}
                          style={{padding: "3px 0", fontFamily: "monospace",
                                      fontSize: 11}}>
                  · <b style={{color: "#fbbf24"}}>{r.split_pct}%</b> →
                  &nbsp;{r.name} ({r.type}: {String(r.address).slice(0,12)}…)
                </div>
              ))}
            </>
          ) : (
            <div>Channel has no Lightning splits configured.
                Set them in Channel Settings → Lightning splits.</div>
          )}
        </div>
      ) : (
        <LightningSplitsEditor
          testIdPrefix="lightning-ep"
          loadUrl={`${API}/podcasts/episodes/${ep_id}/lightning-splits`}
          saveUrl={`${API}/podcasts/episodes/${ep_id}/lightning-splits`}
          helperText="Episode-specific override — overrides the channel default for this episode only."
        />
      )}
    </section>
  );
}

function _lsMsg(e) {
  return e?.response?.data?.detail || e?.message || String(e);
}

function _Tail() {
  return null;  // marker
}

function StatusBar({status, mockMode, onKick, busy}) {
  const label = {
    no_transcript:        "Draft — no transcript",
    transcribing:           "AI is transcribing…",
    metadata_pending:  "Transcript ready · AI metadata generating…",
    ready:                       "Ready to publish",
    error:                       "Transcription error",
  }[status] || status;
  const color = status === "ready" ? "#22c55e"
                          : status === "error" ? "#ef4444"
                          : "#fbbf24";
  return (
    <>
      <div data-testid="status-banner"
              style={{marginTop: 10, padding: 10, borderRadius: 8,
                          background: "rgba(255,255,255,0.03)",
                          border: `1px solid ${color}33`, color}}>
        <span data-testid={`status-label-${status}`} style={{fontWeight: 600}}>
          {label}
        </span>
      </div>
      {mockMode && (
        <div data-testid="mock-mode-banner"
                style={{marginTop: 8, padding: 10, borderRadius: 8,
                            background: "rgba(245,158,11,0.1)",
                            border: "1px solid rgba(245,158,11,0.4)",
                            color: "#fbbf24", fontSize: 13}}>
          ⚠ Transcription is in <b>MOCK mode</b>. Set
          <code style={{margin: "0 4px", padding: "1px 5px", borderRadius: 3,
                                background: "rgba(0,0,0,0.4)"}}>ASSEMBLYAI_API_KEY</code>
          to get real diarized transcripts.
        </div>
      )}
    </>
  );
}

function Field({label, children}) {
  return (
    <div style={{marginBottom: 12}}>
      <div style={{fontSize: 10, textTransform: "uppercase",
                            color: "#9aa3af", letterSpacing: 0.5, marginBottom: 4}}>
        {label}
      </div>
      {children}
    </div>
  );
}

const inp = () => ({
  width: "100%", padding: 8, borderRadius: 6,
  background: "#0a0a0c", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.08)", fontSize: 13,
});

const chip = () => ({
  padding: "4px 10px", borderRadius: 999, fontSize: 11,
  background: "rgba(245,158,11,0.12)", color: "#fbbf24",
  border: "1px solid rgba(245,158,11,0.3)", cursor: "pointer",
});

const btn = (variant) => ({
  padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
  cursor: "pointer", border: "1px solid rgba(255,255,255,0.08)",
  background: variant === "primary" ? "#f59e0b" : "transparent",
  color: variant === "primary" ? "#0a0a0c" : "#e7e7ea",
});
