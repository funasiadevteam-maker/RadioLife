// RadioLife Merchant — memberships as an entitlement engine (mobile).
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const FREQS: [string, string][] = [['daily', 'Daily'], ['weekly', 'Weekly'], ['monthly', 'Monthly'], ['billing_cycle', 'Billing cycle'], ['total', 'One-time']];
const TARGETS: [string, string][] = [['any', 'Anything'], ['category', 'Category'], ['item', 'Items']];
const blankEnt = () => ({ label: '', target_type: 'any', category: '', target_ids: [] as string[], included_option_ids: [] as string[], quantity: '1', reset_frequency: 'monthly', rollover: false, stackable: false, days: [] as number[], start_hour: '', end_hour: '', max_upcharge: '' });

export default function MerchantMemberships() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', price: '', interval: 'month' });
  const [ents, setEnts] = useState<any[]>([blankEnt()]);
  const [catalog, setCatalog] = useState<any[]>([]);

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/memberships'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    Promise.all([
      api.get('/merchant/marketplace/menu').catch(() => ({ data: { items: [] } })),
      api.get('/merchant/marketplace/products').catch(() => ({ data: { items: [] } })),
    ]).then(([m, p]) => {
      const menu = (m.data.items || []).map((it: any) => ({ id: it.item_id, name: it.name, category: it.section, options: (it.option_groups || []).flatMap((g: any) => g.options) }));
      const prods = (p.data.items || []).map((x: any) => ({ id: x.product_id, name: x.name, category: x.category, options: (x.option_groups || []).flatMap((g: any) => g.options) }));
      setCatalog([...menu, ...prods]);
    });
  }, []);

  const categories = useMemo(() => [...new Set(catalog.map((c) => c.category).filter(Boolean))], [catalog]);
  const optionChoices = useMemo(() => {
    const seen: Record<string, any> = {};
    catalog.forEach((c) => c.options.forEach((o: any) => { if (!seen[o.option_id]) seen[o.option_id] = { id: o.option_id, label: o.label }; }));
    return Object.values(seen);
  }, [catalog]);

  const reset = () => { setForm({ name: '', description: '', price: '', interval: 'month' }); setEnts([blankEnt()]); setEditingId(null); };
  const updEnt = (i: number, patch: any) => setEnts((a) => a.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  const toggleIn = (i: number, key: string, val: any) => setEnts((a) => a.map((e, idx) => {
    if (idx !== i) return e;
    const set = new Set(e[key]); set.has(val) ? set.delete(val) : set.add(val);
    return { ...e, [key]: [...set] };
  }));

  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const entitlements = ents.filter((e) => e.label.trim()).map((e) => {
      const dt = (e.days.length || e.start_hour !== '' || e.end_hour !== '')
        ? { days: e.days, start_hour: e.start_hour === '' ? null : Number(e.start_hour), end_hour: e.end_hour === '' ? null : Number(e.end_hour) } : null;
      return {
        label: e.label.trim(), target_type: e.target_type,
        category: e.target_type === 'category' ? (e.category || null) : null,
        target_ids: ['item', 'product'].includes(e.target_type) ? e.target_ids : [],
        included_option_ids: e.included_option_ids,
        quantity: parseInt(e.quantity, 10) || 1, reset_frequency: e.reset_frequency,
        rollover: !!e.rollover, rollover_cap: 0, day_time: dt, stackable: !!e.stackable,
        max_upcharge_cents: e.max_upcharge === '' ? null : Math.round((parseFloat(e.max_upcharge) || 0) * 100), active: true,
      };
    });
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), interval: form.interval, entitlements, active: true };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/memberships/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/memberships/items', body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p: any) => {
    setEditingId(p.plan_id);
    setForm({ name: p.name || '', description: p.description || '', price: ((p.price_cents || 0) / 100).toString(), interval: p.interval || 'month' });
    const mapped = (p.entitlements || []).map((e: any) => ({
      label: e.label || '', target_type: e.target_type || 'any', category: e.category || '',
      target_ids: e.target_ids || [], included_option_ids: e.included_option_ids || [],
      quantity: String(e.quantity || 1), reset_frequency: e.reset_frequency || 'monthly',
      rollover: !!e.rollover, stackable: !!e.stackable, days: e.day_time?.days || [],
      start_hour: e.day_time?.start_hour ?? '', end_hour: e.day_time?.end_hour ?? '',
      max_upcharge: e.max_upcharge_cents == null ? '' : String(e.max_upcharge_cents / 100),
    }));
    setEnts(mapped.length ? mapped : [blankEnt()]);
  };
  const del = async (pid: string) => { try { await api.delete(`/merchant/marketplace/memberships/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  const Chip = ({ on, label, onPress, tid, green }: any) => (
    <TouchableOpacity onPress={onPress} testID={tid} style={[s.chip, on && (green ? s.chipGreen : s.chipOn)]}>
      <Text style={[s.chipText, on && { color: '#fff' }]}>{label}</Text>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mmem-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Memberships</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mmem-root">
        <View style={s.card} testID="mmem-form">
          <Text style={s.cardTitle}>{editingId ? 'Edit membership' : 'New membership'}</Text>
          <TextInput value={form.name} onChangeText={(v) => setForm({ ...form, name: v })} placeholder="Name e.g. Pizza Club" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mmem-name" />
          <TextInput value={form.description} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} style={s.input} testID="mmem-desc" />
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <TextInput value={form.price} onChangeText={(v) => setForm({ ...form, price: v })} placeholder="Price" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { flex: 1 }]} testID="mmem-price" />
            <TouchableOpacity style={[s.input, { flex: 1, justifyContent: 'center' }]} onPress={() => setForm({ ...form, interval: form.interval === 'month' ? 'week' : 'month' })} testID="mmem-interval">
              <Text style={{ color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' }}>{form.interval === 'month' ? 'Monthly' : 'Weekly'}</Text>
            </TouchableOpacity>
          </View>

          <Text style={s.section}>ENTITLEMENTS</Text>
          {ents.map((e, i) => (
            <View key={i} style={s.entBox} testID={`mmem-ent-${i}`}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TextInput value={e.label} onChangeText={(v) => updEnt(i, { label: v })} placeholder="Perk e.g. Free Pizza (Medium)" placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID={`mmem-ent-label-${i}`} />
                {ents.length > 1 && <TouchableOpacity style={s.entX} onPress={() => setEnts((a) => a.filter((_, idx) => idx !== i))} testID={`mmem-ent-remove-${i}`}><Ionicons name="close" size={16} color={COLORS.red} /></TouchableOpacity>}
              </View>

              <Text style={s.lbl}>Applies to</Text>
              <View style={s.chipRow} testID={`mmem-ent-target-${i}`}>
                {TARGETS.map(([v, l]) => <Chip key={v} on={e.target_type === v} label={l} onPress={() => updEnt(i, { target_type: v })} tid={`mmem-ent-target-${i}-${v}`} />)}
              </View>
              {e.target_type === 'category' && (
                <View style={s.chipRow} testID={`mmem-ent-category-${i}`}>
                  {categories.map((c) => <Chip key={c} on={e.category === c} label={c} onPress={() => updEnt(i, { category: c })} tid={`mmem-ent-cat-${i}-${c}`} />)}
                </View>
              )}
              {e.target_type === 'item' && (
                <View style={s.chipRow} testID={`mmem-ent-items-${i}`}>
                  {catalog.map((c) => <Chip key={c.id} on={e.target_ids.includes(c.id)} label={c.name} onPress={() => toggleIn(i, 'target_ids', c.id)} tid={`mmem-ent-item-${i}-${c.id}`} />)}
                </View>
              )}

              {optionChoices.length > 0 && (
                <>
                  <Text style={s.lbl}>Included free</Text>
                  <View style={s.chipRow} testID={`mmem-ent-included-${i}`}>
                    {optionChoices.map((o: any) => <Chip key={o.id} green on={e.included_option_ids.includes(o.id)} label={o.label} onPress={() => toggleIn(i, 'included_option_ids', o.id)} tid={`mmem-ent-inc-${i}-${o.id}`} />)}
                  </View>
                </>
              )}

              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TextInput value={e.quantity} onChangeText={(v) => updEnt(i, { quantity: v })} placeholder="Qty" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { width: 64 }]} testID={`mmem-ent-qty-${i}`} />
                <TouchableOpacity style={[s.input, { flex: 1, justifyContent: 'center' }]} testID={`mmem-ent-reset-${i}`}
                  onPress={() => { const idx = FREQS.findIndex(([v]) => v === e.reset_frequency); updEnt(i, { reset_frequency: FREQS[(idx + 1) % FREQS.length][0] }); }}>
                  <Text style={{ color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' }}>Resets: {FREQS.find(([v]) => v === e.reset_frequency)?.[1]}</Text>
                </TouchableOpacity>
              </View>
              <TextInput value={e.max_upcharge} onChangeText={(v) => updEnt(i, { max_upcharge: v })} placeholder="Max upgrade covered ($, optional)" placeholderTextColor={COLORS.textMuted} keyboardType="decimal-pad" style={[s.input, { marginTop: 8 }]} testID={`mmem-ent-cap-${i}`} />

              <Text style={s.lbl}>Days (optional)</Text>
              <View style={s.chipRow} testID={`mmem-ent-days-${i}`}>
                {DAYS.map((d, di) => <Chip key={d} on={e.days.includes(di)} label={d} onPress={() => toggleIn(i, 'days', di)} tid={`mmem-ent-day-${i}-${di}`} />)}
              </View>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TextInput value={String(e.start_hour)} onChangeText={(v) => updEnt(i, { start_hour: v })} placeholder="Start hr" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { flex: 1 }]} testID={`mmem-ent-start-${i}`} />
                <TextInput value={String(e.end_hour)} onChangeText={(v) => updEnt(i, { end_hour: v })} placeholder="End hr" placeholderTextColor={COLORS.textMuted} keyboardType="number-pad" style={[s.input, { flex: 1 }]} testID={`mmem-ent-end-${i}`} />
              </View>

              <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                <TouchableOpacity style={[s.toggle, e.stackable && s.toggleOn]} onPress={() => updEnt(i, { stackable: !e.stackable })} testID={`mmem-ent-stackable-${i}`}>
                  <Ionicons name={e.stackable ? 'checkbox' : 'square-outline'} size={15} color={e.stackable ? COLORS.primary : COLORS.textMuted} />
                  <Text style={s.toggleText}>Stack w/ coupons</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.toggle, e.rollover && s.toggleOn]} onPress={() => updEnt(i, { rollover: !e.rollover })} testID={`mmem-ent-rollover-${i}`}>
                  <Ionicons name={e.rollover ? 'checkbox' : 'square-outline'} size={15} color={e.rollover ? COLORS.primary : COLORS.textMuted} />
                  <Text style={s.toggleText}>Roll over</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
          <TouchableOpacity style={s.addEnt} onPress={() => setEnts((a) => [...a, blankEnt()])} testID="mmem-add-ent">
            <Ionicons name="add" size={16} color={COLORS.primary} /><Text style={s.addEntText}>Add entitlement</Text>
          </TouchableOpacity>

          <View style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
            {editingId && <TouchableOpacity style={s.cancel} onPress={reset} testID="mmem-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>}
            <TouchableOpacity style={[common.btnPrimary, { flex: 1 }, saving && { opacity: 0.6 }]} disabled={saving} onPress={save} testID="mmem-save">
              <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Create'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {!items.length && <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }} testID="mmem-empty">No memberships yet.</Text>}
        {items.map((p) => (
          <View key={p.plan_id} style={s.item} testID={`mmem-item-${p.plan_id}`}>
            <View style={s.itemIcon}><Ionicons name="ribbon" size={18} color={COLORS.primary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={s.itemName}>{p.name} · {money(p.price_cents)}/{p.interval}</Text>
              <Text style={s.itemMeta}>{(p.entitlements || []).length} entitlements · {p.member_count || 0} members{!p.active ? ' · inactive' : ''}</Text>
            </View>
            <TouchableOpacity onPress={() => edit(p)} style={s.iconBtn} testID={`mmem-edit-${p.plan_id}`}><Ionicons name="pencil" size={16} color={COLORS.secondary} /></TouchableOpacity>
            <TouchableOpacity onPress={() => del(p.plan_id)} style={s.iconBtn} testID={`mmem-del-${p.plan_id}`}><Ionicons name="trash" size={16} color={COLORS.red} /></TouchableOpacity>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 8 },
  title: { color: COLORS.text, fontSize: 20, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 16, gap: 10 },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  section: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900', marginTop: 4 },
  lbl: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '900', marginTop: 8 },
  entBox: { borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 10 },
  entX: { width: 42, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipGreen: { backgroundColor: COLORS.green, borderColor: COLORS.green },
  chipText: { color: COLORS.textDim, fontSize: 11, fontWeight: '800' },
  toggle: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 10, paddingVertical: 9 },
  toggleOn: { borderColor: COLORS.primary },
  toggleText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800' },
  addEnt: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  addEntText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  cancel: { flex: 1, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center', paddingVertical: 12 },
  cancelText: { color: COLORS.textDim, fontWeight: '800' },
  item: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  itemIcon: { width: 40, height: 40, borderRadius: RADIUS.sm, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  itemMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
});
