// RadioLife Shop — Amazon-style product grid (web): search + category chips +
// sort, clean product cards that open the detail page. Quick-add opens mini-cart.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Plus, Search, ShoppingBag, Coins, Store } from "lucide-react";
import { API } from "@/AuthContext";
import { useProductCart } from "../useProductCart";
import { useMiniCart } from "../useMiniCart";
import ProductMiniCart from "../components/ProductMiniCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const SORTS = [["featured", "Featured"], ["price_asc", "Price: low → high"], ["price_desc", "Price: high → low"], ["name", "Name A–Z"]];

export default function ShopProductsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/products/")[1]?.split("/")[0];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [sort, setSort] = useState("featured");
  const { add, count } = useProductCart();
  const showCart = useMiniCart((s) => s.show);
  const cartCount = count();

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/products`)
      .then((r) => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const cats = useMemo(() => [...new Set((data?.products || []).map((p) => p.category).filter(Boolean))], [data]);
  const products = useMemo(() => {
    let list = [...(data?.products || [])];
    if (q.trim()) { const s = q.toLowerCase(); list = list.filter((p) => p.name.toLowerCase().includes(s) || (p.description || "").toLowerCase().includes(s)); }
    if (cat) list = list.filter((p) => p.category === cat);
    if (sort === "price_asc") list.sort((a, b) => a.price_cents - b.price_cents);
    else if (sort === "price_desc") list.sort((a, b) => b.price_cents - a.price_cents);
    else if (sort === "name") list.sort((a, b) => a.name.localeCompare(b.name));
    return list;
  }, [data, q, cat, sort]);

  const quickAdd = (e, p) => {
    e.stopPropagation();
    if ((p.variants || []).length) { navigate(`/shop/products/${id}/${encodeURIComponent(p.product_id)}`); return; }
    add(id, data.public_name, p, null, 1);
    showCart();
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Shop unavailable.</div>;

  return (
    <div className="pb-28" data-testid="rl-shop-products-page">
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate(-1)} data-testid="prod-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
          <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name}</h1>
        </div>
        <button onClick={() => navigate("/shop/cart")} data-testid="prod-go-cart" className="relative">
          <ShoppingBag size={22} className="text-slate-700" />
          {cartCount > 0 && <span className="absolute -top-1.5 -right-2 bg-orange-600 text-white text-[10px] font-black rounded-full min-w-[16px] h-4 px-1 flex items-center justify-center">{cartCount}</span>}
        </button>
      </div>

      {/* Search */}
      <div className="px-4">
        <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2.5">
          <Search size={16} className="text-slate-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search products…" data-testid="prod-search"
            className="flex-1 bg-transparent text-sm outline-none" />
        </div>
      </div>

      {/* Category chips + sort */}
      <div className="mt-3 px-4 flex items-center gap-2">
        <div className="flex-1 flex gap-2 overflow-x-auto pb-1">
          <button onClick={() => setCat("")} data-testid="prod-cat-all"
            className={`shrink-0 px-3.5 py-1.5 rounded-full text-xs font-black ${!cat ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>All</button>
          {cats.map((c) => (
            <button key={c} onClick={() => setCat(c)} data-testid={`prod-cat-${c}`}
              className={`shrink-0 px-3.5 py-1.5 rounded-full text-xs font-black whitespace-nowrap ${cat === c ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}>{c}</button>
          ))}
        </div>
        <select value={sort} onChange={(e) => setSort(e.target.value)} data-testid="prod-sort"
          className="shrink-0 bg-white border border-slate-200 rounded-xl px-2.5 py-2 text-xs font-bold text-slate-700">
          {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      {/* Grid */}
      <div className="px-4 mt-4">
        {products.length === 0 ? (
          <div className="text-center text-slate-500 mt-10">
            <Store size={40} className="mx-auto text-slate-300" />
            <p className="mt-3 font-semibold">{data.products?.length ? "No products match your search." : "No products yet."}</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {products.map((p) => {
              const soldOut = (p.variants || []).length ? p.variants.every((v) => v.stock <= 0) : p.stock <= 0;
              return (
                <button key={p.product_id} onClick={() => navigate(`/shop/products/${id}/${encodeURIComponent(p.product_id)}`)}
                  data-testid={`prod-card-${p.product_id}`}
                  className="text-left bg-white border border-slate-200 rounded-2xl overflow-hidden hover:border-orange-300 hover:shadow-md transition flex flex-col">
                  <div className="relative w-full aspect-square bg-slate-100 overflow-hidden">
                    {p.image_url
                      ? <img src={p.image_url} alt={p.name} className="w-full h-full object-cover" />
                      : <div className="w-full h-full flex items-center justify-center text-slate-300"><Store size={32} /></div>}
                    {p.category && <span className="absolute top-2 left-2 text-[10px] font-black uppercase tracking-wide text-white bg-black/45 px-2 py-0.5 rounded-full">{p.category}</span>}
                    {soldOut && <span className="absolute inset-x-0 bottom-0 bg-rose-600 text-white text-[11px] font-black text-center py-1">Sold out</span>}
                  </div>
                  <div className="p-2.5 flex-1 flex flex-col">
                    <div className="text-sm font-bold text-slate-900 line-clamp-2 min-h-[2.5rem]">{p.name}</div>
                    {p.bigpoints > 0 && <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] font-bold text-amber-700"><Coins size={11} />+{p.bigpoints} pts</div>}
                    <div className="mt-auto flex items-center justify-between pt-2">
                      <span className="text-base font-black text-slate-900">{money(p.price_cents)}</span>
                      <span onClick={(e) => quickAdd(e, p)} data-testid={`prod-add-${p.product_id}`}
                        className={`w-8 h-8 rounded-full flex items-center justify-center ${soldOut ? "bg-slate-100 text-slate-300" : "bg-orange-500 text-slate-900"}`}>
                        <Plus size={16} />
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {cartCount > 0 && (
        <div className="fixed bottom-16 left-0 right-0 max-w-3xl mx-auto px-4 py-3 z-[70]">
          <button onClick={() => navigate("/shop/cart")}
            className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 shadow-lg">
            <ShoppingBag size={16} />View cart · {cartCount} item{cartCount > 1 ? "s" : ""}
          </button>
        </div>
      )}

      <ProductMiniCart />
    </div>
  );
}
