// Mock expo-notifications for tests
export const addNotificationResponseReceivedListener = jest.fn((callback: any) => {
  // Store the callback so tests can invoke it
  (addNotificationResponseReceivedListener as any)._callback = callback;
  return { remove: jest.fn() };
});

export const getPermissionsAsync = jest.fn().mockResolvedValue({ status: 'granted' });
export const requestPermissionsAsync = jest.fn().mockResolvedValue({ status: 'granted' });
export const getExpoPushTokenAsync = jest.fn().mockResolvedValue({ data: 'ExponentPushToken[test]' });

export const setNotificationHandler = jest.fn();
