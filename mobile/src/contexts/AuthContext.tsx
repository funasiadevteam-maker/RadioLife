import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import api, { loadToken, saveToken, clearToken, BACKEND } from '../api/client';
import { deregisterPushToken } from '../utils/pushNotifications';

export type User = {
  user_id: string;
  name: string;
  email: string;
  picture?: string | null;
  role?: string;
  auth_provider: string;
  onboarding_complete: boolean;
  is_premium?: boolean;
  premium_tier?: string | null;
  subscription_status?: string;
  subscription_period_end?: string | null;
  cancel_at_period_end?: boolean;
  reward_multiplier?: number;
  preference_vector?: any;
  market?: string;
  is_advertiser?: boolean;
  session_token?: string;
  session_expires_at?: string;
} | null;

type Billing = {
  billing_status?: string;
  is_premium?: boolean;
  plan_slug?: string;
  cancel_at_period_end?: boolean;
  period_end?: string;
} | null;

type AuthCtx = {
  user: User;
  setUser: (u: User) => void;
  loading: boolean;
  billing: Billing;
  refresh: () => Promise<User>;
  login: (email: string, password: string) => Promise<any>;
  register: (email: string, password: string, name: string) => Promise<any>;
  logout: () => Promise<void>;
  googleSignIn: () => Promise<void>;
  refreshBilling: () => Promise<Billing>;
};

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);
  const [billing, setBilling] = useState<Billing>(null);

  const refreshBilling = useCallback(async () => {
    try {
      const r = await api.get('/billing/status');
      setBilling(r.data);
      return r.data;
    } catch {
      setBilling(null);
      return null;
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get('/auth/me');
      setUser(r.data);
      refreshBilling();
      return r.data;
    } catch {
      setUser(null);
      setBilling(null);
      return null;
    }
  }, [refreshBilling]);

  // Boot: load persisted token → verify session
  useEffect(() => {
    (async () => {
      await loadToken();
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  // Shared helper: extract session_token from login/register/google response body
  const handleAuthResponse = useCallback(async (data: any) => {
    if (data.session_token) {
      await saveToken(data.session_token);
    }
    setUser(data);
    refreshBilling();
    return data;
  }, [refreshBilling]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post('/auth/login', { email, password });
    return handleAuthResponse(r.data);
  }, [handleAuthResponse]);

  const register = useCallback(async (email: string, password: string, name: string) => {
    const r = await api.post('/auth/register', { email, password, name });
    return handleAuthResponse(r.data);
  }, [handleAuthResponse]);

  const logout = useCallback(async () => {
    try { await deregisterPushToken(api); } catch {}
    try { await api.post('/auth/logout'); } catch {}
    await clearToken();
    setUser(null);
    setBilling(null);
  }, []);

  // Google sign-in via OUR OWN OAuth client (server-side auth-code flow).
  // Opens the system browser to the backend, which 302s to Google's own
  // branded consent screen, then hands the opaque session token back to
  // the app through the deep link (mobile://auth?token=...).
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT
  // URLS, THIS BREAKS THE AUTH.
  const googleSignIn = useCallback(async () => {
    try {
      const returnUrl = Linking.createURL('auth');
      const startUrl =
        `${BACKEND}/api/auth/google/login?platform=mobile&app_redirect=${encodeURIComponent(returnUrl)}`;
      const result = await WebBrowser.openAuthSessionAsync(startUrl, returnUrl);
      if (result.type === 'success' && result.url) {
        const m = result.url.match(/[?&]token=([^&]+)/);
        const token = m ? decodeURIComponent(m[1]) : null;
        if (token) {
          await saveToken(token);
          await refresh();
        }
      }
    } catch {
      /* user can retry from the login screen */
    }
  }, [refresh]);

  return (
    <AuthContext.Provider value={{
      user, setUser, loading, billing, refresh,
      login, register, logout, googleSignIn, refreshBilling,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be inside <AuthProvider>');
  return ctx;
}
