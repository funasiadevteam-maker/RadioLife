// Phase B — Personalized city tags hook.
//
// Fetches `/api/personalized/city_tags` once per mount + on the 60s
// stale-window the backend already caches on.  Returns the shape the
// home hero + station chrome consume directly:
//
//     { primary_city, tags, fallback_used, isLoading, error, refresh }
//
// Why no React Query / SWR dependency:
// the rest of the codebase fetches with plain axios + useEffect, and
// adding a query lib for a single 60s-cached call would be over-kill.
// We use a tiny in-module cache so multiple components on the same
// page (hero + station strip) share a single network call per minute.
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

const STALE_MS    = 60 * 1000;
const _moduleCache = { ts: 0, data: null, inflight: null };

async function fetchCityTags() {
  const now = Date.now();
  if (_moduleCache.data && now - _moduleCache.ts < STALE_MS) {
    return _moduleCache.data;
  }
  if (_moduleCache.inflight) return _moduleCache.inflight;
  _moduleCache.inflight = axios
    .get(`${API}/personalized/city_tags`, {
      withCredentials: true, timeout: 6000,
    })
    .then((r) => {
      _moduleCache.data = r.data || null;
      _moduleCache.ts    = Date.now();
      _moduleCache.inflight = null;
      return _moduleCache.data;
    })
    .catch((e) => {
      _moduleCache.inflight = null;
      throw e;
    });
  return _moduleCache.inflight;
}

export function useCityTags() {
  const [data,     setData]     = useState(_moduleCache.data);
  const [isLoading, setLoading] = useState(!_moduleCache.data);
  const [error,    setError]    = useState(null);

  const load = useCallback(async () => {
    setLoading(!_moduleCache.data);
    try {
      const d = await fetchCityTags();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const refresh = useCallback(() => {
    _moduleCache.ts = 0; _moduleCache.data = null;
    return load();
  }, [load]);

  return {
    primaryCity:  data?.primary_city || "",
    tags:          Array.isArray(data?.tags) ? data.tags : [],
    fallbackUsed: !!data?.fallback_used,
    isLoading,
    error,
    refresh,
  };
}

/**
 * Helper: format the tags into a "Live in A, B & C" string with
 * graceful fallback for <3 tags.  Used by both the marketing
 * landing hero and the authed home daypart strip.
 */
export function formatLiveInString(tags) {
  if (!tags || tags.length === 0) return "Live everywhere";
  const cities = tags.map((t) => t.city).filter(Boolean);
  if (cities.length === 1) return `Live in ${cities[0]}`;
  if (cities.length === 2) return `Live in ${cities[0]} & ${cities[1]}`;
  return `Live in ${cities[0]}, ${cities[1]} · ${cities[2]}`;
}
