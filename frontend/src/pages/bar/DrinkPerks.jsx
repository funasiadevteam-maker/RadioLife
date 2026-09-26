// "My drink perks" wallet — every bar-wheel prize the user has won, with codes
// they can show at the bar. GET /api/bar-games/wallet · POST …/plays/{id}/redeem
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Ticket, ArrowLeft, Wine, CheckCircle2, Gift } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function DrinkPerks() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/bar-games/wallet`, { withCredentials: true }); setData(data); }
    catch (_) { setData({ items: [], count: 0, active: 0 }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const redeem = async (id) => {
    try {
      await axios.post(`${API}/bar-games/plays/${id}/redeem`, {}, { withCredentials: true });
      setData((d) => ({ ...d, items: d.items.map((i) => (i.play_id === id ? { ...i, redeemed: true } : i)),
        active: Math.max(0, (d.active || 1) - 1) }));
      toast.success("Marked as redeemed 🍸");
    } catch (_) { toast.error("Couldn’t update."); }
  };

  return (
    <div className="min-h-screen text-white" style={{ background: "radial-gradient(900px 500px at 50% 0%,#241041,#0d0a1e 70%)" }}>
      <div className="max-w-lg mx-auto px-4 py-6" data-testid="drink-perks-page">
        <div className="flex items-center gap-3 mb-5">
          <button onClick={() => navigate(-1)} className="w-9 h-9 grid place-items-center rounded-full bg-white/10" data-testid="perks-back"><ArrowLeft size={18} /></button>
          <div>
            <h1 className="text-2xl font-black flex items-center gap-2"><Gift size={22} /> My drink perks</h1>
            <p className="text-sm text-purple-200/70">Codes you’ve won on bar wheels.</p>
          </div>
        </div>

        {!data ? (
          <div className="flex justify-center py-20"><Loader2 className="animate-spin text-purple-400" /></div>
        ) : data.items.length === 0 ? (
          <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-10 text-center text-slate-300/80" data-testid="perks-empty">
            <Wine size={34} className="mx-auto mb-3 text-purple-300/70" />
            No perks yet — spin a bar wheel to win free drinks and deals. 🍸
          </div>
        ) : (
          <div className="space-y-3">
            {data.items.map((p) => (
              <div key={p.play_id} data-testid={`perk-${p.play_id}`}
                   className="rounded-2xl border p-4 flex items-center gap-4"
                   style={{ background: p.redeemed ? "rgba(255,255,255,0.03)" : "rgba(52,211,153,0.08)",
                            borderColor: p.redeemed ? "rgba(255,255,255,0.1)" : "#34d39955", opacity: p.redeemed ? 0.6 : 1 }}>
                <span className="text-3xl">{p.emoji || "🍹"}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-black truncate">{p.label}</div>
                  <div className="text-[11px] text-slate-400 truncate">{p.business_name}</div>
                  <div className="inline-flex items-center gap-1.5 mt-1 font-mono font-black text-emerald-300 text-sm">
                    <Ticket size={13} /> {p.code}
                  </div>
                </div>
                {p.redeemed ? (
                  <span className="text-[11px] font-bold text-slate-400 flex items-center gap-1"><CheckCircle2 size={13} /> Redeemed</span>
                ) : (
                  <button onClick={() => redeem(p.play_id)} data-testid={`perk-redeem-${p.play_id}`}
                          className="text-[11px] font-black px-3 h-9 rounded-full bg-emerald-500/20 text-emerald-300">
                    Mark redeemed
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
