/**
 * Push notifications — Emergent managed relay (SuprSend).
 *
 * The backend is the only caller of the push relay; the client just registers
 * its NATIVE device token (getDevicePushTokenAsync) against the logged-in
 * user_id via POST /api/register-push. Tokens rotate, so we re-register on
 * every app open. Web preview + Expo Go cannot deliver real push — the calls
 * no-op gracefully there (native builds work after Publish).
 */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

let _cachedToken: string | null = null;

export function getCachedPushToken(): string | null {
  return _cachedToken;
}

/** Request permission (iOS prompt / Android 13+ POST_NOTIFICATIONS) then fetch
 *  the native FCM/APNs token. Returns null when unavailable/denied. */
export async function requestPushPermission(): Promise<string | null> {
  if (Platform.OS === 'web' || !Device.isDevice) return null;
  try {
    const { status: existing } = await Notifications.getPermissionsAsync();
    let status = existing;
    if (existing !== 'granted') {
      status = (await Notifications.requestPermissionsAsync()).status;
    }
    if (status !== 'granted') return null;
    const tokenResp = await Notifications.getDevicePushTokenAsync();
    _cachedToken = String(tokenResp.data);
    return _cachedToken;
  } catch {
    return null;
  }
}

/** Register (or refresh) this device for the given user. Best-effort. */
export async function registerForPush(userId?: string | null): Promise<void> {
  if (Platform.OS === 'web' || !userId) return;
  const token = await requestPushPermission();
  if (!token) return;
  try {
    await fetch(`${BACKEND_URL}/api/register-push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, platform: Platform.OS, device_token: token }),
    });
  } catch {
    /* best-effort — will retry on next app open */
  }
}

/** Kept for call-site compatibility. SuprSend manages token lifecycle, so
 *  there's nothing to deregister on the client. */
export async function deregisterPushToken(_apiClient?: any): Promise<void> {
  _cachedToken = null;
}

/** Kept for the notifications toggle screen. */
export async function registerPushToken(_apiClient: any, userId?: string | null): Promise<void> {
  await registerForPush(userId);
}
