// RadioLife Shop — restaurant / business detail (web).
// Now a full ordering surface: each card has an instant "+" add and a
// "Customize" button; a live cart is pinned on the right (desktop) with a
// floating "View order" bar on mobile. Works for both food menus and retail
// product stores. Compact earn bar + check-in + category filter preserved.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ChevronLeft, Star, ShoppingBag, ShoppingCart, MapPin, Wallet, Crown, Gift,
  Package as PackageIcon, CalendarDays, Check, Plus, Minus, Coins, Sliders, RotateCcw,
} from "lucide-react";
import { API } from "@/AuthContext";
import { useShopCart } from "../useShopCart";
import { useProductCart } from "../useProductCart";
import ItemOptionModal, { defaultMenuSelection, menuQuickAddReady } from "../ItemOptionModal";
import ProductVariantModal from "../components/ProductVariantModal";
import StoreCartPanel from "../components/StoreCartPanel";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const EARN_ICONS = { "bag-check": ShoppingBag, location: MapPin, wallet: Wallet };

export default function ShopBusinessRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/")[1];
  const [b, setB] = useState(null);
  const [groups, setGroups] = useState([]); // [{key,title,items:[{id,name,price_cents,image_url,kind,hasVariants,raw}]}]
  const [cat, setCat] = useState("all");
  const [loading, setLoading] = useState(true);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checking, setChecking] = useState(false);
  const [modalItem, setModalItem] = useState(null);      // menu customize
  const [variantProduct, setVariantProduct] = useState(null); // product customize
  const [lastOrder, setLastOrder] = useState(null);

  const menuCart = useShopCart();
  const productCart = useProductCart();

  const mode = useMemo(() => {
    if (!b) return "other";
    const sells = b.sells || [];
    if (sells.includes("menu") || b.has_menu) return "menu";
    if (sells.includes("products") || b.has_products) return "product";
    return "other";
  }, [b]);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/shop/businesses/${id}`);
        if (!alive) return;
        const biz = r.data.business;
        setB(biz);
        const sells = biz.sells || [];
        if (sells.includes("menu") || biz.has_menu) {
          const m = await axios.get(`${API}/shop/businesses/${id}/menu`);
          const secs = (m.data.sections || []).map((s, i) => ({
            key: `sec-${i}`, title: s.title,
            items: (s.items || []).map((it) => ({
              id: it.item_id, name: it.name, price_cents: it.price_cents,
              image_url: it.image_url, kind: "menu",
              hasVariants: (it.option_groups || []).length > 0, raw: it,
            })),
          }));
          if (alive) setGroups(secs);
        } else if (biz.has_products || sells.includes("products")) {
          const pr = await axios.get(`${API}/shop/businesses/${id}/products`);
          const byCat = {};
          (pr.data.products || []).forEach((p) => {
            const c = p.category || "All";
            (byCat[c] = byCat[c] || []).push({
              id: p.product_id, name: p.name, price_cents: p.price_cents,
              image_url: p.image_url, kind: "product",
              hasVariants: (p.variants || []).length > 0, raw: p,
            });
          });
          if (alive) setGroups(Object.keys(byCat).map((c, i) => ({ key: `cat-${i}`, title: c, items: byCat[c] })));
        }
      } catch { if (alive) setB(null); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [id]);

  // Last order for "Reorder" (menu stores only).
  useEffect(() => {
    if (mode !== "menu") { setLastOrder(null); return; }
    let alive = true;
    axios.get(`${API}/shop/orders/last/${id}`)
      .then((r) => { if (alive && r.data?.has_order && (r.data.items || []).length) setLastOrder(r.data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [id, mode]);

  const allItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const shown = useMemo(() => {
    if (cat === "all") return allItems;
    return groups.find((g) => g.key === cat)?.items || [];
  }, [cat, groups, allItems]);

  // ---- Ordering ----
  const quickAddMenu = (raw) => {
    if (!menuQuickAddReady(raw)) { setModalItem(raw); return; }
    const sel = defaultMenuSelection(raw);
    menuCart.addLine(id, b.public_name, {
      item_id: raw.item_id, name: raw.name, price_cents: sel.unit_price_cents,
      selected_option_ids: sel.selected_option_ids, option_summary: sel.option_summary,
      apply_entitlement_id: null,
    });
    toast.success(`Added ${raw.name}`);
  };
  const quickAddProduct = (raw) => {
    const variants = raw.variants || [];
    if (variants.length) {
      const v = variants.find((x) => x.stock > 0);
      if (!v) { toast.error("Sold out"); return; }
      productCart.add(id, b.public_name, raw, v, 1);
    } else {
      if (raw.stock <= 0) { toast.error("Sold out"); return; }
      productCart.add(id, b.public_name, raw, null, 1);
    }
    toast.success(`Added ${raw.name}`);
  };
  const onPlus = (it) => (it.kind === "product" ? quickAddProduct(it.raw) : quickAddMenu(it.raw));
  const onCustomize = (it) => (it.kind === "product" ? setVariantProduct(it.raw) : setModalItem(it.raw));

  // ---- Per-card "in cart" state (sticky add bar) ----
  const menuLines = menuCart.businessId === id ? menuCart.items : [];
  const productItems = productCart.groups[id]?.items || [];
  const qtyFor = (it) => it.kind === "product"
    ? productItems.filter((i) => i.product_id === it.raw.product_id).reduce((n, i) => n + i.qty, 0)
    : menuLines.filter((l) => l.item_id === it.raw.item_id).reduce((n, l) => n + l.qty, 0);
  const isPlain = (it) => it.kind === "product"
    ? !(it.raw.variants || []).length
    : !(it.raw.option_groups || []).length;
  const plainInc = (it) => it.kind === "product" ? productCart.inc(id, it.raw.product_id) : menuCart.inc(`${it.raw.item_id}::::`);
  const plainDec = (it) => it.kind === "product" ? productCart.dec(id, it.raw.product_id) : menuCart.dec(`${it.raw.item_id}::::`);

  // ---- Related upsell (cheapest add-ons not already in the cart) ----
  const ADDON = ["coffee", "drink", "beverage", "side", "dessert", "extra", "sauce"];
  const inCartKeys = new Set(mode === "product" ? productItems.map((i) => i.product_id) : menuLines.map((l) => l.item_id));
  const keyOfItem = (it) => (it.kind === "product" ? it.raw.product_id : it.raw.item_id);
  const preferred = [];
  const rest = [];
  groups.forEach((g) => {
    const addon = ADDON.some((p) => (g.title || "").toLowerCase().includes(p));
    g.items.forEach((it) => {
      if (inCartKeys.has(keyOfItem(it))) return;
      (addon ? preferred : rest).push(it);
    });
  });
  const suggestions = [...(preferred.length ? preferred : rest)]
    .sort((a, b) => a.price_cents - b.price_cents).slice(0, 3);

  // ---- "Make it a meal" combo (menu only) — mirrors backend detection ----
  const DRINK_KW = ["coffee", "drink", "beverage", "tea", "juice", "soda", "shake", "latte", "smoothie", "cola", "water", "mocktail"];
  const ADDON_KW = [...DRINK_KW, "dessert", "side", "extra", "sauce", "topping"];
  const sectionByItem = {};
  groups.forEach((g) => g.items.forEach((it) => { sectionByItem[keyOfItem(it)] = g.title || ""; }));
  const lc = (s) => (s || "").toLowerCase();
  const drinkUnits = menuLines.filter((l) => DRINK_KW.some((k) => lc(sectionByItem[l.item_id]).includes(k))).map((l) => l.price_cents);
  const hasMainInCart = menuLines.some((l) => !ADDON_KW.some((k) => lc(sectionByItem[l.item_id]).includes(k)));
  const comboApplies = mode === "menu" && hasMainInCart && drinkUnits.length > 0;
  const combo = { applies: comboApplies, saveCents: comboApplies ? Math.round(Math.min(...drinkUnits) * 0.30) : 0 };

  const reorderLast = () => {
    if (!lastOrder?.items?.length) return;
    lastOrder.items.forEach((li) => menuCart.addLine(id, b.public_name, {
      item_id: li.item_id, name: li.name, price_cents: li.price_cents,
      selected_option_ids: li.selected_option_ids || [], option_summary: li.option_summary,
      note: li.note, qty: li.qty || 1,
    }));
    toast.success(lastOrder.dropped ? "Added your last order (some items are no longer available)" : "Added your last order");
  };

  // ---- Cart totals (for mobile bar) ----
  const cartCount = mode === "product"
    ? (productCart.groups[id]?.items || []).reduce((n, i) => n + i.qty, 0)
    : (menuCart.businessId === id ? menuCart.count() : 0);
  const cartSubtotal = mode === "product"
    ? (productCart.groups[id]?.items || []).reduce((n, i) => n + i.price_cents * i.qty, 0)
    : (menuCart.businessId === id ? menuCart.subtotal() : 0);
  const reviewPath = mode === "product" ? "/shop/cart" : "/shop/checkout/menu";

  const orderPath = () => {
    const sells = b.sells || [];
    if (sells.includes("services") || sells.includes("appointments")) return `/shop/services/${b.business_id}`;
    return "/wallet";
  };

  const doCheckin = async () => {
    if (checkedIn || checking) return;
    setChecking(true);
    try {
      const r = await axios.post(`${API}/shop/businesses/${id}/checkin`);
      setCheckedIn(true);
      toast.success(r.data.already ? "Already checked in today" : `Checked in! +${r.data.awarded} BigPoints`);
    } catch { toast.error("Could not check in"); }
    finally { setChecking(false); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!b) return <div className="px-4 pt-10 text-center text-slate-500">Business not found.</div>;

  const ways = b.ways_to_earn || [];
  const orderable = mode === "menu" || mode === "product";

  // Secondary shop extras (inline, wrap — avoids overlapping the right cart).
  const extras = (
    <div className="flex flex-wrap gap-2" data-testid="shop-detail-actions">
      {mode === "menu" && lastOrder && (
        <button onClick={reorderLast} data-testid="shop-reorder-last"
          className="flex items-center gap-1.5 bg-orange-50 border-2 border-orange-500 text-orange-700 font-black rounded-full pl-3 pr-4 py-2 shadow-sm text-sm">
          <RotateCcw size={15} />Reorder last order
        </button>
      )}
      {b.has_giftcards && (
        <button onClick={() => navigate(`/shop/giftcards/${b.business_id}`)} data-testid="shop-detail-giftcard"
          className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-sm text-sm"><Gift size={15} className="text-orange-600" />Gift card</button>
      )}
      {b.has_packages && (
        <button onClick={() => navigate(`/shop/packages/${b.business_id}`)} data-testid="shop-detail-package"
          className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-sm text-sm"><PackageIcon size={15} className="text-orange-600" />Packages</button>
      )}
      {b.has_events && (
        <button onClick={() => navigate(`/shop/events/${b.business_id}`)} data-testid="shop-detail-event"
          className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-sm text-sm"><CalendarDays size={15} className="text-blue-600" />Events</button>
      )}
      {b.has_memberships && (
        <button onClick={() => navigate(`/shop/memberships/${b.business_id}`)} data-testid="shop-detail-membership"
          className="flex items-center gap-1.5 bg-white border-2 border-amber-400 text-amber-700 font-black rounded-full pl-3 pr-4 py-2 shadow-sm text-sm"><Crown size={15} />Membership</button>
      )}
      {!orderable && (
        <button onClick={() => navigate(orderPath())} data-testid="shop-detail-cta"
          className="flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-full pl-4 pr-5 py-2 shadow-sm text-sm">
          <ShoppingBag size={16} />Order · Earn {b.default_bigpoints}
        </button>
      )}
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto pb-28 lg:pb-10" data-testid="rl-shop-detail-page">
      {/* Cover */}
      <div className="relative h-44 sm:h-52 bg-slate-100">
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        <button onClick={() => navigate(-1)} data-testid="shop-detail-back"
          className="absolute top-3 left-3 w-10 h-10 rounded-full bg-black/45 text-white flex items-center justify-center">
          <ChevronLeft size={22} />
        </button>
      </div>

      <div className="lg:flex lg:gap-6 lg:px-4">
        {/* Main column */}
        <div className="lg:flex-1 lg:min-w-0">
          <div className="px-4 lg:px-0 pt-4">
            <div className="flex items-start justify-between gap-3">
              <h1 className="text-2xl font-black text-slate-900">{b.public_name}</h1>
              {b.rating ? (
                <span className="flex items-center gap-1 bg-amber-100 text-amber-900 px-3 py-1.5 rounded-full font-black shrink-0">
                  <Star size={13} className="fill-amber-500 text-amber-500" />{b.rating.toFixed(1)}</span>
              ) : null}
            </div>
            <div className="text-slate-500 text-sm font-semibold capitalize mt-0.5">
              {b.subcategory || b.category}{b.city ? ` · ${b.city}` : ""}</div>
            {b.description && <p className="text-slate-600 text-sm leading-relaxed mt-2">{b.description}</p>}

            {/* Ways to earn — single top bar */}
            {ways.length > 0 && (
              <div className="mt-3 flex items-stretch bg-white border border-slate-200 rounded-2xl overflow-hidden" data-testid="shop-earn-bar">
                {ways.map((w, i) => {
                  const Icon = EARN_ICONS[w.icon] || Coins;
                  const isCheckin = (w.label || "").toLowerCase().includes("check");
                  const inner = (
                    <>
                      <Icon size={16} className={isCheckin && checkedIn ? "text-green-600" : "text-orange-600"} />
                      <span className="text-[11px] font-bold text-slate-700 leading-tight text-center mt-1">{w.label}</span>
                      <span className={`text-xs font-black mt-0.5 ${isCheckin && checkedIn ? "text-green-600" : "text-slate-900"}`}>
                        {isCheckin && checkedIn ? <span className="inline-flex items-center gap-0.5"><Check size={12} />Done</span> : `+${w.points}`}
                      </span>
                    </>
                  );
                  const base = `flex-1 flex flex-col items-center justify-center px-2 py-3 ${i > 0 ? "border-l border-slate-200" : ""}`;
                  return isCheckin ? (
                    <button key={i} onClick={doCheckin} disabled={checking} data-testid="shop-checkin-btn"
                      className={`${base} active:bg-slate-50 ${checkedIn ? "bg-green-50" : "bg-orange-50/40"}`}>{inner}</button>
                  ) : (
                    <div key={i} className={base} data-testid={`shop-earn-${i}`}>{inner}</div>
                  );
                })}
              </div>
            )}

            {/* Shop extras */}
            <div className="mt-3">{extras}</div>
          </div>

          {/* Category filter — horizontal scroll */}
          {groups.length > 0 && (
            <div className="mt-4 flex gap-2 overflow-x-auto px-4 lg:px-0 pb-1" data-testid="shop-cat-rail">
              <button onClick={() => setCat("all")} data-testid="shop-cat-all"
                className={`shrink-0 px-4 h-9 rounded-full text-sm font-black whitespace-nowrap ${cat === "all" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>All</button>
              {groups.map((g) => (
                <button key={g.key} onClick={() => setCat(g.key)} data-testid={`shop-cat-${g.key}`}
                  className={`shrink-0 px-4 h-9 rounded-full text-sm font-black whitespace-nowrap ${cat === g.key ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>{g.title}</button>
              ))}
            </div>
          )}

          {/* Product / menu grid */}
          {groups.length > 0 ? (
            <div className="px-4 lg:px-0 mt-2 grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="shop-item-grid">
              {shown.map((it) => {
                const qn = orderable ? qtyFor(it) : 0;
                const plain = isPlain(it);
                return (
                <div key={it.id} data-testid={`shop-item-${it.id}`}
                  className="bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-orange-300 transition-colors flex flex-col">
                  <div className="relative bg-slate-100 overflow-hidden" style={{ aspectRatio: "1 / 1" }}>
                    {it.image_url && <img src={it.image_url} alt={it.name} className="w-full h-full object-cover" />}
                    {qn > 0 && (
                      <span className="absolute top-2 right-2 inline-flex items-center gap-1 bg-green-600 text-white text-[11px] font-black rounded-full pl-1.5 pr-2 py-0.5 shadow" data-testid={`shop-incart-${it.id}`}>
                        <Check size={11} />{qn}
                      </span>
                    )}
                    {orderable && (
                      <button onClick={() => onCustomize(it)} data-testid={`shop-customize-${it.id}`}
                        className="absolute bottom-2 left-2 inline-flex items-center gap-1 bg-white/95 backdrop-blur text-slate-800 text-[11px] font-black rounded-full pl-2 pr-2.5 py-1.5 shadow border border-slate-200">
                        <Sliders size={12} className="text-orange-600" />Customize
                      </button>
                    )}
                    {orderable && qn > 0 && plain ? (
                      <div className="absolute bottom-2 right-2 flex items-center gap-1 bg-white rounded-full px-1 py-0.5 shadow border border-slate-200" data-testid={`shop-stepper-${it.id}`}>
                        <button onClick={() => plainDec(it)} data-testid={`shop-dec-${it.id}`} className="w-7 h-7 rounded-full bg-orange-50 flex items-center justify-center"><Minus size={15} className="text-orange-600" /></button>
                        <span className="font-black text-slate-900 w-5 text-center text-sm">{qn}</span>
                        <button onClick={() => plainInc(it)} data-testid={`shop-inc-${it.id}`} className="w-7 h-7 rounded-full bg-orange-50 flex items-center justify-center"><Plus size={15} className="text-orange-600" /></button>
                      </div>
                    ) : (
                      <button onClick={() => (orderable ? onPlus(it) : navigate(`/shop/menu/${b.business_id}`))} data-testid={`shop-add-${it.id}`}
                        className="absolute bottom-2 right-2 w-9 h-9 rounded-full bg-orange-600 text-white flex items-center justify-center shadow hover:bg-orange-700 active:scale-95 transition">
                        <Plus size={18} />
                      </button>
                    )}
                  </div>
                  <div className="p-2.5">
                    <div className="text-sm font-bold text-slate-900 line-clamp-1">{it.name}</div>
                    <div className="text-sm font-black text-slate-900 mt-1">{money(it.price_cents)}{it.hasVariants ? "+" : ""}</div>
                  </div>
                </div>
                );
              })}
            </div>
          ) : (
            <div className="px-4 lg:px-0 mt-4">
              <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-950 px-3 py-2 rounded-full font-bold text-sm">
                <Coins size={16} /> Earn {b.default_bigpoints} BigPoints here
              </div>
            </div>
          )}

          {/* Contact */}
          {(b.phone || b.website) && (
            <div className="px-4 lg:px-0 mt-4 flex flex-wrap gap-x-5 gap-y-1">
              {b.phone && <a href={`tel:${b.phone}`} className="text-orange-600 font-semibold text-sm">{b.phone}</a>}
              {b.website && <a href={b.website} className="text-orange-600 font-semibold text-sm truncate max-w-[220px]">{b.website}</a>}
            </div>
          )}
        </div>

        {/* Pinned cart (desktop) */}
        {orderable && (
          <aside className="hidden lg:block lg:w-[340px] lg:shrink-0 mt-4">
            <div className="sticky top-4">
              <StoreCartPanel mode={mode} bizId={id} bizName={b.public_name} suggestions={suggestions} onAdd={onPlus} combo={combo} />
            </div>
          </aside>
        )}
      </div>

      {/* Mobile floating cart bar */}
      {orderable && cartCount > 0 && (
        <div className="lg:hidden fixed bottom-24 left-0 right-0 px-4 max-w-md mx-auto z-30">
          <button onClick={() => navigate(reviewPath)} data-testid="shop-mobile-cart-bar"
            className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3.5 shadow-lg">
            <ShoppingCart size={16} />View order ({cartCount}) · {money(cartSubtotal)}
          </button>
        </div>
      )}

      {/* Customize modals */}
      {modalItem && (
        <ItemOptionModal
          item={modalItem}
          entitlement={null}
          onClose={() => setModalItem(null)}
          onConfirm={(sel) => {
            menuCart.addLine(id, b.public_name, {
              item_id: modalItem.item_id, name: modalItem.name, price_cents: sel.unit_price_cents,
              qty: sel.qty, selected_option_ids: sel.selected_option_ids,
              option_summary: sel.option_summary, note: sel.note,
              apply_entitlement_id: sel.apply_entitlement_id,
              entitlement_label: sel.entitlement_label,
            });
            setModalItem(null);
            toast.success(`Added ${modalItem.name}`);
          }}
        />
      )}
      {variantProduct && (
        <ProductVariantModal
          product={variantProduct}
          onClose={() => setVariantProduct(null)}
          onConfirm={({ variant, qty, note }) => {
            productCart.add(id, b.public_name, variantProduct, variant, qty, note);
            setVariantProduct(null);
            toast.success(`Added ${variantProduct.name}`);
          }}
        />
      )}
    </div>
  );
}
