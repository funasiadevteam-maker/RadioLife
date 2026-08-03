// Phase MER.2 — Public staff-invite acceptance page.
// Fetches preview (public); prompts for sign-in if needed; accepts the
// invite via authenticated POST.
import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Loader2, Sparkles,
                  ArrowRight, ShieldAlert, Mail } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function StaffInvite() {
  const { token } = useParams();
  const navigate = useNavigate();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState(null);
  const [accepted, setAccepted] = useState(null);

  useEffect(() => {
    setLoading(true);
    axios.get(`${API}/staff/invite/${token}/preview`)
      .then((r) => setPreview(r.data))
      .catch((e) => setError(e?.response?.data?.detail?.detail
                                                    || e?.response?.data?.detail
                                                    || e.message))
      .finally(() => setLoading(false));
  }, [token]);

  const accept = async () => {
    setAccepting(true); setError(null);
    try {
      const { data } = await axios.post(`${API}/staff/invite/${token}/accept`,
                                                                        { display_name: user?.display_name
                                                                                                        || user?.name || undefined },
                                                                        { withCredentials: true });
      setAccepted(data);
      toast.success(`Welcome to ${preview.merchant_name}!`);
      setTimeout(() => navigate(data.redirect_to || "/merchant/dashboard"), 1200);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(d?.detail || d?.code || d || e.message);
    } finally { setAccepting(false); }
  };

  const bg = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50 flex items-center justify-center p-5"
    : "min-h-screen bg-slate-950 flex items-center justify-center p-5";
  const cardCls = light
    ? "bg-white shadow-lg border border-slate-100 rounded-3xl p-8 w-full max-w-md"
    : "bg-slate-900 border border-slate-800 rounded-3xl p-8 w-full max-w-md";

  if (loading || authLoading) {
    return (
      <div className={bg} data-testid="staff-invite-loading">
        <div className={cardCls}>
          <Loader2 className={`animate-spin mx-auto ${
            light ? "text-purple-600" : "text-cyan-400"
          }`} size={22}/>
        </div>
      </div>
    );
  }

  if (error && !preview) {
    return (
      <div className={bg} data-testid="staff-invite-error">
        <div className={cardCls}>
          <div className="text-center">
            <XCircle className={light ? "text-rose-600 mx-auto"
                                                            : "text-rose-400 mx-auto"} size={40}/>
            <h1 className={`mt-4 text-2xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`}>Invite unavailable</h1>
            <p className={`mt-2 text-sm ${
              light ? "text-slate-600" : "text-slate-400"
            }`}>{error}</p>
            <Link to="/"
                        className={`inline-block mt-6 h-11 px-6 rounded-full font-bold text-sm inline-flex items-center gap-1 ${
                          light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                  : "bg-slate-800 text-slate-200 hover:bg-slate-700"
                        }`}>Back to BigFM <ArrowRight size={14}/></Link>
          </div>
        </div>
      </div>
    );
  }

  const isPending = preview.status === "pending";
  const isExpired = preview.status === "expired";
  const isAccepted = preview.status === "accepted";
  const isRevoked = preview.status === "revoked";

  if (!isPending) {
    const meta = isAccepted
      ? { title: "Invite already accepted", desc: "You\u2019ve already joined this team." }
      : isExpired
      ? { title: "Invite expired", desc: "This link is more than 7 days old — ask the owner for a fresh invite." }
      : isRevoked
      ? { title: "Invite revoked", desc: "The team owner has revoked this invite." }
      : { title: "Invite unavailable", desc: `Status: ${preview.status}` };
    return (
      <div className={bg} data-testid="staff-invite-inactive">
        <div className={cardCls}>
          <div className="text-center">
            <ShieldAlert className={light ? "text-amber-600 mx-auto"
                                                                : "text-amber-400 mx-auto"} size={40}/>
            <h1 className={`mt-4 text-2xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`}>{meta.title}</h1>
            <p className={`mt-2 text-sm ${
              light ? "text-slate-600" : "text-slate-400"
            }`}>{meta.desc}</p>
          </div>
        </div>
      </div>
    );
  }

  if (accepted) {
    return (
      <div className={bg} data-testid="staff-invite-accepted">
        <div className={cardCls}>
          <div className="text-center">
            <CheckCircle2 className={light ? "text-emerald-600 mx-auto"
                                                                    : "text-emerald-400 mx-auto"} size={40}/>
            <h1 className={`mt-4 text-2xl font-black ${
              light ? "text-slate-900" : "text-white"
            }`}>You&apos;re in!</h1>
            <p className={`mt-2 text-sm ${
              light ? "text-slate-600" : "text-slate-400"
            }`}>Redirecting to your merchant portal…</p>
            <Loader2 className={`animate-spin mx-auto mt-4 ${
              light ? "text-purple-600" : "text-cyan-400"
            }`} size={18}/>
          </div>
        </div>
      </div>
    );
  }

  // ─── PENDING — show invite CTA ─────────────────────────────
  return (
    <div className={bg} data-testid="staff-invite-page">
      <div className={cardCls}>
        <div className="text-center">
          <div className={`inline-flex w-16 h-16 rounded-2xl items-center justify-center ${
            light ? "bg-purple-100 text-purple-700"
                    : "bg-cyan-500/15 text-cyan-300"
          }`}>
            <Sparkles size={30}/>
          </div>
          <div className={`text-[10px] font-black uppercase tracking-widest mt-4 ${
            light ? "text-purple-600" : "text-cyan-400"
          }`}>Team invite</div>
          <h1 className={`mt-1 text-2xl font-black ${
            light ? "text-slate-900" : "text-white"
          }`}>Join <span className="whitespace-nowrap">{preview.merchant_name}</span></h1>
          <p className={`mt-2 text-sm ${
            light ? "text-slate-600" : "text-slate-400"
          }`}>
            You&apos;ve been invited as a <b className={
              light ? "text-purple-700" : "text-cyan-300"
            }>{preview.role}</b>.
          </p>
        </div>

        <div className={`mt-6 rounded-xl p-4 ${
          light ? "bg-slate-50" : "bg-slate-950 border border-slate-800"
        }`}>
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>Invited email</div>
          <div className={`text-sm font-mono mt-0.5 ${
            light ? "text-slate-800" : "text-slate-200"
          }`}>{preview.email_masked}</div>
          <div className={`text-[10px] mt-2 ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>Expires {new Date(preview.expires_at)
                                                    .toLocaleDateString(undefined,
                { month: "short", day: "numeric", year: "numeric" })}</div>
        </div>

        {error && (
          <div className={`mt-4 rounded-lg p-3 text-xs ${
            light ? "bg-rose-50 text-rose-700 border border-rose-100"
                    : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
          }`} data-testid="staff-invite-form-error">{error}</div>
        )}

        {!user ? (
          <div className="mt-6 space-y-2">
            <Link to={`/login?next=/staff/invite/${token}`}
                        data-testid="staff-invite-login-cta"
                        className="w-full h-12 rounded-full font-black text-sm text-white inline-flex items-center justify-center"
                        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              Sign in to accept
            </Link>
            <Link to={`/register?next=/staff/invite/${token}`}
                        data-testid="staff-invite-register-cta"
                        className={`w-full h-12 rounded-full font-bold text-sm inline-flex items-center justify-center ${
                          light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                  : "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
                        }`}>
              Create account
            </Link>
          </div>
        ) : (
          <button onClick={accept} disabled={accepting}
                        data-testid="staff-invite-accept-btn"
                        className="w-full mt-6 h-12 rounded-full font-black text-sm text-white"
                        style={{ background: accepting ? "#94a3b8"
                                          : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {accepting ? "Accepting…" : `Accept as ${preview.role}`}
          </button>
        )}

        <div className={`text-center mt-4 text-[10px] font-black uppercase tracking-widest ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>Powered by BigFM</div>
      </div>
    </div>
  );
}
