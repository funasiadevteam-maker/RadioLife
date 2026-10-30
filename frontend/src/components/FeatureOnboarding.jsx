// First-run "Build your FUUSIC" step — pick which features power your Home.
// Opens ONCE for new users right AFTER the interests step (sequenced via the
// `bigfm:interests:done` event so the two modals never overlap).
// Reuses the shared feature-prefs store (/api/social/features).
import { useEffect, useState } from "react";
import axios from "axios";
import {
  Sparkles, Check, Loader2, Lock, Users, Headphones, Radio,
  ShoppingBag, Gamepad2, Utensils, Coins, Sun, Moon, Monitor,
} from "lucide-react";
import { useFeaturePrefs } from "@/store/useFeaturePrefs";
import { useTheme } from "@/theme/useTheme";
import AccentSwatches from "@/theme/AccentSwatches";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const APPEARANCE = [
  { k: "light", label: "Light", desc: "Bright & clean", Icon: Sun },
  { k: "dark", label: "Dark", desc: "Easy on the eyes", Icon: Moon },
  { k: "system", label: "Match device", desc: "Follow your device", Icon: Monitor },
];

const ICONS = {
  users: Users, headphones: Headphones, radio: Radio, "shopping-bag": ShoppingBag,
  "gamepad-2": Gamepad2, utensils: Utensils, coins: Coins, sparkles: Sparkles,
};

export default function FeatureOnboarding() {
  const bootstrap = useFeaturePrefs((s) => s.bootstrap);
  const save = useFeaturePrefs((s) => s.save);
  const catalog = useFeaturePrefs((s) => s.catalog);
  const mandatory = useFeaturePrefs((s) => s.mandatory);
  const enabled = useFeaturePrefs((s) => s.enabled);
  const needsOnboarding = useFeaturePrefs((s) => s.needsOnboarding);
  const loaded = useFeaturePrefs((s) => s.loaded);

  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  const [gated, setGated] = useState(false);
  const { setMode } = useTheme();
  const [appr, setAppr] = useState("system");

  const pickAppr = (k) => { setAppr(k); setMode(k); };

  useEffect(() => { bootstrap(); }, [bootstrap]);

  // Show only after the interests step is done (sequenced).
  useEffect(() => {
    if (!loaded || gated) return;
    setGated(true);
    if (!needsOnboarding) return;
    axios.get(`${API}/social/interests`, { withCredentials: true })
      .then((r) => {
        if (r.data?.needs_onboarding) {
          window.addEventListener("bigfm:interests:done",
            () => setOpen(true), { once: true });
        } else {
          setOpen(true);
        }
      })
      .catch(() => setOpen(true));
  }, [loaded, needsOnboarding, gated]);

  // Default selection = current enabled (all, for a new user).
  useEffect(() => {
    if (catalog.length && sel.length === 0) {
      setSel(enabled && enabled.length ? enabled : catalog.map((f) => f.key));
    }
  }, [catalog, enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;

  const isMand = (k) => mandatory.includes(k);
  const toggle = (k) => {
    if (isMand(k)) return;
    setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));
  };

  const confirm = async () => {
    setBusy(true);
    await save(Array.from(new Set([...mandatory, ...sel])));
    setBusy(false);
    setOpen(false);
  };

  const count = Array.from(new Set([...mandatory, ...sel])).length;

  return (
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm"
      data-testid="feature-onboarding">
      <div className="w-full sm:max-w-xl max-h-[90vh] overflow-y-auto rounded-t-3xl sm:rounded-3xl border border-white/10 p-6"
        style={{ background: "linear-gradient(180deg,#0b1220,#0a0f1c)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-cyan-300 text-[10px] font-black uppercase tracking-widest">
          <Sparkles size={13} /> Build your FUUSIC
        </div>
        <h2 className="mt-1 text-2xl font-black text-white">Pick what you want to see</h2>
        <p className="text-sm text-slate-400 mt-1 mb-4">
          Your Home will show only the features you choose — keep it simple, add more anytime from Settings.
        </p>

        {/* Appearance — Light / Dark / Match device (live preview on tap) */}
        <div className="mb-5" data-testid="onboarding-appearance">
          <div className="text-[10px] font-black uppercase tracking-widest text-cyan-300 mb-2">
            Choose your look
          </div>
          <div className="grid grid-cols-3 gap-2.5">
            {APPEARANCE.map(({ k, label, desc, Icon }) => {
              const on = appr === k;
              return (
                <button key={k} type="button" onClick={() => pickAppr(k)}
                  data-testid={`onboarding-appearance-${k}`} aria-pressed={on}
                  className={`flex flex-col items-center gap-1.5 rounded-2xl p-3 border transition ${
                    on ? "border-cyan-400/60 bg-cyan-400/[0.08]" : "border-white/10 bg-white/[0.03] hover:border-white/25"}`}>
                  <span className="w-9 h-9 rounded-xl grid place-items-center"
                    style={{ background: on ? "linear-gradient(135deg,#22d3ee,#a855f7)" : "rgba(255,255,255,0.06)" }}>
                    <Icon size={16} color={on ? "#fff" : "#9aa6c8"} />
                  </span>
                  <span className="text-xs font-black text-white">{label}</span>
                  <span className="text-[10px] text-slate-400 text-center leading-tight">{desc}</span>
                </button>
              );
            })}
          </div>
          <p className="text-[11px] text-slate-500 mt-2">You can change this anytime in Settings.</p>

          <div className="mt-4">
            <div className="text-[10px] font-black uppercase tracking-widest text-cyan-300 mb-2">
              Accent colour
            </div>
            <AccentSwatches testIdPrefix="onboarding-accent" size={36} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {catalog.map((f) => {
            const on = sel.includes(f.key) || isMand(f.key);
            const Icon = ICONS[f.icon] || Sparkles;
            return (
              <button key={f.key} type="button" onClick={() => toggle(f.key)}
                data-testid={`feature-onboarding-${f.key}`}
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
                  <span className="block text-[12px] text-slate-400 mt-0.5 leading-snug">{f.desc}</span>
                </span>
                <span className={`shrink-0 w-6 h-6 rounded-full grid place-items-center border ${
                  on ? "bg-cyan-400 border-cyan-400" : "border-white/25"}`}>
                  {on && <Check size={14} className="text-slate-950" />}
                </span>
              </button>
            );
          })}
        </div>

        <button type="button" onClick={confirm} disabled={busy}
          data-testid="feature-onboarding-save"
          className="mt-5 w-full h-12 rounded-full font-black text-slate-950 disabled:opacity-60"
          style={{ background: "linear-gradient(135deg,#22d3ee,#a855f7)" }}>
          {busy ? <Loader2 className="animate-spin mx-auto" size={18} />
            : `Build my Home (${count})`}
        </button>
        <p className="mt-2 text-center text-[11px] text-slate-500">Listen stays on so you always have radio.</p>
      </div>
    </div>
  );
}
