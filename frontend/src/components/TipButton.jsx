// Phase J.4 — Tip button + modal.  Mountable on:
//    community stations  → receiver_type="community_station_owner"
//    persona cards         → receiver_type="persona_rj"     (house pool)
//    user profiles          → receiver_type="user"
//
// Sender debit / receiver credit / platform 10% fee all happen
// server-side in /api/tips/send.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Coins, Loader2, Heart, MessageCircle, X } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { useAuth } from "@/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const QUICK_PICKS = [10, 50, 100, 500, 1000];

export default function TipButton({ receiver, variant = "outline",
                                                                              size = "md", className = "" }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;
  if (receiver?.id && user?.user_id === receiver.id) return null;
  return (
    <>
      <Button variant={variant} size={size}
                      className={className}
                      onClick={() => setOpen(true)}
                      data-testid={`tip-btn-${receiver?.type}-${receiver?.id || "x"}`}>
        <Coins size={14} /> Send tip
      </Button>
      {open && (
        <TipModal receiver={receiver} onClose={() => setOpen(false)} />
      )}
    </>
  );
}

function TipModal({ receiver, onClose }) {
  const { refresh } = useAuth();
  const [amount, setAmount] = useState(100);
  const [custom, setCustom] = useState("");
  const [message, setMessage] = useState("");
  const [balance, setBalance] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/me/points`);
        if (!cancelled) setBalance(Number(r.data?.balance || 0));
      } catch (_e) { /* ignored */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const effective = custom ? Math.max(10, Math.min(1000, Number(custom) | 0)) : amount;
  const fee = Math.round(effective * 0.10);
  const credit = effective - fee;
  const insufficient = balance !== null && balance < effective;

  const send = async () => {
    if (busy || insufficient) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/tips/send`, {
        receiver_type: receiver.type,
        receiver_entity_id: receiver.id,
        amount_pts: effective,
        message: message.trim() || undefined,
      });
      toast.success(`Sent ${effective} pts — ${receiver.name || "receiver"} got ${r.data?.tip?.receiver_credit_pts || credit}.`);
      onClose();
      try { await refresh(); } catch (_e) { /* */ }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = (typeof detail === "object" ? detail?.code : detail)
                              || "Tip failed.";
      toast.error(`Tip failed · ${msg.replace(/_/g, " ")}`);
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="tip-modal"
            className="fixed inset-0 z-[90] bg-black/70 backdrop-blur-sm
                              flex items-end sm:items-center justify-center px-3 py-6"
            onClick={onClose}>
      <Card className="w-full max-w-md p-5 sm:p-6 space-y-4 relative
                                      animate-[slide-up_180ms_ease-out]"
                  onClick={(e) => e.stopPropagation()}>
        <button onClick={onClose} aria-label="Close tip modal"
                        data-testid="tip-modal-close"
                        className="absolute top-3 right-3 text-text-secondary
                                          hover:text-white">
          <X size={16} />
        </button>

        <header className="space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-accent-gold flex items-center gap-2">
            <Heart size={11} /> Tip
          </div>
          <h2 className="font-display font-bold text-2xl tracking-display-tight">
            Send <span className="text-accent-gold">{receiver?.name || "creator"}</span> a tip
          </h2>
          <p className="text-xs text-text-secondary">
            {receiver?.type === "persona_rj"
              ? "Tips for AI hosts go to a house pool that funds listener prize draws."
              : "Send a small thank-you to the creator. 10% supports RadioLife."}
          </p>
        </header>

        <div data-testid="tip-quick-picks" className="grid grid-cols-5 gap-1.5">
          {QUICK_PICKS.map((n) => (
            <button key={n} onClick={() => { setAmount(n); setCustom(""); }}
                            data-testid={`tip-amount-${n}`}>
              <Chip active={!custom && amount === n}
                          tone={(!custom && amount === n) ? "gold" : "neutral"}>
                {n}
              </Chip>
            </button>
          ))}
        </div>

        <label className="block space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary">Or custom amount (10-1000 pts)</span>
          <input type="number" inputMode="numeric" min={10} max={1000}
                          placeholder="—"
                          value={custom}
                          onChange={(e) => setCustom(e.target.value)}
                          data-testid="tip-custom-amount"
                          className="w-full rounded-token-md bg-white/[0.04]
                                          border border-white/10 px-3.5 py-2 text-sm
                                          focus:outline-none focus:border-accent-gold/60" />
        </label>

        <label className="block space-y-1">
          <span className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-1.5">
            <MessageCircle size={11} /> Message (optional, 140 chars)
          </span>
          <textarea value={message} maxLength={140} rows={2}
                          onChange={(e) => setMessage(e.target.value)}
                          data-testid="tip-message"
                          className="w-full rounded-token-md bg-white/[0.04]
                                          border border-white/10 px-3.5 py-2 text-sm
                                          focus:outline-none focus:border-accent-gold/60
                                          resize-none" />
        </label>

        <div className="bg-white/[0.04] rounded-token-md p-3 text-xs space-y-1.5
                                font-mono" data-testid="tip-breakdown">
          <div className="flex justify-between">
            <span className="text-text-secondary">You send</span>
            <span className="text-text-primary">{effective.toLocaleString()} pts</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">{receiver?.name || "Receiver"} gets</span>
            <span className="text-accent-gold">{credit.toLocaleString()} pts</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">RadioLife fee (10%)</span>
            <span className="text-text-secondary">{fee.toLocaleString()} pts</span>
          </div>
          {balance !== null && (
            <div className="flex justify-between border-t border-white/[0.06] pt-1.5 mt-1">
              <span className="text-text-secondary">Your balance</span>
              <span className={insufficient ? "text-rose-300"
                                                                      : "text-text-primary"}>
                {balance.toLocaleString()} pts
              </span>
            </div>
          )}
        </div>

        <Button variant="gold" className="w-full"
                        onClick={send} disabled={busy || insufficient}
                        data-testid="tip-confirm">
          {busy
            ? <><Loader2 size={14} className="animate-spin" /> Sending…</>
            : insufficient
              ? "Insufficient balance"
              : <>Send {effective.toLocaleString()} pts <Coins size={14} /></>}
        </Button>
      </Card>
    </div>
  );
}
