/**
 * Push Notifications — wired to POST /api/users/push_token
 *
 * On web preview: Push notifications are NOT supported. The permission request
 * will silently fail. This is expected — native builds will work correctly.
 */
import { Platform } from 'react-native';

let Notifications: any = null;
let Device: any = null;

/** Cached token so logout can deregister without re-requesting permission. */
let _cachedToken: string | null = null;

export function getCachedPushToken(): string | null {
  return _cachedToken;
}

async function loadModules() {
  if (Platform.OS === 'web') return false;
  try {
    Notifications = await import('expo-notifications');
    Device = await import('expo-device');
    return true;
  } catch {
    return false;
  }
}

export async function requestPushPermission(): Promise<string | null> {
  if (Platform.OS === 'web') return null;

  const loaded = await loadModules();
  if (!loaded || !Notifications || !Device) return null;
  if (!Device.isDevice) return null;

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') return null;

  try {
    const tokenData = await Notifications.getExpoPushTokenAsync();
    _cachedToken = tokenData.data;
    return _cachedToken;
  } catch {
    return null;
  }
}

/**
 * Register push token with backend.
 * Best-effort: logs on failure, never crashes, no retry loop.
 */
export async function registerPushToken(apiClient: any): Promise<void> {
  const token = await requestPushPermission();
  if (!token) return;

  try {
    await apiClient.post('/users/push_token', {
      expo_push_token: token,
      platform: Platform.OS,
    });
    console.log('[Push] Token registered');
  } catch (e: any) {
    console.warn('[Push] Registration failed (will retry on next foreground):', e?.message);
  }
}

/**
 * Deregister push token on logout. Best-effort — never blocks logout.
 */
export async function deregisterPushToken(apiClient: any): Promise<void> {
  const token = _cachedToken;
  if (!token) return;
  try {
    await apiClient.delete('/users/push_token', { data: { expo_push_token: token } });
    console.log('[Push] Token deregistered');
  } catch {
    // best-effort — don't block logout
  }
  _cachedToken = null;
}

/**
 * Setup foreground notification handler.
 */
export function setupForegroundHandler() {
  if (Platform.OS === 'web' || !Notifications) return;

  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });
}

/**
 * Setup notification response handler (tap on notification).
 */
export function setupResponseHandler(router: any) {
  if (Platform.OS === 'web' || !Notifications) return null;

  const subscription = Notifications.addNotificationResponseReceivedListener((response: any) => {
    const data = response.notification.request.content.data;

    if (data?.type === 'trivia_room' && data?.room_code) {
      router.push(`/trivia/rooms/${data.room_code}`);
    } else if (data?.screen === 'coupon' && data?.id) {
      router.push(`/coupon/${data.id}`);
    } else if (data?.screen === 'lobby' && data?.id) {
      router.push(`/lobby/${data.id}`);
    } else if (data?.screen === 'game' && data?.id) {
      router.push(`/game/${data.id}`);
    } else if (data?.screen === 'wallet') {
      router.push('/(tabs)/wallet');
    } else if (data?.screen === 'passport') {
      router.push('/(tabs)/passport');
    }
  });

  return subscription;
}
