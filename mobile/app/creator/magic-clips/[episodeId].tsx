import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  ActivityIndicator, StyleSheet, Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import {
  getEpisodeMagicClips, publishMagicClip, patchMagicClip, deleteMagicClip,
} from '../../../src/api/podcastApi';

function fmtSec(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
}

export default function MagicClipsReviewScreen() {
  const { episodeId } = useLocalSearchParams<{ episodeId: string }>();
  const router = useRouter();
  const [clips, setClips] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const load = useCallback(async () => {
    if (!episodeId) return;
    try {
      const items = await getEpisodeMagicClips(episodeId);
      setClips(items);
    } catch { setClips([]); }
    finally { setLoading(false); }
  }, [episodeId]);

  useEffect(() => { load(); }, [load]);

  const doPublish = async (clipId: string) => {
    setBusy(clipId);
    try {
      await publishMagicClip(clipId);
      setClips(prev => prev.filter(c => c.id !== clipId));
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Publish failed'); }
    finally { setBusy(null); }
  };

  const doPublishAll = async () => {
    const drafts = clips.filter(c => c.status === 'draft');
    setBusy('all');
    try {
      await Promise.all(drafts.map(c => publishMagicClip(c.id)));
      setClips(prev => prev.filter(c => c.status !== 'draft'));
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Bulk publish failed'); }
    finally { setBusy(null); }
  };

  const doSaveTitle = async (clipId: string) => {
    setBusy(clipId);
    try {
      await patchMagicClip(clipId, { title: editTitle });
      setClips(prev => prev.map(c => c.id === clipId ? { ...c, title: editTitle } : c));
      setEditingId(null);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Update failed'); }
    finally { setBusy(null); }
  };

  const doDelete = async (clipId: string) => {
    Alert.alert('Delete clip?', 'This cannot be undone.', [
      { text: 'Cancel' },
      {
        text: 'Delete', style: 'destructive', onPress: async () => {
          setBusy(clipId);
          try {
            await deleteMagicClip(clipId);
            setClips(prev => prev.filter(c => c.id !== clipId));
          } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Delete failed'); }
          finally { setBusy(null); }
        },
      },
    ]);
  };

  const drafts = clips.filter(c => c.status === 'draft');
  const published = clips.filter(c => c.status === 'published');

  if (loading) return (
    <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
  );

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}>
        {/* Header */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text testID="mobile-clips-title" style={s.title}>Magic Clips</Text>
            <Text style={s.subtitle}>Review, edit, and publish highlights for this episode.</Text>
          </View>
        </View>

        {clips.length === 0 ? (
          <View testID="mobile-clips-empty" style={s.empty}>
            <Ionicons name="sparkles-outline" size={40} color={COLORS.textDim} />
            <Text style={s.emptyText}>No magic clips for this episode.</Text>
          </View>
        ) : (
          <>
            {/* Bulk publish */}
            {drafts.length > 0 && (
              <TouchableOpacity testID="mobile-clips-publish-all" style={s.publishAllBtn}
                onPress={doPublishAll} disabled={busy === 'all'}>
                <Text style={s.publishAllText}>
                  {busy === 'all' ? 'Publishing…' : `Publish all ${drafts.length} drafts`}
                </Text>
              </TouchableOpacity>
            )}

            {/* Drafts */}
            {drafts.length > 0 && <Text style={common.sectionTitle}>Drafts ({drafts.length})</Text>}
            {drafts.map(c => (
              <View key={c.id} testID={`mobile-clip-draft-${c.id}`} style={s.clipCard}>
                {editingId === c.id ? (
                  <View style={s.editRow}>
                    <TextInput testID={`mobile-clip-edit-title-${c.id}`}
                      style={[common.input, { flex: 1 }]}
                      value={editTitle} onChangeText={setEditTitle} />
                    <TouchableOpacity onPress={() => doSaveTitle(c.id)} style={s.saveEditBtn}>
                      <Text style={{ color: '#0a0a0c', fontWeight: '700', fontSize: FONT.xs }}>Save</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => setEditingId(null)}>
                      <Text style={{ color: COLORS.textDim, fontSize: FONT.xs }}>Cancel</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <Text style={s.clipTitle}>{c.title || 'Untitled'}</Text>
                )}
                <Text style={s.clipMeta}>
                  {fmtSec(c.start_sec || 0)}–{fmtSec(c.end_sec || 0)} · {((c.end_sec || 0) - (c.start_sec || 0))}s
                  · score {(c.score || 0).toFixed(2)}
                </Text>
                {c.transcript_excerpt && (
                  <Text style={s.excerpt} numberOfLines={2}>{c.transcript_excerpt}</Text>
                )}
                <View style={s.actionsRow}>
                  <TouchableOpacity testID={`mobile-clip-publish-${c.id}`}
                    style={s.actionPrimary} onPress={() => doPublish(c.id)} disabled={busy === c.id}>
                    <Text style={s.actionPrimaryText}>{busy === c.id ? '…' : 'Publish'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID={`mobile-clip-edit-${c.id}`} style={s.actionGhost}
                    onPress={() => { setEditingId(c.id); setEditTitle(c.title || ''); }}>
                    <Text style={s.actionGhostText}>Edit title</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID={`mobile-clip-delete-${c.id}`} style={s.actionDelete}
                    onPress={() => doDelete(c.id)}>
                    <Ionicons name="trash-outline" size={14} color={COLORS.red} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}

            {/* Published */}
            {published.length > 0 && <Text style={[common.sectionTitle, { marginTop: SPACING.lg }]}>Published ({published.length})</Text>}
            {published.map(c => (
              <View key={c.id} testID={`mobile-clip-published-${c.id}`} style={[s.clipCard, { opacity: 0.7 }]}>
                <Text style={s.clipTitle}>{c.title || 'Untitled'}</Text>
                <Text style={s.clipMeta}>
                  {fmtSec(c.start_sec || 0)}–{fmtSec(c.end_sec || 0)} · score {(c.score || 0).toFixed(2)} · published
                </Text>
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xxl, fontWeight: '800', color: COLORS.text },
  subtitle: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 2 },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.md },
  publishAllBtn: { backgroundColor: COLORS.orange, paddingVertical: 10, borderRadius: 8, alignItems: 'center', marginBottom: SPACING.lg },
  publishAllText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.md },
  clipCard: {
    padding: 14, marginBottom: 8, borderRadius: 10,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  clipTitle: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  clipMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 3 },
  excerpt: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 6, lineHeight: 16, fontStyle: 'italic' },
  actionsRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  actionPrimary: { backgroundColor: COLORS.orange, paddingVertical: 5, paddingHorizontal: 12, borderRadius: 6 },
  actionPrimaryText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.xs },
  actionGhost: { paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  actionGhostText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  actionDelete: { padding: 5, borderWidth: 1, borderColor: 'rgba(239,68,68,0.4)', borderRadius: 6 },
  editRow: { flexDirection: 'row', gap: 6, alignItems: 'center', marginBottom: 4 },
  saveEditBtn: { backgroundColor: COLORS.orange, paddingVertical: 4, paddingHorizontal: 10, borderRadius: 4 },
});
