// Phase MER.1 — Stripe Connect status page + Express dashboard link.
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle2, XCircle, AlertTriangle, ExternalLink,
                  Loader2, Zap, Wallet, ShieldCheck, RefreshCw } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantStripe() {
  const { merchant, light } = useMerchant();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}`,
        { withCredentials: true });
      setStatus(data);
    } catch (e) {
      toast.error(`Load: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { if (merchant) load(); }, [merchant]);

  const openStripe = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/dashboard-link`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      if (data.url) window.open(data.url, "_blank");
      else toast.error("No URL returned");
    } catch (e) {
      toast.error(`Stripe: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  const refreshStatus = async () => {
    setBusy(true);
    try {
      await axios.post(
        `${API}/stripe/connect/refresh-status`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      await load();
      toast.success("Status refreshed from Stripe");
    } catch (e) {
      toast.error(`Refresh: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  if (!status) {
    return (
      <div className="p-8 max-w-4xl mx-auto" data-testid="merchant-stripe-loading">
        <Loader2 className="animate-spin" size={16}/>
      </div>
    );
  }

  const checks = [
    { key: "charges_enabled",      label: "Accept payments",
      value: status.stripe_charges_enabled },
    { key: "payouts_enabled",      label: "Receive payouts",
      value: status.stripe_payouts_enabled },
    { key: "details_submitted",  label: "Business details submitted",
      value: status.stripe_details_submitted },
  ];

  return (
    <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-5"
              data-testid="merchant-stripe-page">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className={`text-3xl font-black tracking-tight ${
          light ? "text-slate-900" : "text-white"
        }`}>Stripe Connect</h1>
        <button onClick={refreshStatus} disabled={busy}
                      data-testid="merchant-stripe-refresh"
                      className={`ml-auto text-xs font-bold flex items-center gap-1.5 ${
                        light ? "text-slate-500 hover:text-slate-700"
                                : "text-slate-500 hover:text-slate-300"
                      }`}>
          {loading || busy ? <Loader2 className="animate-spin" size={12}/>
                                          : <RefreshCw size={12}/>} Refresh
        </button>
      </div>

      {/* Onboarding status card */}
      <div className={`rounded-2xl p-6 ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-stripe-status-card">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
            status.stripe_charges_enabled && status.stripe_payouts_enabled
              ? (light ? "bg-emerald-100 text-emerald-700"
                              : "bg-emerald-500/15 text-emerald-300")
              : (light ? "bg-amber-100 text-amber-700"
                              : "bg-amber-500/15 text-amber-300")
          }`}>
            <Zap size={22}/>
          </div>
          <div className="flex-1">
            <div className={`text-xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`} data-testid="merchant-stripe-onboarding-status">
              {(status.stripe_onboarding_status || "not_started").replace(/_/g, " ")}
            </div>
            <div className={`text-xs mt-1 ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>
              Account: <code className="font-mono">{status.stripe_account_id || "not_connected"}</code>
            </div>
          </div>
        </div>

        <div className="mt-5 space-y-2">
          {checks.map((c) => (
            <div key={c.key} data-testid={`merchant-stripe-check-${c.key}`}
                      className={`flex items-center gap-2.5 text-sm ${
                        light ? "text-slate-700" : "text-slate-300"
                      }`}>
              {c.value
                ? <CheckCircle2 size={16} className={
                        light ? "text-emerald-600" : "text-emerald-400"}/>
                : <XCircle size={16} className={
                        light ? "text-slate-400" : "text-slate-600"}/>}
              <span>{c.label}</span>
            </div>
          ))}
        </div>

        <div className="mt-6 flex gap-2 flex-wrap">
          <button onClick={openStripe} disabled={busy}
                        data-testid="merchant-stripe-open-dashboard"
                        className={`inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-sm text-white ${
                          busy ? "bg-slate-400 cursor-not-allowed"
                                : ""
                        }`}
                        style={!busy ? { background: "linear-gradient(135deg,#635BFF,#a855f7)"}
                                                  : undefined}>
            {busy ? <Loader2 className="animate-spin" size={16}/>
                        : <>Open Stripe Dashboard <ExternalLink size={14}/></>}
          </button>
        </div>
      </div>

      {/* Requirements card */}
      {(status.requirements_currently_due?.length > 0
              || status.requirements_past_due?.length > 0) && (
        <div className={`rounded-2xl p-6 ${
          light ? "bg-amber-50 border border-amber-200"
                  : "bg-amber-500/10 border border-amber-500/20"
        }`} data-testid="merchant-stripe-requirements">
          <div className="flex items-start gap-3">
            <AlertTriangle className={light ? "text-amber-600" : "text-amber-300"} size={20}/>
            <div className="flex-1">
              <div className={`text-sm font-black ${
                light ? "text-amber-900" : "text-amber-200"
              }`}>Action required</div>
              <p className={`text-xs mt-1 ${
                light ? "text-amber-800" : "text-amber-300/80"
              }`}>Stripe needs the following before enabling your account:</p>
              <ul className="mt-2 space-y-1">
                {[...(status.requirements_currently_due || []),
                    ...(status.requirements_past_due || [])].map((r) => (
                  <li key={r} className={`text-xs font-mono ${
                    light ? "text-amber-900" : "text-amber-200"
                  }`}>• {r}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Info card */}
      <div className={`rounded-2xl p-6 ${
        light ? "bg-purple-50 border border-purple-100"
                : "bg-slate-900 border border-slate-800"
      }`} data-testid="merchant-stripe-info-card">
        <div className="flex items-start gap-3">
          <ShieldCheck className={light ? "text-purple-600" : "text-cyan-400"}
                                        size={20}/>
          <div>
            <div className={`text-sm font-black ${
              light ? "text-purple-900" : "text-white"
            }`}>Your money, your account</div>
            <p className={`text-xs mt-1 ${
              light ? "text-purple-800/80" : "text-slate-400"
            }`}>
              BigFM uses Stripe Connect Standard.  Customer payments are
              routed directly to your Stripe account &mdash; we retain only
              the platform commission.  Payouts follow your Stripe payout
              schedule (typically daily or weekly).
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
