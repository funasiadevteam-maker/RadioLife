// Phase H v1 — Commute Mode MVP.  Real Google Maps + Places Autocomplete
// + Routes-backed offer matching.  Route: /commute.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { APIProvider, Map, AdvancedMarker, useMap, useMapsLibrary }
  from "@vis.gl/react-google-maps";
import { decode as decodePolyline } from "@googlemaps/polyline-codec";
import {
  MapPin, Navigation, Cloud, Gauge, Sparkles, Save, ArrowLeft, Utensils,
  Wine, Moon, Car, Loader2, Search, X, CheckCircle2,
} from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { toast } from "sonner";
import { useCommuteMode } from "@/hooks/useCommuteMode";

const GOOGLE_MAPS_API_KEY = process.env.REACT_APP_GOOGLE_MAPS_API_KEY || "";
const DUBAI_CENTER = { lat: 25.15, lng: 55.25 };
// Seed origin default per test brief — Dubai Marina.  Users can override.
const DEFAULT_ORIGIN = { lat: 25.0777, lng: 55.1300, address: "Dubai Marina, Dubai, UAE" };

const ACTIVITIES = [
  { id: "commute",   label: "Commute",   Icon: Car,      hint: "Coffee · gas" },
  { id: "lunch",     label: "Lunch",     Icon: Utensils, hint: "Cafes · restaurants" },
  { id: "dinner",    label: "Dinner",    Icon: Wine,     hint: "Bars · dining" },
  { id: "nightlife", label: "Nightlife", Icon: Moon,     hint: "Late-night" },
];

// Map dark styling — matches FUUSIC dark theme.
const MAP_STYLE_ID = null;

export default function CommuteMode() {
  const navigate = useNavigate();
  const { session, loading, error, startCommute, saveCoupon, endCommute }
    = useCommuteMode();
  const [activity, setActivity] = useState("lunch");
  const [origin, setOrigin] = useState(DEFAULT_ORIGIN);
  const [destination, setDestination] = useState(null);
  const [savingOfferId, setSavingOfferId] = useState(null);

  // Try to pull the user's current location.  Fall back silently on denial.
  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setOrigin({ lat: pos.coords.latitude, lng: pos.coords.longitude,
                                address: "Current location" }),
      () => { /* keep default */ },
      { enableHighAccuracy: false, timeout: 5000, maximumAge: 60_000 });
  }, []);

  const handleStart = useCallback(async (destPoint) => {
    if (!origin || !destPoint) {
      toast.error("Set a destination first");
      return;
    }
    try {
      await startCommute({
        origin: { lat: origin.lat, lng: origin.lng,
                    formatted_address: origin.address },
        destination: { lat: destPoint.lat, lng: destPoint.lng,
                             formatted_address: destPoint.address,
                             place_id: destPoint.place_id },
        activity });
      toast.success("Route built");
    } catch (e) {
      toast.error(`Couldn't build route: ${String(e.message || e).slice(0, 120)}`);
    }
  }, [origin, activity, startCommute]);

  const handleDestinationPicked = useCallback((place) => {
    setDestination(place);
    handleStart(place);
  }, [handleStart]);

  const handleSaveCoupon = useCallback(async (offerId) => {
    setSavingOfferId(offerId);
    try {
      await saveCoupon(offerId, session?.session_id);
      toast.success("Coupon saved to wallet");
    } catch (e) {
      toast.error(`Save failed: ${String(e.message || e).slice(0, 120)}`);
    } finally {
      setSavingOfferId(null);
    }
  }, [saveCoupon, session]);

  const handleReset = useCallback(async () => {
    if (session?.session_id) {
      try { await endCommute(session.session_id); } catch { /* ignore */ }
    }
    setDestination(null);
  }, [session, endCommute]);

  const polyPoints = useMemo(() => {
    const enc = session?.route?.encoded_polyline;
    if (!enc) return [];
    try {
      return decodePolyline(enc).map(([lat, lng]) => ({ lat, lng }));
    } catch { return []; }
  }, [session]);

  const mapCenter = useMemo(() => {
    if (destination) return { lat: destination.lat, lng: destination.lng };
    if (origin) return { lat: origin.lat, lng: origin.lng };
    return DUBAI_CENTER;
  }, [origin, destination]);

  if (!GOOGLE_MAPS_API_KEY) {
    return (
      <div className="min-h-screen bg-bg-base text-text-primary p-6"
              data-testid="commute-no-key">
        <div className="max-w-md mx-auto">
          <Card className="p-6">
            <h1 className="text-xl font-display font-bold mb-2">Commute Mode</h1>
            <p className="text-text-secondary text-sm">
              Google Maps API key not configured. Set{" "}
              <code className="text-accent-electric">REACT_APP_GOOGLE_MAPS_API_KEY</code>
              {" "}in the frontend environment.
            </p>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <APIProvider apiKey={GOOGLE_MAPS_API_KEY} libraries={["places"]}>
      <div className="min-h-screen bg-bg-base text-text-primary pb-24"
              data-testid="commute-mode-page">
        {/* ── Header ─────────────────────────────────────────────────── */}
        <header className="sticky top-0 z-30 bg-bg-base/90 backdrop-blur-md
                                    border-b border-white/[0.06]">
          <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => navigate("/")}
              data-testid="commute-back-btn"
              className="p-2 -ml-2 rounded-full hover:bg-white/[0.06]
                                 transition-colors">
              <ArrowLeft size={20} />
            </button>
            <div className="flex-1">
              <div className="text-xs font-mono uppercase tracking-widest
                                        text-accent-electric">Phase H</div>
              <h1 className="text-lg font-display font-bold tracking-display-tight">
                Commute Mode
              </h1>
            </div>
            {session && (
              <button
                onClick={handleReset}
                data-testid="commute-reset-btn"
                className="p-2 rounded-full hover:bg-white/[0.06] transition-colors">
                <X size={18} />
              </button>
            )}
          </div>
        </header>

        <div className="max-w-3xl mx-auto px-4 pt-4 space-y-4">
          {/* ── Activity chips ──────────────────────────────────────── */}
          <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-1 px-1"
                    data-testid="commute-activity-row">
            {ACTIVITIES.map(({ id, label, Icon, hint }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActivity(id)}
                data-testid={`commute-activity-${id}`}
                className={[
                  "flex-shrink-0 flex items-center gap-2 px-3.5 py-2 rounded-full",
                  "border transition-all text-sm font-medium",
                  activity === id
                    ? "bg-accent-electric/15 border-accent-electric text-accent-electric"
                    : "bg-white/[0.03] border-white/[0.06] text-text-secondary hover:text-text-primary",
                ].join(" ")}>
                <Icon size={15} />
                <span>{label}</span>
                <span className="text-[10px] font-mono uppercase tracking-wider opacity-60">
                  · {hint}
                </span>
              </button>
            ))}
          </div>

          {/* ── Destination search ──────────────────────────────────── */}
          <Card className="p-3">
            <div className="flex items-center gap-2 text-xs font-mono uppercase
                                    tracking-widest text-text-secondary mb-2">
              <MapPin size={14} className="text-accent-electric" />
              <span>Where to?</span>
            </div>
            <PlacesAutocompleteInput
              onPick={handleDestinationPicked}
              disabled={loading} />
            <div className="mt-2 text-[11px] font-mono uppercase tracking-widest
                                    text-text-secondary/70 flex items-center gap-1.5">
              <Navigation size={11} />
              From: {origin?.address || "Current location"}
            </div>
          </Card>

          {/* ── Loading / error state ───────────────────────────────── */}
          {loading && (
            <Card className="p-4 flex items-center gap-3" data-testid="commute-loading">
              <Loader2 size={16} className="animate-spin text-accent-electric" />
              <span className="text-sm text-text-secondary">
                Building your route + finding offers…
              </span>
            </Card>
          )}
          {error && !loading && (
            <Card className="p-4 border-red-500/40" data-testid="commute-error">
              <div className="text-red-400 text-sm font-mono">
                {String(error).slice(0, 220)}
              </div>
            </Card>
          )}

          {/* ── Session — Route summary + map + offers ──────────────── */}
          {session && (
            <>
              <RouteSummary session={session} />
              <div data-testid="commute-map-wrapper"
                    className="rounded-token-card overflow-hidden border
                                        border-white/[0.06] h-[380px] relative">
                <Map
                  defaultCenter={mapCenter}
                  defaultZoom={12}
                  mapId="bigfm-commute-map"
                  disableDefaultUI={false}
                  gestureHandling="greedy"
                  colorScheme="DARK">
                  <AdvancedMarker
                    position={{ lat: session.origin.lat, lng: session.origin.lng }}>
                    <div className="commute-marker commute-marker-origin" />
                  </AdvancedMarker>
                  <AdvancedMarker
                    position={{ lat: session.destination.lat,
                                    lng: session.destination.lng }}>
                    <div className="commute-marker commute-marker-dest" />
                  </AdvancedMarker>
                  {(session.matched_offers || []).slice(0, 8).map((o) => (
                    o.business_lat && o.business_lng ? (
                      <AdvancedMarker
                        key={o.offer_id}
                        position={{ lat: o.business_lat, lng: o.business_lng }}>
                        <div className="commute-marker commute-marker-offer">%</div>
                      </AdvancedMarker>
                    ) : null
                  ))}
                  <RoutePolyline points={polyPoints} />
                  <FitBounds points={polyPoints} />
                </Map>
              </div>

              <OffersList
                offers={session.matched_offers || []}
                onSave={handleSaveCoupon}
                savingId={savingOfferId} />
            </>
          )}

          {/* ── Empty state (no session yet) ─────────────────────────── */}
          {!session && !loading && (
            <Card className="p-6 text-center" data-testid="commute-empty">
              <MapPin size={28} className="text-accent-electric mx-auto mb-3" />
              <div className="text-sm font-medium mb-1">Pick a destination to start</div>
              <div className="text-xs text-text-secondary">
                We&apos;ll build a real-time route, check traffic, and match{" "}
                <span className="text-accent-electric">{activity}</span>{" "}
                offers along the way.
              </div>
            </Card>
          )}
        </div>
      </div>
    </APIProvider>
  );
}

// ─── Places Autocomplete input (uses NEW PlaceAutocompleteElement API,
//      which is the only Autocomplete surface available to Google Maps
//      customers who created keys after March 1st, 2025).
function PlacesAutocompleteInput({ onPick, disabled }) {
  const placesLib = useMapsLibrary("places");
  const containerRef = useRef(null);
  const elRef = useRef(null);

  useEffect(() => {
    if (!placesLib || !containerRef.current) return;
    if (elRef.current) return;  // already mounted
    let paEl;
    try {
      paEl = new placesLib.PlaceAutocompleteElement({
        // Bias predictions toward the UAE (Dubai) area — user can still
        // pick anywhere globally.  50 km radius around Dubai centre.
        locationBias: {
          center: { lat: 25.15, lng: 55.25 },
          radius: 50000,
        },
      });
    } catch (err) {
      // Older API path (shouldn't hit — new customers only get this class)
      console.warn("PlaceAutocompleteElement unavailable:", err);
      return;
    }
    paEl.setAttribute("placeholder", "Destination address or place");
    paEl.style.width = "100%";
    paEl.style.display = "block";
    // The internal input inherits from the container — we style the
    // container.  The web component reads a `--gmpx-color-*` set of CSS
    // custom properties for theming.
    containerRef.current.appendChild(paEl);
    elRef.current = paEl;
    // (Optional) — testid attribute for automation
    paEl.setAttribute("data-testid", "commute-destination-input");

    const onSelect = async (event) => {
      try {
        // v1: event has `placePrediction`; older beta had `place`.
        const pred = event.placePrediction || event.detail?.placePrediction;
        if (!pred) return;
        const place = pred.toPlace();
        await place.fetchFields({
          fields: ["displayName", "formattedAddress", "location", "id"],
        });
        const loc = place.location;
        if (!loc) return;
        onPick({
          lat: typeof loc.lat === "function" ? loc.lat() : loc.lat,
          lng: typeof loc.lng === "function" ? loc.lng() : loc.lng,
          address: place.formattedAddress
                        || (place.displayName && (place.displayName.text || place.displayName))
                        || null,
          place_id: place.id,
        });
      } catch (err) {
        console.warn("place select error:", err);
      }
    };
    paEl.addEventListener("gmp-select", onSelect);
    return () => {
      try {
        paEl.removeEventListener("gmp-select", onSelect);
        if (paEl.parentNode) paEl.parentNode.removeChild(paEl);
      } catch { /* ignore */ }
      elRef.current = null;
    };
  }, [placesLib, onPick]);

  return (
    <div
      className={[
        "commute-place-autocomplete relative rounded-token-input",
        "bg-white/[0.04] border border-white/[0.06] px-3 py-1",
        "focus-within:border-accent-electric",
        disabled ? "opacity-50 pointer-events-none" : "",
      ].join(" ")}
      data-testid="commute-destination-input-wrap">
      <div ref={containerRef} className="w-full" />
      {!placesLib && (
        <div className="text-[11px] text-text-secondary/70 py-2 pl-1">
          <Search size={13} className="inline mr-1.5" />
          Loading Google Places…
        </div>
      )}
    </div>
  );
}

// ─── Route summary strip ─────────────────────────────────────────────
function RouteSummary({ session }) {
  const eta = session.route?.eta_seconds || 0;
  const km = ((session.route?.distance_meters || 0) / 1000).toFixed(1);
  const mins = Math.round(eta / 60);
  const traffic = session.route?.traffic_status || "unknown";
  const trafficTone = { light: "text-emerald-400", moderate: "text-amber-400",
                                heavy: "text-red-400", unknown: "text-text-secondary" }[traffic];
  const weather = session.weather;
  return (
    <Card className="p-4" data-testid="commute-route-summary">
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest
                                    text-text-secondary">ETA</div>
          <div className="text-2xl font-display font-bold tabular-nums"
                    data-testid="commute-eta">{mins} min</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest
                                    text-text-secondary">Distance</div>
          <div className="text-2xl font-display font-bold tabular-nums"
                    data-testid="commute-distance">{km} km</div>
        </div>
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest
                                    text-text-secondary">Traffic</div>
          <div className={`text-2xl font-display font-bold capitalize ${trafficTone}`}
                    data-testid="commute-traffic">{traffic}</div>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-white/[0.06]
                              flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5 text-xs text-text-secondary"
                  data-testid="commute-offer-count">
          <Sparkles size={13} className="text-accent-electric" />
          {(session.matched_offers || []).length} offers along your route
        </div>
        <div className="flex items-center gap-1.5 text-xs text-text-secondary">
          <Gauge size={13} />
          <span className="capitalize">{session.activity} mode</span>
        </div>
        {weather?.condition && (
          <div className="flex items-center gap-1.5 text-xs text-text-secondary"
                    data-testid="commute-weather-chip">
            <Cloud size={13} />
            <span className="capitalize">{String(weather.condition).toLowerCase()}</span>
            {typeof weather.temperature_c === "number" && (
              <span className="tabular-nums">
                · {Math.round(weather.temperature_c)}°C
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ─── Route polyline overlay ──────────────────────────────────────────
function RoutePolyline({ points }) {
  const map = useMap();
  const polyRef = useRef(null);
  useEffect(() => {
    if (!map || !window.google?.maps || !points?.length) return;
    if (polyRef.current) polyRef.current.setMap(null);
    polyRef.current = new window.google.maps.Polyline({
      path: points,
      strokeColor: "#00D4FF",
      strokeOpacity: 0.9,
      strokeWeight: 5,
      map,
    });
    return () => { if (polyRef.current) polyRef.current.setMap(null); };
  }, [map, points]);
  return null;
}

// ─── Fit map bounds to include the whole route ───────────────────────
function FitBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (!map || !window.google?.maps || !points?.length) return;
    const bounds = new window.google.maps.LatLngBounds();
    points.forEach((p) => bounds.extend(p));
    map.fitBounds(bounds, 60);
  }, [map, points]);
  return null;
}

// ─── Offers list ─────────────────────────────────────────────────────
function OffersList({ offers, onSave, savingId }) {
  if (!offers.length) {
    return (
      <Card className="p-4 text-center" data-testid="commute-offers-empty">
        <div className="text-sm text-text-secondary">
          No matching offers found along this route yet.
        </div>
        <div className="text-[11px] font-mono uppercase tracking-widest
                                text-text-secondary/60 mt-1">
          Try a different activity or a longer route.
        </div>
      </Card>
    );
  }
  return (
    <div className="space-y-2" data-testid="commute-offers-list">
      {offers.map((o) => (
        <Card key={o.offer_id} className="p-4"
                  data-testid={`commute-offer-card-${o.offer_id}`}>
          <div className="flex items-start gap-3">
            <div className="w-11 h-11 rounded-token-card
                                    bg-accent-electric/15 flex items-center justify-center
                                    flex-shrink-0">
              <Sparkles size={18} className="text-accent-electric" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-display font-bold text-sm truncate">
                    {o.title || "Offer"}
                  </div>
                  <div className="text-[11px] font-mono uppercase tracking-widest
                                            text-text-secondary/80 truncate mt-0.5">
                    {o.business_name}
                    {o.business_category && ` · ${o.business_category}`}
                  </div>
                </div>
                {typeof o.discount_percent === "number" && (
                  <div className="text-lg font-display font-black
                                            text-accent-electric flex-shrink-0">
                    -{o.discount_percent}%
                  </div>
                )}
              </div>
              {o.description && (
                <p className="text-xs text-text-secondary mt-1.5 line-clamp-2">
                  {o.description}
                </p>
              )}
              <div className="flex items-center gap-3 mt-2 text-[10px]
                                        font-mono uppercase tracking-widest
                                        text-text-secondary">
                {typeof o.distance_from_route_m === "number" && (
                  <span>{Math.round(o.distance_from_route_m)} m off route</span>
                )}
                {typeof o.extra_drive_time_s === "number" && o.extra_drive_time_s > 0 && (
                  <span>+{o.extra_drive_time_s}s detour</span>
                )}
              </div>
            </div>
          </div>
          <div className="mt-3 flex justify-end">
            {o.saved ? (
              <div className="flex items-center gap-1.5 text-xs
                                        text-emerald-400 font-mono uppercase tracking-widest"
                        data-testid={`commute-offer-saved-${o.offer_id}`}>
                <CheckCircle2 size={14} /> Saved to wallet
              </div>
            ) : (
              <Button
                onClick={() => onSave(o.offer_id)}
                disabled={savingId === o.offer_id}
                variant="primary"
                size="sm"
                data-testid={`commute-offer-save-btn-${o.offer_id}`}>
                {savingId === o.offer_id ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Save size={13} />
                )}
                <span>Save coupon</span>
              </Button>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
