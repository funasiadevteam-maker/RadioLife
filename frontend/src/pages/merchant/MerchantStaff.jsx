// Phase MER.2 — Merchant Staff management page (inside MerchantShell).
// Requires `can_invite_staff` permission (owner + manager + admin).
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { UserPlus, Copy, X, Loader2, Trash2, Shield, Mail,
                  Clock, RefreshCw, ChevronDown } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STAFF_ROLES = [
  { value: "manager",              label: "Manager",              hint: "Full merchant access except staff invites limited to non-owners" },
  { value: "cashier",              label: "Cashier",              hint: "Coupon redemption only" },
  { value: "marketing",          label: "Marketing",          hint: "Create + view payment links + analytics" },
  { value: "analytics_only", label: "Analytics Only", hint: "Read-only view of KPIs + payouts" },
];

const ROLE_TINT = (role, light) => {
  const m = {
    owner:                    light ? "bg-purple-100 text-purple-700"
                                                : "bg-purple-500/15 text-purple-300",
    manager:                light ? "bg-emerald-100 text-emerald-700"
                                                : "bg-emerald-500/15 text-emerald-300",
    cashier:                light ? "bg-amber-100 text-amber-700"
                                                : "bg-amber-500/15 text-amber-300",
    marketing:            light ? "bg-sky-100 text-sky-700"
                                                : "bg-sky-500/15 text-sky-300",
    analytics_only: light ? "bg-slate-100 text-slate-700"
                                                : "bg-slate-500/15 text-slate-300",
  };
  return m[role] || m.analytics_only;
};


export default function MerchantStaff() {
  const { merchant, light } = useMerchant();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/staff`,
        { withCredentials: true });
      setData(data);
    } catch (e) {
      toast.error(`Load: ${e?.response?.data?.detail?.detail
                                                || e?.response?.data?.detail
                                                || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { if (merchant) load(); }, [merchant]);

  const changeRole = async (staff, newRole) => {
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/staff/${staff.staff_user_id}/role`,
        { role: newRole }, { withCredentials: true });
      toast.success(`Role updated to ${newRole}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.detail || e.message);
    }
  };

  const deactivate = async (staff) => {
    if (!window.confirm(`Deactivate ${staff.display_name || staff.email}?`)) return;
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/staff/${staff.staff_user_id}/deactivate`,
        {}, { withCredentials: true });
      toast.success("Staff deactivated");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.detail || e.message);
    }
  };

  const revokeInvite = async (inv) => {
    if (!window.confirm(`Revoke invite to ${inv.email}?`)) return;
    try {
      await axios.post(
        `${API}/merchant/${merchant.merchant_id}/staff/invites/${inv.invite_id}/revoke`,
        {}, { withCredentials: true });
      toast.success("Invite revoked");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.detail || e.message);
    }
  };

  const copyInvite = (token) => {
    const url = `${window.location.origin}/staff/invite/${token}`;
    navigator.clipboard.writeText(url);
    toast.success("Invite link copied");
  };

  if (loading || !data) {
    return (
      <div className="p-8 max-w-4xl mx-auto" data-testid="merchant-staff-loading">
        <Loader2 className="animate-spin" size={16}/>
      </div>
    );
  }

  const activeStaff = (data.staff || []).filter((s) => s.active !== false);
  const inactiveStaff = (data.staff || []).filter((s) => s.active === false);

  return (
    <div className="p-6 lg:p-10 max-w-5xl mx-auto space-y-5"
              data-testid="merchant-staff-page">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className={`text-3xl font-black tracking-tight ${
          light ? "text-slate-900" : "text-white"
        }`}>Team & Staff</h1>
        <button onClick={load}
                      className={`text-xs font-bold flex items-center gap-1.5 ${
                        light ? "text-slate-500 hover:text-slate-700"
                                : "text-slate-500 hover:text-slate-300"
                      }`}>
          <RefreshCw size={12}/> Refresh
        </button>
        <button onClick={() => setInviteOpen(true)}
                      data-testid="merchant-staff-invite-btn"
                      className="ml-auto inline-flex items-center gap-2 h-10 px-4 rounded-full font-bold text-sm text-white"
                      style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <UserPlus size={14}/> Invite Staff
        </button>
      </div>

      {/* Active staff */}
      <div className={`rounded-2xl overflow-hidden ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-staff-active-table">
        <div className={`px-5 py-3 text-[10px] font-black uppercase tracking-widest ${
          light ? "bg-slate-50 text-slate-500"
                  : "bg-slate-950 text-slate-500"
        }`}>Active team · {(data.owner ? 1 : 0) + activeStaff.length}</div>
        <div>
          {/* Owner row */}
          {data.owner && (
            <StaffRow light={light}
                                    staff={{ ...data.owner, role: "owner" }}
                                    isOwner
                                    testid={`merchant-staff-row-owner`}/>
          )}
          {activeStaff.map((s) => (
            <StaffRow key={s.staff_user_id} light={light} staff={s}
                                    testid={`merchant-staff-row-${s.staff_user_id}`}
                                    onChangeRole={(r) => changeRole(s, r)}
                                    onDeactivate={() => deactivate(s)}/>
          ))}
          {activeStaff.length === 0 && !data.owner && (
            <div className={`p-6 text-center text-sm ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>No active staff yet.</div>
          )}
        </div>
      </div>

      {/* Pending invites */}
      <div className={`rounded-2xl overflow-hidden ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-staff-invites-table">
        <div className={`px-5 py-3 text-[10px] font-black uppercase tracking-widest ${
          light ? "bg-slate-50 text-slate-500"
                  : "bg-slate-950 text-slate-500"
        }`}>Pending invites · {data.pending_invites.length}</div>
        {data.pending_invites.length === 0 ? (
          <div className={`p-6 text-center text-sm ${
            light ? "text-slate-500" : "text-slate-500"
          }`} data-testid="merchant-staff-invites-empty">
            No pending invites.
          </div>
        ) : (
          <div>
            {data.pending_invites.map((i) => (
              <div key={i.invite_id}
                        data-testid={`merchant-staff-invite-row-${i.invite_id}`}
                        className={`flex items-center gap-3 px-5 py-3 ${
                          light ? "border-t border-slate-100"
                                  : "border-t border-slate-800"
                        }`}>
                <Mail size={14} className={light ? "text-slate-400" : "text-slate-500"}/>
                <div className="flex-1 min-w-0">
                  <div className={`text-sm font-semibold truncate ${
                    light ? "text-slate-800" : "text-slate-200"
                  }`}>{i.email}</div>
                  <div className={`text-[10px] flex items-center gap-1 ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>
                    <Clock size={10}/> expires {new Date(i.expires_at)
                                                                                                .toLocaleDateString(undefined,
                          { month: "short", day: "numeric" })}
                  </div>
                </div>
                <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${ROLE_TINT(i.role, light)}`}>
                  {i.role}
                </span>
                <button onClick={() => copyInvite(i.token)}
                              title="Copy invite link"
                              data-testid={`merchant-staff-invite-copy-${i.invite_id}`}
                              className={`p-1.5 rounded ${
                                light ? "text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                                          : "text-slate-500 hover:text-slate-200 hover:bg-slate-800"
                              }`}><Copy size={13}/></button>
                <button onClick={() => revokeInvite(i)}
                              title="Revoke"
                              data-testid={`merchant-staff-invite-revoke-${i.invite_id}`}
                              className={`p-1.5 rounded ${
                                light ? "text-rose-600 hover:bg-rose-50"
                                          : "text-rose-400 hover:bg-rose-500/10"
                              }`}><Trash2 size={13}/></button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Inactive (soft-deleted) */}
      {inactiveStaff.length > 0 && (
        <details className={`rounded-2xl overflow-hidden ${
          light ? "bg-white border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <summary className={`px-5 py-3 cursor-pointer text-[10px] font-black uppercase tracking-widest ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>Deactivated · {inactiveStaff.length}</summary>
          {inactiveStaff.map((s) => (
            <StaffRow key={s.staff_user_id} light={light} staff={s}
                                    deactivated
                                    testid={`merchant-staff-row-inactive-${s.staff_user_id}`}/>
          ))}
        </details>
      )}

      {inviteOpen && (
        <InviteModal light={light}
                                    merchantId={merchant.merchant_id}
                                    onClose={() => setInviteOpen(false)}
                                    onSuccess={() => { setInviteOpen(false); load(); }}/>
      )}
    </div>
  );
}


function StaffRow({ light, staff, isOwner, deactivated, onChangeRole,
                                        onDeactivate, testid }) {
  const [dropdown, setDropdown] = useState(false);
  return (
    <div className={`flex items-center gap-3 px-5 py-3 ${
      light ? "border-t border-slate-100 first:border-t-0"
              : "border-t border-slate-800 first:border-t-0"
    } ${deactivated ? "opacity-50" : ""}`} data-testid={testid}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center text-xs font-black ${
        light ? "bg-slate-100 text-slate-700" : "bg-slate-800 text-slate-300"
      }`}>
        {(staff.display_name || staff.email || "?").charAt(0).toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-semibold truncate ${
          light ? "text-slate-800" : "text-slate-200"
        }`}>{staff.display_name || staff.email || "—"}</div>
        <div className={`text-[10px] truncate ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>{staff.email}</div>
      </div>
      <div className={`text-[10px] hidden sm:block ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>
        {staff.accepted_at ? "Joined " + new Date(staff.accepted_at)
                                                                          .toLocaleDateString(undefined,
              { month: "short", day: "numeric" }) : ""}
      </div>
      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${ROLE_TINT(staff.role, light)}`}>
        {staff.role}
      </span>
      {!isOwner && !deactivated && onChangeRole && (
        <div className="relative">
          <button onClick={() => setDropdown(!dropdown)}
                        title="Change role"
                        data-testid={`${testid}-role-menu`}
                        className={`text-[10px] font-bold px-2 py-1 rounded ${
                          light ? "text-slate-600 hover:bg-slate-100"
                                  : "text-slate-400 hover:bg-slate-800"
                        }`}><ChevronDown size={13}/></button>
          {dropdown && (
            <div onMouseLeave={() => setDropdown(false)}
                      className={`absolute right-0 top-full mt-1 z-10 rounded-lg overflow-hidden ${
                        light ? "bg-white shadow-lg border border-slate-100"
                                : "bg-slate-900 border border-slate-700"
                      }`}>
              {STAFF_ROLES.map((r) => (
                <button key={r.value}
                              onClick={() => { onChangeRole(r.value); setDropdown(false); }}
                              className={`block w-full text-left px-3 py-2 text-xs font-semibold whitespace-nowrap ${
                                light ? "hover:bg-slate-50 text-slate-800"
                                        : "hover:bg-slate-800 text-slate-200"
                              }`}>
                  {r.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {!isOwner && !deactivated && onDeactivate && (
        <button onClick={onDeactivate}
                      data-testid={`${testid}-deactivate`}
                      title="Deactivate"
                      className={`p-1.5 rounded ${
                        light ? "text-rose-600 hover:bg-rose-50"
                                : "text-rose-400 hover:bg-rose-500/10"
                      }`}><Trash2 size={13}/></button>
      )}
    </div>
  );
}


function InviteModal({ light, merchantId, onClose, onSuccess }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("cashier");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [invited, setInvited] = useState(null);

  const submit = async () => {
    if (!email.trim() || !email.includes("@")) {
      setErr("Enter a valid email"); return;
    }
    setBusy(true); setErr(null);
    try {
      const { data } = await axios.post(
        `${API}/merchant/${merchantId}/staff/invite`,
        { email: email.trim().toLowerCase(), role },
        { withCredentials: true });
      setInvited(data);
      toast.success(`Invited ${email} as ${role}`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(d?.detail || d?.code || d || e.message);
    } finally { setBusy(false); }
  };

  const copyLink = () => {
    const url = invited.invite_url;
    navigator.clipboard.writeText(url);
    toast.success("Invite link copied");
  };

  return (
    <div onClick={onClose}
              data-testid="merchant-staff-invite-backdrop"
              className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div onClick={(e) => e.stopPropagation()}
                data-testid="merchant-staff-invite-modal"
                className={`w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"
                }`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`text-lg font-black ${
            light ? "text-slate-900" : "text-white"
          }`}>{invited ? "Invite sent" : "Invite Staff"}</h3>
          <button onClick={onClose} className={
            light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>

        {!invited ? (
          <>
            <Label light={light}>Email address</Label>
            <input type="email" autoFocus value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="staff@example.com"
                        data-testid="merchant-staff-invite-email"
                        className={inputCls(light)}/>

            <Label light={light}>Role</Label>
            <div className="space-y-2">
              {STAFF_ROLES.map((r) => (
                <label key={r.value}
                              className={`block rounded-xl p-3 cursor-pointer border-2 ${
                                role === r.value
                                  ? (light ? "border-purple-500 bg-purple-50"
                                                  : "border-cyan-500 bg-cyan-500/10")
                                  : (light ? "border-slate-100 hover:border-slate-200"
                                                  : "border-slate-800 hover:border-slate-700")
                              }`}>
                  <input type="radio" name="role" value={r.value} hidden
                              checked={role === r.value}
                              onChange={() => setRole(r.value)}
                              data-testid={`merchant-staff-invite-role-${r.value}`}/>
                  <div className={`text-sm font-black ${
                    light ? "text-slate-900" : "text-white"
                  }`}>{r.label}</div>
                  <div className={`text-[11px] mt-0.5 ${
                    light ? "text-slate-600" : "text-slate-400"
                  }`}>{r.hint}</div>
                </label>
              ))}
            </div>

            {err && (
              <div className={`text-xs rounded-lg p-2 mt-3 ${
                light ? "bg-rose-50 text-rose-700 border border-rose-100"
                        : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
              }`} data-testid="merchant-staff-invite-error">{err}</div>
            )}

            <button onClick={submit} disabled={busy}
                          data-testid="merchant-staff-invite-submit"
                          className="w-full mt-5 h-12 rounded-full font-black text-sm text-white"
                          style={{ background: busy ? "#94a3b8"
                                            : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              {busy ? "Sending…" : "Send invite"}
            </button>
          </>
        ) : (
          <>
            <div className={`rounded-xl p-4 mb-4 ${
              light ? "bg-emerald-50 border border-emerald-100"
                      : "bg-emerald-500/10 border border-emerald-500/20"
            }`}>
              <div className={`text-sm font-bold ${
                light ? "text-emerald-800" : "text-emerald-300"
              }`}>✓ Invited {invited.email}</div>
              <div className={`text-xs mt-1 ${
                light ? "text-emerald-700" : "text-emerald-300/70"
              }`}>as <b>{invited.role}</b>.  Expires {new Date(invited.expires_at)
                                                                                                                    .toLocaleDateString()}.  Email sent.</div>
            </div>
            <Label light={light}>Or share this link directly:</Label>
            <div className="flex items-center gap-2">
              <input readOnly value={invited.invite_url}
                          className={`${inputCls(light)} text-xs font-mono`}/>
              <button onClick={copyLink}
                            data-testid="merchant-staff-invite-copylink"
                            className={`p-3 rounded-xl ${
                              light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                      : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                            }`}><Copy size={14}/></button>
            </div>
            <button onClick={onSuccess}
                          className="w-full mt-5 h-12 rounded-full font-black text-sm text-white"
                          style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              Done
            </button>
          </>
        )}
      </div>
    </div>
  );
}


function Label({ light, children }) {
  return <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 mt-3 ${
    light ? "text-slate-500" : "text-slate-500"
  }`}>{children}</div>;
}
function inputCls(light) {
  return `w-full h-11 rounded-xl px-3 text-sm outline-none ${
    light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
            : "bg-slate-950 border border-slate-800 text-slate-200 focus:border-cyan-500"
  }`;
}
