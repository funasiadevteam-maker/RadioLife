// Phase E — AD.7.1 Split-the-bill modal.
// Renders on top of ScanCheckout when the user taps "Split with a friend".
// Steps: (1) edit shares (2-8 payers) → (2) POST /api/scan-to-pay/splits →
// (3) show invite links + QR codes.
import { useMemo, useState } from "react";
import axios from "axios";
import {
  X, Plus, Trash2, Copy, Loader2, QrCode, AlertCircle, ArrowLeft,
  CheckCircle2, Users,
} from "lucide-react";
import { API } from "@/AuthContext";
import QRCode from "qrcode";

const MIN_SHARES = 2;
const MAX_SHARES = 8;
const DEFAULT_MIN_SHARE_CENTS = 100;


export default function SplitModal({
  open, onClose, merchant, qrToken, totalAmountCents, currency = "usd",
  minShareCents = DEFAULT_MIN_SHARE_CENTS, light = false,
}) {
  const [step, setStep] = useState("edit");   // edit | done
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [description, setDescription] = useState("");
  const [shares, setShares] = useState(() => defaultShares(2, totalAmountCents));

  const total = totalAmountCents || 0;
  const sum = useMemo(
    () => shares.reduce((a, s) => a + Number(s.share_amount_cents || 0), 0),
    [shares]);
  const sumOk = sum === total;
  const anyBelowMin = shares.some(
    (s) => Number(s.share_amount_cents || 0) < minShareCents);

  const set = (i, patch) => setShares((cur) =>
    cur.map((s, idx) => idx === i ? { ...s, ...patch } : s));
  const addShare = () => {
    if (shares.length >= MAX_SHARES) return;
    setShares((cur) => [...cur, {
      share_amount_cents: 0,
      display_name: `Guest ${cur.length + 1}`,
    }]);
  };
  const removeShare = (i) => {
    if (shares.length <= MIN_SHARES) return;
    setShares((cur) => cur.filter((_, idx) => idx !== i));
  };
  const evenSplit = () => {
    const n = shares.length;
    const base = Math.floor(total / n);
    const rem = total - base * n;
    const next = shares.map((s, idx) => ({
      ...s,
      share_amount_cents: base + (idx === n - 1 ? rem : 0),
    }));
    setShares(next);
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = {
        merchant_id: merchant?.merchant_id,
        total_amount_cents: total,
        currency: (currency || "usd").toLowerCase(),
        qr_token: qrToken,
        description: description.trim() || undefined,
        shares: shares.map((s) => ({
          share_amount_cents: Number(s.share_amount_cents || 0),
          display_name: (s.display_name || "").trim() || undefined,
        })),
      };
      const r = await axios.post(`${API}/scan-to-pay/splits`, body,
                                                    { withCredentials: true });
      setResult(r.data);
      setStep("done");
    } catch (err) {
      setError(err?.response?.data?.detail?.code
                      || err?.response?.data?.detail
                      || err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  const backdrop = "fixed inset-0 z-[80] bg-black/70 backdrop-blur";
  const shell = light
    ? "bg-white text-slate-900 border border-slate-200"
    : "bg-slate-900 text-white border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const input = light
    ? "bg-white border border-slate-200 text-slate-900"
    : "bg-slate-950 border border-slate-800 text-white";
  const ghost = light
    ? "text-slate-500 hover:text-slate-900"
    : "text-slate-400 hover:text-white";

  return (
    <div className={backdrop} data-testid="split-modal">
      <div className="min-h-screen p-4 flex items-start sm:items-center justify-center">
        <div className={`${shell} w-full max-w-md rounded-2xl shadow-2xl`}>
          <div className="flex items-center justify-between px-5 py-4 border-b border-inherit
                                        border-slate-500/20">
            <div className="flex items-center gap-2">
              <Users size={16} className="text-fuchsia-500" />
              <span className="text-sm font-black uppercase tracking-widest">
                Split the bill
              </span>
            </div>
            <button onClick={onClose} className={ghost}
                            data-testid="split-modal-close">
              <X size={18} />
            </button>
          </div>

          {step === "edit" && (
            <div className="px-5 py-4">
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                Bill total
              </div>
              <div className="text-3xl font-black tabular-nums"
                          data-testid="split-modal-total">
                {formatMoney(total, currency)}
              </div>
              <div className={`text-[11px] ${muted} mt-0.5`}>
                {merchant?.name || "Merchant"} · min share {formatMoney(minShareCents, currency)}
              </div>

              <label className={`block text-[10px] mt-4 mb-1 font-mono uppercase
                                                    tracking-widest ${muted}`}>Note (optional)</label>
              <input type="text" value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Dinner on Friday…"
                            data-testid="split-modal-description"
                            className={`w-full px-3 py-2 rounded-lg text-sm ${input}`} />

              <div className="mt-5 space-y-2">
                {shares.map((s, i) => (
                  <div key={i} className="flex items-center gap-2"
                              data-testid={`split-modal-row-${i}`}>
                    <input type="text" value={s.display_name || ""}
                                  onChange={(e) => set(i, { display_name: e.target.value })}
                                  placeholder={`Guest ${i + 1}`}
                                  data-testid={`split-modal-name-${i}`}
                                  className={`flex-1 px-3 py-2 rounded-lg text-sm ${input}`} />
                    <div className={`flex items-center gap-1 px-2 rounded-lg
                                                    ${light ? "bg-slate-100" : "bg-slate-950/40"} min-w-[140px]`}>
                      <span className={`text-xs ${muted}`}>
                        {symbolFor(currency)}
                      </span>
                      <input type="number" min="0" step="1"
                                    value={s.share_amount_cents / 100 || ""}
                                    onChange={(e) => set(i, {
                                      share_amount_cents:
                                        Math.round(Number(e.target.value || 0) * 100),
                                    })}
                                    data-testid={`split-modal-amount-${i}`}
                                    className="flex-1 bg-transparent px-1 py-2 text-sm
                                                          text-right font-mono focus:outline-none" />
                    </div>
                    <button onClick={() => removeShare(i)}
                                    disabled={shares.length <= MIN_SHARES}
                                    data-testid={`split-modal-remove-${i}`}
                                    className={`${ghost} disabled:opacity-30 p-1.5`}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap gap-2 mt-3">
                <button onClick={addShare} disabled={shares.length >= MAX_SHARES}
                                data-testid="split-modal-add-share"
                                className={`inline-flex items-center gap-1 text-xs
                                                        px-3 py-1.5 rounded-full border
                                                        ${light ? "border-slate-300 text-slate-700 hover:bg-slate-100"
                                                                    : "border-slate-700 text-slate-300 hover:bg-slate-800/50"}
                                                        disabled:opacity-30`}>
                  <Plus size={12} /> Add payer
                </button>
                <button onClick={evenSplit}
                                data-testid="split-modal-even-split"
                                className="inline-flex items-center gap-1 text-xs
                                                        px-3 py-1.5 rounded-full
                                                        bg-fuchsia-500/15 border border-fuchsia-500/40
                                                        text-fuchsia-500 hover:bg-fuchsia-500/25">
                  Even split ({shares.length})
                </button>
              </div>

              <div className={`mt-4 rounded-lg px-3 py-2 flex items-center justify-between
                                              text-xs ${
                                                sumOk ? (light ? "bg-emerald-50 border border-emerald-200 text-emerald-700"
                                                                        : "bg-emerald-500/10 border border-emerald-500/40 text-emerald-400")
                                                              : (light ? "bg-red-50 border border-red-200 text-red-700"
                                                                          : "bg-red-500/10 border border-red-500/40 text-red-400")}`}>
                <span>Sum of shares</span>
                <span className="font-mono font-black" data-testid="split-modal-sum">
                  {formatMoney(sum, currency)} / {formatMoney(total, currency)}
                </span>
              </div>

              {error && (
                <div className={`mt-3 rounded-lg px-3 py-2 flex items-center gap-2 text-xs
                                                bg-red-500/10 border border-red-500/40 text-red-400`}
                            data-testid="split-modal-error">
                  <AlertCircle size={12} />
                  <span>{prettyError(error)}</span>
                </div>
              )}

              <button onClick={submit}
                              disabled={busy || !sumOk || anyBelowMin}
                              data-testid="split-modal-submit"
                              className="w-full mt-5 py-3 rounded-full text-sm font-black
                                                    inline-flex items-center justify-center gap-2
                                                    bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                    disabled:opacity-40 disabled:cursor-not-allowed">
                {busy ? <Loader2 size={16} className="animate-spin" /> : null}
                Send invite links
              </button>
            </div>
          )}

          {step === "done" && result && (
            <div className="px-5 py-4"
                        data-testid="split-modal-done">
              <div className="text-center mb-4">
                <div className="w-12 h-12 mx-auto rounded-full grid place-items-center
                                            bg-emerald-500/15 border-2 border-emerald-500 mb-2">
                  <CheckCircle2 size={24} className="text-emerald-500" />
                </div>
                <div className="text-sm font-black">Split created</div>
                <div className={`text-[11px] font-mono ${muted}`}>
                  ID {result.split_id}
                </div>
              </div>

              <ShareLinksList result={result} light={light} />

              <button onClick={onClose}
                              data-testid="split-modal-done-close"
                              className={`w-full mt-4 py-2.5 rounded-full text-xs font-black
                                                    border ${light ? "border-slate-300 text-slate-700 hover:bg-slate-100"
                                                                            : "border-slate-700 text-slate-300 hover:bg-slate-800/40"}`}>
                Done
              </button>
              <a href="/my/splits"
                  className="block text-center text-[11px] mt-2 text-fuchsia-500 hover:underline"
                  data-testid="split-modal-my-splits-link">
                View my splits →
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function ShareLinksList({ result, light }) {
  return (
    <div className="space-y-2">
      {(result.shares || []).map((s) => {
        const url = result.invite_urls?.[s.share_id];
        return (
          <ShareLinkRow key={s.share_id} share={s} url={url} light={light} />
        );
      })}
    </div>
  );
}


function ShareLinkRow({ share, url, light }) {
  const [copied, setCopied] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState(null);
  const bg = light ? "bg-slate-50 border border-slate-200"
                                        : "bg-slate-950/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* ignore */ }
  };
  const showQr = async () => {
    if (!qrDataUrl && url) {
      const d = await QRCode.toDataURL(url, { width: 200,
                                                                              margin: 1,
                                                                              color: {
                                                                                dark: light ? "#0f172a" : "#f8fafc",
                                                                                light: light ? "#ffffff" : "#020617",
                                                                              } });
      setQrDataUrl(d);
    }
    setQrOpen((o) => !o);
  };

  return (
    <div className={`${bg} rounded-lg p-3`}
              data-testid={`split-modal-share-${share.share_id}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="min-w-0">
          <div className="text-sm font-black truncate"
                      data-testid={`split-modal-share-name-${share.share_id}`}>
            {share.display_name}
          </div>
          <div className={`text-[10px] font-mono ${muted}`}>
            {(share.share_amount_cents / 100).toFixed(2)}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={showQr}
                          data-testid={`split-modal-share-qr-${share.share_id}`}
                          className={`p-1.5 rounded ${
                            light ? "hover:bg-slate-200 text-slate-600"
                                        : "hover:bg-slate-800/50 text-slate-300"}`}>
            <QrCode size={14} />
          </button>
          <button onClick={copy}
                          data-testid={`split-modal-share-copy-${share.share_id}`}
                          className={`inline-flex items-center gap-1 text-[11px] px-2 py-1
                                                    rounded ${copied ? "text-emerald-500"
                                                                                  : light ? "hover:bg-slate-200 text-slate-700"
                                                                                              : "hover:bg-slate-800/50 text-slate-200"}`}>
            <Copy size={12} /> {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className={`text-[10px] font-mono ${muted} break-all`}
                  data-testid={`split-modal-share-url-${share.share_id}`}>
        {url}
      </div>
      {qrOpen && qrDataUrl && (
        <div className="mt-2 grid place-items-center bg-white rounded p-2"
                    data-testid={`split-modal-share-qr-img-${share.share_id}`}>
          <img src={qrDataUrl} alt="QR" className="w-32 h-32" />
        </div>
      )}
    </div>
  );
}


function defaultShares(n, total) {
  const arr = [];
  const base = Math.floor((total || 0) / n);
  const rem = (total || 0) - base * n;
  for (let i = 0; i < n; i++) {
    arr.push({
      share_amount_cents: base + (i === n - 1 ? rem : 0),
      display_name: `Guest ${i + 1}`,
    });
  }
  return arr;
}


function symbolFor(cur) {
  const c = (cur || "").toLowerCase();
  if (c === "usd") return "$";
  if (c === "aed") return "AED";
  if (c === "eur") return "€";
  if (c === "gbp") return "£";
  return c.toUpperCase();
}
function formatMoney(cents, cur) {
  return `${symbolFor(cur)} ${((cents || 0) / 100).toFixed(2)}`;
}
function prettyError(code) {
  const map = {
    shares_sum_mismatch: "The sum of shares doesn't match the total.",
    share_below_min:      "One or more shares are below the minimum.",
    invalid_share_count: "You need between 2 and 8 payers.",
    merchant_not_found:  "Merchant not found.",
    invalid_total:            "Bill total must be positive.",
    auth_required:          "Sign in required.",
  };
  return map[code] || String(code);
}
