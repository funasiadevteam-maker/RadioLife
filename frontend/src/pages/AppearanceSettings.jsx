// Settings → Appearance. Light/Dark/System, accent colour, and Scheduled Dark
// (auto dark/light by local clock). Backed by the shared theme store
// (/api/shell/prefs). Mirrors the mobile Profile appearance controls.
import { useNavigate } from "react-router-dom";
import { Sun, Moon, Monitor, ArrowLeft, Clock } from "lucide-react";
import { useTheme } from "@/theme/useTheme";
import AccentSwatches from "@/theme/AccentSwatches";

const MODE_OPTS = [
  { k: "light", label: "Light", Icon: Sun },
  { k: "dark", label: "Dark", Icon: Moon },
  { k: "system", label: "Match device", Icon: Monitor },
];

const hourLabel = (h) => {
  const ap = h < 12 ? "AM" : "PM";
  const hr = h % 12 === 0 ? 12 : h % 12;
  return `${hr}:00 ${ap}`;
};
const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function AppearanceSettings() {
  const navigate = useNavigate();
  const { mode, accent, schedule, setMode, setSchedule } = useTheme();

  return (
    <div className="fz-app min-h-screen" data-testid="appearance-settings">
      <div className="max-w-xl mx-auto px-4 py-6">
        <button onClick={() => navigate(-1)} data-testid="appearance-back"
          className="flex items-center gap-2 fz-sub hover:fz-text mb-5">
          <ArrowLeft size={18} /> Back
        </button>

        <h1 className="text-2xl font-black fz-text">Appearance</h1>
        <p className="fz-sub text-sm mt-1 mb-6">Make FUUSIC yours — it syncs across your devices.</p>

        {/* Theme mode */}
        <div className="text-[11px] font-black uppercase tracking-widest fz-sub mb-2">Theme</div>
        <div className="grid grid-cols-3 gap-2.5 mb-7">
          {MODE_OPTS.map(({ k, label, Icon }) => {
            const on = !schedule.enabled && mode === k;
            return (
              <button key={k} type="button" onClick={() => setMode(k)}
                data-testid={`appearance-mode-${k}`} aria-pressed={on}
                className="flex flex-col items-center gap-1.5 rounded-2xl p-3.5 border transition fz-card"
                style={{
                  borderColor: on ? "var(--brand-solid)" : "var(--card-border)",
                  background: on ? "var(--chip-bg)" : "var(--bg-glass)",
                }}>
                <Icon size={18} style={{ color: on ? "var(--accent-ink)" : "var(--text-secondary)" }} />
                <span className="text-xs font-black fz-text">{label}</span>
              </button>
            );
          })}
        </div>

        {/* Accent */}
        <div className="text-[11px] font-black uppercase tracking-widest fz-sub mb-3">Accent colour</div>
        <div className="mb-7"><AccentSwatches testIdPrefix="appearance-accent" size={44} /></div>

        {/* Scheduled Dark */}
        <div className="fz-card rounded-2xl p-4 border" style={{ borderColor: "var(--card-border)" }}>
          <div className="flex items-center gap-3">
            <Clock size={18} style={{ color: "var(--brand-solid)" }} />
            <div className="flex-1">
              <div className="font-black fz-text text-sm">Scheduled Dark</div>
              <div className="fz-sub text-[12px]">Automatically switch to Dark at night and Light in the morning.</div>
            </div>
            <button type="button" role="switch" aria-checked={schedule.enabled}
              data-testid="appearance-schedule-toggle"
              onClick={() => setSchedule({ enabled: !schedule.enabled })}
              className="relative shrink-0"
              style={{
                width: 46, height: 27, borderRadius: 999, border: "none", cursor: "pointer",
                background: schedule.enabled ? "var(--brand-solid)" : "var(--card-border)",
                transition: "background .15s",
              }}>
              <span style={{
                position: "absolute", top: 3, left: schedule.enabled ? 22 : 3, width: 21, height: 21,
                borderRadius: "50%", background: "#fff", transition: "left .15s",
              }} />
            </button>
          </div>

          {schedule.enabled && (
            <div className="grid grid-cols-2 gap-3 mt-4" data-testid="appearance-schedule-times">
              <label className="block">
                <span className="fz-sub text-[11px] uppercase tracking-wide">Dark from</span>
                <select data-testid="appearance-schedule-dark-hour"
                  value={schedule.dark_hour}
                  onChange={(e) => setSchedule({ dark_hour: parseInt(e.target.value, 10) })}
                  className="fz-field mt-1 w-full rounded-xl px-3 py-2 text-sm">
                  {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="fz-sub text-[11px] uppercase tracking-wide">Light from</span>
                <select data-testid="appearance-schedule-light-hour"
                  value={schedule.light_hour}
                  onChange={(e) => setSchedule({ light_hour: parseInt(e.target.value, 10) })}
                  className="fz-field mt-1 w-full rounded-xl px-3 py-2 text-sm">
                  {HOURS.map((h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
                </select>
              </label>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
