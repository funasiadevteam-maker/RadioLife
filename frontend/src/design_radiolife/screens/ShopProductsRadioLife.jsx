// RadioLife Shop — ecommerce products (browse, variants) → add to multi-venue cart — web.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Plus, Package, ShoppingBag } from "lucide-react";
import { API } from "@/AuthContext";
import { useProductCart } from "../useProductCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopProductsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/products/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [variantPick, setVariantPick] = useState({});
  const { add, count } = useProductCart();
  const cartCount = count();

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/products`).then((r) => {
      setData(r.data);
    }).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const priceOf = (p, v) => (v && v.price_cents > 0 ? v.price_cents : p.price_cents);
  const addToCart = (p) => {
    const v = p.variants?.length ? p.variants.find((x) => x.label === variantPick[p.product_id]) : null;
    if (p.variants?.length && !v) return;
    add(id, data.public_name, p, v);
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
                <button onClick={() => addToCart(p)} disabled={soldOut} data-testid={`prod-add-${p.product_id}`}
                  className="mt-2 inline-flex items-center gap-1 bg-orange-600 text-white font-black rounded-full px-4 py-1.5 text-sm disabled:opacity-40">
                  <Plus size={14} />{soldOut ? "Sold out" : "Add to cart"}
                </button>
              </div>
            </div>
          );
        })}
        {(!data.products || !data.products.length) && <p className="text-center text-slate-500 mt-6">No products yet.</p>}
      </div>

      {cartCount > 0 && (
        <div className="fixed bottom-16 left-0 right-0 max-w-3xl mx-auto px-4 py-3">
          <button onClick={() => navigate("/shop/cart")} data-testid="prod-go-cart"
            className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 shadow-lg">
            <ShoppingBag size={16} />View cart · {cartCount} item{cartCount > 1 ? "s" : ""}
          </button>
        </div>
      )}
    </div>
  );
}

