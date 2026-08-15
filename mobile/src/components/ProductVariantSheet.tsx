// Product variant + quantity + note picker (mobile). Absolute-overlay bottom
// sheet used for "Customize" on the store detail page. Mirrors the web
// ProductVariantModal (variant tiles + qty + note presets).
import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Pressable, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;
const PRODUCT_PRESETS = ['Gift wrap', 'Fragile', 'Leave at door', 'Call on arrival'];

export default function ProductVariantSheet({ product, onClose, onConfirm }: any) {
  const variants = product.variants || [];
  const hasVariants = variants.length > 0;
  const firstInStock = useMemo(() => variants.find((v: any) => v.stock > 0) || variants[0] || null, [variants]);
  const [variant, setVariant] = useState<any>(hasVariants ? firstInStock : null);
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState('');
  const price = variant && variant.price_cents > 0 ? variant.price_cents : product.price_cents;
  const soldOut = hasVariants ? variants.every((v: any) => v.stock <= 0) : product.stock <= 0;

  const addPreset = (chip: string) =>
    setNote((n) => (n.toLowerCase().includes(chip.toLowerCase()) ? n : (n ? `${n}, ${chip}` : chip)));

  return (
    <View style={st.overlay} testID="product-variant-sheet">
      <Pressable style={st.backdrop} onPress={onClose} />
      <View style={st.sheet}>
        <View style={st.handle} />
        <View style={st.head}>
          <Text style={st.title} numberOfLines={1}>{product.name}</Text>
          <TouchableOpacity onPress={onClose} testID="product-variant-close"><Ionicons name="close" size={20} color={COLORS.textDim} /></TouchableOpacity>
        </View>
        <ScrollView style={{ maxHeight: 400 }} contentContainerStyle={{ paddingBottom: 8 }}>
          {!!product.image_url && (
            <Image source={{ uri: product.image_url }} style={st.hero} contentFit="cover" transition={150} testID="product-variant-hero" />
          )}
          <Text style={st.price}>{money(price)}</Text>
          {!!product.description && <Text style={st.desc}>{product.description}</Text>}

          {hasVariants && (
            <View style={{ marginTop: 12 }}>
              <Text style={st.grpName}>Options</Text>
              <View style={st.variantWrap}>
                {variants.map((vr: any) => {
                  const out = vr.stock <= 0;
                  const active = variant?.label === vr.label;
                  return (
                    <TouchableOpacity key={vr.label} disabled={out} onPress={() => setVariant(vr)}
                      style={[st.variant, active && st.variantOn, out && { opacity: 0.4 }]} testID={`pv-variant-${vr.label}`}>
                      <Text style={[st.variantLabel, active && { color: COLORS.primary }]}>{vr.label}</Text>
                      {vr.price_cents > 0 && <Text style={st.variantPrice}>{money(vr.price_cents)}</Text>}
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          )}

          <View style={{ marginTop: 14 }}>
            <Text style={st.grpName}>Note to seller</Text>
            <View style={st.chips} testID="product-note-presets">
              {PRODUCT_PRESETS.map((chip) => (
                <TouchableOpacity key={chip} onPress={() => addPreset(chip)} style={st.chip} testID={`product-note-chip-${chip}`}>
                  <Text style={st.chipText}>+ {chip}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput value={note} onChangeText={setNote} maxLength={140} multiline
              placeholder="e.g. gift wrap, colour preference" placeholderTextColor={COLORS.textMuted}
              style={st.noteInput} testID="product-variant-note" />
          </View>

          <View style={st.qtyRow}>
            <Text style={st.grpName}>Quantity</Text>
            <View style={st.stepper}>
              <TouchableOpacity onPress={() => setQty((q) => Math.max(1, q - 1))} style={st.stepBtn} testID="product-variant-qty-dec"><Ionicons name="remove" size={16} color={COLORS.primary} /></TouchableOpacity>
              <Text style={st.qtyText}>{qty}</Text>
              <TouchableOpacity onPress={() => setQty((q) => q + 1)} style={st.stepBtn} testID="product-variant-qty-inc"><Ionicons name="add" size={16} color={COLORS.primary} /></TouchableOpacity>
            </View>
          </View>
        </ScrollView>
        <TouchableOpacity style={[st.confirm, soldOut && { opacity: 0.5 }]} disabled={soldOut}
          onPress={() => onConfirm({ variant, qty, note: note.trim() || null })} testID="product-variant-confirm">
          <Text style={st.confirmText}>{soldOut ? 'Sold out' : `Add ${qty} to cart`}</Text>
          {!soldOut && <Text style={st.confirmPrice} testID="product-variant-total">{money(price * qty)}</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, justifyContent: 'flex-end' },
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)' },
  sheet: { backgroundColor: COLORS.card, borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 24 },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: COLORS.surfaceBorder, marginBottom: 10 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  title: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  hero: { width: '100%', height: 160, borderRadius: RADIUS.lg, backgroundColor: COLORS.inputBg, marginTop: 6 },
  price: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', marginTop: 12 },
  desc: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20, marginTop: 6 },
  grpName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginBottom: 8 },
  variantWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  variant: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  variantOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  variantLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  variantPrice: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  noteInput: { minHeight: 44, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, textAlignVertical: 'top' },
  qtyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  qtyText: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', minWidth: 18, textAlign: 'center' },
  confirm: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 20, paddingVertical: 14, marginTop: 12 },
  confirmText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  confirmPrice: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
