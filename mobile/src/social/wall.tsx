// FUUSIC Social V2 — Mobile Social Home wall (single-column).
// Combined "what people & things you follow are doing" feed: horizontal quick
// actions + composer + FOLLOWING/FOR YOU toggle + real activity cards.
// Extends the shared /api/social/feed-v2 contract. No duplicate feed system.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
  RefreshControl, TextInput, Modal, Share,
} from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { TSPACE, TRADIUS, TFONT } from '../constants/tube';
import { useThemeTokens } from '../theme/ThemeProvider';
import type { ThemeTokens } from '../theme/tokens';
import api from '../api/client';
import { AvatarM } from '../../app/(tabs)/social';
import { RadioClipCardM, ClipShareModalM } from './RadioClipCardM';

const fireEvent = (event: string, extra: any = {}) =>
  api.post('/social/feed-events', { event, ...extra }).catch(() => {});

const TYPE_META: any = {
  MOMENT: { verb: 'shared a moment', icon: 'image', tone: '#EC4899' },
  LIVE_VIDEO: { verb: 'went live', icon: 'videocam', tone: '#ef4444' },
  BUSINESS_LIVE: { verb: 'is live shopping', icon: 'videocam', tone: '#ef4444' },
  EVENT: { verb: 'has an event', icon: 'sparkles', tone: '#22D3EE' },
  LISTEN_ROOM: { verb: 'is listening together', icon: 'headset', tone: '#22D3EE' },
  DREAM: { verb: 'shared a dream', icon: 'moon', tone: '#A855F7' },
  CLUB_POST: { verb: 'posted in a club', icon: 'people', tone: '#A855F7' },
  TAROT_SHARE: { verb: 'shared a Tarot card', emoji: '🃏', tone: '#c084fc' },
  STATION_ACTIVITY: { verb: 'posted', icon: 'radio', tone: '#38bdf8' },
  RADIO_CLIP: { verb: 'shared a clip', icon: 'mic', tone: '#A855F7' },
};

function RelChip({ rel }: any) {
  const t = useThemeTokens();
  const w = makeStyles(t);
  const map: any = {
    friend_following: ['Friend · Following', t.electric],
    friend: ['Friend', t.electric], following: ['Following', t.magenta],
  };
  const m = map[rel];
  if (!m) return null;
  return (
    <View style={[w.relChip, { backgroundColor: `${m[1]}22` }]}>
      <Text style={[w.relChipTxt, { color: m[1] }]}>{m[0]}</Text>
    </View>
  );
}

function WallCard({ item, mode, onFollow, onNavigateTab }: any) {
  const router = useRouter();
  const t = useThemeTokens();
  const w = makeStyles(t);
  const meta = TYPE_META[item.type] || { verb: '', icon: 'sparkles', tone: t.magenta };
  const actor = item.actor || {};
  const [liked, setLiked] = useState(!!item.meta?.liked_by_me);
  const [likeCount, setLikeCount] = useState(item.meta?.like_count || 0);
  const [saved, setSaved] = useState(!!item.meta?.saved_by_me);
  const [shares, setShares] = useState(item.meta?.share_count || 0);
  const [followed, setFollowed] = useState(false);
  const isMine = !!item.is_mine || actor.kind === 'self';
  const pending = !!item.approval_status && item.approval_status !== 'approved';
  const [clipOpen, setClipOpen] = useState(false);
  const isSponsored = !!item.sponsored || item.type === 'SPONSORED_POST';
  const isReading = item.type === 'READING';
  const [hidden, setHidden] = useState(false);
  const hideAd = async () => {
    setHidden(true);
    try {
      const rawId = String(item.id).includes(':') ? String(item.id).split(':')[1] : item.id;
      await api.post('/social/suggestions/dismiss',
        { actor_type: 'sponsored_post', actor_id: rawId, action: 'hide' });
    } catch (_) {}
  };

  const openCta = () => {
    fireEvent('feed_item_open', { item_id: item.id, item_type: item.type, mode });
    const tgt = item.cta?.target;
    switch (item.cta?.action) {
      case 'open_room': fireEvent('feed_join_room', { item_id: item.id }); router.push(`/social/room/${tgt}` as any); break;
      case 'open_live': fireEvent('feed_watch_live', { item_id: item.id }); onNavigateTab?.('live'); break;
      case 'open_dream': fireEvent('feed_dream_similar', { item_id: item.id }); router.push('/social/dreams' as any); break;
      case 'open_tarot': fireEvent('feed_tarot_open', { item_id: item.id }); router.push('/social/tarot' as any); break;
      case 'open_station': router.push('/stations' as any); break;
      case 'open_moment': default: onNavigateTab?.('moments'); break;
    }
  };

  const like = async () => {
    const next = !liked;
    setLiked(next); setLikeCount((c: number) => Math.max(0, c + (next ? 1 : -1)));
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    try { const r = await api.post('/social/wall/like', { item_id: item.id }); setLiked(!!r.data.liked); if (typeof r.data.like_count === 'number') setLikeCount(r.data.like_count); }
    catch (_) { setLiked(!next); setLikeCount((c: number) => Math.max(0, c + (next ? -1 : 1))); }
  };

  const save = async () => {
    const next = !saved; setSaved(next);
    Haptics.selectionAsync().catch(() => {});
    try { const r = await api.post('/social/wall/save', { item_id: item.id }); setSaved(!!r.data.saved); }
    catch (_) { setSaved(!next); }
  };

  const share = async () => {
    try { const r = await api.post('/social/wall/share', { item_id: item.id }); if (typeof r.data?.share_count === 'number') setShares(r.data.share_count); } catch (_) {}
    try { await Share.share({ message: `${actor.name || 'FUUSIC'} on FUUSIC — ${item.text || item.title || 'Check this out'}` }); } catch (_) {}
  };

  const follow = async () => {
    if (!actor.id) return;
    setFollowed(true);
    try { await api.post(`/social/follow/${actor.id}`); fireEvent('feed_follow_click', { item_id: item.id }); onFollow?.(); }
    catch (_) { setFollowed(false); }
  };

  const showFollow = !isMine && mode === 'for_you' && item.follow_relationship === 'discovery'
    && actor.kind === 'user' && actor.id && !actor.anonymous;

  if (hidden) return null;
  return (
    <View style={w.card} testID={`wall-card-${item.type}`}>
      <View style={w.cardHead}>
        <AvatarM name={actor.name} url={actor.avatar_url} size={40} />
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <Text style={w.actorName} numberOfLines={1}>{actor.name || 'FUUSIC'}</Text>
            {isSponsored ? (
              <Text testID={`wall-sponsored-${item.id}`} style={[w.verb, { fontWeight: '800' }]}>Sponsored</Text>
            ) : isReading ? (
              <Text style={[w.verb, { color: t.magenta, fontWeight: '700' }]}>AI · for reflection</Text>
            ) : (
              <Text style={w.verb} numberOfLines={1}>{meta.verb}</Text>
            )}
            {!isSponsored && !isReading && <RelChip rel={item.follow_relationship} />}
            {isMine && pending && (
              <View testID={`wall-pending-${item.id}`} style={[w.relChip, { backgroundColor: `${t.gold || '#f59e0b'}22` }]}>
                <Text style={[w.relChipTxt, { color: t.gold || '#f59e0b' }]}>Pending Review</Text>
              </View>
            )}
          </View>
        </View>
        {isSponsored ? (
          <Pressable onPress={hideAd} testID={`wall-hidead-${item.id}`} style={[w.relChip, { borderWidth: 1, borderColor: t.border }]}>
            <Text style={[w.relChipTxt, { color: t.textMuted }]}>Hide Ad</Text>
          </Pressable>
        ) : (
          <View style={[w.typeIcon, { backgroundColor: `${meta.tone}22` }]}>
            {meta.emoji ? <Text style={{ fontSize: 14 }}>{meta.emoji}</Text>
              : <Ionicons name={meta.icon} size={14} color={meta.tone} />}
          </View>
        )}
      </View>

      {(item.title || item.text) ? (
        <View style={{ paddingHorizontal: 14, paddingBottom: 8 }}>
          {item.title ? <Text style={w.title}>{item.title}</Text> : null}
          {isReading && meta.headline ? <Text style={[w.text, { color: t.magenta, fontWeight: '700', marginBottom: 2 }]}>{meta.headline}</Text> : null}
          {item.text ? <Text style={w.text}>{item.text}</Text> : null}
          {isReading && meta.disclaimer ? <Text style={{ color: t.textMuted, fontSize: 11, fontStyle: 'italic', marginTop: 6 }}>{meta.disclaimer}</Text> : null}
          {item.meta?.tags?.length > 0 && (
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
              {item.meta.tags.map((tag: string) => <Text key={tag} style={w.tag}>#{tag}</Text>)}
            </View>
          )}
        </View>
      ) : null}

      {item.media_type === 'audio' && item.media_url ? (
        <RadioClipCardM item={item} t={t} onClip={() => setClipOpen(true)} />
      ) : item.media_url ? (
        <Pressable onPress={openCta}>
          <Image source={{ uri: item.media_url }} style={w.media} contentFit="cover" transition={200} />
          {(item.type === 'LIVE_VIDEO' || item.type === 'BUSINESS_LIVE') && (
            <View style={w.liveTag}><Text style={w.liveTagTxt}>● LIVE</Text></View>
          )}
          {item.type === 'EVENT' && (
            <View style={w.upTag}><Text style={w.upTagTxt}>UPCOMING</Text></View>
          )}
        </Pressable>
      ) : null}

      <ClipShareModalM visible={clipOpen} t={t} onClose={() => setClipOpen(false)}
        onPosted={() => {}} station={{ id: item.meta?.station_id, name: item.meta?.station_name,
          logo: item.meta?.station_logo, slug: item.meta?.station_slug }} />

      {item.meta?.products?.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingHorizontal: 14, paddingTop: 8 }}>
          {item.meta.products.map((p: any, i: number) => (
            <View key={i} style={w.product}>
              <Text style={w.productTxt}>{p.title} · ${((p.price_cents || 0) / 100).toFixed(0)}</Text>
            </View>
          ))}
        </ScrollView>
      )}

      <View style={w.cardActions}>
        <Pressable onPress={like} testID={`wall-like-${item.id}`} style={w.actBtn}>
          <Ionicons name={liked ? 'heart' : 'heart-outline'} size={18} color={liked ? t.pink : t.textMuted} />
          <Text style={w.actTxt}>{likeCount > 0 ? likeCount : 'Like'}</Text>
        </Pressable>
        {item.type === 'MOMENT' && (
          <Pressable onPress={openCta} testID={`wall-comment-${item.id}`} style={w.actBtn}>
            <Ionicons name="chatbubble-outline" size={17} color={t.textMuted} />
            <Text style={w.actTxt}>{item.meta?.comment_count || 0}</Text>
          </Pressable>
        )}
        <Pressable onPress={share} testID={`wall-share-${item.id}`} style={w.actBtn}>
          <Ionicons name="arrow-redo-outline" size={17} color={t.textMuted} />
          <Text style={w.actTxt}>{shares > 0 ? shares : 'Share'}</Text>
        </Pressable>
        <Pressable onPress={save} testID={`wall-save-${item.id}`} style={w.actBtn}>
          <Ionicons name={saved ? 'bookmark' : 'bookmark-outline'} size={17} color={saved ? t.magenta : t.textMuted} />
        </Pressable>
        <View style={{ flex: 1 }} />
        {showFollow ? (
          <Pressable onPress={follow} disabled={followed} testID={`wall-follow-${item.id}`}>
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.ctaBtn}>
              <Text style={w.ctaTxt}>{followed ? 'Following' : 'Follow'}</Text>
            </LinearGradient>
          </Pressable>
        ) : (
          <Pressable onPress={openCta} testID={`wall-cta-${item.id}`}>
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.ctaBtn}>
              <Text style={w.ctaTxt}>{item.cta?.label || 'Open'}</Text>
              <Ionicons name="chevron-forward" size={14} color="#fff" />
            </LinearGradient>
          </Pressable>
        )}
      </View>
    </View>
  );
}

function MomentComposer({ visible, onClose, onPosted }: any) {
  const t = useThemeTokens();
  const w = makeStyles(t);
  const [caption, setCaption] = useState('');
  const [media, setMedia] = useState('');
  const [busy, setBusy] = useState(false);
  const post = async () => {
    if (!caption.trim() && !media.trim()) return;
    setBusy(true);
    try {
      await api.post('/social/moments', {
        caption: caption.trim(), media_url: media.trim() || null,
        media_type: media.trim() ? 'photo' : null, visibility: 'friends',
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setCaption(''); setMedia(''); onPosted?.(); onClose();
    } catch (_) {} finally { setBusy(false); }
  };
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={w.modalWrap}>
        <View style={w.modalCard} testID="moment-composer">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text style={w.modalTitle}>Share a moment</Text>
            <Pressable onPress={onClose}><Ionicons name="close" size={22} color={t.text} /></Pressable>
          </View>
          <TextInput value={caption} onChangeText={setCaption} placeholder="What's happening?"
            placeholderTextColor={t.textMuted} style={w.modalInput} multiline testID="moment-caption" />
          <TextInput value={media} onChangeText={setMedia} placeholder="Image URL (optional)"
            placeholderTextColor={t.textMuted} style={w.modalInput2} autoCapitalize="none" testID="moment-media" />
          <Pressable onPress={post} disabled={busy} testID="moment-post">
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.modalPost}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={w.modalPostTxt}>Share moment</Text>}
            </LinearGradient>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

export default function SocialWall({ actions, onOpenFollowing, onNavigateTab }: any) {
  const router = useRouter();
  const t = useThemeTokens();
  const w = makeStyles(t);
  const [mode, setMode] = useState<'following' | 'for_you'>('following');
  const [items, setItems] = useState<any[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const latestRef = useRef<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  const fetchFeed = useCallback(async (m: string) => {
    try {
      const r = await api.get('/social/feed-v2', { params: { mode: m, limit: 20 } });
      setItems(r.data.items || []);
      setCursor(r.data.next_cursor || null);
      setHasMore(!!r.data.has_more);
      latestRef.current = (r.data.items || [])[0]?.created_at || null;
      setNewCount(0);
      fireEvent('social_feed_view', { mode: m });
      fireEvent(m === 'following' ? 'social_feed_mode_following' : 'social_feed_mode_for_you', { mode: m });
    } catch (_) {} finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { setLoading(true); fetchFeed(mode); }, [mode, fetchFeed]);

  useEffect(() => {
    const id = setInterval(async () => {
      if (!latestRef.current) return;
      try {
        const r = await api.get('/social/feed-v2/new-count', { params: { since: latestRef.current, mode } });
        if ((r.data.new_count || 0) > 0) setNewCount(r.data.new_count);
      } catch (_) {}
    }, 60000);
    return () => clearInterval(id);
  }, [mode]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await api.get('/social/feed-v2', { params: { mode, cursor, limit: 20 } });
      setItems((prev) => [...prev, ...(r.data.items || [])]);
      setCursor(r.data.next_cursor || null);
      setHasMore(!!r.data.has_more);
    } catch (_) {} finally { setLoadingMore(false); }
  };

  const showNew = () => {
    scrollRef.current?.scrollTo({ y: 0, animated: true });
    setLoading(true); fetchFeed(mode);
  };

  return (
    <>
      <ScrollView ref={scrollRef} testID="social-wall"
        contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 14 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={t.magenta}
          onRefresh={() => { setRefreshing(true); fetchFeed(mode); }} />}
        onScrollEndDrag={(e) => {
          const { layoutMeasurement, contentOffset, contentSize } = e.nativeEvent;
          if (layoutMeasurement.height + contentOffset.y >= contentSize.height - 300) loadMore();
        }}>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 10 }} testID="social-quick-actions">
          {actions.map((a: any) => (
            <Pressable key={a.key} onPress={a.on} testID={`social-quick-${a.key}`} style={w.qa}>
              <LinearGradient colors={a.grad} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={w.qaIcon}>
                {a.emoji ? <Text style={{ fontSize: 18 }}>{a.emoji}</Text>
                  : <Ionicons name={a.icon} size={18} color="#fff" />}
              </LinearGradient>
              <Text style={w.qaLabel} numberOfLines={1}>{a.label}</Text>
              <Text style={w.qaBlurb} numberOfLines={1}>{a.blurb}</Text>
            </Pressable>
          ))}
        </ScrollView>

        <Pressable onPress={() => setComposerOpen(true)} style={w.composer} testID="composer-open">
          <Text style={w.composerTxt}>Share something with your friends…</Text>
          <Ionicons name="image-outline" size={18} color={t.pink} />
          <Pressable onPress={() => router.push('/social/dreams' as any)} testID="composer-dream">
            <Ionicons name="moon" size={18} color={t.magenta} />
          </Pressable>
        </Pressable>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} testID="wall-mode-toggle">
          {(['following', 'for_you'] as const).map((k) => {
            const active = mode === k;
            const label = k === 'following' ? 'Following' : 'For You';
            return active ? (
              <Pressable key={k} onPress={() => setMode(k)} testID={`wall-mode-${k}`}>
                <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.modePill}>
                  <Text style={w.modePillActive}>{label}</Text>
                </LinearGradient>
              </Pressable>
            ) : (
              <Pressable key={k} onPress={() => setMode(k)} testID={`wall-mode-${k}`} style={[w.modePill, w.modePillIdle]}>
                <Text style={w.modePillIdleTxt}>{label}</Text>
              </Pressable>
            );
          })}
          <View style={{ flex: 1 }} />
          <Pressable onPress={onOpenFollowing} testID="wall-open-following">
            <Text style={w.manage}>Manage following</Text>
          </Pressable>
        </View>

        {newCount > 0 && (
          <Pressable onPress={showNew} testID="wall-new-posts">
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.newPosts}>
              <Ionicons name="arrow-up" size={15} color="#fff" />
              <Text style={w.newPostsTxt}>{newCount} new post{newCount > 1 ? 's' : ''}</Text>
            </LinearGradient>
          </Pressable>
        )}

        {loading ? (
          <View style={{ paddingVertical: 40 }}><ActivityIndicator color={t.magenta} /></View>
        ) : items.length === 0 ? (
          <WallEmpty mode={mode} onOpenFollowing={onOpenFollowing} switchForYou={() => setMode('for_you')} />
        ) : (
          <View style={{ gap: 12 }} testID="wall-items">
            {items.map((it) => (
              <WallCard key={it.id} item={it} mode={mode} onNavigateTab={onNavigateTab}
                onFollow={() => fetchFeed(mode)} />
            ))}
            {hasMore && (
              <Pressable onPress={loadMore} disabled={loadingMore} style={w.loadMore} testID="wall-load-more">
                {loadingMore ? <ActivityIndicator color={t.magenta} />
                  : <Text style={w.loadMoreTxt}>Load more</Text>}
              </Pressable>
            )}
          </View>
        )}
      </ScrollView>
      <MomentComposer visible={composerOpen} onClose={() => setComposerOpen(false)} onPosted={() => fetchFeed(mode)} />
    </>
  );
}

function WallEmpty({ mode, onOpenFollowing, switchForYou }: any) {
  const t = useThemeTokens();
  const w = makeStyles(t);
  if (mode === 'for_you') {
    return (
      <View style={w.empty} testID="wall-empty">
        <Ionicons name="sparkles" size={26} color={t.magenta} />
        <Text style={w.emptyTitle}>You're all caught up</Text>
        <Text style={w.emptyTxt}>Check back soon for fresh activity near you.</Text>
      </View>
    );
  }
  return (
    <View style={w.empty} testID="wall-empty">
      <Ionicons name="people" size={26} color={t.magenta} />
      <Text style={w.emptyTitle}>Build your FUUSIC feed</Text>
      <Text style={w.emptyTxt}>Follow people, businesses, creators and clubs — their moments, live shows and dreams show up here.</Text>
      <Pressable onPress={onOpenFollowing} testID="wall-empty-follow">
        <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={w.emptyBtn}>
          <Text style={w.emptyBtnTxt}>Find people to follow</Text>
        </LinearGradient>
      </Pressable>
      <Pressable onPress={switchForYou} style={w.emptyBtn2}><Text style={w.emptyBtn2Txt}>Explore For You</Text></Pressable>
    </View>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  qa: { width: 150, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 12, gap: 4 },
  qaIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  qaLabel: { color: t.text, fontSize: TFONT.sm, fontWeight: '900' },
  qaBlurb: { color: t.textMuted, fontSize: TFONT.xs },
  composer: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, paddingHorizontal: 14, paddingVertical: 12 },
  composerTxt: { flex: 1, color: t.textMuted, fontSize: TFONT.sm },
  modePill: { height: 36, paddingHorizontal: 18, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  modePillIdle: { backgroundColor: t.elevated },
  modePillActive: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  modePillIdleTxt: { color: t.textMuted, fontSize: TFONT.sm, fontWeight: '900' },
  manage: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  newPosts: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 44, borderRadius: 22 },
  newPostsTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  card: { backgroundColor: t.card, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, overflow: 'hidden' },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  actorName: { color: t.text, fontSize: TFONT.sm, fontWeight: '900', maxWidth: 140 },
  verb: { color: t.textMuted, fontSize: TFONT.xs },
  relChip: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  relChipTxt: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  typeIcon: { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  title: { color: t.text, fontSize: 15, fontWeight: '800' },
  text: { color: t.textMuted, fontSize: TFONT.sm, marginTop: 2, lineHeight: 19 },
  tag: { color: '#c4b5fd', fontSize: 11 },
  media: { width: '100%', aspectRatio: 16 / 9, backgroundColor: 'rgba(0,0,0,0.3)' },
  liveTag: { position: 'absolute', top: 12, left: 12, backgroundColor: 'rgba(239,68,68,0.9)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  liveTagTxt: { color: '#fff', fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  upTag: { position: 'absolute', top: 12, left: 12, backgroundColor: 'rgba(34,211,238,0.9)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  upTagTxt: { color: '#04121a', fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  product: { backgroundColor: 'rgba(255,255,255,0.1)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  productTxt: { color: t.text, fontSize: 11, fontWeight: '800' },
  cardActions: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12 },
  actBtn: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  actTxt: { color: t.textMuted, fontSize: TFONT.sm, fontWeight: '800' },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, height: 36, paddingHorizontal: 16, borderRadius: 18 },
  ctaTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  loadMore: { height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: t.line, alignItems: 'center', justifyContent: 'center' },
  loadMoreTxt: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  empty: { backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 28, alignItems: 'center', gap: 8 },
  emptyTitle: { color: t.text, fontSize: TFONT.lg, fontWeight: '900' },
  emptyTxt: { color: t.textMuted, fontSize: TFONT.sm, textAlign: 'center', maxWidth: 300 },
  emptyBtn: { height: 44, paddingHorizontal: 20, borderRadius: 22, alignItems: 'center', justifyContent: 'center', marginTop: 6 },
  emptyBtnTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  emptyBtn2: { height: 44, paddingHorizontal: 20, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.1)' },
  emptyBtn2Txt: { color: t.text, fontSize: TFONT.sm, fontWeight: '900' },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)' },
  modalCard: { backgroundColor: t.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, borderColor: t.line, borderWidth: 1 },
  modalTitle: { color: t.text, fontSize: TFONT.lg, fontWeight: '900' },
  modalInput: { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: t.line, borderWidth: 1, borderRadius: 16, padding: 12, color: t.text, fontSize: TFONT.sm, minHeight: 72, textAlignVertical: 'top' },
  modalInput2: { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: t.line, borderWidth: 1, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 10, color: t.text, fontSize: TFONT.sm, marginTop: 8 },
  modalPost: { height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center', marginTop: 12 },
  modalPostTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
});
