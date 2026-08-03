import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, ActivityIndicator,
  ScrollView, SafeAreaView, Switch, Alert, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/contexts/AuthContext';
import api, { BACKEND } from '../src/api/client';
import { COLORS, SPACING, RADIUS, FONT } from '../src/constants/theme';

let createAudioPlayer: any;
try { createAudioPlayer = require('expo-audio').createAudioPlayer; } catch {}

const LANGUAGES = [
  { id: 'hindi', label: 'Hindi' }, { id: 'punjabi', label: 'Punjabi' },
  { id: 'english', label: 'English' }, { id: 'bollywood', label: 'Bollywood' },
  { id: 'tamil', label: 'Tamil' }, { id: 'arabic', label: 'Arabic' },
  { id: 'malayalam', label: 'Malayalam' }, { id: 'telugu', label: 'Telugu' },
];
const GENRES = ['bollywood','hip_hop','pop','electronic','retro','indie','sufi','ghazal','devotional','rock','punjabi_pop','arabic_pop'];
const ERAS = [{ id: '80s', label: '80s' }, { id: '90s', label: '90s' }, { id: '2000s', label: '2000s' }, { id: '2010s', label: '2010s' }, { id: '2020s', label: '2020s' }];
const MOODS = ['energetic','chill','romantic','party','uplifting','melancholy','devotional','nostalgic'];
const ACTIVITIES = [
  { id: 'morning_commute', label: 'Morning commute' }, { id: 'workday_focus', label: 'Workday focus' },
  { id: 'lunch_break', label: 'Lunch break' }, { id: 'evening_commute', label: 'Evening commute' },
  { id: 'dinner', label: 'Dinner' }, { id: 'late_night_drive', label: 'Late-night drive' },
  { id: 'workout', label: 'Workout' }, { id: 'party', label: 'Party' },
  { id: 'devotional_time', label: 'Devotional time' },
];
const DUBAI_AREAS = ['Karama','Bur Dubai','Deira','Al Nahda','JLT','Business Bay','Downtown','Marina','Sharjah','Other'];
const DFW_AREAS = ['Frisco','Plano','Irving','Carrollton','Richardson','Dallas','Fort Worth','Arlington','Garland','Allen','McKinney','Lewisville','Other'];
const MARKETS = [
  { id: 'dubai', label: 'Dubai', blurb: 'UAE — Karama, JLT, Marina' },
  { id: 'dfw', label: 'DFW', blurb: 'Dallas–Fort Worth — Frisco, Plano' },
];
const VOICES = [
  { id: 'veer_dubai', name: 'Veer', blurb: 'Late-night charm, smooth host.', fits: 'CHILL · MEDIUM' },
  { id: 'monika_dubai', name: 'Monika', blurb: 'Hindi-native, warm natural.', fits: 'CHILL · MEDIUM' },
  { id: 'dj_dubai', name: 'DJ Charlie', blurb: 'Club energy, party MC.', fits: 'HIGH · PARTY' },
  { id: 'dj_riya_dubai', name: 'DJ Riya', blurb: 'Female club MC.', fits: 'HIGH · PARTY' },
  { id: 'pandit_anand', name: 'Pandit Anand', blurb: 'Devotional broadcaster.', fits: 'CHILL' },
  { id: 'gurpreet_bhaji', name: 'Gurpreet Bhaji', blurb: 'Punjabi specialist.', fits: 'MED · HIGH' },
  { id: 'aarti_morning', name: 'Aarti', blurb: 'Bubbly morning-show.', fits: 'MEDIUM · HIGH' },
  { id: 'kishore_retro', name: 'Kishore Da', blurb: 'Classic retro nostalgia.', fits: 'CHILL · MED' },
  { id: 'simran_punjabi', name: 'Simran', blurb: 'Punjabi female co-host.', fits: 'MED · HIGH' },
  { id: 'auto', name: 'Auto', blurb: 'Let BigFM pick by vibe.', fits: 'SMART ROUTING' },
];
const STEP_TITLES = ['Welcome','Languages','Genres','Eras','Moods','When','Market','Artists','Your RJ','Content filter','Done'];
const nice = (g: string) => g.replace(/_/g, ' ');

function ChipGrid({ options, selected, onToggle, testID }: any) {
  return (
    <View style={cs.grid} testID={testID}>
      {options.map((o: any) => {
        const id = typeof o === 'string' ? o : o.id;
        const label = typeof o === 'string' ? nice(o) : o.label;
        const on = selected.includes(id);
        return (
          <TouchableOpacity key={id} style={[cs.chip, on && cs.chipOn]} onPress={() => onToggle(id)} testID={`${testID}-${id}`}>
            {on && <Ionicons name="checkmark" size={14} color="#fff" />}
            <Text style={[cs.chipText, on && cs.chipTextOn]}>{label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

export default function Onboarding() {
  const { user, refresh, setUser } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [pv, setPv] = useState({
    languages: [] as string[], genres: [] as string[], eras: [] as string[],
    moods: [] as string[], activities: [] as string[], favorite_artists: [] as string[],
    city: 'Dubai', home_area: null as string | null, host_personality: 'auto',
    explicit_ok: false, market: 'dubai',
  });
  const [artistDraft, setArtistDraft] = useState('');
  const playerRef = useRef<any>(null);
  const previewPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [previewing, setPreviewing] = useState<string | null>(null);

  useEffect(() => {
    if (user?.preference_vector) {
      const v = user.preference_vector;
      setPv(p => ({ ...p, ...v, favorite_artists: v.favorite_artists || [] }));
    }
  }, [user]);

  useEffect(() => {
    return () => {
      if (previewPollRef.current) clearInterval(previewPollRef.current);
      try { playerRef.current?.release?.(); } catch {}
    };
  }, []);

  const toggle = (key: string) => (id: string) => {
    setPv(p => {
      const arr = (p as any)[key] || [];
      return { ...p, [key]: arr.includes(id) ? arr.filter((x: string) => x !== id) : [...arr, id] };
    });
  };

  const stopPreview = () => {
    if (previewPollRef.current) { clearInterval(previewPollRef.current); previewPollRef.current = null; }
    try { playerRef.current?.release?.(); } catch {}
    playerRef.current = null;
    setPreviewing(null);
  };

  const playPreview = async (voice_id: string) => {
    if (previewing === voice_id) { stopPreview(); return; }
    stopPreview();
    if (!createAudioPlayer) { Alert.alert('Error', 'Audio not available'); return; }
    try {
      const player = createAudioPlayer(`${BACKEND}/api/voices/preview/${voice_id}`);
      playerRef.current = player;
      setPreviewing(voice_id);
      player.play();
      previewPollRef.current = setInterval(() => {
        try {
          const p = playerRef.current;
          if (!p) { clearInterval(previewPollRef.current!); previewPollRef.current = null; return; }
          if (p.duration > 0 && !p.playing && p.currentTime > 0.1) {
            clearInterval(previewPollRef.current!);
            previewPollRef.current = null;
            setPreviewing(null);
          }
        } catch {}
      }, 500);
    } catch {
      Alert.alert('Error', 'Could not load voice preview');
      setPreviewing(null);
    }
  };

  const stepValid = useMemo(() => {
    switch (step) {
      case 0: return true;
      case 1: return pv.languages.length >= 1;
      case 2: return pv.genres.length >= 2;
      case 3: return pv.eras.length >= 1;
      case 4: return pv.moods.length >= 2;
      case 5: return pv.activities.length >= 1;
      case 6: return !!pv.home_area;
      case 7: return true;
      case 8: return !!pv.host_personality;
      case 9: return true;
      case 10: return true;
      default: return true;
    }
  }, [step, pv]);

  const next = async () => {
    if (!stepValid) { Alert.alert('', 'Pick at least the minimum to continue'); return; }
    if (step < 10) { setStep(s => s + 1); return; }
    setSaving(true); stopPreview();
    try {
      const r = await api.post('/users/preferences', pv);
      setUser(r.data);
      Alert.alert('All set!', `Sab set, ${r.data.name}!`);
      router.replace('/(tabs)/radio');
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not save preferences');
      await refresh();
    } finally { setSaving(false); }
  };

  const back = () => { if (step > 0) setStep(s => s - 1); };
  const addArtist = () => {
    const t = artistDraft.trim();
    if (!t) return;
    if (pv.favorite_artists.length >= 10) { Alert.alert('', 'Up to 10'); return; }
    setPv(p => ({ ...p, favorite_artists: [...p.favorite_artists, t] }));
    setArtistDraft('');
  };

  const progress = (step / 10) * 100;

  return (
    <SafeAreaView style={s.screen}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        {/* Header */}
        <View style={s.header}>
          <View style={s.brandRow}>
            <View style={s.dot} /><Text style={s.brandName}>BigFM <Text style={{ color: COLORS.secondary }}>Dubai</Text></Text>
          </View>
          <Text style={s.stepLabel} testID="wizard-step">STEP {step + 1} / 11 · {STEP_TITLES[step].toUpperCase()}</Text>
        </View>
        <View style={s.progressTrack}><View style={[s.progressFill, { width: `${progress}%` }]} /></View>

        <ScrollView contentContainerStyle={s.main} keyboardShouldPersistTaps="handled">
          {step === 0 && (
            <View testID="step-welcome">
              <Text style={s.title}>Namaste, Dubai.</Text>
              <Text style={s.lede}>Kuch sawal hain — phir non-stop music chalega. 30 seconds, max.</Text>
              <View style={s.bulletRow}><Text style={s.bulletNum}>01</Text><Text style={s.bulletText}>Pick languages, genres & moods</Text></View>
              <View style={s.bulletRow}><Text style={s.bulletNum}>02</Text><Text style={s.bulletText}>Pick your RJ (or let us choose)</Text></View>
              <View style={s.bulletRow}><Text style={s.bulletNum}>03</Text><Text style={s.bulletText}>Press ON AIR. Music chalu.</Text></View>
            </View>
          )}
          {step === 1 && (<View><Text style={s.title}>Aap kya sunte ho?</Text><Text style={s.lede}>Pick one or more languages (min 1).</Text><ChipGrid options={LANGUAGES} selected={pv.languages} onToggle={toggle('languages')} testID="step-languages" /></View>)}
          {step === 2 && (<View><Text style={s.title}>Which genres hit the spot?</Text><Text style={s.lede}>Pick at least 2.</Text><ChipGrid options={GENRES} selected={pv.genres} onToggle={toggle('genres')} testID="step-genres" /></View>)}
          {step === 3 && (<View><Text style={s.title}>Which era is your jam?</Text><Text style={s.lede}>Pick at least 1.</Text><ChipGrid options={ERAS} selected={pv.eras} onToggle={toggle('eras')} testID="step-eras" /></View>)}
          {step === 4 && (<View><Text style={s.title}>What mood do you want?</Text><Text style={s.lede}>Pick at least 2.</Text><ChipGrid options={MOODS} selected={pv.moods} onToggle={toggle('moods')} testID="step-moods" /></View>)}
          {step === 5 && (<View><Text style={s.title}>When do you tune in?</Text><Text style={s.lede}>Pick at least 1.</Text><ChipGrid options={ACTIVITIES} selected={pv.activities} onToggle={toggle('activities')} testID="step-activities" /></View>)}
          {step === 6 && (
            <View>
              <Text style={s.title}>Which BigFM are you on?</Text>
              <Text style={s.lede}>Pick your market — Dubai or DFW.</Text>
              <View style={cs.grid} testID="step-market-grid">
                {MARKETS.map(m => (
                  <TouchableOpacity key={m.id} style={[cs.areaCard, pv.market === m.id && cs.areaCardOn]} onPress={() => setPv(p => ({ ...p, market: m.id, city: m.id === 'dubai' ? 'Dubai' : 'DFW', home_area: null }))} testID={`market-card-${m.id}`}>
                    {pv.market === m.id && <Ionicons name="checkmark" size={14} color="#fff" />}
                    <Text style={cs.areaLabel}>{m.label}</Text>
                    <Text style={cs.areaBlurb}>{m.blurb}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={[s.lede, { marginTop: 20 }]}>And which area?</Text>
              <View style={cs.grid} testID="step-area-grid">
                {(pv.market === 'dfw' ? DFW_AREAS : DUBAI_AREAS).map(a => (
                  <TouchableOpacity key={a} style={[cs.areaCard, pv.home_area === a && cs.areaCardOn]} onPress={() => setPv(p => ({ ...p, home_area: a }))} testID={`area-card-${a.toLowerCase().replace(/ /g, '-')}`}>
                    {pv.home_area === a && <Ionicons name="checkmark" size={14} color="#fff" />}
                    <Text style={cs.areaLabel}>{a}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
          {step === 7 && (
            <View>
              <Text style={s.title}>Favorite artists?</Text>
              <Text style={s.lede}>Up to 10. Optional hints for personalization.</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
                <TextInput style={[s.input, { flex: 1 }]} placeholder="Type an artist" placeholderTextColor={COLORS.textMuted} value={artistDraft} onChangeText={setArtistDraft} onSubmitEditing={addArtist} testID="artist-input" />
                <TouchableOpacity style={s.addBtn} onPress={addArtist} testID="artist-add-btn"><Ionicons name="add" size={18} color="#fff" /><Text style={{ color: '#fff', fontWeight: '700' }}>ADD</Text></TouchableOpacity>
              </View>
              <View style={cs.grid} testID="artist-chips">
                {pv.favorite_artists.map(a => (
                  <View key={a} style={cs.artistChip} testID={`artist-chip-${a}`}>
                    <Text style={{ color: '#fff', fontSize: 13 }}>{a}</Text>
                    <TouchableOpacity onPress={() => setPv(p => ({ ...p, favorite_artists: p.favorite_artists.filter(x => x !== a) }))}><Ionicons name="close" size={14} color={COLORS.textDim} /></TouchableOpacity>
                  </View>
                ))}
                {pv.favorite_artists.length === 0 && <Text style={{ color: COLORS.textMuted, fontSize: 13 }}>Nothing yet — totally optional.</Text>}
              </View>
            </View>
          )}
          {step === 8 && (
            <View>
              <Text style={s.title}>Pick your RJ</Text>
              <Text style={s.lede}>Tap preview to hear each voice.</Text>
              {VOICES.map(v => (
                <TouchableOpacity key={v.id} style={[cs.voiceCard, pv.host_personality === v.id && cs.voiceCardOn]} onPress={() => setPv(p => ({ ...p, host_personality: v.id }))} testID={`voice-card-${v.id}`}>
                  <View style={cs.voiceAvatar}><Text style={cs.voiceInitial}>{v.name[0]}</Text></View>
                  <View style={{ flex: 1 }}>
                    <Text style={cs.voiceName}>{v.name}</Text>
                    <Text style={cs.voiceBlurb}>{v.blurb}</Text>
                    <Text style={cs.voiceFits}>{v.fits}</Text>
                  </View>
                  {v.id !== 'auto' && (
                    <TouchableOpacity style={cs.previewBtn} onPress={() => playPreview(v.id)} testID={`voice-preview-${v.id}`}>
                      <Ionicons name={previewing === v.id ? 'pause' : 'play'} size={12} color={COLORS.secondary} />
                      <Text style={cs.previewText}>{previewing === v.id ? 'Stop' : '5s'}</Text>
                    </TouchableOpacity>
                  )}
                  {pv.host_personality === v.id && <Ionicons name="checkmark-circle" size={20} color={COLORS.primary} />}
                </TouchableOpacity>
              ))}
            </View>
          )}
          {step === 9 && (
            <View>
              <Text style={s.title}>Explicit content?</Text>
              <Text style={s.lede}>Allow songs with adult language?</Text>
              <View style={cs.toggleRow} testID="explicit-toggle">
                <Switch value={pv.explicit_ok} onValueChange={v => setPv(p => ({ ...p, explicit_ok: v }))} trackColor={{ false: COLORS.cardBorder, true: COLORS.primary }} thumbColor="#fff" testID="explicit-checkbox" />
                <Text style={cs.toggleLabel}>{pv.explicit_ok ? 'Explicit ON' : 'Explicit OFF · clean radio only'}</Text>
              </View>
            </View>
          )}
          {step === 10 && (
            <View testID="step-done">
              <Text style={s.title}>Sab set, {user?.name || 'yaar'}!</Text>
              <Text style={s.lede}>Your personalized BigFM Dubai is ready. Tap below to start.</Text>
              <View style={cs.summaryGrid} testID="summary-grid">
                {[['LANGUAGES', pv.languages.join(' · ')], ['GENRES', pv.genres.map(nice).join(' · ')], ['ERAS', pv.eras.join(' · ')], ['MOODS', pv.moods.join(' · ')], ['MARKET', pv.market === 'dfw' ? 'DFW' : 'Dubai'], ['AREA', pv.home_area || '—'], ['RJ', pv.host_personality], ['EXPLICIT', pv.explicit_ok ? 'ON' : 'OFF']].map(([label, val]) => (
                  <View key={label} style={cs.summaryRow}>
                    <Text style={cs.summaryLabel}>{label}</Text>
                    <Text style={cs.summaryValue}>{val || '—'}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </ScrollView>

        {/* Footer nav */}
        <View style={s.footer}>
          <TouchableOpacity style={s.backBtn} onPress={back} disabled={step === 0 || saving} testID="wizard-back-btn">
            <Ionicons name="chevron-back" size={16} color={step === 0 ? COLORS.textMuted : COLORS.textDim} />
            <Text style={[s.backText, step === 0 && { color: COLORS.textMuted }]}>BACK</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.nextBtn, (!stepValid || saving) && { opacity: 0.5 }]} onPress={next} disabled={!stepValid || saving} testID="wizard-next-btn">
            {saving ? <ActivityIndicator color="#fff" size="small" /> : (
              <>
                <Text style={s.nextText}>{step === 10 ? 'START LISTENING' : 'CONTINUE'}</Text>
                <Ionicons name={step === 10 ? 'radio' : 'chevron-forward'} size={16} color="#fff" />
              </>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: SPACING.md },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  brandName: { color: '#fff', fontSize: FONT.lg, fontWeight: '900' },
  stepLabel: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5 },
  progressTrack: { height: 3, backgroundColor: COLORS.cardBorder },
  progressFill: { height: 3, backgroundColor: COLORS.primary },
  main: { padding: SPACING.lg, paddingBottom: 100 },
  title: { color: '#fff', fontSize: FONT.xxl, fontWeight: '900', marginBottom: 8 },
  lede: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 22, marginBottom: SPACING.lg },
  bulletRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  bulletNum: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800', letterSpacing: 1 },
  bulletText: { color: COLORS.textDim, fontSize: FONT.md },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, padding: 14, color: '#fff', fontSize: FONT.md },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.primary, paddingHorizontal: 16, borderRadius: RADIUS.md },
  footer: { flexDirection: 'row', justifyContent: 'space-between', padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, padding: 12 },
  backText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', letterSpacing: 1 },
  nextBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary, paddingHorizontal: 24, paddingVertical: 14, borderRadius: RADIUS.lg },
  nextText: { color: '#fff', fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.5 },
});

const cs = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  chipTextOn: { color: '#fff' },
  areaCard: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  areaCardOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  areaLabel: { color: '#fff', fontSize: FONT.md, fontWeight: '700' },
  areaBlurb: { color: COLORS.textDim, fontSize: FONT.xs },
  artistChip: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.card, paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.cardBorder },
  voiceCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: RADIUS.lg, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: 8 },
  voiceCardOn: { borderColor: COLORS.primary },
  voiceAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  voiceInitial: { color: '#fff', fontSize: 16, fontWeight: '800' },
  voiceName: { color: '#fff', fontSize: FONT.md, fontWeight: '700' },
  voiceBlurb: { color: COLORS.textDim, fontSize: FONT.xs },
  voiceFits: { color: COLORS.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 1, marginTop: 2 },
  previewBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLORS.secondary },
  previewText: { color: COLORS.secondary, fontSize: 11, fontWeight: '700' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 16 },
  toggleLabel: { color: COLORS.textDim, fontSize: FONT.md, flex: 1 },
  summaryGrid: { marginTop: 8 },
  summaryRow: { flexDirection: 'row', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  summaryLabel: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, width: 100 },
  summaryValue: { color: '#fff', fontSize: FONT.sm, flex: 1 },
});
