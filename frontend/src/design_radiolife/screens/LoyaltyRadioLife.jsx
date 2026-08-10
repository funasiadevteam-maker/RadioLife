// RadioLife Shop — my loyalty tier + perks (web).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Star, CheckCircle2 } from "lucide-react";
import { API } from "@/AuthContext";

export default function LoyaltyRadioLife() {
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/shop/loyalty`).then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!d) return <div className="px-4 pt-10 text-center text-slate-500">Unavailable.</div>;

  return (
    <div className="pb-24" data-testid="rl-loyalty-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="loyalty-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">My Loyalty</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="rounded-2xl border-2 bg-white p-6 text-center" style={{ borderColor: d.color }}>
          <div className="w-14 h-14 rounded-full mx-auto flex items-center justify-center" style={{ backgroundColor: d.color }}>
            <Star size={24} className="text-white fill-white" />
          </div>
          <div className="text-2xl font-black text-slate-900 mt-3" data-testid="loyalty-tier">{d.tier_name}</div>
          <div className="text-sm font-black text-orange-600 mt-0.5">{d.bonus_pct > 0 ? `+${d.bonus_pct}% bonus BigPoints` : "Start earning to level up"}</div>
          <div className="text-sm text-slate-500 mt-1.5">{d.lifetime_points.toLocaleString()} lifetime BigPoints</div>
          {d.next_tier && (
            <>
              <div className="w-full h-2 rounded-full bg-slate-100 mt-4 overflow-hidden">
                <div className="h-2 rounded-full" style={{ width: `${Math.round(d.progress * 100)}%`, backgroundColor: d.color }} />
              </div>
              <div className="text-xs font-bold text-slate-500 mt-1.5">{d.points_to_next.toLocaleString()} more to {d.next_tier}</div>
            </>
          )}
        </div>

        <h2 className="text-base font-black text-slate-900">Your perks</h2>
        {(d.perks || []).map((p, i) => (
          <div key={i} className="flex items-center gap-2" data-testid={`loyalty-perk-${i}`}>
            <CheckCircle2 size={16} className="text-green-600" /><span className="text-sm font-semibold text-slate-600">{p}</span>
          </div>
        ))}

        <h2 className="text-base font-black text-slate-900 pt-2">All tiers</h2>
        {(d.all_tiers || []).map((t) => (
          <div key={t.key} data-testid={`loyalty-tier-${t.key}`}
            className={`flex items-center gap-3 bg-white rounded-xl p-3 ${t.key === d.tier ? "border-2" : "border border-slate-200"}`}
            style={t.key === d.tier ? { borderColor: d.color } : undefined}>
            <div className="w-3.5 h-3.5 rounded-full" style={{ backgroundColor: t.color }} />
            <span className="flex-1 text-sm font-black text-slate-900">{t.name}</span>
            <span className="text-xs font-bold text-slate-500">{t.min_points.toLocaleString()}+ · +{t.bonus_pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
