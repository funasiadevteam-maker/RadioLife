// Phase 22b — Bulk Music Upload (admin). Multi-ZIP + mixed selection.
//
// Single staging pool now accepts ANY combination of audio files + ZIP
// archives. The 22a "ZIP MODE vs MULTI-FILE MODE" auto-detect indicator
// is gone. Result panel groups ZIP-extracted entries under their archive
// name and renders a one-line headline ("Uploaded N tracks from K ZIPs +
// M loose files (X duplicates skipped)").

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Upload, FolderUp, FileArchive, Music, Loader2, CheckCircle2,
  Recycle, AlertTriangle, XCircle, ArrowLeft,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API } from "@/AuthContext";
import AdminSubNav from "@/AdminSubNav";
import AdminBulkUploadHistory, { MyRecentUploadsWidget }
              from "@/AdminBulkUploadHistory";

const ACCEPT = ".mp3,.wav,.m4a,.flac,.ogg,.zip,audio/*";
const isZipName = (n) => /\.zip$/i.test(n || "");

// Bulk uploads are chunked into small requests so a large batch never exceeds
// the platform's ingress request timeout (which killed big single-request
// uploads mid-transfer on normal upload bandwidth). Each request stays small.
const BATCH_MAX_FILES = 12;
const BATCH_MAX_BYTES = 30 * 1024 * 1024;   // 30 MB per request — safe on slow uplinks

function makeBatches(files) {
  const batches = [];
  let cur = [], curBytes = 0;
  for (const f of files) {
    const sz = f.size || 0;
    if (cur.length && (cur.length >= BATCH_MAX_FILES ||
                       curBytes + sz > BATCH_MAX_BYTES)) {
      batches.push(cur); cur = []; curBytes = 0;
    }
    cur.push(f); curBytes += sz;
  }
  if (cur.length) batches.push(cur);
  return batches;
}

const fmtBytes = (b) => {
  if (!b) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = b, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(v < 10 && i ? 1 : 0)} ${units[i]}`;
};

function StatusBadge({ status }) {
  const map = {
    uploaded:           { Icon: CheckCircle2,    color: "#22c55e", label: "uploaded" },
    duplicate:           { Icon: Recycle,            color: "#f59e0b", label: "duplicate" },
    skipped_non_audio: { Icon: AlertTriangle,  color: "#f59e0b", label: "skipped" },
    failed:                 { Icon: XCircle,            color: "#ef4444", label: "failed" },
  };
  const m = map[status] || map.failed;
  return (
    <span data-testid={`bulk-status-${status}`}
                style={{display: "inline-flex", alignItems: "center", gap: 4,
                            padding: "2px 6px", borderRadius: 4, fontSize: 11,
                            fontFamily: "monospace",
                            background: `${m.color}22`, color: m.color}}>
      <m.Icon size={11} /> {m.label}
    </span>
  );
}

function ResultRow({ it, indent }) {
  return (
    <tr data-testid={`bulk-result-row-${it.filename}`}
            style={{borderTop: "1px solid rgba(255,255,255,0.04)",
                        background: indent ? "rgba(255,255,255,0.015)" : "transparent"}}>
      <td style={{padding: 6, paddingLeft: indent ? 28 : 6}}>
        {indent && <span style={{color: "#666", marginRight: 4}}>↳</span>}
        {it.filename}
      </td>
      <td style={{padding: 6}}><StatusBadge status={it.status}/></td>
      <td style={{padding: 6}}>{it.title || "—"}</td>
      <td style={{padding: 6}}>{it.artist || "—"}</td>
      <td style={{padding: 6}}>
        {typeof it.duration_sec === "number"
          ? `${Math.round(it.duration_sec)}s` : "—"}
      </td>
      <td style={{padding: 6}}>
        {it.track_id && (
          <Link to={`/admin/tracks/${it.track_id}`}
                      data-testid={`open-track-${it.track_id}`}
                      style={{color: "#f59e0b"}}>open →</Link>
        )}
        {it.existing_track_id && (
          <Link to={`/admin/tracks/${it.existing_track_id}`}
                      data-testid={`existing-track-${it.existing_track_id}`}
                      style={{color: "#9aa3af"}}>existing →</Link>
        )}
        {it.reason && (
          <span style={{color: "#ef4444"}} title={it.reason}>
            {String(it.reason).slice(0, 40)}
          </span>
        )}
      </td>
    </tr>
  );
}

export default function AdminBulkUpload() {
  const [staged, setStaged] = useState([]);   // File[]
  const [defaults, setDefaults] = useState({
    language: "", genre: "", era: "", channel_eligibility: "on_air",
  });
  const [limits, setLimits] = useState({
    max_files: 100, max_bytes: 500 * 1024 * 1024,
    max_extracted_files: 1000, max_zip_entries: 500,
  });
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);   // { done, total } while uploading
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("upload");   // Phase 22g — upload | history
  const fileRef = useRef(null);

  useEffect(() => {
    axios.get(`${API}/admin/tracks/bulk-upload/limits`)
        .then((r) => setLimits((prev) => ({...prev, ...r.data})))
        .catch(() => {/* defaults already set */});
  }, []);

  const totalBytes = useMemo(() =>
    staged.reduce((acc, f) => acc + (f.size || 0), 0), [staged]);

  const counts = useMemo(() => {
    const zips    = staged.filter((f) => isZipName(f.name)).length;
    const loose = staged.length - zips;
    return { zips, loose };
  }, [staged]);

  const stage = useCallback((files) => {
    const arr = Array.from(files || []);
    if (!arr.length) return;
    if (arr.length > limits.max_files) {
      toast.error(`Too many files: limit is ${limits.max_files}`); return;
    }
    setStaged(arr);
    setResult(null);
  }, [limits.max_files]);

  const onDrop = (e) => {
    e.preventDefault();
    stage(e.dataTransfer.files);
  };

  const submit = async () => {
    if (!staged.length) { toast.warning("Stage at least one file"); return; }
    if (totalBytes > limits.max_bytes) {
      toast.error(`Total ${fmtBytes(totalBytes)} exceeds ${fmtBytes(limits.max_bytes)}`);
      return;
    }

    // Snapshot staged file sizes (for the dedupe MB-saved report) before we
    // clear the pool.
    const sizeByName = {};
    staged.forEach((f) => { sizeByName[f.name] = f.size || 0; });

    // Split into small requests so no single upload exceeds the ingress
    // timeout, then aggregate every batch's result into one summary.
    const batches = makeBatches(staged);

    setBusy(true);
    setResult(null);
    setProgress({ done: 0, total: batches.length });

    const agg = {
      ok: true, uploaded: 0, duplicates: 0, skipped_non_audio: 0, failed: 0,
      zip_archives_processed: 0, audio_files_direct: 0,
      audio_files_extracted_from_zip: 0, items: [],
      duplicates_skipped_details: [], job_ids: [],
    };
    let anyBatchError = false;

    for (let bi = 0; bi < batches.length; bi += 1) {
      const fd = new FormData();
      batches[bi].forEach((f) => fd.append("files", f));
      if (defaults.language) fd.append("default_language", defaults.language);
      if (defaults.genre)       fd.append("default_genre", defaults.genre);
      if (defaults.era)           fd.append("default_era", defaults.era);
      if (defaults.channel_eligibility)
          fd.append("channel_eligibility", defaults.channel_eligibility);
      try {
        const r = await axios.post(`${API}/admin/tracks/bulk-upload`, fd, {
          headers: {"Content-Type": "multipart/form-data"},
          timeout: 300000,
        });
        const d = r.data || {};
        agg.uploaded                       += d.uploaded || 0;
        agg.duplicates                    += d.duplicates || 0;
        agg.skipped_non_audio         += d.skipped_non_audio || 0;
        agg.failed                            += d.failed || 0;
        agg.zip_archives_processed  += d.zip_archives_processed || 0;
        agg.audio_files_direct           += d.audio_files_direct || 0;
        agg.audio_files_extracted_from_zip += d.audio_files_extracted_from_zip || 0;
        if (Array.isArray(d.items)) agg.items.push(...d.items);
        if (Array.isArray(d.duplicates_skipped_details))
          agg.duplicates_skipped_details.push(...d.duplicates_skipped_details);
        if (d.job_id) agg.job_ids.push(d.job_id);
      } catch (e) {
        anyBatchError = true;
        const dd = e?.response?.data?.detail;
        if (dd && typeof dd === "object" && Array.isArray(dd.items)) {
          agg.items.push(...dd.items);
          agg.failed += dd.items.filter((it) => it.status === "failed").length;
        } else {
          const reason = typeof dd === "string"
            ? dd : (dd?.code || e?.message || "upload_failed");
          batches[bi].forEach((f) => agg.items.push({
            source: "direct", filename: f.name, status: "failed", reason,
          }));
          agg.failed += batches[bi].length;
        }
      }
      setProgress({ done: bi + 1, total: batches.length });
    }

    agg.ok = agg.uploaded > 0 || !anyBatchError;
    agg._staged_size_by_name = sizeByName;
    agg.job_id = agg.job_ids[0];
    setResult(agg);

    const savedBytes = agg.duplicates_skipped_details.reduce(
      (acc, d) => acc + (sizeByName[d.file_name] || 0), 0);
    const savedMB = savedBytes / (1024 * 1024);
    const mbStr = savedMB > 0 ? ` (saved ${savedMB.toFixed(2)} MB)` : "";
    if (agg.uploaded > 0 || !anyBatchError) {
      toast.success(
        `${agg.uploaded} imported, ${agg.duplicates} duplicates auto-skipped${mbStr}`
          + (anyBatchError ? ` · ${agg.failed} failed` : ""),
        { duration: 6000 });
    } else {
      toast.error(`Upload failed — ${agg.failed} file(s) not uploaded`);
    }
    setStaged([]);
    if (fileRef.current) fileRef.current.value = "";
    setBusy(false);
    setProgress(null);
  };

  // Group the items into a render-ready stream: direct rows + per-archive
  // sections (zip summary row + nested entries).
  const renderedRows = useMemo(() => {
    if (!result?.items?.length) return [];
    const direct = result.items.filter((it) => it.source === "direct");
    const grouped = {};
    for (const it of result.items) {
      if (it.source === "zip") {
        (grouped[it.archive] = grouped[it.archive] || []).push(it);
      }
    }
    const rows = [];
    direct.forEach((it) => rows.push({ kind: "direct", it }));
    for (const [archive, entries] of Object.entries(grouped)) {
      const uploadedN  = entries.filter((e) => e.status === "uploaded").length;
      const dupN          = entries.filter((e) => e.status === "duplicate").length;
      const skippedN  = entries.filter((e) => e.status === "skipped_non_audio").length;
      const failedN    = entries.filter((e) => e.status === "failed").length;
      rows.push({ kind: "archive_header", archive,
                            summary: { uploadedN, dupN, skippedN, failedN } });
      entries.forEach((it) => rows.push({ kind: "zip_entry", it }));
    }
    return rows;
  }, [result]);

  return (
    <div style={{display: "flex", minHeight: "100vh"}}>
      <AdminSubNav />
      <div className="bigfm-shell" style={{flex: 1, minWidth: 0}}>
        <Toaster theme="dark" position="bottom-right" richColors />

        <header className="bigfm-header" data-testid="bulk-upload-header">
          <div className="bigfm-logo">
            <span className="dot" />
            <strong style={{letterSpacing: 0.5}}>FUUSIC</strong>
            <span className="badge mono">ADMIN · BULK UPLOAD</span>
          </div>
          <div className="bigfm-tag">
            <div className="tag-line mono">
              max {limits.max_files} files · {fmtBytes(limits.max_bytes)} ·
              {" "}max {limits.max_extracted_files} extracted ·
              {" "}{limits.max_zip_entries}/zip
            </div>
            <Link to="/admin" className="back-link" data-testid="back-to-catalog-link">
              <ArrowLeft size={12}/> Back to Catalog
            </Link>
          </div>
        </header>

        {/* Phase 22g — Job History tab + own-recent widget. */}
        <div data-testid="bulk-upload-tabs"
                style={{display: "flex", gap: 8, marginBottom: 12,
                            borderBottom: "1px solid rgba(255,255,255,0.06)"}}>
          {[["upload", "New Upload"], ["history", "Job History"]].map(([k, label]) => (
            <button key={k}
                            onClick={() => setTab(k)}
                            data-testid={`tab-${k}`}
                            style={{padding: "8px 14px", fontSize: 13,
                                        background: "transparent",
                                        color: tab === k ? "#f59e0b" : "#9aa3af",
                                        border: 0,
                                        borderBottom: tab === k
                                            ? "2px solid #f59e0b"
                                            : "2px solid transparent",
                                        cursor: "pointer", fontWeight: tab === k ? 600 : 400}}>
              {label}
            </button>
          ))}
        </div>

        {tab === "history" ? (
          <AdminBulkUploadHistory />
        ) : (
          <div data-testid="bulk-upload-tab-content">
            <MyRecentUploadsWidget />
            <div className="panel" data-testid="bulk-upload-panel">
          <div className="panel-title">
            <h2><Upload size={16} style={{display:"inline",marginRight:8,
                                                          verticalAlign:-2}}/>
                  Bulk upload</h2>
            <span className="hint mono">
              {counts.loose} audio · {counts.zips} zip
            </span>
          </div>

          <div data-testid="bulk-defaults-row"
                      style={{display: "grid", gap: 10, marginBottom: 14,
                                  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))"}}>
            {[
              ["language", "default-language-input", "e.g. english, hindi"],
              ["genre",       "default-genre-input",      "e.g. pop, bollywood"],
              ["era",          "default-era-input",          "e.g. 2020s"],
              ["channel_eligibility", "channel-eligibility-input", "on_air,retro_lounge"],
            ].map(([key, tid, ph]) => (
              <label key={key} className="mono"
                          style={{fontSize: 11, color: "#9aa3af"}}>
                {key === "channel_eligibility" ? "channel eligibility (CSV slugs)" :
                  `default ${key}`}
                <input data-testid={tid} type="text" placeholder={ph}
                            value={defaults[key]}
                            onChange={(e) => setDefaults(d =>
                              ({...d, [key]: e.target.value}))}
                            style={inputStyle}/>
              </label>
            ))}
          </div>

          <div data-testid="bulk-dropzone"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={onDrop}
                      onClick={() => fileRef.current?.click()}
                      style={dropzoneStyle}>
            <FolderUp size={28} />
            <p style={{margin: "8px 0 4px", fontWeight: 600}}>
              Drop audio + ZIPs here, or click to choose
            </p>
            <p style={{margin: 0, fontSize: 11, color: "#9aa3af"}}>
              Any combination of .mp3 .wav .m4a .flac .ogg .zip in a single
              request.
            </p>
            <input ref={fileRef} type="file" accept={ACCEPT} multiple
                        onChange={(e) => stage(e.target.files)}
                        style={{display: "none"}}
                        data-testid="bulk-file-input" />
          </div>

          {staged.length > 0 && (
            <div data-testid="staged-list"
                        style={{marginTop: 12, fontFamily: "monospace", fontSize: 12}}>
              <div style={{color: "#9aa3af", marginBottom: 6}}>
                staged: {staged.length} item{staged.length === 1 ? "" : "s"} ·{" "}
                {fmtBytes(totalBytes)} · {counts.loose} loose + {counts.zips} ZIP
              </div>
              <ul style={{margin: 0, padding: 0, listStyle: "none",
                                  maxHeight: 220, overflowY: "auto",
                                  border: "1px solid rgba(255,255,255,0.06)",
                                  borderRadius: 4}}>
                {staged.map((f, i) => {
                  const isZip = isZipName(f.name);
                  return (
                    <li key={i} data-testid={`staged-item-${i}`}
                          style={{padding: "4px 8px",
                                      borderTop: i ? "1px solid rgba(255,255,255,0.04)" : "none",
                                      display: "flex", justifyContent: "space-between"}}>
                      <span style={{display: "inline-flex", gap: 4,
                                                alignItems: "center"}}>
                        {isZip ? <FileArchive size={12} color="#f59e0b"/>
                                      : <Music size={12} color="#60a5fa"/>}
                        {" "}{f.name}
                      </span>
                      <span style={{color: "#9aa3af"}}>{fmtBytes(f.size)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          <div style={{marginTop: 14, display: "flex", gap: 8, alignItems: "center"}}>
            <button data-testid="submit-bulk-upload-btn"
                          disabled={busy || !staged.length}
                          onClick={submit}
                          className="btn"
                          style={{background: busy ? "#444" : "#f59e0b",
                                      color: "#000", padding: "8px 14px",
                                      border: "none", borderRadius: 4,
                                      cursor: busy ? "wait" : "pointer",
                                      fontWeight: 700,
                                      opacity: staged.length ? 1 : 0.4}}>
              {busy ? <Loader2 size={14} className="spin"/> : <Upload size={14}/>}
              {" "}{busy
                      ? (progress ? `Uploading ${progress.done}/${progress.total}…` : "Uploading…")
                      : `Upload ${staged.length || ""}`}
            </button>
            {busy && (
              <span data-testid="bulk-upload-busy" className="mono"
                          style={{color: "#9aa3af", fontSize: 11}}>
                {progress
                  ? `uploading batch ${progress.done} of ${progress.total} — tagging + storing…`
                  : "processing — extracting ZIPs + tagging…"}
              </span>
            )}
          </div>
        </div>

        {result && (
          <div className="panel" data-testid="bulk-upload-results">
            <div className="panel-title">
              <h2><CheckCircle2 size={16}
                                                  style={{display:"inline",marginRight:8,
                                                              verticalAlign:-2}}/>
                    Result</h2>
              <span className="hint mono" data-testid="bulk-result-headline">
                Uploaded {result.uploaded} tracks from{" "}
                {result.zip_archives_processed || 0} ZIP
                {(result.zip_archives_processed || 0) === 1 ? "" : "s"} +{" "}
                {result.audio_files_direct || 0} loose
                {result.duplicates ? ` (${result.duplicates} duplicates skipped)` : ""}
              </span>
            </div>

            {/* Phase 22e — collapsible duplicate-details panel. Lists up
                  to 20 files with their matched_rule + matched track name
                  so admins instantly see why each was skipped. */}
            {(result.duplicates_skipped_details
                  && result.duplicates_skipped_details.length > 0) && (
              <details data-testid="bulk-duplicates-details" open={false}
                              style={{margin: "0 0 14px",
                                          background: "rgba(245,158,11,0.05)",
                                          border: "1px solid rgba(245,158,11,0.2)",
                                          borderRadius: 4, padding: "8px 12px"}}>
                <summary data-testid="bulk-duplicates-details-toggle"
                                  style={{cursor: "pointer", fontFamily: "monospace",
                                              fontSize: 12, color: "#f59e0b"}}>
                  <Recycle size={12} style={{display: "inline",
                                                                  verticalAlign: -2,
                                                                  marginRight: 4}}/>
                  Show{" "}
                  {Math.min(result.duplicates_skipped_details.length, 20)}
                  {" "}duplicate
                  {result.duplicates_skipped_details.length === 1 ? "" : "s"}
                  {" "}auto-skipped
                </summary>
                <table data-testid="bulk-duplicates-details-table"
                              style={{width: "100%", marginTop: 8,
                                          borderCollapse: "collapse",
                                          fontFamily: "monospace", fontSize: 11}}>
                  <thead>
                    <tr style={{color: "#9aa3af", textAlign: "left"}}>
                      <th style={{padding: "4px 6px"}}>file</th>
                      <th style={{padding: "4px 6px"}}>matched_rule</th>
                      <th style={{padding: "4px 6px"}}>matched track</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.duplicates_skipped_details.slice(0, 20)
                            .map((d, i) => {
                      const sz = result._staged_size_by_name
                                              ? (result._staged_size_by_name[d.file_name] || 0)
                                              : 0;
                      return (
                      <tr key={i}
                              data-testid={`bulk-duplicate-row-${d.file_name}`}
                              style={{borderTop: "1px solid rgba(255,255,255,0.04)"}}>
                        <td style={{padding: "4px 6px"}}>
                          {d.file_name}
                          {sz > 0 && (
                            <span data-testid={`bulk-duplicate-size-${d.file_name}`}
                                          style={{color: "#9aa3af", marginLeft: 6}}>
                              ({fmtBytes(sz)})
                            </span>
                          )}
                        </td>
                        <td style={{padding: "4px 6px", color: "#f59e0b"}}>
                          {d.matched_rule}
                        </td>
                        <td style={{padding: "4px 6px", color: "#9aa3af"}}>
                          {d.matched_track_title || "—"}
                          {d.matched_track_artist
                            ? ` · ${d.matched_track_artist}` : ""}
                        </td>
                      </tr>
                      );
                    })}
                    {result.duplicates_skipped_details.length > 20 && (
                      <tr><td colSpan={3}
                                      style={{padding: "6px",
                                                  color: "#9aa3af",
                                                  fontStyle: "italic"}}>
                        +{result.duplicates_skipped_details.length - 20}
                        {" "}more (audit row at job_id={result.job_id}
                        {" "}has the full list)
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </details>
            )}

            <table data-testid="bulk-upload-results-table"
                          style={{width: "100%", borderCollapse: "collapse",
                                      fontFamily: "monospace", fontSize: 12}}>
              <thead>
                <tr style={{textAlign: "left", color: "#9aa3af"}}>
                  <th style={{padding: 6}}>file</th>
                  <th style={{padding: 6}}>status</th>
                  <th style={{padding: 6}}>title</th>
                  <th style={{padding: 6}}>artist</th>
                  <th style={{padding: 6}}>duration</th>
                  <th style={{padding: 6}}></th>
                </tr>
              </thead>
              <tbody>
                {renderedRows.map((row, idx) => {
                  if (row.kind === "direct") {
                    return <ResultRow key={`d-${idx}`} it={row.it}/>;
                  }
                  if (row.kind === "archive_header") {
                    return (
                      <tr key={`a-${idx}`}
                              data-testid={`bulk-archive-${row.archive}`}
                              style={{borderTop: "1px solid rgba(245,158,11,0.2)",
                                          background: "rgba(245,158,11,0.06)"}}>
                        <td colSpan={6} style={{padding: "6px 8px",
                                                                  color: "#f59e0b",
                                                                  fontWeight: 700}}>
                          <FileArchive size={12} style={{marginRight: 6,
                                                                                  verticalAlign: -2}}/>
                          {row.archive}{" "}
                          <span style={{color: "#9aa3af", fontWeight: 400}}>
                            · {row.summary.uploadedN}↑
                            {" "}· {row.summary.dupN}♻
                            {" "}· {row.summary.skippedN}⚠
                            {" "}· {row.summary.failedN}✗
                          </span>
                        </td>
                      </tr>
                    );
                  }
                  return <ResultRow key={`z-${idx}`} it={row.it} indent />;
                })}
              </tbody>
            </table>
          </div>
        )}
          </div>
        )}
      </div>
    </div>
  );
}

const inputStyle = {
  display: "block", marginTop: 4, width: "100%",
  padding: "6px 8px",
  background: "#0a0a0c", border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 4, color: "#e7e7ea", fontFamily: "monospace", fontSize: 12,
};

const dropzoneStyle = {
  border: "2px dashed rgba(245,158,11,0.4)",
  borderRadius: 6, padding: "24px 16px", textAlign: "center",
  cursor: "pointer", background: "rgba(245,158,11,0.04)",
  color: "#e7e7ea", transition: "background 120ms",
};
