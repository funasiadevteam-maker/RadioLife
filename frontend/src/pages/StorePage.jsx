// P1 — branded storefront landing at /store/:id.
// A sponsor-branded page (e.g. /store/adv_fpk) that shows the advertiser's
// live coupon games with real-time "coupons left today" scarcity + a play CTA.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Gamepad2, ArrowRight, Ticket, ChevronLeft, Store as StoreIcon, BellRing, Check,
} from "lucide-react";
import { CouponScarcityStrip } from "@/components/CouponScarcityStrip";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const GAME_ICON = {
  spin_wheel: "🎡", scratch_card: "🎟️", quiz: "❓",
  mystery_box: "🎁", memory_match: "🧠", word_puzzle: "🔤", pick_a_card: "🃏",
};

export default function StorePage() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [waitlisted, setWaitlisted] = useState(new Set());
  const [joining, setJoining] = useState(null);

  useEffect(() => {
    setData(null); setError(null);
    axios.get(`${API}/store/${id}`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail?.code || e?.response?.data?.detail || e.message));
    axios.get(`${API}/me/waitlist`)
      .then((r) => setWaitlisted(new Set(r.data.campaign_ids || [])))
      .catch(() => {});
  }, [id]);

  const joinWaitlist = async (campaignId) => {
    setJoining(campaignId);
    try {
      await axios.post(`${API}/store/${id}/waitlist`, { campaign_id: campaignId });
      setWaitlisted((s) => new Set(s).add(campaignId));
    } catch (e) { /* ignore */ } finally { setJoining(null); }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 text-white grid place-items-center px-6" data-testid="store-error">
        <div className="text-center">
          <StoreIcon className="w-12 h-12 mx-auto opacity-40" />
          <div className="mt-3 font-black text-lg">Store not found</div>
          <div className="text-sm text-slate-400 mt-1">{String(error)}</div>
          <Link to="/play" className="inline-flex items-center gap-1 mt-5 px-5 py-2.5 rounded-full bg-white/10 hover:bg-white/20 text-sm font-black">
            Browse games <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="min-h-screen bg-slate-950 text-white grid place-items-center" data-testid="store-loading">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }

  const { brand, games, coupons_left_today, resets_at } = data;
  const accent = brand.primary || "#0aa54b";
  const restockLabel = resets_at
    ? new Date(resets_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : null;

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="store-page">
      {/* Branded hero */}
      <section
        className="relative overflow-hidden border-b border-white/10"
        style={{ background: `linear-gradient(135deg, ${accent}22, ${brand.secondary || "#0a0a0b"} 70%)` }}
        data-testid="store-hero"
      >
        <div className="max-w-6xl mx-auto px-4 py-12">
          <Link to="/play" className="inline-flex items-center gap-1 text-xs text-white/60 hover:text-white mb-6" data-testid="store-back">
            <ChevronLeft className="w-4 h-4" /> All games
          </Link>
          <div className="flex items-center gap-4">
            {brand.logo_url ? (
              <img src={brand.logo_url} alt={brand.name}
                   className="w-16 h-16 rounded-2xl object-cover bg-white/10 border border-white/20" />
            ) : (
              <div className="w-16 h-16 rounded-2xl grid place-items-center text-2xl font-black"
                   style={{ background: accent, color: "#0a0a0b" }}>
                {String(brand.name || "?").slice(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest" style={{ color: accent }}>
                Official Store
              </div>
              <h1 className="text-3xl md:text-4xl font-black tracking-tight" data-testid="store-name">
                {brand.name}
              </h1>
            </div>
          </div>
          <p className="mt-4 max-w-xl text-sm text-white/75">{brand.tagline}</p>
          <div className="mt-5">
            <CouponScarcityStrip remaining={coupons_left_today} resetsAt={resets_at}
                                 accent={accent} testId="store-scarcity" />
          </div>
        </div>
      </section>

      {/* Games */}
      <div className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-white/50 mb-5">
          <Gamepad2 className="w-4 h-4" /> Play &amp; win coupons
        </div>
        {games.length === 0 ? (
          <div className="text-center py-16 text-white/50" data-testid="store-empty">
            <Ticket className="w-12 h-12 mx-auto opacity-40" />
            <div className="mt-3 font-bold">No live games right now.</div>
            <div className="text-xs mt-1">Check back soon.</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="store-games">
            {games.map((g) => {
              const soldOut = g.is_coupon_game && g.remaining_today !== null && g.remaining_today <= 0;
              const onWaitlist = waitlisted.has(g.campaign_id);
              const inner = (
                <>
                  <div className="text-4xl mb-3">{GAME_ICON[g.game_type] || "🎮"}</div>
                  <div className="font-black text-lg leading-tight">{g.title}</div>
                  <div className="text-xs text-white/50 mt-1 line-clamp-2 flex-1">{g.description}</div>
                  <div className="mt-4 flex items-center justify-between gap-2">
                    {g.is_coupon_game ? (
                      g.remaining_today === null ? (
                        <span className="text-[11px] font-black" style={{ color: accent }}>Unlimited today</span>
                      ) : (
                        <span className={`text-[11px] font-black ${soldOut ? "text-slate-500" : ""}`}
                              style={soldOut ? {} : { color: accent }}
                              data-testid={`store-game-${g.campaign_id}-left`}>
                          {soldOut ? "Sold out today" : `${g.remaining_today.toLocaleString()} left today`}
                        </span>
                      )
                    ) : <span className="text-[11px] text-white/40">BigPoints</span>}
                    {soldOut ? (
                      onWaitlist ? (
                        <span className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-emerald-500/15 text-emerald-400"
                              data-testid={`store-game-${g.campaign_id}-waitlisted`}>
                          <Check className="w-3.5 h-3.5" /> On waitlist
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => joinWaitlist(g.campaign_id)}
                          disabled={joining === g.campaign_id}
                          data-testid={`store-game-${g.campaign_id}-remindme`}
                          className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 transition">
                          {joining === g.campaign_id
                            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            : <BellRing className="w-3.5 h-3.5" />} Remind me
                        </button>
                      )
                    ) : (
                      <span className="inline-flex items-center gap-1 text-sm font-black px-3 py-1.5 rounded-full transition"
                            style={{ background: accent, color: "#0a0a0b" }}>
                        Play <ArrowRight className="w-3.5 h-3.5" />
                      </span>
                    )}
                  </div>
                  {soldOut && restockLabel && (
                    <div className="mt-2 text-[11px] text-white/50 flex items-center gap-1"
                         data-testid={`store-game-${g.campaign_id}-restock`}>
                      🔔 Fresh coupons drop at {restockLabel}
                    </div>
                  )}
                </>
              );
              const cardCls = "group relative rounded-2xl overflow-hidden bg-slate-900/70 border border-white/10 hover:border-white/25 transition p-5 flex flex-col";
              return soldOut ? (
                <div key={g.campaign_id} data-testid={`store-game-${g.campaign_id}`} className={cardCls}>
                  {inner}
                </div>
              ) : (
                <Link key={g.campaign_id} to={g.play_route}
                      data-testid={`store-game-${g.campaign_id}`} className={cardCls}>
                  {inner}
                </Link>
              );
            })}
          </div>
        )}

        <div className="mt-10 text-center">
          <Link to="/offers?tab=mine" data-testid="store-view-coupons"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-white/10 hover:bg-white/20 text-sm font-black">
            <Ticket className="w-4 h-4" /> View my coupons <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}
