// FUUSIC Merchant — create ticketed events with limited capacity (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Switch, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => (c === 0 ? 'Free' : `$${(c / 100).toFixed(2)}`);

export default function MerchantEvents() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: '', description: '', location: '', startsAt: '', price: '', capacity: '', allowPoints: true, allowCard: true });

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/events'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ title: '', description: '', location: '', startsAt: '', price: '', capacity: '', allowPoints: true, allowCard: true }); setEditingId(null); };
  const save = async () => {
    if (!form.title.trim() || !form.startsAt.trim() || !form.capacity) { Alert.alert('Title, date/time and capacity are required'); return; }
    setSaving(true);
    let iso = form.startsAt.trim();
    try { iso = new Date(form.startsAt.trim()).toISOString(); } catch { /* keep raw */ }
    const body = { title: form.title.trim(), description: form.description.trim() || null,
      location: form.location.trim() || null, starts_at: iso,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), capacity: parseInt(form.capacity, 10) || 1,
      allow_points: form.allowPoints, allow_card: form.allowCard, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/events/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/events/items', body);
      reset(); load();
    } catch (e: any) { Alert.alert('Save failed', e?.response?.data?.detail?.code || 'Try again'); } finally { setSaving(false); }
  };
  const edit = (ev: any) => { setEditingId(ev.event_id); setForm({ title: ev.title || '', description: ev.description || '', location: ev.location || '', startsAt: (ev.starts_at || '').slice(0, 16), price: ((ev.price_cents || 0) / 100).toString(), capacity: String(ev.capacity || ''), allowPoints: ev.allow_points, allowCard: ev.allow_card }); };
  const del = async (eid: string) => { try { await api.delete(`/merchant/marketplace/events/items/${eid}`); load(); } catch { /* ignore */ } };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mevt-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Events</Text>
        <TouchableOpacity onPress={() => router.push('/merchant/ticket-scan')} testID="mevt-scan-link"
          style={{ marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.primary, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 }}>
          <Ionicons name="qr-code-outline" size={15} color="#fff" />
          <Text style={{ color: '#fff', fontWeight: '900', fontSize: FONT.xs }}>Scan</Text>
        </TouchableOpacity>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mevt-root">
        <View style={s.card} testID="mevt-form">
          <Text style={s.cardTitle}>{editingId ? 'Edit event' : 'New event'}</Text>
          <TextInput value={form.title} onChangeText={(v) => setForm({ ...form, title: v })} placeholder="Title e.g. Live Jazz Night" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mevt-title" />
          <TextInput value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mevt-desc" />
          <TextInput value={form.location} onChangeText={(v) => setForm({ ...form, location: v })} placeholder="Location (optional)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mevt-location" />
          <TextInput value={form.startsAt} onChangeText={(v) => setForm({ ...form, startsAt: v })} placeholder="Starts (YYYY-MM-DD HH:MM)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mevt-startsat" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} placeholder="Price (0 = free)" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { flex: 1 }]} testID="mevt-price" />
            <TextInput value={form.capacity} onChangeText={(v) => setForm({ ...form, capacity: v })} placeholder="Capacity" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { flex: 1 }]} testID="mevt-capacity" />
          </View>
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by card</Text><Switch value={form.allowCard} onValueChange={(v) => setForm({ ...form, allowCard: v })} trackColor={{ true: COLORS.primary }} testID="mevt-allow-card" /></View>
          <View style={s.swRow}><Text style={s.swLabel}>Allow pay by BigPoints</Text><Switch value={form.allowPoints} onValueChange={(v) => setForm({ ...form, allowPoints: v })} trackColor={{ true: COLORS.primary }} testID="mevt-allow-points" /></View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            {editingId && <TouchableOpacity style={s.cancel} onPress={reset} testID="mevt-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>}
            <TouchableOpacity style={[common.btnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} disabled={saving} onPress={save} testID="mevt-save">
              <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!items.length && <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }} testID="mevt-empty">No events yet.</Text>}
        {items.map((ev) => (
          <View key={ev.event_id} style={s.item} testID={`mevt-item-${ev.event_id}`}>
            <View style={s.itemIcon}><Ionicons name="calendar" size={18} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.itemName} numberOfLines={1}>{ev.title} · {money(ev.price_cents)}</Text>
              <Text style={s.itemMeta}>{ev.tickets_sold}/{ev.capacity} sold{ev.sold_out ? ' · SOLD OUT' : ''}{!ev.active ? ' · inactive' : ''}</Text>
            </View>
            <TouchableOpacity onPress={() => edit(ev)} style={s.iconBtn} testID={`mevt-edit-${ev.event_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
            <TouchableOpacity onPress={() => del(ev.event_id)} style={s.iconBtn} testID={`mevt-del-${ev.event_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
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
