// FUUSIC — mobile Daily Readings subscribe control (Tarot / Horoscope / Numerology).
import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api/client';
import { useThemeTokens } from '../theme/ThemeProvider';

const ITEMS = [
  { k: 'tarot', label: 'Daily Tarot', icon: 'sparkles' },
  { k: 'horoscope', label: 'Horoscope', icon: 'moon' },
  { k: 'numerology', label: 'Numerology', icon: 'calculator' },
];

export default function DailyReadingsCardM({ onChanged }: any) {
  const t = useThemeTokens();
  const [subs, setSubs] = useState<any[] | null>(null);

  useEffect(() => {
    let on = true;
    api.get('/social/daily-readings')
      .then((r) => { if (on) setSubs(r.data?.subscriptions || []); })
      .catch(() => { if (on) setSubs([]); });
    return () => { on = false; };
  }, []);

  if (subs === null) return null;
  const enabled: any = {};
  subs.forEach((s) => { enabled[s.reading_type] = s.enabled; });

  const toggle = async (k: string) => {
    const next = !enabled[k];
    setSubs((p) => {
      const has = (p || []).some((s) => s.reading_type === k);
      const upd = (p || []).map((s) => s.reading_type === k ? { ...s, enabled: next, frequency: next ? 'daily' : 'off' } : s);
      return has ? upd : [...upd, { reading_type: k, enabled: next, frequency: next ? 'daily' : 'off' }];
    });
    try {
      await api.put(`/social/daily-readings/${k}`, { enabled: next, frequency: next ? 'daily' : 'off' });
      onChanged?.();
    } catch (_) {}
  };

  return (
    <View testID="daily-readings-card" style={[s.card, { backgroundColor: t.surface, borderColor: t.border }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 2 }}>
        <Ionicons name="sparkles" size={16} color={t.magenta} />
        <Text style={{ color: t.text, fontWeight: '900', fontSize: 15 }}>Daily Readings</Text>
      </View>
      <Text style={{ color: t.textMuted, fontSize: 12.5, marginBottom: 12 }}>
        Private daily cards, just for you — AI reflection, never shared.
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {ITEMS.map(({ k, label, icon }) => {
          const on = !!enabled[k];
          return (
            <Pressable key={k} onPress={() => toggle(k)} testID={`dr-toggle-${k}`}
              style={[s.chip, { borderColor: on ? t.magenta : t.border, backgroundColor: on ? `${t.magenta}1a` : 'transparent' }]}>
              <Ionicons name={on ? 'checkmark' : (icon as any)} size={14} color={on ? t.magenta : t.textMuted} />
              <Text style={{ color: on ? t.magenta : t.textMuted, fontWeight: '700', fontSize: 13 }}>{label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: { marginHorizontal: 14, marginBottom: 16, borderRadius: 16, borderWidth: 1, padding: 14 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1.5, borderRadius: 999, paddingVertical: 8, paddingHorizontal: 14 },
});
