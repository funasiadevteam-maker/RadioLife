// Merchant Products — catalogue (variants + photos), delivery, fulfillment.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Switch, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);
// parse "S:5, M:3, L:2" -> variants
const parseVariants = (s: string) => s.split(',').map((p) => p.trim()).filter(Boolean).map((p) => {
  const [label, stock] = p.split(':'); return { label: (label || '').trim(), price_cents: 0, stock: parseInt((stock || '0').trim(), 10) || 0 };
}).filter((v) => v.label);
const variantsStr = (vs: any[]) => (vs || []).map((v) => `${v.label}:${v.stock}`).join(', ');
const NEXT: Record<string, { label: string; status: string }> = {
  paid: { label: 'Mark Packed', status: 'packed' }, packed: { label: 'Mark Shipped', status: 'shipped' }, shipped: { label: 'Mark Delivered', status: 'delivered' },
};

export default function MerchantProducts() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [delivery, setDelivery] = useState<any>({ pickup: true, delivery: false, fee_cents: 0, free_over_cents: 0 });
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: '', description: '', category: '', price: '', stock: '', variants: '', points: '' });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, o, d] = await Promise.all([
        api.get('/merchant/marketplace/products'),
        api.get('/merchant/marketplace/products/orders'),
        api.get('/merchant/marketplace/products/delivery'),
      ]);
      setItems(p.data.items || []); setOrders(o.data.items || []); if (d.data.delivery) setDelivery(d.data.delivery);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: '', description: '', category: '', price: '', stock: '', variants: '', points: '' }); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const variants = parseVariants(form.variants);
    const body = { name: form.name.trim(), description: form.description.trim() || null, category: form.category.trim() || 'Products',
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), stock: variants.length ? 0 : (parseInt(form.stock, 10) || 0),
      variants, bigpoints: form.points ? parseInt(form.points, 10) : null, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/products/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/products/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p: any) => { setEditingId(p.product_id); setForm({ name: p.name || '', description: p.description || '', category: p.category || '', price: ((p.price_cents || 0) / 100).toString(), stock: String(p.stock || 0), variants: variantsStr(p.variants), points: p.bigpoints != null ? String(p.bigpoints) : '' }); };
  const del = async (id: string) => { try { await api.delete(`/merchant/marketplace/products/items/${id}`); load(); } catch { /* ignore */ } };
  const saveDelivery = async (patch: any) => { const nd = { ...delivery, ...patch }; setDelivery(nd); try { await api.patch('/merchant/marketplace/products/delivery', nd); } catch { /* ignore */ } };
  const uploadPhoto = async (pid: string) => {
    const res = await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.7 });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setPhotoBusy(pid); try { await api.post(`/merchant/marketplace/products/items/${pid}/photo`, { file_base64: res.assets[0].base64, ext: 'jpg' }); load(); } catch { /* ignore */ } finally { setPhotoBusy(null); }
  };
  const aiPhoto = async (pid: string) => { setPhotoBusy(pid); try { await api.post(`/merchant/marketplace/products/items/${pid}/photo/ai`, {}); load(); } catch { /* ignore */ } finally { setPhotoBusy(null); } };
  const advance = async (o: any) => { const n = NEXT[o.status]; if (!n) return; try { await api.patch(`/merchant/marketplace/products/orders/${o.order_id}/status`, { status: n.status }); load(); } catch { /* ignore */ } };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="mprod-back" style={{ padding: 2 }}><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>Products &amp; Delivery</Text>
        <View style={{ width: 22 }} />
      </View>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="mprod-root">
          <View style={s.card}>
            <Text style={s.cardTitle}>Delivery settings</Text>
            <View style={s.swRow}><Text style={s.swLabel}>Pickup</Text><Switch value={!!delivery.pickup} onValueChange={(v) => saveDelivery({ pickup: v })} trackColor={{ true: COLORS.primary }} testID="mprod-pickup" /></View>
            <View style={s.swRow}><Text style={s.swLabel}>Delivery</Text><Switch value={!!delivery.delivery} onValueChange={(v) => saveDelivery({ delivery: v })} trackColor={{ true: COLORS.primary }} testID="mprod-delivery" /></View>
            {delivery.delivery && (
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TextInput style={[s.input, { flex: 1, marginTop: 0 }]} keyboardType="decimal-pad" defaultValue={String((delivery.fee_cents || 0) / 100)} onEndEditing={(e) => saveDelivery({ fee_cents: Math.round((parseFloat(e.nativeEvent.text) || 0) * 100) })} placeholder="Fee $" placeholderTextColor={COLORS.textMuted} testID="mprod-fee" />
                <TextInput style={[s.input, { flex: 1, marginTop: 0 }]} keyboardType="decimal-pad" defaultValue={String((delivery.free_over_cents || 0) / 100)} onEndEditing={(e) => saveDelivery({ free_over_cents: Math.round((parseFloat(e.nativeEvent.text) || 0) * 100) })} placeholder="Free over $" placeholderTextColor={COLORS.textMuted} testID="mprod-freeover" />
              </View>
            )}
          </View>

          <View style={s.card}>
            <Text style={s.cardTitle}>{editingId ? 'Edit product' : 'Add product'}</Text>
            <TextInput style={s.input} value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} placeholder="Name" placeholderTextColor={COLORS.textMuted} testID="mprod-name" />
            <TextInput style={s.input} value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} testID="mprod-desc" />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TextInput style={[s.input, { flex: 1 }]} value={form.category} onChangeText={(v) => setForm({ ...form, category: v })} placeholder="Category" placeholderTextColor={COLORS.textMuted} testID="mprod-cat" />
              <TextInput style={[s.input, { flex: 1 }]} value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} keyboardType="decimal-pad" placeholder="Price" placeholderTextColor={COLORS.textMuted} testID="mprod-price" />
            </View>
            <TextInput style={s.input} value={form.stock} onChangeText={(v) => setForm({ ...form, stock: v })} keyboardType="number-pad" placeholder="Stock (if no variants)" placeholderTextColor={COLORS.textMuted} testID="mprod-stock" />
            <TextInput style={s.input} value={form.variants} onChangeText={(v) => setForm({ ...form, variants: v })} placeholder="Variants e.g. S:5, M:3, L:2" placeholderTextColor={COLORS.textMuted} testID="mprod-variants" />
            <TextInput style={s.input} value={form.points} onChangeText={(v) => setForm({ ...form, points: v })} keyboardType="number-pad" placeholder="BigPoints (optional)" placeholderTextColor={COLORS.textMuted} testID="mprod-points" />
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
              {editingId && <TouchableOpacity style={[common.btnGhost, { flex: 1 }]} onPress={reset} testID="mprod-cancel"><Text style={common.btnGhostText}>Cancel</Text></TouchableOpacity>}
              <TouchableOpacity style={[common.btnPrimary, { flex: 1 }]} onPress={save} disabled={saving} testID="mprod-save">{saving ? <ActivityIndicator color="#fff" /> : <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Add Product'}</Text>}</TouchableOpacity>
            </View>
          </View>

          <Text style={s.section}>Your products</Text>
          {!items.length && <Text style={s.empty}>No products yet.</Text>}
          {items.map((p) => (
            <View key={p.product_id} style={s.prodRow} testID={`mprod-item-${p.product_id}`}>
              {absUrl(p.image_url) ? <Image source={{ uri: absUrl(p.image_url)! }} style={s.thumb} contentFit="cover" /> : <View style={[s.thumb, { alignItems: 'center', justifyContent: 'center' }]}><Ionicons name="pricetag-outline" size={16} color={COLORS.textMuted} /></View>}
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.pName}>{p.name}</Text>
                <Text style={s.pMeta}>{money(p.price_cents)} · {p.variants?.length ? p.variants.map((v: any) => `${v.label}(${v.stock})`).join(' ') : `stock ${p.stock}`}</Text>
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
                  <TouchableOpacity onPress={() => uploadPhoto(p.product_id)} disabled={!!photoBusy} style={s.photoBtn} testID={`mprod-upload-${p.product_id}`}>{photoBusy === p.product_id ? <ActivityIndicator size="small" color={COLORS.primary} /> : <><Ionicons name="cloud-upload-outline" size={13} color={COLORS.primary} /><Text style={s.photoText}>Upload</Text></>}</TouchableOpacity>
                  <TouchableOpacity onPress={() => aiPhoto(p.product_id)} disabled={!!photoBusy} style={s.photoBtn} testID={`mprod-aiphoto-${p.product_id}`}><Ionicons name="sparkles" size={13} color={COLORS.primary} /><Text style={s.photoText}>AI</Text></TouchableOpacity>
                </View>
              </View>
              <TouchableOpacity onPress={() => edit(p)} style={s.iconBtn} testID={`mprod-edit-${p.product_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
              <TouchableOpacity onPress={() => del(p.product_id)} style={s.iconBtn} testID={`mprod-del-${p.product_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
            </View>
          ))}

          <Text style={s.section}>Incoming orders</Text>
          {!orders.length && <Text style={s.empty} testID="mprod-orders-empty">No paid orders yet.</Text>}
          {orders.map((o) => (
            <View key={o.order_id} style={s.orderCard} testID={`mprod-order-${o.order_id}`}>
              <View style={s.head}><Text style={s.oStatus}>{o.status}</Text><Text style={s.oFul}>{o.fulfillment}</Text></View>
              {(o.items || []).map((it: any, i: number) => <Text key={i} style={s.oItem}>{it.qty}× {it.name}{it.variant_label ? ` (${it.variant_label})` : ''}</Text>)}
              <Text style={s.oTotal}>{money(o.total_cents)} · rewards {o.points_to_award}</Text>
              {o.fulfillment === 'delivery' && !!o.address && <Text style={s.oAddr}>📍 {o.address}</Text>}
              {NEXT[o.status] && <TouchableOpacity style={s.advBtn} onPress={() => advance(o)} testID={`mprod-advance-${o.order_id}`}><Text style={s.advText}>{NEXT[o.status].label}</Text><Ionicons name="arrow-forward" size={15} color="#fff" /></TouchableOpacity>}
              {o.status === 'delivered' && <Text style={s.awarded}>✓ {o.points_to_award} BigPoints awarded</Text>}
            </View>
          ))}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 6 },
  swRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  swLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, marginTop: 8 },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 4, marginBottom: 8 },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: 8 },
  prodRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  thumb: { width: 48, height: 48, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg },
  pName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  pMeta: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  photoBtn: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 4 },
  photoText: { color: COLORS.primary, fontSize: 10, fontWeight: '800' },
  iconBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  orderCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14, marginBottom: 10 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  oStatus: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900', textTransform: 'uppercase' },
  oFul: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', textTransform: 'uppercase' },
  oItem: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  oTotal: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 6 },
  oAddr: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 4 },
  advBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingVertical: 10, marginTop: 10 },
  advText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  awarded: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '800', marginTop: 10 },
});
