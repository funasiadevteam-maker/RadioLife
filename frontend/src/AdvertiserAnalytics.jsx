// Phase 18b — Admin analytics dashboard for advertiser KPIs.
import { useEffect, useState } from "react";
import axios from "axios";
import { TrendingUp, AlertCircle, Sparkles, Clock } from "lucide-react";
import PacingHealthPanel from "./advertiser/PacingHealthPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdvertiserAnalytics() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/admin/advertiser/analytics?days=${days}`);
        setData(r.data);
      } catch {}
    })();
  }, [days]);

  if (!data) {
    return (
      <div className="min-h-screen bg-bg-base text-text-primary p-8"
              data-testid="advertiser-analytics">
        Loading…
      </div>
    );
  }

  const rate = Math.round((data.auto_approve_rate || 0) * 100);
  const cats = Object.entries(data.rejection_categories || {})
                              .sort((a, b) => b[1] - a[1]);
  const stages = Object.entries(data.stage_latency_ms_avg || {});

  return (
    <div className="min-h-screen bg-bg-base text-text-primary"
            data-testid="advertiser-analytics">
      <header className="border-b border-white/[0.06] px-6 py-4 flex justify-between items-center">
        <h1 className="font-display font-bold text-xl">Advertiser analytics</h1>
        <select className="bigfm-input" data-testid="analytics-range"
                    value={days} onChange={(e) => setDays(parseInt(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </header>

      <div className="max-w-6xl mx-auto p-6 grid md:grid-cols-3 gap-4">
        <Card icon={<TrendingUp size={18} className="text-emerald-400" />}
                  label="Auto-approve rate"
                  value={`${rate}%`}
                  sub={`${data.verdict_counts.approved}/${data.total_uploads} uploads`}
                  testid="kpi-approve-rate" />
        <Card icon={<Clock size={18} className="text-amber-400" />}
                  label="Manual review queue"
                  value={`${data.pending_review_queue_depth}`}
                  sub="campaigns waiting on admin"
                  testid="kpi-queue-depth" />
        <Card icon={<Sparkles size={18} className="text-violet-300" />}
                  label="AI-generated share"
                  value={`${data.source_counts.ai_generated}/${data.total_uploads || 0}`}
                  sub={`${data.source_counts.manual_upload} manual uploads`}
                  testid="kpi-ai-share" />

        <section className="md:col-span-2 rounded-2xl p-5 border border-white/[0.08]"
                       data-testid="kpi-rejections">
          <h2 className="font-display font-bold text-lg mb-3 flex items-center gap-2">
            <AlertCircle size={18} className="text-rose-400" />
            Safety-rejection breakdown
          </h2>
          {cats.length === 0 ? (
            <div className="text-text-secondary text-sm">No rejections yet.</div>
          ) : (
            <div className="space-y-2">
              {cats.map(([c, n]) => (
                <div key={c} className="flex items-center gap-3" data-testid={`reject-cat-${c}`}>
                  <div className="w-32 text-sm">{c}</div>
                  <div className="flex-1 h-3 rounded-full bg-white/[0.04] overflow-hidden">
                    <div className="h-full bg-rose-400/70"
                              style={{ width: `${Math.min(100, (n / cats[0][1]) * 100)}%` }} />
                  </div>
                  <div className="w-10 text-right text-sm font-semibold">{n}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-2xl p-5 border border-white/[0.08]"
                       data-testid="kpi-latency">
          <h2 className="font-display font-bold text-lg mb-3">Avg latency / stage</h2>
          {stages.length === 0 ? (
            <div className="text-text-secondary text-sm">No telemetry yet.</div>
          ) : (
            <div className="space-y-1 text-sm">
              {stages.map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-text-secondary">{k}</span>
                  <span className="font-mono">{v} ms</span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Phase 18c — pacing health panel (ahead/behind). */}
        <div className="md:col-span-3">
          <PacingHealthPanel />
        </div>
      </div>
    </div>
  );
}

const Card = ({ icon, label, value, sub, testid }) => (
  <div className="rounded-2xl p-5 border border-white/[0.08]" data-testid={testid}>
    <div className="flex items-center gap-2 text-xs text-text-secondary uppercase">
      {icon} {label}
    </div>
    <div className="text-3xl font-display font-bold mt-2">{value}</div>
    <div className="text-xs text-text-secondary mt-1">{sub}</div>
  </div>
);
