/**
 * Phase 36c Stage 1 — Solo Audio Recording Studio.
 *
 * Routes:
 *   /creator/studio/new       — channel picker + title + recording_mode + Start
 *   /creator/studio/:sid       — live studio panel (mic, level meter, timer, record)
 *
 * Stage 1 scope: solo audio only. 10-min cap. Single active session
 * platform-wide (server enforces disk_constrained 409 if another is active).
 * Transcode-and-delete-source server-side (uploaded webm → mp3 → source gone).
 *
 * GlobalAudio safety: imperatively pause via the public window.bigfmAudio
 * helper at session start; restore on exit. Does NOT touch GlobalAudio source.
 */
import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import ConnectionQualityPill, {
  usePollConnectionQuality,
} from "./components/ConnectionQualityPill";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const RECORDING_CAP_SEC = 600;    // 10 min — must match backend
const WARN_AT_SEC                = 540;    // 9 min warning

const fmt = (s) => {
  s = Math.max(0, Math.floor(s));
  return `${Math.floor(s/60)}:${String(s%60).padStart(2, "0")}`;
};

const pickMimeType = () => {
  // Prefer Chromium/Firefox opus; fallback to Safari mp4a.
  const cands = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  if (typeof MediaRecorder === "undefined") return cands[0];
  for (const t of cands) if (MediaRecorder.isTypeSupported(t)) return t;
  return cands[0];
};

// ──────────────────────────────────────────────────────────────────
//  /creator/studio/new — picker + start
// ──────────────────────────────────────────────────────────────────
export function StudioNew() {
  const nav = useNavigate();
  const [meCreator, setMeCreator] = useState(null);
  const [channels, setChannels] = useState([]);
  const [nextRoute, setNextRoute] = useState(null);
  const [channelId, setChannelId] = useState("");
  const [title, setTitle] = useState("");
  const [lkMock, setLkMock]    = useState(true);
  const [busy, setBusy]            = useState(false);
  const [err, setErr]                 = useState("");
  // Phase 36c Stage 4 polish — pre-record control row + device picker.
  // The session row is created with these values; backend has no PATCH route,
  // so the live Studio screen shows them read-only (locked once started).
  const [videoEnabled, setVideoEnabled] = useState(false);
  const [gridLayout, setGridLayout]        = useState("auto");
  const [camQuality, setCamQuality]      = useState("1080p");    // 720p|1080p, client-side
  const [devices, setDevices]                  = useState({cams: [], mics: []});
  const [camDeviceId, setCamDeviceId]   = useState("");
  const [micDeviceId, setMicDeviceId]   = useState("");
  const [permState, setPermState]          = useState("idle");    // idle|granted|denied

  useEffect(() => {
    (async () => {
      // Phase 36c Stage 1 bug fix — explicit 2-step creator→channels flow.
      // Step 1: resolve current user's creator profile.
      let creator = null;
      try {
        const cr = await axios.get(`${API}/podcasts/creators/me`,
                                                  {withCredentials: true});
        creator = cr.data.creator || null;
      } catch (_) { /* 401/500 → treat as no creator */ }
      if (!creator || creator.application_status !== "approved") {
        setMeCreator(null);
        setChannels([]);
        setNextRoute("/creator/apply");
      } else {
        setMeCreator(creator);
        // Step 2: fetch this creator's channels and filter approved+active client-side.
        try {
          const chr = await axios.get(
            `${API}/podcasts/creators/${creator.id}/channels`,
            {withCredentials: true});
          const active = (chr.data.channels || []).filter(
            (c) => c.approval_status === "approved" && c.active);
          setChannels(active);
          if (active.length) {
            setChannelId(active[0].id);
            setNextRoute(null);
          } else {
            setNextRoute("/creator/podcasts/new");
          }
        } catch (_) {
          setChannels([]);
          setNextRoute("/creator/podcasts/new");
        }
      }
      try {
        const s = await axios.get(`${API}/admin/podcasts/integrations/livekit/status`,
                                                  {withCredentials: true});
        setLkMock(!s.data.is_live);
      } catch (_) { /* non-admins fall through; default mock */ }
    })();
  }, []);

  const start = async () => {
    if (!meCreator?.id) { setErr("No creator profile"); return; }
    if (!channelId) { setErr("Pick a channel"); return; }
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/podcasts/creators/${meCreator.id}/recording-sessions`,
        {channel_id: channelId, title: title || "Untitled",
          recording_mode: "solo",
          video_enabled: !!videoEnabled,
          grid_layout: gridLayout},
        {withCredentials: true});
      // Persist the device + quality preferences so the live Studio
      // screen can apply them at getUserMedia() time.
      try {
        sessionStorage.setItem("bigfm.studio.prefs", JSON.stringify({
          camDeviceId, micDeviceId,
          camQuality, videoEnabled: !!videoEnabled}));
      } catch (_) { /* SS unavailable in private mode → no-op */ }
      nav(`/creator/studio/${r.data.session_id}`);
    } catch (e) {
      setErr(e?.response?.data?.detail?.message
                  || e?.response?.data?.detail
                  || e.message);
    } finally { setBusy(false); }
  };

  // Pre-flight device enumeration. Browsers return empty `label` until
  // permission is granted, so we expose a "Grant access" button that
  // triggers a tiny getUserMedia prompt then re-enumerates.
  const enumerate = async () => {
    try {
      const list = await navigator.mediaDevices.enumerateDevices();
      const cams = list.filter((d) => d.kind === "videoinput");
      const mics = list.filter((d) => d.kind === "audioinput");
      setDevices({cams, mics});
      if (!camDeviceId && cams[0]) setCamDeviceId(cams[0].deviceId);
      if (!micDeviceId && mics[0]) setMicDeviceId(mics[0].deviceId);
    } catch (_) { /* enumerate is best-effort */ }
  };
  const grantAccess = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({audio: true, video: true});
      s.getTracks().forEach((t) => t.stop());
      setPermState("granted");
      await enumerate();
    } catch (_) { setPermState("denied"); }
  };
  useEffect(() => { enumerate(); }, []);    // populate on mount; labels empty until grant

  return (
    <div data-testid="studio-new"
            style={{padding: 24, color: "#e7e7ea", background: "#0a0a0c",
                        minHeight: "100vh"}}>
      <Link to="/creator" style={{color: "#9aa3af", fontSize: 12,
                                                          textDecoration: "none"}}>← Back to Creator</Link>
      <h1 style={{fontSize: 28, fontWeight: 700, marginTop: 6}}>Studio</h1>
      <div data-testid="poc-banner"
              style={{margin: "10px 0", padding: 10, borderRadius: 8,
                          background: "rgba(245,158,11,0.1)",
                          border: "1px solid rgba(245,158,11,0.3)",
                          color: "#fbbf24", fontSize: 13}}>
        Solo audio only for now — guests + video coming next.
        10-min cap. Studio is single-session: one creator at a time.
      </div>
      {lkMock && (
        <div data-testid="livekit-mock-banner"
                style={{margin: "10px 0", padding: 10, borderRadius: 8,
                            background: "rgba(245,158,11,0.1)",
                            border: "1px solid rgba(245,158,11,0.4)",
                            color: "#fbbf24", fontSize: 12}}>
          ⚠ LiveKit in <b>MOCK mode</b>. Recording works locally; multi-guest
          rooms unavailable until <code>LIVEKIT_API_KEY/SECRET/URL</code> land.
        </div>
      )}
      <div style={{background: "#13131a", borderRadius: 12, padding: 20,
                            border: "1px solid rgba(255,255,255,0.06)",
                            maxWidth: 540, marginTop: 14}}>
        <Field label="Channel">
          <select data-testid="channel-select" value={channelId}
                          onChange={(e) => setChannelId(e.target.value)} style={inp()}>
            {channels.length === 0 && <option value="">No approved channels yet</option>}
            {channels.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
          </select>
        </Field>
        {channels.length === 0 && nextRoute && (
          <div data-testid="studio-next-route-cta"
                  style={{margin: "4px 0 12px 0", padding: 10, borderRadius: 8,
                              background: "rgba(245,158,11,0.08)",
                              border: "1px solid rgba(245,158,11,0.25)",
                              fontSize: 13, color: "#fbbf24"}}>
            {nextRoute === "/creator/apply"
              ? <>You don't have an approved creator profile yet. <Link to={nextRoute} style={{color: "#fbbf24", fontWeight: 700}}>Apply as creator →</Link></>
              : <>You have a creator profile but no channels yet. <Link to={nextRoute} style={{color: "#fbbf24", fontWeight: 700}}>Create a channel first →</Link></>}
          </div>
        )}
        <Field label="Episode title">
          <input data-testid="studio-title-input"
                      value={title} onChange={(e) => setTitle(e.target.value)}
                      placeholder="Untitled Recording" style={inp()} />
        </Field>

        {/* Phase 36c Stage 4 polish — control row */}
        <div data-testid="studio-controls-row"
                style={{padding: 12, borderRadius: 10, marginBottom: 12,
                            background: "#0e0e14",
                            border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{fontSize: 10, textTransform: "uppercase",
                                color: "#9aa3af", letterSpacing: 0.5, marginBottom: 10}}>
            Studio settings
          </div>

          {/* Record video toggle */}
          <label style={{display: "flex", alignItems: "center", gap: 8,
                                    marginBottom: 12, cursor: "pointer", fontSize: 13}}>
            <input data-testid="record-video-toggle" type="checkbox"
                        checked={videoEnabled}
                        onChange={(e) => setVideoEnabled(e.target.checked)} />
            <span>Record video</span>
            <span style={{fontSize: 11, color: "#71717a"}}>
              (audio-only otherwise)
            </span>
          </label>

          {/* Camera quality — client-side getUserMedia constraint */}
          {videoEnabled && (
            <Field label="Camera quality">
              <select data-testid="camera-quality-select" value={camQuality}
                              onChange={(e) => setCamQuality(e.target.value)}
                              style={inp()}>
                <option value="1080p">1080p</option>
                <option value="720p">720p</option>
              </select>
              <div data-testid="camera-quality-help"
                      style={{fontSize: 11, color: "#71717a", marginTop: 4}}>
                Affects your camera capture only. Final mix is always 1080p.
              </div>
            </Field>
          )}

          {/* Grid layout — backend enum mirror */}
          <Field label="Grid layout">
            <select data-testid="grid-layout-select" value={gridLayout}
                            onChange={(e) => setGridLayout(e.target.value)}
                            style={inp()}>
              <option value="auto">▦  Auto</option>
              <option value="side_by_side">▌▐  Side-by-side</option>
              <option value="speaker_view">◉  Speaker view</option>
              <option value="2x2">⊞  2×2 grid</option>
            </select>
            <div data-testid="grid-layout-help"
                    style={{fontSize: 11, color: "#71717a", marginTop: 4}}>
              Layout switches to screen-priority automatically when anyone screen-shares.
            </div>
          </Field>

          {/* Pre-flight device picker */}
          {videoEnabled && (
            <div data-testid="device-picker"
                    style={{marginTop: 8, paddingTop: 12,
                                borderTop: "1px dashed rgba(255,255,255,0.08)"}}>
              <div style={{display: "flex", justifyContent: "space-between",
                                    alignItems: "center", marginBottom: 8}}>
                <div style={{fontSize: 10, textTransform: "uppercase",
                                      color: "#9aa3af", letterSpacing: 0.5}}>
                  Devices
                </div>
                {permState !== "granted" && (
                  <button data-testid="grant-devices-btn" onClick={grantAccess}
                                  type="button"
                                  style={{...btn("secondary"), fontSize: 11, padding: "4px 10px"}}>
                    Grant access
                  </button>
                )}
              </div>
              <Field label="Camera">
                <select data-testid="camera-device-select" value={camDeviceId}
                                onChange={(e) => setCamDeviceId(e.target.value)}
                                style={inp()}>
                  {devices.cams.length === 0 && (
                    <option value="">{permState === "denied"
                      ? "Access denied — check browser permissions"
                      : "No cameras found — click Grant access"}</option>
                  )}
                  {devices.cams.map((d, i) => (
                    <option key={d.deviceId || i} value={d.deviceId}>
                      {d.label || `Camera ${i + 1}`}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Microphone">
                <select data-testid="mic-device-select" value={micDeviceId}
                                onChange={(e) => setMicDeviceId(e.target.value)}
                                style={inp()}>
                  {devices.mics.length === 0 && (
                    <option value="">{permState === "denied"
                      ? "Access denied — check browser permissions"
                      : "No microphones found — click Grant access"}</option>
                  )}
                  {devices.mics.map((d, i) => (
                    <option key={d.deviceId || i} value={d.deviceId}>
                      {d.label || `Microphone ${i + 1}`}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Screen share source">
                <div data-testid="screen-share-affordance"
                        style={{fontSize: 12, color: "#9aa3af", padding: 8,
                                    background: "rgba(255,255,255,0.02)", borderRadius: 6,
                                    border: "1px dashed rgba(255,255,255,0.08)"}}>
                  The browser asks you to pick a window or tab when you click
                  "Share screen" inside the session.
                </div>
              </Field>
            </div>
          )}
        </div>
        {err && <div data-testid="studio-err"
                                style={{color: "#ef4444", fontSize: 12, marginBottom: 8}}>{err}</div>}
        <button data-testid="start-session-btn" onClick={start}
                        disabled={busy || !channelId} style={btn("primary")}>
          {busy ? "Starting…" : "Start Studio"}
        </button>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
//  /creator/studio/:sid — live studio panel
// ──────────────────────────────────────────────────────────────────
export default function Studio() {
  const { sid } = useParams();
  const nav = useNavigate();
  const [session, setSession] = useState(null);
  const [permState, setPermState] = useState("idle"); // idle|granted|denied
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed]        = useState(0);
  const [level, setLevel]                  = useState(0);
  const [uploading, setUploading] = useState(false);
  const [phase, setPhase]               = useState("idle"); // idle|recording|stopped|uploading|finalizing|done|error
  const [err, setErr]                          = useState("");
  const [lkMock, setLkMock]            = useState(true);

  const streamRef       = useRef(null);
  const recorderRef    = useRef(null);
  const chunksRef       = useRef([]);
  const audioCtxRef    = useRef(null);
  const analyserRef    = useRef(null);
  const rafRef               = useRef(null);
  const startedAtRef = useRef(null);
  const wasPlayingRef = useRef(false);

  // Load session.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/podcasts/recording-sessions/${sid}`,
                                                  {withCredentials: true});
        setSession(r.data);
      } catch (e) { setErr("Could not load session."); }
      try {
        const s = await axios.get(`${API}/admin/podcasts/integrations/livekit/status`,
                                                  {withCredentials: true});
        setLkMock(!s.data.is_live);
      } catch (_) {}
    })();
  }, [sid]);

  // GlobalAudio safety — pause while we have the mic open.
  useEffect(() => {
    try {
      const g = window.bigfmAudio;    // public radio control surface
      if (g && typeof g.isPlaying === "function" && g.isPlaying()) {
        wasPlayingRef.current = true;
        g.pause();
      }
    } catch (_) {}
    return () => {
      try {
        const g = window.bigfmAudio;
        if (wasPlayingRef.current && g && typeof g.resume === "function") {
          g.resume();
        }
      } catch (_) {}
    };
  }, []);

  // Mic level meter using AnalyserNode.
  const startLevelMeter = (stream) => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    audioCtxRef.current = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const a = ctx.createAnalyser(); a.fftSize = 1024;
    src.connect(a);
    analyserRef.current = a;
    const data = new Uint8Array(a.frequencyBinCount);
    const tick = () => {
      a.getByteTimeDomainData(data);
      let peak = 0;
      for (let i = 0; i < data.length; i++) {
        const v = Math.abs(data[i] - 128) / 128;
        if (v > peak) peak = v;
      }
      setLevel(peak);
      rafRef.current = requestAnimationFrame(tick);
    };
    tick();
  };

  const requestMic = async () => {
    try {
      // Phase 36c Stage 4 polish — honor StudioNew's device-picker & camera-quality
      // preferences (persisted in sessionStorage at session-create time).
      let prefs = {};
      try {
        prefs = JSON.parse(sessionStorage.getItem("bigfm.studio.prefs") || "{}");
      } catch (_) {}
      const audio = {echoCancellation: true, noiseSuppression: true,
                              autoGainControl: true, sampleRate: 48000};
      if (prefs.micDeviceId) audio.deviceId = {exact: prefs.micDeviceId};
      let video = false;
      if (prefs.videoEnabled || session?.video_enabled) {
        video = {height: prefs.camQuality === "720p" ? 720 : 1080};
        if (prefs.camDeviceId) video.deviceId = {exact: prefs.camDeviceId};
      }
      const s = await navigator.mediaDevices.getUserMedia({audio, video});
      streamRef.current = s;
      setPermState("granted");
      startLevelMeter(s);
    } catch (e) {
      setPermState("denied");
      setErr("Microphone permission denied.");
    }
  };

  // Timer tick.
  useEffect(() => {
    if (!recording) return;
    const i = setInterval(() => {
      const sec = (Date.now() - startedAtRef.current) / 1000;
      setElapsed(sec);
      if (sec >= RECORDING_CAP_SEC) stopRecording();
    }, 250);
    return () => clearInterval(i);
  }, [recording]);

  const startRecording = async () => {
    if (!streamRef.current) await requestMic();
    if (!streamRef.current) return;
    try {
      await axios.post(`${API}/podcasts/recording-sessions/${sid}/start`, {},
                                  {withCredentials: true});
    } catch (e) {
      setErr("Could not start session on server."); return;
    }
    chunksRef.current = [];
    const mime = pickMimeType();
    const r = new MediaRecorder(streamRef.current, {mimeType: mime, audioBitsPerSecond: 128000});
    r.ondataavailable = (e) => { if (e.data && e.data.size > 0) chunksRef.current.push(e.data); };
    r.onstop = () => uploadAndFinalize(mime);
    r.start(1000);    // 1s timeslices
    recorderRef.current = r;
    startedAtRef.current = Date.now();
    setRecording(true); setPhase("recording");
  };

  const stopRecording = async () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    setRecording(false); setPhase("stopped");
    try {
      await axios.post(
        `${API}/podcasts/recording-sessions/${sid}/stop`,
        {client_duration_seconds: elapsed}, {withCredentials: true});
    } catch (_) {}
  };

  const uploadAndFinalize = async (mime) => {
    setUploading(true); setPhase("uploading");
    try {
      const blob = new Blob(chunksRef.current,
        {type: mime.startsWith("audio/mp4") ? "audio/mp4" : "audio/webm"});
      const ext = mime.startsWith("audio/mp4") ? "mp4" : "webm";
      const fd = new FormData();
      fd.append("audio", blob, `host.${ext}`);
      fd.append("participant_role", "host");
      // Client-fast-fail duration hint. Server still authoritatively verifies
      // via ffprobe after transcode, so this is just a UX nicety to short-circuit
      // obviously-too-long uploads before they hit the wire.
      fd.append("client_duration_seconds", String(elapsed || 0));
      await axios.post(
        `${API}/podcasts/recording-sessions/${sid}/upload-track`, fd,
        {withCredentials: true});
      setPhase("finalizing");
      const fin = await axios.post(
        `${API}/podcasts/recording-sessions/${sid}/finalize`, {},
        {withCredentials: true});
      setPhase("done");
      // Tear down stream + meter before navigation.
      teardown();
      nav(`/creator/episodes/${fin.data.episode_id}/edit`);
    } catch (e) {
      setPhase("error");
      const c = e?.response?.data?.detail?.code;
      const m = e?.response?.data?.detail?.message;
      setErr(c === "disk_pressure"
          ? "The platform is under disk pressure — try again in 60 seconds."
          : (m || e.message || "Upload failed"));
    } finally { setUploading(false); }
  };

  const teardown = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (audioCtxRef.current) { try { audioCtxRef.current.close(); } catch (_) {} }
    if (streamRef.current)        { streamRef.current.getTracks().forEach((t) => t.stop()); }
  };

  useEffect(() => () => teardown(), []);    // unmount cleanup

  const remaining = Math.max(0, RECORDING_CAP_SEC - elapsed);
  const nearCap = elapsed >= WARN_AT_SEC;

  return (
    <div data-testid="studio-panel"
            style={{padding: 24, color: "#e7e7ea", background: "#0a0a0c",
                        minHeight: "100vh"}}>
      <Link to="/creator" style={{color: "#9aa3af", fontSize: 12,
                                                          textDecoration: "none"}}>← Back to Creator</Link>
      <h1 style={{fontSize: 24, fontWeight: 700, marginTop: 6}}>
        {session?.title || "Studio"}
      </h1>
      {lkMock && (
        <div data-testid="livekit-mock-pill"
                style={{display: "inline-block", marginTop: 6, padding: "3px 10px",
                            borderRadius: 999, background: "rgba(245,158,11,0.12)",
                            color: "#fbbf24", fontSize: 11,
                            border: "1px solid rgba(245,158,11,0.3)"}}>
          LiveKit MOCK
        </div>
      )}

      {/* Phase 36c Stage 4 polish — read-only studio-settings strip.
            Backend has no PATCH route, so once a session is created these are
            locked in. The pre-record control row on /creator/studio/new is
            where these are picked. */}
      {session && (
        <div data-testid="studio-settings-readonly"
                style={{display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10,
                            fontSize: 11, color: "#9aa3af"}}>
          <span style={pillRO()} data-testid="ro-video">
            {session.video_enabled ? "📹  Video on" : "🎙  Audio only"}
          </span>
          <span style={pillRO()} data-testid="ro-grid">
            Grid: <b style={{color: "#e7e7ea"}}>{session.grid_layout || "auto"}</b>
          </span>
          <span style={pillRO()} data-testid="ro-status">
            Status: <b style={{color: session.status === "recording" ? "#ef4444"
                                                    : session.status === "completed" ? "#22c55e"
                                                    : "#fbbf24"}}>{session.status}</b>
          </span>
          {session.status === "recording" && (
            <span style={{...pillRO(),
                                    color: "#71717a", fontStyle: "italic"}}>
              Settings locked while recording.
            </span>
          )}
        </div>
      )}

      <div style={{display: "flex", gap: 24, marginTop: 18, flexWrap: "wrap"}}>
        <section style={{flex: 1, minWidth: 320,
                                    background: "#13131a", borderRadius: 12, padding: 20,
                                    border: "1px solid rgba(255,255,255,0.06)"}}>
          {permState === "idle" && (
            <button data-testid="grant-mic-btn" onClick={requestMic} style={btn("primary")}>
              Grant microphone permission
            </button>
          )}
          {permState === "denied" && (
            <div style={{color: "#ef4444"}}>Microphone denied. Allow it in your browser and reload.</div>
          )}
          {permState === "granted" && (
            <>
              <div style={{fontSize: 10, textTransform: "uppercase",
                                    color: "#9aa3af", letterSpacing: 0.5, marginBottom: 6}}>
                Mic level
              </div>
              <div data-testid="mic-level-meter"
                      style={{height: 16, borderRadius: 8, background: "rgba(255,255,255,0.04)",
                                  overflow: "hidden", marginBottom: 12}}>
                <div style={{height: "100%",
                                      width: `${Math.min(100, level * 200)}%`,
                                      background: level > 0.5 ? "#ef4444"
                                                : level > 0.2 ? "#22c55e" : "#fbbf24",
                                      transition: "width 60ms"}} />
              </div>
              <div data-testid="recording-timer"
                      style={{fontSize: 40, fontWeight: 700, fontFamily: "monospace",
                                  color: nearCap ? "#ef4444" : "#e7e7ea", marginBottom: 4}}>
                {fmt(elapsed)} <span style={{fontSize: 14, color: "#9aa3af"}}>
                  / {fmt(RECORDING_CAP_SEC)}
                </span>
              </div>
              {nearCap && (
                <div data-testid="cap-warning"
                        style={{fontSize: 12, color: "#ef4444", marginBottom: 8}}>
                  Less than {Math.ceil(remaining)}s left — auto-stop at 10:00.
                </div>
              )}
              {!recording && phase === "idle" && (
                <button data-testid="record-btn" onClick={startRecording} style={btn("record")}>
                  ● Record
                </button>
              )}
              {recording && (
                <button data-testid="stop-btn" onClick={stopRecording} style={btn("stop")}>
                  ■ Stop
                </button>
              )}
              {phase === "uploading" && <Status testid="status-uploading">Uploading audio…</Status>}
              {phase === "finalizing" && <Status testid="status-finalizing">Finalizing episode…</Status>}
              {phase === "done"          && <Status testid="status-done" color="#22c55e">Done!</Status>}
              {phase === "error"          && <Status testid="status-error" color="#ef4444">{err || "Error"}</Status>}
            </>
          )}
        </section>

        <section style={{flex: 1, minWidth: 280,
                                    background: "#13131a", borderRadius: 12, padding: 20,
                                    border: "1px solid rgba(255,255,255,0.06)"}}>
          <h3 style={{fontSize: 14, fontWeight: 700, marginBottom: 8}}>
            Pre-roll checklist
          </h3>
          <ul style={{fontSize: 13, lineHeight: 1.7, color: "#cfd3dc",
                                marginLeft: 16, paddingLeft: 0}}>
            <li>Headphones recommended (no echo)</li>
            <li>Quiet room with minimal background noise</li>
            <li>Speak 6-8 inches from the mic</li>
            <li>Test the level meter — green = good, red = clipping</li>
            <li>10-minute cap — auto-stops at 10:00</li>
            <li>After stop: audio uploads, then 36b AI auto-transcribes the draft</li>
          </ul>
          <div style={{fontSize: 11, color: "#9aa3af", marginTop: 12}}>
            Session ID: <code>{sid}</code>
          </div>
          {session?.livekit_token && (
            <div style={{fontSize: 11, color: "#9aa3af", marginTop: 4}}>
              LiveKit room: <code>{session.livekit_room_name}</code>
            </div>
          )}
        </section>

        <GuestsAndLobbyPanel sid={sid} session={session} />
      </div>
    </div>
  );
}


// ─── Phase 36c Stage 2 — Guests + Lobby panel ─────────────────
function GuestsAndLobbyPanel({sid, session}) {
  const [invites, setInvites]            = useState([]);
  const [participants, setPart]        = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [formName, setFormName]   = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formConsent, setConsent] = useState(true);
  const [lastInviteUrl, setLastUrl] = useState("");
  const [busy, setBusy]                  = useState(false);
  const [err, setErr]                        = useState("");

  const refresh = useCallback(async () => {
    if (!sid) return;
    try {
      const r = await axios.get(`${API}/podcasts/recording-sessions/${sid}/invites`,
                                                  {withCredentials: true});
      setInvites(r.data.invites || []);
    } catch (_) {}
    try {
      const s = await axios.get(`${API}/podcasts/recording-sessions/${sid}`,
                                                  {withCredentials: true});
      setPart(s.data.participants || []);
    } catch (_) {}
  }, [sid]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);    // poll as WS-fallback
    return () => clearInterval(id);
  }, [refresh]);

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/podcasts/recording-sessions/${sid}/invite-guest`,
        {guest_name:           formName.trim(),
          guest_email:         formEmail.trim(),
          guest_phone:         formPhone.trim() || null,
          consent_required: formConsent},
        {withCredentials: true});
      setLastUrl(r.data.invite_url);
      setFormName(""); setFormEmail(""); setFormPhone("");
      await refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail?.message
                  || e?.response?.data?.detail || "Could not create invite.");
    } finally { setBusy(false); }
  };

  const cancelInvite = async (iid) => {
    await axios.post(
      `${API}/podcasts/recording-sessions/${sid}/invites/${iid}/cancel`,
      {}, {withCredentials: true});
    refresh();
  };
  const admit = async (pid) => {
    await axios.post(
      `${API}/podcasts/recording-sessions/${sid}/lobby/admit/${pid}`,
      {}, {withCredentials: true});
    refresh();
  };
  const kick = async (pid) => {
    await axios.post(
      `${API}/podcasts/recording-sessions/${sid}/lobby/kick/${pid}`,
      {}, {withCredentials: true});
    refresh();
  };
  const copy = (text) => {
    try { navigator.clipboard.writeText(text); } catch (_) {}
  };

  const inLobby     = participants.filter(p => p.role === "guest" && p.lobby_status === "lobby");
  const admittedGs = participants.filter(p => p.role === "guest" && p.lobby_status === "admitted");
  const hostP            = participants.find(p => p.role === "host");
  const activePCount = participants.filter(p =>
    ["admitted", "lobby"].includes(p.lobby_status) || p.role === "host").length;

  // Phase 36c Stage 4 polish — poll connection-quality every 5s while the
  // session is active. Hook stops on its own when active becomes false.
  const pollingActive = !!session && session.status !== "completed";
  const qualityByPid = usePollConnectionQuality(sid, pollingActive);

  return (
    <section data-testid="guests-panel" style={{flex: 1, minWidth: 320,
                                background: "#13131a", borderRadius: 12, padding: 20,
                                border: "1px solid rgba(255,255,255,0.06)"}}>
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8}}>
        <h3 style={{fontSize: 14, fontWeight: 700}}>Guests & Lobby</h3>
        <button data-testid="open-invite-modal-btn" onClick={() => setShowModal(true)}
                    disabled={activePCount >= 4} style={btn("primary")}>
          {activePCount >= 4 ? "Session full (4/4)" : "Invite guest"}
        </button>
      </div>

      {inLobby.length > 0 && (
        <div data-testid="lobby-ribbon" style={{marginBottom: 10, padding: 8, borderRadius: 8,
                                background: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.4)"}}>
          <div style={{fontSize: 11, textTransform: "uppercase", color: "#a78bfa", marginBottom: 4}}>
            {inLobby.length} guest{inLobby.length === 1 ? "" : "s"} waiting
          </div>
          {inLobby.map(p => {
            const q = qualityByPid[p.id] || {};
            return (
            <div key={p.id} data-testid={`lobby-row-${p.id}`}
                    style={{display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0"}}>
              <span style={{display: "flex", alignItems: "center", gap: 6}}>
                {p.display_name || "Anonymous"}
                <ConnectionQualityPill
                  testid={`quality-pill-${p.id}`}
                  score={q.score} rtt_ms={q.rtt_ms}
                  jitter_ms={q.jitter_ms} packet_loss_pct={q.packet_loss_pct} />
              </span>
              <div style={{display: "flex", gap: 6}}>
                <button data-testid={`admit-${p.id}`} onClick={() => admit(p.id)}
                            style={btn("primary")}>Admit</button>
                <button data-testid={`kick-${p.id}`} onClick={() => kick(p.id)}
                            style={btn("stop")}>Kick</button>
              </div>
            </div>
            );
          })}
        </div>
      )}

      {/* Phase 36c Stage 4 polish — connected tiles strip (host + admitted guests),
            each with a top-right connection-quality pill. */}
      {(hostP || admittedGs.length > 0) && (
        <div data-testid="participant-tiles" style={{marginBottom: 10}}>
          <div style={{fontSize: 11, textTransform: "uppercase", color: "#9aa3af", marginBottom: 4}}>
            Connected participants ({admittedGs.length + (hostP ? 1 : 0)} incl. host)
          </div>
          {hostP && (() => {
            const q = qualityByPid[hostP.id] || {};
            return (
              <div key={hostP.id} data-testid={`tile-host-${hostP.id}`}
                      style={{position: "relative", padding: 8, borderRadius: 6,
                                  background: "rgba(245,158,11,0.08)",
                                  border: "1px solid rgba(245,158,11,0.3)", marginBottom: 4,
                                  display: "flex", justifyContent: "space-between",
                                  alignItems: "center"}}>
                <span>● {hostP.display_name || "Host"} <span style={{color: "#fbbf24", fontSize: 11}}>host</span></span>
                <ConnectionQualityPill
                  testid={`quality-pill-${hostP.id}`}
                  score={q.score} rtt_ms={q.rtt_ms}
                  jitter_ms={q.jitter_ms} packet_loss_pct={q.packet_loss_pct} />
              </div>
            );
          })()}
          {admittedGs.map(p => {
            const q = qualityByPid[p.id] || {};
            return (
            <div key={p.id} data-testid={`connected-${p.id}`}
                    style={{position: "relative", padding: 6, borderRadius: 6,
                                background: "rgba(34,197,94,0.08)",
                                border: "1px solid rgba(34,197,94,0.3)", marginBottom: 4,
                                display: "flex", justifyContent: "space-between",
                                alignItems: "center"}}>
              <span>● {p.display_name || "Guest"} <span style={{color: "#22c55e", fontSize: 11}}>admitted</span></span>
              <ConnectionQualityPill
                testid={`quality-pill-${p.id}`}
                score={q.score} rtt_ms={q.rtt_ms}
                jitter_ms={q.jitter_ms} packet_loss_pct={q.packet_loss_pct} />
            </div>
            );
          })}
        </div>
      )}

      <div data-testid="invites-list" style={{marginTop: 8}}>
        <div style={{fontSize: 11, textTransform: "uppercase", color: "#9aa3af", marginBottom: 4}}>
          Active invites
        </div>
        {invites.length === 0 && (
          <div style={{fontSize: 12, color: "#71717a"}}>No invites yet.</div>
        )}
        {invites.map(inv => (
          <div key={inv.id} data-testid={`invite-row-${inv.id}`}
                  style={{padding: 6, borderRadius: 6, background: "#0e0e14",
                            border: "1px solid rgba(255,255,255,0.05)", marginBottom: 4,
                            display: "flex", justifyContent: "space-between", gap: 6, alignItems: "center"}}>
            <div style={{flex: 1, minWidth: 0}}>
              <div style={{fontSize: 13}}>{inv.guest_name} <span style={{color: "#71717a"}}>· {inv.guest_email}</span></div>
              <div style={{fontSize: 10,
                                    color: inv.invite_status === "accepted" ? "#22c55e"
                                              : inv.invite_status === "cancelled" ? "#ef4444"
                                              : inv.invite_status === "expired" ? "#9ca3af" : "#fbbf24"}}>
                {inv.invite_status}
              </div>
            </div>
            {(inv.invite_status === "pending" || inv.invite_status === "accepted") && (
              <>
                <button data-testid={`copy-link-${inv.id}`}
                            onClick={() => copy(`${window.location.origin}/studio/join/${inv.invite_token}`)}
                            style={{...btn("secondary"), fontSize: 11, padding: "4px 8px"}}>Copy link</button>
                <button data-testid={`cancel-invite-${inv.id}`} onClick={() => cancelInvite(inv.id)}
                            style={{...btn("stop"), fontSize: 11, padding: "4px 8px"}}>Cancel</button>
              </>
            )}
          </div>
        ))}
      </div>

      {showModal && (
        <div data-testid="invite-modal" style={{position: "fixed", inset: 0,
                                  background: "rgba(0,0,0,0.7)", display: "flex",
                                  alignItems: "center", justifyContent: "center", zIndex: 50}}>
          <div style={{background: "#13131a", padding: 24, borderRadius: 12,
                            width: 380, maxWidth: "90vw",
                            border: "1px solid rgba(255,255,255,0.1)"}}>
            <h3 style={{fontSize: 16, fontWeight: 700, marginBottom: 12}}>Invite a guest</h3>
            <Field label="Guest name *">
              <input data-testid="invite-name-input" value={formName}
                          onChange={e => setFormName(e.target.value)} style={inp()} />
            </Field>
            <Field label="Email *">
              <input data-testid="invite-email-input" type="email" value={formEmail}
                          onChange={e => setFormEmail(e.target.value)} style={inp()} />
            </Field>
            <Field label="Phone (optional)">
              <input data-testid="invite-phone-input" value={formPhone}
                          onChange={e => setFormPhone(e.target.value)} style={inp()} />
            </Field>
            <label style={{display: "flex", gap: 8, alignItems: "center", marginBottom: 8, fontSize: 13}}>
              <input data-testid="invite-consent-required" type="checkbox"
                          checked={formConsent} onChange={e => setConsent(e.target.checked)} />
              Require consent signature
            </label>
            <div style={{fontSize: 11, color: "#fbbf24", marginBottom: 8,
                                background: "rgba(245,158,11,0.1)", padding: 6, borderRadius: 6,
                                border: "1px solid rgba(245,158,11,0.3)"}}>
              Email sending is MOCKED — share the link manually after submitting.
            </div>
            {err && <div data-testid="invite-form-error" style={{color: "#ef4444", fontSize: 12, marginBottom: 6}}>{err}</div>}
            {lastInviteUrl && (
              <div data-testid="copy-link-banner" style={{padding: 8, marginBottom: 8,
                                    background: "rgba(34,197,94,0.1)", borderRadius: 6,
                                    border: "1px solid rgba(34,197,94,0.4)"}}>
                <div style={{fontSize: 11, color: "#22c55e", marginBottom: 4}}>Invite created!</div>
                <code style={{fontSize: 11, wordBreak: "break-all"}}>{lastInviteUrl}</code>
                <button onClick={() => copy(lastInviteUrl)} data-testid="copy-last-link-btn"
                            style={{...btn("primary"), fontSize: 11, padding: "4px 8px", marginTop: 6}}>
                  Copy link
                </button>
              </div>
            )}
            <div style={{display: "flex", gap: 8, justifyContent: "flex-end"}}>
              <button data-testid="invite-modal-close" onClick={() => {setShowModal(false); setLastUrl("");}} style={btn("secondary")}>Close</button>
              <button data-testid="invite-modal-submit" onClick={submit}
                          disabled={busy || !formName.trim() || !formEmail.trim()}
                          style={btn("primary")}>{busy ? "Sending…" : "Send invite"}</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

const Field = ({label, children}) => (
  <div style={{marginBottom: 12}}>
    <div style={{fontSize: 10, textTransform: "uppercase",
                          color: "#9aa3af", letterSpacing: 0.5, marginBottom: 4}}>
      {label}
    </div>
    {children}
  </div>
);

const Status = ({testid, children, color = "#fbbf24"}) => (
  <div data-testid={testid}
          style={{marginTop: 10, fontSize: 13, color}}>{children}</div>
);

const inp = () => ({width: "100%", padding: 8, borderRadius: 6,
                                      background: "#0a0a0c", color: "#e7e7ea",
                                      border: "1px solid rgba(255,255,255,0.08)", fontSize: 13});

const btn = (variant) => ({
  padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 700,
  cursor: "pointer", border: "1px solid rgba(255,255,255,0.08)",
  background: variant === "primary" ? "#f59e0b"
                  : variant === "record"  ? "#ef4444"
                  : variant === "stop"      ? "#374151"
                  : "transparent",
  color: variant === "primary" ? "#0a0a0c" : "#fff",
});

// Phase 36c Stage 4 polish — read-only pill style for the studio-settings strip.
const pillRO = () => ({
  display: "inline-block", padding: "3px 10px", borderRadius: 999,
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.08)",
  fontSize: 11, color: "#9aa3af",
});
