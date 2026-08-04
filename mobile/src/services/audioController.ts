/**
 * audioController — module-level singleton that holds a reference to the
 * CURRENTLY active expo-audio player instance.
 *
 * The audio player is created inside the Radio screen (`app/(tabs)/radio.tsx`),
 * but transport controls also live OUTSIDE that screen — most importantly the
 * persistent <MiniPlayer /> in the root layout. Without a shared reference the
 * MiniPlayer can only flip a zustand flag and never actually starts/stops sound.
 *
 * The Radio screen registers its player here whenever a segment starts, and
 * any component can toggle/pause/play through these helpers.
 */

let currentPlayer: any = null;

/** Radio screen calls this each time it creates/plays a new segment. */
export function registerPlayer(player: any): void {
  currentPlayer = player;
}

/** Clear the reference (on release/unmount). Pass the player to only clear if it still matches. */
export function clearPlayer(player?: any): void {
  if (!player || player === currentPlayer) currentPlayer = null;
}

/** True if there is a live player instance that is currently playing. */
export function playerIsPlaying(): boolean {
  try {
    return !!currentPlayer?.playing;
  } catch {
    return false;
  }
}

/** True if a player has been registered (audio session exists). */
export function hasPlayer(): boolean {
  return !!currentPlayer;
}

export function playPlayback(): void {
  try {
    currentPlayer?.play?.();
  } catch {}
}

export function pausePlayback(): void {
  try {
    currentPlayer?.pause?.();
  } catch {}
}

/**
 * Toggle playback. Returns the resulting playing state
 * (`true` = now playing, `false` = now paused / no player).
 */
export function togglePlayback(): boolean {
  const p = currentPlayer;
  if (!p) return false;
  try {
    if (p.playing) {
      p.pause();
      return false;
    }
    p.play();
    return true;
  } catch {
    return false;
  }
}
