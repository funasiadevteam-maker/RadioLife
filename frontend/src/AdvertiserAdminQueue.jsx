// Phase 18a — Admin pending-review queue for advertiser campaigns.
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Check, X, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdvertiserCampaignsAdminQueue() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [rejecting, setRejecting] = useState(null);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState("pending_review");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/advertiser/campaigns?status=${status}`);
      setItems(r.data.items || []);
    } catch { setItems([]); }
    setLoading(false);
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const approve = async (cid) => {
    try { await axios.post(`${API}/admin/advertiser/campaigns/${cid}/approve`);
      toast.success("approved"); load(); }
    catch (e) { toast.error("approve failed"); }
  };
  const reject = async () => {
    try { await axios.post(`${API}/admin/advertiser/campaigns/${rejecting}/reject`,
                                            { reason });
      toast.success("rejected"); setRejecting(null); setReason(""); load(); }
    catch (e) { toast.error("reject failed"); }
  };

  return (
    <div className="min-h-screen bg-bg-base text-text-primary p-6 space-y-4"
              data-testid="admin-adv-queue">
      <div className="flex items-end justify-between">
        <h1 className="font-display font-bold text-2xl">Advertiser campaign queue</h1>
        <select className="bigfm-input" value={status} onChange={(e) => setStatus(e.target.value)}
                    data-testid="queue-status-filter">
          <option value="pending_review">pending_review</option>
          <option value="active">active</option>
          <option value="rejected">rejected</option>
        </select>
      </div>
      {loading ? <Loader2 className="animate-spin" /> :
        items.length === 0 ? (
          <p className="text-text-secondary" data-testid="queue-empty">Nothing to review.</p>
        ) : (
          <div className="space-y-2" data-testid="queue-list">
            {items.map((c) => (
              <div key={c.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 flex items-center gap-3"
                    data-testid={`queue-row-${c.id}`}>
                <div className="flex-1 min-w-0">
                  <div className="font-display font-bold flex items-center flex-wrap gap-1">
                    <span>{c.name}</span>
                    {c.takeover_config?.enabled && (
                      <span data-testid={`takeover-pill-${c.id}`}
                                className="ml-2 inline-flex items-center gap-1 rounded-full
                                              bg-amber-500/15 text-amber-300 px-2 py-0.5 text-xs">
                        🌟 Takeover · {_window_hours(c.takeover_config)}h on {c.takeover_config.channel_slug}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-text-secondary">
                    {c.advertiser_name || c.advertiser_id} · ${c.budget_total_usd} · {c.objective}
                  </div>
                </div>
                <button onClick={() => approve(c.id)}
                            className="bigfm-cta" data-testid={`approve-${c.id}`}>
                  <Check size={14} /> Approve
                </button>
                <button onClick={() => setRejecting(c.id)}
                            className="bigfm-cta-ghost" data-testid={`reject-${c.id}`}>
                  <X size={14} /> Reject
                </button>
              </div>
            ))}
          </div>
        )}
      {rejecting && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50"
                onClick={() => setRejecting(null)}>
          <div className="bg-bg-base border border-white/[0.10] rounded-2xl p-6 max-w-md w-full space-y-3"
                onClick={(e) => e.stopPropagation()} data-testid="reject-modal">
            <h3 className="font-display font-bold text-xl">Reject reason</h3>
            <textarea className="bigfm-input w-full h-24" value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Tell the advertiser why..."
                          data-testid="reject-reason-input" />
            <div className="flex gap-2">
              <button className="bigfm-cta-ghost flex-1" onClick={() => setRejecting(null)}>Cancel</button>
              <button className="bigfm-cta flex-1" onClick={reject} data-testid="reject-confirm">
                Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function _window_hours(tc) {
  try {
    const a = new Date(tc.window_start), b = new Date(tc.window_end);
    return Math.max(1, Math.round((b - a) / 36e5));
  } catch { return 2; }
}
