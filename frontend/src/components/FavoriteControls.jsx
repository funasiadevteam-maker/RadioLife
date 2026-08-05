/** Phase 42-D3 — Heart toggle button + the bottom-bar favorites strip.
 *
 *  Shared between LiveRadioStation, RadioDiscover, RadioBrowse, and
 *  the MiniPlayer flyout so the heart icon, tooltip, and store wiring
 *  are guaranteed identical everywhere.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Heart, X, Music, ChevronUp } from "lucide-react";
import { toast } from "sonner";
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { usePlayerStore } from "@/store/usePlayerStore";
// P0 mixed-content fix — rewrite http:// stream URLs through the proxy.
import { toPlayableStreamUrl } from "@/utils/streamUrl";

const API = process.env.REACT_APP_BACKEND_URL;

// ── Heart toggle ──────────────────────────────────────────────
export function FavoriteHeart({
  stationId, stationType, station = null,
  size = 16, className = "",
}) {
  const toggle      = useStationFavoritesStore((s) => s.toggle);
  const isFav        = useStationFavoritesStore((s) => s.isFavorited(stationId));
  const [busy, setBusy] = useState(false);

  const onClick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const r = await toggle(stationId, stationType, station);
      if (!r.ok && r.message) toast.error(r.message);
      else if (r.ok && !isFav) toast.success("Added to favorites");
    } finally { setBusy(false); }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`fav-heart-${stationId}`}
      data-favorited={isFav}
      aria-label={isFav ? "Remove from favorites" : "Add to favorites"}
      className={[
        "inline-flex items-center justify-center rounded-full",
        "transition-colors duration-150",
        "bg-black/40 backdrop-blur-sm border border-white/[0.10]",
        "hover:border-rose-400/40 hover:bg-rose-500/10",
        busy ? "opacity-60" : "",
        className,
      ].join(" ")}
      style={{ width: size + 14, height: size + 14 }}
    >
      <Heart
        size={size}
        className={isFav ? "text-rose-400" : "text-white/70"}
        fill={isFav ? "currentColor" : "none"} />
    </button>
  );
}

// ── Bottom-bar favorites strip flyout ────────────────────────
export function FavoritesFlyout({ open, onClose }) {
  const { favorites, loaded, bootstrap, remove } = useStationFavoritesStore();
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);

  useEffect(() => {
    if (open && !loaded) bootstrap();
  }, [open, loaded, bootstrap]);

  if (!open) return null;

  const playStation = async (fav) => {
    const s = fav.station || {};
    if (fav.station_type === "imported") {
      // Route via the same unified player path the 42-B2 fix uses, so
      // the pre-roll overlay fires for free users.
      try {
        const r = await axios.post(
          `${API}/api/radio/play/${fav.station_id}`,
          {}, { withCredentials: true });
        const data = r.data || {};
        setImportedStation({
          id: fav.station_id,
          name: data.name || s.name,
          stream_url: toPlayableStreamUrl(data.stream_url || s.stream_url),
          favicon: data.favicon || s.favicon,
          country: data.country || s.country,
          language: data.language || s.language,
          source: "imported",
        });
      } catch (_e) {
        // Fall back to the joined object's stream URL if /radio/play 4xx'd.
        if (s.stream_url) {
          setImportedStation({
            id: fav.station_id, name: s.name,
            stream_url: toPlayableStreamUrl(s.stream_url), favicon: s.favicon,
            country: s.country, language: s.language,
            source: "imported",
          });
        } else {
          toast.error("Stream unavailable.");
          return;
        }
      }
    } else {
      // RadioLife AI channel — route to /radio?ch=<slug> autoplay.
      window.location.href = `/radio?ch=${encodeURIComponent(fav.station_id)}&autoplay=1`;
      return;
    }
    onClose?.();
  };

  return (
    <div
      data-testid="favorites-flyout"
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 80,
        background: "rgba(0,0,0,0.5)",
        backdropFilter: "blur(2px)",
      }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "fixed", left: 0, right: 0, bottom: 96, padding: "16px",
          background: "rgba(8,8,12,0.96)",
          borderTop: "1px solid rgba(255,255,255,0.10)",
          maxHeight: "60vh", overflow: "auto",
        }}>
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Heart size={14} className="text-rose-400" fill="currentColor" />
              <span className="text-sm font-semibold text-white">
                Favorites · {favorites.length}
              </span>
            </div>
            <button
              onClick={onClose}
              data-testid="favorites-flyout-close"
              className="p-1.5 rounded hover:bg-white/[0.08] text-white/70">
              <X size={14} />
            </button>
          </div>
          {favorites.length === 0 ? (
            <div data-testid="favorites-flyout-empty"
                  className="py-8 text-center text-sm text-white/50">
              No favorites yet — tap ♡ on any station to add it here.
            </div>
          ) : (
            <ul className="flex gap-3 overflow-x-auto pb-2"
                  data-testid="favorites-flyout-list">
              {favorites.map((f) => {
                const st = f.station || {};
                const art = (st.thumbnail_url || st.favicon || "");
                const artUrl = art && art.startsWith("http")
                  ? art
                  : (art ? `${API}${art}` : null);
                return (
                  <li key={f.favorite_id}
                          data-testid={`favorites-flyout-row-${f.station_id}`}
                          className="flex-shrink-0 w-[150px] relative group">
                    <button
                      onClick={() => playStation(f)}
                      data-testid={`favorites-flyout-play-${f.station_id}`}
                      className="block w-full text-left rounded-xl
                                          border border-white/[0.10] bg-white/[0.04]
                                          hover:bg-white/[0.08] overflow-hidden
                                          transition-colors">
                      <div className="w-full aspect-square bg-bg-elevated
                                                  flex items-center justify-center
                                                  relative">
                        {artUrl
                          ? <img src={artUrl} alt=""
                                          className="w-full h-full object-cover"
                                          onError={(e) => {
                                            e.currentTarget.style.display = "none";
                                          }} />
                          : <Music size={28} className="text-white/30" />}
                        <span className={`absolute top-1.5 left-1.5 text-[9px]
                                                          px-1.5 py-0.5 rounded font-mono
                                                          ${f.station_type === "bigfm"
                                                              ? "bg-cyan-400/30 text-cyan-100"
                                                              : "bg-emerald-400/30 text-emerald-100"}`}>
                          {f.station_type === "bigfm" ? "AI" : "LIVE"}
                        </span>
                      </div>
                      <div className="p-2.5">
                        <div className="text-xs font-semibold text-white truncate"
                                  title={st.name}>
                          {st.name || f.station_id}
                        </div>
                        <div className="text-[10px] text-white/40 truncate mt-0.5">
                          {st.country || st.tagline || "—"}
                        </div>
                      </div>
                    </button>
                    <button
                      onClick={() => remove(f.station_id)}
                      data-testid={`favorites-flyout-remove-${f.station_id}`}
                      className="absolute top-1.5 right-1.5 p-1
                                          rounded-full bg-black/60 hover:bg-rose-500/60
                                          text-white/80 hover:text-white opacity-0
                                          group-hover:opacity-100 transition-opacity">
                      <X size={11} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Mini-player chevron button — opens the flyout ────────────
export function FavoritesFlyoutToggle({ open, onToggle }) {
  const count = useStationFavoritesStore((s) => s.favorites.length);
  return (
    <button
      type="button"
      onClick={onToggle}
      data-testid="favorites-flyout-toggle"
      aria-label="Open favorites"
      className="inline-flex items-center gap-1 px-2 h-7 rounded-full
                          bg-white/[0.06] hover:bg-white/[0.10]
                          border border-white/[0.10] text-[11px]
                          text-white/70 hover:text-white transition-colors">
      <Heart size={11}
                  className={count > 0 ? "text-rose-400" : "text-white/50"}
                  fill={count > 0 ? "currentColor" : "none"} />
      {count > 0 && <span className="font-mono">{count}</span>}
      <ChevronUp size={10} className={open ? "rotate-180" : ""} />
    </button>
  );
}
