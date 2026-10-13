// Settings → Personalize Home. Each user picks which features show, drags to
// reorder them, sees a live preview of their Home, discovers features they've
// turned off, and can reset to smart defaults for their city.
// Backed by the shared feature-prefs store (/api/social/features).
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Sparkles, Check, Loader2, Lock, ArrowLeft, Users, Headphones, Radio,
  ShoppingBag, Gamepad2, Utensils, Coins, ChevronUp, ChevronDown, X, Plus,
  GripVertical, RotateCcw, MapPin, Eye, ChevronRight,
} from "lucide-react";
import { useFeaturePrefs } from "@/store/useFeaturePrefs";

const ICONS = {
  users: Users, headphones: Headphones, radio: Radio, "shopping-bag": ShoppingBag,
  "gamepad-2": Gamepad2, utensils: Utensils, coins: Coins, sparkles: Sparkles,
};

// Brand gradients per feature — mirrors the FUUSIC World tiles on Home.
const GRADS = {
  social: ["#14b8a6", "#22c55e"], listen: ["#a855f7", "#ec4899"],
  live: ["#f43f5e", "#a855f7"], shop: ["#ec4899", "#f59e0b"],
  play: ["#8b5cf6", "#6366f1"], dining: ["#fb923c", "#ec4899"],
  earn: ["#f59e0b", "#f5c563"], explore: ["#06b6d4", "#3b82f6"],
};
const gradOf = (k) => `linear-gradient(135deg, ${(GRADS[k] || ["#22d3ee", "#a855f7"]).join(",")})`;

export default function PersonalizeHome() {
  const navigate = useNavigate();
  const bootstrap = useFeaturePrefs((s) => s.bootstrap);
  const save = useFeaturePrefs((s) => s.save);
  const catalog = useFeaturePrefs((s) => s.catalog);
  const mandatory = useFeaturePrefs((s) => s.mandatory);
  const enabled = useFeaturePrefs((s) => s.enabled);
  const defaults = useFeaturePrefs((s) => s.defaults);
  const homeCity = useFeaturePrefs((s) => s.homeCity);
  const loaded = useFeaturePrefs((s) => s.loaded);

  const [sel, setSel] = useState(null);  // ordered list of enabled keys
  const [busy, setBusy] = useState(false);
  const [dragKey, setDragKey] = useState(null);

  useEffect(() => { bootstrap(); }, [bootstrap]);
  useEffect(() => {
    if (loaded && sel === null) {
      setSel(enabled && enabled.length ? [...enabled] : catalog.map((f) => f.key));
    }
  }, [loaded, enabled, catalog, sel]);

  const byKey = useMemo(
    () => Object.fromEntries(catalog.map((f) => [f.key, f])), [catalog]);
  const isMand = (k) => mandatory.includes(k);

  // Features not currently selected → the "Discover more" shelf.
  const available = useMemo(
    () => catalog.filter((f) => !(sel || []).includes(f.key)), [catalog, sel]);

  const addFeature = (k) => setSel((s) => (s.includes(k) ? s : [...s, k]));
  const removeFeature = (k) => { if (!isMand(k)) setSel((s) => s.filter((x) => x !== k)); };

  const move = (k, dir) => setSel((s) => {
    const i = s.indexOf(k);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= s.length) return s;
    const n = [...s];
    [n[i], n[j]] = [n[j], n[i]];
    return n;
  });

  const onDrop = (overKey) => {
    if (!dragKey || dragKey === overKey) { setDragKey(null); return; }
    setSel((s) => {
      const n = s.filter((x) => x !== dragKey);
      const at = n.indexOf(overKey);
      n.splice(at < 0 ? n.length : at, 0, dragKey);
      return n;
    });
    setDragKey(null);
  };

  const resetToDefaults = () => {
    if (defaults && defaults.length) {
      setSel([...defaults]);
      toast.success(homeCity ? `Reset to ${homeCity} defaults.` : "Reset to recommended defaults.");
    }
  };

  const onSave = async () => {
    setBusy(true);
    const ordered = [...(sel || [])];
    mandatory.forEach((m) => { if (!ordered.includes(m)) ordered.unshift(m); });
    await save(ordered);
    setBusy(false);
    toast.success("Home updated — showing just what you picked, in your order.");
  };

  if (!loaded || sel === null) {
    return (
      <div className="flex items-center justify-center py-24" data-testid="personalize-home-loading">
        <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-1 py-2" data-testid="personalize-home-root">
      <button type="button" onClick={() => navigate(-1)}
        data-testid="personalize-home-back"
        className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-white mb-4">
        <ArrowLeft size={16} /> Back
      </button>

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="flex items-center gap-2 text-cyan-300 text-[10px] font-black uppercase tracking-widest">
            <Sparkles size={13} /> Personalize Home
          </div>
          <h1 className="mt-1 text-2xl font-black text-white">Your features</h1>
          <p className="text-sm text-white/50 mt-1 max-w-lg">
            Turn features on or off and drag to set their order. Your Home and menu
            update to match — simplest first.
          </p>
        </div>
        {defaults && defaults.length > 0 && (
          <button type="button" onClick={resetToDefaults}
            data-testid="personalize-reset-defaults"
            className="inline-flex items-center gap-1.5 text-xs font-bold text-white/70 hover:text-white border border-white/15 hover:border-white/35 rounded-full px-3 h-9">
            <RotateCcw size={13} />
            Reset{homeCity ? ` to ${homeCity}` : " to defaults"}
          </button>
        )}
      </div>

      {homeCity && (
        <div className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-semibold text-cyan-200/80 bg-cyan-400/[0.08] border border-cyan-400/20 rounded-full px-3 py-1"
          data-testid="personalize-city-hint">
          <MapPin size={12} /> Smart defaults tuned for {homeCity}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mt-5">
        {/* ── Feature manager (reorder + toggle) ── */}
        <div className="lg:col-span-3" data-testid="personalize-manager">
          <div className="text-[11px] font-black uppercase tracking-widest text-white/40 mb-2">
            On your Home · drag to reorder
          </div>
          <div className="space-y-2" data-testid="personalize-selected-list">
            {sel.map((k, idx) => {
              const f = byKey[k];
              if (!f) return null;
              const Icon = ICONS[f.icon] || Sparkles;
              return (
                <div key={k}
                  draggable
                  onDragStart={() => setDragKey(k)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => onDrop(k)}
                  onDragEnd={() => setDragKey(null)}
                  data-testid={`personalize-feature-${k}`}
                  className={`flex items-center gap-3 rounded-2xl p-3 border transition ${
                    dragKey === k ? "border-cyan-400/70 bg-cyan-400/[0.12] opacity-70"
                      : "border-cyan-400/40 bg-cyan-400/[0.06]"}`}>
                  <span className="cursor-grab active:cursor-grabbing text-white/30 hover:text-white/60 touch-none">
                    <GripVertical size={16} />
                  </span>
                  <span className="w-9 h-9 rounded-xl grid place-items-center shrink-0"
                    style={{ background: gradOf(k) }}>
                    <Icon size={16} color="#fff" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="font-black text-white text-sm">{f.label}</span>
                      {isMand(k) && <Lock size={11} className="text-slate-500" />}
                    </span>
                    <span className="block text-[11px] text-white/40 truncate">{f.desc}</span>
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <button type="button" onClick={() => move(k, -1)} disabled={idx === 0}
                      data-testid={`personalize-move-up-${k}`}
                      className="w-7 h-7 grid place-items-center rounded-lg border border-white/10 text-white/60 hover:text-white hover:border-white/30 disabled:opacity-25">
                      <ChevronUp size={14} />
                    </button>
                    <button type="button" onClick={() => move(k, 1)} disabled={idx === sel.length - 1}
                      data-testid={`personalize-move-down-${k}`}
                      className="w-7 h-7 grid place-items-center rounded-lg border border-white/10 text-white/60 hover:text-white hover:border-white/30 disabled:opacity-25">
                      <ChevronDown size={14} />
                    </button>
                    {!isMand(k) && (
                      <button type="button" onClick={() => removeFeature(k)}
                        data-testid={`personalize-remove-${k}`}
                        className="w-7 h-7 grid place-items-center rounded-lg border border-white/10 text-white/50 hover:text-rose-300 hover:border-rose-400/40">
                        <X size={14} />
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>

          {/* ── Feature discovery ── */}
          {available.length > 0 && (
            <div className="mt-6" data-testid="personalize-discover">
              <div className="text-[11px] font-black uppercase tracking-widest text-white/40 mb-2">
                Discover more
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {available.map((f) => {
                  const Icon = ICONS[f.icon] || Sparkles;
                  return (
                    <button key={f.key} type="button" onClick={() => addFeature(f.key)}
                      data-testid={`personalize-add-${f.key}`}
                      className="flex items-center gap-3 text-left rounded-2xl p-3 border border-white/10 bg-white/[0.02] hover:border-white/25 hover:bg-white/[0.05] transition">
                      <span className="w-9 h-9 rounded-xl grid place-items-center shrink-0 opacity-80"
                        style={{ background: gradOf(f.key) }}>
                        <Icon size={16} color="#fff" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block font-black text-white text-sm">{f.label}</span>
                        <span className="block text-[11px] text-white/40 truncate">{f.desc}</span>
                      </span>
                      <span className="shrink-0 inline-flex items-center gap-1 text-[11px] font-black text-cyan-300">
                        <Plus size={13} /> Add
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* ── Live preview ── */}
        <div className="lg:col-span-2" data-testid="personalize-preview">
          <div className="lg:sticky lg:top-4">
            <div className="flex items-center gap-1.5 text-[11px] font-black uppercase tracking-widest text-white/40 mb-2">
              <Eye size={13} /> Live preview
            </div>
            <div className="rounded-3xl border border-white/10 p-4"
              style={{ background: "linear-gradient(180deg,#0b1220,#0a0f1c)" }}>
              <div className="text-sm font-black text-white mb-0.5">Your FUUSIC World</div>
              <div className="text-[11px] text-white/40 mb-3">Everything you love, your order</div>
              <div className="grid grid-cols-2 gap-2.5">
                {sel.map((k) => {
                  const f = byKey[k];
                  if (!f) return null;
                  const Icon = ICONS[f.icon] || Sparkles;
                  return (
                    <div key={k} data-testid={`personalize-preview-tile-${k}`}
                      className="relative overflow-hidden rounded-2xl p-3 border border-white/10 bg-white/[0.03]">
                      <div className="absolute -right-6 -top-6 w-20 h-20 rounded-full"
                        style={{ background: (GRADS[k] || ["#a855f7"])[0], opacity: 0.18, filter: "blur(18px)" }} />
                      <div className="relative z-10">
                        <span className="w-8 h-8 rounded-xl grid place-items-center" style={{ background: gradOf(k) }}>
                          <Icon size={15} color="#fff" />
                        </span>
                        <div className="mt-2 text-[13px] font-black text-white">{f.label}</div>
                        <div className="mt-0.5 inline-flex items-center gap-0.5 text-[10px] font-bold text-white/55">
                          Open <ChevronRight size={11} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      <button type="button" onClick={onSave} disabled={busy}
        data-testid="personalize-home-save"
        className="mt-6 w-full h-12 rounded-full font-black text-slate-950 disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#22d3ee,#a855f7)" }}>
        {busy ? <Loader2 className="animate-spin mx-auto" size={18} /> : "Save my Home"}
      </button>
    </div>
  );
}
