import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, Alert, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

const OBJECTIVES = [
  { id: 'awareness', title: 'Awareness', blurb: 'Maximize reach', icon: 'megaphone-outline' },
  { id: 'coupon_save', title: 'Coupon Save', blurb: 'Drive coupon saves', icon: 'pricetag-outline' },
  { id: 'store_visit', title: 'Store Visit', blurb: 'Drive foot traffic', icon: 'storefront-outline' },
  { id: 'ticket_sale', title: 'Ticket Sale', blurb: 'Sell event tickets', icon: 'ticket-outline' },
];

const CHANNELS = [
  'morning_masala', 'bollywood_mehfil', 'party_dubai',
  'punjabi_beats', 'late_night_drive', 'devotional_hour',
  'retro_lounge', 'workout_wala',
];
const TIME_OF_DAY = ['morning', 'afternoon', 'evening', 'late_night'];
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const TAKEOVER_THRESHOLD = 1000;

const FREQ_LABELS: Record<string, [string, number]> = {
  min_seconds_between: ['Min seconds between', 600],
  max_impressions_per_hour: ['Max per hour', 3],
  max_impressions_per_day: ['Max per day', 10],
  max_per_advertiser_per_week: ['Max per advertiser / week', 50],
  max_per_channel_cadence: ['Min songs between', 4],
};

export default function CampaignWizard() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [advId, setAdvId] = useState('');
  const [name, setName] = useState('');
  const [obj, setObj] = useState('awareness');
  const [budget, setBudget] = useState('80');
  const [dailyBudget, setDailyBudget] = useState('20');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [market, setMarket] = useState('dubai');
  const [channelSlugs, setChannelSlugs] = useState<string[]>([]);
  const [timeOfDay, setTimeOfDay] = useState<string[]>([]);
  const [daysOfWeek, setDaysOfWeek] = useState<number[]>([]);
  const [attrWindow, setAttrWindow] = useState('24');
  const [freqCaps, setFreqCaps] = useState<Record<string, number>>({});
  const [takeoverEnabled, setTakeoverEnabled] = useState(false);
  const [takeoverChannel, setTakeoverChannel] = useState('morning_masala');
  const [formats, setFormats] = useState<any[]>([]);
  const [adFormat, setAdFormat] = useState('banner');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/advertiser/me');
        const items = r.data.items || [];
        if (items.length) {
          setAdvId(items[0].advertiser_id);
          setMarket(items[0].market || 'dubai');
        }
      } catch {}
      try {
        const f = await api.get('/rate-card/formats');
        setFormats(f.data.items || []);
        if (f.data.items?.length) setAdFormat(f.data.items[0].format);
      } catch {}
    })();
  }, []);

  const toggle = (arr: string[], v: string) =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
  const toggleDay = (i: number) =>
    daysOfWeek.includes(i) ? daysOfWeek.filter((x) => x !== i) : [...daysOfWeek, i];

  const submit = async () => {
    if (!advId) { Alert.alert('Error', 'No advertiser'); return; }
    const budgetVal = parseFloat(budget) || 0;
    if (budgetVal <= 0) { Alert.alert('Error', 'Budget must be > 0'); return; }
    const windowVal = parseInt(attrWindow) || 24;
    if (windowVal < 1 || windowVal > 720) {
      Alert.alert('Validation', 'Attribution window must be 1–720 hours'); return;
    }
    setSubmitting(true);
    try {
      const body: any = {
        name: name || 'Untitled campaign',
        objective: obj,
        budget_total_usd: budgetVal,
        budget_daily_usd: parseFloat(dailyBudget) || null,
        start_date: startDate || null,
        end_date: endDate || null,
        targeting: {
          market, time_of_day: timeOfDay, days_of_week: daysOfWeek,
          weather: [], channel_slugs: channelSlugs, interests: [],
          ad_format: adFormat,
        },
        creative_ids: [],
        attribution_window_hours: windowVal,
      };
      if (takeoverEnabled && budgetVal >= TAKEOVER_THRESHOLD) {
        body.takeover_config = {
          enabled: true, channel_slug: takeoverChannel,
          window_start: '', window_end: '',
          windows_per_day: 1, exclusive: true,
        };
      }
      if (Object.keys(freqCaps).length > 0) {
        body.frequency_caps = freqCaps;
      }
      const c = await api.post(`/advertiser/${advId}/campaigns`, body);
      const cid = c.data.campaign_id;
      try { await api.post(`/advertiser/${advId}/campaigns/${cid}/submit`); } catch {}
      Alert.alert('Success', 'Campaign created');
      router.replace(`/advertiser/campaign/${cid}`);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Submit failed');
    } finally { setSubmitting(false); }
  };

  const next = () => setStep((s) => Math.min(4, s + 1));
  const prev = () => setStep((s) => Math.max(1, s - 1));
  const estImpressions = Math.round((parseFloat(budget) || 0) / 5 * 1000);
  const budgetNum = parseFloat(budget) || 0;

  return (
    <SafeAreaView style={common.screen} testID="campaign-wizard">
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        {/* Header */}
        <View style={st.header}>
          <Text style={st.headerTitle}>New campaign · Step {step}/4</Text>
          <TouchableOpacity onPress={() => router.back()} testID="wizard-close">
            <Ionicons name="close" size={20} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>

        {/* Progress bar */}
        <View style={st.progressRow}>
          {[1, 2, 3, 4].map((i) => (
            <View key={i} style={[st.progressSeg, i <= step && st.progressSegActive]} />
          ))}
        </View>

        <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
          {/* Step 1: Basics */}
          {step === 1 && (
            <View testID="wizard-step-1">
              <Text style={st.stepTitle}>Pick your goal</Text>
              <Text style={common.label}>CAMPAIGN NAME</Text>
              <TextInput style={common.input} placeholder="Campaign name" placeholderTextColor={COLORS.textMuted}
                value={name} onChangeText={setName} testID="wizard-name" />

              <Text style={[common.label, { marginTop: SPACING.lg }]}>OBJECTIVE</Text>
              <View style={st.objGrid}>
                {OBJECTIVES.map((o) => (
                  <TouchableOpacity key={o.id} onPress={() => setObj(o.id)}
                    style={[st.objCard, obj === o.id && st.objCardActive]}
                    testID={`wizard-obj-${o.id}`}>
                    <Ionicons name={o.icon as any} size={20} color={obj === o.id ? COLORS.secondary : COLORS.textDim} />
                    <Text style={[st.objTitle, obj === o.id && { color: COLORS.secondary }]}>{o.title}</Text>
                    <Text style={st.objBlurb}>{o.blurb}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[common.label, { marginTop: SPACING.lg }]}>AD FORMAT</Text>
              <View style={st.fmtRow}>
                {formats.map((f) => {
                  const on = adFormat === f.format;
                  const price = f.base_cents != null
                    ? `${f.pricing_model} · $${(f.base_cents / 100).toFixed(2)}`
                    : '';
                  return (
                    <TouchableOpacity key={f.format} onPress={() => setAdFormat(f.format)}
                      style={[st.fmtCard, on && st.fmtCardActive]} testID={`wizard-format-${f.format}`}>
                      <Ionicons name={f.icon as any} size={18} color={on ? COLORS.secondary : COLORS.textDim} />
                      <Text style={[st.fmtTitle, on && { color: COLORS.secondary }]}>{f.label}</Text>
                      <Text style={st.fmtPrice}>{price}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {budgetNum >= TAKEOVER_THRESHOLD && (
                <TouchableOpacity
                  style={[st.takeoverCard, obj === 'channel_takeover' && st.takeoverCardActive]}
                  onPress={() => { setObj('channel_takeover'); setTakeoverEnabled(true); }}
                  testID="wizard-obj-channel_takeover"
                >
                  <Text style={{ fontSize: 20 }}>🌟</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={st.takeoverTitle}>Channel takeover · 2hr</Text>
                    <Text style={st.takeoverBlurb}>Own 100% of inter-song slots · min $1,000</Text>
                  </View>
                </TouchableOpacity>
              )}

              <Text style={[common.label, { marginTop: SPACING.lg }]}>TOTAL BUDGET (USD)</Text>
              <TextInput style={common.input} keyboardType="numeric" value={budget}
                onChangeText={setBudget} testID="wizard-budget" />

              <Text style={[common.label, { marginTop: SPACING.md }]}>DAILY BUDGET (OPTIONAL)</Text>
              <TextInput style={common.input} keyboardType="numeric" value={dailyBudget}
                onChangeText={setDailyBudget} />

              <View style={[common.card, { marginTop: SPACING.md }]}>
                <Text style={common.label}>ESTIMATED IMPRESSIONS</Text>
                <Text style={st.estValue} testID="wizard-est-impressions">{estImpressions.toLocaleString()}</Text>
                <Text style={{ color: COLORS.textDim, fontSize: FONT.xs }}>at $5 CPM</Text>
              </View>
            </View>
          )}

          {/* Step 2: Creative */}
          {step === 2 && (
            <View testID="wizard-step-2">
              <Text style={st.stepTitle}>Creative</Text>
              <Text style={{ color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.lg }}>
                Add a creative for your campaign. Use the AI Ad Creator to generate one automatically.
              </Text>
              <TouchableOpacity
                style={[common.card, { alignItems: 'center', paddingVertical: SPACING.xl }]}
                onPress={() => router.push('/advertiser/ai-create')}
                testID="mobile-ai-create-submit"
              >
                <Ionicons name="sparkles" size={32} color={COLORS.orange} />
                <Text style={[st.stepTitle, { marginTop: SPACING.sm, textAlign: 'center' }]}>
                  Generate with AI
                </Text>
                <Text style={{ color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: 4 }}>
                  Script + voice + image in one click
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Step 3: Targeting */}
          {step === 3 && (
            <View testID="wizard-step-3">
              <Text style={st.stepTitle}>Targeting</Text>
              <Text style={common.label}>MARKET</Text>
              <View style={st.chipsRow}>
                {['dubai', 'dfw'].map((m) => (
                  <TouchableOpacity key={m} style={[st.chip, market === m && st.chipActive]}
                    onPress={() => setMarket(m)}>
                    <Text style={[st.chipText, market === m && st.chipTextActive]}>
                      {m === 'dubai' ? '🇦🇪 Dubai' : '🇺🇸 DFW'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[common.label, { marginTop: SPACING.md }]}>TIME OF DAY</Text>
              <View style={st.chipsRow}>
                {TIME_OF_DAY.map((t) => (
                  <TouchableOpacity key={t} style={[st.chip, timeOfDay.includes(t) && st.chipActive]}
                    onPress={() => setTimeOfDay(toggle(timeOfDay, t))} testID={`chip-${t}`}>
                    <Text style={[st.chipText, timeOfDay.includes(t) && st.chipTextActive]}>{t}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[common.label, { marginTop: SPACING.md }]}>DAYS</Text>
              <View style={st.chipsRow}>
                {DAYS.map((d, i) => (
                  <TouchableOpacity key={d} style={[st.chip, daysOfWeek.includes(i) && st.chipActive]}
                    onPress={() => setDaysOfWeek(toggleDay(i) as any)} testID={`chip-${d}`}>
                    <Text style={[st.chipText, daysOfWeek.includes(i) && st.chipTextActive]}>{d}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={[common.label, { marginTop: SPACING.md }]}>CHANNELS</Text>
              <View style={st.chipsRow}>
                {CHANNELS.map((c) => (
                  <TouchableOpacity key={c} style={[st.chip, channelSlugs.includes(c) && st.chipActive]}
                    onPress={() => setChannelSlugs(toggle(channelSlugs, c))} testID={`chip-${c}`}>
                    <Text style={[st.chipText, channelSlugs.includes(c) && st.chipTextActive]}>{c}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}

          {/* Step 4: Advanced */}
          {step === 4 && (
            <View testID="wizard-step-4">
              <Text style={st.stepTitle}>Advanced</Text>

              <Text style={common.label}>ATTRIBUTION WINDOW (HOURS)</Text>
              <TextInput style={common.input} keyboardType="numeric" value={attrWindow}
                onChangeText={setAttrWindow} testID="wizard-attribution-window-hours" />
              <Text style={{ color: COLORS.textDim, fontSize: FONT.xs, marginTop: 4 }}>
                Coupon saves only count if within this window of ad serve. Default 24h, range 1–720.
              </Text>

              <Text style={[common.label, { marginTop: SPACING.lg }]}>FREQUENCY CAPS</Text>
              <View style={common.card} testID="freq-caps-editor">
                {Object.entries(FREQ_LABELS).map(([key, [label, def]]) => (
                  <View key={key} style={st.freqRow}>
                    <Text style={{ color: COLORS.textDim, fontSize: FONT.sm, flex: 1 }}>{label}</Text>
                    <TextInput
                      style={[common.input, { width: 80, textAlign: 'right', padding: 10 }]}
                      keyboardType="numeric"
                      defaultValue={String(freqCaps[key] ?? def)}
                      onChangeText={(v) => setFreqCaps({ ...freqCaps, [key]: parseInt(v) || 0 })}
                      testID={`cap-${key}`}
                    />
                  </View>
                ))}
              </View>

              {budgetNum >= TAKEOVER_THRESHOLD && (
                <View style={{ marginTop: SPACING.lg }}>
                  <TouchableOpacity
                    style={[st.takeoverCard, takeoverEnabled && st.takeoverCardActive]}
                    onPress={() => setTakeoverEnabled(!takeoverEnabled)}
                    testID="wizard-takeover-toggle"
                  >
                    <Text style={{ fontSize: 18 }}>🌟</Text>
                    <View style={{ flex: 1 }}>
                      <Text style={st.takeoverTitle}>Channel Takeover</Text>
                      <Text style={st.takeoverBlurb}>Exclusive slot ownership · 2hr window</Text>
                    </View>
                    <Ionicons name={takeoverEnabled ? 'checkbox' : 'square-outline'} size={22} color={COLORS.orange} />
                  </TouchableOpacity>
                  {takeoverEnabled && (
                    <View style={[common.card, { marginTop: SPACING.sm }]}>
                      <Text style={common.label}>TAKEOVER CHANNEL</Text>
                      <View style={st.chipsRow}>
                        {CHANNELS.map((c) => (
                          <TouchableOpacity key={c}
                            style={[st.chip, takeoverChannel === c && st.chipActive]}
                            onPress={() => setTakeoverChannel(c)} testID={`takeover-ch-${c}`}>
                            <Text style={[st.chipText, takeoverChannel === c && st.chipTextActive]}>{c}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    </View>
                  )}
                </View>
              )}
            </View>
          )}

          {/* Nav */}
          <View style={st.navRow}>
            {step > 1 && (
              <TouchableOpacity style={common.btnGhost} onPress={prev} testID="wizard-prev">
                <Ionicons name="arrow-back" size={14} color={COLORS.textDim} />
                <Text style={common.btnGhostText}>Back</Text>
              </TouchableOpacity>
            )}
            <View style={{ flex: 1 }} />
            {step < 4 ? (
              <TouchableOpacity style={common.btnPrimary} onPress={next} testID="wizard-next">
                <Text style={common.btnPrimaryText}>Continue</Text>
                <Ionicons name="arrow-forward" size={14} color="#fff" />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                style={[common.btnPrimary, submitting && { opacity: 0.5 }]}
                onPress={submit} disabled={submitting} testID="wizard-submit"
              >
                {submitting ? <ActivityIndicator size="small" color="#fff" /> : (
                  <>
                    <Ionicons name="checkmark" size={16} color="#fff" />
                    <Text style={common.btnPrimaryText}>Submit campaign</Text>
                  </>
                )}
              </TouchableOpacity>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder,
  },
  headerTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '700' },
  progressRow: { flexDirection: 'row', gap: 4, paddingHorizontal: SPACING.lg, paddingTop: SPACING.md },
  progressSeg: { flex: 1, height: 4, borderRadius: 2, backgroundColor: COLORS.surfaceBorder },
  progressSegActive: { backgroundColor: COLORS.secondary },
  scroll: { padding: SPACING.lg, paddingBottom: 100 },
  stepTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '800', marginBottom: SPACING.md },
  objGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  objCard: {
    width: '48%' as any, borderRadius: RADIUS.lg, padding: SPACING.md,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  objCardActive: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.08)' },
  objTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700', marginTop: SPACING.xs },
  objBlurb: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  fmtRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  fmtCard: {
    width: '48%', padding: SPACING.md, borderRadius: RADIUS.md, borderWidth: 1,
    borderColor: COLORS.surfaceBorder, backgroundColor: COLORS.card,
  },
  fmtCardActive: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.06)' },
  fmtTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 6 },
  fmtPrice: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  takeoverCard: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: SPACING.md,
    borderWidth: 1, borderColor: 'rgba(251,183,86,0.3)',
  },
  takeoverCardActive: { borderColor: COLORS.orange, backgroundColor: 'rgba(251,183,86,0.08)' },
  takeoverTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  takeoverBlurb: { color: COLORS.textDim, fontSize: FONT.xs },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  chip: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  chipActive: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.08)' },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  chipTextActive: { color: COLORS.secondary },
  estValue: { color: COLORS.secondary, fontSize: FONT.xxl, fontWeight: '800', marginTop: 4 },
  freqRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: SPACING.sm },
  navRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.xl },
});
