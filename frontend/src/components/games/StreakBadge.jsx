import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";
import { Flame } from "lucide-react";

// Daily-play streak flame. Shows the current streak + today's bonus hint.
export function StreakBadge({ refreshKey = 0 }) {
  const [s, setS] = useState(null);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/games/streak`, { withCredentials: true })
      .then(({ data }) => { if (alive) setS(data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [refreshKey]);

  if (!s) return null;
  const n = s.current_streak || 0;
  const hot = n > 0;

  return (
    <div data-testid="streak-badge" style={{
      display: "inline-flex", alignItems: "center", gap: 10, padding: "8px 14px",
      borderRadius: 999,
      border: `1px solid ${hot ? "rgba(251,146,60,0.5)" : "rgba(255,255,255,0.12)"}`,
      background: hot
        ? "linear-gradient(135deg, rgba(251,146,60,0.2), rgba(236,72,153,0.14))"
        : "rgba(255,255,255,0.05)",
    }}>
      <Flame size={18} color={hot ? "#fb923c" : "#64748b"} fill={hot ? "#fb923c" : "none"} />
      <div style={{ lineHeight: 1.15 }}>
        <div data-testid="streak-count" style={{ fontSize: 13, fontWeight: 900, color: "#fff" }}>
          {n}-day streak
        </div>
        <div style={{ fontSize: 10.5, color: "#c4b5fd" }}>
          {s.claim_available
            ? `Play today for +${s.pending_bonus_points} pts`
            : "Bonus claimed today 🎉"}
        </div>
      </div>
    </div>
  );
}

export default StreakBadge;
