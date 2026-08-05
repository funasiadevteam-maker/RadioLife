// Phase 15d.2 — single source of truth for the "RadioLife <city>" brand lockup.
// Reads `geoCity` from useGeoStore so every page renders the listener's
// resolved market consistently. Anon visitors / marketing pages can omit
// the city suffix via `showCity={false}` (default true) — they fall back
// to plain "RadioLife" with no city, since we don't know the market yet.
//
// Replaces 5+ hardcoded `<h1>RadioLife Dubai</h1>` lockups across the app.
import React from "react";
import { useGeoStore } from "@/store/useGeoStore";

export default function BigFmBrand({
  showCity   = true,
  variant    = "lockup",   // "lockup" (h1) | "inline" (span)
  className  = "",
  cityClassName = "dxb",
  testId     = "bigfm-brand",
}) {
  const geoCity = useGeoStore((s) => s.city);
  // Anon visitor protection: only render the city span when we've actually
  // resolved one. `geoCity` is hydrated from localStorage at boot, but a
  // brand-new visitor on a marketing page may not have it yet.
  const city = showCity ? (geoCity || "") : "";
  const cityNode = city
    ? <span className={cityClassName} data-testid={`${testId}-city`}>{city}</span>
    : null;
  if (variant === "lockup") {
    return (
      <h1 className={className} data-testid={testId}>
        RadioLife{cityNode ? " " : ""}{cityNode}
      </h1>
    );
  }
  return (
    <span className={`brand-name ${className}`} data-testid={testId}>
      RadioLife{cityNode ? " " : ""}{cityNode}
    </span>
  );
}
