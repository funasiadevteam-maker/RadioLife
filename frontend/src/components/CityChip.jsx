// Phase 15d — CityChip. Shows the resolved market in the top bar and
// opens a slide-out sheet that lets the user pick any of the 5 supported
// markets. Persists the override to /api/users/me/market when authed.
import React, { useState } from "react";
import { MapPin, Check, ChevronRight } from "lucide-react";
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useGeoStore } from "@/store/useGeoStore";

const MARKETS = [
  { key: "dubai",         label: "Dubai",         country: "United Arab Emirates" },
  { key: "new_york",      label: "New York",      country: "United States" },
  { key: "london",        label: "London",        country: "United Kingdom" },
  { key: "mumbai",        label: "Mumbai",        country: "India" },
  { key: "los_angeles",   label: "Los Angeles",   country: "United States" },
  { key: "dfw",           label: "Dallas",        country: "United States" },
];

export default function CityChip() {
  const market = useGeoStore((s) => s.market);
  const city = useGeoStore((s) => s.city);
  const source = useGeoStore((s) => s.source);
  const setMarket = useGeoStore((s) => s.setMarket);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(null);

  const display = city || (market || "—");

  const onPick = async (k) => {
    if (k === market) { setOpen(false); return; }
    setSaving(k);
    await setMarket(k);
    setSaving(null);
    setOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          data-testid="topbar-city-chip"
          className="inline-flex items-center gap-2 h-8 px-3 rounded-full
                            bg-white/[0.04] border border-white/[0.06] text-xs
                            font-mono uppercase tracking-widest text-text-secondary
                            hover:text-white hover:bg-white/[0.08] hover:border-white/[0.12]
                            transition-colors duration-150"
        >
          <MapPin size={12} className="text-accent-electric" />
          <span className="text-white">{display}</span>
          {source === "override" && (
            <span className="text-[9px] text-accent-electric/80">·set</span>
          )}
        </button>
      </SheetTrigger>
      <SheetContent
        side="right"
        data-testid="city-chip-sheet"
        className="w-full sm:w-[420px] bg-bg-elevated border-l border-white/[0.06]
                            text-white"
      >
        <SheetHeader>
          <SheetTitle className="font-display text-2xl tracking-display-tight">
            Change your city
          </SheetTitle>
          <SheetDescription className="text-text-secondary">
            BigFM personalises hosts, news and offers per market.
            Pick one — we'll remember it for you.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-2" data-testid="city-chip-list">
          {MARKETS.map((m) => {
            const active = m.key === market;
            return (
              <button
                key={m.key}
                type="button"
                disabled={!!saving}
                onClick={() => onPick(m.key)}
                data-testid={`city-option-${m.key}`}
                className={[
                  "w-full flex items-center justify-between gap-3 px-4 py-3",
                  "rounded-token-md border transition-colors duration-150",
                  active
                    ? "bg-accent-electric/10 border-accent-electric/40"
                    : "bg-white/[0.02] border-white/[0.06] hover:bg-white/[0.06]",
                ].join(" ")}
              >
                <div className="text-left">
                  <div className="font-medium">{m.label}</div>
                  <div className="text-xs text-text-secondary font-mono">
                    {m.country}
                  </div>
                </div>
                {active
                  ? <Check size={16} className="text-accent-electric" />
                  : saving === m.key
                    ? <span className="text-xs font-mono text-text-secondary">…</span>
                    : <ChevronRight size={16} className="text-text-secondary" />}
              </button>
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}
