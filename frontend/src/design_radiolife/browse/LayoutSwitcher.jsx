import React, { useState } from "react";
import { Layers, Check, ChevronDown } from "lucide-react";
import { useBrowseLayoutStore, BROWSE_LAYOUTS } from "./useBrowseLayout";

export default function LayoutSwitcher({ tone = "dark" }) {
  const layout = useBrowseLayoutStore((s) => s.layout);
  const setLayout = useBrowseLayoutStore((s) => s.setLayout);
  const [open, setOpen] = useState(false);
  const light = tone === "light";
  const cur = BROWSE_LAYOUTS.find((l) => l.key === layout) || BROWSE_LAYOUTS[0];
  return (
    <div className="relative" data-testid="layout-switcher">
      <button onClick={() => setOpen((o) => !o)} data-testid="layout-switcher-btn"
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold border transition-colors ${light ? "bg-white border-slate-200 text-slate-700 hover:bg-slate-50" : "bg-white/10 border-white/15 text-white hover:bg-white/20"}`}>
        <Layers size={14} /> {cur.label} <ChevronDown size={14} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className={`absolute right-0 mt-2 w-52 rounded-xl border shadow-2xl z-50 overflow-hidden ${light ? "bg-white border-slate-200" : "bg-[#181818] border-white/10"}`}>
            <div className={`px-3 pt-2.5 pb-1 text-[10px] font-black uppercase tracking-wider ${light ? "text-slate-400" : "text-white/40"}`}>Choose a layout</div>
            {BROWSE_LAYOUTS.map((l) => (
              <button key={l.key} onClick={() => { setLayout(l.key); setOpen(false); }} data-testid={`layout-opt-${l.key}`}
                className={`w-full flex items-center justify-between px-3 py-2.5 text-left ${light ? "hover:bg-slate-50" : "hover:bg-white/10"}`}>
                <span>
                  <span className={`block text-sm font-bold ${light ? "text-slate-800" : "text-white"}`}>{l.label}</span>
                  <span className={`block text-[10px] ${light ? "text-slate-400" : "text-white/40"}`}>{l.desc}</span>
                </span>
                {layout === l.key && <Check size={16} className="text-emerald-500" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
