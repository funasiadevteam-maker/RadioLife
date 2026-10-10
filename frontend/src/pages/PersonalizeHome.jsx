// Settings → Personalize Home. Each user turns features on/off; Home + the nav
// update to show only what they keep. Backed by the shared feature-prefs store.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Sparkles, Check, Loader2, Lock, ArrowLeft, Users, Headphones, Radio,
  ShoppingBag, Gamepad2, Utensils, Coins,
} from "lucide-react";
import { useFeaturePrefs } from "@/store/useFeaturePrefs";

const ICONS = {
  users: Users, headphones: Headphones, radio: Radio, "shopping-bag": ShoppingBag,
  "gamepad-2": Gamepad2, utensils: Utensils, coins: Coins, sparkles: Sparkles,
};

export default function PersonalizeHome() {
  const navigate = useNavigate();
  const bootstrap = useFeaturePrefs((s) => s.bootstrap);
  const save = useFeaturePrefs((s) => s.save);
  const catalog = useFeaturePrefs((s) => s.catalog);
  const mandatory = useFeaturePrefs((s) => s.mandatory);
  const enabled = useFeaturePrefs((s) => s.enabled);
  const loaded = useFeaturePrefs((s) => s.loaded);

  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { bootstrap(); }, [bootstrap]);
  useEffect(() => {
    if (loaded && sel === null) {
      setSel(enabled && enabled.length ? [...enabled] : catalog.map((f) => f.key));
    }
  }, [loaded, enabled, catalog, sel]);

  const isMand = (k) => mandatory.includes(k);
  const toggle = (k) => {
    if (isMand(k)) return;
    setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));
  };

  const onSave = async () => {
    setBusy(true);
    await save(Array.from(new Set([...mandatory, ...(sel || [])])));
    setBusy(false);
    toast.success("Home updated — showing just what you picked.");
  };

  if (!loaded || sel === null) {
    return (
      <div className="flex items-center justify-center py-24" data-testid="personalize-home-loading">
        <Loader2 className="w-6 h-6 animate-spin text-cyan-400" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-1 py-2" data-testid="personalize-home-root">
      <button type="button" onClick={() => navigate(-1)}
        data-testid="personalize-home-back"
        className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-white mb-4">
        <ArrowLeft size={16} /> Back
      </button>

      <div className="flex items-center gap-2 text-cyan-300 text-[10px] font-black uppercase tracking-widest">
        <Sparkles size={13} /> Personalize Home
      </div>
      <h1 className="mt-1 text-2xl font-black text-white">Your features</h1>
      <p className="text-sm text-white/50 mt-1 mb-5">
        Show only what you care about. Turn features on or off anytime — they'll appear on Home and in the menu.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {catalog.map((f) => {
          const on = sel.includes(f.key) || isMand(f.key);
          const Icon = ICONS[f.icon] || Sparkles;
          return (
            <button key={f.key} type="button" onClick={() => toggle(f.key)}
              data-testid={`personalize-feature-${f.key}`}
              aria-pressed={on}
              className={`relative flex items-start gap-3 text-left rounded-2xl p-3.5 border transition ${
                on ? "border-cyan-400/60 bg-cyan-400/[0.08]" : "border-white/10 bg-white/[0.03] hover:border-white/25"}`}>
              <span className="w-10 h-10 rounded-xl grid place-items-center shrink-0"
                style={{ background: on ? "linear-gradient(135deg,#22d3ee,#a855f7)" : "rgba(255,255,255,0.06)" }}>
                <Icon size={18} color={on ? "#fff" : "#9aa6c8"} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="font-black text-white text-sm">{f.label}</span>
                  {isMand(f.key) && <Lock size={11} className="text-slate-500" />}
                </span>
                <span className="block text-[12px] text-white/45 mt-0.5 leading-snug">{f.desc}</span>
              </span>
              <span className={`shrink-0 w-6 h-6 rounded-full grid place-items-center border ${
                on ? "bg-cyan-400 border-cyan-400" : "border-white/25"}`}>
                {on && <Check size={14} className="text-slate-950" />}
              </span>
            </button>
          );
        })}
      </div>

      <button type="button" onClick={onSave} disabled={busy}
        data-testid="personalize-home-save"
        className="mt-5 w-full h-12 rounded-full font-black text-slate-950 disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#22d3ee,#a855f7)" }}>
        {busy ? <Loader2 className="animate-spin mx-auto" size={18} /> : "Save my Home"}
      </button>
    </div>
  );
}
