// Phase AD.6 — Mobile-first redemption scanner.
// Route: /advertiser/dashboard/scan
// Requires can_redeem (owner, manager, redemption_staff).
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import {
  ScanLine, CheckCircle2, XCircle, Loader2, AlertTriangle, RefreshCw,
  Send, User, Tag, Clock,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const POLL_MS = 15000;

const REASON_LABEL = {
  not_found:                          "Code not found",
  wrong_advertiser_scope: "Belongs to a different advertiser",
  already_redeemed:                "Already redeemed",
  revoked:                                "Coupon revoked",
  expired:                                "Coupon expired",
};

export default function AdvertiserScan() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser, permissions } = useAdvertiser() || {};
  const [code, setCode] = useState("");
  const [scanResult, setScanResult] = useState(null);   // preview
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [feed, setFeed] = useState([]);
  const [lastFeedAt, setLastFeedAt] = useState(null);
  const inputRef = useRef(null);
  const canRedeem = permissions?.has?.("can_redeem");

  useEffect(() => {
    // Autofocus the input so USB barcode scanners "just work".
    if (inputRef.current) inputRef.current.focus();
  }, []);

  async function loadFeed() {
    if (!advertiser) return;
    try {
      const { data } = await axios.get(
        `${API}/advertiser-app/${advertiser.advertiser_id}/redemptions/live?limit=10`);
      setFeed(data.items || []);
      setLastFeedAt(new Date());
    } catch (_) { /* silent — non-critical */ }
  }
  useEffect(() => {
    loadFeed();
    const t = setInterval(loadFeed, POLL_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [advertiser]);

  async function doScan() {
    if (!code.trim() || !advertiser) return;
    setBusy(true); setError(null); setScanResult(null);
    try {
      const { data } = await axios.post(
        `${API}/advertiser-app/${advertiser.advertiser_id}/scan`,
        { code: code.trim() });
      setScanResult(data);
    } catch (err) {
      setError(err?.response?.data?.detail?.code
                          || err?.response?.data?.detail
                          || err.message);
    } finally { setBusy(false); }
  }

  async function confirmRedeem() {
    if (!scanResult?.ok) return;
    setBusy(true); setError(null);
    try {
      const { data } = await axios.post(
        `${API}/advertiser-app/${advertiser.advertiser_id}/redeem`,
        { code: code.trim() });
      setScanResult({ ...data, kind: "redeemed" });
      setCode("");
      loadFeed();
      if (inputRef.current) inputRef.current.focus();
    } catch (err) {
      setError(err?.response?.data?.detail?.code
                          || err?.response?.data?.detail
                          || err.message);
    } finally { setBusy(false); }
  }

  function reset() {
    setCode(""); setScanResult(null); setError(null);
    if (inputRef.current) inputRef.current.focus();
  }

  if (!advertiser) return null;

  const cardCls = light
    ? "bg-white border border-slate-200"
    : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  if (!canRedeem) {
    return (
      <div data-testid="advertiser-scan-forbidden" className="p-8 text-center">
        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
        <div className="mt-3 font-bold">Your role doesn’t have redemption access.</div>
        <div className={`text-xs ${muted} mt-1`}>Ask an owner or manager to grant `redemption_staff`.</div>
      </div>
    );
  }

  return (
    <div className={`space-y-6 ${light ? "text-slate-900" : "text-white"}`}
              data-testid="advertiser-scan-page">
      {/* Header */}
      <div>
        <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
          Phase AD.6 · Redemption terminal
        </div>
        <h1 className="mt-1 text-3xl font-black inline-flex items-center gap-2">
          <ScanLine className="w-6 h-6 text-amber-500" /> Scan / Redeem
        </h1>
        <p className={`text-sm mt-1 ${muted}`}>
          Point the barcode reader at the customer’s wallet QR — or type the code below.
        </p>
      </div>

      {/* Big input card — mobile-first */}
      <div className={`${cardCls} rounded-2xl p-5 sm:p-6`}
                  data-testid="advertiser-scan-input-card">
        <label className={`block text-xs uppercase tracking-widest font-mono ${muted} mb-2`}>
          Wallet code
        </label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            ref={inputRef}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") doScan(); }}
            placeholder="ADV-XXXX-XXX or QR-token"
            data-testid="advertiser-scan-manual-input"
            autoFocus autoComplete="off"
            className={`flex-1 px-4 py-4 rounded-xl border text-lg font-mono uppercase tracking-wider ${
                                    light ? "bg-white border-slate-300 text-slate-900 placeholder-slate-400"
                                                  : "bg-slate-950 border-slate-800 text-white placeholder-slate-500"} focus:outline-none focus:ring-2 focus:ring-amber-500`} />
          <button
            onClick={doScan}
            disabled={busy || !code.trim()}
            data-testid="advertiser-scan-submit"
            className="inline-flex items-center justify-center gap-2 bg-amber-500 text-slate-900 hover:bg-amber-400 rounded-xl px-6 py-4 text-base font-black shadow-lg shadow-amber-500/20 disabled:opacity-50 transition">
            {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <ScanLine className="w-5 h-5" />}
            Scan
          </button>
        </div>
        <div className={`text-[11px] mt-2 ${muted}`}>
          A USB barcode reader will auto-fill and submit. Press Enter to submit manually.
        </div>
      </div>

      {/* Result panel */}
      {error && (
        <div className="rounded-2xl border border-red-500/40 bg-red-500/10 text-red-300 px-5 py-4 flex items-start gap-3"
                    data-testid="advertiser-scan-error">
          <XCircle className="w-6 h-6 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-black">
              {(() => {
                const c = typeof error === "string" ? error :
                                    (error?.code || JSON.stringify(error));
                return REASON_LABEL[c] || c;
              })()}
            </div>
            <div className="text-xs opacity-80 mt-1 font-mono">{JSON.stringify(error)}</div>
          </div>
        </div>
      )}

      {scanResult && scanResult.ok === false && (
        <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 text-amber-300 px-5 py-4 flex items-start gap-3"
                    data-testid="advertiser-scan-invalid">
          <AlertTriangle className="w-6 h-6 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-black">{REASON_LABEL[scanResult.reason] || scanResult.reason}</div>
            {scanResult.redeemed_at && (
              <div className="text-xs opacity-80 mt-1">
                Redeemed at {new Date(scanResult.redeemed_at).toLocaleString()}
              </div>
            )}
            <button onClick={reset} className="mt-2 text-xs font-semibold underline">
              Scan another
            </button>
          </div>
        </div>
      )}

      {scanResult && scanResult.ok === true && scanResult.kind !== "redeemed" && (
        <div className={`rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-5 space-y-4`}
                    data-testid="advertiser-scan-preview">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-8 h-8 text-emerald-400" />
            <div>
              <div className={`text-xl font-black ${light ? "text-emerald-700" : "text-emerald-200"}`}>
                Valid coupon
              </div>
              <div className={`text-xs ${muted}`}>Review, then confirm to mark redeemed.</div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Campaign" value={scanResult.campaign_name || "—"} light={light} />
            <Field label="Coupon code" mono value={scanResult.code} light={light} />
            <Field label="Discount"
                          value={scanResult.discount_value != null
                                  ? `${scanResult.discount_value} ${scanResult.value_currency || ""}`
                                  : "—"} light={light} />
            <Field label="Customer" value={scanResult.customer_masked || "—"} light={light} />
            <Field label="Expires"
                          value={scanResult.expires_at
                                  ? new Date(scanResult.expires_at).toLocaleDateString()
                                  : "no expiry"} light={light} />
            <Field label="Type" value={scanResult.coupon_type} light={light} />
          </div>
          <div className="flex gap-2">
            <button onClick={confirmRedeem}
                            disabled={busy}
                            data-testid="advertiser-scan-confirm-redeem"
                            className="flex-1 inline-flex items-center justify-center gap-2 bg-emerald-500 text-slate-900 hover:bg-emerald-400 rounded-xl px-6 py-4 font-black shadow-lg shadow-emerald-500/20 disabled:opacity-50">
              {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
              Confirm redemption
            </button>
            <button onClick={reset} disabled={busy}
                            data-testid="advertiser-scan-cancel"
                            className={`px-4 py-4 rounded-xl font-semibold ${
                                              light ? "border border-slate-300 text-slate-700 hover:bg-slate-100"
                                                            : "border border-slate-700 text-slate-300 hover:bg-slate-800"}`}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {scanResult && scanResult.kind === "redeemed" && (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-5 flex items-start gap-3"
                    data-testid="advertiser-scan-redeemed">
          <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0" />
          <div className="flex-1">
            <div className={`text-xl font-black ${light ? "text-emerald-700" : "text-emerald-200"}`}>
              Redeemed ✔
            </div>
            <div className={`text-sm ${muted}`}>
              {scanResult.code} · {scanResult.campaign_name || "campaign"} · at{" "}
              {new Date(scanResult.redeemed_at).toLocaleTimeString()}
            </div>
            <button onClick={reset} className="mt-2 text-xs font-semibold text-emerald-400 hover:text-emerald-300 underline"
                            data-testid="advertiser-scan-next">
              Scan next
            </button>
          </div>
        </div>
      )}

      {/* Live feed */}
      <div className={`${cardCls} rounded-2xl overflow-hidden`}
                  data-testid="advertiser-scan-feed">
        <div className={`px-5 py-3 flex items-center justify-between ${
                                        light ? "bg-slate-50 border-b border-slate-200"
                                                      : "bg-slate-950 border-b border-slate-800"}`}>
          <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
            Recent redemptions
          </div>
          <div className={`text-[10px] font-mono ${muted} inline-flex items-center gap-1`}>
            <RefreshCw className="w-3 h-3" />
            {lastFeedAt ? `Updated ${lastFeedAt.toLocaleTimeString()}` : "—"} · auto 15s
          </div>
        </div>
        {feed.length === 0 ? (
          <div className={`py-8 text-center text-sm ${muted}`}
                      data-testid="advertiser-scan-feed-empty">
            No redemptions yet.
          </div>
        ) : (
          feed.map((r, i) => (
            <div key={r.redemption_id}
                          className={`px-5 py-3 flex items-center justify-between gap-3 ${
                                    light ? "border-b border-slate-100 last:border-0"
                                                  : "border-b border-slate-800 last:border-0"}`}
                          data-testid={`advertiser-recent-redemption-${i}`}>
              <div className="flex items-center gap-3 min-w-0">
                <div className={`w-8 h-8 rounded-full grid place-items-center flex-shrink-0 bg-emerald-500/15`}>
                  <Tag className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="min-w-0">
                  <div className={`text-sm font-mono truncate ${light ? "text-slate-900" : "text-white"}`}>
                    {r.code}
                  </div>
                  <div className={`text-[11px] ${muted} truncate`}>
                    {r.campaign_name || "—"} · staff <User className="inline w-3 h-3" /> {r.staff_email || r.staff_user_id}
                  </div>
                </div>
              </div>
              <div className={`text-[11px] font-mono ${muted} whitespace-nowrap inline-flex items-center gap-1`}>
                <Clock className="w-3 h-3" />
                {new Date(r.redeemed_at).toLocaleTimeString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}


function Field({ label, value, mono, light }) {
  return (
    <div>
      <div className={`text-[9px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>
        {label}
      </div>
      <div className={`mt-1 text-sm ${mono ? "font-mono" : "font-semibold"} ${light ? "text-slate-900" : "text-white"}`}>
        {value}
      </div>
    </div>
  );
}
