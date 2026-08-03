// Phase R.1 — Discover (restaurant directory).
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Search, Star, MapPin, Utensils } from "lucide-react";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import { RLCard, RLChip, RLBadge } from "../DesignSystem";
import { coordsForMarket } from "../utils/market_coords";

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "restaurant", label: "Restaurant" },
  { id: "cafe", label: "Cafe" },
  { id: "fast_food", label: "Fast Food" },
  { id: "bar", label: "Bar" },
  { id: "salon", label: "Salon" },
  { id: "retail", label: "Retail" },
];

export default function DiscoverRadioLife() {
  const market = useGeoStore((s) => s.market);
  const city = useGeoStore((s) => s.city);
  const [businesses, setBusinesses] = useState([]);
  const [category, setCategory] = useState("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const coords = coordsForMarket(market) || { lat: 25.15, lng: 55.25 };
    setLoading(true);
    axios.get(`${API}/public/businesses/nearby?lat=${coords.lat}&lng=${coords.lng}` +
                    `&radius_m=50000&limit=40`)
      .then((r) => setBusinesses(r.data?.items || []))
      .catch(() => setBusinesses([]))
      .finally(() => setLoading(false));
  }, [market]);

  const filtered = useMemo(() => {
    let list = businesses;
    if (category !== "all") list = list.filter((b) => b.category === category);
    const ql = q.trim().toLowerCase();
    if (ql) list = list.filter((b) =>
      `${b.name} ${b.address || ""} ${b.category || ""}`.toLowerCase().includes(ql));
    return list;
  }, [businesses, category, q]);

  return (
    <div className="px-4 pt-6 pb-6 space-y-4" data-testid="rl-discover-page">
      <header>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">Discover</h1>
        <p className="text-slate-500 text-sm mt-1">
          Real places around <span className="text-purple-700 font-semibold">
            {city || "you"}</span>
        </p>
      </header>

      <div className="relative">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2
                                                    text-slate-400 pointer-events-none" />
        <input
          type="text"
          placeholder="Search restaurants, cafes…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid="rl-discover-search"
          className="w-full h-11 pl-10 pr-3 rounded-full bg-white
                              border border-slate-200 focus:border-purple-400
                              focus:outline-none focus:ring-2 focus:ring-purple-400/20
                              text-sm placeholder:text-slate-400" />
      </div>

      <div className="flex gap-2 overflow-x-auto -mx-4 px-4 pb-1"
                data-testid="rl-discover-cats">
        {CATEGORIES.map((c) => (
          <RLChip
            key={c.id}
            active={category === c.id}
            onClick={() => setCategory(c.id)}
            data-testid={`rl-cat-${c.id}`}>
            {c.label}
          </RLChip>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-3" data-testid="rl-restaurant-grid">
        {loading ? (
          <RLCard className="p-4 text-sm text-slate-500">Loading places…</RLCard>
        ) : filtered.length === 0 ? (
          <RLCard className="p-6 text-center" data-testid="rl-discover-empty">
            <Utensils size={28} className="text-purple-300 mx-auto mb-3" />
            <div className="font-semibold text-slate-900">No places match</div>
            <div className="text-sm text-slate-500 mt-1">
              Try another category or clear your search.
            </div>
          </RLCard>
        ) : (
          filtered.map((b) => (
            <Link
              key={b.business_id}
              to={`/business/${b.slug}`}
              data-testid={`rl-restaurant-card-${b.business_id}`}
              className="block">
              <RLCard className="p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-purple-100
                                            flex items-center justify-center text-purple-700
                                            flex-shrink-0">
                    <Utensils size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-bold text-slate-900 truncate">{b.name}</div>
                      {typeof b.rating === "number" && (
                        <div className="flex items-center gap-0.5 flex-shrink-0
                                                    text-slate-700 text-sm font-semibold">
                          <Star size={13} className="fill-amber-400 text-amber-400" />
                          {b.rating.toFixed(1)}
                        </div>
                      )}
                    </div>
                    <div className="text-[11px] uppercase tracking-wider text-slate-500
                                              font-semibold mt-1 flex items-center gap-2">
                      <span className="capitalize">
                        {(b.category || "").replace("_", " ")}
                      </span>
                      {b.address && (
                        <>
                          <span className="opacity-40">·</span>
                          <span className="flex items-center gap-0.5 truncate">
                            <MapPin size={10} className="flex-shrink-0" />
                            <span className="truncate">{b.address}</span>
                          </span>
                        </>
                      )}
                    </div>
                    <div className="mt-2">
                      <RLBadge tone="purple">Points earnable</RLBadge>
                    </div>
                  </div>
                </div>
              </RLCard>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
