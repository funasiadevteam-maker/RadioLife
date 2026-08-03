/**
 * usePlayerStore — Global radio playback state (zustand).
 *
 * Mirrors `/app/frontend/src/store/usePlayerStore.js`.
 * Any screen can read/write playback state without the audio
 * being tied to a single component's lifecycle.
 */
import { create } from 'zustand';

export interface PlayerSegment {
  segment_id: string;
  segment_url: string;
  track_title: string;
  track_artist: string;
  rj_script?: string;
  rj_voice_name?: string;
  rj_start_sec?: number;
  rj_format?: string;
  rj_hosts?: { name: string }[];
  channel_slug?: string;
  channel_name?: string;
}

interface PlayerState {
  // session
  sessionId: string | null;
  channels: any[];
  activeChannel: string | null;
  activeChannelName: string | null;
  activeChannelThumb: string | null;

  // segments
  currentSeg: PlayerSegment | null;
  history: PlayerSegment[];

  // transport
  playing: boolean;
  currentTime: number;
  duration: number;

  // skip
  skipUsed: number;
  skipLimit: number;
  skipResetIn: number;

  // setters
  setSession: (id: string | null) => void;
  setChannels: (ch: any[]) => void;
  setActiveChannel: (slug: string | null, name?: string | null, thumb?: string | null) => void;
  setCurrentSeg: (seg: PlayerSegment | null) => void;
  pushHistory: (seg: PlayerSegment) => void;
  setPlaying: (p: boolean) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  setSkipState: (used?: number, limit?: number, resetIn?: number) => void;
  reset: () => void;
}

const initial = {
  sessionId: null,
  channels: [],
  activeChannel: null,
  activeChannelName: null,
  activeChannelThumb: null,
  currentSeg: null,
  history: [],
  playing: false,
  currentTime: 0,
  duration: 0,
  skipUsed: 0,
  skipLimit: 6,
  skipResetIn: 0,
};

export const usePlayerStore = create<PlayerState>((set, get) => ({
  ...initial,

  setSession: (id) => set({ sessionId: id }),
  setChannels: (ch) => set({ channels: ch }),
  setActiveChannel: (slug, name, thumb) =>
    set({
      activeChannel: slug,
      activeChannelName: name ?? get().activeChannelName,
      activeChannelThumb: thumb ?? get().activeChannelThumb,
    }),
  setCurrentSeg: (seg) => set({ currentSeg: seg }),
  pushHistory: (seg) => set((s) => ({ history: [...s.history, seg].slice(-6) })),
  setPlaying: (p) => set({ playing: p }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),
  setSkipState: (used, limit, resetIn) =>
    set({
      skipUsed: used ?? get().skipUsed,
      skipLimit: limit ?? get().skipLimit,
      skipResetIn: resetIn ?? get().skipResetIn,
    }),
  reset: () => set({ ...initial }),
}));
