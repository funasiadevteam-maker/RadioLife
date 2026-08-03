// Mock expo-audio for tests
export const setAudioModeAsync = jest.fn().mockResolvedValue(undefined);
export default { setAudioModeAsync };
