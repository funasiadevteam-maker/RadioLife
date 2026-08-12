// RadioLife Merchant — Scan to Charge. Enter/scan a customer's pay token,
// confirm the amount, and charge. In-shell.
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, QrCode, CheckCircle2, CreditCard, Coins } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const ERR = {
  invalid_token: "Code not recognised.", expired: "This QR has expired.",
  canceled: "The customer canceled this.", charged: "Already charged.",
  card_declined: "Card was declined.", already_used: "Already charged.",
  no_marketplace_profile: "Register your shop first.",
};

export default function MerchantScanRadioLife() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [resolved, setResolved] = useState(null);
  const [charged, setCharged] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const resolve = async () => {
    setError(null); setBusy(true); setResolved(null);
    try {
      const r = await axios.post(`${API}/shop/scanpay/resolve`, { token: code.trim().toUpperCase() });
      if (r.data.ok) setResolved(r.data);
      else setError(ERR[r.data.error] || "Could not read code");
    } catch (e) { setError(ERR[e?.response?.data?.detail?.code] || "Could not read code"); }
    finally { setBusy(false); }
  };

  const charge = async () => {
    setError(null); setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/scanpay/charge`, { token: resolved.token });
      if (r.data.ok) setCharged(r.data);
      else setError(ERR[r.data.error] || "Charge failed");
    } catch (e) { setError(ERR[e?.response?.data?.detail?.code] || "Charge failed"); }
    finally { setBusy(false); }
  };

  const reset = () => { setCode(""); setResolved(null); setCharged(null); setError(null); };

  return (
    <div className="pb-24" data-testid="rl-merchant-scan-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="merchant-scan-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Scan to Charge</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {charged ? (
          <div className="bg-white border border-green-200 rounded-2xl p-8 text-center" data-testid="merchant-scan-charged">
            <CheckCircle2 size={54} className="mx-auto text-green-600" />
            <p className="mt-3 text-xl font-black text-slate-900">Charged {money(charged.amount_cents)}</p>
            <p className="text-slate-500 text-sm mt-1">Paid by {charged.method === "card" ? "card" : "BigPoints"}.</p>
            <button onClick={reset} data-testid="merchant-scan-again"
              className="mt-5 bg-orange-600 text-white font-black rounded-full px-6 py-3">Charge another</button>
          </div>
        ) : resolved ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center" data-testid="merchant-scan-resolved">
            <p className="text-sm font-bold text-slate-500">{resolved.customer} wants to pay</p>
            <div className="text-4xl font-black text-slate-900 my-2">{money(resolved.amount_cents)}</div>
            <div className="inline-flex items-center gap-1.5 text-sm font-bold text-orange-600">
              {resolved.method === "card" ? <><CreditCard size={15} />Saved card</> : <><Coins size={15} />BigPoints</>}
            </div>
            {error && <div className="text-rose-600 text-sm font-semibold mt-3" data-testid="merchant-scan-error">{error}</div>}
            <button onClick={charge} disabled={busy} data-testid="merchant-scan-charge"
              className="mt-5 w-full bg-green-600 text-white font-black rounded-full py-4 disabled:opacity-60">{busy ? "Charging…" : `Charge ${money(resolved.amount_cents)}`}</button>
            <button onClick={reset} data-testid="merchant-scan-cancel" className="mt-2 text-sm font-bold text-slate-500">Cancel</button>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3">
            <div className="font-black text-slate-900 flex items-center gap-1.5"><QrCode size={16} className="text-orange-600" />Enter the customer's code</div>
            <p className="text-xs text-slate-500">Ask the customer to show their Scan-to-Pay QR, then type the code beneath it.</p>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="SP••••••••" autoCapitalize="characters"
              data-testid="merchant-scan-input" className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-lg font-black uppercase tracking-widest text-center" />
            {error && <div className="text-rose-600 text-sm font-semibold" data-testid="merchant-scan-error">{error}</div>}
            <button onClick={resolve} disabled={busy || !code.trim()} data-testid="merchant-scan-resolve"
              className="w-full bg-orange-600 text-white font-black rounded-full py-4 disabled:opacity-50">{busy ? "Reading…" : "Look up"}</button>
          </div>
        )}
      </div>
    </div>
  );
}
