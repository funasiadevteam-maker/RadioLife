// @ts-nocheck
/* FUUSIC Fun AI — NATIVE voice anchor (xAI Grok Realtime Voice), iOS/Android.
 * Metro loads this file on native builds only; web loads grokVoiceNative.ts
 * (a stub). Needs a published / EAS build + a real device — not Expo Go or
 * the web preview. Raw WebSocket + PCM16 @16kHz, server_vad, barge-in, and
 * tool calls relayed to our backend so results stay verified/policy-gated.
 * The permanent xAI key never reaches the device — only the ephemeral secret.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Buffer } from 'buffer';
import { requestPermission, start as micStart, stop as micStop, addFrameListener }
  from 'expo-stream-audio';
import { initialize as audioInit, playPCMData, stopPlayback }
  from '@speechmatics/expo-two-way-audio';
import api from '../api/client';

export const VOICE_STATES = {
  IDLE: 'idle', AUTHORIZING: 'authorizing', CONNECTING: 'connecting',
  READY: 'ready', LISTENING: 'listening', THINKING: 'thinking',
  SPEAKING: 'speaking', ERROR: 'error', UNSUPPORTED: 'unsupported',
};

const RATE = 16000;

async function runTool(name, args, ctx) {
  try {
    if (name === 'follow_story') {
      const { data } = await api.post('/fun-ai/follows', { topic: args.topic, title: args.topic });
      return { ok: true, followed: data?.follow?.topic || args.topic };
    }
    if (name === 'get_now_playing') {
      const { data } = await api.get('/fun-ai/radio/now-playing',
        { params: { station: ctx?.station?.slug, name: ctx?.station?.name } });
      return data;
    }
    if (name === 'get_available_radio_formats') {
      const { data } = await api.get('/fun-ai/radio/formats'); return data;
    }
    if (name === 'request_radio_action') {
      const { data } = await api.post('/fun-ai/radio/action', {
        action: args.action,
        params: { value: args.value, song: args.value, artist: args.value, target: args.value },
        station: ctx?.station || {},
      });
      return data;
    }
    if (name === 'record_music_feedback') {
      const { data } = await api.post('/fun-ai/radio/action',
        { action: 'record_feedback', params: { value: args.value }, station: ctx?.station || {} });
      return data;
    }
    if (name === 'save_user_approved_memory') {
      const { data } = await api.post('/fun-ai/memory', { kind: args.kind, value: args.value });
      if (ctx?.onToolEvent) ctx.onToolEvent('save_user_approved_memory', { saved: args.value });
      return { ok: data?.ok !== false, saved: args.value };
    }
    const { data } = await api.post('/fun-ai/news/search', args);
    return data;
  } catch (_e) { return { ok: false, error: `${name}_failed` }; }
}

export function nativeVoiceSupported() { return true; }

export function useGrokVoiceNative({ onToolEvent } = {}) {
  const [status, setStatus] = useState(VOICE_STATES.IDLE);
  const [transcript, setTranscript] = useState([]);
  const wsRef = useRef(null);
  const micSubRef = useRef(null);
  const fnNamesRef = useRef({});
  const optsRef = useRef({});
  const asstBufRef = useRef('');

  const send = useCallback((o) => {
    if (wsRef.current?.readyState === 1) wsRef.current.send(JSON.stringify(o));
  }, []);

  const stop = useCallback(async () => {
    try { micSubRef.current?.remove?.(); } catch (_e) {}
    micSubRef.current = null;
    try { await micStop(); } catch (_e) {}
    try { await stopPlayback?.(); } catch (_e) {}
    try { wsRef.current?.close(); } catch (_e) {}
    wsRef.current = null;
    setStatus(VOICE_STATES.IDLE);
  }, []);

  const start = useCallback(async (opts = {}) => {
    optsRef.current = opts || {};
    setTranscript([]);
    setStatus(VOICE_STATES.AUTHORIZING);
    try {
      await audioInit();
      const perm = await requestPermission();
      if (perm !== 'granted') { setStatus(VOICE_STATES.ERROR); return; }

      const { data: sess } = await api.post('/fun-ai/session', {
        mode: opts.mode, topic: opts.topic, surface: opts.surface, station: opts.station,
      });
      setStatus(VOICE_STATES.CONNECTING);

      const ws = new WebSocket(sess.ws_url, [`xai-client-secret.${sess.client_secret}`]);
      wsRef.current = ws;

      ws.onopen = async () => {
        send({ type: 'session.update', session: {
          voice: sess.voice || 'eve',
          instructions: sess.instructions,
          turn_detection: { type: 'server_vad' },
          tools: sess.tools || [],
          audio: {
            input: { format: { type: 'audio/pcm', rate: RATE } },
            output: { format: { type: 'audio/pcm', rate: RATE } },
          },
        }});
        micSubRef.current = addFrameListener((frame) => {
          if (ws.readyState === 1) send({ type: 'input_audio_buffer.append', audio: frame.pcmBase64 });
        });
        await micStart({ sampleRate: RATE, frameDurationMs: 20, channels: 1 });
        setStatus(VOICE_STATES.READY);
      };

      ws.onmessage = async ({ data }) => {
        let e; try { e = JSON.parse(data); } catch (_x) { return; }
        switch (e.type) {
          case 'input_audio_buffer.speech_started':
            try { await stopPlayback?.(); } catch (_x) {}
            setStatus(VOICE_STATES.LISTENING); break;
          case 'response.created':
          case 'input_audio_buffer.speech_stopped':
            setStatus(VOICE_STATES.THINKING); break;
          case 'response.output_audio.delta':
          case 'response.audio.delta':
            if (e.delta) { setStatus(VOICE_STATES.SPEAKING); await playPCMData(new Uint8Array(Buffer.from(e.delta, 'base64'))); }
            break;
          case 'response.output_audio_transcript.delta':
            if (e.delta) asstBufRef.current += e.delta; break;
          case 'response.done':
          case 'response.output_audio.done': {
            const t = asstBufRef.current.trim();
            if (t) setTranscript((p) => [...p, { role: 'anchor', text: t }]);
            asstBufRef.current = ''; setStatus(VOICE_STATES.READY); break;
          }
          case 'conversation.item.input_audio_transcription.completed': {
            const t = (e.transcript || '').trim();
            if (t) setTranscript((p) => [...p, { role: 'you', text: t }]);
            break;
          }
          case 'response.output_item.added':
            if (e.item?.type === 'function_call' && e.item.call_id) fnNamesRef.current[e.item.call_id] = e.item.name;
            break;
          case 'response.function_call_arguments.done': {
            let args = {}; try { args = JSON.parse(e.arguments || '{}'); } catch (_x) {}
            const name = e.name || fnNamesRef.current[e.call_id] || 'search_news';
            const out = await runTool(name, args, optsRef.current);
            if (onToolEvent) onToolEvent(name, out);
            send({ type: 'conversation.item.create', item: {
              type: 'function_call_output', call_id: e.call_id, output: JSON.stringify(out) } });
            send({ type: 'response.create' });
            break;
          }
          default: break;
        }
      };
      ws.onerror = () => setStatus(VOICE_STATES.ERROR);
      ws.onclose = () => { stop(); };
    } catch (_e) { setStatus(VOICE_STATES.ERROR); await stop(); }
  }, [send, stop, onToolEvent]);

  useEffect(() => () => { stop(); }, [stop]);
  return { status, transcript, start, stop };
}
