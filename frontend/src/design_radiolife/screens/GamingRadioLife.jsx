// Web New Look — Gaming hub in RadioLife cream/orange design.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Loader2, Trophy, Zap, Target, Sparkles } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, RLBadge } from "../DesignSystem";

export default function GamingRadioLife() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/games/discover`, { withCredentials: true });
        setItems(data.items || []);
      } catch {
        setItems([]);
      } finally { setLoading(false); }
    })();
  }, []);

  return (
    <div className="px-4 pt-6 pb-6 space-y-5" data-testid="rl-gaming-page">
      <header>
        <div className="text-[10px] font-bold uppercase tracking-widest text-orange-600">
          Games
        </div>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">Play &amp; Win</h1>
        <p className="text-slate-500 text-sm mt-1">
          Spin the wheel or scratch a card at your favourite spots.
        </p>
      </header>

      {loading ? (
        <div className="flex items-center justify-center py-16" data-testid="rl-gaming-loading">
          <Loader2 className="animate-spin text-orange-500" size={28} />
        </div>
      ) : items.length === 0 ? (
        <RLCard className="p-8 text-center" data-testid="rl-gaming-empty">
          <Trophy size={36} className="mx-auto mb-3 text-orange-400" />
          <div className="font-black text-slate-900 text-lg">No games right now</div>
          <div className="text-sm text-slate-500 mt-1">
            Check back soon — merchants launch new games every week.
          </div>
        </RLCard>
      ) : (
        <div className="grid grid-cols-1 gap-3" data-testid="rl-gaming-grid">
          {items.map((g) => {
            const isSpin = g.game_type === "spin_win";
            const Icon = isSpin ? Zap : Target;
            return (
              <Link
                key={g.campaign_id}
                to={`/play/${g.campaign_id}`}
                data-testid={`rl-gaming-card-${g.campaign_id}`}
                className="block">
                <RLCard className="p-4 flex items-center gap-3 hover:shadow-md transition-shadow">
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0"
                        style={{ background: "linear-gradient(135deg,#FDE9DC 0%,#FEF0D9 100%)" }}>
                    <Icon size={22} className="text-orange-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] font-bold uppercase tracking-widest text-orange-600">
                      {isSpin ? "Spin & Win" : "Scratch & Win"}
                    </div>
                    <h3 className="text-base font-black truncate text-slate-900">{g.name}</h3>
                    {g.merchant_name && (
                      <div className="text-xs text-slate-500 truncate">{g.merchant_name}</div>
                    )}
                  </div>
                  <RLBadge tone="amber">Play</RLBadge>
                </RLCard>
              </Link>
            );
          })}
        </div>
      )}

      <RLCard className="p-4 flex items-center gap-3" data-testid="rl-gaming-cta">
        <div className="w-10 h-10 rounded-xl bg-orange-100 text-orange-700 flex items-center justify-center flex-shrink-0">
          <Sparkles size={18} />
        </div>
        <div className="flex-1 text-sm text-slate-700">
          Win points on every spin — then spend them at 100+ local spots.
        </div>
      </RLCard>
    </div>
  );
}
