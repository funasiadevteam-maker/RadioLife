// Compact product variant + quantity picker (web) used for "Customize" on the
// store page. Mirrors the product detail buy-box but as a bottom-sheet/modal.
import React, { useMemo, useState } from "react";
import { X, Plus, Minus, ShoppingCart } from "lucide-react";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ProductVariantModal({ product, onClose, onConfirm }) {
  const variants = product.variants || [];
  const hasVariants = variants.length > 0;
  const firstInStock = useMemo(() => variants.find((v) => v.stock > 0) || variants[0] || null, [variants]);
  const [variant, setVariant] = useState(hasVariants ? firstInStock : null);
  const [qty, setQty] = useState(1);
  const [note, setNote] = useState("");
  const price = variant && variant.price_cents > 0 ? variant.price_cents : product.price_cents;
  const soldOut = hasVariants ? variants.every((v) => v.stock <= 0) : product.stock <= 0;

  return (
    <div className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center" data-testid="product-variant-modal">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl max-h-[88vh] overflow-y-auto">
        <div className="sticky top-0 bg-white flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="font-black text-slate-900 truncate pr-2">{product.name}</div>
          <button onClick={onClose} data-testid="product-variant-close" className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center"><X size={16} /></button>
        </div>

        <div className="p-4 space-y-4">
          {product.image_url && (
            <div className="w-full h-44 rounded-2xl overflow-hidden bg-slate-100" data-testid="product-variant-hero">
              <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />
            </div>
          )}
          <div className="text-2xl font-black text-slate-900">{money(price)}</div>
          {product.description && <p className="text-sm text-slate-500 leading-relaxed">{product.description}</p>}

          {hasVariants && (
            <div>
              <div className="text-sm font-black text-slate-900 mb-1.5">Options</div>
              <div className="flex flex-wrap gap-2">
                {variants.map((vr) => {
                  const out = vr.stock <= 0;
                  const active = variant?.label === vr.label;
                  return (
                    <button key={vr.label} disabled={out} onClick={() => setVariant(vr)} data-testid={`pv-variant-${vr.label}`}
                      className={`px-4 py-2 rounded-xl border text-sm font-bold text-left transition ${active ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"} ${out ? "opacity-40 line-through" : ""}`}>
                      {vr.label}
                      {vr.price_cents > 0 && <span className="block text-xs text-slate-500">{money(vr.price_cents)}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <div className="text-sm font-black text-slate-900 mb-1.5">Note to seller</div>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={140} rows={2}
              placeholder="e.g. gift wrap, colour preference" data-testid="product-variant-note"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none resize-none focus:border-orange-400" />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm font-black text-slate-900">Quantity</span>
            <div className="flex items-center gap-3 bg-slate-50 rounded-full px-2 py-1 border border-slate-200">
              <button onClick={() => setQty((q) => Math.max(1, q - 1))} data-testid="product-variant-qty-dec" className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Minus size={15} className="text-orange-600" /></button>
              <span className="font-black w-5 text-center">{qty}</span>
              <button onClick={() => setQty((q) => q + 1)} data-testid="product-variant-qty-inc" className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Plus size={15} className="text-orange-600" /></button>
            </div>
          </div>
        </div>

        <div className="sticky bottom-0 bg-white border-t border-slate-100 p-4">
          <button onClick={() => onConfirm({ variant, qty, note: note.trim() || null })} disabled={soldOut} data-testid="product-variant-confirm"
            className="w-full flex items-center justify-between gap-2 bg-orange-600 text-white font-black rounded-full px-5 py-3.5 disabled:opacity-60">
            <span className="flex items-center gap-2"><ShoppingCart size={18} />{soldOut ? "Sold out" : `Add ${qty} to cart`}</span>
            {!soldOut && <span data-testid="product-variant-total">{money(price * qty)}</span>}
          </button>
        </div>
      </div>
    </div>
  );
}
