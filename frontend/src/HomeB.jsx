// Audio-first Home (Home Audio V2 — the universal default Home). Answers
// "what should I listen to?" FIRST, then layers monetization AFTER the core
// listening experience per the value-before-advertising doctrine:
//   Continue/Start → For You → Live Right Now → Listening Reward →
//   Do More While You Listen → Native Sponsored card → Contextual Dining →
//   Display banner (Free only).
// Reuses the existing ad / campaign / marketplace engines via /api/shell/home.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Play, Pause, Radio as RadioIcon, Sparkles, ChevronRight,
  Coins, Gamepad2, ShoppingBag, Users as UsersIcon, UtensilsCrossed,
} from "lucide-react";
import { API } from "@/AuthContext";
import { useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useShellSummary, useShellFilter } from "@/shell/useShellData";
import BannerAdSlot from "@/components/BannerAdSlot";
import HomeSponsoredCard, { fireHomeEvent } from "@/shell/HomeSponsoredCard";

function firstName(user) {
  return (user?.first_name || user?.name || "").split(" ")[0] || "there";
}

// Re-scope the For-You rail from the light Home chips. Never returns an
// empty list when stations exist (Local/Trending fall back to All).
function scopeByChip(chip, stations, summary) {
  if (!stations.length) return [];
  if (chip === "trending") {
    return [...stations].sort(
      (a, b) => (b.live ? 1 : 0) - (a.live ? 1 : 0) || (b.listeners || 0) - (a.listeners || 0));
  }
  if (chip === "local") {
    const city = (summary?.city || "").toLowerCase().trim();
    if (city) {
      const local = stations.filter((s) => (s.city || "").toLowerCase().includes(city));
      if (local.length) return local;
    }
    return stations;
  }
  return stations; // all + foryou (already personalized by the backend)
}

const CHIP_TITLES = { all: "For You", foryou: "For You", local: "Local stations", trending: "Trending now" };

// "Do more while you listen" — Shop · Play · Social only. Earn lives in the
// header mini-wallet; Dining is contextual below.
const HOME_RAILS = [
  { key: "shop",   label: "Shop & Eat", sub: "Deals near you",          icon: ShoppingBag,  to: "/shop" },
  { key: "play",   label: "Play & Win", sub: "Games · trivia · predict", icon: Gamepad2,     to: "/play-and-win" },
  { key: "social", label: "Social",     sub: "Lobbies & community",     icon: UsersIcon,    to: "/community" },
];

export default function HomeB() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const summary = useShellSummary();
  const chip = useShellFilter((s) => s.chip);
  const [home, setHome] = useState(null);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/shell/home`, { withCredentials: true })
      .then((r) => { if (!cancel) setHome(r.data); })
      .catch(() => { if (!cancel) setHome({}); });
    return () => { cancel = true; };
  }, []);

  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const activeChannelThumb = usePlayerStore((s) => s.activeChannelThumb);
  const playing = usePlayerStore((s) => s.playing || s.importedPlaying || s.podcastPlaying);

  const nowTitle = importedStation?.name
    || podcastEpisode?.title
    || currentSeg?.title || currentSeg?.track_title
    || activeChannelName;
  const nowArt = importedStation?.favicon
    || podcastEpisode?.cover_image_url
    || currentSeg?.artwork_url || activeChannelThumb;
  const nowSub = importedStation ? "Live radio"
    : podcastEpisode ? (podcastEpisode.podcast_title || "Podcast")
    : (currentSeg?.artist || currentSeg?.channel_name || "AI radio");
  const hasSession = !!nowTitle;

  const togglePlay = () => {
    try { window.dispatchEvent(new CustomEvent("bigfm:player:toggle")); } catch (_e) { /* noop */ }
  };
  const startListening = () => navigate("/radio");

  const stationSet = (home?.for_you?.length ? home.for_you : (summary?.flagships || []));
  const forYou = scopeByChip(chip, stationSet, summary).slice(0, 6);
  const forYouTitle = CHIP_TITLES[chip] || "For You";
  const liveNow = home?.live_now || [];
  const perMin = home?.listening_reward?.points_per_min ?? 1;
  const isPremium = !!home?.is_premium;
  const diningMember = !!home?.dining?.member;

  return (
    <div className="max-w-5xl mx-auto space-y-8" data-testid="home-b">
      {/* Greeting — New vs Returning */}
      <div>
        <div className="text-[11px] font-mono uppercase tracking-widest text-text-secondary">
          {new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"}
        </div>
        <h1 className="text-2xl sm:text-3xl font-display font-black tracking-tight mt-0.5">
          {hasSession
            ? <>Hi {firstName(user)} — ready to pick up where you left off?</>
            : <>Hi {firstName(user)} — ready to listen?</>}
        </h1>
      </div>

      {/* A · Continue Listening / Start My Radio */}
      <section data-testid="home-b-continue">
        {hasSession ? (
          <div className="flex items-center gap-4 rounded-token-card border border-white/[0.08] bg-bg-elevated p-4 sm:p-5"
               data-testid="home-b-resume-card">
            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-token-md overflow-hidden shrink-0 bg-black/30">
              {nowArt
                ? <img src={nowArt} alt="" className="w-full h-full object-cover" />
                : <div className="w-full h-full grid place-items-center"><RadioIcon size={28} className="text-text-secondary" /></div>}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-mono uppercase tracking-widest text-accent-electric">
                {playing ? "Now playing" : "Paused"}
              </div>
              <div className="text-lg sm:text-xl font-bold truncate">{nowTitle}</div>
              <div className="text-sm text-text-secondary truncate">{nowSub}</div>
            </div>
            <button type="button" onClick={togglePlay} data-testid="home-b-resume-btn"
              className="w-14 h-14 rounded-full bg-accent-electric text-black grid place-items-center shrink-0 hover:scale-105 transition-transform">
              {playing ? <Pause size={24} /> : <Play size={24} className="translate-x-0.5" />}
            </button>
          </div>
        ) : (
          <div className="rounded-token-card p-6 sm:p-8 text-white relative overflow-hidden"
               data-testid="home-b-start-card"
               style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
            <div className="relative z-10">
              <div className="text-[11px] font-mono uppercase tracking-widest opacity-80">Your radio, one tap away</div>
              <h2 className="text-2xl sm:text-3xl font-display font-black mt-1">Start My Radio</h2>
              <p className="text-sm opacity-90 mt-1 max-w-md">
                AI-personalized radio built around what you love. Skip what you don't, earn BigPoints as you listen.
              </p>
              <button type="button" onClick={startListening} data-testid="home-b-start-btn"
                className="mt-4 inline-flex items-center gap-2 h-12 px-6 rounded-full bg-white text-black font-bold hover:scale-[1.03] transition-transform">
                <Play size={20} className="translate-x-0.5" /> Start Listening
              </button>
            </div>
            <Sparkles size={140} className="absolute -right-6 -bottom-6 opacity-15" />
          </div>
        )}
      </section>

      {/* B · For You */}
      <section data-testid="home-b-foryou">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold">{forYouTitle}</h2>
          <Link to="/listen" data-testid="home-b-foryou-seeall"
            className="text-sm font-semibold text-accent-electric hover:underline flex items-center gap-1">
            See all listening <ChevronRight size={15} />
          </Link>
        </div>
        <div className="text-[11px] font-mono uppercase tracking-widest text-text-secondary mb-3">
          AI Radio · Live Radio · Podcasts
        </div>
        {forYou.length === 0 ? (
          <div className="rounded-token-card border border-white/[0.08] bg-bg-elevated p-6 text-center text-text-secondary text-sm"
               data-testid="home-b-foryou-empty">
            Start listening and your picks will appear here.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="home-b-foryou-grid">
            {forYou.map((s) => (
              <Link key={s.slug || s.id} to={`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`}
                data-testid={`home-b-foryou-${s.slug || s.id}`}
                className="group rounded-token-md overflow-hidden border border-white/[0.06] bg-bg-elevated hover:border-accent-electric/40 transition-colors">
                <div className="aspect-square bg-black/30 overflow-hidden relative">
                  {(s.art || s.favicon)
                    ? <img src={s.art || s.favicon} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                    : <div className="w-full h-full grid place-items-center"><RadioIcon size={24} className="text-text-secondary" /></div>}
                  {s.live && <span className="absolute top-1.5 left-1.5 text-[9px] font-black px-1.5 py-0.5 rounded-full bg-accent-live text-white">LIVE</span>}
                  <span className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
                    <Play size={22} className="text-white translate-x-0.5" />
                  </span>
                </div>
                <div className="p-2">
                  <div className="text-[13px] font-semibold truncate">{s.name}</div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* C · Live Right Now — live-first, one labelled sponsored slot */}
      {liveNow.length > 0 && (
        <LiveRightNow items={liveNow} />
      )}

      {/* D · Listening Reward */}
      <section data-testid="home-b-listening-reward">
        <Link to="/wallet" data-testid="home-b-reward-card"
          className="flex items-center gap-3 rounded-token-card border border-accent-gold/25 bg-accent-gold/[0.05] p-3.5 hover:border-accent-gold/50 transition-colors">
          <div className="w-10 h-10 rounded-full grid place-items-center bg-accent-gold/15 text-accent-gold shrink-0">
            <Coins size={19} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-bold">Earn +{perMin} BigPoint{perMin === 1 ? "" : "s"} every minute you listen</div>
            <div className="text-[11px] text-text-secondary">Your BigPoints stack up in the background — tap to see rewards</div>
          </div>
          <ChevronRight size={16} className="text-accent-gold shrink-0" />
        </Link>
      </section>

      {/* E · Do More While You Listen — Shop · Play · Social */}
      <section data-testid="home-b-rails">
        <h2 className="text-lg font-bold mb-3">Do more while you listen</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {HOME_RAILS.map((r) => (
            <Link key={r.key} to={r.to} data-testid={`home-b-rail-${r.key}`}
              className="group flex items-center gap-3 rounded-token-card border border-white/[0.08] bg-bg-elevated p-4 hover:border-accent-electric/40 transition-colors">
              <div className="w-10 h-10 rounded-token-md grid place-items-center bg-accent-electric/15 text-accent-electric shrink-0">
                <r.icon size={19} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-bold truncate">{r.label}</div>
                <div className="text-[11px] text-text-secondary truncate">{r.sub}</div>
              </div>
              <ChevronRight size={15} className="text-text-secondary group-hover:text-accent-electric transition-colors" />
            </Link>
          ))}
        </div>
      </section>

      {/* F · Native sponsored card — first conventional placement */}
      <HomeSponsoredCard offer={home?.native_offer} />

      {/* G · Contextual Dining Club — member card, else a slim promo */}
      {diningMember ? (
        <Link to="/dining" data-testid="home-b-dining-member"
          className="flex items-center gap-3 rounded-token-card border border-accent-electric/25 bg-accent-electric/[0.05] p-4 hover:border-accent-electric/50 transition-colors">
          <div className="w-10 h-10 rounded-token-md grid place-items-center bg-accent-electric/15 text-accent-electric shrink-0">
            <UtensilsCrossed size={19} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-bold truncate">Your Dining Club</div>
            <div className="text-[11px] text-text-secondary truncate">Pick this week's meals · spin for tonight</div>
          </div>
          <ChevronRight size={15} className="text-accent-electric shrink-0" />
        </Link>
      ) : (
        <Link to="/dining" data-testid="home-b-dining-promo"
          className="flex items-center gap-3 rounded-token-card border border-white/[0.06] bg-bg-elevated p-4 hover:border-accent-electric/40 transition-colors">
          <div className="w-10 h-10 rounded-token-md grid place-items-center bg-accent-electric/10 text-accent-electric shrink-0">
            <UtensilsCrossed size={19} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-bold truncate">RadioLife Dining Club</div>
            <div className="text-[11px] text-text-secondary truncate">Spin the wheel · $9.99 meals near you</div>
          </div>
          <ChevronRight size={15} className="text-text-secondary shrink-0" />
        </Link>
      )}

      {/* H · Display banner — Free listeners only, placed low */}
      {!isPremium && (
        <DisplayBanner />
      )}
    </div>
  );
}

function LiveRightNow({ items }) {
  const navigate = useNavigate();
  useEffect(() => {
    const sponsored = items.find((s) => s.sponsored);
    if (sponsored) {
      fireHomeEvent("sponsored_station_impression", {
        station_id: sponsored.id, business_id: sponsored.sponsor_business_id });
    }
  }, [items]);
  const open = (s) => {
    if (s.sponsored) {
      fireHomeEvent("sponsored_station_start", {
        station_id: s.id, business_id: s.sponsor_business_id });
    }
    navigate(`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`);
  };
  return (
    <section data-testid="home-b-live-now">
      <h2 className="text-lg font-bold mb-3">Live right now</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="home-b-live-now-grid">
        {items.map((s) => (
          <button type="button" key={`${s.slug || s.id}-${s.sponsored ? "sp" : "org"}`} onClick={() => open(s)}
            data-testid={s.sponsored ? "home-b-live-sponsored" : `home-b-live-${s.slug || s.id}`}
            className="group text-left rounded-token-md overflow-hidden border border-white/[0.06] bg-bg-elevated hover:border-accent-electric/40 transition-colors">
            <div className="aspect-square bg-black/30 overflow-hidden relative">
              {s.art
                ? <img src={s.art} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                : <div className="w-full h-full grid place-items-center"><RadioIcon size={24} className="text-text-secondary" /></div>}
              {s.sponsored
                ? <span className="absolute top-1.5 left-1.5 text-[8px] font-black px-1.5 py-0.5 rounded-full bg-accent-gold text-black tracking-widest">SPONSORED</span>
                : s.live && <span className="absolute top-1.5 left-1.5 text-[9px] font-black px-1.5 py-0.5 rounded-full bg-accent-live text-white">LIVE</span>}
              <span className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
                <Play size={22} className="text-white translate-x-0.5" />
              </span>
            </div>
            <div className="p-2">
              <div className="text-[13px] font-semibold truncate">{s.name}</div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function DisplayBanner() {
  useEffect(() => { fireHomeEvent("home_ad_request"); }, []);
  return (
    <section data-testid="home-b-display-ad" className="flex justify-center">
      <BannerAdSlot slotKey="mid_horizontal" pageRoute="/" />
    </section>
  );
}
