import { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";
import { Trophy } from "lucide-react";

// Live "just won" marquee for the Play & Win page. Real wins first, padded
// with realistic samples by the backend so it never looks empty.
export function WinnersTicker() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      axios.get(`${API}/games/recent-wins`, { params: { limit: 20 }, withCredentials: true })
        .then(({ data }) => { if (alive) setItems(data.items || []); })
        .catch(() => {});
    load();
    const t = setInterval(load, 25000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  if (!items.length) return null;
  const row = [...items, ...items]; // duplicate for a seamless loop

  return (
    <div data-testid="winners-ticker" style={{
      overflow: "hidden", borderRadius: 999,
      border: "1px solid rgba(251,191,36,0.25)",
      background: "linear-gradient(90deg, rgba(36,20,54,0.9), rgba(11,12,22,0.95))",
      padding: "9px 0", position: "relative",
    }}>
      <style>{`@keyframes fuusicMarquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}`}</style>
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 30, whiteSpace: "nowrap",
        animation: "fuusicMarquee 42s linear infinite", willChange: "transform", paddingLeft: 30,
      }}>
        {row.map((w, i) => (
          <span key={i}
            data-testid={i < items.length ? `winner-item-${i}` : undefined}
            style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 13, color: "#e9e3ff" }}>
            <Trophy size={13} color="#fbbf24" />
            <b style={{ color: "#fff" }}>{w.display_name}</b>
            <span style={{ color: "#c4b5fd" }}>won</span>
            <b style={{ color: "#fbbf24" }}>{w.prize_label}</b>
            <span style={{ color: "#8b7fb0" }}>on {w.game_label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export default WinnersTicker;
