/** Phase 42-D2 — Admin: Grants + Voucher codes.
 *
 *  Route: `/admin/subscriptions`
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Plus, Loader2, ShieldCheck, X, Copy, RefreshCw, Check,
  Crown, Ticket, Trash2,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";

const API = process.env.REACT_APP_BACKEND_URL;

function GrantCard() {
  const [userId, setUserId] = useState("");
  const [plan, setPlan]      = useState("premium");
  const [days, setDays]      = useState(30);
  const [busy, setBusy]      = useState(false);
  const [last, setLast]      = useState(null);

  const submit = async () => {
    if (!userId.trim()) { toast.error("Enter a user_id"); return; }
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/api/admin/subscriptions/grant`,
        { user_id: userId.trim(), plan,
            duration_days: parseInt(days, 10) || 30 },
        { withCredentials: true });
      setLast(r.data);
      toast.success(`Granted ${plan} until ${new Date(r.data.expires_at).toLocaleDateString()}`);
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "grant_failed");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="admin-grant-card"
          className="rounded-xl border border-white/[0.10] bg-white/[0.03] p-5">
      <div className="text-xs uppercase tracking-widest text-cyan-300/80
                              font-mono inline-flex items-center gap-1 mb-3">
        <Crown size={11} /> Grant Premium / Trial
      </div>
      <p className="text-xs text-white/50 mb-4">
        Apply a direct, audited subscription grant to any user (no Stripe
        round-trip).  Stamps the same fields the trial endpoint writes.
      </p>
      <div className="space-y-3">
        <div>
          <label className="block text-[11px] text-white/60 mb-1">User ID</label>
          <input
            type="text" value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="user_demo_8b88c27e0f"
            data-testid="admin-grant-userid"
            className="w-full px-3 h-9 rounded-lg bg-black/40
                              border border-white/[0.10] text-sm
                              placeholder:text-white/30 font-mono
                              focus:border-cyan-400/50 focus:outline-none" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[11px] text-white/60 mb-1">Plan</label>
            <select value={plan}
                          onChange={(e) => setPlan(e.target.value)}
                          data-testid="admin-grant-plan"
                          className="w-full px-3 h-9 rounded-lg bg-black/40
                                          border border-white/[0.10] text-sm
                                          focus:border-cyan-400/50 focus:outline-none">
              <option value="premium">Premium</option>
              <option value="trial">Trial</option>
            </select>
          </div>
          <div>
            <label className="block text-[11px] text-white/60 mb-1">Duration (days)</label>
            <input type="number" value={days} min={1} max={3650}
                          onChange={(e) => setDays(e.target.value)}
                          data-testid="admin-grant-days"
                          className="w-full px-3 h-9 rounded-lg bg-black/40
                                          border border-white/[0.10] text-sm
                                          focus:border-cyan-400/50 focus:outline-none" />
          </div>
        </div>
      </div>
      <button onClick={submit} disabled={busy}
                      data-testid="admin-grant-submit"
                      className="inline-flex items-center gap-2 px-4 h-9 mt-4
                                      rounded-full bg-cyan-400 text-slate-900
                                      text-xs font-semibold hover:bg-cyan-300
                                      disabled:opacity-50">
        {busy && <Loader2 size={12} className="animate-spin" />}
        <ShieldCheck size={12} /> Apply grant
      </button>
      {last && (
        <div className="mt-4 text-[11px] font-mono text-emerald-300
                                bg-emerald-400/[0.06] border border-emerald-400/30
                                rounded-lg p-3"
                  data-testid="admin-grant-result">
          ✓ {last.user_id} → {last.plan} until {new Date(last.expires_at).toLocaleString()}<br/>
          grant_id: {last.grant_id}
        </div>
      )}
    </div>
  );
}

function VoucherCreateModal({ open, onClose, onCreated }) {
  const [plan, setPlan]    = useState("premium");
  const [days, setDays]    = useState(30);
  const [max, setMax]      = useState(1);
  const [code, setCode]    = useState("");
  const [busy, setBusy]    = useState(false);
  if (!open) return null;
  const submit = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/api/admin/vouchers/create`, {
        plan, duration_days: parseInt(days, 10) || 30,
        max_redemptions: parseInt(max, 10) || 1,
        code: code.trim() || undefined,
      }, { withCredentials: true });
      toast.success(`Created voucher ${r.data.code}`);
      onCreated?.(r.data);
      onClose?.();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "voucher_create_failed");
    } finally { setBusy(false); }
  };
  return (
    <div data-testid="voucher-create-modal"
          onClick={onClose}
          className="fixed inset-0 z-50 bg-black/70 flex items-center
                              justify-center p-4">
      <div onClick={(e) => e.stopPropagation()}
              className="bg-[#0a0a0c] border border-white/[0.10]
                              rounded-2xl w-full max-w-[460px] p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="text-sm font-semibold">Create voucher code</div>
          <button onClick={onClose}
                          data-testid="voucher-create-close"
                          className="p-1.5 rounded hover:bg-white/[0.08]">
            <X size={14} />
          </button>
        </div>
        <div className="space-y-3 text-sm">
          <div>
            <label className="block text-[11px] text-white/60 mb-1">Code (optional)</label>
            <input type="text" value={code}
                          onChange={(e) => setCode(e.target.value.toUpperCase())}
                          data-testid="voucher-create-code"
                          placeholder="Leave blank for auto-generated"
                          className="w-full px-3 h-9 rounded-lg bg-black/40
                                          border border-white/[0.10] font-mono text-sm" />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-[11px] text-white/60 mb-1">Plan</label>
              <select value={plan} onChange={(e) => setPlan(e.target.value)}
                              data-testid="voucher-create-plan"
                              className="w-full px-2 h-9 rounded-lg bg-black/40
                                              border border-white/[0.10] text-sm">
                <option value="premium">Premium</option>
                <option value="trial">Trial</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] text-white/60 mb-1">Days</label>
              <input type="number" value={days} min={1}
                          onChange={(e) => setDays(e.target.value)}
                          data-testid="voucher-create-days"
                          className="w-full px-2 h-9 rounded-lg bg-black/40
                                          border border-white/[0.10] text-sm" />
            </div>
            <div>
              <label className="block text-[11px] text-white/60 mb-1">Max use</label>
              <input type="number" value={max} min={1}
                          onChange={(e) => setMax(e.target.value)}
                          data-testid="voucher-create-max"
                          className="w-full px-2 h-9 rounded-lg bg-black/40
                                          border border-white/[0.10] text-sm" />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} disabled={busy}
                          data-testid="voucher-create-cancel"
                          className="px-3 h-9 rounded-full bg-white/[0.06] text-xs">
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                          data-testid="voucher-create-submit"
                          className="inline-flex items-center gap-1.5 px-4 h-9
                                          rounded-full bg-cyan-400 text-slate-900
                                          text-xs font-semibold disabled:opacity-50">
            {busy && <Loader2 size={12} className="animate-spin" />}
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

function VoucherList() {
  const [items, setItems]            = useState([]);
  const [loading, setLoading]      = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [busyId, setBusyId]          = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/api/admin/vouchers`,
                                                          { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_e) { setItems([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const revoke = async (v) => {
    setBusyId(v.voucher_id);
    try {
      await axios.post(`${API}/api/admin/vouchers/${v.voucher_id}/revoke`,
                                    {}, { withCredentials: true });
      toast.success(`Revoked ${v.code}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail?.code || "revoke_failed");
    } finally { setBusyId(null); }
  };

  const copy = (code) => {
    navigator.clipboard?.writeText(code);
    toast.success(`Copied ${code}`);
  };

  return (
    <div data-testid="admin-voucher-list"
          className="rounded-xl border border-white/[0.10] bg-white/[0.03] p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs uppercase tracking-widest text-cyan-300/80
                                font-mono inline-flex items-center gap-1">
          <Ticket size={11} /> Voucher codes
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load}
                          data-testid="admin-voucher-refresh"
                          className="p-1.5 rounded bg-white/[0.06]
                                          hover:bg-white/[0.10] text-white/70">
            <RefreshCw size={12} />
          </button>
          <button onClick={() => setCreateOpen(true)}
                          data-testid="admin-voucher-create-open"
                          className="inline-flex items-center gap-1.5 px-3 h-7
                                          rounded-full bg-cyan-400 text-slate-900
                                          text-[11px] font-semibold">
            <Plus size={11} /> New voucher
          </button>
        </div>
      </div>
      {loading ? (
        <div className="py-8 flex items-center justify-center text-white/50">
          <Loader2 size={14} className="animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div data-testid="admin-voucher-empty"
                  className="py-8 text-center text-xs text-white/40">
          No vouchers yet.  Click "New voucher" to create one.
        </div>
      ) : (
        <ul className="space-y-2 max-h-[420px] overflow-y-auto">
          {items.map((v) => (
            <li key={v.voucher_id}
                    data-testid={`admin-voucher-row-${v.voucher_id}`}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg
                                      bg-black/30 border border-white/[0.06]">
              <div className="font-mono text-sm text-white flex-grow">
                {v.code}
                <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded
                                                    ${v.active
                                                      ? "bg-emerald-400/15 text-emerald-300 border border-emerald-400/30"
                                                      : "bg-rose-400/15 text-rose-300 border border-rose-400/30"}`}>
                  {v.active ? "ACTIVE" : "REVOKED"}
                </span>
              </div>
              <div className="text-[11px] text-white/50 font-mono">
                {v.plan} · {v.duration_days}d · {v.redemptions_count}/{v.max_redemptions}
              </div>
              <button onClick={() => copy(v.code)}
                              data-testid={`admin-voucher-copy-${v.voucher_id}`}
                              className="p-1.5 rounded hover:bg-white/[0.08]
                                              text-white/60">
                <Copy size={12} />
              </button>
              {v.active && (
                <button onClick={() => revoke(v)}
                                disabled={busyId === v.voucher_id}
                                data-testid={`admin-voucher-revoke-${v.voucher_id}`}
                                className="p-1.5 rounded hover:bg-rose-500/15
                                                text-rose-300/80 hover:text-rose-300
                                                disabled:opacity-40">
                  {busyId === v.voucher_id
                    ? <Loader2 size={12} className="animate-spin" />
                    : <Trash2 size={12} />}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <VoucherCreateModal open={createOpen}
                                              onClose={() => setCreateOpen(false)}
                                              onCreated={load} />
    </div>
  );
}

export default function AdminSubscriptions() {
  return (
    <div data-testid="admin-subscriptions-page"
          className="flex bg-[#050507] text-white min-h-[100vh]">
      <Toaster richColors theme="dark" position="top-right" />
      <AdminSubNav />
      <main className="flex-grow px-6 py-6 max-w-[1200px]">
        <div className="text-xs uppercase tracking-widest text-white/40
                                font-mono mb-1">Subscriptions</div>
        <h1 className="text-2xl font-bold tracking-tight mb-6">
          Grants &amp; voucher codes
        </h1>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <GrantCard />
          <VoucherList />
        </div>
      </main>
    </div>
  );
}
