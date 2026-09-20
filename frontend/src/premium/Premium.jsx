// Phase RWD.3 — Premium comparison + value screen (/premium).
import React from "react";
import { useNavigate } from "react-router-dom";
import { Check, Sparkles, Coins, Loader2, ChevronLeft } from "lucide-react";
import { Card, Button } from "@/shell/primitives";
import { usePremiumStatus } from "@/rewards/premiumApi";

const FREE_FEATURES = [
  "AI Radio & Live Radio", "Podcasts & Games", "Rewards & Wallet",
  "Local deals", "Standard reward earning",
];

export default function Premium() {
  const { data, loading } = usePremiumStatus();
  const navigate = useNavigate();

  if (loading || !data) {
    return (
      <div className="max-w-2xl mx-auto pt-20 text-center text-text-secondary"
                data-testid="premium-loading">
        <Loader2 className="animate-spin inline-block mr-2" size={18} /> Loading…
      </div>
    );
  }

  const v = data.value || {};
  const cur = data.currency || "USD";

  return (
    <div data-testid="premium-root" className="max-w-2xl mx-auto space-y-6 pb-24">
      <button type="button" onClick={() => navigate(-1)} data-testid="premium-back"
                  className="flex items-center gap-1 text-sm text-text-secondary
                                    hover:text-white">
        <ChevronLeft size={16} /> Back
      </button>

      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-2 text-accent-magenta">
          <Sparkles size={20} />
          <h1 className="font-display font-bold text-3xl tracking-display-tight">
            FUUSIC Premium
          </h1>
        </div>
        <p className="text-text-secondary text-sm">
          Fewer interruptions. More AI. Bigger rewards.
        </p>
      </div>

      {data.is_premium ? (
        <Card className="p-6 text-center space-y-2" data-testid="premium-active">
          <Check size={28} className="text-accent-mint inline-block" />
          <div className="font-display font-bold text-lg">You&apos;re a Premium member</div>
          <div className="text-sm text-text-secondary">
            Enjoy every benefit below — thanks for supporting FUUSIC.
          </div>
        </Card>
      ) : (
        <Card className="p-6 space-y-4" data-testid="premium-value">
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
            Your Premium value this month
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="flex items-center gap-2 text-accent-gold">
                <Coins size={18} />
                <span className="font-display font-bold text-2xl"
                          data-testid="premium-bonus-estimate">
                  +{(v.premium_bonus_points_estimate || 0).toLocaleString()}
                </span>
              </div>
              <div className="text-xs text-text-secondary mt-1">
                bonus points you&apos;d have earned
                {data.points_multiplier > 1 ? ` at ${data.points_multiplier}×` : ""}
              </div>
            </div>
            <div>
              <div className="font-display font-bold text-2xl text-text-primary">
                {(v.month_points_earned || 0).toLocaleString()}
              </div>
              <div className="text-xs text-text-secondary mt-1">
                points earned this month
              </div>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card className="p-5 space-y-3" data-testid="premium-free-col">
          <div className="font-display font-bold text-lg">Free</div>
          <ul className="space-y-2">
            {FREE_FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-2 text-sm text-text-secondary">
                <Check size={14} className="text-text-faint" /> {f}
              </li>
            ))}
          </ul>
          <div className="text-xs text-text-faint pt-2">Includes platform advertising</div>
        </Card>

        <Card className="p-5 space-y-3 border-accent-magenta/40" data-testid="premium-plus-col">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-accent-magenta" />
            <div className="font-display font-bold text-lg">Premium</div>
          </div>
          <div className="text-xs text-text-secondary">Everything in Free, plus:</div>
          <ul className="space-y-2">
            {data.benefits.map((b) => (
              <li key={b.key} data-testid={`premium-benefit-${b.key}`}
                      className="flex items-center gap-2 text-sm">
                <Check size={14} className="text-accent-mint" /> {b.title}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {!data.is_premium && (
        <div className="space-y-2">
          <div className="text-center text-sm text-text-secondary">
            {data.monthly_price != null && (
              <>{cur} {data.monthly_price}/mo · {cur} {data.annual_price}/yr</>
            )}
          </div>
          <Button variant="primary" className="w-full" data-testid="premium-start"
                      onClick={() => navigate("/pricing")}>
            {data.trial_days > 0
              ? `Try Premium free for ${data.trial_days} days`
              : "Start Premium"}
          </Button>
          {data.trial_days > 0 && (
            <div className="text-center text-xs text-text-faint">
              Then {cur} {data.annual_price}/yr. Cancel anytime.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
