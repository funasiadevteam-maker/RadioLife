// Saved Cards wallet — add a card via Stripe hosted setup, set a default for
// one-tap checkout, and remove cards. Route: /shop/wallet/cards.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

const BRAND: Record<string, string> = {
  visa: 'Visa', mastercard: 'Mastercard', amex: 'Amex', discover: 'Discover',
};

type Card = { id: string; brand: string; last4: string; exp_month: number; exp_year: number; is_default: boolean };

export default function WalletCards() {
  const router = useRouter();
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/wallet/cards');
      setCards(r.data.cards || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addCard = async () => {
    setBusy(true);
    try {
      const r = await api.post('/shop/wallet/cards/setup-session', {
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      const sid = r.data.session_id;
      if (r.data.checkout_url) await WebBrowser.openBrowserAsync(r.data.checkout_url);
      if (sid) { try { await api.post(`/shop/wallet/cards/setup-session/${sid}/sync`); } catch { /* ignore */ } }
      await load();
    } catch { /* ignore */ } finally { setBusy(false); }
  };

  const setDefault = async (pm: string) => {
    setBusy(true);
    try { const r = await api.post(`/shop/wallet/cards/${pm}/default`); setCards(r.data.cards || []); }
    catch { /* ignore */ } finally { setBusy(false); }
  };

  const remove = async (pm: string) => {
    setBusy(true);
    try { const r = await api.delete(`/shop/wallet/cards/${pm}`); setCards(r.data.cards || []); }
    catch { /* ignore */ } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="wallet-cards-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Payment methods</Text>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <View style={common.center} testID="wallet-cards-loading"><ActivityIndicator color={COLORS.primary} /></View>
      ) : (
        <>
          <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 180 }} testID="wallet-cards-root">
            {cards.length === 0 ? (
              <View style={s.empty} testID="wallet-cards-empty">
                <Ionicons name="card-outline" size={40} color={COLORS.textMuted} />
                <Text style={s.emptyText}>No saved cards yet. Add one for faster, one-tap checkout.</Text>
              </View>
            ) : cards.map((c) => (
              <View key={c.id} style={s.card} testID={`wallet-card-${c.id}`}>
                <View style={s.cardIcon}><Ionicons name="card" size={20} color="#fff" /></View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.cardName}>{BRAND[c.brand] || c.brand} •••• {c.last4}</Text>
                  <Text style={s.cardExp}>Expires {String(c.exp_month).padStart(2, '0')}/{c.exp_year}</Text>
                </View>
                {c.is_default ? (
                  <View style={s.defaultBadge} testID={`wallet-card-default-badge-${c.id}`}>
                    <Ionicons name="star" size={11} color={COLORS.green} />
                    <Text style={s.defaultText}>Default</Text>
                  </View>
                ) : (
                  <TouchableOpacity onPress={() => setDefault(c.id)} disabled={busy} testID={`wallet-card-setdefault-${c.id}`} style={s.setDefault}>
                    <Text style={s.setDefaultText}>Set default</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => remove(c.id)} disabled={busy} testID={`wallet-card-remove-${c.id}`} style={s.removeBtn}>
                  <Ionicons name="trash-outline" size={16} color={COLORS.red} />
                </TouchableOpacity>
              </View>
            ))}
            <Text style={s.note}>
              <Ionicons name="lock-closed" size={11} color={COLORS.green} />  Cards are stored securely by Stripe — FUUSIC never sees your card number.
            </Text>
          </ScrollView>

          <View style={s.footer}>
            <TouchableOpacity style={[common.btnPrimary, busy && { opacity: 0.6 }]} disabled={busy} onPress={addCard} testID="wallet-cards-add">
              {busy ? <ActivityIndicator color="#fff" />
                : <><Ionicons name="add" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Add a card</Text></>}
            </TouchableOpacity>
          </View>
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  empty: { alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 28 },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', textAlign: 'center', marginTop: 10 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  cardIcon: { width: 42, height: 42, borderRadius: 12, backgroundColor: COLORS.text, alignItems: 'center', justifyContent: 'center' },
  cardName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  cardExp: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  defaultBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.green + '18', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 4 },
  defaultText: { color: COLORS.green, fontSize: 11, fontWeight: '900' },
  setDefault: { borderWidth: 1, borderColor: COLORS.primary + '55', borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 5 },
  setDefaultText: { color: COLORS.primary, fontSize: 11, fontWeight: '800' },
  removeBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  note: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 8, lineHeight: 18 },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
});
