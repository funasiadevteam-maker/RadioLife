// FUUSIC mobile appearance provider — Light / Dark / System. Mirrors the web
// global theme and SHARES the same saved value via /api/shell/prefs, so a
// user's choice carries across web + mobile. `t` holds the active token set.
import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../api/client';
import { THEME, ThemeTokens, Appearance } from './tokens';

const KEY = 'fuusic.appearance';

// Live binding of the active token set. The provider keeps it current (updated
// synchronously in render, before children). Non-context screens read it as a
// plain const so they re-theme when their parent re-renders on a theme change —
// without needing a hook in every nested/function-invoked component.
export let activeTokens: ThemeTokens = THEME.light;

type Ctx = {
  mode: Appearance;
  theme: 'light' | 'dark';
  t: ThemeTokens;
  setMode: (m: Appearance) => void;
  cycle: () => void;
};

const ThemeCtx = createContext<Ctx>({
  mode: 'light', theme: 'light', t: THEME.light, setMode: () => {}, cycle: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const sys = useColorScheme();
  const [mode, setModeState] = useState<Appearance>('light');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const v = await AsyncStorage.getItem(KEY);
        if (alive && (v === 'light' || v === 'dark' || v === 'system')) setModeState(v as Appearance);
      } catch { /* ignore */ }
      try {
        const r = await api.get('/shell/prefs');
        const sv = r.data?.theme;
        if (alive && (sv === 'light' || sv === 'dark' || sv === 'system')) {
          setModeState(sv);
          AsyncStorage.setItem(KEY, sv).catch(() => {});
        }
      } catch { /* anon / offline — keep local */ }
    })();
    return () => { alive = false; };
  }, []);

  const setMode = useCallback((m: Appearance) => {
    setModeState(m);
    AsyncStorage.setItem(KEY, m).catch(() => {});
    api.put('/shell/prefs', { theme: m }).catch(() => {});
  }, []);

  const effective: 'light' | 'dark' = mode === 'system' ? (sys === 'dark' ? 'dark' : 'light') : mode;
  activeTokens = THEME[effective];

  const cycle = useCallback(() => {
    setMode(effective === 'light' ? 'dark' : 'light');
  }, [effective, setMode]);

  const value = useMemo<Ctx>(() => ({
    mode, theme: effective, t: THEME[effective], setMode, cycle,
  }), [mode, effective, setMode, cycle]);

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export const useAppTheme = () => useContext(ThemeCtx);
export const useThemeTokens = () => useContext(ThemeCtx).t;
