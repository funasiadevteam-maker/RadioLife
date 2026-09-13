// Admin · Radio Settings → Playback & Compliance → Skip Rules.
// Tune Free/Premium skips per rolling hour without code. Backend fallback
// stays Free=1 / Premium=6 / 3600s. No user-facing "unlimited" option.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { SkipForward, Save, Loader2, Info } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function AdminSkipRules() {
  const [free, setFree] = useState(1);
  const [premium, setPremium] = useState(6);
  const [windowMin, setWindowMin] = useState(60);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/admin/radio/skip-rules`);
        if (cancel) return;
        setFree(data.free ?? 1);
        setPremium(data.premium ?? 6);
        setWindowMin(Math.round((data.window_sec ?? 3600) / 60));
      } catch (_) { /* keep defaults */ }
      finally { if (!cancel) setLoading(false); }
    })();
    return () => { cancel = true; };
  }, []);

  async function save() {
    setSaving(true);
    setMsg(null);
    try {
      const { data } = await axios.put(`${API}/admin/radio/skip-rules`, {
        free: Number(free), premium: Number(premium), window_sec: Number(windowMin) * 60,
      });
      setFree(data.free); setPremium(data.premium);
      setWindowMin(Math.round(data.window_sec / 60));
      setMsg({ kind: "ok", text: "Skip rules saved." });
    } catch (_) {
      setMsg({ kind: "err", text: "Save failed. Check your admin access." });
    } finally { setSaving(false); }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 px-6 py-8" data-testid="admin-skip-rules">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl bg-purple-500/15 grid place-items-center">
            <SkipForward className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <div className="text-[11px] font-mono uppercase tracking-widest text-slate-500">
              Radio Settings · Playback &amp; Compliance
            </div>
            <h1 className="text-xl font-bold">Skip Rules</h1>
          </div>
        </div>
        <p className="text-sm text-slate-400 mb-6">
          Rolling-window skip allowance per tier. The backend is authoritative;
          the rolling hour never resets on the clock.
        </p>

        {loading ? (
          <Loader2 className="w-6 h-6 animate-spin text-purple-400 mx-auto my-10" />
        ) : (
          <div className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <Field label="Free skips per window" testId="admin-skip-free"
              value={free} onChange={setFree} min={0} max={20} hint="Default 1" />
            <Field label="Premium skips per window" testId="admin-skip-premium"
              value={premium} onChange={setPremium} min={0} max={50} hint="Default 6" />
            <Field label="Rolling window (minutes)" testId="admin-skip-window"
              value={windowMin} onChange={setWindowMin} min={1} max={1440} hint="Default 60" />

            <div className="flex items-start gap-2 text-[12px] text-slate-500 rounded-lg bg-slate-950/60 border border-slate-800 p-3">
              <Info className="w-4 h-4 mt-0.5 shrink-0 text-slate-400" />
              <span>
                Premium is a higher allowance, not unlimited. Preview: Free listeners get
                <b className="text-slate-300"> {free} skip{Number(free) === 1 ? "" : "s"}</b> and Premium get
                <b className="text-slate-300"> {premium} skips</b> every <b className="text-slate-300">{windowMin} min</b>.
              </span>
            </div>

            {msg && (
              <div data-testid="admin-skip-msg"
                className={`text-sm ${msg.kind === "ok" ? "text-emerald-400" : "text-rose-400"}`}>
                {msg.text}
              </div>
            )}

            <button type="button" onClick={save} disabled={saving}
              data-testid="admin-skip-save"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-purple-500 text-white
                                font-semibold hover:bg-purple-400 transition disabled:opacity-50">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save skip rules
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, testId, value, onChange, min, max, hint }) {
  return (
    <label className="block">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-semibold">{label}</span>
        <span className="text-[11px] text-slate-500">{hint}</span>
      </div>
      <input type="number" min={min} max={max} value={value}
        data-testid={testId}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-11 px-3 rounded-lg bg-slate-950 border border-slate-700 text-slate-100
                          focus:outline-none focus:border-purple-500/60" />
    </label>
  );
}
