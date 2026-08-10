// RadioLife Shop — business detail (web).
import React, { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Star, Coins, Phone, Globe, Zap } from "lucide-react";
import { API } from "@/AuthContext";

export default function ShopBusinessRadioLife() {
  const params = useParams();
  const navigate = useNavigate();
  // Overlay renders screens without a <Route> param, so fall back to pathname.
  const id = params.id || window.location.pathname.split("/shop/")[1];
  const [b, setB] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}`)
      .then((r) => setB(r.data.business)).catch(() => setB(null)).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!b) return <div className="px-4 pt-10 text-center text-slate-500">Business not found.</div>;

  const sells = b.sells || [];
  const cta = sells.includes("menu") ? "Order Pickup"
    : (sells.includes("appointments") || sells.includes("services")) ? "Book Now"
    : sells.includes("products") ? "Shop Products" : "View";

  return (
    <div className="pb-24" data-testid="rl-shop-detail-page">
      <div className="relative h-52 bg-slate-100">
        {b.cover_url && <img src={b.cover_url} alt={b.public_name} className="w-full h-full object-cover" />}
        <button onClick={() => navigate(-1)} data-testid="shop-detail-back"
          className="absolute top-3 left-3 w-10 h-10 rounded-full bg-black/45 text-white flex items-center justify-center">
          <ChevronLeft size={22} />
        </button>
      </div>
      <div className="px-4 pt-4 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-2xl font-black text-slate-900">{b.public_name}</h1>
          {b.rating ? <span className="flex items-center gap-1 bg-amber-100 text-amber-900 px-3 py-1.5 rounded-full font-black">
            <Star size={13} className="fill-amber-500 text-amber-500" />{b.rating.toFixed(1)}</span> : null}
        </div>
        <div className="text-slate-500 text-sm font-semibold capitalize">
          {b.subcategory || b.category}{b.city ? ` · ${b.city}` : ""}</div>
        {b.description && <p className="text-slate-600 text-sm leading-relaxed">{b.description}</p>}

        <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-950 px-3 py-2 rounded-full font-bold">
          <Coins size={16} /> Earn {b.default_bigpoints} BigPoints here
        </div>

        <h2 className="text-base font-black text-slate-900 pt-3">Ways to earn here</h2>
        <div className="space-y-2">
          {(b.ways_to_earn || []).map((w, i) => (
            <div key={i} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`shop-earn-${i}`}>
              <Zap size={16} className="text-orange-600" />
              <span className="flex-1 text-sm font-semibold text-slate-800">{w.label}</span>
              <span className="text-sm font-black text-green-600">+{w.points}</span>
            </div>
          ))}
        </div>

        {(b.phone || b.website) && (
          <div className="pt-2 space-y-1">
            {b.phone && <a href={`tel:${b.phone}`} className="flex items-center gap-2 text-orange-600 font-semibold text-sm py-1"><Phone size={15} />{b.phone}</a>}
            {b.website && <a href={b.website} className="flex items-center gap-2 text-orange-600 font-semibold text-sm py-1"><Globe size={15} />{b.website}</a>}
          </div>
        )}
      </div>

      <div className="fixed bottom-20 left-0 right-0 px-4 max-w-md mx-auto">
        {(sells.includes("menu") || b.has_menu) ? (
          <Link to={`/shop/menu/${b.business_id}`} data-testid="shop-detail-cta"
            className="flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 shadow-lg">
            <Zap size={16} />{cta} · Earn {b.default_bigpoints}
          </Link>
        ) : (
          <Link to="/wallet" data-testid="shop-detail-cta"
            className="flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 shadow-lg">
            <Zap size={16} />{cta} · Earn {b.default_bigpoints}
          </Link>
        )}
      </div>
    </div>
  );
}
