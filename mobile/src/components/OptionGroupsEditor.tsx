// Reusable option-groups editor (mobile) for menu items & products.
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, FONT, RADIUS } from '../constants/theme';

const TYPES: [string, string][] = [['size', 'Size'], ['single', 'Single'], ['multi', 'Multiple']];
const blankOpt = () => ({ label: '', price_delta_cents: 0, is_default: false, available: true });
const blankGroup = () => ({ name: '', type: 'single', required: false, min_select: 0, max_select: 1, options: [blankOpt()] });

export default function OptionGroupsEditor({ value, onChange }: { value: any[]; onChange: (v: any[]) => void }) {
  const groups = value || [];
  const updGroup = (gi: number, patch: any) => onChange(groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)));
  const updOpt = (gi: number, oi: number, patch: any) => onChange(groups.map((g, i) => (i === gi
    ? { ...g, options: g.options.map((o: any, j: number) => (j === oi ? { ...o, ...patch } : o)) } : g)));

  return (
    <View style={{ marginTop: 8 }} testID="option-groups-editor">
      <Text style={s.head}>OPTIONS &amp; UPGRADES</Text>
      {groups.map((g, gi) => (
        <View key={gi} style={s.grp} testID={`optgrp-${gi}`}>
          <View style={{ flexDirection: 'row', gap: 6 }}>
            <TextInput value={g.name} onChangeText={(v) => updGroup(gi, { name: v })} placeholder="Group e.g. Size" placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID={`optgrp-name-${gi}`} />
            <TouchableOpacity style={s.x} onPress={() => onChange(groups.filter((_, i) => i !== gi))} testID={`optgrp-remove-${gi}`}><Ionicons name="close" size={15} color={COLORS.red} /></TouchableOpacity>
          </View>
          <View style={s.chipRow} testID={`optgrp-type-${gi}`}>
            {TYPES.map(([v, l]) => (
              <TouchableOpacity key={v} onPress={() => updGroup(gi, { type: v, max_select: v === 'multi' ? Math.max(2, g.max_select) : 1 })} style={[s.chip, g.type === v && s.chipOn]} testID={`optgrp-type-${gi}-${v}`}>
                <Text style={[s.chipText, g.type === v && { color: '#fff' }]}>{l}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity onPress={() => updGroup(gi, { required: !g.required, min_select: !g.required ? 1 : 0 })} style={[s.chip, g.required && s.chipOn]} testID={`optgrp-required-${gi}`}>
              <Text style={[s.chipText, g.required && { color: '#fff' }]}>Required</Text>
            </TouchableOpacity>
          </View>
          {g.options.map((o: any, oi: number) => (
            <View key={oi} style={s.optRow} testID={`optgrp-${gi}-opt-${oi}`}>
              <TextInput value={o.label} onChangeText={(v) => updOpt(gi, oi, { label: v })} placeholder="Option e.g. Large" placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID={`optgrp-${gi}-opt-label-${oi}`} />
              <Text style={s.plus}>+$</Text>
              <TextInput value={o.price_delta_cents ? String(o.price_delta_cents / 100) : ''} onChangeText={(v) => updOpt(gi, oi, { price_delta_cents: Math.round((parseFloat(v) || 0) * 100) })} placeholder="0" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { width: 56 }]} testID={`optgrp-${gi}-opt-price-${oi}`} />
              <TouchableOpacity onPress={() => updOpt(gi, oi, { is_default: !o.is_default })} testID={`optgrp-${gi}-opt-default-${oi}`}>
                <Ionicons name={o.is_default ? 'star' : 'star-outline'} size={16} color={o.is_default ? COLORS.gold : COLORS.textMuted} />
              </TouchableOpacity>
              {g.options.length > 1 && <TouchableOpacity onPress={() => updGroup(gi, { options: g.options.filter((_: any, j: number) => j !== oi) })} testID={`optgrp-${gi}-opt-remove-${oi}`}><Ionicons name="close" size={14} color={COLORS.red} /></TouchableOpacity>}
            </View>
          ))}
          <TouchableOpacity onPress={() => updGroup(gi, { options: [...g.options, blankOpt()] })} style={s.addOpt} testID={`optgrp-${gi}-add-opt`}>
            <Ionicons name="add" size={13} color={COLORS.primary} /><Text style={s.addText}>Add option</Text>
          </TouchableOpacity>
        </View>
      ))}
      <TouchableOpacity onPress={() => onChange([...groups, blankGroup()])} style={s.addGrp} testID="optgrp-add-group">
        <Ionicons name="add" size={15} color={COLORS.primary} /><Text style={s.addText}>Add option group</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  head: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900', marginBottom: 6 },
  grp: { borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 8, marginBottom: 8, gap: 8 },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm },
  x: { width: 40, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: 11, fontWeight: '800' },
  optRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  plus: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800' },
  addOpt: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  addGrp: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  addText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
});
