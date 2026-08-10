// Merchant Services — catalogue + incoming bookings (Marketplace Phase C).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const BOOK_NEXT: Record<string, { label: string; status: string }[]> = {
  confirmed: [{ label: 'Mark Completed', status: 'completed' }, { label: 'No Show', status: 'no_show' }],
};

export default function MerchantServices() {
  const router = useRouter();
  const [services, setServices] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: '', description: '', duration: '30', price: '', fee: '', points: '' });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([
        api.get('/merchant/marketplace/services'),
        api.get('/merchant/marketplace/services/bookings'),
      ]);
      setServices(s.data.items || []); setBookings(b.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: '', description: '', duration: '30', price: '', fee: '', points: '' }); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const body = {
      name: form.name.trim(), description: form.description.trim() || null,
      duration_min: parseInt(form.duration, 10) || 30,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100),
      reservation_fee_cents: Math.round((parseFloat(form.fee) || 0) * 100),
      bigpoints: form.points ? parseInt(form.points, 10) : null, active: true,
    };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/services/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/services/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (s: any) => {
    setEditingId(s.service_id);
    setForm({ name: s.name || '', description: s.description || '', duration: String(s.duration_min || 30),
      price: ((s.price_cents || 0) / 100).toString(), fee: ((s.reservation_fee_cents || 0) / 100).toString(),
      points: s.bigpoints != null ? String(s.bigpoints) : '' });
  };
  const del = async (id: string) => { try { await api.delete(`/merchant/marketplace/services/items/${id}`); load(); } catch { /* ignore */ } };
  const setBooking = async (id: string, status: string) => {
    try { await api.patch(`/merchant/marketplace/services/bookings/${id}/status`, { status }); load(); } catch { /* ignore */ }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="msvc-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Services & Bookings</Text>
        <View style={{ width: 22 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="msvc-root">
          <View style={s.formCard}>
            <Text style={s.cardTitle}>{editingId ? 'Edit service' : 'Add a service'}</Text>
            <TextInput style={s.input} value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} placeholder="Service name (e.g. Men Haircut)" placeholderTextColor={COLORS.textMuted} testID="svc-name" />
            <TextInput style={s.input} value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} testID="svc-desc" />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TextInput style={[s.input, { flex: 1 }]} value={form.duration} onChangeText={(v) => setForm({ ...form, duration: v })} keyboardType="number-pad" placeholder="Mins" placeholderTextColor={COLORS.textMuted} testID="svc-duration" />
              <TextInput style={[s.input, { flex: 1 }]} value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} keyboardType="decimal-pad" placeholder="Price" placeholderTextColor={COLORS.textMuted} testID="svc-price" />
              <TextInput style={[s.input, { flex: 1 }]} value={form.fee} onChangeText={(v) => setForm({ ...form, fee: v })} keyboardType="decimal-pad" placeholder="Reserve fee" placeholderTextColor={COLORS.textMuted} testID="svc-fee" />
            </View>
            <TextInput style={s.input} value={form.points} onChangeText={(v) => setForm({ ...form, points: v })} keyboardType="number-pad" placeholder="BigPoints on completion (optional)" placeholderTextColor={COLORS.textMuted} testID="svc-points" />
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
              {editingId && <TouchableOpacity style={[common.btnGhost, { flex: 1 }]} onPress={reset} testID="svc-cancel"><Text style={common.btnGhostText}>Cancel</Text></TouchableOpacity>}
              <TouchableOpacity style={[common.btnPrimary, { flex: 1 }]} onPress={save} disabled={saving} testID="svc-save">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Add Service'}</Text>}
              </TouchableOpacity>
            </View>
          </View>

          <Text style={s.section}>Your services</Text>
          {!services.length && <Text style={s.empty}>No services yet.</Text>}
          {services.map((sv) => (
            <View key={sv.service_id} style={s.svcRow} testID={`msvc-item-${sv.service_id}`}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.svcName}>{sv.name}</Text>
                <Text style={s.svcMeta}>{sv.duration_min} min · {money(sv.price_cents)}{sv.reservation_fee_cents > 0 ? ` · ${money(sv.reservation_fee_cents)} reserve` : ''}</Text>
              </View>
              <TouchableOpacity onPress={() => edit(sv)} style={s.iconBtn} testID={`msvc-edit-${sv.service_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
              <TouchableOpacity onPress={() => del(sv.service_id)} style={s.iconBtn} testID={`msvc-del-${sv.service_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
            </View>
          ))}

          <Text style={s.section}>Incoming bookings</Text>
          {!bookings.length && <Text style={s.empty} testID="msvc-bookings-empty">No paid bookings yet.</Text>}
          {bookings.map((b) => (
            <View key={b.booking_id} style={s.bookCard} testID={`msvc-booking-${b.booking_id}`}>
              <View style={s.bookHead}>
                <Text style={s.bookSvc}>{b.service_name}</Text>
                <Text style={s.bookStatus}>{b.status}</Text>
              </View>
              <Text style={s.bookMeta}>{b.date} · {b.start_time} · {b.duration_min} min · rewards {b.points_to_award}</Text>
              {(BOOK_NEXT[b.status] || []).length > 0 && (
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                  {BOOK_NEXT[b.status].map((a) => (
                    <TouchableOpacity key={a.status} onPress={() => setBooking(b.booking_id, a.status)}
                      style={[a.status === 'completed' ? s.doneBtn : s.noshowBtn]} testID={`msvc-book-${a.status}-${b.booking_id}`}>
                      <Text style={a.status === 'completed' ? s.doneText : s.noshowText}>{a.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              {b.status === 'completed' && <Text style={s.awarded}>✓ {b.points_to_award} BigPoints awarded</Text>}
            </View>
          ))}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  formCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 4 },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, marginTop: 8 },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: SPACING.lg, marginBottom: 8 },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: 8 },
  svcRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  svcName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  svcMeta: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  iconBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  bookCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14, marginBottom: 10 },
  bookHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  bookSvc: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  bookStatus: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900', textTransform: 'uppercase' },
  bookMeta: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginTop: 4 },
  doneBtn: { flex: 1, alignItems: 'center', backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingVertical: 10 },
  doneText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  noshowBtn: { flex: 1, alignItems: 'center', backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingVertical: 10 },
  noshowText: { color: COLORS.textDim, fontWeight: '800', fontSize: FONT.sm },
  awarded: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '800', marginTop: 10 },
});
