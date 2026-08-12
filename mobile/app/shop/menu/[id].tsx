// Consumer restaurant menu (mobile) — sizes/modifiers + apply membership.
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useCartStore } from '../../../src/stores/useCartStore';
import ItemOptionSheet from '../../../src/components/ItemOptionSheet';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);

export default function BusinessMenu() {
  const router = useRouter();
  const { id, item: preItem } = useLocalSearchParams<{ id: string; item?: string; apply_entitlement?: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [ents, setEnts] = useState<any[]>([]);
  const [sheetItem, setSheetItem] = useState<any>(null);
  const cart = useCartStore();

  const load = useCallback(async () => {
    try { const r = await api.get(`/shop/businesses/${id}/menu`); setData(r.data); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get(`/shop/businesses/${id}/my-entitlements`).then((r) => setEnts(r.data.items || [])).catch(() => setEnts([]));
  }, [id]);

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

  // Deep-link from wallet: auto-open a specific item.
  useEffect(() => {
    if (!data || !preItem) return;
    const found = (data.sections || []).flatMap((s: any) => s.items).find((it: any) => it.item_id === preItem);
    if (found) setSheetItem(found);
  }, [data, ents, preItem]);

  const sameBiz = cart.businessId === id;
  const plainQty = (itemId: string) => sameBiz
    ? cart.items.filter((i) => i.item_id === itemId && !i.selected_option_ids?.length && !i.apply_entitlement_id).reduce((n, i) => n + i.qty, 0) : 0;
  const plainLineId = (itemId: string) => `${itemId}::::`;

  const handleAdd = (it: any) => {
    const hasOpts = (it.option_groups || []).length > 0;
    if (hasOpts || itemEnt[it.item_id]) setSheetItem(it);
    else cart.add(id!, data.public_name, { item_id: it.item_id, name: it.name, price_cents: it.price_cents });
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Menu unavailable.</Text></View>;

  const count = cart.count();

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="menu-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data.public_name}</Text>
        <TouchableOpacity onPress={() => router.push('/shop/orders')} testID="menu-orders">
          <Ionicons name="receipt-outline" size={20} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 120 }} testID="menu-root">
        {!!data.cover_url && <Image source={{ uri: data.cover_url }} style={s.cover} contentFit="cover" transition={200} />}
        <View style={{ padding: SPACING.md }}>
          <View style={s.earnBadge}>
            <Text style={s.earnGlyph}>₿</Text>
            <Text style={s.earnText}>Earn {data.default_bigpoints} BigPoints</Text>
            {data.happy_hour && (
              <View style={s.hhPill} testID="menu-happy-hour">
                <Ionicons name="flash" size={11} color="#fff" />
                <Text style={s.hhText}>{data.points_multiplier}X Happy Hour</Text>
              </View>
            )}
          </View>

          {ents.some((e) => e.remaining > 0) && (
            <View style={s.memBanner} testID="menu-membership-banner">
              <Ionicons name="ribbon" size={15} color={COLORS.primary} />
              <Text style={s.memBannerText}>Your membership is active here — eligible items show a “Membership” tag.</Text>
            </View>
          )}

          {(data.sections || []).map((sec: any) => (
            <View key={sec.title} style={{ marginTop: SPACING.lg }}>
              <Text style={s.secTitle}>{sec.title}</Text>
              {sec.items.map((it: any) => {
                const q = plainQty(it.item_id);
                const hasOpts = (it.option_groups || []).length > 0;
                const ent = itemEnt[it.item_id];
                return (
                  <View key={it.item_id} style={s.itemRow} testID={`menu-item-${it.item_id}`}>
                    {absUrl(it.image_url) && (
                      <Image source={{ uri: absUrl(it.image_url)! }} style={s.itemThumb} contentFit="cover" transition={150} />
                    )}
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.itemName}>{it.name}</Text>
                      {!!it.description && <Text style={s.itemDesc} numberOfLines={2}>{it.description}</Text>}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
                        <Text style={s.itemPrice}>{hasOpts ? `from ${money(it.price_cents)}` : money(it.price_cents)}</Text>
                        {ent && (
                          <View style={s.entTag} testID={`menu-ent-tag-${it.item_id}`}>
                            <Ionicons name="ribbon" size={9} color={COLORS.primary} />
                            <Text style={s.entTagText}>Membership</Text>
                          </View>
                        )}
                      </View>
                    </View>
                    {!hasOpts && !ent && q > 0 && sameBiz ? (
                      <View style={s.stepper}>
                        <TouchableOpacity onPress={() => cart.dec(plainLineId(it.item_id))} testID={`menu-dec-${it.item_id}`} style={s.stepBtn}>
                          <Ionicons name="remove" size={18} color={COLORS.primary} />
                        </TouchableOpacity>
                        <Text style={s.stepQty}>{q}</Text>
                        <TouchableOpacity onPress={() => cart.inc(plainLineId(it.item_id))} testID={`menu-inc-${it.item_id}`} style={s.stepBtn}>
                          <Ionicons name="add" size={18} color={COLORS.primary} />
                        </TouchableOpacity>
                      </View>
                    ) : (
                      <TouchableOpacity style={[s.addBtn, hasOpts && s.chooseBtn]} testID={`menu-add-${it.item_id}`} onPress={() => handleAdd(it)}>
                        {hasOpts ? <><Ionicons name="options" size={14} color="#fff" /><Text style={s.chooseText}>Choose</Text></> : <Ionicons name="add" size={18} color="#fff" />}
                      </TouchableOpacity>
                    )}
                  </View>
                );
              })}
            </View>
          ))}
          {(!data.sections || data.sections.length === 0) && (
            <Text style={{ color: COLORS.textDim, marginTop: 24, textAlign: 'center' }}>
              This restaurant hasn&apos;t published a menu yet.
            </Text>
          )}
        </View>
      </ScrollView>

      {sheetItem && (
        <ItemOptionSheet
          item={sheetItem}
          entitlement={itemEnt[sheetItem.item_id] || null}
          onClose={() => setSheetItem(null)}
          onConfirm={(sel: any) => {
            cart.addLine(id!, data.public_name, {
              item_id: sheetItem.item_id, name: sheetItem.name, price_cents: sel.unit_price_cents,
              qty: sel.qty, selected_option_ids: sel.selected_option_ids, option_summary: sel.option_summary,
              apply_entitlement_id: sel.apply_entitlement_id, entitlement_label: sel.entitlement_label,
            });
            setSheetItem(null);
          }}
        />
      )}

      {count > 0 && (
        <View style={s.footer}>
          <TouchableOpacity style={common.btnPrimary} testID="menu-view-cart" onPress={() => router.push('/shop/cart')}>
            <Ionicons name="cart" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>View Cart ({count}) · {money(cart.subtotal())}</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  cover: { width: '100%', height: 160, backgroundColor: COLORS.inputBg },
  earnBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap', alignSelf: 'flex-start', backgroundColor: COLORS.gold + '1f', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full },
  earnGlyph: { color: COLORS.gold, fontSize: 15, fontWeight: '900' },
  earnText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  hhPill: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.primary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  hhText: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  memBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.md, padding: 10, marginTop: 10 },
  memBannerText: { flex: 1, color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700' },
  secTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  itemThumb: { width: 56, height: 56, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  itemDesc: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2, lineHeight: 16 },
  itemPrice: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  entTag: { flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: COLORS.primary + '1f', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  entTagText: { color: COLORS.primary, fontSize: 9, fontWeight: '900' },
  addBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  chooseBtn: { width: undefined, flexDirection: 'row', gap: 4, paddingHorizontal: 12 },
  chooseText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  stepQty: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', minWidth: 16, textAlign: 'center' },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
});
