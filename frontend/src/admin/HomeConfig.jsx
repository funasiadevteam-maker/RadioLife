// Admin — FUUSIC Home configuration. Reorder ecosystem pillars (Social-first
// default) and toggle / rename Home sections. A/B ready, no code change.
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { LayoutGrid, Loader2, Save, RotateCcw, ArrowUp, ArrowDown } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { Card, Button } from "@/shell/primitives";

const SECTION_ORDER = [
  "fuusic_world", "whats_happening", "continue",
  "for_you", "live_now", "together", "premium",
];
const SECTION_HINT = {
  fuusic_world: "Ecosystem pillar grid (Social first)",
  whats_happening: "Live friend / social activity bridge",
  continue: "Resume audio / rewards / dining",
  for_you: "Personalized recommendations rail",
  live_now: "Live across FUUSIC rail",
  together: "Do Something Together actions",
  premium: "Premium upsell banner",
};

export default function HomeConfig() {
  const [order, setOrder] = useState([]);
  const [sections, setSections] = useState({});
  const [pillars, setPillars] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const apply = (d) => {
    setOrder(d.pillar_order || []);
    setSections(d.sections || {});
    setPillars(d.pillars || {});
  };

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/home-config`, { withCredentials: true });
      apply(r.data || {});
    } catch {
      toast.error("Failed to load — admin only.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const move = (idx, dir) => {
    setOrder((prev) => {
      const next = [...prev];
      const j = idx + dir;
      if (j < 0 || j >= next.length) return prev;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  const setSection = (key, patch) =>
    setSections((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));

  const save = async () => {
    setSaving(true);
    try {
      const r = await axios.put(`${API}/admin/home-config`,
        { pillar_order: order, sections }, { withCredentials: true });
      apply(r.data || {});
      toast.success("Home layout saved");
    } catch {
      toast.error("Save failed");
    } finally { setSaving(false); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24" data-testid="home-config-loading">
        <Loader2 className="w-6 h-6 animate-spin text-orange-500" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8" data-testid="home-config-root">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-orange-500/15 flex items-center justify-center">
            <LayoutGrid className="w-5 h-5 text-orange-500" />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight">FUUSIC Home Layout</h1>
            <p className="text-sm text-neutral-500">Reorder ecosystem pillars and toggle Home sections (New Look V2).</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} data-testid="home-config-reload">
            <RotateCcw className="w-4 h-4 mr-1" /> Reload
          </Button>
          <Button size="sm" onClick={save} disabled={saving} data-testid="home-config-save">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Save className="w-4 h-4 mr-1" /> Save</>}
          </Button>
        </div>
      </div>

      <Card className="p-4 mb-5">
        <div className="text-xs uppercase tracking-wide text-neutral-500 font-bold mb-3">Pillar order — “Your FUUSIC World”</div>
        <div className="space-y-2" data-testid="home-config-pillars">
          {order.map((key, idx) => (
            <div key={key} className="flex items-center gap-3 border border-neutral-200/60 rounded-lg px-3 py-2"
              data-testid={`pillar-row-${key}`}>
              <span className="w-6 text-center font-black text-neutral-400">{idx + 1}</span>
              <span className="flex-1 font-semibold">
                {pillars[key]?.label || key}
                {pillars[key]?.featured && <span className="ml-2 text-[10px] font-black px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">FEATURED</span>}
              </span>
              <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0}
                data-testid={`pillar-up-${key}`}
                className="w-8 h-8 rounded-md grid place-items-center hover:bg-neutral-100 disabled:opacity-30">
                <ArrowUp className="w-4 h-4" />
              </button>
              <button type="button" onClick={() => move(idx, 1)} disabled={idx === order.length - 1}
                data-testid={`pillar-down-${key}`}
                className="w-8 h-8 rounded-md grid place-items-center hover:bg-neutral-100 disabled:opacity-30">
                <ArrowDown className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-4">
        <div className="text-xs uppercase tracking-wide text-neutral-500 font-bold mb-3">Sections — visibility & title</div>
        <div className="space-y-2" data-testid="home-config-sections">
          {SECTION_ORDER.filter((k) => sections[k]).map((key) => (
            <div key={key} className="flex items-center gap-3 border border-neutral-200/60 rounded-lg px-3 py-2"
              data-testid={`section-row-${key}`}>
              <input type="checkbox" checked={!!sections[key]?.visible}
                onChange={(e) => setSection(key, { visible: e.target.checked })}
                data-testid={`section-visible-${key}`} />
              <div className="min-w-0 flex-1">
                <input type="text" value={sections[key]?.title || ""}
                  onChange={(e) => setSection(key, { title: e.target.value })}
                  data-testid={`section-title-${key}`}
                  className="w-full border border-neutral-300 rounded-md px-2 py-1 text-sm font-semibold" />
                <div className="text-[11px] text-neutral-400 mt-0.5">{SECTION_HINT[key]}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <p className="text-xs text-neutral-400 mt-3">
        Changes apply to the New Look V2 Home for all users. Default is Social-first.
      </p>
    </div>
  );
}
