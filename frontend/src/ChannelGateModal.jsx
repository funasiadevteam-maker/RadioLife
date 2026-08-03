// Phase 10c — Channel access gating modal.
// Renders when a user tries to start a channel they don't have access to.
// Surfaces the message + a contextual CTA (upgrade, earn badges, etc.)
// Pulls all copy from the backend `access` / 403 detail payload so this
// stays a thin presentational component.

import { Lock, Crown, Sparkles, ArrowRight, X } from "lucide-react";

export default function ChannelGateModal({ access, channel, onClose, onCta }) {
  if (!access) return null;
  const upgradePath = access.upgrade_path;
  const cta = access.cta || {};
  const reqLevel = cta.required_level;
  const pointsNeeded = cta.points_needed;
  const currentPoints = cta.current_points || 0;
  const requiredPoints = cta.required_points || 0;
  const progressPct = requiredPoints > 0
    ? Math.min(100, Math.round((currentPoints / requiredPoints) * 100))
    : 0;

  const Icon = upgradePath === "premium" ? Crown
    : upgradePath === "earn_badges" ? Sparkles
    : Lock;
  const iconAccent = upgradePath === "premium" ? "#F5D76E"
    : upgradePath === "earn_badges" ? "#22d3ee"
    : "#ff2d95";

  return (
    <div className="channel-gate-modal-backdrop"
          data-testid="channel-gate-modal"
          onClick={onClose}>
      <div className="channel-gate-modal" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="cgm-close"
                  data-testid="channel-gate-modal-close" onClick={onClose}>
          <X size={16} />
        </button>
        <div className="cgm-icon-wrap" style={{ "--cgm-accent": iconAccent }}>
          <Icon size={28} className="cgm-icon" />
        </div>
        <div className="cgm-channel-name mono" data-testid="channel-gate-channel-name">
          {channel?.name || access.channel_name || "This channel"}
        </div>
        <div className="cgm-headline" data-testid="channel-gate-message">
          {access.unlock_message
            || access.message
            || "This channel is currently locked."}
        </div>
        {upgradePath === "earn_badges" && requiredPoints > 0 && (
          <div className="cgm-progress-block" data-testid="channel-gate-progress">
            <div className="cgm-progress-meta mono">
              <span>{currentPoints} pts</span>
              <span>{requiredPoints} pts to L{reqLevel}</span>
            </div>
            <div className="cgm-progress-bar">
              <div className="cgm-progress-fill"
                    style={{ width: `${progressPct}%`,
                                background: iconAccent }} />
            </div>
            <div className="cgm-progress-needed mono">
              {pointsNeeded} more to unlock
            </div>
          </div>
        )}
        <button type="button" className="cgm-cta-btn"
                  data-testid="channel-gate-cta"
                  onClick={() => onCta && onCta(access)}>
          {cta.label || (upgradePath === "premium"
                              ? "Upgrade to Premium"
                              : upgradePath === "earn_badges"
                              ? "Earn more points"
                              : "Learn more")}
          <ArrowRight size={14} />
        </button>
        <button type="button" className="cgm-secondary"
                  data-testid="channel-gate-dismiss"
                  onClick={onClose}>
          Stay on free channels
        </button>
      </div>
    </div>
  );
}
