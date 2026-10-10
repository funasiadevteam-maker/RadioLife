// Home showcase for the huge live-radio catalog (50K+ stations) + a CTA into
// Radio Discover. Tied to the always-on "Listen" feature. Reuses FlagshipStrip
// for a real, tappable station rail beneath the banner.
import React from "react";
import { useNavigate } from "react-router-dom";
import { Radio, ChevronRight, Globe2 } from "lucide-react";
import FlagshipStrip from "@/components/FlagshipStrip";

export default function RadioStationsHomeV2({ title = "50,000+ Radio Stations" }) {
  const navigate = useNavigate();
  return (
    <section data-testid="nlv2-radio-stations" className="space-y-4">
      <div className="relative overflow-hidden rounded-3xl p-5 sm:p-6 border border-white/10"
        style={{ background: "linear-gradient(135deg, rgba(34,211,238,0.14), rgba(168,85,247,0.14))" }}>
        <div className="absolute -right-6 -top-8 opacity-10 pointer-events-none">
          <Radio size={140} color="#fff" />
        </div>
        <div className="relative flex items-center justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-cyan-300 text-[10px] font-black uppercase tracking-widest">
              <Globe2 size={13} /> Live radio worldwide
            </div>
            <h2 className="mt-1 text-2xl sm:text-3xl font-black text-white leading-tight">
              {title}
            </h2>
            <p className="text-sm text-white/60 mt-1 max-w-md">
              Every genre, language and city on Earth — plus AI radio made just for you.
            </p>
          </div>
          <button type="button" data-testid="nlv2-radio-stations-browse"
            onClick={() => navigate("/radio/discover")}
            className="shrink-0 inline-flex items-center gap-1.5 h-11 px-5 rounded-full font-black text-slate-950 transition-transform hover:scale-[1.03]"
            style={{ background: "linear-gradient(135deg,#22d3ee,#a855f7)" }}>
            Browse all <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <FlagshipStrip title="Popular right now"
        testId="nlv2-radio-stations-strip" limit={12} />
    </section>
  );
}
