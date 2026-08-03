// Phase 15b — Home dashboard (logged-in landing). Per brief Section 4:
// 12-col grid, hero (Daypart + Resume) + side rail (Trivia + Wallet + Passport),
// followed by horizontal scrollers (Offers / Unlocked Games / Trivia / Podcasts).
// Wires existing endpoints; falls back to empty states gracefully so we never
// block the surface on network.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Radio as RadioIcon, Gamepad2, Brain, BadgeCheck, MapPin,
  ChevronRight, Sparkles, Podcast, Mic, Megaphone, ShieldCheck,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import {
  Card, Button, Chip, LiveDot, StationTile, GameTile, WalletItemCard,
} from "@/shell/primitives";
import { useRoleNav } from "@/lib/roleNav";  // Phase 19a — role-aware Home quick actions
// Phase 15d — Local news mini-widget + geo store.
import LocalNewsWidget from "@/components/LocalNewsWidget";
import { useGeoStore } from "@/store/useGeoStore";
// Phase B — personalized city tags (Home/Visiting/Live + heat fill).
import { useCityTags } from "@/hooks/useCityTags";
// Phase 18 — top-game/top-channel rec cards + favorites strip.
import {
  TopGameRecCard, TopChannelRecCard, FavoritesStrip,
} from "@/components/Phase18Home";
// Phase 40 — Latest News strip below hero CTAs.
// Phase 41 — HomeNewsStrip moved to /community (Phase 41 Session 3 surface).
// Phase 42 S1 — Top banner ad slot (free-tier only).
import BannerSlot from "@/components/BannerSlot";
// Phase 42 S1 Option B — v2 banner slot component (sprinkled across pages).
import BannerAdSlot from "@/components/BannerAdSlot";
// Phase R — Breaking News Ribbon (dismissable per-session).
import BreakingNewsRibbon from "@/components/BreakingNewsRibbon";
// Phase 42-E2.1 — Cinematic feature tiles + Local highlights.
import FeatureTileCard from "@/components/FeatureTileCard";
import LocalHighlightsStrip from "@/components/LocalHighlightsStrip";
// Phase 42-E2.2 — Universal share button.
import ShareButton from "@/components/ShareButton";
// Phase 42-E2.4 — OG meta tags for social previews.
import OGMeta from "@/components/OGMeta";
// Phase K.7b — image-backed landscape promo banners.
import PromoBannerCard from "@/components/PromoBannerCard";
// Phase FUN.1 — Flagship stations hero strip.
import FlagshipStrip from "@/components/FlagshipStrip";

export default function Home() {
  const { user, loading } = useAuth();
  const { canCreator, canAdvertiser, canAdmin } = useRoleNav();  // Phase 19a
  const navigate = useNavigate();
  const [channels, setChannels] = useState([]);
  // Phase 39 Session 3 — Try Chat tile state.
  const [myPersona, setMyPersona] = useState(null);
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/personas/me`,
                                                          { withCredentials: true });
        if (!cancel) setMyPersona(r.data?.persona || null);
      } catch (e) { /* silent — feature degrades */ }
    })();
    return () => { cancel = true; };
  }, []);
  const [wallet, setWallet] = useState(null);
  // Phase 42-E2.1 — six cinematic feature tiles from /api/home/feature-tiles.
  const [tiles, setTiles] = useState([]);
  // Phase K.7b — marketing asset map for image-backed promo banners.
  const [mktAssets, setMktAssets] = useState({});
  // Phase 15d — resolved market drives Trivia subtitle, news widget, etc.
  const city = useGeoStore((s) => s.city);
  const country = useGeoStore((s) => s.country);
  // Phase B — personalized city tags (Home / Visiting / Live + heat fill).
  const { tags: cityTags } = useCityTags();

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login", { replace: true }); return; }
    if (!user.onboarding_complete) { navigate("/onboarding", { replace: true }); return; }
  }, [user, loading, navigate]);

  useEffect(() => {
    if (!user) return;
    axios.get(`${API}/channels`).then((r) => setChannels(r.data?.channels || []))
            .catch(() => setChannels([]));
    axios.get(`${API}/bigcoin/me`).then((r) => setWallet(r.data))
            .catch(() => setWallet(null));
    // Phase 42-E2.1 — fetch the cinematic feature tile config.
    axios.get(`${API}/home/feature-tiles`)
            .then((r) => setTiles(r.data?.tiles || []))
            .catch(() => setTiles([]));
    // Phase K.7b — fetch the marketing asset map for promo banners.
    axios.get(`${API}/marketing/assets`)
            .then((r) => setMktAssets(r.data?.by_key || {}))
            .catch(() => setMktAssets({}));
  }, [user]);

  if (!user) return null;

  const featured = channels.slice(0, 4);
  const hour = new Date().getHours();
  const daypart =
    hour < 6  ? "Late Night Mehfil" :
    hour < 11 ? "Morning Caravan"    :
    hour < 15 ? "Lunch Rush"          :
    hour < 19 ? "Evening Drive"       :
                "Night Lounge";

  return (
    <div data-testid="home-root" className="space-y-10">
      {/* Phase 42-E2.4 — OG meta for social previews of the home URL. */}
      <OGMeta
        entityType="home"
        entityId="x"
        title="BigFM — Personalized radio, news, and rewards"
        description="Six ways to play tonight: predict & win, games, news radio, points, commute, social passport." />

      {/* Phase FUN.1 — Flagship (FunAsia Network) stations, always at the top.
              Phase F — passes `matchesCountryCode` so the "🔥 Boosted" chip can
              overlay on any card that has a live activation in the user's region. */}
      <FlagshipStrip category="home" title="Flagship Stations"
                                        matchesCountryCode={country || null}
                                        testId="home-flagship-strip" />

      {/* ── Phase K.8 — Featured stations MOVED to the very top.
            The 4 BigFM AI station tiles are the first thing visitors
            see — real images, live indicators, immediate tap-to-play. */}
      {featured.length > 0 && (
        <section data-testid="home-stations">
          <SectionHeader title="Featured stations" linkTo="/radio" />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {featured.map((c) => (
              <StationTile
                key={c.slug}
                name={c.name || c.slug}
                dj={c.tagline || c.dj || ""}
                live={!!c.is_live}
                artwork={c.thumbnail_url ? `${process.env.REACT_APP_BACKEND_URL || ""}${c.thumbnail_url}` : null}
                onPlay={() => navigate(`/radio?ch=${encodeURIComponent(c.slug)}`)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Phase 19a — role-aware quick-actions strip. Listeners see nothing. */}
      {(canCreator || canAdvertiser || canAdmin) && (
        <section data-testid="home-quick-actions"
                          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {canCreator && (
            <Link to="/creator" data-testid="home-quick-studio"
                        className="rounded-token-card border border-white/[0.06]
                                                p-4 bg-white/[0.02] hover:bg-white/[0.05]
                                                transition-colors duration-150 flex items-center gap-3">
              <Mic size={18} className="text-accent-electric" />
              <div className="min-w-0">
                <div className="font-display font-bold text-sm tracking-display-tight">
                  Open Creator Studio
                </div>
                <div className="text-xs text-text-secondary">
                  Episodes, channels, magic clips
                </div>
              </div>
            </Link>
          )}
          {canAdvertiser && (
            <Link to="/advertiser" data-testid="home-quick-advertiser"
                        className="rounded-token-card border border-white/[0.06]
                                                p-4 bg-white/[0.02] hover:bg-white/[0.05]
                                                transition-colors duration-150 flex items-center gap-3">
              <Megaphone size={18} className="text-accent-magenta" />
              <div className="min-w-0">
                <div className="font-display font-bold text-sm tracking-display-tight">
                  Advertiser dashboard
                </div>
                <div className="text-xs text-text-secondary">
                  Campaigns, creatives, analytics
                </div>
              </div>
            </Link>
          )}
          {canAdmin && (
            <Link to="/admin" data-testid="home-quick-admin"
                        className="rounded-token-card border border-white/[0.06]
                                                p-4 bg-white/[0.02] hover:bg-white/[0.05]
                                                transition-colors duration-150 flex items-center gap-3">
              <ShieldCheck size={18} className="text-accent-gold" />
              <div className="min-w-0">
                <div className="font-display font-bold text-sm tracking-display-tight">
                  Admin console
                </div>
                <div className="text-xs text-text-secondary">
                  Catalog, ads, ops, content quality
                </div>
              </div>
            </Link>
          )}
        </section>
      )}

      {/* Phase 42 S2.2 — moved `featured_horizontal` lower (now between
            Featured Stations and Discover) per user feedback. */}
      <BannerSlot id="top_banner" />
      {/* Phase R — Breaking News Ribbon (region-scoped, session-dismissable). */}
      <BreakingNewsRibbon region_code={(useGeoStore.getState?.()?.city) || undefined}
                                          className="mb-4" />
      {/* ── Hero (single-column, full-width) ───────────────────────── */}
      <section>
        <Card className="p-6 lg:p-8 relative overflow-hidden"
                  data-testid="home-hero">
          <div className="absolute -top-12 -right-16 w-80 h-80 rounded-full
                                opacity-30"
                style={{ background: "radial-gradient(closest-side, var(--accent-electric), transparent)" }} />
          <div className="absolute -bottom-16 -left-10 w-72 h-72 rounded-full
                                opacity-20"
                style={{ background: "radial-gradient(closest-side, var(--accent-magenta), transparent)" }} />
          <div className="relative z-[1]">
            {/* Single-column hero — greeting + CTAs only. Right rail tiles
                  (Trivia / Wallet / Passport / Around) moved to the
                  personalization row below. News strip moved to /community
                  for Phase 41 Session 3 discovery surface. */}
            <div className="space-y-5 max-w-2xl">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-text-secondary flex items-center gap-2">
                <LiveDot /> Now on BigFM · {daypart}
              </div>
              {/* Phase B — personalized city pill row.  Replaces the
                    long-standing hardcoded "Live in Dubai · Mumbai · Dallas"
                    triplet with a dynamic Home/Visiting/Live + heat fill
                    derived from user preference + current geo + history.

                    Bug B1/B2 fix — render each pill's label EXACTLY as the
                    API supplies it (`tag.label`) and iterate the array in
                    API order. NO client-side sort / filter / re-order.
                    The PREFIX_BY_SOURCE map is a defensive fallback only
                    triggered when the backend ships a tag without a label
                    string (should not happen with the current contract).
              */}
              {cityTags.length > 0 && (
                <div className="flex flex-wrap items-center gap-2"
                          data-testid="home-city-tags">
                  {cityTags.map((t, idx) => {
                    const PREFIX_BY_SOURCE = {
                      user_home_city:   "HOME",
                      geo_ip:            "VISITING",
                      listener_history: "RECENT",
                      heat:               "LIVE IN",
                      market_default:   "LIVE IN",
                    };
                    const prefix = (t.label && String(t.label).toUpperCase())
                      || PREFIX_BY_SOURCE[t.source]
                      || "LIVE IN";
                    const isHome     = t.source === "user_home_city" && (t.label || "").toLowerCase() === "home";
                    const isLive      = (t.label || "").toLowerCase() === "live";
                    const isVisiting = (t.label || "").toLowerCase() === "visiting";
                    const tone =
                      isLive      ? { bg: "bg-accent-live/15",     fg: "text-accent-live",     dot: "bg-accent-live" } :
                      isHome      ? { bg: "bg-accent-electric/15", fg: "text-accent-electric", dot: "bg-accent-electric" } :
                      isVisiting ? { bg: "bg-accent-magenta/15", fg: "text-accent-magenta", dot: "bg-accent-magenta" } :
                                          { bg: "bg-white/[0.05]",      fg: "text-text-secondary", dot: "bg-text-secondary" };
                    return (
                      <span key={`${t.source}-${t.city}-${idx}`}
                                  data-testid={`home-city-tag-${t.source}`}
                                  data-tag-order={idx}
                                  data-tag-label={prefix}
                                  data-tag-city={t.city}
                                  className={`inline-flex items-center gap-1.5
                                                            rounded-full px-2.5 h-6
                                                            text-[10px] font-mono uppercase
                                                            tracking-widest ${tone.bg} ${tone.fg}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${tone.dot}`} />
                        {prefix} · {t.city}
                      </span>
                    );
                  })}
                </div>
              )}
              <h1 className="font-display font-bold text-4xl sm:text-5xl
                                      lg:text-6xl tracking-display-tight">
                Welcome back, <span className="text-accent-electric" data-testid="home-welcome-name">
                  {user?.first_name || user?.name?.split(" ")?.[0] || "there"}.
                </span>
              </h1>
              <p className="text-text-secondary text-base max-w-xl">
                Your AI radio is ready. Resume where you left off, or jump
                into a channel.
              </p>
              <div className="flex flex-wrap gap-3 pt-2">
                <Button onClick={() => navigate("/radio")}
                            data-testid="home-resume">
                  <RadioIcon size={16} /> Resume listening
                </Button>
                <Button variant="outline"
                            onClick={() => navigate("/play")}
                            data-testid="home-cta-games">
                  <Gamepad2 size={16} /> Play &amp; Win
                </Button>
                {/* Phase 42-E2.2 — Universal share button on the hero. */}
                <ShareButton featureType="home"
                                          title="BigFM — your personalized radio"
                                          text="I'm vibing on BigFM — personalized radio, games, news, and rewards. Tune in:" />
              </div>
            </div>
          </div>
        </Card>
      </section>

      {/* ── Phase 42-E2.1 — Explore BigFM (6 cinematic feature tiles) ── */}
      {tiles.length > 0 && (
        <section data-testid="home-feature-tiles" data-tile-count={tiles.length}>
          <div className="flex items-end justify-between mb-4">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-accent-electric/80 mb-1">
                Explore BigFM
              </div>
              <h2 className="font-display font-bold text-xl
                                          tracking-display-tight">
                Six ways to play tonight
              </h2>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3
                                          gap-4 lg:gap-5">
            {tiles.map((t) => (
              <FeatureTileCard key={t.tile_id} tile={t} />
            ))}
          </div>
        </section>
      )}

      {/* ── Phase 42-E2.1 — Local highlights strip ── */}
      <LocalHighlightsStrip />

      {/* ── Personalization tiles row (Trivia / Wallet / Passport / Around) ── */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
                      data-testid="home-personalization-row">
          <Card className="p-5" data-testid="home-trivia-strip">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain size={18} className="text-accent-magenta" />
                <span className="font-display font-bold tracking-display-tight">
                  Trivia tonight
                </span>
              </div>
              <Chip tone="live" data-testid="home-trivia-live">
                <LiveDot /> 9 PM
              </Chip>
            </div>
            <div className="mt-3 text-sm text-text-secondary"
                      data-testid="home-trivia-subtitle">
              Karak Quiz · {city || "your city"} · 12 venues live
            </div>
            <Button variant="outline" size="sm" className="mt-4"
                        onClick={() => navigate("/trivia")}
                        data-testid="home-trivia-cta">
              See nearby venues <ChevronRight size={14} />
            </Button>
          </Card>

          <Card className="p-5" data-testid="home-wallet-strip">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-accent-gold">
                <Sparkles size={18} />
                <span className="font-display font-bold tracking-display-tight">
                  BigCoin wallet
                </span>
              </div>
              <span className="font-mono text-xs text-text-secondary">
                {wallet?.balance ?? 0} BC
              </span>
            </div>
            <div className="mt-3 text-sm text-text-secondary">
              {wallet?.balance > 0
                ? "Spend on coupons, gift cards, and tickets."
                : "Start listening to earn your first BigCoin."}
            </div>
            <Button variant="gold" size="sm" className="mt-4"
                        onClick={() => navigate("/wallet")}
                        data-testid="home-wallet-cta">
              Open wallet
            </Button>
          </Card>

          <Card className="p-5" data-testid="home-passport-strip">
            <div className="flex items-center gap-2">
              <BadgeCheck size={18} className="text-accent-electric" />
              <span className="font-display font-bold tracking-display-tight">
                Social Passport
              </span>
            </div>
            <div className="mt-3 h-1.5 rounded-full bg-white/[0.08] overflow-hidden">
              <div className="h-full bg-accent-electric"
                      style={{ width: "42%" }} />
            </div>
            <div className="mt-2 text-xs font-mono text-text-secondary">
              42% to next level
            </div>
            <Button variant="ghost" size="sm" className="mt-3"
                        onClick={() => navigate("/passport")}
                        data-testid="home-passport-cta">
              View passport <ChevronRight size={14} />
            </Button>
          </Card>

          {/* Phase 15d — Local headlines for the user's market. */}
          <LocalNewsWidget limit={3} />
      </section>

      {/* Phase K.7b — 3 image-backed landscape promo banner cards
            (replaces the previously-portrait Try Chat purple block
              and the two stacked BannerAdSlots).  Aspect ratio is
              16:6 — short and wide.  Single column on mobile. */}
      <section data-testid="home-banner-row"
                    className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <PromoBannerCard
          testId="home-try-chat-card"
          imageUrl={mktAssets["promo_try_chat"]}
          eyebrow="🎤 Try Chat"
          accent="#c084fc"
          title={myPersona ? `Chat with ${myPersona.display_name}`
                                              : "Pick your AI RJ"}
          body={myPersona
                          ? "Open the chat — say hi, request a mood →"
                          : "Choose a personality and start a live chat →"}
          onClick={() => navigate("/personas")} />
        <PromoBannerCard
          testId="home-promo-community-radio"
          imageUrl={mktAssets["promo_community_radio"]}
          eyebrow="Community radio"
          accent="#00d1ff"
          title="Discover community radio"
          body="Independent DJs, hyperlocal stations, hand-picked vibes →"
          to="/community" />
        <PromoBannerCard
          testId="home-promo-trivia-rewards"
          imageUrl={mktAssets["promo_trivia_rewards"]}
          eyebrow="Earn coins"
          accent="#ff38bb"
          title="Trivia rewards await"
          body="Spin, predict, answer — climb the leaderboard →"
          to="/play-and-win" />
        {/* Phase H v1 — Commute Mode entry tile. */}
        <PromoBannerCard
          testId="home-promo-commute-mode"
          imageUrl={mktAssets["route_based_ads"]}
          eyebrow="🚗 Commute Mode"
          accent="#00D4FF"
          title="Offers along your route"
          body="Live map, traffic, coupons matched to your drive →"
          to="/commute" />
      </section>
      <section className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3"
                    data-testid="home-try-banner">
        <div data-testid="home-try-game-card">
          <TopGameRecCard />
        </div>
        <div data-testid="home-try-station-card">
          <TopChannelRecCard />
        </div>
      </section>

      {/* Phase 18 — Favorites strip with + picker. */}
      <section data-testid="home-favorites-section" className="mt-2">
        <FavoritesStrip allChannels={channels} />
      </section>

      {/* ── Phase K.8 — Featured stations MOVED to top (rendered above) ── */}

      {/* ── Discover · poster grid of all channels ──────────────────── */}
      {/* Phase 42 S2.2 — horizontal banner between Featured stations
            and Discover per user feedback. */}
      <BannerAdSlot slotKey="featured_horizontal" pageRoute="/home" />
      {channels.length > 4 && (
        <section data-testid="home-discover">
          <SectionHeader title="Discover" linkTo="/radio" />
          <HorizontalScroller>
            {channels.slice(4, 14).map((c) => {
              // Phase Π+3.1 — render the artwork as an actual `<img>`
              // (not just a CSS background) so headless tests can
              // measure naturalWidth on the resulting HTMLImageElement.
              const artUrl = c.thumbnail_url
                ? `${process.env.REACT_APP_BACKEND_URL || ""}${c.thumbnail_url}`
                : null;
              return (
              <div key={c.slug} className="min-w-[200px]">
                <button
                  type="button"
                  onClick={() => navigate(`/radio?ch=${encodeURIComponent(c.slug)}`)}
                  data-testid={`home-discover-${c.slug}`}
                  className="relative w-[200px] h-[200px] rounded-token-card
                                          overflow-hidden border border-white/[0.06]
                                          group transition-transform duration-200
                                          hover:-translate-y-0.5"
                  style={!artUrl
                    ? { background: c.cover_color || "var(--accent-electric)" }
                    : undefined}
                >
                  {artUrl ? (
                    <img
                      src={artUrl}
                      alt={c.name || c.slug}
                      loading="lazy"
                      onError={(e) => { e.currentTarget.style.display = "none"; }}
                      className="absolute inset-0 w-full h-full object-cover"
                      data-testid={`home-discover-img-${c.slug}`} />
                  ) : null}
                  <div className="absolute inset-0
                                          bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
                  <div className="absolute inset-x-0 bottom-0 p-3 text-left">
                    <div className="font-display font-bold text-sm
                                              tracking-display-tight text-white">
                      {c.name || c.slug}
                    </div>
                    {c.tagline && (
                      <div className="text-[10px] font-mono uppercase
                                                tracking-widest text-white/65 mt-0.5">
                        {c.tagline}
                      </div>
                    )}
                  </div>
                </button>
              </div>
              );
            })}
          </HorizontalScroller>
        </section>
      )}

      {/* ── Recently played ─────────────────────────────────────────── */}
      <section data-testid="home-recent">
        <SectionHeader title="Recently played" linkTo="/radio" />
        <Card className="p-5 text-text-secondary text-sm flex items-center gap-3">
          <RadioIcon size={18} className="text-accent-electric" />
          {channels.length > 0
            ? `Pick up where you left off — ${channels[0].name || "your last station"}.`
            : "Start a station to build your history."}
          {channels.length > 0 && (
            <Button variant="ghost" size="sm" className="ml-auto"
                        onClick={() => navigate(`/radio?ch=${encodeURIComponent(channels[0].slug)}`)}
                        data-testid="home-recent-resume">
              Resume <ChevronRight size={14} />
            </Button>
          )}
        </Card>
      </section>

      {/* ── Nearby offers ───────────────────────────────────────────── */}
      {/* Phase G1 — city-resolved offer rail.  Reads market from the
              same `useGeoStore` that drives the header CityChip + footer
              greeting, so when the user switches city all three update
              together.  Falls back gracefully to globally-popular when
              there's nothing local yet (no silent Dubai default). */}
      <NearbyOffersRail />

      {/* ── Unlocked games ───────────────────────────────────────────── */}
      <section data-testid="home-games">
        <SectionHeader title="Unlocked games" linkTo="/play" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <GameTile name="Karak Quiz"  prize="Free karak ×3"
                          onJoin={() => navigate("/play")} />
          <GameTile name="Spin the wheel" prize="AED 25 voucher"
                          status="open"
                          onJoin={() => navigate("/play")} />
          <GameTile name="Movie ticket pick" prize="2 free tickets"
                          status="open"
                          onJoin={() => navigate("/play")} />
          <GameTile name="Hidden gem" prize="Mystery box"
                          status="open"
                          onJoin={() => navigate("/play")} />
        </div>
      </section>

      {/* ── Podcasts (placeholder) ──────────────────────────────────── */}
      {/* Phase 42 S2.2 — horizontal banner between Unlocked games and
            Podcast picks per user feedback. */}
      <BannerAdSlot slotKey="mid_horizontal" pageRoute="/home" />
      <section data-testid="home-podcasts">
        <SectionHeader title="Podcast picks" />
        <Card className="p-6 text-text-secondary text-sm flex items-center gap-3">
          <Podcast size={20} className="text-accent-electric" />
          Podcasts arrive in a later phase — your subscriptions will appear here.
        </Card>
      </section>

      {/* Phase SC.2 — small footer nudge to the merchant self-service
              wizard.  Non-invasive; only visible to authenticated listeners. */}
      <section data-testid="home-merchant-cta"
                    className="mt-8 rounded-2xl px-5 py-4 flex items-center
                                            justify-between gap-4 border border-white/[0.06]"
                    style={{ background: "linear-gradient(135deg, rgba(139,92,246,0.14), rgba(236,72,153,0.10))" }}>
        <div>
          <div className="text-xs uppercase tracking-widest font-bold"
                    style={{ color: "#c4b5fd" }}>For business owners</div>
          <div className="mt-1 text-sm text-text-secondary">
            Own a spot? Bring foot traffic through BigFM offers, deals, and
            live plays.
          </div>
        </div>
        <Link to="/merchant/apply"
                  data-testid="home-become-partner-link"
                  className="whitespace-nowrap px-4 h-10 rounded-full text-xs
                                        font-bold uppercase tracking-widest flex items-center"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)",
                                  color: "#fff" }}>
          Become a Partner →
        </Link>
      </section>

      {/* Spacer so the persistent player doesn't cover the last card. */}
      <div className="h-24" />
    </div>
  );
}

function SectionHeader({ title, linkTo }) {
  return (
    <div className="flex items-end justify-between mb-4">
      <h2 className="font-display font-bold text-xl tracking-display-tight">
        {title}
      </h2>
      {linkTo && (
        <Link to={linkTo}
                  className="text-xs font-mono uppercase tracking-widest
                                  text-text-secondary hover:text-accent-electric
                                  transition-colors duration-150">
          See all →
        </Link>
      )}
    </div>
  );
}

function HorizontalScroller({ children }) {
  return (
    <div className="-mx-2 px-2 overflow-x-auto">
      <div className="flex gap-3 pb-1 snap-x snap-mandatory">
        {React.Children.map(children, (c) => (
          <div className="snap-start">{c}</div>
        ))}
      </div>
    </div>
  );
}


// Phase G1 — Geo-aware Nearby Offers rail.  Reads the same `useGeoStore`
// the header + footer use, fetches `/api/offers/nearby?market=…`, and
// renders one of:
//   • happy path — local offers found for the user's market/country
//   • fallback banner — globally popular shown because nothing local yet
//   • empty state — neither local nor global have anything (CTA links to
//      the business onboarding flow).
function NearbyOffersRail() {
  const market = useGeoStore((s) => s.market);
  const city     = useGeoStore((s) => s.city);
  const country = useGeoStore((s) => s.country);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams();
    if (market)   params.set("market", market);
    if (city)        params.set("city", city);
    if (country) params.set("country", country);
    params.set("limit", "10");
    axios.get(`${API}/offers/nearby?${params.toString()}`,
                      { withCredentials: true })
      .then((r) => { if (!cancelled) setData(r.data || null); })
      .catch(() => { if (!cancelled) setData(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
  }, [market, city, country]);

  const items   = data?.items || [];
  const source = data?.resolution_source;
  const banner = data?.fallback_banner;
  const label    = data?.city_label || city || "your area";

  // Headline depends on resolution_source so the rail copy reflects
  // what we actually showed.
  const title = source === "market" || source === "country"
    ? `Nearby offers · ${label}`
    : "Popular offers";

  if (loading) {
    return (
      <section data-testid="home-offers" data-source="loading">
        <SectionHeader title="Nearby offers" linkTo="/map" />
        <HorizontalScroller>
          {[0, 1, 2].map((i) => (
            <div key={i}
                      data-testid={`home-offers-skeleton-${i}`}
                      className="min-w-[260px] h-[120px] rounded-xl bg-white/5 animate-pulse" />
          ))}
        </HorizontalScroller>
      </section>);
  }

  return (
    <section data-testid="home-offers"
                  data-source={source}
                  data-effective-market={data?.effective_market || ""}>
      <SectionHeader title={title} linkTo="/map" />

      {source === "global" && banner && (
        <div data-testid="home-offers-fallback-banner"
                style={{ marginBottom: 10, padding: "8px 12px",
                            background: "rgba(251,191,36,0.08)",
                            border: "1px solid rgba(251,191,36,0.3)",
                            color: "#fbbf24", borderRadius: 10,
                            fontSize: 12 }}>
          {banner}
        </div>
      )}

      {source === "empty" || items.length === 0 ? (
        <div data-testid="home-offers-empty"
                style={{ padding: "20px 16px",
                            background: "rgba(255,255,255,0.03)",
                            border: "1px dashed rgba(255,255,255,0.08)",
                            borderRadius: 12,
                            color: "#94a3b8", fontSize: 13,
                            lineHeight: 1.5 }}>
          <div style={{ fontWeight: 600, color: "#cbd5e1", marginBottom: 4 }}>
            We&apos;re working on partnerships in {label}.
          </div>
          <div>
            Be the first business to list here.{" "}
            <Link to="/business/onboard"
                      data-testid="home-offers-list-business-cta"
                      style={{ color: "#00d9ff", textDecoration: "underline" }}>
              List your business →
            </Link>
          </div>
        </div>
      ) : (
        <HorizontalScroller>
          {items.map((o) => (
            <div key={o.offer_id}
                      data-testid={`home-offer-${o.offer_id}`}
                      className="min-w-[260px]">
              <WalletItemCard
                title={o.title}
                expires={o.discount_label || (o.expires_at ? "Limited time" : "")}
                badge={source === "market" ? "LOCAL" : "POPULAR"} />
            </div>
          ))}
        </HorizontalScroller>
      )}
    </section>);
}
