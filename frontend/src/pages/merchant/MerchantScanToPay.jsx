// Phase AD.7 — Merchant Scan-to-Pay dashboard.
// Route: /merchant/:merchantId/scan-to-pay
//
// Left column: cashier terminal — enter an amount, generate a QR that
// the customer scans.  Live polls for the resulting transaction so the
// cashier sees success/failure without refreshing.
// Right column: settings + recent transactions.
import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import {
  QrCode, Coins, Loader2, CheckCircle2, AlertTriangle, Settings, RefreshCw,
  Clock, ArrowLeft,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";


export default function MerchantScanToPay() {
  const { merchantId } = useParams();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const [txs, setTxs] = useState([]);
  const [totals, setTotals] = useState(null);
  const [error, setError] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        axios.get(`${API}/merchant/${merchantId}/scan-to-pay/settings`,
          { withCredentials: true }),
        axios.get(`${API}/merchant/${merchantId}/scan-to-pay/transactions`,
          { withCredentials: true }),
      ]);
      setSettings(s.data);
      setTxs(t.data.items || []);
      setTotals(t.data.totals || {});
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    }
  }, [merchantId]);

  useEffect(() => { if (user) loadAll(); }, [user, loadAll]);

  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const card = light ? "bg-white border border-slate-200"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`${bg} min-h-screen`} data-testid="merchant-scan-page">
      <div className="max-w-6xl mx-auto px-4 py-6 lg:py-10">
        <button onClick={() => window.history.back()}
                        className={`inline-flex items-center gap-1 text-xs ${muted}
                                              hover:opacity-80 mb-4`}>
          <ArrowLeft size={12} /> Back
        </button>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-2xl grid place-items-center
                                      bg-gradient-to-br from-fuchsia-500 to-amber-500">
            <QrCode size={20} className="text-white" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Phase AD.7
            </div>
            <h1 className="text-3xl font-black">Scan-to-Pay dashboard</h1>
          </div>
        </div>

        {error && (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2 mb-4"
                      data-testid="merchant-scan-error">
            <AlertTriangle size={16} /> {String(error)}
          </div>
        )}

        <div className="grid lg:grid-cols-[2fr,3fr] gap-6">
          {/* Left — cashier terminal */}
          <CashierTerminal merchantId={merchantId}
                                              settings={settings}
                                              light={light} card={card} muted={muted}
                                              onCaptured={loadAll} />
          {/* Right — settings + txns */}
          <div className="space-y-6">
            <MerchantSettings settings={settings} merchantId={merchantId}
                                                    light={light} card={card} muted={muted}
                                                    onSaved={loadAll} />
            <TransactionsTable txs={txs} totals={totals} light={light}
                                                    card={card} muted={muted} />
          </div>
        </div>
      </div>
    </div>
  );
}


// ─── Cashier terminal — generate QR + live status ─────────────────
function CashierTerminal({ merchantId, settings, light, card, muted,
                                                        onCaptured }) {
  const [amount, setAmount] = useState("");
  const [qr, setQr]      = useState(null);
  const [busy, setBusy]  = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const generate = async () => {
    const cents = Math.round(Number(amount) * 100);
    if (!cents || cents < (settings?.min_scan_to_pay_amount_cents || 100)) {
      setError(`Amount must be at least $${((settings?.min_scan_to_pay_amount_cents || 100) / 100).toFixed(2)}`);
      return;
    }
    setBusy(true); setError(null); setStatus(null);
    try {
      const r = await axios.post(`${API}/merchant/scan-to-pay/qr/generate`,
        { merchant_id: merchantId, amount_cents: cents },
        { withCredentials: true });
      setQr(r.data);
      // Poll for the transaction row every 2s while the QR is valid.
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const q = await axios.get(
            `${API}/merchant/${merchantId}/scan-to-pay/transactions?limit=1`,
            { withCredentials: true });
          const first = (q.data.items || [])[0];
          if (first && first.qr_token === r.data.token) {
            setStatus(first.status);
            if (["captured", "refunded"].includes(first.status)) {
              clearInterval(pollRef.current);
              pollRef.current = null;
              onCaptured?.();
            }
          }
        } catch (_e) { /* ignore transient */ }
      }, 2000);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  };

  const reset = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setQr(null); setStatus(null); setError(null); setAmount("");
  };

  return (
    <div className={`${card} rounded-2xl p-6`}
              data-testid="merchant-scan-cashier">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg grid place-items-center bg-amber-500/15">
          <QrCode size={16} className="text-amber-500" />
        </div>
        <div className="font-black text-sm">Cashier terminal</div>
      </div>

      {!settings?.enabled && (
        <div className="rounded-lg px-4 py-3 bg-orange-500/10 border border-orange-500/40 text-orange-400 text-sm inline-flex items-center gap-2 mb-4"
                    data-testid="merchant-scan-disabled-warning">
          <AlertTriangle size={14} /> Scan-to-Pay is disabled. Enable it in settings first.
        </div>
      )}

      {!qr ? (
        <>
          <label className={`block text-[10px] uppercase tracking-widest font-mono ${muted} mb-1`}>
            Bill amount (USD)
          </label>
          <input type="number" min="0.01" step="0.01"
                        value={amount}
                        onChange={(e) => setAmount(e.target.value)}
                        data-testid="merchant-scan-amount-input"
                        placeholder="10.00"
                        className={`w-full text-2xl font-mono font-black px-3 py-3 rounded-xl
                                                    ${light ? "bg-slate-50 border border-slate-300"
                                                                    : "bg-slate-950 border border-slate-800"}`} />
          {error && (
            <div className="rounded-lg px-3 py-2 mt-3 bg-red-500/10 border border-red-500/40 text-red-400 text-xs inline-flex items-center gap-1"
                        data-testid="merchant-scan-generate-error">
              <AlertTriangle size={12} /> {String(error)}
            </div>
          )}
          <button onClick={generate}
                          disabled={busy || !amount || !settings?.enabled}
                          data-testid="merchant-scan-qr-generate"
                          className="w-full mt-4 py-3 rounded-full text-sm font-black
                                                inline-flex items-center justify-center gap-2
                                                bg-amber-500 text-slate-950 hover:bg-amber-400
                                                disabled:opacity-40 disabled:cursor-not-allowed">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <QrCode size={16} />}
            Generate QR
          </button>
        </>
      ) : (
        <div data-testid="merchant-scan-qr-display" className="text-center">
          <div className="text-3xl font-black mb-1">
            ${(qr.amount_cents / 100).toFixed(2)}
          </div>
          <div className={`text-[10px] font-mono mb-4 inline-flex items-center gap-1 ${muted}`}>
            <Clock size={10} /> Expires in {qr.expires_in_s}s
          </div>
          <div className="bg-white p-4 rounded-2xl inline-block">
            <QRCode value={`${window.location.origin}${qr.scan_url}`}
                              size={220} level="M" />
          </div>
          <div className={`text-[10px] font-mono mt-3 ${muted}`}
                      data-testid="merchant-scan-qr-token">
            Token: {qr.token.slice(0, 22)}…
          </div>
          <div className="mt-4">
            {status ? (
              <div className={`inline-flex items-center gap-2 text-sm font-black
                                              ${status === "captured" ? "text-emerald-500"
                                                              : status === "refunded" ? "text-orange-500"
                                                              : "text-amber-500"}`}
                          data-testid="merchant-scan-status">
                {status === "captured" ? <CheckCircle2 size={16} /> :
                  status === "refunded" ? <RefreshCw size={16} /> :
                  <Loader2 size={16} className="animate-spin" />}
                {status.toUpperCase()}
              </div>
            ) : (
              <div className={`inline-flex items-center gap-2 text-sm ${muted}`}
                          data-testid="merchant-scan-status">
                <Loader2 size={14} className="animate-spin" /> Waiting for scan…
              </div>
            )}
          </div>
          <button onClick={reset}
                          data-testid="merchant-scan-new-qr"
                          className="mt-6 text-xs font-black text-accent-electric hover:underline">
            New QR
          </button>
        </div>
      )}
    </div>
  );
}


// ─── Settings tab ──────────────────────────────────────────────
function MerchantSettings({ settings, merchantId, light, card, muted, onSaved }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings) setForm({
      enabled: settings.enabled,
      points_per_dollar: settings.points_per_dollar,
      max_points_redemption_pct: settings.max_points_redemption_pct,
      min_scan_to_pay_amount_cents: settings.min_scan_to_pay_amount_cents,
    });
  }, [settings]);

  const save = async () => {
    setBusy(true);
    try {
      await axios.patch(
        `${API}/merchant/${merchantId}/scan-to-pay/settings`,
        form, { withCredentials: true });
      setSaved(true); setTimeout(() => setSaved(false), 2000);
      onSaved?.();
    } catch (_e) { /* silent */ }
    finally { setBusy(false); }
  };

  const labelCls = `block text-[10px] uppercase tracking-widest font-mono ${muted} mb-1`;
  const inputCls = light
    ? "w-full px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
    : "w-full px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700";

  return (
    <div className={`${card} rounded-2xl p-5`}
              data-testid="merchant-scan-settings">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-lg grid place-items-center bg-fuchsia-500/15">
          <Settings size={14} className="text-fuchsia-400" />
        </div>
        <div className="font-black text-sm">Settings</div>
      </div>
      <div className="space-y-3">
        <label className="inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox"
                        checked={!!form.enabled}
                        onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                        data-testid="merchant-scan-settings-enabled"
                        className="w-4 h-4 accent-amber-500 cursor-pointer" />
          <span className="text-sm font-black">
            {form.enabled ? "Enabled" : "Disabled"}
          </span>
        </label>
        <div>
          <label className={labelCls}>Points per dollar</label>
          <input type="number" min="0" max="1000"
                        value={form.points_per_dollar ?? ""}
                        onChange={(e) => setForm({ ...form,
                                                                                points_per_dollar: Number(e.target.value) || 0 })}
                        data-testid="merchant-scan-settings-ppd"
                        className={inputCls} />
          <div className={`text-[10px] font-mono mt-1 ${muted}`}>
            10 = 10 points per $1 spent (recommended)
          </div>
        </div>
        <div>
          <label className={labelCls}>Max points redemption (%)</label>
          <input type="number" min="0" max="100"
                        value={form.max_points_redemption_pct ?? ""}
                        onChange={(e) => setForm({ ...form,
                                                                                max_points_redemption_pct: Number(e.target.value) || 0 })}
                        data-testid="merchant-scan-settings-max-pct"
                        className={inputCls} />
          <div className={`text-[10px] font-mono mt-1 ${muted}`}>
            Caps how much of a bill can be paid with points.
          </div>
        </div>
        <div>
          <label className={labelCls}>Min scan amount (cents)</label>
          <input type="number" min="0"
                        value={form.min_scan_to_pay_amount_cents ?? ""}
                        onChange={(e) => setForm({ ...form,
                                                                                min_scan_to_pay_amount_cents: Number(e.target.value) || 0 })}
                        data-testid="merchant-scan-settings-min-amount"
                        className={inputCls} />
        </div>
        <button onClick={save} disabled={busy}
                        data-testid="merchant-scan-settings-save"
                        className="w-full py-2 rounded-full text-xs font-black
                                                bg-amber-500 text-slate-950 hover:bg-amber-400
                                                inline-flex items-center justify-center gap-1
                                                disabled:opacity-40">
          {busy ? <Loader2 size={14} className="animate-spin" /> : null}
          Save settings
        </button>
        {saved && (
          <div className="text-xs text-emerald-500 inline-flex items-center gap-1"
                      data-testid="merchant-scan-settings-saved">
            <CheckCircle2 size={12} /> Saved
          </div>
        )}
      </div>
    </div>
  );
}


// ─── Transactions table ────────────────────────────────────────
function TransactionsTable({ txs, totals, light, card, muted }) {
  return (
    <div className={`${card} rounded-2xl p-5`}
              data-testid="merchant-scan-transactions">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-7 h-7 rounded-lg grid place-items-center bg-emerald-500/15">
          <Coins size={14} className="text-emerald-400" />
        </div>
        <div className="font-black text-sm">Recent transactions</div>
        <div className={`ml-auto text-[10px] font-mono ${muted}`}>
          {totals ? `$${((totals.net_cents || 0)/100).toFixed(2)} net · ${txs.length} txns` : ""}
        </div>
      </div>
      {txs.length === 0 ? (
        <div className={`text-xs text-center py-6 ${muted}`}
                    data-testid="merchant-scan-transactions-empty">
          No transactions yet.
        </div>
      ) : (
        <div className="space-y-1 max-h-80 overflow-y-auto">
          {txs.map((t) => (
            <div key={t.transaction_id}
                        data-testid={`merchant-scan-tx-${t.transaction_id}`}
                        className={`flex items-center gap-2 py-2 border-b last:border-0
                                              ${light ? "border-slate-100" : "border-slate-800"}`}>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-mono">
                  ${((t.total_cents || 0)/100).toFixed(2)}
                </div>
                <div className={`text-[10px] font-mono ${muted}`}>
                  {t.points_redeemed || 0} pts redeemed · {t.points_earned_awarded || 0} earned
                </div>
              </div>
              <span className={`text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded ${
                                          t.status === "captured" ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                                          : t.status === "refunded" ? "bg-orange-500/15 text-orange-400 border border-orange-500/30"
                                          : "bg-slate-500/15 text-slate-400 border border-slate-500/30"}`}>
                {t.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
