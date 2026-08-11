// Saved-card picker for one-tap checkout. Lists the user's saved Stripe cards,
// lets them add a card via a hosted setup flow, and reports the chosen card up
// via onSelect (null = pay with a new card at Stripe checkout).
import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

const BRAND: Record<string, string> = {
  visa: 'Visa', mastercard: 'Mastercard', amex: 'Amex', discover: 'Discover',
};

type Card = { id: string; brand: string; last4: string; exp_month: number; exp_year: number; is_default: boolean };

export default function SavedCardPicker({
  selected, onSelect,
}: { selected: string | null; onSelect: (id: string | null) => void }) {
  const router = useRouter();
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async (autoselect = false) => {
    try {
      const r = await api.get('/shop/wallet/cards');
      const list: Card[] = r.data.cards || [];
      setCards(list);
      if (autoselect) {
        const def = list.find((c) => c.is_default);
        if (def) onSelect(def.id);
      }
    } catch { /* keep empty */ } finally { setLoading(false); }
  }, [onSelect]);

  useEffect(() => { load(true); }, [load]);

  const addCard = async () => {
    setAdding(true);
    try {
      const r = await api.post('/shop/wallet/cards/setup-session', {
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      const sid = r.data.session_id;
      if (r.data.checkout_url) await WebBrowser.openBrowserAsync(r.data.checkout_url);
      if (sid) { try { await api.post(`/shop/wallet/cards/setup-session/${sid}/sync`); } catch { /* ignore */ } }
      await load(true);
    } catch { /* ignore */ } finally { setAdding(false); }
  };

  if (loading) {
    return (
      <View style={s.wrap} testID="cart-card-picker-loading">
        <ActivityIndicator color={COLORS.primary} />
      </View>
    );
  }

  return (
    <View style={s.wrap} testID="cart-card-picker">
      <View style={s.head}>
        <Ionicons name="card" size={16} color={COLORS.text} />
        <Text style={s.headText}>Payment method</Text>
        <TouchableOpacity onPress={() => router.push('/shop/wallet/cards')} testID="cart-manage-cards">
          <Text style={s.manage}>Manage</Text>
        </TouchableOpacity>
      </View>

      {cards.map((c) => {
        const on = selected === c.id;
        return (
          <TouchableOpacity key={c.id} style={[s.row, on && s.rowOn]} onPress={() => onSelect(c.id)} testID={`cart-card-${c.id}`}>
            <View style={[s.radio, on && s.radioOn]} />
            <Ionicons name="card-outline" size={16} color={COLORS.text} />
            <Text style={s.rowText}>{BRAND[c.brand] || c.brand} •••• {c.last4}</Text>
            {c.is_default && <Text style={s.defaultTag}>DEFAULT</Text>}
          </TouchableOpacity>
        );
      })}

      <TouchableOpacity style={[s.row, selected === null && s.rowOn]} onPress={() => onSelect(null)} testID="cart-card-new">
        <View style={[s.radio, selected === null && s.radioOn]} />
        <Ionicons name="card-outline" size={16} color={COLORS.text} />
        <Text style={s.rowText}>Pay with a new card</Text>
      </TouchableOpacity>

      <TouchableOpacity style={s.add} onPress={addCard} disabled={adding} testID="cart-add-card">
        {adding ? <ActivityIndicator color={COLORS.primary} />
          : <><Ionicons name="add" size={16} color={COLORS.primary} /><Text style={s.addText}>Add a card</Text></>}
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  headText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  manage: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, padding: 11, marginBottom: 8 },
  rowOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  radio: { width: 16, height: 16, borderRadius: 8, borderWidth: 2, borderColor: COLORS.textMuted },
  radioOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary },
  rowText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  defaultTag: { color: COLORS.green, fontSize: 10, fontWeight: '900' },
  add: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 8 },
  addText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
});
