// Phase MER.3 — Consumer wallet v2 (coupons + gift cards + prepaid meals + points).
// Public route: /wallet-v2 (kept separate from legacy /wallet).
import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { CreditCard, UtensilsCrossed, Ticket, Coins, Loader2,
                  Copy, Sparkles, ArrowLeft, X } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
// Phase AD.11 — wallet banner slot.
import BannerZoneSlot from "@/components/BannerZoneSlot";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FMT = (n, ccy = "AED") => `${(Number(n || 0) / 100).toFixed(2)} ${ccy}`;

export default function WalletV2() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();

  const [tab, setTab] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (authLoading) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/wallet/me`,
                                                                            { withCredentials: true });
        setData(data);
      } catch (e) {
        if (e?.response?.status === 401) toast.error("Please sign in to view your wallet");
        else toast.error(`Load failed: ${e.message}`);
      } finally { setLoading(false); }
    })();
  }, [authLoading]);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (authLoading || loading) {
    return <div className={`${bgClass} flex items-center justify-center`}
                          data-testid="wallet-v2-loading">
      <Loader2 className="animate-spin" size={30}/>
    </div>;
  }
  if (!user) {
    return (
      <div className={`${bgClass} flex items-center justify-center p-6`}
                data-testid="wallet-v2-anon">
        <div className={`max-w-sm rounded-3xl p-6 text-center ${
          light ? "bg-white border border-slate-100 shadow-sm"
                  : "bg-slate-900 border border-slate-800"}`}>
          <Coins className="mx-auto mb-2" size={30}/>
          <h1 className={`text-2xl font-black ${
            light ? "text-slate-900" : "text-white"}`}>Sign in to see your wallet</h1>
          <Link to="/login?next=/wallet-v2"
                      data-testid="wallet-v2-login-link"
                      className="mt-4 inline-block h-11 rounded-full px-6 text-sm font-black text-white leading-[44px]"
                      style={{background:"linear-gradient(135deg,#a855f7,#ec4899)"}}>
            Sign in
          </Link>
        </div>
      </div>
    );
  }

  const counts = data?.counts || {};
  const cardClass = light
    ? "bg-white border border-slate-100 shadow-sm rounded-3xl"
    : "bg-slate-900 border border-slate-800 rounded-3xl";

  return (
    <div className={`${bgClass} p-4 sm:p-8`} data-testid="wallet-v2-page">
      <div className="max-w-6xl xl:max-w-7xl mx-auto">
        <div className="flex items-center gap-2 mb-4">
          <Link to="/" className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            <ArrowLeft className="inline" size={12}/> Home
          </Link>
        </div>

        <div className="flex items-end justify-between mb-6 flex-wrap gap-4">
          <div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"}`}>Wallet</div>
            <h1 className={`text-4xl font-black tracking-tight ${
              light ? "text-slate-900" : "text-white"}`}>Your BigFM Wallet</h1>
          </div>
          <div className={`rounded-2xl px-5 py-3 ${
            light ? "bg-purple-600 text-white" : "bg-cyan-500 text-slate-950"}`}
                data-testid="wallet-v2-points-hero">
            <div className="text-[10px] font-bold uppercase tracking-widest opacity-80">Points</div>
            <div className="text-3xl font-black tabular-nums">
              {data?.points_balance ?? 0}
            </div>
            <div className="text-[10px] mt-1 opacity-80">
              100 points → 1 AED at checkout
            </div>
          </div>
        </div>

        {/* Tab strip */}
        <div className={`flex gap-2 mb-6 overflow-x-auto pb-1`}
              data-testid="wallet-v2-tabs">
          {[
            {id:"all",label:"All",n:(counts.coupons||0)+(counts.gift_cards||0)+(counts.prepaid_meals||0)},
            {id:"coupons",label:"Coupons",n:counts.coupons||0},
            {id:"gift_cards",label:"Gift Cards",n:counts.gift_cards||0},
            {id:"prepaid_meals",label:"Meal Packs",n:counts.prepaid_meals||0},
          ].map(t => (
            <button key={t.id} type="button" onClick={() => setTab(t.id)}
                          data-testid={`wallet-v2-tab-${t.id}`}
                          data-active={tab === t.id}
                          className={`h-10 rounded-full px-4 text-xs font-black whitespace-nowrap ${
                            tab === t.id
                              ? (light ? "bg-slate-900 text-white"
                                            : "bg-white text-slate-950")
                              : (light ? "bg-slate-100 text-slate-700"
                                            : "bg-slate-900 text-slate-300 border border-slate-800")}`}>
              {t.label} · {t.n}
            </button>
          ))}
        </div>

        {/* Phase AD.11 — wallet banner slot. */}
        <BannerZoneSlot zone="wallet" />

        {(tab === "all" || tab === "coupons") && (data?.coupons?.length > 0) && (
          <Section title="Coupons" light={light} testid="wallet-v2-section-coupons">
            {(data?.coupons || []).map(c => (
              <CouponCard key={c.coupon_id} c={c} light={light}
                                        onClick={() => setDetail({type:"coupon", data:c})}/>
            ))}
          </Section>
        )}
        {(tab === "all" || tab === "gift_cards") && (data?.gift_cards?.length > 0) && (
          <Section title="Gift Cards" light={light} testid="wallet-v2-section-giftcards">
            {(data?.gift_cards || []).map(g => (
              <GiftCard key={g.gift_card_id} g={g} light={light}
                                onClick={() => setDetail({type:"gift_card", data:g})}/>
            ))}
          </Section>
        )}
        {(tab === "all" || tab === "prepaid_meals") && (data?.prepaid_meals?.length > 0) && (
          <Section title="Meal Packs" light={light} testid="wallet-v2-section-meals">
            {(data?.prepaid_meals || []).map(m => (
              <MealCard key={m.meal_pack_id} m={m} light={light}
                                onClick={() => setDetail({type:"prepaid_meal", data:m})}/>
            ))}
          </Section>
        )}
        {(counts.coupons + counts.gift_cards + counts.prepaid_meals === 0) && (
          <div className={`${cardClass} p-10 text-center`}
                data-testid="wallet-v2-empty">
            <Sparkles className="mx-auto mb-2" size={30}/>
            <h3 className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"}`}>Your wallet is empty</h3>
            <p className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>
              Save coupons or buy gift cards from your favourite merchants.
            </p>
          </div>
        )}
      </div>

      {detail && (
        <DetailModal light={light} detail={detail}
                                onClose={() => setDetail(null)}/>
      )}
    </div>
  );
}


function Section({ title, light, testid, children }) {
  return (
    <div className="mb-6" data-testid={testid}>
      <h2 className={`text-lg font-black mb-3 ${
        light ? "text-slate-900" : "text-white"}`}>{title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {children}
      </div>
    </div>
  );
}

function CouponCard({ c, light, onClick }) {
  return (
    <button type="button" onClick={onClick}
                  data-testid={`wallet-v2-coupon-${c.coupon_id}`}
                  className={`text-left rounded-3xl p-5 transition-transform hover:scale-[1.01] ${
                    light ? "bg-white border border-slate-100 shadow-sm"
                            : "bg-slate-900 border border-slate-800"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-emerald-600" : "text-emerald-400"}`}>Coupon</div>
          <h3 className={`mt-1 text-base font-black truncate ${
            light ? "text-slate-900" : "text-white"}`}>
            {c.offer_title || "Coupon"}
          </h3>
          <div className={`text-xs mt-1 ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            {c.business_name || "—"}
          </div>
        </div>
        <div className={`text-2xl font-black ${
          light ? "text-emerald-600" : "text-emerald-400"}`}>
          {c.offer_discount_percent ? `${c.offer_discount_percent}%` : ""}
        </div>
      </div>
      <div className={`mt-3 font-mono text-xs ${
        light ? "text-slate-600" : "text-slate-400"}`}>
        {c.code || c.coupon_id}
      </div>
    </button>
  );
}

function GiftCard({ g, light, onClick }) {
  const pct = g.initial_balance_cents
    ? Math.round(100 * g.current_balance_cents / g.initial_balance_cents) : 0;
  const depleted = g.status === "depleted" || g.current_balance_cents <= 0;
  return (
    <button type="button" onClick={onClick}
                  data-testid={`wallet-v2-giftcard-${g.gift_card_id}`}
                  className={`text-left rounded-3xl p-5 transition-transform hover:scale-[1.01] ${
                    depleted ? "opacity-50" : ""} ${
                    light ? "bg-white border border-slate-100 shadow-sm"
                            : "bg-slate-900 border border-slate-800"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-purple-600" : "text-cyan-400"}`}>
            <CreditCard className="inline mr-1" size={11}/>Gift Card
          </div>
          <h3 className={`mt-1 text-base font-black truncate ${
            light ? "text-slate-900" : "text-white"}`}>
            {g.merchant_name || "—"}
          </h3>
        </div>
        <div className="text-right">
          <div className={`text-xl font-black ${
            light ? "text-slate-900" : "text-white"}`}>
            {FMT(g.current_balance_cents, g.currency)}
          </div>
          <div className={`text-[10px] ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            of {FMT(g.initial_balance_cents, g.currency)}
          </div>
        </div>
      </div>
      <div className={`mt-3 h-1.5 rounded-full overflow-hidden ${
        light ? "bg-slate-100" : "bg-slate-800"}`}>
        <div className="h-full" style={{
          width: `${pct}%`,
          background: light ? "#a855f7" : "#00d4ff"
        }}/>
      </div>
      <div className={`mt-2 font-mono text-xs ${
        light ? "text-slate-600" : "text-slate-400"}`}>
        {g.code}
      </div>
    </button>
  );
}

function MealCard({ m, light, onClick }) {
  const depleted = m.status === "depleted" || m.remaining_meals <= 0;
  return (
    <button type="button" onClick={onClick}
                  data-testid={`wallet-v2-meal-${m.meal_pack_id}`}
                  className={`text-left rounded-3xl p-5 transition-transform hover:scale-[1.01] ${
                    depleted ? "opacity-50" : ""} ${
                    light ? "bg-white border border-slate-100 shadow-sm"
                            : "bg-slate-900 border border-slate-800"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-orange-600" : "text-amber-400"}`}>
            <UtensilsCrossed className="inline mr-1" size={11}/>Meal Pack
          </div>
          <h3 className={`mt-1 text-base font-black truncate ${
            light ? "text-slate-900" : "text-white"}`}>
            {m.sku_name || "Meal Pack"}
          </h3>
          <div className={`text-xs mt-1 ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            {m.merchant_name}
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-black ${
            light ? "text-slate-900" : "text-white"}`}>
            {m.remaining_meals}<span className={`text-lg font-bold ${
              light ? "text-slate-500" : "text-slate-500"}`}>/{m.total_meals}</span>
          </div>
          <div className={`text-[10px] ${
            light ? "text-slate-500" : "text-slate-500"}`}>meals left</div>
        </div>
      </div>
      <div className={`mt-3 font-mono text-xs ${
        light ? "text-slate-600" : "text-slate-400"}`}>
        {m.code}
      </div>
    </button>
  );
}


function DetailModal({ light, detail, onClose }) {
  const t = detail.type;
  const d = detail.data;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 p-0 sm:p-4"
              onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
                data-testid="wallet-v2-detail"
                className={`w-full sm:max-w-md sm:rounded-3xl rounded-t-3xl p-6 max-h-[95vh] overflow-y-auto ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex justify-between mb-4">
          <h2 className={`text-lg font-black ${
            light ? "text-slate-900" : "text-white"}`}>
            {t === "coupon" && "Coupon Details"}
            {t === "gift_card" && "Gift Card Details"}
            {t === "prepaid_meal" && "Meal Pack Details"}
          </h2>
          <button type="button" onClick={onClose}
                        className={light ? "text-slate-500" : "text-slate-500"}>
            <X size={22}/>
          </button>
        </div>

        <div className={`rounded-2xl p-6 text-center mb-4 ${
          light ? "bg-gradient-to-br from-purple-100 to-pink-100"
                  : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"}`}>
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-slate-600" : "text-slate-400"}`}>Show this at the counter</div>
          <div className={`mt-3 font-mono text-3xl font-black tabular-nums ${
            light ? "text-slate-900" : "text-white"}`}
                data-testid="wallet-v2-detail-code">
            {d.code || d.coupon_id}
          </div>
          <button type="button"
                        onClick={() => { navigator.clipboard.writeText(d.code || d.coupon_id);
                                                        toast.success("Copied to clipboard"); }}
                        data-testid="wallet-v2-detail-copy"
                        className={`mt-4 inline-flex items-center gap-1 h-9 rounded-full px-4 text-xs font-bold ${
                          light ? "bg-slate-900 text-white"
                                  : "bg-white text-slate-950"}`}>
            <Copy size={12}/> Copy code
          </button>
        </div>

        {t === "coupon" && (
          <div className="space-y-1 text-sm">
            <Row light={light} k="Offer" v={d.offer_title}/>
            <Row light={light} k="Discount" v={`${d.offer_discount_percent || 0}%`}/>
            <Row light={light} k="Merchant" v={d.business_name}/>
          </div>
        )}
        {t === "gift_card" && (
          <div className="space-y-1 text-sm">
            <Row light={light} k="Balance" v={FMT(d.current_balance_cents, d.currency)}/>
            <Row light={light} k="Initial" v={FMT(d.initial_balance_cents, d.currency)}/>
            <Row light={light} k="Merchant" v={d.merchant_name}/>
            <Row light={light} k="Status" v={d.status}/>
          </div>
        )}
        {t === "prepaid_meal" && (
          <div className="space-y-1 text-sm">
            <Row light={light} k="Remaining" v={`${d.remaining_meals} of ${d.total_meals} meals`}/>
            <Row light={light} k="Per meal" v={FMT(d.per_meal_value_cents, "AED")}/>
            <Row light={light} k="Merchant" v={d.merchant_name}/>
            <Row light={light} k="Status" v={d.status}/>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ light, k, v }) {
  return (
    <div className="flex justify-between py-1.5 text-sm border-b border-transparent">
      <span className={light ? "text-slate-500" : "text-slate-500"}>{k}</span>
      <span className={`font-semibold ${light ? "text-slate-900" : "text-white"}`}>{v}</span>
    </div>
  );
}
