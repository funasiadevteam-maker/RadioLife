// Lightweight game sound + vibration FX (web). Assets live in /public/sfx.
const FILES = {
  win: "/sfx/win.wav",
  spin: "/sfx/spin.wav",
  reveal: "/sfx/reveal.wav",
  dice: "/sfx/dice.wav",
  lose: "/sfx/lose.wav",
};
const cache = {};
const MUTE_KEY = "fuusic_game_muted";

export function isMuted() {
  try { return localStorage.getItem(MUTE_KEY) === "1"; } catch { return false; }
}

export function setMuted(m) {
  try { localStorage.setItem(MUTE_KEY, m ? "1" : "0"); } catch { /* noop */ }
}

export function playFx(kind) {
  if (isMuted()) return;
  const src = FILES[kind];
  if (!src) return;
  try {
    let a = cache[kind];
    if (!a) { a = new Audio(src); a.volume = 0.5; cache[kind] = a; }
    a.currentTime = 0;
    const p = a.play();
    if (p && p.catch) p.catch(() => {});
  } catch { /* autoplay blocked */ }
}

export function vibrate(pattern) {
  try { if (typeof navigator !== "undefined" && navigator.vibrate) navigator.vibrate(pattern); }
  catch { /* unsupported */ }
}

// Fire a sound + optional vibration together.
export function fx(kind, vib) {
  playFx(kind);
  if (vib) vibrate(vib);
}
