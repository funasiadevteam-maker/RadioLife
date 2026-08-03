// AdminCampaignsQueue.js — Phase 4: admin reviews + approves campaigns.
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, CheckCircle, XCircle, Pause, RefreshCcw } from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const STATUS_COLORS = {
  draft: "#6c6c78", pending_approval: "#fdb756",
  active: "#4ade80", paused: "#facc15", rejected: "#fb7185", completed: "#888892",
};

export default function AdminCampaignsQueue() {
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState("active");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const q = filter === "all" ? "" : `?status=${filter}`;
      const r = await axios.get(`${API}/admin/ads/campaigns/queue${q}`);
      setItems(r.data.items || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load campaigns");
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const act = async (campaign_id, action, extra = "") => {
    setBusy(campaign_id);
    try {
      await axios.post(`${API}/admin/ads/campaigns/${campaign_id}/${action}${extra}`);
      toast.success(`${action} ok`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${action} failed`);
    } finally { setBusy(null); }
  };

  if (loading || !items) return <div className="admin-img-wrap"><Loader2 className="spin" size={28} /></div>;

  return (
    <div className="admin-img-wrap" data-testid="admin-campaigns-queue">
      <header className="admin-img-header">
        <div>
          <h1>Campaign Queue</h1>
          <p>{items.length} campaigns · approve, pause, or reject</p>
        </div>
        <div className="admin-img-pills">
          <Link to="/admin/ads/revenue" className="admin-pill">Revenue Live</Link>
          <Link to="/admin/advertisers/queue" className="admin-pill">Advertisers</Link>
        </div>
      </header>
      <div className="assets-toolbar">
        {["pending_approval", "active", "paused", "rejected", "all"].map((s) => (
          <button key={s} type="button"
            className={`asset-type-chip ${filter === s ? "on" : ""}`}
            onClick={() => setFilter(s)} data-testid={`cq-filter-${s}`}>
            {s.replace("_", " ").toUpperCase()}
          </button>
        ))}
        <button className="asset-type-chip" onClick={load} data-testid="cq-refresh"><RefreshCcw size={11} /> REFRESH</button>
      </div>
      <div className="assets-grid">
        {items.map((c) => (
          <div key={c.id || c.campaign_id} className="asset-row" data-testid={`campaign-row-${c.campaign_id}`}>
            <div className="asset-row-head">
              <div>
                <div className="asset-slug">{c.campaign_id}</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#fff", marginTop: 4 }}>{c.name}</div>
              </div>
              <span className="asset-status" style={{ background: STATUS_COLORS[c.status] + "33", color: STATUS_COLORS[c.status] }}>
                {c.status}
              </span>
            </div>
            <div className="asset-meta-row">
              <span>ADV<b>{c.advertiser_name || "?"}</b></span>
              <span>BIZ<b>{c.business_name || "?"}</b></span>
              <span>TYPE<b>{c.campaign_type}</b></span>
            </div>
            <div className="asset-meta-row">
              <span>BUDGET<b>${(c.budget_cents / 100).toFixed(0)}</b></span>
              <span>BID<b>{c.bid_cents_per_impression}¢/imp</b></span>
              <span>PACING<b>{c.pacing}</b></span>
            </div>
            <div className="asset-meta-row" style={{ fontSize: 10, color: "#888892" }}>
              Markets: {(c.targeting_json?.markets || []).join(", ")} · Dayparts: {(c.targeting_json?.dayparts || []).join(", ") || "any"}
            </div>
            <div className="asset-actions">
              {c.status !== "active" && (
                <button type="button" className="asset-btn primary"
                  onClick={() => act(c.campaign_id, "approve")} disabled={busy === c.campaign_id}
                  data-testid={`approve-${c.campaign_id}`}>
                  <CheckCircle size={12} /> APPROVE
                </button>
              )}
              {c.status === "active" && (
                <button type="button" className="asset-btn"
                  onClick={() => act(c.campaign_id, "pause")} disabled={busy === c.campaign_id}
                  data-testid={`pause-${c.campaign_id}`}>
                  <Pause size={12} /> PAUSE
                </button>
              )}
              {c.status !== "rejected" && (
                <button type="button" className="asset-btn"
                  onClick={() => act(c.campaign_id, "reject")} disabled={busy === c.campaign_id}
                  data-testid={`reject-${c.campaign_id}`}>
                  <XCircle size={12} /> REJECT
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
