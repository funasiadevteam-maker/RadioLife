// First-run interest onboarding — a skippable "Pick a few interests" step that
// auto-opens ONCE for brand-new users right after their first sign-up (Google
// or email), so their very first Right-Rail suggestions are personalized.
// Reuses the shared GET/PUT /api/social/interests + POST /interests/skip.
// Mounted globally in AppShellV2, but only renders when needs_onboarding=true.
import { useEffect, useState } from "react";
import axios from "axios";
import { Sparkles, Check, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function InterestOnboarding() {
  const [open, setOpen] = useState(false);
  const [topics, setTopics] = useState([]);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/social/interests`, { withCredentials: true })
      .then((r) => {
        if (cancel) return;
        if (r.data?.needs_onboarding) {
          setTopics(r.data?.topics || []);
          setSel(r.data?.selected || []);
          setOpen(true);
        }
      })
      .catch(() => {});
    return () => { cancel = true; };
  }, []);

  if (!open) return null;

  const toggle = (id) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const save = async () => {
    setBusy(true);
    try {
      await axios.put(`${API}/social/interests`, { interests: sel },
        { withCredentials: true });
    } catch (_) { /* soft — still flags onboarded */ }
    finally { setBusy(false); setOpen(false); }
  };

  const skip = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/social/interests/skip`, {}, { withCredentials: true });
    } catch (_) { /* soft */ }
    finally { setBusy(false); setOpen(false); }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center bg-black/75 backdrop-blur-sm"
      data-testid="interest-onboarding">
      <div className="w-full sm:max-w-lg rounded-t-3xl sm:rounded-3xl border border-white/10 p-6"
        style={{ background: "linear-gradient(180deg,#16122e,#0b0918)" }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 text-purple-300 text-[10px] font-black uppercase tracking-widest">
          <Sparkles size={13} /> Welcome to FUUSIC
        </div>
        <h2 className="mt-1 text-2xl font-black text-white">Pick a few interests</h2>
        <p className="text-sm text-slate-400 mt-1 mb-4">
          We'll personalize your feed and rail with creators and shows you'll love.
          You can change this anytime.
        </p>
        <div className="flex flex-wrap gap-2">
          {topics.map((t) => {
            const on = sel.includes(t.id);
            return (
              <button key={t.id} type="button" onClick={() => toggle(t.id)}
                data-testid={`onboarding-interest-${t.id}`}
                className={`inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-sm font-bold border transition ${
                  on ? "text-white border-transparent" : "text-slate-300 border-white/15 bg-white/[0.04]"}`}
                style={on ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
                {on && <Check size={14} />} {t.label}
              </button>
            );
          })}
        </div>
        <div className="mt-6 flex items-center gap-3">
          <button type="button" onClick={skip} disabled={busy}
            data-testid="onboarding-skip"
            className="h-11 px-5 rounded-full font-bold text-slate-300 hover:text-white border border-white/15 disabled:opacity-60">
            Skip for now
          </button>
          <button type="button" onClick={save} disabled={busy || sel.length === 0}
            data-testid="onboarding-save"
            className="flex-1 h-11 rounded-full font-black text-white disabled:opacity-50"
            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {busy ? <Loader2 className="animate-spin mx-auto" size={18} />
              : `Personalize my feed${sel.length ? ` (${sel.length})` : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
