// Phase R.1 — Nearby-deal card (horizontal roll on Home).
import React from "react";
import { Link } from "react-router-dom";
import { Utensils, MapPin } from "lucide-react";
import { RLCard, RLBadge } from "../DesignSystem";

export default function NearbyDealCard({ business, offer, distance_km,
                                                              onSave, className = "" }) {
  const name = business?.name || "Local business";
  const category = (business?.category || "").replace("_", " ");
  const dist = typeof distance_km === "number"
                    ? `${distance_km.toFixed(1)} km` : null;
  const offerTitle = offer?.title;
  const pct = offer?.discount_percent;
  return (
    <RLCard className={"p-4 min-w-[260px] " + className}
                data-testid={`rl-deal-card-${business?.business_id || "x"}`}>
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-2xl flex items-center justify-center
                                text-white shadow-md flex-shrink-0"
                  style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
          <Utensils size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-slate-900 truncate">{name}</div>
          <div className="text-[11px] uppercase tracking-wider text-slate-500
                                    font-semibold flex items-center gap-2 mt-0.5">
            {category && <span className="capitalize">{category}</span>}
            {dist && (
              <>
                <span className="opacity-40">·</span>
                <span className="flex items-center gap-0.5">
                  <MapPin size={10} /> {dist}
                </span>
              </>
            )}
          </div>
        </div>
        {typeof pct === "number" && (
          <RLBadge tone="pink" className="flex-shrink-0"
                          data-testid={`rl-deal-discount-${offer?.offer_id}`}>
            -{pct}%
          </RLBadge>
        )}
      </div>
      {offerTitle && (
        <div className="mt-3 text-sm text-slate-700 line-clamp-2">
          {offerTitle}
        </div>
      )}
      <div className="mt-3 flex justify-between items-center">
        <Link to={business?.slug ? `/business/${business.slug}` : "#"}
                  className="text-[11px] uppercase tracking-widest font-semibold
                                      text-purple-700 hover:text-purple-900">
          View details →
        </Link>
        {onSave && offer && (
          <button
            type="button"
            onClick={() => onSave(offer.offer_id)}
            className="text-[11px] uppercase tracking-widest font-semibold
                                bg-purple-100 text-purple-800 px-3 py-1.5 rounded-full
                                hover:bg-purple-200 transition-colors"
            data-testid={`rl-deal-save-${offer.offer_id}`}>
            Save
          </button>
        )}
      </div>
    </RLCard>
  );
}
