/**
 * Phase 41 S3.A — BusinessHoursPicker
 *
 * 7-day open/close time grid editor. Each row is collapsible to
 * "closed" via a toggle.
 *
 * Controlled component:
 *   <BusinessHoursPicker value={hours} onChange={setHours} />
 *
 * `value` shape: {mon:{open,close,closed}, tue:..., ..., sun:...}
 * All times are HH:MM strings (24-hour). When `closed=true`, open/close
 * are null.
 */
import React from "react";

const DAYS = [
  { key: "mon", label: "Monday"    },
  { key: "tue", label: "Tuesday"   },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday"  },
  { key: "fri", label: "Friday"    },
  { key: "sat", label: "Saturday"  },
  { key: "sun", label: "Sunday"    },
];

const DEFAULT_OPEN  = "09:00";
const DEFAULT_CLOSE = "18:00";

export default function BusinessHoursPicker({ value, onChange }) {
  const safe = value || {};
  const update = (day, patch) => {
    const next = {
      ...safe,
      [day]: { ...(safe[day] || {}), ...patch },
    };
    onChange && onChange(next);
  };

  return (
    <div data-testid="business-hours-picker"
         style={{ display: "grid", gap: 8 }}>
      {DAYS.map(({ key, label }) => {
        const row = safe[key] || {};
        const closed = !!row.closed;
        const o = row.open  || DEFAULT_OPEN;
        const c = row.close || DEFAULT_CLOSE;
        return (
          <div key={key}
               data-testid={`hours-row-${key}`}
               style={{ display: "grid",
                         gridTemplateColumns: "100px 1fr auto",
                         alignItems: "center", gap: 10,
                         padding: "8px 12px", borderRadius: 8,
                         background: "rgba(255,255,255,0.04)",
                         border: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: "#e5e7eb" }}>
              {label}
            </div>
            {closed ? (
              <div data-testid={`hours-${key}-closed-label`}
                   style={{ fontSize: 13, color: "#6b7280",
                             fontStyle: "italic" }}>
                Closed
              </div>
            ) : (
              <div style={{ display: "inline-flex", alignItems: "center",
                              gap: 6, fontSize: 13, color: "#9aa3af" }}>
                <input type="time"
                       data-testid={`hours-${key}-open`}
                       value={o}
                       onChange={(e) => update(key, { open: e.target.value,
                                                       closed: false })}
                       style={timeInputStyle} />
                <span>→</span>
                <input type="time"
                       data-testid={`hours-${key}-close`}
                       value={c}
                       onChange={(e) => update(key, { close: e.target.value,
                                                       closed: false })}
                       style={timeInputStyle} />
              </div>
            )}
            <label style={{ display: "inline-flex", alignItems: "center",
                              gap: 5, fontSize: 11, color: "#9aa3af",
                              cursor: "pointer" }}>
              <input type="checkbox"
                     data-testid={`hours-${key}-closed-toggle`}
                     checked={closed}
                     onChange={(e) => {
                       const isClosed = e.target.checked;
                       update(key, isClosed
                         ? { closed: true, open: null, close: null }
                         : { closed: false, open: DEFAULT_OPEN,
                              close: DEFAULT_CLOSE });
                     }} />
              Closed
            </label>
          </div>
        );
      })}
    </div>
  );
}

const timeInputStyle = {
  background:    "rgba(0,0,0,0.25)",
  color:         "#fff",
  border:        "1px solid rgba(255,255,255,0.08)",
  borderRadius:  6,
  padding:       "4px 8px",
  fontSize:      12,
  fontFamily:    "inherit",
  outline:       "none",
  colorScheme:   "dark",
};
