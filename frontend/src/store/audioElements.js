// Phase 15d.3 — singleton holder for the two HTMLAudioElement nodes that
// drive the BigFM crossfade player.  The audio elements are mounted ONCE
// at the AppShell root by `<GlobalAudio />` so that route navigation does
// NOT unmount them.  Anything that needs to read or mutate the audio (e.g.
// Radio.js, MiniPlayer, keyboard shortcuts) imports the refs from here.
//
// Why a plain module singleton instead of a React context / zustand value?
//   * HTMLMediaElement is imperative — using a context would re-render every
//     consumer on every `volume` change.  We don't want that.
//   * `useRef` objects have a stable identity across renders, so a module
//     export of the same shape is API-compatible with anything that already
//     reads `ref.current`.
//   * The element nodes survive even if every React subtree unmounts —
//     they are anchored on AppShell which only unmounts on app-tear-down.
export const audioElements = {
  a: { current: null },
  b: { current: null },
  // Phase H'.5a — dedicated audio node for inter-song AI-RJ voice
  // segments.  Sits alongside the a/b crossfade pair so RJ playback
  // doesn't interrupt the prefetch chain on the inactive music element.
  rj: { current: null },
};

// Convenience helpers used by GlobalAudio + Logout flow.
export function getActiveAudio(activeIdx) {
  return activeIdx === 0 ? audioElements.a.current : audioElements.b.current;
}

export function pauseAllAudio() {
  try { audioElements.a.current && audioElements.a.current.pause(); } catch (_) { /* */ }
  try { audioElements.b.current && audioElements.b.current.pause(); } catch (_) { /* */ }
  try { audioElements.rj.current && audioElements.rj.current.pause(); } catch (_) { /* */ }
}

export function teardownAllAudio() {
  // Hard stop used by logout.  Pauses both elements and clears src so the
  // browser releases the network connection and decoded buffers.
  for (const ref of [audioElements.a, audioElements.b, audioElements.rj]) {
    const el = ref.current;
    if (!el) continue;
    try { el.pause(); } catch (_) { /* */ }
    try { el.removeAttribute("src"); el.load(); } catch (_) { /* */ }
  }
}
