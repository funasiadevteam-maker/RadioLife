// Merchant → Rail Sponsor. Bid to feature one of your live shows / upcoming
// events as the pinned card in the site-wide compact Right Rail. Exclusive
// auction: the highest active bid wins the single top slot. Real one-time
// Stripe checkout (test card 4242… in preview; live card once claimed).
import { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Radio, Megaphone, Loader2, X, Sparkles, Eye, MousePointerClick,
  TrendingUp, Clock, Calendar, Crown, ArrowUpCircle, BarChart3, ExternalLink,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const usd = (c) => `$${((c || 0) / 100).toFixed(0)}`;

const STATUS_TONE = {
  active: { bg: "bg-emerald-500/15", fg: "text-emerald-300", label: "Active" },
  pending_payment: { bg: "bg-amber-500/15", fg: "text-amber-300", label: "Unpaid" },
  expired: { bg: "bg-slate-500/15", fg: "text-slate-400", label: "Ended" },
  cancelled: { bg: "bg-rose-500/15", fg: "text-rose-300", label: "Cancelled" },
};

export default function MerchantRailSponsor() {
  const ctx = useMerchant();
  const merchant = ctx?.merchant;
  const merchantId = merchant?.merchant_id;
  const [tiers, setTiers] = useState([]);
  const [shows, setShows] = useState([]);
  const [items, setItems] = useState([]);
  const [topBid, setTopBid] = useState(0);
  const [loading, setLoading] = useState(true);
  const [picking, setPicking] = useState(null);   // show being sponsored
  const [raising, setRaising] = useState(null);    // item being raised
  const [tier, setTier] = useState(null);
  const [bid, setBid] = useState(0);               // dollars
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(null);
  const polls = useRef([]);

  const load = useCallback(async () => {
    if (!merchantId) return;
    try {
      const [t, s, l] = await Promise.all([
        axios.get(`${API}/social/rail/sponsor/tiers`, { withCredentials: true })
          .then((r) => r.data?.tiers || []).catch(() => []),
        axios.get(`${API}/social/rail/sponsor/eligible-shows`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data?.shows || []).catch(() => []),
        axios.get(`${API}/social/rail/sponsor/list`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data).catch(() => ({})),
      ]);
      setTiers(t); setShows(s);
      setItems(l?.sponsorships || []);
      setTopBid(l?.current_top_bid_cents || 0);
    } finally { setLoading(false); }
  }, [merchantId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => polls.current.forEach(clearInterval), []);

  const openSponsor = (show) => {
    const first = tiers[0];
    setTier(first?.id || "3d");
    setBid(Math.max((first?.amount_cents || 1900) / 100, (topBid || 0) / 100 + 1));
    setPicking(show);
  };

  const floorFor = (id) => (tiers.find((t) => t.id === id)?.amount_cents || 0) / 100;

  // Poll payment status in the background until the sponsorship activates.
  const pollUntilActive = (sid, sessionId, label) => {
    let ticks = 0;
    const iv = setInterval(async () => {
      ticks += 1;
      try {
        const { data } = await axios.get(`${API}/social/rail/sponsor/${sid}/status`,
          { params: { session_id: sessionId }, withCredentials: true });
        if (data.status === "active" && data.payment_status === "paid") {
          clearInterval(iv);
          toast.success(label || "Payment confirmed — you're featured!");
          load();
        }
      } catch (_) { /* keep polling */ }
      if (ticks > 80) clearInterval(iv); // ~4 min cap
    }, 3000);
    polls.current.push(iv);
  };

  const payAndFeature = async () => {
    if (!picking || !tier) return;
    const floor = floorFor(tier);
    if (bid < floor) { toast.error(`Minimum for this duration is $${floor}.`); return; }
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/social/rail/sponsor`,
        { merchant_id: merchantId, target_id: picking.id, tier, bid_cents: Math.round(bid * 100) },
        { withCredentials: true });
      const sid = data.sponsorship_id;
      const { data: co } = await axios.post(`${API}/social/rail/sponsor/${sid}/checkout`,
        { origin_url: window.location.origin }, { withCredentials: true });
      if (co.checkout_url) {
        window.open(co.checkout_url, "_blank", "noopener");
        pollUntilActive(sid, co.session_id, "Payment confirmed — your card is featured!");
        toast.message("Complete payment in the new tab", {
          description: "Use test card 4242 4242 4242 4242. This page updates automatically.",
        });
      }
      setPicking(null);
      await load();
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code === "not_your_business" ? "This isn't your business."
        : code === "stripe_unconfigured" ? "Payments aren't configured yet."
        : "Couldn't start checkout.");
    } finally { setBusy(false); }
  };

  const submitRaise = async () => {
    if (!raising) return;
    const cur = (raising.bid_cents || 0) / 100;
    if (bid <= cur) { toast.error(`Enter more than your current $${cur} bid.`); return; }
    setBusy(true);
    try {
      const { data: co } = await axios.post(`${API}/social/rail/sponsor/${raising.id}/raise`,
        { bid_cents: Math.round(bid * 100), origin_url: window.location.origin },
        { withCredentials: true });
      if (co.checkout_url) {
        window.open(co.checkout_url, "_blank", "noopener");
        pollUntilActive(raising.id, co.session_id, "Bid raised — you're now bidding higher!");
        toast.message("Pay the difference in the new tab", {
          description: `You're topping up by ${usd(co.delta_cents)}. Test card 4242…`,
        });
      }
      setRaising(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "bid_too_low"
        ? "Bid must be higher than the current one." : "Couldn't raise bid.");
    } finally { setBusy(false); }
  };

  const cancel = async (sid) => {
    try {
      await axios.post(`${API}/social/rail/sponsor/${sid}/cancel`, {}, { withCredentials: true });
      toast.success("Sponsorship cancelled.");
      setConfirmCancel(null);
      await load();
    } catch (_) { toast.error("Couldn't cancel."); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="merchant-rail-sponsor">
      <Toaster position="top-center" richColors />
      <div className="relative overflow-hidden border-b border-white/10"
        style={{ background: "linear-gradient(120deg,#0b0f1e 0%,#241041 60%,#3a1652 100%)" }}>
        <div className="absolute -top-16 -right-10 w-64 h-64 rounded-full blur-3xl opacity-30"
          style={{ background: "radial-gradient(circle,#f5c563,transparent 70%)" }} />
        <div className="relative px-6 lg:px-10 py-6">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-amber-300">
            <Megaphone size={12} /> Rail Sponsor
          </div>
          <h1 className="mt-1 text-2xl lg:text-3xl font-black">Bid to feature a show in the Right Rail</h1>
          <p className="mt-1 text-sm text-slate-300 max-w-xl">
            The highest active bid wins the single "Sponsored" slot at the top of
            the site-wide rail. Track impressions, clicks and CTR in real time.
          </p>
          <div className="mt-3 inline-flex items-center gap-2 text-[11px] font-bold px-3 py-1.5 rounded-full bg-amber-500/15 text-amber-200"
            data-testid="rail-sponsor-top-bid">
            <Crown size={13} /> Current top bid to beat: {usd(topBid)}
          </div>
        </div>
      </div>

      <div className="px-6 lg:px-10 py-8 max-w-5xl mx-auto space-y-10">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400">
            <Loader2 className="animate-spin mr-2" size={18} /> Loading…
          </div>
        ) : (
          <>
            <section data-testid="rail-sponsor-eligible">
              <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
                Your shows to feature
              </h2>
              {shows.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 text-center"
                  data-testid="rail-sponsor-empty-shows">
                  <Radio className="mx-auto mb-3 text-slate-500" size={26} />
                  <div className="font-bold">No live or upcoming shows yet</div>
                  <div className="text-sm text-slate-400 mt-1">
                    Start a live show or schedule an event, then feature it here.
                  </div>
                </div>
              ) : (
                <div className="grid sm:grid-cols-2 gap-4">
                  {shows.map((s) => (
                    <div key={s.id} data-testid={`rail-sponsor-show-${s.id}`}
                      className="rounded-2xl border border-white/10 bg-slate-900/60 overflow-hidden flex flex-col">
                      <div className="h-28 bg-white/5 relative">
                        {s.image && <img src={s.image} alt="" className="w-full h-full object-cover" />}
                        <span className={`absolute top-2 left-2 text-[9px] font-black tracking-widest px-2 py-0.5 rounded-full ${
                          s.kind === "live" ? "bg-red-500/80 text-white" : "bg-cyan-500/80 text-slate-950"}`}>
                          {s.kind === "live" ? "LIVE NOW" : "UPCOMING"}
                        </span>
                      </div>
                      <div className="p-4 flex-1 flex flex-col">
                        <div className="font-bold truncate">{s.title}</div>
                        <div className="text-xs text-slate-400 truncate">
                          {s.business_name || "Your show"}
                        </div>
                        <button type="button" data-testid={`rail-sponsor-feature-${s.id}`}
                          onClick={() => openSponsor(s)}
                          className="mt-3 h-10 rounded-xl font-black text-sm text-slate-950"
                          style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
                          Feature this
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section data-testid="rail-sponsor-list">
              <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
                Your sponsorships
              </h2>
              {items.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 text-center text-slate-400"
                  data-testid="rail-sponsor-empty-list">
                  No sponsorships yet. Feature a show above to get started.
                </div>
              ) : (
                <div className="space-y-3">
                  {items.map((it) => (
                    <SponsorRow key={it.id} it={it} topBid={topBid}
                      confirmCancel={confirmCancel} setConfirmCancel={setConfirmCancel}
                      onCancel={cancel}
                      onRaise={() => { setRaising(it); setBid((it.bid_cents || 0) / 100 + 1); }} />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {/* Bid + duration modal */}
      {picking && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
          onClick={() => !busy && setPicking(null)} data-testid="rail-sponsor-tier-modal">
          <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-white/10 p-5"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest">
                <Sparkles size={12} /> Feature "{picking.title}"
              </div>
              <button type="button" onClick={() => !busy && setPicking(null)}
                data-testid="rail-sponsor-modal-close" className="text-slate-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="text-xs text-slate-400 mb-3">Choose a duration, then set your bid.</div>
            <div className="grid grid-cols-3 gap-2 mb-4">
              {tiers.map((t) => (
                <button key={t.id} type="button" disabled={busy}
                  data-testid={`rail-sponsor-tier-${t.id}`}
                  onClick={() => { setTier(t.id); if (bid < t.amount_cents / 100) setBid(t.amount_cents / 100); }}
                  className={`px-2 py-3 rounded-2xl border text-center transition ${
                    tier === t.id ? "border-amber-400 bg-amber-500/10" : "border-white/10 bg-slate-800/60"}`}>
                  <div className="font-black text-sm">{t.label}</div>
                  <div className="text-[11px] text-amber-300 font-bold mt-0.5">from {usd(t.amount_cents)}</div>
                </button>
              ))}
            </div>
            <label className="block text-[11px] font-bold uppercase tracking-widest text-slate-400 mb-1">
              Your bid (USD)
            </label>
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-800/60 px-3 h-12">
              <span className="text-slate-400 font-black">$</span>
              <input type="number" min={floorFor(tier)} step="1" value={bid}
                data-testid="rail-sponsor-bid-input"
                onChange={(e) => setBid(Number(e.target.value))}
                className="flex-1 bg-transparent outline-none font-black text-lg" />
            </div>
            <div className="mt-1.5 text-[11px] text-slate-400 flex items-center gap-1">
              <Crown size={12} className="text-amber-300" />
              Beat the current top bid ({usd(topBid)}) to win the slot now. Floor: ${floorFor(tier)}.
            </div>
            <button type="button" data-testid="rail-sponsor-pay-btn" disabled={busy}
              onClick={payAndFeature}
              className="mt-4 w-full h-12 rounded-2xl font-black text-slate-950 flex items-center justify-center gap-2 disabled:opacity-60"
              style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
              {busy ? <Loader2 className="animate-spin" size={18} /> : <ExternalLink size={16} />}
              Pay {usd(Math.round(bid * 100))} & feature
            </button>
            <div className="mt-3 text-[11px] text-slate-500 text-center">
              Opens Stripe Checkout · test card 4242 4242 4242 4242 in preview.
            </div>
          </div>
        </div>
      )}

      {/* Raise-bid modal */}
      {raising && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
          onClick={() => !busy && setRaising(null)} data-testid="rail-sponsor-raise-modal">
          <div className="w-full max-w-sm rounded-3xl bg-slate-900 border border-white/10 p-5"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest mb-1">
              <ArrowUpCircle size={12} /> Raise your bid
            </div>
            <div className="text-xs text-slate-400 mb-3">
              Current bid {usd(raising.bid_cents)} · top bid {usd(topBid)}. You'll only pay the difference.
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-800/60 px-3 h-12">
              <span className="text-slate-400 font-black">$</span>
              <input type="number" min={(raising.bid_cents || 0) / 100 + 1} step="1" value={bid}
                data-testid="rail-sponsor-raise-input"
                onChange={(e) => setBid(Number(e.target.value))}
                className="flex-1 bg-transparent outline-none font-black text-lg" />
            </div>
            <button type="button" data-testid="rail-sponsor-raise-submit" disabled={busy}
              onClick={submitRaise}
              className="mt-4 w-full h-12 rounded-2xl font-black text-slate-950 flex items-center justify-center gap-2 disabled:opacity-60"
              style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
              {busy ? <Loader2 className="animate-spin" size={18} /> : <ArrowUpCircle size={16} />}
              Pay difference & raise
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SponsorRow({ it, topBid, confirmCancel, setConfirmCancel, onCancel, onRaise }) {
  const tone = STATUS_TONE[it.status] || STATUS_TONE.expired;
  const [open, setOpen] = useState(false);
  const [series, setSeries] = useState(null);

  const toggleInsights = async () => {
    const next = !open;
    setOpen(next);
    if (next && series === null) {
      try {
        const { data } = await axios.get(`${API}/social/rail/sponsor/${it.id}/insights`,
          { params: { days: 14 }, withCredentials: true });
        setSeries((data?.series || []).map((d) => ({ ...d, day: d.date.slice(5) })));
      } catch (_) { setSeries([]); }
    }
  };

  return (
    <div data-testid={`rail-sponsor-item-${it.id}`}
      className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-14 h-14 rounded-xl overflow-hidden bg-white/5 shrink-0">
          {it.image && <img src={it.image} alt="" className="w-full h-full object-cover" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold truncate">{it.title}</span>
            <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${tone.bg} ${tone.fg}`}
              data-testid={`rail-sponsor-status-${it.id}`}>{tone.label}</span>
            {it.status === "active" && (it.featured ? (
              <span data-testid={`rail-sponsor-featured-${it.id}`}
                className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300">
                <Crown size={10} /> Featured · #1
              </span>
            ) : (
              <span data-testid={`rail-sponsor-outbid-${it.id}`}
                className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-slate-500/20 text-slate-300">
                Outbid · #{it.rank}
              </span>
            ))}
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-3 mt-0.5 flex-wrap">
            <span className="inline-flex items-center gap-1">
              <Clock size={11} /> {it.tier} · bid {usd(it.bid_cents)}
            </span>
            {it.ends_at && (
              <span className="inline-flex items-center gap-1">
                <Calendar size={11} /> ends {new Date(it.ends_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4" data-testid={`rail-sponsor-stats-${it.id}`}>
          <Stat icon={Eye} label="Views" value={it.impressions} />
          <Stat icon={MousePointerClick} label="Clicks" value={it.clicks} />
          <Stat icon={TrendingUp} label="CTR" value={`${it.ctr}%`} accent />
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" data-testid={`rail-sponsor-insights-toggle-${it.id}`}
            onClick={toggleInsights}
            className="inline-flex items-center gap-1 text-xs font-bold text-indigo-300 hover:text-indigo-200 px-3 h-9 rounded-lg border border-indigo-500/30">
            <BarChart3 size={13} /> {open ? "Hide" : "Trend"}
          </button>
          {it.status === "active" && !it.featured && (
            <button type="button" data-testid={`rail-sponsor-raise-${it.id}`} onClick={onRaise}
              className="inline-flex items-center gap-1 text-xs font-black text-amber-300 hover:text-amber-200 px-3 h-9 rounded-lg border border-amber-500/40">
              <ArrowUpCircle size={13} /> Raise bid
            </button>
          )}
          {it.status === "active" && (
            confirmCancel === it.id ? (
              <>
                <button type="button" data-testid={`rail-sponsor-cancel-confirm-${it.id}`}
                  onClick={() => onCancel(it.id)}
                  className="text-xs font-black text-white px-3 h-9 rounded-lg bg-rose-600 hover:bg-rose-500">
                  Confirm
                </button>
                <button type="button" data-testid={`rail-sponsor-cancel-abort-${it.id}`}
                  onClick={() => setConfirmCancel(null)}
                  className="text-xs font-bold text-slate-300 px-3 h-9 rounded-lg border border-white/10">
                  Keep
                </button>
              </>
            ) : (
              <button type="button" data-testid={`rail-sponsor-cancel-${it.id}`}
                onClick={() => setConfirmCancel(it.id)}
                className="text-xs font-bold text-rose-300 hover:text-rose-200 px-3 h-9 rounded-lg border border-rose-500/30">
                Cancel
              </button>
            )
          )}
        </div>
      </div>

      {open && (
        <div className="mt-4 pt-4 border-t border-white/10" data-testid={`rail-sponsor-chart-${it.id}`}>
          {series === null ? (
            <div className="flex items-center justify-center h-40 text-slate-400">
              <Loader2 className="animate-spin mr-2" size={16} /> Loading trend…
            </div>
          ) : series.length === 0 ? (
            <div className="h-24 flex items-center justify-center text-sm text-slate-500">
              No activity yet.
            </div>
          ) : (
            <div style={{ width: "100%", height: 180 }}>
              <ResponsiveContainer>
                <BarChart data={series} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey="day" tick={{ fill: "#94a3b8", fontSize: 10 }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, fontSize: 12 }}
                    labelStyle={{ color: "#e2e8f0" }} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="impressions" name="Views" fill="#a855f7" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="clicks" name="Clicks" fill="#f5c563" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, accent }) {
  return (
    <div className="text-center min-w-[52px]">
      <div className={`text-base font-black tabular-nums ${accent ? "text-amber-300" : "text-white"}`}>
        {value ?? 0}
      </div>
      <div className="text-[9px] uppercase tracking-widest text-slate-500 flex items-center justify-center gap-0.5">
        <Icon size={9} /> {label}
      </div>
    </div>
  );
}
