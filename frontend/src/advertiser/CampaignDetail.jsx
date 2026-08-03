// Phase 18a — Campaign detail (perf chart + creative preview + edit panel).
import { useEffect, useState } from "react";
import axios from "axios";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Pause, Play, ArrowLeft } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CampaignDetail({ advertiserId }) {
  const { cid } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [perf, setPerf] = useState(null);

  const load = async () => {
    if (!advertiserId) return;
    const r = await axios.get(`${API}/advertiser/${advertiserId}/campaigns/${cid}`);
    setData(r.data);
    const p = await axios.get(`${API}/advertiser/${advertiserId}/campaigns/${cid}/performance`);
    setPerf(p.data);
  };
  useEffect(() => { load(); }, [advertiserId, cid]);

  const act = async (action) => {
    try {
      await axios.post(`${API}/advertiser/${advertiserId}/campaigns/${cid}/${action}`);
      toast.success(action); load();
    } catch (e) { toast.error("failed"); }
  };

  if (!data) return <div className="text-text-secondary">Loading...</div>;
  const c = data.campaign;
  const max = Math.max(1, ...((perf?.days || []).map((d) => d.impressions)));

  return (
    <div className="space-y-6" data-testid="campaign-detail">
      <button onClick={() => navigate("/advertiser/campaigns")}
                  className="text-text-secondary text-sm flex items-center gap-1">
        <ArrowLeft size={14} /> Back to campaigns
      </button>
      <div className="flex items-end justify-between">
        <div>
          <h2 className="font-display font-bold text-3xl">{c.name}</h2>
          <div className="text-xs text-text-secondary mt-1">
            Status <b>{c.status}</b> · Objective {c.objective} · Budget ${c.budget_total_usd}
          </div>
        </div>
        <div className="flex gap-2">
          {c.status === "active" && <button className="bigfm-cta-ghost" onClick={() => act("pause")}>
            <Pause size={14} /> Pause</button>}
          {c.status === "paused" && <button className="bigfm-cta" onClick={() => act("resume")}>
            <Play size={14} /> Resume</button>}
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5" data-testid="perf-chart">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary mb-3">
          Performance (impressions per day)
        </div>
        <div className="flex gap-1 items-end h-32">
          {(perf?.days || []).slice(-30).map((d) => (
            <div key={d.date} title={`${d.date}: ${d.impressions}`}
                      className="flex-1 bg-accent-electric/40 hover:bg-accent-electric rounded-t"
                      style={{height: `${(d.impressions/max)*100}%`}} />
          ))}
          {(perf?.days || []).length === 0 && (
            <div className="text-xs text-text-secondary self-center">
              No data yet — impressions will show here once serving starts.
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
          <Kpi label="Impressions" v={perf?.totals?.impressions || 0} />
          <Kpi label="Completes"   v={perf?.totals?.completes || 0} />
          <Kpi label="Saves"       v={perf?.totals?.saves || 0} />
          <Kpi label="Spend"       v={`$${(perf?.totals?.spend_usd || 0).toFixed(2)}`} />
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-5">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary mb-3">
          Creatives
        </div>
        <div className="space-y-2" data-testid="campaign-creatives">
          {(data.creatives || []).map((cr) => (
            <div key={cr.id} className="rounded-xl border border-white/[0.06] p-3 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-sm">{cr.title}</div>
                <div className="text-[10px] text-text-secondary uppercase font-mono">
                  {cr.status} · {cr.duration_sec}s
                </div>
              </div>
              {cr.audio_url && (
                <audio src={`${process.env.REACT_APP_BACKEND_URL}${cr.audio_url}`} controls
                            className="h-8" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


function Kpi({ label, v }) {
  return <div>
    <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">{label}</div>
    <div className="font-display font-bold text-2xl">{v}</div>
  </div>;
}
