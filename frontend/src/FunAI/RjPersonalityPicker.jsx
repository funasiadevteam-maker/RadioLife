/** RjPersonalityPicker — lets the listener choose the Fun AI RJ/anchor
 *  personality (Friendly / Energetic / Calm / Funny / Thoughtful). One
 *  global setting, applied to both the news anchor and the player RJ at the
 *  start of the next voice session. */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

export default function RjPersonalityPicker({ dark = true, accent = "#00b8d9",
                                              testIdPrefix = "rj-personality" }) {
  const [list, setList] = useState([]);
  const [active, setActive] = useState(null);

  useEffect(() => {
    axios.get(`${API}/fun-ai/preferences`, { withCredentials: true })
      .then((r) => { setList(r.data?.personalities || []); setActive(r.data?.personality || null); })
      .catch(() => {});
  }, []);

  const pick = (id) => {
    setActive(id);
    axios.put(`${API}/fun-ai/preferences`, { personality: id },
              { withCredentials: true }).catch(() => {});
  };

  if (!list.length) return null;
  const fg = dark ? "#e7eefc" : "#0b1220";
  const sub = dark ? "#8aa3c7" : "#64748b";
  const line = dark ? "rgba(255,255,255,0.14)" : "rgba(0,0,0,0.12)";
  const chipBg = dark ? "rgba(255,255,255,0.05)" : "#f1f5f9";

  return (
    <div data-testid={`${testIdPrefix}-row`} style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1,
                    color: sub, marginBottom: 6 }}>RJ personality</div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {list.map((p) => {
          const on = p.id === active;
          return (
            <button key={p.id} data-testid={`${testIdPrefix}-${p.id}`} onClick={() => pick(p.id)}
                    title={p.blurb}
                    style={{ cursor: "pointer", padding: "7px 12px", borderRadius: 999,
                             fontSize: 12, fontWeight: 700,
                             border: `1px solid ${on ? accent : line}`,
                             color: on ? "#001018" : fg,
                             background: on ? accent : chipBg }}>
              {p.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
