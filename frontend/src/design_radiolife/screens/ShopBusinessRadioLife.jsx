// RadioLife Shop — restaurant / business detail (web).
// Compact earn bar (Order · Check In · Pay), working check-in, a horizontal
// category filter and a full product/menu grid, with floating Order + Membership.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ChevronLeft, Star, ShoppingBag, MapPin, Wallet, Crown, Gift, Package as PackageIcon, CalendarDays, Check, Plus, Coins } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const EARN_ICONS = { "bag-check": ShoppingBag, location: MapPin, wallet: Wallet };

export default function ShopBusinessRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/")[1];
  const [b, setB] = useState(null);
  const [groups, setGroups] = useState([]); // [{key,title,items:[{id,name,price_cents,image_url,kind,hasVariants}]}]
  const [cat, setCat] = useState("all");
  const [loading, setLoading] = useState(true);
  const [checkedIn, setCheckedIn] = useState(false);
  const [checking, setChecking] = useState(false);

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
              hasVariants: (it.option_groups || []).length > 0,
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
              hasVariants: (p.variants || []).length > 0,
            });
          });
          if (alive) setGroups(Object.keys(byCat).map((c, i) => ({ key: `cat-${i}`, title: c, items: byCat[c] })));
        }
      } catch { if (alive) setB(null); }
      finally { if (alive) setLoading(false); }
    })();
    return () => { alive = false; };
  }, [id]);

  const allItems = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const shown = useMemo(() => {
    if (cat === "all") return allItems;
    return groups.find((g) => g.key === cat)?.items || [];
  }, [cat, groups, allItems]);

  const orderPath = () => {
    const sells = b.sells || [];
    if (sells.includes("services") || sells.includes("appointments")) return `/shop/services/${b.business_id}`;
    if (sells.includes("menu") || b.has_menu) return `/shop/menu/${b.business_id}`;
    if (sells.includes("products") || b.has_products) return `/shop/products/${b.business_id}`;
    return "/wallet";
  };

  const openItem = (it) => {
    if (it.kind === "product") navigate(`/shop/products/${b.business_id}`);
    else navigate(`/shop/menu/${b.business_id}`);
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

  return (
    <div className="pb-44 max-w-3xl mx-auto" data-testid="rl-shop-detail-page">
      {/* Cover */}
      <div className="relative h-44 sm:h-52 bg-slate-100">
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        <button onClick={() => navigate(-1)} data-testid="shop-detail-back"
          className="absolute top-3 left-3 w-10 h-10 rounded-full bg-black/45 text-white flex items-center justify-center">
          <ChevronLeft size={22} />
        </button>
      </div>

      <div className="px-4 pt-4">
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

        {/* Ways to earn — single top bar, all 3 in one line */}
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
      </div>

      {/* Category filter — horizontal scroll */}
      {groups.length > 0 && (
        <div className="mt-4 flex gap-2 overflow-x-auto px-4 pb-1" data-testid="shop-cat-rail">
          <button onClick={() => setCat("all")} data-testid="shop-cat-all"
            className={`shrink-0 px-4 h-9 rounded-full text-sm font-black whitespace-nowrap ${cat === "all" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>All</button>
          {groups.map((g) => (
            <button key={g.key} onClick={() => setCat(g.key)} data-testid={`shop-cat-${g.key}`}
              className={`shrink-0 px-4 h-9 rounded-full text-sm font-black whitespace-nowrap ${cat === g.key ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>{g.title}</button>
          ))}
        </div>
      )}

      {/* Product / menu grid — multiple rows, mobile friendly */}
      {groups.length > 0 ? (
        <div className="px-4 mt-2 grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="shop-item-grid">
          {shown.map((it) => (
            <button key={it.id} onClick={() => openItem(it)} data-testid={`shop-item-${it.id}`}
              className="text-left bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-orange-300 transition-colors">
              <div className="relative aspect-square bg-slate-100">
                {it.image_url && <img src={it.image_url} alt={it.name} className="w-full h-full object-cover" />}
                <span className="absolute bottom-2 right-2 w-8 h-8 rounded-full bg-orange-600 text-white flex items-center justify-center shadow"><Plus size={16} /></span>
              </div>
              <div className="p-2.5">
                <div className="text-sm font-bold text-slate-900 line-clamp-1">{it.name}</div>
                <div className="text-sm font-black text-slate-900 mt-1">{money(it.price_cents)}{it.hasVariants ? "+" : ""}</div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="px-4 mt-4">
          <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-950 px-3 py-2 rounded-full font-bold text-sm">
            <Coins size={16} /> Earn {b.default_bigpoints} BigPoints here
          </div>
        </div>
      )}

      {/* Contact — inline, no overlap */}
      {(b.phone || b.website) && (
        <div className="px-4 mt-4 flex flex-wrap gap-x-5 gap-y-1">
          {b.phone && <a href={`tel:${b.phone}`} className="text-orange-600 font-semibold text-sm">{b.phone}</a>}
          {b.website && <a href={b.website} className="text-orange-600 font-semibold text-sm truncate max-w-[220px]">{b.website}</a>}
        </div>
      )}

      {/* Floating action stack — bottom-right */}
      <div className="fixed bottom-24 right-3 z-30 flex flex-col items-end gap-2" data-testid="shop-detail-actions">
        {b.has_giftcards && (
          <button onClick={() => navigate(`/shop/giftcards/${b.business_id}`)} data-testid="shop-detail-giftcard"
            className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-md text-sm"><Gift size={15} className="text-orange-600" />Gift card</button>
        )}
        {b.has_packages && (
          <button onClick={() => navigate(`/shop/packages/${b.business_id}`)} data-testid="shop-detail-package"
            className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-md text-sm"><PackageIcon size={15} className="text-orange-600" />Packages</button>
        )}
        {b.has_events && (
          <button onClick={() => navigate(`/shop/events/${b.business_id}`)} data-testid="shop-detail-event"
            className="flex items-center gap-1.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-full pl-3 pr-4 py-2 shadow-md text-sm"><CalendarDays size={15} className="text-blue-600" />Events</button>
        )}
        {b.has_memberships && (
          <button onClick={() => navigate(`/shop/memberships/${b.business_id}`)} data-testid="shop-detail-membership"
            className="flex items-center gap-1.5 bg-white border-2 border-amber-400 text-amber-700 font-black rounded-full pl-3 pr-4 py-2 shadow-md text-sm"><Crown size={15} />Membership</button>
        )}
        <button onClick={() => navigate(orderPath())} data-testid="shop-detail-cta"
          className="flex items-center gap-1.5 bg-orange-600 text-white font-black rounded-full pl-4 pr-5 py-3 shadow-lg text-sm">
          <ShoppingBag size={16} />Order · Earn {b.default_bigpoints}
        </button>
      </div>
    </div>
  );
}
