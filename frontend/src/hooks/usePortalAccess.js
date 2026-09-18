// Phase PORTAL.0 — AccessResolver (client).
// ONE shared source of the current user's platform role + all merchant/
// advertiser workspaces, driven by the design-agnostic /api/portal/context
// endpoint. Consumed by PortalRoleRouter (post-login routing) and the
// WorkspaceSwitcher. Presentation is chosen per design variant elsewhere —
// this store is purely functional/authorization state (no theme awareness).
import { create } from "zustand";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const LS_KEY = "bigfm_active_workspace";

function _readActive() {
  try {
    return (typeof window !== "undefined"
      && window.localStorage.getItem(LS_KEY)) || null;
  } catch {
    return null;
  }
}

export const usePortalAccess = create((set, get) => ({
  loaded: false,
  loading: false,
  workspaces: [],
  platformAdmin: false,
  previewAccess: false,
  recommendedRoute: "/",
  recommendedWorkspaceId: null,
  needsChoice: false,
  activeWorkspaceId: _readActive(),

  fetch: async () => {
    set({ loading: true });
    try {
      const r = await axios.get(`${API}/portal/context`, { withCredentials: true });
      const d = r.data || {};
      const ws = d.workspaces || [];
      // Keep a valid persisted active workspace. Only auto-pick the
      // recommendation when there's NO ambiguity — otherwise leave it unset
      // so PortalRoleRouter shows the workspace chooser.
      let active = get().activeWorkspaceId;
      if (active && !ws.find((w) => w.id === active)) active = null;
      if (!active && !d.needs_workspace_choice) {
        active = d.recommended_workspace_id || null;
      }
      set({
        loaded: true,
        loading: false,
        workspaces: ws,
        platformAdmin: !!d.platform_admin,
        previewAccess: !!d.preview_access,
        recommendedRoute: d.recommended_route || "/",
        recommendedWorkspaceId: d.recommended_workspace_id || null,
        needsChoice: !!d.needs_workspace_choice,
        activeWorkspaceId: active,
      });
      return d;
    } catch {
      // Fail soft — a context hiccup should never hard-block navigation.
      set({ loaded: true, loading: false, workspaces: [] });
      return null;
    }
  },

  setActive: (id) => {
    try {
      if (typeof window !== "undefined") window.localStorage.setItem(LS_KEY, id);
    } catch { /* private mode — ignore */ }
    set({ activeWorkspaceId: id });
  },

  getActiveWorkspace: () => {
    const { workspaces, activeWorkspaceId } = get();
    return workspaces.find((w) => w.id === activeWorkspaceId) || null;
  },

  reset: () => {
    try {
      if (typeof window !== "undefined") window.localStorage.removeItem(LS_KEY);
    } catch { /* ignore */ }
    set({ loaded: false, workspaces: [], activeWorkspaceId: null,
                platformAdmin: false, needsChoice: false });
  },
}));
