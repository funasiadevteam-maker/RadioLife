import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import api from '../../src/api/client';
import { useAuth } from '../../src/contexts/AuthContext';

let QRCode: any = null;
try { QRCode = require('react-native-qrcode-svg').default; } catch {}

export default function CouponDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const [coupon, setCoupon] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  useEffect(() => {
    if (!id || authLoading || !user) return;
    (async () => {
      try {
        const r = await api.get(`/commerce/coupons/${id}`);
        setCoupon(r.data);
      } catch {
        Alert.alert('Error', 'Could not load coupon');
        router.back();
      } finally { setLoading(false); }
    })();
  }, [id, authLoading, user]);

  const addToGoogle = async () => {
    try {
      const r = await api.post(`/commerce/coupons/${id}/wallet_pass/google`);
      if (r.data.save_url) Alert.alert('Google Wallet', r.data.pass_status === 'stub' ? (r.data.reason || 'Wallet pass stub') : 'Opening Google Wallet…');
    } catch { Alert.alert('Error', 'Could not mint Google Wallet pass'); }
  };
  const addToApple = async () => {
    try {
      const r = await api.post(`/commerce/coupons/${id}/wallet_pass/apple`);
      Alert.alert('Apple Wallet', r.data.reason || 'Apple Dev cert not configured yet');
    } catch { Alert.alert('Error', 'Apple Wallet stub failed'); }
  };

  if (authLoading || loading) return <View style={st.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!coupon) return <View style={st.center}><Text style={st.emptyText}>Coupon not found</Text></View>;

  const isActive = coupon.status === 'claimed';
  const isRedeemed = coupon.status === 'redeemed';
  const isExpired = coupon.status === 'expired' || (coupon.expires_at && new Date(coupon.expires_at) < new Date());
  const remainingMin = coupon.expires_at ? Math.max(0, Math.floor((new Date(coupon.expires_at).getTime() - Date.now()) / 60000)) : null;

  return (
    <SafeAreaView style={st.screen} testID="coupon-detail-screen">
      <ScrollView contentContainerStyle={st.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={st.backBtn} testID="coupon-back-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back to wallet</Text>
        </TouchableOpacity>

        <Text style={st.eyebrow}>SHOW TO REDEEM</Text>

        {/* QR Code */}
        <View style={st.qrWrap} testID="coupon-qr-code">
          {QRCode ? (
            <QRCode value={coupon.qr_token || coupon.coupon_id || 'N/A'} size={200}
              color="#0f172a" backgroundColor="#ffffff" />
          ) : (
            <View style={st.qrFallback}>
              <Ionicons name="qr-code" size={80} color={COLORS.textDim} />
              <Text style={st.qrFallbackText}>QR: {coupon.qr_token || coupon.coupon_id}</Text>
            </View>
          )}
        </View>

        {/* Redemption code */}
        <View style={st.codeBox} testID="coupon-redemption-code">
          <Text style={st.codeLabel}>REDEMPTION CODE</Text>
          <Text style={st.codeText}>{coupon.redemption_code || '—'}</Text>
        </View>

        {/* Status badge */}
        <View style={st.statusRow}>
          {isActive && <View style={[st.statusBadge, { backgroundColor: 'rgba(74,222,128,0.15)' }]}><Ionicons name="checkmark-circle" size={12} color={COLORS.green} /><Text style={[st.statusText, { color: COLORS.green }]}>Active{remainingMin != null ? ` · ${remainingMin}m left` : ''}</Text></View>}
          {isRedeemed && <View style={[st.statusBadge, { backgroundColor: 'rgba(167,139,250,0.15)' }]}><Ionicons name="checkmark-done" size={12} color={COLORS.purple} /><Text style={[st.statusText, { color: COLORS.purple }]}>Redeemed{coupon.redeemed_at ? ` · ${new Date(coupon.redeemed_at).toLocaleDateString()}` : ''}</Text></View>}
          {isExpired && <View style={[st.statusBadge, { backgroundColor: 'rgba(251,113,133,0.15)' }]}><Ionicons name="time" size={12} color={COLORS.red} /><Text style={[st.statusText, { color: COLORS.red }]}>Expired</Text></View>}
        </View>

        {/* Info */}
        <View style={st.infoCard}>
          <Text style={st.infoLabel}>Offer</Text>
          <Text style={st.infoValue}>{coupon.offer_title || coupon.offer_id}</Text>
          <Text style={st.infoLabel}>Claim Source</Text>
          <Text style={st.infoValue}>{(coupon.claim_source || '').replace(/_/g, ' ')}</Text>
          {coupon.expires_at && <>
            <Text style={st.infoLabel}>Expires</Text>
            <Text style={st.infoValue}>{new Date(coupon.expires_at).toLocaleString()}</Text>
          </>}
          {coupon.merchant_name && <>
            <Text style={st.infoLabel}>Merchant</Text>
            <Text style={st.infoValue}>{coupon.merchant_name}</Text>
          </>}
        </View>

        {/* T&Cs */}
        {coupon.terms_conditions && (
          <View style={st.infoCard}>
            <Text style={st.infoLabel}>TERMS &amp; CONDITIONS</Text>
            <Text style={st.termsText}>{coupon.terms_conditions}</Text>
          </View>
        )}

        {/* Merchant Address + Directions */}
        {coupon.merchant_address && (
          <TouchableOpacity style={st.directionsCard} testID="coupon-get-directions"
            onPress={() => {
              const q = encodeURIComponent(coupon.merchant_address);
              Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${q}`);
            }}>
            <Ionicons name="navigate" size={18} color={COLORS.secondary} />
            <View style={{ flex: 1 }}>
              <Text style={st.directionsLabel}>MERCHANT LOCATION</Text>
              <Text style={st.directionsAddr}>{coupon.merchant_address}</Text>
            </View>
            <Text style={st.directionsLink}>Directions</Text>
          </TouchableOpacity>
        )}

        {/* Redeem button */}
        {isActive && !isExpired && (
          <TouchableOpacity style={[common.btnPrimary, { width: '100%', marginTop: SPACING.sm }]}
            testID="coupon-redeem-btn"
            onPress={async () => {
              try {
                await api.post(`/commerce/coupons/${id}/redeem`);
                Alert.alert('Redeemed!', 'Coupon has been redeemed successfully.');
                setCoupon({ ...coupon, status: 'redeemed', redeemed_at: new Date().toISOString() });
              } catch (e: any) {
                Alert.alert('Error', e?.response?.data?.detail || 'Redeem failed');
              }
            }}>
            <Ionicons name="checkmark-circle" size={18} color="#fff" />
            <Text style={common.btnPrimaryText}>Redeem Now</Text>
          </TouchableOpacity>
        )}

        {/* Wallet pass buttons */}
        {isActive && (
          <View style={st.walletRow}>
            <TouchableOpacity style={st.walletBtn} onPress={addToGoogle} testID="coupon-google-wallet">
              <Ionicons name="logo-google" size={14} color={COLORS.textDim} />
              <Text style={st.walletBtnText}>Google Wallet</Text>
            </TouchableOpacity>
            <TouchableOpacity style={st.walletBtn} onPress={addToApple} testID="coupon-apple-wallet">
              <Ionicons name="logo-apple" size={14} color={COLORS.textDim} />
              <Text style={st.walletBtnText}>Apple Wallet</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.md, paddingBottom: 100, alignItems: 'center' },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', marginBottom: SPACING.md },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  eyebrow: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 2, marginBottom: SPACING.md },
  qrWrap: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.lg, alignItems: 'center', justifyContent: 'center', marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, minHeight: 240, minWidth: 240 },
  qrFallback: { alignItems: 'center', gap: SPACING.sm },
  qrFallbackText: { color: COLORS.textDim, fontSize: FONT.xs, fontFamily: 'monospace' },
  codeBox: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md, alignItems: 'center', borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  codeLabel: { color: COLORS.textDim, fontSize: 9, fontWeight: '700', letterSpacing: 2, marginBottom: 4 },
  codeText: { color: COLORS.text, fontSize: 20, fontWeight: '900', letterSpacing: 3 },
  statusRow: { marginBottom: SPACING.md },
  statusBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full },
  statusText: { fontSize: FONT.sm, fontWeight: '700' },
  infoCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, width: '100%', borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  infoLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, marginTop: 8 },
  infoValue: { color: COLORS.text, fontSize: FONT.md, fontWeight: '600', marginBottom: 4 },
  walletRow: { flexDirection: 'row', gap: 8, width: '100%' },
  walletBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  walletBtnText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm },
  termsText: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20, marginTop: 4 },
  directionsCard: { flexDirection: 'row', alignItems: 'center', gap: 12, width: '100%', backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.sm },
  directionsLabel: { color: COLORS.textDim, fontSize: 9, fontWeight: '700', letterSpacing: 1 },
  directionsAddr: { color: COLORS.text, fontSize: FONT.sm, marginTop: 2 },
  directionsLink: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700' },
});
