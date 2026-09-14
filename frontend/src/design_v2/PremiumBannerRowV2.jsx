import React from "react";
import { useNavigate } from "react-router-dom";
import { Crown, Utensils, ChevronRight } from "lucide-react";

export default function PremiumBannerRowV2({ isPremium }) {
  const navigate = useNavigate();
  return (
    <section data-testid="nlv2-banner-row" className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Upgrade to Premium (hidden for premium users) */}
      {!isPremium && (
        <div data-testid="nlv2-banner-premium"
          className="nlv2-card-hover rounded-3xl p-6 relative overflow-hidden"
          style={{ background: "linear-gradient(120deg, rgba(168,85,247,0.28), rgba(59,130,246,0.20))", border: "1px solid rgba(168,85,247,0.35)" }}>
          <div className="absolute -right-10 -top-10 w-44 h-44 rounded-full" style={{ background: "rgba(236,72,153,0.25)", filter: "blur(30px)" }} />
          <div className="flex items-center gap-2 text-[#f5c563]">
            <Crown size={20} />
            <span className="text-[10px] font-mono uppercase tracking-widest">Premium</span>
          </div>
          <div className="text-2xl font-black mt-1">Upgrade to Premium</div>
          <div className="text-sm text-[#c7cfe8] mt-1.5 max-w-md">
            Ad-free listening, higher rewards, Dining Club access and more!
          </div>
          <button type="button" onClick={() => navigate("/pricing")} data-testid="nlv2-go-premium"
            className="nlv2-btn mt-5 h-11 px-6 rounded-full font-bold text-sm inline-flex items-center gap-2">
            Go Premium <ChevronRight size={15} />
          </button>
        </div>
      )}

      {/* Discover Dining Club */}
      <div data-testid="nlv2-banner-dining"
        className={`nlv2-card-hover rounded-3xl p-6 relative overflow-hidden ${isPremium ? "md:col-span-2" : ""}`}
        style={{ background: "linear-gradient(120deg, rgba(251,146,60,0.24), rgba(236,72,153,0.16))", border: "1px solid rgba(251,146,60,0.35)" }}>
        <div className="absolute -right-10 -bottom-10 w-44 h-44 rounded-full" style={{ background: "rgba(245,158,11,0.25)", filter: "blur(30px)" }} />
        <div className="flex items-center gap-2 text-[#f5c563]">
          <Utensils size={20} />
          <span className="text-[10px] font-mono uppercase tracking-widest">Dining Club</span>
        </div>
        <div className="text-2xl font-black mt-1">Discover Dining Club</div>
        <div className="text-sm text-[#efd6c1] mt-1.5 max-w-md">
          Spin for $9.99 meals at top restaurants. New options every day!
        </div>
        <button type="button" onClick={() => navigate("/dining")} data-testid="nlv2-dining-learn"
          className="nlv2-btn-ghost mt-5 h-11 px-6 rounded-full font-bold text-sm inline-flex items-center gap-2">
          Learn More <ChevronRight size={15} />
        </button>
      </div>
    </section>
  );
}
