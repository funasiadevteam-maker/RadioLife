import React from "react";
import { useNavigate } from "react-router-dom";
import { Play, Pause, Coins, ChevronRight, Utensils, Sparkles } from "lucide-react";

function SectionHead({ title, to, navigate }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-xl font-bold">{title}</h2>
      {to && (
        <button type="button" onClick={() => navigate(to)}
          className="text-sm font-semibold text-[#c084fc] hover:text-white transition-colors inline-flex items-center gap-1">
          See all <ChevronRight size={15} />
        </button>
      )}
    </div>
  );
}

export default function ContinueListeningRowV2({ continueItem, reward, dining, onResume }) {
  const navigate = useNavigate();
  const pm = reward?.points_per_min || 1;
  const isMember = !!dining?.member;

  return (
    <section data-testid="nlv2-continue">
      <SectionHead title="Continue Listening" to="/listen" navigate={navigate} />
      <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr_1fr] gap-4">
        {/* Continue / Start card */}
        <div data-testid="nlv2-continue-card"
          className="nlv2-glass-strong nlv2-card-hover rounded-3xl p-4 flex items-center gap-4 overflow-hidden relative">
          <div className="w-20 h-20 rounded-2xl overflow-hidden shrink-0 bg-black/40 grid place-items-center">
            {continueItem?.art
              ? <img src={continueItem.art} alt="" className="w-full h-full object-cover" />
              : <Sparkles size={26} className="text-[#c084fc]" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-mono uppercase tracking-widest text-[#97a3c2]">
              {continueItem ? "Continue Listening" : "Start listening"}
            </div>
            <div className="text-lg font-bold truncate mt-0.5">
              {continueItem?.title || "Bollywood AI Radio"}
            </div>
            <div className="text-sm text-[#aab4d0] truncate">
              {continueItem?.subtitle || "AI radio built around you"}
            </div>
            <div className="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${continueItem?.progress ?? 22}%`, background: "linear-gradient(90deg,#c084fc,#ec4899)" }} />
            </div>
          </div>
          <button type="button" onClick={onResume} data-testid="nlv2-continue-play"
            className="w-14 h-14 rounded-full shrink-0 grid place-items-center text-white"
            style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)", boxShadow: "0 10px 28px rgba(168,85,247,.45)" }}>
            {continueItem?.playing ? <Pause size={22} fill="currentColor" /> : <Play size={22} fill="currentColor" />}
          </button>
        </div>

        {/* Reward card */}
        <button type="button" onClick={() => navigate("/wallet")} data-testid="nlv2-reward-card"
          className="nlv2-glass nlv2-card-hover rounded-3xl p-5 text-left"
          style={{ borderColor: "rgba(245,197,99,0.28)" }}>
          <div className="flex items-center gap-2 text-[#f5c563]">
            <Coins size={18} />
            <span className="text-lg font-black">+{pm} BigPoint{pm === 1 ? "" : "s"}/minute</span>
          </div>
          <div className="text-sm text-[#aab4d0] mt-2">18 more minutes → <span className="text-white font-semibold">+50 bonus</span></div>
          <div className="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: "64%", background: "linear-gradient(90deg,#f5c563,#f59e0b)" }} />
          </div>
          <div className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-[#f5c563]">
            View Rewards <ChevronRight size={15} />
          </div>
        </button>

        {/* Dining Club native promo card */}
        <button type="button" onClick={() => navigate("/dining")} data-testid="nlv2-dining-card"
          className="nlv2-card-hover rounded-3xl p-5 text-left relative overflow-hidden"
          style={{ background: "linear-gradient(135deg, rgba(251,146,60,0.18), rgba(236,72,153,0.14))", border: "1px solid rgba(251,146,60,0.30)" }}>
          <div className="absolute -right-6 -bottom-6 w-28 h-28 rounded-full grid place-items-center"
            style={{ background: "conic-gradient(from 0deg,#f59e0b,#ec4899,#a855f7,#f59e0b)", opacity: 0.5 }}>
            <div className="w-16 h-16 rounded-full bg-[#0a0e20] grid place-items-center">
              <Utensils size={22} className="text-[#f5c563]" />
            </div>
          </div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-[#f9a8d4]">
            {isMember ? "Member" : "Promoted"}
          </div>
          <div className="text-lg font-black mt-0.5">{isMember ? "Your Dining Club" : "Dining Club"}</div>
          <div className="text-sm text-[#e6c9b0] mt-1 max-w-[70%]">
            {isMember ? "Pick this week's meals" : "$9.99 meals at top restaurants"}
          </div>
          <div className="text-sm text-white/80 mt-0.5">{isMember ? "Spin for tonight" : "Spin for your next meal!"}</div>
          <div className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-[#f5c563]">
            {isMember ? "Open" : "Learn More"} <ChevronRight size={15} />
          </div>
        </button>
      </div>
    </section>
  );
}
