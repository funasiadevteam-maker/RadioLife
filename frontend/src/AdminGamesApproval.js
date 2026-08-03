// Phase 23 Session 5 — Admin moderation workspace.
//
// Upgraded from the basic Phase 8a queue into a real moderation
// surface with: queue-stats strip, bulk-approve, reject reason
// taxonomy modal, side drawer with deep-link, and a "Scratch a
// sample" preview for scratch_card campaigns.
//
// Backend contracts (Phase 23 S5):
//   GET    /games_v2/admin/queue
//   GET    /games_v2/admin/campaigns/queue-stats
//   GET    /games_v2/admin/campaigns/reject-reasons
//   GET    /games_v2/admin/campaigns/{id}/detail
//   POST  /games_v2/admin/campaigns/{id}/approve
//   POST  /games_v2/admin/campaigns/{id}/reject  (taxonomy-aware)
//   POST  /games_v2/admin/campaigns/bulk-approve
import { useEffect, useMemo, useState, useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  ChevronLeft, Check, X, Loader2, Plus, ShieldCheck, Eye,
  Clock, ListChecks, AlertTriangle, BarChart3,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import ScratchCardGame from "@/components/games/ScratchCardGame";
import "./PlayAndWin.css";


function StatCard({ label, value, icon: Icon, testid }) {
  return (
    <div className="admin-stat-card" data-testid={testid}>
      <div className="admin-stat-icon"><Icon size={16} /></div>
      <div>
        <div className="admin-stat-value">
          {value === null || value === undefined ? "—" : value}
        </div>
        <div className="admin-stat-label">{label}</div>
      </div>
    </div>
  );
}


function RejectModal({ open, onClose, onSubmit, submitting, reasons }) {
  const [code, setCode]    = useState("");
  const [notes, setNotes] = useState("");
  useEffect(() => {
    if (open) { setCode(""); setNotes(""); }
  }, [open]);
  if (!open) return null;
  const requiresNotes = code === "other";
  const canSubmit = code && (!requiresNotes || notes.trim().length > 0);
  return (
    <div className="admin-modal-backdrop"
            onClick={onClose}
            data-testid="reject-modal-backdrop">
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}
              data-testid="reject-modal">
        <h3>Reject campaign</h3>
        <p className="dim">Pick a reason from the taxonomy. Notes are
            optional unless reason is <b>Other</b>.</p>
        <label className="admin-modal-label">Reason</label>
        <select value={code} onChange={(e) => setCode(e.target.value)}
                    data-testid="reject-reason-select"
                    className="admin-modal-input">
          <option value="">— Select —</option>
          {reasons.map((r) => (
            <option key={r.code} value={r.code}>{r.label}</option>
          ))}
        </select>
        <label className="admin-modal-label">Notes
            {requiresNotes && <span className="dim"> (required)</span>}</label>
        <textarea value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          rows={4}
                          data-testid="reject-notes-textarea"
                          className="admin-modal-input"
                          placeholder="Additional context for the advertiser…" />
        <div className="admin-modal-actions">
          <button className="btn-ghost" onClick={onClose}
                      data-testid="reject-modal-cancel">Cancel</button>
          <button className="btn-danger"
                      disabled={!canSubmit || submitting}
                      onClick={() => onSubmit({reason_code: code,
                                                                reason_notes: notes.trim() || null})}
                      data-testid="reject-modal-submit">
            {submitting ? <Loader2 size={12} className="spin"/> : <X size={12}/>}
            Confirm reject
          </button>
        </div>
      </div>
    </div>
  );
}


function ScratchPreviewModal({ open, onClose, brand }) {
  if (!open) return null;
  return (
    <div className="admin-modal-backdrop" onClick={onClose}
            data-testid="scratch-preview-modal">
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}
              style={{ maxWidth: 540 }}>
        <h3>Foil preview</h3>
        <p className="dim">Drag your cursor on the foil to verify the
            brand-tint matches your campaign palette.</p>
        <ScratchCardGame
          config={{ type: "scratch_card",
                          sponsor_name: "PREVIEW",
                          prize_preview: { title: "Sample Prize",
                                                          value: "AED 25" } }}
          onSubmit={() => {}}
          submitting={false} result={null}
          brand={brand || "#ff2d95"} />
        <div className="admin-modal-actions">
          <button className="btn-ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}


function Drawer({ campaignId, onClose, onApprove, onRejectClick }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scratchPreview, setScratchPreview] = useState(false);

  useEffect(() => {
    if (!campaignId) return;
    setLoading(true);
    axios.get(`${API}/games_v2/admin/campaigns/${campaignId}/detail`)
      .then((r) => setDetail(r.data))
      .catch(() => toast.error("Failed to load campaign"))
      .finally(() => setLoading(false));
  }, [campaignId]);

  if (!campaignId) return null;
  const c       = detail?.campaign;
  const isScratch = c?.template_id === "tpl_scratch_card";
  const brand = c?.brand_colors_json?.primary || "#ff2d95";
  const math = detail?.math;
  const overBudget = math?.over_budget_pct;

  return (
    <div className="admin-drawer-backdrop" onClick={onClose}
            data-testid="campaign-drawer-backdrop">
      <aside className="admin-drawer" onClick={(e) => e.stopPropagation()}
                  data-testid="campaign-drawer">
        <header className="admin-drawer-head">
          <button onClick={onClose} className="btn-ghost"
                      data-testid="drawer-close">
            <X size={14}/> Close
          </button>
          {loading && <Loader2 size={16} className="spin"/>}
        </header>

        {detail && (
          <>
            <div className="admin-drawer-meta">
              <span className="brand-swatch"
                          style={{background: brand}}
                          data-testid="drawer-brand-swatch"/>
              <div>
                <div className="mono dim">{c.campaign_id}</div>
                <h2 data-testid="drawer-title">{c.title}</h2>
                <div className="dim small">
                  {c.advertiser_name || c.creator_type}
                  {" · "}
                  <code>{c.template_id}</code>
                  {" · "}
                  <span className={`status-pill status-${c.status}`}
                              data-testid="drawer-status">{c.status}</span>
                </div>
              </div>
            </div>

            <section className="admin-drawer-section">
              <h4><BarChart3 size={12}/> Win-rate math</h4>
              <div className="math-grid">
                <div><b>Expected payout / play:</b>{" "}
                  <span data-testid="math-payout-per-play">
                    {math.expected_payout_per_play}
                  </span></div>
                <div><b>Max redemptions:</b> {math.max_total_redemptions}</div>
                <div><b>Expected total cost:</b>{" "}
                  <span data-testid="math-expected-cost">
                    {math.expected_redemption_cost}
                  </span></div>
                <div><b>Budget:</b> {math.max_budget}</div>
              </div>
              {overBudget !== null && (
                <div className="math-warn" data-testid="math-warning">
                  <AlertTriangle size={12}/>
                  Expected payout exceeds budget by {overBudget}%
                </div>
              )}
            </section>

            <section className="admin-drawer-section">
              <h4>Prizes ({detail.prizes.length})</h4>
              <ul className="drawer-prize-list">
                {detail.prizes.map((p) => (
                  <li key={p.prize_id}>
                    <b>{p.title}</b>
                    <span className="mono dim">
                      weight {p.probability_weight} ·
                      {" "}inv {p.inventory_total} ·
                      {" "}{p.value_amount} {p.value_currency || ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section className="admin-drawer-section">
              <h4>Targeting & placement</h4>
              <pre className="drawer-json mono">
{JSON.stringify({targeting: detail.targeting,
                                placement_rules: detail.placement_rules,
                                win_rules: detail.win_rules}, null, 2)}
              </pre>
            </section>

            {isScratch && (
              <section className="admin-drawer-section">
                <button className="btn-ghost"
                            onClick={() => setScratchPreview(true)}
                            data-testid="drawer-scratch-preview-btn">
                  🪙 Scratch a sample
                </button>
              </section>
            )}

            <footer className="admin-drawer-actions">
              <button className="btn-danger"
                          onClick={() => onRejectClick(campaignId)}
                          data-testid="drawer-reject">
                <X size={12}/> Reject
              </button>
              <button className="btn-primary"
                          onClick={() => onApprove(campaignId)}
                          disabled={c.status !== "pending_approval"}
                          data-testid="drawer-approve">
                <Check size={12}/> Approve
              </button>
            </footer>
          </>
        )}
        <ScratchPreviewModal open={scratchPreview}
                                                  onClose={() => setScratchPreview(false)}
                                                  brand={brand}/>
      </aside>
    </div>
  );
}


export default function AdminGamesApproval() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items,    setItems]    = useState([]);
  const [stats,    setStats]    = useState(null);
  const [reasons,  setReasons]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [rejectingId, setRejectingId] = useState(null);
  const [rejectSubmitting, setRejectSubmitting] = useState(false);
  const [drawerId, setDrawerId] = useState(
    searchParams.get("campaign_id") || null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [qr, sr] = await Promise.all([
        axios.get(`${API}/games_v2/admin/queue`),
        axios.get(`${API}/games_v2/admin/campaigns/queue-stats`),
      ]);
      setItems(qr.data.items || []);
      setStats(sr.data);
    } catch (_e) { toast.error("Failed to load queue"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
    if (user.role !== "admin") {
      toast.error("Admin role required"); navigate("/");
      return;
    }
    reload();
    axios.get(`${API}/games_v2/admin/campaigns/reject-reasons`)
      .then((r) => setReasons(r.data.reasons))
      .catch(() => {});
  }, [user, authLoading, reload, navigate]);

  // Deep-link sync: keep URL in step with drawer state.
  useEffect(() => {
    if (drawerId) setSearchParams({ campaign_id: drawerId });
    else if (searchParams.get("campaign_id")) setSearchParams({});
  }, [drawerId]); // eslint-disable-line

  const toggleSelected = (cid) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  };
  const selectAll = () => {
    setSelected(new Set(items.map((c) => c.campaign_id)));
  };
  const clearSelection = () => setSelected(new Set());

  const approveOne = async (cid) => {
    if (!window.confirm("Approve this campaign?")) return;
    try {
      await axios.post(`${API}/games_v2/admin/campaigns/${cid}/approve`);
      toast.success("Approved & live");
      setDrawerId(null);
      reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Approval failed");
    }
  };

  const bulkApprove = async () => {
    const ids = [...selected];
    if (!ids.length) return;
    if (!window.confirm(`Approve ${ids.length} campaigns?`)) return;
    try {
      const r = await axios.post(
        `${API}/games_v2/admin/campaigns/bulk-approve`,
        { campaign_ids: ids });
      const ok    = r.data.approved_count;
      const fail = r.data.failed_count;
      if (fail) toast.warning(`Approved ${ok} of ${ok + fail} — ${fail} failed`);
      else        toast.success(`Approved ${ok} campaigns`);
      clearSelection();
      reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Bulk approval failed");
    }
  };

  const submitReject = async ({ reason_code, reason_notes }) => {
    if (!rejectingId) return;
    setRejectSubmitting(true);
    try {
      await axios.post(
        `${API}/games_v2/admin/campaigns/${rejectingId}/reject`,
        { reason_code, reason_notes });
      toast.success("Rejected");
      setRejectingId(null);
      setDrawerId(null);
      reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Reject failed");
    } finally {
      setRejectSubmitting(false);
    }
  };

  const allSelected = useMemo(() =>
    items.length > 0 && selected.size === items.length,
    [items, selected]);

  if (authLoading || !user) {
    return <div className="paw-loading"><Loader2 size={28} className="spin"/></div>;
  }

  return (
    <div className="advgames-wrap" data-testid="admin-games-approval-page">
      <Toaster theme="dark" position="bottom-right" richColors/>
      <header className="paw-header">
        <div>
          <Link to="/" className="paw-back"><ChevronLeft size={14}/> back</Link>
          <h1><ShieldCheck size={20}/> Game approvals</h1>
          <p className="sub">{items.length} pending review</p>
        </div>
        <Link to="/admin/games/new" className="lobbies-host-btn"
                  data-testid="admin-create-game-btn">
          <Plus size={14}/> Admin create game
        </Link>
      </header>

      {/* Queue-stats strip */}
      <section className="admin-stat-strip" data-testid="admin-stat-strip">
        <StatCard label="Pending"
                          value={stats?.pending}
                          icon={ListChecks}
                          testid="stat-pending"/>
        <StatCard label="Approved today"
                          value={stats?.approved_today}
                          icon={Check}
                          testid="stat-approved-today"/>
        <StatCard label="Rejected today"
                          value={stats?.rejected_today}
                          icon={X}
                          testid="stat-rejected-today"/>
        <StatCard label="Median decision (min)"
                          value={stats?.avg_decision_minutes}
                          icon={Clock}
                          testid="stat-avg-decision"/>
      </section>

      {/* Bulk-approve toolbar */}
      {items.length > 0 && (
        <div className="admin-bulk-toolbar" data-testid="admin-bulk-toolbar">
          <label>
            <input type="checkbox"
                        checked={allSelected}
                        onChange={(e) => e.target.checked ? selectAll()
                                                                            : clearSelection()}
                        data-testid="select-all-checkbox"/>
            {" "}Select all
          </label>
          <button className="btn-primary"
                      disabled={selected.size === 0}
                      onClick={bulkApprove}
                      data-testid="bulk-approve-btn">
            <Check size={12}/> Approve selected ({selected.size})
          </button>
        </div>
      )}

      {loading ? (
        <div className="paw-loading"><Loader2 size={28} className="spin"/></div>
      ) : items.length === 0 ? (
        <div className="paw-empty" data-testid="admin-empty">
          <Check size={28}/>
          <p>Inbox zero — all campaigns processed.</p>
        </div>
      ) : (
        <div className="admin-queue">
          {items.map((c) => (
            <div className="admin-queue-card" key={c.campaign_id}
                    data-testid={`admin-queue-card-${c.campaign_id}`}>
              <div className="aqc-head">
                <input type="checkbox"
                            checked={selected.has(c.campaign_id)}
                            onChange={() => toggleSelected(c.campaign_id)}
                            data-testid={`select-${c.campaign_id}`}/>
                <div className="aqc-info"
                          onClick={() => setDrawerId(c.campaign_id)}
                          style={{cursor: "pointer", flex: 1}}>
                  <span className="mono dim">{c.campaign_id}</span>
                  <h3>{c.title}</h3>
                  <div className="aqc-meta mono dim">
                    {c.sponsor_name} · {c.template_id?.replace("tpl_", "")} ·
                    {" "}objective <b>{c.objective}</b>
                  </div>
                </div>
                <div className="aqc-actions">
                  <button className="btn-ghost"
                              onClick={() => setDrawerId(c.campaign_id)}
                              data-testid={`admin-preview-${c.campaign_id}`}>
                    <Eye size={12}/> Preview
                  </button>
                  <button className="btn-danger"
                              onClick={() => setRejectingId(c.campaign_id)}
                              data-testid={`admin-reject-${c.campaign_id}`}>
                    <X size={12}/> Reject
                  </button>
                  <button className="btn-primary"
                              onClick={() => approveOne(c.campaign_id)}
                              data-testid={`admin-approve-${c.campaign_id}`}>
                    <Check size={12}/> Approve
                  </button>
                </div>
              </div>
              <div className="aqc-prizes" data-testid={`prizes-${c.campaign_id}`}>
                {c.prizes_preview?.map((p, i) => (
                  <div className="aqc-prize" key={i}>
                    <b>{p.title}</b>
                    <span className="mono">{p.probability_weight}% · inv {p.inventory_total}</span>
                    <span className="mono dim">{p.value_amount}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <RejectModal open={!!rejectingId}
                              onClose={() => setRejectingId(null)}
                              onSubmit={submitReject}
                              submitting={rejectSubmitting}
                              reasons={reasons}/>

      <Drawer campaignId={drawerId}
                  onClose={() => setDrawerId(null)}
                  onApprove={approveOne}
                  onRejectClick={(cid) => { setDrawerId(null); setRejectingId(cid); }}/>
    </div>
  );
}
