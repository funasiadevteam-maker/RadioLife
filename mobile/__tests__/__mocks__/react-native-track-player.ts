// Mock react-native-track-player for tests
export const Capability = {
  Play: 'play',
  Pause: 'pause',
  SkipToNext: 'skip_to_next',
};

export const Event = {
  RemotePlay: 'remote-play',
  RemotePause: 'remote-pause',
  RemoteNext: 'remote-next',
};

const TrackPlayer = {
  setupPlayer: jest.fn().mockResolvedValue(undefined),
  updateOptions: jest.fn().mockResolvedValue(undefined),
  reset: jest.fn().mockResolvedValue(undefined),
  add: jest.fn().mockResolvedValue(undefined),
  play: jest.fn().mockResolvedValue(undefined),
  pause: jest.fn().mockResolvedValue(undefined),
  addEventListener: jest.fn().mockReturnValue({ remove: jest.fn() }),
};

export default TrackPlayer;
