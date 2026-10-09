// Pinned AI stations — a reusable row shown on Discover, Home and Listen so
// a listener's favourite FUUSIC AI channels are one tap away everywhere.
// Drag to reorder (framer-motion Reorder); the order persists in localStorage.
// Pins themselves are the listener's favourited AI stations (station_type
// "bigfm"), toggled via the heart on any AI card.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Reorder } from "framer-motion";
import { Pin, X, GripVertical, Sparkles } from "lucide-react";
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { orderByPinOrder, setPinOrder } from "@/utils/pinOrder";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const src = (u) => (u ? (u.startsWith("http") ? u : `${BACKEND}${u}`) : null);

export default function PinnedAiRow({ className = "", testId = "pinned-ai-row" }) {
  const navigate = useNavigate();
  const favorites = useStationFavoritesStore((s) => s.favorites);
  const favLoaded = useStationFavoritesStore((s) => s.loaded);
  const bootstrap = useStationFavoritesStore((s) => s.bootstrap);
  const remove = useStationFavoritesStore((s) => s.remove);

  useEffect(() => { if (!favLoaded) bootstrap(); }, [favLoaded, bootstrap]);

  const pinned = useMemo(() => orderByPinOrder(favorites
    .filter((f) => f.station_type === "bigfm")
    .map((f) => ({
      id: f.station_id,
      name: (f.station && f.station.name) || f.station_id,
      thumb: (f.station && (f.station.favicon || f.station.thumbnail_url)) || null,
    }))), [favorites]);

  const [items, setItems] = useState(pinned);
  useEffect(() => { setItems(pinned); }, [pinned]);

  const dragged = useRef(false);

  const onReorder = (next) => {
    setItems(next);
    setPinOrder(next.map((s) => s.id));
  };

  if (items.length === 0) return null;

  return (
    <section className={className} data-testid={testId}>
      <div className="flex items-center gap-2 mb-3">
        <Pin size={15} className="text-cyan-300" />
        <h3 className="text-base font-bold text-white">Pinned</h3>
        {items.length > 1 && (
          <span className="text-[11px] text-white/40">drag to reorder</span>
        )}
      </div>
      <Reorder.Group axis="x" values={items} onReorder={onReorder}
        className="flex gap-3 overflow-x-auto no-scrollbar pb-1 list-none m-0 p-0">
        {items.map((st) => (
          <Reorder.Item key={st.id} value={st}
            onDragStart={() => { dragged.current = true; }}
            onDragEnd={() => { setTimeout(() => { dragged.current = false; }, 60); }}
            whileDrag={{ scale: 1.05 }}
            data-testid={`pinned-ai-card-${st.id}`}
            className="group relative shrink-0 w-[132px] rounded-2xl overflow-hidden
                              border border-cyan-400/20 bg-white/[0.04] cursor-grab active:cursor-grabbing">
            <button type="button"
              onClick={() => { if (!dragged.current) navigate(`/radio?ch=${encodeURIComponent(st.id)}&autoplay=1`); }}
              className="block w-full text-left">
              <div className="relative aspect-square bg-black/30 overflow-hidden">
                {src(st.thumb)
                  ? <img src={src(st.thumb)} alt="" className="w-full h-full object-cover" draggable={false} />
                  : <div className="w-full h-full grid place-items-center"><Sparkles size={24} className="text-cyan-300" /></div>}
                <span className="absolute top-1.5 left-1.5 text-[8px] font-black px-1.5 py-0.5 rounded-full bg-cyan-400/90 text-slate-950 tracking-widest">AI</span>
              </div>
              <div className="p-2">
                <div className="text-[13px] font-semibold truncate text-white">{st.name}</div>
              </div>
            </button>
            {/* Unpin */}
            <button type="button" data-testid={`pinned-ai-unpin-${st.id}`}
              onClick={(e) => { e.stopPropagation(); remove(st.id); }}
              aria-label="Unpin"
              className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full grid place-items-center
                                bg-black/50 text-white/80 hover:text-white hover:bg-black/70 opacity-0 group-hover:opacity-100 transition-opacity">
              <X size={13} />
            </button>
            {/* Drag affordance */}
            <span className="absolute bottom-1.5 right-1.5 text-white/30 group-hover:text-white/60 transition-colors pointer-events-none">
              <GripVertical size={14} />
            </span>
          </Reorder.Item>
        ))}
      </Reorder.Group>
    </section>
  );
}
