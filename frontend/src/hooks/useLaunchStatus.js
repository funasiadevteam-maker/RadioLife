// Soft-launch — Business Setup Mode launch status.
// A tiny Zustand store that fetches /api/launch/status once (and can refresh
// on auth change). Fails OPEN on error so a status hiccup never locks users out.
import { create } from "zustand";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export const useLaunchStore = create((set, get) => ({
  loaded: false,
  businessSetupMode: false,
  hasBypass: true,
  offerMonths: 6,
  waitlistEnabled: true,
  bypassReason: null,
  launchAt: null,
  fetch: async () => {
    try {
      const r = await axios.get(`${API}/launch/status`, { withCredentials: true });
      const d = r.data || {};
      set({
        loaded: true,
        businessSetupMode: !!d.business_setup_mode,
        hasBypass: d.has_bypass !== false,
        offerMonths: d.offer_months || 6,
        waitlistEnabled: d.waitlist_enabled !== false,
        bypassReason: d.bypass_reason || null,
        launchAt: d.launch_at || null,
      });
    } catch (_e) {
      // Fail open — never lock everyone out on a transient error.
      set({ loaded: true });
    }
  },
  refresh: () => get().fetch(),
}));

// True only once status has loaded AND Business Setup Mode is on AND the
// current visitor lacks bypass (admin / approved business / preview token).
export function useLaunchBlocked() {
  const loaded = useLaunchStore((s) => s.loaded);
  const mode = useLaunchStore((s) => s.businessSetupMode);
  const bypass = useLaunchStore((s) => s.hasBypass);
  return loaded && mode && !bypass;
}
