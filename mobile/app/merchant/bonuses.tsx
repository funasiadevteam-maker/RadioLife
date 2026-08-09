// Phase RWD.5 — Merchant self-serve Sponsored Bonus windows (mobile).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

interface Biz { business_id: string; name?: string; city?: string }
interface Win { window_id: string; title: string; multiplier: number; merchant_id: string; active: boolean; budget_usd?: number }

export default function MerchantBonuses() {
  const router = useRouter();
  const [bizes, setBizes] = useState<Biz[]>([]);
  const [windows, setWindows] = useState<Win[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [mult, setMult] = useState('2');
  const [hours, setHours] = useState('6');
  const [budget, setBudget] = useState('50');
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, w] = await Promise.all([
        api.get('/merchant/my-businesses'),
        api.get('/merchant/bonus-windows'),
      ]);
      setBizes(b.data.items || []);
      setWindows(w.data.items || []);
      if (!sel && b.data.items?.length) setSel(b.data.items[0].business_id);
    } catch { setMsg('Failed to load — merchant login required.'); }
    finally { setLoading(false); }
  }, [sel]);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!sel) { setMsg('Pick a venue first.'); return; }
    setBusy(true);
    try {
      await api.post('/merchant/bonus-windows', {
        merchant_id: sel, multiplier: Number(mult), hours: Number(hours),
        budget_usd: Number(budget), title: title || undefined,
      });
      setMsg('Bonus window live! 🎉');
      setTitle('');
      await load();
    } catch { setMsg("Couldn't create — check your inputs."); }
    finally { setBusy(false); setTimeout(() => setMsg(null), 2500); }
  };

  const deactivate = async (id: string) => {
    await api.post(`/merchant/bonus-windows/${id}/deactivate`);
    await load();
  };

  if (loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="mb-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Sponsor a Bonus</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="merchant-bonuses-root">
        {msg && <View style={s.flash}><Text style={s.flashText}>{msg}</Text></View>}

        <Text style={s.intro}>
          Draw more customers with a time-boxed points multiplier at your venue.
        </Text>

        {bizes.length === 0 ? (
          <View style={s.card}><Text style={s.dim}>No venue is linked to your account yet.</Text></View>
        ) : (
          <>
            <Text style={s.label}>YOUR VENUE</Text>
            <View style={s.chips}>
              {bizes.map((b) => (
                <TouchableOpacity key={b.business_id} testID={`mb-venue-${b.business_id}`}
                  style={[s.chip, sel === b.business_id && s.chipOn]}
                  onPress={() => setSel(b.business_id)}>
                  <Text style={[s.chipText, sel === b.business_id && s.chipTextOn]} numberOfLines={1}>
                    {b.name || b.business_id}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={s.card}>
              <Text style={s.label}>OFFER TITLE</Text>
              <TextInput style={s.input} value={title} onChangeText={setTitle}
                placeholder="e.g. 2× points tonight" placeholderTextColor={COLORS.textMuted}
                testID="mb-title" />
              <View style={s.row3}>
                <View style={{ flex: 1 }}>
                  <Text style={s.label}>MULTIPLIER</Text>
                  <TextInput style={s.input} value={mult} onChangeText={setMult}
                    keyboardType="decimal-pad" testID="mb-multiplier" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.label}>HOURS</Text>
                  <TextInput style={s.input} value={hours} onChangeText={setHours}
                    keyboardType="number-pad" testID="mb-hours" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.label}>BUDGET $</Text>
                  <TextInput style={s.input} value={budget} onChangeText={setBudget}
                    keyboardType="number-pad" testID="mb-budget" />
                </View>
              </View>
              <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }]} onPress={create}
                disabled={busy} testID="mb-create">
                {busy ? <ActivityIndicator color="#fff" />
                  : <><Ionicons name="flash" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Launch bonus</Text></>}
              </TouchableOpacity>
            </View>
          </>
        )}

        {windows.length > 0 && <Text style={s.label}>YOUR BONUS WINDOWS</Text>}
        {windows.map((w) => (
          <View key={w.window_id} style={s.winRow} testID={`mb-window-${w.window_id}`}>
            <Text style={s.winMult}>{w.multiplier}×</Text>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.winTitle} numberOfLines={1}>{w.title}</Text>
              <Text style={s.dim}>{w.active ? 'Active' : 'Ended'} · ${w.budget_usd ?? 0} budget</Text>
            </View>
            {w.active && (
              <TouchableOpacity onPress={() => deactivate(w.window_id)} testID={`mb-end-${w.window_id}`}>
                <Text style={s.end}>End</Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, marginTop: SPACING.sm, marginBottom: 6 },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  dim: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: SPACING.sm },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, maxWidth: 200 },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  chipTextOn: { color: '#fff' },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  row3: { flexDirection: 'row', gap: 10 },
  flash: { backgroundColor: COLORS.green + '18', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  flashText: { color: COLORS.green, fontWeight: '800', fontSize: FONT.sm, textAlign: 'center' },
  winRow: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, marginBottom: SPACING.sm, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  winMult: { color: COLORS.gold, fontSize: FONT.md, fontWeight: '900' },
  winTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  end: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
});
