/** Phase 42-C — Station claim 4-step wizard.
 *
 *  Route: `/claim/station/:station_id`
 *
 *  Step 1 — Identify station (read-only summary, derived from station detail).
 *  Step 2 — Organization & contact (org name, contact email, contact role).
 *  Step 3 — Partner terms (checkbox + readable terms block).
 *  Step 4 — Submit + result screen (auto-verified-via-email vs queued-for-admin).
 */

import React, { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, ArrowRight, Check, Loader2, ShieldCheck, AlertTriangle,
  Mail, Building2, FileText, Radio as RadioIcon, ExternalLink,
} from "lucide-react";
import { API } from "@/AuthContext";
import { useAuth } from "@/AuthContext";
// Phase CLAIM.1b — design variant + proof upload types.
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { Upload, FileImage, Trash2 } from "lucide-react";

const STEPS = [
  { n: 1, label: "Station",           icon: RadioIcon },
  { n: 2, label: "Your details",    icon: Building2 },
  { n: 3, label: "Partner terms", icon: FileText },
  { n: 4, label: "Proof",                icon: Upload },
  { n: 5, label: "Submit",              icon: ShieldCheck },
];

// Phase CLAIM.1b — proof document types accepted by the backend.
// See `services/station_upload_service.py :: DOC_TYPES`.
const PROOF_DOC_TYPES = [
  { key: "business_card",                          label: "Business card image",             required: true },
  { key: "business_email_screenshot", label: "Business email screenshot", required: true },
  { key: "government_id",                          label: "Government ID (optional)",   required: false },
  { key: "station_license",                      label: "Station license (optional)", required: false },
];

function StepDots({ step }) {
  return (
    <ol data-testid="claim-wizard-step-dots"
        className="flex items-center gap-2 mb-8">
      {STEPS.map((s, i) => {
        const done = step > s.n;
        const active = step === s.n;
        const Icon = s.icon;
        return (
          <li key={s.n}
              data-testid={`claim-wizard-step-${s.n}-${active ? "active" : done ? "done" : "pending"}`}
              className="flex items-center gap-2">
            <span className={[
              "inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-mono",
              done ? "bg-cyan-400 text-slate-900" :
              active ? "bg-cyan-400/20 text-cyan-200 border border-cyan-400/40" :
              "bg-white/[0.06] text-white/40 border border-white/[0.10]",
            ].join(" ")}>
              {done ? <Check size={13} /> : <Icon size={13} />}
            </span>
            <span className={[
              "text-xs",
              active ? "text-white" : done ? "text-white/70" : "text-white/40",
            ].join(" ")}>{s.label}</span>
            {i < STEPS.length - 1 && (
              <span className="w-8 h-px bg-white/[0.10] mx-1" />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function ClaimStationWizard() {
  const { station_id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  // Phase CLAIM.1b — design variant.
  const variant = useDesignVariant();
  const light = variant === "radiolife";

  const [station, setStation] = useState(null);
  const [loadErr, setLoadErr] = useState(null);
  const [loading, setLoading] = useState(true);

  const [step, setStep] = useState(1);
  const [orgName, setOrgName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactRole, setContactRole] = useState("Station Manager");
  const [agree, setAgree] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  // Phase CLAIM.1b — proof docs {business_card: File, business_email_screenshot: File, …}
  const [proofFiles, setProofFiles] = useState({});

  // Load station.
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setLoadErr(null);
    (async () => {
      try {
        const r = await axios.get(`${API}/live-radio/stations/${station_id}`);
        if (cancelled) return;
        setStation(r.data?.station || null);
      } catch (e) {
        if (cancelled) return;
        setLoadErr(e.response?.data?.detail?.code || "load_failed");
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [station_id]);

  // Pre-fill contact email from logged-in user.
  useEffect(() => {
    if (user?.email && !contactEmail) setContactEmail(user.email);
  }, [user, contactEmail]);

  const homepage = station?.homepage || "";
  const homepageDomain = useMemo(() => {
    try {
      if (!homepage) return null;
      const u = new URL(homepage.startsWith("http") ? homepage : `http://${homepage}`);
      let h = (u.hostname || "").toLowerCase();
      if (h.startsWith("www.")) h = h.slice(4);
      return h || null;
    } catch { return null; }
  }, [homepage]);

  const willAutoVerify = useMemo(() => {
    if (!homepageDomain || !contactEmail) return false;
    const m = contactEmail.trim().toLowerCase().match(/^[^\s@]+@([^\s@]+)$/);
    if (!m) return false;
    const eh = m[1];
    return eh === homepageDomain || eh.endsWith("." + homepageDomain);
  }, [contactEmail, homepageDomain]);

  // ─── auth gate ───
  if (!authLoading && !user) {
    return (
      <div data-testid="claim-wizard-auth-gate"
           className="text-white max-w-[640px] mx-auto px-5 py-16">
        <h1 className="text-2xl font-bold mb-3">Sign in to claim this station</h1>
        <p className="text-sm text-white/60 mb-6">
          Station ownership is tied to your RadioLife account. Sign in or create
          an account to continue with the claim.
        </p>
        <Link to={`/?next=/claim/station/${station_id}`}
              data-testid="claim-wizard-signin-link"
              className="inline-flex items-center gap-2 px-4 h-10 rounded-full
                         bg-cyan-400 text-slate-900 text-sm font-semibold
                         hover:bg-cyan-300 transition-colors">
          Sign in
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div data-testid="claim-wizard-loading"
           className="text-white max-w-[760px] mx-auto px-5 py-16
                      flex items-center gap-3 text-white/60">
        <Loader2 size={16} className="animate-spin" />
        Loading station…
      </div>
    );
  }

  if (loadErr || !station) {
    return (
      <div data-testid="claim-wizard-error"
           className="text-white max-w-[760px] mx-auto px-5 py-16">
        <h1 className="text-xl font-bold mb-2">Station not found</h1>
        <p className="text-sm text-white/60 mb-4">
          We couldn't load that station. It may have been removed from the
          imported catalog.
        </p>
        <Link to="/radio"
              className="text-xs text-cyan-300 hover:text-cyan-200">
          ← Back to Radio
        </Link>
      </div>
    );
  }

  if (station.source === "bigfm_ai") {
    return (
      <div data-testid="claim-wizard-not-claimable-ai"
           className="text-white max-w-[760px] mx-auto px-5 py-16">
        <h1 className="text-xl font-bold mb-2">This is a RadioLife AI channel</h1>
        <p className="text-sm text-white/60 mb-4">
          AI-curated channels are operated by RadioLife and aren't available to
          claim. Only imported live radio stations (Radio Browser catalog)
          can be claimed.
        </p>
        <Link to={`/radio/station/${station_id}`}
              className="text-xs text-cyan-300 hover:text-cyan-200">
          ← Back to station
        </Link>
      </div>
    );
  }

  if (station.claim_status === "claimed") {
    return (
      <div data-testid="claim-wizard-already-claimed"
           className="text-white max-w-[760px] mx-auto px-5 py-16">
        <div className="inline-flex items-center gap-2 px-3 h-7 rounded-full
                        bg-emerald-400/15 border border-emerald-400/30
                        text-emerald-300 text-xs mb-3">
          <ShieldCheck size={12} /> Verified owner
        </div>
        <h1 className="text-xl font-bold mb-2">This station is already claimed</h1>
        <p className="text-sm text-white/60 mb-4">
          A verified owner is managing <strong>{station.name}</strong>. If you
          believe this is a mistake, contact{" "}
          <a className="text-cyan-300 hover:text-cyan-200"
             href="mailto:partners@bigfantv.com">partners@bigfantv.com</a>.
        </p>
        <Link to={`/radio/station/${station_id}`}
              className="text-xs text-cyan-300 hover:text-cyan-200">
          ← Back to station
        </Link>
      </div>
    );
  }

  // ─── handlers ───
  const next = () => setStep((s) => Math.min(5, s + 1));
  const back = () => setStep((s) => Math.max(1, s - 1));

  const validateStep2 = () => {
    if (!orgName.trim()) return "Please add your organization or station name.";
    if (!contactEmail.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail))
      return "Please enter a valid contact email.";
    if (!contactRole.trim()) return "Please add your role (e.g. Station Manager).";
    return null;
  };

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      const payload = {
        station_id:                station.id,
        organization_name: orgName.trim(),
        contact_email:          contactEmail.trim(),
        contact_role:            contactRole.trim(),
        agreement_accepted: agree,
      };
      // Phase CLAIM.1b — multipart when proofs attached, JSON otherwise.
      const attachedTypes = Object.keys(proofFiles).filter((k) => proofFiles[k]);
      let r;
      if (attachedTypes.length > 0) {
        const fd = new FormData();
        fd.append("payload", JSON.stringify(payload));
        for (const t of attachedTypes) {
          fd.append("proof_files", proofFiles[t]);
          fd.append("document_types", t);
        }
        r = await axios.post(`${API}/radio/claims`, fd,
          { withCredentials: true,
              headers: { "Content-Type": "multipart/form-data" } });
      } else {
        r = await axios.post(`${API}/radio/claims`, payload,
          { withCredentials: true });
      }
      setResult(r.data?.claim || null);
      setStep(5);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      const msg = e.response?.data?.detail?.message;
      if (code === "already_claimed") {
        toast.error("This station was just claimed by someone else.");
        navigate(`/radio/station/${station_id}`);
        return;
      }
      if (code === "active_claim_exists") {
        toast.error("You already have an active claim for this station.");
        navigate("/owner/dashboard");
        return;
      }
      toast.error(msg || code || "Failed to submit claim — try again.");
    } finally {
      setSubmitting(false);
    }
  };

  // Phase CLAIM.1b — proof upload validation.
  const proofsValid = () => {
    const missingRequired = PROOF_DOC_TYPES
      .filter((d) => d.required && !proofFiles[d.key]);
    return missingRequired.length === 0;
  };

  // ─── render ───
  return (
    <div data-testid="claim-wizard-page"
         data-station-id={station_id}
         data-step={step}
         className="text-white max-w-[760px] mx-auto px-5 pt-6 pb-24">
      <Link to={`/radio/station/${station_id}`}
            data-testid="claim-wizard-back"
            className="inline-flex items-center gap-1 text-xs
                       text-white/50 hover:text-white mb-6">
        <ArrowLeft size={12} /> Back to station
      </Link>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
        Claim your station
      </h1>
      <p className="text-sm text-white/50 mb-8 max-w-prose">
        Verify that you operate <strong className="text-white/80">{station.name}</strong>{" "}
        and unlock the owner dashboard — manage metadata, see listener stats,
        and (soon) collect ad revenue.
      </p>

      <StepDots step={step} />

      {/* ─── STEP 1 ─── */}
      {step === 1 && (
        <section data-testid="claim-wizard-step-1"
                 className="rounded-2xl border border-white/[0.10]
                            bg-white/[0.03] p-6 mb-6">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-3 inline-flex items-center gap-1.5">
            <RadioIcon size={11} /> Station you're claiming
          </div>
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 rounded-lg bg-gradient-to-br
                            from-slate-700 to-slate-900 flex items-center
                            justify-center flex-shrink-0 overflow-hidden">
              {station.favicon && (
                <img src={station.favicon} alt=""
                     onError={(e) => { e.currentTarget.style.display = "none"; }}
                     className="w-full h-full object-cover" />
              )}
            </div>
            <div className="flex-grow min-w-0">
              <div data-testid="claim-wizard-station-name"
                   className="font-semibold text-lg mb-1">{station.name}</div>
              <div className="text-xs text-white/50 flex flex-wrap gap-x-3 gap-y-1">
                {station.country && <span>{station.country}</span>}
                {station.language && <span className="capitalize">{station.language}</span>}
                {station.bitrate ? <span>{station.bitrate} kbps</span> : null}
              </div>
              {homepage && (
                <a href={homepage} target="_blank" rel="noopener noreferrer"
                   data-testid="claim-wizard-station-homepage"
                   className="inline-flex items-center gap-1.5 mt-2 text-xs
                              text-cyan-300 hover:text-cyan-200">
                  <ExternalLink size={11} /> {homepage}
                </a>
              )}
            </div>
          </div>
          {homepageDomain ? (
            <div data-testid="claim-wizard-domain-hint"
                 className="mt-5 px-3 py-2 rounded-lg bg-cyan-400/[0.06]
                            border border-cyan-400/20 text-cyan-200 text-xs">
              <strong>Fast track:</strong> If your contact email ends with
              <strong> @{homepageDomain}</strong> (or a subdomain of it), we'll
              auto-verify ownership via email.
            </div>
          ) : (
            <div data-testid="claim-wizard-no-domain-hint"
                 className="mt-5 px-3 py-2 rounded-lg bg-amber-400/[0.06]
                            border border-amber-400/20 text-amber-200 text-xs">
              <AlertTriangle size={11} className="inline mr-1" />
              This station has no homepage on file, so your claim will go
              through manual admin review (1–3 business days).
            </div>
          )}
          <div className="mt-6 flex justify-end">
            <button type="button" onClick={next}
                    data-testid="claim-wizard-step-1-next"
                    className="inline-flex items-center gap-2 px-5 h-10
                               rounded-full bg-cyan-400 text-slate-900
                               text-sm font-semibold hover:bg-cyan-300">
              Continue <ArrowRight size={13} />
            </button>
          </div>
        </section>
      )}

      {/* ─── STEP 2 ─── */}
      {step === 2 && (
        <section data-testid="claim-wizard-step-2"
                 className="rounded-2xl border border-white/[0.10]
                            bg-white/[0.03] p-6 mb-6 space-y-4">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-2 inline-flex items-center gap-1.5">
            <Building2 size={11} /> Your details
          </div>
          <div>
            <label className="block text-xs text-white/60 mb-1">
              Organization / station name
            </label>
            <input
              type="text" value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              data-testid="claim-wizard-org-name"
              placeholder="e.g. Radio Paradise Inc."
              className="w-full px-3 h-10 rounded-lg bg-black/40
                         border border-white/[0.10] text-sm
                         placeholder:text-white/30 focus:border-cyan-400/50
                         focus:outline-none" />
          </div>
          <div>
            <label className="block text-xs text-white/60 mb-1">
              Contact email
            </label>
            <input
              type="email" value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              data-testid="claim-wizard-contact-email"
              placeholder={homepageDomain ? `press@${homepageDomain}` : "you@station.com"}
              className="w-full px-3 h-10 rounded-lg bg-black/40
                         border border-white/[0.10] text-sm
                         placeholder:text-white/30 focus:border-cyan-400/50
                         focus:outline-none" />
            <div className="text-[11px] mt-1.5 flex items-center gap-1.5"
                 data-testid="claim-wizard-verify-mode"
                 data-mode={willAutoVerify ? "email_domain" : "manual_admin"}>
              {willAutoVerify ? (
                <><Mail size={11} className="text-emerald-300" />
                  <span className="text-emerald-300">Email domain matches — auto-verify path</span></>
              ) : (
                <><AlertTriangle size={11} className="text-amber-300" />
                  <span className="text-amber-300">No domain match — manual admin review</span></>
              )}
            </div>
          </div>
          <div>
            <label className="block text-xs text-white/60 mb-1">
              Your role
            </label>
            <input
              type="text" value={contactRole}
              onChange={(e) => setContactRole(e.target.value)}
              data-testid="claim-wizard-contact-role"
              placeholder="Station Manager / Owner / Press Officer"
              className="w-full px-3 h-10 rounded-lg bg-black/40
                         border border-white/[0.10] text-sm
                         placeholder:text-white/30 focus:border-cyan-400/50
                         focus:outline-none" />
          </div>
          <div className="flex justify-between pt-2">
            <button type="button" onClick={back}
                    data-testid="claim-wizard-step-2-back"
                    className="inline-flex items-center gap-1.5 px-4 h-10
                               rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                               border border-white/[0.10] text-sm">
              <ArrowLeft size={13} /> Back
            </button>
            <button type="button" data-testid="claim-wizard-step-2-next"
                    onClick={() => {
                      const err = validateStep2();
                      if (err) { toast.error(err); return; }
                      next();
                    }}
                    className="inline-flex items-center gap-2 px-5 h-10
                               rounded-full bg-cyan-400 text-slate-900
                               text-sm font-semibold hover:bg-cyan-300">
              Continue <ArrowRight size={13} />
            </button>
          </div>
        </section>
      )}

      {/* ─── STEP 3 ─── */}
      {step === 3 && (
        <section data-testid="claim-wizard-step-3"
                 className="rounded-2xl border border-white/[0.10]
                            bg-white/[0.03] p-6 mb-6">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-3 inline-flex items-center gap-1.5">
            <FileText size={11} /> Partner terms (v1.0)
          </div>
          <div data-testid="claim-wizard-terms-body"
               className="rounded-lg border border-white/[0.10]
                          bg-black/40 p-4 text-xs leading-relaxed
                          text-white/70 max-h-[260px] overflow-auto mb-4
                          space-y-2.5">
            <p><strong className="text-white/90">1. Eligibility.</strong> You
            represent that you are an authorized agent of the radio station,
            with legal authority to manage its presence on RadioLife.</p>
            <p><strong className="text-white/90">2. Content.</strong> You
            consent to RadioLife displaying the station's public metadata
            (name, logo, country, language, homepage, stream URL) sourced
            from Radio Browser and any owner-supplied overrides you publish.</p>
            <p><strong className="text-white/90">3. Stream rights.</strong> You
            confirm that your station's broadcast stream is lawfully licensed
            in its country of origin and that you have the right to make
            it publicly available.</p>
            <p><strong className="text-white/90">4. Listener data.</strong> You
            will receive aggregate, anonymized listener counts and playback
            metrics. No personally-identifying data is shared with station
            owners.</p>
            <p><strong className="text-white/90">5. Ad revenue.</strong> Once
            you complete payout setup (Phase 42-D), RadioLife will share net
            advertising revenue earned against your station per the rate
            card published in your owner dashboard.</p>
            <p><strong className="text-white/90">6. Compliance.</strong> Your
            station must remain in good standing with RadioLife's content
            guidelines (no hate speech, no copyright infringement, no
            illegal content). Violations may result in claim revocation.</p>
            <p><strong className="text-white/90">7. Termination.</strong> Either
            party may terminate this partnership at any time. On termination,
            owner overrides revert to the Radio Browser source data.</p>
          </div>
          <label className="flex items-start gap-3 cursor-pointer
                            select-none p-3 rounded-lg
                            bg-white/[0.04] hover:bg-white/[0.06]
                            border border-white/[0.10]">
            <input
              type="checkbox" checked={agree}
              onChange={(e) => setAgree(e.target.checked)}
              data-testid="claim-wizard-agree"
              className="mt-0.5 accent-cyan-400" />
            <span className="text-xs text-white/80">
              I have read and agree to the RadioLife Partner Terms (v1.0). I
              confirm that I am authorized to act on behalf of this station.
            </span>
          </label>
          <div className="flex justify-between mt-5">
            <button type="button" onClick={back}
                    data-testid="claim-wizard-step-3-back"
                    className="inline-flex items-center gap-1.5 px-4 h-10
                               rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                               border border-white/[0.10] text-sm">
              <ArrowLeft size={13} /> Back
            </button>
            <button type="button" data-testid="claim-wizard-step-3-next"
                    onClick={next} disabled={!agree}
                    className="inline-flex items-center gap-2 px-5 h-10
                               rounded-full bg-cyan-400 text-slate-900
                               text-sm font-semibold hover:bg-cyan-300
                               disabled:opacity-40 disabled:cursor-not-allowed">
              Continue <ArrowRight size={13} />
            </button>
          </div>
        </section>
      )}

      {/* ─── STEP 4 — PROOF UPLOAD (CLAIM.1b) ─── */}
      {step === 4 && (
        <section data-testid="claim-wizard-step-4"
                          className={"rounded-2xl border p-6 mb-6 " + (light
                            ? "bg-white border-slate-200"
                            : "border-white/[0.10] bg-white/[0.03]")}>
          <div className={"text-xs uppercase tracking-widest font-mono mb-3 " +
                                        "inline-flex items-center gap-1.5 " +
                                        (light ? "text-slate-500" : "text-white/40")}>
            <Upload size={11} /> Proof of ownership
          </div>
          <p className={"text-sm mb-4 " +
                                    (light ? "text-slate-600" : "text-white/60")}>
            Upload proof that you represent this station. Business card + a
            screenshot from your business email are required; government ID
            and station license are optional but speed up manual review.
          </p>
          <div className="space-y-3 mb-4">
            {PROOF_DOC_TYPES.map((doc) => {
              const file = proofFiles[doc.key];
              return (
                <div key={doc.key}
                          data-testid={`claim-wizard-file-row-${doc.key}`}
                          className={"rounded-lg p-3 flex items-center gap-3 " +
                                                    (light
                                                        ? "bg-slate-50 border border-slate-200"
                                                        : "bg-black/40 border border-white/[0.10]")}>
                  <div className={"w-9 h-9 rounded flex items-center justify-center flex-shrink-0 " +
                                                (file
                                                    ? (light ? "bg-emerald-100 text-emerald-700"
                                                                        : "bg-emerald-400/15 text-emerald-300")
                                                    : (light ? "bg-slate-200 text-slate-500"
                                                                        : "bg-white/[0.06] text-white/50"))}>
                    <FileImage size={16} />
                  </div>
                  <div className="flex-grow min-w-0">
                    <div className={"text-sm font-semibold " +
                                                (light ? "text-slate-900" : "text-white")}>
                      {doc.label}
                      {doc.required && (
                        <span className={"ml-1.5 text-[10px] font-mono " +
                                                            (light ? "text-rose-600" : "text-rose-300")}>
                          required
                        </span>
                      )}
                    </div>
                    {file && (
                      <div className={"text-[11px] mt-0.5 truncate " +
                                                        (light ? "text-slate-500" : "text-white/50")}>
                        {file.name} · {(file.size / 1024).toFixed(0)} KB
                      </div>
                    )}
                  </div>
                  {file ? (
                    <button type="button"
                                    onClick={() => setProofFiles((p) => {
                                      const n = { ...p }; delete n[doc.key]; return n;
                                    })}
                                    data-testid={`claim-wizard-file-remove-${doc.key}`}
                                    className={"p-1.5 rounded " +
                                                          (light
                                                              ? "text-rose-600 hover:bg-rose-50"
                                                              : "text-rose-300 hover:bg-white/[0.06]")}>
                      <Trash2 size={13} />
                    </button>
                  ) : (
                    <label className={"px-3 h-8 rounded-full text-xs font-semibold cursor-pointer " +
                                                            "inline-flex items-center gap-1 " +
                                                            (light
                                                                ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                                : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
                      <Upload size={11} /> Upload
                      <input type="file" hidden
                                    accept="image/*,application/pdf"
                                    data-testid={`claim-wizard-file-upload-${doc.key}`}
                                    onChange={(e) => {
                                      const f = e.target.files && e.target.files[0];
                                      if (!f) return;
                                      if (f.size > 8 * 1024 * 1024) {
                                        toast.error("File exceeds 8 MB");
                                        return;
                                      }
                                      setProofFiles((p) => ({ ...p, [doc.key]: f }));
                                    }} />
                    </label>
                  )}
                </div>
              );
            })}
          </div>
          <div className={"px-3 py-2 rounded-lg text-xs mb-4 " +
                                        (light
                                            ? "bg-amber-50 border border-amber-200 text-amber-800"
                                            : "bg-amber-400/[0.06] border border-amber-400/20 text-amber-200")}>
            <AlertTriangle size={11} className="inline mr-1" />
            Proof documents are stored privately and only visible to RadioLife
            admins during review.  Max 8 MB per file (PNG / JPG / PDF).
          </div>
          <div className="flex justify-between">
            <button type="button" onClick={back}
                            data-testid="claim-wizard-step-4-back"
                            className={"inline-flex items-center gap-1.5 px-4 h-10 rounded-full text-sm " +
                                                (light
                                                    ? "bg-slate-200 text-slate-800 hover:bg-slate-300"
                                                    : "bg-white/[0.06] hover:bg-white/[0.10] border border-white/[0.10]")}>
              <ArrowLeft size={13} /> Back
            </button>
            <button type="button"
                            onClick={() => {
                              if (!proofsValid()) {
                                toast.error("Please upload both required documents.");
                                return;
                              }
                              next();
                            }}
                            data-testid="claim-wizard-step-4-next"
                            className={"inline-flex items-center gap-2 px-5 h-10 rounded-full text-sm font-semibold " +
                                                (light
                                                    ? "bg-fuchsia-600 text-white hover:bg-fuchsia-500"
                                                    : "bg-cyan-400 text-slate-900 hover:bg-cyan-300")}>
              Continue <ArrowRight size={13} />
            </button>
          </div>
        </section>
      )}

      {/* ─── STEP 5 — SUBMIT or RESULT ─── */}
      {step === 5 && !result && (
        <section data-testid="claim-wizard-step-5"
                 className="rounded-2xl border border-white/[0.10]
                            bg-white/[0.03] p-6 mb-6">
          <div className="text-xs uppercase tracking-widest text-white/40
                          font-mono mb-4 inline-flex items-center gap-1.5">
            <ShieldCheck size={11} /> Review &amp; submit
          </div>
          <dl className="space-y-2.5 text-sm mb-6">
            <div className="flex justify-between gap-4">
              <dt className="text-white/50">Station</dt>
              <dd className="text-white text-right">{station.name}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-white/50">Organization</dt>
              <dd className="text-white text-right">{orgName}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-white/50">Contact</dt>
              <dd className="text-white text-right">{contactEmail}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-white/50">Role</dt>
              <dd className="text-white text-right">{contactRole}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-white/50">Verification path</dt>
              <dd className={[
                "text-right", willAutoVerify ? "text-emerald-300" : "text-amber-300",
              ].join(" ")}>
                {willAutoVerify ? "Email domain (auto)" : "Manual admin review"}
              </dd>
            </div>
          </dl>
          <div className="flex justify-between">
            <button type="button" onClick={back}
                    data-testid="claim-wizard-step-5-back"
                    disabled={submitting}
                    className="inline-flex items-center gap-1.5 px-4 h-10
                                              rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                                              border border-white/[0.10] text-sm
                                              disabled:opacity-40">
              <ArrowLeft size={13} /> Back
            </button>
            <button type="button" onClick={onSubmit}
                    data-testid="claim-wizard-submit"
                    disabled={submitting}
                    className="inline-flex items-center gap-2 px-5 h-10
                               rounded-full bg-cyan-400 text-slate-900
                               text-sm font-semibold hover:bg-cyan-300
                               disabled:opacity-50">
              {submitting && <Loader2 size={13} className="animate-spin" />}
              Submit claim
            </button>
          </div>
        </section>
      )}

      {step === 5 && result && (
        <section data-testid="claim-wizard-result"
                 data-claim-status={result.claim_status}
                 data-verification-method={result.verification_method}
                 className="rounded-2xl border border-emerald-400/30
                            bg-emerald-400/[0.06] p-6 mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12
                          rounded-full bg-emerald-400/20 border
                          border-emerald-400/30 mb-4">
            <Check size={22} className="text-emerald-300" />
          </div>
          {result.verification_method === "email_domain" ? (
            <>
              <h2 className="text-xl font-bold mb-2">
                Check your inbox to finish verifying
              </h2>
              <p className="text-sm text-white/70 mb-4">
                We've sent a verification link to{" "}
                <strong className="text-white">{result.contact_email}</strong>.
                Click the link in that email to activate ownership of{" "}
                <strong className="text-white">{result.station_name_snapshot}</strong>.
              </p>
              <div className="text-xs text-white/50 mb-5">
                Don't see it? Check spam, or trigger admin review by
                contacting <a className="text-cyan-300"
                href="mailto:partners@bigfantv.com">partners@bigfantv.com</a>.
              </div>
            </>
          ) : (
            <>
              <h2 className="text-xl font-bold mb-2">
                Your claim is queued for admin review
              </h2>
              <p className="text-sm text-white/70 mb-4">
                We weren't able to auto-verify because your contact email's
                domain doesn't match the station homepage. A RadioLife partner
                manager will review your submission within{" "}
                <strong className="text-white">1–3 business days</strong> and
                reach out at <strong className="text-white">{result.contact_email}</strong>.
              </p>
            </>
          )}
          <div className="flex flex-wrap gap-2">
            <Link to="/owner/dashboard"
                  data-testid="claim-wizard-go-to-dashboard"
                  className="inline-flex items-center gap-1.5 px-4 h-10
                             rounded-full bg-cyan-400 text-slate-900
                             text-sm font-semibold hover:bg-cyan-300">
              Open owner dashboard
            </Link>
            <Link to={`/radio/station/${station_id}`}
                  data-testid="claim-wizard-back-to-station"
                  className="inline-flex items-center gap-1.5 px-4 h-10
                             rounded-full bg-white/[0.06] hover:bg-white/[0.10]
                             border border-white/[0.10] text-sm">
              Back to station
            </Link>
          </div>
          <div className="mt-5 pt-5 border-t border-white/[0.06]
                          text-[11px] text-white/40 font-mono">
            Claim ID: <span data-testid="claim-wizard-claim-id">{result.id}</span>
          </div>
        </section>
      )}
    </div>
  );
}
