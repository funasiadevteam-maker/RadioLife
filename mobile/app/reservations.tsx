// Reservation Manager — view, reschedule, or cancel upcoming bookings.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Booking {
  booking_id: string; campaign_id: string; slot: string; status: string;
  party_size?: number; sponsor_name?: string; venue_title?: string;
  booking_type?: string; available_slots: string[];
}

export default function Reservations() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Booking[]>([]);
  const [favs, setFavs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, fv] = await Promise.all([
        api.get('/bookings/mine'),
        api.get('/favourites/venues').catch(() => ({ data: { items: [] } })),
      ]);
      setItems(r.data.items || []);
      setFavs(fv.data.items || []);
    } catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const rebook = async (campaignId: string) => {
    setBusyId(campaignId);
    try {
      const r = await api.post(`/favourites/venues/${campaignId}/rebook`);
      celebrate({ points: 0, title: `Rebooked ${r.data.venue_title || ''} · ${r.data.slot}` });
      await load();
    } catch { /* ignore */ }
    finally { setBusyId(null); }
  };

  const reschedule = async (b: Booking, slot: string) => {
    setBusyId(b.booking_id);
    try {
      await api.post(`/bookings/${b.booking_id}/reschedule`, { slot });
      celebrate({ points: 0, title: `Moved to ${slot}` });
      setEditId(null);
      await load();
    } catch { /* ignore */ }
    finally { setBusyId(null); }
  };

  const cancel = async (b: Booking) => {
    setBusyId(b.booking_id);
    try { await api.post(`/bookings/${b.booking_id}/cancel`); await load(); }
    catch { /* ignore */ }
    finally { setBusyId(null); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="res-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>My Reservations</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="reservations-root">

        {favs.length > 0 && (
          <View style={{ marginBottom: SPACING.md }} testID="fav-section">
            <Text style={s.favHeader}>Your favourites</Text>
            {favs.map((fv) => (
              <View key={fv.campaign_id} style={s.favCard} testID={`fav-${fv.campaign_id}`}>
                <Ionicons name="heart" size={18} color={COLORS.primary} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.title} numberOfLines={1}>{fv.venue_title || fv.sponsor_name}</Text>
                  <Text style={s.sub}>{fv.usual_slot ? `Usual: ${fv.usual_slot}` : 'Tap to book your usual'}</Text>
                </View>
                <TouchableOpacity style={s.rebookBtn} disabled={!fv.active || busyId === fv.campaign_id}
                  onPress={() => rebook(fv.campaign_id)} testID={`fav-rebook-${fv.campaign_id}`}>
                  {busyId === fv.campaign_id ? <ActivityIndicator color="#fff" />
                    : <Text style={s.rebookText}>{fv.active ? 'Rebook' : 'Closed'}</Text>}
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {items.length === 0 && (
          <View style={s.card}>
            <Ionicons name="calendar-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.empty}>No reservations yet.</Text>
            <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }]}
              onPress={() => router.push('/bookings')} testID="res-book-cta">
              <Ionicons name="calendar" size={16} color="#fff" />
              <Text style={common.btnPrimaryText}>Book a spot</Text>
            </TouchableOpacity>
          </View>
        )}

        {items.map((b) => {
          const editing = editId === b.booking_id;
          const busy = busyId === b.booking_id;
          return (
            <View key={b.booking_id} style={s.card} testID={`res-${b.booking_id}`}>
              <View style={s.head}>
                <View style={s.vIcon}><Ionicons name="restaurant" size={20} color={COLORS.primary} /></View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.title} numberOfLines={1}>{b.venue_title || b.sponsor_name}</Text>
                  <Text style={s.sub}>{b.slot}{b.party_size ? ` · party of ${b.party_size}` : ''}</Text>
                </View>
                <View style={[s.statusPill, b.status === 'cancelled' && s.statusCancel]}>
                  <Text style={[s.statusText, b.status === 'cancelled' && s.statusTextCancel]}>{b.status}</Text>
                </View>
              </View>

              {editing ? (
                <View>
                  <Text style={s.label}>PICK A NEW TIME</Text>
                  <View style={s.slotRow}>
                    {b.available_slots.map((sl) => (
                      <TouchableOpacity key={sl} testID={`res-slot-${b.booking_id}-${sl}`}
                        style={[s.slot, b.slot === sl && s.slotOn]} disabled={busy}
                        onPress={() => reschedule(b, sl)}>
                        <Text style={[s.slotText, b.slot === sl && s.slotTextOn]}>{sl}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <TouchableOpacity style={s.linkBtn} onPress={() => setEditId(null)} testID={`res-cancel-edit-${b.booking_id}`}>
                    <Text style={s.linkText}>Keep current time</Text>
                  </TouchableOpacity>
                </View>
              ) : b.status !== 'cancelled' ? (
                <View style={s.actions}>
                  <TouchableOpacity style={s.actionGhost} onPress={() => setEditId(b.booking_id)}
                    disabled={busy} testID={`res-reschedule-${b.booking_id}`}>
                    <Ionicons name="time-outline" size={15} color={COLORS.primary} />
                    <Text style={s.actionGhostText}>Reschedule</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={s.actionDanger} onPress={() => cancel(b)}
                    disabled={busy} testID={`res-cancel-${b.booking_id}`}>
                    {busy ? <ActivityIndicator color={COLORS.red || '#DC2626'} />
                      : <><Ionicons name="close-circle-outline" size={15} color="#DC2626" />
                        <Text style={s.actionDangerText}>Cancel</Text></>}
                  </TouchableOpacity>
                </View>
              ) : null}
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  vIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  statusPill: { backgroundColor: COLORS.green + '18', paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.full },
  statusText: { color: COLORS.green, fontSize: 10, fontWeight: '900', textTransform: 'capitalize' },
  statusCancel: { backgroundColor: '#DC262618' },
  statusTextCancel: { color: '#DC2626' },
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginTop: SPACING.sm, marginBottom: 6 },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slot: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  slotOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  slotText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  slotTextOn: { color: '#fff' },
  actions: { flexDirection: 'row', gap: 10 },
  actionGhost: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  actionGhostText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  actionDanger: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderColor: '#DC2626', backgroundColor: '#DC262610' },
  actionDangerText: { color: '#DC2626', fontSize: FONT.sm, fontWeight: '800' },
  linkBtn: { alignSelf: 'center', marginTop: 10, padding: 6 },
  linkText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
  favHeader: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginBottom: 8 },
  favCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: 12, marginBottom: 8 },
  rebookBtn: { backgroundColor: COLORS.primary, paddingHorizontal: 16, paddingVertical: 9, borderRadius: RADIUS.full, minWidth: 84, alignItems: 'center' },
  rebookText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
});
