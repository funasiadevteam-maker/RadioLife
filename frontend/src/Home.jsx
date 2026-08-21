// Home feed (redesign) — the feed IS the home. Filter chips re-query the
// feed: All = full feed; Radio/My stations/World = station grids;
// Eat/Salons/Fitness/Shops = venues filtered by that business category;
// Games / Trivia = their sections. Sponsored venue (real promotion) shows
// first, capped one per row.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Gamepad2, ChevronRight, Radio as RadioIcon, Trophy } from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import { StationTile } from "@/shell/primitives";
import { useGeoStore } from "@/store/useGeoStore";
import { useShellSummary, useShellFilter, fmtCount } from "@/shell/useShellData";
import {
  ShelfHeader, ShowCard16x9, VenueCard, NewsRow, absUrl,
} from "@/shell/cards";
import WaysToEarnCard from "@/rewards/WaysToEarnCard";
import LocalHighlightsStrip from "@/components/LocalHighlightsStrip";
import BannerAdSlot from "@/components/BannerAdSlot";
import OGMeta from "@/components/OGMeta";

export default function Home() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const summary = useShellSummary();
  const city = useGeoStore((s) => s.city);
  const chip = useShellFilter((s) => s.chip);

  const [channels, setChannels] = useState([]);
  const [venues, setVenues] = useState([]);
  const [news, setNews] = useState([]);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login", { replace: true }); return; }
    if (!user.onboarding_complete) { navigate("/onboarding", { replace: true }); return; }
  }, [user, loading, navigate]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/channels`).then((r) => setChannels(r.data?.channels || [])).catch(() => setChannels([]));
    axios.get(`${API}/news/headlines`, { params: { limit: 6 } })
      .then((r) => setNews(r.data?.items || [])).catch(() => setNews([]));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/shell/venues`, { params: { limit: 24 }, withCredentials: true })
      .then((r) => setVenues(r.data?.items || [])).catch(() => setVenues([]));
  }, [user]);

  if (!user) return null;

  const firstName = user?.first_name || user?.name?.split(" ")?.[0] || "there";
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const flagships = summary?.flagships || [];
  const gamesLive = summary?.badges?.games || 0;
  const isPremium = !!summary?.is_premium;

  // Sponsored-first ordering (backend already sorts; keep stable client-side).
  const orderVenues = (list) =>
    [...list].sort((a, b) => (b.sponsored ? 1 : 0) - (a.sponsored ? 1 : 0));

  const chipLabel = (summary?.chips || []).find((c) => c.key === chip)?.label || "";
  const catToken = chip.startsWith("cat_") ? chip.slice(4) : null;

  const openStation = (slug) => navigate(`/radio?ch=${encodeURIComponent(slug)}&autoplay=1`);

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
        <OGMeta entityType="home" entityId="x" title="RadioLife" description="Radio, shop & eat, games, news and rewards." />
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
        title="RadioLife — Personalized radio, news, and rewards"
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

      <section data-testid="home-clips">
        <ShelfHeader title="Clips" suffix="RJ MOMENTS · 15–60s" />
        <LocalHighlightsStrip />
      </section>

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

      <section data-testid="home-venues">
        <ShelfHeader title="Eat & earn near you"
          suffix={`${venues.length} VENUES${city ? " · " + city.toUpperCase() : ""}`}
          linkTo="/shop" linkLabel="Open Shop & Eat" />
        {venuesGrid(venues)}
      </section>

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
