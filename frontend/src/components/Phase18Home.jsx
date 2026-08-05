/**
 * Phase 18 home-hero add-ons: top-game card, top-channel card,
 * favorites strip with "+" picker, and bottom-bar quick-channel strip.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Heart, Plus, X, Gamepad2, Play, ChevronRight, Music2,
} from "lucide-react";
import {
  useFavoritesStore, fetchAutoplaySuggestion,
  fetchTopChannelRec, fetchTopGameRec,
} from "@/store/useFavoritesStore";
import SafeImage from "@/components/SafeImage";

const ROOT = process.env.REACT_APP_BACKEND_URL || "";
const API  = ROOT + "/api";

function thumb(url) { return url ? `${ROOT}${url}` : null; }


// ─── Top-channel recommendation card ────────────────────────────────
export function TopChannelRecCard() {
  const navigate = useNavigate();
  const [rec, setRec] = useState(null);
  const [imgFail, setImgFail] = useState(false);
  useEffect(() => { fetchTopChannelRec().then(setRec); }, []);
  if (!rec) return null;
  const minutes = rec.minutes_listened_30d || 0;
  const hours    = (minutes / 60).toFixed(1);
  const showImg = !!rec.thumbnail_url && !imgFail;
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/[0.06] p-4 flex gap-4"
          data-testid="home-rec-top-channel">
      <div
        data-testid="home-rec-top-channel-artwork"
        className="w-20 h-20 rounded-2xl bg-white/[0.06] overflow-hidden flex-shrink-0
                              flex items-center justify-center relative"
        style={!showImg
          ? { background: "linear-gradient(135deg,#22d3ee 0%,#a21caf 100%)" }
          : undefined}>
        {showImg
          ? <img src={thumb(rec.thumbnail_url)} alt={rec.name}
                      onError={() => setImgFail(true)}
                      loading="lazy"
                      data-testid="home-rec-top-channel-img"
                      className="w-full h-full object-cover" />
          : <Music2 size={26} className="text-white/85"
                                data-testid="home-rec-top-channel-fallback" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
          {rec.cold_start ? "Try this station" : "Most listened"}
        </div>
        <div className="font-display font-bold text-lg tracking-display-tight truncate"
              data-testid="home-rec-top-channel-name">
          {rec.name}
        </div>
        <div className="text-xs text-text-secondary">
          {rec.cold_start ? "Popular in your city" : `${hours} hrs in last 30d`}
        </div>
        <button
          onClick={() => navigate(`/radio?ch=${encodeURIComponent(rec.slug)}`)}
          className="mt-2 text-xs text-accent-electric inline-flex items-center gap-1"
          data-testid="home-rec-top-channel-resume">
          <Play size={12} /> Resume
        </button>
      </div>
    </div>
  );
}


// ─── Top-game recommendation card ───────────────────────────────────
export function TopGameRecCard() {
  const navigate = useNavigate();
  const [rec, setRec] = useState(null);
  const [imgFail, setImgFail] = useState(false);
  useEffect(() => { fetchTopGameRec().then(setRec); }, []);
  if (!rec) return null;
  const ago = (iso) => {
    if (!iso) return "Never";
    const d = (Date.now() - new Date(iso).getTime()) / (24 * 3600 * 1000);
    if (d < 1) return "Today";
    if (d < 2) return "Yesterday";
    return `${Math.round(d)}d ago`;
  };
  const showImg = !!rec.icon_url && !imgFail;
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/[0.06] p-4 flex gap-4"
          data-testid="home-rec-top-game">
      <div
        data-testid="home-rec-top-game-artwork"
        className="w-20 h-20 rounded-2xl bg-white/[0.06] overflow-hidden flex-shrink-0
                              flex items-center justify-center text-3xl relative"
        style={!showImg
          ? { background: "linear-gradient(135deg,#ec4899 0%,#f59e0b 100%)" }
          : undefined}>
        {showImg
          ? <img src={thumb(rec.icon_url)} alt={rec.name}
                      onError={() => setImgFail(true)}
                      loading="lazy"
                      data-testid="home-rec-top-game-img"
                      className="w-full h-full object-cover" />
          : <Gamepad2 size={28} className="text-white"
                                data-testid="home-rec-top-game-fallback" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
          {rec.cold_start ? "Try this game" : "Played most"}
        </div>
        <div className="font-display font-bold text-lg tracking-display-tight truncate"
              data-testid="home-rec-top-game-name">
          {rec.name}
        </div>
        <div className="text-xs text-text-secondary">
          {rec.cold_start
            ? "Most played in RadioLife"
            : `Last ${ago(rec.last_played_at)} · played ${rec.play_count}×`}
        </div>
        <button
          onClick={() => navigate(`/play-and-win?game=${encodeURIComponent(rec.game_id)}`)}
          className="mt-2 text-xs text-accent-magenta inline-flex items-center gap-1"
          data-testid="home-rec-top-game-play">
          <Play size={12} /> Play again
        </button>
      </div>
    </div>
  );
}


// ─── Favorites strip (≤8 channels + add picker) ─────────────────────
export function FavoritesStrip({ allChannels = [] }) {
  const { favorites, cap, loaded, bootstrap, add, remove } = useFavoritesStore();
  const [pickerOpen, setPickerOpen] = useState(false);
  const navigate = useNavigate();
  useEffect(() => { if (!loaded) bootstrap(); }, [loaded, bootstrap]);
  const onAdd = async (slug) => {
    const r = await add(slug);
    if (!r.ok && r.code === "favorites_cap")  toast.error(r.message);
    else if (!r.ok)                                                toast.error(r.message || "Couldn't add.");
    else                                                                toast.success("Added to favorites.");
  };
  return (
    <div className="space-y-2" data-testid="home-favorites-strip">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.25em]
                              text-text-secondary font-mono">
        <Heart size={12} className="text-accent-magenta" />
        Favorites · {favorites.length}/{cap}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-2 -mx-1 px-1
                              snap-x scroll-pl-2">
        {favorites.map((f) => (
          <FavChip key={f.channel_slug}
                          fav={f}
                          onPlay={() => navigate(`/radio?ch=${encodeURIComponent(f.channel_slug)}`)}
                          onRemove={() => remove(f.channel_slug)} />
        ))}
        {favorites.length < cap && (
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="w-16 h-16 sm:w-[72px] sm:h-[72px] flex-shrink-0
                              rounded-2xl border-2 border-dashed border-white/[0.20]
                              flex items-center justify-center
                              hover:border-accent-magenta hover:bg-accent-magenta/[0.06]
                              transition-colors"
            data-testid="home-favorites-add"
            aria-label="Add favorite channel">
            <Plus size={20} className="text-text-secondary" />
          </button>
        )}
      </div>
      {pickerOpen && (
        <FavoritesPicker
          allChannels={allChannels}
          onPick={onAdd}
          onClose={() => setPickerOpen(false)} />
      )}
    </div>
  );
}


function FavChip({ fav, onPlay, onRemove }) {
  return (
    <div className="relative w-16 h-16 sm:w-[72px] sm:h-[72px] flex-shrink-0 group"
          data-testid={`home-favorite-chip-${fav.channel_slug}`}>
      <button
        onClick={onPlay}
        title={fav.channel?.name}
        className="w-full h-full rounded-2xl overflow-hidden
                            border border-white/[0.08] bg-white/[0.04]
                            hover:ring-2 hover:ring-accent-magenta transition-shadow">
        {fav.channel?.thumbnail_url
          ? <img src={thumb(fav.channel.thumbnail_url)} alt={fav.channel.name}
                      className="w-full h-full object-cover" />
          : <div className="w-full h-full flex items-center justify-center text-xl">📻</div>}
      </button>
      <button
        onClick={onRemove}
        className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-bg-base
                            border border-white/[0.20] flex items-center justify-center
                            opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Remove from favorites"
        data-testid={`home-favorite-remove-${fav.channel_slug}`}>
        <X size={12} />
      </button>
    </div>
  );
}


function FavoritesPicker({ allChannels, onPick, onClose }) {
  const { favorites } = useFavoritesStore();
  const have = new Set(favorites.map((f) => f.channel_slug));
  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm
                            flex items-center justify-center p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg rounded-2xl bg-bg-base
                              border border-white/[0.10] p-5 max-h-[80vh] overflow-y-auto"
            data-testid="home-favorites-picker">
        <div className="flex items-center justify-between mb-3">
          <div className="font-display font-bold text-xl tracking-display-tight">
            Pick favorites
          </div>
          <button onClick={onClose} className="text-text-secondary"
                        data-testid="home-favorites-picker-close">
            <X size={18} />
          </button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {allChannels.map((c) => {
            const taken = have.has(c.slug);
            return (
              <button
                key={c.slug}
                disabled={taken}
                onClick={async () => { await onPick(c.slug); }}
                data-testid={`home-favorites-picker-${c.slug}`}
                className={`rounded-2xl p-2 text-left border
                                ${taken
                                  ? "border-accent-magenta/40 bg-accent-magenta/[0.08] opacity-60"
                                  : "border-white/[0.08] bg-white/[0.04] hover:bg-white/[0.08]"}`}>
                {c.thumbnail_url && (
                  <div className="w-full h-16 rounded-xl mb-1 overflow-hidden bg-white/[0.06]">
                    <SafeImage src={thumb(c.thumbnail_url)} alt={c.name}
                                              fallbackKind="station"
                                              fallbackText={c.name || ""}
                                              className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="font-display font-bold text-xs truncate">{c.name}</div>
                {taken && <div className="text-[9px] text-accent-magenta">Added</div>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}


// ─── Bottom-bar quick-channel strip ────────────────────────────────
export function BottomBarChannelStrip({ currentSlug, onSwitch }) {
  const { favorites } = useFavoritesStore();
  const [autoTop5, setAutoTop5] = useState([]);
  useEffect(() => {
    fetchAutoplaySuggestion().then((s) => setAutoTop5(s?.top5 || []));
  }, []);
  // Merge favorites first, then autoplay top5 — dedupe.
  const seen = new Set();
  const merged = [];
  for (const f of favorites) {
    if (seen.has(f.channel_slug)) continue;
    seen.add(f.channel_slug);
    merged.push({
      slug: f.channel_slug,
      name: f.channel?.name,
      thumb: f.channel?.thumbnail_url,
    });
  }
  for (const t of autoTop5) {
    if (seen.has(t.channel_slug)) continue;
    seen.add(t.channel_slug);
    merged.push({
      slug: t.channel_slug,
      name: t.name,
      thumb: t.thumbnail_url,
    });
    if (merged.length >= 8) break;
  }
  if (merged.length === 0) return null;
  return (
    <div className="hidden sm:flex gap-1.5 overflow-x-auto items-center
                            snap-x scroll-pl-2 px-2 -mr-2 max-w-[44vw]"
          data-testid="bottombar-channel-strip">
      {merged.map((c) => {
        const active = currentSlug === c.slug;
        return (
          <button
            key={c.slug}
            onClick={() => onSwitch?.(c.slug)}
            title={c.name}
            data-testid={`bottombar-chip-${c.slug}`}
            className={`relative w-10 h-10 rounded-xl flex-shrink-0
                                overflow-hidden border ${active
                                  ? "border-accent-magenta ring-2 ring-accent-magenta/60"
                                  : "border-white/[0.08] hover:border-white/[0.20]"}`}>
            {c.thumb
              ? <SafeImage src={thumb(c.thumb)} alt={c.name}
                                            fallbackKind="station"
                                            fallbackText={c.name || ""}
                                            className="w-full h-full object-cover" />
              : <div className="w-full h-full flex items-center justify-center text-xs"><Music2 size={14} /></div>}
          </button>
        );
      })}
    </div>
  );
}
