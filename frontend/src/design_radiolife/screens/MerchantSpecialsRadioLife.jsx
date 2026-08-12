// RadioLife Merchant — Today's Specials manager. Feature your products/menu
// items with a blurb + optional sale price. Web, in-shell.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Flame, Check } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;

function ItemRow({ item, special, onSave, onRemove }) {
  const [on, setOn] = useState(!!special?.active);
  const [blurb, setBlurb] = useState(special?.blurb || "");
  const [sale, setSale] = useState(special?.sale_price_cents != null ? String((special.sale_price_cents / 100).toFixed(2)) : "");
  const [busy, setBusy] = useState(false);

  const save = async (active) => {
    setBusy(true);
    await onSave({
      kind: item.kind, item_id: item.item_id, blurb: blurb || null,
      sale_price_cents: sale ? Math.round(parseFloat(sale) * 100) : null, active,
    });
    setOn(active); setBusy(false);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`special-item-${item.item_id}`}>
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-slate-100 overflow-hidden shrink-0">
          {item.image_url && <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-black text-slate-900 truncate">{item.name}</div>
          <div className="text-xs text-slate-500">{money(item.price_cents)} · {item.kind === "menu" ? "Menu" : "Product"}</div>
        </div>
        <button onClick={() => save(!on)} disabled={busy} data-testid={`special-toggle-${item.item_id}`}
          className={`text-xs font-black rounded-full px-3 py-1.5 ${on ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-500"}`}>
          {on ? <span className="flex items-center gap-1"><Flame size={12} />Featured</span> : "Feature"}
        </button>
      </div>
      {on && (
        <div className="mt-3 flex gap-2">
          <input value={blurb} onChange={(e) => setBlurb(e.target.value)} placeholder="Blurb e.g. 20% off today" data-testid={`special-blurb-${item.item_id}`}
            className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold" />
          <input value={sale} onChange={(e) => setSale(e.target.value)} placeholder="Sale $" data-testid={`special-sale-${item.item_id}`}
            className="w-24 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
          <button onClick={() => save(true)} disabled={busy} data-testid={`special-save-${item.item_id}`}
            className="bg-slate-900 text-white font-black rounded-xl px-3 text-sm"><Check size={16} /></button>
        </div>
      )}
    </div>
  );
}

export default function MerchantSpecialsRadioLife() {
  const navigate = useNavigate();
  const [data, setData] = useState({ specials: [], products: [], menu: [] });
  const [loading, setLoading] = useState(true);
  const [noProfile, setNoProfile] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/merchant/marketplace/specials`);
      setData(r.data);
    } catch (e) { if (e?.response?.status === 404) setNoProfile(true); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const save = async (body) => { await axios.put(`${API}/merchant/marketplace/specials`, body); load(); };

  if (noProfile) return <div className="px-4 pt-16 text-center text-slate-500" data-testid="merchant-specials-noprofile">Register your shop first.</div>;

  const specialByItem = Object.fromEntries((data.specials || []).map((s) => [s.item_id, s]));
  const items = [...(data.products || []), ...(data.menu || [])];

  return (
    <div className="pb-24" data-testid="rl-merchant-specials-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="merchant-specials-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Today's Specials</h1>
      </div>
      <p className="px-4 mt-1 text-sm text-slate-500">Feature items to appear in the "Today's Specials" row on the Shop home.</p>

      <div className="px-4 mt-4 space-y-3">
        {loading ? <p className="text-slate-400 text-sm">Loading…</p>
          : !items.length ? <p className="text-slate-500 text-sm" data-testid="merchant-specials-empty">Add products or menu items first.</p>
          : items.map((it) => (
            <ItemRow key={`${it.kind}-${it.item_id}`} item={it} special={specialByItem[it.item_id]} onSave={save} />
          ))}
      </div>
    </div>
  );
}
