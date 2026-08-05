// Phase SC.3 — /merchant/dashboard stub.
//
// The SC.2 approval email links merchants here.  Full portal comes in
// Phase MER.1.  This stub is deliberately minimal — it's a "welcome
// mat" that surfaces the approval status + the two things the merchant
// might want to do NOW:
//   1. Check application status
//   2. Open Stripe Express dashboard
// Anything more elaborate would risk exposing features that don't yet
// exist (per SC.3 constraint 7).
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowRight, ExternalLink, Loader2, LogOut, Sparkles,
                  ClipboardList } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantDashboardStub() {
  const { user, loading: authLoading, logout } = useAuth();
  const variant = useDesignVariant();
  const navigate = useNavigate();
  const light = variant === "radiolife";

  const [merchant, setMerchant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [stripeBusy, setStripeBusy] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) {
      navigate("/login?next=" + encodeURIComponent("/merchant/dashboard"),
                    { replace: true });
    }
  }, [authLoading, user, navigate]);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/merchant/mine`,
                                                                { withCredentials: true });
      const items = data.items || [];
      // Prefer the highest-status active merchant (active > approved > submitted > draft)
      const priority = { active: 5, approved: 4, submitted: 3,
                                          verification_pending: 2, stripe_onboarding_pending: 1,
                                          draft: 0, rejected: -1, suspended: -1 };
      items.sort((a, b) => (priority[b.merchant_status] || 0)
                                        - (priority[a.merchant_status] || 0));
      setMerchant(items[0] || null);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const openStripe = async () => {
    if (!merchant?.merchant_id) return;
    setStripeBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/dashboard-link`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      if (data?.url) {
        window.open(data.url, "_blank", "noopener,noreferrer");
      }
    } catch (e) {
      toast.error(`Stripe dashboard unavailable: ${e?.response?.data?.detail || e.message}`);
    } finally { setStripeBusy(false); }
  };

  if (authLoading || !user) {
    return <div className={light ? "min-h-screen bg-white flex items-center justify-center"
                                                    : "min-h-screen bg-slate-950 flex items-center justify-center"}>
      <Loader2 className="animate-spin" size={28}
                        color={light ? "#a855f7" : "#00d4ff"}/>
    </div>;
  }

  const status = merchant?.effective_status || merchant?.merchant_status;
  const isApproved = status === "approved" || status === "active";
  const stripeReady = merchant?.stripe_onboarding_status === "active"
                                || merchant?.stripe_onboarding_status === "payouts_disabled";

  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
                          : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="merchant-dashboard-page"
              data-variant={variant}
              data-status={status || "none"}>
      <div className="max-w-2xl mx-auto px-5 py-10">
        <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
          light ? "text-purple-600" : "text-cyan-400"
        }`}>RadioLife Merchant Portal</div>
        <h1 className={`text-3xl sm:text-4xl font-black tracking-tight mb-2 ${
          light ? "text-slate-900" : "text-white"
        }`} data-testid="merchant-dashboard-welcome">
          {merchant?.name
              ? `Welcome, ${merchant.name}`
              : "Welcome"}
        </h1>
        <p className={light ? "text-slate-600 text-sm" : "text-slate-400 text-sm"}>
          {isApproved
            ? "Full merchant portal (analytics, coupons, campaigns) ships soon.  Meanwhile, everything you need to run your account today lives below."
            : "The full merchant portal ships alongside your first approved application.  Track your status below."}
        </p>

        {loading ? (
          <div className={`mt-8 flex items-center gap-2 text-sm ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>
            <Loader2 className="animate-spin" size={16}/> Loading merchant…
          </div>
        ) : merchant ? (
          <>
            <div className={`mt-6 rounded-3xl p-6 ${
              light ? "bg-white shadow-sm border border-slate-100"
                      : "bg-slate-900 border border-slate-800"
            }`}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className={`text-xs font-bold uppercase tracking-widest ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>Current status</div>
                  <div className={`mt-1 text-2xl font-black ${
                    isApproved
                      ? (light ? "text-emerald-700" : "text-emerald-400")
                      : (light ? "text-slate-900" : "text-slate-100")
                  }`} data-testid="merchant-dashboard-status">
                    {String(status || "").replace(/_/g, " ") || "—"}
                  </div>
                </div>
                <button type="button"
                              onClick={() => navigate(`/merchant/status?merchant_id=${merchant.merchant_id}`)}
                              data-testid="merchant-dashboard-status-link"
                              className={`inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-xs font-bold uppercase tracking-widest ${
                                light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                        : "bg-slate-800 text-slate-200 border border-slate-700"
                              }`}>
                  <ClipboardList size={14}/> Merchant status
                </button>
              </div>
            </div>

            {isApproved && (
              <div className={`mt-4 rounded-3xl p-6 ${
                light ? "bg-white shadow-sm border border-slate-100"
                        : "bg-slate-900 border border-slate-800"
              }`} data-testid="merchant-dashboard-payment-links-card">
                <div className={`text-xs font-bold uppercase tracking-widest mb-2 ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>Payment Links & QR Codes</div>
                <p className={`text-sm mb-4 ${light ? "text-slate-600" : "text-slate-400"}`}>
                  Create shareable payment URLs + printable QR codes for
                  tables, offers, gift cards, tickets, and more.
                </p>
                <button type="button"
                              onClick={() => navigate("/merchant/payment-links")}
                              data-testid="merchant-dashboard-payment-links-btn"
                              className="inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-white shadow-lg shadow-purple-500/25"
                              style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  Open Payment Links <ArrowRight size={14}/>
                </button>
              </div>
            )}

            {isApproved && (
              <div className={`mt-4 rounded-3xl p-6 ${
                light ? "bg-white shadow-sm border border-slate-100"
                        : "bg-slate-900 border border-slate-800"
              }`}>
                <div className={`text-xs font-bold uppercase tracking-widest mb-2 ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>Payments & payouts</div>
                <p className={`text-sm mb-4 ${light ? "text-slate-600" : "text-slate-400"}`}>
                  Manage refunds, payouts, and account details in your Stripe
                  Express dashboard — you own the account, we just connect to it.
                </p>
                <button type="button" onClick={openStripe}
                              disabled={stripeBusy || !stripeReady}
                              title={stripeReady ? "" : "Available once Stripe activation is complete"}
                              data-testid="merchant-dashboard-stripe-btn"
                              className={`inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-sm ${
                                stripeReady
                                  ? "text-white shadow-lg shadow-purple-500/25"
                                  : "text-slate-500 bg-slate-200/50 cursor-not-allowed"
                              }`}
                              style={stripeReady
                                ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" }
                                : undefined}>
                  {stripeBusy ? <Loader2 className="animate-spin" size={16}/>
                                        : <>Open Stripe Express <ExternalLink size={14}/></>}
                </button>
                <button type="button"
                              onClick={() => navigate("/merchant/payouts")}
                              data-testid="merchant-dashboard-payouts-btn"
                              className={`ml-2 inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-sm ${
                                light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                        : "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
                              }`}>
                  View Payouts <ArrowRight size={14}/>
                </button>
              </div>
            )}

            {!isApproved && (
              <div className={`mt-4 rounded-3xl p-6 ${
                light ? "bg-purple-50 border border-purple-100"
                        : "bg-slate-900 border border-slate-800"
              }`}>
                <div className={`text-xs font-bold uppercase tracking-widest mb-2 ${
                  light ? "text-purple-600" : "text-cyan-400"
                }`}>Next step</div>
                <p className={`text-sm mb-4 ${light ? "text-slate-700" : "text-slate-300"}`}>
                  {status === "draft"
                    ? "Finish your merchant application to unlock the portal."
                    : status === "submitted"
                      ? "Application is under review.  We'll email you as soon as an admin decides."
                      : status === "rejected"
                        ? "Your application was not approved.  Review the reason and reapply."
                        : "Complete the required steps below to progress your application."}
                </p>
                <button type="button"
                              onClick={() => navigate(`/merchant/apply?merchant_id=${merchant.merchant_id}`)}
                              data-testid="merchant-dashboard-resume-btn"
                              className="inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-white shadow-lg shadow-purple-500/25"
                              style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  {status === "rejected" ? "Start new application"
                                                        : "Resume application"} <ArrowRight size={14}/>
                </button>
              </div>
            )}
          </>
        ) : (
          <div className={`mt-6 rounded-3xl p-6 ${
            light ? "bg-white shadow-sm border border-slate-100"
                    : "bg-slate-900 border border-slate-800"
          }`}>
            <div className="flex items-start gap-3">
              <Sparkles size={20}
                              className={light ? "text-purple-600" : "text-cyan-400"}/>
              <div>
                <div className={`font-semibold ${light ? "text-slate-900" : "text-white"}`}>
                  No merchant application yet
                </div>
                <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
                  Start your RadioLife merchant application to bring your business
                  onto the platform.
                </p>
                <button type="button"
                              onClick={() => navigate("/merchant/apply")}
                              data-testid="merchant-dashboard-start-btn"
                              className="mt-4 inline-flex items-center gap-2 h-11 px-5 rounded-full font-bold text-white"
                              style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  Start application <ArrowRight size={14}/>
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-8 flex justify-end">
          <button type="button"
                        onClick={() => { logout(); navigate("/"); }}
                        data-testid="merchant-dashboard-logout"
                        className={`inline-flex items-center gap-1.5 text-xs font-semibold ${
                          light ? "text-slate-500 hover:text-slate-700"
                                  : "text-slate-500 hover:text-slate-300"
                        }`}>
            <LogOut size={14}/> Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
