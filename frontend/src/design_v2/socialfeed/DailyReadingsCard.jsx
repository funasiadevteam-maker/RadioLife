// FUUSIC — Daily Readings subscribe control. Private cards (Tarot / Horoscope /
// Numerology) that appear only on the member's own feed.
import { useEffect, useState } from "react";
import axios from "axios";
import { Sparkles, Moon, Hash, Check } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const ITEMS = [
  { k: "tarot", label: "Daily Tarot", Icon: Sparkles },
  { k: "horoscope", label: "Horoscope", Icon: Moon },
  { k: "numerology", label: "Numerology", Icon: Hash },
];

export default function DailyReadingsCard({ t, onChanged }) {
  const [subs, setSubs] = useState(null);
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let on = true;
    axios.get(`${API}/social/daily-readings`, { withCredentials: true })
      .then((r) => { if (on) setSubs(r.data?.subscriptions || []); })
      .catch(() => { if (on) setSubs([]); });
    return () => { on = false; };
  }, []);

  if (subs === null) return null;
  const enabled = {};
  subs.forEach((s) => { enabled[s.reading_type] = s.enabled; });

  const toggle = async (k) => {
    const next = !enabled[k];
    setBusy(k);
    setSubs((p) => {
      const has = p.some((s) => s.reading_type === k);
      const upd = p.map((s) => s.reading_type === k
        ? { ...s, enabled: next, frequency: next ? "daily" : "off" } : s);
      return has ? upd : [...upd, { reading_type: k, enabled: next, frequency: next ? "daily" : "off" }];
    });
    try {
      await axios.put(`${API}/social/daily-readings/${k}`,
        { enabled: next, frequency: next ? "daily" : "off" }, { withCredentials: true });
      onChanged && onChanged();
    } catch (_e) { /* revert on next load */ } finally { setBusy(null); }
  };

  return (
    <div data-testid="daily-readings-card" style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 18, boxShadow: t.shadow, padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
        <Sparkles size={17} color={t.accent} />
        <span style={{ fontWeight: 900, fontSize: 15, color: t.text }}>Daily Readings</span>
      </div>
      <div style={{ fontSize: 12.5, color: t.muted, marginBottom: 12 }}>
        Private daily cards, just for you — AI reflection, never shared.
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {ITEMS.map(({ k, label, Icon }) => {
          const on = !!enabled[k];
          return (
            <button key={k} onClick={() => toggle(k)} disabled={busy === k} data-testid={`dr-toggle-${k}`} className="sf-press"
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 14px", borderRadius: 999, cursor: "pointer", fontWeight: 700, fontSize: 13,
                border: `1.5px solid ${on ? t.accent : t.border}`,
                background: on ? t.accentSoft : "transparent",
                color: on ? t.accent : t.text2 }}>
              {on ? <Check size={15} /> : <Icon size={15} />} {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
