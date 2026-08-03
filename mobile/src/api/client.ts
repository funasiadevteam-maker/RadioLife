import axios from 'axios';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;
export const BACKEND = BACKEND_URL;

const TOKEN_KEY = 'bigfm_session_token';

let sessionToken: string | null = null;

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
});

export const radioApi = axios.create({
  baseURL: API_BASE,
  timeout: 120000,
});

/* ── Platform-aware token persistence ──
   expo-secure-store doesn't reliably persist on web (Expo web preview),
   so we fall back to localStorage for web. Native keeps SecureStore. */

function webGet(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function webSet(key: string, val: string) {
  try { localStorage.setItem(key, val); } catch {}
}
function webDel(key: string) {
  try { localStorage.removeItem(key); } catch {}
}

export async function loadToken(): Promise<string | null> {
  try {
    if (Platform.OS === 'web') {
      sessionToken = webGet(TOKEN_KEY);
    } else {
      sessionToken = await SecureStore.getItemAsync(TOKEN_KEY);
    }
  } catch {
    sessionToken = null;
  }
  return sessionToken;
}

export async function saveToken(token: string): Promise<void> {
  sessionToken = token;
  try {
    if (Platform.OS === 'web') {
      webSet(TOKEN_KEY, token);
    } else {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
    }
  } catch {}
}

export async function clearToken(): Promise<void> {
  sessionToken = null;
  try {
    if (Platform.OS === 'web') {
      webDel(TOKEN_KEY);
    } else {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  } catch {}
}

export function getToken(): string | null {
  return sessionToken;
}

/* ── Interceptors ── */

function attachBearer(config: any) {
  if (sessionToken) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${sessionToken}`;
  }
  return config;
}

api.interceptors.request.use(attachBearer);
radioApi.interceptors.request.use(attachBearer);

// On 401 → clear persisted token (caller handles redirect)
function on401(error: any) {
  if (error?.response?.status === 401) {
    clearToken();
  }
  return Promise.reject(error);
}

api.interceptors.response.use((r) => r, on401);
radioApi.interceptors.response.use((r) => r, on401);

export default api;
