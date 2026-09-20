// Phase 15c — desktop-only right rail for /radio.
// Mounted via a CSS grid wrapper in Radio.js; hidden below the `lg`
// breakpoint so the mobile vertical full-screen player from 15b is
// unchanged. Strictly read-only on the listening side — no upcoming
// queue, no track scrubbing — per non-interactive radio compliance.

import React, { useEffect, useState } from "react";
import axios from "axios";
import { ChevronDown, ChevronUp, Mic, Radio as RadioIcon,
                Sparkles, History } from "lucide-react";
import { API } from "@/AuthContext";
import { Card, Chip, LiveDot } from "@/shell/primitives";

export default function RadioRail({ user, currentChannel, recentTracks }) {
  return (
    <aside data-testid="radio-rail"
                className="hidden lg:flex flex-col gap-4 w-full">
      <LyricsPanel />
      <StationInfo user={user} channel={currentChannel} />
      <RecentlyPlayed tracks={recentTracks} />
    </aside>
  );
}

function LyricsPanel() {
  const [open, setOpen] = useState(true);
  return (
    <Card className="overflow-hidden" data-testid="radio-rail-lyrics">
      <button type="button"
                  onClick={() => setOpen((v) => !v)}
                  className="w-full px-5 py-4 flex items-center
                                  justify-between hover:bg-white/[0.02]
                                  transition-colors duration-150">
        <div className="flex items-center gap-2">
          <Mic size={16} className="text-accent-electric" />
          <span className="font-display font-bold tracking-display-tight">
            Lyrics
          </span>
        </div>
        {open
          ? <ChevronUp   size={16} className="text-text-secondary" />
          : <ChevronDown size={16} className="text-text-secondary" />}
      </button>
      {open && (
        <div className="px-5 pb-5 border-t border-white/[0.04]
                              text-sm text-text-secondary">
          <p className="mt-4">
            Lyrics will sync when available for this track.
          </p>
        </div>
      )}
    </Card>
  );
}

function StationInfo({ user, channel }) {
  // Pulls the active channel object when we have one, else falls back to
  // generic copy. We don't refetch — the parent passes whatever it has.
  const name = channel?.name || channel?.slug || "FUUSIC";
  const tagline = channel?.tagline || "Personalized AI radio";
  const market = (user?.market || "dubai").toUpperCase();
  const hour = new Date().getHours();
  const daypart =
    hour < 6  ? "Late Night Mehfil" :
    hour < 11 ? "Morning Caravan"    :
    hour < 15 ? "Lunch Rush"          :
    hour < 19 ? "Evening Drive"       :
                "Night Lounge";
  return (
    <Card className="p-5" data-testid="radio-rail-station">
      <div className="flex items-center gap-2">
        <RadioIcon size={16} className="text-accent-magenta" />
        <span className="font-display font-bold tracking-display-tight">
          Station
        </span>
      </div>
      <div className="mt-3 font-display font-bold text-xl
                            tracking-display-tight">{name}</div>
      <div className="mt-1 text-sm text-text-secondary">{tagline}</div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Chip tone="live"><LiveDot /> on air</Chip>
        <Chip tone="neutral">{daypart}</Chip>
        <Chip tone="neutral">{market}</Chip>
      </div>
    </Card>
  );
}

function RecentlyPlayed({ tracks }) {
  // Last 5, read-only. Compliance: this is NOT a queue — no upcoming.
  // Falls back to fetching from a lightweight endpoint if the parent
  // didn't pass anything. We tolerate failure silently.
  const [items, setItems] = useState(tracks || []);
  useEffect(() => {
    if (tracks && tracks.length) { setItems(tracks); return; }
    let cancelled = false;
    axios.get(`${API}/radio/recent?limit=5`)
              .then((r) => { if (!cancelled) setItems(r.data?.tracks || []); })
              .catch(() => { /* swallow — show empty state */ });
    return () => { cancelled = true; };
  }, [tracks]);
  return (
    <Card className="p-5" data-testid="radio-rail-recent">
      <div className="flex items-center gap-2">
        <History size={16} className="text-accent-gold" />
        <span className="font-display font-bold tracking-display-tight">
          Recently played
        </span>
      </div>
      {items.length === 0 ? (
        <div className="mt-4 text-sm text-text-secondary flex items-center gap-2">
          <Sparkles size={14} className="text-accent-electric" />
          Your last 5 tracks will appear here.
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.slice(0, 5).map((t, i) => (
            <li key={`${t?.id || t?.title || i}-${i}`}
                      className="flex items-center justify-between text-sm">
              <div className="min-w-0 pr-3">
                <div className="truncate">{t?.title || "Untitled"}</div>
                <div className="truncate text-xs text-text-secondary">
                  {t?.artist || "—"}
                </div>
              </div>
              <span className="text-xs font-mono text-text-secondary
                                          shrink-0">#{i + 1}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
