// Phase MKT.1 — Merchant Marketplace "Get More Customers" goal-first flow (mobile).
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
interface Goal { key: string; title: string; subtitle: string; icon: string; recommended: string[] }
interface CType { type: string; label: string; desc: string; icon: string; rate_key: string }
interface Campaign {
  campaign_id: string; type: string; title: string; status: string;
  budget_usd: number; spent_usd: number; bid_cents?: number; reward_points?: number;
  drawn?: boolean; entries_count?: number; num_winners?: number;
  impressions?: number; clicks?: number; plays?: number; wins?: number;
  answers_count?: number; correct_count?: number; claims?: number;
}

type Step = 'list' | 'goal' | 'type' | 'form';

export default function Marketplace() {
  const router = useRouter();
  const [step, setStep] = useState<Step>('list');
  const [loading, setLoading] = useState(true);
  const [bizes, setBizes] = useState<Biz[]>([]);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [ctypes, setCtypes] = useState<Record<string, CType>>({});
  const [hints, setHints] = useState<Record<string, any>>({});
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  // Wizard state
  const [goal, setGoal] = useState<Goal | null>(null);
  const [ctype, setCtype] = useState<CType | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [budget, setBudget] = useState('20');
  const [bid, setBid] = useState('30');
  const [couponTitle, setCouponTitle] = useState('');
  const [rewardPts, setRewardPts] = useState('10');
  const [q, setQ] = useState('');
  const [choiceA, setChoiceA] = useState('');
  const [choiceB, setChoiceB] = useState('');
  const [answer, setAnswer] = useState(0);
  const [winPts, setWinPts] = useState('25');
  const [winProb, setWinProb] = useState('30');
  const [prizeLabel, setPrizeLabel] = useState('');
  const [prizeDesc, setPrizeDesc] = useState('');
  const [numWinners, setNumWinners] = useState('1');
  const [tagline, setTagline] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [b, g, c] = await Promise.all([
        api.get('/merchant/my-businesses'),
        api.get('/merchant/marketplace/goals'),
        api.get('/merchant/marketplace/campaigns'),
      ]);
      setBizes(b.data.items || []);
      setGoals(g.data.goals || []);
      setCtypes(g.data.campaign_types || {});
      setHints(g.data.rate_card_hints || {});
      setCampaigns(c.data.items || []);
      if (!sel && b.data.items?.length) setSel(b.data.items[0].business_id);
    } catch { setMsg('Merchant login required to use the marketplace.'); }
    finally { setLoading(false); }
  }, [sel]);

  useEffect(() => { load(); }, [load]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(null), 2500); };

  const submit = async () => {
    if (!sel) { flash('Pick a venue first.'); return; }
    if (!ctype) return;
    setBusy(true);
    try {
      const body: any = {
        merchant_id: sel, type: ctype.type, goal: goal?.key,
        title: title || ctype.label, budget_usd: Number(budget),
      };
      if (ctype.type === 'coupon_bid') {
        body.bid_cents = Number(bid);
        body.coupon_title = couponTitle || title;
        body.reward_points_on_claim = 5;
      } else if (ctype.type === 'trivia') {
        body.reward_points = Number(rewardPts);
        body.questions = [{ q, choices: [choiceA, choiceB], answer_index: answer }];
      } else if (ctype.type === 'spin' || ctype.type === 'scratch') {
        body.win_points = Number(winPts);
        body.win_probability = Math.min(1, Math.max(0.01, Number(winProb) / 100));
        body.prize_label = prizeLabel || `${winPts} points`;
      } else if (ctype.type === 'giveaway') {
        body.prize_desc = prizeDesc;
        body.num_winners = Number(numWinners);
        body.reward_points_on_claim = 5;
      } else if (ctype.type === 'featured') {
        body.bid_cents = Number(bid);
        body.tagline = tagline;
      }
      await api.post('/merchant/marketplace/campaigns', body);
      flash('Campaign launched! 🎉');
      resetWizard();
      setStep('list');
      await load();
    } catch (e: any) {
      flash(e?.response?.data?.detail?.code || "Couldn't launch — check inputs.");
    } finally { setBusy(false); }
  };

  const resetWizard = () => {
    setGoal(null); setCtype(null); setTitle(''); setBudget('20'); setBid('30');
    setCouponTitle(''); setRewardPts('10'); setQ(''); setChoiceA(''); setChoiceB(''); setAnswer(0);
    setWinPts('25'); setWinProb('30'); setPrizeLabel(''); setPrizeDesc(''); setNumWinners('1');
    setTagline('');
  };

  const toggleStatus = async (c: Campaign) => {
    const action = c.status === 'active' ? 'pause' : 'activate';
    try { await api.post(`/merchant/marketplace/campaigns/${c.campaign_id}/${action}`); await load(); }
    catch (e: any) { flash(e?.response?.data?.detail?.code || 'Could not update.'); }
  };

  const campIcon = (t: string) =>
    t === 'trivia' ? 'help-circle' : t === 'spin' ? 'sync-circle'
    : t === 'scratch' ? 'sparkles' : t === 'giveaway' ? 'gift'
    : t === 'featured' ? 'star' : 'pricetag';

  const drawGiveaway = async (c: Campaign) => {
    try {
      const r = await api.post(`/merchant/marketplace/campaigns/${c.campaign_id}/draw`);
      flash(`Drew ${r.data.winners.length} winner(s) from ${r.data.total_entries} entries 🎉`);
      await load();
    } catch (e: any) { flash(e?.response?.data?.detail?.code || 'Could not draw.'); }
  };

  const campStats = (c: Campaign): { label: string; value: string | number }[] => {
    if (c.type === 'featured') return [{ label: 'Views', value: c.impressions ?? 0 }, { label: 'Taps', value: c.clicks ?? 0 }];
    if (c.type === 'spin' || c.type === 'scratch') return [{ label: 'Plays', value: c.plays ?? 0 }, { label: 'Wins', value: c.wins ?? 0 }];
    if (c.type === 'trivia') return [{ label: 'Answers', value: c.answers_count ?? 0 }, { label: 'Correct', value: c.correct_count ?? 0 }];
    if (c.type === 'coupon_bid') return [{ label: 'Claims', value: c.claims ?? 0 }];
    if (c.type === 'giveaway') return [{ label: 'Entries', value: c.entries_count ?? 0 }];
    return [];
  };

  if (loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const headerTitle = step === 'list' ? 'Get More Customers'
    : step === 'goal' ? "What's your goal?"
    : step === 'type' ? 'Pick a campaign' : 'Set it up';

  const onBack = () => {
    if (step === 'list') router.back();
    else if (step === 'goal') setStep('list');
    else if (step === 'type') setStep('goal');
    else setStep('type');
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={onBack} testID="mkt-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>{headerTitle}</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="marketplace-root">
        {msg && <View style={s.flash}><Text style={s.flashText}>{msg}</Text></View>}

        {/* STEP: LIST */}
        {step === 'list' && (
          <>
            <TouchableOpacity style={s.startCta} testID="mkt-start" onPress={() => setStep('goal')}>
              <Ionicons name="rocket" size={20} color="#fff" />
              <View style={{ flex: 1 }}>
                <Text style={s.startTitle}>Launch a campaign</Text>
                <Text style={s.startSub}>Bring more listeners to your venue</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color="#fff" />
            </TouchableOpacity>

            {campaigns.length > 0 && <Text style={s.label}>YOUR CAMPAIGNS</Text>}
            {campaigns.length === 0 && (
              <View style={s.card}><Text style={s.dim}>No campaigns yet. Launch your first one above.</Text></View>
            )}
            {campaigns.map((c) => (
              <View key={c.campaign_id} style={s.campWrap} testID={`mkt-campaign-${c.campaign_id}`}>
                <View style={s.campRow}>
                  <View style={s.campIcon}>
                    <Ionicons name={campIcon(c.type) as any} size={18} color={COLORS.primary} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.campTitle} numberOfLines={1}>{c.title}</Text>
                    <Text style={s.dim}>
                      {(ctypes[c.type]?.label || c.type)} · ${c.spent_usd.toFixed(2)}/${c.budget_usd} spent
                    </Text>
                  </View>
                  <TouchableOpacity onPress={() => toggleStatus(c)} testID={`mkt-toggle-${c.campaign_id}`}
                    style={[s.statusPill, c.status === 'active' ? s.statusActive : s.statusPaused]}>
                    <Text style={[s.statusText, { color: c.status === 'active' ? COLORS.green : COLORS.textMuted }]}>
                      {c.status === 'active' ? 'Active' : 'Paused'}
                    </Text>
                  </TouchableOpacity>
                  {c.type === 'giveaway' && !c.drawn && (
                    <TouchableOpacity onPress={() => drawGiveaway(c)} testID={`mkt-draw-${c.campaign_id}`}
                      style={s.drawBtn}>
                      <Text style={s.drawText}>Draw</Text>
                    </TouchableOpacity>
                  )}
                  {c.type === 'featured' && (
                    <TouchableOpacity onPress={() => router.push(`/merchant/insights/${c.campaign_id}` as any)}
                      testID={`mkt-insights-${c.campaign_id}`} style={s.drawBtn}>
                      <Ionicons name="stats-chart" size={13} color={COLORS.gold} />
                    </TouchableOpacity>
                  )}
                </View>
                <View style={s.statsRow} testID={`mkt-stats-${c.campaign_id}`}>
                  {campStats(c).map((st2) => (
                    <View key={st2.label} style={s.statPill}>
                      <Text style={s.statValue}>{st2.value}</Text>
                      <Text style={s.statLabel}>{st2.label}</Text>
                    </View>
                  ))}
                  <View style={s.statPill}>
                    <Text style={s.statValue}>${c.spent_usd.toFixed(2)}</Text>
                    <Text style={s.statLabel}>Spend</Text>
                  </View>
                </View>
              </View>
            ))}
          </>
        )}

        {/* STEP: GOAL */}
        {step === 'goal' && goals.map((g) => (
          <TouchableOpacity key={g.key} style={s.goalCard} testID={`mkt-goal-${g.key}`}
            onPress={() => { setGoal(g); setStep('type'); }}>
            <View style={s.goalIcon}><Ionicons name={g.icon as any} size={22} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.goalTitle}>{g.title}</Text>
              <Text style={s.dim}>{g.subtitle}</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
          </TouchableOpacity>
        ))}

        {/* STEP: TYPE */}
        {step === 'type' && goal && (
          <>
            <Text style={s.hintTop}>Recommended for “{goal.title}”</Text>
            {goal.recommended.map((t) => {
              const ct = ctypes[t];
              const h = hints[t] || {};
              if (!ct) return null;
              return (
                <TouchableOpacity key={t} style={s.goalCard} testID={`mkt-type-${t}`}
                  onPress={() => { setCtype(ct); setStep('form'); }}>
                  <View style={s.goalIcon}><Ionicons name={ct.icon as any} size={22} color={COLORS.primary} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.goalTitle}>{ct.label}</Text>
                    <Text style={s.dim}>{ct.desc}</Text>
                    {!!h.base_cents && (
                      <Text style={s.rate}>~{h.pricing_model} · ${(h.base_cents / 100).toFixed(2)} suggested</Text>
                    )}
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                </TouchableOpacity>
              );
            })}
          </>
        )}

        {/* STEP: FORM */}
        {step === 'form' && ctype && (
          <View>
            {bizes.length === 0 ? (
              <View style={s.card}><Text style={s.dim}>No venue linked to your account.</Text></View>
            ) : (
              <>
                <Text style={s.label}>YOUR VENUE</Text>
                <View style={s.chips}>
                  {bizes.map((b) => (
                    <TouchableOpacity key={b.business_id} testID={`mkt-venue-${b.business_id}`}
                      style={[s.chip, sel === b.business_id && s.chipOn]}
                      onPress={() => setSel(b.business_id)}>
                      <Text style={[s.chipText, sel === b.business_id && s.chipTextOn]} numberOfLines={1}>
                        {b.name || b.business_id}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </>
            )}

            <View style={s.card}>
              <Text style={s.label}>CAMPAIGN TITLE</Text>
              <TextInput style={s.input} value={title} onChangeText={setTitle}
                placeholder={ctype.label} placeholderTextColor={COLORS.textMuted} testID="mkt-title" />

              {ctype.type === 'coupon_bid' ? (
                <>
                  <Text style={s.label}>COUPON HEADLINE</Text>
                  <TextInput style={s.input} value={couponTitle} onChangeText={setCouponTitle}
                    placeholder="e.g. Free latte with any pastry" placeholderTextColor={COLORS.textMuted}
                    testID="mkt-coupon-title" />
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BID / CLAIM ¢</Text>
                      <TextInput style={s.input} value={bid} onChangeText={setBid}
                        keyboardType="number-pad" testID="mkt-bid" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BUDGET $</Text>
                      <TextInput style={s.input} value={budget} onChangeText={setBudget}
                        keyboardType="number-pad" testID="mkt-budget" />
                    </View>
                  </View>
                  <Text style={s.hint}>Higher bids win the top Featured Coupon slot.</Text>
                </>
              ) : ctype.type === 'trivia' ? (
                <>
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>REWARD PTS</Text>
                      <TextInput style={s.input} value={rewardPts} onChangeText={setRewardPts}
                        keyboardType="number-pad" testID="mkt-reward-pts" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BUDGET $</Text>
                      <TextInput style={s.input} value={budget} onChangeText={setBudget}
                        keyboardType="number-pad" testID="mkt-budget" />
                    </View>
                  </View>
                  <Text style={s.label}>QUESTION</Text>
                  <TextInput style={s.input} value={q} onChangeText={setQ}
                    placeholder="e.g. When did we open?" placeholderTextColor={COLORS.textMuted} testID="mkt-question" />
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>ANSWER A</Text>
                      <TextInput style={s.input} value={choiceA} onChangeText={setChoiceA} testID="mkt-choice-a" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>ANSWER B</Text>
                      <TextInput style={s.input} value={choiceB} onChangeText={setChoiceB} testID="mkt-choice-b" />
                    </View>
                  </View>
                  <Text style={s.label}>CORRECT ANSWER</Text>
                  <View style={s.chips}>
                    {['A', 'B'].map((lbl, i) => (
                      <TouchableOpacity key={lbl} testID={`mkt-answer-${i}`}
                        style={[s.chip, answer === i && s.chipOn]} onPress={() => setAnswer(i)}>
                        <Text style={[s.chipText, answer === i && s.chipTextOn]}>{lbl}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </>
              ) : (ctype.type === 'spin' || ctype.type === 'scratch') ? (
                <>
                  <Text style={s.label}>PRIZE LABEL</Text>
                  <TextInput style={s.input} value={prizeLabel} onChangeText={setPrizeLabel}
                    placeholder="e.g. 25 points" placeholderTextColor={COLORS.textMuted} testID="mkt-prize-label" />
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>WIN PTS</Text>
                      <TextInput style={s.input} value={winPts} onChangeText={setWinPts}
                        keyboardType="number-pad" testID="mkt-win-pts" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>WIN %</Text>
                      <TextInput style={s.input} value={winProb} onChangeText={setWinProb}
                        keyboardType="number-pad" testID="mkt-win-prob" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BUDGET $</Text>
                      <TextInput style={s.input} value={budget} onChangeText={setBudget}
                        keyboardType="number-pad" testID="mkt-budget" />
                    </View>
                  </View>
                  <Text style={s.hint}>Listeners get one play. Winners earn the prize points instantly.</Text>
                </>
              ) : ctype.type === 'giveaway' ? (
                <>
                  <Text style={s.label}>PRIZE DESCRIPTION</Text>
                  <TextInput style={s.input} value={prizeDesc} onChangeText={setPrizeDesc}
                    placeholder="e.g. $100 dinner for two" placeholderTextColor={COLORS.textMuted}
                    testID="mkt-prize-desc" />
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>WINNERS</Text>
                      <TextInput style={s.input} value={numWinners} onChangeText={setNumWinners}
                        keyboardType="number-pad" testID="mkt-num-winners" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BUDGET $</Text>
                      <TextInput style={s.input} value={budget} onChangeText={setBudget}
                        keyboardType="number-pad" testID="mkt-budget" />
                    </View>
                  </View>
                  <Text style={s.hint}>Listeners enter to win. Draw winners from your campaign list.</Text>
                </>
              ) : (
                <>
                  <Text style={s.label}>TAGLINE</Text>
                  <TextInput style={s.input} value={tagline} onChangeText={setTagline}
                    placeholder="e.g. Best karak in Karama" placeholderTextColor={COLORS.textMuted}
                    testID="mkt-tagline" />
                  <View style={s.row2}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BID / TAP ¢</Text>
                      <TextInput style={s.input} value={bid} onChangeText={setBid}
                        keyboardType="number-pad" testID="mkt-bid" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.label}>BUDGET $</Text>
                      <TextInput style={s.input} value={budget} onChangeText={setBudget}
                        keyboardType="number-pad" testID="mkt-budget" />
                    </View>
                  </View>
                  <Text style={s.hint}>Higher bids rank first in local discovery.</Text>
                </>
              )}

              <TouchableOpacity style={[common.btnPrimary, { marginTop: 14 }]} onPress={submit}
                disabled={busy} testID="mkt-launch">
                {busy ? <ActivityIndicator color="#fff" />
                  : <><Ionicons name="rocket" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Launch campaign</Text></>}
              </TouchableOpacity>
            </View>
          </View>
        )}
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
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, marginTop: SPACING.sm, marginBottom: 6 },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  dim: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  hint: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 8 },
  hintTop: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginBottom: SPACING.sm },
  rate: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '700', marginTop: 4 },
  startCta: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  startTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  startSub: { color: '#ffffffcc', fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  goalCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.sm },
  goalIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  goalTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: SPACING.sm },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, maxWidth: 200 },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  chipTextOn: { color: '#fff' },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  row2: { flexDirection: 'row', gap: 10 },
  flash: { backgroundColor: COLORS.green + '18', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  flashText: { color: COLORS.green, fontWeight: '800', fontSize: FONT.sm, textAlign: 'center' },
  campRow: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, marginBottom: 6, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  campWrap: { marginBottom: SPACING.sm },
  statsRow: { flexDirection: 'row', gap: 8, marginTop: -4, marginBottom: 2, paddingHorizontal: 2 },
  statPill: { flex: 1, alignItems: 'center', paddingVertical: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  statValue: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  statLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 0.8, textTransform: 'uppercase', marginTop: 1 },
  campIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  campTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  statusPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, borderWidth: 1 },
  statusActive: { borderColor: COLORS.green + '55', backgroundColor: COLORS.green + '14' },
  statusPaused: { borderColor: COLORS.surfaceBorder, backgroundColor: COLORS.inputBg },
  statusText: { fontSize: FONT.xs, fontWeight: '800' },
  drawBtn: { marginLeft: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.gold + '22', borderWidth: 1, borderColor: COLORS.gold + '55' },
  drawText: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '800' },
});