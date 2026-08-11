// Phase R.1 — Design variant switcher.  Persists to localStorage, broadcasts
// via a small Zustand store so the whole app re-renders when the user flips
// the toggle.  Values: "legacy" | "radiolife".
//
// Phase R.1.2 — `?design=legacy|radiolife` query-param override.  Precedence
// order: query param > localStorage > default("legacy").  When a valid
// query-param value is present, it is ALSO persisted to localStorage so the
// variant survives internal SPA navigation (which typically drops the
// query param from the URL).
import { create } from "zustand";

const LS_KEY = "bigfm_design_variant";
const QP_KEY = "design";
const VALID = new Set(["legacy", "radiolife"]);

function readQueryVariant() {
  try {
    if (typeof window === "undefined") return null;
    const q = new URLSearchParams(window.location.search).get(QP_KEY);
    return VALID.has(q) ? q : null;
  } catch {
    return null;
  }
}

// NOTE (in-shell Shop): the Shop used to force the RadioLife variant on
// every /shop route (so it opened as a full-screen app overlay). That made
// the classic left sidebar + top bar disappear. The Shop now renders INSIDE
// the legacy shell (<ShopInShell>), so we no longer force the variant here —
// legacy users stay legacy (in-shell shop), radiolife users keep the overlay.

function readInitial() {
  // Query-param wins if valid — write-through to localStorage so subsequent
  // in-app navigations without the query param stay on the same variant.
  const q = readQueryVariant();
  if (q) {
    try {
      if (typeof window !== "undefined") window.localStorage.setItem(LS_KEY, q);
    } catch { /* private mode etc — ignore */ }
    return q;
  }
  try {
    const v = typeof window !== "undefined" && window.localStorage.getItem(LS_KEY);
    return v === "radiolife" ? "radiolife" : "legacy";
  } catch {
    return "legacy";
  }
}

export const useDesignVariantStore = create((set) => ({
  variant: readInitial(),
  setVariant: (v) => {
    const next = v === "radiolife" ? "radiolife" : "legacy";
    try {
      if (typeof window !== "undefined") window.localStorage.setItem(LS_KEY, next);
    } catch { /* private mode etc — ignore */ }
    set({ variant: next });
  },
  toggle: () => set((s) => {
    const next = s.variant === "radiolife" ? "legacy" : "radiolife";
    try {
      if (typeof window !== "undefined") window.localStorage.setItem(LS_KEY, next);
    } catch { /* ignore */ }
    return { variant: next };
  }),
}));

// Ergonomic hook — returns just the variant string.
export function useDesignVariant() {
  return useDesignVariantStore((s) => s.variant);
}


// Phase PREROLL.EXT — admin ops screens always render Legacy dark
// regardless of the user-chosen variant.  Pages under `/admin/*` should
// consume this hook instead of `useDesignVariant()` so admin chrome
// stays consistent (ops staff don't want radiolife light on admin).
// SSR-safe: falls back to the store when window is unavailable.
export function useEffectivePageVariant() {
  const variant = useDesignVariantStore((s) => s.variant);
  try {
    const pathname = typeof window !== "undefined"
      ? window.location.pathname : "";
    if (pathname && pathname.startsWith("/admin")) return "legacy";
  } catch (_e) { /* ignore */ }
  return variant;
}
