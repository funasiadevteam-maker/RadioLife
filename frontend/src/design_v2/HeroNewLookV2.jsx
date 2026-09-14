import React from "react";
import { useNavigate } from "react-router-dom";
import { Play, Radio, Globe, MapPin, ShieldCheck } from "lucide-react";
import { HERO_IMG } from "./analytics";

const STATS = [
  { icon: Radio, label: "50,000+ Stations" },
  { icon: Globe, label: "Global" },
  { icon: MapPin, label: "Local" },
  { icon: ShieldCheck, label: "Ad-Free (Premium)" },
];

export default function HeroNewLookV2({ greeting, name }) {
  const navigate = useNavigate();
  return (
    <section data-testid="nlv2-hero" className="nlv2-hero-grid grid grid-cols-[1.1fr_0.9fr] gap-6 xl:gap-10 items-stretch">
      {/* Left — copy + CTAs */}
      <div className="flex flex-col justify-center py-2">
        <p data-testid="nlv2-greeting" className="text-sm font-semibold tracking-widest uppercase text-[#97a3c2] mb-3">
          {greeting}, {name}
        </p>
        <h1 className="font-black leading-[0.98] tracking-tight text-[44px] sm:text-[58px] xl:text-[68px]">
          Ready to<br /><span className="nlv2-grad">listen?</span>
        </h1>
        <p className="mt-5 text-[15px] sm:text-base text-[#aab4d0] max-w-md leading-relaxed">
          AI-personalized radio built around what you love. Skip what you don't,
          earn BigPoints as you listen.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <button type="button" data-testid="nlv2-cta-airadio" onClick={() => navigate("/radio")}
            className="nlv2-btn h-12 px-6 rounded-full font-bold text-sm inline-flex items-center gap-2">
            <Play size={17} fill="currentColor" /> Start My AI Radio
          </button>
          <button type="button" data-testid="nlv2-cta-live" onClick={() => navigate("/listen")}
            className="nlv2-btn-ghost h-12 px-6 rounded-full font-bold text-sm inline-flex items-center gap-2">
            <Radio size={17} /> Explore Live Radio
          </button>
        </div>
        <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3">
          {STATS.map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-2 text-[13px] font-semibold text-[#c3cbe4]">
              <span className="w-7 h-7 rounded-full nlv2-glass grid place-items-center">
                <Icon size={14} className="text-[#c084fc]" />
              </span>
              {label}
            </div>
          ))}
        </div>
      </div>

      {/* Right — cinematic lifestyle image */}
      <div className="relative rounded-[26px] overflow-hidden min-h-[340px] nlv2-glass">
        <img src={HERO_IMG} alt="Enjoying music" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 pointer-events-none" style={{ background: "linear-gradient(180deg, rgba(7,10,23,0.15) 0%, rgba(7,10,23,0.15) 45%, rgba(7,10,23,0.72) 100%)" }} />
        <div className="absolute inset-0 pointer-events-none" style={{ boxShadow: "inset 0 0 120px rgba(124,58,237,0.35)" }} />
        <div className="absolute left-6 bottom-7">
          <div style={{ fontFamily: "'Brush Script MT','Segoe Script',cursive" }}
            className="text-white text-3xl sm:text-4xl drop-shadow-lg">Music Connects Us</div>
        </div>
        <div className="absolute right-5 top-6 text-right max-w-[140px]">
          <div className="text-[10px] font-mono uppercase tracking-widest text-[#f9a8d4]">Today's Vibe</div>
          <div className="mt-1 text-sm font-semibold text-white/90 leading-snug">
            Your music.<br />Your mood.<br />A better you.
          </div>
        </div>
      </div>
    </section>
  );
}
