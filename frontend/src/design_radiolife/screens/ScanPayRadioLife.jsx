// RadioLife — Scan to Pay (customer). Generate a QR the shop scans to charge
// your saved card or BigPoints. In-shell.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import { ChevronLeft, CreditCard, Coins, QrCode, CheckCircle2, AlertTriangle, RotateCw } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const BRAND = { visa: "Visa", mastercard: "Mastercard", amex: "Amex", discover: "Discover" };

export default function ScanPayRadioLife() {
  const navigate = useNavigate();
  const [method, setMethod] = useState("card");
  const [cards, setCards] = useState([]);
  const [payWith, setPayWith] = useState(null);
  const [amount, setAmount] = useState("");
  const [token, setToken] = useState(null);
  const [status, setStatus] = useState("form"); // form | qr | charged | expired
  const [error, setError] = useState(null);
  const [reportName, setReportName] = useState("");
  const [reported, setReported] = useState(false);
  const poll = useRef(null);

  useEffect(() => {
    axios.get(`${API}/shop/wallet/cards`).then((r) => {
      setCards(r.data.cards || []);
      const def = (r.data.cards || []).find((c) => c.is_default);
      setPayWith(def ? def.id : (r.data.cards?.[0]?.id || null));
    }).catch(() => {});
  }, []);

  const stopPoll = () => { if (poll.current) { clearInterval(poll.current); poll.current = null; } };
  useEffect(() => stopPoll, []);

  const startPoll = useCallback((tk) => {
    stopPoll();
    poll.current = setInterval(async () => {
      try {
        const r = await axios.get(`${API}/shop/scanpay/token/${tk}/status`);
        if (r.data.status === "charged") { setStatus("charged"); stopPoll(); }
        else if (["expired", "canceled", "not_found"].includes(r.data.status)) { setStatus("expired"); stopPoll(); }
      } catch { /* keep polling */ }
    }, 2500);
  }, []);

  const generate = async () => {
    setError(null);
    const cents = Math.round(parseFloat(amount) * 100);
    if (!cents || cents <= 0) { setError("Enter an amount"); return; }
    if (method === "card" && !payWith) { setError("Add a card first"); return; }
    try {
      const r = await axios.post(`${API}/shop/scanpay/token`, {
        method, amount_cents: cents,
        payment_method_id: method === "card" ? payWith : undefined,
      });
      setToken(r.data.token); setStatus("qr"); startPoll(r.data.token);
    } catch (e) {
      setError(ERR[e?.response?.data?.detail?.code] || "Could not create QR");
    }
  };

  const cancel = async () => {
    if (token) { try { await axios.post(`${API}/shop/scanpay/token/${token}/cancel`); } catch { /* ignore */ } }
    stopPoll(); setStatus("form"); setToken(null);
  };

  const report = async () => {
    try {
      await axios.post(`${API}/shop/scanpay/report-bypass`, {
        business_name: reportName || undefined, note: "Asked to pay outside the app",
      });
      setReported(true);
    } catch { /* ignore */ }
  };

  return (
    <div className="pb-24" data-testid="rl-scanpay-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="scanpay-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Scan to Pay</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {status === "charged" ? (
          <div className="bg-white border border-green-200 rounded-2xl p-8 text-center" data-testid="scanpay-charged">
            <CheckCircle2 size={54} className="mx-auto text-green-600" />
            <p className="mt-3 text-xl font-black text-slate-900">Paid {money(Math.round(parseFloat(amount) * 100))}</p>
            <p className="text-slate-500 text-sm mt-1">The shop charged your {method === "card" ? "card" : "BigPoints"}.</p>
            <button onClick={() => { setStatus("form"); setToken(null); setAmount(""); }} data-testid="scanpay-done"
              className="mt-5 bg-orange-600 text-white font-black rounded-full px-6 py-3">Done</button>
          </div>
        ) : status === "qr" ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center" data-testid="scanpay-qr">
            <p className="text-sm font-bold text-slate-500">Show this to the shop to pay</p>
            <div className="text-3xl font-black text-slate-900 my-2">{money(Math.round(parseFloat(amount) * 100))}</div>
            <div className="bg-white p-4 inline-block rounded-xl border border-slate-100" data-testid="scanpay-qr-code">
              <QRCode value={token || ""} size={196} />
            </div>
            <div className="mt-3 text-xs tracking-widest font-black text-slate-400" data-testid="scanpay-token">{token}</div>
            <p className="text-xs text-slate-400 mt-2 flex items-center justify-center gap-1"><RotateCw size={12} className="animate-spin" />Waiting for the shop to scan…</p>
            <button onClick={cancel} data-testid="scanpay-cancel" className="mt-4 text-sm font-bold text-rose-600">Cancel</button>
          </div>
        ) : status === "expired" ? (
          <div className="bg-white border border-amber-200 rounded-2xl p-8 text-center" data-testid="scanpay-expired">
            <AlertTriangle size={44} className="mx-auto text-amber-500" />
            <p className="mt-3 font-black text-slate-900">QR expired or canceled</p>
            <button onClick={() => { setStatus("form"); setToken(null); }} data-testid="scanpay-retry"
              className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-3">Try again</button>
          </div>
        ) : (
          <>
            <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3">
              <div className="font-black text-slate-900 flex items-center gap-1.5"><QrCode size={16} className="text-orange-600" />Pay in-store with a QR</div>
              <div className="flex gap-2">
                <button onClick={() => setMethod("card")} data-testid="scanpay-method-card"
                  className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-3 font-black text-sm border ${method === "card" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}><CreditCard size={15} />Card</button>
                <button onClick={() => setMethod("points")} data-testid="scanpay-method-points"
                  className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-3 font-black text-sm border ${method === "points" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}><Coins size={15} />BigPoints</button>
              </div>

              {method === "card" && (
                cards.length ? (
                  <div className="space-y-2">
                    {cards.map((c) => (
                      <button key={c.id} onClick={() => setPayWith(c.id)} data-testid={`scanpay-card-${c.id}`}
                        className={`w-full flex items-center gap-3 rounded-xl p-3 text-left border ${payWith === c.id ? "border-orange-500 bg-orange-50" : "border-slate-200 bg-slate-50"}`}>
                        <span className={`w-4 h-4 rounded-full border-2 ${payWith === c.id ? "border-orange-500 bg-orange-500" : "border-slate-300"}`} />
                        <CreditCard size={16} className="text-slate-700" />
                        <span className="text-sm font-bold text-slate-900">{BRAND[c.brand] || c.brand} •••• {c.last4}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <button onClick={() => navigate("/shop/wallet/cards")} data-testid="scanpay-add-card"
                    className="w-full text-sm font-bold text-orange-600 border border-orange-200 rounded-xl py-2.5">Add a card first</button>
                )
              )}

              <label className="block text-xs font-bold text-slate-500">Amount ($)
                <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00"
                  data-testid="scanpay-amount" className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-lg font-black" />
              </label>
              {error && <div className="text-rose-600 text-sm font-semibold" data-testid="scanpay-error">{error}</div>}
              <button onClick={generate} data-testid="scanpay-generate"
                className="w-full bg-orange-600 text-white font-black rounded-full py-4">Generate QR</button>
            </div>

            {/* Anti-fraud report */}
            <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="scanpay-report">
              <div className="text-sm font-black text-slate-900 flex items-center gap-1.5"><AlertTriangle size={15} className="text-amber-500" />Asked to pay outside the app?</div>
              <p className="text-xs text-slate-500 mt-1">Report a shop that skipped the scan so we can look into it.</p>
              {reported ? (
                <div className="mt-2 text-sm font-bold text-green-700" data-testid="scanpay-report-done">Thanks — reported for review.</div>
              ) : (
                <div className="flex gap-2 mt-2">
                  <input value={reportName} onChange={(e) => setReportName(e.target.value)} placeholder="Shop name"
                    data-testid="scanpay-report-input" className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-bold" />
                  <button onClick={report} data-testid="scanpay-report-btn" className="bg-slate-900 text-white font-black rounded-xl px-4 text-sm">Report</button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const ERR = {
  insufficient_points: "You don't have enough BigPoints.",
  card_not_found: "Card not found — add a card first.",
  bad_amount: "Enter a valid amount.",
};
