// Headless engine for the sleep timer. Mounted once in AppShellV2.
// When `endsAt` is set, it schedules a single timeout; on fire it pauses
// whatever source is playing (the `bigfm:player:toggle` event is owned by
// the active source — AI via GlobalAudio, imported/podcast via their
// bridges) and clears the timer.
import { useEffect } from "react";
import { toast } from "sonner";
import { useSleepTimer } from "@/store/useSleepTimer";
import { usePlayerStore } from "@/store/usePlayerStore";

export default function SleepTimerEngine() {
  const endsAt = useSleepTimer((s) => s.endsAt);
  const cancel = useSleepTimer((s) => s.cancel);

  useEffect(() => {
    if (!endsAt) return;
    const ms = endsAt - Date.now();
    if (ms <= 0) { cancel(); return; }
    const t = setTimeout(() => {
      // Only pause if something is actually playing (toggle = pause when playing).
      if (usePlayerStore.getState().playing) {
        window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
      }
      cancel();
      toast("Sleep timer ended — playback paused. Good night 🌙");
    }, ms);
    return () => clearTimeout(t);
  }, [endsAt, cancel]);

  return null;
}
