// Tube (YouTube-style) browse skin: light, category chips + responsive grid.
import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search, Play, Sparkles } from "lucide-react";
import { Art, NAV } from "./browseShared";
import LayoutSwitcher from "./LayoutSwitcher";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

function VideoCard({ item, onOpen }) {
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-tile" className="group text-left">
      <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-slate-100">
        <Art item={item} rounded="rounded-xl" />
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
        {item.badge && (
          <span className="absolute bottom-2 right-2 text-[10px] font-black px-1.5 py-0.5 rounded bg-black/80 text-white">{item.badge}</span>
        )}
      </div>
      <div className="flex gap-3 mt-2.5">
        <span className="shrink-0 h-9 w-9 rounded-full flex items-center justify-center text-white font-black text-sm"
          style={{ background: "linear-gradient(135deg,#FF0000,#c4302b)" }}>{(item.title || "?").slice(0, 1)}</span>
        <div className="min-w-0">
          <div className="font-bold text-[15px] leading-snug text-[#0f0f0f] line-clamp-2">{item.title}</div>
          <div className="text-[13px] text-slate-500 line-clamp-1 mt-0.5">{item.subtitle}</div>
        </div>
      </div>
    </button>
  );
}

export default function TubeBrowse({ data, loading, onOpen }) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const rails = data?.rails || [];
  const chips = useMemo(() => [{ key: "all", title: "All" }, ...rails.map((r) => ({ key: r.key, title: r.title }))], [rails]);
  const items = useMemo(() => {
    let list = cat === "all" ? rails.flatMap((r) => r.items) : (rails.find((r) => r.key === cat)?.items || []);
    if (q.trim()) {
      const ql = q.toLowerCase();
      list = list.filter((i) => (i.title || "").toLowerCase().includes(ql));
    }
    return list;
  }, [rails, cat, q]);

  return (
    <div className="min-h-screen bg-white text-[#0f0f0f]" data-testid="browse-tube" style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      {/* Top bar */}
      <header className="sticky top-0 z-30 flex items-center gap-4 px-4 lg:px-8 h-14 bg-white border-b border-slate-100">
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

      {/* Nav row */}
      <div className="hidden md:flex items-center gap-4 px-8 h-10 border-b border-slate-100 text-sm">
        {NAV.map(([to, label]) => (
          <Link key={to} to={to} className="text-slate-600 hover:text-black font-semibold">{label}</Link>
        ))}
      </div>

      {/* Category chips */}
      <div className="sticky top-14 z-20 bg-white/95 backdrop-blur flex gap-2 overflow-x-auto no-scrollbar px-4 lg:px-8 py-3 border-b border-slate-100" data-testid="browse-chips">
        {chips.map((c) => (
          <button key={c.key} onClick={() => setCat(c.key)} data-testid={`browse-chip-${c.key}`}
            className={`shrink-0 px-3.5 py-1.5 rounded-lg text-sm font-bold transition-colors ${cat === c.key ? "bg-[#0f0f0f] text-white" : "bg-slate-100 text-slate-800 hover:bg-slate-200"}`}>
            {c.title}
          </button>
        ))}
      </div>

      {/* Grid */}
      <div className="px-4 lg:px-8 py-6">
        {loading && <div className="py-20 text-center text-slate-400">Loading…</div>}
        {!loading && items.length === 0 && <div className="py-20 text-center text-slate-400">No results.</div>}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-4 gap-y-7">
          {items.map((it, i) => <VideoCard key={(it.id || "") + it.title + i} item={it} onOpen={onOpen} />)}
        </div>
      </div>
    </div>
  );
}
