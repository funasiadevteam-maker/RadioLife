// 3-way design switcher: Classic A (original) · Classic B (new consumer
// nav) · New Look (FUUSIC). Replaces the old 2-state "Try new look".
import React, { useEffect, useRef, useState } from "react";
import { Sparkles, Check, ChevronDown } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

const OPTIONS = [
  { key: "legacy",    label: "Classic A", hint: "Original shell" },
  { key: "classic_b", label: "Classic B", hint: "New consumer nav" },
  { key: "radiolife", label: "New Look",  hint: "FUUSIC design" },
  { key: "new_look_v2", label: "New Look V2", hint: "Premium dark streaming" },
];

export default function VariantSwitcher() {
  const { user } = useAuth();
  const variant = useDesignVariantStore((s) => s.variant);
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!user || user.role !== "admin") return null;
  const current = OPTIONS.find((o) => o.key === variant) || OPTIONS[0];
  const isNew = variant === "radiolife" || variant === "classic_b";

  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((v) => !v)}
        data-testid="variant-switcher-btn" aria-haspopup="true" aria-expanded={open}
        title="Switch design"
        className={[
          "h-9 px-3 rounded-full border text-[11px] font-semibold uppercase tracking-widest",
          "transition-all duration-150 flex items-center gap-1.5 whitespace-nowrap",
          isNew ? "text-white border-transparent shadow-md" : "text-text-secondary hover:text-text-primary",
        ].join(" ")}
        style={isNew ? { background: "linear-gradient(135deg, #A020F0, #EC4899)" } : { borderColor: "var(--line)" }}>
        <Sparkles size={12} />
        <span className="hidden xl:inline">{current.label}</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <div data-testid="variant-switcher-menu" style={{ borderColor: "var(--line)" }}
          className="absolute right-0 mt-2 w-56 rl-card p-1.5 z-50 border bg-bg-elevated rounded-token-card shadow-2xl">
          <div className="px-3 pt-1 pb-2 text-[10px] font-mono uppercase tracking-widest text-text-secondary">
            Design
          </div>
          {OPTIONS.map((o) => {
            const active = variant === o.key;
            return (
              <button key={o.key} type="button"
                data-testid={`variant-opt-${o.key}`}
                onClick={() => { setVariant(o.key); setOpen(false); }}
                className={[
                  "w-full flex items-center gap-3 px-3 h-11 rounded-token-md text-left transition-colors duration-150",
                  active ? "bg-accent-electric/15 text-accent-electric" : "text-text-primary hover:bg-[var(--bg-glass)]",
                ].join(" ")}>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold">{o.label}</div>
                  <div className="text-[11px] text-text-secondary truncate">{o.hint}</div>
                </div>
                {active && <Check size={15} className="shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
