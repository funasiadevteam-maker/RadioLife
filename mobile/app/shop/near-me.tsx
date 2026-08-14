// Near Me — shops & services around the user's location (map + list).
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as Location from 'expo-location';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { formatDistance } from '../../src/utils/distance';
import NativeMap, { MAPS_AVAILABLE } from '../../src/components/NativeMap';

const DUBAI = { lat: 25.2048, lng: 55.2708 };

type Biz = {
  business_id: string; public_name: string; category: string; subcategory?: string;
  cover_url?: string; default_bigpoints: number; distance_km?: number | null;
  delivery_enabled?: boolean; geo?: { lat: number; lng: number } | null;
};

export default function NearMe() {
  const router = useRouter();
  const [perm, setPerm] = useState<'unknown' | 'prompt' | 'granted' | 'denied' | 'blocked'>('unknown');
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [usingDefault, setUsingDefault] = useState(false);
  const [items, setItems] = useState<Biz[]>([]);
  const [loading, setLoading] = useState(false);
  const [cat, setCat] = useState<string>('all');

  const getPosition = useCallback(async () => {
    try {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      setUsingDefault(false);
    } catch {
      setCoords(DUBAI); setUsingDefault(true);
    }
  }, []);

  // On mount, only check (never request) the existing permission state.
  useEffect(() => {
    (async () => {
      const p = await Location.getForegroundPermissionsAsync();
      if (p.granted) { setPerm('granted'); getPosition(); }
      else if (!p.canAskAgain) setPerm('blocked');
      else setPerm('prompt');
    })();
  }, [getPosition]);

  // Contextual request — only after the user taps "Use my location".
  const requestLocation = useCallback(async () => {
    const p = await Location.requestForegroundPermissionsAsync();
    if (p.granted) { setPerm('granted'); getPosition(); }
    else if (!p.canAskAgain) setPerm('blocked');
    else setPerm('denied');
  }, [getPosition]);

  const browseDefault = () => { setCoords(DUBAI); setUsingDefault(true); };

  const load = useCallback(async () => {
    if (!coords) return;
    setLoading(true);
    try {
      const r = await api.get('/shop/businesses', {
        params: { sort: 'nearby', lat: coords.lat, lng: coords.lng, limit: 40 },
      });
      setItems(r.data.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [coords]);
  useEffect(() => { load(); }, [load]);

  const cats = useMemo(() => {
    const set = new Map<string, string>();
    items.forEach((b) => { if (b.category) set.set(b.category, b.subcategory || b.category); });
    return ['all', ...Array.from(set.keys())];
  }, [items]);

  const filtered = useMemo(
    () => (cat === 'all' ? items : items.filter((b) => b.category === cat)),
    [items, cat],
  );

  const region = coords ? {
    latitude: coords.lat, longitude: coords.lng,
    latitudeDelta: 0.12, longitudeDelta: 0.12,
  } : undefined;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="near-me-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Near You</Text>
        <View style={{ width: 22 }} />
      </View>

      {/* Permission / intent gate */}
      {!coords ? (
        <View style={common.center} testID="near-me-gate">
          <View style={s.gateIcon}><Ionicons name="navigate" size={34} color={COLORS.primary} /></View>
          <Text style={s.gateTitle}>Discover what&apos;s around you</Text>
          <Text style={s.gateSub}>Share your location to see shops, restaurants and services nearby — sorted by distance.</Text>
          {perm === 'blocked' ? (
            <>
              <TouchableOpacity style={s.gateBtn} onPress={() => Linking.openSettings()} testID="near-me-open-settings">
                <Ionicons name="settings-outline" size={16} color="#fff" />
                <Text style={s.gateBtnText}>Open Settings</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={browseDefault} testID="near-me-browse-default" style={{ marginTop: 14 }}>
                <Text style={s.gateLink}>Browse Dubai instead</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <TouchableOpacity style={s.gateBtn} onPress={requestLocation} testID="near-me-use-location">
                <Ionicons name="location" size={16} color="#fff" />
                <Text style={s.gateBtnText}>Use my location</Text>
              </TouchableOpacity>
              {perm === 'denied' && <Text style={s.gateDenied}>Location was denied. You can still browse Dubai.</Text>}
              <TouchableOpacity onPress={browseDefault} testID="near-me-browse-default" style={{ marginTop: 14 }}>
                <Text style={s.gateLink}>Browse Dubai instead</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      ) : (
        <>
          {/* Map (native builds only) */}
          {MAPS_AVAILABLE && region ? (
            <View style={s.mapWrap} testID="near-me-map">
              <NativeMap region={region} showsUserLocation
                markers={filtered.filter((b) => b.geo).map((b) => ({
                  id: b.business_id, lat: b.geo!.lat, lng: b.geo!.lng,
                  title: b.public_name, description: b.subcategory || b.category,
                  onPress: () => router.push(`/shop/${b.business_id}` as any),
                }))} />
            </View>
          ) : (
            <View style={s.mapFallback} testID="near-me-map-fallback">
              <Ionicons name="map-outline" size={20} color={COLORS.textMuted} />
              <Text style={s.mapFallbackText}>Live map available in the mobile app build.</Text>
            </View>
          )}

          {usingDefault && (
            <Text style={s.defaultNote} testID="near-me-default-note">📍 Showing Dubai — turn on location for results around you.</Text>
          )}

          {/* Category chips — single horizontal scroller */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false}
            contentContainerStyle={s.chipRow} testID="near-me-cats">
            {cats.map((c) => (
              <TouchableOpacity key={c} onPress={() => setCat(c)}
                style={[s.chip, cat === c && s.chipOn]} testID={`near-me-cat-${c}`}>
                <Text style={[s.chipText, cat === c && s.chipTextOn]}>{c === 'all' ? 'All' : c}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {loading ? (
            <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
          ) : (
            <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 90 }} testID="near-me-list">
              {filtered.length === 0 ? (
                <View style={common.center}><Text style={s.empty}>No places found nearby.</Text></View>
              ) : filtered.map((b) => (
                <TouchableOpacity key={b.business_id} style={s.row} testID={`near-me-biz-${b.business_id}`}
                  onPress={() => router.push(`/shop/${b.business_id}` as any)} activeOpacity={0.85}>
                  <Image source={{ uri: b.cover_url }} style={s.thumb} contentFit="cover" transition={150} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.name} numberOfLines={1}>{b.public_name}</Text>
                    <Text style={s.cat} numberOfLines={1}>{b.subcategory || b.category}</Text>
                    <View style={s.metaRow}>
                      <View style={s.ptsTag}>
                        <Text style={s.ptsGlyph}>₿</Text>
                        <Text style={s.ptsText}>Earn {b.default_bigpoints}</Text>
                      </View>
                      {b.delivery_enabled && (
                        <View style={s.delTag}><Ionicons name="bicycle" size={11} color={COLORS.green} /><Text style={s.delText}>Delivery</Text></View>
                      )}
                    </View>
                  </View>
                  {b.distance_km != null && (
                    <View style={s.distBox} testID={`near-me-dist-${b.business_id}`}>
                      <Ionicons name="navigate" size={12} color={COLORS.primary} />
                      <Text style={s.distText}>{formatDistance(b.distance_km)}</Text>
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  gateIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  gateTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginBottom: 8 },
  gateSub: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', textAlign: 'center', paddingHorizontal: 32, lineHeight: 20, marginBottom: 22 },
  gateBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 24, paddingVertical: 13 },
  gateBtnText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  gateDenied: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '700', marginTop: 12, textAlign: 'center', paddingHorizontal: 24 },
  gateLink: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  mapWrap: { height: 220, backgroundColor: COLORS.inputBg },
  mapFallback: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.inputBg, paddingVertical: 14, marginHorizontal: SPACING.md, marginTop: SPACING.sm, borderRadius: RADIUS.md },
  mapFallbackText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  defaultNote: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', paddingHorizontal: SPACING.md, paddingTop: 10 },
  chipRow: { paddingHorizontal: SPACING.md, gap: 8, paddingVertical: SPACING.sm },
  chip: { flexShrink: 0, height: 36, justifyContent: 'center', paddingHorizontal: 14, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  chipTextOn: { color: '#fff' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 10, marginBottom: 8 },
  thumb: { width: 60, height: 60, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cat: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  ptsTag: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.gold, paddingHorizontal: 7, paddingVertical: 2, borderRadius: RADIUS.full },
  ptsGlyph: { color: '#3a2a00', fontSize: 10, fontWeight: '900' },
  ptsText: { color: '#3a2a00', fontSize: 10, fontWeight: '900' },
  delTag: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.green + '18', paddingHorizontal: 7, paddingVertical: 2, borderRadius: RADIUS.full },
  delText: { color: COLORS.green, fontSize: 10, fontWeight: '900' },
  distBox: { alignItems: 'center', gap: 2 },
  distText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginTop: 40 },
});
