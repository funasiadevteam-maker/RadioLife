// Tube (YouTube-style) browse skin: left sidebar + top chips + an endless,
// mixed-size feed (video grid with sprinkled Shop cards, Shorts shelf,
// Play & Win playables shelf with Play buttons, Shop shelf, featured promo).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Search, Play, Sparkles, Home, Film, ShoppingBag, Gamepad2, Flame,
  User, History, ListVideo, ThumbsUp, ChevronRight, Loader2,
  ShoppingCart, X, Plus, Minus, Trash2, ChevronUp,
} from "lucide-react";
import { Art } from "./browseShared";
import LayoutSwitcher from "./LayoutSwitcher";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
import { useShopCart } from "../useShopCart";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

// Legacy-style shopping subfilters shown when the "Shopping" tab is active.
// Legacy Discover quick set first, then the remaining canonical business
// categories. "Restaurant" is relabeled to "Eat".
const SHOP_SUBCATS = [
  { id: "all", label: "All" },
  { id: "restaurant", label: "Eat" },
  { id: "cafe", label: "Cafe" },
  { id: "fast_food", label: "Fast Food" },
  { id: "bar", label: "Bar" },
  { id: "salon", label: "Salon" },
  { id: "retail", label: "Retail" },
  { id: "grocery", label: "Grocery" },
  { id: "medical_dental", label: "Medical & Dental" },
  { id: "fitness", label: "Fitness" },
  { id: "entertainment", label: "Entertainment" },
  { id: "movie_theater", label: "Movie Theater" },
  { id: "event_promoter", label: "Event Promoter" },
  { id: "concert_promoter", label: "Concert Promoter" },
  { id: "club_lounge", label: "Club & Lounge" },
  { id: "radio_station", label: "Radio Station" },
  { id: "podcast_creator", label: "Podcast Creator" },
  { id: "service_business", label: "Service Business" },
  { id: "other", label: "Other" },
];

// ── cards ────────────────────────────────────────────────────────────
function VideoCard({ item, onOpen }) {
  const isGame = item.type === "game";
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-tile" className="group text-left w-full">
      <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-slate-100">
        <Art item={item} rounded="rounded-xl" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
        {isGame && (
          <span data-testid="browse-game-play"
            className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
            <span className="inline-flex items-center gap-1.5 bg-white/95 text-[#0f0f0f] font-black text-sm px-4 py-2 rounded-full shadow-lg">
              <Play size={14} fill="currentColor" /> Play
            </span>
          </span>
        )}
        {item.badge && (
          <span className="absolute bottom-2 right-2 text-[10px] font-black px-1.5 py-0.5 rounded bg-black/80 text-white">{item.badge}</span>
        )}
      </div>
      <div className="flex gap-3 mt-2.5">
        <span className="shrink-0 h-9 w-9 rounded-full flex items-center justify-center text-white font-black text-sm"
          style={{ background: "linear-gradient(135deg,#FF0000,#c4302b)" }}>{(item.subtitle || item.title || "?").slice(0, 1)}</span>
        <div className="min-w-0">
          <div className="font-bold text-[15px] leading-snug text-[#0f0f0f] line-clamp-2">{item.title}</div>
          <div className="text-[13px] text-slate-500 line-clamp-1 mt-0.5">{item.subtitle}</div>
        </div>
      </div>
    </button>
  );
}

function ShopGridCard({ item, onOpen, onAdd }) {
  return (
    <div data-testid="browse-shop-tile" className="group text-left w-full">
      <button onClick={() => onOpen(item)} className="block w-full text-left">
        <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-slate-100 ring-1 ring-orange-100">
          <Art item={item} rounded="rounded-xl" />
          <span className="absolute top-2 left-2 inline-flex items-center gap-1 text-[10px] font-black px-2 py-0.5 rounded-full bg-orange-500 text-white">
            <ShoppingBag size={11} /> SHOP
          </span>
          {item.price && (
            <span className="absolute bottom-2 left-2 text-xs font-black px-2 py-1 rounded-lg bg-white/95 text-[#0f0f0f] shadow">{item.price}</span>
          )}
        </div>
      </button>
      <div className="mt-2.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-bold text-[15px] leading-snug text-[#0f0f0f] line-clamp-2">{item.title}</div>
          <div className="text-[13px] text-orange-600 font-semibold line-clamp-1 mt-0.5">{item.subtitle}</div>
        </div>
        {item.buyable && (
          <button onClick={() => onAdd(item)} data-testid="browse-add-to-cart" title="Add to cart"
            className="shrink-0 mt-0.5 inline-flex items-center gap-1 bg-orange-500 hover:bg-orange-600 text-white font-black text-xs rounded-full px-3 py-1.5">
            <Plus size={13} /> Add
          </button>
        )}
      </div>
    </div>
  );
}

function ShelfHeader({ icon: Icon, title, color }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {Icon && <Icon size={22} style={{ color }} className={!color ? "text-[#0f0f0f]" : ""} />}
      <h2 className="text-lg font-black text-[#0f0f0f]">{title}</h2>
    </div>
  );
}

function ShortsShelf({ title, items, onOpenShorts }) {
  return (
    <section className="py-4" data-testid="browse-shelf-shorts">
      <ShelfHeader icon={Flame} title={title} color="#FF0000" />
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
        {items.map((it, i) => (
          <button key={(it.id || "") + i} onClick={() => onOpenShorts(items, i)} data-testid="browse-short-card" className="shrink-0 w-[150px] group text-left">
            <div className="relative w-full rounded-xl overflow-hidden bg-slate-100" style={{ aspectRatio: "9/16" }}>
              <Art item={it} rounded="rounded-xl" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
              <span className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <Play size={30} className="text-white drop-shadow" fill="currentColor" />
              </span>
            </div>
            <div className="font-bold text-[13px] leading-snug text-[#0f0f0f] line-clamp-2 mt-1.5">{it.title}</div>
          </button>
        ))}
      </div>
    </section>
  );
}

// Full-screen vertical, swipeable Shorts player (scroll-snap = flick up/down).
function ShortsPlayer({ items, index, onClose, onOpen }) {
  const scrollerRef = useRef(null);
  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTo({ top: index * el.clientHeight });
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="fixed inset-0 z-[120] bg-black" data-testid="browse-shorts-player">
      <button onClick={onClose} data-testid="browse-shorts-close"
        className="absolute top-4 right-4 z-10 h-10 w-10 rounded-full bg-white/15 hover:bg-white/25 text-white flex items-center justify-center">
        <X size={22} />
      </button>
      <div ref={scrollerRef} className="h-full overflow-y-auto snap-y snap-mandatory no-scrollbar">
        {items.map((it, i) => (
          <div key={(it.id || "") + i} className="h-full w-full snap-start flex items-center justify-center relative" data-testid="browse-short-slide">
            <div className="relative h-full w-full max-w-[440px] mx-auto">
              <Art item={it} rounded="rounded-none" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/20" />
              <div className="absolute left-4 right-16 bottom-8 text-white">
                <div className="flex items-center gap-2 mb-2">
                  <span className="h-9 w-9 rounded-full flex items-center justify-center bg-white/20 font-black">{(it.subtitle || it.title || "?").slice(0, 1)}</span>
                  <span className="font-bold text-sm">{it.subtitle}</span>
                </div>
                <div className="font-black text-lg leading-snug line-clamp-3">{it.title}</div>
                <button onClick={() => onOpen(it)} data-testid="browse-short-play"
                  className="mt-3 inline-flex items-center gap-1.5 bg-white text-black font-black rounded-full px-5 py-2 text-sm">
                  <Play size={14} fill="currentColor" /> Play
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// In-feed shopping cart drawer (reuses the shared single-merchant cart).
function CartDrawer({ open, onClose, onCheckout, checkingOut }) {
  const items = useShopCart((s) => s.items);
  const businessName = useShopCart((s) => s.businessName);
  const inc = useShopCart((s) => s.inc);
  const dec = useShopCart((s) => s.dec);
  const clear = useShopCart((s) => s.clear);
  const subtotal = items.reduce((n, i) => n + i.price_cents * i.qty, 0);
  if (!open) return null;
  return (
    <>
      <div className="fixed inset-0 z-[95] bg-black/40" onClick={onClose} />
      <aside data-testid="browse-cart-drawer" className="fixed right-0 top-0 z-[100] h-full w-full max-w-sm bg-white shadow-2xl flex flex-col">
        <div className="flex items-center justify-between px-4 h-14 border-b border-slate-100">
          <div className="font-black text-[#0f0f0f] flex items-center gap-2"><ShoppingCart size={18} /> Your cart</div>
          <button onClick={onClose} data-testid="browse-cart-close" className="h-9 w-9 rounded-full hover:bg-slate-100 flex items-center justify-center"><X size={18} /></button>
        </div>
        {items.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-2">
            <ShoppingCart size={32} /> <span className="text-sm">Your cart is empty</span>
          </div>
        ) : (
          <>
            <div className="px-4 py-2 text-xs font-bold text-slate-400">{businessName}</div>
            <div className="flex-1 overflow-y-auto px-4 divide-y divide-slate-100">
              {items.map((i) => (
                <div key={i.line_id} className="flex items-center gap-3 py-3" data-testid="browse-cart-item">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-sm text-[#0f0f0f] line-clamp-1">{i.name}</div>
                    <div className="text-xs text-slate-500">{money(i.price_cents)}</div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => dec(i.line_id)} className="h-7 w-7 rounded-full bg-slate-100 flex items-center justify-center"><Minus size={13} /></button>
                    <span className="w-6 text-center font-black text-sm">{i.qty}</span>
                    <button onClick={() => inc(i.line_id)} data-testid="browse-cart-inc" className="h-7 w-7 rounded-full bg-slate-100 flex items-center justify-center"><Plus size={13} /></button>
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-slate-100 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-slate-500 font-bold text-sm">Subtotal</span>
                <span className="font-black text-lg text-[#0f0f0f]" data-testid="browse-cart-subtotal">{money(subtotal)}</span>
              </div>
              <button onClick={onCheckout} disabled={checkingOut} data-testid="browse-cart-checkout"
                className="w-full inline-flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">
                {checkingOut ? <Loader2 className="w-5 h-5 animate-spin" /> : <ShoppingBag size={18} />} Checkout
              </button>
              <button onClick={clear} className="w-full text-center text-xs font-bold text-slate-400 mt-2 flex items-center justify-center gap-1"><Trash2 size={12} /> Clear cart</button>
            </div>
          </>
        )}
      </aside>
    </>
  );
}

function PlayablesShelf({ title, items, onOpen }) {
  return (
    <section className="py-4" data-testid="browse-shelf-playables">
      <ShelfHeader icon={Gamepad2} title={title} color="#7c3aed" />
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
        {items.map((it, i) => (
          <div key={(it.id || "") + i} className="shrink-0 w-[190px]">
            <div className="relative w-full aspect-square rounded-2xl overflow-hidden bg-slate-100">
              <Art item={it} rounded="rounded-2xl" />
            </div>
            <button onClick={() => onOpen(it)} data-testid="browse-game-play"
              className="mt-2 w-full inline-flex items-center justify-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-[#0f0f0f] font-black text-sm rounded-full py-2 transition-colors">
              <Play size={14} fill="currentColor" /> Play
            </button>
            <div className="font-bold text-sm text-[#0f0f0f] line-clamp-1 mt-1.5">{it.title}</div>
            <div className="text-[12px] text-slate-500 line-clamp-1">{it.subtitle}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ShopShelf({ title, items, onOpen, onAdd }) {
  return (
    <section className="py-4" data-testid="browse-shelf-shop">
      <ShelfHeader icon={ShoppingBag} title={title} color="#f97316" />
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
        {items.map((it, i) => (
          <div key={(it.id || "") + i} className="shrink-0 w-[190px]">
            <button onClick={() => onOpen(it)} className="block w-full text-left">
              <div className="relative w-full aspect-square rounded-2xl overflow-hidden bg-slate-100 ring-1 ring-orange-100">
                <Art item={it} rounded="rounded-2xl" />
                {it.price && <span className="absolute bottom-2 left-2 text-xs font-black px-2 py-1 rounded-lg bg-white/95 text-[#0f0f0f] shadow">{it.price}</span>}
              </div>
              <div className="font-bold text-sm text-[#0f0f0f] line-clamp-2 mt-1.5">{it.title}</div>
              <div className="text-[12px] text-orange-600 font-semibold line-clamp-1">{it.subtitle}</div>
            </button>
            {it.buyable && (
              <button onClick={() => onAdd(it)} data-testid="browse-add-to-cart"
                className="mt-1.5 w-full inline-flex items-center justify-center gap-1 bg-orange-500 hover:bg-orange-600 text-white font-black text-xs rounded-full py-1.5">
                <Plus size={13} /> Add to cart
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function FeaturedBlock({ item, cta, onOpen, onAdd }) {
  const shop = item.type === "shop";
  return (
    <section className="py-5" data-testid="browse-featured">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
        <button onClick={() => onOpen(item)} className="relative w-full aspect-video rounded-2xl overflow-hidden bg-slate-100 text-left">
          <Art item={item} rounded="rounded-2xl" />
          {item.price && <span className="absolute bottom-3 left-3 text-sm font-black px-2.5 py-1 rounded-lg bg-white/95 text-[#0f0f0f] shadow">{item.price}</span>}
        </button>
        <div>
          <span className={`inline-flex items-center gap-1 text-[11px] font-black px-2 py-0.5 rounded-full ${shop ? "bg-orange-100 text-orange-700" : "bg-slate-100 text-slate-700"}`}>
            {shop ? <ShoppingBag size={11} /> : <Sparkles size={11} />} {shop ? "Featured shop" : "Featured"}
          </span>
          <h2 className="text-2xl lg:text-3xl font-black text-[#0f0f0f] mt-2 leading-tight">{item.title}</h2>
          <p className="text-slate-500 mt-1">{item.subtitle}</p>
          <div className="flex items-center gap-2 mt-4">
            <button onClick={() => onOpen(item)}
              className="inline-flex items-center gap-1.5 bg-[#0f0f0f] text-white font-black rounded-full px-5 py-2.5 text-sm">
              {cta} <ChevronRight size={16} />
            </button>
            {shop && item.buyable && (
              <button onClick={() => onAdd(item)} data-testid="browse-add-to-cart"
                className="inline-flex items-center gap-1.5 bg-orange-500 hover:bg-orange-600 text-white font-black rounded-full px-5 py-2.5 text-sm">
                <Plus size={15} /> Add to cart
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

// ── sidebar ───────────────────────────────────────────────────────────
const YOU_LINKS = [
  [User, "Your channel", "/profile"], [History, "History", "/history"],
  [ListVideo, "Playlists", "/playlists"], [ThumbsUp, "Liked", "/liked"],
];

function SideItem({ icon: Icon, label, active, onClick }) {
  return (
    <button onClick={onClick} data-testid={`browse-side-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
      className={`w-full flex items-center gap-5 px-3 py-2.5 rounded-xl text-sm font-semibold text-left ${active ? "bg-slate-100 font-black" : "hover:bg-slate-100"}`}>
      <Icon size={20} /> <span className="truncate">{label}</span>
    </button>
  );
}

function Sidebar({ cat, setCat, subs }) {
  const main = [
    [Home, "Home", "all"], [Film, "Shorts", "all"],
    [ShoppingBag, "Shopping", "shopping"], [Gamepad2, "Play & Win", "games"],
  ];
  return (
    <aside data-testid="browse-sidebar"
      className="hidden lg:block fixed left-0 top-14 w-60 h-[calc(100vh-56px)] overflow-y-auto no-scrollbar px-3 py-3 border-r border-slate-100 bg-white">
      {main.map(([Icon, label, key]) => (
        <SideItem key={label} icon={Icon} label={label} active={cat === key && (label !== "Shorts" || cat === "all")}
          onClick={() => setCat(key)} />
      ))}
      <div className="border-t border-slate-100 my-3" />
      <div className="px-3 text-[11px] font-black text-slate-400 uppercase tracking-wide mb-1">Subscriptions</div>
      {(subs || []).slice(0, 7).map((s, i) => (
        <button key={(s.id || "") + i} onClick={() => setCat("all")}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm hover:bg-slate-100 text-left">
          <span className="shrink-0 h-6 w-6 rounded-full overflow-hidden bg-slate-200">
            <Art item={s} rounded="rounded-full" />
          </span>
          <span className="truncate text-slate-700">{s.subtitle || s.title}</span>
        </button>
      ))}
      <div className="border-t border-slate-100 my-3" />
      <div className="px-3 text-[11px] font-black text-slate-400 uppercase tracking-wide mb-1">You</div>
      {YOU_LINKS.map(([Icon, label, to]) => (
        <Link key={label} to={to} className="w-full flex items-center gap-5 px-3 py-2.5 rounded-xl text-sm font-semibold hover:bg-slate-100">
          <Icon size={20} /> {label}
        </Link>
      ))}
    </aside>
  );
}

// ── grid renderer ─────────────────────────────────────────────────────
function Grid({ items, onOpen, q, onAdd }) {
  const list = q ? items.filter((i) => (i.title || "").toLowerCase().includes(q.toLowerCase())) : items;
  if (!list.length) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-7 py-2">
      {list.map((it, i) => it.type === "shop"
        ? <ShopGridCard key={(it.id || "") + it.title + i} item={it} onOpen={onOpen} onAdd={onAdd} />
        : <VideoCard key={(it.id || "") + it.title + i} item={it} onOpen={onOpen} />)}
    </div>
  );
}

// ── main ──────────────────────────────────────────────────────────────
export default function TubeBrowse({ onOpen }) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [chips, setChips] = useState([{ key: "all", title: "All" }, { key: "shopping", title: "Shopping" }]);
  const [subs, setSubs] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const loadingRef = useRef(false);
  const sentinelRef = useRef(null);
  const stateRef = useRef({ page: 0, hasMore: true, cat: "all" });
  useEffect(() => { stateRef.current = { page, hasMore, cat }; }, [page, hasMore, cat]);

  const fetchPage = useCallback(async (p, category, replace) => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    if (replace) setLoading(true);
    try {
      const r = await axios.get(`${API}/browse/feed`, { params: { page: p, cat: category } });
      if (p === 0 && r.data.chips) setChips(r.data.chips);
      if (p === 0 && r.data.subs) setSubs(r.data.subs);
      setBlocks((prev) => (replace ? r.data.blocks : [...prev, ...r.data.blocks]));
      setHasMore(!!r.data.has_more);
      setPage(p);
    } catch (_e) {
      setHasMore(false);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, []);

  const loadMore = useCallback(() => {
    const st = stateRef.current;
    if (st.hasMore && !loadingRef.current) fetchPage(st.page + 1, st.cat, false);
  }, [fetchPage]);

  useEffect(() => { fetchPage(0, cat, true); }, [cat, fetchPage]);

  // Scroll-driven endless load (stable listener; reads latest state via ref).
  useEffect(() => {
    const onScroll = () => {
      const doc = document.documentElement;
      if (doc.scrollHeight - (window.scrollY + window.innerHeight) < 900) loadMore();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, [loadMore]);

  // Keep loading until the feed fills the viewport (so the user can scroll).
  useEffect(() => {
    if (!loading && stateRef.current.hasMore
        && document.documentElement.scrollHeight <= window.innerHeight + 300) {
      loadMore();
    }
  }, [blocks, loading, loadMore]);

  const [shopSub, setShopSub] = useState("all");
  const chooseCat = (k) => {
    if (k !== "shopping") setShopSub("all");
    if (k !== cat) { setBlocks([]); setPage(0); setCat(k); }
  };

  // Shop cart + Shorts player state
  const cartCount = useShopCart((s) => s.items.reduce((n, i) => n + i.qty, 0));
  const [cartOpen, setCartOpen] = useState(false);
  const [checkingOut, setCheckingOut] = useState(false);
  const [shorts, setShorts] = useState(null); // {items, index}

  const addToCart = (it) => {
    if (!it.business_id || !it.price_cents) { toast.error("This item isn't purchasable yet"); return; }
    const cur = useShopCart.getState();
    if (cur.businessId && cur.businessId !== it.business_id && cur.items.length) {
      toast(`Started a new cart for ${it.business_name}`);
    }
    useShopCart.getState().add(it.business_id, it.business_name,
      { item_id: it.id, name: it.title, price_cents: it.price_cents });
    toast.success("Added to cart");
    setCartOpen(true);
  };

  const checkout = async () => {
    const st = useShopCart.getState();
    if (!st.items.length) return;
    setCheckingOut(true);
    try {
      const r = await axios.post(`${API}/shop/product-orders/checkout`, {
        business_id: st.businessId,
        items: st.items.map((i) => ({ product_id: i.item_id, qty: i.qty })),
        fulfillment: "pickup",
        origin_url: window.location.origin,
      });
      if (r.data.checkout_url) {
        window.open(r.data.checkout_url, "_blank", "noopener");
        toast.success("Opening secure checkout…");
      } else if (r.data.status === "paid" || r.data.order_id) {
        toast.success("Order placed!");
        st.clear();
        setCartOpen(false);
      } else {
        toast.success("Order created");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || e?.response?.data?.detail || "Checkout failed");
    } finally {
      setCheckingOut(false);
    }
  };

  const openShorts = (items, index) => setShorts({ items, index });

  const renderBlock = (b, i) => {
    if (b.kind === "grid") return <Grid key={`g${i}`} items={b.items || []} onOpen={onOpen} q={q} onAdd={addToCart} />;
    if (b.kind === "featured") return <FeaturedBlock key={`f${i}`} item={b.item} cta={b.cta} onOpen={onOpen} onAdd={addToCart} />;
    if (b.kind === "shelf") {
      if (b.variant === "shorts") return <ShortsShelf key={`s${i}`} title={b.title} items={b.items || []} onOpenShorts={openShorts} />;
      if (b.variant === "playables") return <PlayablesShelf key={`s${i}`} title={b.title} items={b.items || []} onOpen={onOpen} />;
      if (b.variant === "shop") return <ShopShelf key={`s${i}`} title={b.title} items={b.items || []} onOpen={onOpen} onAdd={addToCart} />;
    }
    return null;
  };

  const chipRow = useMemo(() => chips, [chips]);

  return (
    <div className="min-h-screen bg-white text-[#0f0f0f]" data-testid="browse-tube" style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      {/* Top bar */}
      <header className="sticky top-0 z-40 flex items-center gap-4 px-4 lg:px-6 h-14 bg-white border-b border-slate-100">
        <Link to="/" className="flex items-center gap-1.5 text-xl font-black tracking-tight">
          <span className="h-6 w-9 rounded-md flex items-center justify-center" style={{ background: "#FF0000" }}>
            <Play size={13} className="text-white ml-0.5" fill="currentColor" />
          </span>
          RadioLife
        </Link>
        <div className="hidden md:flex items-center flex-1 max-w-xl mx-auto">
          <div className="flex items-center flex-1 bg-slate-50 border border-slate-200 rounded-l-full px-4 py-2">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" data-testid="browse-search"
              className="bg-transparent text-sm outline-none w-full" />
          </div>
          <button className="px-5 py-2 bg-slate-100 border border-l-0 border-slate-200 rounded-r-full"><Search size={18} className="text-slate-600" /></button>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setCartOpen(true)} data-testid="browse-cart-btn"
            className="relative h-10 w-10 rounded-full hover:bg-slate-100 flex items-center justify-center">
            <ShoppingCart size={20} className="text-[#0f0f0f]" />
            {cartCount > 0 && (
              <span data-testid="browse-cart-count" className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-orange-500 text-white text-[10px] font-black flex items-center justify-center">{cartCount}</span>
            )}
          </button>
          <LayoutSwitcher tone="light" />
          <button onClick={() => setVariant("legacy")} data-testid="browse-exit-legacy"
            className="hidden lg:inline-flex items-center gap-1 text-[11px] font-bold text-slate-500 hover:text-slate-800">
            <Sparkles size={12} /> Legacy
          </button>
        </div>
      </header>

      <Sidebar cat={cat} setCat={chooseCat} subs={subs} />

      <main className="lg:ml-60">
        {/* Category chips */}
        <div className="sticky top-14 z-30 bg-white/95 backdrop-blur flex gap-2 overflow-x-auto no-scrollbar px-4 lg:px-6 py-3 border-b border-slate-100" data-testid="browse-chips">
          {chipRow.map((c) => (
            <button key={c.key} onClick={() => chooseCat(c.key)} data-testid={`browse-chip-${c.key}`}
              className={`shrink-0 px-3.5 py-1.5 rounded-lg text-sm font-bold transition-colors ${cat === c.key ? "bg-[#0f0f0f] text-white" : c.key === "shopping" ? "bg-orange-50 text-orange-700 hover:bg-orange-100" : "bg-slate-100 text-slate-800 hover:bg-slate-200"}`}>
              {c.key === "shopping" ? "🛍 Shopping" : c.title}
            </button>
          ))}
        </div>

        {/* Shopping subfilters (legacy-style categories) */}
        {cat === "shopping" && (
          <div data-testid="browse-shop-subchips"
            className="sticky top-[6.75rem] z-20 bg-white/95 backdrop-blur flex gap-2 overflow-x-auto no-scrollbar px-4 lg:px-6 py-2.5 border-b border-slate-100">
            {SHOP_SUBCATS.map((s) => (
              <button key={s.id} onClick={() => setShopSub(s.id)} data-testid={`browse-shop-subchip-${s.id}`}
                className={`shrink-0 px-3.5 py-1.5 rounded-full text-sm font-bold border transition-colors ${shopSub === s.id ? "bg-orange-500 text-white border-orange-500" : "bg-white text-slate-700 border-slate-200 hover:bg-orange-50 hover:border-orange-200"}`}>
                {s.label}
              </button>
            ))}
          </div>
        )}

        {/* Feed */}
        <div className="px-4 lg:px-6 py-4">
          {loading && blocks.length === 0 && <div className="py-24 text-center text-slate-400"><Loader2 className="w-6 h-6 animate-spin inline" /></div>}
          {!loading && blocks.length === 0 && <div className="py-24 text-center text-slate-400">Nothing here yet.</div>}
          {blocks.map(renderBlock)}
          <div ref={sentinelRef} data-testid="browse-feed-sentinel" className="h-10" />
          {hasMore && blocks.length > 0 && (
            <div className="py-6 text-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin inline" /></div>
          )}
        </div>
      </main>

      <CartDrawer open={cartOpen} onClose={() => setCartOpen(false)} onCheckout={checkout} checkingOut={checkingOut} />
      {shorts && <ShortsPlayer items={shorts.items} index={shorts.index} onClose={() => setShorts(null)} onOpen={onOpen} />}
    </div>
  );
}
