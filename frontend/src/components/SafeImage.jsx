// Phase STATIC.BOOT.v2 (2026-08-01) — SafeImage component.
//
// Drop-in replacement for `<img>` that NEVER shows a broken-image
// icon.  When the URL fails to load OR is empty, renders a gradient
// placeholder with an optional icon glyph or initial letters.
//
// Usage:
//   <SafeImage src={url} alt="..." className="..." fallbackKind="station" />
//
// Props:
//   src                 — image URL (may be null/undefined/"")
//   alt                 — accessibility alt text
//   className         — passed to both <img> and the fallback div
//   fallbackKind    — one of "station" | "podcast" | "game" | "business" |
//                                "persona" | "ad" | "generic"    (default "generic")
//   fallbackText    — used to derive initials + palette (defaults to alt)
//   onLoad, onError — passthrough handlers (fire on the underlying image)
//   ...rest              — any other <img> attrs
//
// Rendering:
//   probe === "ok"   → renders <img src={src}>
//   otherwise           → renders fallback div with gradient + text/icon

import React from "react";
import {
  Radio, Mic2, Gamepad2, Store, User, Megaphone, Image as ImageIcon,
} from "lucide-react";
import { useImageProbe } from "@/hooks/useImageProbe";

const ICON_BY_KIND = {
  station:  Radio,
  podcast:  Mic2,
  game:      Gamepad2,
  business: Store,
  persona:  User,
  ad:          Megaphone,
  generic:  ImageIcon,
};

// Palette pool — each string is a `linear-gradient(...)`.  We pick
// deterministically from `text` so re-renders show the same colour.
const PALETTE_POOL = [
  "linear-gradient(135deg,#ec4899 0%,#8b5cf6 100%)",  // magenta → violet
  "linear-gradient(135deg,#22d3ee 0%,#6366f1 100%)",  // cyan → indigo
  "linear-gradient(135deg,#f59e0b 0%,#ef4444 100%)",  // amber → red
  "linear-gradient(135deg,#84cc16 0%,#0ea5e9 100%)",  // lime → sky
  "linear-gradient(135deg,#a855f7 0%,#ec4899 100%)",  // purple → pink
  "linear-gradient(135deg,#0ea5e9 0%,#8b5cf6 100%)",  // sky → purple
  "linear-gradient(135deg,#f97316 0%,#eab308 100%)",  // orange → yellow
  "linear-gradient(135deg,#14b8a6 0%,#22c55e 100%)",  // teal → green
];

function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h) + s.charCodeAt(i) | 0;
  return Math.abs(h);
}

function initials(text) {
  if (!text || typeof text !== "string") return "";
  return text.trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0]?.toUpperCase() || "").join("");
}

export function SafeImage({
  src,
  alt = "",
  className = "",
  fallbackKind = "generic",
  fallbackText,
  onLoad,
  onError,
  showInitials = true,
  showGlyph = true,
  style,
  ...rest
}) {
  const probe = useImageProbe(src);
  const Icon = ICON_BY_KIND[fallbackKind] || ICON_BY_KIND.generic;
  const text = fallbackText || alt || "";
  const gradient = PALETTE_POOL[hashStr(text || fallbackKind) % PALETTE_POOL.length];
  const showFallback = probe !== "ok";

  if (showFallback) {
    return (
      <div
        role="img"
        aria-label={alt}
        data-safeimg="fallback"
        data-safeimg-kind={fallbackKind}
        data-safeimg-state={probe}
        className={className}
        style={{
          background: gradient,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "rgba(255,255,255,0.9)",
          textShadow: "0 1px 3px rgba(0,0,0,0.4)",
          fontWeight: 700,
          letterSpacing: 0.5,
          userSelect: "none",
          overflow: "hidden",
          ...style,
        }}
      >
        {showInitials && initials(text) ? (
          <span style={{ fontSize: "clamp(14px, 3vw, 32px)",
                                            fontFamily: "system-ui, sans-serif" }}>
            {initials(text)}
          </span>
        ) : showGlyph ? (
          <Icon size={28} strokeWidth={1.8} />
        ) : null}
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      style={style}
      data-safeimg="ok"
      onLoad={onLoad}
      onError={(e) => { if (onError) onError(e); }}
      {...rest}
    />
  );
}

export default SafeImage;
