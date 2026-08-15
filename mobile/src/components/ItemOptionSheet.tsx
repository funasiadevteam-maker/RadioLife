// Item option + membership entitlement picker (mobile). Absolute overlay
// bottom sheet (renders reliably on web preview + native). Mirrors the web
// ItemOptionModal: size/single/multi groups with upcharges + optional
// "apply membership" so the base is free and only upgrades are charged.
import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, Pressable, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const signed = (c: number) => (c > 0 ? `+${money(c)}` : c < 0 ? `−${money(-c)}` : 'Free');
const DEFAULT_PRESETS = ['No onions', 'Extra spicy', 'No ice', 'Less sugar', 'Well done', 'On the side'];

function initialSelection(groups: any[]) {
  const sel = new Set<string>();
  (groups || []).forEach((g) => {
    if ((g.type === 'size' || g.type === 'single') && g.options?.length) {
      const def = g.options.find((o: any) => o.is_default) || g.options[0];
      if (def) sel.add(def.option_id);
    }
  });
  return sel;
}

// Default line (selection + unit price + summary) for one-tap "quick add".
export function defaultMenuSelection(item: any) {
  const groups = item.option_groups || [];
  const sel = initialSelection(groups);
  let unit = item.price_cents || 0;
  const labels: string[] = [];
  groups.forEach((g: any) => g.options.forEach((o: any) => {
    if (sel.has(o.option_id)) { unit += o.price_delta_cents || 0; labels.push(o.label); }
  }));
  return { selected_option_ids: [...sel], unit_price_cents: unit, option_summary: labels.join(', ') || null };
}

// True when defaults already satisfy every required group, so "+" can add
// instantly; otherwise the customize sheet must be opened.
export function menuQuickAddReady(item: any) {
  const groups = item.option_groups || [];
  const sel = initialSelection(groups);
  return groups.every((g: any) => {
    if (!g.required && !(g.min_select > 0)) return true;
    const n = g.options.filter((o: any) => sel.has(o.option_id)).length;
    return n >= Math.max(1, g.min_select || 0);
  });
}

export default function ItemOptionSheet({ item, entitlement, notePresets, onClose, onConfirm }: any) {
  const groups = item.option_groups || [];
  const [selected, setSelected] = useState<Set<string>>(() => initialSelection(groups));
  const [applyEnt, setApplyEnt] = useState(!!entitlement);
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const presets: string[] = (notePresets && notePresets.length ? notePresets : DEFAULT_PRESETS);
  const addPreset = (chip: string) =>
    setNote((n) => (n.toLowerCase().includes(chip.toLowerCase()) ? n : (n ? `${n}, ${chip}` : chip)));

  const toggle = (g: any, o: any) => {
    setErr(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (g.type === 'multi') {
        if (next.has(o.option_id)) next.delete(o.option_id);
        else {
          const chosen = g.options.filter((x: any) => next.has(x.option_id)).length;
          if (chosen >= (g.max_select || 1)) return prev;
          next.add(o.option_id);
        }
      } else {
        g.options.forEach((x: any) => next.delete(x.option_id));
        next.add(o.option_id);
      }
      return next;
    });
  };

  const { unit, entDiscount, optionSummary, charged } = useMemo(() => {
    let u = item.price_cents || 0;
    let waived = entitlement && applyEnt ? item.price_cents || 0 : 0;
    let ch = 0;
    const included = new Set(entitlement?.included_option_ids || []);
    const labels: string[] = [];
    groups.forEach((g: any) => g.options.forEach((o: any) => {
      if (selected.has(o.option_id)) {
        u += o.price_delta_cents || 0;
        if (entitlement && applyEnt) {
          if (included.has(o.option_id)) waived += o.price_delta_cents || 0;
          else ch += o.price_delta_cents || 0;
        }
        labels.push(o.label);
      }
    }));
    return { unit: u, entDiscount: Math.min(waived, u), optionSummary: labels.join(', ') || null, charged: ch };
  }, [selected, applyEnt, groups, item, entitlement]);

  const netPay = Math.max(0, unit - entDiscount);
  const cap = entitlement?.max_upcharge_cents;
  const overCap = entitlement && applyEnt && cap != null && charged > cap;

  const confirm = () => {
    for (const g of groups) {
      const n = g.options.filter((o: any) => selected.has(o.option_id)).length;
      if (g.required && n < Math.max(1, g.min_select || 0)) { setErr(`Please choose ${g.name}`); return; }
    }
    if (overCap) { setErr(`Upgrades over ${money(cap)} aren't covered by this membership`); return; }
    onConfirm({
      qty, selected_option_ids: [...selected], option_summary: optionSummary, unit_price_cents: unit,
      note: note.trim() || null,
      apply_entitlement_id: entitlement && applyEnt ? entitlement.entitlement_id : null,
      entitlement_label: entitlement && applyEnt ? entitlement.label : null,
    });
  };

  return (
    <View style={st.overlay} testID="item-option-sheet">
      <Pressable style={st.backdrop} onPress={onClose} />
      <View style={st.sheet}>
        <View style={st.handle} />
        <View style={st.head}>
          <Text style={st.title} numberOfLines={1}>{item.name}</Text>
          <TouchableOpacity onPress={onClose} testID="item-option-close"><Ionicons name="close" size={20} color={COLORS.textDim} /></TouchableOpacity>
        </View>
        <ScrollView style={{ maxHeight: 380 }} contentContainerStyle={{ paddingBottom: 8 }}>
          {entitlement && (
            <TouchableOpacity style={[st.entRow, applyEnt && st.entRowOn]} onPress={() => setApplyEnt((v) => !v)} testID="item-option-apply-membership">
              <View style={[st.cbox, applyEnt && st.cboxOn]}>{applyEnt && <Ionicons name="checkmark" size={13} color="#fff" />}</View>
              <Ionicons name="ribbon" size={16} color={COLORS.primary} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={st.entTitle}>Use {entitlement.plan_name || 'membership'}</Text>
                <Text style={st.entSub}>{entitlement.label} · {entitlement.remaining} left</Text>
              </View>
              {applyEnt && <Text style={st.freeTag}>BASE FREE</Text>}
            </TouchableOpacity>
          )}
          {groups.map((g: any) => (
            <View key={g.group_id} style={{ marginTop: 12 }} testID={`opt-group-${g.group_id}`}>
              <View style={st.grpHead}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={st.grpName}>{g.name}</Text>
                  {g.required && <View style={st.reqPill}><Text style={st.reqPillText}>REQUIRED</Text></View>}
                </View>
                <Text style={st.grpHint}>{g.type === 'multi' ? `Up to ${g.max_select}` : 'Choose 1'}</Text>
              </View>
              {g.options.map((o: any) => {
                const on = selected.has(o.option_id);
                const included = applyEnt && new Set(entitlement?.included_option_ids || []).has(o.option_id);
                return (
                  <TouchableOpacity key={o.option_id} disabled={o.available === false} onPress={() => toggle(g, o)}
                    style={[st.opt, on && st.optOn, o.available === false && { opacity: 0.4 }]} testID={`opt-${o.option_id}`}>
                    <View style={[g.type === 'multi' ? st.sq : st.circ, on && st.markOn]}>{on && <Ionicons name="checkmark" size={11} color="#fff" />}</View>
                    <Text style={st.optLabel}>{o.label}</Text>
                    <Text style={[st.optPrice, included && { color: COLORS.green }]}>{included ? 'Included' : signed(o.price_delta_cents)}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          ))}
          <View style={st.noteBlock}>
            <Text style={st.grpName}>Special instructions</Text>
            <View style={st.chips} testID="item-note-presets">
              {presets.map((chip) => (
                <TouchableOpacity key={chip} onPress={() => addPreset(chip)} style={st.chip} testID={`item-note-chip-${chip}`}>
                  <Text style={st.chipText}>+ {chip}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput value={note} onChangeText={setNote} maxLength={140} multiline
              placeholder="e.g. no onions, extra spicy" placeholderTextColor={COLORS.textMuted}
              style={st.noteInput} testID="item-option-note" />
          </View>
          <View style={st.qtyRow}>
            <Text style={st.grpName}>Quantity</Text>
            <View style={st.stepper}>
              <TouchableOpacity onPress={() => setQty((q) => Math.max(1, q - 1))} style={st.stepBtn} testID="item-option-qty-dec"><Ionicons name="remove" size={16} color={COLORS.primary} /></TouchableOpacity>
              <Text style={st.qtyText}>{qty}</Text>
              <TouchableOpacity onPress={() => setQty((q) => q + 1)} style={st.stepBtn} testID="item-option-qty-inc"><Ionicons name="add" size={16} color={COLORS.primary} /></TouchableOpacity>
            </View>
          </View>
          {!!err && <Text style={st.err} testID="item-option-error">{err}</Text>}
        </ScrollView>
        <TouchableOpacity style={st.confirm} onPress={confirm} testID="item-option-confirm">
          <Text style={st.confirmText}>Add {qty} to order</Text>
          <Text style={st.confirmPrice} testID="item-option-total">{money(netPay * qty)}</Text>
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
  entRow: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 2, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 12, marginTop: 8 },
  entRowOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  cbox: { width: 20, height: 20, borderRadius: 6, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  cboxOn: { backgroundColor: COLORS.primary },
  entTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  entSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  freeTag: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '900' },
  reqPill: { backgroundColor: COLORS.green + '22', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  reqPillText: { color: COLORS.green, fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  grpHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  grpName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  grpHint: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  opt: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 11, marginBottom: 6 },
  optOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  circ: { width: 18, height: 18, borderRadius: 9, borderWidth: 2, borderColor: COLORS.surfaceBorder, alignItems: 'center', justifyContent: 'center' },
  sq: { width: 18, height: 18, borderRadius: 5, borderWidth: 2, borderColor: COLORS.surfaceBorder, alignItems: 'center', justifyContent: 'center' },
  markOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  optLabel: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  optPrice: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '900' },
  qtyRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 },
  noteBlock: { marginTop: 14 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8, marginBottom: 8 },
  chip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  noteInput: { minHeight: 44, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, textAlignVertical: 'top' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  qtyText: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', minWidth: 18, textAlign: 'center' },
  err: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '700', marginTop: 10 },
  confirm: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 20, paddingVertical: 14, marginTop: 12 },
  confirmText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  confirmPrice: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
