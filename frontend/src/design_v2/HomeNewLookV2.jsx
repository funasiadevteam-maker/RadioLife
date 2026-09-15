import React, { useEffect, useState } from "react";
import axios from "axios";
import { API, useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import BannerAdSlot from "@/components/BannerAdSlot";
import "./newlookv2.css";
import HeroNewLookV2 from "./HeroNewLookV2";
import ContinueListeningRowV2 from "./ContinueListeningRowV2";
import RailV2 from "./RailV2";
import ActionCardsV2 from "./ActionCardsV2";
import PremiumBannerRowV2 from "./PremiumBannerRowV2";

function greetingFor(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export default function HomeNewLookV2() {
  const { user } = useAuth();
  const [home, setHome] = useState(null);

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
    return () => { cancel = true; };
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

  // For You — inject the native sponsored offer as one labelled card.
  const forYouItems = [...((home?.for_you) || [])];
  if (home?.native_offer) {
    const n = home.native_offer;
    forYouItems.splice(Math.min(3, forYouItems.length), 0, {
      id: n.business_id || n.campaign_id || "native",
      title: n.title, subtitle: n.subtitle, image: n.image,
      sponsored: true, to: n.to,
      business_id: n.business_id, campaign_id: n.campaign_id, kind: n.kind,
    });
  }
  const liveItems = (home?.live_now) || [];

  return (
    <div data-testid="home-new-look-v2" className="w-full space-y-10 pb-10">
      <HeroNewLookV2 greeting={greetingFor()} name={name} />
      <ContinueListeningRowV2
        continueItem={continueItem}
        reward={home?.listening_reward}
        dining={home?.dining}
        onResume={onResume}
      />
      <RailV2 title="For You" subtitle="Based on your listening, location and interests"
        items={forYouItems} testId="nlv2-foryou" />
      <RailV2 title="Live Right Now" subtitle="Trending stations from around the world"
        items={liveItems} testId="nlv2-live" />
      <ActionCardsV2 />
      <PremiumBannerRowV2 isPremium={!!home?.is_premium} />
      {!home?.is_premium && (
        <section data-testid="nlv2-display-ad" className="nlv2-glass rounded-2xl p-2 flex justify-center">
          <BannerAdSlot slotKey="mid_horizontal" pageRoute="/" />
        </section>
      )}
    </div>
  );
}
