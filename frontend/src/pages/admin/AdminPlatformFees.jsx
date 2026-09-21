// Super-admin: platform commission config. Global default (fallback for
// everyone) + per-category overrides (category takes precedence). Basis points
// stored server-side; shown/edited as percentages here.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Loader2, Plus, Trash2, Percent, Save, ArrowLeft, ShieldCheck } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const KNOWN = ["merchant", "tarot", "astrology", "numerology", "spiritual",
  "licensed_sleep", "licensed_mental_health"];

export default function AdminPlatformFees() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [defaultPct, setDefaultPct] = useState("15");
  const [requireOnboard, setRequireOnboard] = useState(false);
  const [rows, setRows] = useState([]); // {key, pct}
  const [newKey, setNewKey] = useState("");

  useEffect(() => {
    axios.get(`${API}/admin/platform-fees`, { withCredentials: true })
      .then(({ data }) => {
        setDefaultPct(String(data.default_pct ?? 15));
        setRequireOnboard(!!data.require_payout_onboarding);
        setRows(Object.entries(data.category_bps || {}).map(([key, bps]) => ({ key, pct: String(bps / 100) })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const addRow = (key) => {
    const k = (key || newKey).trim().toLowerCase().replace(/\s+/g, "_");
    if (!k || rows.some((r) => r.key === k)) return;
    setRows((r) => [...r, { key: k, pct: "10" }]);
    setNewKey("");
  };
  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      const category_bps = {};
      rows.forEach((r) => { const p = parseFloat(r.pct); if (!isNaN(p)) category_bps[r.key] = Math.round(p * 100); });
      await axios.put(`${API}/admin/platform-fees`, {
        default_bps: Math.round(parseFloat(defaultPct || "0") * 100),
        category_bps, require_payout_onboarding: requireOnboard,
      }, { withCredentials: true });
      setSaved(true); setTimeout(() => setSaved(false), 2500);
    } catch (_) { alert("Save failed"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="min-h-screen grid place-items-center bg-slate-950"><Loader2 className="animate-spin text-slate-400" /></div>;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100" data-testid="admin-platform-fees">
      <div className="max-w-2xl mx-auto px-5 py-8">
        <Link to="/admin" className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-5"><ArrowLeft size={15} /> Admin</Link>
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-violet-500/20 grid place-items-center"><Percent size={18} className="text-violet-300" /></div>
          <h1 className="text-2xl font-black">Platform Fees</h1>
        </div>
        <p className="text-sm text-slate-400 mb-6">Commission taken from every vendor transaction before payout. A category fee overrides the default.</p>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <label className="text-xs font-bold uppercase tracking-widest text-slate-500">Global default fee</label>
          <div className="flex items-center gap-2 mt-2">
            <input type="number" step="0.5" min="0" max="50" value={defaultPct} onChange={(e) => setDefaultPct(e.target.value)}
              data-testid="fee-default-input" className="w-28 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-lg font-black" />
            <span className="text-slate-400 font-bold">%</span>
            <span className="text-xs text-slate-500 ml-2">applies when no category fee is set</span>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 mt-4">
          <div className="flex items-center justify-between mb-3">
            <label className="text-xs font-bold uppercase tracking-widest text-slate-500">Category overrides</label>
          </div>
          <div className="space-y-2" data-testid="fee-category-rows">
            {rows.length === 0 && <div className="text-xs italic text-slate-500">No category overrides — everyone pays the default.</div>}
            {rows.map((r, i) => (
              <div key={r.key} className="flex items-center gap-2" data-testid={`fee-row-${r.key}`}>
                <span className="flex-1 text-sm font-semibold">{r.key.replace(/_/g, " ")}</span>
                <input type="number" step="0.5" min="0" max="50" value={r.pct}
                  onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, pct: e.target.value } : x))}
                  data-testid={`fee-row-input-${r.key}`} className="w-20 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-sm font-black text-right" />
                <span className="text-slate-500 text-sm">%</span>
                <button onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} className="text-slate-500 hover:text-red-400 p-1" data-testid={`fee-row-remove-${r.key}`}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-4 flex-wrap">
            {KNOWN.filter((k) => !rows.some((r) => r.key === k)).map((k) => (
              <button key={k} onClick={() => addRow(k)} data-testid={`fee-add-known-${k}`}
                className="text-xs px-2.5 py-1.5 rounded-full bg-slate-800 hover:bg-slate-700 inline-flex items-center gap-1"><Plus size={11} /> {k.replace(/_/g, " ")}</button>
            ))}
          </div>
        </div>

        <label className="rounded-2xl border border-slate-800 bg-slate-900 p-4 mt-4 flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={requireOnboard} onChange={(e) => setRequireOnboard(e.target.checked)} className="accent-violet-500 w-4 h-4" data-testid="fee-require-onboarding" />
          <div>
            <div className="text-sm font-bold flex items-center gap-1.5"><ShieldCheck size={14} className="text-violet-300" /> Require payout onboarding before selling</div>
            <div className="text-xs text-slate-500">Vendors can't take payments until their Stripe payout account is active.</div>
          </div>
        </label>

        <button onClick={save} disabled={saving} data-testid="fee-save-btn"
          className="mt-6 w-full h-12 rounded-full font-black text-white disabled:opacity-50 inline-flex items-center justify-center gap-2"
          style={{ background: "linear-gradient(135deg,#8b5cf6,#6366f1)" }}>
          {saving ? <Loader2 className="animate-spin" size={16} /> : saved ? "Saved ✓" : <><Save size={16} /> Save fees</>}
        </button>
      </div>
    </div>
  );
}
