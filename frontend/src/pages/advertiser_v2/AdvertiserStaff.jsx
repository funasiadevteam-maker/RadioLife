// Phase AD.6 — Advertiser staff management page.
// Route: /advertiser/dashboard/staff  (inside AdvertiserShell)
// Owner + admin only.
import { useEffect, useState } from "react";
import axios from "axios";
import {
  Users, UserPlus, Loader2, CheckCircle2, XCircle, Mail, Shield,
  AlertTriangle, RefreshCw, Trash2,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const ROLES = ["manager", "redemption_staff", "analytics_only"];
const ROLE_LABEL = {
  owner:                    "Owner",
  manager:                "Manager",
  redemption_staff: "Redemption staff",
  analytics_only:    "Analytics only",
};

export default function AdvertiserStaff() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser, permissions } = useAdvertiser() || {};
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [toast, setToast] = useState(null);

  const canInvite = permissions?.has?.("can_invite_staff");

  const showToast = (kind, message) => {
    setToast({ kind, message });
    setTimeout(() => setToast(null), 4000);
  };

  async function load() {
    if (!advertiser) return;
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/advertiser-app/${advertiser.advertiser_id}/staff`);
      setData(data);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [advertiser]);

  async function changeRole(staffUserId, role) {
    setBusy(true);
    try {
      await axios.patch(
        `${API}/advertiser-app/${advertiser.advertiser_id}/staff/${staffUserId}/role`,
        { role });
      await load();
      showToast("success", `Role updated to ${ROLE_LABEL[role]}`);
    } catch (err) {
      showToast("error",
        err?.response?.data?.detail?.code || "role_update_failed");
    } finally { setBusy(false); }
  }

  async function revokeStaff(staffUserId, email) {
    if (!window.confirm(`Revoke ${email}? They lose access on the next API call.`)) return;
    setBusy(true);
    try {
      await axios.delete(
        `${API}/advertiser-app/${advertiser.advertiser_id}/staff/${staffUserId}`);
      await load();
      showToast("success", `${email} removed`);
    } catch (err) {
      showToast("error", err?.response?.data?.detail?.code || "revoke_failed");
    } finally { setBusy(false); }
  }

  async function revokeInvite(inviteId) {
    setBusy(true);
    try {
      await axios.post(
        `${API}/advertiser-app/${advertiser.advertiser_id}/staff/invites/${inviteId}/revoke`);
      await load();
      showToast("success", "Invite revoked");
    } catch (err) {
      showToast("error", err?.response?.data?.detail?.code || "revoke_failed");
    } finally { setBusy(false); }
  }

  if (!advertiser) return null;
  const cardCls = light
    ? "bg-white border border-slate-200"
    : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`space-y-6 ${light ? "text-slate-900" : "text-white"}`}
              data-testid="advertiser-staff-page">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Phase AD.6 · Team
          </div>
          <h1 className="mt-1 text-3xl font-black inline-flex items-center gap-2">
            <Users className="w-6 h-6 text-amber-500" /> Staff
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            Invite teammates to scan customer redemptions or view analytics.
          </p>
        </div>
        {canInvite && (
          <button onClick={() => setInviteOpen(true)}
                          data-testid="advertiser-staff-invite-button"
                          className="inline-flex items-center gap-2 bg-amber-500 hover:bg-amber-400 text-slate-900 font-black text-sm px-4 py-2.5 rounded-full shadow-lg shadow-amber-500/30 transition">
            <UserPlus className="w-4 h-4" /> Invite staff
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-8"
                    data-testid="advertiser-staff-loading">
          <Loader2 className="animate-spin w-4 h-4" /> Loading…
        </div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2"
                    data-testid="advertiser-staff-error">
          <AlertTriangle className="w-4 h-4" /> {String(error)}
        </div>
      ) : (
        <>
          {/* Active staff */}
          <div className={`${cardCls} rounded-2xl overflow-hidden`}
                      data-testid="advertiser-staff-table">
            <div className={`hidden md:grid grid-cols-[2fr,1.4fr,110px,90px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                      light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                    : "text-slate-500 bg-slate-950 border-b border-slate-800"
                                  }`}>
              <div>Email</div><div>Role</div><div>Active</div><div className="text-right">Actions</div>
            </div>
            {(data?.staff || []).map((row) => {
              const isOwner = row.role === "owner";
              return (
                <div key={row.staff_user_id}
                              className={`grid md:grid-cols-[2fr,1.4fr,110px,90px] gap-3 px-5 py-4 items-center ${
                                          light ? "border-b border-slate-100 last:border-0"
                                                        : "border-b border-slate-800 last:border-0"}`}
                              data-testid={`advertiser-staff-row-${row.staff_user_id}`}>
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-9 h-9 rounded-full grid place-items-center flex-shrink-0 ${
                                                      isOwner ? "bg-amber-500 text-slate-900"
                                                                      : (light ? "bg-slate-100 text-slate-600"
                                                                                        : "bg-slate-800 text-slate-300")}`}>
                      {isOwner ? <Shield className="w-4 h-4" /> : <Users className="w-4 h-4" />}
                    </div>
                    <div className="truncate">
                      <div className="font-semibold truncate">{row.email}</div>
                      <div className={`text-[10px] font-mono ${muted} truncate`}>{row.staff_user_id}</div>
                    </div>
                  </div>
                  <div>
                    {isOwner ? (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider bg-amber-500/15 text-amber-500">
                        Owner
                      </span>
                    ) : canInvite ? (
                      <select
                        disabled={busy}
                        value={row.role}
                        onChange={(e) => changeRole(row.staff_user_id, e.target.value)}
                        data-testid={`advertiser-staff-role-select-${row.staff_user_id}`}
                        className={`text-sm rounded-md px-2 py-1 ${
                                                    light ? "bg-white border border-slate-300 text-slate-900"
                                                                  : "bg-slate-950 border border-slate-800 text-white"}`}>
                        {ROLES.map((r) => (
                          <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-sm">{ROLE_LABEL[row.role] || row.role}</span>
                    )}
                  </div>
                  <div>
                    <span className={`inline-flex items-center gap-1 text-xs ${
                                                    row.active !== false ? "text-emerald-400" : "text-slate-500"}`}>
                      {row.active !== false ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                      {row.active !== false ? "Active" : "Revoked"}
                    </span>
                  </div>
                  <div className="text-right">
                    {!isOwner && canInvite && row.active !== false && (
                      <button onClick={() => revokeStaff(row.staff_user_id, row.email)}
                                      data-testid={`advertiser-staff-revoke-${row.staff_user_id}`}
                                      className="p-1.5 rounded-md text-red-400 hover:bg-red-500/10">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pending invites */}
          {(data?.invites || []).length > 0 && (
            <div className={`${cardCls} rounded-2xl overflow-hidden`}
                        data-testid="advertiser-staff-invites">
              <div className={`px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                              light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                            : "text-slate-500 bg-slate-950 border-b border-slate-800"
                                          }`}>
                Pending invites ({data.invites.length})
              </div>
              {data.invites.map((inv) => (
                <div key={inv.invite_id}
                              className={`flex items-center justify-between gap-3 px-5 py-3 text-sm ${
                                          light ? "border-b border-slate-100 last:border-0"
                                                        : "border-b border-slate-800 last:border-0"}`}
                              data-testid={`advertiser-staff-invite-${inv.invite_id}`}>
                  <div className="flex items-center gap-2 min-w-0">
                    <Mail className="w-4 h-4 text-amber-500 flex-shrink-0" />
                    <div className="min-w-0">
                      <div className="truncate">{inv.email}</div>
                      <div className={`text-[10px] font-mono ${muted}`}>
                        {ROLE_LABEL[inv.role]} · expires {inv.expires_at?.slice(0,10)}
                      </div>
                    </div>
                  </div>
                  <button onClick={() => revokeInvite(inv.invite_id)}
                                  data-testid={`advertiser-staff-invite-revoke-${inv.invite_id}`}
                                  className={`text-xs font-semibold px-3 py-1 rounded-full ${
                                              light ? "text-slate-600 hover:bg-slate-100"
                                                            : "text-slate-400 hover:bg-slate-800"}`}>
                    Revoke
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="advertiser-staff-toast">
          <div className={`${toast.kind === "error"
                                                  ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                                  : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>
            {toast.message}
          </div>
        </div>
      )}

      {inviteOpen && (
        <InviteModal
          advertiserId={advertiser.advertiser_id}
          light={light}
          onClose={() => setInviteOpen(false)}
          onSuccess={(m) => { load(); showToast("success", m); }}
          onError={(m) => showToast("error", m)}
        />
      )}
    </div>
  );
}


function InviteModal({ advertiserId, light, onClose, onSuccess, onError }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("redemption_staff");
  const [busy, setBusy] = useState(false);
  const [inviteUrl, setInviteUrl] = useState(null);

  async function submit() {
    if (!email.trim()) return;
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/advertiser-app/${advertiserId}/staff/invite`,
        { email: email.trim().toLowerCase(), role });
      setInviteUrl(data.invite_url);
      onSuccess(`Invited ${data.email} as ${data.role}`);
    } catch (err) {
      const code = err?.response?.data?.detail?.code || "invite_failed";
      onError(`Invite failed: ${code}`);
    } finally { setBusy(false); }
  }

  const bg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";
  const inputCls = `w-full px-3 py-2 rounded-lg border text-sm ${
                      light ? "bg-white border-slate-300 text-slate-900"
                                    : "bg-slate-950 border-slate-800 text-white"} focus:outline-none focus:ring-2 focus:ring-amber-500`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
              data-testid="advertiser-staff-invite-modal"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${bg} border ${border} rounded-2xl shadow-2xl max-w-md w-full`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center gap-2`}>
          <UserPlus className="w-5 h-5 text-amber-500" />
          <h2 className="text-lg font-bold">Invite staff</h2>
        </div>
        {!inviteUrl ? (
          <div className="p-6 space-y-4">
            <div>
              <label className={`block text-xs uppercase tracking-wider font-mono mb-1 ${light ? "text-slate-500" : "text-slate-400"}`}>Email</label>
              <input type="email" value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="teammate@example.com"
                            className={inputCls}
                            data-testid="advertiser-staff-invite-email" />
            </div>
            <div>
              <label className={`block text-xs uppercase tracking-wider font-mono mb-1 ${light ? "text-slate-500" : "text-slate-400"}`}>Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)}
                              className={inputCls}
                              data-testid="advertiser-staff-invite-role">
                {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
              <p className={`text-[11px] mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                {role === "manager" && "Full access to staff, redemptions, campaigns, analytics."}
                {role === "redemption_staff" && "Can scan and redeem customer wallet QRs."}
                {role === "analytics_only" && "Read-only view of campaign analytics."}
              </p>
            </div>
          </div>
        ) : (
          <div className="p-6 space-y-3" data-testid="advertiser-staff-invite-success">
            <div className="text-sm">Invite sent. Share this link if the email doesn’t arrive:</div>
            <div className={`p-3 rounded-lg font-mono text-[11px] break-all ${
                                              light ? "bg-slate-100 text-slate-700"
                                                            : "bg-slate-950 text-slate-300"}`}>
              {inviteUrl}
            </div>
            <button onClick={() => navigator.clipboard?.writeText(inviteUrl)}
                            className="text-xs font-semibold text-amber-500 hover:text-amber-400"
                            data-testid="advertiser-staff-invite-copy-link">
              Copy link
            </button>
          </div>
        )}
        <div className={`px-6 py-4 border-t ${border} flex items-center justify-end gap-2`}>
          <button onClick={onClose}
                          data-testid="advertiser-staff-invite-cancel"
                          className={`px-4 py-2 rounded-full text-sm font-semibold ${
                                              light ? "text-slate-700 hover:bg-slate-100"
                                                            : "text-slate-300 hover:bg-slate-800"}`}>
            {inviteUrl ? "Done" : "Cancel"}
          </button>
          {!inviteUrl && (
            <button onClick={submit} disabled={busy || !email.trim()}
                            data-testid="advertiser-staff-invite-submit"
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-500 text-slate-900 text-sm font-bold hover:bg-amber-400 disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Send invite
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
