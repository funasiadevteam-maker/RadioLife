// Perk Redemption Scan — bar staff/owner type a customer's drink code to
// validate it, then burn it. POST /api/bar-games/{id}/staff/lookup + /staff/redeem
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Loader2, ScanLine, CheckCircle2, XCircle, Clock, Ticket } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS = {
  valid: { color: "#34d399", icon: CheckCircle2, text: "Valid — ready to redeem" },
  redeemed: { color: "#f59e0b", icon: XCircle, text: "Already redeemed" },
  expired: { color: "#fb7185", icon: Clock, text: "Expired" },
  not_found: { color: "#94a3b8", icon: XCircle, text: "No matching code" },
};

export default function BarStaffScan({ businessId, onClose }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {status, perk}

  const lookup = async () => {
    if (code.trim().length < 3) return;
    setBusy(true); setResult(null);
    try {
      const { data } = await axios.post(`${API}/bar-games/${businessId}/staff/lookup`,
        { code: code.trim() }, { withCredentials: true });
      setResult(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "not_bar_staff" ? "Staff only." : "Lookup failed.");
    } finally { setBusy(false); }
  };

  const redeem = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/bar-games/${businessId}/staff/redeem`,
        { code: code.trim() }, { withCredentials: true });
      if (data.ok) { toast.success("Perk redeemed 🍸"); setResult({ status: "redeemed", perk: result?.perk }); }
      else { toast.info(`Cannot redeem — ${data.status}.`); setResult((r) => ({ ...r, status: data.status })); }
    } catch (_) { toast.error("Redeem failed."); } finally { setBusy(false); }
  };

  const st = result && STATUS[result.status];

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center p-4 bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="bar-staff-scan">
      <div className="w-full max-w-sm rounded-3xl border border-white/10 p-5"
           style={{ background: "linear-gradient(135deg,#160f2e,#241041)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-white font-black text-lg"><ScanLine size={18} /> Redeem a perk</div>
          <button onClick={onClose} className="text-slate-400" data-testid="scan-close"><X size={20} /></button>
        </div>

        <label className="block text-xs text-slate-300 font-bold mb-1">Customer's code</label>
        <div className="flex gap-2">
          <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="BAR-XXXXXXXX" data-testid="scan-code"
                 className="flex-1 min-w-0 rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-white font-mono outline-none" />
          <button onClick={lookup} disabled={busy} data-testid="scan-lookup"
                  className="px-4 rounded-xl text-white font-black bg-white/10 inline-flex items-center gap-1.5">
            {busy && !st ? <Loader2 size={16} className="animate-spin" /> : "Check"}
          </button>
        </div>

        {st && (
          <div className="mt-4 rounded-2xl p-4" data-testid="scan-result"
               style={{ background: `${st.color}1a`, border: `1px solid ${st.color}55` }}>
            <div className="flex items-center gap-2 font-black" style={{ color: st.color }}>
              <st.icon size={18} /> {st.text}
            </div>
            {result.perk && (
              <div className="mt-2 text-white">
                <div className="text-lg font-black">{result.perk.emoji} {result.perk.label}</div>
                <div className="text-[12px] text-slate-300/80 flex items-center gap-1.5 mt-1"><Ticket size={12} /> {result.perk.code} · {result.perk.customer}</div>
              </div>
            )}
            {result.status === "valid" && (
              <button onClick={redeem} disabled={busy} data-testid="scan-redeem"
                      className="mt-3 w-full h-10 rounded-full text-white font-black inline-flex items-center justify-center gap-2"
                      style={{ background: "linear-gradient(135deg,#059669,#34d399)" }}>
                {busy ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />} Redeem now
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
