// Merchant Today's Specials — feature products/menu items. Mobile.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

function ItemRow({ item, special, onSave }: any) {
  const [on, setOn] = useState(!!special?.active);
  const [blurb, setBlurb] = useState(special?.blurb || '');
  const [sale, setSale] = useState(special?.sale_price_cents != null ? String((special.sale_price_cents / 100).toFixed(2)) : '');
  const [busy, setBusy] = useState(false);

  const save = async (active: boolean) => {
    setBusy(true);
    await onSave({ kind: item.kind, item_id: item.item_id, blurb: blurb || null,
      sale_price_cents: sale ? Math.round(parseFloat(sale) * 100) : null, active });
    setOn(active); setBusy(false);
  };

  return (
    <View style={s.row} testID={`special-item-${item.item_id}`}>
      <View style={s.rowTop}>
        <View style={s.thumb}><Image source={{ uri: item.image_url }} style={{ flex: 1 }} contentFit="cover" /></View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.name} numberOfLines={1}>{item.name}</Text>
          <Text style={s.meta}>{money(item.price_cents)} · {item.kind === 'menu' ? 'Menu' : 'Product'}</Text>
        </View>
        <TouchableOpacity onPress={() => save(!on)} disabled={busy} testID={`special-toggle-${item.item_id}`}
          style={[s.toggle, on && { backgroundColor: COLORS.primary }]}>
          <Text style={[s.toggleText, on && { color: '#fff' }]}>{on ? '🔥 Featured' : 'Feature'}</Text>
        </TouchableOpacity>
      </View>
      {on && (
        <View style={s.editRow}>
          <TextInput style={s.blurbInput} value={blurb} onChangeText={setBlurb} placeholder="Blurb e.g. 20% off" placeholderTextColor={COLORS.textMuted} testID={`special-blurb-${item.item_id}`} />
          <TextInput style={s.saleInput} value={sale} onChangeText={setSale} keyboardType="decimal-pad" placeholder="Sale $" placeholderTextColor={COLORS.textMuted} testID={`special-sale-${item.item_id}`} />
          <TouchableOpacity style={s.saveBtn} onPress={() => save(true)} disabled={busy} testID={`special-save-${item.item_id}`}>
            <Ionicons name="checkmark" size={18} color="#fff" />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

export default function MerchantSpecials() {
  const router = useRouter();
  const [data, setData] = useState<any>({ specials: [], products: [], menu: [] });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/specials'); setData(r.data); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (body: any) => { await api.put('/merchant/marketplace/specials', body); load(); };

  const specialByItem: Record<string, any> = Object.fromEntries((data.specials || []).map((x: any) => [x.item_id, x]));
  const items = [...(data.products || []), ...(data.menu || [])];

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="merchant-specials-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Today's Specials</Text>
        <View style={{ width: 22 }} />
      </View>
      {loading ? <View style={common.center}><ActivityIndicator color={COLORS.primary} /></View> : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 100 }} testID="merchant-specials-root">
          <Text style={s.hint}>Feature items to appear in the "Today's Specials" row on the Shop home.</Text>
          {!items.length ? <Text style={s.empty} testID="merchant-specials-empty">Add products or menu items first.</Text>
            : items.map((it: any) => <ItemRow key={`${it.kind}-${it.item_id}`} item={it} special={specialByItem[it.item_id]} onSave={save} />)}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  hint: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginBottom: 12 },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  row: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  thumb: { width: 46, height: 46, borderRadius: 10, backgroundColor: COLORS.inputBg, overflow: 'hidden' },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  meta: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  toggle: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 7 },
  toggleText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '900' },
  editRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  blurbInput: { flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  saleInput: { width: 76, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  saveBtn: { backgroundColor: COLORS.text, borderRadius: RADIUS.md, paddingHorizontal: 12, justifyContent: 'center' },
});
