/**
 * nativePlayerBridge — Platform-aware lock-screen / foreground-service bridge.
 *
 * On native (iOS/Android):
 *   Uses `react-native-track-player` for:
 *   - iOS Now Playing (title, artist, album, artwork)
 *   - Android foreground-service notification with transport controls
 *
 * On web:
 *   No-op — web preview uses expo-audio directly and has no lock-screen.
 *
 * IMPORTANT: The actual audio playback on web still uses `expo-audio`.
 * On native builds, `react-native-track-player` handles BOTH playback
 * and lock-screen metadata.
 */
import { Platform } from 'react-native';
import { BACKEND } from '../api/client';

/* ── Lazy imports (native modules unavailable on web) ── */
let TrackPlayer: any = null;
let Capability: any = null;
let Event: any = null;
let _tpReady = false;

if (Platform.OS !== 'web') {
  try {
    const tp = require('react-native-track-player');
    TrackPlayer = tp.default || tp;
    Capability = tp.Capability;
    Event = tp.Event;
  } catch {
    // native module not linked — dev-client not built
  }
}

/** One-time setup. Call from root layout after auth hydration. */
export async function setupNativePlayer(): Promise<void> {
  if (!TrackPlayer || Platform.OS === 'web') return;
  try {
    await TrackPlayer.setupPlayer({ waitForBuffer: true });
    await TrackPlayer.updateOptions({
      capabilities: [Capability.Play, Capability.Pause, Capability.SkipToNext],
      compactCapabilities: [Capability.Play, Capability.Pause, Capability.SkipToNext],
      notificationCapabilities: [Capability.Play, Capability.Pause, Capability.SkipToNext],
    });
    _tpReady = true;
  } catch (e) {
    console.warn('[TrackPlayer] setup failed:', e);
  }
}

/**
 * Push a new segment into TrackPlayer with lock-screen metadata.
 *
 * @param segmentUrl — full URL to the MP3 segment
 * @param title — track title
 * @param artist — track artist
 * @param channelName — e.g. "Bollywood Mehfil" (dynamic, never hardcoded "Dubai")
 * @param channelThumbUrl — relative thumbnail path from /api/channels
 */
export async function updateNowPlaying(
  segmentUrl: string,
  title: string,
  artist: string,
  channelName: string,
  channelThumbUrl: string | null,
): Promise<void> {
  if (!_tpReady || !TrackPlayer) return;
  try {
    await TrackPlayer.reset();
    await TrackPlayer.add({
      url: segmentUrl,
      title: title || 'Now playing',
      artist: artist || 'FUUSIC',
      album: `FUUSIC · ${channelName}`,
      artwork: channelThumbUrl ? `${BACKEND}${channelThumbUrl}` : undefined,
    });
    await TrackPlayer.play();
  } catch (e) {
    console.warn('[TrackPlayer] updateNowPlaying failed:', e);
  }
}

/** Mirror play/pause from app UI to lock-screen. */
export async function nativePlay(): Promise<void> {
  if (!_tpReady || !TrackPlayer) return;
  try { await TrackPlayer.play(); } catch {}
}

export async function nativePause(): Promise<void> {
  if (!_tpReady || !TrackPlayer) return;
  try { await TrackPlayer.pause(); } catch {}
}

export async function nativeStop(): Promise<void> {
  if (!_tpReady || !TrackPlayer) return;
  try { await TrackPlayer.reset(); } catch {}
}

/**
 * Subscribe to lock-screen remote events.
 * Returns a cleanup function, or null on web.
 *
 * @param onPlay — called when user taps play on lock-screen
 * @param onPause — called when user taps pause
 * @param onNext — called when user taps next
 */
export function subscribeRemoteEvents(
  onPlay: () => void,
  onPause: () => void,
  onNext: () => void,
): (() => void) | null {
  if (!TrackPlayer || !Event || Platform.OS === 'web') return null;
  try {
    const subs = [
      TrackPlayer.addEventListener(Event.RemotePlay, onPlay),
      TrackPlayer.addEventListener(Event.RemotePause, onPause),
      TrackPlayer.addEventListener(Event.RemoteNext, onNext),
    ];
    return () => subs.forEach((s: any) => s?.remove?.());
  } catch {
    return null;
  }
}

export const isNativePlayerAvailable = (): boolean => _tpReady;
