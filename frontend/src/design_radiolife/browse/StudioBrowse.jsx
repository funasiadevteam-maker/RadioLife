// Studio (Spotify-style) browse skin: left library sidebar + card grids, dark/green.
import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { Home, Search, Library, Play, Sparkles } from "lucide-react";
import { Art, NAV } from "./browseShared";
import LayoutSwitcher from "./LayoutSwitcher";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

const GREEN = "#1DB954";

function Card({ item, onOpen }) {
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-tile"
      className="group shrink-0 w-44 text-left bg-white/5 hover:bg-white/10 rounded-xl p-3 transition-colors">
      <div className="relative w-full aspect-square rounded-lg overflow-hidden shadow-lg mb-3">
        <Art item={item} rounded="rounded-lg" />
        <span className="absolute bottom-2 right-2 h-11 w-11 rounded-full flex items-center justify-center shadow-xl translate-y-2 opacity-0 group-hover:translate-y-0 group-hover:opacity-100 transition-all"
          style={{ background: GREEN }}>
          <Play size={18} className="text-black ml-0.5" fill="currentColor" />
        </span>
      </div>
      <div className="text-white font-bold text-sm line-clamp-1">{item.title}</div>
      <div className="text-white/50 text-xs line-clamp-2 mt-0.5">{item.subtitle}</div>
    </button>
  );
}

function QuickPick({ item, onOpen }) {
  return (
    <button onClick={() => onOpen(item)} data-testid="browse-tile"
      className="group flex items-center gap-3 bg-white/10 hover:bg-white/20 rounded-md overflow-hidden transition-colors">
      <div className="h-16 w-16 shrink-0"><Art item={item} rounded="" /></div>
      <span className="font-bold text-white text-sm truncate pr-3">{item.title}</span>
    </button>
  );
}

export default function StudioBrowse({ data, loading, onOpen }) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const rails = data?.rails || [];
  const quick = useMemo(() => rails.flatMap((r) => r.items).slice(0, 6), [rails]);
  const greeting = (() => {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  })();

  return (
    <div className="min-h-screen bg-black text-white flex" data-testid="browse-studio" style={{ fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif" }}>
      {/* Sidebar */}
      <aside className="hidden md:flex flex-col w-60 shrink-0 gap-2 p-4">
        <Link to="/" className="text-2xl font-black tracking-tight mb-3" style={{ color: GREEN }}>RadioLife</Link>
        <div className="bg-[#121212] rounded-xl p-3 space-y-1">
          {[["/", Home, "Home"], ["/discover", Search, "Search"], ["/wallet", Library, "Your Library"]].map(([to, Icon, label]) => (
            <Link key={label} to={to} className="flex items-center gap-3 px-2 py-2 rounded-lg text-white/70 hover:text-white font-bold text-sm">
              <Icon size={18} /> {label}
            </Link>
          ))}
        </div>
        <div className="bg-[#121212] rounded-xl p-3 mt-2 flex-1 overflow-y-auto">
          <div className="text-white/40 text-[10px] font-black uppercase tracking-wider px-2 mb-1">Browse</div>
          {rails.map((r) => (
            <a key={r.key} href={`#rail-${r.key}`} className="block px-2 py-1.5 rounded-lg text-white/60 hover:text-white text-sm font-semibold">{r.title}</a>
          ))}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 bg-gradient-to-b from-[#1f1f1f] to-[#0a0a0a]">
        <header className="sticky top-0 z-30 flex items-center gap-3 px-5 lg:px-8 h-16 bg-black/40 backdrop-blur">
          <h1 className="text-xl lg:text-2xl font-black">{greeting}</h1>
          <nav className="hidden lg:flex items-center gap-4 ml-4 text-sm">
            {NAV.map(([to, label]) => (
              <Link key={to} to={to} className="text-white/60 hover:text-white font-semibold">{label}</Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <LayoutSwitcher tone="dark" />
            <button onClick={() => setVariant("legacy")} data-testid="browse-exit-legacy"
              className="hidden lg:inline-flex items-center gap-1 text-[11px] font-bold text-white/60 hover:text-white">
              <Sparkles size={12} /> Legacy
            </button>
          </div>
        </header>

        <div className="px-5 lg:px-8 pb-20">
          {loading && <div className="py-20 text-center text-white/40">Loading…</div>}

          {/* Quick picks */}
          {quick.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-4 mb-8">
              {quick.map((it) => <QuickPick key={(it.id || "") + it.title} item={it} onOpen={onOpen} />)}
            </div>
          )}

          {/* Rails */}
          {rails.map((r) => (
            <section key={r.key} id={`rail-${r.key}`} className="mb-8" data-testid={`browse-rail-${r.key}`}>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-white font-black text-xl">{r.title}</h2>
                {r.accent && <span className="text-xs font-bold" style={{ color: GREEN }}>Originals</span>}
              </div>
              <div className="flex gap-3 overflow-x-auto no-scrollbar pb-2">
                {r.items.map((it) => <Card key={(it.id || "") + it.title} item={it} onOpen={onOpen} />)}
              </div>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
