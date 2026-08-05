// Phase I — Business Redemption Portal: dashboard.
// Shows the storefront identity card, period-toggleable stats, recent
// redemptions, and quick links to /business/redeem and /business/campaigns.
// Phase J.1 — adds the "Launch your first coupon in 60 seconds" CTA card
// for businesses with zero lifetime redemptions.
import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Store, ScanLine, Megaphone, BarChart3, Clock,
          ShieldCheck, Loader2, ChevronRight, Ticket,
          Rocket, Copy, Share2, X } from "lucide-react";
import { Card, Button, Chip, LiveDot } from "@/shell/primitives";
import { API } from "@/AuthContext";

function fmt(n) { return Number(n || 0).toLocaleString(); }
function fmtTime(t) {
  if (!t) return "—";
  const d = new Date(t);
  if (isNaN(d.getTime())) return t;
  return d.toLocaleString();
}

const TPL_TONES = {
  magenta: "bg-accent-magenta/15 text-accent-magenta border-accent-magenta/30",
  electric: "bg-accent-electric/15 text-accent-electric border-accent-electric/30",
  gold:    "bg-accent-gold/15 text-accent-gold border-accent-gold/30",
  emerald: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
};

export default function BusinessDashboard() {
  const navigate = useNavigate();
  const [biz, setBiz]       = useState(null);
  const [stats, setStats]  = useState(null);
  const [recent, setRecent] = useState([]);
  const [period, setPeriod] = useState("week");
  const [loading, setLoading] = useState(true);
  // Phase J.1
  const [templates, setTemplates] = useState([]);
  const [launchResult, setLaunchResult] = useState(null);
  const [launching, setLaunching] = useState(false);

  const load = useCallback(async (p = period) => {
    setLoading(true);
    try {
      const [b, s, r, tp] = await Promise.all([
        axios.get(`${API}/business/me`),
        axios.get(`${API}/business/dashboard/stats?period=${p}`),
        axios.get(`${API}/business/coupons/recent?limit=8`),
        axios.get(`${API}/business/coupons/launch-templates`)
              .catch(() => ({ data: { templates: [] } })),
      ]);
      setBiz(b.data);
      setStats(s.data);
      setRecent(r.data.items || []);
      setTemplates(tp.data.templates || []);
    } catch (e) {
      if (e?.response?.status === 403) {
        toast.message("Set up your business profile first.");
        navigate("/business/register", { replace: true });
      } else {
        toast.error(e?.response?.data?.detail || "Couldn't load your dashboard.");
      }
    } finally { setLoading(false); }
  }, [period, navigate]);

  useEffect(() => { load(period); }, [load, period]);

  const launchTemplate = async (tpl) => {
    if (launching || tpl.already_issued) return;
    setLaunching(true);
    try {
      const r = await axios.post(
        `${API}/business/coupons/launch-template`,
        { template_id: tpl.id });
      setLaunchResult(r.data);
      toast.success(`100 codes minted · ${tpl.name}`);
      // refresh template list to grey-out the used one.
      try {
        const tp = await axios.get(`${API}/business/coupons/launch-templates`);
        setTemplates(tp.data.templates || []);
      } catch (_e) { /* */ }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail?.code === "already_issued") {
        toast.message("You already issued this template.");
        setLaunchResult(detail);
      } else {
        toast.error(detail?.code || detail || "Launch failed.");
      }
    } finally { setLaunching(false); }
  };

  if (loading && !biz) {
    return (
      <div className="min-h-screen grid place-items-center text-text-secondary"
              data-testid="business-dashboard-loading">
        <Loader2 size={22} className="animate-spin" />
      </div>
    );
  }

  const showLaunchCta = (stats?.total_lifetime_redemptions || 0) === 0
                                                  && templates.some((t) => !t.already_issued);

  return (
    <div data-testid="business-dashboard"
            className="min-h-screen bg-bg-base px-4 sm:px-6 py-8 pb-24
                                      max-w-6xl mx-auto space-y-6">
      <Toaster richColors theme="dark" position="bottom-right" />

      {/* Header — storefront identity */}
      <Card className="p-6 sm:p-8 flex flex-col sm:flex-row items-start
                                      sm:items-center gap-4 sm:gap-6">
        <div className="w-14 h-14 rounded-token-md grid place-items-center
                                bg-accent-gold/15 text-accent-gold flex-shrink-0">
          <Store size={26} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h1 className="font-display font-bold text-2xl sm:text-3xl
                                  tracking-display-tight" data-testid="business-name">
              {biz?.name || "Your business"}
            </h1>
            {biz?.verified
              ? <Chip tone="emerald" data-testid="business-verified-chip">
                    <ShieldCheck size={11} /> Verified
                </Chip>
              : <Chip tone="neutral" data-testid="business-unverified-chip">
                    Pending verification
                </Chip>}
          </div>
          <div className="text-xs text-text-secondary flex flex-wrap gap-x-3 gap-y-1">
            <span data-testid="business-category">{biz?.category?.toUpperCase()}</span>
            {biz?.address && <span>· {biz.address}</span>}
            <span className="font-mono">· id {biz?._id || biz?.id}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="gold" onClick={() => navigate("/business/redeem")}
                          data-testid="business-cta-redeem">
            <ScanLine size={14} /> Redeem coupon
          </Button>
          <Button variant="outline" onClick={() => navigate("/business/ads/buy")}
                          data-testid="business-cta-ads">
            <Megaphone size={14} /> Run ads
          </Button>
        </div>
      </Card>

      {/* Phase J.1 — Launch coupon CTA (only for zero-redemption businesses). */}
      {showLaunchCta && !launchResult && (
        <Card className="p-5 sm:p-6 space-y-4 border-accent-magenta/25
                                      bg-gradient-to-br from-accent-magenta/[0.06]
                                                                  to-transparent"
                    data-testid="business-launch-cta">
          <header className="flex items-start justify-between gap-3 flex-wrap">
            <div className="space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-accent-magenta flex items-center gap-2">
                <Rocket size={11} /> First-time activation
              </div>
              <h3 className="font-display font-bold text-xl sm:text-2xl
                                          tracking-display-tight">
                Launch your first coupon in <span className="text-accent-magenta">60 seconds</span>
              </h3>
              <p className="text-xs text-text-secondary max-w-md">
                Pick a template, get 100 voucher codes minted, targeted to
                listeners within 5 miles of your storefront. No setup, no
                approvals.
              </p>
            </div>
          </header>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            {templates.map((t) => {
              const toneCls = TPL_TONES[t.tone] || TPL_TONES.magenta;
              return (
                <button key={t.id} disabled={t.already_issued || launching}
                                onClick={() => launchTemplate(t)}
                                data-testid={`business-launch-tpl-${t.id}`}
                                className={`rounded-token-md border p-3 text-left
                                                  flex flex-col gap-2 transition-all
                                                  ${t.already_issued
                                                      ? "opacity-40 cursor-not-allowed bg-white/[0.02] border-white/10"
                                                      : `${toneCls} hover:scale-[1.02]`}`}>
                  <div className="text-[10px] font-mono uppercase tracking-widest">
                    {t.discount_label}
                  </div>
                  <div className="font-semibold text-sm text-text-primary">
                    {t.name}
                  </div>
                  {t.already_issued && (
                    <div className="text-[10px] text-text-secondary">
                      Already issued
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </Card>
      )}

      {/* Phase J.1 — Launch result success card. */}
      {launchResult && (
        <Card className="p-5 sm:p-6 space-y-3 border-accent-gold/30
                                      bg-accent-gold/[0.06]"
                    data-testid="business-launch-result">
          <header className="flex items-center justify-between flex-wrap gap-2">
            <div className="space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-accent-gold flex items-center gap-2">
                <Rocket size={11} /> Coupons live
              </div>
              <h3 className="font-display font-bold text-xl tracking-display-tight">
                {launchResult.title || launchResult.discount_label || "Launch promo"}
              </h3>
              <p className="text-xs text-text-secondary">
                <strong className="text-accent-gold">
                  {launchResult.code_count || 100} voucher codes
                </strong>{" "}
                minted · expires {launchResult.expires_at
                  ? new Date(launchResult.expires_at).toLocaleDateString()
                  : "in 30 days"}.
              </p>
            </div>
            <button onClick={() => setLaunchResult(null)}
                            data-testid="business-launch-result-close"
                            className="text-text-secondary hover:text-white">
              <X size={14} />
            </button>
          </header>
          <div className="flex flex-wrap gap-2 items-center">
            <code className="flex-1 min-w-[200px] bg-bg-base/60 rounded-token-md
                                          px-3 py-2 text-xs font-mono text-text-secondary
                                          truncate"
                          data-testid="business-launch-result-url">
              {window.location.origin}{launchResult.public_share_url}
            </code>
            <Button size="sm" variant="outline"
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(
                                  `${window.location.origin}${launchResult.public_share_url}`);
                                toast.success("Link copied!");
                              } catch (_e) { toast.error("Copy failed"); }
                            }}
                            data-testid="business-launch-result-copy">
              <Copy size={12} /> Copy
            </Button>
            <Button size="sm" variant="gold"
                            onClick={async () => {
                              const url = `${window.location.origin}${launchResult.public_share_url}`;
                              const text = launchResult.share_text || `Check out our offer on RadioLife: ${url}`;
                              try {
                                if (navigator.share) {
                                  await navigator.share({
                                    title: launchResult.title || "RadioLife Offer",
                                    text, url,
                                  });
                                } else {
                                  await navigator.clipboard.writeText(`${text}\n${url}`);
                                  toast.success("Share text copied!");
                                }
                              } catch (_e) { /* user cancelled */ }
                            }}
                            data-testid="business-launch-result-share">
              <Share2 size={12} /> Share now
            </Button>
          </div>
        </Card>
      )}

      {/* Period toggle */}
      <div className="flex items-center justify-between" data-testid="business-period-row">
        <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary flex items-center gap-2">
          <LiveDot /> Activity · last <span className="text-accent-gold">{period}</span>
        </div>
        <div className="flex gap-1.5">
          {["today", "week", "month"].map((p) => (
            <button key={p} onClick={() => setPeriod(p)}
                            data-testid={`business-period-${p}`}>
              <Chip active={period === p} tone={period === p ? "electric" : "neutral"}>
                {p}
              </Chip>
            </button>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3"
              data-testid="business-stats">
        <StatTile icon={Ticket}
                          label="Redemptions"
                          value={fmt(stats?.redemptions)}
                          accent="text-accent-gold"
                          testid="business-stat-redemptions" />
        <StatTile icon={BarChart3}
                          label="Revenue attributed"
                          value={`$${fmt(stats?.revenue_attributed)}`}
                          accent="text-accent-electric"
                          testid="business-stat-revenue" />
        <StatTile icon={Clock}
                          label="Lifetime"
                          value={fmt(stats?.total_lifetime_redemptions)}
                          accent="text-accent-magenta"
                          testid="business-stat-lifetime" />
        <StatTile icon={ShieldCheck}
                          label="Status"
                          value={biz?.verified ? "Verified" : "Pending"}
                          accent={biz?.verified ? "text-emerald-400" : "text-yellow-400"}
                          testid="business-stat-status" />
      </div>

      {/* Top offers */}
      {(stats?.top_offers || []).length > 0 && (
        <Card className="p-5 space-y-3" data-testid="business-top-offers">
          <h3 className="font-display font-bold text-lg tracking-display-tight">
            Top offers
          </h3>
          <ul className="divide-y divide-white/[0.06]">
            {stats.top_offers.map((o, i) => (
              <li key={`${o._id}_${i}`}
                  className="py-2.5 flex items-center justify-between gap-3 text-sm"
                  data-testid={`business-top-offer-${i}`}>
                <span className="truncate text-text-primary">
                  {o._id || "Untitled offer"}
                </span>
                <span className="text-xs text-text-secondary">
                  <strong className="text-accent-gold">{fmt(o.n)}</strong> redemptions
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Recent redemptions */}
      <Card className="p-5 space-y-3" data-testid="business-recent">
        <header className="flex items-center justify-between">
          <h3 className="font-display font-bold text-lg tracking-display-tight">
            Recent redemptions
          </h3>
          <Link to="/business/redeem"
                  className="text-xs text-accent-electric hover:underline">
            Open redemption screen <ChevronRight size={11} className="inline" />
          </Link>
        </header>
        {recent.length === 0 && (
          <p className="text-sm text-text-secondary">
            No redemptions yet. When a customer claims one of your offers
            and scans it at your counter, it&apos;ll show up here.
          </p>
        )}
        {recent.length > 0 && (
          <ul className="divide-y divide-white/[0.06]">
            {recent.map((r) => (
              <li key={r._id}
                  className="py-2.5 flex flex-col sm:flex-row sm:items-center
                                gap-1 sm:gap-3 text-sm"
                  data-testid={`business-recent-row-${r._id}`}>
                <span className="text-text-primary flex-1 truncate">
                  {r.offer_title || "Coupon"}
                </span>
                <span className="text-xs text-text-secondary font-mono">
                  {r.code}
                </span>
                <span className="text-xs text-text-secondary">
                  {fmtTime(r.redeemed_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="flex justify-end">
        <Link to="/business/campaigns"
                className="text-xs text-text-secondary hover:text-white inline-flex
                                items-center gap-1.5"
                data-testid="business-campaigns-link">
          See your ad campaigns →
        </Link>
      </div>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, accent, testid }) {
  return (
    <Card className="p-4 flex flex-col gap-2" data-testid={testid}>
      <div className={`flex items-center gap-1.5 text-[10px] font-mono
                                  uppercase tracking-widest text-text-secondary`}>
        <Icon size={11} /> {label}
      </div>
      <div className={`font-display font-bold text-2xl tracking-display-tight ${accent}`}>
        {value}
      </div>
    </Card>
  );
}
