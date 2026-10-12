// Global appearance system: Light / Dark / System. The user's chosen *mode*
// is persisted (profile via /api/shell/prefs + localStorage). The *effective*
// theme is applied via data-theme="light|dark" on <html>; "system" resolves
// against the OS preference and live-updates when it changes.
import { create } from "zustand";
import axios from "axios";
import { API } from "@/AuthContext";

const LS_KEY = "radiolife.theme"; // stores the MODE (light|dark|system)
const MODES = new Set(["light", "dark", "system"]);

function systemPrefersDark() {
  try { return window.matchMedia("(prefers-color-scheme: dark)").matches; }
  catch (_e) { return false; }
}
function resolve(mode) {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode === "dark" ? "dark" : "light";
}
function apply(theme) {
  try { document.documentElement.setAttribute("data-theme", theme); } catch (_e) { /* SSR */ }
}
function readLocal() {
  try {
    const v = window.localStorage.getItem(LS_KEY);
    return MODES.has(v) ? v : "light";
  } catch (_e) { return "light"; }
}

let _mql = null;

export const useThemeStore = create((set, get) => ({
  mode: "light",   // user preference: light | dark | system
  theme: "light",  // effective (applied): light | dark
  hydrated: false,

  // Apply the locally-remembered mode immediately (pre-paint), wire the OS
  // listener, then reconcile with the user's saved server preference.
  hydrate: async () => {
    const localMode = readLocal();
    const eff0 = resolve(localMode);
    apply(eff0);
    set({ mode: localMode, theme: eff0 });
    try {
      if (!_mql && window.matchMedia) {
        _mql = window.matchMedia("(prefers-color-scheme: dark)");
        _mql.addEventListener("change", () => {
          if (get().mode === "system") {
            const eff = resolve("system");
            apply(eff);
            set({ theme: eff });
          }
        });
      }
    } catch (_e) { /* ignore */ }
    try {
      const r = await axios.get(`${API}/shell/prefs`, { withCredentials: true });
      const server = r.data?.theme;
      if (MODES.has(server) && server !== get().mode) {
        const eff = resolve(server);
        apply(eff);
        set({ mode: server, theme: eff });
        try { window.localStorage.setItem(LS_KEY, server); } catch (_e) { /* ignore */ }
      }
    } catch (_e) { /* anon or offline — keep local */ }
    set({ hydrated: true });
  },

  setMode: (mode) => {
    if (!MODES.has(mode)) return;
    const eff = resolve(mode);
    apply(eff);
    set({ mode, theme: eff });
    try { window.localStorage.setItem(LS_KEY, mode); } catch (_e) { /* ignore */ }
    axios.put(`${API}/shell/prefs`, { theme: mode }, { withCredentials: true })
      .catch(() => { /* best-effort; localStorage already holds it */ });
  },

  // Legacy API kept for existing callers (ThemeToggle etc.).
  setTheme: (t) => get().setMode(t === "dark" ? "dark" : "light"),
  toggle: () => get().setMode(get().theme === "dark" ? "light" : "dark"),
}));

export function useTheme() {
  const mode = useThemeStore((s) => s.mode);
  const theme = useThemeStore((s) => s.theme);
  const setMode = useThemeStore((s) => s.setMode);
  const toggle = useThemeStore((s) => s.toggle);
  const setTheme = useThemeStore((s) => s.setTheme);
  return { mode, theme, setMode, toggle, setTheme };
}
