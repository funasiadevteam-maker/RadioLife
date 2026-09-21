// Super-admin: unified vendor payout fees + onboarding gate (Payouts Hub).
// Two knobs that drive the REAL charge paths:
//   • Advisor % → dream_payout_config.commission_pct (dream_payouts transfers)
//   • Merchant % → commission_rules "*/*" fallback (payment_service app fee)
// plus the "require onboarding before selling" gate.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Loader2, Percent, Save, ArrowLeft, ShieldCheck, Sparkles, Store } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminPlatformFees() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [advisorPct, setAdvisorPct] = useState("15");
  const [merchantPct, setMerchantPct] = useState("5");
  const [requireOnboard, setRequireOnboard] = useState(false);

  useEffect(() => {
    axios.get(`${API}/admin/vendor-fees`, { withCredentials: true })
      .then(({ data }) => {
        setAdvisorPct(String(data.advisor_pct ?? 15));
        setMerchantPct(String(data.merchant_pct ?? 5));
        setRequireOnboard(!!data.require_onboarding);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await axios.put(`${API}/admin/vendor-fees`, {
        advisor_pct: Math.round(parseFloat(advisorPct || "0")),
        merchant_pct: Math.round(parseFloat(merchantPct || "0")),
        require_onboarding: requireOnboard,
      }, { withCredentials: true });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (_) { alert("Save failed"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="min-h-screen grid place-items-center bg-slate-950"><Loader2 className="animate-spin text-slate-400" /></div>;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100" data-testid="admin-platform-fees">
      <div className="max-w-2xl mx-auto px-5 py-8">
        <Link to="/admin" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-5"><ArrowLeft size={15} /> Admin</Link>
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-violet-500/20 grid place-items-center"><Percent size={18} className="text-violet-300" /></div>
          <h1 className="text-2xl font-black">Vendor Payout Fees</h1>
        </div>
        <p className="text-sm text-slate-400 mb-6">Platform commission taken from every vendor transaction before payout via Stripe Connect.</p>

        <FeeCard Icon={Sparkles} title="Expert / Advisor fee" hint="Kept from each reading or session; the rest is transferred to the advisor on delivery."
          value={advisorPct} onChange={setAdvisorPct} testid="fee-advisor-input" />

        <FeeCard Icon={Store} title="Business / Merchant fee" hint="Applied as the Stripe application fee on merchant payment links & bookings."
          value={merchantPct} onChange={setMerchantPct} testid="fee-merchant-input" />

        <label className="rounded-2xl border border-slate-800 bg-slate-900 p-4 mt-4 flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={requireOnboard} onChange={(e) => setRequireOnboard(e.target.checked)} className="accent-violet-500 w-4 h-4" data-testid="fee-require-onboarding" />
          <div>
            <div className="text-sm font-bold flex items-center gap-1.5"><ShieldCheck size={14} className="text-violet-300" /> Require payout onboarding before selling</div>
            <div className="text-xs text-slate-500">Vendors can't take payments until their Stripe payout account is active.</div>
          </div>
        </label>

        <button onClick={save} disabled={saving} data-testid="fee-save-btn"
          className="mt-6 w-full h-12 rounded-full font-black text-white disabled:opacity-50 inline-flex items-center justify-center gap-2"
          style={{ background: "linear-gradient(135deg,#8b5cf6,#6366f1)" }}>
          {saving ? <Loader2 className="animate-spin" size={16} /> : saved ? "Saved ✓" : <><Save size={16} /> Save fees</>}
        </button>
      </div>
    </div>
  );
}

function FeeCard({ Icon, title, hint, value, onChange, testid }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 mt-4">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={15} className="text-violet-300" />
        <label className="text-xs font-bold uppercase tracking-widest text-slate-400">{title}</label>
      </div>
      <div className="flex items-center gap-2 mt-2">
        <input type="number" step="1" min="0" max="90" value={value} onChange={(e) => onChange(e.target.value)}
          data-testid={testid} className="w-28 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-lg font-black" />
        <span className="text-slate-400 font-bold">%</span>
      </div>
      <p className="text-xs text-slate-500 mt-2">{hint}</p>
    </div>
  );
}
