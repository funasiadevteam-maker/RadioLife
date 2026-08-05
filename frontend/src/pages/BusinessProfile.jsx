// Phase MER.4 — Shoppable Business Profile.
// Public route: /business/{slug_or_id}
//
// Hero + about + photo carousel + offers grid + gift-card grid +
// prepaid-meal grid + locations map + sticky CTA rail.
// Both design variants.
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Heart, Bookmark, MapPin, Phone, Globe, ShieldCheck, Loader2,
  CreditCard, UtensilsCrossed, Tag, Sparkles, ChevronLeft,
  ChevronRight, Trophy, Zap, Radio, Calendar, X, Navigation,
  Play,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
// Phase FUN.1 — Flagship stations recommendation strip.
import FlagshipStrip from "@/components/FlagshipStrip";
import SafeImage from "@/components/SafeImage";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FMT = (n, ccy = "AED") => `${(Number(n || 0) / 100).toFixed(2)} ${ccy}`;

export default function BusinessProfile() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { slug } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [comingSoon, setComingSoon] = useState(null);
  const [photoIdx, setPhotoIdx] = useState(0);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/business/${slug}/profile`,
                                                                        { withCredentials: true });
      setProfile(data);
    } catch (e) {
      if (e?.response?.status === 404) setErr("not_found");
      else { setErr("load"); toast.error(`Load failed: ${e.message}`); }
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [slug]);

  const bgClass = light
    ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
    : "min-h-screen bg-slate-950 text-slate-100";

  if (loading) return (
    <div className={`${bgClass} flex items-center justify-center`}
              data-testid="business-profile-loading">
      <Loader2 className="animate-spin" size={30}/>
    </div>);

  if (err === "not_found") return (
    <div className={`${bgClass} flex items-center justify-center p-6`}
              data-testid="business-profile-not-found">
      <div className={`max-w-sm rounded-3xl p-6 text-center ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"}`}>
        <h1 className={`text-2xl font-black ${
          light ? "text-slate-900" : "text-white"}`}>Business not found</h1>
        <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
          The link you followed may be broken or this business has been removed.
        </p>
        <Link to="/" className="mt-4 inline-block text-purple-600 hover:underline">
          Back to home
        </Link>
      </div>
    </div>);

  const m = profile?.merchant || {};
  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const logoUrl = m.logo_url
    ? (m.logo_url.startsWith("http") ? m.logo_url : backendBase + m.logo_url)
    : null;
  const photos = m.photos || [];
  const primaryLocation = (profile?.locations || []).find(l => l.is_primary);
  const generalToken = profile?.payment_links_summary?.general_payment_token;
  const hasGeneralLink = profile?.payment_links_summary?.has_active_general_link;
  const activity = profile?.activity_signals || {};

  return (
    <div className={bgClass}
              data-testid="business-profile-page"
              data-slug={slug}
              data-variant={variant}>
      {/* ── HERO ─────────────────────────────────────────────── */}
      <div className="max-w-5xl mx-auto px-5 pt-8 pb-24 sm:pb-8">
        <div className={`rounded-3xl overflow-hidden ${
          light ? "bg-white shadow-md" : "bg-slate-900 border border-slate-800"}`}
              data-testid="business-profile-hero">

          {/* Photo carousel */}
          {photos.length > 0 && (
            <div className="relative h-64 sm:h-80 bg-slate-900"
                        data-testid="business-profile-carousel">
              <SafeImage src={photos[photoIdx].url}
                                        alt={photos[photoIdx].caption || m.name}
                                        fallbackKind="business"
                                        fallbackText={m.name || ""}
                                        className="w-full h-full object-cover"/>
              {photos.length > 1 && (
                <>
                  <button type="button"
                                onClick={() => setPhotoIdx((photoIdx - 1 + photos.length) % photos.length)}
                                data-testid="business-profile-carousel-prev"
                                className="absolute top-1/2 left-3 -translate-y-1/2 w-9 h-9 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70">
                    <ChevronLeft size={18}/>
                  </button>
                  <button type="button"
                                onClick={() => setPhotoIdx((photoIdx + 1) % photos.length)}
                                data-testid="business-profile-carousel-next"
                                className="absolute top-1/2 right-3 -translate-y-1/2 w-9 h-9 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70">
                    <ChevronRight size={18}/>
                  </button>
                  <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5">
                    {photos.map((_, i) => (
                      <button key={i} type="button"
                                    onClick={() => setPhotoIdx(i)}
                                    className={`w-2 h-2 rounded-full ${
                                      i === photoIdx ? "bg-white" : "bg-white/40"}`}/>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          <div className="p-6 sm:p-8">
            <div className="flex items-start gap-4">
              {logoUrl ? (
                <SafeImage src={logoUrl} alt={m.name || ""}
                                          fallbackKind="business"
                                          fallbackText={m.name || ""}
                                          className="w-20 h-20 rounded-2xl object-cover flex-shrink-0"/>
              ) : (
                <div className={`w-20 h-20 rounded-2xl flex-shrink-0 ${
                  light ? "bg-gradient-to-br from-purple-100 to-pink-100"
                          : "bg-gradient-to-br from-cyan-500/20 to-purple-500/20"}`}/>
              )}
              <div className="min-w-0 flex-1">
                {m.category && (
                  <div className={`inline-block text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full mb-1 ${
                    light ? "bg-purple-100 text-purple-700"
                            : "bg-cyan-500/15 text-cyan-300"}`}>
                    {m.category}
                  </div>
                )}
                <h1 className={`text-2xl sm:text-3xl font-black tracking-tight ${
                  light ? "text-slate-900" : "text-white"}`}
                        data-testid="business-profile-name">{m.name}</h1>
                {m.verified && (
                  <div className={`mt-1 inline-flex items-center gap-1 text-xs font-black ${
                    light ? "text-emerald-700" : "text-emerald-400"}`}
                        data-testid="business-profile-verified-badge">
                    <ShieldCheck size={14}/> Verified
                  </div>
                )}
              </div>
              <FollowSaveButtons profile={profile} light={light}
                                                    onChange={load} user={user}/>
            </div>

            {m.description && (
              <p className={`mt-5 text-sm leading-relaxed ${
                light ? "text-slate-700" : "text-slate-300"}`}
                  data-testid="business-profile-description">
                {m.description}
              </p>
            )}

            <div className={`mt-4 flex flex-wrap gap-3 text-xs ${
              light ? "text-slate-600" : "text-slate-400"}`}>
              {m.phone && (
                <a href={`tel:${m.phone}`} className="inline-flex items-center gap-1 hover:underline"
                      data-testid="business-profile-phone">
                  <Phone size={12}/> {m.phone}
                </a>
              )}
              {m.website && (
                <a href={m.website} target="_blank" rel="noreferrer"
                      className="inline-flex items-center gap-1 hover:underline"
                      data-testid="business-profile-website">
                  <Globe size={12}/> {m.website.replace(/^https?:\/\//, "")}
                </a>
              )}
            </div>
          </div>
        </div>

        {/* ── OFFERS ────────────────────────────────────────── */}
        {profile?.offers?.length > 0 && (
          <Section title="Available Offers" icon={Tag} light={light}
                          testid="business-profile-section-offers">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profile.offers.map(o => (
                <OfferCard key={o.offer_id} offer={o} merchantId={m.id}
                                        light={light} />
              ))}
            </div>
          </Section>
        )}

        {/* ── GIFT CARDS ────────────────────────────────────── */}
        {profile?.gift_card_skus?.length > 0 && (
          <Section title="Gift Cards" icon={CreditCard} light={light}
                          testid="business-profile-section-giftcards">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profile.gift_card_skus.map(sku => (
                <GiftCardCard key={sku.sku_id} sku={sku}
                                              merchantId={m.id} verified={m.verified}
                                              light={light}
                                              onDisabled={() => setComingSoon(
                                                "This business hasn't finished payment activation yet.")}/>
              ))}
            </div>
          </Section>
        )}

        {/* ── PREPAID MEALS ─────────────────────────────────── */}
        {profile?.prepaid_meal_skus?.length > 0 && (
          <Section title="Meal Packs" icon={UtensilsCrossed} light={light}
                          testid="business-profile-section-meals">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {profile.prepaid_meal_skus.map(sku => (
                <MealPackCard key={sku.sku_id} sku={sku}
                                                merchantId={m.id} verified={m.verified}
                                                light={light}
                                                onDisabled={() => setComingSoon(
                                                  "This business hasn't finished payment activation yet.")}/>
              ))}
            </div>
          </Section>
        )}

        {/* ── LOCATIONS ─────────────────────────────────────── */}
        {profile?.locations?.length > 0 && (
          <Section title="Locations" icon={MapPin} light={light}
                          testid="business-profile-section-locations">
            <div className="space-y-3">
              {profile.locations.map((l, i) => (
                <LocationRow key={i} location={l} light={light}
                                          onDirections={() => {
                                            if (l.lat && l.lng) {
                                              window.open(`https://www.google.com/maps/search/?api=1&query=${l.lat},${l.lng}`);
                                            } else {
                                              window.open(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(l.address || "")}`);
                                            }
                                          }}/>
              ))}
            </div>
          </Section>
        )}

        {/* ── TRACK 3 STUBS ─────────────────────────────────── */}
        <Section title="More on RadioLife" icon={Sparkles} light={light}
                        testid="business-profile-section-track3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Track3Stub label="Play & Win" Icon={Trophy}
                                  active={activity.play_and_win_active} light={light}
                                  testid="business-profile-track3-play"
                                  onClick={() => {
                                    if (activity.play_and_win_active && activity.active_game_campaign_id) {
                                      window.location.href = `/play/${activity.active_game_campaign_id}`;
                                    } else {
                                      setComingSoon("Play & Win launches in Track 3.");
                                    }
                                  }}/>
            <Track3Stub label="Predict & Win" Icon={Zap}
                                  active={activity.predict_and_win_active} light={light}
                                  testid="business-profile-track3-predict"
                                  onClick={() => setComingSoon("Predict & Win launches in Track 3.")}/>
            <Track3Stub label="Live Trivia" Icon={Radio}
                                  active={activity.live_trivia_active} light={light}
                                  testid="business-profile-track3-trivia"
                                  onClick={() => setComingSoon("Live Trivia launches in Track 3.")}/>
            <Track3Stub label="Book Appointment" Icon={Calendar}
                                  active={false} light={light}
                                  testid="business-profile-track3-book"
                                  onClick={() => setComingSoon("Appointment booking coming soon.")}/>
            <Track3Stub label="Reserve Table" Icon={UtensilsCrossed}
                                  active={false} light={light}
                                  testid="business-profile-track3-reserve"
                                  onClick={() => setComingSoon("Table reservations coming soon.")}/>
            <Track3Stub label="Watch Live" Icon={Play}
                                  active={false} light={light}
                                  testid="business-profile-track3-live"
                                  onClick={() => setComingSoon("Live station broadcasts coming soon.")}/>
          </div>
        </Section>

        {/* Phase FUN.1 — Recommended flagship stations, matched on city + language.
              Only renders when the API returns > 0 items (component self-guards). */}
        <div className="mt-8" data-testid="business-profile-section-flagship">
          <FlagshipStrip
            matchesCity={(profile?.locations?.[0]?.city) || null}
            limit={4}
            title="Recommended Stations"
            testId="business-profile-flagship-strip"
            light={light} />
        </div>

        {/* Stats */}
        <div className={`mt-6 rounded-2xl p-4 flex items-center gap-4 ${
          light ? "bg-white border border-slate-100"
                  : "bg-slate-900 border border-slate-800"}`}
              data-testid="business-profile-stats">
          <Sparkles size={18} color={light ? "#a855f7" : "#00d4ff"}/>
          <div className={`text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
            <b>{profile?.stats?.total_transactions_month || 0}</b> transactions this month
          </div>
        </div>
      </div>

      {/* ── STICKY CTA RAIL ────────────────────────────────── */}
      <StickyCTA light={light} profile={profile}
                            generalToken={generalToken}
                            hasGeneralLink={hasGeneralLink && m.verified}
                            primaryLocation={primaryLocation}
                            onComingSoon={setComingSoon}
                            onDirections={() => {
                              if (primaryLocation?.lat && primaryLocation?.lng) {
                                window.open(`https://www.google.com/maps/search/?api=1&query=${primaryLocation.lat},${primaryLocation.lng}`);
                              }
                            }}/>

      {comingSoon && (
        <ComingSoonModal light={light} text={comingSoon}
                                            onClose={() => setComingSoon(null)}/>
      )}
    </div>
  );
}


// ── Sub-components ─────────────────────────────────────────────

function Section({ title, icon: Icon, light, testid, children }) {
  return (
    <div className="mt-6" data-testid={testid}>
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} color={light ? "#a855f7" : "#00d4ff"}/>
        <h2 className={`text-lg font-black ${
          light ? "text-slate-900" : "text-white"}`}>{title}</h2>
      </div>
      {children}
    </div>
  );
}

function FollowSaveButtons({ profile, light, onChange, user }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const m = profile.merchant;

  const toggleFollow = async () => {
    if (!user) { navigate(`/login?next=/business/${m.slug || m.id}`); return; }
    setBusy(true);
    try {
      const url = m.is_followed ? "unfollow" : "follow";
      await axios.post(`${API}/business/${m.id}/${url}`, null,
                                        { withCredentials: true });
      onChange();
      toast.success(m.is_followed ? "Unfollowed" : `Following ${m.name}`);
    } catch (e) { toast.error(`Failed: ${e.message}`); }
    finally { setBusy(false); }
  };

  const toggleSave = async () => {
    if (!user) { navigate(`/login?next=/business/${m.slug || m.id}`); return; }
    setBusy(true);
    try {
      const url = m.is_saved ? "unsave" : "save";
      await axios.post(`${API}/business/${m.id}/${url}`, null,
                                        { withCredentials: true });
      onChange();
      toast.success(m.is_saved ? "Removed from saved" : "Saved");
    } catch (e) { toast.error(`Failed: ${e.message}`); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex gap-2">
      <button type="button" onClick={toggleFollow} disabled={busy}
                    data-testid="business-profile-follow-btn"
                    data-state={m.is_followed ? "on" : "off"}
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      m.is_followed
                        ? (light ? "bg-rose-500 text-white"
                                        : "bg-rose-500 text-white")
                        : (light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                        : "bg-slate-800 text-slate-300 hover:bg-slate-700")}`}
                    aria-label={m.is_followed ? "Unfollow" : "Follow"}>
        <Heart size={16} fill={m.is_followed ? "currentColor" : "none"}/>
      </button>
      <button type="button" onClick={toggleSave} disabled={busy}
                    data-testid="business-profile-save-btn"
                    data-state={m.is_saved ? "on" : "off"}
                    className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      m.is_saved
                        ? (light ? "bg-amber-500 text-white"
                                        : "bg-amber-500 text-white")
                        : (light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                        : "bg-slate-800 text-slate-300 hover:bg-slate-700")}`}
                    aria-label={m.is_saved ? "Unsave" : "Save"}>
        <Bookmark size={16} fill={m.is_saved ? "currentColor" : "none"}/>
      </button>
    </div>
  );
}

function OfferCard({ offer, merchantId, light }) {
  return (
    <div className={`rounded-3xl p-5 ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"}`}
              data-testid={`business-profile-offer-${offer.offer_id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-emerald-600" : "text-emerald-400"}`}>Offer</div>
          <h3 className={`mt-1 text-base font-black ${
            light ? "text-slate-900" : "text-white"}`}>{offer.title}</h3>
          {offer.description && (
            <p className={`text-xs mt-1 ${
              light ? "text-slate-600" : "text-slate-500"}`}>
              {offer.description}
            </p>
          )}
        </div>
        <div className={`text-3xl font-black ${
          light ? "text-emerald-600" : "text-emerald-400"}`}>
          {offer.discount_percent ? `${offer.discount_percent}%` : ""}
        </div>
      </div>
    </div>
  );
}

function GiftCardCard({ sku, merchantId, verified, light, onDisabled }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [selectedDenom, setSelectedDenom] = useState(sku.denominations?.[0]);

  const buy = async () => {
    if (!verified) { onDisabled(); return; }
    // Consumers can't create payment links; the merchant already created
    // link_type=gift_card links via MER.3.  Look one up for this SKU+denom.
    setBusy(true);
    try {
      const { data } = await axios.get(
        `${API}/business/${merchantId}/gift-card-purchase-link?sku_id=${sku.sku_id}&amount_cents=${selectedDenom}`,
        { withCredentials: true });
      if (data.token) navigate(`/pay/${data.token}`);
      else toast.error("No purchase link available. Ask the merchant to enable this gift card.");
    } catch (e) {
      if (e?.response?.status === 404) {
        toast.error("This gift card denomination isn't set up yet.");
      } else toast.error(`Failed: ${e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <div className={`rounded-3xl p-5 ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"}`}
              data-testid={`business-profile-gc-${sku.sku_id}`}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${
        light ? "text-purple-600" : "text-cyan-400"}`}>Gift Card</div>
      <h3 className={`mt-1 text-base font-black ${
        light ? "text-slate-900" : "text-white"}`}>{sku.name}</h3>
      <div className="mt-3 flex flex-wrap gap-1">
        {(sku.denominations || []).map(d => (
          <button key={d} type="button"
                        onClick={() => setSelectedDenom(d)}
                        data-testid={`business-profile-gc-${sku.sku_id}-denom-${d}`}
                        data-selected={selectedDenom === d}
                        className={`h-8 rounded-full px-3 text-xs font-bold ${
                          selectedDenom === d
                            ? (light ? "bg-purple-600 text-white"
                                            : "bg-cyan-500 text-slate-950")
                            : (light ? "bg-slate-100 text-slate-700"
                                            : "bg-slate-800 text-slate-300")}`}>
            {FMT(d, sku.currency)}
          </button>
        ))}
      </div>
      <button type="button" onClick={buy} disabled={busy}
                    data-testid={`business-profile-gc-${sku.sku_id}-buy`}
                    className={`mt-4 w-full h-10 rounded-full text-xs font-black ${
                      verified
                        ? "text-white"
                        : (light ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                                        : "bg-slate-800 text-slate-500 cursor-not-allowed")}`}
                    style={verified
                                        ? {background:"linear-gradient(135deg,#a855f7,#ec4899)"}
                                        : undefined}>
        {busy ? "Loading…" : `Buy ${FMT(selectedDenom, sku.currency)}`}
      </button>
    </div>
  );
}

function MealPackCard({ sku, merchantId, verified, light, onDisabled }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const buy = async () => {
    if (!verified) { onDisabled(); return; }
    setBusy(true);
    try {
      const { data } = await axios.get(
        `${API}/business/${merchantId}/meal-pack-purchase-link?sku_id=${sku.sku_id}`,
        { withCredentials: true });
      if (data.token) navigate(`/pay/${data.token}`);
      else toast.error("No purchase link available.");
    } catch (e) {
      if (e?.response?.status === 404) toast.error("This meal pack isn't set up yet.");
      else toast.error(`Failed: ${e.message}`);
    } finally { setBusy(false); }
  };

  const perMeal = sku.per_meal_value_cents || 0;
  const totalIfSeparate = (sku.meal_count || 0) * perMeal;
  const savings = totalIfSeparate - (sku.total_price_cents || 0);
  const savingsPct = totalIfSeparate ? Math.round(savings / totalIfSeparate * 100) : 0;

  return (
    <div className={`rounded-3xl p-5 ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"}`}
              data-testid={`business-profile-meal-${sku.sku_id}`}>
      <div className={`text-[10px] font-bold uppercase tracking-widest ${
        light ? "text-orange-600" : "text-amber-400"}`}>Meal Pack</div>
      <h3 className={`mt-1 text-base font-black ${
        light ? "text-slate-900" : "text-white"}`}>{sku.name}</h3>
      <div className={`mt-2 text-2xl font-black ${
        light ? "text-slate-900" : "text-white"}`}>
        {sku.meal_count} meals
        <span className={`ml-2 text-lg ${
          light ? "text-purple-600" : "text-cyan-400"}`}>
          for {FMT(sku.total_price_cents, sku.currency)}
        </span>
      </div>
      {savingsPct > 0 && (
        <div className={`text-[10px] font-black uppercase mt-1 ${
          light ? "text-emerald-700" : "text-emerald-300"}`}>
          Save {savingsPct}%
        </div>
      )}
      <button type="button" onClick={buy} disabled={busy}
                    data-testid={`business-profile-meal-${sku.sku_id}-buy`}
                    className={`mt-4 w-full h-10 rounded-full text-xs font-black ${
                      verified
                        ? "text-white"
                        : (light ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                                        : "bg-slate-800 text-slate-500 cursor-not-allowed")}`}
                    style={verified
                                        ? {background:"linear-gradient(135deg,#a855f7,#ec4899)"}
                                        : undefined}>
        {busy ? "Loading…" : `Buy pack`}
      </button>
    </div>
  );
}

function LocationRow({ location, light, onDirections }) {
  return (
    <div className={`rounded-2xl p-4 flex items-start gap-3 ${
      light ? "bg-white border border-slate-100 shadow-sm"
              : "bg-slate-900 border border-slate-800"}`}
              data-testid="business-profile-location-row">
      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
        light ? "bg-purple-100 text-purple-700"
                : "bg-cyan-500/15 text-cyan-300"}`}>
        <MapPin size={18}/>
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-black ${
          light ? "text-slate-900" : "text-white"}`}>{location.address}</div>
        {(location.city || location.country) && (
          <div className={`text-xs ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            {location.city}{location.city && location.country && ", "}{location.country}
          </div>
        )}
        {location.phone && (
          <div className={`text-xs mt-1 ${
            light ? "text-slate-500" : "text-slate-500"}`}>
            {location.phone}
          </div>
        )}
      </div>
      <button type="button" onClick={onDirections}
                    data-testid="business-profile-directions-btn"
                    className={`px-3 h-9 rounded-full text-xs font-bold inline-flex items-center gap-1 ${
                      light ? "bg-slate-100 text-slate-800 hover:bg-slate-200"
                              : "bg-slate-800 text-slate-200 hover:bg-slate-700"}`}>
        <Navigation size={12}/> Directions
      </button>
    </div>
  );
}

function Track3Stub({ label, Icon, active, light, testid, onClick }) {
  return (
    <button type="button" onClick={onClick}
                  data-testid={testid}
                  data-active={active}
                  className={`rounded-2xl p-4 text-left transition-all ${
                    active
                      ? (light ? "bg-purple-100 border border-purple-200"
                                    : "bg-cyan-500/15 border border-cyan-500/30")
                      : (light ? "bg-white/70 border border-slate-100 opacity-60"
                                    : "bg-slate-900/50 border border-slate-800 opacity-50")}`}>
      <Icon size={20} color={active
                                                  ? (light ? "#a855f7" : "#00d4ff")
                                                  : (light ? "#94a3b8" : "#64748b")}/>
      <div className={`mt-2 text-xs font-black ${
        light ? "text-slate-800" : "text-slate-200"}`}>{label}</div>
      <div className={`text-[9px] font-bold uppercase tracking-widest mt-1 ${
        active
          ? (light ? "text-purple-600" : "text-cyan-400")
          : (light ? "text-slate-400" : "text-slate-500")}`}>
        {active ? "Live" : "Coming soon"}
      </div>
    </button>
  );
}

function StickyCTA({ light, profile, generalToken, hasGeneralLink,
                                        primaryLocation, onComingSoon, onDirections }) {
  const navigate = useNavigate();
  return (
    <div className={`fixed bottom-0 inset-x-0 z-40 border-t px-4 py-3 sm:hidden ${
      light ? "bg-white/95 backdrop-blur border-slate-200"
              : "bg-slate-900/95 backdrop-blur border-slate-800"}`}
              data-testid="business-profile-sticky-cta">
      <div className="flex gap-2 max-w-lg mx-auto">
        <button type="button"
                      onClick={() => hasGeneralLink
                                                ? navigate(`/pay/${generalToken}`)
                                                : onComingSoon("This business doesn't accept in-app payments yet.")}
                      data-testid="business-profile-cta-pay"
                      className={`flex-1 h-11 rounded-full text-xs font-black ${
                        hasGeneralLink
                          ? "text-white"
                          : (light ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                                          : "bg-slate-800 text-slate-500")}`}
                      style={hasGeneralLink
                                          ? {background:"linear-gradient(135deg,#a855f7,#ec4899)"}
                                          : undefined}>
          Pay with App
        </button>
        {primaryLocation?.lat && (
          <button type="button" onClick={onDirections}
                        data-testid="business-profile-cta-directions"
                        className={`h-11 rounded-full px-4 text-xs font-bold ${
                          light ? "bg-slate-100 text-slate-800"
                                  : "bg-slate-800 text-slate-200"}`}>
            <Navigation size={12} className="inline mr-1"/> Directions
          </button>
        )}
      </div>
    </div>
  );
}

function ComingSoonModal({ light, text, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
              onClick={onClose}>
      <div onClick={e => e.stopPropagation()}
                data-testid="business-profile-coming-soon-modal"
                className={`w-full max-w-sm rounded-3xl p-6 text-center ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex justify-end">
          <button type="button" onClick={onClose}
                        className={light ? "text-slate-500" : "text-slate-500"}>
            <X size={18}/>
          </button>
        </div>
        <div className={`inline-flex w-14 h-14 rounded-2xl items-center justify-center mb-3 ${
          light ? "bg-purple-100 text-purple-700"
                  : "bg-cyan-500/15 text-cyan-300"}`}>
          <Sparkles size={22}/>
        </div>
        <h3 className={`text-xl font-black ${
          light ? "text-slate-900" : "text-white"}`}>Coming Soon</h3>
        <p className={`mt-2 text-sm ${
          light ? "text-slate-600" : "text-slate-400"}`}>{text}</p>
        <button type="button" onClick={onClose}
                      data-testid="business-profile-coming-soon-close"
                      className={`mt-5 w-full h-10 rounded-full text-xs font-bold ${
                        light ? "bg-slate-900 text-white"
                                : "bg-white text-slate-950"}`}>
          Got it
        </button>
      </div>
    </div>
  );
}
