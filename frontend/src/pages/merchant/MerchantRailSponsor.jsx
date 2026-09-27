// Merchant → Rail Sponsor. Pay to feature one of your live shows / upcoming
// events as a highlighted card in the site-wide compact Right Rail. Reuses the
// existing Stripe checkout flow (test mode auto-activates instantly).
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Radio, Megaphone, Loader2, X, Sparkles, Eye, MousePointerClick,
  TrendingUp, Clock, CheckCircle2, Calendar,
} from "lucide-react";
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
  const [loading, setLoading] = useState(true);
  const [picking, setPicking] = useState(null); // the show being sponsored
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(null);

  const load = useCallback(async () => {
    if (!merchantId) return;
    setLoading(true);
    try {
      const [t, s, l] = await Promise.all([
        axios.get(`${API}/social/rail/sponsor/tiers`, { withCredentials: true })
          .then((r) => r.data?.tiers || []).catch(() => []),
        axios.get(`${API}/social/rail/sponsor/eligible-shows`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data?.shows || []).catch(() => []),
        axios.get(`${API}/social/rail/sponsor/list`,
          { params: { merchant_id: merchantId }, withCredentials: true })
          .then((r) => r.data?.sponsorships || []).catch(() => []),
      ]);
      setTiers(t); setShows(s); setItems(l);
    } finally { setLoading(false); }
  }, [merchantId]);

  useEffect(() => { load(); }, [load]);

  const confirmSponsor = async (tierId) => {
    if (!picking) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/social/rail/sponsor`,
        { merchant_id: merchantId, target_id: picking.id, tier: tierId },
        { withCredentials: true });
      const sid = data.sponsorship_id;
      const { data: co } = await axios.post(
        `${API}/social/rail/sponsor/${sid}/checkout`, {}, { withCredentials: true });
      if (co.mock) {
        toast.success("Sponsorship is live! Your card is now featured in the rail.");
      } else if (co.checkout_url) {
        window.location.href = co.checkout_url; return;
      }
      setPicking(null);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "not_your_business"
        ? "This isn't your business." : "Couldn't start sponsorship.");
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
      {/* Header */}
      <div className="relative overflow-hidden border-b border-white/10"
        style={{ background: "linear-gradient(120deg,#0b0f1e 0%,#241041 60%,#3a1652 100%)" }}>
        <div className="absolute -top-16 -right-10 w-64 h-64 rounded-full blur-3xl opacity-30"
          style={{ background: "radial-gradient(circle,#f5c563,transparent 70%)" }} />
        <div className="relative px-6 lg:px-10 py-6">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-amber-300">
            <Megaphone size={12} /> Rail Sponsor
          </div>
          <h1 className="mt-1 text-2xl lg:text-3xl font-black">Feature a show in the Right Rail</h1>
          <p className="mt-1 text-sm text-slate-300 max-w-xl">
            Pin one of your live shows or upcoming events to the top of the
            site-wide rail with a gold "Sponsored" highlight. See impressions and
            clicks in real time.
          </p>
        </div>
      </div>

      <div className="px-6 lg:px-10 py-8 max-w-5xl mx-auto space-y-10">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400">
            <Loader2 className="animate-spin mr-2" size={18} /> Loading…
          </div>
        ) : (
          <>
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

            {/* Active + past sponsorships */}
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
                  {items.map((it) => {
                    const tone = STATUS_TONE[it.status] || STATUS_TONE.expired;
                    return (
                      <div key={it.id} data-testid={`rail-sponsor-item-${it.id}`}
                        className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 flex items-center gap-4 flex-wrap">
                        <div className="w-14 h-14 rounded-xl overflow-hidden bg-white/5 shrink-0">
                          {it.image && <img src={it.image} alt="" className="w-full h-full object-cover" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-bold truncate">{it.title}</span>
                            <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full ${tone.bg} ${tone.fg}`}
                              data-testid={`rail-sponsor-status-${it.id}`}>{tone.label}</span>
                          </div>
                          <div className="text-xs text-slate-400 flex items-center gap-3 mt-0.5 flex-wrap">
                            <span className="inline-flex items-center gap-1">
                              <Clock size={11} /> {it.tier} · {usd(it.amount_cents)}
                            </span>
                            {it.ends_at && (
                              <span className="inline-flex items-center gap-1">
                                <Calendar size={11} /> ends {new Date(it.ends_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                        {/* Performance */}
                        <div className="flex items-center gap-4" data-testid={`rail-sponsor-stats-${it.id}`}>
                          <Stat icon={Eye} label="Views" value={it.impressions} />
                          <Stat icon={MousePointerClick} label="Clicks" value={it.clicks} />
                          <Stat icon={TrendingUp} label="CTR" value={`${it.ctr}%`} accent />
                        </div>
                        {it.status === "active" && (
                          confirmCancel === it.id ? (
                            <div className="flex items-center gap-1.5">
                              <button type="button" data-testid={`rail-sponsor-cancel-confirm-${it.id}`}
                                onClick={() => cancel(it.id)}
                                className="text-xs font-black text-white px-3 h-9 rounded-lg bg-rose-600 hover:bg-rose-500">
                                Confirm
                              </button>
                              <button type="button" data-testid={`rail-sponsor-cancel-abort-${it.id}`}
                                onClick={() => setConfirmCancel(null)}
                                className="text-xs font-bold text-slate-300 px-3 h-9 rounded-lg border border-white/10">
                                Keep
                              </button>
                            </div>
                          ) : (
                            <button type="button" data-testid={`rail-sponsor-cancel-${it.id}`}
                              onClick={() => setConfirmCancel(it.id)}
                              className="text-xs font-bold text-rose-300 hover:text-rose-200 px-3 h-9 rounded-lg border border-rose-500/30">
                              Cancel
                            </button>
                          )
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {/* Tier picker modal */}
      {picking && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-end sm:items-center justify-center p-4"
          onClick={() => !busy && setPicking(null)} data-testid="rail-sponsor-tier-modal">
          <div className="w-full max-w-md rounded-3xl bg-slate-900 border border-white/10 p-5"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2 text-amber-300 text-[10px] font-black uppercase tracking-widest">
                <Sparkles size={12} /> Choose a duration
              </div>
              <button type="button" onClick={() => !busy && setPicking(null)}
                data-testid="rail-sponsor-modal-close" className="text-slate-400 hover:text-white">
                <X size={18} />
              </button>
            </div>
            <div className="font-black text-lg truncate">{picking.title}</div>
            <div className="text-xs text-slate-400 mb-4">Featured at the top of the rail, site-wide.</div>
            <div className="space-y-2">
              {tiers.map((t) => (
                <button key={t.id} type="button" disabled={busy}
                  data-testid={`rail-sponsor-tier-${t.id}`}
                  onClick={() => confirmSponsor(t.id)}
                  className="w-full flex items-center justify-between px-4 h-14 rounded-2xl border border-white/10 bg-slate-800/60 hover:border-amber-400/50 transition disabled:opacity-60">
                  <span className="flex items-center gap-2 font-bold">
                    <Clock size={15} className="text-amber-300" /> {t.label}
                  </span>
                  <span className="font-black text-amber-300">{usd(t.amount_cents)}</span>
                </button>
              ))}
            </div>
            {busy && (
              <div className="mt-4 flex items-center justify-center text-sm text-slate-400">
                <Loader2 className="animate-spin mr-2" size={16} /> Activating…
              </div>
            )}
            <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-500">
              <CheckCircle2 size={13} className="text-emerald-400" />
              Test mode — activates instantly, no real charge.
            </div>
          </div>
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
