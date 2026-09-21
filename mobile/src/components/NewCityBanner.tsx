import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { COLORS, SPACING, RADIUS } from '../constants/theme';
import api from '../api/client';

// Gentle "you're in {city} now — switch?" prompt. Shows only when the
// IP-detected market differs from the applied market; remembers a dismissal
// per detected city so it never nags.
const SUPPORTED = ['dubai', 'new_york', 'london', 'mumbai', 'los_angeles', 'dfw'];
const DISMISS_KEY = 'fuusic.geoPrompt.dismissed.v1';

export default function NewCityBanner() {
  const [market, setMarket] = useState<string | null>(null);
  const [detected, setDetected] = useState<{ market: string; city: string } | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(DISMISS_KEY).then((v) => setDismissed(v)).catch(() => {});
    api.get('/geo/me').then(({ data }) => {
      setMarket(data?.market || null);
      if (data?.detected_market) setDetected({ market: data.detected_market, city: data.detected_city || data.detected_market });
    }).catch(() => {});
  }, []);

  if (hidden || !detected) return null;
  const dm = detected.market;
  if (!SUPPORTED.includes(dm) || dm === market || dismissed === dm) return null;

  const doSwitch = async () => {
    setBusy(true);
    try { await api.patch('/users/me/market', { market: dm }); } catch (_) {}
    setBusy(false);
    setHidden(true);
  };
  const notNow = async () => {
    try { await AsyncStorage.setItem(DISMISS_KEY, dm); } catch (_) {}
    setHidden(true);
  };

  return (
    <View style={st.card} testID="new-city-banner">
      <View style={st.iconWrap}><Ionicons name="location" size={16} color="#fff" /></View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={st.title} numberOfLines={1}>Looks like you're in {detected.city} now</Text>
        <Text style={st.sub} numberOfLines={1}>Switch for local stations, news & offers.</Text>
      </View>
      <Pressable onPress={doSwitch} disabled={busy} style={st.switchBtn} testID="new-city-switch">
        {busy ? <ActivityIndicator size="small" color="#fff" /> : <Text style={st.switchTxt}>Switch</Text>}
      </Pressable>
      <Pressable onPress={notNow} hitSlop={8} style={st.closeBtn} testID="new-city-dismiss">
        <Ionicons name="close" size={16} color={COLORS.textMuted} />
      </Pressable>
    </View>
  );
}

const st = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: 'rgba(168,85,247,0.10)', borderWidth: 1, borderColor: 'rgba(168,85,247,0.35)',
    borderRadius: RADIUS.lg, padding: SPACING.sm + 2, marginBottom: SPACING.md,
  },
  iconWrap: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#a855f7', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: 13, fontWeight: '800' },
  sub: { color: '#c7bce8', fontSize: 11, marginTop: 1 },
  switchBtn: { height: 34, paddingHorizontal: 14, borderRadius: 17, backgroundColor: '#a855f7', alignItems: 'center', justifyContent: 'center' },
  switchTxt: { color: '#fff', fontSize: 12, fontWeight: '900' },
  closeBtn: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
});
