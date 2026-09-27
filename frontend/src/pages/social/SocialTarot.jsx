// FUUSIC Social V2 — Tarot (its own Social category, separate from Dreams).
// Phase 2 build: AI tarot draws (1/3-card) with Love/Career/General/Custom
// intents, saved readings, and explicit "Share to Social" (only shared tarot
// ever appears in the wall). Reuses the existing /api/social/readings backend.
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Sparkles, Share2, Check } from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const readings = axios.create({ baseURL: `${BACKEND}/api/social/readings`, withCredentials: true });

const INTENTS = [
  { key: "general", label: "General Reflection", q: "" },
  { key: "love", label: "Love", q: "What should I know about my love life right now?" },
  { key: "career", label: "Career", q: "What guidance is there for my career path?" },
  { key: "custom", label: "Custom Question", q: null },
];

export default function SocialTarot() {
  const navigate = useNavigate();
  const [spread, setSpread] = useState("three");
  const [intent, setIntent] = useState("general");
  const [question, setQuestion] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [result, setResult] = useState(null);
  const [saved, setSaved] = useState([]);
  const [sharing, setSharing] = useState(false);

  const loadSaved = useCallback(async () => {
    try { const r = await readings.get("", { params: { kind: "tarot" } }); setSaved(r.data.items || []); }
    catch (_) {}
  }, []);
  useEffect(() => { loadSaved(); }, [loadSaved]);

  const draw = async () => {
    setDrawing(true); setResult(null);
    const q = intent === "custom" ? question.trim() : (INTENTS.find((i) => i.key === intent)?.q || "");
    try {
      const r = await readings.post("/tarot", { spread, question: q });
      setResult(r.data);
      loadSaved();
    } catch (_) { toast.error("Couldn't draw your cards. Try again."); }
    finally { setDrawing(false); }
  };

  const share = async () => {
    if (!result?.reading_id) return;
    setSharing(true);
    try {
      await readings.post(`/${result.reading_id}/share`, { public: true });
      setResult((r) => ({ ...r, public: true }));
      toast.success("Shared to your Social wall");
    } catch (_) { toast.error("Couldn't share"); }
    finally { setSharing(false); }
  };

  return (
    <div className="min-h-screen text-white" data-testid="social-tarot"
         style={{ background: "linear-gradient(180deg,#0d0a24 0%,#140b2e 45%,#0a0a14 100%)" }}>
      <div className="max-w-2xl mx-auto px-4 sm:px-6 pt-8 pb-32">
        <button type="button" onClick={() => navigate("/social")} data-testid="tarot-back"
                className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white mb-4">
          <ArrowLeft size={16} /> Social
        </button>
        <div className="flex items-center gap-3">
          <span className="text-4xl">🃏</span>
          <div>
            <h1 className="text-3xl sm:text-4xl font-black">Tarot</h1>
            <p className="text-slate-400 text-sm">Draw a card, reflect — entertainment only.</p>
          </div>
        </div>

        <div className="mt-6 rounded-3xl border border-white/10 p-5"
             style={{ background: "linear-gradient(135deg,#1e1b4b,#3b0764)" }}>
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-violet-300 mb-2">Choose a spread</div>
          <div className="flex gap-2 mb-4">
            {[["one", "1 Card"], ["three", "3 Card · Past/Present/Future"]].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setSpread(k)} data-testid={`tarot-spread-${k}`}
                      className={`h-10 px-4 rounded-full text-sm font-bold ${spread === k ? "text-white" : "text-slate-300 bg-white/[0.06]"}`}
                      style={spread === k ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
                {l}
              </button>
            ))}
          </div>
          <div className="text-[11px] font-black uppercase tracking-[0.18em] text-violet-300 mb-2">Focus</div>
          <div className="flex gap-2 flex-wrap mb-3">
            {INTENTS.map((i) => (
              <button key={i.key} type="button" onClick={() => setIntent(i.key)} data-testid={`tarot-intent-${i.key}`}
                      className={`h-9 px-4 rounded-full text-xs font-bold ${intent === i.key ? "text-white bg-white/20" : "text-slate-300 bg-white/[0.06]"}`}>
                {i.label}
              </button>
            ))}
          </div>
          {intent === "custom" && (
            <input value={question} onChange={(e) => setQuestion(e.target.value)} data-testid="tarot-question"
                   placeholder="Ask your question…"
                   className="w-full rounded-2xl bg-white/[0.06] border border-white/10 px-4 py-3 text-sm outline-none mb-3" />
          )}
          <button type="button" onClick={draw} disabled={drawing} data-testid="tarot-draw"
                  className="w-full h-12 rounded-full font-black text-white disabled:opacity-60 flex items-center justify-center gap-2"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {drawing ? <Loader2 className="animate-spin" size={18} /> : <><Sparkles size={17} /> Draw cards</>}
          </button>
        </div>

        {result && (
          <div className="mt-5 rounded-3xl border border-white/10 bg-white/[0.04] p-5" data-testid="tarot-result">
            <div className="flex gap-3 overflow-x-auto no-scrollbar mb-4">
              {(result.cards || []).map((c, i) => (
                <div key={i} className="flex-shrink-0 w-28 rounded-2xl p-3 text-center border border-violet-400/30"
                     style={{ background: "linear-gradient(160deg,#2e1065,#4c1d95)" }}>
                  <div className="text-3xl mb-1">🃏</div>
                  <div className="text-[10px] uppercase tracking-widest text-violet-300">{c.position}</div>
                  <div className="text-xs font-black mt-0.5">{c.name}</div>
                  <div className="text-[10px] text-slate-400 capitalize">{c.orientation}</div>
                </div>
              ))}
            </div>
            <div className="text-sm text-slate-200 whitespace-pre-line leading-relaxed">
              {typeof result.result === "string" ? result.result : (result.result?.reading || result.result?.text || "")}
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{result.disclaimer}</p>
            <button type="button" onClick={share} disabled={sharing || result.public} data-testid="tarot-share"
                    className="mt-4 inline-flex items-center gap-2 h-10 px-5 rounded-full text-sm font-bold text-white disabled:opacity-60"
                    style={{ background: result.public ? "rgba(255,255,255,0.12)" : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              {result.public ? <><Check size={16} /> Shared to Social</> : <><Share2 size={16} /> Share to Social</>}
            </button>
          </div>
        )}

        {saved.length > 0 && (
          <div className="mt-8">
            <div className="text-[11px] font-black uppercase tracking-[0.18em] text-slate-400 mb-3">Saved readings</div>
            <div className="space-y-2" data-testid="tarot-saved">
              {saved.map((r) => (
                <div key={r.reading_id} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3.5">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-bold">{r.title || "Tarot reading"}</div>
                    {r.public && <span className="text-[10px] font-black text-cyan-300">SHARED</span>}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">{r.subject}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
