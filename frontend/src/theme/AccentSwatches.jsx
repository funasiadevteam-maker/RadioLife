// Accent colour picker — recolours the app's brand elements. Reused in
// onboarding and the Appearance settings page.
import React from "react";
import { Check } from "lucide-react";
import { useTheme } from "./useTheme";

export const ACCENT_SWATCHES = [
  { k: "violet", label: "Violet", color: "#A855F7", on: "#ffffff" },
  { k: "coral", label: "Coral", color: "#F26B2A", on: "#2A1200" },
  { k: "teal", label: "Teal", color: "#0D9488", on: "#ffffff" },
  { k: "amber", label: "Amber", color: "#D97706", on: "#231600" },
  { k: "blue", label: "Blue", color: "#2563EB", on: "#ffffff" },
];

export default function AccentSwatches({ testIdPrefix = "accent", size = 40 }) {
  const { accent, setAccent } = useTheme();
  return (
    <div className="flex items-center gap-3 flex-wrap" data-testid={`${testIdPrefix}-swatches`}>
      {ACCENT_SWATCHES.map((a) => {
        const on = accent === a.k;
        return (
          <button key={a.k} type="button" onClick={() => setAccent(a.k)}
            data-testid={`${testIdPrefix}-${a.k}`} aria-pressed={on} title={a.label}
            className="rounded-full grid place-items-center transition"
            style={{
              width: size, height: size, background: a.color,
              boxShadow: on ? `0 0 0 3px rgba(255,255,255,0.9), 0 0 0 5px ${a.color}` : "none",
              outline: on ? "none" : "2px solid transparent",
            }}>
            {on && <Check size={Math.round(size * 0.45)} color={a.on} strokeWidth={3} />}
          </button>
        );
      })}
    </div>
  );
}
