// Shop Home — FUUSIC Super Marketplace consumer entry.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, TextInput, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { SPACING, FONT, RADIUS } from '../../src/constants/theme';
import { useThemeTokens } from '../../src/theme/ThemeProvider';
import type { ThemeTokens } from '../../src/theme/tokens';
import { useCartStore } from '../../src/stores/useCartStore';

interface Biz {
  business_id: string; public_name: string; category: string; subcategory?: string;
  cover_url?: string; default_bigpoints: number; rating?: number;
  featured?: boolean; sponsored?: boolean; promoted?: boolean;
}
interface Section { key: string; title: string; subtitle?: string; items: Biz[]; }
interface Cat { key: string; name: string; icon?: string; }

export default function ShopHome() {
  const router = useRouter();
  const [headline, setHeadline] = useState('SHOP LOCAL. EARN BIGPOINTS.');
  const [cats, setCats] = useState<Cat[]>([]);
  const [filters, setFilters] = useState<string[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [specials, setSpecials] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isMerchant, setIsMerchant] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [usual, setUsual] = useState<any>(null);
  const [usualDismissed, setUsualDismissed] = useState(false);
  const [liveShows, setLiveShows] = useState<any[]>([]);
  const menuCart = useCartStore();
  const t = useThemeTokens();
  const s = makeStyles(t);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/home');
      setHeadline(r.data.headline);
      setCats(r.data.categories || []);
      setFilters(r.data.filters || []);
      setSpecials(r.data.specials || []);
      setSections((r.data.sections || []).filter((s: Section) => s.items.length));
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  // Promotion analytics — beacon one impression per promoted shop shown.
  const trackedRef = React.useRef<Set<string>>(new Set());
  useEffect(() => {
    sections.forEach((sec) => (sec.items || []).forEach((b: any) => {
      if (b.promoted && b.business_id && !trackedRef.current.has(b.business_id)) {
        trackedRef.current.add(b.business_id);
        api.post('/shop/track', { business_id: b.business_id, kind: 'impression' }).catch(() => {});
      }
    }));
  }, [sections]);

  useEffect(() => {
    // Role-gate merchant tools — only business owners see the dashboard.
    api.get('/merchant/marketplace/profile')
      .then((r) => setIsMerchant(!!r.data?.profile))
      .catch(() => setIsMerchant(false));
    // "Get your usual" one-tap for returning customers (auth-only; 401 → hide).
    api.get('/shop/usual')
      .then((r) => { if (r.data?.has_usual) setUsual(r.data); })
      .catch(() => setUsual(null));
    // Live Shopping — live shows first, then upcoming (scheduled) shows.
    Promise.all([
      api.get('/social/liveshows', { params: { status: 'live' } }).catch(() => ({ data: { items: [] } })),
      api.get('/social/liveshows', { params: { status: 'scheduled' } }).catch(() => ({ data: { items: [] } })),
    ]).then(([lv, up]) => {
      setLiveShows([...(lv.data.items || []), ...(up.data.items || [])].slice(0, 8));
    }).catch(() => setLiveShows([]));
  }, []);

  const addUsual = () => {
    if (!usual?.items?.length) return;
    usual.items.forEach((u: any) => menuCart.addLine(usual.business_id, usual.business_name, {
      item_id: u.item_id, name: u.name, price_cents: u.price_cents,
      selected_option_ids: u.selected_option_ids || [], option_summary: u.option_summary, note: u.note,
    }));
    router.push('/shop/cart');
  };

  const ACCOUNT_LINKS: [string, string, string, string][] = [
    ['/shop/concierge', 'sparkles', 'Order by Chat', 'shop-concierge-link'],
    ['/shop/orders', 'receipt-outline', 'My Orders', 'shop-my-orders'],
    ['/shop/product-orders', 'cube-outline', 'Product Orders', 'shop-my-product-orders'],
    ['/shop/bookings', 'calendar-outline', 'My Bookings', 'shop-my-bookings'],
    ['/shop/my-memberships', 'ribbon', 'My Memberships', 'shop-my-memberships'],
    ['/shop/loyalty', 'star-outline', 'My Loyalty', 'shop-my-loyalty'],
    ['/shop/wallet/cards', 'card-outline', 'Payment Methods', 'shop-payment-methods'],
    ['/shop/scan-pay', 'qr-code-outline', 'Scan to Pay', 'shop-scan-pay'],
  ];
  const openLink = (to: string) => { setMenuOpen(false); router.push(to as any); };

  const goSearch = () => router.push({ pathname: '/shop/browse', params: { q: query } });

  if (loading) return <View style={s.center}><ActivityIndicator size="large" color={t.primary} /></View>;

  return (
    <SafeAreaView style={s.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: 90 }} testID="shop-home-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={t.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        <View style={s.hero}>
          <View style={s.heroTop}>
            <Text style={s.eyebrow}>FUUSIC SHOP</Text>
            <TouchableOpacity style={s.accountBtn} onPress={() => setMenuOpen(true)} testID="shop-account-button">
              <Ionicons name="person-circle-outline" size={26} color={t.text} />
            </TouchableOpacity>
          </View>
          <Text style={s.headline}>{headline}</Text>
          <View style={s.searchBar}>
            <Ionicons name="search" size={18} color={t.textMuted} />
            <TextInput style={s.searchInput} value={query} onChangeText={setQuery}
              placeholder="What are you looking for?" placeholderTextColor={t.textMuted}
              returnKeyType="search" onSubmitEditing={goSearch} testID="shop-search-input" />
          </View>
          <TouchableOpacity style={s.nearMeBtn} onPress={() => router.push('/shop/near-me')} testID="shop-near-me">
            <Ionicons name="navigate" size={16} color={t.primary} />
            <Text style={s.nearMeText}>Explore shops &amp; services near you</Text>
            <Ionicons name="chevron-forward" size={16} color={t.textMuted} />
          </TouchableOpacity>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.catRow} testID="shop-categories">
          {cats.map((c) => (
            <TouchableOpacity key={c.key} style={s.catChip} testID={`shop-cat-${c.key}`}
              onPress={() => router.push({ pathname: '/shop/browse', params: { category: c.key } })}>
              <View style={s.catIcon}>
                <Ionicons name={(c.icon || 'storefront') as any} size={20} color={t.primary} />
              </View>
              <Text style={s.catLabel} numberOfLines={1}>{c.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.filterRow} testID="shop-filters">
          {filters.map((f) => (
            <TouchableOpacity key={f} style={s.filterChip}
              onPress={() => (f === 'Nearby'
                ? router.push('/shop/near-me')
                : router.push({ pathname: '/shop/browse', params: { filter: f } }))}>
              <Text style={s.filterText}>{f}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {isMerchant ? (
          <TouchableOpacity style={s.dashCard} onPress={() => router.push('/merchant/dashboard')} testID="shop-merchant-banner">
            <Ionicons name="grid-outline" size={24} color="#fff" />
            <View style={{ flex: 1 }}>
              <Text style={s.sellTitle}>Merchant Dashboard</Text>
              <Text style={s.sellSub}>Manage your menu, products, orders, memberships & more.</Text>
            </View>
            <Ionicons name="arrow-forward-circle" size={30} color="#fff" />
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={s.sellCard} onPress={() => router.push('/sell')} testID="shop-sell-cta">
            <View style={{ flex: 1 }}>
              <Text style={s.sellTitle}>Sell on FUUSIC</Text>
              <Text style={s.sellSub}>List your business & reward local customers with BigPoints.</Text>
            </View>
            <Ionicons name="arrow-forward-circle" size={30} color="#fff" />
          </TouchableOpacity>
        )}

        <TouchableOpacity style={s.conciergeCard} onPress={() => router.push('/shop/concierge')} testID="shop-concierge-banner" activeOpacity={0.9}>
          <Ionicons name="sparkles" size={22} color="#fff" />
          <View style={{ flex: 1 }}>
            <Text style={s.sellTitle}>Order by chat ✨</Text>
            <Text style={s.sellSub}>Tell our AI concierge what you want — it applies your memberships automatically.</Text>
          </View>
          <Ionicons name="arrow-forward-circle" size={30} color="#fff" />
        </TouchableOpacity>

        {usual && !usualDismissed && (
          <View style={s.usualCard} testID="shop-usual-card">
            <View style={s.usualHead}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="refresh" size={16} color={t.primary} />
                <Text style={s.usualTitle}>Get your usual</Text>
              </View>
              <TouchableOpacity onPress={() => setUsualDismissed(true)} testID="shop-usual-dismiss">
                <Text style={s.usualDismiss}>Dismiss</Text>
              </TouchableOpacity>
            </View>
            <Text style={s.usualSub}>from {usual.business_name}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, marginTop: 10 }}>
              {(usual.items || []).map((u: any) => (
                <TouchableOpacity key={u.item_id} style={s.usualItem} onPress={() => router.push(`/shop/${usual.business_id}`)} testID={`shop-usual-item-${u.item_id}`}>
                  <View style={s.usualImgWrap}>
                    <Image source={{ uri: u.image_url }} style={s.usualImg} contentFit="cover" transition={150} />
                    <View style={s.usualCount}><Text style={s.usualCountText}>×{u.times_ordered}</Text></View>
                  </View>
                  <Text style={s.usualName} numberOfLines={1}>{u.name}</Text>
                  <Text style={s.usualPrice}>${(u.price_cents / 100).toFixed(2)}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TouchableOpacity style={s.usualBtn} onPress={addUsual} testID="shop-usual-add-all">
              <Text style={s.usualBtnText}>Add my usual ({(usual.items || []).length}) &amp; checkout</Text>
            </TouchableOpacity>
          </View>
        )}

        {liveShows.length > 0 && (
          <View style={{ marginTop: SPACING.lg }} testID="shop-live-shopping">
            <View style={s.liveHead}>
              <View style={s.liveBadge}>
                <View style={s.liveDot} />
                <Text style={s.liveBadgeText}>LIVE</Text>
              </View>
              <Text style={s.sectionTitleInline}>Live Shopping</Text>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 12 }}>
              {liveShows.map((sh) => {
                const isLive = sh.status === 'live';
                return (
                  <Pressable key={sh.show_id} style={s.liveCard} testID={`shop-live-${sh.show_id}`}
                    onPress={() => router.push('/(tabs)/social?tab=live' as any)}>
                    <View style={s.liveCover}>
                      <Image source={{ uri: sh.cover_url }} style={s.cover} contentFit="cover" transition={200} />
                      <View style={[s.liveTag, !isLive && s.upcomingTag]}>
                        {isLive && <View style={s.liveDot} />}
                        <Text style={s.liveTagText}>{isLive ? 'LIVE' : 'UPCOMING'}</Text>
                      </View>
                      {isLive && (
                        <View style={s.liveViewers}>
                          <Ionicons name="eye" size={10} color="#fff" />
                          <Text style={s.liveViewersText}>{sh.viewer_count || 0}</Text>
                        </View>
                      )}
                    </View>
                    <View style={{ padding: 10 }}>
                      <Text style={s.bizName} numberOfLines={1}>{sh.title || 'Live show'}</Text>
                      <Text style={s.bizCat} numberOfLines={1}>{sh.business_name || sh.host?.display_name || 'FUUSIC Live'}</Text>
                    </View>
                  </Pressable>
                );
              })}
            </ScrollView>
          </View>
        )}

        {specials.length > 0 && (
          <View style={{ marginTop: SPACING.lg }} testID="shop-specials-row">
            <Text style={s.sectionTitle}>{"🔥 Today's Specials"}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 12 }}>
              {specials.map((sp) => (
                <TouchableOpacity key={sp.special_id} style={s.specialCard} testID={`shop-special-${sp.special_id}`}
                  onPress={() => router.push(`/shop/${sp.business_id}`)} activeOpacity={0.85}>
                  <View style={s.specialCover}>
                    <Image source={{ uri: sp.image_url }} style={s.cover} contentFit="cover" transition={200} />
                    <View style={s.specialTag}><Text style={s.specialTagText}>SPECIAL</Text></View>
                  </View>
                  <View style={{ padding: 10 }}>
                    <Text style={s.bizName} numberOfLines={1}>{sp.name}</Text>
                    <Text style={s.bizCat} numberOfLines={1}>{sp.business_name}</Text>
                    {!!sp.blurb && <Text style={s.specialBlurb} numberOfLines={1}>{sp.blurb}</Text>}
                    <View style={s.specialPriceRow}>
                      {sp.sale_price_cents != null ? (
                        <>
                          <Text style={s.specialSale}>${(sp.sale_price_cents / 100).toFixed(2)}</Text>
                          <Text style={s.specialWas}>${(sp.price_cents / 100).toFixed(2)}</Text>
                        </>
                      ) : <Text style={s.specialSale}>${(sp.price_cents / 100).toFixed(2)}</Text>}
                    </View>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {sections.map((sec, idx) => (
          <View key={sec.key} style={{ marginTop: SPACING.lg }} testID={`shop-section-${sec.key}`}>
            <Text style={s.sectionTitle}>{idx === 0 ? 'Featured Near You' : sec.title}</Text>
            {sec.subtitle ? (
              <Text style={{ color: t.primary, fontSize: FONT.xs, fontWeight: '700', paddingHorizontal: SPACING.md, marginTop: -2, marginBottom: 4 }} testID={`shop-section-sub-${sec.key}`}>{sec.subtitle}</Text>
            ) : null}
            {idx === 0 ? (
              <View style={s.grid}>
                {sec.items.slice(0, 6).map((b) => (
                  <BizCard key={b.business_id + sec.key} b={b} grid
                    onPress={() => router.push(`/shop/${b.business_id}`)} />
                ))}
              </View>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false}
                contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 12 }}>
                {sec.items.map((b) => (
                  <BizCard key={b.business_id + sec.key} b={b}
                    onPress={() => router.push(`/shop/${b.business_id}`)} />
                ))}
              </ScrollView>
            )}
          </View>
        ))}
      </ScrollView>

      {menuOpen && (
        <View style={s.overlayFill} testID="shop-account-overlay">
          <Pressable style={s.overlayBackdrop} onPress={() => setMenuOpen(false)} />
          <View style={s.sheet} testID="shop-account-menu">
            <View style={s.sheetHandle} />
            <Text style={s.sheetTitle}>My Account</Text>
            {isMerchant && (
              <TouchableOpacity style={s.dashRow} onPress={() => openLink('/merchant/dashboard')} testID="shop-merchant-dash">
                <Ionicons name="grid-outline" size={18} color="#fff" />
                <Text style={s.dashRowText}>Merchant Dashboard</Text>
                <Ionicons name="chevron-forward" size={18} color="#fff" />
              </TouchableOpacity>
            )}
            {ACCOUNT_LINKS.map(([to, icon, label, tid]) => (
              <TouchableOpacity key={to} style={s.linkRow} onPress={() => openLink(to)} testID={tid}>
                <Ionicons name={icon as any} size={18} color={t.primary} />
                <Text style={s.linkRowText}>{label}</Text>
                <Ionicons name="chevron-forward" size={16} color={t.textMuted} />
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

export function BizCard({ b, onPress, wide, grid }: { b: Biz; onPress: () => void; wide?: boolean; grid?: boolean }) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  return (
    <TouchableOpacity style={[s.card, wide && { width: '100%' }, grid && s.cardGrid]} onPress={onPress}
      testID={`shop-biz-${b.business_id}`} activeOpacity={0.85}>
      <View style={[s.coverWrap, grid && s.coverWrapGrid]}>
        <Image source={{ uri: b.cover_url }} style={[s.cover, grid && s.coverGrid]} contentFit="cover" transition={200} />
        {b.promoted ? <View style={s.promotedTag}><Text style={s.sponsoredText}>Promoted</Text></View>
          : b.sponsored ? <View style={s.sponsoredTag}><Text style={s.sponsoredText}>Sponsored</Text></View> : null}
        <View style={s.ptsBadge}>
          <Text style={s.ptsGlyph}>₿</Text>
          <Text style={s.ptsText}>Earn {b.default_bigpoints}</Text>
        </View>
      </View>
      <View style={{ padding: 10 }}>
        <Text style={s.bizName} numberOfLines={1}>{b.public_name}</Text>
        <View style={s.metaRow}>
          <Text style={s.bizCat} numberOfLines={1}>{b.subcategory || b.category}</Text>
          {b.rating ? (
            <View style={s.ratingRow}>
              <Ionicons name="star" size={11} color={t.gold} />
              <Text style={s.ratingText}>{b.rating.toFixed(1)}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: t.bg },
  hero: { paddingHorizontal: SPACING.md, paddingTop: SPACING.lg, paddingBottom: SPACING.sm },
  heroTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  accountBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  eyebrow: { color: t.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  headline: { color: t.text, fontSize: 26, fontWeight: '900', marginTop: 4, marginBottom: 14, lineHeight: 30 },
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: t.card, borderWidth: 1, borderColor: t.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 12 },
  searchInput: { flex: 1, color: t.text, fontSize: FONT.sm, padding: 0 },
  nearMeBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, backgroundColor: t.primary + '12', borderWidth: 1, borderColor: t.primary + '44', borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 11 },
  nearMeText: { flex: 1, color: t.text, fontSize: FONT.sm, fontWeight: '800' },
  catRow: { paddingHorizontal: SPACING.md, gap: 14, paddingVertical: SPACING.sm },
  catChip: { alignItems: 'center', width: 68 },
  catIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: t.primary + '15', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  catLabel: { color: t.textDim, fontSize: 11, fontWeight: '700', textAlign: 'center' },
  filterRow: { paddingHorizontal: SPACING.md, gap: 8, paddingBottom: SPACING.sm },
  filterChip: { flexShrink: 0, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: t.inputBg, borderWidth: 1, borderColor: t.surfaceBorder },
  filterText: { color: t.textDim, fontSize: FONT.xs, fontWeight: '700' },
  sellCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.primary, borderRadius: RADIUS.lg, padding: 16 },
  dashCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#1f2430', borderRadius: RADIUS.lg, padding: 16 },
  conciergeCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.primary, borderRadius: RADIUS.lg, padding: 16 },
  usualCard: { marginHorizontal: SPACING.md, marginTop: SPACING.md, backgroundColor: t.primary + '10', borderWidth: 1, borderColor: t.primary + '33', borderRadius: RADIUS.lg, padding: 14 },
  usualHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  usualTitle: { color: t.text, fontSize: FONT.md, fontWeight: '900' },
  usualDismiss: { color: t.textMuted, fontSize: FONT.xs, fontWeight: '900' },
  usualSub: { color: t.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  usualItem: { width: 104, backgroundColor: t.card, borderWidth: 1, borderColor: t.primary + '33', borderRadius: RADIUS.md, overflow: 'hidden' },
  usualImgWrap: { position: 'relative', width: '100%', height: 72, backgroundColor: t.inputBg },
  usualImg: { width: '100%', height: '100%' },
  usualCount: { position: 'absolute', top: 6, right: 6, backgroundColor: t.primary, borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 2 },
  usualCountText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  usualName: { color: t.text, fontSize: FONT.xs, fontWeight: '800', paddingHorizontal: 8, paddingTop: 6 },
  usualPrice: { color: t.text, fontSize: FONT.xs, fontWeight: '900', paddingHorizontal: 8, paddingBottom: 8, paddingTop: 2 },
  usualBtn: { backgroundColor: t.primary, borderRadius: RADIUS.full, paddingVertical: 12, alignItems: 'center', marginTop: 12 },
  usualBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  sellTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  sellSub: { color: '#fff', opacity: 0.9, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  overlayFill: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'flex-end' },
  overlayBackdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)' },
  sheet: { backgroundColor: t.card, borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 34 },
  sheetHandle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: t.surfaceBorder, marginBottom: 12 },
  sheetTitle: { color: t.text, fontSize: FONT.lg, fontWeight: '900', marginBottom: 10 },
  dashRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.primary, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 14, marginBottom: 8 },
  dashRowText: { flex: 1, color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: t.surfaceBorder },
  linkRowText: { flex: 1, color: t.text, fontSize: FONT.md, fontWeight: '700' },
  specialCard: { width: 176, backgroundColor: t.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: t.primary + '44', overflow: 'hidden' },
  specialCover: { height: 96, backgroundColor: t.inputBg },
  specialTag: { position: 'absolute', top: 8, left: 8, backgroundColor: t.primary, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  specialTagText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  specialBlurb: { color: t.primary, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  specialPriceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6, marginTop: 4 },
  specialSale: { color: t.text, fontSize: FONT.sm, fontWeight: '900' },
  specialWas: { color: t.textMuted, fontSize: FONT.xs, fontWeight: '700', textDecorationLine: 'line-through' },
  sectionTitle: { color: t.text, fontSize: FONT.lg, fontWeight: '900', paddingHorizontal: SPACING.md, marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', paddingHorizontal: SPACING.md, rowGap: 12 },
  liveHead: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: SPACING.md, marginBottom: 10 },
  liveBadge: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: t.live || '#E02020', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3 },
  liveBadgeText: { color: '#fff', fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#fff' },
  sectionTitleInline: { color: t.text, fontSize: FONT.lg, fontWeight: '900' },
  liveCard: { width: 176, backgroundColor: t.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, overflow: 'hidden' },
  liveCover: { position: 'relative', height: 112, backgroundColor: t.inputBg },
  liveTag: { position: 'absolute', top: 8, left: 8, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: t.live || '#E02020', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3 },
  upcomingTag: { backgroundColor: t.primary },
  liveTagText: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 0.3 },
  liveViewers: { position: 'absolute', bottom: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(0,0,0,0.55)', borderRadius: RADIUS.full, paddingHorizontal: 7, paddingVertical: 3 },
  liveViewersText: { color: '#fff', fontSize: 9, fontWeight: '800' },
  card: { width: 220, backgroundColor: t.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, overflow: 'hidden' },
  cardGrid: { width: '48%' },
  coverWrap: { position: 'relative' },
  coverWrapGrid: {},
  cover: { width: '100%', height: 120, backgroundColor: t.inputBg },
  coverGrid: { aspectRatio: 1, height: undefined },
  sponsoredTag: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  promotedTag: { position: 'absolute', top: 8, left: 8, backgroundColor: t.primary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  sponsoredText: { color: '#fff', fontSize: 9, fontWeight: '800' },
  ptsBadge: { position: 'absolute', bottom: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: t.gold, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  ptsGlyph: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  ptsText: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  bizName: { color: t.text, fontSize: FONT.sm, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 3 },
  bizCat: { color: t.textMuted, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  ratingText: { color: t.textDim, fontSize: FONT.xs, fontWeight: '800' },
});
