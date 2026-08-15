// Business / restaurant detail — RadioLife Shop (mobile).
// Full inline ordering surface (parity with the web store page): instant "+"
// add, per-item Customize sheet, in-cart badge + stepper, combo badges,
// "Get your usual" + Reorder-last, save-for-later, and a floating cart bar.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';
import { useCartStore } from '../../src/stores/useCartStore';
import { useProductCart } from '../../src/stores/useProductCart';
import { useSavedForLater } from '../../src/stores/useSavedForLater';
import ItemOptionSheet, { defaultMenuSelection, menuQuickAddReady } from '../../src/components/ItemOptionSheet';
import ProductVariantSheet from '../../src/components/ProductVariantSheet';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);
const EARN_ICON: Record<string, any> = { 'bag-check': 'bag-check', location: 'location', wallet: 'wallet' };
const lc = (s?: string | null) => (s || '').toLowerCase();

export default function BusinessDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { celebrate } = useReward();
  const [biz, setBiz] = useState<any>(null);
  const [groups, setGroups] = useState<any[]>([]);
  const [cat, setCat] = useState('all');
  const [loading, setLoading] = useState(true);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checking, setChecking] = useState(false);
  const [ents, setEnts] = useState<any[]>([]);
  const [combos, setCombos] = useState<any[]>([]);
  const [usual, setUsual] = useState<any[] | null>(null);
  const [usualDismissed, setUsualDismissed] = useState(false);
  const [lastOrder, setLastOrder] = useState<any>(null);
  const [sheetItem, setSheetItem] = useState<any>(null);
  const [variantProduct, setVariantProduct] = useState<any>(null);

  const menuCart = useCartStore();
  const productCart = useProductCart();
  const savedCount = useSavedForLater((st) => (st.byBiz[id!] || []).length);

  const mode = useMemo(() => {
    if (!biz) return 'other';
    const sells: string[] = biz.sells || [];
    if (sells.includes('menu') || biz.has_menu) return 'menu';
    if (sells.includes('products') || biz.has_products) return 'product';
    return 'other';
  }, [biz]);
  const orderable = mode === 'menu' || mode === 'product';

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await api.get(`/shop/businesses/${id}`);
        if (!alive) return;
        const b = r.data.business;
        setBiz(b);
        api.post('/shop/track', { business_id: id, kind: 'view' }).catch(() => {});
        const sells: string[] = b.sells || [];
        if (sells.includes('menu') || b.has_menu) {
          const m = await api.get(`/shop/businesses/${id}/menu`);
          const secs = (m.data.sections || []).map((sec: any, i: number) => ({
            key: `sec-${i}`, title: sec.title,
            items: (sec.items || []).map((it: any) => ({
              id: it.item_id, name: it.name, price_cents: it.price_cents,
              image_url: it.image_url, kind: 'menu', hasVariants: (it.option_groups || []).length > 0, raw: it,
            })),
          }));
          if (alive) setGroups(secs);
        } else if (b.has_products || sells.includes('products')) {
          const pr = await api.get(`/shop/businesses/${id}/products`);
          const byCat: Record<string, any[]> = {};
          (pr.data.products || []).forEach((p: any) => {
            const c = p.category || 'All';
            (byCat[c] = byCat[c] || []).push({
              id: p.product_id, name: p.name, price_cents: p.price_cents,
              image_url: p.image_url, kind: 'product', hasVariants: (p.variants || []).length > 0, raw: p,
            });
          });
          if (alive) setGroups(Object.keys(byCat).map((c, i) => ({ key: `cat-${i}`, title: c, items: byCat[c] })));
        }
      } catch { if (alive) setBiz(null); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [id]);

  // Menu-only extras: entitlements (for the sheet), combos, usual, last order.
  useEffect(() => {
    if (mode !== 'menu') { setEnts([]); setCombos([]); setUsual(null); setLastOrder(null); return; }
    let alive = true;
    api.get(`/shop/businesses/${id}/my-entitlements`).then((r) => { if (alive) setEnts(r.data.items || []); }).catch(() => {});
    api.get(`/shop/businesses/${id}/combos`).then((r) => { if (alive) setCombos(r.data?.combos || []); }).catch(() => {});
    api.get(`/shop/businesses/${id}/usual`).then((r) => { if (alive && r.data?.has_usual) setUsual(r.data.items || []); }).catch(() => {});
    api.get(`/shop/orders/last/${id}`).then((r) => { if (alive && r.data?.has_order && (r.data.items || []).length) setLastOrder(r.data); }).catch(() => {});
    return () => { alive = false; };
  }, [id, mode]);

  const itemEnt = useMemo(() => {
    const rank = (t: string) => (t === 'item' || t === 'product' ? 3 : t === 'category' ? 2 : 1);
    const map: Record<string, any> = {};
    ents.forEach((e) => {
      if (e.remaining <= 0 || !e.available_now) return;
      (e.eligible_items || []).forEach((it: any) => {
        if (!map[it.id] || rank(e.target_type) > rank(map[it.id].target_type)) map[it.id] = e;
      });
    });
    return map;
  }, [ents]);

  const allItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const shown = useMemo(
    () => (cat === 'all' ? allItems : (groups.find((g) => g.key === cat)?.items || [])),
    [cat, groups, allItems]);

  // Combo badge — item's section matches an active combo requirement category.
  const sectionByItem = useMemo(() => {
    const m: Record<string, string> = {};
    groups.forEach((g) => g.items.forEach((it: any) => { m[it.id] = g.title || ''; }));
    return m;
  }, [groups]);
  const comboCats = useMemo(
    () => combos.filter((c) => c.active_now !== false).flatMap((c) => (c.requirements || []).map((r: any) => lc(r.category))),
    [combos]);
  const isComboItem = (it: any) => mode === 'menu' && comboCats.some((c) => c && lc(sectionByItem[it.id]).includes(c));

  // In-cart quantity per item.
  const menuLines = menuCart.businessId === id ? menuCart.items : [];
  const productItems = productCart.groups[id!]?.items || [];
  const qtyFor = (it: any) => it.kind === 'product'
    ? productItems.filter((i) => i.product_id === it.id).reduce((n, i) => n + i.qty, 0)
    : menuLines.filter((l) => l.item_id === it.id).reduce((n, l) => n + l.qty, 0);
  const isPlain = (it: any) => !it.hasVariants && !(it.kind === 'menu' && itemEnt[it.id]);
  const plainInc = (it: any) => it.kind === 'product' ? productCart.inc(id!, it.id) : menuCart.inc(`${it.id}::::`);
  const plainDec = (it: any) => it.kind === 'product' ? productCart.dec(id!, it.id) : menuCart.dec(`${it.id}::::`);

  // ── Ordering actions ──
  const quickAddMenu = (raw: any) => {
    if ((raw.option_groups || []).length > 0 || itemEnt[raw.item_id] || !menuQuickAddReady(raw)) { setSheetItem(raw); return; }
    const sel = defaultMenuSelection(raw);
    menuCart.addLine(id!, biz.public_name, {
      item_id: raw.item_id, name: raw.name, price_cents: sel.unit_price_cents,
      selected_option_ids: sel.selected_option_ids, option_summary: sel.option_summary,
    });
  };
  const quickAddProduct = (raw: any) => {
    const variants = raw.variants || [];
    if (variants.length) {
      const v = variants.find((x: any) => x.stock > 0);
      if (!v) return;
      productCart.add(id!, biz.public_name, raw, v, biz.delivery);
    } else {
      if (raw.stock <= 0) return;
      productCart.add(id!, biz.public_name, raw, null, biz.delivery);
    }
  };
  const onPlus = (it: any) => (it.kind === 'product' ? quickAddProduct(it.raw) : quickAddMenu(it.raw));
  const onCustomize = (it: any) => (it.kind === 'product' ? setVariantProduct(it.raw) : setSheetItem(it.raw));

  const reorderLast = () => {
    if (!lastOrder?.items?.length) return;
    lastOrder.items.forEach((li: any) => menuCart.addLine(id!, biz.public_name, {
      item_id: li.item_id, name: li.name, price_cents: li.price_cents,
      selected_option_ids: li.selected_option_ids || [], option_summary: li.option_summary, note: li.note, qty: li.qty || 1,
    }));
  };
  const addUsual = () => {
    if (!usual?.length) return;
    usual.forEach((u) => menuCart.addLine(id!, biz.public_name, {
      item_id: u.item_id, name: u.name, price_cents: u.price_cents,
      selected_option_ids: u.selected_option_ids || [], option_summary: u.option_summary, note: u.note,
    }));
    setUsualDismissed(true);
  };

  const doCheckin = async () => {
    if (checkedIn || checking) return;
    setChecking(true);
    try {
      const r = await api.post(`/shop/businesses/${id}/checkin`);
      setCheckedIn(true);
      if (!r.data.already) celebrate({ points: r.data.awarded, title: 'Checked in! 🎉' });
    } catch { /* ignore */ }
    finally { setChecking(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!biz) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Business not found.</Text></View>;

  const ways: any[] = biz.ways_to_earn || [];
  const cartCount = mode === 'product'
    ? productItems.reduce((n, i) => n + i.qty, 0)
    : (menuCart.businessId === id ? menuCart.count() : 0);
  const cartSubtotal = mode === 'product'
    ? productItems.reduce((n, i) => n + i.price_cents * i.qty, 0)
    : (menuCart.businessId === id ? menuCart.subtotal() : 0);
  const reviewPath = mode === 'product' ? '/shop/product-cart' : '/shop/cart';

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: cartCount > 0 ? 150 : 40 }} testID="shop-detail-root">
        <View>
          <Image source={{ uri: biz.cover_url }} style={s.cover} contentFit="cover" transition={200} />
          <TouchableOpacity style={s.backBtn} onPress={() => router.back()} testID="shop-detail-back">
            <Ionicons name="chevron-back" size={22} color="#fff" />
          </TouchableOpacity>
        </View>

        <View style={{ padding: SPACING.md }}>
          <View style={s.titleRow}>
            <Text style={s.name}>{biz.public_name}</Text>
            {biz.rating ? (
              <View style={s.ratingPill}>
                <Ionicons name="star" size={12} color={COLORS.gold} />
                <Text style={s.ratingText}>{biz.rating.toFixed(1)}</Text>
              </View>
            ) : null}
          </View>
          <Text style={s.cat}>{biz.subcategory || biz.category}{biz.city ? ` · ${biz.city}` : ''}</Text>
          {!!biz.description && <Text style={s.desc}>{biz.description}</Text>}

          {/* Ways to earn — single bar */}
          {ways.length > 0 && (
            <View style={s.earnBar} testID="shop-earn-bar">
              {ways.map((w, i) => {
                const isCheckin = (w.label || '').toLowerCase().includes('check');
                const cell = (
                  <>
                    <Ionicons name={(EARN_ICON[w.icon] || 'star') as any} size={16}
                      color={isCheckin && checkedIn ? COLORS.green : COLORS.primary} />
                    <Text style={s.earnLabel} numberOfLines={1}>{w.label}</Text>
                    <Text style={[s.earnPts, isCheckin && checkedIn && { color: COLORS.green }]}>
                      {isCheckin && checkedIn ? '✓ Done' : `+${w.points}`}
                    </Text>
                  </>
                );
                return isCheckin ? (
                  <TouchableOpacity key={i} style={[s.earnCell, i > 0 && s.earnDivider, { backgroundColor: checkedIn ? COLORS.green + '14' : COLORS.primary + '0d' }]}
                    onPress={doCheckin} disabled={checking} testID="shop-checkin-btn">{cell}</TouchableOpacity>
                ) : (
                  <View key={i} style={[s.earnCell, i > 0 && s.earnDivider]} testID={`shop-earn-${i}`}>{cell}</View>
                );
              })}
            </View>
          )}

          {/* Action chips — reorder / saved / extras */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.actionRow} testID="shop-detail-actions">
            {mode === 'menu' && lastOrder && (
              <TouchableOpacity style={[s.actChip, s.actChipHot]} onPress={reorderLast} testID="shop-reorder-last">
                <Ionicons name="refresh" size={14} color={COLORS.primary} />
                <Text style={[s.actChipText, { color: COLORS.primary }]}>Reorder last</Text>
              </TouchableOpacity>
            )}
            {savedCount > 0 && (
              <TouchableOpacity style={s.actChip} onPress={() => router.push(reviewPath as any)} testID="shop-saved-pill">
                <Ionicons name="bookmark" size={14} color={COLORS.primary} />
                <Text style={s.actChipText}>{savedCount} saved</Text>
              </TouchableOpacity>
            )}
            {biz.has_giftcards && (
              <TouchableOpacity style={s.actChip} onPress={() => router.push(`/shop/giftcards/${biz.business_id}` as any)} testID="shop-detail-giftcard">
                <Ionicons name="gift" size={14} color={COLORS.primary} /><Text style={s.actChipText}>Gift card</Text>
              </TouchableOpacity>
            )}
            {biz.has_packages && (
              <TouchableOpacity style={s.actChip} onPress={() => router.push(`/shop/packages/${biz.business_id}` as any)} testID="shop-detail-package">
                <Ionicons name="cube" size={14} color={COLORS.primary} /><Text style={s.actChipText}>Packages</Text>
              </TouchableOpacity>
            )}
            {biz.has_events && (
              <TouchableOpacity style={s.actChip} onPress={() => router.push(`/shop/events/${biz.business_id}` as any)} testID="shop-detail-event">
                <Ionicons name="calendar" size={14} color={COLORS.secondary} /><Text style={s.actChipText}>Events</Text>
              </TouchableOpacity>
            )}
            {biz.has_memberships && (
              <TouchableOpacity style={[s.actChip, s.actChipGold]} onPress={() => router.push(`/shop/memberships/${biz.business_id}` as any)} testID="shop-detail-membership">
                <Ionicons name="ribbon" size={14} color={COLORS.gold} /><Text style={[s.actChipText, { color: COLORS.gold }]}>Membership</Text>
              </TouchableOpacity>
            )}
          </ScrollView>

          {/* Get your usual? */}
          {mode === 'menu' && usual && !usualDismissed && (
            <View style={s.usualCard} testID="usual-card">
              <View style={s.usualHead}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name="refresh" size={15} color={COLORS.primary} />
                  <Text style={s.usualTitle}>Get your usual?</Text>
                </View>
                <TouchableOpacity onPress={() => setUsualDismissed(true)} testID="usual-dismiss"><Text style={s.usualDismiss}>Dismiss</Text></TouchableOpacity>
              </View>
              <View style={s.usualChips}>
                {usual.map((u) => (
                  <View key={u.item_id} style={s.usualChip}><Text style={s.usualChipText}>{u.name} ×{u.times_ordered}</Text></View>
                ))}
              </View>
              <TouchableOpacity style={s.usualBtn} onPress={addUsual} testID="usual-add-all">
                <Text style={s.usualBtnText}>Add my usual ({usual.length})</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Category filter */}
        {groups.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.catRow} testID="shop-cat-rail">
            <TouchableOpacity onPress={() => setCat('all')} style={[s.chip, cat === 'all' && s.chipOn]} testID="shop-cat-all">
              <Text style={[s.chipText, cat === 'all' && s.chipTextOn]}>All</Text>
            </TouchableOpacity>
            {groups.map((g) => (
              <TouchableOpacity key={g.key} onPress={() => setCat(g.key)} style={[s.chip, cat === g.key && s.chipOn]} testID={`shop-cat-${g.key}`}>
                <Text style={[s.chipText, cat === g.key && s.chipTextOn]}>{g.title}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}

        {/* Item grid — inline ordering */}
        {groups.length > 0 ? (
          <View style={s.grid} testID="shop-item-grid">
            {shown.map((it: any) => {
              const qn = orderable ? qtyFor(it) : 0;
              const plain = isPlain(it);
              return (
                <View key={it.id} style={s.card} testID={`shop-item-${it.id}`}>
                  <View style={s.cardImgWrap}>
                    <Image source={{ uri: absUrl(it.image_url) || undefined }} style={s.cardImg} contentFit="cover" transition={150} />
                    {isComboItem(it) && (
                      <View style={s.comboBadge} testID={`shop-combo-badge-${it.id}`}>
                        <Text style={s.comboBadgeText}>🍔 Combo</Text>
                      </View>
                    )}
                    {qn > 0 && (
                      <View style={s.incartBadge} testID={`shop-incart-${it.id}`}>
                        <Ionicons name="checkmark" size={11} color="#fff" />
                        <Text style={s.incartText}>{qn}</Text>
                      </View>
                    )}
                    {orderable && (
                      <TouchableOpacity style={s.customizeBtn} onPress={() => onCustomize(it)} testID={`shop-customize-${it.id}`}>
                        <Ionicons name="options" size={12} color={COLORS.primary} />
                        <Text style={s.customizeText}>Customize</Text>
                      </TouchableOpacity>
                    )}
                    {orderable && qn > 0 && plain ? (
                      <View style={s.cardStepper} testID={`shop-stepper-${it.id}`}>
                        <TouchableOpacity onPress={() => plainDec(it)} style={s.cardStepBtn} testID={`shop-dec-${it.id}`}><Ionicons name="remove" size={15} color={COLORS.primary} /></TouchableOpacity>
                        <Text style={s.cardStepQty}>{qn}</Text>
                        <TouchableOpacity onPress={() => plainInc(it)} style={s.cardStepBtn} testID={`shop-inc-${it.id}`}><Ionicons name="add" size={15} color={COLORS.primary} /></TouchableOpacity>
                      </View>
                    ) : (
                      <TouchableOpacity style={s.addFab} onPress={() => (orderable ? onPlus(it) : router.push(`/shop/menu/${biz.business_id}` as any))} testID={`shop-add-${it.id}`}>
                        <Ionicons name="add" size={18} color="#fff" />
                      </TouchableOpacity>
                    )}
                  </View>
                  <Text style={s.itemName} numberOfLines={1}>{it.name}</Text>
                  <Text style={s.itemPrice}>{money(it.price_cents)}{it.hasVariants ? '+' : ''}</Text>
                </View>
              );
            })}
          </View>
        ) : (
          <View style={{ paddingHorizontal: SPACING.md }}>
            <View style={s.earnBadge}>
              <Text style={s.earnGlyph}>₿</Text>
              <Text style={s.earnBadgeText}>Earn {biz.default_bigpoints} BigPoints here</Text>
            </View>
          </View>
        )}

        {/* Contact */}
        {(biz.phone || biz.website) && (
          <View style={{ paddingHorizontal: SPACING.md, marginTop: 14 }}>
            {!!biz.phone && (
              <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(`tel:${biz.phone}`)}>
                <Ionicons name="call" size={16} color={COLORS.primary} />
                <Text style={s.contactText}>{biz.phone}</Text>
              </TouchableOpacity>
            )}
            {!!biz.website && (
              <TouchableOpacity style={s.contactRow} onPress={() => Linking.openURL(biz.website)}>
                <Ionicons name="globe" size={16} color={COLORS.primary} />
                <Text style={s.contactText} numberOfLines={1}>{biz.website}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>

      {/* Non-orderable stores keep an explicit Order CTA */}
      {!orderable && (
        <View style={s.actions}>
          <TouchableOpacity style={s.orderPill} onPress={() => router.push(`/shop/services/${biz.business_id}` as any)} testID="shop-detail-cta">
            <Ionicons name="bag-handle" size={16} color="#fff" />
            <Text style={s.orderPillText}>Order · Earn {biz.default_bigpoints}</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Floating cart bar */}
      {orderable && cartCount > 0 && (
        <View style={s.cartBarWrap}>
          <TouchableOpacity style={s.cartBar} onPress={() => router.push(reviewPath as any)} testID="shop-mobile-cart-bar">
            <Ionicons name="cart" size={16} color="#fff" />
            <Text style={s.cartBarText}>View order ({cartCount}) · {money(cartSubtotal)}</Text>
          </TouchableOpacity>
        </View>
      )}

      {sheetItem && (
        <ItemOptionSheet
          item={sheetItem}
          entitlement={itemEnt[sheetItem.item_id] || null}
          notePresets={biz.note_presets || []}
          onClose={() => setSheetItem(null)}
          onConfirm={(sel: any) => {
            menuCart.addLine(id!, biz.public_name, {
              item_id: sheetItem.item_id, name: sheetItem.name, price_cents: sel.unit_price_cents,
              qty: sel.qty, selected_option_ids: sel.selected_option_ids, option_summary: sel.option_summary,
              note: sel.note, apply_entitlement_id: sel.apply_entitlement_id, entitlement_label: sel.entitlement_label,
            });
            setSheetItem(null);
          }}
        />
      )}
      {variantProduct && (
        <ProductVariantSheet
          product={variantProduct}
          onClose={() => setVariantProduct(null)}
          onConfirm={({ variant, qty, note }: any) => {
            productCart.add(id!, biz.public_name, variantProduct, variant, biz.delivery, qty, note);
            setVariantProduct(null);
          }}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  cover: { width: '100%', height: 200, backgroundColor: COLORS.inputBg },
  backBtn: { position: 'absolute', top: 12, left: 12, width: 38, height: 38, borderRadius: 19, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { color: COLORS.text, fontSize: 24, fontWeight: '900', flex: 1 },
  ratingPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  ratingText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cat: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '700', marginTop: 3, textTransform: 'capitalize' },
  desc: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20, marginTop: 12 },
  earnBar: { flexDirection: 'row', marginTop: 14, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, overflow: 'hidden' },
  earnCell: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 12, paddingHorizontal: 4 },
  earnDivider: { borderLeftWidth: 1, borderLeftColor: COLORS.cardBorder },
  earnLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', marginTop: 5, textAlign: 'center' },
  earnPts: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginTop: 2 },
  actionRow: { gap: 8, paddingVertical: 12 },
  actChip: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 8, flexShrink: 0 },
  actChipHot: { borderWidth: 2, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  actChipGold: { borderWidth: 2, borderColor: COLORS.gold, backgroundColor: COLORS.gold + '14' },
  actChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '900' },
  usualCard: { backgroundColor: COLORS.primary + '10', borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.lg, padding: 12, marginTop: 4 },
  usualHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  usualTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  usualDismiss: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900' },
  usualChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  usualChip: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 5 },
  usualChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  usualBtn: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 11, alignItems: 'center', marginTop: 10 },
  usualBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  catRow: { paddingHorizontal: SPACING.md, gap: 8, paddingBottom: 6 },
  chip: { flexShrink: 0, height: 36, justifyContent: 'center', paddingHorizontal: 16, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  chipTextOn: { color: '#fff' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', paddingHorizontal: SPACING.md, marginTop: 10, gap: 12 },
  card: { width: '47%', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, overflow: 'hidden', marginBottom: 4 },
  cardImgWrap: { position: 'relative', width: '100%', aspectRatio: 1, backgroundColor: COLORS.inputBg },
  cardImg: { width: '100%', height: '100%' },
  comboBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3 },
  comboBadgeText: { color: '#fff', fontSize: 10, fontWeight: '900' },
  incartBadge: { position: 'absolute', top: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3 },
  incartText: { color: '#fff', fontSize: 11, fontWeight: '900' },
  customizeBtn: { position: 'absolute', bottom: 8, left: 8, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(255,255,255,0.95)', borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 5 },
  customizeText: { color: COLORS.text, fontSize: 10, fontWeight: '900' },
  cardStepper: { position: 'absolute', bottom: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#fff', borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 4, paddingVertical: 3 },
  cardStepBtn: { width: 26, height: 26, borderRadius: 13, backgroundColor: COLORS.primary + '12', alignItems: 'center', justifyContent: 'center' },
  cardStepQty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', minWidth: 14, textAlign: 'center' },
  addFab: { position: 'absolute', bottom: 8, right: 8, width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', paddingHorizontal: 10, paddingTop: 8 },
  itemPrice: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', paddingHorizontal: 10, paddingTop: 2, paddingBottom: 10 },
  earnBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: COLORS.gold + '1f', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, marginTop: 6 },
  earnGlyph: { color: COLORS.gold, fontSize: 15, fontWeight: '900' },
  earnBadgeText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  contactRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8 },
  contactText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '700', flex: 1 },
  actions: { position: 'absolute', right: 14, bottom: 22, alignItems: 'flex-end', gap: 10 },
  orderPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 18, paddingVertical: 13, shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  orderPillText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  cartBarWrap: { position: 'absolute', bottom: 22, left: SPACING.md, right: SPACING.md },
  cartBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 15, shadowColor: '#000', shadowOpacity: 0.3, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  cartBarText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
