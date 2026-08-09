// Phase RWD.4 — Admin: Sponsored Bonus windows + Fraud Alerts console.
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { AlertTriangle, Zap, Loader2, Check, Plus } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { Card, Button } from "@/shell/primitives";

export default function MerchantOps() {
  const [alerts, setAlerts] = useState([]);
  const [windows, setWindows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [form, setForm] = useState({
    merchant_id: "", sponsor_name: "", multiplier: 2,
    hours: 6, title: "",
  });

  const load = useCallback(async () => {
    try {
      const [a, w] = await Promise.all([
        axios.get(`${API}/admin/fraud-alerts?status=open`),
        axios.get(`${API}/admin/bonus-windows`),
      ]);
      setAlerts(a.data.items || []);
      setWindows(w.data.items || []);
    } catch {
      toast.error("Failed to load — admin only.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setScanning(true);
    try {
      const r = await axios.post(`${API}/admin/fraud-alerts/scan`);
      toast.success(`Scan complete — ${r.data.merchants_flagged} flagged`);
      await load();
    } catch { toast.error("Scan failed"); }
    finally { setScanning(false); }
  };

  const resolve = async (id) => {
    await axios.post(`${API}/admin/fraud-alerts/${id}/resolve`);
    toast.success("Alert resolved");
    await load();
  };

  const createWindow = async () => {
    if (!form.merchant_id) { toast.error("Merchant ID required"); return; }
    const now = new Date();
    const end = new Date(now.getTime() + form.hours * 3600 * 1000);
    try {
      await axios.post(`${API}/admin/bonus-windows`, {
        merchant_id: form.merchant_id,
        sponsor_name: form.sponsor_name || null,
        multiplier: Number(form.multiplier),
        title: form.title || `${form.multiplier}× points`,
        starts_at: now.toISOString(),
        ends_at: end.toISOString(),
      });
      toast.success("Bonus window created");
      setForm({ merchant_id: "", sponsor_name: "", multiplier: 2, hours: 6, title: "" });
      await load();
    } catch { toast.error("Create failed"); }
  };

  const deactivate = async (id) => {
    await axios.post(`${API}/admin/bonus-windows/${id}/deactivate`);
    await load();
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto pt-20 text-center text-text-secondary"
                data-testid="merchant-ops-loading">
        <Loader2 className="animate-spin inline-block mr-2" size={18} /> Loading…
      </div>
    );
  }

  const inputCls = "w-full rounded-token-md bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm";

  return (
    <div data-testid="merchant-ops-root" className="max-w-3xl mx-auto space-y-8 pb-24">
      <h1 className="font-display font-bold text-2xl tracking-display-tight">
        Merchant Ops
      </h1>

      {/* Fraud alerts */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display font-bold text-lg flex items-center gap-2">
            <AlertTriangle size={18} className="text-accent-gold" /> Fraud alerts
          </h2>
          <Button variant="secondary" size="sm" onClick={scan} disabled={scanning}
                      data-testid="fraud-scan-btn">
            {scanning ? <Loader2 size={13} className="animate-spin" /> : "Run scan"}
          </Button>
        </div>
        {alerts.length === 0 && (
          <Card className="p-4 text-sm text-text-secondary" data-testid="fraud-empty">
            No open alerts. Merchants with a high coupon show-vs-scan gap will appear here.
          </Card>
        )}
        {alerts.map((a) => (
          <Card key={a.alert_id} className="p-4 flex items-center gap-3"
                    data-testid={`fraud-alert-${a.alert_id}`}>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate">{a.merchant_id}</div>
              <div className="text-xs text-text-secondary">
                {a.shows} shows · {a.redemptions} redeemed ·
                {" "}{Math.round(a.redemption_rate * 100)}% rate · {a.unredeemed} unredeemed
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={() => resolve(a.alert_id)}
                        data-testid={`fraud-resolve-${a.alert_id}`}>
              <Check size={13} /> Resolve
            </Button>
          </Card>
        ))}
      </section>

      {/* Sponsored bonus windows */}
      <section className="space-y-3">
        <h2 className="font-display font-bold text-lg flex items-center gap-2">
          <Zap size={18} className="text-accent-gold" /> Sponsored bonus windows
        </h2>
        <Card className="p-4 space-y-3" data-testid="bonus-create-form">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input className={inputCls} placeholder="Merchant / venue ID"
                        data-testid="bonus-merchant-id" value={form.merchant_id}
                        onChange={(e) => setForm({ ...form, merchant_id: e.target.value })} />
            <input className={inputCls} placeholder="Sponsor name (e.g. The Grill House)"
                        data-testid="bonus-sponsor" value={form.sponsor_name}
                        onChange={(e) => setForm({ ...form, sponsor_name: e.target.value })} />
            <input className={inputCls} placeholder="Title" value={form.title}
                        data-testid="bonus-title"
                        onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <div className="flex gap-3">
              <input className={inputCls} type="number" step="0.5" min="1"
                          placeholder="Multiplier" data-testid="bonus-multiplier"
                          value={form.multiplier}
                          onChange={(e) => setForm({ ...form, multiplier: e.target.value })} />
              <input className={inputCls} type="number" min="1" placeholder="Hours"
                          data-testid="bonus-hours" value={form.hours}
                          onChange={(e) => setForm({ ...form, hours: e.target.value })} />
            </div>
          </div>
          <Button variant="primary" size="sm" onClick={createWindow}
                      data-testid="bonus-create-btn">
            <Plus size={13} /> Create window
          </Button>
        </Card>

        {windows.map((w) => (
          <Card key={w.window_id} className="p-4 flex items-center gap-3"
                    data-testid={`bonus-window-${w.window_id}`}>
            <span className="font-mono text-sm text-accent-gold">{w.multiplier}×</span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate">
                {w.title} {w.sponsor_name ? `· ${w.sponsor_name}` : ""}
              </div>
              <div className="text-xs text-text-secondary truncate">
                {w.merchant_id} · {w.active ? "active" : "inactive"}
              </div>
            </div>
            {w.active && (
              <Button variant="ghost" size="sm" onClick={() => deactivate(w.window_id)}
                          data-testid={`bonus-deactivate-${w.window_id}`}>
                End
              </Button>
            )}
          </Card>
        ))}
      </section>
    </div>
  );
}
