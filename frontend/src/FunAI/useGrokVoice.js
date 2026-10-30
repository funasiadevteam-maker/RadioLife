/** useGrokVoice — xAI Grok Realtime Voice client hook (Phase 1 Interactive News).
 *
 *  Flow: mint an ephemeral client secret from our backend (/api/fun-ai/session),
 *  open a WebSocket straight to xAI with the secret as a subprotocol, stream the
 *  mic as PCM16 @ 24 kHz, play the anchor's PCM16 back with a jitter queue, and
 *  relay the `search_news` tool call to our backend so the model only gets
 *  source-grounded, verified news. Server VAD drives turn-taking + barge-in.
 *
 *  The permanent xAI key is NEVER in the browser — only the short-lived secret.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

// Voice states surfaced to the UI.
export const VOICE_STATES = {
  IDLE: "idle",
  AUTHORIZING: "authorizing",
  CONNECTING: "connecting",
  READY: "ready",
  LISTENING: "listening",
  THINKING: "thinking",
  SPEAKING: "speaking",
  ERROR: "error",
};

function b64encode(bytes) {
  let s = "";
  const CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(s);
}
function b64decode(str) {
  const bin = atob(str);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export default function useGrokVoice({ onError, onToolEvent } = {}) {
  const [status, setStatus] = useState(VOICE_STATES.IDLE);
  const [micActive, setMicActive] = useState(false);
  const [transcript, setTranscript] = useState([]); // [{role:'you'|'anchor', text}]
  const [errorMsg, setErrorMsg] = useState(null);

  const wsRef = useRef(null);
  const ctxRef = useRef(null);
  const streamRef = useRef(null);
  const procRef = useRef(null);
  const sinkRef = useRef(null);
  const nextTimeRef = useRef(0);
  const sourcesRef = useRef([]);
  const sessRef = useRef(null);
  const startTsRef = useRef(0);
  const stoppingRef = useRef(false);
  const assistantBufRef = useRef("");
  const fnNamesRef = useRef({}); // call_id -> function name
  const optsRef = useRef({});    // last start() options (surface, station, …)

  const send = useCallback((obj) => {
    const w = wsRef.current;
    if (w && w.readyState === 1) w.send(JSON.stringify(obj));
  }, []);

  const flushPlayback = useCallback(() => {
    sourcesRef.current.forEach((s) => { try { s.stop(); } catch (_e) { /* noop */ } });
    sourcesRef.current = [];
    nextTimeRef.current = 0;
  }, []);

  const enqueuePCM = useCallback((bytes) => {
    const ctx = ctxRef.current;
    if (!ctx) return;
    const n = Math.floor(bytes.byteLength / 2);
    if (n <= 0) return;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const buf = ctx.createBuffer(1, n, 24000);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = view.getInt16(i * 2, true) / 32768;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const start = Math.max(ctx.currentTime + 0.02, nextTimeRef.current);
    src.start(start);
    nextTimeRef.current = start + buf.duration;
    sourcesRef.current.push(src);
    src.onended = () => {
      sourcesRef.current = sourcesRef.current.filter((s) => s !== src);
    };
  }, []);

  const fail = useCallback((code, message) => {
    setStatus(VOICE_STATES.ERROR);
    setErrorMsg(message || code);
    if (onError) onError(code, message);
  }, [onError]);

  const startCapture = useCallback((ctx, stream) => {
    const srcNode = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;
    // Route the processor into a muted sink so it runs without echoing the mic.
    const sink = ctx.createGain();
    sink.gain.value = 0;
    sinkRef.current = sink;
    proc.onaudioprocess = (e) => {
      const f = e.inputBuffer.getChannelData(0);
      const pcm = new Int16Array(f.length);
      for (let i = 0; i < f.length; i++) {
        const v = Math.max(-1, Math.min(1, f[i]));
        pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
      }
      send({ type: "input_audio_buffer.append",
             audio: b64encode(new Uint8Array(pcm.buffer)) });
    };
    srcNode.connect(proc);
    proc.connect(sink);
    sink.connect(ctx.destination);
  }, [send]);

  const handleMessage = useCallback(async (raw) => {
    let x;
    try { x = JSON.parse(raw); } catch (_e) { return; }
    switch (x.type) {
      case "input_audio_buffer.speech_started":
        flushPlayback();            // barge-in: drop any queued anchor audio
        setStatus(VOICE_STATES.LISTENING);
        break;
      case "input_audio_buffer.speech_stopped":
      case "response.created":
        setStatus(VOICE_STATES.THINKING);
        break;
      case "response.output_audio.delta":
        if (x.delta) { setStatus(VOICE_STATES.SPEAKING); enqueuePCM(b64decode(x.delta)); }
        break;
      case "response.output_audio_transcript.delta":
        if (x.delta) assistantBufRef.current += x.delta;
        break;
      case "response.done":
      case "response.output_audio.done": {
        const t = assistantBufRef.current.trim();
        if (t) setTranscript((p) => [...p, { role: "anchor", text: t }]);
        assistantBufRef.current = "";
        setStatus(VOICE_STATES.READY);
        break;
      }
      case "conversation.item.input_audio_transcription.completed": {
        const t = (x.transcript || "").trim();
        if (t) setTranscript((p) => [...p, { role: "you", text: t }]);
        break;
      }
      case "response.output_item.added":
        if (x.item?.type === "function_call" && x.item.call_id) {
          fnNamesRef.current[x.item.call_id] = x.item.name;
        }
        break;
      case "response.function_call_arguments.done": {
        let args = {};
        try { args = JSON.parse(x.arguments || "{}"); } catch (_e) { args = {}; }
        const fnName = x.name || fnNamesRef.current[x.call_id] || "search_news";
        const ctx = optsRef.current || {};
        setStatus(VOICE_STATES.THINKING);
        let out = {};
        try {
          if (fnName === "follow_story") {
            const r = await axios.post(`${API}/fun-ai/follows`,
              { topic: args.topic, title: args.topic }, { withCredentials: true });
            out = { ok: true, followed: r.data?.follow?.topic || args.topic };
            if (onToolEvent) onToolEvent("follow_story", out);
          } else if (fnName === "get_now_playing") {
            const r = await axios.get(`${API}/fun-ai/radio/now-playing`,
              { params: { station: ctx.station?.slug, name: ctx.station?.name },
                withCredentials: true });
            out = r.data;
          } else if (fnName === "get_available_radio_formats") {
            const r = await axios.get(`${API}/fun-ai/radio/formats`, { withCredentials: true });
            out = r.data;
          } else if (fnName === "request_radio_action") {
            const r = await axios.post(`${API}/fun-ai/radio/action`, {
              action: args.action,
              params: { value: args.value, song: args.value, artist: args.value,
                        target: args.value },
              station: ctx.station || {},
            }, { withCredentials: true });
            out = r.data;
            if (onToolEvent) onToolEvent("request_radio_action", out);
          } else if (fnName === "record_music_feedback") {
            const r = await axios.post(`${API}/fun-ai/radio/action`, {
              action: "record_feedback",
              params: { value: args.value || args.feedback },
              station: ctx.station || {},
            }, { withCredentials: true });
            out = r.data;
          } else if (fnName === "save_user_approved_memory") {
            const r = await axios.post(`${API}/fun-ai/memory`,
              { kind: args.kind, value: args.value }, { withCredentials: true });
            out = { ok: r.data?.ok !== false, saved: args.value, kind: args.kind };
            if (onToolEvent) onToolEvent("save_user_approved_memory", out);
          } else {
            const r = await axios.post(`${API}/fun-ai/news/search`, args,
                                       { withCredentials: true });
            out = r.data;
          }
        } catch (_e) { out = { ok: false, error: `${fnName}_failed` }; }
        send({ type: "conversation.item.create",
               item: { type: "function_call_output", call_id: x.call_id,
                       output: JSON.stringify(out) } });
        send({ type: "response.create" });
        break;
      }
      case "error":
        fail("realtime_error", x.error?.message || "Voice error");
        break;
      default:
        break;
    }
  }, [enqueuePCM, flushPlayback, send, fail, onToolEvent]);

  const stop = useCallback(async () => {
    if (stoppingRef.current) return;
    stoppingRef.current = true;
    const elapsed = startTsRef.current
      ? Math.round((Date.now() - startTsRef.current) / 1000) : 0;
    try { wsRef.current && wsRef.current.close(); } catch (_e) { /* noop */ }
    try { procRef.current && procRef.current.disconnect(); } catch (_e) { /* noop */ }
    try { streamRef.current && streamRef.current.getTracks().forEach((t) => t.stop()); } catch (_e) { /* noop */ }
    flushPlayback();
    try { ctxRef.current && (await ctxRef.current.close()); } catch (_e) { /* noop */ }
    wsRef.current = null; procRef.current = null; streamRef.current = null; ctxRef.current = null;
    setMicActive(false);
    setStatus(VOICE_STATES.IDLE);
    const sid = sessRef.current?.session_id;
    if (sid || elapsed) {
      axios.post(`${API}/fun-ai/session/end`,
                 { session_id: sid, voice_seconds: elapsed },
                 { withCredentials: true }).catch(() => {});
    }
    sessRef.current = null;
    stoppingRef.current = false;
  }, [flushPlayback]);

  const start = useCallback(async (opts = {}) => {
    setErrorMsg(null);
    setTranscript([]);
    stoppingRef.current = false;
    optsRef.current = opts || {};
    setStatus(VOICE_STATES.AUTHORIZING);
    let sess;
    try {
      sess = await axios.post(`${API}/fun-ai/session`,
                              { mode: opts.mode, topic: opts.topic,
                                surface: opts.surface, station: opts.station },
                              { withCredentials: true }).then((r) => r.data);
    } catch (err) {
      const d = err?.response?.data?.detail || {};
      fail(d.code || "session_failed", d.message || "Could not start Fun AI.");
      return;
    }
    sessRef.current = sess;
    setStatus(VOICE_STATES.CONNECTING);

    let ctx;
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC({ sampleRate: 24000 });
      ctxRef.current = ctx;
      if (ctx.state === "suspended") { try { await ctx.resume(); } catch (_e) { /* noop */ } }
    } catch (_e) { fail("audio_unsupported", "Audio is not supported in this browser."); return; }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (_e) {
      fail("mic_denied", "Microphone access is needed to talk with Fun AI.");
      await stop();
      return;
    }
    streamRef.current = stream;
    setMicActive(true);

    let ws;
    try {
      ws = new WebSocket(sess.ws_url, [`xai-client-secret.${sess.client_secret}`]);
    } catch (_e) { fail("ws_failed", "Could not connect to the voice service."); return; }
    wsRef.current = ws;
    startTsRef.current = Date.now();

    ws.onopen = () => {
      send({
        type: "session.update",
        session: {
          voice: sess.voice || "eve",
          instructions: sess.instructions,
          turn_detection: { type: "server_vad" },
          tools: sess.tools || [],
          audio: {
            input: { format: { type: "audio/pcm", rate: 24000 } },
            output: { format: { type: "audio/pcm", rate: 24000 } },
          },
        },
      });
      setStatus(VOICE_STATES.READY);
      startCapture(ctx, stream);
    };
    ws.onmessage = (e) => handleMessage(e.data);
    ws.onerror = () => fail("connection_error", "Voice connection error.");
    ws.onclose = () => {
      if (!stoppingRef.current) {
        // unexpected close — surface a fallback state, stop cleanly
        setStatus((s) => (s === VOICE_STATES.ERROR ? s : VOICE_STATES.IDLE));
        stop();
      }
    };
  }, [fail, handleMessage, send, startCapture, stop]);

  // Clean up on unmount.
  useEffect(() => () => { stop(); }, [stop]);

  return { status, micActive, transcript, errorMsg, start, stop };
}
