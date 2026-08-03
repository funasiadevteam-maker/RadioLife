// Phase 18a — Advertiser overview: 4 stat cards + top-campaign card + CTA.
import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { TrendingUp, Sparkles, Heart, Wallet, ArrowRight, Plus } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdvertiserOverview({ advertiserId }) {
  const [adv, setAdv]                = useState(null);
  const [campaigns, setCampaigns]    = useState([]);
  const navigate                     = useNavigate();

  useEffect(() => {
    if (!advertiserId) return;
    (async () => {
      const r1 = await axios.get(`${API}/advertiser/${advertiserId}`);
      setAdv(r1.data.advertiser);
      const r2 = await axios.get(`${API}/advertiser/${advertiserId}/campaigns`);
      setCampaigns(r2.data.items || []);
    })().catch(() => {});
  }, [advertiserId]);

  if (!adv) return <div className="text-text-secondary" data-testid="overview-loading">Loading...</div>;

  const active = campaigns.filter((c) => c.status === "active");
  const topCmp = active[0] || campaigns[0];

  return (
    <div className="space-y-6" data-testid="advertiser-overview">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
            Advertiser
          </div>
          <h2 className="font-display font-bold text-3xl tracking-display-tight">{adv.name}</h2>
        </div>
        <button className="bigfm-cta" onClick={() => navigate("/advertiser/campaigns/new")}
                  data-testid="overview-new-campaign">
          <Plus size={14} /> New campaign
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4" data-testid="overview-stats">
        <Stat icon={Wallet}        label="Balance"   value={`$${(adv.account_balance_usd || 0).toFixed(2)}`} tone="electric" />
        <Stat icon={Sparkles}      label="Active campaigns" value={active.length} tone="magenta" />
        <Stat icon={TrendingUp} label="30d impressions" value={campaigns.reduce((s,c)=>s+((c.spend_usd||0)/0.005),0).toFixed(0)} tone="gold" />
        <Stat icon={Heart}             label="Coupon saves" value="—" tone="electric" />
      </div>

      {topCmp && (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5" data-testid="overview-top-campaign">
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">Top campaign</div>
          <h3 className="font-display font-bold text-xl mt-1">{topCmp.name}</h3>
          <div className="text-xs text-text-secondary mt-1">
            Status: <b style={{color: topCmp.status==="active" ? "#4ade80" : "#fdb756"}}>{topCmp.status}</b>
            &nbsp;·&nbsp; Budget ${topCmp.budget_total_usd}
            &nbsp;·&nbsp; Spend ${(topCmp.spend_usd||0).toFixed(2)}
          </div>
          <button className="bigfm-cta-ghost mt-3"
                       onClick={() => navigate(`/advertiser/campaigns/${topCmp.id}`)}>
            View details <ArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}


function Stat({ icon: Icon, label, value, tone="electric" }) {
  const tones = { electric: "#33d2ff", magenta: "#ff2d95", gold: "#fdb756" };
  return (
    <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-text-secondary">
        <Icon size={11} /> {label}
      </div>
      <div className="font-display font-bold text-3xl mt-1" style={{color: tones[tone]}}>{value}</div>
    </div>
  );
}
