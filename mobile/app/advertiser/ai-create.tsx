import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, Alert, ActivityIndicator, KeyboardAvoidingView, Platform, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const TONES = ['friendly', 'energetic', 'luxurious', 'chill', 'urgent'];
const STAGES_ORDER = ['script', 'safety', 'voice', 'image', 'save'];
const STAGE_LABELS: Record<string, string> = {
  script: 'Writing script',
  safety: 'Safety check',
  voice: 'Recording voice',
  image: 'Designing visual',
  save: 'Saving creative',
};

export default function AIAdCreator() {
  const router = useRouter();
  const [advId, setAdvId] = useState('');
  const [form, setForm] = useState({
    business: '', description: '', tone: 'friendly',
    audio_length_sec: 15, voice_id: 'maya',
    brand_color: '#F59E0B', keywords: '',
    include_image: true,
  });
  const [stage, setStage] = useState<string | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/advertiser/me');
        const items = r.data?.items || [];
        if (items.length) {
          setAdvId(items[0].advertiser_id);
          if (items[0].name) setForm((p) => ({ ...p, business: items[0].name }));
        }
      } catch {}
    })();
  }, []);

  const generate = async () => {
    if (!advId) { Alert.alert('Error', 'No advertiser selected'); return; }
    if (!form.business?.trim() || !form.description?.trim()) {
      Alert.alert('Required', 'Business name and description are required'); return;
    }
    setPreview(null); setErrMsg(null);
    setStage('script');
    // Cosmetic progress while API runs
    const lapse = (s: string, ms: number) =>
      new Promise<void>((r) => setTimeout(() => { setStage(s); r(); }, ms));
    lapse('safety', 600).then(() => lapse('voice', 1200)).then(() => lapse('image', 1800));

    try {
      const body = {
        ...form,
        keywords: form.keywords
          ? form.keywords.split(',').map((x: string) => x.trim()).filter(Boolean).slice(0, 3)
          : null,
      };
      const r = await api.post(`/advertiser/${advId}/ai/generate`, body);
      setPreview(r.data);
      setStage('done');
    } catch (e: any) {
      setStage('error');
      setErrMsg(e?.response?.data?.detail || 'Generation failed');
    }
  };

  const save = async () => {
    if (!preview) return;
    setSaving(true);
    try {
      await api.post(`/advertiser/${advId}/ai/save`, {
        creative_id: preview.creative_id,
        title: form.business + ' · AI',
        script: preview.script,
        audio_url: preview.audio_url,
        audio_path: preview.audio_path,
        duration_sec: preview.duration_sec,
        image_url: preview.image_url,
        brand_safety_check: preview.brand_safety_check,
        vast_xml: preview.vast_xml,
        voice_id: preview.voice_id,
        tone: preview.tone,
        audio_length_sec: preview.audio_length_sec,
        audio_source: preview.audio_source,
      });
      Alert.alert('Saved', 'Creative saved to your library');
      router.back();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Save failed');
    } finally { setSaving(false); }
  };

  const verdict = preview?.brand_safety_check?.verdict;
  const badgeColor = verdict === 'approved' ? COLORS.green : verdict === 'rejected' ? COLORS.red : COLORS.orange;
  const badgeText = verdict === 'approved' ? 'Approved' : verdict === 'rejected' ? 'Rejected' : 'Needs review';
  const totalMs = preview?.total_latency_ms || 0;
  const latencySec = (totalMs / 1000).toFixed(1);
  const isSlow = totalMs > 20000;
  const isRunning = stage && stage !== 'done' && stage !== 'error';

  return (
    <SafeAreaView style={common.screen} testID="ai-creator">
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        {/* Header */}
        <View style={s.header}>
          <View style={common.row}>
            <Ionicons name="sparkles" size={20} color={COLORS.orange} />
            <Text style={s.headerTitle}>AI Ad Creator</Text>
          </View>
          <TouchableOpacity onPress={() => router.back()} testID="ai-close">
            <Ionicons name="close" size={20} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          {/* Input Form */}
          <View testID="ai-form">
            <Text style={common.label}>BUSINESS NAME</Text>
            <TextInput style={common.input} placeholderTextColor={COLORS.textMuted}
              value={form.business} onChangeText={(t) => setForm({ ...form, business: t })}
              testID="ai-business" />

            <Text style={[common.label, { marginTop: SPACING.md }]}>OFFER / PRODUCT</Text>
            <TextInput style={[common.input, { height: 80, textAlignVertical: 'top' }]}
              placeholderTextColor={COLORS.textMuted} multiline
              placeholder="e.g. Free dessert with any lunch combo, weekdays 12-2pm"
              value={form.description}
              onChangeText={(t) => setForm({ ...form, description: t })}
              testID="ai-description" />

            <View style={s.rowTwo}>
              <View style={{ flex: 1 }}>
                <Text style={common.label}>TONE</Text>
                <View style={s.chipsRow}>
                  {TONES.map((t) => (
                    <TouchableOpacity key={t}
                      style={[s.chip, form.tone === t && s.chipActive]}
                      onPress={() => setForm({ ...form, tone: t })}
                      testID={`ai-tone-${t}`}>
                      <Text style={[s.chipText, form.tone === t && s.chipTextActive]}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>

            <View style={[common.row, { marginTop: SPACING.md, justifyContent: 'space-between' }]}>
              <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>
                Skip image (faster · cuts ~7s)
              </Text>
              <Switch
                value={!form.include_image}
                onValueChange={(v) => setForm({ ...form, include_image: !v })}
                trackColor={{ false: COLORS.surfaceBorder, true: COLORS.orange }}
                testID="ai-skip-image"
              />
            </View>

            <Text style={[common.label, { marginTop: SPACING.md }]}>KEYWORDS (OPTIONAL, COMMA-SEP)</Text>
            <TextInput style={common.input} placeholderTextColor={COLORS.textMuted}
              value={form.keywords}
              onChangeText={(t) => setForm({ ...form, keywords: t })}
              testID="ai-keywords" />

            <TouchableOpacity
              style={[s.generateBtn, isRunning && { opacity: 0.6 }]}
              onPress={generate}
              disabled={!!isRunning}
              testID="ai-generate-btn"
            >
              {isRunning ? (
                <ActivityIndicator size="small" color={COLORS.bg} />
              ) : (
                <Ionicons name="sparkles" size={16} color={COLORS.bg} />
              )}
              <Text style={s.generateBtnText}>
                {isRunning ? 'Cooking your ad…' : 'Generate ad'}
              </Text>
            </TouchableOpacity>
          </View>

          {/* Progress */}
          {isRunning && (
            <View style={[common.card, { marginTop: SPACING.lg }]} testID="ai-progress">
              {STAGES_ORDER.slice(0, 4).map((name) => {
                const idx = STAGES_ORDER.indexOf(name);
                const curIdx = STAGES_ORDER.indexOf(stage!);
                const done = idx < curIdx;
                const active = idx === curIdx;
                return (
                  <View key={name} style={[common.row, { paddingVertical: 6 }]} testID={`ai-step-${name}`}>
                    {done ? (
                      <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
                    ) : active ? (
                      <ActivityIndicator size="small" color={COLORS.orange} />
                    ) : (
                      <View style={{ width: 16 }} />
                    )}
                    <Text style={{
                      marginLeft: 8, fontSize: FONT.sm,
                      color: done ? COLORS.green : active ? COLORS.orange : COLORS.textDim,
                    }}>
                      {STAGE_LABELS[name] || name}
                    </Text>
                  </View>
                );
              })}
            </View>
          )}

          {/* Error */}
          {stage === 'error' && (
            <View style={[common.card, { marginTop: SPACING.lg, borderColor: COLORS.red }]} testID="ai-error">
              <Ionicons name="alert-circle" size={16} color={COLORS.red} />
              <Text style={{ color: COLORS.red, fontSize: FONT.sm, marginLeft: 8 }}>{errMsg}</Text>
            </View>
          )}

          {/* Preview */}
          {preview && stage === 'done' && (
            <View style={{ marginTop: SPACING.lg }} testID="ai-preview">
              {/* Image or placeholder */}
              {preview.image_url ? (
                <View style={s.imagePreview} testID="ai-image">
                  <Text style={{ color: '#fff', fontSize: FONT.sm }}>Image preview available at web</Text>
                </View>
              ) : (
                <View style={[s.imagePreview, { backgroundColor: form.brand_color }]} testID="ai-image-skipped">
                  <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: FONT.xs, textTransform: 'uppercase', letterSpacing: 2 }}>Audio-only ad</Text>
                  <Text style={{ color: '#fff', fontSize: FONT.xxl, fontWeight: '800', marginTop: 4 }}>
                    {form.business || 'Your brand'}
                  </Text>
                </View>
              )}

              {/* Script */}
              <View style={[common.card, { marginTop: SPACING.sm }]}>
                <Text style={common.label}>SCRIPT</Text>
                <Text style={{ color: '#fff', fontSize: FONT.sm, lineHeight: 20 }} testID="ai-transcript">
                  {preview.script}
                </Text>
                <Text style={{ color: COLORS.textDim, fontSize: FONT.xs, marginTop: 6 }}>
                  Voice: {preview.voice_label} ({preview.audio_source}) · {Math.round(preview.duration_sec)}s
                </Text>
              </View>

              {/* Safety badge */}
              <View style={[common.card, { marginTop: SPACING.sm, borderColor: badgeColor }]} testID="ai-safety">
                <View style={common.row}>
                  <Ionicons name="shield-checkmark" size={16} color={badgeColor} />
                  <Text style={{ color: badgeColor, fontSize: FONT.sm, fontWeight: '700', marginLeft: 6 }}>
                    Safety: {badgeText}
                  </Text>
                </View>
              </View>

              {/* Latency chip */}
              <View style={[common.card, { marginTop: SPACING.sm, borderColor: isSlow ? COLORS.orange : COLORS.cardBorder }]}
                testID="ai-latency-chip">
                <Text style={{ color: isSlow ? COLORS.orange : COLORS.textDim, fontSize: FONT.sm }}>
                  Took <Text style={{ color: '#fff', fontWeight: '700' }}>{latencySec}s</Text>
                  {isSlow ? ' — try Skip image to cut time in half.' : ''}
                </Text>
              </View>

              {/* Actions */}
              <View style={[s.actionRow, { marginTop: SPACING.md }]}>
                <TouchableOpacity style={[common.btnGhost, { flex: 1 }]} onPress={generate} testID="ai-regenerate">
                  <Ionicons name="refresh" size={14} color={COLORS.textDim} />
                  <Text style={common.btnGhostText}>Regenerate</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.saveBtn, { flex: 1 }, saving && { opacity: 0.5 }]}
                  onPress={save} disabled={saving} testID="ai-save"
                >
                  {saving ? <ActivityIndicator size="small" color={COLORS.bg} /> : (
                    <Text style={s.saveBtnText}>Save as creative</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder,
  },
  headerTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '700', marginLeft: SPACING.sm },
  scroll: { padding: SPACING.lg, paddingBottom: 100 },
  rowTwo: { marginTop: SPACING.md },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm, marginTop: SPACING.xs },
  chip: {
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  chipActive: { borderColor: COLORS.orange, backgroundColor: 'rgba(251,183,86,0.08)' },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  chipTextActive: { color: COLORS.orange },
  generateBtn: {
    marginTop: SPACING.lg, backgroundColor: COLORS.orange, borderRadius: RADIUS.lg,
    paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  generateBtnText: { color: COLORS.bg, fontWeight: '800', fontSize: FONT.md },
  imagePreview: {
    width: '100%', aspectRatio: 1, borderRadius: RADIUS.lg,
    backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center',
  },
  actionRow: { flexDirection: 'row', gap: SPACING.sm },
  saveBtn: {
    backgroundColor: COLORS.orange, borderRadius: RADIUS.lg,
    paddingVertical: 14, alignItems: 'center', justifyContent: 'center',
  },
  saveBtnText: { color: COLORS.bg, fontWeight: '800', fontSize: FONT.md },
});
