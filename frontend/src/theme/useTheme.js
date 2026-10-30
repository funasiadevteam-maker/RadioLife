// Global appearance system: Light / Dark / System + user ACCENT colour +
// optional Scheduled Dark (auto dark/light by local clock). The chosen *mode*,
// *accent* and *schedule* are persisted (profile via /api/shell/prefs +
// localStorage). The *effective* theme is applied via data-theme="light|dark"
// on <html>; accent via data-accent; "system" resolves against the OS pref and
// live-updates; schedule (when enabled) overrides mode from the clock.
import { create } from "zustand";
import axios from "axios";
import { API } from "@/AuthContext";

const LS_KEY = "radiolife.theme";        // MODE (light|dark|system)
const LS_ACCENT = "radiolife.accent";    // violet|coral|teal|amber|blue
const LS_SCHED = "radiolife.schedule";   // {enabled,dark_hour,light_hour}
const MODES = new Set(["light", "dark", "system"]);
const ACCENTS = new Set(["violet", "coral", "teal", "amber", "blue"]);
const DEFAULT_SCHED = { enabled: false, dark_hour: 19, light_hour: 7 };

function systemPrefersDark() {
  try { return window.matchMedia("(prefers-color-scheme: dark)").matches; }
  catch (_e) { return false; }
}
function resolve(mode) {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode === "dark" ? "dark" : "light";
}
function cleanSchedule(raw) {
  const s = { ...DEFAULT_SCHED };
  if (raw && typeof raw === "object") {
    s.enabled = !!raw.enabled;
    [["dark_hour"], ["light_hour"]].forEach(([k]) => {
      const v = parseInt(raw[k], 10);
      if (Number.isInteger(v) && v >= 0 && v <= 23) s[k] = v;
    });
  }
  return s;
}
function inDarkWindow(sched) {
  const h = new Date().getHours();
  const d = sched.dark_hour, l = sched.light_hour;
  if (d === l) return false;
  if (d > l) return h >= d || h < l;   // night spans midnight (typical)
  return h >= d && h < l;              // dark band inside a single day
}
function effectiveOf(mode, sched) {
  if (sched && sched.enabled) return inDarkWindow(sched) ? "dark" : "light";
  return resolve(mode);
}
function apply(theme) {
  try { document.documentElement.setAttribute("data-theme", theme); } catch (_e) { /* SSR */ }
}
function applyAccent(accent) {
  try {
    if (accent && accent !== "violet") document.documentElement.setAttribute("data-accent", accent);
    else document.documentElement.removeAttribute("data-accent");
  } catch (_e) { /* SSR */ }
}
function readLocal() {
  try { const v = window.localStorage.getItem(LS_KEY); return MODES.has(v) ? v : "light"; }
  catch (_e) { return "light"; }
}
function readLocalAccent() {
  try { const v = window.localStorage.getItem(LS_ACCENT); return ACCENTS.has(v) ? v : "violet"; }
  catch (_e) { return "violet"; }
}
function readLocalSchedule() {
  try { return cleanSchedule(JSON.parse(window.localStorage.getItem(LS_SCHED) || "null")); }
  catch (_e) { return { ...DEFAULT_SCHED }; }
}
function writeLocal(mode, accent, sched) {
  try {
    if (mode) window.localStorage.setItem(LS_KEY, mode);
    if (accent) window.localStorage.setItem(LS_ACCENT, accent);
    if (sched) window.localStorage.setItem(LS_SCHED, JSON.stringify(sched));
  } catch (_e) { /* ignore */ }
}

let _mql = null;
let _ticker = null;
let _userTouched = false;   // set once the user changes a setting themselves
function startTicker(get, set) {
  if (_ticker) return;
  _ticker = setInterval(() => {
    const st = get();
    if (!st.schedule.enabled) return;
    const eff = effectiveOf(st.mode, st.schedule);
    if (eff !== st.theme) { apply(eff); set({ theme: eff }); }
  }, 60000);
}

export const useThemeStore = create((set, get) => ({
  mode: "light",
  theme: "light",
  accent: "violet",
  schedule: { ...DEFAULT_SCHED },
  hydrated: false,

  hydrate: async () => {
    const localMode = readLocal();
    const localAccent = readLocalAccent();
    const localSched = readLocalSchedule();
    const eff0 = effectiveOf(localMode, localSched);
    apply(eff0); applyAccent(localAccent);
    set({ mode: localMode, accent: localAccent, schedule: localSched, theme: eff0 });
    startTicker(get, set);
    try {
      if (!_mql && window.matchMedia) {
        _mql = window.matchMedia("(prefers-color-scheme: dark)");
        _mql.addEventListener("change", () => {
          const st = get();
          if (st.schedule.enabled || st.mode !== "system") return;
          const eff = resolve("system");
          apply(eff); set({ theme: eff });
        });
      }
    } catch (_e) { /* ignore */ }
    try {
      const r = await axios.get(`${API}/shell/prefs`, { withCredentials: true });
      if (_userTouched) { set({ hydrated: true }); return; }  // don't clobber a user's in-flight choice
      const server = r.data?.theme;
      const sa = r.data?.accent;
      const ss = r.data?.theme_schedule;
      const nextMode = MODES.has(server) ? server : get().mode;
      const nextAccent = ACCENTS.has(sa) ? sa : get().accent;
      const nextSched = cleanSchedule(ss);
      const eff = effectiveOf(nextMode, nextSched);
      apply(eff); applyAccent(nextAccent);
      set({ mode: nextMode, accent: nextAccent, schedule: nextSched, theme: eff });
      writeLocal(nextMode, nextAccent, nextSched);
    } catch (_e) { /* anon or offline — keep local */ }
    set({ hydrated: true });
  },

  setMode: (mode) => {
    if (!MODES.has(mode)) return;
    _userTouched = true;
    const sched = { ...get().schedule, enabled: false }; // manual pick turns auto off
    const eff = effectiveOf(mode, sched);
    apply(eff);
    set({ mode, theme: eff, schedule: sched });
    writeLocal(mode, null, sched);
    axios.put(`${API}/shell/prefs`, { theme: mode, theme_schedule: sched },
      { withCredentials: true }).catch(() => {});
  },

  setAccent: (accent) => {
    if (!ACCENTS.has(accent)) return;
    _userTouched = true;
    applyAccent(accent);
    set({ accent });
    writeLocal(null, accent, null);
    axios.put(`${API}/shell/prefs`, { accent }, { withCredentials: true }).catch(() => {});
  },

  setSchedule: (patch) => {
    _userTouched = true;
    const sched = cleanSchedule({ ...get().schedule, ...patch });
    const eff = effectiveOf(get().mode, sched);
    apply(eff);
    set({ schedule: sched, theme: eff });
    writeLocal(null, null, sched);
    axios.put(`${API}/shell/prefs`, { theme_schedule: sched },
      { withCredentials: true }).catch(() => {});
  },

  // Legacy API kept for existing callers (ThemeToggle etc.).
  setTheme: (t) => get().setMode(t === "dark" ? "dark" : "light"),
  toggle: () => get().setMode(get().theme === "dark" ? "light" : "dark"),
}));

export function useTheme() {
  const mode = useThemeStore((s) => s.mode);
  const theme = useThemeStore((s) => s.theme);
  const accent = useThemeStore((s) => s.accent);
  const schedule = useThemeStore((s) => s.schedule);
  const setMode = useThemeStore((s) => s.setMode);
  const setAccent = useThemeStore((s) => s.setAccent);
  const setSchedule = useThemeStore((s) => s.setSchedule);
  const toggle = useThemeStore((s) => s.toggle);
  const setTheme = useThemeStore((s) => s.setTheme);
  return { mode, theme, accent, schedule, setMode, setAccent, setSchedule, toggle, setTheme };
}
