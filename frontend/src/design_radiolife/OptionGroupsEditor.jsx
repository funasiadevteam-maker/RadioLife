// Reusable option-groups editor (web) for menu items & products. Lets a
// merchant define size/single/multi groups whose options carry an upcharge
// (price delta). Emits API-shaped groups (price_delta_cents in cents).
import React from "react";
import { Plus, X } from "lucide-react";

const TYPES = [["size", "Size (pick one)"], ["single", "Single choice"], ["multi", "Multiple choice"]];
const blankOpt = () => ({ label: "", price_delta_cents: 0, is_default: false, available: true });
const blankGroup = () => ({ name: "", type: "single", required: false, min_select: 0, max_select: 1, options: [blankOpt()] });

export default function OptionGroupsEditor({ value, onChange }) {
  const groups = value || [];
  const set = (next) => onChange(next);
  const updGroup = (gi, patch) => set(groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)));
  const updOpt = (gi, oi, patch) => set(groups.map((g, i) => (i === gi
    ? { ...g, options: g.options.map((o, j) => (j === oi ? { ...o, ...patch } : o)) } : g)));

  return (
    <div className="space-y-2" data-testid="option-groups-editor">
      <div className="text-xs font-black text-slate-500 uppercase">Options &amp; upgrades</div>
      {groups.map((g, gi) => (
        <div key={gi} className="border border-slate-200 rounded-xl p-2.5 space-y-2 bg-slate-50/40" data-testid={`optgrp-${gi}`}>
          <div className="flex gap-2">
            <input value={g.name} onChange={(e) => updGroup(gi, { name: e.target.value })} placeholder="Group name e.g. Size" data-testid={`optgrp-name-${gi}`}
              className="flex-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            <select value={g.type} onChange={(e) => updGroup(gi, { type: e.target.value, max_select: e.target.value === "multi" ? Math.max(2, g.max_select) : 1 })} data-testid={`optgrp-type-${gi}`}
              className="bg-white border border-slate-200 rounded-lg px-2 py-2 text-sm">
              {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <button onClick={() => set(groups.filter((_, i) => i !== gi))} data-testid={`optgrp-remove-${gi}`} className="w-9 h-9 rounded-lg bg-white border border-slate-200 flex items-center justify-center"><X size={15} className="text-rose-600" /></button>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600" data-testid={`optgrp-required-${gi}`}>
              <input type="checkbox" checked={g.required} onChange={(e) => updGroup(gi, { required: e.target.checked, min_select: e.target.checked ? 1 : 0 })} className="accent-orange-600" />Required
            </label>
            {g.type === "multi" && (
              <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600">Max
                <input type="number" min={1} value={g.max_select} onChange={(e) => updGroup(gi, { max_select: parseInt(e.target.value, 10) || 1 })} data-testid={`optgrp-max-${gi}`} className="w-16 bg-white border border-slate-200 rounded-lg px-2 py-1 text-sm" />
              </label>
            )}
          </div>
          <div className="space-y-1.5">
            {g.options.map((o, oi) => (
              <div key={oi} className="flex gap-2 items-center" data-testid={`optgrp-${gi}-opt-${oi}`}>
                <input value={o.label} onChange={(e) => updOpt(gi, oi, { label: e.target.value })} placeholder="Option e.g. Large" data-testid={`optgrp-${gi}-opt-label-${oi}`}
                  className="flex-1 bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-sm" />
                <div className="flex items-center gap-1">
                  <span className="text-xs font-bold text-slate-400">+$</span>
                  <input type="number" step="0.01" value={o.price_delta_cents ? o.price_delta_cents / 100 : ""} onChange={(e) => updOpt(gi, oi, { price_delta_cents: Math.round((parseFloat(e.target.value) || 0) * 100) })} placeholder="0.00" data-testid={`optgrp-${gi}-opt-price-${oi}`}
                    className="w-20 bg-white border border-slate-200 rounded-lg px-2 py-1.5 text-sm" />
                </div>
                <label className="flex items-center gap-1 text-[10px] font-bold text-slate-500" data-testid={`optgrp-${gi}-opt-default-${oi}`}>
                  <input type="checkbox" checked={o.is_default} onChange={(e) => updOpt(gi, oi, { is_default: e.target.checked })} className="accent-orange-600" />Def
                </label>
                {g.options.length > 1 && <button onClick={() => updGroup(gi, { options: g.options.filter((_, j) => j !== oi) })} data-testid={`optgrp-${gi}-opt-remove-${oi}`} className="text-rose-500"><X size={14} /></button>}
              </div>
            ))}
            <button onClick={() => updGroup(gi, { options: [...g.options, blankOpt()] })} data-testid={`optgrp-${gi}-add-opt`} className="text-orange-600 font-black text-xs flex items-center gap-1"><Plus size={13} />Add option</button>
          </div>
        </div>
      ))}
      <button onClick={() => set([...groups, blankGroup()])} data-testid="optgrp-add-group" className="flex items-center gap-1 text-orange-600 font-black text-sm"><Plus size={15} />Add option group</button>
    </div>
  );
}
