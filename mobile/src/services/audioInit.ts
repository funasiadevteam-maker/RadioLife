/**
 * audioInit — Configures audio mode for background playback.
 *
 * Called ONCE from the root layout after auth hydration.
 * Uses expo-audio (SDK 54+) which is already installed.
 */
import { Platform } from 'react-native';

let AudioModule: any = null;
try {
  const mod = require('expo-audio');
  AudioModule = mod.default || mod;
} catch {}

let _configured = false;

/**
 * Configure audio mode for background playback + silent mode.
 * Safe to call multiple times — idempotent.
 */
export async function configureAudioMode(): Promise<void> {
  if (_configured || !AudioModule?.setAudioModeAsync) return;
  try {
    await AudioModule.setAudioModeAsync({
      staysActiveInBackground: true,
      playsInSilentModeIOS: true,
      interruptionModeIOS: 1, // DoNotMix
      interruptionModeAndroid: 1, // DoNotMix
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    });
    _configured = true;
    if (__DEV__) console.log('[Audio] Background mode configured');
  } catch (e) {
    console.warn('[Audio] setAudioModeAsync failed:', e);
  }
}

export function isAudioConfigured(): boolean {
  return _configured;
}

// Re-export for tests
export { AudioModule };
