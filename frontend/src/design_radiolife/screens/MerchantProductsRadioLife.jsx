// RadioLife Merchant — products catalogue (variants + photos), delivery, fulfillment (web).
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Pencil, Trash2, Image as ImageIcon, Sparkles, Camera, ArrowRight, CheckCircle2 } from "lucide-react";
import { API } from "@/AuthContext";
import OptionGroupsEditor from "../OptionGroupsEditor";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const NEXT = { paid: { label: "Mark Packed", status: "packed" }, packed: { label: "Mark Shipped", status: "shipped" }, shipped: { label: "Mark Delivered", status: "delivered" } };
const parseVariants = (s) => s.split(",").map((p) => p.trim()).filter(Boolean).map((p) => {
  const [label, stock] = p.split(":"); return { label: (label || "").trim(), price_cents: 0, stock: parseInt((stock || "0").trim(), 10) || 0 };
}).filter((v) => v.label);
const variantsStr = (vs) => (vs || []).map((v) => `${v.label}:${v.stock}`).join(", ");

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result || "").toString().split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function MerchantProductsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [orders, setOrders] = useState([]);
  const [delivery, setDelivery] = useState({ pickup: true, delivery: false, fee_cents: 0, free_over_cents: 0 });
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", description: "", category: "", price: "", stock: "", variants: "", points: "" });
  const [optionGroups, setOptionGroups] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(null);
  const [photoTarget, setPhotoTarget] = useState(null);
  const photoRef = useRef();

  const load = useCallback(async () => {
    try {
      const [p, o, d] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/products`),
        axios.get(`${API}/merchant/marketplace/products/orders`),
        axios.get(`${API}/merchant/marketplace/products/delivery`),
      ]);
      setItems(p.data.items || []); setOrders(o.data.items || []); if (d.data.delivery) setDelivery(d.data.delivery);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: "", description: "", category: "", price: "", stock: "", variants: "", points: "" }); setOptionGroups([]); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const variants = parseVariants(form.variants);
    const body = { name: form.name.trim(), description: form.description.trim() || null, category: form.category.trim() || "Products",
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), stock: variants.length ? 0 : (parseInt(form.stock, 10) || 0),
      variants, option_groups: optionGroups.filter((g) => g.name.trim() && g.options.some((o) => o.label.trim())),
      bigpoints: form.points ? parseInt(form.points, 10) : null, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/products/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/products/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p) => { setEditingId(p.product_id); setForm({ name: p.name || "", description: p.description || "", category: p.category || "", price: ((p.price_cents || 0) / 100).toString(), stock: String(p.stock || 0), variants: variantsStr(p.variants), points: p.bigpoints != null ? String(p.bigpoints) : "" }); setOptionGroups(p.option_groups || []); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const del = async (id) => { try { await axios.delete(`${API}/merchant/marketplace/products/items/${id}`); load(); } catch { /* ignore */ } };
  const saveDelivery = async (patch) => { const nd = { ...delivery, ...patch }; setDelivery(nd); try { await axios.patch(`${API}/merchant/marketplace/products/delivery`, nd); } catch { /* ignore */ } };

  const clickPhoto = (pid) => { setPhotoTarget(pid); photoRef.current?.click(); };
  const onPhotoFile = async (e) => {
    const file = e.target.files?.[0]; const pid = photoTarget; e.target.value = "";
    if (!file || !pid) return;
    setPhotoBusy(pid);
    try { const b64 = await fileToBase64(file); await axios.post(`${API}/merchant/marketplace/products/items/${pid}/photo`, { file_base64: b64, ext: "jpg" }); load(); }
    catch { /* ignore */ } finally { setPhotoBusy(null); setPhotoTarget(null); }
  };
  const aiPhoto = async (pid) => { setPhotoBusy(pid); try { await axios.post(`${API}/merchant/marketplace/products/items/${pid}/photo/ai`, {}); load(); } catch { /* ignore */ } finally { setPhotoBusy(null); } };
  const advance = async (o) => { const n = NEXT[o.status]; if (!n) return; try { await axios.patch(`${API}/merchant/marketplace/products/orders/${o.order_id}/status`, { status: n.status }); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  const Input = (props) => <input {...props} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />;

  return (
    <div className="pb-24" data-testid="rl-merchant-products-page">
      <input ref={photoRef} type="file" accept="image/*" onChange={onPhotoFile} className="hidden" />
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mprod-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Products &amp; Delivery</h1>
      </div>

      <div className="px-4 space-y-4">
        {/* Delivery settings */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mprod-delivery-card">
          <div className="font-black text-slate-900">Delivery settings</div>
          {[["Pickup", "pickup", "mprod-pickup"], ["Delivery", "delivery", "mprod-delivery"]].map(([lbl, key, tid]) => (
            <div key={key} className="flex items-center justify-between py-1">
              <span className="text-sm font-bold text-slate-700">{lbl}</span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={!!delivery[key]} onChange={(e) => saveDelivery({ [key]: e.target.checked })} data-testid={tid} />
                <div className="w-11 h-6 bg-slate-200 peer-checked:bg-orange-600 rounded-full peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
              </label>
            </div>
          ))}
          {delivery.delivery && (
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Input type="number" defaultValue={(delivery.fee_cents || 0) / 100} onBlur={(e) => saveDelivery({ fee_cents: Math.round((parseFloat(e.target.value) || 0) * 100) })} placeholder="Fee $" data-testid="mprod-fee" />
              <Input type="number" defaultValue={(delivery.free_over_cents || 0) / 100} onBlur={(e) => saveDelivery({ free_over_cents: Math.round((parseFloat(e.target.value) || 0) * 100) })} placeholder="Free over $" data-testid="mprod-freeover" />
            </div>
          )}
        </div>

        {/* Add / edit product */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mprod-form">
          <div className="font-black text-slate-900">{editingId ? "Edit product" : "Add product"}</div>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" data-testid="mprod-name" />
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="mprod-desc" />
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} placeholder="Category" data-testid="mprod-cat" />
            <Input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price" data-testid="mprod-price" />
          </div>
          <Input value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} placeholder="Stock (if no variants)" data-testid="mprod-stock" />
          <Input value={form.variants} onChange={(e) => setForm({ ...form, variants: e.target.value })} placeholder="Variants e.g. S:5, M:3, L:2" data-testid="mprod-variants" />
          <Input value={form.points} onChange={(e) => setForm({ ...form, points: e.target.value })} placeholder="BigPoints (optional)" data-testid="mprod-points" />
          <OptionGroupsEditor value={optionGroups} onChange={setOptionGroups} />
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mprod-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="mprod-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Add Product"}</button>
          </div>
        </div>

        {/* Products */}
        <h3 className="text-base font-black text-slate-900">Your products</h3>
        {!items.length && <p className="text-slate-500 text-sm">No products yet.</p>}
        {items.map((p) => (
          <div key={p.product_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mprod-item-${p.product_id}`}>
            {p.image_url
              ? <img src={p.image_url} alt={p.name} className="w-12 h-12 rounded-lg object-cover bg-slate-100" />
              : <div className="w-12 h-12 rounded-lg bg-slate-100 flex items-center justify-center"><Camera size={16} className="text-slate-400" /></div>}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{p.name}</div>
              <div className="text-xs font-black text-orange-600">{money(p.price_cents)} · {p.variants?.length ? p.variants.map((v) => `${v.label}(${v.stock})`).join(" ") : `stock ${p.stock}`}</div>
              <div className="flex gap-2 mt-1">
                <button onClick={() => clickPhoto(p.product_id)} disabled={!!photoBusy} data-testid={`mprod-upload-${p.product_id}`} className="flex items-center gap-1 bg-orange-50 text-orange-600 rounded-full px-2 py-1 text-[10px] font-black disabled:opacity-50"><ImageIcon size={12} />Upload</button>
                <button onClick={() => aiPhoto(p.product_id)} disabled={!!photoBusy} data-testid={`mprod-aiphoto-${p.product_id}`} className="flex items-center gap-1 bg-orange-50 text-orange-600 rounded-full px-2 py-1 text-[10px] font-black disabled:opacity-50">{photoBusy === p.product_id ? "…" : <><Sparkles size={12} />AI</>}</button>
              </div>
            </div>
            <button onClick={() => edit(p)} data-testid={`mprod-edit-${p.product_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(p.product_id)} data-testid={`mprod-del-${p.product_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}

        {/* Orders */}
        <h3 className="text-base font-black text-slate-900">Incoming orders</h3>
        {!orders.length && <p className="text-slate-500 text-sm" data-testid="mprod-orders-empty">No paid orders yet.</p>}
        {orders.map((o) => (
          <div key={o.order_id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`mprod-order-${o.order_id}`}>
            <div className="flex items-center justify-between">
              <div className="text-xs font-black uppercase text-orange-600">{o.status}</div>
              <div className="text-xs font-black uppercase text-slate-400">{o.fulfillment}</div>
            </div>
            {(o.items || []).map((it, i) => <div key={i} className="text-sm text-slate-600 font-semibold">{it.qty}× {it.name}{it.variant_label ? ` (${it.variant_label})` : ""}</div>)}
            <div className="text-sm font-bold text-slate-900 mt-1">{money(o.total_cents)} · rewards {o.points_to_award}</div>
            {o.fulfillment === "delivery" && o.address && <div className="text-xs text-slate-500 mt-1">📍 {o.address}</div>}
            {NEXT[o.status] && (
              <button onClick={() => advance(o)} data-testid={`mprod-advance-${o.order_id}`}
                className="mt-3 w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-lg py-2.5">{NEXT[o.status].label}<ArrowRight size={15} /></button>
            )}
            {o.status === "delivered" && <div className="flex items-center gap-1.5 mt-3 text-green-600 text-xs font-bold"><CheckCircle2 size={16} />{o.points_to_award} BigPoints awarded</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
