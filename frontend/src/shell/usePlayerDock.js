// Player dock preference (web desktop): bottom | top | left | right | float.
// Persisted to localStorage for instant apply + synced to the account so it
// sticks across devices.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

const KEY = "fuusic.player.dock";
const EVT = "fuusic-player-dock";
export const DOCK_OPTIONS = ["bottom", "top", "left", "right", "float"];

function read() {
  try {
    const v = localStorage.getItem(KEY);
    return DOCK_OPTIONS.includes(v) ? v : "bottom";
  } catch (_) { return "bottom"; }
}

export function usePlayerDock() {
  const [dock, setDockState] = useState(read);

  useEffect(() => {
    const onEvt = (e) => setDockState(e.detail);
    window.addEventListener(EVT, onEvt);
    return () => window.removeEventListener(EVT, onEvt);
  }, []);

  // Pull the account-saved value once (cross-device persistence).
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/me/ui-prefs`, { withCredentials: true })
      .then(({ data }) => {
        const d = data?.ui_prefs?.player_dock;
        if (alive && DOCK_OPTIONS.includes(d)) {
          try { localStorage.setItem(KEY, d); } catch (_) { /* ignore */ }
          window.dispatchEvent(new CustomEvent(EVT, { detail: d }));
        }
      }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const setDock = useCallback((d) => {
    if (!DOCK_OPTIONS.includes(d)) return;
    try { localStorage.setItem(KEY, d); } catch (_) { /* ignore */ }
    window.dispatchEvent(new CustomEvent(EVT, { detail: d }));
    axios.put(`${API}/me/ui-prefs`, { player_dock: d }, { withCredentials: true }).catch(() => {});
  }, []);

  return { dock, setDock };
}
