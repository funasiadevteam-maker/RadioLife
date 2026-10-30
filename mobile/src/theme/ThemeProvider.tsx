// FUUSIC mobile appearance provider — Light / Dark / System + accent colour +
// Scheduled Dark (auto dark/light by local clock). Mirrors the web global theme
// and SHARES the same saved values via /api/shell/prefs, so a user's choice
// carries across web + mobile. `t` holds the active (accent-applied) token set.
import React, { createContext, useContext, useEffect, useState, useCallback, useMemo } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../api/client';
import { THEME, ThemeTokens, Appearance, AccentKey, ACCENTS, withAccent } from './tokens';

const KEY = 'fuusic.appearance';
const KEY_ACCENT = 'fuusic.accent';
const KEY_SCHED = 'fuusic.schedule';

type Schedule = { enabled: boolean; dark_hour: number; light_hour: number };
const DEFAULT_SCHED: Schedule = { enabled: false, dark_hour: 19, light_hour: 7 };

function cleanSchedule(raw: any): Schedule {
  const s: Schedule = { ...DEFAULT_SCHED };
  if (raw && typeof raw === 'object') {
    s.enabled = !!raw.enabled;
    (['dark_hour', 'light_hour'] as const).forEach((k) => {
      const v = parseInt(raw[k], 10);
      if (Number.isInteger(v) && v >= 0 && v <= 23) s[k] = v;
    });
  }
  return s;
}
function inDarkWindow(s: Schedule): boolean {
  const h = new Date().getHours();
  if (s.dark_hour === s.light_hour) return false;
  if (s.dark_hour > s.light_hour) return h >= s.dark_hour || h < s.light_hour;
  return h >= s.dark_hour && h < s.light_hour;
}

// Live binding of the active token set, kept current by the provider so
// non-context screens (reading it as a plain const) re-theme on parent re-render.
export let activeTokens: ThemeTokens = THEME.light;

type Ctx = {
  mode: Appearance;
  theme: 'light' | 'dark';
  accent: AccentKey;
  schedule: Schedule;
  t: ThemeTokens;
  setMode: (m: Appearance) => void;
  setAccent: (a: AccentKey) => void;
  setSchedule: (patch: Partial<Schedule>) => void;
  cycle: () => void;
};

const ThemeCtx = createContext<Ctx>({
  mode: 'light', theme: 'light', accent: 'violet', schedule: DEFAULT_SCHED,
  t: THEME.light, setMode: () => {}, setAccent: () => {}, setSchedule: () => {}, cycle: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const sys = useColorScheme();
  const [mode, setModeState] = useState<Appearance>('light');
  const [accent, setAccentState] = useState<AccentKey>('violet');
  const [schedule, setScheduleState] = useState<Schedule>(DEFAULT_SCHED);
  const [, setTick] = useState(0);

  // Re-evaluate the clock every minute while Scheduled Dark is on.
  useEffect(() => {
    const id = setInterval(() => setTick((x) => x + 1), 60000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [v, a, sc] = await Promise.all([
          AsyncStorage.getItem(KEY), AsyncStorage.getItem(KEY_ACCENT), AsyncStorage.getItem(KEY_SCHED),
        ]);
        if (!alive) return;
        if (v === 'light' || v === 'dark' || v === 'system') setModeState(v);
        if (a && a in ACCENTS) setAccentState(a as AccentKey);
        if (sc) setScheduleState(cleanSchedule(JSON.parse(sc)));
      } catch { /* ignore */ }
      try {
        const r = await api.get('/shell/prefs');
        if (!alive) return;
        const sv = r.data?.theme;
        const sa = r.data?.accent;
        const ss = r.data?.theme_schedule;
        if (sv === 'light' || sv === 'dark' || sv === 'system') {
          setModeState(sv); AsyncStorage.setItem(KEY, sv).catch(() => {});
        }
        if (sa && sa in ACCENTS) {
          setAccentState(sa as AccentKey); AsyncStorage.setItem(KEY_ACCENT, sa).catch(() => {});
        }
        if (ss) {
          const cs = cleanSchedule(ss);
          setScheduleState(cs); AsyncStorage.setItem(KEY_SCHED, JSON.stringify(cs)).catch(() => {});
        }
      } catch { /* anon / offline — keep local */ }
    })();
    return () => { alive = false; };
  }, []);

  const setMode = useCallback((m: Appearance) => {
    const sched = { ...DEFAULT_SCHED, enabled: false };
    setModeState(m);
    setScheduleState((prev) => ({ ...prev, enabled: false }));
    AsyncStorage.setItem(KEY, m).catch(() => {});
    api.put('/shell/prefs', { theme: m, theme_schedule: { ...sched } }).catch(() => {});
  }, []);

  const setAccent = useCallback((a: AccentKey) => {
    setAccentState(a);
    AsyncStorage.setItem(KEY_ACCENT, a).catch(() => {});
    api.put('/shell/prefs', { accent: a }).catch(() => {});
  }, []);

  const setSchedule = useCallback((patch: Partial<Schedule>) => {
    setScheduleState((prev) => {
      const next = cleanSchedule({ ...prev, ...patch });
      AsyncStorage.setItem(KEY_SCHED, JSON.stringify(next)).catch(() => {});
      api.put('/shell/prefs', { theme_schedule: next }).catch(() => {});
      return next;
    });
  }, []);

  const effective: 'light' | 'dark' = schedule.enabled
    ? (inDarkWindow(schedule) ? 'dark' : 'light')
    : (mode === 'system' ? (sys === 'dark' ? 'dark' : 'light') : mode);

  const t = withAccent(THEME[effective], accent, effective);
  activeTokens = t;

  const cycle = useCallback(() => {
    setMode(effective === 'light' ? 'dark' : 'light');
  }, [effective, setMode]);

  const value = useMemo<Ctx>(() => ({
    mode, theme: effective, accent, schedule, t, setMode, setAccent, setSchedule, cycle,
  }), [mode, effective, accent, schedule, t, setMode, setAccent, setSchedule, cycle]);

  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export const useAppTheme = () => useContext(ThemeCtx);
export const useThemeTokens = () => useContext(ThemeCtx).t;
