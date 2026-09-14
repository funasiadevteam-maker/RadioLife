// Phase AD.4 — Customer-facing offers surface.
// Route: /offers  (both design variants)
// Lists live coupon campaigns filtered by user market.  Tap-to-save →
// coupon lands in wallet, advertiser billed.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Ticket, Store, MapPin, Loader2, Check, X, Zap, ArrowRight, Sparkles,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useGeoStore } from "@/store/useGeoStore";
import SafeImage from "@/components/SafeImage";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function CouponOffers() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user } = useAuth();
  const market = useGeoStore((s) => s.market);
  const country = useGeoStore((s) => s.country);
  const cityName = useGeoStore((s) => s.city);
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [saved, setSaved] = useState({});   // {campaign_id: {ok, coupon_id, short_code} }
  const [toast, setToast] = useState(null);

  // P1 — "My Coupons" tab (owned coupons unified across all engines).
  const initialTab = new URLSearchParams(window.location.search).get("tab") === "mine" ? "mine" : "deals";
  const [tab, setTab] = useState(initialTab);
  const [mine, setMine] = useState(null);
  const [mineErr, setMineErr] = useState(null);

  useEffect(() => {
    if (tab !== "mine" || mine !== null || !user) return;
    axios.get(`${API}/me/wallet-coupons`)
      .then((r) => setMine(r.data.items || []))
      .catch((e) => setMineErr(e?.response?.data?.detail?.code || e.message));
  }, [tab, mine, user]);

  const showToast = (kind, message) => {
    setToast({ kind, message });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    const params = new URLSearchParams();
    // Backend filters by ISO-2 country_code; geo store's `country` holds
    // that (e.g. "AE"). `market` is the city slug — we send the city
    // display too so future targeting refinements land automatically.
    const cc = (country || "").toUpperCase();
    if (cc) params.set("market", cc);
    if (cityName && cityName !== "Global") params.set("city", cityName);
    axios.get(`${API}/coupon-campaigns/live?${params}`)
      .then((r) => setItems(r.data.items || []))
      .catch((e) => setError(e?.response?.data?.detail?.code || e.message));
  }, [market, country, cityName]);

  async function save(id) {
    if (!user) {
      window.location.href = `/login?next=/offers`;
      return;
    }
    setSavingId(id);
    try {
      const { data } = await axios.post(`${API}/coupon-campaigns/${id}/save`);
      setSaved((s) => ({ ...s, [id]: data }));
      showToast(data.already_saved ? "info" : "success",
        data.already_saved ? "Already in your wallet."
                                                : `Saved to wallet — code ${data.short_code}`);
    } catch (err) {
      const detail = err?.response?.data?.detail || {};
      const code = detail.reason || detail.code || err.message;
      showToast("error", `Save failed: ${code}`);
    } finally { setSavingId(null); }
  }

  const bg = light
    ? "bg-gradient-to-b from-white via-fuchsia-50/40 to-white text-slate-900"
    : "bg-slate-950 text-white";
  const cardCls = light
    ? "bg-white border border-slate-200 shadow-md hover:shadow-xl"
    : "bg-slate-900/60 border border-slate-800 hover:border-amber-500/50 hover:shadow-xl hover:shadow-amber-500/10";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`${bg} min-h-screen`} data-testid="offers-page">
      {/* Hero strip */}
      <section className={`${light
                                          ? "bg-gradient-to-r from-fuchsia-500 to-purple-600 text-white"
                                          : "bg-gradient-to-r from-slate-900 to-amber-950/40 border-b border-amber-500/20"} py-10`}
                        data-testid="offers-hero">
        <div className="max-w-7xl xl:max-w-[1400px] mx-auto px-4">
          <div className={`inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest ${light ? "text-amber-200" : "text-amber-400"}`}>
            <Sparkles className="w-3 h-3" /> Live deals in your city
          </div>
          <h1 className="mt-2 text-3xl md:text-4xl xl:text-5xl font-black tracking-tight" data-testid="offers-title">
            Save deals · Redeem in-store
          </h1>
          <p className={`mt-2 text-sm ${light ? "text-white/85" : "text-slate-300"}`}>
            Tap Save to add the coupon to your wallet.  Show the QR at checkout.
          </p>
          {/* P1 — Deals / My Coupons tabs */}
          <div className="mt-5 inline-flex rounded-full p-1 bg-black/20 border border-white/15" data-testid="offers-tabs">
            {[["deals", "Deals"], ["mine", "My Coupons"]].map(([key, label]) => (
              <button key={key} onClick={() => setTab(key)}
                      data-testid={`offers-tab-${key}`}
                      className={`px-5 py-1.5 rounded-full text-xs font-black uppercase tracking-wider transition ${
                        tab === key ? "bg-white text-slate-900" : "text-white/80 hover:text-white"}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="mt-4">
            <Link to="/store/adv_fpk" data-testid="offers-fpk-store"
                      className="inline-flex items-center gap-1.5 text-xs font-black underline decoration-dotted underline-offset-4 opacity-90 hover:opacity-100">
              <Sparkles className="w-3.5 h-3.5" /> Visit the FPK Store →
            </Link>
          </div>
        </div>
      </section>

      <div className="max-w-7xl xl:max-w-[1400px] mx-auto px-4 py-8">
        {tab === "mine" ? (
          <MyCouponsView light={light} mine={mine} mineErr={mineErr} user={user} />
        ) : (<>
        {items === null && !error ? (
          <div className="flex items-center gap-2 py-8"><Loader2 className="w-4 h-4 animate-spin" /> Loading offers…</div>
        ) : error ? (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm"
                      data-testid="offers-error">
            {String(error)}
          </div>
        ) : items.length === 0 ? (
          <div className={`text-center py-16 ${muted}`} data-testid="offers-empty">
            <Ticket className="w-12 h-12 mx-auto opacity-40" />
            <div className="mt-3 font-bold">No live offers in your area right now.</div>
            <div className="text-xs mt-1">Check back soon — advertisers add new coupons daily.</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
                      data-testid="offers-grid">
            {items.map((c) => {
              const s = saved[c.campaign_id];
              const isSaving = savingId === c.campaign_id;
              return (
                <div key={c.campaign_id}
                              className={`${cardCls} rounded-2xl overflow-hidden transition transform hover:-translate-y-0.5`}
                              data-testid={`offer-card-${c.campaign_id}`}>
                  <div className={`aspect-[16/9] bg-gradient-to-br ${
                                                    light ? "from-fuchsia-400 to-purple-500"
                                                                  : "from-amber-600/30 to-purple-600/20"}
                                                    relative overflow-hidden`}>
                    {c.hero_image_url && (
                      <img src={c.hero_image_url} alt=""
                                className="w-full h-full object-cover" />
                    )}
                    <div className="absolute top-3 right-3">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-[10px] uppercase font-black tracking-wider ${
                                                            light ? "bg-white text-purple-700"
                                                                          : "bg-amber-500 text-slate-900"}`}>
                        {c.inventory_remaining} left
                      </span>
                    </div>
                    {c.logo_url && (
                      <div className="absolute bottom-3 left-3">
                        <SafeImage src={c.logo_url} alt=""
                                                  fallbackKind="business"
                                                  fallbackText={c.brand_name || c.title || ""}
                                                  className="w-12 h-12 rounded-xl bg-white/10 border border-white/30 object-cover" />
                      </div>
                    )}
                  </div>
                  <div className="p-4">
                    <div className={`text-xs font-bold uppercase tracking-widest ${
                                                        light ? "text-purple-600" : "text-amber-400"}`}>
                      {(c.category_tags || []).slice(0, 2).join(" · ") || "Deal"}
                    </div>
                    <div className="mt-1 text-lg font-black leading-tight" data-testid={`offer-card-${c.campaign_id}-title`}>
                      {c.title}
                    </div>
                    <div className={`text-xs mt-1 line-clamp-2 ${muted}`}>
                      {c.description || " "}
                    </div>
                    {c.sponsoring_merchant && (
                      <div className={`mt-2 flex items-center gap-1 text-[11px] ${muted}`}>
                        <Store className="w-3 h-3" /> {c.sponsoring_merchant.name}
                        {c.sponsoring_merchant.city && (
                          <><span className="opacity-50">·</span><MapPin className="w-3 h-3" /> {c.sponsoring_merchant.city}</>
                        )}
                      </div>
                    )}
                    <div className={`mt-3 pt-3 border-t ${light ? "border-slate-100" : "border-slate-800"} flex items-center justify-between`}>
                      <div>
                        <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>Worth</div>
                        <div className={`text-lg font-black ${light ? "text-emerald-600" : "text-emerald-400"}`}>
                          {(c.retail_value_cents/100).toFixed(2)} <span className="text-xs">{c.value_currency}</span>
                        </div>
                      </div>
                      {s?.ok ? (
                        <div className="inline-flex flex-col items-end">
                          <span className="inline-flex items-center gap-1 text-xs font-black text-emerald-500"
                                        data-testid={`offer-card-${c.campaign_id}-saved`}>
                            <Check className="w-4 h-4" /> {s.already_saved ? "In wallet" : "Saved!"}
                          </span>
                          <div className={`font-mono text-[10px] mt-0.5 ${muted}`}>{s.short_code}</div>
                        </div>
                      ) : (
                        <button onClick={() => save(c.campaign_id)}
                                        disabled={isSaving}
                                        data-testid={`offer-card-${c.campaign_id}-save`}
                                        className={`inline-flex items-center gap-1 px-4 py-2 rounded-full text-sm font-black transition ${
                                                          light ? "bg-purple-600 text-white hover:bg-purple-500 shadow-lg shadow-purple-500/25"
                                                                        : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-lg shadow-amber-500/25"}
                                                          disabled:opacity-50`}>
                          {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                          Save
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-8 text-center">
          <Link to="/wallet"
                    data-testid="offers-view-wallet-cta"
                    className={`inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-black ${
                                        light ? "bg-slate-100 hover:bg-slate-200 text-slate-800"
                                                      : "bg-slate-800 hover:bg-slate-700 text-white"}`}>
            View my wallet <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        </>)}
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="offers-toast">
          <div className={`${toast.kind === "error"
                                                ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                                : toast.kind === "info"
                                                    ? "bg-blue-500/15 border border-blue-500/40 text-blue-300"
                                                    : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>
            {toast.message}
          </div>
        </div>
      )}
    </div>
  );
}


// P1 — "My Coupons": the user's owned coupons unified across engines.
function MyCouponsView({ light, mine, mineErr, user }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  const cardCls = light
    ? "bg-white border border-slate-200 shadow-sm"
    : "bg-slate-900/60 border border-slate-800";
  const [copied, setCopied] = useState(null);

  const copy = (code) => {
    if (!code) return;
    try { navigator.clipboard.writeText(code); } catch {}
    setCopied(code);
    setTimeout(() => setCopied(null), 1800);
  };

  if (!user) {
    return (
      <div className={`text-center py-16 ${muted}`} data-testid="mycoupons-signin">
        <Ticket className="w-12 h-12 mx-auto opacity-40" />
        <div className="mt-3 font-bold">Sign in to see your coupons.</div>
        <div className="text-xs mt-1">Your saved deals and game wins live here.</div>
        <a href="/login?next=/offers?tab=mine" data-testid="mycoupons-signin-cta"
           className={`inline-flex items-center gap-2 mt-5 px-5 py-2.5 rounded-full text-sm font-black ${
             light ? "bg-purple-600 text-white" : "bg-amber-500 text-slate-900"}`}>
          Sign in <ArrowRight className="w-4 h-4" />
        </a>
      </div>
    );
  }
  if (mineErr) {
    return (
      <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm" data-testid="mycoupons-error">
        {String(mineErr)}
      </div>
    );
  }
  if (mine === null) {
    return <div className="flex items-center gap-2 py-8" data-testid="mycoupons-loading"><Loader2 className="w-4 h-4 animate-spin" /> Loading your coupons…</div>;
  }
  if (mine.length === 0) {
    return (
      <div className={`text-center py-16 ${muted}`} data-testid="mycoupons-empty">
        <Ticket className="w-12 h-12 mx-auto opacity-40" />
        <div className="mt-3 font-bold">No coupons yet.</div>
        <div className="text-xs mt-1">Save a deal or play a sponsored game to earn coupons.</div>
        <Link to="/play" data-testid="mycoupons-play-cta"
              className={`inline-flex items-center gap-2 mt-5 px-5 py-2.5 rounded-full text-sm font-black ${
                light ? "bg-purple-600 text-white" : "bg-amber-500 text-slate-900"}`}>
          <Zap className="w-4 h-4" /> Play &amp; win
        </Link>
      </div>
    );
  }

  const SOURCE_LABEL = { game_win: "Game win", saved: "Saved", wallet: "Wallet" };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="mycoupons-grid">
      {mine.map((c) => {
        const redeemed = c.status === "redeemed";
        return (
          <div key={c.id} className={`${cardCls} rounded-2xl p-4 flex flex-col`} data-testid={`mycoupon-${c.id}`}>
            <div className="flex items-center justify-between">
              <span className={`text-[10px] font-black uppercase tracking-widest ${light ? "text-purple-600" : "text-amber-400"}`}>
                {SOURCE_LABEL[c.source] || "Coupon"}
              </span>
              <span className={`text-[10px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full ${
                redeemed ? "bg-slate-500/20 text-slate-400" : "bg-emerald-500/15 text-emerald-500"}`}
                data-testid={`mycoupon-${c.id}-status`}>
                {redeemed ? "Redeemed" : "Active"}
              </span>
            </div>
            <div className="mt-2 font-black text-lg leading-tight">{c.title}</div>
            {c.sponsor_name && <div className={`text-xs mt-0.5 ${muted}`}>{c.sponsor_name}</div>}
            {c.description && <div className={`text-xs mt-1 line-clamp-2 ${muted}`}>{c.description}</div>}
            <div className="flex-1" />
            {c.code && (
              <button onClick={() => copy(c.code)} disabled={redeemed}
                      data-testid={`mycoupon-${c.id}-code`}
                      className={`mt-3 flex items-center justify-between gap-2 px-3 py-2 rounded-lg font-mono text-sm border transition ${
                        light ? "bg-slate-50 border-slate-200 hover:bg-slate-100" : "bg-slate-950/60 border-slate-700 hover:border-slate-500"} ${redeemed ? "opacity-50" : ""}`}>
                <span className="truncate">{c.code}</span>
                {copied === c.code
                  ? <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                  : <span className="text-[10px] uppercase tracking-wider opacity-60 shrink-0">Copy</span>}
              </button>
            )}
            {c.expires_at && (
              <div className={`text-[11px] mt-2 ${muted}`}>
                Expires {new Date(c.expires_at).toLocaleDateString()}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
