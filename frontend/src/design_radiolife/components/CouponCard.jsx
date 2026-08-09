// Phase R.1 — Coupon card for Rewards Wallet.
import React from "react";
import { Link } from "react-router-dom";
import { Ticket, Clock } from "lucide-react";
import { RLCard, RLBadge } from "../DesignSystem";

export default function CouponCard({ coupon, offer, business }) {
  const title = offer?.title || coupon.title || "Saved coupon";
  const bizName = business?.name || coupon.business_name;
  const expiresAt = coupon.expires_at ? new Date(coupon.expires_at) : null;
  const daysLeft = expiresAt ? Math.max(0,
    Math.round((expiresAt.getTime() - Date.now()) / 86_400_000)) : null;
  const pct = offer?.discount_percent;
  return (
    <RLCard className="p-4" data-testid={`rl-coupon-card-${coupon.coupon_id}`}>
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-2xl flex items-center justify-center
                                text-white flex-shrink-0"
                  style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
          <Ticket size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-bold text-slate-900 line-clamp-1">{title}</div>
          {bizName && (
            <div className="text-[11px] uppercase tracking-wider text-slate-500
                                    font-semibold mt-0.5 truncate">{bizName}</div>
          )}
          <div className="mt-1.5 flex items-center gap-2 flex-wrap">
            {typeof pct === "number" && (
              <RLBadge tone="purple">-{pct}%</RLBadge>
            )}
            {daysLeft !== null && (
              <span className={"text-[11px] font-semibold flex items-center gap-1 " +
                                        (daysLeft <= 3 ? "text-amber-600" : "text-slate-500")}>
                <Clock size={11} />
                {daysLeft === 0 ? "Expires today" : `${daysLeft}d left`}
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-widest text-slate-400 font-mono">
          {coupon.code}
        </span>
        <Link
          to={`/coupon/${coupon.coupon_id}`}
          data-testid={`rl-coupon-use-${coupon.coupon_id}`}
          className="text-[11px] uppercase tracking-widest font-semibold
                              px-4 py-1.5 rounded-full text-white shadow-md
                              hover:shadow-lg transition-all"
          style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
          Use
        </Link>
      </div>
    </RLCard>
  );
}
