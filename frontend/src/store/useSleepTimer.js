// Sleep timer — "stop after N minutes" so a station winds down on its own.
// The SleepTimerEngine (mounted once in AppShellV2) watches `endsAt` and
// pauses whatever is playing when it elapses. The control lives in the
// player bar (SleepTimerButton).
import { create } from "zustand";

export const useSleepTimer = create((set) => ({
  endsAt: null,   // epoch ms when playback should pause, or null
  minutes: null,  // the chosen duration label

  start: (minutes) =>
    set({ minutes, endsAt: Date.now() + minutes * 60000 }),
  cancel: () => set({ minutes: null, endsAt: null }),
}));
