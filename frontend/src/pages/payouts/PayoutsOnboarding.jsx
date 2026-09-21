// Payments, Payouts & Earnings — unified self-serve Stripe Connect for BOTH
// social professionals (advisors, 15% fee) and business merchants (5% fee).
// Backed by the Payouts Hub (/api/payouts/*), which reconciles onto the same
// Standard connected accounts used by dream_payouts + payment_service.
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  Loader2, ShieldCheck, CheckCircle2, AlertTriangle, ArrowRight,
  Landmark, Store, Sparkles, ArrowLeft,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const TYPE_META = {
  advisor: { label: "Expert / Advisor", Icon: Sparkles, blurb: "Get paid for readings & sessions" },
  merchant: { label: "Business / Store", Icon: Store, blurb: "Get paid for sales & bookings" },
};
const money = (c) => `$${(((c || 0)) / 100).toFixed(2)}`;

export default function PayoutsOnboarding() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState(sp.get("connect") === "done" ? "checking" : "");

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/payouts/overview`, { withCredentials: true });
      setData(data);
    } catch (_) { setData({ eligible: false, accounts: [] }); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // On return from Stripe hosted onboarding, sync each account's live status
  // (the return URL alone is NOT proof of completion) then reload.
  useEffect(() => {
    if (sp.get("connect")) {
      (async () => {
        for (const vt of ["advisor", "merchant"]) {
          try { await axios.post(`${API}/payouts/refresh`, { vendor_type: vt }, { withCredentials: true }); } catch (_) {}
        }
        await load();
        setNotice("");
        setSp({}, { replace: true });
      })();
    }
  }, [sp, load, setSp]);

  if (loading) {
    return <div className="min-h-screen grid place-items-center bg-[#0b0710]"><Loader2 className="animate-spin text-violet-400" /></div>;
  }
  const accounts = data?.accounts || [];
  const gateOn = !!data?.gate_on;
  const anyBlocked = gateOn && accounts.some((a) => !a.ready);

  return (
    <div className="min-h-screen bg-[#0b0710] text-white" data-testid="payouts-page">
      <div className="max-w-2xl mx-auto px-5 py-8">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-white/50 hover:text-white mb-6" data-testid="payouts-back">
          <ArrowLeft size={15} /> Back
        </button>
        <div className="flex items-center gap-3 mb-2">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-600 grid place-items-center">
            <Landmark size={22} />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight">Payments, Payouts &amp; Earnings</h1>
            <p className="text-sm text-white/50">Connect a Stripe account to receive your earnings.</p>
          </div>
        </div>

        {notice === "checking" && (
          <div className="mt-4 rounded-xl bg-violet-500/10 border border-violet-500/30 p-3 text-sm text-violet-200 flex items-center gap-2" data-testid="payouts-return-notice">
            <Loader2 size={15} className="animate-spin" /> Confirming your Stripe setup…
          </div>
        )}

        {anyBlocked && (
          <div className="mt-4 rounded-xl bg-amber-500/10 border border-amber-500/30 p-3 text-sm text-amber-200 flex items-start gap-2" data-testid="payouts-gate-banner">
            <ShieldCheck size={16} className="mt-0.5 shrink-0" />
            <span>Payout onboarding is required. You can't accept payments until your Stripe payout account is active.</span>
          </div>
        )}

        {accounts.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.03] p-8 text-center" data-testid="payouts-not-eligible">
            <AlertTriangle className="mx-auto text-amber-400 mb-3" />
            <div className="font-bold">No vendor profile yet</div>
            <p className="text-sm text-white/50 mt-1">Become a verified expert or register a business to start accepting payments.</p>
          </div>
        ) : (
          <div className="mt-6 space-y-4">
            {accounts.map((a) => <PayoutCard key={a.vendor_type} a={a} onChanged={load} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function PayoutCard({ a, onChanged }) {
  const meta = TYPE_META[a.vendor_type] || TYPE_META.merchant;
  const Icon = meta.Icon;
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = !!a.ready;
  const pending = !active && !!a.has_account;
  const e = a.earnings || {};
  const agreement = `I agree to pay a ${a.fee_pct}% platform fee on each transaction, and I accept that I am solely and personally responsible for any chargebacks, refunds, or disputes. FUUSIC is not liable for chargebacks.`;

  const go = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/payouts/onboard`, {
        vendor_type: a.vendor_type, agreement_accepted: true,
        origin_url: window.location.origin,
      }, { withCredentials: true });
      if (data.onboarding_url) window.location.href = data.onboarding_url;
    } catch (e) {
      setBusy(false);
      alert(e?.response?.data?.detail?.code || "Couldn't start payout setup. Please try again.");
    }
  };

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5" data-testid={`payout-card-${a.vendor_type}`}>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-white/[0.06] grid place-items-center"><Icon size={18} className="text-violet-300" /></div>
        <div className="flex-1 min-w-0">
          <div className="font-black">{meta.label}</div>
          <div className="text-xs text-white/45">{a.display_name || meta.blurb}</div>
        </div>
        <StatusPill active={active} pending={pending} />
      </div>

      <div className="mt-4 flex items-center gap-4 text-sm">
        <div className="rounded-lg bg-white/[0.04] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-white/40">Platform fee</div>
          <div className="font-black text-violet-300" data-testid={`payout-fee-${a.vendor_type}`}>{a.fee_pct}%</div>
        </div>
        <div className="rounded-lg bg-white/[0.04] px-3 py-2">
          <div className="text-[10px] uppercase tracking-widest text-white/40">Payout currency</div>
          <div className="font-black uppercase">{a.currency}</div>
        </div>
      </div>

      {/* Earnings dashboard */}
      <div className="mt-4 rounded-2xl bg-gradient-to-br from-emerald-600/90 to-teal-600/90 p-4" data-testid={`payouts-earnings-${a.vendor_type}`}>
        <div className="text-[10px] font-black tracking-widest text-white/80">NET EARNINGS</div>
        <div className="text-3xl font-black tabular-nums" data-testid={`payouts-earnings-paid-${a.vendor_type}`}>{money(e.paid_cents)}</div>
        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
          <Stat label="Sales" value={money(e.sales_cents)} />
          <Stat label="Fees" value={money(e.fees_cents)} />
          <Stat label="Pending" value={money(e.pending_cents)} />
        </div>
      </div>

      {active ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-emerald-300" data-testid={`payout-active-${a.vendor_type}`}>
          <CheckCircle2 size={16} /> Payouts are active — you keep {100 - a.fee_pct}% of each sale.
        </div>
      ) : pending ? (
        <button onClick={go} disabled={busy} data-testid={`payout-resume-${a.vendor_type}`}
          className="mt-4 w-full h-11 rounded-full font-black bg-white/10 hover:bg-white/15 inline-flex items-center justify-center gap-2">
          {busy ? <Loader2 className="animate-spin" size={16} /> : <>Finish Stripe setup <ArrowRight size={15} /></>}
        </button>
      ) : (
        <>
          <label className="mt-4 flex items-start gap-2.5 cursor-pointer rounded-xl bg-white/[0.03] border border-white/10 p-3" data-testid={`payout-agree-wrap-${a.vendor_type}`}>
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 accent-violet-500 w-4 h-4" data-testid={`payout-agree-${a.vendor_type}`} />
            <span className="text-xs leading-relaxed text-white/70">{agreement}</span>
          </label>
          <button onClick={go} disabled={!agreed || busy} data-testid={`payout-connect-${a.vendor_type}`}
            className="mt-3 w-full h-11 rounded-full font-black text-white disabled:opacity-40 inline-flex items-center justify-center gap-2"
            style={{ background: "linear-gradient(135deg,#8b5cf6,#ec4899)" }}>
            {busy ? <Loader2 className="animate-spin" size={16} /> : <><ShieldCheck size={16} /> Set up payouts with Stripe</>}
          </button>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-black/15 px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-widest text-white/70">{label}</div>
      <div className="text-sm font-black tabular-nums">{value}</div>
    </div>
  );
}

function StatusPill({ active, pending }) {
  if (active) return <span className="text-[10px] font-black px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-300">ACTIVE</span>;
  if (pending) return <span className="text-[10px] font-black px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300">PENDING</span>;
  return <span className="text-[10px] font-black px-2.5 py-1 rounded-full bg-white/10 text-white/50">NOT SET UP</span>;
}
