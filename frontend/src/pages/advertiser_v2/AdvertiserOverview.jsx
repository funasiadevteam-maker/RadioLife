// Phase AD.1 — Overview tab (KPIs).
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { ArrowRight, Megaphone, Wallet, TrendingUp, Loader2 } from "lucide-react";

import { useAdvertiser } from "./AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import FlagshipSponsorUpsellBanner from "@/components/FlagshipSponsorUpsellBanner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;

export default function AdvertiserOverview() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active } = useAdvertiser();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/ad1/advertiser/${active.advertiser_id}/overview`);
        setData(data);
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, [active]);

  if (loading) return <Loader2 className="w-6 h-6 animate-spin text-amber-500 mx-auto mt-16" />;

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-6`;

  const pendingApproval = active?.status !== "active";

  return (
    <div className="space-y-6" data-testid="advertiser-overview-page">
      <FlagshipSponsorUpsellBanner business_id={active?.advertiser_id}
                                    source_page="advertiser_overview" />
      <div>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Overview</div>
        <h1 className="text-3xl md:text-4xl xl:text-5xl font-bold mt-1">Welcome back{active?.contact_name ? `, ${active.contact_name}` : ""}.</h1>
      </div>

      {pendingApproval && (
        <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 px-5 py-4 text-sm text-amber-500"
                      data-testid="advertiser-overview-pending-banner">
          Your advertiser account is <b>{active.status}</b>.  You can create draft campaigns while you wait for admin approval — campaigns can be submitted once your account is active.
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card testid="advertiser-kpi-budget" Icon={Wallet} label="Budget available"
                    value={fmt(data?.budget_available_cents)}
                    className={cardCls}
                    light={light} />
        <Card testid="advertiser-kpi-active" Icon={Megaphone} label="Active campaigns"
                    value={data?.active_campaigns ?? 0}
                    className={cardCls}
                    light={light} />
        <Card testid="advertiser-kpi-impressions" Icon={TrendingUp} label="Impressions (mo)"
                    value={(data?.impressions_this_month || 0).toLocaleString()}
                    className={cardCls}
                    light={light} />
        <Card testid="advertiser-kpi-spend" Icon={TrendingUp} label="Total spend"
                    value={fmt(data?.total_spend_cents)}
                    className={cardCls}
                    light={light} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className={cardCls}>
          <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Next step</div>
          <div className="mt-2 font-bold text-lg">Create a campaign</div>
          <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Launch a display banner, sponsor a merchant's game, or reserve an audio-preroll slot.
          </p>
          <Link to="/advertiser/dashboard/campaigns"
                        data-testid="advertiser-overview-cta-campaigns"
                        className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-500 text-slate-950 font-semibold text-sm hover:bg-amber-400 transition">
            Manage campaigns <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className={cardCls}>
          <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Budget</div>
          <div className="mt-2 font-bold text-lg">Add funds</div>
          <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Top up your budget via Stripe Checkout.  Funds are available immediately once payment clears.
          </p>
          <Link to="/advertiser/dashboard/budget"
                        data-testid="advertiser-overview-cta-budget"
                        className={`mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition ${
                            light ? "border border-slate-300 text-slate-900 hover:bg-slate-100"
                                          : "border border-slate-700 text-slate-100 hover:bg-slate-800"
                        }`}>
            Top up budget <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}

function Card({ Icon, label, value, testid, className, light }) {
  return (
    <div className={className} data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className={`text-[10px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
        <Icon className="w-4 h-4 text-amber-500" />
      </div>
      <div className="mt-3 text-2xl font-bold">{value}</div>
    </div>
  );
}
