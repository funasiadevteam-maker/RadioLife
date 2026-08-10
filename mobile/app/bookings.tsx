// Booking CPA — consumer bookings (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Venue {
  campaign_id: string; sponsor_name?: string; title: string;
  booking_type: string; slots: string[];
}

export default function Bookings() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Venue[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [slot, setSlot] = useState('');
  const [party, setParty] = useState('2');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState<Record<string, string>>({});
  const [mine, setMine] = useState<{ booking_id: string; slot: string; sponsor_name?: string; venue_title?: string; party_size?: number }[]>([]);

  const load = useCallback(async () => {
    try {
      const [avail, m] = await Promise.all([
        api.get('/bookings/available'),
        api.get('/bookings/mine').catch(() => ({ data: { items: [] } })),
      ]);
      setItems(avail.data.items || []);
      setMine(m.data.items || []);
    } catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const book = async (v: Venue) => {
    if (!slot) return;
    if (!name.trim() || !phone.trim()) return;
    setBusy(true);
    try {
      const r = await api.post(`/bookings/${v.campaign_id}/book`,
        { slot, party_size: Number(party), name, phone });
      setBooked((p) => ({ ...p, [v.campaign_id]: `${slot} · party of ${party}` }));
      celebrate({ points: 0, title: `Booked at ${r.data.sponsor_name || v.title}!` });
      setOpenId(null); setSlot(''); setName(''); setPhone('');
      load();
    } catch { /* inactive */ }
    finally { setBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="bk-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Book a Spot</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="bookings-root">
        <Text style={s.intro}>Reserve a table or appointment at local venues.</Text>

        {mine.length > 0 && (
          <TouchableOpacity style={s.reminder} testID="bookings-reminder"
            onPress={() => router.push('/reservations')} activeOpacity={0.85}>
            <View style={s.remHead}>
              <Ionicons name="notifications" size={16} color={COLORS.primary} />
              <Text style={s.remTitle}>Upcoming reservations</Text>
              <View style={{ flex: 1 }} />
              <Text style={s.remManage}>Manage</Text>
              <Ionicons name="chevron-forward" size={14} color={COLORS.primary} />
            </View>
            {mine.slice(0, 3).map((b) => (
              <Text key={b.booking_id} style={s.remLine} testID={`bk-mine-${b.booking_id}`}>
                {b.venue_title || b.sponsor_name} · {b.slot}{b.party_size ? ` · party of ${b.party_size}` : ''}
              </Text>
            ))}
            <Text style={s.remHint}>Tap to reschedule or cancel · we&apos;ll remind you before your slot.</Text>
          </TouchableOpacity>
        )}

        {items.length === 0 && (
          <View style={s.card}>
            <Ionicons name="calendar-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.empty}>No venues taking bookings right now.</Text>
          </View>
        )}

        {items.map((v) => {
          const done = booked[v.campaign_id];
          const open = openId === v.campaign_id;
          return (
            <View key={v.campaign_id} style={s.card} testID={`bk-venue-${v.campaign_id}`}>
              <View style={s.head}>
                <View style={s.vIcon}><Ionicons name="restaurant" size={20} color={COLORS.primary} /></View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.title} numberOfLines={1}>{v.title}</Text>
                  <Text style={s.sub}>{v.sponsor_name} · {v.booking_type}</Text>
                </View>
              </View>

              {done ? (
                <View style={s.confirmed} testID={`bk-confirmed-${v.campaign_id}`}>
                  <Ionicons name="checkmark-circle" size={18} color={COLORS.green} />
                  <Text style={s.confirmedText}>Confirmed — {done}</Text>
                </View>
              ) : open ? (
                <View>
                  <Text style={s.label}>PICK A TIME</Text>
                  <View style={s.slotRow}>
                    {v.slots.map((sl) => (
                      <TouchableOpacity key={sl} testID={`bk-slot-${v.campaign_id}-${sl}`}
                        style={[s.slot, slot === sl && s.slotOn]} onPress={() => setSlot(sl)}>
                        <Text style={[s.slotText, slot === sl && s.slotTextOn]}>{sl}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>PARTY</Text>
                      <TextInput style={s.input} value={party} onChangeText={setParty}
                        keyboardType="number-pad" testID="bk-party" />
                    </View>
                    <View style={{ flex: 2 }}>
                      <Text style={s.label}>NAME</Text>
                      <TextInput style={s.input} value={name} onChangeText={setName}
                        placeholder="Your name" placeholderTextColor={COLORS.textMuted} testID="bk-name" />
                    </View>
                  </View>
                  <Text style={s.label}>PHONE</Text>
                  <TextInput style={s.input} value={phone} onChangeText={setPhone}
                    keyboardType="phone-pad" placeholder="Contact number"
                    placeholderTextColor={COLORS.textMuted} testID="bk-phone" />
                  <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }]}
                    onPress={() => book(v)} disabled={busy} testID={`bk-confirm-${v.campaign_id}`}>
                    {busy ? <ActivityIndicator color="#fff" />
                      : <><Ionicons name="calendar" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Confirm booking</Text></>}
                  </TouchableOpacity>
                </View>
              ) : (
                <TouchableOpacity style={s.bookBtn} onPress={() => { setOpenId(v.campaign_id); setSlot(''); }}
                  testID={`bk-open-${v.campaign_id}`}>
                  <Ionicons name="calendar-outline" size={16} color={COLORS.primary} />
                  <Text style={s.bookText}>Book now</Text>
                </TouchableOpacity>
              )}
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
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  reminder: { backgroundColor: COLORS.primary + '0F', borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.primary + '44', padding: SPACING.md, marginBottom: SPACING.md },
  remHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  remTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  remManage: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', marginRight: 2 },
  remLine: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginBottom: 3 },
  remHint: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 4 },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  vIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1, textTransform: 'capitalize' },
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginTop: SPACING.sm, marginBottom: 6 },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slot: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  slotOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  slotText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  slotTextOn: { color: '#fff' },
  row2: { flexDirection: 'row', gap: 10 },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  bookBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  bookText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  confirmed: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.green + '14', borderWidth: 1, borderColor: COLORS.green + '55' },
  confirmedText: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '800' },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
});
