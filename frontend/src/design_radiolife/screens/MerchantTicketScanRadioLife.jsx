// Merchant Ticket Scanner — enter/scan an event ticket code to check a guest
// in at the door. Validates against the merchant's own events.
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, QrCode, CheckCircle2, XCircle, AlertTriangle, Ticket } from "lucide-react";
import { API } from "@/AuthContext";

export default function MerchantTicketScanRadioLife() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {kind, ticket, label}

  const submit = async (e) => {
    e?.preventDefault?.();
    const c = code.trim();
    if (!c) return;
    setBusy(true); setResult(null);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/events/tickets/checkin`, { code: c });
      const d = r.data;
      if (d.ok) setResult({ kind: "ok", ticket: d.ticket, label: "Checked in ✓" });
      else if (d.status === "already_checked_in") setResult({ kind: "warn", ticket: d.ticket, label: "Already checked in" });
      else setResult({ kind: "warn", ticket: d.ticket, label: `Ticket ${d.status}` });
    } catch (err) {
      const cd = err?.response?.data?.detail?.code;
      setResult({ kind: "err", label: cd === "ticket_not_found" ? "Ticket not found" : cd === "no_marketplace_profile" ? "No merchant profile" : "Check-in failed" });
    } finally { setBusy(false); setCode(""); }
  };

  const tone = result?.kind === "ok" ? { bg: "bg-emerald-50", bd: "border-emerald-200", tx: "text-emerald-700", Icon: CheckCircle2 }
    : result?.kind === "warn" ? { bg: "bg-amber-50", bd: "border-amber-200", tx: "text-amber-700", Icon: AlertTriangle }
    : { bg: "bg-rose-50", bd: "border-rose-200", tx: "text-rose-700", Icon: XCircle };

  return (
    <div className="px-4 pt-4 lg:pt-8 pb-24 lg:max-w-xl lg:mx-auto" data-testid="rl-ticket-scan-page">
      <div className="flex items-center gap-3 pb-2">
        <button onClick={() => navigate("/shop/merchant/events")} data-testid="scan-back"
          className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl lg:text-2xl font-black text-slate-900">Scan Tickets</h1>
      </div>
      <p className="text-slate-500 text-sm mb-4">Enter or scan a guest's ticket code to check them in at the door.</p>

      <form onSubmit={submit} className="bg-white border border-slate-200 rounded-2xl p-4">
        <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-3">
          <QrCode size={20} className="text-orange-600" />
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="Ticket code e.g. DEMO1234"
            data-testid="scan-code-input"
            autoFocus
            className="flex-1 bg-transparent text-lg font-black tracking-widest text-slate-900 outline-none placeholder:text-slate-300 placeholder:tracking-normal placeholder:font-medium placeholder:text-sm" />
        </div>
        <button type="submit" disabled={busy || !code.trim()} data-testid="scan-submit"
          className="w-full mt-3 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">
          {busy ? "Checking…" : "Check In"}
        </button>
      </form>

      {result && (
        <div className={`mt-4 rounded-2xl border p-4 ${tone.bg} ${tone.bd}`} data-testid="scan-result">
          <div className={`flex items-center gap-2 font-black ${tone.tx}`}>
            <tone.Icon size={20} /> {result.label}
          </div>
          {result.ticket && (
            <div className="mt-2 text-sm text-slate-700 space-y-0.5">
              <div className="flex items-center gap-2 font-bold"><Ticket size={14} /> {result.ticket.event_title}</div>
              <div className="text-xs text-slate-500">Code {result.ticket.code} · Qty {result.ticket.qty}</div>
              {result.kind !== "ok" && result.ticket.checked_in_at && (
                <div className="text-xs font-bold text-amber-700">
                  Checked in {new Date(result.ticket.checked_in_at).toLocaleString()}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
