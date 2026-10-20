// FUUSIC Travel — mobile deal browser (search / filter / follow).
// Following the "travel" topic surfaces recommended deals in the social wall.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

type Deal = {
  deal_id: string; title: string; deal_type: string; destination: string;
  price_cents: number; strike_cents?: number; bigpoints: number; image_url?: string;
  duration?: string; rating?: number; promoted?: boolean;
};

const money = (c: number) => `$${Math.round((c || 0) / 100)}`;

type Trend = {
  destination: string; city: string; country: string; emoji: string;
  price: number; airline?: string; transfers: number; deep_link: string;
};

const HUBS: { iata: string; city: string; emoji: string }[] = [
  { iata: 'DXB', city: 'Dubai', emoji: '🇦🇪' },
  { iata: 'AUH', city: 'Abu Dhabi', emoji: '🇦🇪' },
  { iata: 'DOH', city: 'Doha', emoji: '🇶🇦' },
  { iata: 'RUH', city: 'Riyadh', emoji: '🇸🇦' },
  { iata: 'JED', city: 'Jeddah', emoji: '🇸🇦' },
  { iata: 'KWI', city: 'Kuwait City', emoji: '🇰🇼' },
  { iata: 'CAI', city: 'Cairo', emoji: '🇪🇬' },
  { iata: 'IST', city: 'Istanbul', emoji: '🇹🇷' },
  { iata: 'LON', city: 'London', emoji: '🇬🇧' },
  { iata: 'DEL', city: 'Delhi', emoji: '🇮🇳' },
  { iata: 'BOM', city: 'Mumbai', emoji: '🇮🇳' },
  { iata: 'KHI', city: 'Karachi', emoji: '🇵🇰' },
];

function TrendingRow() {
  const [origin, setOrigin] = useState<string | null>(null);
  const [originCity, setOriginCity] = useState('Dubai');
  const [confident, setConfident] = useState(true);
  const [items, setItems] = useState<Trend[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    api.get('/travel/nearest-airport')
      .then((r) => {
        if (!on) return;
        const d = r.data || {};
        setOrigin((d.origin || 'DXB').toUpperCase());
        setOriginCity(d.city || 'Dubai');
        setConfident(!!d.confident);
      })
      .catch(() => { if (on) { setOrigin('DXB'); setOriginCity('Dubai'); setConfident(false); } });
    return () => { on = false; };
  }, []);

  useEffect(() => {
    if (!origin) return;
    let on = true;
    setLoading(true);
    api.get(`/travel/trending?origin=${origin}&limit=8`)
      .then((r) => {
        if (!on) return;
        setItems(r.data?.items || []);
        if (r.data?.origin_city && r.data.origin_city !== origin) setOriginCity(r.data.origin_city);
      })
      .catch(() => { if (on) setItems([]); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [origin]);

  const hubList = (!origin || HUBS.some((h) => h.iata === origin))
    ? HUBS : [{ iata: origin, city: originCity, emoji: '📍' }, ...HUBS];

  return (
    <View style={{ marginTop: 6 }} testID="travel-trending">
      <View style={tr.head}>
        <Ionicons name="trending-up" size={15} color={COLORS.primary} />
        <Text style={tr.headTxt} numberOfLines={1}>Trending from {originCity}</Text>
        <View style={tr.liveDot}><Text style={tr.liveDotTxt}>LIVE</Text></View>
      </View>
      {!confident && (
        <View style={tr.prompt} testID="travel-origin-prompt">
          <Ionicons name="location-outline" size={12} color={COLORS.primary} />
          <Text style={tr.promptTxt}>Not your city? Pick your departure city below.</Text>
        </View>
      )}
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 8, paddingBottom: 8 }}
        testID="travel-origin-switcher">
        {hubList.map((h) => {
          const on = origin === h.iata;
          return (
            <TouchableOpacity key={h.iata} testID={`travel-origin-${h.iata}`}
              onPress={() => { setOrigin(h.iata); setOriginCity(h.city); setConfident(true); }}
              style={[tr.originChip, on && tr.originChipOn]}>
              <Text style={[tr.originChipTxt, on && tr.originChipTxtOn]}>{h.emoji} {h.city}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 10 }}>
        {loading ? (
          [0, 1, 2, 3].map((i) => <View key={i} style={[tr.card, { backgroundColor: COLORS.inputBg }]} />)
        ) : items.length === 0 ? (
          <Text style={tr.empty}>No live prices for this origin right now.</Text>
        ) : (
          items.map((it) => (
            <TouchableOpacity key={it.destination} activeOpacity={0.85} testID={`trending-${it.destination}`}
              onPress={() => Linking.openURL(it.deep_link).catch(() => {})} style={tr.card}>
              <Text style={{ fontSize: 22 }}>{it.emoji}</Text>
              <Text style={tr.city} numberOfLines={1}>{it.city}</Text>
              <Text style={tr.country} numberOfLines={1}>{it.country}</Text>
              <Text style={tr.price}>from {money(it.price * 100)}</Text>
              <Text style={tr.sub}>{it.transfers === 0 ? 'Direct' : `${it.transfers} stop`} · {it.airline}</Text>
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </View>
  );
}

const tr = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: SPACING.md, marginBottom: 8 },
  headTxt: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  liveDot: { backgroundColor: COLORS.red, borderRadius: 999, paddingHorizontal: 7, paddingVertical: 2, marginLeft: 2 },
  liveDotTxt: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.4 },
  card: { width: 136, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 11, gap: 1, minHeight: 104 },
  city: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
  country: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  price: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 3 },
  sub: { color: COLORS.textDim, fontSize: 10, fontWeight: '600' },
  prompt: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: SPACING.md, marginBottom: 6 },
  promptTxt: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  originChip: { flexShrink: 0, height: 32, justifyContent: 'center', paddingHorizontal: 12, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  originChipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  originChipTxt: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  originChipTxtOn: { color: '#fff' },
  empty: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', paddingHorizontal: SPACING.md, paddingVertical: 10 },
});
const TYPES: { key: string; label: string; icon: any }[] = [
  { key: 'all', label: 'All', icon: 'globe-outline' },
  { key: 'flight', label: 'Flights', icon: 'airplane-outline' },
  { key: 'hotel', label: 'Hotels', icon: 'bed-outline' },
  { key: 'package', label: 'Packages', icon: 'briefcase-outline' },
  { key: 'experience', label: 'Experiences', icon: 'compass-outline' },
  { key: 'cruise', label: 'Cruises', icon: 'boat-outline' },
];
const SORTS = [
  { key: 'featured', label: 'Featured' }, { key: 'price_low', label: 'Price ↑' },
  { key: 'price_high', label: 'Price ↓' }, { key: 'rating', label: 'Top Rated' },
];

export default function TravelHome() {
  const router = useRouter();
  const [items, setItems] = useState<Deal[]>([]);
  const [type, setType] = useState('all');
  const [sort, setSort] = useState('featured');
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);
  const [following, setFollowing] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);

  useEffect(() => {
    api.get('/travel/follow').then((r) => setFollowing(!!r.data?.following)).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = { sort };
      if (type !== 'all') params.type = type;
      if (q.trim()) params.q = q.trim();
      const r = await api.get('/travel/deals', { params });
      setItems(r.data?.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [type, sort, q]);
  useEffect(() => { load(); }, [load]);

  const toggleFollow = async () => {
    setFollowBusy(true);
    const next = !following;
    setFollowing(next);
    try {
      if (next) await api.post('/travel/follow');
      else await api.delete('/travel/follow');
    } catch { setFollowing(!next); }
    finally { setFollowBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="travel-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Travel</Text>
        <TouchableOpacity onPress={() => router.push('/shop/travel/trips' as any)} testID="travel-my-trips"
          hitSlop={8} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          <Ionicons name="briefcase-outline" size={16} color={COLORS.primary} />
          <Text style={{ color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' }}>My Trips</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 90 }} testID="travel-home-root"
        stickyHeaderIndices={[]}>
        <TouchableOpacity onPress={toggleFollow} disabled={followBusy} testID="travel-follow-btn"
          activeOpacity={0.9} style={[s.follow, following && s.followOn]}>
          <Ionicons name={following ? 'notifications' : 'notifications-outline'} size={20}
            color={following ? COLORS.primary : '#fff'} />
          <View style={{ flex: 1 }}>
            <Text style={[s.followTitle, following && { color: COLORS.text }]}>
              {following ? 'Following Travel deals' : 'Follow Travel deals'}
            </Text>
            <Text style={[s.followSub, following && { color: COLORS.textMuted }]}>
              {following ? 'Recommended deals show in your wall.' : 'Get recommended deals in your wall.'}
            </Text>
          </View>
          <View style={[s.followPill, following && s.followPillOn]}>
            <Text style={[s.followPillTxt, following && { color: COLORS.text }]}>{following ? 'Following' : 'Follow'}</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity activeOpacity={0.9} testID="travel-live-search-btn"
          onPress={() => router.push('/shop/travel/search' as any)} style={s.liveBtn}>
          <Ionicons name="airplane" size={18} color="#fff" />
          <View style={{ flex: 1 }}>
            <Text style={s.liveBtnTitle}>Search live flights &amp; hotels</Text>
            <Text style={s.liveBtnSub}>Real-time prices · powered by Travelpayouts</Text>
          </View>
          <View style={s.liveBadge}><Text style={s.liveBadgeTxt}>LIVE</Text></View>
        </TouchableOpacity>

        <TrendingRow />

        <View style={s.search}>
          <Ionicons name="search" size={18} color={COLORS.textMuted} />
          <TextInput value={q} onChangeText={setQ} placeholder="Search destinations, deals…"
            placeholderTextColor={COLORS.textMuted} style={s.searchInput}
            returnKeyType="search" testID="travel-search" />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow} testID="travel-types">
          {TYPES.map((tp) => {
            const on = type === tp.key;
            return (
              <TouchableOpacity key={tp.key} onPress={() => setType(tp.key)}
                style={[s.chip, on && s.chipOn]} testID={`travel-type-${tp.key}`}>
                <Ionicons name={tp.icon} size={14} color={on ? '#fff' : COLORS.textDim} />
                <Text style={[s.chipText, on && s.chipTextOn]}>{tp.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow} testID="travel-sorts">
          {SORTS.map((so) => {
            const on = sort === so.key;
            return (
              <TouchableOpacity key={so.key} onPress={() => setSort(so.key)}
                style={[s.chip, on && s.chipOn]} testID={`travel-sort-${so.key}`}>
                <Text style={[s.chipText, on && s.chipTextOn]}>{so.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {loading ? (
          <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
        ) : items.length === 0 ? (
          <View style={common.center}><Text style={s.empty}>No deals found.</Text></View>
        ) : (
          <View style={s.grid} testID="travel-grid">
            {items.map((d) => (
              <TouchableOpacity key={d.deal_id} style={s.card} activeOpacity={0.85}
                testID={`travel-deal-${d.deal_id}`}
                onPress={() => router.push(`/shop/travel/${d.deal_id}` as any)}>
                <View style={s.cardImgWrap}>
                  <Image source={{ uri: d.image_url }} style={s.cardImg} contentFit="cover" transition={150} />
                  {d.promoted && <View style={s.dealTag}><Text style={s.dealTagTxt}>DEAL</Text></View>}
                  <View style={s.ptsTag}><Text style={s.ptsTxt}>₿ +{d.bigpoints}</Text></View>
                </View>
                <View style={{ padding: 10 }}>
                  <Text style={s.cardTitle} numberOfLines={1}>{d.title}</Text>
                  <Text style={s.cardDest} numberOfLines={1}>{d.destination}</Text>
                  <View style={s.cardMeta}>
                    <Text style={s.price}>{money(d.price_cents)}</Text>
                    {d.strike_cents ? <Text style={s.strike}>{money(d.strike_cents)}</Text> : null}
                    {d.rating ? (
                      <View style={s.ratingBox}>
                        <Ionicons name="star" size={11} color={COLORS.gold} />
                        <Text style={s.ratingTxt}>{d.rating.toFixed(1)}</Text>
                      </View>
                    ) : null}
                  </View>
                </View>
              </TouchableOpacity>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  follow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, margin: SPACING.md, marginBottom: 6, borderRadius: RADIUS.lg, padding: 14 },
  followOn: { backgroundColor: COLORS.primary + '18', borderWidth: 1, borderColor: COLORS.primary + '55' },
  followTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  followSub: { color: 'rgba(255,255,255,0.85)', fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  followPill: { backgroundColor: 'rgba(255,255,255,0.2)', borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 6 },
  followPillOn: { backgroundColor: COLORS.card },
  followPillTxt: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 10, marginHorizontal: SPACING.md, marginTop: 6 },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.sm, padding: 0 },
  chipRow: { paddingHorizontal: SPACING.md, gap: 8, paddingVertical: SPACING.sm },
  chip: { flexShrink: 0, flexDirection: 'row', alignItems: 'center', gap: 6, height: 36, paddingHorizontal: 14, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  chipTextOn: { color: '#fff' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', paddingHorizontal: SPACING.md, gap: 12 },
  card: { width: '48%', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, overflow: 'hidden', marginBottom: 2 },
  cardImgWrap: { height: 110, backgroundColor: COLORS.inputBg },
  cardImg: { width: '100%', height: '100%' },
  dealTag: { position: 'absolute', top: 8, left: 8, backgroundColor: COLORS.red, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  dealTagTxt: { color: '#fff', fontSize: 9, fontWeight: '900' },
  ptsTag: { position: 'absolute', bottom: 8, right: 8, backgroundColor: COLORS.gold, borderRadius: RADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  ptsTxt: { color: '#3a2a00', fontSize: 10, fontWeight: '900' },
  cardTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cardDest: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  cardMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 },
  price: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  strike: { color: COLORS.textMuted, fontSize: FONT.xs, textDecorationLine: 'line-through' },
  ratingBox: { flexDirection: 'row', alignItems: 'center', gap: 2, marginLeft: 'auto' },
  ratingTxt: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginTop: 40 },
  liveBtn: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#111827', marginHorizontal: SPACING.md, marginTop: 6, marginBottom: 2, borderRadius: RADIUS.lg, padding: 14 },
  liveBtnTitle: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  liveBtnSub: { color: 'rgba(255,255,255,0.7)', fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  liveBadge: { backgroundColor: COLORS.red, borderRadius: RADIUS.full, paddingHorizontal: 9, paddingVertical: 3 },
  liveBadgeTxt: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
});
