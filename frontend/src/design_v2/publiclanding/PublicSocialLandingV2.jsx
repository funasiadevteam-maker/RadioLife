// FUUSIC public social-first landing (New Look V2 → Social). Self-contained
// (own nav/footer/player) and rendered bare by AppShellV2 for anonymous "/".
// One responsive layout + shared Light/Dark tokens; honours Business Setup Mode.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useLandingConfig } from "@/hooks/useLandingConfig";
import { fplTokens } from "./fplTokens";
import PublicNav from "./PublicNav";
import PublicHero from "./PublicHero";
import PublicLeftRail from "./PublicLeftRail";
import PublicWall from "./PublicWall";
import PublicRightRail from "./PublicRightRail";
import PublicPlayerBar from "./PublicPlayerBar";
import PublicFooter from "./PublicFooter";
import "./publiclanding.css";
import "../socialfeed/socialfeed.css";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const HERO_IMG = "https://images.unsplash.com/photo-1768321140311-ed354a0828e3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwxfHx3b21hbiUyMGhlYWRwaG9uZXMlMjBjaXR5JTIwc2t5bGluZSUyMG5pZ2h0JTIwbGlmZXN0eWxlfGVufDB8fHx8MTc5MTk2MTYzNHww&ixlib=rb-4.1.0&q=85";
const MODES = ["light", "dark", "system"];
const LANDING_THEME_KEY = "fuusic.landing.theme";
function systemPrefersDark() {
  try { return window.matchMedia("(prefers-color-scheme: dark)").matches; } catch (_e) { return false; }
}

const DEFAULT_HERO = {
  headline: "Everything You Love, Together.",
  subheadline: "Listen. Connect. Play. Shop. Earn.",
  supporting: "Discover your people, share experiences, explore radio stations worldwide, watch what's live, shop local, play games and earn BigPoints.",
  primary_cta_label: "Join FUUSIC for Free",
  secondary_cta_label: "Explore Live Now",
  chips: ["Radio Stations", "Live Experiences", "Friends & Communities", "Local Businesses", "Games", "BigPoints"],
};

function useSEO() {
  useEffect(() => {
    const prevTitle = document.title;
    document.title = "FUUSIC — Everything You Love, Together.";
    const desc = "Connect with friends, explore radio stations worldwide, discover live experiences, shop local, play games and earn BigPoints on FUUSIC.";
    let m = document.querySelector('meta[name="description"]');
    if (!m) { m = document.createElement("meta"); m.setAttribute("name", "description"); document.head.appendChild(m); }
    const prevDesc = m.getAttribute("content");
    m.setAttribute("content", desc);
    return () => { document.title = prevTitle; if (prevDesc != null) m.setAttribute("content", prevDesc); };
  }, []);
}

export default function PublicSocialLandingV2({ comingSoon = false, offerMonths = 6,
  waitlistEnabled = true }) {
  const navigate = useNavigate();
  const config = useLandingConfig((s) => s.config);
  useSEO();

  const cfg = config || {};
  const hero = { ...DEFAULT_HERO, ...(cfg.hero || {}), image_url: HERO_IMG };
  const allowThemeSwitch = cfg.allow_theme_switch !== false;
  const stationCopy = cfg.station_copy_text || "Thousands of radio stations. One world of sound.";

  // Self-managed appearance: public default is Light (admin-configurable via
  // default_theme). Decoupled from the global dark-for-anon default so the
  // public homepage honours the spec without affecting the classic view.
  const [savedMode, setSavedMode] = useState(() => {
    try { const v = window.localStorage.getItem(LANDING_THEME_KEY); return MODES.includes(v) ? v : null; } catch (_e) { return null; }
  });
  const cfgDefault = MODES.includes(cfg.default_theme) ? cfg.default_theme : "light";
  const mode = savedMode || cfgDefault;
  const [sysDark, setSysDark] = useState(systemPrefersDark);
  const theme = mode === "system" ? (sysDark ? "dark" : "light") : (mode === "dark" ? "dark" : "light");
  const t = useMemo(() => fplTokens(theme), [theme]);

  const setMode = useCallback((m) => {
    if (!MODES.includes(m)) return;
    setSavedMode(m);
    try { window.localStorage.setItem(LANDING_THEME_KEY, m); } catch (_e) { /* ignore */ }
  }, []);

  // Keep <html data-theme> in sync with the resolved landing theme + react to
  // OS changes while on "system".
  useEffect(() => {
    try { document.documentElement.setAttribute("data-theme", theme); } catch (_e) { /* ignore */ }
  }, [theme]);
  useEffect(() => {
    let mql;
    try {
      mql = window.matchMedia("(prefers-color-scheme: dark)");
      const on = () => setSysDark(mql.matches);
      mql.addEventListener("change", on);
      return () => mql.removeEventListener("change", on);
    } catch (_e) { /* ignore */ }
  }, []);

  // Data
  const [feed, setFeed] = useState([]);
  const [feedMeta, setFeedMeta] = useState({ loading: true, hasMore: false, offset: 0 });
  const [people, setPeople] = useState([]);
  const [live, setLive] = useState([]);
  const [discover, setDiscover] = useState([]);
  const [promos, setPromos] = useState([]);

  const loadFeed = useCallback(async (offset = 0) => {
    setFeedMeta((m) => ({ ...m, loading: true }));
    try {
      const r = await axios.get(`${API}/public/feed`, { params: { limit: 6, offset } });
      const items = r.data?.items || [];
      setFeed((prev) => (offset === 0 ? items : [...prev, ...items]));
      setFeedMeta({ loading: false, hasMore: !!r.data?.has_more, offset: offset + items.length });
    } catch (_e) {
      setFeedMeta({ loading: false, hasMore: false, offset });
    }
  }, []);

  useEffect(() => { loadFeed(0); }, [loadFeed]);
  useEffect(() => {
    let alive = true;
    axios.get(`${API}/public/people`).then((r) => { if (alive) setPeople(r.data?.people || []); }).catch(() => {});
    axios.get(`${API}/public/live-now`).then((r) => {
      if (!alive) return;
      setLive(r.data?.live || []); setDiscover(r.data?.discover || []);
    }).catch(() => {});
    axios.get(`${API}/public/promos`).then((r) => { if (alive) setPromos(r.data?.promos || []); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  // Landing analytics (best-effort)
  useEffect(() => {
    axios.post(`${API}/shell/landing-event`, { event: "social_landing_view" }).catch(() => {});
  }, []);

  const wallRef = useRef(null);
  const onAuth = useCallback((kind) => {
    // Business + staff/admin sign-in stay reachable even in Setup/ComingSoon.
    if (kind === "business") { navigate("/for-business"); return; }
    if (kind === "staff") { navigate("/portal/login"); return; }
    if (comingSoon) { navigate("/waitlist"); return; }
    navigate("/login");
  }, [comingSoon, navigate]);

  const onNavigate = useCallback((to) => {
    if (!to) return;
    if (to === "/") { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    if (comingSoon) { onAuth("waitlist"); return; }
    navigate(to);
  }, [comingSoon, navigate, onAuth]);

  const onExplore = useCallback(() => {
    if (wallRef.current) wallRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const signupLabel = comingSoon ? "Join Waitlist" : "Sign Up";

  return (
    <div className="fpl" style={{ background: t.pageBg, color: t.text }}>
      <PublicNav t={t} mode={mode} setMode={setMode} allowThemeSwitch={allowThemeSwitch}
        comingSoon={comingSoon} onNavigate={onNavigate} onAuth={onAuth} signupLabel={signupLabel} />

      <main>
        <div className="fpl-shell">
          <PublicHero t={t} hero={hero} comingSoon={comingSoon} offerMonths={offerMonths}
            waitlistEnabled={waitlistEnabled} onAuth={onAuth} onExplore={onExplore} stationCopy={stationCopy} />

          <div className="fpl-grid" ref={wallRef}>
            <PublicLeftRail t={t} onNavigate={onNavigate} />
            <PublicWall t={t} items={feed} loading={feedMeta.loading} hasMore={feedMeta.hasMore}
              onLoadMore={() => loadFeed(feedMeta.offset)} onFollow={() => onAuth("login")}
              onAuth={onAuth} onNavigate={onNavigate} />
            <PublicRightRail t={t} people={people} live={live} discover={discover} promos={promos}
              onAuth={onAuth} onNavigate={onNavigate} />
          </div>
        </div>

        <PublicFooter t={t} onNavigate={onNavigate} onAuth={onAuth} signupLabel={signupLabel} />
      </main>

      <PublicPlayerBar t={t} onActivate={() => onAuth("login")} />
    </div>
  );
}
