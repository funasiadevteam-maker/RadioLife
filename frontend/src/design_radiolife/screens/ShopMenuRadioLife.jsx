// RadioLife Shop — Uber-Eats-style store page (web): store header (rating,
// pickup ETA, address), Pickup/Delivery toggle, search-in-store, category rail
// that scrolls to sections, roomier item rows, membership entitlements.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  ChevronLeft, Plus, Minus, Coins, Zap, ShoppingCart, Crown, Star, MapPin, Clock, Search, Store,
} from "lucide-react";
import { API } from "@/AuthContext";
import { useShopCart } from "../useShopCart";
import ItemOptionModal from "../ItemOptionModal";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopMenuRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/menu/")[1];
  const preItem = new URLSearchParams(window.location.search).get("item");
  const [data, setData] = useState(null);
  const [biz, setBiz] = useState(null);
  const [loading, setLoading] = useState(true);
  const [ents, setEnts] = useState([]);
  const [modalItem, setModalItem] = useState(null);
  const [q, setQ] = useState("");
  const [activeCat, setActiveCat] = useState("");
  const cart = useShopCart();
  const secRefs = useRef({});

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/menu`)
      .then((r) => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
    axios.get(`${API}/shop/businesses/${id}`)
      .then((r) => setBiz(r.data.business || r.data)).catch(() => {});
    axios.get(`${API}/shop/businesses/${id}/my-entitlements`)
      .then((r) => setEnts(r.data.items || [])).catch(() => setEnts([]));
  }, [id]);

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

  useEffect(() => {
    if (!data || !preItem) return;
    const found = (data.sections || []).flatMap((s) => s.items).find((it) => it.item_id === preItem);
    if (found) setModalItem(found);
  }, [data, ents, preItem]);

  const plainQty = (itemId) => sameBiz
    ? cart.items.filter((i) => i.item_id === itemId && (!i.selected_option_ids || !i.selected_option_ids.length) && !i.apply_entitlement_id).reduce((n, i) => n + i.qty, 0) : 0;
  const plainLineId = (itemId) => `${itemId}::::`;

  const quickAdd = (it) => cart.add(id, data.public_name, { item_id: it.item_id, name: it.name, price_cents: it.price_cents });
  const handleAdd = (it) => {
    const hasOpts = (it.option_groups || []).length > 0;
    if (hasOpts || itemEnt[it.item_id]) setModalItem(it);
    else quickAdd(it);
  };

  const sections = useMemo(() => {
    if (!data?.sections) return [];
    if (!q.trim()) return data.sections;
    const s = q.toLowerCase();
    return data.sections
      .map((sec) => ({ ...sec, items: sec.items.filter((it) => it.name.toLowerCase().includes(s) || (it.description || "").toLowerCase().includes(s)) }))
      .filter((sec) => sec.items.length);
  }, [data, q]);

  const scrollToCat = (title) => {
    setActiveCat(title);
    const el = secRefs.current[title];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Menu unavailable.</div>;

  const count = cart.count();
  const address = biz?.locations?.[0]?.address || biz?.city || null;

  return (
    <div className="pb-32" data-testid="rl-shop-menu-page">
      {/* Cover */}
      <div className="relative h-48 bg-slate-100">
        {data.cover_url && <img src={data.cover_url} alt={data.public_name} className="w-full h-full object-cover" />}
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
        <button onClick={() => navigate(-1)} data-testid="menu-back"
          className="absolute top-3 left-3 w-10 h-10 rounded-full bg-black/50 text-white flex items-center justify-center"><ChevronLeft size={22} /></button>
      </div>

      {/* Store header */}
      <div className="px-4 -mt-8 relative">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
          <h1 className="text-2xl font-black text-slate-900">{data.public_name}</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm">
            {biz?.rating > 0 && <span className="flex items-center gap-1 font-black text-slate-900"><Star size={14} className="text-amber-500 fill-amber-500" />{biz.rating}</span>}
            {biz?.category && <span className="text-slate-500 font-bold capitalize">{biz.category}</span>}
            <span className="flex items-center gap-1 text-green-700 font-bold"><Clock size={13} />Ready in ~15 min</span>
          </div>
          {address && <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1.5"><MapPin size={13} />{address}</div>}

          {/* Pickup / Delivery toggle */}
          <div className="flex gap-2 mt-3 bg-slate-100 rounded-full p-1" data-testid="menu-fulfillment">
            <button onClick={() => cart.setFulfillment && cart.setFulfillment("pickup")} data-testid="menu-fulfillment-pickup"
              className={`flex-1 py-2 rounded-full text-sm font-black ${(cart.fulfillment || "pickup") === "pickup" ? "bg-white text-slate-900 shadow" : "text-slate-500"}`}>Pickup</button>
            <button onClick={() => cart.setFulfillment && cart.setFulfillment("delivery")} data-testid="menu-fulfillment-delivery"
              className={`flex-1 py-2 rounded-full text-sm font-black ${cart.fulfillment === "delivery" ? "bg-white text-slate-900 shadow" : "text-slate-500"}`}>Delivery</button>
          </div>

          <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-950 px-3 py-1.5 rounded-full font-bold mt-3 text-sm">
            <Coins size={15} /> Earn {data.default_bigpoints} BigPoints
            {data.happy_hour && (
              <span className="ml-1 inline-flex items-center gap-1 bg-orange-600 text-white px-2 py-0.5 rounded-full text-xs" data-testid="menu-happy-hour">
                <Zap size={11} />{data.points_multiplier}X Happy Hour
              </span>
            )}
          </div>
        </div>
      </div>

      {ents.some((e) => e.remaining > 0) && (
        <div className="mx-4 mt-3 flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-xl px-3 py-2" data-testid="menu-membership-banner">
          <Crown size={16} className="text-orange-600" />
          <span className="text-xs font-bold text-orange-800">Your membership is active here — eligible items show a “Membership” tag.</span>
        </div>
      )}

      {/* Search */}
      <div className="px-4 mt-4">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2.5">
          <Search size={16} className="text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${data.public_name}…`} data-testid="menu-search"
            className="flex-1 bg-transparent text-sm outline-none" />
        </div>
      </div>

      {/* Category rail */}
      {data.sections?.length > 1 && (
        <div className="sticky top-0 z-[5] bg-[var(--rl-bg,transparent)] px-4 mt-3">
          <div className="flex gap-2 overflow-x-auto pb-2">
            {data.sections.map((sec) => (
              <button key={sec.title} onClick={() => scrollToCat(sec.title)} data-testid={`menu-cat-${sec.title}`}
                className={`shrink-0 px-4 py-1.5 rounded-full text-xs font-black whitespace-nowrap ${activeCat === sec.title ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>{sec.title}</button>
            ))}
          </div>
        </div>
      )}

      {/* Menu sections */}
      <div className="px-4">
        {sections.map((sec) => (
          <div key={sec.title} className="mt-6" ref={(el) => { secRefs.current[sec.title] = el; }}>
            <h2 className="text-lg font-black text-slate-900 mb-2">{sec.title}</h2>
            {sec.items.map((it) => {
              const qn = plainQty(it.item_id);
              const hasOpts = (it.option_groups || []).length > 0;
              const ent = itemEnt[it.item_id];
              return (
                <div key={it.item_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-3 mb-2.5" data-testid={`menu-item-${it.item_id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="text-[15px] font-bold text-slate-900">{it.name}</div>
                    {it.description && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{it.description}</div>}
                    <div className="flex items-center gap-2 mt-1.5">
                      <div className="text-sm font-black text-slate-900">{hasOpts ? `from ${money(it.price_cents)}` : money(it.price_cents)}</div>
                      {ent && <span className="inline-flex items-center gap-1 bg-orange-100 text-orange-700 text-[10px] font-black px-1.5 py-0.5 rounded-full" data-testid={`menu-ent-tag-${it.item_id}`}><Crown size={9} />Membership</span>}
                    </div>
                  </div>
                  <div className="relative shrink-0">
                    <div className="w-24 h-24 rounded-xl bg-slate-100 overflow-hidden">
                      {it.image_url
                        ? <img src={it.image_url} alt={it.name} className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center text-slate-300"><Store size={26} /></div>}
                    </div>
                    {!hasOpts && !ent && qn > 0 ? (
                      <div className="absolute -bottom-2 right-1 flex items-center gap-1 bg-white border border-slate-200 rounded-full px-1 py-0.5 shadow">
                        <button onClick={() => cart.dec(plainLineId(it.item_id))} data-testid={`menu-dec-${it.item_id}`} className="w-6 h-6 rounded-full bg-orange-50 flex items-center justify-center"><Minus size={14} className="text-orange-600" /></button>
                        <span className="font-black text-slate-900 w-4 text-center text-sm">{qn}</span>
                        <button onClick={() => cart.inc(plainLineId(it.item_id))} data-testid={`menu-inc-${it.item_id}`} className="w-6 h-6 rounded-full bg-orange-50 flex items-center justify-center"><Plus size={14} className="text-orange-600" /></button>
                      </div>
                    ) : (
                      <button onClick={() => handleAdd(it)} data-testid={`menu-add-${it.item_id}`}
                        className="absolute -bottom-2 right-1 w-9 h-9 rounded-full bg-white border border-slate-200 shadow flex items-center justify-center text-orange-600">
                        <Plus size={20} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
        {!sections.length && <p className="text-center text-slate-500 mt-8">{q ? "No items match your search." : "This restaurant hasn't published a menu yet."}</p>}
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
          <button onClick={() => navigate("/shop/checkout/menu")} data-testid="menu-checkout"
            className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3.5 shadow-lg">
            <ShoppingCart size={16} />View order ({count}) · {money(cart.subtotal())}
          </button>
        </div>
      )}
    </div>
  );
}
