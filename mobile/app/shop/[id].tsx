// Business / restaurant detail — RadioLife Shop (mobile).
// Compact earn bar (Order · Check In · Pay), working check-in, horizontal
// category filter + product grid, and a floating Order/Membership stack.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;
const EARN_ICON: Record<string, any> = { 'bag-check': 'bag-check', location: 'location', wallet: 'wallet' };

export default function BusinessDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { celebrate } = useReward();
  const [biz, setBiz] = useState<any>(null);
  const [groups, setGroups] = useState<any[]>([]);
  const [cat, setCat] = useState('all');
  const [loading, setLoading] = useState(true);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await api.get(`/shop/businesses/${id}`);
        if (!alive) return;
        const b = r.data.business;
        setBiz(b);
        const sells: string[] = b.sells || [];
        if (sells.includes('menu') || b.has_menu) {
          const m = await api.get(`/shop/businesses/${id}/menu`);
          const secs = (m.data.sections || []).map((s: any, i: number) => ({
            key: `sec-${i}`, title: s.title,
            items: (s.items || []).map((it: any) => ({
              id: it.item_id, name: it.name, price_cents: it.price_cents,
              image_url: it.image_url, kind: 'menu', hasVariants: (it.option_groups || []).length > 0,
            })),
          }));
          if (alive) setGroups(secs);
        } else if (b.has_products || sells.includes('products')) {
          const pr = await api.get(`/shop/businesses/${id}/products`);
          const byCat: Record<string, any[]> = {};
          (pr.data.products || []).forEach((p: any) => {
            const c = p.category || 'All';
            (byCat[c] = byCat[c] || []).push({
              id: p.product_id, name: p.name, price_cents: p.price_cents,
              image_url: p.image_url, kind: 'product', hasVariants: (p.variants || []).length > 0,
            });
          });
          if (alive) setGroups(Object.keys(byCat).map((c, i) => ({ key: `cat-${i}`, title: c, items: byCat[c] })));
        }
      } catch { if (alive) setBiz(null); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [id]);

  const allItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const shown = useMemo(
    () => (cat === 'all' ? allItems : (groups.find((g) => g.key === cat)?.items || [])),
    [cat, groups, allItems]);

  const orderPath = useCallback(() => {
    const sells: string[] = biz.sells || [];
    if (sells.includes('services') || sells.includes('appointments')) return `/shop/services/${biz.business_id}`;
    if (sells.includes('menu') || biz.has_menu) return `/shop/menu/${biz.business_id}`;
    if (sells.includes('products') || biz.has_products) return `/shop/products/${biz.business_id}`;
    return '/bookings';
  }, [biz]);

  const openItem = (it: any) => {
    if (it.kind === 'product') router.push(`/shop/products/${biz.business_id}` as any);
    else router.push(`/shop/menu/${biz.business_id}` as any);
  };

  const doCheckin = async () => {
    if (checkedIn || checking) return;
    setChecking(true);
    try {
      const r = await api.post(`/shop/businesses/${id}/checkin`);
      setCheckedIn(true);
      if (!r.data.already) celebrate({ points: r.data.awarded, title: 'Checked in! 🎉' });
    } catch { /* ignore */ }
    finally { setChecking(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!biz) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Business not found.</Text></View>;

  const ways: any[] = biz.ways_to_earn || [];

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: 140 }} testID="shop-detail-root">
        <View>
          <Image source={{ uri: biz.cover_url }} style={s.cover} contentFit="cover" transition={200} />
          <TouchableOpacity style={s.backBtn} onPress={() => router.back()} testID="shop-detail-back">
            <Ionicons name="chevron-back" size={22} color="#fff" />
          </TouchableOpacity>
        </View>

        <View style={{ padding: SPACING.md }}>
          <View style={s.titleRow}>
            <Text style={s.name}>{biz.public_name}</Text>
            {biz.rating ? (
              <View style={s.ratingPill}>
                <Ionicons name="star" size={12} color={COLORS.gold} />
                <Text style={s.ratingText}>{biz.rating.toFixed(1)}</Text>
              </View>
            ) : null}
          </View>
          <Text style={s.cat}>{biz.subcategory || biz.category}{biz.city ? ` · ${biz.city}` : ''}</Text>
          {!!biz.description && <Text style={s.desc}>{biz.description}</Text>}

          {/* Ways to earn — single bar, all in one line */}
          {ways.length > 0 && (
            <View style={s.earnBar} testID="shop-earn-bar">
              {ways.map((w, i) => {
                const isCheckin = (w.label || '').toLowerCase().includes('check');
                const cell = (
                  <>
                    <Ionicons name={(EARN_ICON[w.icon] || 'star') as any} size={16}
                      color={isCheckin && checkedIn ? COLORS.green : COLORS.primary} />
                    <Text style={s.earnLabel} numberOfLines={1}>{w.label}</Text>
                    <Text style={[s.earnPts, isCheckin && checkedIn && { color: COLORS.green }]}>
                      {isCheckin && checkedIn ? '✓ Done' : `+${w.points}`}
                    </Text>
                  </>
                );
                return isCheckin ? (
                  <TouchableOpacity key={i} style={[s.earnCell, i > 0 && s.earnDivider, { backgroundColor: checkedIn ? COLORS.green + '14' : COLORS.primary + '0d' }]}
                    onPress={doCheckin} disabled={checking} testID="shop-checkin-btn">{cell}</TouchableOpacity>
                ) : (
                  <View key={i} style={[s.earnCell, i > 0 && s.earnDivider]} testID={`shop-earn-${i}`}>{cell}</View>
                );
              })}
            </View>
          )}
        </View>

        {/* Category filter — single horizontal scroller */}
        {groups.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false}
            contentContainerStyle={s.catRow} testID="shop-cat-rail">
            <TouchableOpacity onPress={() => setCat('all')} style={[s.chip, cat === 'all' && s.chipOn]} testID="shop-cat-all">
              <Text style={[s.chipText, cat === 'all' && s.chipTextOn]}>All</Text>
            </TouchableOpacity>
            {groups.map((g) => (
              <TouchableOpacity key={g.key} onPress={() => setCat(g.key)} style={[s.chip, cat === g.key && s.chipOn]} testID={`shop-cat-${g.key}`}>
                <Text style={[s.chipText, cat === g.key && s.chipTextOn]}>{g.title}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {/* Product / menu grid — 2 columns, multiple rows */}
        {groups.length > 0 ? (
          <View style={s.grid} testID="shop-item-grid">
            {shown.map((it: any) => (
              <TouchableOpacity key={it.id} style={s.card} onPress={() => openItem(it)} testID={`shop-item-${it.id}`} activeOpacity={0.85}>
                <View style={s.cardImgWrap}>
                  <Image source={{ uri: it.image_url }} style={s.cardImg} contentFit="cover" transition={150} />
                  <View style={s.addFab}><Ionicons name="add" size={16} color="#fff" /></View>
                </View>
                <Text style={s.itemName} numberOfLines={1}>{it.name}</Text>
                <Text style={s.itemPrice}>{money(it.price_cents)}{it.hasVariants ? '+' : ''}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : (
          <View style={{ paddingHorizontal: SPACING.md }}>
            <View style={s.earnBadge}>
              <Text style={s.earnGlyph}>₿</Text>
              <Text style={s.earnBadgeText}>Earn {biz.default_bigpoints} BigPoints here</Text>
            </View>
          </View>
        )}

        {/* Contact — inline */}
        {(biz.phone || biz.website) && (
          <View style={{ paddingHorizontal: SPACING.md, marginTop: 14 }}>
            {!!biz.phone && (
              <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(`tel:${biz.phone}`)}>
                <Ionicons name="call" size={16} color={COLORS.primary} />
                <Text style={s.contactText}>{biz.phone}</Text>
              </TouchableOpacity>
            )}
            {!!biz.website && (
              <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(biz.website)}>
                <Ionicons name="globe" size={16} color={COLORS.primary} />
                <Text style={s.contactText} numberOfLines={1}>{biz.website}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>

      {/* Floating action stack — bottom right */}
      <View style={s.actions} testID="shop-detail-actions">
        {biz.has_memberships && (
          <TouchableOpacity style={s.memPill} onPress={() => router.push(`/shop/memberships/${biz.business_id}` as any)} testID="shop-detail-membership">
            <Ionicons name="ribbon" size={15} color={COLORS.gold} />
            <Text style={s.memPillText}>Membership</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={s.orderPill} onPress={() => router.push(orderPath() as any)} testID="shop-detail-cta">
          <Ionicons name="bag-handle" size={16} color="#fff" />
          <Text style={s.orderPillText}>Order · Earn {biz.default_bigpoints}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  cover: { width: '100%', height: 200, backgroundColor: COLORS.inputBg },
  backBtn: { position: 'absolute', top: 12, left: 12, width: 38, height: 38, borderRadius: 19, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { color: COLORS.text, fontSize: 24, fontWeight: '900', flex: 1 },
  ratingPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  ratingText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cat: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '700', marginTop: 3, textTransform: 'capitalize' },
  desc: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20, marginTop: 12 },
  earnBar: { flexDirection: 'row', marginTop: 14, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, overflow: 'hidden' },
  earnCell: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 12, paddingHorizontal: 4 },
  earnDivider: { borderLeftWidth: 1, borderLeftColor: COLORS.cardBorder },
  earnLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', marginTop: 5, textAlign: 'center' },
  earnPts: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginTop: 2 },
  catRow: { paddingHorizontal: SPACING.md, gap: 8, paddingBottom: 6 },
  chip: { flexShrink: 0, height: 36, justifyContent: 'center', paddingHorizontal: 16, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  chipTextOn: { color: '#fff' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', paddingHorizontal: SPACING.md, marginTop: 10, gap: 12 },
  card: { width: '47%', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, overflow: 'hidden', marginBottom: 4 },
  cardImgWrap: { position: 'relative', width: '100%', aspectRatio: 1, backgroundColor: COLORS.inputBg },
  cardImg: { width: '100%', height: '100%' },
  addFab: { position: 'absolute', bottom: 8, right: 8, width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', paddingHorizontal: 10, paddingTop: 8 },
  itemPrice: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', paddingHorizontal: 10, paddingTop: 2, paddingBottom: 10 },
  earnBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: COLORS.gold + '1f', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, marginTop: 6 },
  earnGlyph: { color: COLORS.gold, fontSize: 15, fontWeight: '900' },
  earnBadgeText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  contactRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 },
  contactText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '700', flex: 1 },
  actions: { position: 'absolute', right: 14, bottom: 22, alignItems: 'flex-end', gap: 10 },
  memPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.card, borderWidth: 2, borderColor: COLORS.gold, borderRadius: RADIUS.full, paddingHorizontal: 16, paddingVertical: 10 },
  memPillText: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  orderPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 18, paddingVertical: 13, shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  orderPillText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
