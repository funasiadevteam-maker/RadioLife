// Phase AD.1 — Advertiser self-service signup.
// Public page at /advertiser/apply.  Auth required to save.

import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Building2, Mail, Globe, User, Phone, Loader2, ChevronRight, Gamepad2 } from "lucide-react";

import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const INDUSTRIES = [
  "Retail", "F&B", "Automotive", "Real Estate", "Financial Services",
  "Telco", "Health & Beauty", "Fashion", "Travel", "Entertainment",
  "Education", "Technology", "Other",
];

export default function AdvertiserApply() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  // Phase AD.6 · Bonus — deep-link prefill from merchant Sponsor CTA.
  const prefillGameId = search.get("prefill_game");
  const prefillGameName = search.get("game_name");

  const [name, setName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactName, setContactName] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState("");
  const [industry, setIndustry] = useState("Retail");
  const [logoUrl, setLogoUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (authLoading) return null;
  if (!user) {
    return (
      <div className={`${light ? "bg-white text-slate-900" : "bg-slate-950 text-white"} min-h-screen flex items-center justify-center p-8`}
                data-testid="advertiser-apply-anon">
        <div className="max-w-md w-full text-center">
          <div className="text-xs uppercase tracking-widest text-amber-500 font-mono">Sign in required</div>
          <h1 className="text-3xl font-bold mt-3">Become a RadioLife Advertiser</h1>
          <p className={`mt-3 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Sign in with your RadioLife account to apply for the advertiser dashboard.
          </p>
          <button onClick={() => navigate(`/login?next=/advertiser/apply`)}
                          data-testid="advertiser-apply-login-cta"
                          className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-amber-500 text-slate-950 font-semibold hover:bg-amber-400 transition">
            Sign in <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  async function submit(e) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) { setError("Company name is required."); return; }
    if (!contactEmail.trim() || !contactEmail.includes("@")) {
      setError("A valid contact email is required."); return;
    }
    setSubmitting(true);
    try {
      const { data } = await axios.post(`${API}/ad1/advertiser/register`, {
        name, contact_email: contactEmail, contact_name: contactName || null,
        phone: phone || null, website: website || null,
        industry, logo_url: logoUrl || null,
      });
      // Auto-submit for approval on create.
      try {
        await axios.post(`${API}/ad1/advertiser/${data.advertiser_id}/submit-for-approval`);
      } catch (_) {}
      navigate(`/advertiser/dashboard/overview?advertiser_id=${data.advertiser_id}`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "object" ? (detail.code || JSON.stringify(detail)) : (detail || err.message));
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls = `w-full px-4 py-2.5 rounded-lg border ${
    light ? "border-slate-300 bg-white focus:border-amber-500" :
                    "border-slate-700 bg-slate-900 focus:border-amber-500"
  } focus:outline-none focus:ring-2 focus:ring-amber-500/20 text-sm`;

  return (
    <div className={`${light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white"} min-h-screen`}
              data-testid="advertiser-apply-page">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Phase AD.1</div>
        <h1 className="text-4xl font-bold mt-2">Advertise on RadioLife</h1>
        <p className={`mt-3 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
          Reach commuting listeners across cities.  Register your brand — an admin will review and activate your account.
        </p>

        {/* Phase AD.6 · Bonus — sponsor-a-game deep-link banner. */}
        {prefillGameId && (
          <div className={`mt-6 rounded-2xl p-4 flex items-start gap-3 ${
                                            light ? "bg-amber-50 border border-amber-200"
                                                          : "bg-amber-500/10 border border-amber-500/30"}`}
                      data-testid="advertiser-apply-prefill-banner">
            <Gamepad2 className={`w-6 h-6 flex-shrink-0 ${light ? "text-amber-600" : "text-amber-400"}`} />
            <div className="min-w-0">
              <div className={`text-sm font-black ${light ? "text-amber-800" : "text-amber-300"}`}>
                Sponsor <span className="underline">{prefillGameName || "this game"}</span>
              </div>
              <div className={`text-xs mt-0.5 ${light ? "text-amber-700/90" : "text-amber-200/80"}`}>
                Complete your registration below.  After approval, you can attach a brand + budget to <code className="font-mono text-[10px]">{prefillGameId.slice(0,16)}</code> in <b>Campaigns → Sponsor a game</b>.
              </div>
            </div>
          </div>
        )}

        <form onSubmit={submit} className="mt-8 space-y-5"
                    data-testid="advertiser-apply-form">
          <Field label="Company / Brand name *" Icon={Building2}>
            <input type="text" required value={name} onChange={(e) => setName(e.target.value)}
                          className={inputCls} placeholder="Acme Corp"
                          data-testid="advertiser-apply-name" />
          </Field>
          <Field label="Contact email *" Icon={Mail}>
            <input type="email" required value={contactEmail} onChange={(e) => setContactEmail(e.target.value)}
                          className={inputCls} placeholder="ads@acme.com"
                          data-testid="advertiser-apply-email" />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Contact name" Icon={User}>
              <input type="text" value={contactName} onChange={(e) => setContactName(e.target.value)}
                            className={inputCls} placeholder="Jane Doe"
                            data-testid="advertiser-apply-contact-name" />
            </Field>
            <Field label="Phone" Icon={Phone}>
              <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
                            className={inputCls} placeholder="+971-…"
                            data-testid="advertiser-apply-phone" />
            </Field>
          </div>
          <Field label="Website" Icon={Globe}>
            <input type="url" value={website} onChange={(e) => setWebsite(e.target.value)}
                          className={inputCls} placeholder="https://acme.com"
                          data-testid="advertiser-apply-website" />
          </Field>
          <Field label="Industry">
            <select value={industry} onChange={(e) => setIndustry(e.target.value)}
                            className={inputCls} data-testid="advertiser-apply-industry">
              {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </Field>
          <Field label="Logo URL (optional)">
            <input type="url" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)}
                          className={inputCls} placeholder="https://.../logo.png"
                          data-testid="advertiser-apply-logo" />
          </Field>

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-400"
                        data-testid="advertiser-apply-error">
              {error}
            </div>
          )}

          <button type="submit" disabled={submitting}
                          data-testid="advertiser-apply-submit"
                          className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full bg-amber-500 text-slate-950 font-semibold hover:bg-amber-400 disabled:opacity-50 transition">
            {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Submitting…</> :
                                          <>Submit application <ChevronRight className="w-4 h-4" /></>}
          </button>
          <p className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            After submission, an admin will review and activate your account within 1 business day.
          </p>
        </form>
      </div>
    </div>
  );
}

function Field({ label, Icon, children }) {
  return (
    <label className="block">
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-widest font-mono text-slate-500 mb-1.5">
        {Icon && <Icon className="w-3 h-3" />} {label}
      </div>
      {children}
    </label>
  );
}
