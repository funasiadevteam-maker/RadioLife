// Phase 36d Turn 1 — Magic Clips: creator review tab + global Highlights feed.
//
// Single file exports: <MagicClipsTab episodeId .../>, <Highlights/>,
// <ChannelHighlightsCarousel channelId ... />.

import React, {useEffect, useState, useCallback} from "react";
import axios from "axios";
import {Link} from "react-router-dom";
import {ShoppableCardsSidebar} from "@/ShoppableCards";  // Phase 36d Turn 2

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
axios.defaults.withCredentials = true;
const POLL_MS = 5000;

function formatSec(s) {
  if (s == null) return "—";
  const m = Math.floor(s / 60); const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

function ClipCard({clip, onPublish, onEditTitle, onDelete, isOwner}) {
  const [editing, setEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState(clip.title || "");
  const dur = (clip.end_sec || 0) - (clip.start_sec || 0);
  return (
    <div data-testid={`magic-clip-${clip.id}`} data-status={clip.status}
            style={{display: "flex", gap: 12, padding: 12,
                        borderRadius: 8, background: "#101018",
                        border: "1px solid rgba(255,255,255,0.06)",
                        marginBottom: 8}}>
      <div style={{width: 92, height: 56, borderRadius: 4, flexShrink: 0,
                          background: "linear-gradient(135deg, #1e1e2a, #2a1a2e)",
                          display: "flex", alignItems: "center",
                          justifyContent: "center", fontSize: 11,
                          color: "#9aa3af"}}>
        {clip.ext === "mp4" ? "VIDEO" : "AUDIO"}
      </div>
      <div style={{flex: 1, minWidth: 0}}>
        {editing ? (
          <input data-testid={`title-input-${clip.id}`}
                      value={titleDraft}
                      onChange={(e) => setTitleDraft(e.target.value)}
                      onBlur={() => { onEditTitle(clip, titleDraft); setEditing(false); }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          onEditTitle(clip, titleDraft); setEditing(false);
                        }}}
                      autoFocus
                      style={{width: "100%", padding: 4, background: "#0a0a14",
                                  border: "1px solid #444", color: "#fff",
                                  borderRadius: 4}} />
        ) : (
          <div style={{fontWeight: 600, color: "#e7e7ea"}}>
            {clip.title || "Untitled"}
          </div>
        )}
        <div style={{fontSize: 11, color: "#9aa3af", marginTop: 2}}>
          {formatSec(clip.start_sec)}–{formatSec(clip.end_sec)} · {dur.toFixed(0)}s ·
          score {(clip.score || 0).toFixed(2)} ·{" "}
          <span data-testid={`clip-status-${clip.id}`}
                    style={{color: clip.status === "published" ? "#22c55e" : "#fbbf24"}}>
            {clip.status}
          </span>
        </div>
        {clip.summary && (
          <div style={{fontSize: 12, color: "#9aa3af",
                              marginTop: 4, lineHeight: 1.4}}>
            {clip.summary}
          </div>
        )}
      </div>
      {isOwner && (
        <div style={{display: "flex", flexDirection: "column", gap: 4,
                            alignSelf: "center"}}>
          {clip.status === "draft" && (
            <button data-testid={`publish-${clip.id}`}
                            onClick={() => onPublish(clip)}
                            style={btnPrimary()}>Publish</button>
          )}
          <button data-testid={`edit-${clip.id}`}
                          onClick={() => setEditing(true)}
                          style={btnSec()}>Edit title</button>
          <button data-testid={`delete-${clip.id}`}
                          onClick={() => onDelete(clip)}
                          style={btnDelete()}>Delete</button>
        </div>
      )}
    </div>
  );
}

export function MagicClipsTab({episodeId, isOwner = false}) {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState(null);
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/podcasts/episodes/${episodeId}/magic-clips`);
      setItems(r.data?.items || []);
      setStatus(r.data?.magic_clips_status);
      setErr(r.data?.magic_clips_error || "");
    } catch (e) { setErr(e?.response?.data?.detail || e.message); }
  }, [episodeId]);

  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      if (status === "running" || status === "pending") refresh();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [refresh, status]);

  const drafts        = items.filter((c) => c.status === "draft");
  const published = items.filter((c) => c.status === "published");

  const onGenerate = async () => {
    await axios.post(`${API}/podcasts/episodes/${episodeId}/magic-clips/generate`);
    setStatus("pending"); refresh();
  };
  const onPublish = async (c) => {
    await axios.post(`${API}/podcasts/magic-clips/${c.id}/publish`); refresh();
  };
  const onEditTitle = async (c, title) => {
    if (title === c.title) return;
    await axios.patch(`${API}/podcasts/magic-clips/${c.id}`, {title}); refresh();
  };
  const onDelete = async (c) => {
    if (!window.confirm("Delete this clip?")) return;
    await axios.delete(`${API}/podcasts/magic-clips/${c.id}`); refresh();
  };
  const onPublishAll = async () => {
    for (const c of drafts) {
      await axios.post(`${API}/podcasts/magic-clips/${c.id}/publish`);
    }
    refresh();
  };

  return (
    <div data-testid="magic-clips-tab" style={{color: "#e7e7ea"}}>
      <div style={{display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 12}}>
        <h2 style={{fontSize: 18, margin: 0}}>Magic Clips</h2>
        {isOwner && (
          <div style={{display: "flex", gap: 8}}>
            <button data-testid="generate-clips" onClick={onGenerate}
                            style={btnSec()}>Re-generate</button>
            {drafts.length > 0 && (
              <button data-testid="publish-all" onClick={onPublishAll}
                              style={btnPrimary()}>Publish all ({drafts.length})</button>
            )}
          </div>
        )}
      </div>
      {status && (
        <div data-testid="magic-clips-status"
                style={{fontSize: 12, marginBottom: 8, color: "#9aa3af"}}>
          Status: <b data-testid="status-value">{status}</b>
          {err && <span style={{color: "#ef4444"}}> · {err}</span>}
        </div>
      )}
      {drafts.length > 0 && (
        <>
          <div style={sectionH()}>Drafts ({drafts.length})</div>
          {drafts.map((c) => (
            <ClipCard key={c.id} clip={c} isOwner={isOwner}
                              onPublish={onPublish} onEditTitle={onEditTitle}
                              onDelete={onDelete} />
          ))}
        </>
      )}
      {published.length > 0 && (
        <>
          <div style={sectionH()}>Published ({published.length})</div>
          {published.map((c) => (
            <ClipCard key={c.id} clip={c} isOwner={isOwner}
                              onPublish={onPublish} onEditTitle={onEditTitle}
                              onDelete={onDelete} />
          ))}
        </>
      )}
      {items.length === 0 && status !== "running" && status !== "pending" && (
        <div data-testid="magic-clips-empty"
                style={{padding: 24, textAlign: "center", color: "#9aa3af"}}>
          No magic clips yet for this episode.
        </div>
      )}
    </div>
  );
}

export function Highlights() {
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (c) => {
    setLoading(true);
    const url = `${API}/podcasts/highlights?limit=20${c ? "&cursor=" + encodeURIComponent(c) : ""}`;
    const r = await axios.get(url);
    setItems((prev) => (c ? [...prev, ...(r.data.items || [])] : (r.data.items || [])));
    setCursor(r.data.next_cursor); setHasMore(r.data.has_more);
    setLoading(false);
  }, []);

  useEffect(() => { load(null); }, [load]);
  return (
    <div data-testid="highlights-page"
            style={{minHeight: "100vh", background: "#0a0a14", color: "#e7e7ea",
                        padding: 24, maxWidth: 960, margin: "0 auto"}}>
      <h1 style={{fontSize: 28, fontWeight: 800, margin: "0 0 4px"}}>
        Highlights
      </h1>
      <p style={{color: "#9aa3af", marginTop: 0, marginBottom: 20}}>
        Best moments across FUUSIC channels.
      </p>
      {items.length === 0 && !loading && (
        <div data-testid="highlights-empty"
                style={{padding: 40, textAlign: "center", color: "#9aa3af"}}>
          No highlights yet — clip auto-generation kicks in after each new episode.
        </div>
      )}
      {items.map((c) => (
        <div key={c.id} data-testid={`highlight-${c.id}`}
                style={{padding: 12, marginBottom: 8, borderRadius: 8,
                            background: "#101018",
                            border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{fontWeight: 600}}>{c.title}</div>
          <div style={{fontSize: 11, color: "#9aa3af"}}>
            {(c.end_sec - c.start_sec).toFixed(0)}s · score {(c.score || 0).toFixed(2)}
            {c.channel_id && (
              <>{" · "}<Link to={`/podcasts/channels/${c.channel_id}`}
                                          style={{color: "#a78bfa"}}>channel</Link></>
            )}
          </div>
          {/* Phase 36d Turn 2 — shoppable cards per magic clip (compact 2-col). */}
          <div style={{marginTop: 8}}>
            <ShoppableCardsSidebar magicClipId={c.id} variant="compact" />
          </div>
        </div>
      ))}
      {hasMore && (
        <button data-testid="load-more" onClick={() => load(cursor)}
                        disabled={loading} style={{...btnSec(), marginTop: 12}}>
          {loading ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}

export function ChannelHighlightsCarousel({channelId}) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    axios.get(`${API}/podcasts/channels/${channelId}/highlights?limit=10`)
              .then((r) => setItems(r.data?.items || [])).catch(() => {});
  }, [channelId]);
  if (items.length === 0) return null;
  return (
    <div data-testid="channel-highlights-carousel" style={{margin: "16px 0"}}>
      <div style={sectionH()}>Recent clips</div>
      <div style={{display: "flex", gap: 8, overflowX: "auto", padding: "4px 0"}}>
        {items.map((c) => (
          <div key={c.id} data-testid={`carousel-clip-${c.id}`}
                  style={{minWidth: 220, padding: 10, borderRadius: 8,
                              background: "#101018",
                              border: "1px solid rgba(255,255,255,0.06)"}}>
            <div style={{fontWeight: 600, fontSize: 13}}>{c.title}</div>
            <div style={{fontSize: 11, color: "#9aa3af"}}>
              {(c.end_sec - c.start_sec).toFixed(0)}s
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const btnPrimary = () => ({padding: "5px 12px", borderRadius: 6, fontSize: 11,
  fontWeight: 700, cursor: "pointer", background: "#f59e0b",
  color: "#0a0a0c", border: "none"});
const btnSec = () => ({padding: "5px 12px", borderRadius: 6, fontSize: 11,
  fontWeight: 700, cursor: "pointer", background: "rgba(255,255,255,0.05)",
  color: "#e7e7ea", border: "1px solid rgba(255,255,255,0.1)"});
const btnDelete = () => ({...btnSec(), color: "#ef4444"});
const sectionH = () => ({fontSize: 10, textTransform: "uppercase", color: "#9aa3af",
  letterSpacing: 0.5, margin: "10px 0 6px"});
