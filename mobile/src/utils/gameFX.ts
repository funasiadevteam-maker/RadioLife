// Game sound + haptic FX for mobile. SFX assets live in /assets/sfx.
import { createAudioPlayer, type AudioPlayer } from 'expo-audio';
import * as Haptics from 'expo-haptics';

const SOURCES: Record<string, number> = {
  win: require('../../assets/sfx/win.wav'),
  spin: require('../../assets/sfx/spin.wav'),
  reveal: require('../../assets/sfx/reveal.wav'),
  dice: require('../../assets/sfx/dice.wav'),
  lose: require('../../assets/sfx/lose.wav'),
};
type FxKind = keyof typeof SOURCES;
type HKind = 'light' | 'medium' | 'heavy' | 'success' | 'error';

const players: Record<string, AudioPlayer> = {};
let muted = false;

export function setMuted(m: boolean) { muted = m; }
export function isMuted() { return muted; }

function player(kind: string): AudioPlayer | null {
  try {
    if (!players[kind]) {
      players[kind] = createAudioPlayer(SOURCES[kind]);
      players[kind].volume = 0.6;
    }
    return players[kind];
  } catch { return null; }
}

export function playFx(kind: FxKind) {
  if (muted) return;
  const p = player(kind);
  if (!p) return;
  try { p.seekTo(0); p.play(); } catch { /* noop */ }
}

export function haptic(type: HKind) {
  try {
    if (type === 'success') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    else if (type === 'error') Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    else Haptics.impactAsync(
      type === 'heavy' ? Haptics.ImpactFeedbackStyle.Heavy
        : type === 'medium' ? Haptics.ImpactFeedbackStyle.Medium
          : Haptics.ImpactFeedbackStyle.Light);
  } catch { /* unsupported */ }
}

export function gameFx(kind: FxKind, h?: HKind) {
  playFx(kind);
  if (h) haptic(h);
}
