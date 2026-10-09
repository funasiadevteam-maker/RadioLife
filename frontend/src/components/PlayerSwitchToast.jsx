// "Now playing — switched to <station>" — fires ONE toast whenever the active
// audio source changes (AI ↔ Live ↔ Podcast, or between AI channels), so the
// handoff after the mutual-exclusivity swap is obvious. Headless: renders null.
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { usePlayerStore } from "@/store/usePlayerStore";

export default function PlayerSwitchToast() {
  const sessionId = usePlayerStore((s) => s.sessionId);
  const activeChannel = usePlayerStore((s) => s.activeChannel);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const prev = useRef({ key: null, inited: false });

  useEffect(() => {
    let key = null;
    let name = null;
    let kind = null;
    if (sessionId) {
      key = `ai:${activeChannel || ""}`;
      name = activeChannelName || "FUUSIC AI Radio";
      kind = "AI Radio";
    } else if (importedStation) {
      key = `imp:${importedStation.id}`;
      name = importedStation.name || "Live station";
      kind = "Live";
    } else if (podcastEpisode) {
      key = `pod:${podcastEpisode.episode_id || ""}`;
      name = podcastEpisode.podcast_title || podcastEpisode.title || "Podcast";
      kind = "Podcast";
    }

    // Don't announce whatever is already playing on first mount.
    if (!prev.current.inited) {
      prev.current = { key, inited: true };
      return;
    }
    if (key && key !== prev.current.key) {
      toast(`Now playing — switched to ${name}`, {
        description: kind, duration: 2600,
      });
    }
    prev.current.key = key;
  }, [sessionId, activeChannel, activeChannelName, importedStation, podcastEpisode]);

  return null;
}
