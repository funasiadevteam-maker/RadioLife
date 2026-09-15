/** Phase 42 S2 — PageFrame.
 *
 *  TOI-style 3-column frame that sits OUTSIDE the AppShell:
 *    ┌────────────────────────────────────────────┐
 *    │            top_billboard (970x250)          │
 *    ├──────┬───────────────────────────────┬──────┤
 *    │  L   │                                │   R │
 *    │ sky  │   AppShell (nav + routes)     │ sky │
 *    │      │                                │     │
 *    └──────┴───────────────────────────────┴──────┘
 *    └────── mobile_sticky_bottom (320x50) ──────┘
 *
 *  Routes can opt OUT of the frame via the EXCLUDE list (login/admin/
 *  advertiser/checkout — places where ads would be inappropriate or
 *  conflict with chrome).
 */
import React, { useMemo } from "react";
import { useLocation } from "react-router-dom";
import BannerAdSlot from "@/components/BannerAdSlot";
import NowPlayingStrip from "@/components/NowPlayingStrip";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";

// Routes that should NEVER render the banner frame.
const EXCLUDE = [
  /^\/login/, /^\/signup/, /^\/onboarding/,
  /^\/admin/, /^\/advertiser/,
  /^\/checkout/, /^\/billing/, /^\/privacy/,
  /^\/r\//,           // station detail keeps its own header
  /^\/radio\/create/,
];

// Mapping from real pathname → canonical page_route used by backend
// page-pattern matching + frontend slot routing.
const ROUTE_MAP = [
  { test: /^\/$/,                  route: "/home" },
  { test: /^\/radio$/,             route: "/channels" },
  { test: /^\/community/,          route: "/community" },
  { test: /^\/news/,               route: "/news" },
  { test: /^\/passport/,           route: "/social-passport" },
  { test: /^\/wallet/,             route: "/wallet" },
  { test: /^\/commute/,            route: "/commute" },
  { test: /^\/places/,             route: "/places" },
];

export default function PageFrame({ children }) {
  const { pathname } = useLocation();
  const variant = useDesignVariantStore((s) => s.variant);
  const excluded = useMemo(() => EXCLUDE.some(rx => rx.test(pathname)),
                              [pathname]);
  const pageRoute = useMemo(() => {
    for (const r of ROUTE_MAP) if (r.test.test(pathname)) return r.route;
    return null;
  }, [pathname]);

  // New Look V2 owns its own centered frame + right-rail ad inside
  // AppShellV2, so the shared TOI frame must not double-wrap it.
  if (variant === "new_look_v2") return <>{children}</>;
  if (excluded || !pageRoute) return <>{children}</>;

  return (
    <div data-testid="page-frame"
         style={{ display: "flex", flexDirection: "column",
                  minHeight: "100vh", background: "#0b0b0b" }}>
      {/* Phase 42 S2.3 — "Now playing on community radio" strip
            sits at y=0 where the removed top_billboard used to. NOT an
            ad slot — drives community-radio discovery. */}
      <NowPlayingStrip />

      {/* 3-column body: left sky / content / right sky. Skyscrapers
            sticky-pin at the top of viewport so they extend FROM TOP
            (TOI frame style), not below the content. Hidden on mobile
            via the `.bigfm-rail` class (see index.css). */}
      <style>{`
        @media (max-width: 1023px) {
          [data-testid="frame-left-rail"],
          [data-testid="frame-right-rail"] { display: none !important; }
        }
        @media (min-width: 1024px) {
          [data-testid="frame-mobile-sticky"] { display: none !important; }
        }
      `}</style>
      <div data-testid="frame-body"
           style={{ display: "flex", alignItems: "flex-start",
                    flex: 1, width: "100%" }}>
        {/* Phase 42 S2.2 — left_skyscraper render REMOVED per user
              feedback. Slot row preserved in `banner_ad_slots` for
              future direct-sold use. Content column reclaims that
              horizontal space; only right rail remains. */}

        <main data-testid="frame-content"
              style={{ flex: 1, minWidth: 0, minHeight: "100vh" }}>
          {children}
        </main>

        <aside data-testid="frame-right-rail"
               className="bigfm-rail bigfm-rail-right"
               style={{ flex: "0 0 180px", padding: "16px 12px 16px 8px",
                        position: "sticky", top: 0, alignSelf: "flex-start" }}>
          <BannerAdSlot slotKey="right_skyscraper" pageRoute={pageRoute} />
        </aside>
      </div>

      {/* Mobile-only sticky bottom — desktop-hidden via the slot's
            mobile_only flag in the decision response. */}
      <div data-testid="frame-mobile-sticky"
           style={{ position: "fixed", bottom: 0, left: 0, right: 0,
                    display: "flex", justifyContent: "center",
                    zIndex: 50, pointerEvents: "none" }}>
        <div style={{ pointerEvents: "auto" }}>
          <BannerAdSlot slotKey="mobile_sticky_bottom" pageRoute={pageRoute} />
        </div>
      </div>
    </div>
  );
}
