import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  Image, Animated,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

export default function NewsArticle() {
  const router = useRouter();
  const p = useLocalSearchParams<{
    headline_id?: string; title?: string; summary?: string; source_name?: string;
    source_url?: string; image_url?: string; published_at?: string; category?: string;
  }>();
  const [reward, setReward] = useState<{ points: number } | null>(null);
  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Award reading points (server-capped per day).
    api.post('/news/read', { headline_id: p.headline_id, title: p.title })
      .then((r) => {
        if (r.data?.awarded && r.data?.points > 0) {
          setReward({ points: r.data.points });
          Animated.sequence([
            Animated.timing(fade, { toValue: 1, duration: 300, useNativeDriver: true }),
            Animated.delay(2200),
            Animated.timing(fade, { toValue: 0, duration: 400, useNativeDriver: true }),
          ]).start();
        }
      }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openOriginal = () => { if (p.source_url) WebBrowser.openBrowserAsync(String(p.source_url)); };

  return (
    <SafeAreaView style={common.screen} testID="news-article-screen">
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()} testID="news-article-back" style={s.iconBtn}>
          <Ionicons name="arrow-back" size={20} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Article</Text>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 80 }} showsVerticalScrollIndicator={false}>
        {!!p.image_url && (
          <Image source={{ uri: String(p.image_url) }} style={s.hero} resizeMode="cover" />
        )}
        {!!p.category && (
          <View style={s.catBadge}><Text style={s.catText}>{String(p.category).toUpperCase()}</Text></View>
        )}
        <Text style={s.title} testID="news-article-title">{p.title}</Text>
        <View style={s.metaRow}>
          <Text style={s.source}>{p.source_name || '—'}</Text>
          {!!p.published_at && (
            <Text style={s.time}>{new Date(String(p.published_at)).toLocaleDateString()}</Text>
          )}
        </View>
        {!!p.summary && <Text style={s.summary}>{p.summary}</Text>}

        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.lg }]} onPress={openOriginal} testID="news-article-open-original" disabled={!p.source_url}>
          <Ionicons name="open-outline" size={16} color="#fff" />
          <Text style={common.btnPrimaryText}>Read full article</Text>
        </TouchableOpacity>
      </ScrollView>

      <Animated.View style={[s.rewardToast, { opacity: fade }]} pointerEvents="none" testID="news-article-reward">
        <Ionicons name="logo-bitcoin" size={14} color="#fff" />
        <Text style={s.rewardText}>+{reward?.points || 0} BigCoin for reading</Text>
      </Animated.View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm },
  iconBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  topTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  hero: { width: '100%', height: 190, borderRadius: RADIUS.lg, marginBottom: SPACING.md },
  catBadge: { alignSelf: 'flex-start', backgroundColor: '#fff2e6', borderRadius: RADIUS.sm, paddingHorizontal: 8, paddingVertical: 3, marginBottom: 8 },
  catText: { color: COLORS.primary, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', lineHeight: 30 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 },
  source: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '800' },
  time: { color: COLORS.textMuted, fontSize: FONT.xs },
  summary: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 23, marginTop: SPACING.md },
  rewardToast: { position: 'absolute', bottom: 30, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingHorizontal: 16, paddingVertical: 10 },
  rewardText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
});
