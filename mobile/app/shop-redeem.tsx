import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';

export default function ShopRedeemScreen() {
  const router = useRouter();
  const [code, setCode] = useState('');
  const [pin, setPin] = useState('');
  const [info, setInfo] = useState<any>(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(false);
  const [redeeming, setRedeeming] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const reset = () => { setCode(''); setPin(''); setInfo(null); setNotFound(false); setMsg(null); };

  const lookup = async () => {
    if (!code.trim()) return;
    setLoading(true); setInfo(null); setNotFound(false); setMsg(null);
    try {
      const { data } = await api.get('/games/coupon/lookup', { params: { code: code.trim() } });
      if (!data.found) setNotFound(true);
      else setInfo(data);
    } catch { setMsg('Lookup failed'); }
    finally { setLoading(false); }
  };

  const redeem = async () => {
    setRedeeming(true); setMsg(null);
    try {
      const { data } = await api.post('/games/coupon/redeem', { code: code.trim(), pin: pin.trim() || undefined });
      setInfo((p: any) => ({ ...(p || {}), status: 'redeemed' }));
      setMsg(data.idempotent ? 'Already redeemed earlier' : 'Redeemed \u2713');
    } catch (e: any) {
      const c = e?.response?.data?.detail?.code || e?.response?.data?.code;
      setMsg(c === 'expired' ? 'Coupon expired'
        : c === 'already_redeemed' ? 'Already redeemed'
        : c === 'bad_pin' ? 'Wrong staff PIN'
        : c === 'code_not_found' ? 'Code not found' : 'Redemption failed');
    } finally { setRedeeming(false); }
  };

  const done = info?.status === 'redeemed';
  const isGift = info && String(info.prize_title || '').toLowerCase().includes('gift');

  return (
    <SafeAreaView style={s.safe} edges={['top', 'bottom']}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="shop-redeem-back" style={s.backBtn}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.title}>Redeem a code</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, gap: SPACING.md }}>
        <Text style={s.subtitle}>Enter the code your customer won in a game.</Text>

        <View style={s.card}>
          <Text style={s.label}>COUPON CODE</Text>
          <View style={s.inputRow}>
            <TextInput
              value={code}
              onChangeText={(v) => setCode(v.toUpperCase())}
              placeholder="BIGFM-XXXXXX"
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="characters"
              style={s.input}
              testID="shop-redeem-code"
            />
            <TouchableOpacity style={s.checkBtn} onPress={lookup} disabled={loading || !code.trim()} testID="shop-redeem-lookup">
              {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.checkTxt}>Check</Text>}
            </TouchableOpacity>
          </View>

          {notFound && (
            <View style={s.errBox} testID="shop-redeem-notfound">
              <Ionicons name="close-circle" size={16} color="#f87171" />
              <Text style={s.errTxt}>Code not found — check and try again.</Text>
            </View>
          )}

          {info && (
            <View style={[s.detail, done && { borderColor: COLORS.cardBorder }]} testID="shop-redeem-detail">
              <View style={s.detailRow}>
                <View style={[s.prizeIcon, { backgroundColor: isGift ? '#facc1522' : '#10b98122' }]}>
                  <Ionicons name={isGift ? 'gift' : 'pricetag'} size={20} color={isGift ? '#facc15' : '#10b981'} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.prizeTitle} testID="shop-redeem-prize">{info.prize_title}</Text>
                  <Text style={s.bizName}>{info.business_name || 'Fun Pizza Kitchen'}</Text>
                  <View style={[s.statusPill, done ? s.statusDone : s.statusOk]}>
                    <Text style={[s.statusTxt, done ? { color: COLORS.textMuted } : { color: '#6ee7b7' }]} testID="shop-redeem-status">
                      {done ? 'Redeemed' : 'Valid \u00b7 ready to redeem'}
                    </Text>
                  </View>
                </View>
              </View>

              {!done ? (
                <>
                  {info.pin_required && (
                    <View style={{ gap: 4 }} testID="shop-redeem-pin-wrap">
                      <Text style={s.label}>STAFF PIN</Text>
                      <TextInput
                        value={pin}
                        onChangeText={setPin}
                        placeholder="••••"
                        placeholderTextColor={COLORS.textMuted}
                        keyboardType="number-pad"
                        secureTextEntry
                        maxLength={8}
                        style={[s.input, { textAlign: 'center', letterSpacing: 6 }]}
                        testID="shop-redeem-pin"
                      />
                    </View>
                  )}
                  <TouchableOpacity style={s.redeemBtn} onPress={redeem} disabled={redeeming} testID="shop-redeem-confirm">
                    {redeeming ? <ActivityIndicator color="#0a0a0c" size="small" /> : <Text style={s.redeemTxt}>Mark as redeemed</Text>}
                  </TouchableOpacity>
                </>
              ) : (
                <View style={s.successRow} testID="shop-redeem-success">
                  <Ionicons name="checkmark-circle" size={18} color={COLORS.gold} />
                  <Text style={s.successTxt}>Done — enjoy the pizza!</Text>
                </View>
              )}
            </View>
          )}

          {msg && <Text style={s.msg}>{msg}</Text>}

          {(info || notFound) && (
            <TouchableOpacity style={s.resetBtn} onPress={reset} testID="shop-redeem-reset">
              <Ionicons name="refresh" size={13} color={COLORS.text} />
              <Text style={s.resetTxt}>Next code</Text>
            </TouchableOpacity>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  subtitle: { color: COLORS.textMuted, fontSize: FONT.sm },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, gap: SPACING.sm },
  label: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1 },
  inputRow: { flexDirection: 'row', gap: 8 },
  input: { flex: 1, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 12, color: COLORS.text, fontSize: FONT.md, letterSpacing: 1 },
  checkBtn: { paddingHorizontal: 18, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  checkTxt: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  errBox: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(248,113,113,0.1)', borderRadius: RADIUS.md, padding: 12 },
  errTxt: { color: '#fca5a5', fontSize: FONT.sm, flex: 1 },
  detail: { borderWidth: 1, borderColor: 'rgba(16,185,129,0.3)', borderRadius: RADIUS.md, padding: SPACING.sm, gap: SPACING.sm },
  detailRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  prizeIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  prizeTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  bizName: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 2 },
  statusPill: { alignSelf: 'flex-start', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2, marginTop: 6 },
  statusOk: { backgroundColor: 'rgba(16,185,129,0.15)' },
  statusDone: { backgroundColor: 'rgba(148,163,184,0.15)' },
  statusTxt: { fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  redeemBtn: { height: 46, borderRadius: RADIUS.full, backgroundColor: COLORS.gold, alignItems: 'center', justifyContent: 'center' },
  redeemTxt: { color: '#0a0a0c', fontWeight: '900', fontSize: FONT.md },
  successRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  successTxt: { color: COLORS.gold, fontWeight: '800', fontSize: FONT.sm },
  msg: { color: COLORS.textMuted, fontSize: FONT.sm, textAlign: 'center' },
  resetBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 40, borderRadius: RADIUS.full, backgroundColor: 'rgba(255,255,255,0.06)' },
  resetTxt: { color: COLORS.text, fontWeight: '700', fontSize: FONT.sm },
});
