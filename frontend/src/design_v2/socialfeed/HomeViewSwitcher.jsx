// Top-bar dropdown to switch the Home view: V1 (classic), V2 (Social · Light),
// V3 (Social · Dark). Available on every page via the shell header.
import { useState, useRef, useEffect } from "react";
import { LayoutGrid, Check, ChevronDown, Sun, Moon } from "lucide-react";
import { useHomeView } from "@/store/useHomeView";

const OPTIONS = [
  { key: "v1", label: "Classic", desc: "Original FUUSIC home", icon: LayoutGrid },
  { key: "v2", label: "Social · Light", desc: "Feed, light theme", icon: Sun },
  { key: "v3", label: "Social · Dark", desc: "Feed, dark theme", icon: Moon },
];

export default function HomeViewSwitcher({ dark = true }) {
  const homeView = useHomeView((s) => s.homeView);
  const setView = useHomeView((s) => s.setView);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const cur = OPTIONS.find((o) => o.key === homeView) || OPTIONS[1];
  const CurIcon = cur.icon;
  const panelBg = dark ? "#141829" : "#ffffff";
  const panelBorder = dark ? "rgba(255,255,255,.12)" : "#e4e7f0";
  const txt = dark ? "#f4f6ff" : "#101830";
  const txt2 = dark ? "#9aa3bf" : "#5c6880";

  return (
    <div ref={ref} style={{ position: "relative" }} data-testid="home-view-switcher">
      <button type="button" onClick={() => setOpen((v) => !v)}
        data-testid="home-view-switcher-btn"
        className="sf-press"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6, height: 36,
          padding: "0 10px", borderRadius: 999, cursor: "pointer",
          background: dark ? "rgba(255,255,255,.07)" : "#eef0f7",
          border: `1px solid ${dark ? "rgba(255,255,255,.12)" : "#e4e7f0"}`, color: txt,
        }}>
        <CurIcon size={15} />
        <span style={{ fontSize: 12, fontWeight: 800, whiteSpace: "nowrap" }}>{cur.label}</span>
        <ChevronDown size={13} style={{ opacity: .7 }} />
      </button>
      {open && (
        <div className="sf-fade-in" style={{
          position: "absolute", right: 0, top: 44, width: 236, zIndex: 80,
          background: panelBg, border: `1px solid ${panelBorder}`, borderRadius: 16,
          boxShadow: "0 12px 40px rgba(0,0,0,.35)", padding: 6, overflow: "hidden",
        }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: ".12em", textTransform: "uppercase", color: txt2, padding: "8px 10px 4px" }}>
            Choose your home view
          </div>
          {OPTIONS.map((o) => {
            const Icon = o.icon; const active = o.key === homeView;
            return (
              <button key={o.key} type="button"
                data-testid={`home-view-opt-${o.key}`}
                onClick={() => { setView(o.key); setOpen(false); }}
                className="sf-press"
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 10,
                  padding: "9px 10px", borderRadius: 11, cursor: "pointer",
                  background: active ? (dark ? "rgba(168,85,247,.16)" : "#efe9ff") : "transparent",
                  border: "none", textAlign: "left", color: txt,
                }}>
                <span style={{ width: 30, height: 30, borderRadius: 9, display: "grid", placeItems: "center", background: active ? "linear-gradient(135deg,#a855f7,#ec4899)" : (dark ? "rgba(255,255,255,.06)" : "#f0f2f8") }}>
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
