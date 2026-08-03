// Phase 18a — Billing: balance + Stripe Checkout top-up + invoice/spend log.
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Plus, Wallet } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Billing({ advertiserId }) {
  const [adv, setAdv] = useState(null);
  const [amount, setAmount] = useState(100);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!advertiserId) return;
    axios.get(`${API}/advertiser/${advertiserId}`)
            .then((r) => setAdv(r.data.advertiser)).catch(() => {});
  }, [advertiserId]);

  const topup = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/advertiser/${advertiserId}/topup`,
                                                    { amount_usd: parseFloat(amount) });
      if (r.data.checkout_url) {
        if (r.data.mocked) {
          toast.success(`Mocked top-up: $${amount} credited (no Stripe key)`);
          setTimeout(() => window.location.reload(), 800);
        } else {
          window.location = r.data.checkout_url;
        }
      }
    } catch (e) {
      toast.error("top-up failed");
    } finally { setBusy(false); }
  };

  if (!adv) return <div className="text-text-secondary">Loading...</div>;

  return (
    <div className="space-y-4" data-testid="advertiser-billing">
      <h2 className="font-display font-bold text-2xl">Billing</h2>

      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5"
                  data-testid="billing-balance-card">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
          <Wallet size={11} className="inline mr-1" /> Account balance
        </div>
        <div className="font-display font-bold text-4xl text-accent-electric mt-1">
          ${(adv.account_balance_usd || 0).toFixed(2)}
        </div>
        <div className="text-xs text-text-secondary mt-1">
          Stripe customer: <span className="font-mono">{adv.stripe_customer_id || "—"}</span>
        </div>
      </div>

      <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 space-y-3"
                  data-testid="billing-topup-card">
        <div className="font-display font-bold text-lg">Top up ad wallet</div>
        <div className="flex gap-2">
          {[50, 100, 250, 500].map((v) => (
            <button key={v} onClick={() => setAmount(v)}
                        data-testid={`topup-preset-${v}`}
                        className={`text-xs px-3 py-1.5 rounded-full border
                            ${amount === v ? "border-accent-electric text-accent-electric bg-accent-electric/[0.08]"
                                                  : "border-white/[0.10] text-text-secondary"}`}>${v}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input type="number" min="10" className="bigfm-input flex-1" value={amount}
                    data-testid="topup-amount-input"
                    onChange={(e) => setAmount(e.target.value)} />
          <button className="bigfm-cta" onClick={topup} disabled={busy}
                      data-testid="topup-submit-btn">
            <Plus size={14} /> {busy ? "..." : "Top up"}
          </button>
        </div>
      </div>
    </div>
  );
}
