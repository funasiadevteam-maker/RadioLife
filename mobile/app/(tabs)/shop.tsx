// Shop Home — RadioLife Super Marketplace consumer entry.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, TextInput, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useCartStore } from '../../src/stores/useCartStore';

interface Biz {
  business_id: string; public_name: string; category: string; subcategory?: string;
  cover_url?: string; default_bigpoints: number; rating?: number;
  featured?: boolean; sponsored?: boolean;
}
interface Section { key: string; title: string; items: Biz[]; }
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
  const menuCart = useCartStore();

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
  useEffect(() => {
    // Role-gate merchant tools — only business owners see the dashboard.
    api.get('/merchant/marketplace/profile')
      .then((r) => setIsMerchant(!!r.data?.profile))
      .catch(() => setIsMerchant(false));
    // "Get your usual" one-tap for returning customers (auth-only; 401 → hide).
    api.get('/shop/usual')
      .then((r) => { if (r.data?.has_usual) setUsual(r.data); })
      .catch(() => setUsual(null));
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

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: 90 }} testID="shop-home-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        <View style={s.hero}>
          <View style={s.heroTop}>
            <Text style={s.eyebrow}>RADIOLIFE SHOP</Text>
            <TouchableOpacity style={s.accountBtn} onPress={() => setMenuOpen(true)} testID="shop-account-button">
              <Ionicons name="person-circle-outline" size={26} color={COLORS.text} />
            </TouchableOpacity>
          </View>
          <Text style={s.headline}>{headline}</Text>
          <View style={s.searchBar}>
            <Ionicons name="search" size={18} color={COLORS.textMuted} />
            <TextInput style={s.searchInput} value={query} onChangeText={setQuery}
              placeholder="What are you looking for?" placeholderTextColor={COLORS.textMuted}
              returnKeyType="search" onSubmitEditing={goSearch} testID="shop-search-input" />
          </View>
          <TouchableOpacity style={s.nearMeBtn} onPress={() => router.push('/shop/near-me')} testID="shop-near-me">
            <Ionicons name="navigate" size={16} color={COLORS.primary} />
            <Text style={s.nearMeText}>Explore shops &amp; services near you</Text>
            <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
          </TouchableOpacity>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.catRow} testID="shop-categories">
          {cats.map((c) => (
            <TouchableOpacity key={c.key} style={s.catChip} testID={`shop-cat-${c.key}`}
              onPress={() => router.push({ pathname: '/shop/browse', params: { category: c.key } })}>
              <View style={s.catIcon}>
                <Ionicons name={(c.icon || 'storefront') as any} size={20} color={COLORS.primary} />
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
              <Text style={s.sellTitle}>Sell on RadioLife</Text>
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
                <Ionicons name="refresh" size={16} color={COLORS.primary} />
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

        {sections.map((sec) => (
          <View key={sec.key} style={{ marginTop: SPACING.lg }} testID={`shop-section-${sec.key}`}>
            <Text style={s.sectionTitle}>{sec.title}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 12 }}>
              {sec.items.map((b) => (
                <BizCard key={b.business_id + sec.key} b={b}
                  onPress={() => router.push(`/shop/${b.business_id}`)} />
              ))}
            </ScrollView>
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
                <Ionicons name={icon as any} size={18} color={COLORS.primary} />
                <Text style={s.linkRowText}>{label}</Text>
                <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            ))}
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

export function BizCard({ b, onPress, wide }: { b: Biz; onPress: () => void; wide?: boolean }) {
  return (
    <TouchableOpacity style={[s.card, wide && { width: '100%' }]} onPress={onPress}
      testID={`shop-biz-${b.business_id}`} activeOpacity={0.85}>
      <View style={s.coverWrap}>
        <Image source={{ uri: b.cover_url }} style={s.cover} contentFit="cover" transition={200} />
        {b.sponsored && <View style={s.sponsoredTag}><Text style={s.sponsoredText}>Sponsored</Text></View>}
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
              <Ionicons name="star" size={11} color={COLORS.gold} />
              <Text style={s.ratingText}>{b.rating.toFixed(1)}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  hero: { paddingHorizontal: SPACING.md, paddingTop: SPACING.lg, paddingBottom: SPACING.sm },
  heroTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  accountBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  eyebrow: { color: COLORS.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  headline: { color: COLORS.text, fontSize: 26, fontWeight: '900', marginTop: 4, marginBottom: 14, lineHeight: 30 },
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 12 },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.sm, padding: 0 },
  nearMeBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, backgroundColor: COLORS.primary + '12', borderWidth: 1, borderColor: COLORS.primary + '44', borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 11 },
  nearMeText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  catRow: { paddingHorizontal: SPACING.md, gap: 14, paddingVertical: SPACING.sm },
  catChip: { alignItems: 'center', width: 68 },
  catIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  catLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', textAlign: 'center' },
  filterRow: { paddingHorizontal: SPACING.md, gap: 8, paddingBottom: SPACING.sm },
  filterChip: { flexShrink: 0, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  filterText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  sellCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: 16 },
  dashCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#1f2430', borderRadius: RADIUS.lg, padding: 16 },
  conciergeCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: 16 },
  usualCard: { marginHorizontal: SPACING.md, marginTop: SPACING.md, backgroundColor: COLORS.primary + '10', borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.lg, padding: 14 },
  usualHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  usualTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  usualDismiss: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900' },
  usualSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  usualItem: { width: 104, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.md, overflow: 'hidden' },
  usualImgWrap: { position: 'relative', width: '100%', height: 72, backgroundColor: COLORS.inputBg },
  usualImg: { width: '100%', height: '100%' },
  usualCount: { position: 'absolute', top: 6, right: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 2 },
  usualCountText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  usualName: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800', paddingHorizontal: 8, paddingTop: 6 },
  usualPrice: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '900', paddingHorizontal: 8, paddingBottom: 8, paddingTop: 2 },
  usualBtn: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 12, alignItems: 'center', marginTop: 12 },
  usualBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  sellTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  sellSub: { color: '#fff', opacity: 0.9, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  overlayFill: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'flex-end' },
  overlayBackdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)' },
  sheet: { backgroundColor: COLORS.card, borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 34 },
  sheetHandle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: COLORS.surfaceBorder, marginBottom: 12 },
  sheetTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginBottom: 10 },
  dashRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 14, marginBottom: 8 },
  dashRowText: { flex: 1, color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  linkRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14, paddingHorizontal: 4, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  linkRowText: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  specialCard: { width: 176, backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary + '44', overflow: 'hidden' },
  specialCover: { height: 96, backgroundColor: COLORS.inputBg },
  specialTag: { position: 'absolute', top: 8, left: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  specialTagText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  specialBlurb: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  specialPriceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6, marginTop: 4 },
  specialSale: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  specialWas: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', textDecorationLine: 'line-through' },
  sectionTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', paddingHorizontal: SPACING.md, marginBottom: 10 },
  card: { width: 220, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, overflow: 'hidden' },
  coverWrap: { position: 'relative' },
  cover: { width: '100%', height: 120, backgroundColor: COLORS.inputBg },
  sponsoredTag: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  sponsoredText: { color: '#fff', fontSize: 9, fontWeight: '800' },
  ptsBadge: { position: 'absolute', bottom: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.gold, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  ptsGlyph: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  ptsText: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  bizName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 3 },
  bizCat: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  ratingText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
});
