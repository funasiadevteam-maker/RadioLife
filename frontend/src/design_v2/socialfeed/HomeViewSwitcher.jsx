// Top-bar control: pick the global appearance (Light / Dark / System) and the
// home layout (Social Feed vs Classic). Appearance drives the WHOLE app via the
// global theme; layout only affects the Home route.
import { useState, useRef, useEffect } from "react";
import { Sun, Moon, Monitor, LayoutGrid, Newspaper, Check, ChevronDown } from "lucide-react";
import { useHomeView } from "@/store/useHomeView";
import { useThemeStore } from "@/theme/useTheme";

const APPEARANCE = [
  { key: "light", label: "Light", icon: Sun },
  { key: "dark", label: "Dark", icon: Moon },
  { key: "system", label: "System", icon: Monitor },
];
const LAYOUT = [
  { key: "v2", label: "Social Feed", desc: "Facebook-style activity wall", icon: Newspaper },
  { key: "v1", label: "Classic", desc: "Original FUUSIC home", icon: LayoutGrid },
];

function labelStyle(c) {
  return {
    fontSize: 10, fontWeight: 800, letterSpacing: ".12em",
    textTransform: "uppercase", color: c, padding: "8px 10px 4px",
  };
}

export default function HomeViewSwitcher() {
  const mode = useThemeStore((s) => s.mode);
  const theme = useThemeStore((s) => s.theme);
  const setMode = useThemeStore((s) => s.setMode);
  const homeView = useHomeView((s) => s.homeView);
  const setView = useHomeView((s) => s.setView);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const dark = theme === "dark";
  const layoutKey = homeView === "v1" ? "v1" : "v2";
  const curAppear = APPEARANCE.find((a) => a.key === mode) || APPEARANCE[0];
  const CurIcon = curAppear.icon;
  const panelBg = dark ? "#151B2B" : "#ffffff";
  const panelBorder = dark ? "rgba(255,255,255,.12)" : "#e4e7f0";
  const txt = dark ? "#f4f6ff" : "#101830";
  const txt2 = dark ? "#9aa3bf" : "#5c6880";
  const selectView = (k) => { if (k !== layoutKey) setView(k === "v1" ? "v1" : "v2"); setOpen(false); };

  return (
    <div ref={ref} style={{ position: "relative" }} data-testid="home-view-switcher">
      <button type="button" onClick={() => setOpen((v) => !v)}
        data-testid="home-view-switcher-btn" className="sf-press"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6, height: 36, padding: "0 10px",
          borderRadius: 999, cursor: "pointer", background: dark ? "rgba(255,255,255,.07)" : "#eef0f7",
          border: `1px solid ${dark ? "rgba(255,255,255,.12)" : "#e4e7f0"}`, color: txt,
        }}>
        <CurIcon size={15} />
        <span style={{ fontSize: 12, fontWeight: 800, whiteSpace: "nowrap" }}>{curAppear.label}</span>
        <ChevronDown size={13} style={{ opacity: .7 }} />
      </button>
      {open && (
        <div className="sf-fade-in" style={{
          position: "absolute", right: 0, top: 44, width: 248, zIndex: 80,
          background: panelBg, border: `1px solid ${panelBorder}`, borderRadius: 16,
          boxShadow: "0 12px 40px rgba(0,0,0,.35)", padding: 6, overflow: "hidden",
        }}>
          <div style={labelStyle(txt2)}>Appearance</div>
          <div style={{ display: "flex", gap: 6, padding: "2px 6px 8px" }}>
            {APPEARANCE.map((a) => {
              const Icon = a.icon; const active = a.key === mode;
              return (
                <button key={a.key} type="button" data-testid={`appearance-opt-${a.key}`}
                  onClick={() => setMode(a.key)} className="sf-press"
                  style={{
                    flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                    padding: "9px 4px", borderRadius: 11, cursor: "pointer", border: "none",
                    color: active ? "#fff" : txt,
                    background: active ? "linear-gradient(135deg,#a855f7,#ec4899)"
                      : (dark ? "rgba(255,255,255,.06)" : "#f0f2f8"),
                  }}>
                  <Icon size={16} color={active ? "#fff" : txt2} />
                  <span style={{ fontSize: 11, fontWeight: 800 }}>{a.label}</span>
                </button>
              );
            })}
          </div>
          <div style={labelStyle(txt2)}>Home layout</div>
          {LAYOUT.map((o) => {
            const Icon = o.icon; const active = o.key === layoutKey;
            return (
              <button key={o.key} type="button" data-testid={`home-view-opt-${o.key}`}
                onClick={() => selectView(o.key)} className="sf-press"
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "9px 10px",
                  borderRadius: 11, cursor: "pointer", border: "none", textAlign: "left", color: txt,
                  background: active ? (dark ? "rgba(168,85,247,.16)" : "#efe9ff") : "transparent",
                }}>
                <span style={{
                  width: 30, height: 30, borderRadius: 9, display: "grid", placeItems: "center",
                  background: active ? "linear-gradient(135deg,#a855f7,#ec4899)"
                    : (dark ? "rgba(255,255,255,.06)" : "#f0f2f8"),
                }}>
                  <Icon size={15} color={active ? "#fff" : txt2} />
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: "block", fontSize: 13, fontWeight: 800 }}>{o.label}</span>
                  <span style={{ display: "block", fontSize: 11, color: txt2 }}>{o.desc}</span>
                </span>
                {active && <Check size={15} color="#a855f7" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
