/**
 * Phase 15d.3 — Background Audio Tests
 *
 * Verifies:
 * 1. Audio mode configured for background playback (staysActiveInBackground + playsInSilentModeIOS)
 * 2. TrackPlayer updates on segment change (reset + add with correct metadata)
 * 3. Lock-screen album uses channel.name, NOT hardcoded "Dubai"
 */

// Define React Native globals that the source modules expect
(globalThis as any).__DEV__ = true;

// Get mocked modules (mapped via jest.config.js moduleNameMapper)
const mockAudio = require('expo-audio');
const mockTP = require('react-native-track-player').default;

// Import the actual service modules (they use the mocked dependencies via moduleNameMapper)
const audioInit = require('../src/services/audioInit');
const bridge = require('../src/services/nativePlayerBridge');

describe('Phase 15d.3 — Background Audio', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('test_audio_mode_configured_for_background_playback', async () => {
    // audioInit.configureAudioMode() calls Audio.setAudioModeAsync internally.
    // On first call _configured is false, so it will fire.
    const setAudioModeAsync = mockAudio.default?.setAudioModeAsync || mockAudio.setAudioModeAsync;

    await audioInit.configureAudioMode();

    expect(setAudioModeAsync).toHaveBeenCalledTimes(1);
    const args = setAudioModeAsync.mock.calls[0][0];
    expect(args).toEqual(
      expect.objectContaining({
        staysActiveInBackground: true,
        playsInSilentModeIOS: true,
        shouldDuckAndroid: true,
      }),
    );
    // interruptionModeIOS = 1 (DoNotMix enum value)
    expect(args.interruptionModeIOS).toBeTruthy();
    expect(args.interruptionModeAndroid).toBeTruthy();
  });

  test('test_track_player_updates_on_segment_change', async () => {
    // Setup native player first (makes _tpReady = true)
    await bridge.setupNativePlayer();

    // Clear setup-related calls
    mockTP.reset.mockClear();
    mockTP.add.mockClear();
    mockTP.play.mockClear();

    // Push a new segment
    await bridge.updateNowPlaying(
      'https://test.bigfm.app/api/radio/segment/abc123',
      'Tum Hi Ho',
      'Arijit Singh',
      'Bollywood Mehfil',
      '/api/static/channel_thumbnails/bollywood_mehfil.webp',
    );

    // Assert reset -> add -> play sequence
    expect(mockTP.reset).toHaveBeenCalledTimes(1);
    expect(mockTP.add).toHaveBeenCalledTimes(1);
    expect(mockTP.play).toHaveBeenCalledTimes(1);

    // Verify metadata fields in TrackPlayer.add()
    const addArgs = mockTP.add.mock.calls[0][0];
    expect(addArgs.title).toBe('Tum Hi Ho');
    expect(addArgs.artist).toBe('Arijit Singh');
    expect(addArgs.album).toBe('BigFM · Bollywood Mehfil');
    expect(addArgs.artwork).toContain('bollywood_mehfil.webp');
    expect(addArgs.url).toBe('https://test.bigfm.app/api/radio/segment/abc123');
  });

  test('test_lockscreen_album_uses_channel_name_not_dubai', async () => {
    // Ensure player is ready
    await bridge.setupNativePlayer();
    mockTP.add.mockClear();

    // Simulate DFW market user listening to "Party Mix" channel
    await bridge.updateNowPlaying(
      'https://test.bigfm.app/api/radio/segment/xyz789',
      'Levitating',
      'Dua Lipa',
      'Party Mix',
      '/api/static/channel_thumbnails/party_mix.webp',
    );

    const addArgs = mockTP.add.mock.calls[0][0];

    // Album MUST contain the dynamic channel name
    expect(addArgs.album).toBe('BigFM · Party Mix');
    expect(addArgs.album).toContain('Party Mix');

    // Album MUST NOT contain "Dubai" (de-Dubai brand requirement from Phase 15d)
    expect(addArgs.album).not.toContain('Dubai');
    expect(addArgs.album).not.toContain('dubai');
  });
});
