// RadioLife Shop — web consumer marketplace (Super Marketplace Phase A).
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Search, Star, Store, ArrowRight, Coins, ShoppingCart, Crown, CreditCard, QrCode, User, Receipt, LayoutDashboard, X, Calendar, Sparkles, Navigation, RotateCcw } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, RLChip } from "../DesignSystem";
import { useProductCart } from "../useProductCart";
import { useShopCart } from "../useShopCart";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

function BizCard({ b }) {
  return (
    <Link to={`/shop/${b.business_id}`} data-testid={`shop-biz-${b.business_id}`}
      className="block rounded-2xl overflow-hidden bg-white border border-slate-200 hover:shadow-lg transition-shadow">
      <div className="relative h-32 bg-slate-100">
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        {b.promoted ? <span className="absolute top-2 left-2 text-[10px] font-black text-white bg-orange-600 px-2 py-0.5 rounded-full">Promoted</span>
          : b.sponsored ? <span className="absolute top-2 left-2 text-[10px] font-bold text-white bg-black/60 px-2 py-0.5 rounded-full">Sponsored</span> : null}
        <span className="absolute bottom-2 right-2 flex items-center gap-1 bg-amber-400 text-amber-950 text-[11px] font-black px-2 py-1 rounded-full">
          <Coins size={11} /> Earn {b.default_bigpoints}
        </span>
      </div>
      <div className="p-3">
        <div className="font-black text-slate-900 truncate">{b.public_name}</div>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-xs text-slate-500 capitalize truncate">{b.subcategory || b.category}</span>
          {b.rating ? <span className="flex items-center gap-1 text-xs font-bold text-slate-700">
            <Star size={11} className="text-amber-500 fill-amber-500" />{b.rating.toFixed(1)}</span> : null}
        </div>
      </div>
    </Link>
  );
}

export default function ShopRadioLife() {
  const navigate = useNavigate();
  const [home, setHome] = useState(null);
  const [cats, setCats] = useState([]);
  const [category, setCategory] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("featured");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isMerchant, setIsMerchant] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [usual, setUsual] = useState(null);
  const [usualDismissed, setUsualDismissed] = useState(false);
  const menuCart = useShopCart();
  const cartCount = useProductCart((st) => Object.values(st.groups).reduce((n, g) => n + g.items.reduce((m, i) => m + i.qty, 0), 0));

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/shop/home`).catch(() => ({ data: {} })),
      axios.get(`${API}/shop/categories`).catch(() => ({ data: { items: [] } })),
    ]).then(([h, c]) => {
      setHome(h.data);
      setCats([{ key: "all", name: "All" }, ...(c.data.items || [])]);
      setLoading(false);
    });
    // Role-gate merchant tools — only owners of a business see the dashboard.
    axios.get(`${API}/merchant/marketplace/profile`)
      .then((r) => setIsMerchant(!!r.data?.profile))
      .catch(() => setIsMerchant(false));
    // "Get your usual" one-tap for returning customers (auth-only; 401 → hide).
    axios.get(`${API}/shop/usual`)
      .then((r) => { if (r.data?.has_usual) setUsual(r.data); })
      .catch(() => setUsual(null));
  }, []);

  // Promotion analytics — beacon one impression per promoted shop shown.
  const trackedRef = React.useRef(new Set());
  useEffect(() => {
    const shown = [];
    (home?.sections || []).forEach((s) => (s.items || []).forEach((b) => { if (b.promoted) shown.push(b.business_id); }));
    (items || []).forEach((b) => { if (b.promoted) shown.push(b.business_id); });
    shown.forEach((bid) => {
      if (bid && !trackedRef.current.has(bid)) {
        trackedRef.current.add(bid);
        axios.post(`${API}/shop/track`, { business_id: bid, kind: "impression" }).catch(() => {});
      }
    });
  }, [home, items]);

  const addUsual = () => {
    if (!usual?.items?.length) return;
    usual.items.forEach((u) => menuCart.addLine(usual.business_id, usual.business_name, {
      item_id: u.item_id, name: u.name, price_cents: u.price_cents,
      selected_option_ids: u.selected_option_ids || [], option_summary: u.option_summary, note: u.note,
    }));
    navigate("/shop/checkout/menu");
  };

  useEffect(() => {
    const params = { sort };
    if (category !== "all") params.category = category;
    if (q.trim()) params.q = q.trim();
    axios.get(`${API}/shop/businesses`, { params }).then((r) => setItems(r.data.items || [])).catch(() => setItems([]));
  }, [category, q, sort]);

  const browsing = category !== "all" || q.trim();
  const sections = useMemo(() => (home?.sections || []).filter((s) => s.items?.length), [home]);
  const specials = home?.specials || [];

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading Shop…</div>;

  return (
    <div className="px-4 pt-6 pb-8 space-y-4" data-testid="rl-shop-page">
      <header className="flex items-start justify-between gap-3 relative">
        <div>
          <div className="text-orange-600 text-[11px] font-black tracking-widest">RADIOLIFE SHOP</div>
          <h1 className="text-3xl font-black tracking-tight text-slate-900 leading-tight mt-1">
            {home?.headline || "SHOP LOCAL. EARN BIGPOINTS."}</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button type="button" onClick={() => setMenuOpen((o) => !o)} data-testid="shop-account-button"
            className="w-11 h-11 rounded-full bg-white border border-slate-200 flex items-center justify-center hover:shadow-md transition-shadow">
            <User size={20} className="text-slate-700" />
          </button>
          <Link to="/shop/cart" data-testid="shop-cart-button"
            className="relative w-11 h-11 rounded-full bg-white border border-slate-200 flex items-center justify-center hover:shadow-md transition-shadow">
            <ShoppingCart size={20} className="text-slate-700" />
            {cartCount > 0 && (
              <span data-testid="shop-cart-badge"
                className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full bg-orange-600 text-white text-[11px] font-black flex items-center justify-center">
                {cartCount}</span>
            )}
          </Link>
        </div>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setMenuOpen(false)} />
            <div data-testid="shop-account-menu"
              className="fixed top-20 right-4 z-[100] w-60 bg-white rounded-2xl border border-slate-200 shadow-xl p-2">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-xs font-black text-slate-400 tracking-wide">MY ACCOUNT</span>
                <button onClick={() => setMenuOpen(false)} className="text-slate-400 hover:text-slate-700"><X size={15} /></button>
              </div>
              {isMerchant && (
                <Link to="/shop/merchant" data-testid="shop-merchant-dash" onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 mb-1 bg-orange-600 text-white font-black text-sm hover:bg-orange-700">
                  <LayoutDashboard size={16} /> Merchant Dashboard
                </Link>
              )}
              {[
                ["/shop/concierge", Sparkles, "Order by Chat", "shop-concierge-link"],
                ["/shop/orders", Receipt, "My Orders", "shop-my-orders"],
                ["/shop/product-orders", Store, "Product Orders", "shop-my-product-orders"],
                ["/shop/bookings", Calendar, "My Bookings", "shop-my-bookings"],
                ["/shop/memberships", Crown, "My Memberships", "shop-my-memberships-link"],
                ["/shop/loyalty", Star, "My Loyalty", "shop-my-loyalty"],
                ["/shop/wallet/cards", CreditCard, "Payment Methods", "shop-payment-methods"],
                ["/shop/scan-pay", QrCode, "Scan to Pay", "shop-scan-pay"],
              ].map(([to, Icon, label, tid]) => (
                <Link key={to} to={to} data-testid={tid} onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-bold text-slate-700 hover:bg-orange-50">
                  <Icon size={16} className="text-orange-600" /> {label}
                </Link>
              ))}
            </div>
          </>
        )}
      </header>

      <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-full px-4 py-3">
        <Search size={18} className="text-slate-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="shop-search"
          placeholder="What are you looking for?" className="flex-1 outline-none text-sm text-slate-800" />
      </div>

      <Link to="/shop/near-me" data-testid="shop-near-me"
        className="flex items-center gap-2 bg-orange-50 border border-orange-200 rounded-full px-4 py-2.5 hover:bg-orange-100 transition-colors">
        <Navigation size={16} className="text-orange-600" />
        <span className="flex-1 text-sm font-bold text-slate-800">Explore shops &amp; services near you</span>
        <ArrowRight size={16} className="text-slate-400" />
      </Link>

      <div className="flex gap-2 overflow-x-auto pb-1" data-testid="shop-categories">
        {cats.map((c) => (
          <RLChip key={c.key} active={category === c.key} onClick={() => setCategory(c.key)}
            data-testid={`shop-cat-${c.key}`} className="whitespace-nowrap capitalize">{c.name}</RLChip>
        ))}
      </div>

      {isMerchant ? (
        <Link to="/shop/merchant" data-testid="shop-merchant-banner"
          className="flex items-center gap-3 bg-slate-900 text-white rounded-2xl p-4 hover:bg-slate-800 transition-colors">
          <LayoutDashboard size={22} />
          <div className="flex-1">
            <div className="font-black">Merchant Dashboard</div>
            <div className="text-xs opacity-80">Manage your menu, products, orders, memberships & more.</div>
          </div>
          <ArrowRight size={22} />
        </Link>
      ) : (
        <Link to="/sell" data-testid="shop-sell-cta"
          className="flex items-center gap-3 bg-orange-600 text-white rounded-2xl p-4 hover:bg-orange-700 transition-colors">
          <Store size={22} />
          <div className="flex-1">
            <div className="font-black">Sell on RadioLife</div>
            <div className="text-xs opacity-90">List your business & reward local customers with BigPoints.</div>
          </div>
          <ArrowRight size={22} />
        </Link>
      )}

      <Link to="/shop/concierge" data-testid="shop-concierge-banner"
        className="flex items-center gap-3 bg-gradient-to-br from-orange-600 to-amber-500 text-white rounded-2xl p-4 hover:opacity-95 transition-opacity">
        <Sparkles size={22} />
        <div className="flex-1">
          <div className="font-black">Order by chat ✨</div>
          <div className="text-xs opacity-90">Tell our AI concierge what you want — it applies your memberships automatically.</div>
        </div>
        <ArrowRight size={22} />
      </Link>

      {browsing ? (
        <>
          <div className="flex items-center gap-2">
            {[["featured", "Featured"], ["bigpoints", "Most BigPoints"], ["rating", "Top Rated"]].map(([k, l]) => (
              <RLChip key={k} active={sort === k} onClick={() => setSort(k)} data-testid={`shop-sort-${k}`}>{l}</RLChip>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {items.map((b) => <BizCard key={b.business_id} b={b} />)}
          </div>
          {items.length === 0 && <div className="text-center text-slate-400 py-8">No businesses found.</div>}
        </>
      ) : (
        <>
          {usual && !usualDismissed && (
            <section data-testid="shop-usual-card"
              className="bg-gradient-to-r from-orange-50 to-amber-50 border border-orange-200 rounded-2xl p-4">
              <div className="flex items-center justify-between">
                <div className="font-black text-slate-900 flex items-center gap-1.5">
                  <RotateCcw size={17} className="text-orange-600" />Get your usual
                </div>
                <button onClick={() => setUsualDismissed(true)} data-testid="shop-usual-dismiss"
                  className="text-slate-400 text-xs font-black">Dismiss</button>
              </div>
              <div className="text-xs text-slate-500 font-bold mt-0.5">from {usual.business_name}</div>
              <div className="flex gap-2 overflow-x-auto pb-1 mt-2.5 -mx-1 px-1">
                {(usual.items || []).map((u) => (
                  <Link key={u.item_id} to={`/shop/${usual.business_id}`} data-testid={`shop-usual-item-${u.item_id}`}
                    className="shrink-0 w-28 rounded-xl overflow-hidden bg-white border border-orange-200">
                    <div className="relative h-20 bg-slate-100">
                      {u.image_url && <img src={u.image_url} alt={u.name} className="w-full h-full object-cover" />}
                      <span className="absolute top-1 right-1 text-[10px] font-black text-white bg-orange-600 px-1.5 py-0.5 rounded-full">×{u.times_ordered}</span>
                    </div>
                    <div className="p-2">
                      <div className="text-[11px] font-bold text-slate-900 line-clamp-1">{u.name}</div>
                      <div className="text-[11px] font-black text-slate-900">{money(u.price_cents)}</div>
                    </div>
                  </Link>
                ))}
              </div>
              <button onClick={addUsual} data-testid="shop-usual-add-all"
                className="mt-2 w-full bg-orange-600 text-white font-black rounded-full py-2.5 text-sm hover:bg-orange-700 transition-colors">
                Add my usual ({(usual.items || []).length}) &amp; checkout
              </button>
            </section>
          )}
          {specials.length > 0 && (
            <section data-testid="shop-specials-row">
              <h2 className="text-lg font-black text-slate-900 mb-2 flex items-center gap-1.5">🔥 Today&apos;s Specials</h2>
              <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1">
                {specials.map((sp) => (
                  <Link key={sp.special_id} to={`/shop/${sp.business_id}`} data-testid={`shop-special-${sp.special_id}`}
                    className="shrink-0 w-44 rounded-2xl overflow-hidden bg-white border border-orange-200 hover:shadow-lg transition-shadow">
                    <div className="relative h-24 bg-slate-100">
                      {sp.image_url && <img src={sp.image_url} alt={sp.name} className="w-full h-full object-cover" />}
                      <span className="absolute top-2 left-2 text-[10px] font-black text-white bg-orange-600 px-2 py-0.5 rounded-full">SPECIAL</span>
                    </div>
                    <div className="p-3">
                      <div className="font-black text-slate-900 text-sm truncate">{sp.name}</div>
                      <div className="text-[11px] text-slate-500 truncate">{sp.business_name}</div>
                      {sp.blurb && <div className="text-[11px] text-orange-600 font-bold truncate mt-0.5">{sp.blurb}</div>}
                      <div className="mt-1 flex items-baseline gap-1.5">
                        {sp.sale_price_cents != null ? (
                          <>
                            <span className="font-black text-slate-900 text-sm">${(sp.sale_price_cents / 100).toFixed(2)}</span>
                            <span className="text-[11px] text-slate-400 line-through">${(sp.price_cents / 100).toFixed(2)}</span>
                          </>
                        ) : <span className="font-black text-slate-900 text-sm">${(sp.price_cents / 100).toFixed(2)}</span>}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}
          {sections.map((sec) => (
            <section key={sec.key} data-testid={`shop-section-${sec.key}`}>
              <h2 className="text-lg font-black text-slate-900 mb-0.5">{sec.title}</h2>
              {sec.subtitle
                ? <p className="text-xs font-semibold text-orange-600 mb-2" data-testid={`shop-section-sub-${sec.key}`}>{sec.subtitle}</p>
                : <div className="mb-1.5" />}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {sec.items.slice(0, 6).map((b) => <BizCard key={b.business_id + sec.key} b={b} />)}
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
