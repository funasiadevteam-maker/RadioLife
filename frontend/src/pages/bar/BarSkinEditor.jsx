// Bar owner's wheel editor — pick accent colours, a logo, and signature-drink
// prizes. Saves via PUT /api/bar-games/{id}/skin (owner/admin only).
import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Plus, Trash2, Loader2, Palette } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function BarSkinEditor({ businessId, config, onClose, onSaved }) {
  const theme = config?.theme || {};
  const [accent, setAccent] = useState(theme.accent || "#22d3ee");
  const [accent2, setAccent2] = useState(theme.accent2 || "#f472b6");
  const [logo, setLogo] = useState(theme.logo_url || "");
  const [segments, setSegments] = useState(
    (config?.segments || []).map((s) => ({ label: s.label, emoji: s.emoji, win: s.win, weight: s.weight || 8 }))
  );
  const [busy, setBusy] = useState(false);

  const update = (i, patch) => setSegments((list) => list.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const addSeg = () => setSegments((l) => [...l, { label: "New prize", emoji: "🍹", win: true, weight: 8 }]);
  const delSeg = (i) => setSegments((l) => l.filter((_, j) => j !== i));

  const save = async () => {
    if (segments.length < 3) { toast.info("Add at least 3 wheel segments."); return; }
    setBusy(true);
    try {
      const { data } = await axios.put(`${API}/bar-games/${businessId}/skin`,
        { accent, accent2, logo_url: logo || null, segments }, { withCredentials: true });
      onSaved(data.config);
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code === "not_bar_owner" ? "Only the bar owner can edit this." : "Couldn’t save the wheel.");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-[100] grid place-items-center p-4 bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="bar-skin-editor">
      <div className="w-full max-w-md rounded-3xl border border-white/10 p-5 max-h-[90vh] overflow-auto"
           style={{ background: "linear-gradient(135deg,#160f2e,#241041)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-white font-black text-lg"><Palette size={18} /> Customize your wheel</div>
          <button onClick={onClose} className="text-slate-400" data-testid="bar-skin-close"><X size={20} /></button>
        </div>

        <div className="flex gap-4 mb-4">
          <label className="flex-1 text-xs text-slate-300 font-bold">Accent
            <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} data-testid="skin-accent"
                   className="mt-1 w-full h-10 rounded-lg bg-transparent border border-white/10" />
          </label>
          <label className="flex-1 text-xs text-slate-300 font-bold">Accent 2
            <input type="color" value={accent2} onChange={(e) => setAccent2(e.target.value)} data-testid="skin-accent2"
                   className="mt-1 w-full h-10 rounded-lg bg-transparent border border-white/10" />
          </label>
        </div>

        <label className="block text-xs text-slate-300 font-bold mb-4">Logo URL (optional)
          <input value={logo} onChange={(e) => setLogo(e.target.value)} placeholder="https://…" data-testid="skin-logo"
                 className="mt-1 w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm text-white outline-none" />
        </label>

        <div className="text-xs text-slate-300 font-bold mb-2">Prizes ({segments.length})</div>
        <div className="space-y-2">
          {segments.map((s, i) => (
            <div key={i} className="flex items-center gap-2 rounded-xl bg-white/[0.04] border border-white/10 p-2" data-testid={`skin-seg-${i}`}>
              <input value={s.emoji} onChange={(e) => update(i, { emoji: e.target.value })} maxLength={4}
                     className="w-10 text-center rounded-lg bg-white/[0.06] py-2 text-sm" />
              <input value={s.label} onChange={(e) => update(i, { label: e.target.value })}
                     className="flex-1 min-w-0 rounded-lg bg-white/[0.06] px-2 py-2 text-sm text-white outline-none" />
              <button onClick={() => update(i, { win: !s.win })}
                      className="text-[10px] font-black px-2 py-1.5 rounded-lg"
                      style={{ background: s.win ? "rgba(52,211,153,0.2)" : "rgba(255,255,255,0.08)", color: s.win ? "#34d399" : "#94a3b8" }}>
                {s.win ? "WIN" : "LOSE"}
              </button>
              <button onClick={() => delSeg(i)} className="text-slate-400 p-1"><Trash2 size={15} /></button>
            </div>
          ))}
        </div>
        <button onClick={addSeg} data-testid="skin-add-seg"
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-white h-9 px-3 rounded-full bg-white/10">
          <Plus size={13} /> Add prize
        </button>

        <button onClick={save} disabled={busy} data-testid="bar-skin-save"
                className="mt-4 w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2"
                style={{ background: `linear-gradient(135deg,${accent},${accent2})` }}>
          {busy ? <Loader2 size={16} className="animate-spin" /> : "Save wheel"}
        </button>
      </div>
    </div>
  );
}
