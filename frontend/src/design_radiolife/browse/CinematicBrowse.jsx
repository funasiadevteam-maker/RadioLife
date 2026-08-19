// Cinematic (Netflix-style) browse skin: dark, hero banner + horizontal rails.
import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Play, Info, Search, ChevronRight, Sparkles } from "lucide-react";
import { Art, NAV } from "./browseShared";
import LayoutSwitcher from "./LayoutSwitcher";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

function Tile({ item, onOpen }) {
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-tile"
      className="group relative shrink-0 w-64 h-36 rounded-lg overflow-hidden bg-white/5 transition-transform duration-200 hover:scale-105 hover:z-10 focus:outline-none">
      <Art item={item} rounded="rounded-lg" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
      {item.badge && (
        <span className="absolute top-2 left-2 text-[9px] font-black tracking-wider px-1.5 py-0.5 rounded bg-[#E50914] text-white">{item.badge}</span>
      )}
      <div className="absolute bottom-0 left-0 right-0 p-2.5 text-left">
        <div className="text-white font-bold text-sm leading-tight line-clamp-1">{item.title}</div>
        <div className="text-white/60 text-[11px] line-clamp-1">{item.subtitle}</div>
      </div>
    </button>
  );
}

function Rail({ rail, onOpen }) {
  return (
    <section className="mb-8" data-testid={`browse-rail-${rail.key}`}>
      <h2 className="flex items-center gap-2 text-white font-black text-lg mb-3 px-6 lg:px-10">
        {rail.accent && <span className="inline-block w-1 h-5 rounded bg-[#E50914]" />}
        {rail.title}
        <ChevronRight size={18} className="text-white/40" />
      </h2>
      <div className="flex gap-3 overflow-x-auto no-scrollbar px-6 lg:px-10 pb-2">
        {rail.items.map((it) => <Tile key={(it.id || "") + it.title} item={it} onOpen={onOpen} />)}
      </div>
    </section>
  );
}

export default function CinematicBrowse({ data, loading, onOpen }) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const [q, setQ] = useState("");
  const rails = useMemo(() => {
    const rs = data?.rails || [];
    if (!q.trim()) return rs;
    const ql = q.toLowerCase();
    return rs
      .map((r) => ({ ...r, items: r.items.filter((i) => (i.title || "").toLowerCase().includes(ql)) }))
      .filter((r) => r.items.length);
  }, [data, q]);
  const hero = data?.hero;

  return (
    <div className="min-h-screen bg-[#0b0b0f] text-white" data-testid="browse-cinematic" style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex items-center gap-4 px-6 lg:px-10 h-16 bg-gradient-to-b from-black/95 to-black/40 backdrop-blur">
        <Link to="/" className="text-2xl font-black tracking-tight text-[#E50914]">RadioLife</Link>
        <nav className="hidden md:flex items-center gap-4 ml-4 text-sm">
          {NAV.map(([to, label]) => (
            <Link key={to} to={to} className="text-white/70 hover:text-white font-semibold">{label}</Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 bg-white/10 border border-white/15 rounded-full px-3 py-1.5">
            <Search size={14} className="text-white/60" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" data-testid="browse-search"
              className="bg-transparent text-sm text-white placeholder:text-white/40 outline-none w-32" />
          </div>
          <LayoutSwitcher tone="dark" />
          <button onClick={() => setVariant("legacy")} data-testid="browse-exit-legacy"
            className="hidden lg:inline-flex items-center gap-1 text-[11px] font-bold text-white/60 hover:text-white">
            <Sparkles size={12} /> Legacy
          </button>
        </div>
      </header>

      {/* Hero */}
      {hero && (
        <div className="relative h-[52vh] min-h-[340px] w-full -mt-16" data-testid="browse-hero">
          <div className="absolute inset-0"><Art item={hero} rounded="" /></div>
          <div className="absolute inset-0 bg-gradient-to-r from-black via-black/70 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0b0b0f] via-transparent to-transparent" />
          <div className="relative h-full flex flex-col justify-end pb-12 px-6 lg:px-10 max-w-2xl">
            {hero.badge && <span className="mb-3 w-fit text-[10px] font-black tracking-wider px-2 py-1 rounded bg-[#E50914]">{hero.badge}</span>}
            <h1 className="text-4xl lg:text-6xl font-black leading-none mb-3">{hero.title}</h1>
            <p className="text-white/80 text-sm lg:text-base mb-5 line-clamp-2">{hero.tagline || hero.subtitle}</p>
            <div className="flex items-center gap-3">
              <button onClick={() => onOpen(hero)} data-testid="browse-hero-play"
                className="inline-flex items-center gap-2 bg-white text-black font-black rounded-md px-6 py-2.5 hover:bg-white/85">
                <Play size={18} fill="currentColor" /> Play
              </button>
              <button onClick={() => onOpen(hero)}
                className="inline-flex items-center gap-2 bg-white/20 text-white font-bold rounded-md px-5 py-2.5 hover:bg-white/30">
                <Info size={18} /> More info
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rails */}
      <div className={hero ? "-mt-8 relative z-10 pb-16" : "pt-6 pb-16"}>
        {loading && <div className="px-10 py-20 text-center text-white/40">Loading…</div>}
        {!loading && rails.length === 0 && <div className="px-10 py-20 text-center text-white/40">Nothing here yet.</div>}
        {rails.map((r) => <Rail key={r.key} rail={r} onOpen={onOpen} />)}
      </div>
    </div>
  );
}
