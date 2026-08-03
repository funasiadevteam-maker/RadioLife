// Phase AD.6 — Advertiser staff invite accept page.
// Route: /advertiser-app/staff/accept/:token
// Public preview + authed accept.  Handles: pending / expired / accepted /
// revoked / not_found.  Redirects to /advertiser/dashboard/scan on success.
import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { Loader2, CheckCircle2, XCircle, ShieldCheck, LogIn } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const ROLE_LABEL = {
  manager:                "Manager",
  redemption_staff: "Redemption staff",
  analytics_only:    "Analytics only",
};

export default function AdvertiserStaffAccept() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState(null);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/advertiser-app/staff/invite/${token}/preview`)
      .then((r) => setPreview(r.data))
      .catch((e) => setError(e?.response?.data?.detail?.code || "invite_not_found"))
      .finally(() => setLoading(false));
  }, [token]);

  async function doAccept() {
    setAccepting(true); setError(null);
    try {
      await axios.post(`${API}/advertiser-app/staff/invite/${token}/accept`, {});
      setAccepted(true);
      setTimeout(() => navigate("/advertiser/dashboard/scan"), 1200);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || "accept_failed");
    } finally { setAccepting(false); }
  }

  const bg = light
    ? "bg-gradient-to-br from-fuchsia-50 via-white to-purple-50 text-slate-900"
    : "bg-slate-950 text-white";
  const cardCls = light
    ? "bg-white border border-slate-200 shadow-2xl"
    : "bg-slate-900 border border-slate-800 shadow-2xl";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`${bg} min-h-screen grid place-items-center p-4`}
              data-testid="advertiser-staff-accept-page">
      <div className={`${cardCls} rounded-3xl p-8 max-w-md w-full`}>
        <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500 text-center">
          Phase AD.6 · Team invite
        </div>

        {loading || authLoading ? (
          <div className="mt-4 text-center py-8">
            <Loader2 className="w-8 h-8 animate-spin text-amber-500 mx-auto" />
            <div className={`mt-3 text-sm ${muted}`}>Loading invite…</div>
          </div>
        ) : error === "invite_not_found" ? (
          <ErrorBlock title="Invite not found"
                                        body="Ask the person who invited you to send a fresh link."
                                        light={light} testid="advertiser-staff-accept-error-notfound" />
        ) : accepted ? (
          <div className="mt-6 text-center" data-testid="advertiser-staff-accept-success">
            <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
            <div className="mt-4 text-xl font-black">You’re in!</div>
            <div className={`text-sm ${muted} mt-1`}>Redirecting to the redemption scanner…</div>
          </div>
        ) : preview?.status === "expired" ? (
          <ErrorBlock title="Invite expired"
                                        body="Ask the owner to send you a fresh invite."
                                        light={light} testid="advertiser-staff-accept-expired" />
        ) : preview?.status === "accepted" ? (
          <ErrorBlock title="Already accepted"
                                        body="This invite was accepted earlier. Sign in and open the advertiser dashboard."
                                        light={light} testid="advertiser-staff-accept-already"
                                        cta={{label:"Go to dashboard", to:"/advertiser/dashboard/scan"}} />
        ) : preview?.status === "revoked" ? (
          <ErrorBlock title="Invite revoked"
                                        body="The owner has revoked this invite."
                                        light={light} testid="advertiser-staff-accept-revoked" />
        ) : !user ? (
          <div className="mt-6 text-center" data-testid="advertiser-staff-accept-signin">
            <div className="flex items-center justify-center gap-3">
              {preview?.advertiser_logo_url && (
                <img src={preview.advertiser_logo_url} alt=""
                          className="w-14 h-14 rounded-2xl object-cover bg-slate-800/40" />
              )}
              <div className="text-left">
                <div className={`text-xs uppercase tracking-widest font-mono ${muted}`}>invited to</div>
                <div className="text-xl font-black">{preview?.advertiser_name}</div>
              </div>
            </div>
            <div className={`mt-4 text-sm ${muted}`}>
              You’ve been invited as <span className="font-bold text-amber-500">{ROLE_LABEL[preview?.role] || preview?.role}</span>.
              Sign in to accept.
            </div>
            <Link to={`/login?next=/advertiser-app/staff/accept/${token}`}
                        className="mt-6 inline-flex items-center gap-2 bg-amber-500 text-slate-900 hover:bg-amber-400 rounded-full font-black px-6 py-3 transition"
                        data-testid="advertiser-staff-accept-signin-button">
              <LogIn className="w-4 h-4" /> Sign in to continue
            </Link>
          </div>
        ) : (
          <div className="mt-6" data-testid="advertiser-staff-accept-ready">
            <div className="flex items-center gap-3">
              {preview?.advertiser_logo_url && (
                <img src={preview.advertiser_logo_url} alt=""
                          className="w-16 h-16 rounded-2xl object-cover bg-slate-800/40 flex-shrink-0" />
              )}
              <div className="min-w-0">
                <div className={`text-xs uppercase tracking-widest font-mono ${muted}`}>invited to</div>
                <div className="text-xl font-black truncate">{preview?.advertiser_name}</div>
                <div className={`text-xs ${muted}`}>as <span className="text-amber-500 font-bold">{ROLE_LABEL[preview?.role] || preview?.role}</span></div>
              </div>
            </div>

            <div className={`mt-6 rounded-xl p-4 ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-950 border border-slate-800"}`}>
              <div className="text-xs font-black uppercase tracking-widest inline-flex items-center gap-1 text-amber-500">
                <ShieldCheck className="w-3.5 h-3.5" /> Signed in as
              </div>
              <div className="mt-1 text-sm">{user.email}</div>
            </div>

            {error && (
              <div className="mt-4 rounded-lg px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 text-sm"
                          data-testid="advertiser-staff-accept-error">
                {String(error)}
              </div>
            )}

            <button onClick={doAccept}
                            disabled={accepting}
                            data-testid="advertiser-staff-accept-submit"
                            className="mt-6 w-full inline-flex items-center justify-center gap-2 bg-amber-500 text-slate-900 hover:bg-amber-400 rounded-full font-black px-6 py-4 disabled:opacity-50 transition">
              {accepting ? <Loader2 className="w-5 h-5 animate-spin" /> : <CheckCircle2 className="w-5 h-5" />}
              Accept invite
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function ErrorBlock({ title, body, light, testid, cta }) {
  return (
    <div className="mt-6 text-center" data-testid={testid}>
      <XCircle className="w-12 h-12 text-red-500 mx-auto" />
      <div className="mt-4 text-xl font-black">{title}</div>
      <div className={`text-sm mt-2 ${light ? "text-slate-500" : "text-slate-400"}`}>
        {body}
      </div>
      {cta && (
        <Link to={cta.to}
                    className="mt-4 inline-flex items-center gap-2 bg-amber-500 text-slate-900 hover:bg-amber-400 rounded-full font-black px-6 py-3">
          {cta.label}
        </Link>
      )}
    </div>
  );
}
