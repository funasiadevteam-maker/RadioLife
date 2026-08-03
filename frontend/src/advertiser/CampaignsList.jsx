// Phase 18a — Campaign list + row actions.
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Pause, Play, Plus } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_TONES = {
  draft: "#888892", pending_review: "#fdb756",
  active: "#4ade80", paused: "#facc15", rejected: "#fb7185", blocked: "#fb7185",
};

export default function AdvertiserCampaigns({ advertiserId }) {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("all");
  const navigate = useNavigate();

  const load = useCallback(async () => {
    if (!advertiserId) return;
    const q = filter === "all" ? "" : `?status=${filter}`;
    const r = await axios.get(`${API}/advertiser/${advertiserId}/campaigns${q}`);
    setItems(r.data.items || []);
  }, [advertiserId, filter]);

  useEffect(() => { load(); }, [load]);

  const act = async (cid, action) => {
    try {
      await axios.post(`${API}/advertiser/${advertiserId}/campaigns/${cid}/${action}`);
      toast.success(`${action} ok`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${action} failed`);
    }
  };

  return (
    <div className="space-y-4" data-testid="advertiser-campaigns">
      <div className="flex items-end justify-between">
        <h2 className="font-display font-bold text-2xl">Campaigns</h2>
        <button className="bigfm-cta" onClick={() => navigate("/advertiser/campaigns/new")}
                    data-testid="campaigns-new-btn">
          <Plus size={14} /> New campaign
        </button>
      </div>
      <div className="flex gap-2 flex-wrap">
        {["all", "active", "paused", "draft", "pending_review", "rejected"].map((s) => (
          <button key={s} onClick={() => setFilter(s)}
                      data-testid={`filter-${s}`}
                      className={`text-xs px-3 py-1 rounded-full border
                          ${filter===s ? "border-accent-electric text-accent-electric bg-accent-electric/[0.08]"
                                            : "border-white/[0.10] text-text-secondary"}`}>{s}</button>
        ))}
      </div>
      {items.length === 0 ? (
        <p className="text-text-secondary text-sm" data-testid="campaigns-empty">
          No campaigns yet — create your first one.</p>
      ) : (
        <div className="space-y-2" data-testid="campaigns-table">
          {items.map((c) => (
            <div key={c.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-center gap-4"
                  data-testid={`campaign-row-${c.id}`}>
              <div className="flex-1 min-w-0">
                <div className="font-display font-bold truncate">{c.name}</div>
                <div className="text-xs text-text-secondary truncate">
                  {c.objective} · Budget ${c.budget_total_usd} · Spend ${(c.spend_usd||0).toFixed(2)}
                </div>
              </div>
              <span className="text-xs font-mono uppercase tracking-widest"
                        style={{color: STATUS_TONES[c.status] || "#888"}}>{c.status}</span>
              {c.status === "active" && (
                <button onClick={() => act(c.id, "pause")} title="Pause"
                            data-testid={`pause-${c.id}`}
                            className="p-2 rounded-lg hover:bg-white/[0.05]"><Pause size={14} /></button>
              )}
              {c.status === "paused" && (
                <button onClick={() => act(c.id, "resume")} title="Resume"
                            data-testid={`resume-${c.id}`}
                            className="p-2 rounded-lg hover:bg-white/[0.05]"><Play size={14} /></button>
              )}
              <button onClick={() => navigate(`/advertiser/campaigns/${c.id}`)}
                          className="text-xs text-accent-electric"
                          data-testid={`open-${c.id}`}>Open →</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
