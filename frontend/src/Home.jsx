// Home feed (redesign) — the feed IS the home. Filter chips re-query the
// feed: All = full feed; Radio/My stations/World = station grids;
// Eat/Salons/Fitness/Shops = venues filtered by that business category;
// Games / Trivia = their sections. Sponsored venue (real promotion) shows
// first, capped one per row.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Gamepad2, ChevronRight, Radio as RadioIcon, Trophy, Ticket, X, CheckCircle2 } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { StationTile } from "@/shell/primitives";
import { useGeoStore } from "@/store/useGeoStore";
import { useShellSummary, useShellFilter, fmtCount } from "@/shell/useShellData";
import {
  ShelfHeader, ShowCard16x9, ClipCard9x16, VenueCard, NewsRow, HScroll, absUrl,
} from "@/shell/cards";
import WaysToEarnCard from "@/rewards/WaysToEarnCard";
import BannerAdSlot from "@/components/BannerAdSlot";
import OGMeta from "@/components/OGMeta";

export default function Home() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const summary = useShellSummary();
  const city = useGeoStore((s) => s.city);
  const market = useGeoStore((s) => s.market);
  const chip = useShellFilter((s) => s.chip);

  const [channels, setChannels] = useState([]);
  const [venues, setVenues] = useState([]);
  const [clips, setClips] = useState([]);
  const [news, setNews] = useState([]);
  const [claimClip, setClaimClip] = useState(null);
  const [claiming, setClaiming] = useState(false);
  const [claimResult, setClaimResult] = useState(null);
  const [flagshipsOverride, setFlagshipsOverride] = useState(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login", { replace: true }); return; }
    if (!user.onboarding_complete) { navigate("/onboarding", { replace: true }); return; }
  }, [user, loading, navigate]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/channels`).then((r) => setChannels(r.data?.channels || [])).catch(() => setChannels([]));
  }, [user]);

  // News follows the single geo source — matches the listener's detected city.
  useEffect(() => {
    if (!user) return;
    const params = { limit: 6 };
    if (market && market !== "global") params.market = market;
    axios.get(`${API}/news/headlines`, { params })
      .then((r) => setNews(r.data?.items || [])).catch(() => setNews([]));
  }, [user, market]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/shell/venues`, { params: { limit: 24, market, city }, withCredentials: true })
      .then((r) => setVenues(r.data?.items || [])).catch(() => setVenues([]));
  }, [user, market, city]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/shell/clips`, { params: { limit: 10 }, withCredentials: true })
      .then((r) => setClips(r.data?.items || [])).catch(() => setClips([]));
  }, [user]);

  // Self-heal flagship art on every home load (and right after login):
  // the backend regenerates any flagship whose cover is only a placeholder
  // OR whose stored art file has vanished (e.g. a prod redeploy wiped the
  // disk). Idempotent + fire-and-forget; we refresh tiles once it settles.
  const flCount = summary?.flagship_count || 0;
  useEffect(() => {
    const fl = summary?.flagships || [];
    if (!user || !fl.length) return;
    axios.post(`${API}/imported-stations/ensure-flagship-art`).catch(() => {});
    const t = setTimeout(() => {
      axios.get(`${API}/shell/summary`, { withCredentials: true })
        .then((r) => setFlagshipsOverride(r.data?.flagships || null)).catch(() => {});
    }, 18000);
    return () => clearTimeout(t);
  }, [user, flCount]);

  if (!user) return null;

  const firstName = user?.first_name || user?.name?.split(" ")?.[0] || "there";
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const flagships = flagshipsOverride || summary?.flagships || [];
  const gamesLive = summary?.badges?.games || 0;
  const isPremium = !!summary?.is_premium;

  // Sponsored-first ordering (backend already sorts; keep stable client-side).
  const orderVenues = (list) =>
    [...list].sort((a, b) => (b.sponsored ? 1 : 0) - (a.sponsored ? 1 : 0));

  const chipLabel = (summary?.chips || []).find((c) => c.key === chip)?.label || "";
  const catToken = chip.startsWith("cat_") ? chip.slice(4) : null;

  const openStation = (slug) => navigate(`/radio?ch=${encodeURIComponent(slug)}&autoplay=1`);

  // Sponsored clips open the claim sheet; station clips open the station.
  const openClip = (c) => {
    if (c.sponsored && c.campaign_id) { setClaimResult(null); setClaimClip(c); return; }
    if (c.business_id) { navigate(`/shop/${c.business_id}`); return; }
    if (c.slug) { openStation(c.slug); return; }
    navigate("/radio");
  };
  const doClaim = async () => {
    if (!claimClip) return;
    setClaiming(true);
    try {
      const r = await axios.post(`${API}/shell/clips/claim`,
        { campaign_id: claimClip.campaign_id }, { withCredentials: true });
      setClaimResult(r.data);
    } catch (_e) {
      setClaimResult({ ok: false, error: "Couldn't claim right now — please try again." });
    } finally { setClaiming(false); }
  };

  const stationGrid = (items, kind) => (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4"
      data-testid="home-station-grid">
      {items.map((s) => (
        <StationTile key={(s.slug || s.id) + kind} name={s.name} dj={s.dj || s.city || s.tagline}
          live={kind === "flagship" ? s.live : !!s.is_live}
          artwork={absUrl(kind === "flagship" ? s.art : s.thumbnail_url)}
          onPlay={() => (kind === "flagship"
            ? navigate(`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`)
            : openStation(s.slug))} />
      ))}
    </div>
  );

  const greeting = () => (
    <div data-testid="home-resume-strip" className="flex flex-wrap items-center gap-3">
      <div className="font-display font-bold text-xl sm:text-2xl tracking-display-tight">
        {greet}, <span className="text-accent-electric" data-testid="home-welcome-name">{firstName}</span>
      </div>
      {channels[0] && (
        <button type="button" onClick={() => openStation(channels[0].slug)} data-testid="home-recent-resume"
          className="ml-auto inline-flex items-center gap-2 rl-card px-3.5 h-9 text-sm font-semibold text-text-secondary hover:text-text-primary transition-colors">
          <RadioIcon size={15} className="text-accent-electric" />
          Pick up where you left off — {channels[0].name || "your station"} · Resume
        </button>
      )}
    </div>
  );

  const venuesGrid = (list) => {
    const ordered = orderVenues(list);
    if (!ordered.length) {
      return (
        <div data-testid="home-venues-empty" className="rl-card p-6 text-sm text-text-secondary">
          No spots{chipLabel ? ` under ${chipLabel}` : ""}{city ? ` in ${city}` : ""} yet — check back soon.
        </div>
      );
    }
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {ordered.slice(0, 8).map((o, idx) => (
          <VenueCard key={o.business_id} testId={`home-venue-${o.business_id}`}
            name={o.name} category={o.category_label} rating={o.rating} earn={o.earn}
            image={o.image} status={idx === 0 && o.sponsored ? "sponsored" : undefined}
            onOpen={() => navigate(`/shop/${o.business_id}`)} />
        ))}
      </div>
    );
  };

  // ── Filtered views (chip !== "all") ──────────────────────────────────
  if (chip !== "all") {
    let body = null;
    if (chip === "radio" || chip === "world") {
      body = (
        <section data-testid="home-filter-radio">
          <ShelfHeader title="Radio stations"
            suffix={`${summary?.ai_count || channels.length} AI + ${fmtCount(summary?.world_count)} WORLD`}
            linkTo="/radio" linkLabel="Browse all" />
          {stationGrid(channels, "channel")}
        </section>
      );
    } else if (chip === "mine") {
      body = (
        <section data-testid="home-filter-mine">
          <ShelfHeader title="My stations" suffix={`★ ${summary?.flagship_count || 0} FLAGSHIPS`} linkTo="/radio" />
          {flagships.length ? stationGrid(flagships, "flagship")
            : <div className="rl-card p-6 text-sm text-text-secondary">Follow a station to see it here.</div>}
        </section>
      );
    } else if (catToken || chip === "offers") {
      body = (
        <section data-testid="home-filter-shop">
          <ShelfHeader title={`Shop & Eat${chipLabel && catToken ? " · " + chipLabel : ""}`}
            suffix={city ? city.toUpperCase() : "EARN BIGPOINTS"} linkTo="/shop" linkLabel="Open Shop & Eat" />
          {venuesGrid(catToken ? venues.filter((o) => (o.category || "").toLowerCase() === catToken) : venues)}
        </section>
      );
    } else if (chip === "games") {
      body = <GamesStrip gamesLive={gamesLive} navigate={navigate} />;
    } else if (chip === "trivia") {
      body = (
        <section data-testid="home-filter-trivia" className="space-y-4">
          <button type="button" onClick={() => navigate("/trivia")} data-testid="home-trivia-cta"
            className="w-full rl-card p-5 flex items-center gap-4 text-left hover:-translate-y-0.5 transition-transform duration-150">
            <div className="w-12 h-12 rounded-token-md grid place-items-center shrink-0"
              style={{ background: "color-mix(in srgb, var(--accent-gold) 18%, transparent)", color: "var(--accent-gold)" }}>
              <Trophy size={24} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-display font-bold tracking-display-tight">Daily Trivia</div>
              <div className="text-sm text-text-secondary truncate">Answer today&apos;s quiz for BigPoints and free spins.</div>
            </div>
            <span className="inline-flex items-center gap-1 text-sm font-bold text-accent-electric shrink-0">Play <ChevronRight size={16} /></span>
          </button>
          <WaysToEarnCard />
        </section>
      );
    }
    return (
      <div data-testid="home-root" className="space-y-9 max-w-[1400px]">
        <OGMeta entityType="home" entityId="x" title="FUUSIC" description="Radio, shop & eat, games, news and rewards." />
        {greeting()}
        {body}
        <div className="h-24" />
      </div>
    );
  }

  // ── Default full feed (chip === "all") ───────────────────────────────
  return (
    <div data-testid="home-root" className="space-y-9 max-w-[1400px]">
      <OGMeta entityType="home" entityId="x"
        title="FUUSIC — Personalized radio, news, and rewards"
        description="Radio, shop & eat, games, news, and rewards — all in one feed." />

      {greeting()}

      {channels.length > 0 && (
        <section data-testid="home-stations" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {channels.slice(0, 3).map((c) => (
            <ShowCard16x9 key={c.slug} testId={`home-show-${c.slug}`}
              title={c.name || c.slug} station={c.tagline || c.dj} city={city}
              live={!!c.is_live} image={c.thumbnail_url}
              onOpen={() => openStation(c.slug)} />
          ))}
        </section>
      )}

      {clips.length > 0 && (
        <section data-testid="home-clips">
          <ShelfHeader title="Clips" suffix="RJ MOMENTS · 15–60s" />
          <HScroll itemClass="w-[150px] sm:w-[165px]">
            {clips.map((c) => (
              <ClipCard9x16 key={c.id} testId={`home-clip-${c.id}`}
                title={c.title} channel={c.channel} image={c.image} sponsored={c.sponsored}
                onOpen={() => openClip(c)} />
            ))}
          </HScroll>
        </section>
      )}

      {flagships.length > 0 && (
        <section data-testid="home-your-stations">
          <ShelfHeader title="Your stations"
            suffix={`★ ${summary.flagship_count} FLAGSHIPS + ${fmtCount(summary.world_count)} WORLD`}
            linkTo="/radio" />
          {stationGrid(flagships.slice(0, 4), "flagship")}
        </section>
      )}

      {!isPremium && (
        <div data-testid="ad-infeed" className="flex justify-center">
          <BannerAdSlot slotKey="featured_horizontal" pageRoute="/home" />
        </div>
      )}

      {venues.length > 0 && (
        <section data-testid="home-venues">
          <ShelfHeader title="Eat & earn near you"
            suffix={`${venues.length} VENUES${city ? " · " + city.toUpperCase() : ""}`}
            linkTo="/shop" linkLabel="Open Shop & Eat" />
          {venuesGrid(venues)}
        </section>
      )}

      {news.length > 0 && (
        <section data-testid="home-news">
          <ShelfHeader title="News for you" suffix={city ? `LOCAL · ${city.toUpperCase()}` : ""} linkTo="/news" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {news.slice(0, 3).map((n) => (
              <NewsRow key={n.headline_id || n.id} testId={`home-news-${n.headline_id || n.id}`}
                title={n.headline_text || n.title} source={n.source_name || n.source_id}
                time={fmtTime(n.published_at || n.pubDate)} image={n.image_url}
                onOpen={() => { const u = n.source_url || n.link; if (u) window.open(u, "_blank", "noopener"); else navigate("/news"); }} />
            ))}
          </div>
        </section>
      )}

      <GamesStrip gamesLive={gamesLive} navigate={navigate} />

      <WaysToEarnCard />

      {!isPremium && (
        <div data-testid="ad-infeed-2" className="flex justify-center">
          <BannerAdSlot slotKey="mid_horizontal" pageRoute="/home" />
        </div>
      )}

      {claimClip && (
        <div data-testid="clip-claim-overlay" className="fixed inset-0 z-[95] flex items-end sm:items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.6)" }} onClick={() => setClaimClip(null)}>
          <div data-testid="clip-claim-sheet" onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rl-card overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
            <div className="relative h-40 w-full overflow-hidden bg-bg-elevated">
              {claimClip.image
                ? <img src={claimClip.image} alt={claimClip.channel} className="w-full h-full object-cover" />
                : <div className="w-full h-full" style={{ background: "linear-gradient(135deg,var(--accent-electric),var(--accent-magenta))" }} />}
              <span className="absolute top-3 left-3 text-[10px] font-black tracking-wide px-2 py-1 rounded-full"
                style={{ background: "var(--accent-gold)", color: "#0a0a0c" }}>SPONSORED</span>
              <button type="button" data-testid="clip-claim-close" onClick={() => setClaimClip(null)}
                aria-label="Close" className="absolute top-3 right-3 w-8 h-8 grid place-items-center rounded-full"
                style={{ background: "rgba(0,0,0,0.5)", color: "#fff" }}>
                <X size={16} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <div className="text-xs font-bold text-accent-electric">{claimClip.channel}</div>
                <div className="font-display font-bold text-lg tracking-display-tight text-text-primary">{claimClip.offer || claimClip.title}</div>
              </div>
              {claimResult?.ok ? (
                <div data-testid="clip-claim-success" className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--accent-green,#22c55e)" }}>
                    <CheckCircle2 size={18} /> {claimResult.already ? "Already claimed" : "Offer claimed!"}
                  </div>
                  <div className="rl-card p-4 text-center">
                    <div className="text-xs text-text-secondary mb-1">Show this code in-store</div>
                    <div data-testid="clip-claim-code" className="font-display font-black text-2xl tracking-widest text-text-primary">{claimResult.code}</div>
                  </div>
                  <button type="button" data-testid="clip-claim-done" onClick={() => setClaimClip(null)}
                    className="w-full py-3 rounded-token-md font-bold" style={{ background: "var(--text-primary)", color: "var(--bg-base)" }}>
                    Done
                  </button>
                </div>
              ) : (
                <button type="button" data-testid="clip-claim-btn" onClick={doClaim} disabled={claiming}
                  className="w-full py-3 rounded-token-md font-bold flex items-center justify-center gap-2 disabled:opacity-60"
                  style={{ background: "var(--accent-gold)", color: "#0a0a0c" }}>
                  <Ticket size={18} /> {claiming ? "Claiming…" : "Claim this offer"}
                </button>
              )}
              {claimResult && !claimResult.ok && (
                <div data-testid="clip-claim-error" className="text-sm text-center" style={{ color: "var(--accent-live,#ef4444)" }}>
                  {claimResult.error || "Something went wrong."}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="h-24" />
    </div>
  );
}

function GamesStrip({ gamesLive, navigate }) {
  return (
    <section data-testid="home-games">
      <button type="button" onClick={() => navigate("/play")} data-testid="home-games-strip"
        className="w-full rl-card p-5 flex items-center gap-4 text-left hover:-translate-y-0.5 transition-transform duration-150">
        <div className="w-12 h-12 rounded-token-md grid place-items-center shrink-0"
          style={{ background: "color-mix(in srgb, var(--accent-magenta) 18%, transparent)", color: "var(--accent-magenta)" }}>
          <Gamepad2 size={24} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-display font-bold tracking-display-tight">
            {gamesLive > 0 ? `${gamesLive} games live` : "Spin & Win is live"}
          </div>
          <div className="text-sm text-text-secondary truncate">
            Spin the wheel, trivia, predictions — play now for BigPoints.
          </div>
        </div>
        <span className="inline-flex items-center gap-1 text-sm font-bold text-accent-electric shrink-0">
          Play now <ChevronRight size={16} />
        </span>
      </button>
    </section>
  );
}

function fmtTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 60000;
    if (diff < 60) return `${Math.max(1, Math.round(diff))}m ago`;
    if (diff < 1440) return `${Math.round(diff / 60)}h ago`;
    return d.toLocaleDateString();
  } catch (_e) { return ""; }
}
