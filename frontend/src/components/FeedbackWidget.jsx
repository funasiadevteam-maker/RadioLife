// Phase Π.5 — Floating "🐛 Feedback" widget.  Only renders for employees
// (`user.is_employee`) or admins.  Posts to /api/feedback/submit.
import React, { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Bug, X, Loader2, Send, Camera } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { Card, Button, Chip } from "@/shell/primitives";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const CATEGORIES = [
  { id: "bug",                  label: "🐞 Bug",                tone: "danger" },
  { id: "suggestion",  label: "💡 Suggestion",  tone: "electric" },
  { id: "praise",            label: "🎉 Praise",          tone: "gold" },
  { id: "other",              label: "📝 Other",            tone: "neutral" },
];

export default function FeedbackWidget() {
  const { user } = useAuth();
  const [open, setOpen]    = useState(false);
  const [cat, setCat]        = useState("bug");
  const [text, setText]    = useState("");
  const [busy, setBusy]    = useState(false);
  const [shot, setShot]    = useState(null); // data URL when captured

  if (!user) return null;
  if (!(user.is_employee || user.is_admin || user.role === "admin")) {
    return null;
  }

  const capture = async () => {
    try {
      const mod = await import(/* webpackChunkName: "html2canvas" */ "html2canvas");
      const canvas = await mod.default(document.body,
                                                                              { useCORS: true, scale: 0.6 });
      const url = canvas.toDataURL("image/jpeg", 0.55);
      // Hard-cap at ~1.8MB to fit our 2MB inline limit.
      setShot(url.length > 1_800_000 ? null : url);
      if (url.length > 1_800_000) {
        toast.error("Screenshot too large — please describe instead.");
      } else {
        toast.success("Screenshot attached.");
      }
    } catch (_e) {
      toast.message("html2canvas not installed — skipping screenshot.");
      setShot(null);
    }
  };

  const submit = async () => {
    if (busy || text.trim().length < 4) return;
    setBusy(true);
    try {
      await axios.post(`${API}/feedback/submit`, {
        category: cat,
        text: text.trim(),
        screenshot_data_url: shot || undefined,
        current_url: window.location.href,
        current_user_agent: navigator.userAgent,
      });
      toast.success("Thanks — feedback logged.");
      setOpen(false); setText(""); setShot(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Submit failed.");
    } finally { setBusy(false); }
  };

  return (
    <>
      <button onClick={() => setOpen(true)}
                      data-testid="feedback-widget-fab"
                      title="Send RadioLife feedback"
                      className="fixed bottom-4 right-4 z-[60]
                                        bg-accent-gold text-bg-base
                                        rounded-full p-3 shadow-lg
                                        hover:scale-105 transition-transform
                                        flex items-center gap-2 font-semibold">
        <Bug size={16} />
        <span className="hidden sm:inline text-xs">Feedback</span>
      </button>

      {open && (
        <div data-testid="feedback-widget-modal"
                  className="fixed inset-0 z-[90] bg-black/70 backdrop-blur-sm
                                    flex items-end sm:items-center justify-center px-3 py-6"
                  onClick={() => !busy && setOpen(false)}>
          <Card className="w-full max-w-md p-5 sm:p-6 space-y-4 relative"
                      onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setOpen(false)} disabled={busy}
                            data-testid="feedback-widget-close"
                            className="absolute top-3 right-3 text-text-secondary
                                              hover:text-white">
              <X size={16} />
            </button>
            <header className="space-y-1">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-accent-gold flex items-center gap-2">
                <Bug size={11} /> Employee Feedback
              </div>
              <h2 className="font-display font-bold text-2xl tracking-display-tight">
                Tell us what you found
              </h2>
            </header>

            <div data-testid="feedback-widget-categories"
                      className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((c) => (
                <button key={c.id} onClick={() => setCat(c.id)}
                                data-testid={`feedback-widget-cat-${c.id}`}>
                  <Chip active={cat === c.id}
                              tone={cat === c.id ? c.tone : "neutral"}>
                    {c.label}
                  </Chip>
                </button>
              ))}
            </div>

            <textarea value={text} maxLength={2000} rows={5}
                                placeholder="What happened? What did you expect?"
                                onChange={(e) => setText(e.target.value)}
                                data-testid="feedback-widget-text"
                                className="w-full rounded-token-md bg-white/[0.04]
                                                border border-white/10 px-3.5 py-2.5 text-sm
                                                focus:outline-none focus:border-accent-gold/60
                                                resize-none" />

            <div className="flex items-center gap-2 flex-wrap">
              <Button variant="ghost" size="sm" onClick={capture}
                              data-testid="feedback-widget-capture">
                <Camera size={12} /> {shot ? "Re-capture" : "Capture screenshot"}
              </Button>
              {shot && (
                <Chip tone="emerald" data-testid="feedback-widget-shot-chip">
                  Screenshot attached
                </Chip>
              )}
            </div>

            <Button variant="gold" className="w-full"
                            onClick={submit}
                            disabled={busy || text.trim().length < 4}
                            data-testid="feedback-widget-submit">
              {busy
                ? <><Loader2 size={14} className="animate-spin" /> Sending…</>
                : <>Send feedback <Send size={14} /></>}
            </Button>
            <p className="text-[10px] text-text-secondary text-center">
              Visible only to RadioLife admins.  Includes your URL + browser.
            </p>
          </Card>
        </div>
      )}
    </>
  );
}
