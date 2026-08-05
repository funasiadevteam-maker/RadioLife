/** Phase 42-C — Public verification landing page.
 *
 *  Route: `/claim/verify/:verification_token`
 *
 *  Anonymous-friendly so the link in the (mocked) verification email
 *  can be opened from any email client without a session.  The page
 *  auto-POSTs to /api/radio/claims/verify/{token} on mount.
 */

import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link, useParams } from "react-router-dom";
import { Check, Loader2, AlertTriangle, ShieldCheck } from "lucide-react";
import { API } from "@/AuthContext";
import { useAuth } from "@/AuthContext";

export default function ClaimVerify() {
  const { verification_token } = useParams();
  const { user } = useAuth();
  const [state, setState] = useState("verifying"); // verifying|success|error|already
  const [data, setData] = useState(null);
  const [errCode, setErrCode] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setState("verifying"); setData(null); setErrCode(null);
    (async () => {
      try {
        const r = await axios.post(
          `${API}/radio/claims/verify/${verification_token}`, {});
        if (cancelled) return;
        if (r.data?.already_finalized) {
          setState("already");
        } else {
          setState("success");
        }
        setData(r.data);
      } catch (e) {
        if (cancelled) return;
        setErrCode(e.response?.data?.detail?.code || "unknown_error");
        setState("error");
      }
    })();
    return () => { cancelled = true; };
  }, [verification_token]);

  return (
    <div data-testid="claim-verify-page"
         data-state={state}
         className="text-white max-w-[640px] mx-auto px-5 py-16">
      {state === "verifying" && (
        <div data-testid="claim-verify-loading"
             className="flex items-center gap-3 text-white/70">
          <Loader2 size={18} className="animate-spin" />
          Verifying your claim…
        </div>
      )}

      {state === "success" && (
        <div data-testid="claim-verify-success">
          <div className="inline-flex items-center justify-center w-14 h-14
                          rounded-full bg-emerald-400/20 border
                          border-emerald-400/40 mb-5">
            <Check size={26} className="text-emerald-300" />
          </div>
          <h1 className="text-3xl font-bold mb-2">You're verified</h1>
          <p className="text-sm text-white/70 mb-6 max-w-prose">
            <strong className="text-white">{data?.station_name}</strong> is now
            officially yours on RadioLife. You can edit metadata, see listener
            stats, and configure payouts from the owner dashboard.
          </p>
          <div className="rounded-xl border border-white/[0.10]
                          bg-white/[0.03] p-4 mb-6 space-y-2 text-xs
                          font-mono text-white/60">
            <div>claim_id: <span className="text-white/90"
                                  data-testid="claim-verify-claim-id">
              {data?.claim_id}</span></div>
            <div>station_id: <span className="text-white/90"
                                    data-testid="claim-verify-station-id">
              {data?.station_id}</span></div>
            <div>profile_id: <span className="text-white/90">
              {data?.profile_id}</span></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/owner/dashboard"
                  data-testid="claim-verify-go-to-dashboard"
                  className="inline-flex items-center gap-1.5 px-4 h-10
                             rounded-full bg-cyan-400 text-slate-900
                             text-sm font-semibold hover:bg-cyan-300">
              <ShieldCheck size={13} /> Open owner dashboard
            </Link>
            {data?.station_id && (
              <Link to={`/radio/station/${data.station_id}`}
                    data-testid="claim-verify-go-to-station"
                    className="inline-flex items-center gap-1.5 px-4 h-10
                               rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                               border border-white/[0.10] text-sm">
                View station page
              </Link>
            )}
          </div>
          {!user && (
            <div className="mt-6 text-xs text-white/50">
              Tip: sign in with your RadioLife account to manage your station.
            </div>
          )}
        </div>
      )}

      {state === "already" && (
        <div data-testid="claim-verify-already-finalized">
          <div className="inline-flex items-center justify-center w-14 h-14
                          rounded-full bg-cyan-400/15 border
                          border-cyan-400/40 mb-5">
            <ShieldCheck size={26} className="text-cyan-300" />
          </div>
          <h1 className="text-2xl font-bold mb-2">This claim is already finalized</h1>
          <p className="text-sm text-white/70 mb-6">
            Status: <strong className="text-white">{data?.claim_status}</strong>.
            You can manage your station from the owner dashboard.
          </p>
          <Link to="/owner/dashboard"
                className="inline-flex items-center gap-1.5 px-4 h-10
                           rounded-full bg-cyan-400 text-slate-900
                           text-sm font-semibold hover:bg-cyan-300">
            Open owner dashboard
          </Link>
        </div>
      )}

      {state === "error" && (
        <div data-testid="claim-verify-error"
             data-error-code={errCode}>
          <div className="inline-flex items-center justify-center w-14 h-14
                          rounded-full bg-amber-400/15 border
                          border-amber-400/40 mb-5">
            <AlertTriangle size={26} className="text-amber-300" />
          </div>
          <h1 className="text-2xl font-bold mb-2">We couldn't verify that link</h1>
          <p className="text-sm text-white/70 mb-4">
            {errCode === "verification_token_not_found"
              ? "This verification link is invalid or has expired. If you submitted a claim recently, please request a fresh email or contact support."
              : errCode === "verification_not_email_path"
              ? "This claim isn't on the email-verification path. Please check your owner dashboard for status."
              : "Something went wrong while verifying your claim. Please try again or contact partners@bigfantv.com."}
          </p>
          <div className="text-[11px] font-mono text-white/40 mb-6">
            error_code: {errCode}
          </div>
          <Link to="/radio"
                className="inline-flex items-center gap-1.5 px-4 h-10
                           rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                           border border-white/[0.10] text-sm">
            ← Back to Radio
          </Link>
        </div>
      )}
    </div>
  );
}
