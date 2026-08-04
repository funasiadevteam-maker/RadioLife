import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Alert, Modal, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Slider from '@react-native-community/slider';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

const PW_BASE = '/predict-win';

function useCountdown(targetIso: string | null) {
  const [secs, setSecs] = useState(() =>
    targetIso ? Math.max(0, Math.floor((new Date(targetIso).getTime() - Date.now()) / 1000)) : 0
  );
  useEffect(() => {
    if (!targetIso) return;
    const tick = () => setSecs(Math.max(0,
      Math.floor((new Date(targetIso).getTime() - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetIso]);
  return secs;
}

function fmtCountdown(secs: number) {
  if (secs <= 0) return 'Locked';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs - d * 86400) / 3600);
  const m = Math.floor((secs - d * 86400 - h * 3600) / 60);
  const s = secs - d * 86400 - h * 3600 - m * 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

const STATUS_META: Record<string, { label: string; color: string; icon: string }> = {
  submitted: { label: 'Locked in', color: '#3b82f6', icon: 'time-outline' },
  winner: { label: 'Won', color: '#22c55e', icon: 'trophy-outline' },
  loser: { label: 'Not this time', color: '#71717a', icon: 'close-outline' },
  void: { label: 'Withdrawn', color: '#a1a1aa', icon: 'close-outline' },
};

export default function PredictWinScreen() {
  const router = useRouter();
  const [tab, setTab] = useState<'active' | 'picks' | 'wins'>('active');
  const [enterCampaignId, setEnterCampaignId] = useState<string | null>(null);

  const tabs = [
    { key: 'active' as const, label: 'Active' },
    { key: 'picks' as const, label: 'My Picks' },
    { key: 'wins' as const, label: 'Won Rewards' },
  ];

  return (
    <SafeAreaView style={s.screen} testID="predict-win-screen">
      {/* Header */}
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="predict-back-btn">
          <Ionicons name="chevron-back" size={20} color={COLORS.text} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.topLabel}>COMMUNITY PREDICTIONS</Text>
          <Text style={s.topTitle}>Predict & Win</Text>
        </View>
      </View>

      <Text style={s.subtitle}>
        Free community predictions. Make your pick before the lock, and if you{"'"}re right you{"'"}ll win prizes.
      </Text>

      {/* Sub-tabs */}
      <View style={s.tabRow} testID="pw-subnav">
        {tabs.map((t) => (
          <TouchableOpacity
            key={t.key}
            style={[s.tabBtn, tab === t.key && s.tabBtnActive]}
            onPress={() => setTab(t.key)}
            testID={`pw-tab-${t.key}`}
          >
            <Text style={[s.tabBtnText, tab === t.key && s.tabBtnTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'active' && <ActiveTab onPick={setEnterCampaignId} />}
      {tab === 'picks' && <MyPicksTab />}
      {tab === 'wins' && <WonRewardsTab />}

      {enterCampaignId && (
        <EnterModal
          campaignId={enterCampaignId}
          onClose={() => setEnterCampaignId(null)}
          onSubmitted={() => { setEnterCampaignId(null); setTab('picks'); }}
        />
      )}
    </SafeAreaView>
  );
}

// ── Active Tab ──────────────────────────────────────────────
function ActiveTab({ onPick }: { onPick: (id: string) => void }) {
  const [items, setItems] = useState<any[]>([]);
  const [categories, setCategories] = useState<any[]>([]);
  const [catFilter, setCatFilter] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const url = catFilter
        ? `${PW_BASE}/active?limit=30&category_slug=${catFilter}`
        : `${PW_BASE}/active?limit=30`;
      const r = await api.get(url);
      setItems(r.data.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [catFilter]);

  useEffect(() => { load(); }, [load]);

  /* Category chips come from GET /api/predict-win/categories
     (pdx_curator public_router) -> {items:[{slug, display_name, ...}]}. */
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get(`${PW_BASE}/categories`);
        setCategories(r.data.items || []);
      } catch {
        setCategories([]);
      }
    })();
  }, []);

  return (
    <ScrollView contentContainerStyle={s.listContent}>
      {/* Category chips */}
      {categories.length > 0 && (
        <View style={s.chipRow} testID="pw-category-chips">
          <TouchableOpacity
            style={[s.chip, catFilter === '' && s.chipActive]}
            onPress={() => setCatFilter('')}
            testID="pw-cat-chip-all"
          >
            <Text style={[s.chipText, catFilter === '' && s.chipTextActive]}>All</Text>
          </TouchableOpacity>
          {categories.map((c: any) => (
            <TouchableOpacity
              key={c.slug}
              style={[s.chip, catFilter === c.slug && s.chipActive]}
              onPress={() => setCatFilter(catFilter === c.slug ? '' : c.slug)}
              testID={`pw-cat-chip-${c.slug}`}
            >
              <Text style={[s.chipText, catFilter === c.slug && s.chipTextActive]}>
                {c.display_name}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {loading ? (
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 40 }} />
      ) : items.length === 0 ? (
        <View style={s.emptyCard} testID="pw-active-empty">
          <Ionicons name="sparkles-outline" size={28} color={COLORS.textMuted} />
          <Text style={s.emptyText}>
            {catFilter ? 'No predictions in this category.' : 'No live predictions right now.'}
          </Text>
        </View>
      ) : (
        items.map((c: any) => (
          <ActiveCard key={c.campaign_id} campaign={c} onPick={onPick} />
        ))
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function ActiveCard({ campaign, onPick }: { campaign: any; onPick: (id: string) => void }) {
  const remaining = useCountdown(campaign.lock_time);
  const e = campaign.eligibility || {};

  return (
    <View style={s.activeCard} testID={`active-card-${campaign.campaign_id}`}>
      {/* Event type pill */}
      <View style={s.pillRow}>
        <View style={[s.eventPill, { backgroundColor: '#3b82f615' }]}>
          <Text style={[s.eventPillText, { color: '#3b82f6' }]}>
            {(campaign.event_type || '').replace(/_/g, ' ').toUpperCase()}
          </Text>
        </View>
        {campaign.points_reward > 0 && (
          <View style={s.pointsPill} testID={`active-card-points-${campaign.campaign_id}`}>
            <Text style={s.pointsPillText}>+{campaign.points_reward} pts</Text>
          </View>
        )}
      </View>

      <Text style={s.activeTitle}>{campaign.title}</Text>
      {campaign.question_prompt && (
        <Text style={s.activeQuestion}>{campaign.question_prompt}</Text>
      )}

      {/* Prize */}
      {campaign.prize && (
        <View style={s.prizeRow} testID={`active-card-prize-${campaign.campaign_id}`}>
          <Ionicons name="gift-outline" size={14} color={COLORS.green} />
          <Text style={s.prizeText}>
            Prize: {campaign.prize.title}
            {campaign.prize.value_amount
              ? ` (${campaign.prize.value_amount} ${campaign.prize.value_currency || ''})`
              : ''}
          </Text>
        </View>
      )}

      {/* Countdown */}
      <View style={s.countdownRow} testID={`active-card-lock-${campaign.campaign_id}`}>
        <Ionicons name="time-outline" size={14}
          color={remaining > 600 ? COLORS.textMuted : '#f59e0b'} />
        <Text style={[s.countdownText, remaining <= 600 && { color: '#f59e0b' }]}>
          {remaining > 0 ? `Picks close in ${fmtCountdown(remaining)}` : 'Picks are closed'}
        </Text>
      </View>

      {/* Action button */}
      {campaign.user_has_entered ? (
        <View style={s.alreadyBtn} testID={`active-card-already-${campaign.campaign_id}`}>
          <Ionicons name="checkmark" size={14} color={COLORS.textMuted} />
          <Text style={s.alreadyText}>Pick locked in</Text>
        </View>
      ) : e.can_enter ? (
        <TouchableOpacity
          style={s.pickBtn}
          onPress={() => onPick(campaign.campaign_id)}
          testID={`active-card-pick-${campaign.campaign_id}`}
        >
          <Ionicons name="sparkles" size={14} color="#fff" />
          <Text style={s.pickBtnText}>Make your pick</Text>
        </TouchableOpacity>
      ) : (
        <View style={s.alreadyBtn} testID={`active-card-blocked-${campaign.campaign_id}`}>
          <Ionicons name="close" size={14} color={COLORS.textMuted} />
          <Text style={s.alreadyText}>Not eligible</Text>
        </View>
      )}
    </View>
  );
}

// ── My Picks Tab ────────────────────────────────────────────
function MyPicksTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  const filters = [
    { value: 'all', label: 'All' },
    { value: 'submitted', label: 'Locked in' },
    { value: 'winner', label: 'Won' },
    { value: 'loser', label: 'Not this time' },
  ];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`${PW_BASE}/my-picks?status=${filter}&limit=50`);
      setItems(r.data.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView contentContainerStyle={s.listContent}>
      {/* Filter chips */}
      <View style={s.chipRow} testID="picks-filter-row">
        {filters.map((f) => (
          <TouchableOpacity
            key={f.value}
            style={[s.chip, filter === f.value && s.chipActive]}
            onPress={() => setFilter(f.value)}
            testID={`picks-filter-${f.value}`}
          >
            <Text style={[s.chipText, filter === f.value && s.chipTextActive]}>{f.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 40 }} />
      ) : items.length === 0 ? (
        <View style={s.emptyCard} testID="picks-empty">
          <Ionicons name="trophy-outline" size={28} color={COLORS.textMuted} />
          <Text style={s.emptyText}>No picks yet. Head to the Active tab and make your first pick.</Text>
        </View>
      ) : (
        items.map((it: any) => <PickRow key={it.entry.entry_id} item={it} />)
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function PickRow({ item }: { item: any }) {
  const e = item.entry;
  const c = item.campaign;
  const meta = STATUS_META[e.status] || STATUS_META.submitted;

  return (
    <View style={s.pickRow} testID={`pick-row-${e.entry_id}`}>
      <View style={[s.pickIcon, { backgroundColor: `${meta.color}15` }]}>
        <Ionicons name={meta.icon as any} size={16} color={meta.color} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.pickTitle} numberOfLines={1}>{c.title}</Text>
        {c.question_prompt && (
          <Text style={s.pickQuestion} numberOfLines={1}>{c.question_prompt}</Text>
        )}
        <View style={s.pickMetaRow}>
          <Text style={[s.pickStatus, { color: meta.color }]}>{meta.label}</Text>
          {e.confidence && <Text style={s.pickMeta}> · confidence {e.confidence}/10</Text>}
        </View>
      </View>
    </View>
  );
}

// ── Won Rewards Tab ─────────────────────────────────────────
function WonRewardsTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get(`${PW_BASE}/my-wins?limit=50`);
        setItems(r.data.items || []);
      } catch { setItems([]); }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <ScrollView contentContainerStyle={s.listContent}>
      {loading ? (
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 40 }} />
      ) : items.length === 0 ? (
        <View style={s.emptyCard} testID="wins-empty">
          <Ionicons name="ribbon-outline" size={28} color={COLORS.textMuted} />
          <Text style={s.emptyText}>No wins yet. Make picks in the Active tab to start winning!</Text>
        </View>
      ) : (
        items.map((it: any) => <WinCard key={it.entry.entry_id} item={it} />)
      )}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

function WinCard({ item }: { item: any }) {
  const c = item.campaign;
  const prize = item.prize;
  const award = item.award;

  return (
    <View style={s.winCard} testID={`win-card-${item.entry.entry_id}`}>
      <View style={s.winIconWrap}>
        <Ionicons name="trophy" size={22} color="#22c55e" />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.winLabel}>YOU WON</Text>
        {prize && (
          <Text style={s.winTitle}>
            {prize.title}
            {prize.value_amount ? ` (${prize.value_amount} ${prize.value_currency || ''})` : ''}
          </Text>
        )}
        <Text style={s.winFrom} numberOfLines={1}>from {c.title}</Text>
        {award?.delivery_status && (
          <View style={[s.deliveryPill, {
            backgroundColor: award.delivery_status === 'delivered' ? '#dcfce7' : '#fef3c7',
          }]}>
            <Text style={[s.deliveryText, {
              color: award.delivery_status === 'delivered' ? '#16a34a' : '#d97706',
            }]}>
              {award.delivery_status === 'delivered' ? 'Credited'
                : award.delivery_status === 'in_wallet' ? 'In wallet'
                : award.delivery_status || 'Pending'}
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

// ── Enter Modal ─────────────────────────────────────────────
function EnterModal({
  campaignId, onClose, onSubmitted,
}: {
  campaignId: string;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [detail, setDetail] = useState<any>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [confidence, setConfidence] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get(`${PW_BASE}/campaigns/${campaignId}`);
        setDetail(r.data);
      } catch (e: any) {
        Alert.alert('Error', e?.response?.data?.detail || 'Failed to load campaign');
        onClose();
      }
    })();
  }, [campaignId, onClose]);

  const submit = async () => {
    if (!picked) { Alert.alert('Pick an option first'); return; }
    setSubmitting(true);
    try {
      await api.post(`${PW_BASE}/campaigns/${campaignId}/enter`, {
        selected_option_id: picked,
        confidence,
        // Must be one of the backend's ALLOWED_ENTRY_SOURCES
        // {app, qr, tv, lobby, deep_link}. Sending 'mobile_app' here made
        // every pick fail with 400 invalid_source.
        source_context: 'app',
      });
      Alert.alert('Success', 'Pick locked in!');
      onSubmitted();
    } catch (e: any) {
      const code = e?.response?.data?.detail?.code;
      if (code === 'already_entered') Alert.alert('Already Entered', 'You already submitted a pick.');
      else if (code === 'entries_closed') Alert.alert('Closed', 'Picks are closed.');
      else Alert.alert('Error', e?.response?.data?.detail?.message || e.message || 'Submit failed');
    } finally { setSubmitting(false); }
  };

  const c = detail?.campaign;
  const prize = detail?.prizes?.[0];
  const dist = detail?.option_pick_distribution;

  return (
    <Modal visible transparent animationType="slide" testID="enter-modal">
      <View style={s.modalBackdrop}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={s.modalCard}>
          {!detail ? (
            <ActivityIndicator size="large" color={COLORS.primary} style={{ padding: 40 }} />
          ) : (
            <ScrollView showsVerticalScrollIndicator={false}>
              {/* Header */}
              <View style={s.modalHeader}>
                <View style={{ flex: 1 }}>
                  <Text style={s.modalEventType}>
                    {(c.event_type || '').replace(/_/g, ' ').toUpperCase()}
                  </Text>
                  <Text style={s.modalTitle}>{c.title}</Text>
                </View>
                <TouchableOpacity onPress={onClose} testID="enter-modal-close">
                  <Ionicons name="close" size={22} color={COLORS.textDim} />
                </TouchableOpacity>
              </View>

              {/* Question */}
              <Text style={s.modalQuestion}>{c.question?.prompt}</Text>

              {/* Options */}
              <View style={s.modalOptions} testID="enter-modal-options">
                {(c.question?.answer_options || []).map((o: any) => {
                  const isSel = picked === o.option_id;
                  const distRow = (dist || []).find((d: any) => d.option_id === o.option_id);
                  return (
                    <TouchableOpacity
                      key={o.option_id}
                      style={[s.modalOption, isSel && s.modalOptionSel]}
                      onPress={() => setPicked(o.option_id)}
                      testID={`enter-option-${o.option_id}`}
                    >
                      <View style={[s.radio, isSel && s.radioSel]}>
                        {isSel && <View style={s.radioDot} />}
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.modalOptionLabel}>{o.label}</Text>
                        {distRow && (
                          <Text style={s.distText}>
                            Community: {distRow.pct}% ({distRow.count})
                          </Text>
                        )}
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Prize */}
              {prize && (
                <View style={s.modalPrize} testID="enter-modal-prize">
                  <Ionicons name="gift-outline" size={14} color={COLORS.green} />
                  <Text style={s.modalPrizeText}>
                    Prize: {prize.title}
                    {prize.value_amount ? ` (${prize.value_amount} ${prize.value_currency || ''})` : ''}
                  </Text>
                </View>
              )}

              {/* Confidence slider */}
              <View style={s.confidenceSection}>
                <Text style={s.confidenceLabel}>Confidence (1–10)</Text>
                <Slider
                  style={{ width: '100%', height: 40 }}
                  minimumValue={1}
                  maximumValue={10}
                  step={1}
                  value={confidence}
                  onValueChange={setConfidence}
                  minimumTrackTintColor={COLORS.primary}
                  maximumTrackTintColor={COLORS.inputBorder}
                  thumbTintColor={COLORS.primary}
                  testID="enter-modal-confidence"
                />
                <View style={s.confidenceRow}>
                  <Text style={s.confidenceEnd}>low</Text>
                  <Text style={s.confidenceVal}>{confidence}</Text>
                  <Text style={s.confidenceEnd}>high</Text>
                </View>
              </View>

              {/* Buttons */}
              <View style={s.modalActions}>
                <TouchableOpacity style={s.cancelBtn} onPress={onClose} testID="enter-modal-cancel">
                  <Text style={s.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.submitBtn, (!picked || submitting) && { opacity: 0.5 }]}
                  onPress={submit}
                  disabled={!picked || submitting}
                  testID="enter-modal-submit"
                >
                  {submitting ? (
                    <ActivityIndicator size="small" color="#fff" />
                  ) : (
                    <>
                      <Ionicons name="sparkles" size={14} color="#fff" />
                      <Text style={s.submitBtnText}>Lock in my pick</Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

// ── Styles ──────────────────────────────────────────────────
const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  topBar: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: SPACING.lg, paddingTop: SPACING.md, paddingBottom: SPACING.sm,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  topLabel: { fontSize: 9, fontWeight: '700', color: COLORS.textMuted, letterSpacing: 1 },
  topTitle: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text },
  subtitle: {
    fontSize: FONT.sm, color: COLORS.textDim, paddingHorizontal: SPACING.lg,
    marginBottom: SPACING.md, lineHeight: 18,
  },

  // Tabs
  tabRow: {
    flexDirection: 'row', paddingHorizontal: SPACING.lg,
    borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder, marginBottom: 4,
  },
  tabBtn: { paddingVertical: 10, paddingHorizontal: 14, borderBottomWidth: 2, borderBottomColor: 'transparent' },
  tabBtnActive: { borderBottomColor: COLORS.primary },
  tabBtnText: { fontSize: FONT.sm, fontWeight: '600', color: COLORS.textMuted },
  tabBtnTextActive: { color: COLORS.primary, fontWeight: '700' },

  // Shared
  listContent: { padding: SPACING.lg },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: SPACING.md },
  chip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card,
  },
  chipActive: { borderColor: COLORS.primary, backgroundColor: '#F26B2A10' },
  chipText: { fontSize: 11, fontWeight: '600', color: COLORS.textMuted },
  chipTextActive: { color: COLORS.primary, fontWeight: '700' },
  emptyCard: {
    padding: SPACING.xl, alignItems: 'center',
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  emptyText: { fontSize: FONT.sm, color: COLORS.textMuted, textAlign: 'center', marginTop: 8 },

  // Active cards
  activeCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.md, marginBottom: 10,
  },
  pillRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap' },
  eventPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  eventPillText: { fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  pointsPill: {
    marginLeft: 'auto',
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full,
    backgroundColor: COLORS.primary,
  },
  pointsPillText: { color: '#fff', fontSize: 10, fontWeight: '700' },
  activeTitle: { fontSize: FONT.md, fontWeight: '800', color: COLORS.text, marginBottom: 4 },
  activeQuestion: { fontSize: FONT.sm, color: COLORS.textDim, marginBottom: 8 },
  prizeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#dcfce7', borderRadius: 6, padding: 8, marginBottom: 8,
  },
  prizeText: { fontSize: FONT.sm, color: '#16a34a', fontWeight: '600', flex: 1 },
  countdownRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 },
  countdownText: { fontSize: FONT.sm, color: COLORS.textMuted },
  pickBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: COLORS.primary, borderRadius: 8,
    paddingVertical: 10,
  },
  pickBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '700' },
  alreadyBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: 8,
    paddingVertical: 10, opacity: 0.6,
  },
  alreadyText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600' },

  // Pick rows
  pickRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    backgroundColor: COLORS.card, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.md, marginBottom: 8,
  },
  pickIcon: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  pickTitle: { fontSize: FONT.sm, fontWeight: '700', color: COLORS.text },
  pickQuestion: { fontSize: 11, color: COLORS.textMuted, marginTop: 2 },
  pickMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  pickStatus: { fontSize: 10, fontWeight: '700', letterSpacing: 0.4, textTransform: 'uppercase' },
  pickMeta: { fontSize: 10, color: COLORS.textMuted },

  // Win cards
  winCard: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 12,
    backgroundColor: '#f0fdf4', borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: '#bbf7d0',
    padding: SPACING.md, marginBottom: 10,
  },
  winIconWrap: {
    width: 48, height: 48, borderRadius: 12,
    backgroundColor: '#dcfce7',
    alignItems: 'center', justifyContent: 'center',
  },
  winLabel: { fontSize: 9, fontWeight: '700', color: '#16a34a', letterSpacing: 0.6 },
  winTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text, marginTop: 2 },
  winFrom: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 4 },
  deliveryPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full, marginTop: 6, alignSelf: 'flex-start' },
  deliveryText: { fontSize: 9, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },

  // Modal
  modalBackdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: COLORS.card, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: SPACING.lg, maxHeight: '90%',
  },
  modalHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 14 },
  modalEventType: { fontSize: 9, fontWeight: '700', color: COLORS.textMuted, letterSpacing: 0.5 },
  modalTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, marginTop: 2 },
  modalQuestion: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text, marginBottom: 14 },
  modalOptions: { gap: 8, marginBottom: 14 },
  modalOption: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    borderRadius: 8, padding: 12, backgroundColor: COLORS.bg,
  },
  modalOptionSel: { borderColor: COLORS.primary, backgroundColor: '#F26B2A08' },
  radio: {
    width: 20, height: 20, borderRadius: 10, borderWidth: 2,
    borderColor: COLORS.inputBorder, alignItems: 'center', justifyContent: 'center',
  },
  radioSel: { borderColor: COLORS.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  modalOptionLabel: { fontSize: FONT.sm, fontWeight: '600', color: COLORS.text },
  distText: { fontSize: 10, color: COLORS.textMuted, marginTop: 2 },
  modalPrize: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#dcfce7', borderRadius: 6, padding: 10, marginBottom: 14,
  },
  modalPrizeText: { fontSize: FONT.sm, color: '#16a34a', fontWeight: '600', flex: 1 },
  confidenceSection: { marginBottom: 14 },
  confidenceLabel: { fontSize: 11, fontWeight: '600', color: COLORS.textDim, marginBottom: 4 },
  confidenceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  confidenceEnd: { fontSize: 11, color: COLORS.textMuted },
  confidenceVal: { fontSize: FONT.md, fontWeight: '800', color: COLORS.primary },
  modalActions: { flexDirection: 'row', gap: 10, marginTop: 8 },
  cancelBtn: {
    flex: 1, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: 8,
    paddingVertical: 14, alignItems: 'center',
  },
  cancelBtnText: { color: COLORS.textDim, fontWeight: '600', fontSize: FONT.md },
  submitBtn: {
    flex: 2, backgroundColor: COLORS.primary, borderRadius: 8,
    paddingVertical: 14, alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row', gap: 6,
  },
  submitBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
});
