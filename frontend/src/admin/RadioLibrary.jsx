// Admin — Rebuild demo track library. One tap re-seeds the demo music rows and
// re-uploads any missing audio to object storage so AI radio keeps playing
// even after a fresh preview. Polls a background job for progress.
import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

const cfg = { withCredentials: true };

export default function RadioLibrary() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pollRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/rebuild-track-library/status`, cfg);
      setStatus(r.data || {});
      return r.data || {};
    } catch (e) {
      setErr("Could not load status (admin only).");
      return null;
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchStatus]);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const s = await fetchStatus();
      if (s && s.running === false) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setBusy(false);
      }
    }, 2000);
  }, [fetchStatus]);

  const rebuild = useCallback(async (force) => {
    setErr("");
    setBusy(true);
    try {
      await axios.post(`${API}/admin/rebuild-track-library${force ? "?force=true" : ""}`, {}, cfg);
      await fetchStatus();
      startPolling();
    } catch (e) {
      setErr("Failed to start rebuild.");
      setBusy(false);
    }
  }, [fetchStatus, startPolling]);

  const total = status?.total || status?.library_size || 16;
  const done = status?.done || 0;
  const pct = total ? Math.round((done / total) * 100) : 0;
  const running = !!status?.running || busy;

  return (
    <div className="max-w-2xl mx-auto px-6 py-10 text-white" data-testid="admin-radio-library">
      <h1 className="text-2xl font-black tracking-tight">Radio Track Library</h1>
      <p className="mt-2 text-sm text-white/60">
        The demo music library powers AI radio. If playback ever fails because the
        library went missing, rebuild it here — this re-seeds the track rows and
        re-uploads any missing audio to object storage in one tap.
      </p>

      <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest text-white/45">Persisted in storage</div>
            <div className="text-3xl font-black mt-1" data-testid="library-persisted">
              {status?.persisted_ok ?? "—"}<span className="text-white/40 text-lg"> / {status?.library_size ?? 16}</span>
            </div>
          </div>
          <div className={`px-3 py-1 rounded-full text-xs font-bold ${
            (status?.persisted_ok ?? 0) >= (status?.library_size ?? 16)
              ? "bg-emerald-500/20 text-emerald-300"
              : "bg-amber-500/20 text-amber-300"}`} data-testid="library-health">
            {(status?.persisted_ok ?? 0) >= (status?.library_size ?? 16) ? "Healthy" : "Needs rebuild"}
          </div>
        </div>

        {running && (
          <div className="mt-5" data-testid="rebuild-progress">
            <div className="flex justify-between text-xs text-white/60 mb-1">
              <span>Rebuilding… {done}/{total}</span>
              <span>{status?.uploaded || 0} uploaded · {status?.skipped || 0} skipped</span>
            </div>
            <div className="h-2 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full bg-violet-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {!running && status?.finished_at && (
          <div className="mt-4 text-xs text-white/50" data-testid="rebuild-last">
            Last rebuild: {status.uploaded || 0} uploaded, {status.skipped || 0} already present
            {status.error ? ` · error: ${status.error}` : ""}
          </div>
        )}

        {err && <div className="mt-4 text-xs text-rose-400" data-testid="rebuild-error">{err}</div>}

        <div className="mt-6 flex flex-wrap gap-3">
          <button type="button" onClick={() => rebuild(false)} disabled={running}
            data-testid="rebuild-btn"
            className={`h-11 px-6 rounded-full font-bold text-sm transition-colors ${
              running ? "bg-white/10 text-white/40 cursor-not-allowed"
                      : "bg-violet-500 hover:bg-violet-400 text-white"}`}>
            {running ? "Rebuilding…" : "Rebuild track library"}
          </button>
          <button type="button" onClick={() => rebuild(true)} disabled={running}
            data-testid="rebuild-force-btn"
            className="h-11 px-6 rounded-full font-bold text-sm border border-white/15 text-white/70 hover:bg-white/[0.06] disabled:opacity-40">
            Force re-upload all
          </button>
        </div>
      </div>

      <p className="text-xs text-white/40 mt-4">
        Note: AI radio also needs ffmpeg on the server (bundled in production).
        Rebuilding restores the persistent music; playback then works on any fresh environment.
      </p>
    </div>
  );
}
