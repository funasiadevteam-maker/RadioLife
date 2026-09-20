// Phase SC.2 — Merchant status page (post-submit).  Polls for status
// changes and surfaces rejection reasons + next steps.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, Clock, Loader2, XCircle,
                  AlertTriangle, Sparkles, RefreshCw } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_PRESET = {
  draft:                {icon: Clock,        tint: "amber",      title: "Draft",
                                    sub: "Finish the wizard to submit your application."},
  submitted:        {icon: Clock,        tint: "cyan",        title: "Submitted",
                                    sub: "We're reviewing your application.  Most decisions arrive within 2 business days."},
  approved:          {icon: CheckCircle2, tint: "emerald",  title: "Approved",
                                    sub: "You're in!  Your merchant dashboard ships in the next release — SC.4."},
  active:              {icon: CheckCircle2, tint: "emerald",  title: "Active",
                                    sub: "Approved and Stripe-activated.  You can now transact through FUUSIC."},
  rejected:          {icon: XCircle,      tint: "rose",        title: "Not approved",
                                    sub: "See the reason below.  You may reapply after addressing the feedback."},
  suspended:        {icon: AlertTriangle, tint: "amber",     title: "Suspended",
                                    sub: "Your account has been temporarily suspended.  See details below."},
  restricted:        {icon: AlertTriangle, tint: "amber",     title: "Stripe restricted",
                                    sub: "Stripe flagged compliance issues.  Please complete outstanding items in your Stripe dashboard."},
  payouts_disabled: {icon: AlertTriangle, tint: "amber",  title: "Payouts disabled",
                                    sub: "Stripe temporarily disabled payouts.  Complete outstanding requirements to resume."},
  stripe_onboarding_pending: {icon: Clock, tint: "cyan",  title: "Stripe onboarding",
                                    sub: "Awaiting Stripe onboarding completion."},
  verification_pending: {icon: Clock, tint: "cyan",      title: "Verification pending",
                                    sub: "Stripe is verifying your details."},
};

const TINTS = {
  amber:      { bg: "bg-amber-100",    fg: "text-amber-700",    ring: "ring-amber-200",
                          dbg: "bg-amber-500/10", dfg: "text-amber-300",  dring: "ring-amber-500/30" },
  cyan:        { bg: "bg-cyan-100",      fg: "text-cyan-800",      ring: "ring-cyan-200",
                          dbg: "bg-cyan-500/10",  dfg: "text-cyan-300",    dring: "ring-cyan-500/30" },
  emerald:  { bg: "bg-emerald-100", fg: "text-emerald-800", ring: "ring-emerald-200",
                          dbg: "bg-emerald-500/10", dfg: "text-emerald-300", dring: "ring-emerald-500/30" },
  rose:        { bg: "bg-rose-100",      fg: "text-rose-800",      ring: "ring-rose-200",
                          dbg: "bg-rose-500/10",  dfg: "text-rose-300",    dring: "ring-rose-500/30" },
};


export default function MerchantStatus() {
  const { user, loading: authLoading } = useAuth();
  const variant = useDesignVariant();
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const mid = sp.get("merchant_id");
  const [merchant, setMerchant] = useState(null);
  const [loading, setLoading] = useState(true);

  const light = variant === "radiolife";

  useEffect(() => {
    if (!authLoading && !user) {
      navigate(`/login?next=${encodeURIComponent(`/merchant/status?merchant_id=${mid || ""}`)}`,
                    { replace: true });
    }
  }, [authLoading, user, mid, navigate]);

  const load = useCallback(async () => {
    if (!mid) { setLoading(false); return; }
    try {
      const { data } = await axios.get(`${API}/merchant/${mid}`,
                                                                { withCredentials: true });
      setMerchant(data);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, [mid]);

  useEffect(() => { load(); }, [load]);

  // Auto-poll while status is submitted / verification_pending
  useEffect(() => {
    if (!merchant) return;
    if (!["submitted", "verification_pending", "stripe_onboarding_pending"]
              .includes(merchant.merchant_status)) return;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [merchant, load]);

  if (loading || authLoading) {
    return <div className={light ? "min-h-screen bg-white flex items-center justify-center"
                                                    : "min-h-screen bg-slate-950 flex items-center justify-center"}>
      <Loader2 className="animate-spin" size={28}
                        color={light ? "#a855f7" : "#00d4ff"}/>
    </div>;
  }

  if (!mid || !merchant) {
    return <div className={light ? "min-h-screen bg-white p-10"
                                                    : "min-h-screen bg-slate-950 p-10 text-slate-200"}>
      <div className="max-w-lg mx-auto text-center">
        <h1 className="text-2xl font-bold mb-2">No merchant application</h1>
        <p className="text-sm opacity-70 mb-6">Start a new application from the “Become a Partner” link.</p>
        <button type="button" onClick={() => navigate("/merchant/apply")}
                      className="px-5 h-11 rounded-full font-semibold text-white"
                      style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}
                      data-testid="merchant-status-start-new">
          Start application
        </button>
      </div>
    </div>;
  }

  const eff = merchant.effective_status || merchant.merchant_status;
  const preset = STATUS_PRESET[eff] || STATUS_PRESET.draft;
  const Icon = preset.icon;
  const tint = TINTS[preset.tint] || TINTS.cyan;

  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
                          : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="merchant-status-page"
              data-variant={variant}
              data-status={eff}>
      <div className="max-w-2xl mx-auto px-5 py-10">
        <button type="button" onClick={() => navigate("/")}
                      className={`inline-flex items-center gap-1.5 text-sm font-medium mb-8 ${
                        light ? "text-purple-700 hover:text-purple-900"
                                : "text-slate-400 hover:text-cyan-400"
                      }`}
                      data-testid="merchant-status-home-btn">
          <ArrowLeft size={16}/> Back to FUUSIC
        </button>

        <div className={`rounded-3xl p-8 sm:p-10 ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full font-bold uppercase tracking-widest text-xs mb-6 ring-1 ${
            light ? `${tint.bg} ${tint.fg} ${tint.ring}`
                    : `${tint.dbg} ${tint.dfg} ${tint.dring}`
          }`} data-testid="merchant-status-pill">
            <Icon size={14}/> {eff.replace(/_/g, " ")}
          </div>

          <h1 className={`text-3xl sm:text-4xl font-extrabold tracking-tight mb-2 ${
            light ? "text-slate-900" : "text-white"
          }`} data-testid="merchant-status-title">{preset.title}</h1>
          <p className={light ? "text-slate-600" : "text-slate-400"}
                data-testid="merchant-status-sub">{preset.sub}</p>

          <div className={`mt-6 p-4 rounded-2xl ${
            light ? "bg-slate-50 border border-slate-100"
                    : "bg-slate-950 border border-slate-800"
          }`}>
            <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>Merchant</div>
            <div className={`font-semibold ${light ? "text-slate-900" : "text-white"}`}>
              {merchant.name}
            </div>
            <div className={`text-xs mt-0.5 font-mono ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>{merchant.merchant_id}</div>
          </div>

          {merchant.rejection_reason && (
            <div className={`mt-4 p-4 rounded-2xl ${
              light ? "bg-rose-50 border border-rose-200"
                      : "bg-rose-500/10 border border-rose-500/30"
            }`} data-testid="merchant-status-rejection">
              <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${
                light ? "text-rose-700" : "text-rose-300"
              }`}>Reason from our team</div>
              <div className={`text-sm ${light ? "text-slate-800" : "text-slate-200"}`}>
                {merchant.rejection_reason}
              </div>
            </div>
          )}

          {merchant.suspension_reason && (
            <div className={`mt-4 p-4 rounded-2xl ${
              light ? "bg-amber-50 border border-amber-200"
                      : "bg-amber-500/10 border border-amber-500/30"
            }`} data-testid="merchant-status-suspension">
              <div className={`text-xs font-bold uppercase tracking-wider mb-1 ${
                light ? "text-amber-700" : "text-amber-300"
              }`}>Suspension reason</div>
              <div className={`text-sm ${light ? "text-slate-800" : "text-slate-200"}`}>
                {merchant.suspension_reason}
              </div>
            </div>
          )}

          <div className="mt-6 flex flex-wrap gap-2">
            <button type="button" onClick={load}
                          className={`inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-sm font-semibold ${
                            light ? "bg-white border border-slate-200 hover:border-purple-300 text-slate-700"
                                    : "bg-slate-800 border border-slate-700 text-slate-200 hover:border-cyan-500/50"
                          }`}
                          data-testid="merchant-status-refresh">
              <RefreshCw size={14}/> Refresh
            </button>
            {merchant.merchant_status === "draft" && (
              <button type="button" onClick={() => navigate(`/merchant/apply?merchant_id=${mid}`)}
                            className="inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-sm font-semibold text-white"
                            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}
                            data-testid="merchant-status-resume">
                <Sparkles size={14}/> Resume application
              </button>
            )}
            {merchant.merchant_status === "rejected" && (
              <button type="button" onClick={() => navigate("/merchant/apply")}
                            className="inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-sm font-semibold text-white"
                            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}
                            data-testid="merchant-status-reapply">
                Start new application
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
