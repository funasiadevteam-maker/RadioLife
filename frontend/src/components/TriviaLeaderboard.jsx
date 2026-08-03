/** Phase 41 Session 4.5.B — "Top Brains" trivia leaderboard.
 *
 * Renders below TopFansSection on `/r/:slug`. Public — works for all
 * viewers. Shows the top 10 trivia players for this station with a
 * window pill toggle (7d / 30d / All).
 *
 * Auto-hides on empty + window=all (so demo stations don't see a
 * permanent "no plays yet" placeholder taking up space).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Brain, User } from "lucide-react";
import { API } from "@/AuthContext";

const WINDOWS = [
  { key: "7d",  label: "7d" },
  { key: "30d", label: "30d" },
  { key: "all", label: "All" },
];

export default function TriviaLeaderboard({ slug, currentUserId }) {
  const [window, setWindow] = useState("7d");
  const [data, setData]     = useState(null);
  const [loading, setLoad]  = useState(false);

  const load = useCallback(async (w) => {
    setLoad(true);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/trivia_leaderboard`,
        { params: { window: w, limit: 10 } });
      setData(r.data);
    } catch {
      setData({ top_brains: [], count: 0 });
    } finally {
      setLoad(false);
    }
  }, [slug]);

  useEffect(() => {
    let cancel = false;
    Promise.resolve().then(() => { if (!cancel) load(window); });
    return () => { cancel = true; };
  }, [load, window]);

  const top = data?.top_brains || [];
  // Hide cleanly on all-time when there's no data at all.
  if (window === "all" && !loading && top.length === 0) return null;

  return (
    <div data-testid="trivia-leaderboard"
         style={{ marginTop: 28, padding: 18, borderRadius: 14,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                     alignItems: "center", marginBottom: 12, gap: 8,
                     flexWrap: "wrap" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Brain size={14} color="#a78bfa" />
          <div data-testid="trivia-leaderboard-heading"
                style={{ fontSize: 13, fontWeight: 700, color: "#fff",
                          letterSpacing: "0.04em", textTransform: "uppercase" }}>
            Top Brains
          </div>
          <div style={{ fontSize: 10, color: "#9aa3af" }}>
            Trivia leaderboard
          </div>
        </div>
        <div data-testid="trivia-leaderboard-window-pill"
             role="tablist"
             style={{ display: "inline-flex", gap: 2,
                       background: "rgba(0,0,0,0.4)", padding: 3,
                       borderRadius: 999,
                       border: "1px solid rgba(255,255,255,0.05)" }}>
          {WINDOWS.map((w) => (
            <button key={w.key}
                    role="tab"
                    aria-selected={window === w.key}
                    data-testid={`trivia-window-${w.key}`}
                    data-active={window === w.key ? "true" : "false"}
                    onClick={() => setWindow(w.key)}
                    style={{ padding: "4px 12px", borderRadius: 999,
                              fontSize: 11, fontWeight: 700,
                              background: window === w.key
                                ? "rgba(167,139,250,0.18)"
                                : "transparent",
                              color: window === w.key ? "#a78bfa" : "#9aa3af",
                              border: "none",
                              cursor: "pointer",
                              letterSpacing: "0.04em",
                              textTransform: "uppercase" }}>
              {w.label}
            </button>
          ))}
        </div>
      </div>

      {loading && top.length === 0 && (
        <div data-testid="trivia-leaderboard-loading"
             style={{ color: "#9aa3af", fontSize: 12, padding: 12 }}>
          Loading…
        </div>
      )}

      {!loading && top.length === 0 && (
        <div data-testid="trivia-leaderboard-empty"
             style={{ color: "#9aa3af", fontSize: 12, padding: "14px 8px",
                       textAlign: "center" }}>
          {data?.note || "No trivia plays in this window yet."}
        </div>
      )}

      {top.length > 0 && (
        <div role="table"
             style={{ display: "grid", gap: 4 }}>
          <div role="row"
               style={{ display: "grid",
                         gridTemplateColumns: "32px 1fr auto auto",
                         gap: 12, alignItems: "center",
                         padding: "6px 10px",
                         fontSize: 10, color: "#6b7280",
                         letterSpacing: "0.1em", textTransform: "uppercase",
                         fontFamily: "monospace",
                         borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
            <span>#</span>
            <span>Player</span>
            <span style={{ textAlign: "right" }}>Plays</span>
            <span style={{ textAlign: "right" }}>Score</span>
          </div>
          {top.map((row) => (
            <LeaderboardRow key={row.user_id} row={row}
                              isMe={row.user_id === currentUserId} />
          ))}
        </div>
      )}
    </div>
  );
}

function LeaderboardRow({ row, isMe }) {
  const rank = row.rank;
  const rankColor = rank === 1 ? "#fdb756"
                   : rank === 2 ? "#cbd5e1"
                   : rank === 3 ? "#d97706"
                   : "#6b7280";
  return (
    <div role="row"
         data-testid={`trivia-leaderboard-row-${row.user_id}`}
         data-rank={rank}
         data-is-me={isMe ? "true" : "false"}
         style={{ display: "grid",
                   gridTemplateColumns: "32px 1fr auto auto",
                   gap: 12, alignItems: "center",
                   padding: "8px 10px",
                   borderRadius: 8,
                   background: isMe
                     ? "rgba(167,139,250,0.08)"
                     : "rgba(255,255,255,0.02)",
                   border: `1px solid ${isMe
                     ? "rgba(167,139,250,0.3)"
                     : "rgba(255,255,255,0.04)"}` }}>
      <span style={{ color: rankColor, fontWeight: 800, fontSize: 14,
                      fontFamily: "monospace", textAlign: "center" }}>
        {rank}
      </span>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 8,
                     minWidth: 0 }}>
        {row.avatar_url ? (
          <img src={row.avatar_url} alt=""
                 style={{ width: 22, height: 22, borderRadius: 999,
                           objectFit: "cover" }} />
        ) : (
          <div style={{ width: 22, height: 22, borderRadius: 999,
                          background: "rgba(167,139,250,0.15)",
                          display: "grid", placeItems: "center" }}>
            <User size={12} color="#a78bfa" />
          </div>
        )}
        <span style={{ fontSize: 13, color: "#fff", fontWeight: 600,
                        overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap" }}>
          {row.name}{isMe ? " · You" : ""}
        </span>
      </div>
      <span style={{ fontSize: 12, color: "#9aa3af",
                      fontFamily: "monospace", textAlign: "right" }}>
        {row.sessions_played}
      </span>
      <span style={{ fontSize: 14, color: "#fff", fontWeight: 700,
                      fontFamily: "monospace", textAlign: "right" }}>
        {row.score}
      </span>
    </div>
  );
}
