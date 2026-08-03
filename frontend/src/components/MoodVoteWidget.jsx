/** Phase 41M.A — Mood vote widget.
 *
 * Inline widget rendered on StationPage near the now-playing block.
 * 5 emoji mood buttons + a thin distribution bar that only appears
 * once the station has ≥5 votes (kills cold-start noise).
 *
 * Optimistic update: clicking a mood instantly highlights the chip
 * and updates the local distribution before the server confirms;
 * server response replaces local state. Errors roll back.
 *
 * Anon listeners can't vote — explicit 401 from server. We render a
 * small "Sign in to vote" CTA when caller is unauthenticated.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API, useAuth } from "@/AuthContext";
import { toast } from "sonner";

const MOODS = [
  { key: "chill", label: "Chill",  emoji: "😌", tint: "#67e8f9" },
  { key: "hype",  label: "Hype",   emoji: "🔥", tint: "#f59e0b" },
  { key: "sad",   label: "Sad",    emoji: "😢", tint: "#818cf8" },
  { key: "party", label: "Party",  emoji: "🎉", tint: "#ec4899" },
  { key: "focus", label: "Focus",  emoji: "🎯", tint: "#22d3ee" },
];

const MIN_VOTES_TO_REVEAL = 5;

export default function MoodVoteWidget({ slug }) {
  const { user } = useAuth();
  const [agg, setAgg]         = useState(null);
  const [myMood, setMyMood]   = useState(null);
  const [busy, setBusy]       = useState(false);
  const [err, setErr]         = useState(null);

  const fetchAgg = useCallback(async () => {
    if (!user) {
      setAgg(null);
      setMyMood(null);
      return;
    }
    try {
      const r = await axios.get(
        `${API}/stations/${slug}/mood_aggregate?window=7d`);
      setAgg(r.data);
      setMyMood(r.data?.your_vote?.mood || null);
      setErr(null);
    } catch (e) {
      // 401 = anon listener; surface gracefully.
      if (e?.response?.status !== 401) setErr("Couldn't load mood data.");
    }
  }, [slug, user]);

  useEffect(() => { fetchAgg(); }, [fetchAgg]);

  const cast = useCallback(async (mood) => {
    if (!user) {
      toast.error("Sign in to vote on the vibe.");
      return;
    }
    if (busy) return;
    const prevMood = myMood;
    setMyMood(mood);          // optimistic
    setBusy(true);
    try {
      const r = await axios.post(
        `${API}/stations/${slug}/mood_vote`, { mood });
      setAgg(r.data.aggregate);
      setMyMood(r.data.your_vote?.mood || null);
    } catch (e) {
      setMyMood(prevMood);    // rollback
      const code = e?.response?.data?.detail?.code;
      if (code === "auth_required" || e?.response?.status === 401) {
        toast.error("Sign in to vote on the vibe.");
      } else {
        toast.error("Couldn't record your vote — try again.");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, myMood, slug, user]);

  const clear = useCallback(async () => {
    if (busy || !myMood) return;
    const prev = myMood;
    setMyMood(null);
    setBusy(true);
    try {
      await axios.delete(`${API}/stations/${slug}/mood_vote`);
      fetchAgg();
    } catch (e) {
      setMyMood(prev);
      toast.error("Couldn't clear your vote.");
    } finally {
      setBusy(false);
    }
  }, [busy, myMood, slug, fetchAgg]);

  const total = agg?.station_total || 0;
  const dist  = agg?.station_level || {};
  const reveal = total >= MIN_VOTES_TO_REVEAL;

  return (
    <div data-testid="mood-vote-widget"
         style={{ marginTop: 18,
                   padding: "12px 14px",
                   borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center",
                     justifyContent: "space-between", gap: 12,
                     marginBottom: 10 }}>
        <div style={{ fontSize: 11, color: "#9aa3af",
                       letterSpacing: 1.6, fontFamily: "monospace" }}>
          WHAT&apos;S THE VIBE?
        </div>
        {myMood && (
          <button data-testid="mood-vote-clear" onClick={clear}
                  style={{ background: "none", border: "none",
                            color: "#9aa3af", fontSize: 11,
                            cursor: "pointer" }}>
            clear
          </button>
        )}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {MOODS.map((m) => {
          const isActive = myMood === m.key;
          return (
            <button key={m.key}
                    data-testid={`mood-vote-${m.key}`}
                    data-active={isActive ? "true" : "false"}
                    onClick={() => cast(m.key)}
                    disabled={busy}
                    style={{
                      flex: "1 1 0",
                      minWidth: 64,
                      padding: "8px 10px",
                      borderRadius: 10,
                      border: isActive
                        ? `1px solid ${m.tint}`
                        : "1px solid rgba(255,255,255,0.08)",
                      background: isActive
                        ? `rgba(${hexToRgb(m.tint)},0.12)`
                        : "rgba(255,255,255,0.02)",
                      color: isActive ? m.tint : "#cbd5e1",
                      fontSize: 13,
                      cursor: busy ? "wait" : "pointer",
                      display: "flex", alignItems: "center",
                      gap: 6, justifyContent: "center",
                      transition: "background 0.15s, border-color 0.15s",
                    }}>
              <span style={{ fontSize: 16 }}>{m.emoji}</span>
              <span>{m.label}</span>
            </button>
          );
        })}
      </div>

      {reveal && (
        <div data-testid="mood-vote-aggregate"
             style={{ marginTop: 12 }}>
          <div style={{ display: "flex", height: 6,
                         borderRadius: 4, overflow: "hidden",
                         background: "rgba(255,255,255,0.04)" }}>
            {MOODS.map((m) => {
              const c = dist[m.key] || 0;
              const w = total > 0 ? (c / total) * 100 : 0;
              if (w <= 0) return null;
              return (
                <div key={m.key}
                     data-testid={`mood-bar-${m.key}`}
                     title={`${m.label}: ${c} vote${c === 1 ? "" : "s"}`}
                     style={{ width: `${w}%`, background: m.tint,
                                transition: "width 0.3s" }} />
              );
            })}
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: "#6b7280" }}>
            {total} vote{total === 1 ? "" : "s"} · last 7 days
          </div>
        </div>
      )}
      {!reveal && total > 0 && (
        <div style={{ marginTop: 10, fontSize: 11, color: "#6b7280" }}>
          {MIN_VOTES_TO_REVEAL - total} more vote
          {MIN_VOTES_TO_REVEAL - total === 1 ? "" : "s"} until distribution reveals
        </div>
      )}
      {err && (
        <div style={{ marginTop: 8, fontSize: 11, color: "#fca5a5" }}>
          {err}
        </div>
      )}
    </div>
  );
}

// Tiny inline helper — no extra dep.
function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `${r},${g},${b}`;
}
