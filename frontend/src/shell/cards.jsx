// Card grammar (web) — fixed shapes per content type so users identify
// content by silhouette. All theme-token driven (no hardcoded colors).
import React from "react";
import { Link } from "react-router-dom";
import { Play, Star, MapPin, Coins, ChevronRight } from "lucide-react";
import { LiveDot } from "@/shell/primitives";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
export function absUrl(u) {
  if (!u || u === "null" || u === "undefined") return null;
  return u.startsWith("http") ? u : `${BACKEND}${u}`;
}

function Cover({ src, alt, className = "", children }) {
  const [broken, setBroken] = React.useState(false);
  const url = absUrl(src);
  return (
    <div className={`relative overflow-hidden bg-[var(--bg-base)] ${className}`}>
      {url && !broken ? (
        <img src={url} alt={alt || ""} loading="lazy" onError={() => setBroken(true)}
          className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0"
          style={{ background: "linear-gradient(135deg, var(--accent-electric), var(--accent-magenta))" }} />
      )}
      {children}
    </div>
  );
}

// ── ShelfHeader — title + mono context suffix ──────────────────────────
export function ShelfHeader({ title, suffix, linkTo, linkLabel = "See all", testId }) {
  return (
    <div className="flex items-end justify-between mb-3" data-testid={testId}>
      <div className="flex items-baseline gap-2 min-w-0">
        <h2 className="font-display font-bold text-lg sm:text-xl tracking-display-tight truncate">
          {title}
        </h2>
        {suffix && (
          <span className="hidden sm:inline text-[10px] font-mono uppercase tracking-widest text-text-secondary">
            · {suffix}
          </span>
        )}
      </div>
      {linkTo && (
        <Link to={linkTo}
          className="shrink-0 text-xs font-mono uppercase tracking-widest text-text-secondary hover:text-accent-electric transition-colors duration-150">
          {linkLabel} →
        </Link>
      )}
    </div>
  );
}

// ── ShowCard16x9 — live shows, episodes, podcasts ──────────────────────
export function ShowCard16x9({ title, station, city, meta, live, duration, image, onOpen, testId }) {
  return (
    <button type="button" onClick={onOpen} data-testid={testId}
      className="group text-left w-full">
      <Cover src={image} alt={title} className="aspect-video rounded-[14px]">
        <div className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 transition-opacity duration-150 bg-black/30">
          <span className="w-12 h-12 rounded-full bg-accent-electric text-black grid place-items-center">
            <Play size={20} fill="currentColor" />
          </span>
        </div>
        {live ? (
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-black/70 text-[10px] font-black uppercase tracking-widest text-accent-live">
            <LiveDot /> Live
          </span>
        ) : duration ? (
          <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/75 text-[10px] font-mono text-white">
            {duration}
          </span>
        ) : null}
      </Cover>
      <div className="mt-2">
        <div className="font-display font-extrabold text-[13.5px] leading-snug tracking-display-tight line-clamp-2">
          {title}
        </div>
        <div className="mt-0.5 text-xs text-text-secondary truncate">
          {[station, city, meta].filter(Boolean).join(" · ")}
        </div>
      </div>
    </button>
  );
}

// ── ClipCard9x16 — clips / highlights / merchant vertical video ────────
export function ClipCard9x16({ title, channel, views, image, sponsored, onOpen, testId }) {
  return (
    <button type="button" onClick={onOpen} data-testid={testId} className="group text-left w-full">
      <Cover src={image} alt={title} className="aspect-[9/16] rounded-[14px]">
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
        {sponsored && (
          <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded bg-black/70 text-[9px] font-black uppercase tracking-widest text-accent-electric">
            Sponsored
          </span>
        )}
        {views != null && (
          <span className="absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/60 text-[10px] font-mono text-white">
            <Play size={9} fill="currentColor" /> {views}
          </span>
        )}
        <div className="absolute inset-x-0 bottom-0 p-2.5">
          <div className="text-white font-bold text-[12.5px] leading-tight line-clamp-2" style={{ textShadow: "0 1px 6px rgba(0,0,0,0.6)" }}>
            {title}
          </div>
        </div>
      </Cover>
      {channel && <div className="mt-1.5 text-xs text-text-secondary truncate px-0.5">{channel}</div>}
    </button>
  );
}

// ── VenueCard — Shop & Eat venues ──────────────────────────────────────
export function VenueCard({ name, category, distance, rating, earn, image, status, onOpen, testId }) {
  const statusPill = status === "onair"
    ? { label: "On air now", cls: "text-accent-gold" }
    : status === "sponsored"
      ? { label: "Sponsored", cls: "text-accent-electric" }
      : null;
  return (
    <button type="button" onClick={onOpen} data-testid={testId} className="group text-left w-full rl-card overflow-hidden hover:-translate-y-0.5 transition-transform duration-150">
      <Cover src={image} alt={name} className="aspect-[16/10]">
        {statusPill && (
          <span className={`absolute top-2 left-2 px-2 py-0.5 rounded-full bg-black/70 text-[10px] font-black uppercase tracking-widest ${statusPill.cls}`}>
            {statusPill.label}
          </span>
        )}
        {earn != null && (
          <span className="absolute bottom-2 right-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-black" style={{ background: "rgba(0,0,0,0.6)", color: "#FFD27A" }}>
            <Coins size={12} /> Earn {earn}
          </span>
        )}
      </Cover>
      <div className="p-3">
        <div className="font-display font-bold text-sm tracking-display-tight truncate">{name}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-text-secondary">
          <span className="truncate">{[category, distance].filter(Boolean).join(" · ")}</span>
          {rating != null && (
            <span className="ml-auto inline-flex items-center gap-0.5 text-accent-gold shrink-0">
              <Star size={11} fill="currentColor" /> {rating}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

// ── NewsRow — thumbnail-left compact ───────────────────────────────────
export function NewsRow({ title, source, time, image, onOpen, testId }) {
  return (
    <button type="button" onClick={onOpen} data-testid={testId} className="group flex items-center gap-3 w-full text-left rl-card p-2.5 hover:-translate-y-0.5 transition-transform duration-150">
      <Cover src={image} alt={title} className="w-24 h-16 rounded-[10px] shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-[13px] leading-snug line-clamp-2">{title}</div>
        <div className="mt-1 text-[11px] font-mono uppercase tracking-widest text-text-secondary truncate">
          {[source, time].filter(Boolean).join(" · ")}
        </div>
      </div>
      <ChevronRight size={16} className="text-text-secondary shrink-0" />
    </button>
  );
}

// ── Row layouts ────────────────────────────────────────────────────────
export function HScroll({ children, itemClass = "" }) {
  return (
    <div className="-mx-2 px-2 overflow-x-auto no-scrollbar">
      <div className="flex gap-3 pb-1 snap-x">
        {React.Children.map(children, (c) => (
          <div className={`snap-start shrink-0 ${itemClass}`}>{c}</div>
        ))}
      </div>
    </div>
  );
}
