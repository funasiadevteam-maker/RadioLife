/** Phase 42 S1 UX correction — page-top global leaderboard.
 *
 *  Renders ABOVE the AppShell header/nav, full-width on a transparent
 *  band, on every authed page that's in the visible-route allow-list.
 *  Not sticky (TOI-style scroll-away).
 *
 *  Scope: replaces the per-page <BannerAdSlot slotKey="top_leaderboard"/>
 *  sprinkles that used to sit BELOW the page header.
 */
import React, { useMemo } from "react";
import { useLocation } from "react-router-dom";
import BannerAdSlot from "@/components/BannerAdSlot";

const ROUTES = [
  { test: /^\/$/,                 route: "/home" },
  { test: /^\/radio(\?|$)/,       route: "/channels" },
  { test: /^\/community(\?|$)/,    route: "/community" },
  { test: /^\/news(\/|\?|$)/,     route: "/news" },
  { test: /^\/passport(\/|\?|$)/, route: "/social-passport" },
  { test: /^\/wallet(\?|$)/,      route: "/wallet" },
  { test: /^\/commute(\?|$)/,     route: "/commute" },
  { test: /^\/places(\?|\/|$)/,   route: "/places" },
];

export default function GlobalTopLeaderboard() {
  const { pathname } = useLocation();
  const pageRoute = useMemo(() => {
    for (const r of ROUTES) if (r.test.test(pathname)) return r.route;
    return null;
  }, [pathname]);
  if (!pageRoute) return null;
  return (
    <div data-testid="global-top-leaderboard"
         style={{ width: "100%", display: "flex", justifyContent: "center",
                  background: "#0b0b0b",
                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                  padding: "6px 12px" }}>
      <BannerAdSlot slotKey="top_leaderboard" pageRoute={pageRoute} />
    </div>
  );
}
