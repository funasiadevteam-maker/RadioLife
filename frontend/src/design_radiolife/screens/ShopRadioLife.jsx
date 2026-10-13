// FUUSIC Shop — web consumer marketplace (Super Marketplace).
// Fully migrated to the unified Light/Dark theme (semantic CSS tokens), brand
// purple→pink accents, 2-column product cards, BigPoints tags + a Live
// Shopping rail. See /app/design_guidelines.json + index.css tokens.
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Search, Star, Store, ArrowRight, Coins, ShoppingCart, Crown, CreditCard, QrCode, User, Receipt, LayoutDashboard, X, Calendar, Sparkles, Navigation, RotateCcw, Eye } from "lucide-react";
import { API } from "@/AuthContext";
import { useProductCart } from "../useProductCart";
import { useShopCart } from "../useShopCart";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

function Chip({ active, children, ...props }) {
  return (
    <button type="button"
      className={`shrink-0 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-bold capitalize transition-colors active:scale-95 ${active ? "fz-chip-active" : "fz-chip"}`}
      {...props}>{children}</button>
  );
}

function BizCard({ b }) {
  return (
    <Link to={`/shop/${b.business_id}`} data-testid={`shop-biz-${b.business_id}`}
      className="fz-card block rounded-2xl overflow-hidden transition-transform hover:-translate-y-1"
      style={{ boxShadow: "var(--card-shadow)" }}>
      <div className="relative aspect-square" style={{ background: "var(--surface-2)" }}>
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        {b.promoted ? <span className="absolute top-2 left-2 text-[10px] font-black text-white px-2 py-0.5 rounded-full" style={{ background: "var(--brand-solid)" }}>Promoted</span>
          : b.sponsored ? <span className="absolute top-2 left-2 text-[10px] font-bold text-white bg-black/60 px-2 py-0.5 rounded-full">Sponsored</span> : null}
        <span className="absolute bottom-2 right-2 flex items-center gap-1 text-[11px] font-black px-2 py-1 rounded-full" style={{ background: "var(--bigpoints-gold)", color: "#3a2a00" }}>
          <Coins size={11} /> Earn {b.default_bigpoints}
        </span>
      </div>
      <div className="p-3">
        <div className="fz-text font-black truncate">{b.public_name}</div>
        <div className="flex items-center justify-between mt-0.5">
          <span className="fz-muted text-xs capitalize truncate">{b.subcategory || b.category}</span>
          {b.rating ? <span className="flex items-center gap-1 text-xs font-bold fz-sub">
            <Star size={11} style={{ color: "var(--bigpoints-gold)", fill: "var(--bigpoints-gold)" }} />{b.rating.toFixed(1)}</span> : null}
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
  const [liveShows, setLiveShows] = useState([]);
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
    axios.get(`${API}/merchant/marketplace/profile`)
      .then((r) => setIsMerchant(!!r.data?.profile))
      .catch(() => setIsMerchant(false));
    axios.get(`${API}/shop/usual`)
      .then((r) => { if (r.data?.has_usual) setUsual(r.data); })
      .catch(() => setUsual(null));
    // Live Shopping — live shows first, then upcoming (scheduled) shows.
    Promise.all([
      axios.get(`${API}/social/liveshows`, { params: { status: "live" } }).catch(() => ({ data: { items: [] } })),
      axios.get(`${API}/social/liveshows`, { params: { status: "scheduled" } }).catch(() => ({ data: { items: [] } })),
    ]).then(([lv, up]) => {
      setLiveShows([...(lv.data.items || []), ...(up.data.items || [])].slice(0, 10));
    });
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

  if (loading) return <div className="px-4 pt-10 text-center fz-muted">Loading Shop…</div>;

  const LiveRail = () => liveShows.length === 0 ? null : (
    <section data-testid="shop-live-shopping">
      <h2 className="fz-text text-lg font-black mb-2 flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-black px-2 py-0.5 rounded-full text-white" style={{ background: "var(--live)" }}>
          <span className="live-dot inline-block w-1.5 h-1.5 rounded-full bg-white" /> LIVE
        </span>
        Live Shopping
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar">
        {liveShows.map((sh) => {
          const isLive = sh.status === "live";
          return (
            <button key={sh.show_id} type="button" onClick={() => navigate("/social?tab=live")}
              data-testid={`shop-live-${sh.show_id}`}
              className="fz-card shrink-0 w-44 text-left rounded-2xl overflow-hidden transition-transform hover:-translate-y-1">
              <div className="relative h-28" style={{ background: "var(--surface-2)" }}>
                {sh.cover_url && <img src={sh.cover_url} alt={sh.title} className="w-full h-full object-cover" />}
                <span className="absolute top-2 left-2 flex items-center gap-1 text-[10px] font-black text-white px-2 py-0.5 rounded-full"
                  style={{ background: isLive ? "var(--live)" : "var(--brand-solid)" }}>
                  {isLive ? <><span className="live-dot inline-block w-1.5 h-1.5 rounded-full bg-white" /> LIVE</> : "UPCOMING"}
                </span>
                {isLive && (
                  <span className="absolute bottom-2 right-2 flex items-center gap-1 text-[10px] font-bold text-white bg-black/55 px-2 py-0.5 rounded-full">
                    <Eye size={10} /> {sh.viewer_count || 0}
                  </span>
                )}
              </div>
              <div className="p-2.5">
                <div className="fz-text font-black text-sm truncate">{sh.title || "Live show"}</div>
                <div className="fz-muted text-[11px] truncate">{sh.business_name || sh.host?.display_name || "FUUSIC Live"}</div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );

  return (
    <div className="px-4 pt-6 pb-8 space-y-4 fz-text" data-testid="rl-shop-page">
      <header className="flex items-start justify-between gap-3 relative">
        <div>
          <div className="fz-brand text-[11px] font-black tracking-widest">FUUSIC SHOP</div>
          <h1 className="text-3xl font-black tracking-tight fz-text leading-tight mt-1">
            {home?.headline || "SHOP LOCAL. EARN BIGPOINTS."}</h1>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button type="button" onClick={() => setMenuOpen((o) => !o)} data-testid="shop-account-button"
            className="fz-card w-11 h-11 rounded-full flex items-center justify-center hover:shadow-md transition-shadow">
            <User size={20} className="fz-sub" />
          </button>
          <Link to="/shop/cart" data-testid="shop-cart-button"
            className="fz-card relative w-11 h-11 rounded-full flex items-center justify-center hover:shadow-md transition-shadow">
            <ShoppingCart size={20} className="fz-sub" />
            {cartCount > 0 && (
              <span data-testid="shop-cart-badge"
                className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1 rounded-full text-white text-[11px] font-black flex items-center justify-center" style={{ background: "var(--brand-solid)" }}>
                {cartCount}</span>
            )}
          </Link>
        </div>

        {menuOpen && (
          <>
            <div className="fixed inset-0 z-[90]" onClick={() => setMenuOpen(false)} />
            <div data-testid="shop-account-menu"
              className="fz-card fixed top-20 right-4 z-[100] w-60 rounded-2xl shadow-xl p-2">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-xs font-black fz-muted tracking-wide">MY ACCOUNT</span>
                <button onClick={() => setMenuOpen(false)} className="fz-muted hover:opacity-70"><X size={15} /></button>
              </div>
              {isMerchant && (
                <Link to="/shop/merchant" data-testid="shop-merchant-dash" onClick={() => setMenuOpen(false)}
                  className="fz-grad flex items-center gap-2.5 rounded-xl px-3 py-2.5 mb-1 font-black text-sm">
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
                  className="flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-bold fz-sub hover:bg-[var(--chip-bg)]">
                  <Icon size={16} className="fz-brand" /> {label}
                </Link>
              ))}
            </div>
          </>
        )}
      </header>

      <div className="fz-field flex items-center gap-2 rounded-full px-4 py-3">
        <Search size={18} className="fz-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="shop-search"
          placeholder="Search restaurants, products, services…" className="fz-field flex-1 outline-none text-sm border-0 bg-transparent p-0" style={{ background: "transparent" }} />
      </div>

      <Link to="/shop/near-me" data-testid="shop-near-me"
        className="fz-brand-soft flex items-center gap-2 rounded-full px-4 py-2.5 hover:opacity-90 transition-opacity">
        <Navigation size={16} className="fz-brand" />
        <span className="flex-1 text-sm font-bold fz-text">Explore shops &amp; services near you</span>
        <ArrowRight size={16} className="fz-muted" />
      </Link>

      <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar" data-testid="shop-categories">
        {cats.map((c) => (
          <Chip key={c.key} active={category === c.key} onClick={() => setCategory(c.key)}
            data-testid={`shop-cat-${c.key}`}>{c.name}</Chip>
        ))}
      </div>

      {browsing ? (
        <>
          <div className="flex items-center gap-2">
            {[["featured", "Featured"], ["bigpoints", "Most BigPoints"], ["rating", "Top Rated"]].map(([k, l]) => (
              <Chip key={k} active={sort === k} onClick={() => setSort(k)} data-testid={`shop-sort-${k}`}>{l}</Chip>
            ))}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {items.map((b) => <BizCard key={b.business_id} b={b} />)}
          </div>
          {items.length === 0 && <div className="text-center fz-muted py-8">No businesses found.</div>}
        </>
      ) : (
        <>
          {usual && !usualDismissed && (
            <section data-testid="shop-usual-card" className="fz-brand-soft rounded-2xl p-4">
              <div className="flex items-center justify-between">
                <div className="font-black fz-text flex items-center gap-1.5">
                  <RotateCcw size={17} className="fz-brand" />Get your usual
                </div>
                <button onClick={() => setUsualDismissed(true)} data-testid="shop-usual-dismiss"
                  className="fz-muted text-xs font-black">Dismiss</button>
              </div>
              <div className="text-xs fz-muted font-bold mt-0.5">from {usual.business_name}</div>
              <div className="flex gap-2 overflow-x-auto pb-1 mt-2.5 -mx-1 px-1 no-scrollbar">
                {(usual.items || []).map((u) => (
                  <Link key={u.item_id} to={`/shop/${usual.business_id}`} data-testid={`shop-usual-item-${u.item_id}`}
                    className="fz-card shrink-0 w-28 rounded-xl overflow-hidden">
                    <div className="relative h-20" style={{ background: "var(--surface-2)" }}>
                      {u.image_url && <img src={u.image_url} alt={u.name} className="w-full h-full object-cover" />}
                      <span className="absolute top-1 right-1 text-[10px] font-black text-white px-1.5 py-0.5 rounded-full" style={{ background: "var(--brand-solid)" }}>×{u.times_ordered}</span>
                    </div>
                    <div className="p-2">
                      <div className="text-[11px] font-bold fz-text line-clamp-1">{u.name}</div>
                      <div className="text-[11px] font-black fz-text">{money(u.price_cents)}</div>
                    </div>
                  </Link>
                ))}
              </div>
              <button onClick={addUsual} data-testid="shop-usual-add-all"
                className="fz-grad mt-2 w-full font-black rounded-full py-2.5 text-sm hover:opacity-95 transition-opacity">
                Add my usual ({(usual.items || []).length}) &amp; checkout
              </button>
            </section>
          )}

          <LiveRail />

          {specials.length > 0 && (
            <section data-testid="shop-specials-row">
              <h2 className="text-lg font-black fz-text mb-2 flex items-center gap-1.5">🔥 Today&apos;s Specials</h2>
              <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar">
                {specials.map((sp) => (
                  <Link key={sp.special_id} to={`/shop/${sp.business_id}`} data-testid={`shop-special-${sp.special_id}`}
                    className="fz-card shrink-0 w-44 rounded-2xl overflow-hidden transition-transform hover:-translate-y-1">
                    <div className="relative h-24" style={{ background: "var(--surface-2)" }}>
                      {sp.image_url && <img src={sp.image_url} alt={sp.name} className="w-full h-full object-cover" />}
                      <span className="absolute top-2 left-2 text-[10px] font-black text-white px-2 py-0.5 rounded-full" style={{ background: "var(--brand-solid)" }}>SPECIAL</span>
                    </div>
                    <div className="p-3">
                      <div className="font-black fz-text text-sm truncate">{sp.name}</div>
                      <div className="text-[11px] fz-muted truncate">{sp.business_name}</div>
                      {sp.blurb && <div className="text-[11px] fz-brand font-bold truncate mt-0.5">{sp.blurb}</div>}
                      <div className="mt-1 flex items-baseline gap-1.5">
                        {sp.sale_price_cents != null ? (
                          <>
                            <span className="font-black fz-text text-sm">{money(sp.sale_price_cents)}</span>
                            <span className="text-[11px] fz-muted line-through">{money(sp.price_cents)}</span>
                          </>
                        ) : <span className="font-black fz-text text-sm">{money(sp.price_cents)}</span>}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {sections.map((sec, idx) => (
            <section key={sec.key} data-testid={`shop-section-${sec.key}`}>
              <h2 className="text-lg font-black fz-text mb-0.5">{idx === 0 ? "Featured Near You" : sec.title}</h2>
              {sec.subtitle
                ? <p className="text-xs font-semibold fz-brand mb-2" data-testid={`shop-section-sub-${sec.key}`}>{sec.subtitle}</p>
                : <div className="mb-1.5" />}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {sec.items.slice(0, 6).map((b) => <BizCard key={b.business_id + sec.key} b={b} />)}
              </div>
            </section>
          ))}
        </>
      )}

      {/* Merchant / Sell CTA — moved to the bottom of the page. */}
      {isMerchant ? (
        <Link to="/shop/merchant" data-testid="shop-merchant-banner"
          className="fz-surface-2 flex items-center gap-3 rounded-2xl p-4 hover:opacity-90 transition-opacity border fz-border">
          <LayoutDashboard size={22} className="fz-text" />
          <div className="flex-1">
            <div className="font-black fz-text">Merchant Dashboard</div>
            <div className="text-xs fz-muted">Manage your menu, products, orders, memberships &amp; more.</div>
          </div>
          <ArrowRight size={22} className="fz-text" />
        </Link>
      ) : (
        <Link to="/sell" data-testid="shop-sell-cta"
          className="fz-grad flex items-center gap-3 rounded-2xl p-4 hover:opacity-95 transition-opacity">
          <Store size={22} />
          <div className="flex-1">
            <div className="font-black">Sell on FUUSIC</div>
            <div className="text-xs opacity-90">List your business &amp; reward local customers with BigPoints.</div>
          </div>
          <ArrowRight size={22} />
        </Link>
      )}

      {/* Order by chat — floating capsule pinned to the right. */}
      <Link to="/shop/concierge" data-testid="shop-concierge-fab" title="Order by chat"
        className="fz-grad fixed right-4 bottom-28 z-40 flex items-center gap-2 rounded-full pl-4 pr-5 py-3 shadow-xl hover:shadow-2xl hover:scale-105 transition-all">
        <Sparkles size={20} />
        <span className="font-black text-sm whitespace-nowrap">Order by chat ✨</span>
      </Link>
    </div>
  );
}
