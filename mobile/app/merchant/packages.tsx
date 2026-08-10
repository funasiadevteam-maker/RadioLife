// RadioLife Merchant — sell prepaid packages / bundles (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

export default function MerchantPackages() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', price: '', credits: '', allowPoints: true, allowCard: true });

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/packages'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: '', description: '', price: '', credits: '', allowPoints: true, allowCard: true }); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price || !form.credits) return;
    setSaving(true);
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), credits: parseInt(form.credits, 10) || 1,
      allow_points: form.allowPoints, allow_card: form.allowCard, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/packages/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/packages/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p: any) => { setEditingId(p.package_id); setForm({ name: p.name || '', description: p.description || '', price: ((p.price_cents || 0) / 100).toString(), credits: String(p.credits || ''), allowPoints: p.allow_points, allowCard: p.allow_card }); };
  const del = async (pid: string) => { try { await api.delete(`/merchant/marketplace/packages/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mpkg-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Packages</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mpkg-root">
        <View style={s.card} testID="mpkg-form">
          <Text style={s.cardTitle}>{editingId ? 'Edit package' : 'New package'}</Text>
          <TextInput value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} placeholder="Name e.g. 5 Haircuts" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mpkg-name" />
          <TextInput value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mpkg-desc" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} placeholder="Price" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { flex: 1 }]} testID="mpkg-price" />
            <TextInput value={form.credits} onChangeText={(v) => setForm({ ...form, credits: v })} placeholder="Credits" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { flex: 1 }]} testID="mpkg-credits" />
          </View>
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by card</Text><Switch value={form.allowCard} onValueChange={(v) => setForm({ ...form, allowCard: v })} trackColor={{ true: COLORS.primary }} testID="mpkg-allow-card" /></View>
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by BigPoints</Text><Switch value={form.allowPoints} onValueChange={(v) => setForm({ ...form, allowPoints: v })} trackColor={{ true: COLORS.primary }} testID="mpkg-allow-points" /></View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            {editingId && <TouchableOpacity style={s.cancel} onPress={reset} testID="mpkg-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>}
            <TouchableOpacity style={[common.btnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} disabled={saving} onPress={save} testID="mpkg-save">
              <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!items.length && <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }} testID="mpkg-empty">No packages yet.</Text>}
        {items.map((p) => (
          <View key={p.package_id} style={s.item} testID={`mpkg-item-${p.package_id}`}>
            <View style={s.itemIcon}><Ionicons name="cube" size={18} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.itemName}>{p.name} · {money(p.price_cents)}</Text>
              <Text style={s.itemMeta}>{p.credits} credits · {p.sold_count || 0} sold{!p.active ? ' · inactive' : ''}</Text>
            </View>
            <TouchableOpacity onPress={() => edit(p)} style={s.iconBtn} testID={`mpkg-edit-${p.package_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
            <TouchableOpacity onPress={() => del(p.package_id)} style={s.iconBtn} testID={`mpkg-del-${p.package_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
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
