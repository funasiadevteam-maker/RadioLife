// Phase AD.1 — Profile tab: edit brand details.
// Phase AD.12 bundle — Weekly-digest opt-out toggle.
import { useEffect, useState } from "react";
import axios from "axios";
import { Save, Loader2, CheckCircle2, Mail } from "lucide-react";

import { useAdvertiser } from "./AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function AdvertiserProfile() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active } = useAdvertiser();
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [error, setError] = useState(null);
  // Phase AD.12 bundle — digest preference (opt-out semantics: default ON).
  const [digestOn, setDigestOn] = useState(true);
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestFlash, setDigestFlash] = useState(false);

  useEffect(() => {
    if (active) {
      setForm({
        name: active.name || "", contact_email: active.contact_email || "",
        contact_name: active.contact_name || "", phone: active.phone || "",
        website: active.website || "", industry: active.industry || "",
        logo_url: active.logo_url || "",
      });
      // Load digest preference.
      axios.get(`${API}/advertiser/${active.advertiser_id}/digest/preferences`,
                          { withCredentials: true })
        .then((r) => setDigestOn(!!r.data?.email_weekly_digest))
        .catch(() => setDigestOn(true));
    }
  }, [active]);

  async function toggleDigest() {
    if (!active) return;
    setDigestBusy(true);
    try {
      const next = !digestOn;
      await axios.patch(
        `${API}/advertiser/${active.advertiser_id}/digest/preferences`,
        { email_weekly_digest: next }, { withCredentials: true });
      setDigestOn(next);
      setDigestFlash(true);
      setTimeout(() => setDigestFlash(false), 2000);
    } catch (_e) { /* silent */ }
    finally { setDigestBusy(false); }
  }

  const inputCls = `w-full px-3 py-2 rounded-lg border ${
    light ? "border-slate-300 bg-white" : "border-slate-700 bg-slate-900"
  } focus:outline-none text-sm`;

  async function save(e) {
    e.preventDefault();
    setError(null); setBusy(true);
    try {
      await axios.put(`${API}/ad1/advertiser/${active.advertiser_id}`, form);
      setSavedFlash(true); setTimeout(() => setSavedFlash(false), 2000);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "object" ? (detail.code || JSON.stringify(detail)) : (detail || err.message));
    } finally { setBusy(false); }
  }

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-6`;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="space-y-6" data-testid="advertiser-profile-page">
      <div>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Profile</div>
        <h1 className="text-3xl font-bold mt-1">Brand details</h1>
      </div>

      <form onSubmit={save} className={`${cardCls} space-y-4`}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Company / Brand name">
            <input value={form.name || ""} onChange={set("name")} className={inputCls}
                          disabled={active?.status === "active"}
                          data-testid="advertiser-profile-name" />
          </Field>
          <Field label="Contact email">
            <input type="email" value={form.contact_email || ""} onChange={set("contact_email")}
                          className={inputCls}
                          disabled={active?.status === "active"}
                          data-testid="advertiser-profile-email" />
          </Field>
          <Field label="Contact name">
            <input value={form.contact_name || ""} onChange={set("contact_name")}
                          className={inputCls}
                          data-testid="advertiser-profile-contact-name" />
          </Field>
          <Field label="Phone">
            <input value={form.phone || ""} onChange={set("phone")}
                          className={inputCls}
                          data-testid="advertiser-profile-phone" />
          </Field>
          <Field label="Website">
            <input value={form.website || ""} onChange={set("website")}
                          className={inputCls}
                          data-testid="advertiser-profile-website" />
          </Field>
          <Field label="Logo URL">
            <input value={form.logo_url || ""} onChange={set("logo_url")}
                          className={inputCls}
                          data-testid="advertiser-profile-logo" />
          </Field>
        </div>
        {active?.status === "active" && (
          <p className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            Only cosmetic fields (logo, phone, website, contact name) can be updated once the account is active.  Contact support to change brand name or email.
          </p>
        )}
        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400"
                      data-testid="advertiser-profile-error">
            {error}
          </div>
        )}
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy}
                          data-testid="advertiser-profile-save"
                          className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-amber-500 text-slate-950 text-sm font-semibold hover:bg-amber-400 disabled:opacity-50 transition">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save
          </button>
          {savedFlash && (
            <div className="inline-flex items-center gap-1 text-sm text-emerald-500"
                        data-testid="advertiser-profile-saved">
              <CheckCircle2 className="w-4 h-4" /> Saved
            </div>
          )}
        </div>
      </form>

      {/* Phase AD.12 bundle — Weekly digest opt-out toggle. */}
      <div id="digest" className={`${cardCls} space-y-3`}
                  data-testid="advertiser-profile-digest-section">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl grid place-items-center
                                      bg-gradient-to-br from-fuchsia-500 to-amber-500 shrink-0">
            <Mail className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <div className="font-black text-sm">Weekly performance digest</div>
            <p className={`text-xs mt-0.5 ${light ? "text-slate-500" : "text-slate-400"}`}>
              Every Monday at 09:00 UTC, we email a summary of your last 7 days
              across all ad types (spend, CTR, top creatives, zone performance,
              recommendations).  On by default — flip it off if you&rsquo;d
              rather check the dashboard yourself.
            </p>
          </div>
          <label className="inline-flex items-center gap-2 cursor-pointer shrink-0"
                        data-testid="advertiser-profile-digest-toggle-wrap">
            <input type="checkbox"
                          checked={digestOn}
                          onChange={toggleDigest}
                          disabled={digestBusy}
                          data-testid="advertiser-profile-digest-toggle"
                          className="w-4 h-4 accent-amber-500 cursor-pointer" />
            <span data-testid="advertiser-profile-digest-state"
                        className={`text-xs font-black ${digestOn ? "text-emerald-500" : "text-slate-400"}`}>
              {digestBusy ? "…" : digestOn ? "ON" : "OFF"}
            </span>
          </label>
        </div>
        {digestFlash && (
          <div className="inline-flex items-center gap-1 text-xs text-emerald-500"
                      data-testid="advertiser-profile-digest-saved">
            <CheckCircle2 className="w-3 h-3" /> Preference saved
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest font-mono text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}
