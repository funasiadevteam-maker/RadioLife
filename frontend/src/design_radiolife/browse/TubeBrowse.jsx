// Tube (YouTube-style) browse skin: left sidebar + top chips + an endless,
// mixed-size feed (video grid with sprinkled Shop cards, Shorts shelf,
// Play & Win playables shelf with Play buttons, Shop shelf, featured promo).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Search, Play, Sparkles, Home, Film, ShoppingBag, Gamepad2, Flame,
  User, History, ListVideo, ThumbsUp, ChevronRight, Loader2,
} from "lucide-react";
import { Art } from "./browseShared";
import LayoutSwitcher from "./LayoutSwitcher";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

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

function ShopGridCard({ item, onOpen }) {
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-shop-tile" className="group text-left w-full">
      <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-slate-100 ring-1 ring-orange-100">
        <Art item={item} rounded="rounded-xl" />
        <span className="absolute top-2 left-2 inline-flex items-center gap-1 text-[10px] font-black px-2 py-0.5 rounded-full bg-orange-500 text-white">
          <ShoppingBag size={11} /> SHOP
        </span>
        {item.price && (
          <span className="absolute bottom-2 left-2 text-xs font-black px-2 py-1 rounded-lg bg-white/95 text-[#0f0f0f] shadow">{item.price}</span>
        )}
      </div>
      <div className="mt-2.5">
        <div className="font-bold text-[15px] leading-snug text-[#0f0f0f] line-clamp-2">{item.title}</div>
        <div className="text-[13px] text-orange-600 font-semibold line-clamp-1 mt-0.5">{item.subtitle} · Shop now</div>
      </div>
    </button>
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

function ShortsShelf({ title, items, onOpen }) {
  return (
    <section className="py-4" data-testid="browse-shelf-shorts">
      <ShelfHeader icon={Flame} title={title} color="#FF0000" />
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
        {items.map((it, i) => (
          <button key={(it.id || "") + i} onClick={() => onOpen(it)} className="shrink-0 w-[150px] group text-left">
            <div className="relative w-full rounded-xl overflow-hidden bg-slate-100" style={{ aspectRatio: "9/16" }}>
              <Art item={it} rounded="rounded-xl" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent" />
            </div>
            <div className="font-bold text-[13px] leading-snug text-[#0f0f0f] line-clamp-2 mt-1.5">{it.title}</div>
          </button>
        ))}
      </div>
    </section>
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

function ShopShelf({ title, items, onOpen }) {
  return (
    <section className="py-4" data-testid="browse-shelf-shop">
      <ShelfHeader icon={ShoppingBag} title={title} color="#f97316" />
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
        {items.map((it, i) => (
          <button key={(it.id || "") + i} onClick={() => onOpen(it)} className="shrink-0 w-[190px] text-left">
            <div className="relative w-full aspect-square rounded-2xl overflow-hidden bg-slate-100 ring-1 ring-orange-100">
              <Art item={it} rounded="rounded-2xl" />
              {it.price && <span className="absolute bottom-2 left-2 text-xs font-black px-2 py-1 rounded-lg bg-white/95 text-[#0f0f0f] shadow">{it.price}</span>}
            </div>
            <div className="font-bold text-sm text-[#0f0f0f] line-clamp-2 mt-1.5">{it.title}</div>
            <div className="text-[12px] text-orange-600 font-semibold line-clamp-1">{it.subtitle}</div>
          </button>
        ))}
      </div>
    </section>
  );
}

function FeaturedBlock({ item, cta, onOpen }) {
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
          <button onClick={() => onOpen(item)}
            className="mt-4 inline-flex items-center gap-1.5 bg-[#0f0f0f] text-white font-black rounded-full px-5 py-2.5 text-sm">
            {cta} <ChevronRight size={16} />
          </button>
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
function Grid({ items, onOpen, q }) {
  const list = q ? items.filter((i) => (i.title || "").toLowerCase().includes(q.toLowerCase())) : items;
  if (!list.length) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-7 py-2">
      {list.map((it, i) => it.type === "shop"
        ? <ShopGridCard key={(it.id || "") + it.title + i} item={it} onOpen={onOpen} />
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

  const chooseCat = (k) => { if (k !== cat) { setBlocks([]); setPage(0); setCat(k); } };

  const renderBlock = (b, i) => {
    if (b.kind === "grid") return <Grid key={`g${i}`} items={b.items || []} onOpen={onOpen} q={q} />;
    if (b.kind === "featured") return <FeaturedBlock key={`f${i}`} item={b.item} cta={b.cta} onOpen={onOpen} />;
    if (b.kind === "shelf") {
      if (b.variant === "shorts") return <ShortsShelf key={`s${i}`} title={b.title} items={b.items || []} onOpen={onOpen} />;
      if (b.variant === "playables") return <PlayablesShelf key={`s${i}`} title={b.title} items={b.items || []} onOpen={onOpen} />;
      if (b.variant === "shop") return <ShopShelf key={`s${i}`} title={b.title} items={b.items || []} onOpen={onOpen} />;
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
    </div>
  );
}
