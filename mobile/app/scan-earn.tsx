import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, TextInput,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

export default function ScanEarn() {
  const router = useRouter();
  const [amount, setAmount] = useState('20');
  const [merchant, setMerchant] = useState('m_karak');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  const earn = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) return;
    setBusy(true); setResult(null);
    try {
      const r = await api.post('/rewards/scan-earn', {
        amount_usd: amt, merchant_id: merchant || undefined,
      });
      setResult(r.data);
    } catch { setResult({ error: true }); }
    finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen} testID="scan-earn-screen">
      <View style={s.top}>
        <TouchableOpacity onPress={() => router.back()} testID="scan-earn-back"><Ionicons name="arrow-back" size={20} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>Scan & Earn</Text><View style={{ width: 20 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.lg }}>
        <View style={s.hero}>
          <Ionicons name="sparkles" size={22} color="#fff" />
          <Text style={s.heroText}>Points are decided by AI — the more you engage, the more you earn per dollar.</Text>
        </View>

        <Text style={s.label}>Amount spent (USD)</Text>
        <TextInput style={s.input} value={amount} onChangeText={setAmount} keyboardType="numeric" testID="scan-earn-amount" placeholder="20" placeholderTextColor={COLORS.textMuted} />
        <Text style={s.label}>Merchant</Text>
        <TextInput style={s.input} value={merchant} onChangeText={setMerchant} testID="scan-earn-merchant" placeholder="merchant id" placeholderTextColor={COLORS.textMuted} />

        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.lg }, busy && { opacity: 0.5 }]} onPress={earn} disabled={busy} testID="scan-earn-btn">
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={common.btnPrimaryText}>Scan & Earn points</Text>}
        </TouchableOpacity>

        {result && !result.error && (
          <View style={s.card} testID="scan-earn-result">
            <Text style={s.points}>+{result.points} <Text style={s.bc}>BigCoin</Text></Text>
            <Text style={s.mult}>AI multiplier ×{result.multiplier} · {result.tier} tier</Text>
            <Text style={s.reason}>{result.reason}</Text>
            {(result.bonuses?.bonus_points > 0) && (
              <View style={s.bonus} testID="scan-earn-bonus"><Ionicons name="gift" size={14} color={COLORS.green} /><Text style={s.bonusText}>+{result.bonuses.bonus_points} threshold bonus!</Text></View>
            )}
            {result.bonuses?.bonus_games_unlocked && (
              <View style={s.bonus}><Ionicons name="game-controller" size={14} color={COLORS.primary} /><Text style={s.bonusText}>Bonus games unlocked</Text></View>
            )}
            {result.bonuses?.concert_pass && (
              <View style={s.bonus}><Ionicons name="ticket" size={14} color={COLORS.secondary} /><Text style={s.bonusText}>Concert pass unlocked!</Text></View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm },
  topTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  hero: { flexDirection: 'row', gap: 10, alignItems: 'center', backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  heroText: { color: '#fff', fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1, marginTop: SPACING.md, marginBottom: 6 },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, paddingHorizontal: 14, paddingVertical: 12, color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  card: { marginTop: SPACING.lg, backgroundColor: '#fff7ed', borderRadius: RADIUS.xl, borderWidth: 1, borderColor: '#fed7aa', padding: SPACING.lg, alignItems: 'center' },
  points: { color: COLORS.primary, fontSize: 34, fontWeight: '900' },
  bc: { fontSize: FONT.md, fontWeight: '800' },
  mult: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 4 },
  reason: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6, textAlign: 'center' },
  bonus: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 },
  bonusText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
});
