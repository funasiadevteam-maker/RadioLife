/**
 * Phase 41 Session 2.B — community-station listener-session hook.
 *
 * Mounted from Radio.js whenever a community station is active. Calls
 *   POST /api/stations/{slug}/listen/join      (on slug change)
 *   POST /api/stations/{slug}/listen/ping      (every 30 s)
 *   POST /api/stations/{slug}/listen/leave     (on cleanup / unload)
 *
 * The endpoint returns 404 `not_community_station` for admin channel
 * slugs — the hook silently swallows that so it's safe to mount for
 * every channel switch without filtering first.
 *
 * The "unload" leave uses `navigator.sendBeacon` so it fires even on
 * hard-close / mobile bg.  Falls back to a plain axios call when
 * sendBeacon is unavailable.
 */
import { useEffect, useRef } from "react";
import axios from "axios";
import { API } from "@/AuthContext";

const PING_INTERVAL_MS = 30 * 1000;

// Stable anon id stored in localStorage so the same anon device doesn't
// inflate the live count by rejoining repeatedly. Not used for auth.
function getAnonId() {
  try {
    let id = localStorage.getItem("bigfm_anon_listener_id");
    if (!id) {
      id = "anon_" + Math.random().toString(36).slice(2, 10)
                    + Date.now().toString(36).slice(-4);
      localStorage.setItem("bigfm_anon_listener_id", id);
    }
    return id;
  } catch { return null; }
}

export default function useStationListenerSession(activeSlug, isPlaying) {
  const sessionRef = useRef(null);
  const pingRef    = useRef(null);

  useEffect(() => {
    if (!activeSlug || !isPlaying) {
      // No active community listening → cleanup any prior session.
      return undefined;
    }
    let cancelled = false;
    let sessionToken = null;

    const join = async () => {
      try {
        const r = await axios.post(
          `${API}/stations/${encodeURIComponent(activeSlug)}/listen/join`,
          { anon_id: getAnonId() },
          { withCredentials: true });
        if (cancelled) return;
        sessionToken = r.data.session_token;
        sessionRef.current = { slug: activeSlug, token: sessionToken };
        pingRef.current = setInterval(async () => {
          try {
            await axios.post(
              `${API}/stations/${encodeURIComponent(activeSlug)}/listen/ping`,
              { session_token: sessionToken },
              { withCredentials: true });
          } catch (e) {
            // session_expired → rejoin once
            if (e.response?.data?.detail?.code === "session_expired") {
              join();
            }
          }
        }, PING_INTERVAL_MS);
      } catch (e) {
        // 404 not_community_station = admin channel → silently no-op
        if (e.response?.data?.detail?.code !== "not_community_station") {
          // Other errors aren't surfaced as toasts — listener tracking
          // is best-effort, not a blocker on playback.
        }
      }
    };
    join();

    // Always-installed unload handler: sendBeacon the leave call.
    const onUnload = () => {
      const cur = sessionRef.current;
      if (!cur || !cur.token) return;
      const url = `${API}/stations/${encodeURIComponent(cur.slug)}/listen/leave`;
      const blob = new Blob(
        [JSON.stringify({ session_token: cur.token })],
        { type: "application/json" });
      try {
        if (navigator.sendBeacon) {
          navigator.sendBeacon(url, blob);
        } else {
          // Last-resort fire-and-forget — `keepalive` is the spec hook.
          fetch(url, { method: "POST", body: blob, keepalive: true,
                          credentials: "include",
                          headers: { "Content-Type": "application/json" }});
        }
      } catch { /* */ }
    };
    window.addEventListener("beforeunload", onUnload);
    window.addEventListener("pagehide",     onUnload);

    return () => {
      cancelled = true;
      window.removeEventListener("beforeunload", onUnload);
      window.removeEventListener("pagehide",     onUnload);
      if (pingRef.current) { clearInterval(pingRef.current);
                              pingRef.current = null; }
      // Normal close path — not sendBeacon, so we get the real return.
      if (sessionToken) {
        axios.post(
          `${API}/stations/${encodeURIComponent(activeSlug)}/listen/leave`,
          { session_token: sessionToken },
          { withCredentials: true }).catch(() => { /* */ });
      }
      sessionRef.current = null;
    };
  }, [activeSlug, isPlaying]);
}
