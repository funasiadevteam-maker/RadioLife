# BigFM — Expo Mobile Mirror · Background Audio Handoff Brief

**Audience:** `e1_expo_frontend_dev` (Expo specialist).
**From:** `e1_dev` (web side).
**Phase:** 15d.3 — Audio persistence.
**Status of web side:** ✅ shipped + tested. Hand-off ready.

---

## Context

The user filed a P0: *"app should continue playing music even if we minimize
it, same way it should continue playing music even on browser, if I am
working in another tab"*.

The **web** half of this is now solved:

* The two crossfade `<audio>` nodes are hoisted to AppShell root via
  `/app/frontend/src/components/GlobalAudio.jsx`. Route navigation never
  unmounts them.
* Playback state lives in `/app/frontend/src/store/usePlayerStore.js` so
  Radio.js can come and go without losing the session.
* MiniPlayer (`/app/frontend/src/shell/primitives.jsx`) reads from the
  same store, so the bottom-of-screen play/pause control works from
  every route.
* Media Session API is wired so Chrome's media hub, macOS Touch Bar,
  Android lock screen, and Windows volume mixer all show track metadata
  + working play/pause/next handlers.
* PWA manifest at `/app/frontend/public/manifest.json` with `display:
  standalone` so the Add-to-Home-Screen path also gives the lock-screen
  controls on Android.
* 9 Jest tests in `Phase15d3_AudioPersistence.test.jsx` — all green.

**The mobile half** (Expo app at `/app/mobile`) is your task.

---

## What you need to configure

### 1. `app.json` / `app.config.js`

```json
{
  "expo": {
    "ios": {
      "infoPlist": {
        "UIBackgroundModes": ["audio"]
      }
    },
    "android": {
      "permissions": [
        "FOREGROUND_SERVICE",
        "FOREGROUND_SERVICE_MEDIA_PLAYBACK",
        "WAKE_LOCK"
      ]
    }
  }
}
```

### 2. Audio mode at app start (`App.tsx` or root layout)

```ts
import { Audio, InterruptionModeIOS, InterruptionModeAndroid } from "expo-av";

await Audio.setAudioModeAsync({
  staysActiveInBackground: true,
  playsInSilentModeIOS: true,
  interruptionModeIOS: InterruptionModeIOS.DoNotMix,
  interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
  shouldDuckAndroid: true,
});
```

### 3. Lock-screen / notification controls

`expo-av` alone does NOT give iOS Now Playing controls or an Android
foreground-service notification. Pick one:

* **Recommended:** swap to `react-native-track-player` (gives both
  iOS Now Playing + Android foreground service notification with
  artwork + play/pause/next out of the box). Same MediaSession-style
  metadata as the web:

```ts
import TrackPlayer, { Capability } from "react-native-track-player";

await TrackPlayer.setupPlayer();
await TrackPlayer.updateOptions({
  capabilities: [Capability.Play, Capability.Pause, Capability.SkipToNext],
  notificationCapabilities: [Capability.Play, Capability.Pause, Capability.SkipToNext],
});
await TrackPlayer.add({
  url: segment.segment_url,
  title: currentSeg.track_title,
  artist: currentSeg.track_artist,
  album: `BigFM · ${channel.name}`,   // use the dynamic market — never "Dubai"
  artwork: `${BACKEND_URL}${channel.thumbnail_url}`,
});
await TrackPlayer.play();
```

* **Lighter:** keep `expo-av` + `expo-notifications` and ship a
  manual foreground-service notification on Android. iOS will get
  basic background audio but no Now Playing artwork until you bridge
  `MPNowPlayingInfoCenter`.

### 4. Metadata source of truth

Mirror the same data the web Media Session uses:

| Field    | Source                                      |
|----------|---------------------------------------------|
| title    | `currentSeg.track_title`                    |
| artist   | `currentSeg.track_artist`                   |
| album    | `BigFM · {channel.name}` (NEVER "Dubai")    |
| artwork  | `BACKEND_URL + channel.thumbnail_url`       |

`channel.thumbnail_url` is now populated on `/api/channels` (Phase 15d.2)
and points at the Nano-Banana generated `.webp` posters served from
`/api/static/channel_thumbnails/{slug}.webp`.

### 5. Acceptance criteria

1. Start playback in the app.
2. Press home / lock screen → audio CONTINUES.
3. Lock screen shows: title, artist, channel name, channel thumbnail,
   play/pause, next (next track respects 6/hr skip cap — the existing
   `/api/radio/next` endpoint already enforces this).
4. Tap play/pause on lock screen → state syncs back to the app when
   foregrounded.
5. Tap notification → opens app to `/radio`.
6. Switch apps (not lock) on Android → foreground service notification
   visible with artwork.
7. iOS: audio continues for at least 60 minutes in background.
8. Android: audio continues with screen off; foreground service does
   not crash on doze.

### 6. Backend touchpoints (no changes needed — already live)

* `POST /api/radio/start` — start a session for a channel slug.
* `GET /api/radio/next?session_id=...` — next segment URL + skip state.
* `GET /api/radio/segment/{id}` — actual MP3, supports HTTP Range.
* `GET /api/channels` — returns `thumbnail_url` per channel.

### 7. Tests to add on mobile side

* `test_audio_continues_when_app_backgrounded` — start playback, send
  app to background, wait 10s, assert TrackPlayer state is still
  PLAYING.
* `test_lock_screen_metadata_updates_on_track_change` — change track,
  assert MPNowPlayingInfoCenter / MediaSession metadata reflects the
  new title/artist/artwork.
* `test_lock_screen_play_pause_syncs_with_app` — fire native pause from
  notification, verify app's player store also reflects paused state.

---

## Web side reference

| Concern                       | Web file                                                    |
|-------------------------------|-------------------------------------------------------------|
| Global audio mount            | `/app/frontend/src/components/GlobalAudio.jsx`              |
| Player state store            | `/app/frontend/src/store/usePlayerStore.js`                 |
| Singleton audio element refs  | `/app/frontend/src/store/audioElements.js`                  |
| MiniPlayer wired to store     | `/app/frontend/src/shell/primitives.jsx` (`MiniPlayer`)     |
| PWA manifest                  | `/app/frontend/public/manifest.json`                        |
| Jest suite                    | `/app/frontend/src/__tests__/Phase15d3_AudioPersistence.test.jsx` |

The web side does NOT depend on the Expo side shipping — they're
independent code paths. Web is already verified green.

— End of brief —
