// Phase K.7b — Promo banner card.  Landscape (16:6-ish) image-backed
// banner with dark gradient mask + bottom-left text overlay.
//
// Used in the Home "promo strip" — replaces the previously-portrait
// purple Try Chat card + the two stacked BannerAdSlots.
//
// Props
// ─────
//   imageUrl   - background image (served via /api/static/landing_images/<key>.png)
//   eyebrow    - tiny uppercase tag above the title
//   title      - main CTA text (white, bold)
//   body       - one-line descriptor
//   accent     - hex color for the eyebrow tint (default cyan)
//   onClick    - optional click handler
//   to         - optional react-router path; if set, wraps in a Link
//   testId     - data-testid for the outer element

import React from "react";
import { Link } from "react-router-dom";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function resolveImg(u) {
  if (!u) return null;
  if (u.startsWith("http")) return u;
  if (u.startsWith("/api/")) return `${BACKEND_URL}${u}`;
  return u;
}

// Phase STATIC.BOOT (2026-07-31) — swap CSS-background to a real
// gradient fallback when the image URL 404s in prod.  We keep the
// CSS-background style for perf (no extra <img> element), and use a
// hidden `Image()` probe to detect failure.  When the probe fails,
// state flips and the div falls back to `fallbackGradient`.
function useImageProbe(url) {
  const [state, setState] = React.useState(url ? "loading" : "empty");
  React.useEffect(() => {
    if (!url) { setState("empty"); return; }
    setState("loading");
    const im = new Image();
    let cancelled = false;
    im.onload  = () => { if (!cancelled) setState("ok"); };
    im.onerror = () => { if (!cancelled) setState("error"); };
    im.src = url;
    return () => { cancelled = true; im.onload = im.onerror = null; };
  }, [url]);
  return state;
}


export default function PromoBannerCard({
  imageUrl,
  eyebrow,
  title,
  body,
  accent = "#00d1ff",
  onClick,
  to,
  testId = "promo-banner",
  fallbackGradient = "linear-gradient(135deg,#6366f1 0%,#8b5cf6 100%)",
}) {
  const bg = resolveImg(imageUrl);
  const probe = useImageProbe(bg);
  const useImage = bg && probe === "ok";
  const content = (
    <div
      data-testid={testId}
      data-img-state={probe}
      onClick={onClick}
      style={{
        position: "relative",
        aspectRatio: "16 / 6",
        minHeight: 132,
        maxHeight: 200,
        borderRadius: 14,
        overflow: "hidden",
        cursor: onClick || to ? "pointer" : "default",
        border: "1px solid rgba(255,255,255,0.08)",
        background: useImage
          ? `linear-gradient(to right, rgba(8,10,18,0.85) 0%, rgba(8,10,18,0.55) 55%, rgba(8,10,18,0.15) 100%), url("${bg}") center/cover no-repeat`
          : fallbackGradient,
        transition: "transform 150ms ease-out, box-shadow 150ms ease-out",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-2px)";
        e.currentTarget.style.boxShadow = "0 14px 40px -10px rgba(0,0,0,0.6)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          padding: "16px 18px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
          color: "#fff",
        }}
      >
        {eyebrow && (
          <div
            data-testid={`${testId}-eyebrow`}
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: accent,
              marginBottom: 4,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          data-testid={`${testId}-title`}
          style={{
            fontSize: 17,
            fontWeight: 800,
            lineHeight: 1.2,
            letterSpacing: "-0.01em",
            marginBottom: 4,
            textShadow: "0 1px 6px rgba(0,0,0,0.4)",
          }}
        >
          {title}
        </div>
        {body && (
          <div
            data-testid={`${testId}-body`}
            style={{
              fontSize: 12,
              opacity: 0.88,
              maxWidth: "85%",
              textShadow: "0 1px 4px rgba(0,0,0,0.45)",
            }}
          >
            {body}
          </div>
        )}
      </div>
    </div>
  );
  if (to) {
    return (
      <Link to={to} style={{ textDecoration: "none", display: "block" }}>
        {content}
      </Link>
    );
  }
  return content;
}
