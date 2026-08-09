import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator,
  RefreshControl, StyleSheet, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import {
  getEpisode, getEpisodeMagicClips, publishMagicClip,
  patchMagicClip, deleteMagicClip,
  getEpisodeMedia, uploadEpisodeVideo, putEpisodeChapters, putEpisodeTranscript,
} from '../../../src/api/podcastApi';

function formatSec(s: number | null | undefined): string {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
}

export default function CreatorEpisodeDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [episode, setEpisode] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [media, setMedia] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [ep, cl, md] = await Promise.all([
        getEpisode(id),
        getEpisodeMagicClips(id).catch(() => []),
        getEpisodeMedia(id).catch(() => null),
      ]);
      setEpisode(ep?.episode || ep);
      setClips(cl);
      setMedia(md);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load episode');
    } finally { setLoading(false); setRefreshing(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const doPublish = async (clipId: string) => {
    try {
      await publishMagicClip(clipId);
      await load();
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Publish failed'); }
  };

  const doDelete = (clipId: string) => {
    Alert.alert('Delete Clip', 'Remove this magic clip?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try { await deleteMagicClip(clipId); await load(); }
        catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Delete failed'); }
      }},
    ]);
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (err) return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <View style={{ padding: SPACING.lg }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 12 }}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text testID="episode-detail-error" style={{ color: COLORS.red, fontSize: FONT.md }}>{err}</Text>
      </View>
    </SafeAreaView>
  );

  const drafts = clips.filter(c => c.status === 'draft');
  const published = clips.filter(c => c.status === 'published');

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView
        contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        {/* Header */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text testID="episode-detail-title" style={s.title} numberOfLines={2}>
              {episode?.title || 'Episode'}
            </Text>
            <Text style={s.subtitle}>
              {episode?.publish_status === 'published' ? 'Published' : 'Draft'} · {episode?.duration_sec ? `${Math.floor(episode.duration_sec / 60)}m ${episode.duration_sec % 60}s` : '—'}
            </Text>
          </View>
        </View>

        {/* Episode info card */}
        {episode?.description && (
          <View testID="episode-description-card" style={s.infoCard}>
            <Text style={s.infoLabel}>DESCRIPTION</Text>
            <Text style={s.infoText} numberOfLines={4}>{episode.description}</Text>
          </View>
        )}

        {/* Video, Chapters & Transcript editor */}
        <VideoChaptersEditor episodeId={id!} media={media} onSaved={load} />

        {/* Magic Clips Header */}
        <View style={s.clipsHeader}>
          <Text style={common.sectionTitle}>Magic Clips ({clips.length})</Text>
          <TouchableOpacity testID="episode-magic-clips-link"
            onPress={() => router.push(`/creator/magic-clips/${id}`)}>
            <Text style={s.linkText}>Full Clips View →</Text>
          </TouchableOpacity>
        </View>

        {clips.length === 0 && (
          <View style={s.emptyCard}>
            <Ionicons name="sparkles-outline" size={28} color={COLORS.textDim} />
            <Text style={s.emptyText}>No magic clips yet. Clips are generated automatically after publishing.</Text>
          </View>
        )}

        {/* Draft clips — needs approve/reject */}
        {drafts.length > 0 && (
          <>
            <Text style={s.subSection}>Awaiting Review ({drafts.length})</Text>
            {drafts.map(clip => (
              <ClipCard key={clip.id} clip={clip}
                onApprove={() => doPublish(clip.id)}
                onReject={() => doDelete(clip.id)}
              />
            ))}
          </>
        )}

        {/* Published clips */}
        {published.length > 0 && (
          <>
            <Text style={[s.subSection, { marginTop: SPACING.md }]}>Published ({published.length})</Text>
            {published.map(clip => (
              <ClipCard key={clip.id} clip={clip} published
                onReject={() => doDelete(clip.id)}
              />
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function VideoChaptersEditor({ episodeId, media, onSaved }: {
  episodeId: string; media: any; onSaved: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [chapters, setChapters] = useState<{ title: string; start_seconds: number }[]>([]);
  const [transcript, setTranscript] = useState('');
  const [savingCh, setSavingCh] = useState(false);
  const [savingTr, setSavingTr] = useState(false);
  const [chTitle, setChTitle] = useState('');
  const [chMin, setChMin] = useState('');
  const [chSec, setChSec] = useState('');

  useEffect(() => {
    if (media) {
      setChapters(media.chapters || []);
      setTranscript(media.transcript || '');
    }
  }, [media]);

  const pickVideo = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: 'video/*', copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.length) return;
      const a = res.assets[0];
      setUploading(true);
      await uploadEpisodeVideo(episodeId, { uri: a.uri, name: a.name || 'video.mp4', mimeType: a.mimeType });
      onSaved();
    } catch (e: any) {
      Alert.alert('Upload failed', e?.response?.data?.detail?.code || e?.message || 'Try a smaller MP4.');
    } finally { setUploading(false); }
  };

  const addChapter = () => {
    if (!chTitle.trim()) return;
    const start = (parseInt(chMin || '0', 10) * 60) + parseInt(chSec || '0', 10);
    const next = [...chapters, { title: chTitle.trim(), start_seconds: start }]
      .sort((a, b) => a.start_seconds - b.start_seconds);
    setChapters(next);
    setChTitle(''); setChMin(''); setChSec('');
  };

  const removeChapter = (i: number) => setChapters(chapters.filter((_, idx) => idx !== i));

  const saveChapters = async () => {
    setSavingCh(true);
    try { await putEpisodeChapters(episodeId, chapters); onSaved(); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail?.code || 'Save failed'); }
    finally { setSavingCh(false); }
  };

  const saveTranscript = async () => {
    setSavingTr(true);
    try { await putEpisodeTranscript(episodeId, transcript); onSaved(); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail?.code || 'Save failed'); }
    finally { setSavingTr(false); }
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const hasVideo = !!media?.video_url;

  return (
    <View style={s.videoCard} testID="episode-video-editor">
      <Text style={common.sectionTitle}>Video, Chapters &amp; Transcript</Text>

      <TouchableOpacity style={[s.uploadBtn, hasVideo && s.uploadBtnDone]} onPress={pickVideo}
        disabled={uploading} testID="episode-upload-video">
        {uploading ? <ActivityIndicator color={COLORS.primary} />
          : <><Ionicons name={hasVideo ? 'checkmark-circle' : 'videocam'} size={18}
                color={hasVideo ? COLORS.green : COLORS.primary} />
              <Text style={[s.uploadText, hasVideo && { color: COLORS.green }]}>
                {hasVideo ? 'Video uploaded — replace' : 'Upload video (MP4)'}
              </Text></>}
      </TouchableOpacity>
      <Text style={s.helpText}>Stored securely in Tigris object storage. Max 500 MB.</Text>

      {/* Chapters */}
      <Text style={s.editLabel}>CHAPTERS</Text>
      {chapters.map((c, i) => (
        <View key={`${c.start_seconds}-${i}`} style={s.chapterRow} testID={`episode-chapter-${i}`}>
          <Text style={s.chapterTime}>{fmt(c.start_seconds)}</Text>
          <Text style={s.chapterTitle} numberOfLines={1}>{c.title}</Text>
          <TouchableOpacity onPress={() => removeChapter(i)} testID={`episode-chapter-remove-${i}`}>
            <Ionicons name="close-circle" size={18} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>
      ))}
      <View style={s.chapterAddRow}>
        <TextInput style={[s.chInput, { flex: 1 }]} value={chTitle} onChangeText={setChTitle}
          placeholder="Chapter title" placeholderTextColor={COLORS.textMuted} testID="episode-chapter-title" />
        <TextInput style={[s.chInput, { width: 44 }]} value={chMin} onChangeText={setChMin}
          keyboardType="number-pad" placeholder="m" placeholderTextColor={COLORS.textMuted} testID="episode-chapter-min" />
        <TextInput style={[s.chInput, { width: 44 }]} value={chSec} onChangeText={setChSec}
          keyboardType="number-pad" placeholder="s" placeholderTextColor={COLORS.textMuted} testID="episode-chapter-sec" />
        <TouchableOpacity style={s.chAddBtn} onPress={addChapter} testID="episode-chapter-add">
          <Ionicons name="add" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
      <TouchableOpacity style={s.saveRow} onPress={saveChapters} disabled={savingCh} testID="episode-chapters-save">
        {savingCh ? <ActivityIndicator color={COLORS.primary} size="small" />
          : <Text style={s.saveText}>Save chapters</Text>}
      </TouchableOpacity>

      {/* Transcript */}
      <Text style={s.editLabel}>TRANSCRIPT</Text>
      <TextInput style={s.transcriptInput} value={transcript} onChangeText={setTranscript}
        multiline placeholder="Paste or type the episode transcript…"
        placeholderTextColor={COLORS.textMuted} testID="episode-transcript-input" />
      <TouchableOpacity style={s.saveRow} onPress={saveTranscript} disabled={savingTr} testID="episode-transcript-save">
        {savingTr ? <ActivityIndicator color={COLORS.primary} size="small" />
          : <Text style={s.saveText}>Save transcript</Text>}
      </TouchableOpacity>
    </View>
  );
}

function ClipCard({ clip, published, onApprove, onReject }: {
  clip: any; published?: boolean; onApprove?: () => void; onReject?: () => void;
}) {
  const dur = (clip.end_sec || 0) - (clip.start_sec || 0);
  return (
    <View testID={`clip-card-${clip.id}`} style={s.clipCard}>
      <View style={s.clipTop}>
        <View style={s.clipBadge}>
          <Text style={s.clipBadgeText}>{clip.ext === 'mp4' ? 'VIDEO' : 'AUDIO'}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Text style={s.clipTitle} numberOfLines={1}>{clip.title || 'Untitled'}</Text>
          <Text style={s.clipMeta}>
            {formatSec(clip.start_sec)}–{formatSec(clip.end_sec)} · {dur.toFixed(0)}s · score {(clip.score || 0).toFixed(2)}
          </Text>
        </View>
        <View style={[s.clipStatus, published ? s.clipStatusGreen : s.clipStatusYellow]}>
          <Text style={[s.clipStatusText, published ? { color: COLORS.green } : { color: COLORS.orange }]}>
            {clip.status || 'draft'}
          </Text>
        </View>
      </View>
      <View style={s.clipActions}>
        {!published && onApprove && (
          <TouchableOpacity testID={`clip-approve-${clip.id}`} style={s.approveBtn} onPress={onApprove}>
            <Ionicons name="checkmark-circle" size={16} color="#0a0a0c" />
            <Text style={s.approveBtnText}>Approve & Publish</Text>
          </TouchableOpacity>
        )}
        {onReject && (
          <TouchableOpacity testID={`clip-reject-${clip.id}`} style={s.rejectBtn} onPress={onReject}>
            <Ionicons name="trash-outline" size={14} color={COLORS.red} />
            <Text style={s.rejectBtnText}>{published ? 'Remove' : 'Reject'}</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  subtitle: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 2 },
  infoCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg,
  },
  infoLabel: { fontSize: FONT.xs, fontWeight: '700', color: COLORS.textDim, letterSpacing: 1.5, marginBottom: 6 },
  infoText: { fontSize: FONT.sm, color: COLORS.text, lineHeight: 20 },
  clipsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  linkText: { fontSize: FONT.xs, color: COLORS.orange },
  subSection: { fontSize: FONT.sm, fontWeight: '700', color: COLORS.textDim, marginBottom: SPACING.sm },
  emptyCard: {
    alignItems: 'center', paddingVertical: 30, borderRadius: RADIUS.md,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg,
  },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 8, textAlign: 'center', paddingHorizontal: 20 },
  clipCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: 12,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: 8,
  },
  clipTop: { flexDirection: 'row', alignItems: 'center' },
  clipBadge: {
    width: 48, height: 32, borderRadius: 4, backgroundColor: '#1e1e2a',
    alignItems: 'center', justifyContent: 'center',
  },
  clipBadgeText: { fontSize: 9, fontWeight: '700', color: COLORS.textDim, letterSpacing: 0.5 },
  clipTitle: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text },
  clipMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  clipStatus: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  clipStatusGreen: { borderColor: 'rgba(74,222,128,0.3)', backgroundColor: 'rgba(74,222,128,0.08)' },
  clipStatusYellow: { borderColor: 'rgba(245,158,11,0.3)', backgroundColor: 'rgba(245,158,11,0.08)' },
  clipStatusText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  clipActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
  approveBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: COLORS.green, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 6,
  },
  approveBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.xs },
  rejectBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6,
  },
  rejectBtnText: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '600' },
  videoCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg },
  uploadBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10', marginTop: 8 },
  uploadBtnDone: { borderColor: COLORS.green, backgroundColor: COLORS.green + '10' },
  uploadText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  helpText: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 6 },
  editLabel: { fontSize: FONT.xs, fontWeight: '800', color: COLORS.textDim, letterSpacing: 1.2, marginTop: SPACING.md, marginBottom: 8 },
  chapterRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  chapterTime: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', width: 44 },
  chapterTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  chapterAddRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 },
  chInput: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm },
  chAddBtn: { width: 38, height: 38, borderRadius: RADIUS.sm, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  transcriptInput: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, padding: 12, color: COLORS.text, fontSize: FONT.sm, minHeight: 100, textAlignVertical: 'top' },
  saveRow: { alignItems: 'center', paddingVertical: 10, marginTop: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  saveText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
});
