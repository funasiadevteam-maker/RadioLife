// RadioLife Shop — web consumer marketplace (Super Marketplace Phase A).
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Search, Star, Store, ArrowRight, Coins } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, RLChip } from "../DesignSystem";

function BizCard({ b }) {
  return (
    <Link to={`/shop/${b.business_id}`} data-testid={`shop-biz-${b.business_id}`}
      className="block rounded-2xl overflow-hidden bg-white border border-slate-200 hover:shadow-lg transition-shadow">
      <div className="relative h-32 bg-slate-100">
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        {b.sponsored && <span className="absolute top-2 left-2 text-[10px] font-bold text-white bg-black/60 px-2 py-0.5 rounded-full">Sponsored</span>}
        <span className="absolute bottom-2 right-2 flex items-center gap-1 bg-amber-400 text-amber-950 text-[11px] font-black px-2 py-1 rounded-full">
          <Coins size={11} /> Earn {b.default_bigpoints}
        </span>
      </div>
      <div className="p-3">
        <div className="font-black text-slate-900 truncate">{b.public_name}</div>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-xs text-slate-500 capitalize truncate">{b.subcategory || b.category}</span>
          {b.rating ? <span className="flex items-center gap-1 text-xs font-bold text-slate-700">
            <Star size={11} className="text-amber-500 fill-amber-500" />{b.rating.toFixed(1)}</span> : null}
        </div>
      </div>
    </Link>
  );
}

export default function ShopRadioLife() {
  const [home, setHome] = useState(null);
  const [cats, setCats] = useState([]);
  const [category, setCategory] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("featured");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/shop/home`).catch(() => ({ data: {} })),
      axios.get(`${API}/shop/categories`).catch(() => ({ data: { items: [] } })),
    ]).then(([h, c]) => {
      setHome(h.data);
      setCats([{ key: "all", name: "All" }, ...(c.data.items || [])]);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    const params = { sort };
    if (category !== "all") params.category = category;
    if (q.trim()) params.q = q.trim();
    axios.get(`${API}/shop/businesses`, { params }).then((r) => setItems(r.data.items || [])).catch(() => setItems([]));
  }, [category, q, sort]);

  const browsing = category !== "all" || q.trim();
  const sections = useMemo(() => (home?.sections || []).filter((s) => s.items?.length), [home]);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading Shop…</div>;

  return (
    <div className="px-4 pt-6 pb-8 space-y-4" data-testid="rl-shop-page">
      <header>
        <div className="text-orange-600 text-[11px] font-black tracking-widest">RADIOLIFE SHOP</div>
        <h1 className="text-3xl font-black tracking-tight text-slate-900 leading-tight mt-1">
          {home?.headline || "SHOP LOCAL. EARN BIGPOINTS."}</h1>
      </header>

      <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-full px-4 py-3">
        <Search size={18} className="text-slate-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="shop-search"
          placeholder="What are you looking for?" className="flex-1 outline-none text-sm text-slate-800" />
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1" data-testid="shop-categories">
        {cats.map((c) => (
          <RLChip key={c.key} active={category === c.key} onClick={() => setCategory(c.key)}
            data-testid={`shop-cat-${c.key}`} className="whitespace-nowrap capitalize">{c.name}</RLChip>
        ))}
      </div>

      <Link to="/sell" data-testid="shop-sell-cta"
        className="flex items-center gap-3 bg-orange-600 text-white rounded-2xl p-4 hover:bg-orange-700 transition-colors">
        <Store size={22} />
        <div className="flex-1">
          <div className="font-black">Sell on RadioLife</div>
          <div className="text-xs opacity-90">List your business & reward local customers with BigPoints.</div>
        </div>
        <ArrowRight size={22} />
      </Link>

      <div className="grid grid-cols-3 gap-3">
        <Link to="/shop/orders" data-testid="shop-my-orders"
          className="flex items-center justify-center gap-2 bg-orange-50 text-orange-600 font-black rounded-xl py-3">Orders</Link>
        <Link to="/shop/bookings" data-testid="shop-my-bookings"
          className="flex items-center justify-center gap-2 bg-orange-50 text-orange-600 font-black rounded-xl py-3">Bookings</Link>
        <Link to="/shop/merchant" data-testid="shop-merchant-dash"
          className="flex items-center justify-center gap-2 bg-orange-50 text-orange-600 font-black rounded-xl py-3">Merchant</Link>
      </div>

      {browsing ? (
        <>
          <div className="flex items-center gap-2">
            {[["featured", "Featured"], ["bigpoints", "Most BigPoints"], ["rating", "Top Rated"]].map(([k, l]) => (
              <RLChip key={k} active={sort === k} onClick={() => setSort(k)} data-testid={`shop-sort-${k}`}>{l}</RLChip>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {items.map((b) => <BizCard key={b.business_id} b={b} />)}
          </div>
          {items.length === 0 && <div className="text-center text-slate-400 py-8">No businesses found.</div>}
        </>
      ) : (
        sections.map((sec) => (
          <section key={sec.key} data-testid={`shop-section-${sec.key}`}>
            <h2 className="text-lg font-black text-slate-900 mb-2">{sec.title}</h2>
            <div className="grid grid-cols-2 gap-3">
              {sec.items.slice(0, 6).map((b) => <BizCard key={b.business_id + sec.key} b={b} />)}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
