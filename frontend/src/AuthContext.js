// AuthContext — single source of truth for the signed-in user.
// Reads /api/auth/me on mount (skipping while we still hold a #session_id
// fragment, which AuthCallback will process first).
//
// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// All requests must carry/receive the bigfm_session cookie.
axios.defaults.withCredentials = true;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [billing, setBilling] = useState(null);  // Phase 6.1 — sticky banner state

  const refreshBilling = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/billing/status`);
      setBilling(r.data);
      return r.data;
    } catch (_e) {
      setBilling(null);
      return null;
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/auth/me`);
      setUser(r.data);
      // Fire billing-status fetch in parallel; banner shows past_due/canceled
      refreshBilling();
      return r.data;
    } catch (_e) {
      setUser(null);
      setBilling(null);
      return null;
    }
  }, [refreshBilling]);

  useEffect(() => {
    // CRITICAL: If we landed here mid-OAuth round-trip, skip the /me check.
    // AuthCallback will exchange the session_id and then call refresh() itself.
    if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  // Phase 6.1 — refresh billing status when the tab regains focus (e.g.
  // returning from Stripe Customer Portal). Clears the banner automatically
  // if the user updated their card mid-flow.
  useEffect(() => {
    const onFocus = () => { if (user) refreshBilling(); };
    const onVis = () => { if (document.visibilityState === "visible" && user) refreshBilling(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [user, refreshBilling]);

  const login = useCallback(async (email, password) => {
    const r = await axios.post(`${API}/auth/login`, { email, password });
    setUser(r.data);
    refreshBilling();
    return r.data;
  }, [refreshBilling]);

  const register = useCallback(async (email, password, name) => {
    const r = await axios.post(`${API}/auth/register`, { email, password, name });
    setUser(r.data);
    refreshBilling();
    return r.data;
  }, [refreshBilling]);

  const logout = useCallback(async () => {
    try { await axios.post(`${API}/auth/logout`); } catch (_e) { /* ignore */ }
    setUser(null);
    setBilling(null);
  }, []);

  const googleSignIn = useCallback(() => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirect = window.location.origin + "/";
    window.location.href =
      `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
  }, []);

  const demoLogin = useCallback(async () => {
    const r = await axios.post(`${API}/auth/demo`);
    setUser(r.data);
    refreshBilling();
    return r.data;
  }, [refreshBilling]);

  const value = { user, setUser, loading, refresh, login, register, logout,
                   googleSignIn, demoLogin, billing, refreshBilling };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
