import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Radio, Play } from "lucide-react";
import { fireV2Event } from "./analytics";

// Shared image-led rail for "For You" + "Live Right Now". Each item:
//   { id, name/title, city/subtitle, art/image, live, sponsored, to?, kind? }
export default function RailV2({ title, subtitle, items = [], testId }) {
  const navigate = useNavigate();
  const firedRef = useRef(false);

  useEffect(() => {
    if (firedRef.current) return;
    const sponsored = items.find((i) => i.sponsored);
    if (sponsored) {
      firedRef.current = true;
      const ev = sponsored.to ? "native_offer_impression" : "sponsored_station_impression";
      fireV2Event(ev, {
        station_id: sponsored.id, business_id: sponsored.business_id,
        campaign_id: sponsored.campaign_id, kind: sponsored.kind,
      });
    }
  }, [items]);

  if (!items.length) return null;

  const onCard = (it) => {
    if (it.sponsored) {
      fireV2Event(it.to ? "native_offer_click" : "sponsored_station_start", {
        station_id: it.id, business_id: it.business_id, campaign_id: it.campaign_id, kind: it.kind,
      });
    }
    if (it.to) navigate(it.to);
    else if (it.id) navigate(`/radio/station/${encodeURIComponent(it.id)}?autoplay=1`);
  };

  return (
    <section data-testid={testId}>
      <div className="mb-4">
        <h2 className="text-xl font-bold">{title}</h2>
        {subtitle && <p className="text-sm text-[#97a3c2] mt-0.5">{subtitle}</p>}
      </div>
      <div className="flex gap-4 overflow-x-auto nlv2-scroll pb-2">
        {items.map((it, idx) => {
          const img = it.art || it.image;
          const name = it.name || it.title;
          const sub = it.city || it.subtitle;
          return (
            <button type="button" key={(it.id || "n") + idx}
              onClick={() => onCard(it)}
              data-testid={it.sponsored ? "nlv2-rail-sponsored" : `nlv2-rail-card-${idx}`}
              className="group shrink-0 w-[168px] text-left nlv2-card-hover">
              <div className="relative w-[168px] h-[168px] rounded-2xl overflow-hidden nlv2-glass">
                {img
                  ? <img src={img} alt="" className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                  : <div className="absolute inset-0 grid place-items-center"><Radio size={26} className="text-[#97a3c2]" /></div>}
                <div className="absolute inset-0" style={{ background: "linear-gradient(180deg,transparent 45%,rgba(7,10,23,0.65) 100%)" }} />
                {it.sponsored && (
                  <span className="absolute top-2 left-2 text-[8.5px] font-black tracking-widest px-2 py-0.5 rounded-full"
                    style={{ background: "#f5c563", color: "#0a0e20" }}>SPONSORED</span>
                )}
                {it.live && !it.sponsored && (
                  <span className="absolute top-2 left-2 inline-flex items-center gap-1 text-[9px] font-black tracking-widest px-2 py-0.5 rounded-full bg-red-500/90 text-white">
                    <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE
                  </span>
                )}
                {it.type && !it.sponsored && !it.live && !["station"].includes(it.type) && (
                  <span data-testid={`nlv2-rail-badge-${it.type}`}
                    className="absolute top-2 left-2 text-[8.5px] font-black tracking-widest px-2 py-0.5 rounded-full"
                    style={{ background: "rgba(124,58,237,0.92)", color: "#fff" }}>
                    {(it.badge || it.type).toUpperCase()}
                  </span>
                )}
                <div className="absolute right-2.5 bottom-2.5 w-9 h-9 rounded-full grid place-items-center opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  <Play size={15} fill="#fff" color="#fff" />
                </div>
              </div>
              <div className="mt-2 px-0.5">
                <div className="text-sm font-bold truncate">{name}</div>
                {sub && <div className="text-xs text-[#97a3c2] truncate">{sub}</div>}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
