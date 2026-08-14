// Free OpenStreetMap (Nominatim) geocoding — no API key. Used to resolve a
// delivery address into a jurisdiction (country/state/county/city) so the
// backend can charge destination-based tax, plus lat/lng for the route map.
export type GeoResult = {
  label: string;
  line1: string | null;
  lat: number;
  lng: number;
  country: string | null;   // ISO2, e.g. "US"
  state: string | null;     // ISO 3166-2 subdivision, e.g. "CA"
  county: string | null;
  city: string | null;
};

const HEADERS = { 'Accept': 'application/json' } as any;

function jurisdiction(a: any) {
  const iso = a['ISO3166-2-lvl4'] || a['ISO3166-2-lvl3'] || '';
  const stateCode = iso.includes('-') ? iso.split('-')[1] : null;
  return {
    country: a.country_code ? String(a.country_code).toUpperCase() : null,
    state: stateCode || a.state || null,
    county: a.county || a.state_district || null,
    city: a.city || a.town || a.village || a.suburb || a.municipality || null,
  };
}

export async function reverseGeocode(lat: number, lng: number): Promise<GeoResult | null> {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&addressdetails=1`;
    const r = await fetch(url, { headers: HEADERS });
    const d = await r.json();
    if (!d || !d.address) return null;
    const j = jurisdiction(d.address);
    return { label: d.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`, line1: d.display_name || null, lat, lng, ...j };
  } catch {
    return null;
  }
}

export async function forwardGeocode(query: string): Promise<GeoResult | null> {
  try {
    const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&q=${encodeURIComponent(query)}&addressdetails=1&limit=1`;
    const r = await fetch(url, { headers: HEADERS });
    const arr = await r.json();
    const d = Array.isArray(arr) ? arr[0] : null;
    if (!d) return null;
    const j = jurisdiction(d.address || {});
    return { label: d.display_name || query, line1: query, lat: parseFloat(d.lat), lng: parseFloat(d.lon), ...j };
  } catch {
    return null;
  }
}

// OSRM free routing — returns [lng,lat] coordinate pairs for a driving route.
export async function routeLine(from: { lat: number; lng: number }, to: { lat: number; lng: number }):
  Promise<{ lat: number; lng: number }[] | null> {
  try {
    const url = `https://router.project-osrm.org/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    const r = await fetch(url);
    const d = await r.json();
    const coords = d?.routes?.[0]?.geometry?.coordinates;
    if (!Array.isArray(coords)) return null;
    return coords.map((c: number[]) => ({ lat: c[1], lng: c[0] }));
  } catch {
    return null;
  }
}
