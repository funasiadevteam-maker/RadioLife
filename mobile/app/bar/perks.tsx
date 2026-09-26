// Win Wallet (mobile) — "My drink perks": every bar-wheel prize the user won.
import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator, RefreshControl, Share, Modal } from 'react-native';
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
  const [giftFor, setGiftFor] = useState<any>(null);
  const [friends, setFriends] = useState<any[]>([]);

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

  const openGift = async (p: any) => {
    setGiftFor(p);
    try { const { data } = await api.get('/social/friends'); setFriends(data.friends || []); } catch (_) { setFriends([]); }
  };
  const doGift = async (fid: string) => {
    const pid = giftFor.play_id;
    try {
      await api.post(`/bar-games/plays/${pid}/gift`, { friend_id: fid });
      setData((d: any) => ({ ...d, items: d.items.filter((i: any) => i.play_id !== pid) }));
      setGiftFor(null);
    } catch (_) {}
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
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <TouchableOpacity onPress={() => share(p)} testID={`perk-share-${p.play_id}`} style={s.shareBtn}>
                      <Ionicons name="share-social-outline" size={12} color={COLORS.text} />
                      <Text style={s.shareTxt}>Share</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => openGift(p)} testID={`perk-gift-${p.play_id}`} style={s.giftBtn}>
                      <Ionicons name="gift-outline" size={12} color="#db2777" />
                      <Text style={s.giftTxt}>Gift</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}
            </View>
            );
          })}
        </ScrollView>
      )}

      <Modal visible={!!giftFor} transparent animationType="slide" onRequestClose={() => setGiftFor(null)}>
        <TouchableOpacity style={s.modalBg} activeOpacity={1} onPress={() => setGiftFor(null)} testID="perk-gift-modal">
          <TouchableOpacity activeOpacity={1} style={s.sheet}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={s.sheetTitle}>🎁 Gift “{giftFor?.label}”</Text>
              <TouchableOpacity onPress={() => setGiftFor(null)} testID="gift-close"><Ionicons name="close" size={22} color={COLORS.text} /></TouchableOpacity>
            </View>
            <Text style={s.sheetSub}>Pick a friend — the perk leaves your wallet and lands in theirs.</Text>
            {friends.length === 0 ? (
              <Text style={s.giftEmpty} testID="gift-no-friends">Add friends first to gift a perk.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 320 }}>
                {friends.map((f) => (
                  <TouchableOpacity key={f.user_id} onPress={() => doGift(f.user_id)} testID={`gift-friend-${f.user_id}`} style={s.friendRow}>
                    <View style={s.friendAv}><Text style={{ color: '#fff', fontWeight: '900' }}>{(f.name || '?').slice(0, 1)}</Text></View>
                    <Text style={s.friendName} numberOfLines={1}>{f.name || 'Listener'}</Text>
                    <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
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
  giftBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, height: 30, borderRadius: 15, backgroundColor: 'rgba(219,39,119,0.12)' },
  giftTxt: { color: '#db2777', fontSize: FONT.xs, fontWeight: '800' },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.bg, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: SPACING.md, paddingBottom: SPACING.xl },
  sheetTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  sheetSub: { color: COLORS.textDim, fontSize: FONT.xs, marginBottom: 12 },
  giftEmpty: { color: COLORS.textMuted, fontSize: FONT.sm, textAlign: 'center', paddingVertical: 24 },
  friendRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  friendAv: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.purple, alignItems: 'center', justifyContent: 'center' },
  friendName: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  redeemed: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  redeemedTxt: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
});
