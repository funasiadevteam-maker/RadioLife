// Dual-theme system (dark default + light). Theme is applied via
// data-theme="dark|light" on <html>, persisted to localStorage AND to the
// user profile (/api/shell/prefs) with a localStorage fallback for anon.
import { create } from "zustand";
import axios from "axios";
import { API } from "@/AuthContext";

const LS_KEY = "radiolife.theme";
const VALID = new Set(["dark", "light"]);

function readLocal() {
  try {
    const v = window.localStorage.getItem(LS_KEY);
    return VALID.has(v) ? v : "dark";
  } catch (_e) { return "dark"; }
}

function apply(theme) {
  try {
    document.documentElement.setAttribute("data-theme", theme);
  } catch (_e) { /* SSR / no-DOM */ }
}

export const useThemeStore = create((set, get) => ({
  theme: "dark",
  hydrated: false,

  // Apply the locally-remembered theme immediately (pre-paint), then
  // reconcile with the user's saved server preference.
  hydrate: async () => {
    const local = readLocal();
    apply(local);
    set({ theme: local });
    try {
      const r = await axios.get(`${API}/shell/prefs`, { withCredentials: true });
      const server = r.data?.theme;
      if (VALID.has(server) && server !== get().theme) {
        apply(server);
        set({ theme: server });
        try { window.localStorage.setItem(LS_KEY, server); } catch (_e) { /* ignore */ }
      }
    } catch (_e) { /* anon or offline — keep local */ }
    set({ hydrated: true });
  },

  setTheme: (theme) => {
    if (!VALID.has(theme)) return;
    apply(theme);
    set({ theme });
    try { window.localStorage.setItem(LS_KEY, theme); } catch (_e) { /* ignore */ }
    axios.put(`${API}/shell/prefs`, { theme }, { withCredentials: true })
      .catch(() => { /* best-effort; localStorage already holds it */ });
  },

  toggle: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    get().setTheme(next);
  },
}));

// Convenience hook.
export function useTheme() {
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggle);
  const setTheme = useThemeStore((s) => s.setTheme);
  return { theme, toggle, setTheme };
}
