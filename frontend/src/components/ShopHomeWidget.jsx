// Home Shop Widget (legacy dashboard) — surfaces the RadioLife marketplace
// on the web home page with a jump-in link + a few featured venues.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Store, ArrowRight, Coins } from "lucide-react";
import { API } from "@/AuthContext";

export default function ShopHomeWidget() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let ok = true;
    axios.get(`${API}/shop/businesses?sort=featured&limit=6`)
      .then((r) => { if (ok) setItems((r.data.items || []).slice(0, 4)); })
      .catch(() => {});
    return () => { ok = false; };
  }, []);

  if (!items.length) return null;

  return (
    <section data-testid="home-shop-widget">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-8 h-8 rounded-token-card bg-accent-electric/15 flex items-center justify-center">
            <Store size={16} className="text-accent-electric" />
          </span>
          <h2 className="font-display font-bold text-xl tracking-display-tight">Shop local & earn BigPoints</h2>
        </div>
        <Link to="/shop" data-testid="home-shop-open"
          className="text-sm font-bold text-accent-electric hover:underline flex items-center gap-1">
          Open Shop <ArrowRight size={14} />
        </Link>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {items.map((b) => (
          <Link
            key={b.business_id}
            to={`/shop/${b.business_id}`}
            data-testid={`home-shop-biz-${b.business_id}`}
            className="group rounded-token-card border border-white/[0.06] bg-white/[0.02]
                       hover:bg-white/[0.05] transition-colors duration-150 overflow-hidden">
            <div className="aspect-[16/10] bg-white/[0.04] overflow-hidden">
              {b.cover_url && (
                <img src={b.cover_url} alt={b.public_name} loading="lazy"
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
              )}
            </div>
            <div className="p-3">
              <div className="font-display font-bold text-sm truncate">{b.public_name}</div>
              <div className="text-xs text-text-secondary truncate">{b.subcategory || b.category}</div>
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
