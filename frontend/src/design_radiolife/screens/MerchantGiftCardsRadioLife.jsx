// RadioLife Merchant — sell your own branded gift cards (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Trash2, Gift, Pencil } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(0)}`;
const parseDenoms = (s) => [...new Set(s.split(",").map((x) => Math.round((parseFloat(x.trim()) || 0) * 100)).filter((c) => c >= 100 && c <= 1000000))].sort((a, b) => a - b);

export default function MerchantGiftCardsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [denoms, setDenoms] = useState("25, 50, 100");
  const [allowPoints, setAllowPoints] = useState(true);
  const [allowCard, setAllowCard] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/marketplace/giftcards`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setDenoms("25, 50, 100"); setAllowPoints(true); setAllowCard(true); setEditingId(null); };
  const save = async () => {
    const denominations_cents = parseDenoms(denoms);
    if (!denominations_cents.length) { alert("Add at least one valid amount"); return; }
    setSaving(true);
    const body = { denominations_cents, allow_points: allowPoints, allow_card: allowCard, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/giftcards/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/giftcards/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p) => { setEditingId(p.product_id); setDenoms((p.denominations_cents || []).map((c) => c / 100).join(", ")); setAllowPoints(p.allow_points); setAllowCard(p.allow_card); };
  const del = async (pid) => { try { await axios.delete(`${API}/merchant/marketplace/giftcards/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  return (
    <div className="pb-24" data-testid="rl-merchant-giftcards-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mgc-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Gift Cards</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3" data-testid="mgc-form">
          <div className="font-black text-slate-900">{editingId ? "Edit gift card" : "New gift card"}</div>
          <label className="text-xs font-bold text-slate-500">Amounts ($, comma separated)</label>
          <input value={denoms} onChange={(e) => setDenoms(e.target.value)} placeholder="25, 50, 100" data-testid="mgc-denoms"
            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by card</span>
            <input type="checkbox" checked={allowCard} onChange={(e) => setAllowCard(e.target.checked)} data-testid="mgc-allow-card" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by BigPoints</span>
            <input type="checkbox" checked={allowPoints} onChange={(e) => setAllowPoints(e.target.checked)} data-testid="mgc-allow-points" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mgc-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="mgc-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Create"}</button>
          </div>
        </div>

        {!items.length && <p className="text-slate-500 text-sm" data-testid="mgc-empty">No gift cards yet.</p>}
        {items.map((p) => (
          <div key={p.product_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mgc-item-${p.product_id}`}>
            <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center"><Gift size={18} className="text-orange-600" /></div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{(p.denominations_cents || []).map(money).join(" · ")}</div>
              <div className="text-xs font-black text-slate-500">{p.allow_card ? "Card" : ""}{p.allow_card && p.allow_points ? " · " : ""}{p.allow_points ? "Points" : ""}{!p.active ? " · inactive" : ""}</div>
            </div>
            <button onClick={() => edit(p)} data-testid={`mgc-edit-${p.product_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(p.product_id)} data-testid={`mgc-del-${p.product_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
