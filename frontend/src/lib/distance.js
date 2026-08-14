// Local-unit distance formatting (km / miles) based on country/region.
const MILES_REGIONS = new Set(["US", "GB", "MM", "LR"]);

export function distanceUnit(region) {
  let r = (region || "").toUpperCase();
  if (!r && typeof navigator !== "undefined") {
    const loc = navigator.language || "";
    const m = loc.split("-")[1];
    if (m) r = m.toUpperCase();
  }
  return MILES_REGIONS.has(r) ? "mi" : "km";
}

export function formatDistance(km, region) {
  if (km == null) return "";
  const unit = distanceUnit(region);
  const val = unit === "mi" ? km * 0.621371 : km;
  if (val < 0.1) return unit === "mi" ? "< 0.1 mi" : "< 0.1 km";
  return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${unit}`;
}
