// Reusable item option + membership entitlement picker (web). Handles
// size/single/multi option groups with upcharges, enforces required/min/max,
// and (when eligible) lets the member apply a membership so the base item is
// free and only upgrades are charged. Server re-prices authoritatively.
import React, { useMemo, useState } from "react";
import { X, Check, Crown, Plus, Minus } from "lucide-react";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const signed = (c) => (c > 0 ? `+${money(c)}` : c < 0 ? `−${money(-c)}` : "Free");

// Auto-select defaults for size/single groups so required rules pass.
function initialSelection(groups) {
  const sel = new Set();
  (groups || []).forEach((g) => {
    if ((g.type === "size" || g.type === "single") && g.options?.length) {
      const def = g.options.find((o) => o.is_default) || g.options[0];
      if (def) sel.add(def.option_id);
    }
  });
  return sel;
}

// Default line (selection + unit price + summary) for a one-tap "quick add".
export function defaultMenuSelection(item) {
  const groups = item.option_groups || [];
  const sel = initialSelection(groups);
  let unit = item.price_cents || 0;
  const labels = [];
  groups.forEach((g) => g.options.forEach((o) => {
    if (sel.has(o.option_id)) { unit += o.price_delta_cents || 0; labels.push(o.label); }
  }));
  return { selected_option_ids: [...sel], unit_price_cents: unit, option_summary: labels.join(", ") || null };
}

// True when the default selection already satisfies every required group, so
// "+" can add instantly; otherwise the customize sheet must be opened.
export function menuQuickAddReady(item) {
  const groups = item.option_groups || [];
  const sel = initialSelection(groups);
  return groups.every((g) => {
    if (!g.required && !(g.min_select > 0)) return true;
    const n = g.options.filter((o) => sel.has(o.option_id)).length;
    return n >= Math.max(1, g.min_select || 0);
  });
}

export default function ItemOptionModal({ item, entitlement, notePresets, onClose, onConfirm }) {
  const groups = item.option_groups || [];
  const [selected, setSelected] = useState(() => initialSelection(groups));
  const [applyEnt, setApplyEnt] = useState(!!entitlement);
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const toggle = (g, o) => {
    setErr(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (g.type === "multi") {
        if (next.has(o.option_id)) next.delete(o.option_id);
        else {
          const chosen = g.options.filter((x) => next.has(x.option_id)).length;
          if (chosen >= (g.max_select || 1)) return prev;
          next.add(o.option_id);
        }
      } else {
        g.options.forEach((x) => next.delete(x.option_id));
        next.add(o.option_id);
      }
      return next;
    });
  };

  const { unit, entDiscount, optionSummary } = useMemo(() => {
    let u = item.price_cents || 0;
    let waived = entitlement && applyEnt ? item.price_cents || 0 : 0;
    const included = new Set(entitlement?.included_option_ids || []);
    const labels = [];
    groups.forEach((g) => {
      g.options.forEach((o) => {
        if (selected.has(o.option_id)) {
          u += o.price_delta_cents || 0;
          if (entitlement && applyEnt && included.has(o.option_id)) waived += o.price_delta_cents || 0;
          labels.push(o.label);
        }
      });
    });
    return { unit: u, entDiscount: Math.min(waived, u), optionSummary: labels.join(", ") || null };
  }, [selected, applyEnt, groups, item, entitlement]);

  const netPay = Math.max(0, unit - entDiscount);
  const cap = entitlement?.max_upcharge_cents;
  const charged = unit - (entitlement && applyEnt ? (item.price_cents || 0) : 0)
    - [...selected].reduce((s, id) => {
        const inc = new Set(entitlement?.included_option_ids || []);
        if (!(entitlement && applyEnt) || !inc.has(id)) return s;
        const o = groups.flatMap((g) => g.options).find((x) => x.option_id === id);
        return s + (o?.price_delta_cents || 0);
      }, 0);
  const overCap = entitlement && applyEnt && cap != null && charged > cap;

  const confirm = () => {
    for (const g of groups) {
      const n = g.options.filter((o) => selected.has(o.option_id)).length;
      if (g.required && n < Math.max(1, g.min_select || 0)) { setErr(`Please choose ${g.name}`); return; }
      if (n < (g.min_select || 0)) { setErr(`Choose at least ${g.min_select} for ${g.name}`); return; }
    }
    if (overCap) { setErr(`Upgrades over ${money(cap)} aren't covered by this membership`); return; }
    onConfirm({
      qty,
      selected_option_ids: [...selected],
      option_summary: optionSummary,
      note: note.trim() || null,
      unit_price_cents: unit,
      apply_entitlement_id: entitlement && applyEnt ? entitlement.entitlement_id : null,
      entitlement_label: entitlement && applyEnt ? entitlement.label : null,
      entitlement_discount_cents: entitlement && applyEnt ? entDiscount : 0,
    });
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center" data-testid="item-option-modal">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl max-h-[88vh] overflow-y-auto">
        <div className="sticky top-0 bg-white flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="font-black text-slate-900 truncate pr-2">{item.name}</div>
          <button onClick={onClose} data-testid="item-option-close" className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {item.image_url && (
            <div className="w-full h-44 rounded-2xl overflow-hidden bg-slate-100 -mt-1" data-testid="item-option-hero">
              <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
            </div>
          )}
          {item.description && <p className="text-sm text-slate-500 leading-relaxed">{item.description}</p>}
          {entitlement && (
            <button onClick={() => setApplyEnt((v) => !v)} data-testid="item-option-apply-membership"
              className={"w-full flex items-center gap-3 rounded-2xl p-3 text-left border-2 " + (applyEnt ? "border-orange-500 bg-orange-50" : "border-slate-200 bg-white")}>
              <span className={`w-5 h-5 rounded-md flex items-center justify-center ${applyEnt ? "bg-orange-600" : "bg-slate-200"}`}>{applyEnt && <Check size={13} className="text-white" />}</span>
              <Crown size={18} className="text-orange-600" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-black text-slate-900">Use {entitlement.plan_name || "membership"}</div>
                <div className="text-[11px] font-bold text-slate-500">{entitlement.label} · {entitlement.remaining} left</div>
              </div>
              {applyEnt && <span className="text-xs font-black text-green-700">BASE FREE</span>}
            </button>
          )}

          {groups.map((g) => (
            <div key={g.group_id} data-testid={`opt-group-${g.group_id}`}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="text-sm font-black text-slate-900 flex items-center gap-2">
                  {g.name}
                  {g.required && <span className="text-[10px] font-black text-green-700 bg-green-100 px-1.5 py-0.5 rounded-full uppercase tracking-wide">Required</span>}
                </div>
                <div className="text-[11px] font-bold text-slate-400">{g.type === "multi" ? `Up to ${g.max_select}` : "Choose 1"}</div>
              </div>
              <div className="space-y-1.5">
                {g.options.map((o) => {
                  const on = selected.has(o.option_id);
                  const included = applyEnt && new Set(entitlement?.included_option_ids || []).has(o.option_id);
                  return (
                    <button key={o.option_id} disabled={o.available === false} onClick={() => toggle(g, o)}
                      data-testid={`opt-${o.option_id}`}
                      className={"w-full flex items-center gap-3 rounded-xl px-3 py-2.5 text-left border " + (on ? "border-orange-500 bg-orange-50" : "border-slate-200 bg-slate-50") + (o.available === false ? " opacity-40" : "")}>
                      <span className={`w-4 h-4 ${g.type === "multi" ? "rounded-md" : "rounded-full"} border-2 flex items-center justify-center ${on ? "border-orange-500 bg-orange-500" : "border-slate-300"}`}>{on && <Check size={11} className="text-white" />}</span>
                      <span className="flex-1 text-sm font-bold text-slate-800">{o.label}</span>
                      <span className={"text-xs font-black " + (included ? "text-green-700" : "text-slate-500")}>{included ? "Included" : signed(o.price_delta_cents)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          <div>
            <div className="text-sm font-black text-slate-900 mb-1.5">Special instructions</div>
            <div className="flex flex-wrap gap-1.5 mb-2" data-testid="item-note-presets">
              {(notePresets && notePresets.length ? notePresets : ["No onions", "Extra spicy", "No ice", "Less sugar", "Well done", "On the side"]).map((chip) => (
                <button key={chip} type="button" data-testid={`item-note-chip-${chip}`}
                  onClick={() => setNote((n) => (n.toLowerCase().includes(chip.toLowerCase()) ? n : (n ? `${n}, ${chip}` : chip)))}
                  className="px-2.5 py-1 rounded-full border border-slate-200 bg-slate-50 text-xs font-bold text-slate-600 hover:border-orange-400 hover:text-orange-600">
                  + {chip}
                </button>
              ))}
            </div>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={140} rows={2}
              placeholder="e.g. no onions, extra spicy" data-testid="item-option-note"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none resize-none focus:border-orange-400" />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm font-black text-slate-900">Quantity</span>
            <div className="flex items-center gap-3 bg-slate-50 rounded-full px-2 py-1 border border-slate-200">
              <button onClick={() => setQty((q) => Math.max(1, q - 1))} data-testid="item-option-qty-dec" className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Minus size={15} className="text-orange-600" /></button>
              <span className="font-black w-5 text-center">{qty}</span>
              <button onClick={() => setQty((q) => q + 1)} data-testid="item-option-qty-inc" className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Plus size={15} className="text-orange-600" /></button>
            </div>
          </div>

          {err && <div className="text-rose-600 text-sm font-semibold" data-testid="item-option-error">{err}</div>}
        </div>

        <div className="sticky bottom-0 bg-white border-t border-slate-100 p-4">
          <button onClick={confirm} data-testid="item-option-confirm"
            className="w-full flex items-center justify-between gap-2 bg-orange-600 text-white font-black rounded-full px-5 py-3.5 disabled:opacity-60">
            <span>Add {qty} to order</span>
            <span className="flex items-center gap-2">
              {entitlement && applyEnt && entDiscount > 0 && <span className="text-white/60 line-through text-sm">{money(unit * qty)}</span>}
              <span data-testid="item-option-total">{money(netPay * qty)}</span>
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
