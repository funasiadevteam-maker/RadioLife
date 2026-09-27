// Merchant → Rail Sponsor. Fund an Ad-Wallet, then place STANDING BIDS to
// feature your live shows / upcoming events in the site-wide compact Right
// Rail. Each targeted area (Social / Shop / Listen) runs a DAILY SECOND-PRICE
// (Vickrey) auction: the highest bid wins the single slot and is charged only
// the clearing price (runner-up + $0.01, floored), debited from your wallet.
// Raise your bid to win a slot back; you're alerted the moment you're outbid.
import { useEffect, useState, useCallback, useRef } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Radio, Megaphone, Loader2, X, Sparkles, Eye, MousePointerClick,
  TrendingUp, Crown, ArrowUpCircle, BarChart3, Wallet,
  Plus, Bell, CircleDollarSign, Layers,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const usd = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const usd0 = (c) => `$${Math.round((c || 0) / 100)}`;

const AREA_TONE = {
  social: { bg: "bg-purple-500/15", fg: "text-purple-300", dot: "#a855f7" },
  shop: { bg: "bg-amber-500/15", fg: "text-amber-300", dot: "#f59e0b" },
  listen: { bg: "bg-cyan-500/15", fg: "text-cyan-300", dot: "#22d3ee" },
};
const AREA_LABEL = { social: "Social", shop: "Shop", listen: "Listen" };

const STATUS_TONE = {
  active: { bg: "bg-emerald-500/15", fg: "text-emerald-300", label: "Active" },
  ended: { bg: "bg-slate-500/15", fg: "text-slate-400", label: "Ended" },
};

export default function MerchantRailSponsor() {
  const ctx = useMerchant();
  const merchant = ctx?.merchant;
  const merchantId = merchant?.merchant_id;

  const [config, setConfig] = useState(null);
  const [shows, setShows] = useState([]);
  const [items, setItems] = useState([]);
  const [wallet, setWallet] = useState({ balance_cents: 0, txns: [] });
  const [floor, setFloor] = useState(500);
  const [alerts, setAlerts] = useState({ alerts: [], unread: 0 });
  const [loading, setLoading] = useState(true);

  const [picking, setPicking] = useState(null);      // show being featured
  const [raising, setRaising] = useState(null);       // item being raised
  const [funding, setFunding] = useState(false);      // top-up modal open
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(null);
  const polls = useRef([]);

  const loadCore = useCallback(async () => {
    if (!merchantId) return;
    try {
      const [cfg, s, l, w, a] = await Promise.all([
        axios.get(`${API}/social/rail/sponsor/config`, { withCredentials: true })
          .then((r) => r.data).catch(() => null),
        axios.get(`${API}/social/rail/sponsor/eligible-shows`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data?.shows || []).catch(() => []),
        axios.get(`${API}/social/rail/sponsor/list`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data).catch(() => ({})),
        axios.get(`${API}/social/rail/wallet`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data).catch(() => ({ balance_cents: 0, txns: [] })),
        axios.get(`${API}/social/rail/alerts`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data).catch(() => ({ alerts: [], unread: 0 })),
      ]);
      if (cfg) { setConfig(cfg); setFloor(cfg.daily_floor_cents || 500); }
      setShows(s);
      setItems(l?.sponsorships || []);
      setFloor(l?.daily_floor_cents || cfg?.daily_floor_cents || 500);
      setWallet(w || { balance_cents: 0, txns: [] });
      setAlerts(a || { alerts: [], unread: 0 });
    } finally { setLoading(false); }
  }, [merchantId]);

  useEffect(() => { loadCore(); }, [loadCore]);
  useEffect(() => () => polls.current.forEach(clearInterval), []);

  const pollTopup = useCallback((topupId, sessionId) => {
    let ticks = 0;
    const iv = setInterval(async () => {
      ticks += 1;
      try {
        const { data } = await axios.get(
          `${API}/social/rail/wallet/topup/${topupId}/status`,
          { params: { session_id: sessionId }, withCredentials: true });
        if (data.status === "credited") {
          clearInterval(iv);
          toast.success("Wallet funded — you're ready to bid!");
          setWallet((w) => ({ ...w, balance_cents: data.balance_cents }));
          loadCore();
        }
      } catch (_) { /* keep polling */ }
      if (ticks > 80) clearInterval(iv);
    }, 3000);
    polls.current.push(iv);
  }, [loadCore]);

  // Return-from-Stripe top-up → poll to credit the wallet.
  useEffect(() => {
    if (!merchantId) return;
    const q = new URLSearchParams(window.location.search);
    const tid = q.get("topup");
    const sid = q.get("session_id");
    if (tid) {
      pollTopup(tid, sid);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [merchantId, pollTopup]);

  const openAlerts = async () => {
    setAlertsOpen(true);
    if (alerts.unread > 0) {
      try {
        await axios.post(`${API}/social/rail/alerts/read`, null,
          { params: { merchant_id: merchantId }, withCredentials: true });
        setAlerts((a) => ({ ...a, unread: 0 }));
      } catch (_) { /* soft */ }
    }
  };

  const cancel = async (sid) => {
    try {
      await axios.post(`${API}/social/rail/sponsor/${sid}/cancel`, {},
        { withCredentials: true });
      toast.success("Campaign cancelled.");
      setConfirmCancel(null);
      await loadCore();
    } catch (_) { toast.error("Couldn't cancel."); }
  };

  const lowBalance = (wallet.balance_cents || 0) < floor;

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="merchant-rail-sponsor">
      <Toaster position="top-center" richColors />

      {/* Hero */}
      <div className="relative overflow-hidden border-b border-white/10"
        style={{ background: "linear-gradient(120deg,#0b0f1e 0%,#241041 60%,#3a1652 100%)" }}>
        <div className="absolute -top-16 -right-10 w-64 h-64 rounded-full blur-3xl opacity-30"
          style={{ background: "radial-gradient(circle,#f5c563,transparent 70%)" }} />
        <div className="relative px-6 lg:px-10 py-6 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-amber-300">
              <Megaphone size={12} /> Rail Sponsor
            </div>
            <h1 className="mt-1 text-2xl lg:text-3xl font-black">Bid to feature your shows across the rail</h1>
            <p className="mt-1 text-sm text-slate-300 max-w-xl">
              Fund your ad-wallet, then set a max daily bid per area. Each area runs a
              daily <b>second-price auction</b> — you win the slot and pay only the clearing price.
            </p>
          </div>
          <button type="button" onClick={openAlerts} data-testid="rail-sponsor-alerts-btn"
            className="relative w-11 h-11 grid place-items-center rounded-2xl bg-white/10 border border-white/10 hover:bg-white/15">
            <Bell size={18} />
            {alerts.unread > 0 && (
              <span data-testid="rail-sponsor-alerts-unread"
                className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-[10px] font-black grid place-items-center">
                {alerts.unread}
              </span>
            )}
          </button>
        </div>
      </div>

      <div className="px-6 lg:px-10 py-8 max-w-5xl mx-auto space-y-10">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400">
            <Loader2 className="animate-spin mr-2" size={18} /> Loading…
          </div>
        ) : (
          <>
            {/* Ad Wallet */}
            <section data-testid="rail-wallet">
              <div className="rounded-3xl border border-white/10 p-5 flex items-center justify-between gap-4 flex-wrap"
                style={{ background: "linear-gradient(135deg,#12102b,#0b0918)" }}>
                <div className="flex items-center gap-4">
                  <span className="w-12 h-12 rounded-2xl grid place-items-center"
                    style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
                    <Wallet size={22} className="text-slate-950" />
                  </span>
                  <div>
                    <div className="text-[11px] font-black uppercase tracking-widest text-slate-400">Ad-Wallet balance</div>
                    <div className="text-3xl font-black tabular-nums" data-testid="rail-wallet-balance">
                      {usd(wallet.balance_cents)}
                    </div>
                    {lowBalance && (
                      <div className="text-[11px] text-amber-300 font-bold mt-0.5">
                        Add at least {usd0(floor)} to cover a day's minimum bid.
                      </div>
                    )}
                  </div>
                </div>
                <button type="button" onClick={() => setFunding(true)} data-testid="rail-wallet-topup-btn"
                  className="inline-flex items-center gap-2 h-11 px-5 rounded-2xl font-black text-slate-950"
                  style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
                  <Plus size={16} /> Add funds
                </button>
              </div>
              {wallet.txns?.length > 0 && (
                <div className="mt-3 rounded-2xl border border-white/10 bg-slate-900/60 divide-y divide-white/5"
                  data-testid="rail-wallet-txns">
                  {wallet.txns.slice(0, 5).map((t, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-2.5 text-sm">
                      <span className="text-slate-300 capitalize flex items-center gap-2">
                        <CircleDollarSign size={13} className="text-slate-500" />
                        {t.kind}{t.ref ? ` · ${t.ref}` : ""}
                      </span>
                      <span className={`font-black tabular-nums ${t.amount_cents < 0 ? "text-rose-300" : "text-emerald-300"}`}>
                        {t.amount_cents < 0 ? "-" : "+"}{usd(Math.abs(t.amount_cents))}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Eligible shows */}
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
                          onClick={() => setPicking(s)}
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

            {/* Campaigns */}
            <section data-testid="rail-sponsor-list">
              <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">
                Your campaigns
              </h2>
              {items.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-8 text-center text-slate-400"
                  data-testid="rail-sponsor-empty-list">
                  No campaigns yet. Feature a show above to start bidding.
                </div>
              ) : (
                <div className="space-y-3">
                  {items.map((it) => (
                    <SponsorRow key={it.id} it={it} floor={floor}
                      confirmCancel={confirmCancel} setConfirmCancel={setConfirmCancel}
                      onCancel={cancel}
                      onRaise={() => setRaising(it)} />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {picking && config && (
        <FeatureModal show={picking} config={config} floor={floor}
          merchantId={merchantId} balance={wallet.balance_cents}
          onClose={() => setPicking(null)}
          onDone={() => { setPicking(null); loadCore(); }}
          onNeedFunds={() => { setPicking(null); setFunding(true); }} />
      )}

      {raising && (
        <RaiseModal item={raising} floor={floor}
          onClose={() => setRaising(null)}
          onDone={() => { setRaising(null); loadCore(); }} />
      )}

      {funding && config && (
        <TopupModal config={config} merchantId={merchantId}
          onClose={() => setFunding(false)}
          onStarted={(tid, sid) => { setFunding(false); pollTopup(tid, sid); }} />
      )}

      {alertsOpen && (
        <AlertsModal alerts={alerts.alerts} onClose={() => setAlertsOpen(false)} />
      )}
    </div>
  );
}

// ── Feature (place a standing bid) ──────────────────────────────────
function FeatureModal({ show, config, floor, merchantId, balance, onClose, onDone, onNeedFunds }) {
  const durations = config.durations || [];
  const areas = config.areas || [];
  const [tier, setTier] = useState(durations[durations.length - 1]?.id || "7d");
  const [sel, setSel] = useState(["social"]);
  const [bid, setBid] = useState(Math.max(Math.round(floor / 100), 10));
  const [busy, setBusy] = useState(false);
  const floorUsd = `$${(floor / 100).toFixed(2)}`;

  const toggleArea = (id) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const submit = async () => {
    if (sel.length === 0) { toast.error("Pick at least one area."); return; }
    if (bid < floor / 100) { toast.error(`Minimum daily bid is ${floorUsd}.`); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/social/rail/sponsor`, {
        merchant_id: merchantId, target_id: show.id, duration_tier: tier,
        daily_bid_cents: Math.round(bid * 100), target_pages: sel,
      }, { withCredentials: true });
      toast.success("Bid placed — you're in the auction!");
      if ((balance || 0) < Math.round(bid * 100)) {
        toast.message("Heads up: fund your wallet to keep winning", {
          description: "Slots are charged daily from your ad-wallet.",
        });
      }
      onDone();
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(
        code === "no_target_areas" ? "Pick at least one area."
          : code === "bid_below_floor" ? `Bid is below the ${floorUsd} floor.`
          : code === "bad_duration" ? "Pick a valid duration."
          : code === "show_not_found_or_not_host" ? "That show isn't yours."
          : "Couldn't place the bid.");
    } finally { setBusy(false); }
  };

  const perDay = Math.round(bid * 100) * sel.length;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
      onClick={() => !busy && onClose()} data-testid="rail-sponsor-feature-modal">
      <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-white/10 p-5"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest">
            <Sparkles size={12} /> Feature "{show.title}"
          </div>
          <button type="button" onClick={() => !busy && onClose()}
            data-testid="rail-sponsor-modal-close" className="text-slate-400 hover:text-white">
            <X size={18} />
          </button>
        </div>

        {/* Duration */}
        <div className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mt-4 mb-1.5">Run for</div>
        <div className="grid grid-cols-3 gap-2">
          {durations.map((d) => (
            <button key={d.id} type="button" disabled={busy}
              data-testid={`rail-sponsor-duration-${d.id}`}
              onClick={() => setTier(d.id)}
              className={`px-2 py-3 rounded-2xl border text-center transition ${
                tier === d.id ? "border-amber-400 bg-amber-500/10" : "border-white/10 bg-slate-800/60"}`}>
              <div className="font-black text-sm">{d.label}</div>
            </button>
          ))}
        </div>

        {/* Areas */}
        <div className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mt-4 mb-1.5 flex items-center gap-1.5">
          <Layers size={12} /> Show it in
        </div>
        <div className="flex flex-wrap gap-2">
          {areas.map((a) => {
            const on = sel.includes(a.id);
            const tone = AREA_TONE[a.id] || AREA_TONE.social;
            return (
              <button key={a.id} type="button" disabled={busy}
                data-testid={`rail-sponsor-area-${a.id}`}
                onClick={() => toggleArea(a.id)}
                className={`inline-flex items-center gap-2 h-10 px-4 rounded-full text-sm font-bold border transition ${
                  on ? `${tone.bg} ${tone.fg} border-transparent` : "text-slate-300 border-white/15 bg-white/[0.04]"}`}>
                <span className="w-2 h-2 rounded-full" style={{ background: tone.dot }} />
                {a.label}
              </button>
            );
          })}
        </div>
        <div className="text-[11px] text-slate-500 mt-1.5">Bids compete separately in each area.</div>

        {/* Bid */}
        <div className="text-[11px] font-bold uppercase tracking-widest text-slate-400 mt-4 mb-1.5">
          Max daily bid (per area)
        </div>
        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-800/60 px-3 h-12">
          <span className="text-slate-400 font-black">$</span>
          <input type="number" min={floor / 100} step="1" value={bid}
            data-testid="rail-sponsor-bid-input"
            onChange={(e) => setBid(Number(e.target.value))}
            className="flex-1 bg-transparent outline-none font-black text-lg" />
          <span className="text-slate-500 text-xs">/ area / day</span>
        </div>
        <div className="mt-1.5 text-[11px] text-slate-400">
          Floor {floorUsd}. You pay only the second-price clearing rate.
          Across {sel.length || 0} area{sel.length === 1 ? "" : "s"} you'll spend up to
          {" "}<b className="text-amber-300">{usd(perDay)}/day</b>.
        </div>

        <button type="button" data-testid="rail-sponsor-place-bid-btn" disabled={busy}
          onClick={submit}
          className="mt-4 w-full h-12 rounded-2xl font-black text-slate-950 flex items-center justify-center gap-2 disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <Crown size={16} />}
          Place bid
        </button>
        {(balance || 0) < floor && (
          <button type="button" onClick={onNeedFunds} data-testid="rail-sponsor-feature-fund-link"
            className="mt-2 w-full text-[11px] font-bold text-amber-300 hover:text-amber-200">
            Wallet is low — add funds first →
          </button>
        )}
      </div>
    </div>
  );
}

// ── Raise standing bid ──────────────────────────────────────────────
function RaiseModal({ item, floor, onClose, onDone }) {
  const [bid, setBid] = useState((item.daily_bid_cents || floor) / 100 + 1);
  const [busy, setBusy] = useState(false);
  const floorUsd = `$${(floor / 100).toFixed(2)}`;

  const submit = async () => {
    if (bid < floor / 100) { toast.error(`Minimum daily bid is ${floorUsd}.`); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/social/rail/sponsor/${item.id}/bid`,
        { daily_bid_cents: Math.round(bid * 100) }, { withCredentials: true });
      toast.success("Bid updated — auctions re-run instantly.");
      onDone();
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code === "bid_below_floor" ? `Bid is below the ${floorUsd} floor.`
        : code === "not_active" ? "This campaign has ended." : "Couldn't update the bid.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
      onClick={() => !busy && onClose()} data-testid="rail-sponsor-raise-modal">
      <div className="w-full max-w-sm rounded-3xl bg-slate-900 border border-white/10 p-5"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest mb-1">
          <ArrowUpCircle size={12} /> Update your daily bid
        </div>
        <div className="text-xs text-slate-400 mb-3">
          Current max bid {usd(item.daily_bid_cents)} / area / day. You're only charged the clearing price on days you win.
        </div>
        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-slate-800/60 px-3 h-12">
          <span className="text-slate-400 font-black">$</span>
          <input type="number" min={floor / 100} step="1" value={bid}
            data-testid="rail-sponsor-raise-input"
            onChange={(e) => setBid(Number(e.target.value))}
            className="flex-1 bg-transparent outline-none font-black text-lg" />
        </div>
        <button type="button" data-testid="rail-sponsor-raise-submit" disabled={busy}
          onClick={submit}
          className="mt-4 w-full h-12 rounded-2xl font-black text-slate-950 flex items-center justify-center gap-2 disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <ArrowUpCircle size={16} />}
          Update bid
        </button>
      </div>
    </div>
  );
}

// ── Fund the ad-wallet ──────────────────────────────────────────────
function TopupModal({ config, merchantId, onClose, onStarted }) {
  const presets = config.topup_presets_cents || [2000, 5000, 10000, 25000];
  const [amount, setAmount] = useState(presets[1] || 5000);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/social/rail/wallet/topup`, {
        merchant_id: merchantId, amount_cents: amount,
        origin_url: window.location.origin,
      }, { withCredentials: true });
      if (data.checkout_url) {
        window.open(data.checkout_url, "_blank", "noopener");
        toast.message("Complete payment in the new tab", {
          description: "Use test card 4242 4242 4242 4242. This updates automatically.",
        });
        onStarted(data.topup_id, data.session_id);
      }
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code === "stripe_unconfigured" ? "Payments aren't configured yet."
        : code === "not_your_business" ? "This isn't your business." : "Couldn't start top-up.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
      onClick={() => !busy && onClose()} data-testid="rail-topup-modal">
      <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-white/10 p-5"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest">
            <Wallet size={12} /> Add funds to your ad-wallet
          </div>
          <button type="button" onClick={() => !busy && onClose()}
            data-testid="rail-topup-close" className="text-slate-400 hover:text-white">
            <X size={18} />
          </button>
        </div>
        <div className="text-xs text-slate-400 mb-4">
          Your wallet is charged the daily clearing price only while you're winning a slot.
        </div>
        <div className="grid grid-cols-2 gap-2">
          {presets.map((c) => (
            <button key={c} type="button" disabled={busy}
              data-testid={`rail-topup-preset-${c}`}
              onClick={() => setAmount(c)}
              className={`h-14 rounded-2xl border font-black text-lg transition ${
                amount === c ? "border-amber-400 bg-amber-500/10 text-amber-200" : "border-white/10 bg-slate-800/60"}`}>
              {usd0(c)}
            </button>
          ))}
        </div>
        <button type="button" data-testid="rail-topup-submit" disabled={busy}
          onClick={submit}
          className="mt-4 w-full h-12 rounded-2xl font-black text-slate-950 flex items-center justify-center gap-2 disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#f5c563,#f59e0b)" }}>
          {busy ? <Loader2 className="animate-spin" size={18} /> : <Plus size={16} />}
          Fund {usd0(amount)}
        </button>
        <div className="mt-3 text-[11px] text-slate-500 text-center">
          Opens Stripe Checkout · test card 4242 4242 4242 4242 in preview.
        </div>
      </div>
    </div>
  );
}

// ── Bid alerts inbox ────────────────────────────────────────────────
function AlertsModal({ alerts, onClose }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
      onClick={onClose} data-testid="rail-alerts-modal">
      <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-white/10 p-5 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest">
            <Bell size={12} /> Bid alerts
          </div>
          <button type="button" onClick={onClose} data-testid="rail-alerts-close"
            className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>
        {alerts.length === 0 ? (
          <div className="py-10 text-center text-slate-400 text-sm" data-testid="rail-alerts-empty">
            No alerts yet. We'll ping you here (and by email) if you're outbid.
          </div>
        ) : (
          <div className="space-y-2 overflow-y-auto">
            {alerts.map((a) => {
              const tone = AREA_TONE[a.area] || AREA_TONE.social;
              return (
                <div key={a.id} data-testid={`rail-alert-${a.id}`}
                  className="rounded-2xl border border-white/10 bg-slate-800/50 p-3">
                  <div className="flex items-center gap-2">
                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${tone.bg} ${tone.fg}`}>
                      {AREA_LABEL[a.area] || a.area}
                    </span>
                    <span className="font-bold text-sm">{a.title}</span>
                    {!a.read && <span className="w-2 h-2 rounded-full bg-rose-400 ml-auto" />}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">{a.body}</div>
                  {a.created_at && (
                    <div className="text-[10px] text-slate-500 mt-1">
                      {new Date(a.created_at).toLocaleString()}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Campaign row ────────────────────────────────────────────────────
function SponsorRow({ it, floor, confirmCancel, setConfirmCancel, onCancel, onRaise }) {
  const tone = STATUS_TONE[it.status] || STATUS_TONE.ended;
  const [open, setOpen] = useState(false);
  const [series, setSeries] = useState(null);
  const areaStatus = it.area_status || {};

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
            {it.status === "active" && it.featured_any && (
              <span data-testid={`rail-sponsor-featured-${it.id}`}
                className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300">
                <Crown size={10} /> Featured
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            Max bid {usd(it.daily_bid_cents)} / area / day{it.ends_at ? ` · ends ${new Date(it.ends_at).toLocaleDateString()}` : ""}
          </div>
          {/* Per-area status chips */}
          <div className="flex flex-wrap gap-1.5 mt-2" data-testid={`rail-sponsor-areas-${it.id}`}>
            {(it.target_pages || []).map((a) => {
              const t = AREA_TONE[a] || AREA_TONE.social;
              const st = areaStatus[a] || {};
              const win = st.featured;
              return (
                <span key={a} data-testid={`rail-sponsor-area-status-${it.id}-${a}`}
                  className={`inline-flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded-lg ${t.bg} ${t.fg}`}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.dot }} />
                  {AREA_LABEL[a] || a}
                  {it.status === "active" && (win
                    ? ` · #1 · pays ${usd(st.clearing_cents)}`
                    : st.rank ? ` · #${st.rank}${st.active_total ? ` of ${st.active_total}` : ""}` : "")}
                </span>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-4" data-testid={`rail-sponsor-stats-${it.id}`}>
          <Stat icon={Eye} label="Views" value={it.impressions} />
          <Stat icon={MousePointerClick} label="Clicks" value={it.clicks} />
          <Stat icon={TrendingUp} label="CTR" value={`${it.ctr}%`} accent />
          <Stat icon={CircleDollarSign} label="Spent" value={usd(it.spend_cents)} />
        </div>
      </div>

      <div className="flex items-center gap-1.5 mt-3 flex-wrap">
        <button type="button" data-testid={`rail-sponsor-insights-toggle-${it.id}`}
          onClick={toggleInsights}
          className="inline-flex items-center gap-1 text-xs font-bold text-indigo-300 hover:text-indigo-200 px-3 h-9 rounded-lg border border-indigo-500/30">
          <BarChart3 size={13} /> {open ? "Hide" : "Trend"}
        </button>
        {it.status === "active" && (
          <button type="button" data-testid={`rail-sponsor-raise-${it.id}`} onClick={onRaise}
            className="inline-flex items-center gap-1 text-xs font-black text-amber-300 hover:text-amber-200 px-3 h-9 rounded-lg border border-amber-500/40">
            <ArrowUpCircle size={13} /> Adjust bid
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
