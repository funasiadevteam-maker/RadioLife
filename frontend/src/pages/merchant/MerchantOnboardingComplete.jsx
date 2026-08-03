// Phase SC.2 — Stripe Connect return-URL handler.
// Reached after the merchant finishes (or cancels) the Stripe hosted
// onboarding flow.  Refreshes account status, then routes back into the
// wizard so the user can either continue or submit for approval.
import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantOnboardingComplete() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const variant = useDesignVariant();
  const mid = sp.get("merchant_id");
  const [state, setState] = useState({ loading: true, status: null,
                                                                      error: null });

  const light = variant === "radiolife";

  useEffect(() => {
    (async () => {
      if (!mid) {
        setState({ loading: false, error: "no_merchant_id" });
        return;
      }
      try {
        const { data } = await axios.post(
          `${API}/stripe/connect/status/refresh`,
          { merchant_id: mid },
          { withCredentials: true });
        setState({ loading: false,
                          status: data.stripe_onboarding_status,
                          error: null });
        toast.success(`Stripe status: ${data.stripe_onboarding_status}`);
        // Route back to the wizard so the user can advance to Review
        setTimeout(() => {
          navigate(`/merchant/apply?merchant_id=${mid}`, { replace: true });
        }, 1500);
      } catch (e) {
        setState({ loading: false, error: e?.response?.data?.detail || e.message });
      }
    })();
  }, [mid, navigate]);

  const Icon = state.error ? AlertTriangle : state.status ? CheckCircle2 : Loader2;

  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50 flex items-center justify-center"
                          : "min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center"}
              data-testid="merchant-onboarding-complete-page">
      <div className={`max-w-md w-full mx-4 rounded-3xl p-8 text-center ${
        light ? "bg-white shadow-sm border border-slate-100"
                : "bg-slate-900 border border-slate-800"
      }`}>
        <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-4 ${
          state.error
            ? (light ? "bg-rose-100 text-rose-700" : "bg-rose-500/20 text-rose-300")
            : state.status
              ? (light ? "bg-emerald-100 text-emerald-700" : "bg-emerald-500/20 text-emerald-300")
              : (light ? "bg-purple-100 text-purple-700" : "bg-cyan-500/20 text-cyan-300")
        }`}>
          <Icon size={28} className={state.loading ? "animate-spin" : ""}/>
        </div>
        <h1 className={`text-2xl font-bold mb-1 ${light ? "text-slate-900" : "text-white"}`}>
          {state.error ? "We hit a snag"
                                : state.status ? "Stripe status refreshed"
                                : "Finalising Stripe setup…"}
        </h1>
        <p className={light ? "text-slate-600 text-sm" : "text-slate-400 text-sm"}>
          {state.error ? String(state.error)
                                : state.status ? `Status: ${state.status.replace(/_/g, " ")}. Redirecting…`
                                : "Fetching your latest Stripe account status."}
        </p>
        {state.error && (
          <button type="button" onClick={() => navigate(`/merchant/apply?merchant_id=${mid || ""}`)}
                        className="mt-6 px-5 h-11 rounded-full font-semibold text-white"
                        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}
                        data-testid="merchant-onboarding-back-to-wizard">
            Back to wizard
          </button>
        )}
      </div>
    </div>
  );
}
