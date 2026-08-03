// Channel switcher — horizontal scroll strip above the now-playing card.
// Renders chips with cover color + hosts; click switches the session.
// Phase 3: premium_only chips get a gold accent + lock icon for free users.
// Phase 10c: respects the backend `access` field (ambassador-tier locks).

import { useEffect, useRef } from "react";
import { Loader2, Lock, Crown, Sparkles, ChevronRight, Play } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function ChannelSwitcher({
  channels, activeSlug, switching, onSwitch, onLocked, isPremium,
}) {
  const stripRef = useRef(null);
  const activeRef = useRef(null);

  useEffect(() => {
    if (activeRef.current && stripRef.current) {
      activeRef.current.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    }
  }, [activeSlug]);

  // Phase 15c — keyboard ←/→ scrolls the strip by ~one card-width when
  // the strip itself has focus. The chevron button (right side) advances
  // one card; clicking past the end is a no-op (overflow stops naturally).
  const scrollByCard = (dir) => {
    const el = stripRef.current;
    if (!el) return;
    const card = el.querySelector(".channel-chip");
    const step = card ? card.getBoundingClientRect().width + 10 /* gap */ : 240;
    el.scrollBy({ left: step * dir, behavior: "smooth" });
  };
  const onKey = (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); scrollByCard(+1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); scrollByCard(-1); }
  };

  return (
    <div className="channel-strip-wrap" data-testid="channel-switcher">
      <div className="channel-strip-label mono">CHANNELS</div>
      <div className="channel-strip" ref={stripRef}
                tabIndex={0} onKeyDown={onKey}
                aria-label="Channels carousel — use arrow keys to scroll">
        {(channels || []).map((c) => {
          const active = c.slug === activeSlug;
          const isSwitching = switching === c.slug;
          const hostsLine = c.hosts?.length
            ? c.hosts.map((h) => h.name).join(" × ")
            : "Auto";
          // Phase 10c — backend tells us whether this user has access.
          const access = c.access || { allowed: true };
          const locked = access.allowed === false;
          const upgradePath = access.upgrade_path;
          const tier = c.exclusivity_tier || "free";
          const isPremiumTier = tier === "premium" || c.premium_only;
          const isAmbassadorTier = tier && tier.startsWith("ambassador_");
          const LockIcon = upgradePath === "earn_badges" ? Sparkles
            : upgradePath === "premium" ? Crown
            : Lock;
          const badgeLabel = isPremiumTier ? "VIP"
            : isAmbassadorTier ? tier.replace("ambassador_", "").toUpperCase()
            : "LOCKED";
          const thumb = c.thumbnail_url
            ? (c.thumbnail_url.startsWith("http") ? c.thumbnail_url : `${BACKEND_URL}${c.thumbnail_url}`)
            : null;
          return (
            <button
              key={c.slug}
              ref={active ? activeRef : null}
              type="button"
              className={`channel-chip ${active ? "is-on" : ""} ${isSwitching ? "is-switching" : ""} ${isPremiumTier ? "is-premium" : ""} ${isAmbassadorTier ? "is-ambassador" : ""} ${locked ? "is-locked" : ""} ${thumb ? "has-thumb" : ""}`}
              style={{
                "--ch-color": c.cover_color || "#ff2d95",
                ...(thumb ? { "--ch-thumb": `url("${thumb}")` } : {}),
              }}
              onClick={() => {
                if (active || switching) return;
                if (locked) { onLocked && onLocked(c); return; }
                onSwitch(c.slug, c);
              }}
              disabled={!!switching}
              data-testid={`channel-chip-${c.slug}`}
              aria-pressed={active}
              aria-disabled={locked}
            >
              {thumb && (
                <div
                  className="ch-thumb-bg"
                  data-testid={`channel-chip-thumb-${c.slug}`}
                  style={{ backgroundImage: `url("${thumb}")` }}
                  aria-hidden
                />
              )}
              <div className="ch-color-bar" />
              {(isPremiumTier || isAmbassadorTier) && (
                <div className="ch-premium-badge mono"
                      data-testid={`channel-vip-badge-${c.slug}`}>
                  {locked ? <Lock size={9} /> : <Crown size={9} />}
                  {badgeLabel}
                </div>
              )}
              <div className="ch-chip-body">
                <div className="ch-name">{c.name}</div>
                {c.tagline && <div className="ch-tagline">{c.tagline}</div>}
                <div className="ch-hosts mono">with {hostsLine}</div>
              </div>
              {!isSwitching && !locked && (
                <div
                  className="ch-play-overlay"
                  data-testid={`channel-chip-play-${c.slug}`}
                  aria-hidden
                >
                  <Play size={18} strokeWidth={2.5} fill="currentColor" />
                </div>
              )}
              {isSwitching && (
                <div className="ch-switching">
                  <Loader2 size={14} className="spin" />
                  <span>TUNING…</span>
                </div>
              )}
              {active && !isSwitching && <div className="ch-live mono">LIVE</div>}
              {locked && !isSwitching && (
                <div className="ch-locked-overlay mono"
                      data-testid={`channel-lock-overlay-${c.slug}`}>
                  <LockIcon size={10} /> {upgradePath === "earn_badges"
                                                  ? "EARN TO UNLOCK"
                                                  : "UPGRADE TO UNLOCK"}
                </div>
              )}
            </button>
          );
        })}
      </div>
      {/* Phase 15c — visible right-edge chevron. The fade-mask + chevron
            are scoped to .radio-page-v2 in radio-page-v2.css. */}
      <button type="button" className="channel-strip-chevron"
                  aria-label="Scroll channels right"
                  onClick={() => scrollByCard(+1)}
                  data-testid="channel-strip-chevron">
        <ChevronRight size={18} strokeWidth={2} />
      </button>
    </div>
  );
}
