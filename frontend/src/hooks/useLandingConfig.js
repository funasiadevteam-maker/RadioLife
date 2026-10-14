// Fetches the public landing configuration once (admin-driven). Fails open to
// sensible defaults so the homepage always renders.
import { create } from "zustand";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export const useLandingConfig = create((set, get) => ({
  config: null,
  loaded: false,
  loading: false,
  bootstrap: async () => {
    if (get().loading || get().loaded) return;
    set({ loading: true });
    try {
      const r = await axios.get(`${API}/public/landing-config`);
      set({ config: r.data || null, loaded: true });
    } catch (_e) {
      set({ loaded: true });
    } finally {
      set({ loading: false });
    }
  },
}));
