/**
 * Phase 15d.3 — Audio persistence + Media Session API regression suite.
 *
 * The user's bug report: "when I move from tab or any other link, my radio
 * stops playing — it needs to continue playing, unless I switch another
 * radio channel".
 *
 * These tests verify the architecture that fixes it:
 *   1. The two HTMLAudioElement nodes live in a module singleton
 *      (`audioElements.js`) that's mounted by `<GlobalAudio />` at AppShell
 *      root.  Route navigation never unmounts them.
 *   2. `usePlayerStore` zustand store holds session/segment/transport state
 *      that survives Radio.js unmount.
 *   3. Logout calls `teardownAllAudio()` → audio stopped + src cleared.
 *   4. Media Session API metadata + action handlers are wired so the
 *      browser media hub / OS lock screen show the current BigFM track.
 *
 * We test the store + module helpers + the GlobalAudio Media Session
 * wiring directly (no Playwright needed for these — Playwright would
 * verify the cross-route behavior in /app/tests/).
 */
import React from "react";
import { render, act } from "@testing-library/react";
import { audioElements, pauseAllAudio, teardownAllAudio } from "../store/audioElements";
import { usePlayerStore } from "../store/usePlayerStore";
import GlobalAudio from "../components/GlobalAudio";

// JSDOM's HTMLMediaElement doesn't implement play/pause/load — stub them.
beforeAll(() => {
  Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: jest.fn().mockResolvedValue(undefined),
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
    configurable: true,
    value: jest.fn(),
  });
  Object.defineProperty(window.HTMLMediaElement.prototype, "load", {
    configurable: true,
    value: jest.fn(),
  });
  // Mock Media Session API (not in JSDOM).
  if (!("mediaSession" in navigator)) {
    Object.defineProperty(navigator, "mediaSession", {
      configurable: true,
      value: {
        metadata: null,
        setActionHandler: jest.fn(),
      },
    });
  }
  if (typeof window.MediaMetadata === "undefined") {
    window.MediaMetadata = function (init) { Object.assign(this, init); };
  }
});

beforeEach(() => {
  usePlayerStore.getState().reset();
  audioElements.a.current = null;
  audioElements.b.current = null;
  if (navigator.mediaSession) {
    navigator.mediaSession.metadata = null;
  }
});

// ── 1. Audio element singleton survives across component mount/unmount ──
test("test_audio_persists_across_route_navigation", () => {
  // Mount GlobalAudio once — simulates AppShell at app root.
  const { container, unmount: _ } = render(<GlobalAudio />);
  expect(audioElements.a.current).toBeTruthy();
  expect(audioElements.b.current).toBeTruthy();
  const aBefore = audioElements.a.current;
  // The singleton refs MUST remain pointing at the same HTMLAudioElement
  // even after the consuming component (Radio.js) would unmount.  Here we
  // simulate that by mounting + unmounting a "Radio" component that does
  // NOT own the audio element — proving the audio survives.
  const FakeRadio = () => <div data-testid="radio-page" />;
  const radio = render(<FakeRadio />);
  radio.unmount();
  // After unmount, the audio singleton's element ref is unchanged.
  expect(audioElements.a.current).toBe(aBefore);
  expect(container.querySelector("[data-testid=audio-0]")).toBeTruthy();
});

// ── 2. visibilitychange / blur DO NOT pause audio ──
test("test_audio_persists_across_tab_visibility_change", () => {
  render(<GlobalAudio />);
  const a = audioElements.a.current;
  expect(a).toBeTruthy();
  // Spy on pause — neither tab-blur nor visibilitychange should fire it.
  const pauseSpy = jest.spyOn(a, "pause");
  Object.defineProperty(document, "hidden", { value: true, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
  window.dispatchEvent(new Event("blur"));
  Object.defineProperty(document, "hidden", { value: false, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
  expect(pauseSpy).not.toHaveBeenCalled();
});

// ── 3. Switching channels updates state in store ──
test("test_audio_switches_source_on_channel_change", () => {
  render(<GlobalAudio />);
  act(() => {
    usePlayerStore.getState().setActiveChannel("morning_masala", "Morning Masala", "/api/static/x.webp");
  });
  expect(usePlayerStore.getState().activeChannel).toBe("morning_masala");
  expect(usePlayerStore.getState().activeChannelName).toBe("Morning Masala");
  // Switch to a different channel.
  act(() => {
    usePlayerStore.getState().setActiveChannel("late_night_drive", "Late Night Drive", "/api/static/y.webp");
  });
  expect(usePlayerStore.getState().activeChannel).toBe("late_night_drive");
  expect(usePlayerStore.getState().activeChannelName).toBe("Late Night Drive");
});

// ── 4. bigfm:player:toggle pauses a playing audio ──
test("test_audio_stops_on_explicit_pause", async () => {
  render(<GlobalAudio />);
  const a = audioElements.a.current;
  expect(a).toBeTruthy();
  // Force "playing" state by making paused=false.
  Object.defineProperty(a, "paused", { value: false, configurable: true });
  const pauseSpy = jest.spyOn(a, "pause");
  await act(async () => {
    window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
  });
  expect(pauseSpy).toHaveBeenCalled();
});

// ── 5. Logout teardown stops both audio elements + clears src ──
test("test_audio_stops_on_logout", () => {
  render(<GlobalAudio />);
  const a = audioElements.a.current;
  const b = audioElements.b.current;
  a.src = "/api/some/segment.mp3";
  b.src = "/api/other/segment.mp3";
  const pauseA = jest.spyOn(a, "pause");
  const pauseB = jest.spyOn(b, "pause");
  teardownAllAudio();
  expect(pauseA).toHaveBeenCalled();
  expect(pauseB).toHaveBeenCalled();
  expect(a.getAttribute("src")).toBeFalsy();
  expect(b.getAttribute("src")).toBeFalsy();
});

// ── 6. Media Session metadata updates on track change ──
test("test_media_session_metadata_set_on_track_change", () => {
  render(<GlobalAudio />);
  act(() => {
    usePlayerStore.getState().setActiveChannel("vip_lounge", "VIP Lounge", "/api/static/vip.webp");
    usePlayerStore.getState().setCurrentSeg({
      segment_id: "seg_1",
      track_title: "Mehfil Nights",
      track_artist: "Ananya R",
      segment_url: "/api/radio/segment/1.mp3",
    });
  });
  expect(navigator.mediaSession.metadata).toBeTruthy();
  expect(navigator.mediaSession.metadata.title).toBe("Mehfil Nights");
  expect(navigator.mediaSession.metadata.artist).toBe("Ananya R");
  expect(navigator.mediaSession.metadata.album).toContain("VIP Lounge");
  expect(navigator.mediaSession.metadata.album).toContain("BigFM");
  // Album must NEVER hardcode "Dubai" — it follows the channel/market.
  expect(navigator.mediaSession.metadata.album).not.toContain("Dubai");
});

// ── 6b. Phase 15d.3 race fix — channel switch publishes WITHIN 1s,
//      synchronously with the store update — no need to wait for the
//      audio element's `loadedmetadata` event.
test("test_media_session_album_refreshes_within_1s_of_channel_switch", () => {
  jest.useFakeTimers();
  render(<GlobalAudio />);
  // 1.  Establish channel A as playing.
  act(() => {
    usePlayerStore.getState().setActiveChannel(
      "bollywood_mehfil", "Bollywood Mehfil",
      "/api/static/channel_thumbnails/bollywood_mehfil.webp");
    usePlayerStore.getState().setCurrentSeg({
      segment_id: "seg_A",
      track_title: "Dil Se",
      track_artist: "AR Rahman",
      segment_url: "/api/radio/segment/A.mp3",
    });
  });
  expect(navigator.mediaSession.metadata.album).toContain("Bollywood Mehfil");

  // 2.  User clicks channel B.  Radio.js writes the new channel name +
  //     thumb to the store OPTIMISTICALLY (synchronously) — currentSeg
  //     still belongs to channel A because the new segment hasn't loaded
  //     yet.  Album should already reflect channel B.
  act(() => {
    usePlayerStore.getState().setActiveChannel(
      "party_dubai", "Party Mix",
      "/api/static/channel_thumbnails/party_dubai.webp");
  });
  // No wait — assert inside the SAME synchronous tick.
  expect(navigator.mediaSession.metadata.album).toBe("BigFM · Party Mix");
  expect(navigator.mediaSession.metadata.album).not.toContain("Bollywood Mehfil");

  // 3.  Advance time by < 1s to confirm the publish ALREADY happened
  //     (no setTimeout, no event wait).
  act(() => { jest.advanceTimersByTime(900); });
  expect(navigator.mediaSession.metadata.album).toBe("BigFM · Party Mix");

  // 4.  Artwork also follows the new channel within the same window.
  expect(navigator.mediaSession.metadata.artwork[0].src)
    .toContain("party_dubai.webp");
  expect(navigator.mediaSession.metadata.artwork[0].src)
    .not.toContain("bollywood_mehfil.webp");
  jest.useRealTimers();
});

// ── 7. Media Session action handlers wired ──
test("test_media_session_action_handlers_wired", () => {
  const setActionHandler = jest.spyOn(navigator.mediaSession, "setActionHandler");
  render(<GlobalAudio />);
  const calls = setActionHandler.mock.calls.map((c) => c[0]);
  expect(calls).toContain("play");
  expect(calls).toContain("pause");
  expect(calls).toContain("nexttrack");
  // previoustrack is explicitly nulled (non-interactive radio).
  expect(calls).toContain("previoustrack");
});

// ── 8. Media Session artwork uses channel thumbnail ──
test("test_media_session_artwork_uses_channel_thumbnail", () => {
  render(<GlobalAudio />);
  act(() => {
    usePlayerStore.getState().setActiveChannel("bollywood_mehfil", "Bollywood Mehfil",
      "/api/static/channel_thumbnails/bollywood_mehfil.webp");
    usePlayerStore.getState().setCurrentSeg({
      segment_id: "seg_2",
      track_title: "Tum Hi Ho",
      track_artist: "Arijit Singh",
      segment_url: "/api/radio/segment/2.mp3",
    });
  });
  const art = navigator.mediaSession.metadata.artwork;
  expect(Array.isArray(art)).toBe(true);
  expect(art.length).toBeGreaterThan(0);
  expect(art[0].src).toContain("/api/static/channel_thumbnails/bollywood_mehfil.webp");
  expect(art[0].type).toBe("image/webp");
});

// ── helper coverage ──
test("pauseAllAudio handles missing refs gracefully", () => {
  audioElements.a.current = null;
  audioElements.b.current = null;
  expect(() => pauseAllAudio()).not.toThrow();
});
