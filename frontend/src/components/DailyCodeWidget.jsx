// Phase AD.8 — Daily Code Claim widget.
//
// Mounted inside the Now Playing surface (LiveRadioStation.jsx).
// Anonymous users see a "sign in to claim" nudge; authed users see the
// 6-char code (plaintext), a claim button, and their streak counter.
//
// After claim: shows the points awarded + multiplier + confetti/success
// state.  Streak counter shows the flame + day count.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Flame, Coins, CheckCircle2, Loader2, KeyRound, LogIn } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";


export default function DailyCodeWidget() {
  const { user } = useAuth();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [state, setState] = useState({
    loading: true, current: null, code: "", busy: false,
    error: null, justClaimed: null,
  });

  const s = state;
  const set = (patch) => setState((cur) => ({ ...cur, ...patch }));

  const loadCurrent = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/daily-code/current`,
        { withCredentials: true });
      set({ current: r.data, loading: false });
    } catch (_e) {
      set({ current: null, loading: false });
    }
  }, []);

  useEffect(() => { loadCurrent(); }, [loadCurrent]);

  const claim = async () => {
    if (!user) return;
    set({ busy: true, error: null });
    try {
      const r = await axios.post(`${API}/daily-code/claim`,
        { code: s.code.trim().toUpperCase() },
        { withCredentials: true });
      set({ justClaimed: r.data, busy: false, code: "" });
      loadCurrent();
    } catch (err) {
      set({ busy: false,
                error: err?.response?.data?.detail?.code || err.message });
    }
  };

  const claimAuto = async () => {
    // Auto-fill code from response and claim in one tap.
    if (!s.current?.code) return;
    set({ code: s.current.code });
    setTimeout(claim, 50);
  };

  // Anonymous
  if (!user) {
    return (
      <div className={`rounded-2xl p-4 mt-4 border ${light ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"}`}
                data-testid="daily-code-widget-anon">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl grid place-items-center bg-gradient-to-br from-amber-500 to-fuchsia-500">
            <Coins size={18} className="text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Daily Code
            </div>
            <div className={`text-sm font-black ${light ? "text-slate-900" : "text-white"}`}>
              Earn free points every day.
            </div>
          </div>
          <Link to="/login" data-testid="daily-code-signin-cta"
                        className="inline-flex items-center gap-1 text-xs font-black px-3 py-2 rounded-full bg-amber-500 text-slate-900 hover:bg-amber-400">
            <LogIn size={12} /> Sign in
          </Link>
        </div>
      </div>
    );
  }

  if (s.loading) {
    return (
      <div className={`rounded-2xl p-4 mt-4 border ${light ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"}`}
                data-testid="daily-code-widget-loading">
        <div className={`inline-flex items-center gap-2 text-xs ${light ? "text-slate-500" : "text-slate-400"}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading daily code…
        </div>
      </div>
    );
  }

  // Just claimed — success state
  if (s.justClaimed) {
    return (
      <div className={`rounded-2xl p-5 mt-4 border-2 ${light
                          ? "bg-emerald-50 border-emerald-400 text-emerald-900"
                          : "bg-emerald-500/10 border-emerald-500 text-white"}`}
                data-testid="daily-code-widget-success">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-xl grid place-items-center bg-emerald-500">
            <CheckCircle2 size={22} className="text-white" />
          </div>
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-widest font-mono text-emerald-500">
              Claimed
            </div>
            <div className="text-lg font-black" data-testid="daily-code-claim-result">
              +{s.justClaimed.points_awarded} points
            </div>
            <div className={`text-xs mt-0.5 ${light ? "text-emerald-700" : "text-emerald-300"} inline-flex items-center gap-1`}>
              <Flame size={12} /> {s.justClaimed.streak_days}-day streak · {s.justClaimed.streak_multiplier}× multiplier
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Already claimed today
  if (s.current?.already_claimed) {
    return (
      <div className={`rounded-2xl p-4 mt-4 border ${light ? "bg-slate-50 border-slate-200" : "bg-slate-900/60 border-slate-800"}`}
                data-testid="daily-code-widget-already">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl grid place-items-center bg-emerald-500/20">
            <CheckCircle2 size={18} className="text-emerald-500" />
          </div>
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-widest font-mono text-emerald-500">
              Claimed today
            </div>
            <div className={`text-sm font-black ${light ? "text-slate-900" : "text-white"} inline-flex items-center gap-1`}>
              <Flame size={12} className="text-amber-500" />
              <span data-testid="daily-code-streak-counter">
                {s.current.streak_days}-day streak
              </span>
              · {s.current.next_multiplier}× multiplier
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Active — show input + claim button
  return (
    <div className={`rounded-2xl p-4 mt-4 border-2 ${light
                        ? "bg-white border-amber-300"
                        : "bg-slate-900/60 border-amber-500/40"}`}
              data-testid="daily-code-widget">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-xl grid place-items-center bg-gradient-to-br from-amber-500 to-fuchsia-500">
          <KeyRound size={18} className="text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Daily code · {s.current?.estimated_points ?? s.current?.points_reward} pts
          </div>
          <div className={`text-sm font-black ${light ? "text-slate-900" : "text-white"} inline-flex items-center gap-1`}>
            <Flame size={12} className="text-amber-500" />
            <span data-testid="daily-code-streak-counter">
              {s.current?.streak_days || 0}-day streak
            </span>
            · {s.current?.next_multiplier}× multiplier
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input value={s.code}
                      onChange={(e) => set({ code: e.target.value.toUpperCase().slice(0, 6) })}
                      onKeyDown={(e) => { if (e.key === "Enter") claim(); }}
                      data-testid="daily-code-input"
                      maxLength={6}
                      placeholder="Enter code"
                      className={`flex-1 px-3 py-2 rounded-lg text-lg font-mono font-black tracking-widest uppercase
                                                  ${light ? "bg-slate-50 border border-slate-300 text-slate-900"
                                                                : "bg-slate-950 border border-slate-800 text-white"}`} />
        <button onClick={s.code.length === 6 ? claim : claimAuto}
                        disabled={s.busy}
                        data-testid="daily-code-claim"
                        className="inline-flex items-center gap-1 px-4 py-2 rounded-full text-xs font-black
                                                    bg-amber-500 text-slate-900 hover:bg-amber-400
                                                    disabled:opacity-40 disabled:cursor-not-allowed">
          {s.busy ? <Loader2 size={12} className="animate-spin" /> : <Coins size={12} />}
          {s.code.length === 6 ? "Claim" : "Quick claim"}
        </button>
      </div>
      {s.error && (
        <div className="mt-2 text-xs text-red-400 font-mono"
                    data-testid="daily-code-error">
          {s.error === "wrong_code" ? "Wrong code — check the app copy."
              : s.error === "already_claimed" ? "You already claimed this."
              : s.error === "invalid_code_format" ? "Codes are exactly 6 characters."
              : String(s.error)}
        </div>
      )}
      {s.current?.code && (
        <div className={`mt-2 text-[10px] font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>
          Today&rsquo;s code: <span className="font-black text-amber-500">{s.current.code}</span> · tap Quick claim
        </div>
      )}
    </div>
  );
}
