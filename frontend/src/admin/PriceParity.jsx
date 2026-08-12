// Price Parity Monitor (admin) — flags venues whose in-app price drifts from
// the restaurant's own "direct" price. Admin can override the direct reference
// per item/product (admin override wins over the merchant-supplied value).
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Loader2, AlertTriangle, Check, X } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { Card, Button } from "@/shell/primitives";

const money = (c) => (c == null ? "—" : `$${(c / 100).toFixed(2)}`);
const inputCls = "w-28 rounded-token-md bg-white/[0.04] border border-white/[0.08] px-2 py-1.5 text-sm";

export default function PriceParity() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [onlyFlagged, setOnlyFlagged] = useState(false);
  const [edits, setEdits] = useState({}); // ref -> dollars string
  const [savingRef, setSavingRef] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/marketplace/price-parity`,
        { params: { only_flagged: onlyFlagged } });
      setData(r.data);
    } catch {
      toast.error("Failed to load — admin only.");
    } finally {
      setLoading(false);
    }
  }, [onlyFlagged]);

  useEffect(() => { load(); }, [load]);

  const refKey = (r) => `${r.ref_type}:${r.ref_id}`;

  const save = async (r) => {
    const key = refKey(r);
    const raw = edits[key];
    setSavingRef(key);
    try {
      const cents = raw === "" || raw == null ? null : Math.round(parseFloat(raw) * 100);
      if (cents != null && (Number.isNaN(cents) || cents < 0)) {
        toast.error("Enter a valid price");
        setSavingRef(null);
        return;
      }
      await axios.post(`${API}/admin/marketplace/price-parity/override`, {
        ref_type: r.ref_type, ref_id: r.ref_id, direct_price_cents: cents,
      });
      toast.success(cents == null ? "Override cleared" : "Direct price saved");
      setEdits((e) => { const n = { ...e }; delete n[key]; return n; });
      await load();
    } catch {
      toast.error("Save failed");
    } finally {
      setSavingRef(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto pt-20 text-center text-text-secondary"
        data-testid="price-parity-loading">
        <Loader2 className="animate-spin inline-block mr-2" size={18} /> Loading…
      </div>
    );
  }

  const rows = data?.items || [];

  return (
    <div data-testid="price-parity-root" className="max-w-4xl mx-auto space-y-6 pb-24">
      <div className="flex items-center justify-between">
        <h1 className="font-display font-bold text-2xl tracking-display-tight">
          Price Parity Monitor
        </h1>
        <Button variant="secondary" size="sm" onClick={() => setOnlyFlagged((v) => !v)}
          data-testid="price-parity-toggle-flagged">
          {onlyFlagged ? "Show all" : "Show flagged only"}
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3" data-testid="price-parity-summary">
        <Card className="p-4">
          <div className="text-xs text-text-secondary">Flagged</div>
          <div className="text-2xl font-display font-bold text-accent-gold"
            data-testid="price-parity-flagged-count">{data?.flagged_count ?? 0}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-text-secondary">Tracked (have direct price)</div>
          <div className="text-2xl font-display font-bold">{data?.tracked_count ?? 0}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-text-secondary">Tolerance</div>
          <div className="text-2xl font-display font-bold">±{data?.tolerance_pct ?? 3}%</div>
        </Card>
      </div>

      {rows.length === 0 && (
        <Card className="p-4 text-sm text-text-secondary" data-testid="price-parity-empty">
          Nothing to show. Set a direct price on an item to start tracking drift.
        </Card>
      )}

      <div className="space-y-2">
        {rows.map((r) => {
          const key = refKey(r);
          const editing = edits[key] !== undefined;
          const editVal = editing
            ? edits[key]
            : (r.direct_price_cents != null ? (r.direct_price_cents / 100).toFixed(2) : "");
          return (
            <Card key={key} className="p-3 flex items-center gap-3 flex-wrap"
              data-testid={`price-parity-row-${key}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold truncate flex items-center gap-2">
                  {r.flagged && <AlertTriangle size={14} className="text-accent-gold shrink-0" />}
                  {r.name || r.ref_id}
                  <span className="text-[10px] uppercase font-mono text-text-secondary border border-white/10 rounded px-1 py-0.5">
                    {r.ref_type}
                  </span>
                </div>
                <div className="text-xs text-text-secondary truncate">{r.business_name}</div>
              </div>

              <div className="text-sm">
                <div className="text-[10px] text-text-secondary uppercase">App</div>
                <div className="font-mono font-semibold" data-testid={`price-parity-app-${key}`}>
                  {money(r.app_price_cents)}
                </div>
              </div>

              <div className="flex items-center gap-1">
                <span className="text-text-secondary text-sm">$</span>
                <input
                  className={inputCls}
                  type="number" step="0.01" min="0"
                  placeholder="direct"
                  data-testid={`price-parity-input-${key}`}
                  value={editVal}
                  onChange={(e) => setEdits((s) => ({ ...s, [key]: e.target.value }))} />
              </div>

              <div className="text-sm w-20 text-right">
                <div className="text-[10px] text-text-secondary uppercase">Drift</div>
                <div className={`font-mono font-bold ${r.flagged ? "text-accent-gold" : "text-text-secondary"}`}
                  data-testid={`price-parity-drift-${key}`}>
                  {r.drift_pct == null ? "—" : `${r.drift_pct > 0 ? "+" : ""}${r.drift_pct}%`}
                </div>
              </div>

              <Button variant="primary" size="sm" onClick={() => save(r)}
                disabled={savingRef === key}
                data-testid={`price-parity-save-${key}`}>
                {savingRef === key ? <Loader2 size={13} className="animate-spin" />
                  : <><Check size={13} /> Save</>}
              </Button>
              {r.direct_price_cents != null && (
                <Button variant="ghost" size="sm"
                  onClick={() => { setEdits((s) => ({ ...s, [key]: "" })); save(r); }}
                  data-testid={`price-parity-clear-${key}`}>
                  <X size={13} /> Clear
                </Button>
              )}
              {r.source === "admin" && (
                <span className="text-[10px] text-emerald-400 font-mono">admin-set</span>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
