// RadioLife Shop — Saved Cards wallet. Add a card via Stripe hosted setup,
// pick a default for one-tap checkout, remove cards. Renders in-shell.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, CreditCard, Plus, Trash2, Check, Star } from "lucide-react";
import { API } from "@/AuthContext";

const BRAND = {
  visa: "Visa", mastercard: "Mastercard", amex: "Amex",
  discover: "Discover", jcb: "JCB", diners: "Diners", unionpay: "UnionPay",
};

export default function WalletCardsRadioLife() {
  const navigate = useNavigate();
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/shop/wallet/cards`);
      setCards(r.data.cards || []);
    } catch (e) {
      setError(e?.response?.data?.detail?.code || "Could not load cards");
    } finally { setLoading(false); }
  }, []);

  // Return from the hosted setup flow → sync the newly-added card, then clean URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const setup = params.get("setup");
    const sid = params.get("session_id");
    (async () => {
      if (setup === "success" && sid) {
        try { await axios.post(`${API}/shop/wallet/cards/setup-session/${sid}/sync`); } catch { /* ignore */ }
        window.history.replaceState({}, "", "/shop/wallet/cards");
      }
      await load();
    })();
  }, [load]);

  const addCard = async () => {
    setBusy(true); setError(null);
    try {
      const r = await axios.post(`${API}/shop/wallet/cards/setup-session`, {
        origin_url: window.location.origin,
      });
      window.location.href = r.data.checkout_url;
    } catch (e) {
      setError(e?.response?.data?.detail?.code || "Could not start card setup");
      setBusy(false);
    }
  };

  const setDefault = async (pm) => {
    setBusy(true); setError(null);
    try {
      const r = await axios.post(`${API}/shop/wallet/cards/${pm}/default`);
      setCards(r.data.cards || []);
    } catch (e) { setError(e?.response?.data?.detail?.code || "Could not update"); }
    finally { setBusy(false); }
  };

  const remove = async (pm) => {
    setBusy(true); setError(null);
    try {
      const r = await axios.delete(`${API}/shop/wallet/cards/${pm}`);
      setCards(r.data.cards || []);
    } catch (e) { setError(e?.response?.data?.detail?.code || "Could not remove"); }
    finally { setBusy(false); }
  };

  return (
    <div className="pb-24" data-testid="rl-wallet-cards-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="wallet-cards-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Payment methods</h1>
      </div>

      <div className="px-4 mt-4 space-y-3">
        {loading ? (
          <div className="text-slate-400 text-sm" data-testid="wallet-cards-loading">Loading your cards…</div>
        ) : cards.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-6 text-center" data-testid="wallet-cards-empty">
            <CreditCard size={34} className="mx-auto text-slate-300" />
            <p className="text-slate-500 mt-2 text-sm">No saved cards yet. Add one for faster, one-tap checkout.</p>
          </div>
        ) : (
          cards.map((c) => (
            <div key={c.id} className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center gap-3" data-testid={`wallet-card-${c.id}`}>
              <div className="w-11 h-11 rounded-xl bg-slate-900 flex items-center justify-center">
                <CreditCard size={20} className="text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-black text-slate-900">{BRAND[c.brand] || c.brand} •••• {c.last4}</div>
                <div className="text-xs text-slate-500">Expires {String(c.exp_month).padStart(2, "0")}/{c.exp_year}</div>
              </div>
              {c.is_default ? (
                <span className="text-xs font-black text-green-700 bg-green-100 rounded-full px-2.5 py-1 flex items-center gap-1" data-testid={`wallet-card-default-badge-${c.id}`}>
                  <Star size={12} className="fill-green-700" />Default
                </span>
              ) : (
                <button onClick={() => setDefault(c.id)} disabled={busy} data-testid={`wallet-card-setdefault-${c.id}`}
                  className="text-xs font-bold text-orange-600 border border-orange-200 rounded-full px-3 py-1.5 disabled:opacity-50">Set default</button>
              )}
              <button onClick={() => remove(c.id)} disabled={busy} data-testid={`wallet-card-remove-${c.id}`}
                className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 disabled:opacity-50"><Trash2 size={16} /></button>
            </div>
          ))
        )}

        {error && <div className="text-rose-600 text-sm font-semibold" data-testid="wallet-cards-error">{error}</div>}

        <button onClick={addCard} disabled={busy} data-testid="wallet-cards-add"
          className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-4 disabled:opacity-60">
          {busy ? "Opening…" : <><Plus size={18} />Add a card</>}
        </button>
        <p className="text-xs text-slate-400 flex items-center gap-1"><Check size={12} className="text-green-600" />Cards are stored securely by Stripe — RadioLife never sees your card number.</p>
      </div>
    </div>
  );
}
