// Phase 15d.3 — Global player store.  Holds the radio session + current
// segment + playback flags so that audio survives route navigation.  The
// two HTMLAudioElement nodes live in `audioElements.js` (module singleton)
// and are mounted ONCE by `<GlobalAudio />` at the AppShell root.
//
// Architecture:
//   • Radio.js  → writes session/segment state via setters.
//   • GlobalAudio.jsx → reads state, drives the <audio> tags, handles
//                        `ended` (segment swap + prefetch next), `timeupdate`
//                        (currentTime mirror + prefetch trigger), and the
//                        cross-route `bigfm:player:toggle` event.
//   • MiniPlayer → reads `currentSeg`, `playing`, dispatches toggle.
import { create } from "zustand";

const initialState = {
  // session
  sessionId: null,
  channels: [],
  activeChannel: null,
  activeChannelName: null,   // mirrored for MiniPlayer when channels[] is empty
  activeChannelThumb: null,  // for Media Session artwork

  // segments
  currentSeg: null,
  nextSeg: null,
  history: [],
  activeIdx: 0,

  // transport
  playing: false,
  currentTime: 0,
  duration: 0,
  volume: 0.85,
  muted: false,

  // skip state (mirrored so MiniPlayer can disable Next when exhausted)
  skipUsed: 0,
  skipLimit: 6,
  skipResetIn: 0,

  // Phase 42-A2 — Imported live-radio stream (raw <audio src>, no queue).
  // Coexists with the AI session; the ImportedStreamBridge component
  // reads this slot and drives a third <audio> element.  Setting an
  // importedStation clears the AI session (and vice versa) so the two
  // playback modes are mutually exclusive.
  importedStation: null,         // {id, name, stream_url, favicon, country, language, source}
  importedPlaying: false,

  // Phase B — Podcast episode playback.  Mutually exclusive with
  // importedStation + sessionId.  PodcastPlayerBridge owns a dedicated
  // <audio> element that plays the mp3 + posts progress every 15s.
  //   podcastEpisode = {episode_id, podcast_id, title, cover_image_url,
  //                                      audio_url, duration_seconds, podcast_title,
  //                                      podcast_slug}
  podcastEpisode: null,
  podcastPlaying: false,
  podcastResumePosition: 0,        // seconds to seek to on load

  // Phase H'.5a — AI-RJ inter-song segment glue.
  //  • `rjCadence`      — every-N-songs trigger (fetched once at session
  //                                  start, cached for the rest of the session).
  //  • `songsPlayedSinceRj` — incremented on each song-ended event;
  //                                                  reset to 0 after a segment plays.
  //  • `currentRjSegment` — non-null while the RJ MP3 is playing.  Used
  //                                              by MiniPlayer to swap the source badge to
  //                                              "AI RJ" + persona name.
  rjCadence: null,
  songsPlayedSinceRj: 0,
  currentRjSegment: null,        // {persona_id, voice_id, transcript, audio_url, duration_seconds}
};

export const usePlayerStore = create((set, get) => ({
  ...initialState,

  // ─── Setters ──────────────────────────────────────────────────────────
  setSession: (sessionId) => set({ sessionId }),
  setChannels: (channels) => set({ channels }),
  setActiveChannel: (slug, name = null, thumb = null) =>
    set({
      activeChannel: slug,
      activeChannelName: name ?? get().activeChannelName,
      activeChannelThumb: thumb ?? get().activeChannelThumb,
    }),
  setCurrentSeg: (seg) => set({ currentSeg: seg }),
  setNextSeg: (seg) => set({ nextSeg: seg }),
  setHistory: (h) => set({ history: h }),
  pushHistory: (seg) => set((s) => ({ history: [...s.history, seg].slice(-6) }),
  ),
  setActiveIdx: (i) => set({ activeIdx: i }),
  setPlaying: (p) => set({ playing: !!p }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),
  setVolume: (v) => set({ volume: v }),
  setMuted: (m) => set({ muted: !!m }),
  setSkipState: (used, limit, resetIn) =>
    set({
      skipUsed: used ?? get().skipUsed,
      skipLimit: limit ?? get().skipLimit,
      skipResetIn: resetIn ?? get().skipResetIn,
    }),

  // Phase 42-A2 — imported-stream setters.
  setImportedStation: (station) => set({
    importedStation: station,
    // Switching into imported mode clears the AI session (the
    // ImportedStreamBridge will pause the AI <audio> elements).
    sessionId: station ? null : get().sessionId,
    activeChannel: station ? null : get().activeChannel,
    activeChannelName: station?.name || get().activeChannelName,
    activeChannelThumb: station?.favicon || get().activeChannelThumb,
    currentSeg: station ? null : get().currentSeg,
    nextSeg: station ? null : get().nextSeg,
    importedPlaying: !!station,
    playing: !!station,
  }),
  setImportedPlaying: (p) => set({ importedPlaying: !!p,
                                                                            playing: !!p }),
  clearImported: () => set({ importedStation: null,
                                                                  importedPlaying: false,
                                                                  playing: false }),

  // Phase B — Podcast episode setters.  Setting an episode clears both
  // AI + imported slots so the three modes stay mutually exclusive.
  setPodcastEpisode: (episode, resumePosition = 0) => set({
    podcastEpisode:            episode,
    podcastResumePosition: Number(resumePosition) || 0,
    // Clear other modes.
    sessionId:                        episode ? null : get().sessionId,
    activeChannel:                episode ? null : get().activeChannel,
    activeChannelName:        episode?.podcast_title || get().activeChannelName,
    activeChannelThumb:      episode?.cover_image_url || get().activeChannelThumb,
    currentSeg:                      episode ? null : get().currentSeg,
    nextSeg:                            episode ? null : get().nextSeg,
    importedStation:            episode ? null : get().importedStation,
    importedPlaying:            episode ? false : get().importedPlaying,
    podcastPlaying:              !!episode,
    playing:                            !!episode,
  }),
  setPodcastPlaying: (p) => set({ podcastPlaying: !!p, playing: !!p }),
  clearPodcast: () => set({ podcastEpisode: null,
                                                            podcastPlaying: false,
                                                            podcastResumePosition: 0,
                                                            playing: false }),

  // Phase H'.5a — AI-RJ glue setters.
  setRjCadence: (n) => set({ rjCadence: (typeof n === "number" && n > 0) ? n : null }),
  bumpSongsPlayedSinceRj: () =>
    set((s) => ({ songsPlayedSinceRj: s.songsPlayedSinceRj + 1 })),
  resetSongsPlayedSinceRj: () => set({ songsPlayedSinceRj: 0 }),
  setCurrentRjSegment: (seg) => set({ currentRjSegment: seg || null }),

  // Full reset — called on logout.
  reset: () => set({ ...initialState }),
}));

// Tiny selector helpers used by MiniPlayer + GlobalAudio.
export const selectIsActiveSession = (s) => !!s.sessionId;
export const selectCurrentTrackLabel = (s) => {
  if (!s.currentSeg) return null;
  const title = s.currentSeg.track_title || "Now playing";
  const artist = s.currentSeg.track_artist || s.activeChannelName || "RadioLife";
  return { title, artist };
};
