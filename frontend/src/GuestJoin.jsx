// Phase 36c Stage 2 — Public guest landing page at /studio/join/:token.
// No auth required. Renders consent text, captures display name + mic check,
// then enters lobby state. Once WS broadcasts `you_have_been_admitted`, starts
// MediaRecorder. On `session_ended`, uploads the recorded track and shows a
// thank-you state.

import React, {useState, useEffect, useRef, useCallback} from "react";
import {useParams} from "react-router-dom";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

const STATES = {
  LOADING:       "loading",
  ERROR:           "error",
  CONSENT:      "consent",
  PREFLIGHT: "preflight",
  WAITING:       "waiting",
  RECORDING: "recording",
  UPLOADING: "uploading",
  ENDED:           "ended",
  KICKED:         "kicked",
};

export default function GuestJoin() {
  const {token} = useParams();
  const [stage, setStage]                  = useState(STATES.LOADING);
  const [errMsg, setErrMsg]                = useState("");
  const [invite, setInvite]                  = useState(null);
  const [displayName, setDisplayName]   = useState("");
  const [email, setEmail]                  = useState("");
  const [consentChecked, setConsent] = useState(false);
  const [micOk, setMicOk]                  = useState(null);
  const [participant, setParticipant] = useState(null);
  const [elapsed, setElapsed]            = useState(0);
  const recorderRef = useRef(null);
  const chunksRef    = useRef([]);
  const wsRef             = useRef(null);
  const tickRef         = useRef(null);

  // Step 1: fetch the public invite envelope.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/podcasts/studio/invites/${token}`);
        setInvite(r.data);
        setDisplayName(r.data.guest_name_prefilled || "");
        setEmail(r.data.guest_email_prefilled || "");
        setStage(STATES.CONSENT);
      } catch (e) {
        const code = e?.response?.status || 0;
        const msg = e?.response?.data?.detail?.message
                          || e?.response?.data?.detail
                          || (code === 410 ? "This invite has expired. Ask the host for a new one."
                                : code === 423 ? "This invite was cancelled by the host."
                                : code === 404 ? "This invite link is invalid."
                                : "Could not load this invite.");
        setErrMsg(typeof msg === "string" ? msg : "Unknown error.");
        setStage(STATES.ERROR);
      }
    })();
  }, [token]);

  // Mic pre-flight check.
  const testMic = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      stream.getTracks().forEach(t => t.stop());
      setMicOk(true);
    } catch (_) { setMicOk(false); }
  };

  // Step 2: accept the invite → enter lobby.
  const joinLobby = async () => {
    if (!displayName.trim() || displayName.trim().length < 2) {
      setErrMsg("Please enter your name (2-40 characters)."); return;
    }
    if (invite.consent_required && !consentChecked) {
      setErrMsg("You must accept the consent terms to join."); return;
    }
    // Phase 36c Stage 4 polish — route through the "Test camera & mic"
    // pre-flight panel before actually accepting the invite.
    setErrMsg("");
    setStage(STATES.PREFLIGHT);
  };

  const acceptAndJoin = async () => {
    try {
      const r = await axios.post(
        `${API}/podcasts/studio/invites/${token}/accept`,
        {display_name: displayName.trim(), email,
          consent_accepted: !!consentChecked,
          device_info: {
            browser:       navigator.userAgent,
            os:                 navigator.platform,
            sample_rate: 48000,
          }});
      setParticipant(r.data);
      setStage(STATES.WAITING);
      openWs(r.data);
    } catch (e) {
      const code = e?.response?.status;
      const msg = e?.response?.data?.detail?.message
                        || (code === 409 ? "This session is already full."
                              : "Could not join the lobby.");
      setErrMsg(typeof msg === "string" ? msg : "Unknown error.");
      setStage(STATES.CONSENT);
    }
  };

  // Step 3: WS for admit/kick/session_ended.
  const openWs = useCallback((p) => {
    if (!p) return;
    const url = `${API.replace(/^http/, "ws")}/api/podcasts/studio/${p.livekit_room_name.replace(/^bigfm-/, "")}/ws?token=${p.ws_token}`;
    let ws;
    try { ws = new WebSocket(url); } catch (_) { return; }
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      let msg = {}; try { msg = JSON.parse(ev.data); } catch (_) {}
      if (msg.type === "you_have_been_admitted") startRecording();
      else if (msg.type === "you_have_been_kicked") setStage(STATES.KICKED);
      else if (msg.type === "session_ended") finishAndUpload();
    };
    ws.onclose = () => { wsRef.current = null; };
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const mr = new MediaRecorder(stream, {mimeType: "audio/webm"});
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.start(1000);
      recorderRef.current = mr;
      setStage(STATES.RECORDING);
      tickRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch (e) {
      setErrMsg("Could not access your microphone. " + (e?.message || ""));
      setStage(STATES.ERROR);
    }
  };

  const finishAndUpload = async () => {
    if (tickRef.current) clearInterval(tickRef.current);
    const mr = recorderRef.current;
    if (!mr) { setStage(STATES.ENDED); return; }
    if (mr.state !== "inactive") {
      await new Promise((res) => { mr.onstop = res; mr.stop(); });
    }
    setStage(STATES.UPLOADING);
    try {
      const blob = new Blob(chunksRef.current, {type: "audio/webm"});
      const fd = new FormData();
      fd.append("audio", blob, "guest.webm");
      fd.append("ws_token", participant.ws_token);
      fd.append("participant_id", participant.participant_id);
      fd.append("client_duration_seconds", String(elapsed || 0));
      const sid = participant.livekit_room_name.replace(/^bigfm-/, "");
      await axios.post(`${API}/podcasts/studio/${sid}/upload-track`, fd);
    } catch (_) { /* still ended even if upload errors */ }
    setStage(STATES.ENDED);
  };

  // Render
  if (stage === STATES.LOADING) {
    return <PageShell><p data-testid="gjoin-loading">Loading invite…</p></PageShell>;
  }
  if (stage === STATES.ERROR) {
    return <PageShell><div data-testid="gjoin-error" className="text-red-400">{errMsg}</div></PageShell>;
  }
  if (stage === STATES.CONSENT) {
    return (
      <PageShell>
        <h1 className="text-2xl mb-2" data-testid="gjoin-heading">
          Joining <span className="text-violet-300">{invite.channel_title || "the show"}</span> with{" "}
          <span className="text-violet-300">{invite.host_display_name || "the host"}</span>
        </h1>
        <p className="text-zinc-400 mb-4" data-testid="gjoin-rec-title">
          Recording: <em>{invite.recording_title || "Untitled"}</em>
        </p>
        <h2 className="text-lg mt-4 mb-2">Consent</h2>
        <pre data-testid="gjoin-consent-text" className="whitespace-pre-wrap text-sm bg-zinc-900 p-3 rounded border border-zinc-800 max-h-72 overflow-auto">
          {invite.consent_text}
        </pre>
        <p className="text-xs text-zinc-500 mt-1">
          Consent version v{invite.consent_version}. The full text above is what will be saved with your signature.
        </p>
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col">
            <span className="text-xs text-zinc-400">Display name *</span>
            <input data-testid="gjoin-name-input"
                      value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                      maxLength={40} className="bg-zinc-900 border border-zinc-700 px-2 py-1 rounded" />
          </label>
          <label className="flex flex-col">
            <span className="text-xs text-zinc-400">Email {invite.guest_email_prefilled ? "" : "*"}</span>
            <input data-testid="gjoin-email-input"
                      value={email} onChange={(e) => setEmail(e.target.value)}
                      type="email" className="bg-zinc-900 border border-zinc-700 px-2 py-1 rounded" />
          </label>
        </div>
        {invite.consent_required && (
          <label className="mt-3 flex items-start gap-2 text-sm" data-testid="gjoin-consent-row">
            <input type="checkbox" data-testid="gjoin-consent-checkbox"
                      checked={consentChecked}
                      onChange={(e) => setConsent(e.target.checked)} />
            <span>I have read the consent text above and I agree to it.</span>
          </label>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button onClick={testMic} data-testid="gjoin-test-mic"
                      className="px-3 py-1 bg-zinc-800 border border-zinc-700 rounded hover:bg-zinc-700">
            Test mic
          </button>
          {micOk === true && <span className="text-green-400 text-sm">Mic OK ✓</span>}
          {micOk === false && <span className="text-red-400 text-sm">Mic blocked ✗</span>}
        </div>
        {errMsg && <div className="mt-3 text-red-400 text-sm" data-testid="gjoin-form-error">{errMsg}</div>}
        <button onClick={joinLobby} data-testid="gjoin-submit"
                    disabled={!displayName.trim() || (invite.consent_required && !consentChecked)}
                    className="mt-4 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 disabled:text-zinc-500 rounded">
          Join lobby
        </button>
      </PageShell>
    );
  }
  if (stage === STATES.PREFLIGHT) {
    return (
      <PageShell>
        <h1 className="text-xl mb-3" data-testid="gjoin-preflight-heading">
          Test camera &amp; mic
        </h1>
        <p className="text-zinc-400 text-sm mb-3">
          We&apos;ll request access, mirror your camera below, and show a
          live audio meter. Make sure both look right before joining.
        </p>
        <PreflightPanel
          onCancel={() => { setStage(STATES.CONSENT); setErrMsg(""); }}
          onJoin={acceptAndJoin} />
        {errMsg && <div className="mt-3 text-red-400 text-sm"
                                    data-testid="gjoin-preflight-error">{errMsg}</div>}
      </PageShell>
    );
  }
  if (stage === STATES.WAITING) {    return (
      <PageShell>
        <h1 className="text-xl mb-3" data-testid="gjoin-waiting-heading">
          Waiting for {invite.host_display_name || "the host"} to admit you…
        </h1>
        <p className="text-zinc-400 text-sm">
          You can adjust your microphone or test your setup in the meantime.
        </p>
        <div className="mt-4 px-3 py-2 bg-zinc-900 border border-zinc-800 rounded inline-block">
          Lobby status: <span className="text-violet-300" data-testid="gjoin-lobby-status">lobby</span>
        </div>
      </PageShell>
    );
  }
  if (stage === STATES.RECORDING) {
    return (
      <PageShell>
        <h1 className="text-xl mb-3 flex items-center gap-2" data-testid="gjoin-recording-heading">
          <span className="inline-block w-3 h-3 rounded-full bg-red-500 animate-pulse"></span>
          RECORDING
        </h1>
        <p className="text-zinc-400 text-sm">
          You are live. Speak naturally. {invite.host_display_name || "The host"} will end the session when finished.
        </p>
        <div className="mt-4 text-3xl font-mono" data-testid="gjoin-elapsed">
          {Math.floor(elapsed/60).toString().padStart(2,"0")}:{(elapsed%60).toString().padStart(2,"0")}
        </div>
      </PageShell>
    );
  }
  if (stage === STATES.UPLOADING) {
    return <PageShell><p data-testid="gjoin-uploading">Uploading your recording…</p></PageShell>;
  }
  if (stage === STATES.ENDED) {
    return <PageShell><p data-testid="gjoin-ended">Thanks! Your recording is uploaded. You can close this tab.</p></PageShell>;
  }
  if (stage === STATES.KICKED) {
    return <PageShell><p data-testid="gjoin-kicked" className="text-red-400">You have been removed from this session.</p></PageShell>;
  }
  return null;
}


function PageShell({children}) {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-8">
      <div className="max-w-2xl mx-auto" data-testid="gjoin-shell">
        <header className="mb-6">
          <div className="text-xs text-zinc-500 tracking-widest uppercase">BigFM Studio · Guest</div>
        </header>
        {children}
      </div>
    </div>
  );
}


// Phase 36c Stage 4 polish — guest pre-flight panel (camera mirror + VU meter).
function PreflightPanel({onCancel, onJoin}) {
  const videoRef = React.useRef(null);
  const audioCtxRef = React.useRef(null);
  const rafRef = React.useRef(null);
  const streamRef = React.useRef(null);
  const [state, setState] = React.useState("idle");    // idle|granted|denied|empty
  const [level, setLevel] = React.useState(0);

  const stop = React.useCallback(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (audioCtxRef.current) { try { audioCtxRef.current.close(); } catch (_) {} }
    if (streamRef.current)        { streamRef.current.getTracks().forEach((t) => t.stop()); }
  }, []);

  React.useEffect(() => {
    (async () => {
      try {
        const list = await navigator.mediaDevices.enumerateDevices();
        const cams = list.filter((d) => d.kind === "videoinput");
        const mics = list.filter((d) => d.kind === "audioinput");
        if (cams.length === 0 && mics.length === 0) { setState("empty"); return; }
        const s = await navigator.mediaDevices.getUserMedia(
          {video: cams.length > 0, audio: true});
        streamRef.current = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          videoRef.current.play?.().catch(() => {});
        }
        // VU meter via AnalyserNode.
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (Ctx) {
          const ctx = new Ctx();
          audioCtxRef.current = ctx;
          const src = ctx.createMediaStreamSource(s);
          const a = ctx.createAnalyser(); a.fftSize = 1024;
          src.connect(a);
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
        }
        setState("granted");
      } catch (_) { setState("denied"); }
    })();
    return stop;
  }, [stop]);

  return (
    <div data-testid="gjoin-preflight-panel"
            className="bg-zinc-900 border border-zinc-800 rounded p-4">
      <div data-testid="gjoin-preflight-mirror"
              className="aspect-video bg-black rounded overflow-hidden mb-3
                              flex items-center justify-center">
        {state === "granted" && (
          <video ref={videoRef} muted playsInline
                      data-testid="gjoin-preflight-video"
                      style={{width: "100%", height: "100%",
                                  objectFit: "cover", transform: "scaleX(-1)"}} />
        )}
        {state === "denied" && (
          <div data-testid="gjoin-preflight-denied"
                  className="text-red-400 text-sm p-4 text-center">
            Camera/microphone access was denied. Allow access in your
            browser settings and reload this page to try again.
          </div>
        )}
        {state === "empty" && (
          <div data-testid="gjoin-preflight-empty"
                  className="text-zinc-400 text-sm p-4 text-center">
            No camera or microphone was found on this device. Check your
            OS settings (System Settings → Privacy → Camera / Microphone)
            and reload.
          </div>
        )}
        {state === "idle" && (
          <div className="text-zinc-500 text-sm">Requesting access…</div>
        )}
      </div>
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">
        Audio level
      </div>
      <div data-testid="gjoin-preflight-vu"
              className="h-3 rounded bg-zinc-800 overflow-hidden">
        <div data-testid="gjoin-preflight-vu-fill"
                style={{width: `${Math.min(100, level * 200)}%`,
                            height: "100%",
                            background: level > 0.5 ? "#ef4444"
                                              : level > 0.2 ? "#22c55e" : "#f59e0b",
                            transition: "width 60ms"}} />
      </div>
      <div className="mt-4 flex gap-2 justify-end">
        <button data-testid="gjoin-preflight-cancel" onClick={onCancel}
                    className="px-3 py-1 bg-zinc-800 border border-zinc-700 rounded
                                  hover:bg-zinc-700">
          Cancel
        </button>
        <button data-testid="gjoin-preflight-join"
                    disabled={state !== "granted"}
                    onClick={() => { stop(); onJoin(); }}
                    className="px-4 py-1 bg-violet-600 hover:bg-violet-500
                                  disabled:bg-zinc-700 disabled:text-zinc-500 rounded">
          Looks good — join
        </button>
      </div>
    </div>
  );
}
