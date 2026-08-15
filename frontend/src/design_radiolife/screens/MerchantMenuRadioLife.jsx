// RadioLife Merchant Menu Builder — CRUD + AI import (web).
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Sparkles, Image as ImageIcon, FileText, Grid3x3, Pencil, Trash2, Camera, Utensils, Plus, X } from "lucide-react";
import { API } from "@/AuthContext";
import OptionGroupsEditor from "../OptionGroupsEditor";

const money = (c) => `$${(c / 100).toFixed(2)}`;

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result || "").toString().split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function MerchantMenuRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ section: "", name: "", description: "", price: "" });
  const [optionGroups, setOptionGroups] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(null);
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState(null);
  const [photoBusy, setPhotoBusy] = useState(null);
  const [photoTarget, setPhotoTarget] = useState(null);
  const [combos, setCombos] = useState([]);
  const [comboForm, setComboForm] = useState({ name: "", price: "", reqs: [{ category: "", qty: 1 }, { category: "", qty: 1 }] });
  const [editingCombo, setEditingCombo] = useState(null);
  const [comboSaving, setComboSaving] = useState(false);
  const imgRef = useRef(); const pdfRef = useRef(); const xlsRef = useRef(); const photoRef = useRef();

  const load = useCallback(async () => {
    try {
      const [r, cr] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/menu`),
        axios.get(`${API}/merchant/marketplace/combos`).catch(() => ({ data: { items: [] } })),
      ]);
      setItems(r.data.items || []);
      setCombos(cr.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const resetCombo = () => { setComboForm({ name: "", price: "", reqs: [{ category: "", qty: 1 }, { category: "", qty: 1 }] }); setEditingCombo(null); };
  const setReq = (i, patch) => setComboForm((f) => ({ ...f, reqs: f.reqs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)) }));
  const addReq = () => setComboForm((f) => (f.reqs.length < 4 ? { ...f, reqs: [...f.reqs, { category: "", qty: 1 }] } : f));
  const removeReq = (i) => setComboForm((f) => ({ ...f, reqs: f.reqs.filter((_, idx) => idx !== i) }));
  const saveCombo = async () => {
    const reqs = comboForm.reqs.filter((r) => r.category).map((r) => ({ category: r.category, qty: Number(r.qty) || 1 }));
    if (!comboForm.name.trim() || !comboForm.price || reqs.length < 1) return;
    setComboSaving(true);
    try {
      await axios.post(`${API}/merchant/marketplace/combos`, {
        combo_id: editingCombo || undefined, name: comboForm.name.trim(),
        price_cents: Math.round((parseFloat(comboForm.price) || 0) * 100), requirements: reqs, active: true,
      });
      resetCombo(); load();
    } catch { /* ignore */ } finally { setComboSaving(false); }
  };
  const editCombo = (c) => { setEditingCombo(c.combo_id); setComboForm({ name: c.name, price: ((c.price_cents || 0) / 100).toString(), reqs: (c.requirements || []).map((r) => ({ category: r.category, qty: r.qty })) }); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const delCombo = async (cid) => { try { await axios.delete(`${API}/merchant/marketplace/combos/${cid}`); load(); } catch { /* ignore */ } };

  const reset = () => { setForm({ section: "", name: "", description: "", price: "" }); setOptionGroups([]); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const body = { section: form.section.trim() || "Menu", name: form.name.trim(),
      description: form.description.trim() || null, price_cents: Math.round((parseFloat(form.price) || 0) * 100),
      option_groups: optionGroups.filter((g) => g.name.trim() && g.options.some((o) => o.label.trim())), available: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/menu/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/menu/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (it) => { setEditingId(it.item_id); setForm({ section: it.section || "", name: it.name || "", description: it.description || "", price: ((it.price_cents || 0) / 100).toString() }); setOptionGroups(it.option_groups || []); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const del = async (id) => { try { await axios.delete(`${API}/merchant/marketplace/menu/items/${id}`); load(); } catch { /* ignore */ } };

  const clickPhoto = (itemId) => { setPhotoTarget(itemId); photoRef.current?.click(); };
  const onPhotoFile = async (e) => {
    const file = e.target.files?.[0]; const itemId = photoTarget;
    e.target.value = "";
    if (!file || !itemId) return;
    setPhotoBusy(itemId);
    try {
      const b64 = await fileToBase64(file);
      await axios.post(`${API}/merchant/marketplace/menu/items/${itemId}/photo`, { file_base64: b64, ext: "jpg" });
      load();
    } catch { /* ignore */ } finally { setPhotoBusy(null); setPhotoTarget(null); }
  };
  const aiPhoto = async (itemId) => {
    setPhotoBusy(itemId);
    try { await axios.post(`${API}/merchant/marketplace/menu/items/${itemId}/photo/ai`, {}); load(); }
    catch { /* ignore */ } finally { setPhotoBusy(null); }
  };

  const runAiUrl = async () => {
    if (!importUrl.trim()) return;
    setImporting("url"); setMsg(null); setPreview(null);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/menu/import/ai`, { source_type: "url", url: importUrl.trim() });
      setPreview(r.data.items || []); if (!r.data.items?.length) setMsg("No items found on that page.");
    } catch (e) { setMsg(e?.response?.data?.detail?.code || "Import failed"); } finally { setImporting(null); }
  };
  const onFile = async (e, kind) => {
    const file = e.target.files?.[0]; if (!file) return;
    setImporting(kind); setMsg(null); setPreview(null);
    try {
      const b64 = await fileToBase64(file);
      const endpoint = kind === "file" ? "/merchant/marketplace/menu/import/file" : "/merchant/marketplace/menu/import/ai";
      const body = kind === "file" ? { file_base64: b64, filename: file.name }
        : { source_type: kind === "pdf" ? "pdf" : "image", file_base64: b64 };
      const r = await axios.post(`${API}${endpoint}`, body);
      setPreview(r.data.items || []); if (!r.data.items?.length) setMsg("No items found in that file.");
    } catch (er) { setMsg(er?.response?.data?.detail?.code || "Import failed"); }
    finally { setImporting(null); e.target.value = ""; }
  };
  const addAll = async () => {
    if (!preview?.length) return;
    setSaving(true);
    try {
      await axios.post(`${API}/merchant/marketplace/menu/items/bulk`, {
        items: preview.map((it) => ({ section: it.section || "Menu", name: it.name, description: it.description || null, price_cents: it.price_cents || 0, available: true })), replace: false });
      setPreview(null); setImportUrl(""); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  const grouped = {};
  items.forEach((it) => { (grouped[it.section || "Menu"] ||= []).push(it); });
  const sections = Object.keys(grouped);

  return (
    <div className="pb-24" data-testid="rl-merchant-menu-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="menu-builder-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Menu Builder</h1>
      </div>

      <div className="px-4 space-y-4">
        {/* AI Import */}
        <div className="bg-orange-50 border border-orange-200 rounded-2xl p-4" data-testid="menu-import-card">
          <div className="font-black text-slate-900">✨ Import your menu with AI</div>
          <div className="text-xs text-slate-500 mt-1 mb-3">Paste your website, or upload a photo / PDF / Excel of your menu.</div>
          <div className="flex gap-2">
            <input value={importUrl} onChange={(e) => setImportUrl(e.target.value)} data-testid="import-url-input"
              placeholder="https://your-restaurant.com/menu"
              className="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            <button onClick={runAiUrl} disabled={!!importing} data-testid="import-url-btn"
              className="w-11 rounded-lg bg-orange-600 text-white flex items-center justify-center disabled:opacity-60"><Sparkles size={16} /></button>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <button onClick={() => imgRef.current?.click()} disabled={!!importing} data-testid="import-image-btn" className="flex items-center justify-center gap-1.5 bg-white border border-slate-200 rounded-lg py-2 text-xs font-bold text-orange-600 disabled:opacity-60"><ImageIcon size={15} />Photo</button>
            <button onClick={() => pdfRef.current?.click()} disabled={!!importing} data-testid="import-pdf-btn" className="flex items-center justify-center gap-1.5 bg-white border border-slate-200 rounded-lg py-2 text-xs font-bold text-orange-600 disabled:opacity-60"><FileText size={15} />PDF</button>
            <button onClick={() => xlsRef.current?.click()} disabled={!!importing} data-testid="import-excel-btn" className="flex items-center justify-center gap-1.5 bg-white border border-slate-200 rounded-lg py-2 text-xs font-bold text-orange-600 disabled:opacity-60"><Grid3x3 size={15} />Excel</button>
          </div>
          {importing && <div className="text-xs text-slate-500 mt-2">Reading your menu…</div>}
          {msg && <div className="text-xs text-rose-600 font-semibold mt-2" data-testid="import-msg">{msg}</div>}
          <input ref={imgRef} type="file" accept="image/*" className="hidden" onChange={(e) => onFile(e, "image")} />
          <input ref={pdfRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => onFile(e, "pdf")} />
          <input ref={xlsRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => onFile(e, "file")} />
        </div>
        <input ref={photoRef} type="file" accept="image/*" className="hidden" onChange={onPhotoFile} />

        {preview && preview.length > 0 && (
          <div className="bg-white border-2 border-green-500 rounded-2xl p-4" data-testid="import-preview">
            <div className="font-black text-slate-900">{preview.length} items found</div>
            <div className="mt-2 divide-y divide-slate-100">
              {preview.slice(0, 20).map((it, i) => (
                <div key={i} className="flex justify-between gap-2 py-1.5 text-xs">
                  <span className="text-slate-600 font-semibold truncate">{it.section} · {it.name}</span>
                  <span className="text-orange-600 font-black">{money(it.price_cents || 0)}</span>
                </div>
              ))}
            </div>
            <button onClick={addAll} disabled={saving} data-testid="import-add-all" className="mt-3 w-full bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-60">Add all {preview.length} to menu</button>
          </div>
        )}

        {/* Add/Edit */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2">
          <div className="font-black text-slate-900">{editingId ? "Edit item" : "Add item manually"}</div>
          <input value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} placeholder="Section (e.g. Mains)" data-testid="item-section" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Item name" data-testid="item-name" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="item-desc" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price (e.g. 12.50)" data-testid="item-price" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <OptionGroupsEditor value={optionGroups} onChange={setOptionGroups} />
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="item-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="item-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Add Item"}</button>
          </div>
        </div>

        {/* Meal Combos */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="combos-card">
          <div className="font-black text-slate-900 flex items-center gap-1.5"><Utensils size={16} className="text-orange-600" />{editingCombo ? "Edit combo" : "Meal Combos"}</div>
          <div className="text-xs text-slate-500 -mt-1">Bundle categories for a fixed price (e.g. 1 Pizza + 1 Drink = $15). Auto-applies in the customer's cart.</div>
          {sections.length === 0 ? (
            <div className="text-xs text-slate-400 py-2">Add menu items first so you can pick categories.</div>
          ) : (
            <>
              <input value={comboForm.name} onChange={(e) => setComboForm({ ...comboForm, name: e.target.value })} placeholder="Combo name (e.g. Pizza + Drink)" data-testid="combo-name" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              <input value={comboForm.price} onChange={(e) => setComboForm({ ...comboForm, price: e.target.value })} placeholder="Combo price (e.g. 15.00)" data-testid="combo-price" className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              <div className="text-xs font-black text-slate-500 pt-1">Requires</div>
              {comboForm.reqs.map((r, i) => (
                <div key={i} className="flex gap-2 items-center" data-testid={`combo-req-${i}`}>
                  <input type="number" min={1} max={10} value={r.qty} onChange={(e) => setReq(i, { qty: e.target.value })} data-testid={`combo-req-qty-${i}`} className="w-14 bg-slate-50 border border-slate-200 rounded-lg px-2 py-2 text-sm" />
                  <span className="text-xs text-slate-400">×</span>
                  <select value={r.category} onChange={(e) => setReq(i, { category: e.target.value })} data-testid={`combo-req-cat-${i}`} className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-2 text-sm">
                    <option value="">Pick a category…</option>
                    {sections.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  {comboForm.reqs.length > 1 && <button onClick={() => removeReq(i)} data-testid={`combo-req-remove-${i}`} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center"><X size={14} className="text-rose-600" /></button>}
                </div>
              ))}
              {comboForm.reqs.length < 4 && <button onClick={addReq} data-testid="combo-add-req" className="flex items-center gap-1 text-xs font-black text-orange-600"><Plus size={13} />Add requirement</button>}
              <div className="flex gap-2 pt-1">
                {editingCombo && <button onClick={resetCombo} data-testid="combo-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
                <button onClick={saveCombo} disabled={comboSaving} data-testid="combo-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingCombo ? "Update combo" : "Add combo"}</button>
              </div>
            </>
          )}
          {combos.length > 0 && (
            <div className="pt-2 space-y-2">
              {combos.map((c) => (
                <div key={c.combo_id} className="flex items-center gap-2 bg-slate-50 rounded-xl p-2.5" data-testid={`combo-item-${c.combo_id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-black text-slate-900">{c.name} · {money(c.price_cents)}</div>
                    <div className="text-xs text-slate-500">{(c.requirements || []).map((r) => `${r.qty}× ${r.category}`).join(" + ")}</div>
                  </div>
                  <button onClick={() => editCombo(c)} data-testid={`combo-edit-${c.combo_id}`} className="w-8 h-8 rounded-full bg-white flex items-center justify-center"><Pencil size={14} className="text-blue-600" /></button>
                  <button onClick={() => delCombo(c.combo_id)} data-testid={`combo-del-${c.combo_id}`} className="w-8 h-8 rounded-full bg-white flex items-center justify-center"><Trash2 size={14} className="text-rose-600" /></button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Existing */}
        {Object.keys(grouped).map((sec) => (
          <div key={sec}>
            <h3 className="text-base font-black text-slate-900 mb-2">{sec}</h3>
            {grouped[sec].map((it) => (
              <div key={it.item_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3 mb-2" data-testid={`builder-item-${it.item_id}`}>
                {it.image_url
                  ? <img src={it.image_url} alt={it.name} className="w-12 h-12 rounded-lg object-cover bg-slate-100" />
                  : <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center"><Camera size={16} className="text-slate-400" /></div>}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-slate-900">{it.name}</div>
                  <div className="text-sm font-black text-orange-600">{money(it.price_cents)}</div>
                  <div className="flex gap-2 mt-1">
                    <button onClick={() => clickPhoto(it.item_id)} disabled={!!photoBusy} data-testid={`builder-upload-${it.item_id}`} className="flex items-center gap-1 bg-orange-50 text-orange-600 rounded-full px-2 py-1 text-[10px] font-black disabled:opacity-50"><ImageIcon size={12} />Upload</button>
                    <button onClick={() => aiPhoto(it.item_id)} disabled={!!photoBusy} data-testid={`builder-aiphoto-${it.item_id}`} className="flex items-center gap-1 bg-orange-50 text-orange-600 rounded-full px-2 py-1 text-[10px] font-black disabled:opacity-50">{photoBusy === it.item_id ? "…" : <><Sparkles size={12} />AI Photo</>}</button>
                  </div>
                </div>
                <button onClick={() => edit(it)} data-testid={`builder-edit-${it.item_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
                <button onClick={() => del(it.item_id)} data-testid={`builder-del-${it.item_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
              </div>
            ))}
          </div>
        ))}
        {!items.length && <p className="text-center text-slate-500 mt-4">No items yet — add one or import above.</p>}
      </div>
    </div>
  );
}
