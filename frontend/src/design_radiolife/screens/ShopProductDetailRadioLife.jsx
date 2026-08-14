// RadioLife Shop — Amazon-style single product detail (web).
// Gallery + buy box (price, variant tiles, quantity, Add to cart / Buy Now)
// + "More from this shop". Adding opens the slide-in mini-cart.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Plus, Minus, ShoppingCart, Zap, Coins, Check, Store, ShieldCheck } from "lucide-react";
import { API } from "@/AuthContext";
import { useProductCart } from "../useProductCart";
import { useMiniCart } from "../useMiniCart";
import ProductMiniCart from "../components/ProductMiniCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopProductDetailRadioLife() {
  const navigate = useNavigate();
  const parts = window.location.pathname.split("/").filter(Boolean); // [shop, products, bizId, productId]
  const bizId = parts[2];
  const productId = decodeURIComponent(parts[3] || "");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [variant, setVariant] = useState(null);
  const [qty, setQty] = useState(1);
  const { add } = useProductCart();
  const showCart = useMiniCart((s) => s.show);

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${bizId}/products`)
      .then((r) => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [bizId]);

  const product = useMemo(() => (data?.products || []).find((p) => p.product_id === productId), [data, productId]);
  const others = useMemo(() => (data?.products || []).filter((p) => p.product_id !== productId).slice(0, 8), [data, productId]);

  useEffect(() => { setQty(1); setVariant(null); }, [productId]);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data || !product) return (
    <div className="px-4 pt-16 text-center text-slate-500" data-testid="pd-not-found">
      Product unavailable.
      <div><button onClick={() => navigate(`/shop/products/${bizId}`)} className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">Back to shop</button></div>
    </div>
  );

  const hasVariants = (product.variants || []).length > 0;
  const price = variant && variant.price_cents > 0 ? variant.price_cents : product.price_cents;
  const soldOut = hasVariants ? product.variants.every((v) => v.stock <= 0) : product.stock <= 0;
  const needsPick = hasVariants && !variant;

  const doAdd = () => {
    if (needsPick || soldOut) return;
    add(bizId, data.public_name, product, variant, qty);
    showCart();
  };
  const buyNow = () => {
    if (needsPick || soldOut) return;
    add(bizId, data.public_name, product, variant, qty);
    navigate("/shop/checkout/cart");
  };

  return (
    <div className="pb-24" data-testid="rl-shop-product-detail-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(`/shop/products/${bizId}`)} data-testid="pd-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <button onClick={() => navigate(`/shop/products/${bizId}`)} className="text-sm font-bold text-slate-500 truncate flex items-center gap-1"><Store size={14} className="text-orange-600" />{data.public_name}</button>
      </div>

      <div className="px-4 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Gallery */}
        <div>
          <div className="w-full aspect-square rounded-2xl bg-slate-100 overflow-hidden" data-testid="pd-image">
            {product.image_url
              ? <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" />
              : <div className="w-full h-full flex items-center justify-center text-slate-300"><Store size={48} /></div>}
          </div>
          {product.category && <span className="inline-block mt-3 text-xs font-black uppercase tracking-wide text-orange-600 bg-orange-50 px-2.5 py-1 rounded-full">{product.category}</span>}
        </div>

        {/* Buy box */}
        <div className="lg:sticky lg:top-4 self-start">
          <h1 className="text-2xl font-black text-slate-900 leading-tight">{product.name}</h1>
          <div className="mt-2 text-3xl font-black text-slate-900">{money(price)}</div>
          {product.description && <p className="mt-3 text-sm text-slate-600 leading-relaxed">{product.description}</p>}

          {/* Variants */}
          {hasVariants && (
            <div className="mt-4">
              <div className="text-sm font-black text-slate-900 mb-1.5">Options{needsPick && <span className="text-rose-600 font-bold text-xs ml-1">· select one</span>}</div>
              <div className="flex flex-wrap gap-2">
                {product.variants.map((vr) => {
                  const out = vr.stock <= 0;
                  const active = variant?.label === vr.label;
                  return (
                    <button key={vr.label} disabled={out} onClick={() => setVariant(vr)} data-testid={`pd-variant-${vr.label}`}
                      className={`px-4 py-2 rounded-xl border text-sm font-bold text-left transition ${active ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"} ${out ? "opacity-40 line-through" : ""}`}>
                      {vr.label}
                      {vr.price_cents > 0 && <span className="block text-xs text-slate-500">{money(vr.price_cents)}</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Stock + points */}
          <div className="mt-4 flex items-center gap-3 text-sm">
            {soldOut ? <span className="font-black text-rose-600">Sold out</span>
              : <span className="font-black text-green-700 flex items-center gap-1"><Check size={15} />In stock</span>}
            {product.bigpoints > 0 && <span className="inline-flex items-center gap-1 text-amber-700 font-bold"><Coins size={14} />Earn {product.bigpoints} BigPoints</span>}
          </div>

          {/* Quantity */}
          <div className="mt-4 flex items-center gap-3">
            <span className="text-sm font-bold text-slate-700">Quantity</span>
            <div className="flex items-center gap-2 bg-orange-50 rounded-full px-1.5 py-1">
              <button onClick={() => setQty((q) => Math.max(1, q - 1))} data-testid="pd-qty-dec" className="w-8 h-8 rounded-full bg-white flex items-center justify-center"><Minus size={15} className="text-orange-600" /></button>
              <span className="font-black w-6 text-center text-slate-900" data-testid="pd-qty">{qty}</span>
              <button onClick={() => setQty((q) => q + 1)} data-testid="pd-qty-inc" className="w-8 h-8 rounded-full bg-white flex items-center justify-center"><Plus size={15} className="text-orange-600" /></button>
            </div>
          </div>

          {/* CTAs */}
          <div className="mt-5 space-y-2.5">
            <button onClick={doAdd} disabled={needsPick || soldOut} data-testid="pd-add"
              className="w-full flex items-center justify-center gap-2 bg-orange-500 text-slate-900 font-black rounded-full py-3.5 disabled:opacity-40">
              <ShoppingCart size={18} />Add to cart
            </button>
            <button onClick={buyNow} disabled={needsPick || soldOut} data-testid="pd-buynow"
              className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white font-black rounded-full py-3.5 disabled:opacity-40">
              <Zap size={18} />Buy now
            </button>
          </div>

          <div className="mt-4 text-xs text-slate-500 space-y-1">
            <div className="flex justify-between"><span>Seller</span><span className="font-bold text-slate-700">{data.public_name}</span></div>
            <div className="flex items-center gap-1.5 text-slate-500"><ShieldCheck size={13} className="text-green-600" />Secure checkout · pickup or delivery at next step</div>
          </div>
        </div>
      </div>

      {/* More from this shop */}
      {others.length > 0 && (
        <div className="px-4 mt-10">
          <h2 className="text-base font-black text-slate-900 mb-3">More from {data.public_name}</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {others.map((p) => (
              <button key={p.product_id} onClick={() => navigate(`/shop/products/${bizId}/${encodeURIComponent(p.product_id)}`)}
                data-testid={`pd-also-${p.product_id}`} className="text-left bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-orange-300 transition">
                <div className="w-full aspect-square bg-slate-100 overflow-hidden">
                  {p.image_url && <img src={p.image_url} alt={p.name} className="w-full h-full object-cover" />}
                </div>
                <div className="p-2.5">
                  <div className="text-sm font-bold text-slate-900 line-clamp-2">{p.name}</div>
                  <div className="text-sm font-black text-slate-900 mt-1">{money(p.price_cents)}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <ProductMiniCart />
    </div>
  );
}
