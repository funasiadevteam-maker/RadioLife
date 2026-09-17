// Advertiser "Boost my slot" — raise a station's bid to win more slots in
// the home Sponsored rotation. Higher bid = more airtime.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, TrendingUp, Radio, ArrowUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const usd = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export default function SponsorBoost() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = () => {
    setLoading(true);
    axios.get(`${API}/promoted/stations?limit=12`, { withCredentials: true })
      .then((r) => setItems(r.data?.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const boost = async (promo_id, current, inc) => {
    setBusy(promo_id + inc);
    try {
      const next = Math.round((current || 100) + inc);
      await axios.post(`${API}/promoted/${promo_id}/bid`,
        { cpm_bid_cents: next }, { withCredentials: true });
      toast.success(`Bid raised to ${usd(next)} — more rotation slots`);
      load();
    } catch (e) {
      const s = e?.response?.status;
      toast.error(s === 401 || s === 403
        ? "Log in as the advertiser to boost this slot"
        : "Boost failed");
    } finally { setBusy(null); }
  };

  const maxBid = Math.max(1, ...items.map((i) => i.bid_cents || 0));

  return (
    <div data-testid="sponsor-boost-page"
              className="min-h-screen bg-slate-950 text-slate-100 px-4 py-8
                                max-w-2xl mx-auto space-y-5">
      <Toaster richColors theme="dark" position="bottom-right" />
      <header className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 flex items-center gap-2">
          <TrendingUp size={11} /> Sponsor slots
        </div>
        <h1 className="font-black text-3xl tracking-tight">
          Boost your <span className="text-amber-400">home rotation</span>
        </h1>
        <p className="text-sm text-slate-400">
          The home "Sponsored" spot rotates across these stations. A higher bid
          wins <strong className="text-slate-200">more rotation slots</strong> — more airtime.
        </p>
      </header>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin" size={26} /></div>
      ) : (
        <div className="space-y-3" data-testid="sponsor-boost-list">
          {items.map((s, i) => {
            const share = Math.round(((s.bid_cents || 0) / maxBid) * 100);
            return (
              <div key={s.promo_id}
                        data-testid={`sponsor-boost-row-${i}`}
                        className="rounded-2xl bg-slate-900 border border-slate-800 p-4">
                <div className="flex items-center gap-3">
                  <span className="w-10 h-10 rounded-xl grid place-items-center bg-cyan-500/15 text-cyan-300 flex-shrink-0">
                    <Radio size={18} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-black text-white truncate">{s.name}</div>
                    <div className="text-xs text-slate-400">
                      Current bid <span className="text-amber-300 font-bold"
                                                      data-testid={`sponsor-boost-bid-${i}`}>{usd(s.bid_cents)}</span> CPM
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" disabled={!!busy}
                                  onClick={() => boost(s.promo_id, s.bid_cents, 200)}
                                  data-testid={`sponsor-boost-plus2-${i}`}
                                  className="px-3 h-9 rounded-full text-xs font-black bg-slate-800 text-slate-100 hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-1">
                      <ArrowUp size={12} /> $2
                    </button>
                    <button type="button" disabled={!!busy}
                                  onClick={() => boost(s.promo_id, s.bid_cents, 500)}
                                  data-testid={`sponsor-boost-plus5-${i}`}
                                  className="px-3 h-9 rounded-full text-xs font-black text-slate-950 bg-amber-400 hover:bg-amber-300 disabled:opacity-50 inline-flex items-center gap-1">
                      {busy === s.promo_id + 500 ? <Loader2 size={12} className="animate-spin" /> : <ArrowUp size={12} />} $5
                    </button>
                  </div>
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div className="h-full rounded-full bg-gradient-to-r from-amber-400 to-pink-500"
                            style={{ width: `${share}%` }} />
                </div>
                <div className="text-[10px] text-slate-500 mt-1">{share}% of top bid · more share = more slots</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
