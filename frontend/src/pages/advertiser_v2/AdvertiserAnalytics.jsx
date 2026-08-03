// Phase AD.1 — Analytics tab: per-campaign KPIs (stub — real serving lands later).
import { useEffect, useState } from "react";
import axios from "axios";
import { BarChart3, Loader2 } from "lucide-react";

import { useAdvertiser } from "./AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;

export default function AdvertiserAnalytics() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active } = useAdvertiser();
  const [items, setItems] = useState([]);
  const [analytics, setAnalytics] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/ad1/advertiser/${active.advertiser_id}/campaigns`);
        setItems(data.items || []);
        // Fetch analytics for each in parallel.
        const results = await Promise.all(
          (data.items || []).map((c) =>
            axios.get(`${API}/ad1/advertiser/${active.advertiser_id}/campaigns/${c.campaign_id}/analytics`)
              .then((r) => [c.campaign_id, r.data])
              .catch(() => [c.campaign_id, null])
          ));
        setAnalytics(Object.fromEntries(results));
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, [active]);

  if (loading) return <Loader2 className="w-6 h-6 animate-spin text-amber-500 mx-auto mt-16" />;

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-6`;

  return (
    <div className="space-y-6" data-testid="advertiser-analytics-page">
      <div>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Analytics</div>
        <h1 className="text-3xl font-bold mt-1">Campaign performance</h1>
      </div>

      {items.length === 0 ? (
        <div className={`${cardCls} text-center`} data-testid="advertiser-analytics-empty">
          <BarChart3 className="w-10 h-10 text-slate-500 mx-auto" />
          <div className="mt-3 font-bold">No campaigns yet</div>
          <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Create a campaign to see performance data here.
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {items.map((c) => {
            const a = analytics[c.campaign_id];
            return (
              <div key={c.campaign_id} className={cardCls}
                          data-testid={`advertiser-analytics-row-${c.campaign_id}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-bold">{c.name}</div>
                    <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
                      {c.campaign_type.replace(/_/g, " ")} · {c.status}
                    </div>
                  </div>
                  <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"} font-mono`}>
                    {c.campaign_id}
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <Kpi label="Impressions" value={(a?.impressions || 0).toLocaleString()} light={light} />
                  <Kpi label="Clicks" value={(a?.clicks || 0).toLocaleString()} light={light} />
                  <Kpi label="CTR" value={`${((a?.ctr || 0) * 100).toFixed(2)}%`} light={light} />
                  <Kpi label="Spend / Budget"
                              value={`${fmt(a?.spend_cents)} / ${fmt(c.budget_total_cents)}`}
                              light={light} />
                </div>
              </div>
            );
          })}
        </div>
      )}
      <p className={`text-xs mt-4 ${light ? "text-slate-500" : "text-slate-500"}`}>
        Real-time impression rotation ships in a follow-up phase.  Stats above reflect the AD.1 impression stub.
      </p>
    </div>
  );
}

function Kpi({ label, value, light }) {
  return (
    <div>
      <div className={`text-[10px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className="mt-1 font-bold text-lg">{value}</div>
    </div>
  );
}
