// Phase MKT.1 — Admin: Rate Card Matrix (CPM/CPA/CPL pricing per ad inventory type).
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { DollarSign, Loader2, Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { Card, Button } from "@/shell/primitives";

const MODELS = ["CPM", "CPA", "CPL"];

export default function RateCard() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/rate-card`);
      setItems(r.data.items || []);
    } catch {
      toast.error("Failed to load — admin only.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const update = (idx, field, value) => {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, [field]: value } : it)));
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        items: items.map((it) => ({
          key: it.key,
          label: it.label,
          pricing_model: it.pricing_model,
          base_cents: Number(it.base_cents) || 0,
          min_cents: Number(it.min_cents) || 0,
          max_cents: Number(it.max_cents) || 0,
          multipliers: it.multipliers || {},
          enabled: !!it.enabled,
        })),
      };
      const r = await axios.put(`${API}/admin/rate-card`, payload);
      setItems(r.data.items || []);
      toast.success("Rate card saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Save failed — check min/max & model.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24" data-testid="rate-card-loading">
        <Loader2 className="w-6 h-6 animate-spin text-orange-500" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8" data-testid="rate-card-root">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/15 flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-orange-500" />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight">Rate Card Matrix</h1>
            <p className="text-sm text-neutral-500">
              Set pricing (CPM / CPA / CPL) and multipliers per ad inventory type.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} data-testid="rate-card-reload">
            <RotateCcw className="w-4 h-4 mr-1" /> Reload
          </Button>
          <Button size="sm" onClick={save} disabled={saving} data-testid="rate-card-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Save className="w-4 h-4 mr-1" /> Save</>}
          </Button>
        </div>
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm" data-testid="rate-card-table">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-neutral-500 border-b border-neutral-200/60">
              <th className="p-3">Inventory</th>
              <th className="p-3">Model</th>
              <th className="p-3">Base ¢</th>
              <th className="p-3">Min ¢</th>
              <th className="p-3">Max ¢</th>
              <th className="p-3">Enabled</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, idx) => (
              <tr key={it.key} className="border-b border-neutral-100/60" data-testid={`rate-row-${it.key}`}>
                <td className="p-3 font-semibold">{it.label}</td>
                <td className="p-3">
                  <select
                    className="border border-neutral-300 rounded-md px-2 py-1 bg-white"
                    value={it.pricing_model}
                    onChange={(e) => update(idx, "pricing_model", e.target.value)}
                    data-testid={`rate-model-${it.key}`}
                  >
                    {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </td>
                <td className="p-3">
                  <input type="number" className="w-24 border border-neutral-300 rounded-md px-2 py-1"
                    value={it.base_cents} onChange={(e) => update(idx, "base_cents", e.target.value)}
                    data-testid={`rate-base-${it.key}`} />
                </td>
                <td className="p-3">
                  <input type="number" className="w-20 border border-neutral-300 rounded-md px-2 py-1"
                    value={it.min_cents} onChange={(e) => update(idx, "min_cents", e.target.value)}
                    data-testid={`rate-min-${it.key}`} />
                </td>
                <td className="p-3">
                  <input type="number" className="w-20 border border-neutral-300 rounded-md px-2 py-1"
                    value={it.max_cents} onChange={(e) => update(idx, "max_cents", e.target.value)}
                    data-testid={`rate-max-${it.key}`} />
                </td>
                <td className="p-3">
                  <input type="checkbox" checked={!!it.enabled}
                    onChange={(e) => update(idx, "enabled", e.target.checked)}
                    data-testid={`rate-enabled-${it.key}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <p className="text-xs text-neutral-400 mt-3">
        These rates seed the pricing hints shown to merchants in the Marketplace campaign builder.
      </p>
    </div>
  );
}
