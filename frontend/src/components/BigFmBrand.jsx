// FUUSIC — single source of truth for the primary brand lockup/wordmark.
// Renders the FUUSIC wordmark (no city suffix). Reads the name from the
// central brand config so it can be swapped in one place.
//
// `showCity` / `cityClassName` props are kept for backwards-compat with
// existing call-sites but are intentionally ignored — the FUUSIC brand is
// presented on its own (per the approved brand direction).
import React from "react";
import { BRAND } from "@/config/brand";

export default function BigFmBrand({
  showCity = true, // eslint-disable-line no-unused-vars
  variant = "lockup", // "lockup" (h1) | "inline" (span)
  className = "",
  cityClassName = "dxb", // eslint-disable-line no-unused-vars
  testId = "bigfm-brand",
}) {
  if (variant === "lockup") {
    return (
      <h1 className={className} data-testid={testId}>
        {BRAND.name}
      </h1>
    );
  }
  return (
    <span className={`brand-name ${className}`} data-testid={testId}>
      {BRAND.name}
    </span>
  );
}
