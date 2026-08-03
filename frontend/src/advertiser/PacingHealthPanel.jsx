// Phase 18c — Pacing health panel for /admin/advertiser/analytics
import { useEffect, useState } from "react";
import axios from "axios";
import { TrendingUp, TrendingDown } from "lucide-react";
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PacingHealthPanel() {
  const [data, setData] = useState({ ahead: [], behind: [] });
  useEffect(() => {
    axios.get(`${API}/admin/advertiser/pacing-health`)
            .then((r) => setData(r.data)).catch(() => {});
  }, []);
  return (
    <section className="rounded-2xl p-5 border border-white/[0.08]"
                  data-testid="pacing-health-panel">
      <h2 className="font-display font-bold text-lg mb-3">Pacing health</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <Bucket label="Ahead of pace · throttled"
                    icon={<TrendingUp size={16} className="text-rose-400"/>}
                    rows={data.ahead} kind="ahead" />
        <Bucket label="Behind pace · boosted"
                    icon={<TrendingDown size={16} className="text-amber-400"/>}
                    rows={data.behind} kind="behind" />
      </div>
    </section>
  );
}

const Bucket = ({ label, icon, rows, kind }) => (
  <div className="space-y-2">
    <div className="text-xs uppercase tracking-wide text-text-secondary
                            flex items-center gap-1">{icon} {label}</div>
    {rows.length === 0
      ? <div className="text-sm text-text-secondary">— none —</div>
      : rows.map((r) => (
        <div key={r.campaign_id}
                  data-testid={`pacing-${kind}-${r.campaign_id}`}
                  className="rounded-xl p-3 border border-white/[0.08] text-sm">
          <div className="font-display font-bold">{r.name}</div>
          <div className="text-xs text-text-secondary">{r.advertiser_id}</div>
          <div className="flex justify-between mt-1">
            <span>spend {Math.round((r.spend_progress||0)*100)}%</span>
            <span>time {Math.round((r.time_progress||0)*100)}%</span>
          </div>
        </div>
      ))}
  </div>
);
