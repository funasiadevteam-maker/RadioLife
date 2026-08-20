/**
 * Phase 17b — Multi-venue org rollup + payouts.
 *
 * Routes:
 *   /venue/orgs/:orgId       → org-wide rollup (owner only)
 *   /venue/:venueId/payouts  → per-venue payout report (any staff)
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useParams, NavLink } from "react-router-dom";
import { toast } from "sonner";
import { Card, Button } from "@/shell/primitives";
import { Building2, TrendingUp, DollarSign, Award, Download, BarChart3 } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";
axios.defaults.withCredentials = true;


// ─── /venue/orgs/:orgId ────────────────────────────────────────────
export default function VenueOrgRollup() {
  const { orgId } = useParams();
  const [data, setData]      = useState(null);
  const [period, setPeriod] = useState("month");
  const [err, setErr]        = useState(null);

  useEffect(() => {
    axios.get(`${API}/venue/orgs/${orgId}/rollup?period=${period}`)
      .then(({ data }) => { setData(data); setErr(null); })
      .catch((e) => {
        const d = e?.response?.data?.detail;
        setErr(typeof d === "string" ? d
                  : d?.message || `Couldn't load rollup (status ${e?.response?.status || "?"}).`);
      });
  }, [orgId, period]);

  if (err) {
    return (
      <div className="min-h-screen px-6 sm:px-10 lg:px-14 pt-10 pb-24" data-testid="org-rollup-err">
        <h1 className="font-display font-bold text-3xl">Multi-venue rollup</h1>
        <Card className="p-6 mt-6">
          <div className="text-accent-magenta font-display font-bold">{err}</div>
          <div className="text-text-secondary text-xs mt-2">
            Only the org owner can see this rollup. If you're a manager,
            you'll have visibility into your own venue's dashboard instead.
          </div>
        </Card>
      </div>
    );
  }
  if (!data) {
    return <div className="min-h-screen px-6 pt-10 text-center text-text-secondary">Loading…</div>;
  }

  const org = data.org || {};
  return (
    <div className="min-h-screen px-6 sm:px-10 lg:px-14 pb-24 pt-6"
          data-testid="venue-org-rollup">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
              CHAIN
            </div>
            <h1 className="font-display font-bold text-5xl tracking-display-tight"
                  style={{ color: org.primary_color || undefined }}
                  data-testid="org-name">
              {org.name || "Multi-venue rollup"}
            </h1>
            <div className="text-text-secondary text-sm mt-2">
              {data.total_venues} venue{data.total_venues !== 1 && "s"} ·{" "}
              {data.total_redemptions} redemption{data.total_redemptions !== 1 && "s"} this {period}
            </div>
          </div>
          <div className="flex gap-1 p-1 bg-bg-glass rounded-full text-xs">
            {[["today", "Today"], ["week", "Week"], ["month", "Month"]].map(([p, l]) => (
              <button key={p} onClick={() => setPeriod(p)}
                            className={`px-4 py-1.5 rounded-full ${period === p
                              ? "bg-accent-magenta/20 text-accent-magenta"
                              : "text-text-secondary"}`}
                            data-testid={`org-period-${p}`}>{l}</button>
            ))}
          </div>
        </div>
        {/* 4 stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="org-stat-cards">
          <BigStat icon={<Building2 size={16} />} label="Total venues" v={data.total_venues} />
          <BigStat icon={<TrendingUp size={16} />} label="Redemptions" v={data.total_redemptions} />
          <BigStat icon={<DollarSign size={16} />} label="Cash redeemed"
                        v={`$${(data.total_revenue_usd || 0).toLocaleString()}`} />
          <BigStat icon={<Award size={16} />} label="Best offer"
                        v={data.best_offer?.title || "—"}
                        small={data.best_offer ? `${data.best_offer.redeemed} redeems` : null} />
        </div>
        {/* Per-venue cards */}
        <div className="space-y-2">
          <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono mb-2">
            All venues
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
                data-testid="org-venue-cards">
            {(data.venues || []).map((v) => (
              <NavLink key={v.id} to={`/venue/${v.id}/payouts`}
                              data-testid={`org-venue-card-${v.id}`}>
                <div className={`rounded-2xl p-4 space-y-2 border bg-white/[0.03] hover:bg-white/[0.06]
                                            ${v.id === data.best_venue_id
                                              ? "border-accent-electric/60"
                                              : "border-white/[0.10]"}`}>
                  <div className="flex items-center justify-between">
                    <div className="font-display font-bold text-lg tracking-display-tight truncate">
                      {v.name}
                    </div>
                    {v.id === data.best_venue_id && (
                      <span className="text-[10px] uppercase tracking-widest text-accent-electric font-mono">
                        ★ TOP
                      </span>
                    )}
                  </div>
                  <div className="text-text-secondary text-xs uppercase tracking-wider">
                    {v.market}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs mt-2">
                    <div>
                      <div className="text-text-secondary">Redeems</div>
                      <div className="font-display font-bold text-base">{v.redeems}</div>
                    </div>
                    <div>
                      <div className="text-text-secondary">Revenue</div>
                      <div className="font-display font-bold text-base">${v.revenue_usd}</div>
                    </div>
                  </div>
                  {v.top_offer_title && (
                    <div className="text-xs text-accent-magenta truncate pt-1">
                      Top: {v.top_offer_title}
                    </div>
                  )}
                </div>
              </NavLink>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


// ─── /venue/:venueId/payouts ──────────────────────────────────────
export function VenuePayouts() {
  const { venueId } = useParams();
  const [data, setData]      = useState(null);
  const [period, setPeriod] = useState("month");
  useEffect(() => {
    axios.get(`${API}/venue/${venueId}/payouts?period=${period}`)
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Couldn't load payouts."));
  }, [venueId, period]);

  const exportCsv = () => {
    const url = `${API}/venue/${venueId}/payouts/export.csv?period=${period}`;
    window.open(url, "_blank");
  };

  if (!data) {
    return <div className="min-h-screen px-6 pt-10 text-center text-text-secondary">Loading…</div>;
  }

  return (
    <div className="min-h-screen px-6 sm:px-10 lg:px-14 pb-24 pt-6" data-testid="venue-payouts-page">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
              VENUE HQ
            </div>
            <h1 className="font-display font-bold text-5xl tracking-display-tight"
                  data-testid="payouts-title">
              Payout report
            </h1>
            <div className="text-text-secondary text-sm mt-2">
              Live calculation — no waiting for end-of-month settlement.
            </div>
          </div>
          <div className="flex gap-3 items-center">
            <div className="flex gap-1 p-1 bg-bg-glass rounded-full text-xs">
              {[["week", "Week"], ["month", "Month"]].map(([p, l]) => (
                <button key={p} onClick={() => setPeriod(p)}
                              className={`px-4 py-1.5 rounded-full ${period === p
                                ? "bg-accent-magenta/20 text-accent-magenta"
                                : "text-text-secondary"}`}
                              data-testid={`payouts-period-${p}`}>{l}</button>
              ))}
            </div>
            <Button variant="primary" size="sm" onClick={exportCsv}
                        data-testid="payouts-export-csv">
              <Download size={12} /> Export CSV
            </Button>
          </div>
        </div>
        {/* 4 big stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="payouts-stats">
          <BigStat icon={<TrendingUp size={16} />} label="Redemptions"
                        v={data.cash_redemptions_count} />
          <BigStat icon={<DollarSign size={16} />} label="Cash redeemed"
                        v={`$${data.cash_redemptions_value_usd}`} />
          <BigStat icon={<BarChart3 size={16} />} label="Platform share"
                        v={`$${data.net_platform_revenue_share_usd}`}
                        small={`${data.platform_cut_pct}% cut`} />
          <BigStat icon={<Award size={16} />} label="Expected payout"
                        v={`$${data.expected_payout_to_venue_usd}`} />
        </div>
        {/* Bigcoin liability + ad-spend notice */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Card className="p-4">
            <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
              BigPoints liability
            </div>
            <div className="font-display font-bold text-3xl tracking-display-tight mt-1">
              ${data.bigcoin_liability_usd}
            </div>
            <div className="text-text-secondary text-xs mt-1">
              Awarded to players who redeemed at this venue.
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
              Ad spend (net)
            </div>
            <div className="font-display font-bold text-3xl tracking-display-tight mt-1">
              ${data.ad_spend_net_usd}
            </div>
            <div className="text-text-secondary text-xs mt-1">{data.ad_spend_note}</div>
          </Card>
        </div>
        {/* Bar chart */}
        <Card className="p-5" data-testid="payouts-chart">
          <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono mb-3">
            Daily redemptions × value
          </div>
          <PayoutsBars buckets={data.time_buckets} />
        </Card>
      </div>
    </div>
  );
}


function PayoutsBars({ buckets }) {
  const [R, setR] = useState(null);
  useEffect(() => { import("recharts").then(setR); }, []);
  if (!buckets || buckets.length === 0) {
    return <div className="text-text-secondary text-xs py-6 text-center">
      No redemptions in this window yet.
    </div>;
  }
  if (!R) return <div className="text-text-secondary text-xs">Loading…</div>;
  return (
    <R.ResponsiveContainer width="100%" height={260}>
      <R.BarChart data={buckets}>
        <R.CartesianGrid stroke="rgba(255,255,255,0.06)" />
        <R.XAxis dataKey="day"   stroke="#9aa0a6" fontSize={11} />
        <R.YAxis stroke="#9aa0a6" fontSize={11} />
        <R.Tooltip contentStyle={{ background: "#0a0a0c",
                                              border:     "1px solid rgba(255,255,255,0.1)" }} />
        <R.Legend wrapperStyle={{ fontSize: 11 }} />
        <R.Bar dataKey="redemptions" fill="#7fd1ff" />
        <R.Bar dataKey="value_usd"    fill="#ff2d8a" />
      </R.BarChart>
    </R.ResponsiveContainer>
  );
}


function BigStat({ icon, label, v, small }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] p-4">
      <div className="flex items-center gap-2 text-text-secondary text-[10px]
                                uppercase tracking-[0.25em] font-mono">
        {icon}{label}
      </div>
      <div className="font-display font-bold text-3xl tracking-display-tight mt-2 truncate">
        {v ?? "—"}
      </div>
      {small && <div className="text-xs text-accent-electric mt-1">{small}</div>}
    </div>
  );
}
