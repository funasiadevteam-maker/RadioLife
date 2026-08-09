// Phase RWD.1 — shared Earn Loop client helpers (web).
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

// Semantic action → web route. Backend stays platform-agnostic.
export const ACTION_ROUTE = {
  listen: "/radio",
  daily_code: "/radio",
  trivia: "/trivia",
  predict: "/predict-win",
  game: "/play",
  discover: "/discover",
  share: "/discover",
  refer: "/profile",
};

export function routeForAction(action) {
  return ACTION_ROUTE[action] || "/earn";
}

export async function fetchEarnOverview() {
  const r = await axios.get(`${API}/me/earn/overview`);
  return r.data;
}

export async function fetchWaysToEarn() {
  const r = await axios.get(`${API}/me/earn/ways-to-earn`);
  return r.data.items || [];
}

export async function claimMission(missionId) {
  const r = await axios.post(`${API}/me/earn/missions/${missionId}/claim`);
  return r.data;
}

// Hook — loads the full overview once; exposes reload.
export function useEarnOverview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    try {
      setError(null);
      const d = await fetchEarnOverview();
      setData(d);
    } catch (e) {
      setError(e?.response?.status === 401 ? "unauth" : "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);
  return { data, loading, error, reload };
}
