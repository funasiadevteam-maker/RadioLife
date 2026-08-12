// RadioLife Shop — restaurant menu + cart + pickup checkout (web).
// Items with sizes/modifiers open an option picker; members can apply an
// eligible membership entitlement (free base + paid upgrades) right here.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Plus, Minus, Coins, Zap, Gift, ShoppingCart, Crown, SlidersHorizontal } from "lucide-react";
import { API } from "@/AuthContext";
import { useShopCart } from "../useShopCart";
import ItemOptionModal from "../ItemOptionModal";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopMenuRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/menu/")[1];
  const preItem = new URLSearchParams(window.location.search).get("item");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ents, setEnts] = useState([]);
  const [modalItem, setModalItem] = useState(null);
  const cart = useShopCart();

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/menu`)
      .then((r) => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
    axios.get(`${API}/shop/businesses/${id}/my-entitlements`)
      .then((r) => setEnts(r.data.items || [])).catch(() => setEnts([]));
  }, [id]);

  // item_id -> best usable entitlement covering it (most specific wins)
  const itemEnt = useMemo(() => {
    const rank = (t) => (t === "item" || t === "product" ? 3 : t === "category" ? 2 : 1);
    const map = {};
    ents.forEach((e) => {
      if (e.remaining <= 0 || !e.available_now) return;
      (e.eligible_items || []).forEach((it) => {
        if (!map[it.id] || rank(e.target_type) > rank(map[it.id].target_type)) map[it.id] = e;
      });
    });
    return map;
  }, [ents]);

  const sameBiz = cart.businessId === id;

  // Deep-link from the wallet: auto-open a specific item's picker.
  useEffect(() => {
    if (!data || !preItem) return;
    const found = (data.sections || []).flatMap((s) => s.items).find((it) => it.item_id === preItem);
    if (found) setModalItem(found);
  }, [data, ents, preItem]);

  const plainQty = (itemId) => sameBiz
    ? cart.items.filter((i) => i.item_id === itemId && (!i.selected_option_ids || !i.selected_option_ids.length) && !i.apply_entitlement_id).reduce((n, i) => n + i.qty, 0) : 0;
  const plainLineId = (itemId) => `${itemId}::::`;

  const openItem = (it) => setModalItem(it);
  const quickAdd = (it) => cart.add(id, data.public_name, { item_id: it.item_id, name: it.name, price_cents: it.price_cents });
  const handleAdd = (it) => {
    const hasOpts = (it.option_groups || []).length > 0;
    if (hasOpts || itemEnt[it.item_id]) openItem(it);
    else quickAdd(it);
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Menu unavailable.</div>;

  const count = cart.count();

  return (
    <div className="pb-32" data-testid="rl-shop-menu-page">
      <div className="relative h-40 bg-slate-100">
        {data.cover_url && <img src={data.cover_url} alt={data.public_name} className="w-full h-full object-cover" />}
        <button onClick={() => navigate(-1)} data-testid="menu-back"
          className="absolute top-3 left-3 w-10 h-10 rounded-full bg-black/45 text-white flex items-center justify-center">
          <ChevronLeft size={22} />
        </button>
      </div>

      <div className="px-4 pt-4">
        <h1 className="text-2xl font-black text-slate-900">{data.public_name}</h1>
        <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-950 px-3 py-2 rounded-full font-bold mt-2">
          <Coins size={16} /> Earn {data.default_bigpoints} BigPoints
          {data.happy_hour && (
            <span className="ml-1 inline-flex items-center gap-1 bg-orange-600 text-white px-2 py-0.5 rounded-full text-xs" data-testid="menu-happy-hour">
              <Zap size={11} />{data.points_multiplier}X Happy Hour
            </span>
          )}
        </div>

        {ents.some((e) => e.remaining > 0) && (
          <div className="mt-3 flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-xl px-3 py-2" data-testid="menu-membership-banner">
            <Crown size={16} className="text-orange-600" />
            <span className="text-xs font-bold text-orange-800">Your membership is active here — eligible items show a “Membership” tag.</span>
          </div>
        )}

        {(data.sections || []).map((sec) => (
          <div key={sec.title} className="mt-6">
            <h2 className="text-base font-black text-slate-900 mb-2">{sec.title}</h2>
            {sec.items.map((it) => {
              const q = plainQty(it.item_id);
              const hasOpts = (it.option_groups || []).length > 0;
              const ent = itemEnt[it.item_id];
              return (
                <div key={it.item_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3 mb-2" data-testid={`menu-item-${it.item_id}`}>
                  {it.image_url && <img src={it.image_url} alt={it.name} className="w-14 h-14 rounded-lg object-cover bg-slate-100" />}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-bold text-slate-900">{it.name}</div>
                    {it.description && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{it.description}</div>}
                    <div className="flex items-center gap-2 mt-1">
                      <div className="text-sm font-black text-orange-600">{hasOpts ? `from ${money(it.price_cents)}` : money(it.price_cents)}</div>
                      {ent && <span className="inline-flex items-center gap-1 bg-orange-100 text-orange-700 text-[10px] font-black px-1.5 py-0.5 rounded-full" data-testid={`menu-ent-tag-${it.item_id}`}><Crown size={9} />Membership</span>}
                    </div>
                  </div>
                  {!hasOpts && !ent && q > 0 ? (
                    <div className="flex items-center gap-2 bg-orange-50 rounded-full px-1.5 py-1">
                      <button onClick={() => cart.dec(plainLineId(it.item_id))} data-testid={`menu-dec-${it.item_id}`}
                        className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Minus size={16} className="text-orange-600" /></button>
                      <span className="font-black text-slate-900 w-4 text-center">{q}</span>
                      <button onClick={() => cart.inc(plainLineId(it.item_id))} data-testid={`menu-inc-${it.item_id}`}
                        className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Plus size={16} className="text-orange-600" /></button>
                    </div>
                  ) : (
                    <button onClick={() => handleAdd(it)} data-testid={`menu-add-${it.item_id}`}
                      className="shrink-0 h-9 px-3 rounded-full bg-orange-600 text-white flex items-center justify-center gap-1 text-sm font-black">
                      {hasOpts ? <SlidersHorizontal size={15} /> : <Plus size={18} />}{hasOpts ? "Choose" : ""}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ))}
        {(!data.sections || !data.sections.length) && (
          <p className="text-center text-slate-500 mt-8">This restaurant hasn't published a menu yet.</p>
        )}
      </div>

      {modalItem && (
        <ItemOptionModal
          item={modalItem}
          entitlement={itemEnt[modalItem.item_id] || null}
          onClose={() => setModalItem(null)}
          onConfirm={(sel) => {
            cart.addLine(id, data.public_name, {
              item_id: modalItem.item_id, name: modalItem.name, price_cents: sel.unit_price_cents,
              qty: sel.qty, selected_option_ids: sel.selected_option_ids,
              option_summary: sel.option_summary, apply_entitlement_id: sel.apply_entitlement_id,
              entitlement_label: sel.entitlement_label,
            });
            setModalItem(null);
          }}
        />
      )}

      {count > 0 && (
        <div className="fixed bottom-20 left-0 right-0 px-4 max-w-md mx-auto z-10">
          <div className="bg-white border border-slate-200 rounded-2xl p-3 shadow-lg">
            <div className="flex items-center gap-2 text-xs text-slate-500 mb-2"><Gift size={14} className="text-green-600" />Choose gift card, points & payment on the next step.</div>
            <button onClick={() => navigate("/shop/checkout/menu")} data-testid="menu-checkout"
              className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-60">
              <ShoppingCart size={16} />Review &amp; Checkout ({count}) · {money(cart.subtotal())}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
