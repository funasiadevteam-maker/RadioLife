// Admin — Ad Pacing panel (Phase COMPANION.1). One screen to tune the
// three audio-ad pacing controls that already have admin endpoints:
//   • Pre-roll hop cooldown   → /api/admin/preroll/hop-cooldown   {seconds}
//   • Mid-roll cadence        → /api/admin/midstream-ad/cadence   {every_n_songs}
//   • Pre-roll chain count    → /api/admin/preroll/chain-count    {count}
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Gauge, Timer, Repeat, Layers, Save } from "lucide-react";
import { API } from "@/AuthContext";

const CFG = { withCredentials: true };

function Control({ icon: Icon, title, desc, value, setValue, min, max, unit, onSave, testid, saving }) {
  return (
    <div className="rounded-2xl bg-slate-900 border border-slate-800 p-5" data-testid={testid}>
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4 text-purple-400" />
        <h3 className="text-sm font-bold text-white">{title}</h3>
      </div>
      <p className="text-xs text-slate-400 mb-4">{desc}</p>
      <div className="flex items-center gap-3">
        <input type="number" min={min} max={max} value={value}
          onChange={(e) => setValue(e.target.value)}
          data-testid={`${testid}-input`}
          className="w-24 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:border-purple-500 outline-none" />
        <span className="text-xs text-slate-500">{unit} · {min}–{max}</span>
        <div className="flex-grow" />
        <button onClick={onSave} disabled={saving}
          data-testid={`${testid}-save`}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-xs font-semibold transition-colors">
          <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default function AdminAdPacing() {
  const [hop, setHop] = useState("90");
  const [cadence, setCadence] = useState("4");
  const [chain, setChain] = useState("1");
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState(null);

  const load = async () => {
    setLoading(true);
    const [h, c, ch] = await Promise.allSettled([
      axios.get(`${API}/admin/preroll/hop-cooldown`, CFG),
      axios.get(`${API}/admin/midstream-ad/cadence`, CFG),
      axios.get(`${API}/admin/preroll/chain-count`, CFG),
    ]);
    if (h.status === "fulfilled") setHop(String(h.value.data.effective_seconds));
    if (c.status === "fulfilled") setCadence(String(c.value.data.every_n_songs));
    if (ch.status === "fulfilled") setChain(String(ch.value.data.effective_count));
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const save = async (key, url, body) => {
    setSavingKey(key);
    try {
      await axios.patch(`${API}${url}`, body, CFG);
      toast.success("Saved");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || "Save failed — check the range.");
    } finally { setSavingKey(null); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white px-4 py-8" data-testid="admin-ad-pacing">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-2 mb-1">
          <Gauge className="w-5 h-5 text-purple-400" />
          <h1 className="text-xl font-black">Ad Pacing</h1>
        </div>
        <p className="text-sm text-slate-400 mb-6">
          Tune how often RadioLife inserts audio ads. Value-before-advertising —
          keep these gentle so listening time (not banner count) drives revenue.
        </p>
        {loading ? (
          <div className="text-slate-400 text-sm">Loading current settings…</div>
        ) : (
          <div className="space-y-4">
            <Control icon={Timer} title="Pre-roll hop cooldown"
              desc="After a pre-roll plays, no further pre-roll fires for this long — regardless of station — so rapid station-hopping never re-triggers one. 0 disables."
              value={hop} setValue={setHop} min={0} max={600} unit="seconds"
              testid="pacing-hop"
              saving={savingKey === "hop"}
              onSave={() => save("hop", "/admin/preroll/hop-cooldown", { seconds: Number(hop) })} />
            <Control icon={Repeat} title="Mid-roll cadence"
              desc="Play one mid-stream audio ad every N songs during RadioLife-controlled audio (Free listeners only)."
              value={cadence} setValue={setCadence} min={2} max={8} unit="songs"
              testid="pacing-cadence"
              saving={savingKey === "cadence"}
              onSave={() => save("cadence", "/admin/midstream-ad/cadence", { every_n_songs: Number(cadence) })} />
            <Control icon={Layers} title="Pre-roll chain count"
              desc="How many sequential pre-roll ads to play on a single station start. 1 = a single ad (recommended)."
              value={chain} setValue={setChain} min={1} max={5} unit="ads"
              testid="pacing-chain"
              saving={savingKey === "chain"}
              onSave={() => save("chain", "/admin/preroll/chain-count", { count: Number(chain) })} />
          </div>
        )}
      </div>
    </div>
  );
}
