// FUUSIC Merchant — sell your own branded gift cards (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Switch, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(0)}`;
const parseDenoms = (s: string) => Array.from(new Set(
  s.split(',').map((x) => Math.round((parseFloat(x.trim()) || 0) * 100)).filter((c) => c >= 100 && c <= 1000000)
)).sort((a, b) => a - b);

export default function MerchantGiftCards() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [denoms, setDenoms] = useState('25, 50, 100');
  const [allowPoints, setAllowPoints] = useState(true);
  const [allowCard, setAllowCard] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/giftcards'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setDenoms('25, 50, 100'); setAllowPoints(true); setAllowCard(true); setEditingId(null); };
  const save = async () => {
    const denominations_cents = parseDenoms(denoms);
    if (!denominations_cents.length) { Alert.alert('Add at least one valid amount'); return; }
    setSaving(true);
    const body = { denominations_cents, allow_points: allowPoints, allow_card: allowCard, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/giftcards/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/giftcards/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p: any) => { setEditingId(p.product_id); setDenoms((p.denominations_cents || []).map((c: number) => c / 100).join(', ')); setAllowPoints(p.allow_points); setAllowCard(p.allow_card); };
  const del = async (pid: string) => { try { await api.delete(`/merchant/marketplace/giftcards/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mgc-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Gift Cards</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mgc-root">
        <View style={s.card} testID="mgc-form">
          <Text style={s.cardTitle}>{editingId ? 'Edit gift card' : 'New gift card'}</Text>
          <Text style={s.label}>Amounts ($, comma separated)</Text>
          <TextInput value={denoms} onChangeText={setDenoms} placeholder="25, 50, 100" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mgc-denoms" />
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by card</Text><Switch value={allowCard} onValueChange={setAllowCard} trackColor={{ true: COLORS.primary }} testID="mgc-allow-card" /></View>
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by BigPoints</Text><Switch value={allowPoints} onValueChange={setAllowPoints} trackColor={{ true: COLORS.primary }} testID="mgc-allow-points" /></View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            {editingId && <TouchableOpacity style={s.cancel} onPress={reset} testID="mgc-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>}
            <TouchableOpacity style={[common.btnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} disabled={saving} onPress={save} testID="mgc-save">
              <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!items.length && <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }} testID="mgc-empty">No gift cards yet.</Text>}
        {items.map((p) => (
          <View key={p.product_id} style={s.item} testID={`mgc-item-${p.product_id}`}>
            <View style={s.itemIcon}><Ionicons name="gift" size={18} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.itemName}>{(p.denominations_cents || []).map(money).join('  ·  ')}</Text>
              <Text style={s.itemMeta}>{[p.allow_card && 'Card', p.allow_points && 'Points', !p.active && 'inactive'].filter(Boolean).join(' · ')}</Text>
            </View>
            <TouchableOpacity onPress={() => edit(p)} style={s.iconBtn} testID={`mgc-edit-${p.product_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
            <TouchableOpacity onPress={() => del(p.product_id)} style={s.iconBtn} testID={`mgc-del-${p.product_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 8 },
  title: { color: COLORS.text, fontSize: 20, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 16, gap: 10 },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  label: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  swRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  swLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  cancel: { flex: 1, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center', paddingVertical: 12 },
  cancelText: { color: COLORS.textDim, fontWeight: '800' },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  itemIcon: { width: 40, height: 40, borderRadius: RADIUS.sm, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  itemMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
});
