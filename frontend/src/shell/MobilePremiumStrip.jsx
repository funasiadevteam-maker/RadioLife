// Phase LEGACY.1 — Mobile-only premium/ad strip.
//
// Renders a thin (≤32px) dismissible strip above the mini-player on mobile
// viewports.  Wraps the same `PersistentBannerSlot` component so the same
// ad inventory + attribution pipeline is reused.  On dismissal the choice
// is persisted in localStorage so the strip stays hidden for the session.
//
// This exists because on 375px viewports the ad slot inside the mini-player
// row is 360px wide and pushes the mini-player container tall enough to
// overlap the bottom nav.  Moving the ad above the mini-player restores
// a clean stacking (strip / mini-player / nav) with total height ≤ 96px.

import { useState } from "react";
import { X } from "lucide-react";
import PersistentBannerSlot from "@/components/PersistentBannerSlot";

const DISMISS_KEY = "bigfm.legacy1.mobilePremiumStrip.dismissed";

export default function MobilePremiumStrip() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return typeof window !== "undefined" &&
                    window.localStorage.getItem(DISMISS_KEY) === "1";
    } catch (_) { return false; }
  });

  if (dismissed) return null;

  const dismiss = () => {
    try { window.localStorage.setItem(DISMISS_KEY, "1"); } catch (_) {}
    setDismissed(true);
  };

  return (
    <div
      data-testid="mobile-premium-strip"
      className="flex items-center gap-2 pl-2 pr-1 py-1 min-h-[32px]
                              rounded-token-md border border-white/[0.08]
                              bg-bg-glass backdrop-blur-glass shadow-glass"
    >
      <div className="flex-1 min-w-0 overflow-hidden">
        <PersistentBannerSlot
          placement="miniplayer"
          style={{ maxWidth: "100%", padding: "2px 6px",
                          background: "transparent", border: "none" }}
        />
      </div>
      <button
        type="button"
        onClick={dismiss}
        data-testid="mobile-premium-strip-dismiss"
        aria-label="Dismiss upsell strip"
        className="p-1 rounded-md text-text-secondary hover:text-white
                                hover:bg-white/5 transition-colors flex-shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}
