import * as Localization from 'expo-localization';

// Countries that use miles for everyday road distance.
const MILES_REGIONS = new Set(['US', 'GB', 'MM', 'LR']);

export function distanceUnit(region?: string | null): 'mi' | 'km' {
  let r = (region || '').toUpperCase();
  if (!r) {
    try { r = (Localization.getLocales?.()[0]?.regionCode || '').toUpperCase(); } catch { /* noop */ }
  }
  return MILES_REGIONS.has(r) ? 'mi' : 'km';
}

/** Format a kilometre distance in the caller's local unit (km / mi). */
export function formatDistance(km?: number | null, region?: string | null): string {
  if (km == null) return '';
  const unit = distanceUnit(region);
  const val = unit === 'mi' ? km * 0.621371 : km;
  if (val < 0.1) return unit === 'mi' ? '< 0.1 mi' : '< 0.1 km';
  return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${unit}`;
}
