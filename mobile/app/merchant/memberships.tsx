// RadioLife Merchant — create membership plans with benefit rules (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const blankEnt = () => ({ label: '', qty: '1', period: 'day', options: '' });
const PERIODS = ['day', 'week', 'month'];

export default function MerchantMemberships() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', price: '', interval: 'month' });
  const [ents, setEnts] = useState<any[]>([blankEnt()]);

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/memberships'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: '', description: '', price: '', interval: 'month' }); setEnts([blankEnt()]); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const entitlements = ents.filter((e) => e.label.trim()).map((e) => ({
      label: e.label.trim(), qty: parseInt(e.qty, 10) || 1, period: e.period,
      options: (e.options || '').split(',').map((o: string) => o.trim()).filter(Boolean),
    }));
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), interval: form.interval,
      entitlements, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/memberships/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/memberships/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p: any) => {
    setEditingId(p.plan_id);
    setForm({ name: p.name || '', description: p.description || '', price: ((p.price_cents || 0) / 100).toString(), interval: p.interval || 'month' });
    setEnts((p.entitlements || []).map((e: any) => ({ label: e.label, qty: String(e.qty), period: e.period, options: (e.options || []).join(', ') })));
    if (!(p.entitlements || []).length) setEnts([blankEnt()]);
  };
  const del = async (pid: string) => { try { await api.delete(`/merchant/marketplace/memberships/items/${pid}`); load(); } catch { /* ignore */ } };
  const updEnt = (i: number, patch: any) => setEnts((a) => a.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mmem-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Memberships</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mmem-root">
        <View style={s.card} testID="mmem-form">
          <Text style={s.cardTitle}>{editingId ? 'Edit membership' : 'New membership'}</Text>
          <TextInput value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} placeholder="Name e.g. Coffee Club" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mmem-name" />
          <TextInput value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mmem-desc" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} placeholder="Price" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { flex: 1 }]} testID="mmem-price" />
            <TouchableOpacity style={[s.input, { flex: 1, justifyContent: 'center' }]} onPress={() => setForm({ ...form, interval: form.interval === 'month' ? 'week' : 'month' })} testID="mmem-interval">
              <Text style={{ color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' }}>{form.interval === 'month' ? 'Monthly' : 'Weekly'}</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.section}>BENEFIT RULES</Text>
          {ents.map((e, i) => (
            <View key={i} style={s.entBox} testID={`mmem-ent-${i}`}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TextInput value={e.label} onChangeText={(v) => updEnt(i, { label: v })} placeholder="e.g. Free coffee" placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID={`mmem-ent-label-${i}`} />
                {ents.length > 1 && <TouchableOpacity style={s.entX} onPress={() => setEnts((a) => a.filter((_, idx) => idx !== i))} testID={`mmem-ent-remove-${i}`}><Ionicons name="close" size={16} color={COLORS.red} /></TouchableOpacity>}
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TextInput value={e.qty} onChangeText={(v) => updEnt(i, { qty: v })} placeholder="Qty" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { width: 70 }]} testID={`mmem-ent-qty-${i}`} />
                <TouchableOpacity style={[s.input, { flex: 1, justifyContent: 'center' }]} testID={`mmem-ent-period-${i}`}
                  onPress={() => updEnt(i, { period: PERIODS[(PERIODS.indexOf(e.period) + 1) % 3] })}>
                  <Text style={{ color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' }}>per {e.period}</Text>
                </TouchableOpacity>
              </View>
              <TextInput value={e.options} onChangeText={(v) => updEnt(i, { options: v })} placeholder="Choices (comma) — blank for fixed" placeholderTextColor={COLORS.textMuted} style={[s.input, { marginTop: 8 }]} testID={`mmem-ent-options-${i}`} />
            </View>
          ))}
          <TouchableOpacity style={s.addEnt} onPress={() => setEnts((a) => [...a, blankEnt()])} testID="mmem-add-ent">
            <Ionicons name="add" size={16} color={COLORS.primary} /><Text style={s.addEntText}>Add benefit</Text>
          </TouchableOpacity>

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            {editingId && <TouchableOpacity style={s.cancel} onPress={reset} testID="mmem-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>}
            <TouchableOpacity style={[common.btnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} disabled={saving} onPress={save} testID="mmem-save">
              <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!items.length && <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }} testID="mmem-empty">No memberships yet.</Text>}
        {items.map((p) => (
          <View key={p.plan_id} style={s.item} testID={`mmem-item-${p.plan_id}`}>
            <View style={s.itemIcon}><Ionicons name="ribbon" size={18} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.itemName}>{p.name} · {money(p.price_cents)}/{p.interval}</Text>
              <Text style={s.itemMeta}>{(p.entitlements || []).length} benefits · {p.member_count || 0} members{!p.active ? ' · inactive' : ''}</Text>
            </View>
            <TouchableOpacity onPress={() => edit(p)} style={s.iconBtn} testID={`mmem-edit-${p.plan_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
            <TouchableOpacity onPress={() => del(p.plan_id)} style={s.iconBtn} testID={`mmem-del-${p.plan_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
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
  section: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900', marginTop: 4 },
  entBox: { borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 8 },
  entX: { width: 42, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  addEnt: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  addEntText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  cancel: { flex: 1, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center', paddingVertical: 12 },
  cancelText: { color: COLORS.textDim, fontWeight: '800' },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  itemIcon: { width: 40, height: 40, borderRadius: RADIUS.sm, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  itemMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
});
