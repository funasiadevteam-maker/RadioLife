// "My drink perks" wallet — every bar-wheel prize the user has won, with codes
// they can show at the bar. GET /api/bar-games/wallet · POST …/plays/{id}/redeem
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Ticket, ArrowLeft, Wine, CheckCircle2, Gift, Clock, Share2, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function expiryLabel(iso) {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return { expired: true, text: "Expired" };
  const d = Math.ceil(diff / 86400000);
  return { expired: false, text: `Expires in ${d}d` };
}

export default function DrinkPerks() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [giftFor, setGiftFor] = useState(null);
  const [friends, setFriends] = useState([]);

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

  const share = async (p) => {
    const text = `🍸 I won “${p.label}” at ${p.business_name} on FUUSIC! Redeem with code ${p.code}.`;
    try {
      if (navigator.share) await navigator.share({ title: "FUUSIC drink perk", text });
      else { await navigator.clipboard.writeText(text); toast.success("Perk copied — share it with a friend!"); }
    } catch (_) {}
  };

  const openGift = async (p) => {
    setGiftFor(p);
    try { const { data } = await axios.get(`${API}/social/friends`, { withCredentials: true }); setFriends(data.friends || []); }
    catch (_) { setFriends([]); }
  };
  const doGift = async (friendId) => {
    const pid = giftFor.play_id;
    try {
      await axios.post(`${API}/bar-games/plays/${pid}/gift`, { friend_id: friendId }, { withCredentials: true });
      setData((d) => ({ ...d, items: d.items.filter((i) => i.play_id !== pid), active: Math.max(0, (d.active || 1) - 1) }));
      setGiftFor(null);
      toast.success("Perk gifted 🎁");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "not_friends" ? "You can only gift to friends." : "Couldn’t gift.");
    }
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
            {data.items.map((p) => {
              const exp = expiryLabel(p.expires_at);
              const isExpired = p.expired || (exp && exp.expired);
              return (
              <div key={p.play_id} data-testid={`perk-${p.play_id}`}
                   className="rounded-2xl border p-4 flex items-center gap-4"
                   style={{ background: (p.redeemed || isExpired) ? "rgba(255,255,255,0.03)" : "rgba(52,211,153,0.08)",
                            borderColor: (p.redeemed || isExpired) ? "rgba(255,255,255,0.1)" : "#34d39955", opacity: (p.redeemed || isExpired) ? 0.6 : 1 }}>
                <span className="text-3xl">{p.emoji || "🍹"}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-black truncate">{p.label}</div>
                  <div className="text-[11px] text-slate-400 truncate">{p.business_name}</div>
                  <div className="inline-flex items-center gap-1.5 mt-1 font-mono font-black text-emerald-300 text-sm">
                    <Ticket size={13} /> {p.code}
                  </div>
                  {exp && (
                    <div className={`text-[11px] font-bold mt-1 inline-flex items-center gap-1 ${isExpired ? "text-rose-400" : p.expiring_soon ? "text-rose-300" : "text-amber-300"}`}
                         data-testid={`perk-expiry-${p.play_id}`}>
                      <Clock size={11} /> {isExpired ? "Expired" : p.expiring_soon ? `Expires soon · ${exp.text}` : exp.text}
                    </div>
                  )}
                </div>
                {p.redeemed ? (
                  <span className="text-[11px] font-bold text-slate-400 flex items-center gap-1"><CheckCircle2 size={13} /> Redeemed</span>
                ) : isExpired ? (
                  <span className="text-[11px] font-bold text-rose-400 flex items-center gap-1" data-testid={`perk-expired-${p.play_id}`}>Expired</span>
                ) : (
                  <div className="flex flex-col items-end gap-1.5">
                    <button onClick={() => redeem(p.play_id)} data-testid={`perk-redeem-${p.play_id}`}
                            className="text-[11px] font-black px-3 h-9 rounded-full bg-emerald-500/20 text-emerald-300">
                      Mark redeemed
                    </button>
                    <div className="flex gap-1.5">
                      <button onClick={() => share(p)} data-testid={`perk-share-${p.play_id}`}
                              className="text-[11px] font-bold px-3 h-8 rounded-full bg-white/10 text-white inline-flex items-center gap-1.5">
                        <Share2 size={12} /> Share
                      </button>
                      <button onClick={() => openGift(p)} data-testid={`perk-gift-${p.play_id}`}
                              className="text-[11px] font-bold px-3 h-8 rounded-full bg-pink-500/20 text-pink-200 inline-flex items-center gap-1.5">
                        <Gift size={12} /> Gift
                      </button>
                    </div>
                  </div>
                )}
              </div>
              );
            })}
          </div>
        )}
      </div>

      {giftFor && (
        <div className="fixed inset-0 z-[100] grid place-items-center p-4 bg-black/70 backdrop-blur-sm"
             onClick={() => setGiftFor(null)} data-testid="perk-gift-modal">
          <div className="w-full max-w-sm rounded-3xl border border-white/10 p-5 max-h-[80vh] overflow-auto"
               style={{ background: "linear-gradient(135deg,#160f2e,#241041)" }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 font-black"><Gift size={18} /> Gift “{giftFor.label}”</div>
              <button onClick={() => setGiftFor(null)} className="text-slate-400" data-testid="gift-close"><X size={20} /></button>
            </div>
            <p className="text-[12px] text-slate-300/70 mb-3">Pick a friend — the perk leaves your wallet and lands in theirs.</p>
            {friends.length === 0 ? (
              <div className="text-sm text-slate-400 text-center py-6" data-testid="gift-no-friends">Add friends first to gift a perk.</div>
            ) : (
              <div className="space-y-2">
                {friends.map((f) => (
                  <button key={f.user_id} onClick={() => doGift(f.user_id)} data-testid={`gift-friend-${f.user_id}`}
                          className="w-full flex items-center gap-3 rounded-xl bg-white/[0.04] border border-white/10 p-2.5 text-left hover:border-pink-400/40">
                    <span className="w-9 h-9 rounded-full bg-purple-500/30 grid place-items-center overflow-hidden text-sm font-black">
                      {f.avatar_url ? <img src={f.avatar_url} alt="" className="w-full h-full object-cover" /> : (f.name || "?").slice(0, 1)}
                    </span>
                    <span className="font-bold truncate">{f.name || "Listener"}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
