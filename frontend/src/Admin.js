import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Upload, Disc3, FileText, FolderUp, RefreshCw, Loader2, Edit3, Save, X,
  Music, Mic2, Play, Pause, Trash2, AlertTriangle,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API, useAuth } from "@/AuthContext";
import BigFmBrand from "@/components/BigFmBrand";
import AdminSubNav from "@/AdminSubNav";  // Phase 19a — grouped sub-nav

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const fmt = (s) => {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};

const ENERGY_OPTIONS = ["chill", "medium", "high", "party"];
const MOOD_OPTIONS = [
  "romantic", "energetic", "melancholy", "uplifting", "dance",
  "chill", "devotional", "nostalgic", "party", "sad", "peppy", "intense",
];

function Chip({ children, color = "cyan", "data-testid": dt }) {
  return <span className={`mini-chip mini-chip-${color}`} data-testid={dt}>{children}</span>;
}

// Phase 42 S1 — ⚠ Unplayable badge: lazy-probes the per-track health endpoint
// and surfaces a warning chip when the file is missing on storage.
function TrackHealthBadge({ trackId }) {
  const [state, setState] = useState({ probed: false, playable: true, reason: "" });
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/admin/tracks/${trackId}/health`);
        if (cancel) return;
        setState({ probed: true,
                   playable: !!r.data?.playable,
                   reason: r.data?.reason || "" });
      } catch (_e) { /* silent */ }
    })();
    return () => { cancel = true; };
  }, [trackId]);
  if (!state.probed || state.playable) return null;
  return (
    <span data-testid={`track-unplayable-${trackId}`}
          title={`Unplayable: ${state.reason || "unknown"}`}
          style={{ marginLeft: 8, padding: "2px 6px", borderRadius: 4,
                   background: "rgba(245,158,11,0.12)",
                   border: "1px solid #f59e0b", color: "#f59e0b",
                   fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
                   display: "inline-flex", alignItems: "center", gap: 3 }}>
      <AlertTriangle size={10} /> UNPLAYABLE
    </span>
  );
}

function SingleUploader({ onUploaded }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const submit = async (file) => {
    if (!file || !file.name.toLowerCase().endsWith(".mp3")) {
      toast.error("MP3 only"); return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", file.name.replace(/\.mp3$/i, ""));
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/tracks/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Tagged: ${r.data.title} (${r.data.energy_level} / ${r.data.mood})`);
      onUploaded(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Upload failed"); }
    finally { setBusy(false); }
  };
  return (
    <div className="uploader" onClick={() => inputRef.current?.click()} data-testid="single-uploader">
      <Upload className="icon" size={24} />
      <p>Single MP3 — auto-tagged on the way in</p>
      <input ref={inputRef} type="file" accept=".mp3,audio/mpeg"
             onChange={(e) => submit(e.target.files?.[0])}
             data-testid="single-upload-input" />
      {busy && <div className="upload-progress" data-testid="single-upload-busy">Tagging…</div>}
    </div>
  );
}

function BulkUploader({ onUploaded }) {
  const audioRef = useRef(null);
  const zipRef = useRef(null);
  const csvRef = useRef(null);
  const [audioFiles, setAudioFiles] = useState([]);
  const [zipFile, setZipFile] = useState(null);
  const [csvFile, setCsvFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null); // {done,total}

  const submit = async () => {
    if (!audioFiles.length && !zipFile) {
      toast.warning("Add some MP3s or a ZIP first"); return;
    }
    const fd = new FormData();
    audioFiles.forEach((f) => fd.append("audio_files", f));
    if (zipFile) fd.append("zip_file", zipFile);
    if (csvFile) fd.append("csv_file", csvFile);
    setBusy(true);
    setProgress({ done: 0, total: audioFiles.length || "?" });
    try {
      const r = await axios.post(`${API}/admin/tracks/bulk_upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600000,
      });
      const ok = r.data.succeeded.length;
      const fail = r.data.failed.length;
      toast.success(`Bulk upload complete: ${ok} tagged, ${fail} failed`);
      r.data.succeeded.forEach(onUploaded);
      setAudioFiles([]); setZipFile(null); setCsvFile(null);
      if (audioRef.current) audioRef.current.value = "";
      if (zipRef.current) zipRef.current.value = "";
      if (csvRef.current) csvRef.current.value = "";
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bulk upload failed");
    } finally {
      setBusy(false); setProgress(null);
    }
  };

  const totalCount = audioFiles.length + (zipFile ? 1 : 0);
  return (
    <div className="bulk-uploader" data-testid="bulk-uploader">
      <div className="bulk-grid">
        <div className="bulk-slot" data-testid="bulk-slot-audio">
          <div className="bulk-slot-label"><Music size={14}/> MP3 files</div>
          <button className="btn btn-ghost" onClick={() => audioRef.current?.click()}>
            <FolderUp size={14}/> Choose MP3s
          </button>
          <input ref={audioRef} type="file" accept=".mp3,audio/mpeg" multiple style={{display:"none"}}
                 onChange={(e)=>setAudioFiles(Array.from(e.target.files || []))}
                 data-testid="bulk-mp3-input" />
          <div className="bulk-file-info mono">{audioFiles.length ? `${audioFiles.length} MP3s queued` : "none"}</div>
        </div>
        <div className="bulk-slot" data-testid="bulk-slot-zip">
          <div className="bulk-slot-label"><FolderUp size={14}/> ZIP archive</div>
          <button className="btn btn-ghost" onClick={() => zipRef.current?.click()}>
            <FolderUp size={14}/> Choose ZIP
          </button>
          <input ref={zipRef} type="file" accept=".zip" style={{display:"none"}}
                 onChange={(e)=>setZipFile(e.target.files?.[0] || null)}
                 data-testid="bulk-zip-input" />
          <div className="bulk-file-info mono">{zipFile?.name || "none"}</div>
        </div>
        <div className="bulk-slot" data-testid="bulk-slot-csv">
          <div className="bulk-slot-label"><FileText size={14}/> CSV overrides (optional)</div>
          <button className="btn btn-ghost" onClick={() => csvRef.current?.click()}>
            <FileText size={14}/> Choose CSV
          </button>
          <input ref={csvRef} type="file" accept=".csv,text/csv" style={{display:"none"}}
                 onChange={(e)=>setCsvFile(e.target.files?.[0] || null)}
                 data-testid="bulk-csv-input" />
          <div className="bulk-file-info mono">{csvFile?.name || "none"}</div>
        </div>
      </div>
      <p className="csv-hint">
        CSV columns: <code>filename, title, artist, album, language, era, genre, mood, energy_level</code>.
        Filename is the join key. Provided fields override auto-tags.
      </p>
      <button className="btn btn-primary" onClick={submit}
              disabled={busy || (!audioFiles.length && !zipFile)}
              data-testid="bulk-submit-btn" style={{width:"100%", marginTop:12}}>
        {busy ? <><Loader2 size={14} className="spin"/> Tagging in parallel…</> :
                <><Upload size={14}/> Auto-tag & upload {totalCount > 0 ? `(${audioFiles.length} files${zipFile ? " + ZIP" : ""})` : ""}</>}
      </button>
      {progress && busy && <div className="upload-progress" data-testid="bulk-progress">Processing… auto-tagging via OpenAI in parallel</div>}
    </div>
  );
}

function EnergyChip({ value }) {
  const colorMap = { chill: "cyan", medium: "amber", high: "pink", party: "pink" };
  return <Chip color={colorMap[value] || "neutral"}>{value}</Chip>;
}

function TrackRow({ t, onRetag, onPatch, retagging, onPreview, onDelete, playingId }) {
  const [editing, setEditing] = useState(false);
  const [energy, setEnergy] = useState(t.energy_level);
  const [mood, setMood] = useState(t.mood || "uplifting");
  const isPlaying = playingId === t.id;
  useEffect(() => { setEnergy(t.energy_level); setMood(t.mood || "uplifting"); }, [t]);

  const save = async () => {
    if (energy === t.energy_level && mood === (t.mood || "uplifting")) {
      setEditing(false); return;
    }
    await onPatch(t.id, { energy_level: energy, mood });
    setEditing(false);
  };

  return (
    <tr data-testid={`track-row-${t.id}`}>
      <td className="row-play-cell">
        <button
          type="button"
          className={`ico-btn play ${isPlaying ? "is-on" : ""}`}
          onClick={() => onPreview(t)}
          title={isPlaying ? "Stop preview" : "Play preview"}
          data-testid={`preview-track-${t.id}`}
          aria-label={isPlaying ? `Stop ${t.title}` : `Play ${t.title}`}
        >
          {isPlaying ? <Pause size={13} /> : <Play size={13} />}
        </button>
      </td>
      <td>
        <div className="t-title">{t.title}<TrackHealthBadge trackId={t.id} /></div>
        <div className="t-artist">{t.artist}</div>
      </td>
      <td className="mono">{fmt(t.duration_sec)}</td>
      <td>
        {editing ? (
          <select className="mini-select" value={energy} onChange={(e)=>setEnergy(e.target.value)}
                  data-testid={`edit-energy-${t.id}`}>
            {ENERGY_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : <EnergyChip value={t.energy_level} />}
      </td>
      <td>
        {editing ? (
          <select className="mini-select" value={mood} onChange={(e)=>setMood(e.target.value)}
                  data-testid={`edit-mood-${t.id}`}>
            {MOOD_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : <Chip color="neutral">{t.mood || "—"}</Chip>}
      </td>
      <td>
        <Chip color="neutral">{t.language_confidence || t.language || "—"}</Chip>
      </td>
      <td className="mono dim">{t.bpm || "—"}</td>
      <td>
        <div className="vibe-chips">
          {(t.vibe_tags || []).slice(0, 4).map(v => <Chip key={v} color="dim">{v}</Chip>)}
        </div>
      </td>
      <td className="row-actions">
        {editing ? (
          <>
            <button className="ico-btn ok" onClick={save} title="Save"
                    data-testid={`save-track-${t.id}`}><Save size={13}/></button>
            <button className="ico-btn" onClick={()=>setEditing(false)} title="Cancel"
                    data-testid={`cancel-track-${t.id}`}><X size={13}/></button>
          </>
        ) : (
          <>
            <button className="ico-btn" onClick={()=>setEditing(true)} title="Edit"
                    data-testid={`edit-track-${t.id}`}><Edit3 size={13}/></button>
            <button className="ico-btn" onClick={()=>onRetag(t.id)} disabled={retagging===t.id}
                    title="Re-tag with AI" data-testid={`retag-track-${t.id}`}>
              {retagging === t.id ? <Loader2 size={13} className="spin"/> : <RefreshCw size={13}/>}
            </button>
            <button className="ico-btn danger" onClick={()=>onDelete(t)} title="Delete track"
                    data-testid={`delete-track-${t.id}`}>
              <Trash2 size={13} />
            </button>
          </>
        )}
      </td>
    </tr>
  );
}

export default function Admin() {
  const { user } = useAuth();
  const [tracks, setTracks] = useState([]);
  const [retagging, setRetagging] = useState(null);
  const [filter, setFilter] = useState({ energy: "all", mood: "all", lang: "all", q: "" });
  const [playingId, setPlayingId] = useState(null);
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const previewAudioRef = useRef(null);

  const stopPreview = useCallback(() => {
    if (previewAudioRef.current) {
      try { previewAudioRef.current.pause(); } catch (_e) { /* */ }
      previewAudioRef.current.src = "";
      previewAudioRef.current = null;
    }
    setPlayingId(null);
  }, []);

  const onPreview = useCallback((t) => {
    if (playingId === t.id) { stopPreview(); return; }
    stopPreview();
    const a = new Audio(`${BACKEND_URL}/api/admin/tracks/${t.id}/preview`);
    a.preload = "auto";
    a.volume = 0.95;
    previewAudioRef.current = a;
    setPlayingId(t.id);
    a.addEventListener("ended", () => setPlayingId(null));
    a.addEventListener("error", () => {
      // MediaError differentiation: 4 = MEDIA_ERR_SRC_NOT_SUPPORTED / 404
      const code = a.error && a.error.code;
      toast.error(code === 4 ? "Audio file unavailable for this track"
                                          : "Could not load preview");
      setPlayingId(null);
    });
    a.play().catch((err) => {
      // Phase 42-hotfix — distinguish autoplay block from network/format errors.
      if (err && err.name === "NotAllowedError") {
        toast.warning("Click play again — browser blocked autoplay");
      } else if (err && err.name === "NotSupportedError") {
        toast.error("Audio format not supported by this browser");
      } else {
        toast.error("Could not play preview — check track storage");
      }
      setPlayingId(null);
    });
  }, [playingId, stopPreview]);

  useEffect(() => () => stopPreview(), [stopPreview]);

  const loadTracks = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/tracks`);
      setTracks(r.data || []);
    } catch (e) { toast.error("Could not load tracks"); }
  }, []);
  useEffect(() => { loadTracks(); }, [loadTracks]);

  const onUploaded = (t) => {
    setTracks((prev) => [t, ...prev.filter(x => x.id !== t.id)]);
  };

  const onRetag = async (id) => {
    setRetagging(id);
    try {
      const r = await axios.post(`${API}/admin/tracks/${id}/retag`);
      setTracks(prev => prev.map(t => t.id === id ? r.data : t));
      toast.success(`Re-tagged: ${r.data.title}`);
    } catch (e) { toast.error("Re-tag failed"); }
    finally { setRetagging(null); }
  };

  const onPatch = async (id, payload) => {
    try {
      const r = await axios.patch(`${API}/admin/tracks/${id}`, payload);
      setTracks(prev => prev.map(t => t.id === id ? r.data : t));
      toast.success("Saved");
    } catch (e) { toast.error("Save failed"); }
  };

  const onDelete = (t) => {
    if (playingId === t.id) stopPreview();
    setDeleteCandidate(t);
  };

  const confirmDelete = async () => {
    if (!deleteCandidate) return;
    setDeleting(true);
    try {
      await axios.delete(`${API}/admin/tracks/${deleteCandidate.id}`);
      setTracks((prev) => prev.filter((x) => x.id !== deleteCandidate.id));
      toast.success(`Deleted: ${deleteCandidate.title}`);
      setDeleteCandidate(null);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409) {
        toast.warning(detail || "Track is busy — try again in a moment");
      } else {
        toast.error(detail || "Delete failed");
      }
    } finally {
      setDeleting(false);
    }
  };

  const filtered = useMemo(() => {
    return tracks.filter(t => {
      if (filter.energy !== "all" && t.energy_level !== filter.energy) return false;
      if (filter.mood !== "all" && t.mood !== filter.mood) return false;
      if (filter.lang !== "all" && t.language_confidence !== filter.lang) return false;
      if (filter.q && !`${t.title} ${t.artist}`.toLowerCase().includes(filter.q.toLowerCase())) return false;
      return true;
    });
  }, [tracks, filter]);

  const allLangs = useMemo(() => {
    return Array.from(new Set(tracks.map(t => t.language_confidence).filter(Boolean))).sort();
  }, [tracks]);

  return (
    <div style={{display: "flex", minHeight: "100vh"}}>
      <AdminSubNav />
      <div className="bigfm-shell" style={{flex: 1, minWidth: 0}}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <header className="bigfm-header" data-testid="admin-header">
        <div className="bigfm-logo">
          <span className="dot" />
          <BigFmBrand variant="lockup" testId="admin-brand" />
          <span className="badge mono">ADMIN · CATALOG</span>
        </div>
        <div className="bigfm-tag">
          <div className="tag-line mono">{tracks.length} TRACKS · AUTO-TAGGED</div>
          <Link to="/" className="back-link" data-testid="back-to-radio-link">← Back to Radio</Link>
        </div>
      </header>

      <div className="panel" data-testid="upload-panel">
        <div className="panel-title">
          <h2><Upload size={16} style={{display:"inline",marginRight:8,verticalAlign:-2}}/>Upload tracks</h2>
          <span className="hint">SINGLE · BULK · CSV</span>
        </div>
        <div className="upload-twin">
          <SingleUploader onUploaded={onUploaded} />
          <BulkUploader onUploaded={onUploaded} />
        </div>
      </div>

      <div className="panel" data-testid="library-panel">
        <div className="panel-title">
          <h2><Disc3 size={16} style={{display:"inline",marginRight:8,verticalAlign:-2}}/>Catalog</h2>
          <span className="hint">{filtered.length} / {tracks.length}</span>
        </div>

        <div className="filters" data-testid="library-filters">
          <input className="filter-q" placeholder="Search title or artist…"
                 value={filter.q} onChange={(e)=>setFilter(f=>({...f,q:e.target.value}))}
                 data-testid="filter-q" />
          <select value={filter.energy} onChange={(e)=>setFilter(f=>({...f,energy:e.target.value}))}
                  data-testid="filter-energy">
            <option value="all">All energies</option>
            {ENERGY_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <select value={filter.mood} onChange={(e)=>setFilter(f=>({...f,mood:e.target.value}))}
                  data-testid="filter-mood">
            <option value="all">All moods</option>
            {MOOD_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <select value={filter.lang} onChange={(e)=>setFilter(f=>({...f,lang:e.target.value}))}
                  data-testid="filter-lang">
            <option value="all">All languages</option>
            {allLangs.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        </div>

        <div className="track-table-wrap">
          <table className="track-table" data-testid="track-table">
            <thead>
              <tr>
                <th></th>
                <th>Track</th>
                <th>Dur</th>
                <th>Energy</th>
                <th>Mood</th>
                <th>Lang</th>
                <th>BPM</th>
                <th>Vibe tags</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <TrackRow key={t.id} t={t} onRetag={onRetag} onPatch={onPatch}
                          retagging={retagging} onPreview={onPreview}
                          onDelete={onDelete} playingId={playingId} />
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={9} className="empty-row" data-testid="library-empty">No tracks match your filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {deleteCandidate && (
        <div className="modal-backdrop" data-testid="delete-modal-backdrop" role="dialog" aria-modal="true">
          <div className="modal-card">
            <div className="modal-icon"><AlertTriangle size={20} /></div>
            <h3>Delete "{deleteCandidate.title}"?</h3>
            <p>
              This removes the file and the catalog entry. Cannot be undone.
              {deleteCandidate.artist && <> Artist: <b>{deleteCandidate.artist}</b>.</>}
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="modal-btn ghost"
                disabled={deleting}
                onClick={() => setDeleteCandidate(null)}
                data-testid="cancel-delete-btn"
              >
                Cancel
              </button>
              <button
                type="button"
                className="modal-btn danger"
                disabled={deleting}
                onClick={confirmDelete}
                data-testid="confirm-delete-btn"
              >
                {deleting ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <footer className="bigfm-foot">
        <span>RADIOLIFE · ADMIN · {user?.email}</span>
        <span>PHASE 1 · PERSONALIZED RADIO</span>
      </footer>
      </div>
    </div>
  );
}
