// Phase MER.1 — Merchant Overview (dashboard landing).
// Renders inside <MerchantShell> which provides the sidebar + auth-gate.
import { useEffect, useState } from "react";
import axios from "axios";
import { Link, useNavigate } from "react-router-dom";
import {
  DollarSign, ArrowUpRight, ArrowDownRight, ArrowRight, TrendingUp,
  Users, CreditCard, Wallet, AlertTriangle, ExternalLink, Copy,
  Loader2, ChevronRight, ReceiptText, Undo2, ArrowLeftRight,
} from "lucide-react";
import { toast } from "sonner";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantOverview() {
  const { merchant, light } = useMerchant();
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!merchant) return;
    setLoading(true);
    axios.get(`${API}/merchant/${merchant.merchant_id}/dashboard/overview`,
                          { withCredentials: true })
      .then((r) => setOverview(r.data))
      .catch((e) => toast.error(`Load overview: ${
        e?.response?.data?.detail || e.message}`))
      .finally(() => setLoading(false));
  }, [merchant]);

  if (loading || !overview) {
    return (
      <div className="p-8 max-w-6xl mx-auto" data-testid="merchant-overview-loading">
        <div className={`inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest ${
          light ? "text-purple-600" : "text-cyan-400"
        }`}>
          <Loader2 className="animate-spin" size={14}/> Loading overview…
        </div>
      </div>
    );
  }

  const k = overview.kpis;
  const stripe = overview.stripe_status;
  const stripeIssue = !stripe.charges_enabled || !stripe.payouts_enabled;
  const currency = "USD";

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto space-y-6"
              data-testid="merchant-overview-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className={`text-[10px] font-black uppercase tracking-widest ${
            light ? "text-purple-600" : "text-cyan-400"
          }`}>{new Date().toLocaleDateString(undefined,
                          { weekday: "long", month: "long", day: "numeric" })}</div>
          <h1 className={`mt-1 text-3xl lg:text-4xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"
          }`} data-testid="merchant-overview-title">
            Welcome back, {overview.merchant.name}
          </h1>
          <p className={`mt-1 text-sm ${
            light ? "text-slate-600" : "text-slate-400"
          }`}>
            Here&apos;s how your business is performing this month.
          </p>
        </div>
        <Link to="/merchant/payment-links"
                    data-testid="merchant-overview-new-link"
                    className={`inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-sm text-white shadow-lg shadow-purple-500/25`}
                    style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          Manage Payment Links <ArrowRight size={14}/>
        </Link>
      </div>

      {/* Stripe warning banner */}
      {stripeIssue && (
        <div className={`rounded-2xl p-4 flex items-start gap-3 ${
          light ? "bg-amber-50 border border-amber-200"
                  : "bg-amber-500/10 border border-amber-500/20"
        }`} data-testid="merchant-overview-stripe-warning">
          <AlertTriangle className={light ? "text-amber-600" : "text-amber-300"}
                                        size={18}/>
          <div className="flex-1 min-w-0">
            <div className={`text-sm font-black ${
              light ? "text-amber-900" : "text-amber-200"
            }`}>Complete Stripe onboarding to receive payments</div>
            <div className={`text-xs mt-0.5 ${
              light ? "text-amber-800" : "text-amber-300/70"
            }`}>
              charges: {stripe.charges_enabled ? "✓" : "✗"} ·
              payouts: {stripe.payouts_enabled ? "✓" : "✗"} ·
              status: {stripe.onboarding_status}
            </div>
          </div>
          <Link to="/merchant/stripe"
                    data-testid="merchant-overview-stripe-cta"
                    className={`text-xs font-bold uppercase tracking-widest px-4 h-8 rounded-full inline-flex items-center ${
                      light ? "bg-amber-500 text-white hover:bg-amber-600"
                              : "bg-amber-500 text-slate-950 hover:bg-amber-400"
                    }`}>
            Fix now
          </Link>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard light={light} testid="merchant-kpi-revenue"
                          label="Revenue this month"
                          value={fmtMoney(k.revenue_this_month_cents, currency)}
                          delta={k.revenue_delta_pct}
                          sub={k.revenue_last_month_cents > 0
                                        ? `vs $${(k.revenue_last_month_cents/100).toFixed(2)} last month`
                                        : "First month tracking"}
                          Icon={DollarSign}/>
        <KpiCard light={light} testid="merchant-kpi-transactions"
                          label="Transactions"
                          value={k.transactions_this_month}
                          sub={k.transactions_this_month > 0
                                        ? `avg ${fmtMoney(k.avg_transaction_cents, currency)}/tx`
                                        : "No transactions yet"}
                          Icon={ArrowLeftRight}/>
        <KpiCard light={light} testid="merchant-kpi-links"
                          label="Active payment links"
                          value={k.active_payment_links}
                          sub={`${k.total_impressions_last_30d} impressions · 30d`}
                          Icon={CreditCard}
                          href="/merchant/payment-links"/>
        <KpiCard light={light} testid="merchant-kpi-payout"
                          label={k.pending_payout_cents > 0 ? "Next payout" : "Last payout"}
                          value={k.pending_payout_cents > 0
                                        ? fmtMoney(k.pending_payout_cents, currency)
                                        : (k.last_payout
                                              ? fmtMoney(k.last_payout.amount_cents, currency)
                                              : "—")}
                          sub={k.pending_payout_cents > 0
                                        ? "in transit"
                                        : (k.last_payout?.paid_at
                                              ? new Date(k.last_payout.paid_at).toLocaleDateString(undefined,
                                                              { month: "short", day: "numeric" })
                                              : "No payouts yet")}
                          Icon={Wallet}
                          href="/merchant/payouts"/>
      </div>

      {/* Two-column: Top Links + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Top links table (3 cols) */}
        <div className={`lg:col-span-3 rounded-2xl p-5 ${
          light ? "bg-white border border-slate-100 shadow-sm"
                  : "bg-slate-900 border border-slate-800"
        }`} data-testid="merchant-overview-top-links">
          <div className="flex items-center justify-between mb-3">
            <h2 className={`text-sm font-black uppercase tracking-widest ${
              light ? "text-slate-700" : "text-slate-200"
            }`}>Top payment links</h2>
            <Link to="/merchant/payment-links"
                        className={`text-xs font-bold ${
                          light ? "text-purple-600 hover:text-purple-700"
                                  : "text-cyan-400 hover:text-cyan-300"
                        }`}>See all →</Link>
          </div>
          {overview.top_payment_links.length === 0 ? (
            <div className={`p-6 text-center text-sm rounded-xl ${
              light ? "bg-slate-50 text-slate-500"
                      : "bg-slate-950 text-slate-500 border border-slate-800"
            }`} data-testid="merchant-overview-top-links-empty">
              No active links yet.  <Link to="/merchant/payment-links"
                                                                    className={light ? "text-purple-600 underline"
                                                                                          : "text-cyan-400 underline"}>Create one →</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={`text-[10px] uppercase tracking-wider ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>
                    <th className="text-left pb-2">Title</th>
                    <th className="text-left pb-2">Type</th>
                    <th className="text-right pb-2">Usage</th>
                    <th className="text-right pb-2">Rev · 30d</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {overview.top_payment_links.map((lk) => (
                    <tr key={lk.link_id}
                          data-testid={`merchant-top-link-${lk.link_id}`}
                          className={light ? "border-t border-slate-100"
                                                        : "border-t border-slate-800"}>
                      <td className={`py-2.5 pr-2 font-semibold ${
                        light ? "text-slate-800" : "text-slate-200"
                      }`}>
                        <div className="truncate max-w-[180px]">{lk.title}</div>
                        <div className={`text-[10px] font-mono ${
                          light ? "text-slate-500" : "text-slate-500"
                        }`}>{lk.token}</div>
                      </td>
                      <td className={`py-2.5 pr-2 text-[11px] ${
                        light ? "text-slate-600" : "text-slate-400"
                      }`}>{(lk.link_type || "").replace(/_/g, " ")}</td>
                      <td className={`py-2.5 pr-2 text-right tabular-nums ${
                        light ? "text-slate-700" : "text-slate-300"
                      }`}>{lk.usage_count}</td>
                      <td className={`py-2.5 pr-2 text-right tabular-nums font-bold ${
                        light ? "text-slate-900" : "text-white"
                      }`}>
                        {fmtMoney(lk.revenue_cents_last_30d, lk.currency)}
                      </td>
                      <td className="py-2.5 text-right">
                        <button onClick={() => copyLink(lk.token)}
                                      title="Copy public URL"
                                      data-testid={`merchant-top-link-copy-${lk.link_id}`}
                                      className={light ? "text-slate-500 hover:text-purple-600"
                                                                    : "text-slate-500 hover:text-cyan-400"}>
                          <Copy size={13}/>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent activity (2 cols) */}
        <div className={`lg:col-span-2 rounded-2xl p-5 ${
          light ? "bg-white border border-slate-100 shadow-sm"
                  : "bg-slate-900 border border-slate-800"
        }`} data-testid="merchant-overview-activity">
          <div className="flex items-center justify-between mb-3">
            <h2 className={`text-sm font-black uppercase tracking-widest ${
              light ? "text-slate-700" : "text-slate-200"
            }`}>Recent activity</h2>
            <Link to="/merchant/transactions"
                        className={`text-xs font-bold ${
                          light ? "text-purple-600 hover:text-purple-700"
                                  : "text-cyan-400 hover:text-cyan-300"
                        }`}>All →</Link>
          </div>
          {overview.recent_activity.length === 0 ? (
            <div className={`p-4 text-center text-sm ${
              light ? "text-slate-500" : "text-slate-500"
            }`} data-testid="merchant-overview-activity-empty">No activity yet.</div>
          ) : (
            <div className="space-y-2">
              {overview.recent_activity.map((ev, i) => (
                <ActivityRow key={`${ev.type}-${ev.id}-${i}`}
                                          light={light} ev={ev}/>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Phase AD.2 — Game Sponsorship Revenue widget */}
      <GameSponsorshipRevenueWidget
        merchantId={merchant.merchant_id}
        light={light} />

      {/* Phase AD.4 — Coupon Sponsorship Revenue widget */}
      <CouponSponsorshipRevenueWidget
        merchantId={merchant.merchant_id}
        light={light} />
    </div>
  );
}


// ─── Phase AD.2 — Game Sponsorship Revenue widget ───────────────────
function GameSponsorshipRevenueWidget({ merchantId, light }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!merchantId) return;
    setLoading(true);
    axios.get(`${API}/merchant/${merchantId}/game-revenue`,
                          { withCredentials: true })
      .then((r) => setData(r.data))
      .catch(() => setData({ totals: { events: 0, merchant_cents: 0 },
                                                rolling_30d: { events: 0, merchant_cents: 0 },
                                                per_campaign: [] }))
      .finally(() => setLoading(false));
  }, [merchantId]);

  if (loading || !data) return null;

  // Hide when there's no activity — keep the merchant dashboard tidy.
  const noActivity = (data.totals.events || 0) === 0 &&
                                        (data.per_campaign || []).length === 0;
  if (noActivity) return null;

  return (
    <div className={`rounded-2xl p-5 ${
                          light ? "bg-white border border-slate-100 shadow-sm"
                                        : "bg-slate-900 border border-slate-800"}`}
              data-testid="merchant-game-sponsorship-widget">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className={`text-sm font-black uppercase tracking-widest inline-flex items-center gap-2 ${
                                    light ? "text-slate-700" : "text-slate-200"}`}>
          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md text-white ${
                                              light ? "bg-amber-500" : "bg-amber-600"}`}>
            <TrendingUp size={12} />
          </span>
          Game Sponsorship Revenue
        </h2>
        <span className={`text-[10px] uppercase font-mono tracking-widest ${
                                        light ? "text-amber-600" : "text-amber-400"}`}>
          Phase AD.2 · 70% share
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat label="30-day revenue"
                              value={`$${((data.rolling_30d.merchant_cents || 0) / 100).toFixed(2)}`}
                              light={light} accent testid="game-rev-30d-cents" />
        <MiniStat label="30-day events"
                              value={data.rolling_30d.events || 0}
                              light={light} testid="game-rev-30d-events" />
        <MiniStat label="Lifetime revenue"
                              value={`$${((data.totals.merchant_cents || 0) / 100).toFixed(2)}`}
                              light={light} testid="game-rev-total-cents" />
        <MiniStat label="Sponsors"
                              value={(data.per_campaign || []).length}
                              light={light} testid="game-rev-sponsors" />
      </div>

      {(data.per_campaign || []).length > 0 && (
        <div className={`mt-4 rounded-xl overflow-hidden ${
                                        light ? "border border-slate-100" : "border border-slate-800"}`}
                    data-testid="merchant-game-sponsorship-list">
          <div className={`hidden md:grid grid-cols-[2fr,1fr,90px,110px] gap-3 px-4 py-2 text-[10px] uppercase tracking-widest font-mono ${
                                              light ? "text-slate-500 bg-slate-50 border-b border-slate-100"
                                                            : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
            <div>Game</div><div>Sponsor</div><div className="text-right">Events</div><div className="text-right">Your share</div>
          </div>
          {data.per_campaign.slice(0, 6).map((row) => (
            <div key={row.game_campaign_id}
                          className={`grid md:grid-cols-[2fr,1fr,90px,110px] gap-3 px-4 py-3 items-center ${
                                    light ? "border-b border-slate-100 last:border-0"
                                                  : "border-b border-slate-800 last:border-0"}`}
                          data-testid={`merchant-game-sponsorship-row-${row.game_campaign_id}`}>
              <div className={`min-w-0 truncate ${
                                              light ? "text-slate-900" : "text-white"} text-sm font-semibold`}>
                {row.game_campaign_name || "(unnamed)"}
              </div>
              <div className="flex items-center gap-2 min-w-0">
                {row.advertiser_logo_url && (
                  <img src={row.advertiser_logo_url} alt=""
                            className="w-5 h-5 rounded object-cover shrink-0" />
                )}
                <span className={`truncate text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                  {row.advertiser_name || "—"}
                </span>
              </div>
              <div className={`text-right text-sm font-mono ${
                                              light ? "text-slate-700" : "text-slate-300"}`}>
                {row.events}
              </div>
              <div className={`text-right text-sm font-mono font-bold ${
                                              light ? "text-emerald-600" : "text-emerald-400"}`}>
                ${(row.merchant_cents / 100).toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}



// ─── Phase AD.4 — Coupon Sponsorship Revenue widget ─────────────────
function CouponSponsorshipRevenueWidget({ merchantId, light }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!merchantId) return;
    setLoading(true);
    axios.get(`${API}/merchant/${merchantId}/coupon-sponsorship-revenue`,
                          { withCredentials: true })
      .then((r) => setData(r.data))
      .catch(() => setData({ totals: { saves: 0, merchant_cents: 0 },
                                                rolling_30d: { saves: 0, merchant_cents: 0 },
                                                per_campaign: [] }))
      .finally(() => setLoading(false));
  }, [merchantId]);
  if (loading || !data) return null;
  const noActivity = (data.totals.saves || 0) === 0
                                        && (data.per_campaign || []).length === 0;
  if (noActivity) return null;

  return (
    <div className={`rounded-2xl p-5 ${
                          light ? "bg-white border border-slate-100 shadow-sm"
                                        : "bg-slate-900 border border-slate-800"}`}
              data-testid="merchant-coupon-sponsorship-widget">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h2 className={`text-sm font-black uppercase tracking-widest inline-flex items-center gap-2 ${
                                    light ? "text-slate-700" : "text-slate-200"}`}>
          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-md text-white ${
                                              light ? "bg-amber-500" : "bg-amber-600"}`}>
            <TrendingUp size={12} />
          </span>
          Coupon Sponsorship Revenue
        </h2>
        <span className={`text-[10px] uppercase font-mono tracking-widest ${
                                        light ? "text-amber-600" : "text-amber-400"}`}>
          Phase AD.4 · 70% share
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat label="30-day revenue"
                              value={`$${((data.rolling_30d.merchant_cents || 0) / 100).toFixed(2)}`}
                              light={light} accent testid="coupon-rev-30d-cents" />
        <MiniStat label="30-day saves"
                              value={data.rolling_30d.saves || 0}
                              light={light} testid="coupon-rev-30d-saves" />
        <MiniStat label="Lifetime revenue"
                              value={`$${((data.totals.merchant_cents || 0) / 100).toFixed(2)}`}
                              light={light} testid="coupon-rev-total-cents" />
        <MiniStat label="Advertisers"
                              value={(data.per_campaign || []).length}
                              light={light} testid="coupon-rev-advertisers" />
      </div>
      {(data.per_campaign || []).length > 0 && (
        <div className={`mt-4 rounded-xl overflow-hidden ${
                                        light ? "border border-slate-100" : "border border-slate-800"}`}
                    data-testid="merchant-coupon-sponsorship-list">
          {data.per_campaign.slice(0, 6).map((row) => (
            <div key={row.campaign_id}
                          className={`grid md:grid-cols-[2fr,1fr,80px,110px] gap-3 px-4 py-3 items-center ${
                                    light ? "border-b border-slate-100 last:border-0"
                                                  : "border-b border-slate-800 last:border-0"}`}
                          data-testid={`merchant-coupon-sponsorship-row-${row.campaign_id}`}>
              <div className={`min-w-0 truncate ${light ? "text-slate-900" : "text-white"} text-sm font-semibold`}>
                {row.title || "(untitled)"}
              </div>
              <div className="flex items-center gap-2 min-w-0">
                {row.advertiser_logo_url && (
                  <img src={row.advertiser_logo_url} alt=""
                            className="w-5 h-5 rounded object-cover shrink-0" />
                )}
                <span className={`truncate text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                  {row.advertiser_name || "—"}
                </span>
              </div>
              <div className={`text-right text-sm font-mono ${
                                              light ? "text-slate-700" : "text-slate-300"}`}>
                {row.saves}
              </div>
              <div className={`text-right text-sm font-mono font-bold ${
                                              light ? "text-emerald-600" : "text-emerald-400"}`}>
                ${(row.merchant_cents / 100).toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, light, accent, testid }) {
  return (
    <div className={`rounded-lg p-3 ${
                          light ? "bg-slate-50 border border-slate-100"
                                        : "bg-slate-950 border border-slate-800"}`}
              data-testid={testid}>
      <div className={`text-[9px] uppercase tracking-widest font-mono ${
                                    light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`mt-1 text-lg font-black tabular-nums ${
                                    accent ? (light ? "text-amber-600" : "text-amber-400")
                                                    : (light ? "text-slate-900" : "text-white")}`}>{value}</div>
    </div>
  );
}


function KpiCard({ light, label, value, sub, delta, Icon, href, testid }) {
  const Content = (
    <div className={`rounded-2xl p-5 h-full transition-all ${
      light ? "bg-white border border-slate-100 shadow-sm hover:shadow-md"
              : "bg-slate-900 border border-slate-800 hover:border-slate-700"
    }`} data-testid={testid}>
      <div className="flex items-start justify-between mb-3">
        <span className={`text-[10px] font-black uppercase tracking-widest ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
          light ? "bg-purple-50 text-purple-600"
                  : "bg-cyan-500/10 text-cyan-400"
        }`}><Icon size={14}/></div>
      </div>
      <div className={`text-2xl lg:text-3xl font-black tabular-nums ${
        light ? "text-slate-900" : "text-white"
      }`}>{value}</div>
      {(sub || delta != null) && (
        <div className="mt-1 flex items-center gap-2">
          {delta != null && (
            <span className={`inline-flex items-center gap-0.5 text-xs font-bold ${
              delta >= 0
                ? (light ? "text-emerald-700" : "text-emerald-300")
                : (light ? "text-rose-700" : "text-rose-300")
            }`}>
              {delta >= 0 ? <ArrowUpRight size={12}/> : <ArrowDownRight size={12}/>}
              {Math.abs(delta)}%
            </span>
          )}
          {sub && (
            <span className={`text-xs ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>{sub}</span>
          )}
        </div>
      )}
    </div>
  );
  return href ? <Link to={href}>{Content}</Link> : Content;
}


function ActivityRow({ light, ev }) {
  const meta = {
    transaction: { Icon: ReceiptText, tint: ev.status === "refunded"
                                        ? (light ? "bg-slate-100 text-slate-600"
                                                          : "bg-slate-500/15 text-slate-400")
                                        : (light ? "bg-emerald-100 text-emerald-700"
                                                          : "bg-emerald-500/15 text-emerald-300") },
    refund:            { Icon: Undo2,              tint: light ? "bg-amber-100 text-amber-700"
                                                                              : "bg-amber-500/15 text-amber-300" },
    payout:            { Icon: Wallet,            tint: light ? "bg-purple-100 text-purple-700"
                                                                              : "bg-purple-500/15 text-purple-300" },
  }[ev.type] || { Icon: ReceiptText, tint: "" };
  const label = ev.type === "transaction"
    ? (ev.status === "refunded" ? "Refunded" : "Payment")
    : ev.type === "refund" ? "Refund issued"
    : `Payout ${ev.status || ""}`.trim();
  const detail = ev.customer_email || (ev.type === "payout" ? "to bank" : "");
  return (
    <div className={`rounded-lg p-2.5 flex items-start gap-3 ${
      light ? "hover:bg-slate-50" : "hover:bg-slate-950"
    }`} data-testid={`merchant-activity-${ev.type}-${ev.id}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${meta.tint}`}>
        <meta.Icon size={13}/>
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-xs font-bold ${
          light ? "text-slate-800" : "text-slate-200"
        }`}>{label} · {fmtMoney(ev.amount_cents, ev.currency)}</div>
        {detail && (
          <div className={`text-[10px] truncate ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>{detail}</div>
        )}
      </div>
      <div className={`text-[10px] shrink-0 ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{ev.at ? new Date(ev.at).toLocaleDateString(undefined,
                                            { month: "short", day: "numeric" }) : ""}</div>
    </div>
  );
}


function fmtMoney(cents, currency = "USD") {
  const dollars = (cents || 0) / 100;
  return `$${dollars.toFixed(2)}`;
}


function copyLink(token) {
  const base = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/api\/?$/, "");
  const url = `${window.location.origin}/pay/${token}`;
  navigator.clipboard.writeText(url);
  toast.success("Link copied");
  return base;
}
