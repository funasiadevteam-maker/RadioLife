import { useWindowDimensions } from 'react-native';
import type { ViewStyle } from 'react-native';

// Reactive tablet/phone layout helper. Recomputes on rotation (pairs with
// the per-device orientation lock in app/_layout.tsx — iPad rotates freely).
// On phones every style helper is null (no effect → full-width phone layout).
// On tablets content is capped to a centered column so screens never look
// like a stretched phone: ~640 for reading feeds, ~1040 for card grids.
export function useResponsive() {
  const { width, height } = useWindowDimensions();
  const isTablet = Math.min(width, height) >= 768;
  const feed: ViewStyle | null = isTablet
    ? { maxWidth: 640, width: '100%', alignSelf: 'center' }
    : null;
  const grid: ViewStyle | null = isTablet
    ? { maxWidth: 1040, width: '100%', alignSelf: 'center' }
    : null;
  return { width, height, isTablet, feed, grid };
}

export default useResponsive;
