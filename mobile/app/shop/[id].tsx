// Business detail — RadioLife Shop.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

export default function BusinessDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [biz, setBiz] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { const r = await api.get(`/shop/businesses/${id}`); setBiz(r.data.business); }
      catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!biz) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Business not found.</Text></View>;

  const sells: string[] = biz.sells || [];
  const primaryCta = sells.includes('menu') ? 'Order Pickup'
    : (sells.includes('appointments') || sells.includes('services')) ? 'Book Now'
    : sells.includes('products') ? 'Shop Products' : 'View';

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: 60 }} testID="shop-detail-root">
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

          <View style={s.earnBadge}>
            <Text style={s.earnGlyph}>₿</Text>
            <Text style={s.earnText}>Earn {biz.default_bigpoints} BigPoints here</Text>
          </View>

          <Text style={s.blockTitle}>Ways to earn here</Text>
          {(biz.ways_to_earn || []).map((w: any, i: number) => (
            <View key={i} style={s.earnRow} testID={`shop-earn-${i}`}>
              <View style={s.earnIcon}><Ionicons name={(w.icon || 'star') as any} size={16} color={COLORS.primary} /></View>
              <Text style={s.earnLabel}>{w.label}</Text>
              <Text style={s.earnPts}>+{w.points}</Text>
            </View>
          ))}

          {(biz.phone || biz.website) && (
            <>
              <Text style={s.blockTitle}>Contact</Text>
              {!!biz.phone && (
                <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(`tel:${biz.phone}`)}>
                  <Ionicons name="call" size={16} color={COLORS.primary} />
                  <Text style={s.contactText}>{biz.phone}</Text>
                </TouchableOpacity>
              )}
              {!!biz.website && (
                <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(biz.website)}>
                  <Ionicons name="globe" size={16} color={COLORS.primary} />
                  <Text style={s.contactText}>{biz.website}</Text>
                </TouchableOpacity>
              )}
            </>
          )}
        </View>
      </ScrollView>

      <View style={s.footer}>
        <TouchableOpacity style={common.btnPrimary} testID="shop-detail-cta"
          onPress={() => {
            if (sells.includes('services')) router.push(`/shop/services/${biz.business_id}`);
            else if (sells.includes('menu') || biz.has_menu) router.push(`/shop/menu/${biz.business_id}`);
            else if (sells.includes('products')) router.push(`/shop/products/${biz.business_id}`);
            else router.push('/bookings');
          }}>
          <Ionicons name="flash" size={16} color="#fff" />
          <Text style={common.btnPrimaryText}>{primaryCta} · Earn {biz.default_bigpoints}</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  cover: { width: '100%', height: 220, backgroundColor: COLORS.inputBg },
  backBtn: { position: 'absolute', top: 12, left: 12, width: 38, height: 38, borderRadius: 19, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { color: COLORS.text, fontSize: 24, fontWeight: '900', flex: 1 },
  ratingPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  ratingText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cat: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '700', marginTop: 3, textTransform: 'capitalize' },
  desc: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20, marginTop: 12 },
  earnBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: COLORS.gold + '1f', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, marginTop: 14 },
  earnGlyph: { color: COLORS.gold, fontSize: 15, fontWeight: '900' },
  earnText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  blockTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 20, marginBottom: 8 },
  earnRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  earnIcon: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center' },
  earnLabel: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  earnPts: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '900' },
  contactRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 },
  contactText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '700' },
  footer: { padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
});
