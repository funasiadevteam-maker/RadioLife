/** Phase 42-E2.1 — Home feature tile card.
 *  Cinematic hero image (gpt-image-1 output) + title + tagline + CTA.
 *  Falls back to a coloured gradient block when the tile has no image
 *  yet (cold start before the seed script runs).
 *
 *  Phase STATIC.BOOT (2026-07-31) — also falls back to the gradient
 *  when the image URL 404s in prod, via a hidden Image() probe so
 *  broken CSS backgrounds don't show as dead ink.
 */
import React from "react";
import { useNavigate } from "react-router-dom";
import {
  Trophy, Gamepad2, Radio, Coins, Map, BadgeCheck, Sparkles,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

const ICON_BY_NAME = {
  Trophy, Gamepad2, Radio, Coins, Map, BadgeCheck,
};

const ACCENT_STYLES = {
  magenta: { tint: "rgba(236,72,153,0.65)",  glow: "rgba(236,72,153,0.18)" },
  cyan:      { tint: "rgba(34,211,238,0.65)",  glow: "rgba(34,211,238,0.18)" },
  gold:      { tint: "rgba(245,158,11,0.65)",  glow: "rgba(245,158,11,0.18)" },
  lime:      { tint: "rgba(132,204,22,0.65)",  glow: "rgba(132,204,22,0.18)" },
  indigo:  { tint: "rgba(99,102,241,0.65)",    glow: "rgba(99,102,241,0.18)" },
  rose:      { tint: "rgba(244,63,94,0.65)",    glow: "rgba(244,63,94,0.18)" },
};

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

export default function FeatureTileCard({ tile }) {
  const navigate = useNavigate();
  const Icon = ICON_BY_NAME[tile.lucide_icon] || Sparkles;
  const accent = ACCENT_STYLES[tile.accent] || ACCENT_STYLES.cyan;
  const imgUrl = tile.image_url
    ? (tile.image_url.startsWith("http")
        ? tile.image_url : `${BACKEND_URL}${tile.image_url}`)
    : null;
  const probe = useImageProbe(imgUrl);
  const hasImage = !!imgUrl && probe === "ok";

  return (
    <button
      type="button"
      data-testid={`home-tile-${tile.tile_id}`}
      data-has-image={hasImage ? "true" : "false"}
      data-img-state={probe}
      onClick={() => navigate(tile.route)}
      className="relative w-full text-left overflow-hidden
                              rounded-2xl border border-white/[0.06]
                              transition-transform duration-200
                              hover:-translate-y-1 hover:border-white/[0.18]
                              focus:outline-none focus:ring-2 focus:ring-white/30
                              group"
      style={{ minHeight: 220, aspectRatio: "16/10" }}
    >
      {/* Background — real image or accent-tinted gradient fallback. */}
      <div
        aria-hidden="true"
        className="absolute inset-0"
        style={hasImage
          ? { backgroundImage: `url("${imgUrl}")`,
                  backgroundSize: "cover",
                  backgroundPosition: "center" }
          : { background:
              `radial-gradient(120% 80% at 30% 20%, ${accent.glow}, transparent 60%),
                #0e0e12` }}
      />
      {/* Bottom-up dark gradient so the copy stays legible. */}
      <div aria-hidden="true"
                className="absolute inset-0 bg-gradient-to-t
                                          from-black/90 via-black/55 to-black/20" />
      {/* Accent rim glow. */}
      <div aria-hidden="true"
                className="absolute inset-0 opacity-0 group-hover:opacity-100
                                          transition-opacity duration-200"
                style={{ boxShadow: `inset 0 0 90px ${accent.glow}` }} />

      <div className="relative z-[1] h-full w-full
                                      flex flex-col justify-end p-5 lg:p-6">
        <div className="inline-flex items-center gap-2 mb-3
                                        text-[10px] font-mono uppercase tracking-widest"
                  style={{ color: accent.tint }}>
          <Icon size={14} />
          <span data-testid={`home-tile-${tile.tile_id}-eyebrow`}>
            {tile.cta_text}
          </span>
        </div>
        <h3 className="text-white text-2xl font-display font-bold
                                      tracking-display-tight mb-1.5">
          {tile.title}
        </h3>
        <p className="text-white/70 text-sm leading-snug max-w-[26ch]">
          {tile.tagline}
        </p>
      </div>
    </button>
  );
}
