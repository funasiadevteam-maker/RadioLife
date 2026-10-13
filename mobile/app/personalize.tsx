// Personalize Home (mobile) — pick which FUUSIC features show, reorder them,
// see a live preview, discover features you've turned off, and reset to smart
// city defaults. Shared backend with web (/api/social/features).
import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter, Stack } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { SPACING, FONT, RADIUS } from '../src/constants/theme';
import type { ThemeTokens } from '../src/theme/tokens';
import { useAppTheme } from '../src/theme/ThemeProvider';
import { useFeaturePrefs } from '../src/stores/useFeaturePrefs';

const ICONS: Record<string, string> = {
  social: 'people', listen: 'headset', live: 'radio', shop: 'storefront',
  play: 'game-controller', dining: 'restaurant', earn: 'diamond',
  explore: 'compass', sparkles: 'sparkles',
};
const GRADS: Record<string, [string, string]> = {
  social: ['#14b8a6', '#22c55e'], listen: ['#a855f7', '#ec4899'],
  live: ['#f43f5e', '#a855f7'], shop: ['#ec4899', '#f59e0b'],
  play: ['#8b5cf6', '#6366f1'], dining: ['#fb923c', '#ec4899'],
  earn: ['#f59e0b', '#f5c563'], explore: ['#06b6d4', '#3b82f6'],
};
const iconFor = (k: string, fallback: string) =>
  (ICONS[k] || ICONS[fallback] || 'sparkles') as any;
const gradFor = (k: string): [string, string] => GRADS[k] || ['#a855f7', '#ec4899'];

export default function PersonalizeHome() {
  const router = useRouter();
  const { t } = useAppTheme();
  const s = makeStyles(t);
  const { enabled, catalog, mandatory, defaults, homeCity, loaded, bootstrap, reload, save } =
    useFeaturePrefs();

  const [sel, setSel] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (!loaded) bootstrap(); else reload(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (loaded && sel === null) {
      setSel(enabled && enabled.length ? [...enabled] : catalog.map((f) => f.key));
    }
  }, [loaded, enabled, catalog, sel]);

  const byKey = useMemo(
    () => Object.fromEntries(catalog.map((f) => [f.key, f])), [catalog]);
  const isMand = (k: string) => mandatory.includes(k);
  const available = useMemo(
    () => catalog.filter((f) => !(sel || []).includes(f.key)), [catalog, sel]);

  const add = (k: string) => setSel((l) => (l!.includes(k) ? l : [...l!, k]));
  const remove = (k: string) => { if (!isMand(k)) setSel((l) => l!.filter((x) => x !== k)); };
  const move = (k: string, dir: number) => setSel((l) => {
    const i = l!.indexOf(k); const j = i + dir;
    if (i < 0 || j < 0 || j >= l!.length) return l;
    const n = [...l!]; [n[i], n[j]] = [n[j], n[i]]; return n;
  });

  const resetDefaults = () => {
    if (defaults && defaults.length) {
      setSel([...defaults]);
      Haptics.selectionAsync().catch(() => {});
    }
  };

  const onSave = async () => {
    setBusy(true);
    const ordered = [...(sel || [])];
    mandatory.forEach((m) => { if (!ordered.includes(m)) ordered.unshift(m); });
    await save(ordered);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    setBusy(false);
    if (router.canGoBack()) router.back(); else router.replace('/(tabs)/home');
  };

  if (!loaded || sel === null) {
    return (
      <SafeAreaView style={s.screen} testID="personalize-loading">
        <Stack.Screen options={{ headerShown: false }} />
        <View style={s.center}><ActivityIndicator size="large" color={t.primary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.screen} testID="personalize-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="personalize-back">
          <Ionicons name="chevron-back" size={22} color={t.text} />
        </TouchableOpacity>
        <Text style={s.hTitle}>Personalize Home</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120, gap: 14 }}>
        <Text style={s.sub}>
          Turn features on or off and reorder them. Your Home updates to match.
        </Text>

        {defaults && defaults.length > 0 && (
          <TouchableOpacity onPress={resetDefaults} style={s.resetBtn} testID="personalize-reset">
            <Ionicons name="refresh" size={14} color={t.textDim} />
            <Text style={s.resetTxt}>Reset{homeCity ? ` to ${homeCity}` : ' to defaults'}</Text>
          </TouchableOpacity>
        )}

        {/* Live preview */}
        <View style={s.previewCard} testID="personalize-preview">
          <Text style={s.previewHead}>Your FUUSIC World</Text>
          <Text style={s.previewSub}>Live preview · your order</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: 10, paddingTop: 12 }}>
            {sel.map((k) => {
              const f = byKey[k]; if (!f) return null;
              return (
                <View key={k} style={s.previewTile} testID={`personalize-preview-tile-${k}`}>
                  <LinearGradient colors={gradFor(k)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                    style={s.previewIcon}>
                    <Ionicons name={iconFor(k, f.icon)} size={16} color="#fff" />
                  </LinearGradient>
                  <Text style={s.previewLabel}>{f.label}</Text>
                </View>
              );
            })}
          </ScrollView>
        </View>

        {/* Ordered feature list */}
        <Text style={s.sectionLbl}>On your Home</Text>
        <View style={{ gap: 8 }} testID="personalize-selected-list">
          {sel.map((k, idx) => {
            const f = byKey[k]; if (!f) return null;
            return (
              <View key={k} style={s.row} testID={`personalize-feature-${k}`}>
                <LinearGradient colors={gradFor(k)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.rowIcon}>
                  <Ionicons name={iconFor(k, f.icon)} size={16} color="#fff" />
                </LinearGradient>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                    <Text style={s.rowLabel}>{f.label}</Text>
                    {isMand(k) && <Ionicons name="lock-closed" size={11} color={t.textMuted} />}
                  </View>
                  <Text style={s.rowDesc} numberOfLines={1}>{f.desc}</Text>
                </View>
                <View style={s.rowActions}>
                  <TouchableOpacity onPress={() => move(k, -1)} disabled={idx === 0}
                    testID={`personalize-move-up-${k}`}
                    style={[s.iconBtn, idx === 0 && s.iconBtnOff]}>
                    <Ionicons name="chevron-up" size={16} color={t.textDim} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => move(k, 1)} disabled={idx === sel.length - 1}
                    testID={`personalize-move-down-${k}`}
                    style={[s.iconBtn, idx === sel.length - 1 && s.iconBtnOff]}>
                    <Ionicons name="chevron-down" size={16} color={t.textDim} />
                  </TouchableOpacity>
                  {!isMand(k) && (
                    <TouchableOpacity onPress={() => remove(k)} testID={`personalize-remove-${k}`} style={s.iconBtn}>
                      <Ionicons name="close" size={16} color={t.textDim} />
                    </TouchableOpacity>
                  )}
                </View>
              </View>
            );
          })}
        </View>

        {/* Feature discovery */}
        {available.length > 0 && (
          <>
            <Text style={s.sectionLbl}>Discover more</Text>
            <View style={{ gap: 8 }} testID="personalize-discover">
              {available.map((f) => (
                <TouchableOpacity key={f.key} onPress={() => add(f.key)}
                  testID={`personalize-add-${f.key}`} style={s.discoverRow} activeOpacity={0.8}>
                  <LinearGradient colors={gradFor(f.key)} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.rowIcon}>
                    <Ionicons name={iconFor(f.key, f.icon)} size={16} color="#fff" />
                  </LinearGradient>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.rowLabel}>{f.label}</Text>
                    <Text style={s.rowDesc} numberOfLines={1}>{f.desc}</Text>
                  </View>
                  <View style={s.addPill}>
                    <Ionicons name="add" size={14} color={t.primary} />
                    <Text style={s.addTxt}>Add</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}
      </ScrollView>

      <View style={s.footer}>
        <TouchableOpacity onPress={onSave} disabled={busy} style={s.save} testID="personalize-save">
          {busy ? <ActivityIndicator color="#fff" />
            : <Text style={s.saveTxt}>Save my Home</Text>}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: t.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: t.cardBorder },
  hTitle: { color: t.text, fontSize: FONT.xl, fontWeight: '900' },
  sub: { color: t.textDim, fontSize: FONT.sm, lineHeight: 18 },
  resetBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 12, height: 34, borderRadius: 17, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.card },
  resetTxt: { color: t.textDim, fontSize: FONT.sm, fontWeight: '800' },
  previewCard: { backgroundColor: t.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, padding: SPACING.md },
  previewHead: { color: t.text, fontSize: FONT.md, fontWeight: '900' },
  previewSub: { color: t.textMuted, fontSize: FONT.xs, marginTop: 2 },
  previewTile: { width: 92, borderRadius: RADIUS.md, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface, padding: 10, gap: 8 },
  previewIcon: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  previewLabel: { color: t.text, fontSize: FONT.sm, fontWeight: '800' },
  sectionLbl: { color: t.textMuted, fontSize: FONT.xs, fontWeight: '900', letterSpacing: 1.5, textTransform: 'uppercase', marginTop: 4 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: 'rgba(168,85,247,0.06)', borderRadius: RADIUS.md, borderWidth: 1, borderColor: 'rgba(168,85,247,0.28)', padding: 10 },
  rowIcon: { width: 36, height: 36, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  rowLabel: { color: t.text, fontSize: FONT.md, fontWeight: '900' },
  rowDesc: { color: t.textDim, fontSize: FONT.xs, marginTop: 1 },
  rowActions: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  iconBtn: { width: 30, height: 30, borderRadius: 9, borderWidth: 1, borderColor: t.cardBorder, alignItems: 'center', justifyContent: 'center', backgroundColor: t.card },
  iconBtnOff: { opacity: 0.3 },
  discoverRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: t.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: t.cardBorder, padding: 10 },
  addPill: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 10, height: 30, borderRadius: 15, backgroundColor: 'rgba(168,85,247,0.12)' },
  addTxt: { color: t.primary, fontSize: FONT.sm, fontWeight: '900' },
  footer: { position: 'absolute', left: 0, right: 0, bottom: 0, padding: SPACING.md, paddingBottom: 28, backgroundColor: t.bg, borderTopWidth: 1, borderTopColor: t.cardBorder },
  save: { height: 50, borderRadius: 25, backgroundColor: '#a855f7', alignItems: 'center', justifyContent: 'center' },
  saveTxt: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
