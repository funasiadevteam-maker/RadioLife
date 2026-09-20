// Phase 18a — Advertiser onboarding form (3 visual steps; 1 API call).
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ArrowRight, Loader2, Building2, Mail } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdvertiserOnboard({ onCreated }) {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: "", contact_email: "", contact_phone: "",
    market: "dubai", address: "",
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!form.name || !form.contact_email) {
      toast.error("Name + contact email required"); setStep(1); return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/advertiser/onboard`, form);
      toast.success("Advertiser created");
      onCreated?.(r.data.advertiser_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not onboard");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6 max-w-2xl" data-testid="advertiser-onboard">
      <div>
        <h2 className="font-display font-bold text-3xl tracking-display-tight">
          Start advertising on FUUSIC
        </h2>
        <p className="text-text-secondary mt-2">
          Reach the diaspora through AI radio.  Top up your ad wallet, build a
          campaign in 5 steps, go live in minutes.
        </p>
      </div>

      <div className="flex gap-2 text-xs font-mono uppercase tracking-widest">
        {["Profile", "Stripe", "Team"].map((s, i) => (
          <span key={s}
                    className={`px-3 py-1 rounded-full border
                                ${step >= i + 1
                                  ? "border-accent-electric text-accent-electric"
                                  : "border-white/[0.10] text-text-secondary"}`}>
            {i + 1}. {s}
          </span>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4" data-testid="onboard-step-profile">
          <FormRow label="Business name" icon={Building2}>
            <input className="bigfm-input" data-testid="onboard-name"
                  value={form.name} onChange={(e) => setForm({...form, name: e.target.value})}
                  placeholder="Karak Cafe" />
          </FormRow>
          <FormRow label="Contact email" icon={Mail}>
            <input type="email" className="bigfm-input" data-testid="onboard-email"
                  value={form.contact_email}
                  onChange={(e) => setForm({...form, contact_email: e.target.value})}
                  placeholder="ads@yourbusiness.com" />
          </FormRow>
          <FormRow label="Phone (optional)">
            <input className="bigfm-input"
                  value={form.contact_phone}
                  onChange={(e) => setForm({...form, contact_phone: e.target.value})}
                  placeholder="+971 50 000 0000" />
          </FormRow>
          <FormRow label="Primary market">
            <select className="bigfm-input"
                        value={form.market}
                        onChange={(e) => setForm({...form, market: e.target.value})}>
              <option value="dubai">🇦🇪 Dubai</option>
              <option value="dfw">🇺🇸 DFW</option>
            </select>
          </FormRow>
          <button className="bigfm-cta" onClick={() => setStep(2)} data-testid="onboard-next-1">
            Continue <ArrowRight size={14} />
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4" data-testid="onboard-step-stripe">
          <div className="p-4 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
            <div className="text-sm text-text-secondary mb-2">
              We will create a Stripe customer for your account.  You can top
              up your ad wallet later from the Billing page.
            </div>
            <ul className="text-xs text-text-secondary list-disc pl-5 space-y-1">
              <li>No charge today.</li>
              <li>Card on file via Stripe Checkout when you fund balance.</li>
              <li>You can pause / refund unspent balance any time.</li>
            </ul>
          </div>
          <div className="flex gap-2">
            <button className="bigfm-cta-ghost" onClick={() => setStep(1)}>Back</button>
            <button className="bigfm-cta" onClick={() => setStep(3)} data-testid="onboard-next-2">
              Continue <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4" data-testid="onboard-step-team">
          <div className="p-4 rounded-2xl border border-white/[0.06] bg-white/[0.02]">
            <div className="text-sm text-text-secondary">
              You're the <b>owner</b>.  Invite teammates as managers
              (full edit access) or analysts (read-only) after onboarding from
              Settings.
            </div>
          </div>
          <div className="flex gap-2">
            <button className="bigfm-cta-ghost" onClick={() => setStep(2)}>Back</button>
            <button className="bigfm-cta" onClick={submit} disabled={busy}
                        data-testid="onboard-submit">
              {busy ? <Loader2 className="animate-spin" size={14} /> : <ArrowRight size={14} />}
              {busy ? " Creating..." : " Create advertiser"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


function FormRow({ label, icon: Icon, children }) {
  return (
    <label className="block">
      <span className="text-[10px] font-mono uppercase tracking-widest text-text-secondary flex items-center gap-1">
        {Icon && <Icon size={11} />} {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
