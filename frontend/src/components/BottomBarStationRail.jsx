/**
 * Phase P0-BAR — Bottom-bar station rail (horizontal icon strip).
 *
 * Renders a scrollable rail of small circular station logos inside the
 * persistent bottom `MiniPlayer`.  Data comes from
 * `GET /api/user/bottom-bar-rail`, which combines:
 *
 *   1. The user's favorite imported stations
 *   2. Region-matched flagships (US → Dallas cluster; else → Dubai)
 *
 * Anonymous users see flagships only.  Click on any icon navigates to
 * `/radio/station/<id>?autoplay=1` — the same URL the Play button uses,
 * so `LiveRadioStation.jsx` auto-starts playback within a few seconds.
 *
 * Dual-design: `useDesignVariant()` swaps colors between the dark
 * "legacy" surface and the light "radiolife" surface.  Legacy = amber
 * ring on the #1 favorite; FUUSIC = fuchsia ring.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Heart } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API_BASE = process.env.REACT_APP_BACKEND_URL || "";

export default function BottomBarStationRail() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/api/user/bottom-bar-rail`,
                                                { credentials: "include" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setItems(Array.isArray(d.items) ? d.items : []);
    } catch (_e) {
      // Silent fail — rail just doesn't render.
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const topFavId = useMemo(() => {
    const fav = items.find((x) => x.kind === "favorite");
    return fav?.id || null;
  }, [items]);

  const onPick = (id) => {
    if (!id) return;
    window.location.href = `/radio/station/${encodeURIComponent(id)}?autoplay=1`;
  };

  // Loading shimmer — 5 skeleton bubbles.
  if (loading) {
    return (
      <div data-testid="bottom-bar-rail"
                data-state="loading"
                className="flex items-center gap-2 overflow-x-auto no-scrollbar
                                      px-2 py-1.5 flex-shrink-0">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i}
                    className={"w-8 h-8 rounded-full flex-shrink-0 animate-pulse " +
                                          (light ? "bg-slate-200" : "bg-white/[0.08]")} />
        ))}
      </div>
    );
  }

  if (!items || items.length === 0) return null;

  const ringLegacy    = "shadow-[0_0_0_2px_#f59e0b]";      // amber
  const ringRadiolife = "shadow-[0_0_0_2px_#a855f7]";  // fuchsia
  const ringClass = light ? ringRadiolife : ringLegacy;

  return (
    <div data-testid="bottom-bar-rail"
              data-state="ready"
              data-count={items.length}
              className="flex items-center gap-2 overflow-x-auto no-scrollbar
                                    px-2 py-1.5 flex-shrink-0 max-w-full">
      {items.map((it) => {
        const isFav = it.kind === "favorite";
        const isTopFav = it.id === topFavId;
        const logo = it.logo_url
          ? (it.logo_url.startsWith("http")
              ? it.logo_url
              : `${API_BASE}${it.logo_url}`)
          : null;
        return (
          <button key={it.id}
                          type="button"
                          onClick={() => onPick(it.id)}
                          data-testid={`bottom-bar-rail-item-${it.id}`}
                          data-kind={it.kind}
                          data-is-top-fav={isTopFav ? "true" : "false"}
                          title={it.name}
                          aria-label={`Play ${it.name}`}
                          className={"relative w-9 h-9 rounded-full flex-shrink-0 " +
                                                "overflow-hidden transition-transform hover:scale-110 " +
                                                (isTopFav ? ringClass + " " : "") +
                                                (light
                                                    ? "bg-slate-100 border border-slate-200"
                                                    : "bg-white/[0.06] border border-white/[0.10]")}>
            {logo ? (
              <img src={logo} alt=""
                        onError={(e) => { e.currentTarget.style.display = "none"; }}
                        className="w-full h-full object-cover" />
            ) : (
              <span className={"absolute inset-0 flex items-center justify-center " +
                                                    "text-[10px] font-bold " +
                                                    (light ? "text-slate-600" : "text-white/70")}>
                {(it.name || "?").slice(0, 2).toUpperCase()}
              </span>
            )}
            {isFav && (
              <span data-testid="bottom-bar-rail-favorite-badge"
                          className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full
                                                  bg-rose-500 text-white grid place-items-center
                                                  shadow-[0_1px_3px_rgba(0,0,0,0.35)]">
                <Heart size={8} fill="currentColor" strokeWidth={0} />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
