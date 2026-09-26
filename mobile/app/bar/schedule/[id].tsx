// Owner Live Scheduler (mobile) — a bar owner schedules a Live Shopping event
// and pins products from their page. POST /social/liveshows + …/{id}/products
import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Image as ExpoImage } from 'expo-image';
import { useRouter, useLocalSearchParams, useFocusEffect, Stack } from 'expo-router';
import * as Haptics from 'expo-haptics';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../../src/constants/theme';

const PRESETS = [
  { h: 1, l: 'In 1h' }, { h: 3, l: 'In 3h' }, { h: 6, l: 'In 6h' },
  { h: 24, l: 'Tomorrow' }, { h: 48, l: 'In 2 days' },
];
const emptyProduct = () => ({ title: '', price: '', offer: '', image_url: '' });

export default function BarScheduleLive() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [bizName, setBizName] = useState('');
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [when, setWhen] = useState(3);
  const [cover, setCover] = useState('');
  const [catalog, setCatalog] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([emptyProduct(), emptyProduct()]);
  const [busy, setBusy] = useState(false);
  const [genBusy, setGenBusy] = useState(false);

  const genCover = async () => {
    const prompt = (title.trim() || `${bizName || 'bar'} live night`).slice(0, 180);
    setGenBusy(true);
    try {
      const { data } = await api.post('/bar-games/cover-art', { prompt });
      const base = process.env.EXPO_PUBLIC_BACKEND_URL || '';
      setCover(data.url?.startsWith('http') ? data.url : `${base}${data.url}`);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (_) {} finally { setGenBusy(false); }
  };

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/bar-games/${id}`); setBizName(data.business_name || ''); } catch (_) {}
    try { const { data } = await api.get(`/shop/businesses/${id}/products`); setCatalog(data.products || []); } catch (_) {}
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const addFromCatalog = (c: any) => setProducts((l) => [
    ...l.filter((p) => p.title.trim()),
    { title: c.name || '', price: ((c.price_cents || 0) / 100).toString(), offer: '', image_url: c.image_url || '' },
  ]);

  const upd = (i: number, patch: any) => setProducts((l) => l.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const add = () => setProducts((l) => [...l, emptyProduct()]);
  const del = (i: number) => setProducts((l) => l.filter((_, j) => j !== i));

  const submit = async () => {
    if (title.trim().length < 2) return;
    setBusy(true);
    try {
      const { data: show } = await api.post('/social/liveshows', {
        title, description: desc, business_name: bizName,
        cover_url: cover.trim() || null,
        scheduled_at: new Date(Date.now() + when * 3600000).toISOString() });
      const valid = products.filter((p) => p.title.trim());
      for (const p of valid) {
        await api.post(`/social/liveshows/${show.show_id}/products`, {
          title: p.title.trim(), price_cents: Math.round((parseFloat(p.price) || 0) * 100),
          offer: p.offer.trim(), image_url: p.image_url.trim() || null });
      }
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      if (router.canGoBack()) router.back(); else router.replace(`/shop/${id}` as any);
    } catch (_) {} finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={s.screen} testID="bar-schedule-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="schedule-back"><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.hTitle}>Schedule a Live event</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, gap: 14, paddingBottom: 40 }}>
        <TextInput value={title} onChangeText={setTitle} placeholder="Event title" placeholderTextColor={COLORS.textMuted} style={s.input} testID="scheduler-title" />
        <TextInput value={desc} onChangeText={setDesc} placeholder="What’s it about?" placeholderTextColor={COLORS.textMuted} style={[s.input, { height: 70, textAlignVertical: 'top' }]} multiline testID="scheduler-desc" />

        <Text style={s.lbl}>When</Text>
        <View style={s.chipRow} testID="scheduler-when">
          {PRESETS.map((p) => (
            <TouchableOpacity key={p.h} onPress={() => setWhen(p.h)} testID={`scheduler-when-${p.h}`} style={[s.chip, when === p.h && s.chipOn]}>
              <Text style={[s.chipTxt, when === p.h && { color: '#fff' }]}>{p.l}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={s.lbl}>Cover image (optional)</Text>
        {cover.trim() ? <ExpoImage source={{ uri: cover }} style={{ width: '100%', height: 110, borderRadius: RADIUS.md }} contentFit="cover" /> : null}
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={cover} onChangeText={setCover} placeholder="Paste image URL…" autoCapitalize="none" placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID="scheduler-cover" />
          <TouchableOpacity onPress={genCover} disabled={genBusy} style={s.aiBtn} testID="scheduler-gen-cover">
            {genBusy ? <ActivityIndicator color="#7c3aed" /> : <><Ionicons name="sparkles" size={14} color="#7c3aed" /><Text style={s.aiTxt}>AI</Text></>}
          </TouchableOpacity>
        </View>

        {catalog.length > 0 ? (
          <>
            <Text style={s.lbl}>Add from your shop</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }} testID="scheduler-catalog">
              {catalog.map((c) => (
                <TouchableOpacity key={c.product_id} onPress={() => addFromCatalog(c)} testID={`scheduler-catalog-${c.product_id}`} style={s.catCard}>
                  {c.image_url ? <ExpoImage source={{ uri: c.image_url }} style={{ width: '100%', height: 64 }} contentFit="cover" /> : <View style={s.catPlaceholder}><Ionicons name="pricetag-outline" size={16} color={COLORS.textMuted} /></View>}
                  <View style={{ padding: 6 }}>
                    <Text style={s.catName} numberOfLines={1}>{c.name}</Text>
                    <Text style={s.catPrice}>{(c.price_cents / 100).toFixed(0)}</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </>
        ) : null}

        <Text style={s.lbl}>Products to feature</Text>
        {products.map((p, i) => (
          <View key={i} style={s.prod} testID={`scheduler-prod-${i}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <TextInput value={p.title} onChangeText={(v) => upd(i, { title: v })} placeholder="Product name" placeholderTextColor={COLORS.textMuted} style={[s.pInput, { flex: 1 }]} />
              <TouchableOpacity onPress={() => del(i)}><Ionicons name="trash-outline" size={18} color={COLORS.textMuted} /></TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
              <TextInput value={p.price} onChangeText={(v) => upd(i, { price: v })} placeholder="Price" keyboardType="decimal-pad" placeholderTextColor={COLORS.textMuted} style={[s.pInput, { width: 80 }]} />
              <TextInput value={p.offer} onChangeText={(v) => upd(i, { offer: v })} placeholder="Offer (e.g. -20%)" placeholderTextColor={COLORS.textMuted} style={[s.pInput, { flex: 1 }]} />
            </View>
            <TextInput value={p.image_url} onChangeText={(v) => upd(i, { image_url: v })} placeholder="Image URL (optional)" autoCapitalize="none" placeholderTextColor={COLORS.textMuted} style={[s.pInput, { marginTop: 8 }]} />
          </View>
        ))}
        <TouchableOpacity onPress={add} style={s.addBtn} testID="scheduler-add-prod"><Ionicons name="add" size={16} color={COLORS.text} /><Text style={s.addTxt}>Add product</Text></TouchableOpacity>

        <TouchableOpacity onPress={submit} disabled={busy} style={s.save} testID="scheduler-submit">
          {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="radio" size={16} color="#fff" /><Text style={s.saveTxt}>Schedule event</Text></>}
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  hTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.inputBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  aiBtn: { flexDirection: 'row', gap: 4, paddingHorizontal: 14, borderRadius: RADIUS.md, backgroundColor: 'rgba(124,58,237,0.15)', alignItems: 'center', justifyContent: 'center' },
  aiTxt: { color: '#7c3aed', fontWeight: '900', fontSize: FONT.sm },
  lbl: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 14, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, alignItems: 'center', justifyContent: 'center' },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipTxt: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  prod: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, padding: 10 },
  catCard: { width: 96, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card, overflow: 'hidden' },
  catPlaceholder: { width: '100%', height: 64, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  catName: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800' },
  catPrice: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '800' },
  pInput: { backgroundColor: COLORS.inputBg, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 14, height: 38, borderRadius: 19, backgroundColor: COLORS.inputBg },
  addTxt: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  save: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 50, borderRadius: 25, backgroundColor: '#a855f7', marginTop: 8 },
  saveTxt: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
