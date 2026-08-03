// Phase PG.1 — Consumer game discovery.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Trophy, ArrowLeft, Zap, Target } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function PlayDiscover() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/games/discover`,
                                                                        { withCredentials: true });
        setItems(data.items || []);
      } catch (e) {
        toast.error(`Load failed: ${e.message}`);
      } finally { setLoading(false); }
    })();
  }, []);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (loading) return (
    <div className={`${bgClass} flex items-center justify-center`}
              data-testid="play-discover-loading">
      <Loader2 className="animate-spin" size={30}/>
    </div>);

  return (
    <div className={`${bgClass} p-4 sm:p-8`}
              data-testid="play-discover-page">
      <div className="max-w-4xl mx-auto">
        <Link to="/" className={`inline-flex items-center gap-1 text-xs ${
          light ? "text-slate-500" : "text-slate-500"}`}>
          <ArrowLeft size={12}/> Home
        </Link>
        <div className="mt-4 mb-6">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-purple-600" : "text-cyan-400"}`}>Games</div>
          <h1 className={`text-3xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"}`}>Play &amp; Win</h1>
          <p className={`mt-1 text-sm ${
            light ? "text-slate-600" : "text-slate-400"}`}>
            Spin the wheel or scratch a card at your favourite spots.
          </p>
        </div>

        {items.length === 0 ? (
          <div className={`rounded-3xl p-10 text-center ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"}`}
                data-testid="play-discover-empty">
            <Trophy className="mx-auto mb-3" size={40}
                              color={light ? "#a855f7" : "#00d4ff"}/>
            <h3 className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"}`}>No games right now</h3>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Check back soon — merchants launch new games every week.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                data-testid="play-discover-grid">
            {items.map(g => {
              const Icon = g.game_type === "spin_win" ? Zap : Target;
              return (
                <Link key={g.campaign_id} to={`/play/${g.campaign_id}`}
                            data-testid={`play-discover-card-${g.campaign_id}`}
                            className={`rounded-3xl p-5 flex items-center gap-3 transition-transform hover:scale-[1.02] ${
                              light ? "bg-white border border-slate-100 shadow-sm"
                                      : "bg-slate-900 border border-slate-800"}`}>
                  <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${
                    light ? "bg-gradient-to-br from-purple-100 to-pink-100"
                            : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"}`}>
                    <Icon size={22} color={light ? "#a855f7" : "#00d4ff"}/>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className={`text-[10px] font-bold uppercase tracking-widest ${
                      light ? "text-purple-600" : "text-cyan-400"}`}>
                      {g.game_type === "spin_win" ? "Spin & Win" : "Scratch & Win"}
                    </div>
                    <h3 className={`text-base font-black truncate ${
                      light ? "text-slate-900" : "text-white"}`}>{g.name}</h3>
                    {g.merchant_name && (
                      <div className={`text-xs ${
                        light ? "text-slate-500" : "text-slate-500"}`}>
                        {g.merchant_name}
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
