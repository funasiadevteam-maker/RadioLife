// Free OpenStreetMap (Nominatim) geocoding + OSRM routing — no API key.
// Resolves a delivery address into a jurisdiction (country/state/county/city)
// for destination-based tax, plus lat/lng and a driving route line.

function jurisdiction(a = {}) {
  const iso = a["ISO3166-2-lvl4"] || a["ISO3166-2-lvl3"] || "";
  const stateCode = iso.includes("-") ? iso.split("-")[1] : null;
  return {
    country: a.country_code ? String(a.country_code).toUpperCase() : null,
    state: stateCode || a.state || null,
    county: a.county || a.state_district || null,
    city: a.city || a.town || a.village || a.suburb || a.municipality || null,
  };
}

export async function reverseGeocode(lat, lng) {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&addressdetails=1`;
    const d = await (await fetch(url, { headers: { Accept: "application/json" } })).json();
    if (!d || !d.address) return null;
    return { label: d.display_name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`, line1: d.display_name || null, lat, lng, ...jurisdiction(d.address) };
  } catch { return null; }
}

export async function forwardGeocode(query) {
  try {
    const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&q=${encodeURIComponent(query)}&addressdetails=1&limit=1`;
    const arr = await (await fetch(url, { headers: { Accept: "application/json" } })).json();
    const d = Array.isArray(arr) ? arr[0] : null;
    if (!d) return null;
    return { label: d.display_name || query, line1: query, lat: parseFloat(d.lat), lng: parseFloat(d.lon), ...jurisdiction(d.address || {}) };
  } catch { return null; }
}

export async function routeLine(from, to) {
  try {
    const url = `https://router.project-osrm.org/route/v1/driving/${from.lng},${from.lat};${to.lng},${to.lat}?overview=full&geometries=geojson`;
    const d = await (await fetch(url)).json();
    const coords = d?.routes?.[0]?.geometry?.coordinates;
    if (!Array.isArray(coords)) return null;
    return coords.map((c) => [c[1], c[0]]); // leaflet wants [lat, lng]
  } catch { return null; }
}
