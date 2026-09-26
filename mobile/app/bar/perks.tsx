// Win Wallet (mobile) — "My drink perks": every bar-wheel prize the user won.
import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator, RefreshControl, Share } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useFocusEffect, Stack } from 'expo-router';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

function expiryLabel(iso?: string) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return { expired: true, text: 'Expired' };
  const d = Math.ceil(diff / 86400000);
  return { expired: false, text: `Expires in ${d}d` };
}

export default function DrinkPerks() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get('/bar-games/wallet'); setData(data); }
    catch (_) { setData({ items: [], count: 0, active: 0 }); }
    finally { setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const redeem = async (id: string) => {
    try {
      await api.post(`/bar-games/plays/${id}/redeem`);
      setData((d: any) => ({ ...d, items: d.items.map((i: any) => (i.play_id === id ? { ...i, redeemed: true } : i)) }));
    } catch (_) {}
  };

  const share = async (p: any) => {
    try { await Share.share({ message: `🍸 I won “${p.label}” at ${p.business_name} on FUUSIC! Redeem with code ${p.code}.` }); } catch (_) {}
  };

  return (
    <SafeAreaView style={s.screen} testID="drink-perks-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="perks-back">
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View>
          <Text style={s.hTitle}>My drink perks</Text>
          <Text style={s.hSub}>Codes you’ve won on bar wheels</Text>
        </View>
      </View>

      {!data ? (
        <ActivityIndicator color={COLORS.primary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, gap: 12, paddingBottom: 40 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}>
          {data.items.length === 0 ? (
            <View style={s.empty} testID="perks-empty">
              <Ionicons name="wine-outline" size={34} color={COLORS.textMuted} />
              <Text style={s.emptyTxt}>No perks yet — spin a bar wheel to win free drinks and deals. 🍸</Text>
            </View>
          ) : data.items.map((p: any) => {
            const exp = expiryLabel(p.expires_at);
            const isExpired = p.expired || (exp && exp.expired);
            return (
            <View key={p.play_id} testID={`perk-${p.play_id}`} style={[s.card, (p.redeemed || isExpired) && { opacity: 0.55 }]}>
              <Text style={{ fontSize: 30 }}>{p.emoji || '🍹'}</Text>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.label} numberOfLines={1}>{p.label}</Text>
                <Text style={s.biz} numberOfLines={1}>{p.business_name}</Text>
                <View style={s.codeRow}><Ionicons name="ticket" size={13} color={COLORS.green} /><Text style={s.code}>{p.code}</Text></View>
                {exp ? (
                  <View style={s.expRow} testID={`perk-expiry-${p.play_id}`}>
                    <Ionicons name="time-outline" size={11} color={(isExpired || p.expiring_soon) ? COLORS.red : COLORS.gold} />
                    <Text style={[s.expTxt, { color: (isExpired || p.expiring_soon) ? COLORS.red : COLORS.gold }]}>
                      {isExpired ? 'Expired' : p.expiring_soon ? `Expires soon · ${exp.text}` : exp.text}
                    </Text>
                  </View>
                ) : null}
              </View>
              {p.redeemed ? (
                <View style={s.redeemed}><Ionicons name="checkmark-circle" size={13} color={COLORS.textMuted} /><Text style={s.redeemedTxt}>Redeemed</Text></View>
              ) : isExpired ? (
                <Text style={[s.redeemedTxt, { color: COLORS.red }]} testID={`perk-expired-${p.play_id}`}>Expired</Text>
              ) : (
                <View style={{ gap: 6, alignItems: 'flex-end' }}>
                  <TouchableOpacity onPress={() => redeem(p.play_id)} testID={`perk-redeem-${p.play_id}`} style={s.redeemBtn}>
                    <Text style={s.redeemBtnTxt}>Mark redeemed</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => share(p)} testID={`perk-share-${p.play_id}`} style={s.shareBtn}>
                    <Ionicons name="share-social-outline" size={12} color={COLORS.text} />
                    <Text style={s.shareTxt}>Share</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
            );
          })}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  hTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  hSub: { color: COLORS.textDim, fontSize: FONT.sm },
  empty: { alignItems: 'center', gap: 10, padding: 40, backgroundColor: COLORS.card, borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.cardBorder, marginTop: 20 },
  emptyTxt: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center' },
  card: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: 14, borderWidth: 1, borderColor: COLORS.cardBorder },
  label: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  biz: { color: COLORS.textMuted, fontSize: FONT.xs },
  codeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  code: { color: COLORS.green, fontWeight: '900', fontSize: FONT.sm, letterSpacing: 1 },
  expRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  expTxt: { fontSize: FONT.xs, fontWeight: '800' },
  redeemBtn: { paddingHorizontal: 12, height: 34, borderRadius: 17, backgroundColor: 'rgba(22,163,74,0.14)', alignItems: 'center', justifyContent: 'center' },
  redeemBtnTxt: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '900' },
  shareBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, height: 30, borderRadius: 15, backgroundColor: COLORS.inputBg },
  shareTxt: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800' },
  redeemed: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  redeemedTxt: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
});
