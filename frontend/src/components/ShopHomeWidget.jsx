// Home Shop Widget (legacy dashboard) — a prominent "highlight card" that
// surfaces the RadioLife marketplace on the web home page with a gradient
// hero band, a jump-in CTA, and a few featured local venues.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Store, ArrowRight, Coins, MapPin } from "lucide-react";
import { API } from "@/AuthContext";

export default function ShopHomeWidget() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let ok = true;
    axios.get(`${API}/shop/businesses?sort=featured&limit=6`)
      .then((r) => {
        if (ok) setItems((r.data.items || []).filter((b) => b.cover_url).slice(0, 4));
      })
      .catch(() => {});
    return () => { ok = false; };
  }, []);

  if (!items.length) return null;

  return (
    <section data-testid="home-shop-widget"
      className="rounded-token-card overflow-hidden border border-accent-electric/25
                 bg-gradient-to-br from-accent-electric/[0.12] via-white/[0.02] to-transparent">
      {/* Hero band */}
      <div className="flex items-center justify-between gap-3 p-4 sm:p-5
                      bg-gradient-to-r from-accent-electric/20 to-transparent">
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-11 h-11 rounded-token-card bg-accent-electric/20 flex items-center justify-center shrink-0">
            <Store size={20} className="text-accent-electric" />
          </span>
          <div className="min-w-0">
            <h2 className="font-display font-bold text-xl tracking-display-tight truncate">
              Shop local & earn BigPoints
            </h2>
            <p className="text-xs text-text-secondary truncate">
              Food, services & gift cards from venues near you
            </p>
          </div>
        </div>
        <Link to="/shop" data-testid="home-shop-open"
          className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-accent-electric
                     text-black font-bold text-sm px-4 py-2 hover:brightness-110 transition">
          Open Shop <ArrowRight size={15} />
        </Link>
      </div>

      {/* Featured venues */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 pt-1">
        {items.map((b) => (
          <Link
            key={b.business_id}
            to={`/shop/${b.business_id}`}
            data-testid={`home-shop-biz-${b.business_id}`}
            className="group rounded-token-card border border-white/[0.06] bg-white/[0.02]
                       hover:bg-white/[0.05] hover:border-accent-electric/30
                       transition-colors duration-150 overflow-hidden">
            <div className="aspect-[16/10] bg-white/[0.04] overflow-hidden">
              <img src={b.cover_url} alt={b.public_name} loading="lazy"
                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
            </div>
            <div className="p-3">
              <div className="font-display font-bold text-sm truncate">{b.public_name}</div>
              <div className="text-xs text-text-secondary truncate flex items-center gap-1">
                <MapPin size={10} className="shrink-0" />{b.subcategory || b.category}
              </div>
              <div className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-bold text-accent-gold">
                <Coins size={11} /> Earn {b.default_bigpoints}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
