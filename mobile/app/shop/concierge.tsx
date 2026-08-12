// AI Ordering Concierge (mobile) — chat to order with your memberships applied.
import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, TextInput, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useCartStore } from '../../src/stores/useCartStore';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const EXAMPLES = [
  'Use my Pizza Club for a large Tandoori Chicken pizza tonight',
  'Order me a coffee with my membership',
  'Get a medium pizza with extra cheese',
];

export default function Concierge() {
  const router = useRouter();
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<any>(null);

  const ask = async (q?: string) => {
    const query = (q ?? text).trim();
    if (!query || loading) return;
    setText(query); setLoading(true); setResp(null);
    try {
      const r = await api.post('/shop/concierge', { text: query });
      setResp(r.data);
    } catch {
      setResp({ ok: false, message: 'The concierge is unavailable right now — please try again.' });
    } finally { setLoading(false); }
  };

  const addToOrder = () => {
    const p = resp.proposal;
    useCartStore.getState().addLine(p.business_id, p.business_name, {
      item_id: p.item_id, name: p.name, price_cents: p.unit_price_cents, qty: p.qty,
      selected_option_ids: p.selected_option_ids || [], option_summary: p.option_summary,
      apply_entitlement_id: p.apply_entitlement_id, entitlement_label: p.entitlement_label,
    });
    router.push('/shop/cart');
  };

  const p = resp?.proposal;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="concierge-back">
          <Ionicons name="chevron-back" size={26} color={COLORS.text} />
        </TouchableOpacity>
        <View>
          <Text style={s.eyebrow}>✨ AI CONCIERGE</Text>
          <Text style={s.title}>Order by chat</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="concierge-root">
        <View style={s.inputWrap}>
          <TextInput
            style={s.input}
            value={text}
            onChangeText={setText}
            placeholder="e.g. use my Pizza Club for a large pizza tonight"
            placeholderTextColor={COLORS.textMuted}
            returnKeyType="send"
            onSubmitEditing={() => ask()}
            testID="concierge-input" />
          <TouchableOpacity style={s.sendBtn} onPress={() => ask()} disabled={loading} testID="concierge-send">
            <Ionicons name="send" size={16} color="#fff" />
          </TouchableOpacity>
        </View>

        <View style={s.examples}>
          {EXAMPLES.map((ex) => (
            <TouchableOpacity key={ex} style={s.exChip} onPress={() => ask(ex)} testID="concierge-example">
              <Text style={s.exText}>{ex}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {loading && (
          <View style={{ alignItems: 'center', marginTop: 24 }} testID="concierge-loading">
            <ActivityIndicator color={COLORS.primary} />
            <Text style={{ color: COLORS.textDim, fontWeight: '700', marginTop: 8 }}>Thinking…</Text>
          </View>
        )}

        {resp && !loading && (
          <View style={{ marginTop: SPACING.md }} testID="concierge-response">
            <View style={s.msgRow}>
              <View style={s.msgIcon}><Ionicons name="sparkles" size={15} color="#fff" /></View>
              <Text style={s.msgText}>{resp.message}</Text>
            </View>

            {p && (
              <View style={s.proposal} testID="concierge-proposal">
                <Text style={s.pBiz}>{p.business_name}</Text>
                <Text style={s.pName}>{p.qty}× {p.name}</Text>
                {!!p.option_summary && <Text style={s.pOpts}>{p.option_summary}</Text>}
                {!!p.entitlement_label && (
                  <View style={s.entChip}>
                    <Ionicons name="ribbon" size={11} color={COLORS.primary} />
                    <Text style={s.entChipText}>{p.entitlement_label}</Text>
                  </View>
                )}
                <View style={s.pFooter}>
                  <View>
                    {p.entitlement_discount_cents > 0 && (
                      <Text style={s.pWas}>{money(p.subtotal_cents)}</Text>
                    )}
                    <Text style={s.pTotal} testID="concierge-total">{money(p.total_cents)}</Text>
                  </View>
                  <TouchableOpacity style={s.addBtn} onPress={addToOrder} testID="concierge-add-order">
                    <Ionicons name="bag-add" size={16} color="#fff" />
                    <Text style={s.addBtnText}>Add to order</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  eyebrow: { color: COLORS.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  title: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  inputWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, paddingHorizontal: 12, paddingVertical: 8 },
  input: { flex: 1, color: COLORS.text, fontSize: FONT.sm, padding: 0 },
  sendBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  examples: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  exChip: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 8 },
  exText: { color: COLORS.textDim, fontSize: 11, fontWeight: '800' },
  msgRow: { flexDirection: 'row', gap: 8, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.lg, padding: 12 },
  msgIcon: { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  msgText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', paddingTop: 4 },
  proposal: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: 12 },
  pBiz: { color: COLORS.textMuted, fontSize: 11, fontWeight: '900', letterSpacing: 0.5 },
  pName: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginTop: 2 },
  pOpts: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  entChip: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', backgroundColor: COLORS.primary + '18', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3, marginTop: 6 },
  entChipText: { color: COLORS.primary, fontSize: 11, fontWeight: '900' },
  pFooter: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 14 },
  pWas: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', textDecorationLine: 'line-through' },
  pTotal: { color: COLORS.text, fontSize: 24, fontWeight: '900' },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 18, paddingVertical: 12 },
  addBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
