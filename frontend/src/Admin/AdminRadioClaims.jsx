/** Phase 42-C — Admin: Station claim queue.
 *
 *  Route: `/admin/radio/claims`
 *
 *  Lists pending station claims; admin can approve / reject (with reason).
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Toaster, toast } from "sonner";
import {
  Loader2, Check, X, Mail, ShieldCheck, AlertTriangle,
  Building2, Radio as RadioIcon, ExternalLink, RefreshCw,
  FileText, Image as ImageIcon,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";
// Phase CLAIM.1b — design variant.
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = process.env.REACT_APP_BACKEND_URL;
const URL = `${API}/api/admin/radio/claims`;
const EDITS_URL = `${API}/api/admin/station-edits`;

const FILTERS = [
  { value: "submitted",  label: "Pending review" },
  { value: "verifying",  label: "Verifying" },
  { value: "approved",   label: "Approved" },
  { value: "rejected",   label: "Rejected" },
  { value: "abandoned",  label: "Abandoned" },
  { value: "all",        label: "All" },
];

function VerificationBadge({ method }) {
  if (method === "email_domain") {
    return (
      <span data-testid="admin-claim-method-email"
            className="inline-flex items-center gap-1 px-2 h-6 rounded-full
                       bg-emerald-400/15 border border-emerald-400/30
                       text-emerald-300 text-[10px] font-mono">
        <Mail size={10} /> EMAIL DOMAIN
      </span>
    );
  }
  return (
    <span data-testid="admin-claim-method-manual"
          className="inline-flex items-center gap-1 px-2 h-6 rounded-full
                     bg-amber-400/15 border border-amber-400/30
                     text-amber-200 text-[10px] font-mono">
      <ShieldCheck size={10} /> MANUAL REVIEW
    </span>
  );
}

function StatusBadge({ status }) {
  const map = {
    submitted: { c: "amber",    label: "Pending" },
    verifying: { c: "cyan",     label: "Verifying" },
    approved:  { c: "emerald",  label: "Approved" },
    rejected:  { c: "rose",     label: "Rejected" },
    abandoned: { c: "slate",    label: "Abandoned" },
  };
  const m = map[status] || { c: "slate", label: status };
  const cls = {
    amber: "bg-amber-400/15 border-amber-400/30 text-amber-200",
    cyan: "bg-cyan-400/15 border-cyan-400/30 text-cyan-200",
    emerald: "bg-emerald-400/15 border-emerald-400/30 text-emerald-200",
    rose: "bg-rose-400/15 border-rose-400/30 text-rose-200",
    slate: "bg-white/[0.06] border-white/[0.10] text-white/60",
  }[m.c];
  return (
    <span data-testid={`admin-claim-status-${status}`}
          className={`inline-flex items-center gap-1 px-2 h-6 rounded-full
                      text-[10px] font-mono ${cls}`}>
      {m.label.toUpperCase()}
    </span>
  );
}

function RejectModal({ claim, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!reason.trim()) {
      toast.error("Please provide a reason for the claimant.");
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${URL}/${claim.id}/reject`,
                        { reason: reason.trim() },
                        { withCredentials: true });
      toast.success("Claim rejected");
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "reject_failed");
    } finally { setBusy(false); }
  };
  return (
    <div data-testid="admin-claim-reject-modal"
         className="fixed inset-0 z-50 bg-black/70 flex items-center
                    justify-center p-4">
      <div className="bg-[#0a0a0c] border border-white/[0.10]
                      rounded-2xl w-full max-w-[520px] p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-white/40
                            font-mono">Reject claim</div>
            <div className="font-semibold mt-1 text-white truncate">
              {claim.station_name_snapshot}
            </div>
          </div>
          <button onClick={onClose}
                  data-testid="admin-claim-reject-close"
                  className="p-1.5 rounded hover:bg-white/[0.06]
                             text-white/60">
            <X size={16} />
          </button>
        </div>
        <label className="block text-xs text-white/60 mb-1">
          Reason (sent to claimant for audit)
        </label>
        <textarea value={reason} rows={4}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="admin-claim-reject-reason"
                  placeholder="e.g. Contact email does not match station homepage; please re-submit with a press@<domain> address."
                  className="w-full px-3 py-2 rounded-lg bg-black/40
                             border border-white/[0.10] text-sm
                             placeholder:text-white/30
                             focus:border-rose-400/50 focus:outline-none
                             resize-y" />
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={busy}
                  data-testid="admin-claim-reject-cancel"
                  className="px-4 h-9 rounded-full bg-white/[0.06]
                             hover:bg-white/[0.10] border border-white/[0.10]
                             text-xs">
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                  data-testid="admin-claim-reject-submit"
                  className="inline-flex items-center gap-2 px-4 h-9
                             rounded-full bg-rose-500 text-white
                             text-xs font-semibold hover:bg-rose-400
                             disabled:opacity-50">
            {busy && <Loader2 size={12} className="animate-spin" />}
            Reject claim
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminRadioClaims() {
  // Phase CLAIM.1b — design variant + top-level tab switcher.
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [tab, setTab] = useState("claims");
  const [status, setStatus] = useState("submitted");
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rejectFor, setRejectFor] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const fetchClaims = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${URL}?status=${status}`,
                                                    { withCredentials: true });
      setItems(r.data?.items || []);
      setCounts(r.data?.counts_by_status || {});
      setTotal(r.data?.total || 0);
    } catch (e) {
      const code = e.response?.data?.detail || e.response?.status;
      toast.error(typeof code === "string" ? code : "load_failed");
      setItems([]);
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => {
    if (tab !== "claims") return;
    fetchClaims();
  }, [tab, fetchClaims]);

  const approve = async (claim) => {
    setBusyId(claim.id);
    try {
      await axios.post(`${URL}/${claim.id}/approve`, {},
                        { withCredentials: true });
      toast.success("Claim approved · owner profile linked");
      fetchClaims();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "approve_failed");
    } finally { setBusyId(null); }
  };

  const filterChips = useMemo(() => FILTERS.map((f) => ({
    ...f,
    count: f.value === "all"
      ? Object.values(counts).reduce((a, b) => a + b, 0)
      : (counts[f.value] || 0),
  })), [counts]);

  return (
    <div data-testid="admin-radio-claims-page"
              data-status={status}
              data-variant={variant}
              data-tab={tab}
              className={"flex min-h-[100vh] " +
                                          (light ? "bg-slate-50 text-slate-900"
                                                            : "bg-[#050507] text-white")}>
      <Toaster richColors theme={light ? "light" : "dark"} position="top-right" />
      <AdminSubNav />
      <main className="flex-grow px-6 py-6 max-w-[1300px]">
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className={"text-xs uppercase tracking-widest font-mono mb-1 " +
                                          (light ? "text-slate-500" : "text-white/40")}>
              Radio · Station claims &amp; edits
            </div>
            <h1 className="text-2xl font-bold tracking-tight">Claim queue</h1>
          </div>
          <button onClick={() => (tab === "claims" ? fetchClaims() : window.location.reload())}
                          data-testid="admin-claims-refresh"
                          className={"inline-flex items-center gap-1.5 px-3 h-9 rounded-full text-xs " +
                                                (light
                                                    ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                    : "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.10]")}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>

        {/* Phase CLAIM.1b — tabs between Claims queue and Edit Requests queue. */}
        <div className="flex items-center gap-1 mb-5"
                  data-testid="admin-claims-tabs">
          {[
            { key: "claims", label: "Claims queue" },
            { key: "edits",   label: "Edit requests" },
          ].map((t) => (
            <button key={t.key}
                            onClick={() => setTab(t.key)}
                            data-testid={`admin-claims-tab-${t.key}`}
                            data-active={tab === t.key}
                            className={"px-4 h-9 text-sm rounded-full transition-colors " +
                                                  (tab === t.key
                                                      ? (light ? "bg-fuchsia-600 text-white"
                                                                          : "bg-cyan-400 text-slate-900 font-semibold")
                                                      : (light ? "bg-slate-200 text-slate-700 hover:bg-slate-300"
                                                                          : "bg-white/[0.06] text-white/70 hover:bg-white/[0.10] border border-white/[0.10]"))}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "edits" ? (
          <AdminEditRequestsQueue variant={variant} />
        ) : (
        <>
        <div className="flex flex-wrap gap-2 mb-5"
                  data-testid="admin-claims-filters">
          {filterChips.map((f) => (
            <button key={f.value}
                    onClick={() => setStatus(f.value)}
                    data-testid={`admin-claims-filter-${f.value}`}
                    data-active={status === f.value}
                    className={[
                      "inline-flex items-center gap-1.5 px-3 h-8 rounded-full",
                      "text-xs transition-colors border",
                      status === f.value
                        ? "bg-cyan-400 text-slate-900 border-cyan-400 font-semibold"
                        : "bg-white/[0.04] text-white/70 border-white/[0.10] hover:bg-white/[0.10]",
                    ].join(" ")}>
              {f.label}
              <span className={[
                "px-1.5 py-0.5 rounded text-[10px] font-mono",
                status === f.value
                  ? "bg-slate-900/20"
                  : "bg-white/[0.10] text-white/60",
              ].join(" ")}>{f.count}</span>
            </button>
          ))}
        </div>

        {loading ? (
          <div data-testid="admin-claims-loading"
               className="flex items-center gap-3 text-white/60 py-10">
            <Loader2 size={16} className="animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div data-testid="admin-claims-empty"
               className="rounded-xl border border-white/[0.10]
                          bg-white/[0.02] p-10 text-center text-white/50 text-sm">
            No claims with status <strong>{status}</strong> right now.
          </div>
        ) : (
          <ul data-testid="admin-claims-list"
              className="space-y-3">
            {items.map((c) => (
              <li key={c.id}
                  data-testid={`admin-claim-row-${c.id}`}
                  data-claim-id={c.id}
                  data-claim-status={c.claim_status}
                  className="rounded-xl border border-white/[0.10]
                             bg-white/[0.03] p-4">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex-grow min-w-0">
                    <div className="flex items-center flex-wrap gap-2 mb-2">
                      <StatusBadge status={c.claim_status} />
                      <VerificationBadge method={c.verification_method} />
                      <span className="text-[10px] font-mono text-white/40">
                        {c.id}
                      </span>
                    </div>
                    <div className="font-semibold text-white flex items-center
                                    gap-2 mb-1 flex-wrap">
                      <RadioIcon size={13} className="text-white/60" />
                      {c.station_name_snapshot}
                      {c.station_homepage_snapshot && (
                        <a href={c.station_homepage_snapshot}
                           target="_blank" rel="noopener noreferrer"
                           data-testid={`admin-claim-homepage-${c.id}`}
                           className="inline-flex items-center gap-0.5
                                      text-[11px] text-cyan-300/70
                                      hover:text-cyan-200">
                          <ExternalLink size={10} />
                        </a>
                      )}
                    </div>
                    <div className="text-xs text-white/60 flex flex-wrap
                                    gap-x-4 gap-y-1 mb-1">
                      <span className="inline-flex items-center gap-1.5">
                        <Building2 size={11} /> {c.organization_name}
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <Mail size={11} /> {c.contact_email}
                      </span>
                      <span>· {c.contact_role}</span>
                    </div>
                    <div className="text-[11px] text-white/40 font-mono mt-1">
                      Claimer: {c.claimed_by_email}
                      {" · submitted "}
                      {new Date(c.created_at).toLocaleString()}
                    </div>
                    {c.admin_rejection_reason && (
                      <div data-testid={`admin-claim-rejection-reason-${c.id}`}
                                className="mt-2 px-3 py-2 rounded-lg
                                                        bg-rose-400/[0.06] border
                                                        border-rose-400/20 text-rose-200
                                                        text-xs flex items-start gap-1.5">
                        <AlertTriangle size={11} className="mt-0.5" />
                        <span><strong>Rejection reason:</strong>{" "}
                                    {c.admin_rejection_reason}</span>
                      </div>
                    )}
                    {/* Phase CLAIM.1b — inline proof-document thumbnails. */}
                    {Array.isArray(c.proof_documents) && c.proof_documents.length > 0 && (
                      <div data-testid={`admin-claim-proofs-${c.id}`}
                                className="mt-3 flex flex-wrap gap-2">
                        {c.proof_documents.map((p, idx) => {
                          const isImg = /\.(png|jpe?g|gif|webp)$/i.test(p.filename || p.file_url || "");
                          const href = p.file_url
                                                        || `${API}/api/admin/radio/claims/${c.id}/proof/${encodeURIComponent(p.filename)}`;
                          return (
                            <a key={idx} href={href}
                                    target="_blank" rel="noopener noreferrer"
                                    data-testid={`admin-claim-${c.id}-proof-${idx}`}
                                    title={`${p.document_type || "proof"}: ${p.filename || ""}`}
                                    className={"flex flex-col items-center gap-1 " +
                                                          "w-16 rounded-md overflow-hidden border " +
                                                          (light
                                                              ? "border-slate-200 hover:border-fuchsia-400 bg-slate-50"
                                                              : "border-white/[0.10] hover:border-cyan-400 bg-white/[0.02]")}>
                              {isImg ? (
                                <img src={href} alt={p.document_type}
                                          className="w-16 h-16 object-cover"
                                          onError={(e) => { e.currentTarget.style.display = "none"; }} />
                              ) : (
                                <div className={"w-16 h-16 flex items-center justify-center " +
                                                              (light ? "text-slate-500" : "text-white/50")}>
                                  <FileText size={20} />
                                </div>
                              )}
                              <span className={"text-[9px] font-mono truncate max-w-[60px] pb-1 " +
                                                                (light ? "text-slate-500" : "text-white/50")}>
                                {(p.document_type || "").replace(/_/g, " ")}
                              </span>
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  {(c.claim_status === "submitted"
                    || c.claim_status === "verifying") && (
                    <div className="flex flex-wrap gap-2 flex-shrink-0">
                      <button onClick={() => approve(c)}
                              disabled={busyId === c.id}
                              data-testid={`admin-claim-approve-${c.id}`}
                              className="inline-flex items-center gap-1.5
                                         px-3 h-8 rounded-full
                                         bg-emerald-500 text-white text-xs
                                         font-semibold hover:bg-emerald-400
                                         disabled:opacity-50">
                        {busyId === c.id && (
                          <Loader2 size={12} className="animate-spin" />
                        )}
                        <Check size={12} /> Approve
                      </button>
                      <button onClick={() => setRejectFor(c)}
                              data-testid={`admin-claim-reject-${c.id}`}
                              className="inline-flex items-center gap-1.5
                                         px-3 h-8 rounded-full
                                         bg-white/[0.06] hover:bg-white/[0.10]
                                         border border-white/[0.10]
                                         text-rose-300 text-xs">
                        <X size={12} /> Reject
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-5 text-[11px] text-white/30">
          Showing {items.length} of {total}
        </div>
        </>
        )}
      </main>

      {rejectFor && (
        <RejectModal claim={rejectFor}
                                onClose={() => setRejectFor(null)}
                                onDone={() => { setRejectFor(null); fetchClaims(); }} />
      )}
    </div>
  );
}


// ═════════════════════════════════════════════════════════
// Phase CLAIM.1b — Admin edit-requests queue
// ═════════════════════════════════════════════════════════
function AdminEditRequestsQueue({ variant }) {
  const light = variant === "radiolife";
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [rejectFor, setRejectFor] = useState(null);
  const [reason, setReason] = useState("");

  const fetchEdits = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${EDITS_URL}?status=${status}`,
                                                          { withCredentials: true });
      setItems(r.data?.items || []);
      setTotal(r.data?.total || 0);
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "edits_load_failed");
      setItems([]);
    } finally { setLoading(false); }
  }, [status]);

  useEffect(() => { fetchEdits(); }, [fetchEdits]);

  const approve = async (row) => {
    setBusyId(row.id);
    try {
      await axios.post(`${EDITS_URL}/${row.id}/approve`, {},
                                        { withCredentials: true });
      toast.success("Edit approved · station updated");
      fetchEdits();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "approve_failed");
    } finally { setBusyId(null); }
  };

  const doReject = async () => {
    if (!reason.trim() || reason.trim().length < 3) {
      toast.error("Please write a short reason.");
      return;
    }
    setBusyId(rejectFor.id);
    try {
      await axios.post(`${EDITS_URL}/${rejectFor.id}/reject`,
                                        { review_notes: reason.trim() },
                                        { withCredentials: true });
      toast.success("Edit rejected");
      setRejectFor(null); setReason("");
      fetchEdits();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "reject_failed");
    } finally { setBusyId(null); }
  };

  const STATUS_OPTIONS = ["pending", "approved", "rejected", "withdrawn"];

  return (
    <div data-testid="admin-edits-queue">
      <div className="flex flex-wrap gap-2 mb-4">
        {STATUS_OPTIONS.map((s) => (
          <button key={s} onClick={() => setStatus(s)}
                          data-testid={`admin-edits-filter-${s}`}
                          data-active={status === s}
                          className={"px-3 h-8 rounded-full text-xs " +
                                                (status === s
                                                    ? (light ? "bg-fuchsia-600 text-white font-semibold"
                                                                      : "bg-cyan-400 text-slate-900 font-semibold")
                                                    : (light ? "bg-slate-200 text-slate-700 hover:bg-slate-300"
                                                                      : "bg-white/[0.06] text-white/70 hover:bg-white/[0.10] border border-white/[0.10]"))}>
            {s.toUpperCase()}
          </button>
        ))}
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-white/50 py-8">
          <Loader2 size={14} className="animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <div data-testid="admin-edits-empty"
                  className={"rounded-xl p-8 text-center text-sm " +
                                        (light
                                            ? "bg-slate-50 border border-slate-200 text-slate-500"
                                            : "bg-white/[0.02] border border-white/[0.10] text-white/50")}>
          No edit requests with status <strong>{status}</strong>.
        </div>
      ) : (
        <ul data-testid="admin-edits-list" className="space-y-3">
          {items.map((row) => {
            const changes = row.proposed_changes || {};
            const changeKeys = Object.keys(changes);
            return (
              <li key={row.id} data-edit-id={row.id}
                        data-testid={`admin-edit-row-${row.id}`}
                        className={"rounded-xl p-4 " +
                                              (light
                                                  ? "bg-white border border-slate-200"
                                                  : "bg-white/[0.03] border border-white/[0.10]")}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex-grow min-w-0">
                    <div className={"font-semibold flex items-center gap-2 mb-1 " +
                                                        (light ? "text-slate-900" : "text-white")}>
                      <RadioIcon size={13} />
                      {row.station_name || row.station_id}
                      <span className={"text-[10px] font-mono " +
                                                            (light ? "text-slate-400" : "text-white/40")}>
                        {row.id}
                      </span>
                    </div>
                    <div className={"text-[11px] mb-2 " +
                                                        (light ? "text-slate-500" : "text-white/40")}>
                      change_type: <strong>{row.change_type || "metadata"}</strong>
                      {" · "}submitted {new Date(row.created_at).toLocaleString()}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {changeKeys.slice(0, 6).map((k) => (
                        <span key={k}
                                    data-testid={`admin-edit-${row.id}-change-${k}`}
                                    className={"text-[10px] font-mono px-2 h-6 rounded-full inline-flex items-center " +
                                                          (light
                                                              ? "bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200"
                                                              : "bg-cyan-400/[0.08] text-cyan-200 border border-cyan-400/20")}>
                          {k}
                          {typeof changes[k] === "string" && changes[k].length > 0 && (
                            <span className={"ml-1 " +
                                                              (light ? "text-slate-500" : "text-white/50")}>
                              · {changes[k].slice(0, 20)}{changes[k].length > 20 ? "…" : ""}
                            </span>
                          )}
                        </span>
                      ))}
                      {changeKeys.length > 6 && (
                        <span className={"text-[10px] " +
                                                          (light ? "text-slate-500" : "text-white/50")}>
                          +{changeKeys.length - 6} more
                        </span>
                      )}
                    </div>
                    {/* Thumbnails for uploaded_files */}
                    {Array.isArray(row.uploaded_files) && row.uploaded_files.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {row.uploaded_files.map((f, idx) => (
                          <a key={idx} href={f.file_url}
                                target="_blank" rel="noopener noreferrer"
                                data-testid={`admin-edit-${row.id}-file-${idx}`}
                                className={"flex items-center gap-1 px-2 h-7 rounded-full text-[11px] " +
                                                      (light
                                                          ? "bg-slate-100 border border-slate-200 text-slate-700 hover:bg-slate-200"
                                                          : "bg-white/[0.04] border border-white/[0.10] text-white/70 hover:bg-white/[0.08]")}>
                            <ImageIcon size={10} /> {f.field}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                  {row.edit_status === "pending" && (
                    <div className="flex gap-2 flex-shrink-0">
                      <button onClick={() => approve(row)}
                                      disabled={busyId === row.id}
                                      data-testid={`admin-edit-${row.id}-approve`}
                                      className="inline-flex items-center gap-1.5 px-3 h-8
                                                                rounded-full bg-emerald-500 text-white
                                                                text-xs font-semibold hover:bg-emerald-400
                                                                disabled:opacity-50">
                        {busyId === row.id && <Loader2 size={12} className="animate-spin" />}
                        <Check size={12} /> Approve
                      </button>
                      <button onClick={() => { setRejectFor(row); setReason(""); }}
                                      data-testid={`admin-edit-${row.id}-reject`}
                                      className={"inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-xs " +
                                                            (light
                                                                ? "bg-rose-100 text-rose-700 hover:bg-rose-200 border border-rose-200"
                                                                : "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.10] text-rose-300")}>
                        <X size={12} /> Reject
                      </button>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <div className={"mt-5 text-[11px] " +
                                    (light ? "text-slate-400" : "text-white/30")}>
        Showing {items.length} of {total}
      </div>

      {rejectFor && (
        <div data-testid="admin-edit-reject-modal"
                  className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className={"w-full max-w-[520px] rounded-2xl p-6 " +
                                        (light
                                            ? "bg-white border border-slate-200 shadow-2xl"
                                            : "bg-[#0a0a0c] border border-white/[0.10]")}>
            <div className="flex items-center justify-between mb-4">
              <div className={"font-semibold " +
                                            (light ? "text-slate-900" : "text-white")}>
                Reject edit request
              </div>
              <button onClick={() => setRejectFor(null)}
                              className={"p-1.5 rounded " +
                                                    (light ? "text-slate-500 hover:bg-slate-100"
                                                                      : "text-white/60 hover:bg-white/[0.06]")}>
                <X size={16} />
              </button>
            </div>
            <textarea rows={4} value={reason}
                                  onChange={(e) => setReason(e.target.value)}
                                  data-testid="admin-edit-reject-reason"
                                  placeholder="Explain what needs to change before re-submitting…"
                                  className={"w-full px-3 py-2 rounded-lg text-sm resize-y " +
                                                        (light
                                                            ? "bg-slate-50 border border-slate-200 focus:border-rose-500 focus:outline-none"
                                                            : "bg-black/40 border border-white/[0.10] focus:border-rose-400/50 focus:outline-none")} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setRejectFor(null)} disabled={busyId === rejectFor.id}
                              className={"px-4 h-9 rounded-full text-xs " +
                                                    (light
                                                        ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                        : "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.10]")}>
                Cancel
              </button>
              <button onClick={doReject} disabled={busyId === rejectFor.id}
                              data-testid="admin-edit-reject-submit"
                              className="inline-flex items-center gap-2 px-4 h-9 rounded-full
                                                        bg-rose-500 text-white text-xs font-semibold
                                                        hover:bg-rose-400 disabled:opacity-50">
                {busyId === rejectFor.id && <Loader2 size={12} className="animate-spin" />}
                Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
