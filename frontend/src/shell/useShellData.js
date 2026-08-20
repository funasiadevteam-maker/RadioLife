// Shell data: live summary (nav badges, chips, flagships) + the global
// filter-chip selection that Home shelves read to re-scope the feed.
import { useEffect, useState } from "react";
import { create } from "zustand";
import axios from "axios";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";

// Active filter chip (YouTube-style). Home reads this to re-scope shelves.
export const useShellFilter = create((set) => ({
  chip: "all",
  setChip: (chip) => set({ chip }),
}));

// Cached shell summary — one fetch shared across the shell + Home.
let _cache = null;
let _inflight = null;

export function useShellSummary() {
  const city = useGeoStore((s) => s.city);
  const [data, setData] = useState(_cache);
  useEffect(() => {
    let cancel = false;
    const params = city ? `?city=${encodeURIComponent(city)}` : "";
    if (!_inflight) {
      _inflight = axios.get(`${API}/shell/summary${params}`, { withCredentials: true })
        .then((r) => { _cache = r.data; return r.data; })
        .catch(() => ({}))
        .finally(() => { _inflight = null; });
    }
    _inflight.then((d) => { if (!cancel) setData(d); });
    return () => { cancel = true; };
  }, [city]);
  return data || {};
}

// Format a big count with thousands separators (52,847).
export function fmtCount(n) {
  if (n == null) return "";
  try { return Number(n).toLocaleString("en-US"); } catch (_e) { return String(n); }
}
