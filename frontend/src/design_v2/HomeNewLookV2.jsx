import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { API, useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import BannerAdSlot from "@/components/BannerAdSlot";
import "./newlookv2.css";
import HeroNewLookV2 from "./HeroNewLookV2";
import FuusicWorldGridV2 from "./FuusicWorldGridV2";
import WhatsHappeningNowV2 from "./WhatsHappeningNowV2";
import ContinueListeningRowV2 from "./ContinueListeningRowV2";
import RailV2 from "./RailV2";
import TogetherActionsV2 from "./TogetherActionsV2";
import PremiumBannerRowV2 from "./PremiumBannerRowV2";
import PinnedAiRow from "@/components/PinnedAiRow";

function greetingFor(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export default function HomeNewLookV2() {
  const { user } = useAuth();
  const [home, setHome] = useState(null);
  const [social, setSocial] = useState(null);
  const happeningRef = useRef(null);

  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const activeChannelThumb = usePlayerStore((s) => s.activeChannelThumb);
  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const playing = usePlayerStore((s) => s.playing);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/shell/home`, { withCredentials: true })
      .then((r) => { if (!cancel) setHome(r.data || {}); })
      .catch(() => { if (!cancel) setHome({}); });
    const loadSocial = () => axios.get(`${API}/social/home`, { withCredentials: true })
      .then((r) => { if (!cancel) setSocial(r.data || {}); })
      .catch(() => { if (!cancel) setSocial((s) => s); });
    loadSocial();
    // Poll so live friend/room activity appears the moment friends go live.
    const t = setInterval(loadSocial, 20000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

  const name = user?.first_name || (user?.name || "").split(" ")[0] || "there";

  const title = importedStation?.name || podcastEpisode?.title || activeChannelName;
  const continueItem = title ? {
    title,
    subtitle: importedStation ? (importedStation.country || "Live radio")
      : podcastEpisode ? (podcastEpisode.show || "Podcast")
        : (currentSeg?.title || currentSeg?.track_title || "AI radio"),
    art: importedStation?.favicon || activeChannelThumb || currentSeg?.art || podcastEpisode?.image,
    progress: duration > 0 ? Math.min(100, (currentTime / duration) * 100) : null,
    playing,
  } : null;

  const onResume = () => {
    if (continueItem) window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
    else window.location.assign("/radio");
  };

  // For You — mixed rail (stations + Moments + live + offer + game) from the
  // backend; falls back to stations + the native offer if unavailable.
  let forYouItems = home?.mixed_for_you;
  if (!forYouItems || !forYouItems.length) {
    forYouItems = [...((home?.for_you) || [])];
    if (home?.native_offer) {
      const n = home.native_offer;
      forYouItems.splice(Math.min(3, forYouItems.length), 0, {
        id: n.business_id || n.campaign_id || "native",
        title: n.title, subtitle: n.subtitle, image: n.image,
        sponsored: true, to: n.to,
        business_id: n.business_id, campaign_id: n.campaign_id, kind: n.kind,
      });
    }
  }
  const liveItems = (home?.live_now) || [];

  // Config-driven layout (admin can reorder pillars / toggle sections).
  const sections = home?.home_config || {};
  const show = (k) => sections?.[k]?.visible !== false;
  const heading = (k, dflt) => sections?.[k]?.title || dflt;

  const scrollToHappening = () =>
    happeningRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <div data-testid="home-new-look-v2" className="w-full space-y-10 pb-10">
      <HeroNewLookV2 greeting={greetingFor()} name={name} topGenre={home?.top_genre}
        onSeeHappening={scrollToHappening} />

      <PinnedAiRow testId="home-pinned-ai-row" />

      {show("fuusic_world") && (
        <FuusicWorldGridV2 title={heading("fuusic_world", "Your FUUSIC World")}
          pillars={home?.fuusic_world} social={social?.happening_now} />
      )}

      {show("whats_happening") && (
        <div ref={happeningRef} className="scroll-mt-24">
          <WhatsHappeningNowV2 title={heading("whats_happening", "What's Happening Now")} data={social} />
        </div>
      )}

      {show("continue") && (
        <ContinueListeningRowV2
          continueItem={continueItem}
          reward={home?.listening_reward}
          dining={home?.dining}
          onResume={onResume}
        />
      )}

      {show("for_you") && (
        <RailV2 title={heading("for_you", "For You")}
          subtitle="Based on your interests, activity and what's happening around you"
          items={forYouItems} testId="nlv2-foryou" />
      )}

      {show("live_now") && (
        <RailV2 title={heading("live_now", "Live Right Now")}
          subtitle="What's happening across FUUSIC"
          items={liveItems} testId="nlv2-live" />
      )}

      {show("together") && (
        <TogetherActionsV2 title={heading("together", "Do Something Together")}
          actions={home?.together_actions} />
      )}

      {show("premium") && <PremiumBannerRowV2 isPremium={!!home?.is_premium} />}

      {!home?.is_premium && (
        <section data-testid="nlv2-display-ad" className="nlv2-glass rounded-2xl p-2 flex justify-center">
          <BannerAdSlot slotKey="mid_horizontal" pageRoute="/" />
        </section>
      )}
    </div>
  );
}
