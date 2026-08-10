// Merchant Menu Builder — CRUD + AI import (URL/image/PDF) + Excel import.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { uriToBase64 } from '../../src/utils/fileToBase64';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);

export default function MenuBuilder() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ section: '', name: '', description: '', price: '' });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [importUrl, setImportUrl] = useState('');
  const [importing, setImporting] = useState<string | null>(null);
  const [preview, setPreview] = useState<any[] | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [photoBusy, setPhotoBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/menu'); setItems(r.data.items || []); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ section: '', name: '', description: '', price: '' }); setEditingId(null); };

  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const body = {
      section: form.section.trim() || 'Menu', name: form.name.trim(),
      description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), available: true,
    };
    try {
      if (editingId) await api.patch(`/merchant/marketplace/menu/items/${editingId}`, body);
      else await api.post('/merchant/marketplace/menu/items', body);
      reset(); load();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const edit = (it: any) => {
    setEditingId(it.item_id);
    setForm({ section: it.section || '', name: it.name || '', description: it.description || '',
      price: ((it.price_cents || 0) / 100).toString() });
  };

  const del = async (id: string) => {
    try { await api.delete(`/merchant/marketplace/menu/items/${id}`); load(); } catch { /* ignore */ }
  };

  const uploadPhoto = async (itemId: string) => {
    const res = await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.7 });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setPhotoBusy(itemId);
    try { await api.post(`/merchant/marketplace/menu/items/${itemId}/photo`, { file_base64: res.assets[0].base64, ext: 'jpg' }); load(); }
    catch { /* ignore */ } finally { setPhotoBusy(null); }
  };
  const aiPhoto = async (itemId: string) => {
    setPhotoBusy(itemId);
    try { await api.post(`/merchant/marketplace/menu/items/${itemId}/photo/ai`, {}); load(); }
    catch { /* ignore */ } finally { setPhotoBusy(null); }
  };

  const runAiUrl = async () => {
    if (!importUrl.trim()) return;
    setImporting('url'); setImportMsg(null); setPreview(null);
    try {
      const r = await api.post('/merchant/marketplace/menu/import/ai', { source_type: 'url', url: importUrl.trim() });
      setPreview(r.data.items || []);
      if (!r.data.items?.length) setImportMsg('No items found on that page.');
    } catch (e: any) { setImportMsg(e?.response?.data?.detail?.code || 'Import failed'); }
    finally { setImporting(null); }
  };

  const runAiImage = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.7 });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    setImporting('image'); setImportMsg(null); setPreview(null);
    try {
      const r = await api.post('/merchant/marketplace/menu/import/ai', {
        source_type: 'image', file_base64: res.assets[0].base64 });
      setPreview(r.data.items || []);
      if (!r.data.items?.length) setImportMsg('No items detected in that image.');
    } catch (e: any) { setImportMsg(e?.response?.data?.detail?.code || 'Import failed'); }
    finally { setImporting(null); }
  };

  const pickDoc = async (kind: 'pdf' | 'file') => {
    const type = kind === 'pdf' ? 'application/pdf'
      : ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'text/csv',
         'application/vnd.ms-excel'];
    const res = await DocumentPicker.getDocumentAsync({ type, copyToCacheDirectory: true });
    if (res.canceled || !res.assets?.[0]) return;
    const asset: any = res.assets[0];
    setImporting(kind); setImportMsg(null); setPreview(null);
    try {
      const b64 = await uriToBase64(asset.uri, asset.file);
      const endpoint = kind === 'pdf' ? '/merchant/marketplace/menu/import/ai'
        : '/merchant/marketplace/menu/import/file';
      const body = kind === 'pdf' ? { source_type: 'pdf', file_base64: b64 }
        : { file_base64: b64, filename: asset.name || 'menu.xlsx' };
      const r = await api.post(endpoint, body);
      setPreview(r.data.items || []);
      if (!r.data.items?.length) setImportMsg('No items found in that file.');
    } catch (e: any) { setImportMsg(e?.response?.data?.detail?.code || 'Import failed'); }
    finally { setImporting(null); }
  };

  const addAllPreview = async () => {
    if (!preview?.length) return;
    setSaving(true);
    try {
      await api.post('/merchant/marketplace/menu/items/bulk', {
        items: preview.map((it) => ({
          section: it.section || 'Menu', name: it.name,
          description: it.description || null, price_cents: it.price_cents || 0, available: true })),
        replace: false });
      setPreview(null); setImportUrl(''); load();
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  const grouped: Record<string, any[]> = {};
  items.forEach((it) => { (grouped[it.section || 'Menu'] ||= []).push(it); });

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="menu-builder-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Menu Builder</Text>
        <View style={{ width: 22 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="menu-builder-root">

          {/* AI Import */}
          <View style={s.importCard} testID="menu-import-card">
            <Text style={s.cardTitle}>✨ Import your menu with AI</Text>
            <Text style={s.cardHint}>Paste your website, or upload a photo / PDF / Excel of your menu.</Text>
            <View style={s.urlRow}>
              <TextInput style={s.urlInput} value={importUrl} onChangeText={setImportUrl}
                placeholder="https://your-restaurant.com/menu" placeholderTextColor={COLORS.textMuted}
                autoCapitalize="none" testID="import-url-input" />
              <TouchableOpacity style={s.urlBtn} onPress={runAiUrl} disabled={!!importing} testID="import-url-btn">
                {importing === 'url' ? <ActivityIndicator color="#fff" size="small" />
                  : <Ionicons name="sparkles" size={16} color="#fff" />}
              </TouchableOpacity>
            </View>
            <View style={s.importBtns}>
              <TouchableOpacity style={s.impBtn} onPress={runAiImage} disabled={!!importing} testID="import-image-btn">
                {importing === 'image' ? <ActivityIndicator color={COLORS.primary} size="small" />
                  : <><Ionicons name="image" size={15} color={COLORS.primary} /><Text style={s.impText}>Photo</Text></>}
              </TouchableOpacity>
              <TouchableOpacity style={s.impBtn} onPress={() => pickDoc('pdf')} disabled={!!importing} testID="import-pdf-btn">
                {importing === 'pdf' ? <ActivityIndicator color={COLORS.primary} size="small" />
                  : <><Ionicons name="document" size={15} color={COLORS.primary} /><Text style={s.impText}>PDF</Text></>}
              </TouchableOpacity>
              <TouchableOpacity style={s.impBtn} onPress={() => pickDoc('file')} disabled={!!importing} testID="import-excel-btn">
                {importing === 'file' ? <ActivityIndicator color={COLORS.primary} size="small" />
                  : <><Ionicons name="grid" size={15} color={COLORS.primary} /><Text style={s.impText}>Excel</Text></>}
              </TouchableOpacity>
            </View>
            {!!importMsg && <Text style={s.importMsg} testID="import-msg">{importMsg}</Text>}
          </View>

          {/* AI preview */}
          {preview && preview.length > 0 && (
            <View style={s.previewCard} testID="import-preview">
              <Text style={s.cardTitle}>{preview.length} items found</Text>
              {preview.slice(0, 20).map((it, i) => (
                <View key={i} style={s.prevRow}>
                  <Text style={s.prevName} numberOfLines={1}>{it.section} · {it.name}</Text>
                  <Text style={s.prevPrice}>{money(it.price_cents || 0)}</Text>
                </View>
              ))}
              <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }]} onPress={addAllPreview}
                disabled={saving} testID="import-add-all">
                {saving ? <ActivityIndicator color="#fff" />
                  : <Text style={common.btnPrimaryText}>Add all {preview.length} to menu</Text>}
              </TouchableOpacity>
            </View>
          )}

          {/* Add / edit item */}
          <View style={s.formCard}>
            <Text style={s.cardTitle}>{editingId ? 'Edit item' : 'Add item manually'}</Text>
            <TextInput style={s.input} value={form.section} onChangeText={(v) => setForm({ ...form, section: v })}
              placeholder="Section (e.g. Mains)" placeholderTextColor={COLORS.textMuted} testID="item-section" />
            <TextInput style={s.input} value={form.name} onChangeText={(v) => setForm({ ...form, name: v })}
              placeholder="Item name" placeholderTextColor={COLORS.textMuted} testID="item-name" />
            <TextInput style={s.input} value={form.description} onChangeText={(v) => setForm({ ...form, description: v })}
              placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} testID="item-desc" />
            <TextInput style={s.input} value={form.price} onChangeText={(v) => setForm({ ...form, price: v })}
              keyboardType="decimal-pad" placeholder="Price (e.g. 12.50)" placeholderTextColor={COLORS.textMuted} testID="item-price" />
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
              {editingId && (
                <TouchableOpacity style={[common.btnGhost, { flex: 1 }]} onPress={reset} testID="item-cancel">
                  <Text style={common.btnGhostText}>Cancel</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={[common.btnPrimary, { flex: 1 }]} onPress={save} disabled={saving} testID="item-save">
                {saving ? <ActivityIndicator color="#fff" />
                  : <Text style={common.btnPrimaryText}>{editingId ? 'Update' : 'Add Item'}</Text>}
              </TouchableOpacity>
            </View>
          </View>

          {/* Existing menu */}
          {Object.keys(grouped).map((sec) => (
            <View key={sec} style={{ marginTop: SPACING.md }}>
              <Text style={s.section}>{sec}</Text>
              {grouped[sec].map((it) => (
                <View key={it.item_id} style={s.itemRow} testID={`builder-item-${it.item_id}`}>
                  {absUrl(it.image_url)
                    ? <Image source={{ uri: absUrl(it.image_url)! }} style={s.thumb} contentFit="cover" transition={150} />
                    : <View style={[s.thumb, s.thumbEmpty]}><Ionicons name="fast-food-outline" size={18} color={COLORS.textMuted} /></View>}
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.itemName}>{it.name}</Text>
                    <Text style={s.itemPrice}>{money(it.price_cents)}</Text>
                    <View style={s.photoBtns}>
                      <TouchableOpacity onPress={() => uploadPhoto(it.item_id)} disabled={!!photoBusy} testID={`builder-upload-${it.item_id}`} style={s.photoBtn}>
                        {photoBusy === it.item_id ? <ActivityIndicator size="small" color={COLORS.primary} />
                          : <><Ionicons name="cloud-upload-outline" size={13} color={COLORS.primary} /><Text style={s.photoBtnText}>Upload</Text></>}
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => aiPhoto(it.item_id)} disabled={!!photoBusy} testID={`builder-aiphoto-${it.item_id}`} style={s.photoBtn}>
                        <Ionicons name="sparkles" size={13} color={COLORS.primary} /><Text style={s.photoBtnText}>AI Photo</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => edit(it)} style={s.iconBtn} testID={`builder-edit-${it.item_id}`}>
                    <Ionicons name="pencil" size={16} color={COLORS.secondary} />
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => del(it.item_id)} style={s.iconBtn} testID={`builder-del-${it.item_id}`}>
                    <Ionicons name="trash" size={16} color={COLORS.red} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
          ))}
          {!items.length && <Text style={{ color: COLORS.textDim, marginTop: 20, textAlign: 'center' }}>No items yet — add one or import above.</Text>}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  importCard: { backgroundColor: COLORS.primary + '0d', borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  cardHint: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 3, marginBottom: 10 },
  urlRow: { flexDirection: 'row', gap: 8 },
  urlInput: { flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  urlBtn: { width: 46, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  importBtns: { flexDirection: 'row', gap: 8, marginTop: 10 },
  impBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingVertical: 10 },
  impText: { color: COLORS.primary, fontWeight: '800', fontSize: FONT.xs },
  importMsg: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '700', marginTop: 8 },
  previewCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  prevRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 8, paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  prevName: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  prevPrice: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
  formCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, marginTop: 8 },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  thumb: { width: 48, height: 48, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg },
  thumbEmpty: { alignItems: 'center', justifyContent: 'center' },
  photoBtns: { flexDirection: 'row', gap: 8, marginTop: 6 },
  photoBtn: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 4 },
  photoBtnText: { color: COLORS.primary, fontSize: 10, fontWeight: '800' },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  itemPrice: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 2 },
  iconBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
});
