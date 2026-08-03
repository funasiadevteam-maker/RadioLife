// Phase R.1 — Market → default coordinates.  Used when RadioLife needs
// a lat/lng for the /api/public/businesses/nearby query but the user's
// profile only surfaces a `market` string.  We don't reverse-geocode; a
// city-centroid is sufficient for the nearby-deals radius.
export const MARKET_COORDS = {
  dubai:         { lat: 25.15,      lng: 55.25,     label: "Dubai" },
  new_york:      { lat: 40.7128, lng: -74.0060, label: "New York" },
  london:        { lat: 51.5074, lng: -0.1278,  label: "London" },
  mumbai:      { lat: 19.0760, lng: 72.8777,  label: "Mumbai" },
  los_angeles: { lat: 34.0522, lng: -118.2437, label: "Los Angeles" },
  dfw:            { lat: 32.7767, lng: -96.7970, label: "Dallas–Fort Worth" },
};

export function coordsForMarket(market) {
  const m = (market || "").trim().toLowerCase().replace(/[\s-]/g, "_");
  return MARKET_COORDS[m] || null;
}
