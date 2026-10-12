// Persistent FUUSIC Social-Feed chrome (V2 light / V3 dark). Wraps every
// in-app route when the user's home view is a Social Feed: themed sticky
// header + left nav + right discovery rail (home only) + audio dock +
// mobile bottom nav. The center renders the routed page (the Home feed at "/").
import { useEffect, useState, useCallback } from "react";
import { useLocation } from "react-router-dom";
import axios from "axios";
import { sfTokens } from "./sfTheme";
import {
  SfHeader, LeftSidebar, RightRail, AudioDock, BottomNav, InlineDiscovery,
} from "./socialFeedParts";
import "./socialfeed.css";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function SocialFeedShell({ appearance = "light", children }) {
  const t = sfTokens(appearance);
  const { pathname } = useLocation();
  const isHome = pathname === "/";
  const [rail, setRail] = useState([]);

  const loadRail = useCallback(() => {
    const route = pathname.startsWith("/social") ? "/social"
      : pathname.startsWith("/shop") ? "/shop"
      : pathname.startsWith("/listen") ? "/channels" : "/home";
    axios.get(`${API}/social/rail`, { params: { page_route: route, limit: 7 }, withCredentials: true })
      .then((r) => setRail(r.data?.cards || [])).catch(() => {});
  }, [pathname]);
  useEffect(() => { loadRail(); }, [loadRail]);

  const onFollow = useCallback((id) => {
    if (!id) return;
    axios.post(`${API}/social/follow/${id}`, {}, { withCredentials: true }).catch(() => {});
  }, []);

  return (
    <div className="sf-root" data-testid="social-feed-shell"
      style={{ background: t.canvas, color: t.text, minHeight: "100vh" }}>
      <SfHeader t={t} appearance={appearance} />
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "16px 14px 0",
                    display: "flex", gap: 20, alignItems: "flex-start" }}>
        <LeftSidebar t={t} />
        <main style={{ flex: 1, minWidth: 0, paddingBottom: 150 }}>
          {children}
          {isHome && (
            <div className="lg:hidden" style={{ marginTop: 16 }}>
              <InlineDiscovery t={t} rail={rail} onFollow={onFollow} />
            </div>
          )}
        </main>
        {isHome && <RightRail t={t} rail={rail} onFollow={onFollow} />}
      </div>
      <AudioDock t={t} />
      <BottomNav t={t} />
    </div>
  );
}
