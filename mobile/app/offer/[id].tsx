import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import api from '../../src/api/client';
import { useAuth } from '../../src/contexts/AuthContext';

export default function OfferDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const [offer, setOffer] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace('/login');
  }, [user, authLoading]);

  useEffect(() => {
    if (!id || authLoading || !user) return;
    (async () => {
      try {
        const r = await api.get('/commerce/offers/feed');
        const items = r.data.items || [];
        const found = items.find((o: any) => o.offer_id === id);
        setOffer(found || null);
      } catch {
        Alert.alert('Error', 'Could not load offer');
      } finally {
        setLoading(false);
      }
    })();
  }, [id, authLoading, user]);

  const claimOffer = async () => {
    if (!offer) return;
    setClaiming(true);
    try {
      await api.post(`/commerce/offers/${offer.offer_id}/claim`, {});
      Alert.alert('Claimed!', 'Coupon saved to your wallet.', [
        { text: 'View Wallet', onPress: () => router.push('/(tabs)/wallet') },
        { text: 'OK' },
      ]);
    } catch (e: any) {
      const msg = e?.response?.data?.detail;
      Alert.alert('Error', typeof msg === 'string' ? msg : 'Could not claim offer');
    } finally {
      setClaiming(false);
    }
  };

  if (authLoading || loading) {
    return (
      <View style={st.center}>
        <ActivityIndicator size="large" color={COLORS.primary} />
      </View>
    );
  }

  if (!offer) {
    return (
      <SafeAreaView style={st.screen}>
        <View style={st.center}>
          <Ionicons name="alert-circle" size={36} color={COLORS.textDim} />
          <Text style={st.emptyText}>Offer not found or no longer available.</Text>
          <TouchableOpacity style={st.backLinkBtn} onPress={() => router.back()} testID="offer-not-found-back">
            <Text style={st.backLinkText}>Go back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const soldOut = offer.inventory_remaining != null && offer.inventory_remaining <= 0;
  const hasExpiry = !!offer.end_at;
  const expired = hasExpiry && new Date(offer.end_at) < new Date();

  return (
    <SafeAreaView style={st.screen} testID="offer-detail-screen">
      <ScrollView contentContainerStyle={st.scroll}>
        {/* Header */}
        <TouchableOpacity onPress={() => router.back()} style={st.backBtn} testID="offer-back-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back to offers</Text>
        </TouchableOpacity>

        {/* Offer type badge */}
        <View style={st.typeBadge}>
          <Ionicons name="pricetag" size={11} color={COLORS.gold} />
          <Text style={st.typeText}>{(offer.offer_type || '').replace(/_/g, ' ').toUpperCase()}</Text>
        </View>

        {/* Title */}
        <Text style={st.title} testID="offer-title">{offer.title}</Text>
        {offer.description ? <Text style={st.desc}>{offer.description}</Text> : null}

        {/* Value card */}
        <View style={st.valueCard} testID="offer-value-card">
          <View style={st.valueRow}>
            <Ionicons name="gift" size={18} color={COLORS.green} />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={st.valueLabel}>DISCOUNT</Text>
              <Text style={st.valueAmount}>
                {offer.value_amount != null
                  ? `${offer.value_amount}${offer.offer_type === 'percent_off' ? '%' : ` ${offer.value_currency || 'AED'}`} off`
                  : 'Special offer'}
              </Text>
            </View>
          </View>
          {offer.min_order_amount != null && (
            <Text style={st.minOrder}>Min. order: {offer.min_order_amount} {offer.value_currency || 'AED'}</Text>
          )}
        </View>

        {/* Meta chips */}
        <View style={st.metaRow} testID="offer-meta">
          {hasExpiry && (
            <View style={[st.chip, expired && { borderColor: COLORS.red }]}>
              <Ionicons name="time" size={11} color={expired ? COLORS.red : COLORS.textDim} />
              <Text style={[st.chipText, expired && { color: COLORS.red }]}>
                {expired ? 'Expired' : `Until ${new Date(offer.end_at).toLocaleDateString()}`}
              </Text>
            </View>
          )}
          {offer.inventory_remaining != null && (
            <View style={[st.chip, soldOut && { borderColor: COLORS.red }]}>
              <Ionicons name="cube" size={11} color={soldOut ? COLORS.red : COLORS.textDim} />
              <Text style={[st.chipText, soldOut && { color: COLORS.red }]}>
                {soldOut ? 'Sold out' : `${offer.inventory_remaining} left`}
              </Text>
            </View>
          )}
          {offer.source && (
            <View style={st.chip}>
              <Ionicons name="storefront" size={11} color={COLORS.textDim} />
              <Text style={st.chipText}>{offer.source}</Text>
            </View>
          )}
          {offer.category && (
            <View style={st.chip}>
              <Ionicons name="grid" size={11} color={COLORS.textDim} />
              <Text style={st.chipText}>{offer.category}</Text>
            </View>
          )}
        </View>

        {/* Terms */}
        {offer.terms_text ? (
          <View style={st.termsCard} testID="offer-terms">
            <Text style={st.termsLabel}>TERMS & CONDITIONS</Text>
            <Text style={st.termsText}>{offer.terms_text}</Text>
          </View>
        ) : null}

        {/* Business info */}
        {offer.business_name && (
          <View style={st.bizRow} testID="offer-business">
            <Ionicons name="business" size={16} color={COLORS.primary} />
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={st.bizName}>{offer.business_name}</Text>
              {offer.business_category && <Text style={st.bizCat}>{offer.business_category}</Text>}
            </View>
          </View>
        )}

        {/* Claim CTA */}
        <TouchableOpacity
          style={[st.claimBtn, (soldOut || expired || claiming) && { opacity: 0.4 }]}
          onPress={claimOffer}
          disabled={soldOut || expired || claiming}
          testID="offer-claim-btn"
        >
          {claiming ? (
            <ActivityIndicator size={14} color="#fff" />
          ) : (
            <>
              <Ionicons name="gift" size={16} color="#fff" />
              <Text style={st.claimText}>
                {soldOut ? 'Sold Out' : expired ? 'Expired' : 'Claim Coupon'}
              </Text>
            </>
          )}
        </TouchableOpacity>

        <Text style={st.claimHint}>Claimed coupons appear in your Wallet → Saved Coupons</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg, padding: SPACING.xl },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.md },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  backLinkBtn: { marginTop: SPACING.md, paddingVertical: 10, paddingHorizontal: 20, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  backLinkText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  typeBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: 'rgba(253,183,86,0.12)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full, marginBottom: SPACING.sm },
  typeText: { color: COLORS.gold, fontSize: 10, fontWeight: '700', letterSpacing: 1 },
  title: { color: COLORS.text, fontSize: 26, fontWeight: '900', marginBottom: 6, letterSpacing: -0.5 },
  desc: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 22, marginBottom: SPACING.md },
  valueCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.green, marginBottom: SPACING.md },
  valueRow: { flexDirection: 'row', alignItems: 'center' },
  valueLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 1 },
  valueAmount: { color: COLORS.green, fontSize: 22, fontWeight: '900', marginTop: 2 },
  minOrder: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 8 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: SPACING.md },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.surface, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  chipText: { color: COLORS.textDim, fontSize: 11, fontWeight: '600' },
  termsCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  termsLabel: { color: COLORS.textDim, fontSize: 9, fontWeight: '700', letterSpacing: 2, marginBottom: 6 },
  termsText: { color: COLORS.textMuted, fontSize: FONT.sm, lineHeight: 20, fontStyle: 'italic' },
  bizRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg },
  bizName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  bizCat: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  claimBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 16, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  claimText: { color: '#fff', fontSize: 16, fontWeight: '800' },
  claimHint: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: SPACING.sm },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm, textAlign: 'center' },
});
