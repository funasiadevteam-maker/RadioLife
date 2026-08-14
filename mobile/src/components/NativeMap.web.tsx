// Web stub for NativeMap — react-native-maps is native-only, so the web
// preview renders a graceful fallback instead (handled by the caller).
export const MAPS_AVAILABLE = false;

export type MapPin = {
  id: string; lat: number; lng: number;
  title?: string; description?: string; onPress?: () => void;
};

export default function NativeMap() {
  return null;
}
