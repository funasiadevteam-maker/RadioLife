/* FUUSIC Fun AI — WEB-SAFE stub for the native voice anchor.
 *
 * Metro loads THIS file on web (the Expo preview) and grokVoiceNative.native.ts
 * on iOS/Android builds. The stub imports no native audio modules, so the web
 * preview keeps bundling and the listen-only news experience is unaffected.
 * Live microphone voice only runs in a published / EAS build on a real device.
 */
import { useState } from 'react';

export const VOICE_STATES = {
  IDLE: 'idle', AUTHORIZING: 'authorizing', CONNECTING: 'connecting',
  READY: 'ready', LISTENING: 'listening', THINKING: 'thinking',
  SPEAKING: 'speaking', ERROR: 'error', UNSUPPORTED: 'unsupported',
};

/** False on web/Expo Go — callers fall back to the listen-only explainer. */
export function nativeVoiceSupported(): boolean { return false; }

export function useGrokVoiceNative(_opts: { onToolEvent?: (n: string, o: any) => void } = {}) {
  const [status] = useState(VOICE_STATES.UNSUPPORTED);
  return {
    status,
    transcript: [] as Array<{ role: string; text: string }>,
    start: async (_o?: any) => { /* not available on web/Expo Go */ },
    stop: async () => { /* no-op */ },
  };
}
