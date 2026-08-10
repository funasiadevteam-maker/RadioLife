// RadioLife Shop — ecommerce products (browse, variants, cart, checkout) — web.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Plus, Minus, Package, ShoppingBag } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const keyOf = (pid, v) => (v ? `${pid}::${v}` : pid);

export default function ShopProductsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/products/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState({});
  const [fulfillment, setFulfillment] = useState("pickup");
  const [address, setAddress] = useState("");
  const [variantPick, setVariantPick] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/products`).then((r) => {
      setData(r.data);
      const d = r.data.delivery || {};
      setFulfillment(d.pickup ? "pickup" : (d.delivery ? "delivery" : "pickup"));
    }).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const priceOf = (p, v) => (v && v.price_cents > 0 ? v.price_cents : p.price_cents);
  const add = (p) => {
    const v = p.variants?.length ? p.variants.find((x) => x.label === variantPick[p.product_id]) : null;
    if (p.variants?.length && !v) return;
    const k = keyOf(p.product_id, v?.label);
    setCart((c) => ({ ...c, [k]: { product: p, variant: v, qty: (c[k]?.qty || 0) + 1 } }));
  };
  const dec = (k) => setCart((c) => {
    const q = (c[k]?.qty || 0) - 1; const n = { ...c };
    if (q <= 0) delete n[k]; else n[k] = { ...c[k], qty: q };
    return n;
  });

  const entries = Object.entries(cart);
  const subtotal = entries.reduce((s, [, it]) => s + priceOf(it.product, it.variant) * it.qty, 0);
  const dcfg = data?.delivery || {};
  const deliveryFee = fulfillment === "delivery"
    ? (dcfg.free_over_cents > 0 && subtotal >= dcfg.free_over_cents ? 0 : (dcfg.fee_cents || 0)) : 0;

  const checkout = async () => {
    if (!entries.length) return;
    if (fulfillment === "delivery" && !address.trim()) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/product-orders/checkout`, {
        business_id: id,
        items: entries.map(([, it]) => ({ product_id: it.product.product_id, variant_label: it.variant?.label || null, qty: it.qty })),
        fulfillment, address: fulfillment === "delivery" ? address.trim() : null,
        origin_url: window.location.origin, use_gift_card: true,
      });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      navigate("/shop/product-orders");
    } catch { setBusy(false); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Shop unavailable.</div>;

  return (
    <div className="pb-40" data-testid="rl-shop-products-page">
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate(-1)} data-testid="prod-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
          <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name}</h1>
        </div>
        <button onClick={() => navigate("/shop/product-orders")} data-testid="prod-orders"><Package size={20} className="text-slate-700" /></button>
      </div>

      <div className="px-4 space-y-3">
        {(data.products || []).map((p) => {
          const v = p.variants?.length ? p.variants.find((x) => x.label === variantPick[p.product_id]) : null;
          const soldOut = p.variants?.length ? p.variants.every((x) => x.stock <= 0) : p.stock <= 0;
          return (
            <div key={p.product_id} className="flex gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`prod-${p.product_id}`}>
              {p.image_url && <img src={p.image_url} alt={p.name} className="w-20 h-20 rounded-lg object-cover bg-slate-100" />}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-bold text-slate-900">{p.name}</div>
                {p.description && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{p.description}</div>}
                <div className="text-sm font-black text-orange-600 mt-1">{money(priceOf(p, v))}</div>
                {p.variants?.length > 0 && (
                  <div className="flex gap-1.5 overflow-x-auto mt-1.5 pb-1">
                    {p.variants.map((vr) => (
                      <button key={vr.label} disabled={vr.stock <= 0}
                        onClick={() => setVariantPick((m) => ({ ...m, [p.product_id]: vr.label }))}
                        data-testid={`prod-variant-${p.product_id}-${vr.label}`}
                        className={`shrink-0 px-3 h-8 rounded-full text-xs font-black ${variantPick[p.product_id] === vr.label ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"} ${vr.stock <= 0 ? "opacity-40" : ""}`}>{vr.label}</button>
                    ))}
                  </div>
                )}
                <button onClick={() => add(p)} disabled={soldOut} data-testid={`prod-add-${p.product_id}`}
                  className="mt-2 inline-flex items-center gap-1 bg-orange-600 text-white font-black rounded-full px-4 py-1.5 text-sm disabled:opacity-40">
                  <Plus size={14} />{soldOut ? "Sold out" : "Add"}
                </button>
              </div>
            </div>
          );
        })}
        {(!data.products || !data.products.length) && <p className="text-center text-slate-500 mt-6">No products yet.</p>}
      </div>

      {entries.length > 0 && (
        <div className="fixed bottom-16 left-0 right-0 max-w-md mx-auto px-4 py-3 bg-white border-t border-slate-200" data-testid="prod-cart-bar">
          <div className="max-h-24 overflow-y-auto mb-2 space-y-1">
            {entries.map(([k, it]) => (
              <div key={k} className="flex items-center justify-between text-sm">
                <span className="truncate text-slate-700 font-semibold">{it.product.name}{it.variant ? ` (${it.variant.label})` : ""}</span>
                <span className="flex items-center gap-2">
                  <button onClick={() => dec(k)} className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center"><Minus size={12} /></button>
                  <span className="font-black w-4 text-center">{it.qty}</span>
                  <button onClick={() => add(it.product)} className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center"><Plus size={12} /></button>
                </span>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mb-2">
            {dcfg.pickup && <button onClick={() => setFulfillment("pickup")} data-testid="prod-pickup" className={`flex-1 py-2 rounded-lg font-black text-sm ${fulfillment === "pickup" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>Pickup</button>}
            {dcfg.delivery && <button onClick={() => setFulfillment("delivery")} data-testid="prod-delivery" className={`flex-1 py-2 rounded-lg font-black text-sm ${fulfillment === "delivery" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>Delivery{deliveryFee > 0 ? ` +${money(deliveryFee)}` : " Free"}</button>}
          </div>
          {fulfillment === "delivery" && (
            <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Delivery address" data-testid="prod-address"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm mb-2" />
          )}
          <button onClick={checkout} disabled={busy} data-testid="prod-checkout"
            className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-60">
            <ShoppingBag size={16} />Checkout · {money(subtotal + deliveryFee)}
          </button>
        </div>
      )}
    </div>
  );
}
