// Phase H v1 — Commute Mode hook.  Wraps the four /api/commute/v1/* endpoints.
import { useCallback, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api/commute/v1`;

export function useCommuteMode() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const startCommute = useCallback(async ({ origin, destination, activity }) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await axios.post(
        `${API}/start`,
        { origin, destination, activity },
        { withCredentials: true });
      setSession(data);
      return data;
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "commute_start_failed";
      setError(msg);
      throw new Error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const endCommute = useCallback(async (sessionId) => {
    if (!sessionId) return null;
    try {
      const { data } = await axios.post(
        `${API}/session/${sessionId}/end`,
        {},
        { withCredentials: true });
      setSession(null);
      return data;
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "commute_end_failed";
      setError(msg);
      throw new Error(msg);
    }
  }, []);

  const saveCoupon = useCallback(async (offerId, sessionId) => {
    try {
      const { data } = await axios.post(
        `${API}/save-coupon/${offerId}`,
        { session_id: sessionId || null },
        { withCredentials: true });
      // Merge saved flag into local session state, if present
      setSession((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          matched_offers: (prev.matched_offers || []).map((o) =>
            o.offer_id === offerId ? { ...o, saved: true } : o),
        };
      });
      return data;
    } catch (e) {
      const msg = e?.response?.data?.detail || e?.message || "coupon_save_failed";
      setError(msg);
      throw new Error(msg);
    }
  }, []);

  return { session, loading, error, startCommute, endCommute, saveCoupon, setSession };
}
