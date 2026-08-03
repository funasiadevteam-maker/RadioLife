// Phase SC.2 — Merchant Self-Service Wizard (10 steps).
//
// Login-required.  Redirects `/login?next=/merchant/apply` when anonymous.
// Adapts to both design variants:
//   • legacy   → dark theme, cyan accents, sits above the legacy shell.
//   • radiolife → light theme, purple/pink gradient, sits inside the
//                            RadioLifeOverlay (its screen router routes /merchant/*).
//
// Steps: welcome → profile → locations → logo → photos → hours → terms →
//        stripe → review → status (post-submit).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, ArrowRight, Building2, Check, Coffee, Dumbbell, Film,
  Loader2, MapPin, Mic, Music, PartyPopper, Radio, Scissors,
  ShoppingBasket, Sparkles, Store, Stethoscope, Trash2, Upload,
  Utensils, Wrench, Martini, CalendarDays, Camera, Clock, ExternalLink,
  Copy, X as XIcon,
} from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { APIProvider } from "@vis.gl/react-google-maps";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const CATEGORY_ICONS = {
  Utensils, Coffee, ShoppingBasket, Store, Scissors, Stethoscope, Dumbbell,
  PartyPopper, Film, CalendarDays, Music, Martini, Radio, Mic, Wrench,
  Sparkles,
};

const STEP_LABELS = [
  { id: "welcome",    label: "Basics",              short: "1" },
  { id: "profile",    label: "Profile",              short: "2" },
  { id: "locations",label: "Locations",          short: "3" },
  { id: "logo",          label: "Logo",                  short: "4" },
  { id: "photos",      label: "Photos",              short: "5" },
  { id: "hours",        label: "Hours",                short: "6" },
  { id: "terms",        label: "Terms",                short: "7" },
  { id: "stripe",      label: "Payments",          short: "8" },
  { id: "review",      label: "Review",              short: "9" },
];


export default function MerchantApply() {
  const { user, loading: authLoading } = useAuth();
  const variant = useDesignVariant();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [merchantId, setMerchantId] = useState(
    searchParams.get("merchant_id") || null);
  const [merchant, setMerchant] = useState(null);
  const [step, setStep] = useState("welcome");
  const [busy, setBusy] = useState(false);

  const light = variant === "radiolife";

  // ─── Auth gate ────────────────────────────────────────────────
  useEffect(() => {
    if (!authLoading && !user) {
      navigate(`/login?next=${encodeURIComponent("/merchant/apply")}`,
                    { replace: true });
    }
  }, [authLoading, user, navigate]);

  // ─── Load existing draft on mount ─────────────────────────────
  const loadMerchant = useCallback(async (mid) => {
    if (!mid) return;
    try {
      const { data } = await axios.get(`${API}/merchant/${mid}`,
                                                                { withCredentials: true });
      setMerchant(data);
      // Advance UI step to the next-incomplete step from the server
      if (data.next_step && data.merchant_status === "draft") {
        // SC.3 · surface a resume toast if the merchant is resuming
        // past step 1 (draft with meaningful progress).
        if (data.next_step !== "welcome") {
          const stepLabels = {
            welcome:    "Basics",           profile:  "Business Profile",
            locations: "Locations",      logo:        "Logo",
            photos:      "Photos",              hours:      "Business Hours",
            terms:        "Commission Terms", stripe: "Stripe Setup",
            review:      "Review & Submit",
          };
          const idx = (data.wizard_steps || []).indexOf(data.next_step) + 1;
          toast.info(
            `Resuming your application at Step ${idx} · ${stepLabels[data.next_step] || data.next_step}`,
            { id: `resume-${mid}` });
        }
        setStep(data.next_step);
      } else if (data.merchant_status === "submitted"
                              || data.merchant_status === "approved"
                              || data.merchant_status === "active"
                              || data.merchant_status === "rejected"
                              || data.merchant_status === "suspended") {
        // Post-submit — send them to /merchant/status
        navigate(`/merchant/status?merchant_id=${mid}`, { replace: true });
      }
    } catch (e) {
      if (e?.response?.status === 404) {
        setMerchantId(null);
        setMerchant(null);
      } else {
        toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
      }
    }
  }, [navigate]);

  useEffect(() => {
    if (merchantId) loadMerchant(merchantId);
  }, [merchantId, loadMerchant]);

  // ─── Auto-resume: check /merchant/mine when no explicit id ────
  useEffect(() => {
    if (!user || merchantId) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/merchant/mine`,
                                                                    { withCredentials: true });
        const drafts = (data.items || []).filter(
          (m) => m.merchant_status === "draft"
                      || m.merchant_status === "stripe_onboarding_pending");
        if (drafts.length > 0) {
          setMerchantId(drafts[0].merchant_id);
        }
      } catch (_e) { /* silent — no existing draft is fine */ }
    })();
  }, [user, merchantId]);

  if (authLoading || !user) {
    return <FullscreenLoader light={light} />;
  }

  // ─── Step router ──────────────────────────────────────────────
  const stepIndex = STEP_LABELS.findIndex((s) => s.id === step);

  const advance = (nextId) => {
    if (nextId) setStep(nextId);
    else {
      const next = STEP_LABELS[stepIndex + 1];
      if (next) setStep(next.id);
    }
  };

  const back = () => {
    const prev = STEP_LABELS[stepIndex - 1];
    if (prev) setStep(prev.id);
    else navigate(-1);
  };

  const commonProps = { merchant, merchantId, setMerchantId, setMerchant,
                                        advance, back, light, busy, setBusy,
                                        loadMerchant };

  const renderStep = () => {
    switch (step) {
      case "welcome":    return <StepWelcome {...commonProps} />;
      case "profile":    return <StepProfile {...commonProps} />;
      case "locations":return <StepLocations {...commonProps} />;
      case "logo":          return <StepLogo {...commonProps} />;
      case "photos":      return <StepPhotos {...commonProps} />;
      case "hours":        return <StepHours {...commonProps} />;
      case "terms":        return <StepTerms {...commonProps} />;
      case "stripe":      return <StepStripe {...commonProps} />;
      case "review":      return <StepReview {...commonProps} />;
      default: return null;
    }
  };

  return (
    <div
      className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50 text-slate-900"
                          : "min-h-screen bg-slate-950 text-slate-100"}
      data-testid="merchant-apply-page"
      data-variant={variant}
      data-step={step}
    >
      <div className="max-w-3xl mx-auto px-5 py-8 sm:py-10">
        <div className="flex items-center justify-between mb-6">
          <button type="button" onClick={back}
                        data-testid="merchant-wizard-back"
                        className={light
                                                  ? "flex items-center gap-1.5 text-sm text-purple-700 hover:text-purple-900 font-medium"
                                                  : "flex items-center gap-1.5 text-sm text-slate-400 hover:text-cyan-400"}>
            <ArrowLeft size={16}/> Back
          </button>
          <StepPill light={light} step={step} />
        </div>
        <ProgressBar light={light} currentIdx={stepIndex} />
        <div className="mt-8">
          {renderStep()}
        </div>
      </div>
    </div>
  );
}


// ─── Shared building blocks ─────────────────────────────────────
function FullscreenLoader({ light }) {
  return (
    <div className={light ? "min-h-screen bg-white flex items-center justify-center"
                                          : "min-h-screen bg-slate-950 flex items-center justify-center"}
              data-testid="merchant-apply-loading">
      <Loader2 className="animate-spin" size={32}
                        color={light ? "#a855f7" : "#00d4ff"} />
    </div>
  );
}


function StepPill({ light, step }) {
  return (
    <div
      data-testid="merchant-wizard-step-pill"
      className={light
        ? "text-[11px] font-bold uppercase tracking-widest text-purple-700 bg-purple-100 px-3 py-1.5 rounded-full"
        : "text-[11px] font-bold uppercase tracking-widest text-cyan-400 bg-cyan-500/10 px-3 py-1.5 rounded-full"}>
      Phase SC.2 · {step}
    </div>
  );
}


function ProgressBar({ light, currentIdx }) {
  return (
    <div data-testid="merchant-wizard-progress"
              className="flex items-center gap-1.5">
      {STEP_LABELS.map((s, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        return (
          <div key={s.id} className="flex-1 flex flex-col items-center gap-1">
            <div className={`h-1.5 w-full rounded-full transition-all ${
              done ? (light ? "bg-purple-500" : "bg-cyan-400")
                    : active ? (light ? "bg-gradient-to-r from-purple-500 to-pink-500"
                                                    : "bg-cyan-500/70")
                            : (light ? "bg-slate-200" : "bg-slate-800")
            }`}/>
            <span className={`text-[10px] uppercase tracking-wide font-semibold ${
              active ? (light ? "text-purple-700" : "text-cyan-400")
                        : (light ? "text-slate-500" : "text-slate-500")
            }`}>{s.label}</span>
          </div>
        );
      })}
    </div>
  );
}


function Card({ light, children, className = "", ...props }) {
  return (
    <div className={`${light
                      ? "bg-white rounded-3xl shadow-sm border border-slate-100 p-6 sm:p-8"
                      : "bg-slate-900 rounded-2xl border border-slate-800 p-6 sm:p-8"} ${className}`}
              {...props}>
      {children}
    </div>
  );
}


function Title({ light, eyebrow, title, sub }) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
          light ? "text-purple-600" : "text-cyan-400"
        }`}>{eyebrow}</div>
      )}
      <h1 className={`text-3xl sm:text-4xl font-extrabold tracking-tight ${
        light ? "text-slate-900" : "text-white"
      }`}>{title}</h1>
      {sub && (
        <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
          {sub}
        </p>
      )}
    </div>
  );
}


function PrimaryBtn({ light, children, className = "", disabled, ...props }) {
  return (
    <button type="button" disabled={disabled}
                className={`inline-flex items-center justify-center gap-2 font-semibold rounded-full px-6 h-11 text-sm transition-all disabled:opacity-50 disabled:pointer-events-none ${
                  light
                    ? "text-white shadow-lg shadow-purple-500/25 hover:shadow-xl active:scale-[0.98]"
                    : "text-slate-950 bg-gradient-to-r from-cyan-400 to-indigo-500 hover:brightness-110"
                } ${className}`}
                style={light
                  ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" }
                  : undefined}
                {...props}>
      {children}
    </button>
  );
}


function GhostBtn({ light, children, className = "", ...props }) {
  return (
    <button type="button"
                className={`inline-flex items-center justify-center gap-2 font-semibold rounded-full px-5 h-11 text-sm transition-all disabled:opacity-50 ${
                  light
                    ? "bg-white text-purple-700 border border-purple-200 hover:bg-purple-50"
                    : "bg-slate-800 text-slate-200 border border-slate-700 hover:border-cyan-500/50"
                } ${className}`}
                {...props}>
      {children}
    </button>
  );
}


function Input({ light, error, className = "", ...props }) {
  return (
    <input
      className={`w-full h-11 rounded-xl px-4 text-sm outline-none transition-all ${
        light
          ? `bg-white border ${error ? "border-rose-400" : "border-slate-200"} text-slate-900 placeholder-slate-400 focus:border-purple-500`
          : `bg-slate-950 border ${error ? "border-rose-500" : "border-slate-800"} text-slate-100 placeholder-slate-600 focus:border-cyan-500`
      } ${className}`}
      {...props}
    />
  );
}


function Textarea({ light, error, className = "", rows = 4, ...props }) {
  return (
    <textarea rows={rows}
      className={`w-full rounded-xl px-4 py-3 text-sm outline-none resize-none transition-all ${
        light
          ? `bg-white border ${error ? "border-rose-400" : "border-slate-200"} text-slate-900 placeholder-slate-400 focus:border-purple-500`
          : `bg-slate-950 border ${error ? "border-rose-500" : "border-slate-800"} text-slate-100 placeholder-slate-600 focus:border-cyan-500`
      } ${className}`}
      {...props}
    />
  );
}


// ─── STEP 1 · Welcome (category + name) ────────────────────────
function StepWelcome({ light, advance, merchant, merchantId, setMerchantId,
                                        setMerchant, busy, setBusy }) {
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(
    merchant?.category_id || "");
  const [name, setName] = useState(merchant?.name || "");

  useEffect(() => {
    axios.get(`${API}/business-categories`).then(({ data }) => {
      setCategories(data.items || []);
    }).catch(() => setCategories([]));
  }, []);

  const canSubmit = name.trim().length >= 2 && !!selectedCategory && !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/merchant/apply`,
        { name: name.trim(), category_id: selectedCategory },
        { withCredentials: true });
      setMerchantId(data.merchant_id);
      setMerchant(data);
      toast.success("Application started");
      advance("profile");
    } catch (e) {
      toast.error(`Start failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <Card light={light} data-testid="merchant-step-welcome">
      <Title light={light} eyebrow="Step 1 of 9"
                  title="Become a BigFM Partner"
                  sub="Pick a category and tell us your business name. You can edit everything before submitting." />

      <div className="mb-6">
        <label className={`block text-xs font-bold uppercase tracking-wider mb-2 ${
          light ? "text-slate-600" : "text-slate-400"
        }`}>Business Name</label>
        <Input light={light} value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Karak Café — Karama Branch"
                    data-testid="merchant-name-input"
                    maxLength={120} />
      </div>

      <div>
        <label className={`block text-xs font-bold uppercase tracking-wider mb-3 ${
          light ? "text-slate-600" : "text-slate-400"
        }`}>Category</label>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2"
                  data-testid="merchant-category-grid">
          {categories.map((c) => {
            const Icon = CATEGORY_ICONS[c.icon_hint] || Sparkles;
            const active = selectedCategory === c.id;
            return (
              <button key={c.id} type="button"
                          onClick={() => setSelectedCategory(c.id)}
                          data-testid={`merchant-category-${c.id}`}
                          data-active={active ? "true" : "false"}
                          className={`flex flex-col items-center gap-1.5 rounded-2xl p-4 border transition-all ${
                            active
                              ? (light
                                  ? "border-transparent bg-gradient-to-br from-purple-500 to-pink-500 text-white shadow-lg shadow-purple-500/20"
                                  : "border-cyan-500 bg-cyan-500/10 text-cyan-300")
                              : (light
                                  ? "bg-white border-slate-200 text-slate-700 hover:border-purple-300 hover:bg-purple-50"
                                  : "bg-slate-800/40 border-slate-800 text-slate-300 hover:border-cyan-500/40")
                          }`}>
                <Icon size={22} />
                <span className="text-[12px] font-semibold">{c.name}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex justify-end mt-8">
        <PrimaryBtn light={light} onClick={submit} disabled={!canSubmit}
                              data-testid="merchant-step-welcome-submit">
          {busy ? <><Loader2 className="animate-spin" size={16}/> Starting…</>
                      : <>Continue <ArrowRight size={16}/></>}
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 2 · Profile (description, phone, website) ─────────────
function StepProfile({ light, advance, back, merchant, merchantId,
                                        setMerchant, busy, setBusy }) {
  const [description, setDescription] = useState(merchant?.description || "");
  const [phone, setPhone] = useState(merchant?.phone || "");
  const [website, setWebsite] = useState(merchant?.website || "");

  const canSubmit = description.trim().length >= 1
                                && description.length <= 500 && !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const { data } = await axios.put(`${API}/merchant/${merchantId}/profile`,
        { description: description.trim(),
          phone: phone.trim() || null,
          website: website.trim() || null },
        { withCredentials: true });
      setMerchant(data);
      toast.success("Profile saved");
      advance("locations");
    } catch (e) {
      toast.error(`Save failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <Card light={light} data-testid="merchant-step-profile">
      <Title light={light} eyebrow="Step 2 of 9"
                  title="Tell your story"
                  sub="A short description (max 500 characters) plus optional phone and website." />

      <div className="mb-4">
        <label className={`block text-xs font-bold uppercase tracking-wider mb-2 ${
          light ? "text-slate-600" : "text-slate-400"
        }`}>Description</label>
        <Textarea light={light} rows={5} value={description}
                          onChange={(e) => setDescription(e.target.value.slice(0, 500))}
                          placeholder="What makes your business special? Mention cuisine, vibe, signature items, or events."
                          data-testid="merchant-description-input" />
        <div className={`mt-1 text-xs text-right ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>{description.length} / 500</div>
      </div>

      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div>
          <label className={`block text-xs font-bold uppercase tracking-wider mb-2 ${
            light ? "text-slate-600" : "text-slate-400"
          }`}>Phone</label>
          <Input light={light} value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="+971 50 123 4567"
                        data-testid="merchant-phone-input" />
        </div>
        <div>
          <label className={`block text-xs font-bold uppercase tracking-wider mb-2 ${
            light ? "text-slate-600" : "text-slate-400"
          }`}>Website</label>
          <Input light={light} value={website}
                        onChange={(e) => setWebsite(e.target.value)}
                        placeholder="https://…"
                        data-testid="merchant-website-input" />
        </div>
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={submit} disabled={!canSubmit}
                              data-testid="merchant-step-profile-submit">
          {busy ? <><Loader2 className="animate-spin" size={16}/> Saving…</>
                      : <>Continue <ArrowRight size={16}/></>}
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 3 · Locations (Google Places Autocomplete) ────────────
function StepLocations({ light, advance, back, merchant, merchantId,
                                            setMerchant, busy, setBusy }) {
  const gmapsKey = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
  const [locations, setLocations] = useState(merchant?.locations || []);
  const [showAdd, setShowAdd] = useState(locations.length === 0);
  const primary = locations.find((l) => l.primary);
  const canAdvance = !!primary && !busy;

  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchantId}/locations`,
        { withCredentials: true });
      setLocations(data.items || []);
    } catch (_e) { /* silent */ }
  }, [merchantId]);

  const removeLoc = async (loc_id) => {
    setBusy(true);
    try {
      await axios.delete(`${API}/merchant/${merchantId}/locations/${loc_id}`,
                                          { withCredentials: true });
      toast.success("Location removed");
      await refresh();
    } catch (e) {
      toast.error(`Remove failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  const submit = () => {
    if (canAdvance) advance("logo");
  };

  return (
    <Card light={light} data-testid="merchant-step-locations">
      <Title light={light} eyebrow="Step 3 of 9"
                  title="Where can customers find you?"
                  sub="Add at least one location.  The first location becomes your primary — you can add more branches now or later." />

      <div className="space-y-2 mb-4" data-testid="merchant-locations-list">
        {locations.map((l) => (
          <div key={l.location_id}
                    data-testid={`merchant-location-row-${l.location_id}`}
                    className={`rounded-2xl p-4 flex items-start justify-between gap-3 ${
                      light ? "bg-purple-50/60 border border-purple-100"
                              : "bg-slate-800/40 border border-slate-800"
                    }`}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <MapPin size={14} className={light ? "text-purple-600" : "text-cyan-400"}/>
                <span className={`font-semibold text-sm truncate ${
                  light ? "text-slate-900" : "text-slate-100"
                }`}>{l.name || l.address}</span>
                {l.primary && (
                  <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    light ? "bg-purple-100 text-purple-700"
                          : "bg-cyan-500/20 text-cyan-300"
                  }`}>Primary</span>
                )}
              </div>
              <div className={`text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                {l.address}{l.city ? ` · ${l.city}` : ""}{l.country ? `, ${l.country}` : ""}
              </div>
              {l.phone && (
                <div className={`text-xs mt-0.5 ${light ? "text-slate-500" : "text-slate-500"}`}>
                  {l.phone}
                </div>
              )}
            </div>
            <button type="button" onClick={() => removeLoc(l.location_id)}
                          data-testid={`merchant-location-remove-${l.location_id}`}
                          className={`p-2 rounded-full ${
                            light ? "text-rose-500 hover:bg-rose-50"
                                  : "text-rose-400 hover:bg-rose-500/10"
                          }`}>
              <Trash2 size={16}/>
            </button>
          </div>
        ))}
      </div>

      {showAdd || locations.length === 0 ? (
        gmapsKey ? (
          <APIProvider apiKey={gmapsKey} libraries={["places"]}>
            <AddLocationForm light={light} merchantId={merchantId}
                                          onDone={async () => {
                                            setShowAdd(false);
                                            await refresh();
                                          }} />
          </APIProvider>
        ) : (
          <FallbackAddLocationForm light={light} merchantId={merchantId}
                                                        onDone={async () => {
                                                          setShowAdd(false);
                                                          await refresh();
                                                        }} />
        )
      ) : (
        <GhostBtn light={light} onClick={() => setShowAdd(true)}
                              data-testid="merchant-add-another-location">
          <MapPin size={14}/> Add another location
        </GhostBtn>
      )}

      <div className="flex justify-between mt-8">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={submit} disabled={!canAdvance}
                              data-testid="merchant-step-locations-submit">
          Continue <ArrowRight size={16}/>
        </PrimaryBtn>
      </div>
    </Card>
  );
}


function AddLocationForm({ light, merchantId, onDone }) {
  const wrapRef = useRef(null);
  const [address, setAddress] = useState("");
  const [placeData, setPlaceData] = useState(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!wrapRef.current) return;
    if (!window.google?.maps?.places?.PlaceAutocompleteElement) return;
    // Reuse the Phase-H web-component approach for consistency
    let el;
    try {
      el = new window.google.maps.places.PlaceAutocompleteElement({
        includedRegionCodes: [], // no restriction
      });
      el.setAttribute("data-testid", "merchant-location-autocomplete");
      el.style.width = "100%";
      wrapRef.current.innerHTML = "";
      wrapRef.current.appendChild(el);
      el.addEventListener("gmp-select", async (evt) => {
        try {
          const place = evt.placePrediction?.toPlace?.() || evt.place;
          if (!place) return;
          await place.fetchFields({
            fields: ["displayName", "formattedAddress", "location",
                          "id", "addressComponents"],
          });
          const loc = place.location;
          const city = (place.addressComponents || []).find(
            (c) => (c.types || []).includes("locality"))?.longText;
          const country = (place.addressComponents || []).find(
            (c) => (c.types || []).includes("country"))?.longText;
          setPlaceData({
            address: place.formattedAddress,
            city,
            country,
            latitude:  loc?.lat?.() ?? null,
            longitude: loc?.lng?.() ?? null,
            google_place_id: place.id,
          });
          setAddress(place.formattedAddress || "");
        } catch (e) { console.warn("[merchant-locations] fetchFields:", e); }
      });
    } catch (e) {
      console.warn("[merchant-locations] failed to mount autocomplete:", e);
    }
    return () => { try { el?.remove(); } catch (_e) { /* ignore */ } };
  }, []);

  const submit = async () => {
    if (!placeData?.address && !address.trim()) return;
    setBusy(true);
    try {
      const body = {
        ...(placeData || { address: address.trim() }),
        name: name.trim() || null,
        phone: phone.trim() || null,
      };
      await axios.post(`${API}/merchant/${merchantId}/locations`, body,
                                    { withCredentials: true });
      toast.success("Location added");
      onDone();
    } catch (e) {
      toast.error(`Add failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <div className={`rounded-2xl p-4 mb-4 ${
      light ? "bg-slate-50 border border-slate-200"
              : "bg-slate-950 border border-slate-800"
    }`} data-testid="merchant-add-location-form">
      <label className={`block text-xs font-bold uppercase tracking-wider mb-2 ${
        light ? "text-slate-600" : "text-slate-400"
      }`}>Search address</label>
      <div ref={wrapRef} className="mb-3" />
      {placeData?.address && (
        <div className={`text-xs mb-3 ${light ? "text-slate-600" : "text-slate-400"}`}
                  data-testid="merchant-location-picked">
          Picked: <b>{placeData.address}</b>
          {placeData.latitude && ` · ${placeData.latitude.toFixed(3)}, ${placeData.longitude.toFixed(3)}`}
        </div>
      )}
      <div className="grid sm:grid-cols-2 gap-3 mb-3">
        <Input light={light} value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Branch label (optional, e.g. Karama)"
                    data-testid="merchant-location-name-input" />
        <Input light={light} value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="Branch phone (optional)"
                    data-testid="merchant-location-phone-input" />
      </div>
      <div className="flex justify-end">
        <PrimaryBtn light={light} onClick={submit}
                              disabled={busy || (!placeData?.address && !address.trim())}
                              data-testid="merchant-location-save-btn">
          {busy ? <><Loader2 size={14} className="animate-spin"/> Saving…</>
                      : <>Add location <Check size={14}/></>}
        </PrimaryBtn>
      </div>
    </div>
  );
}


function FallbackAddLocationForm({ light, merchantId, onDone }) {
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (address.trim().length < 3) return;
    setBusy(true);
    try {
      await axios.post(`${API}/merchant/${merchantId}/locations`,
        { address: address.trim(), city: city.trim() || null,
          country: country.trim() || null,
          name: name.trim() || null,
          phone: phone.trim() || null },
        { withCredentials: true });
      toast.success("Location added");
      onDone();
    } catch (e) {
      toast.error(`Add failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <div className={`rounded-2xl p-4 mb-4 ${
      light ? "bg-slate-50 border border-slate-200"
              : "bg-slate-950 border border-slate-800"
    }`} data-testid="merchant-add-location-fallback">
      <div className="text-xs mb-2 text-amber-600">
        Google Maps key unavailable — manual entry.
      </div>
      <Input light={light} value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Street address"
                  className="mb-2"
                  data-testid="merchant-location-address-input" />
      <div className="grid sm:grid-cols-2 gap-2 mb-2">
        <Input light={light} value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="City" />
        <Input light={light} value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    placeholder="Country" />
      </div>
      <div className="grid sm:grid-cols-2 gap-2 mb-3">
        <Input light={light} value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Branch label" />
        <Input light={light} value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="Branch phone" />
      </div>
      <div className="flex justify-end">
        <PrimaryBtn light={light} onClick={submit}
                              disabled={busy || address.trim().length < 3}
                              data-testid="merchant-location-save-btn">
          {busy ? "Saving…" : "Add location"}
        </PrimaryBtn>
      </div>
    </div>
  );
}


// ─── STEP 4 · Logo upload ─────────────────────────────────────────
function StepLogo({ light, advance, back, merchant, merchantId,
                                    setMerchant, busy, setBusy }) {
  const [logoUrl, setLogoUrl] = useState(merchant?.logo_url || null);
  const fileRef = useRef(null);

  const handleFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!/^image\/(png|jpe?g|webp)$/i.test(f.type)) {
      toast.error("Please upload a PNG, JPG, or WebP image");
      return;
    }
    if (f.size > 3 * 1024 * 1024) {
      toast.error("Logo must be under 3 MB");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await axios.post(
        `${API}/merchant/${merchantId}/logo`, fd,
        { withCredentials: true,
          headers: { "Content-Type": "multipart/form-data" } });
      setLogoUrl(data.logo_url);
      setMerchant((m) => m ? { ...m, logo_url: data.logo_url } : m);
      toast.success("Logo uploaded");
    } catch (e2) {
      toast.error(`Upload failed: ${e2?.response?.data?.detail || e2.message}`);
    } finally { setBusy(false); }
  };

  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const displayUrl = logoUrl?.startsWith("http") ? logoUrl
                                    : logoUrl ? backendBase + logoUrl : null;

  return (
    <Card light={light} data-testid="merchant-step-logo">
      <Title light={light} eyebrow="Step 4 of 9"
                  title="Upload your logo"
                  sub="Square logo works best.  PNG, JPG, or WebP under 3 MB." />

      <div className={`rounded-3xl p-6 mb-6 flex flex-col items-center gap-4 ${
        light ? "bg-purple-50/60 border-2 border-dashed border-purple-200"
                : "bg-slate-800/40 border-2 border-dashed border-slate-700"
      }`}>
        {displayUrl ? (
          <img src={displayUrl} alt="Logo preview"
                    data-testid="merchant-logo-preview"
                    className="w-40 h-40 object-cover rounded-2xl shadow-md" />
        ) : (
          <div className={`w-40 h-40 rounded-2xl flex items-center justify-center ${
            light ? "bg-white border border-slate-200"
                    : "bg-slate-900 border border-slate-800"
          }`}>
            <Upload size={32} className={light ? "text-slate-400" : "text-slate-500"}/>
          </div>
        )}
        <input ref={fileRef} type="file" accept="image/*" hidden
                    onChange={handleFile}
                    data-testid="merchant-logo-file-input"/>
        <PrimaryBtn light={light}
                              onClick={() => fileRef.current?.click()}
                              disabled={busy}
                              data-testid="merchant-logo-upload-btn">
          {busy ? <><Loader2 className="animate-spin" size={16}/> Uploading…</>
                      : displayUrl ? <>Replace logo <Upload size={16}/></>
                                              : <>Choose logo <Upload size={16}/></>}
        </PrimaryBtn>
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={() => advance("photos")}
                              disabled={!logoUrl || busy}
                              data-testid="merchant-step-logo-submit">
          Continue <ArrowRight size={16}/>
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 5 · Photos (up to 6, skippable) ─────────────────────────
function StepPhotos({ light, advance, back, merchant, merchantId,
                                      setMerchant, busy, setBusy }) {
  const [photos, setPhotos] = useState(merchant?.photos || []);
  const fileRef = useRef(null);

  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const url = (p) => p.url?.startsWith("http") ? p.url : backendBase + (p.url || "");

  const handleFile = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    for (const f of files) {
      if (photos.length >= 6) {
        toast.warning("Maximum 6 photos");
        break;
      }
      if (f.size > 5 * 1024 * 1024) {
        toast.error(`${f.name} is over 5 MB — skipped`);
        continue;
      }
      if (!/^image\/(png|jpe?g|webp)$/i.test(f.type)) continue;
      setBusy(true);
      try {
        const fd = new FormData(); fd.append("file", f);
        const { data } = await axios.post(
          `${API}/merchant/${merchantId}/photos`, fd,
          { withCredentials: true,
            headers: { "Content-Type": "multipart/form-data" } });
        setPhotos((prev) => [...prev, { url: data.photo_url, key: data.key }]);
      } catch (e2) {
        toast.error(`Upload failed: ${e2?.response?.data?.detail || e2.message}`);
      } finally { setBusy(false); }
    }
    e.target.value = "";
  };

  const remove = async (idx) => {
    setBusy(true);
    try {
      await axios.delete(`${API}/merchant/${merchantId}/photos/${idx}`,
                                          { withCredentials: true });
      setPhotos((prev) => prev.filter((_, i) => i !== idx));
    } catch (e) {
      toast.error(`Remove failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <Card light={light} data-testid="merchant-step-photos">
      <Title light={light} eyebrow="Step 5 of 9"
                  title="Show off your space"
                  sub="Up to 6 photos.  Skippable — you can add photos later from the merchant dashboard." />

      <div className="grid grid-cols-3 gap-3 mb-4" data-testid="merchant-photos-grid">
        {photos.map((p, i) => (
          <div key={i} className="relative"
                    data-testid={`merchant-photo-${i}`}>
            <img src={url(p)} alt="" className="w-full aspect-square object-cover rounded-2xl"/>
            <button type="button" onClick={() => remove(i)}
                          className="absolute top-1.5 right-1.5 h-7 w-7 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-black"
                          data-testid={`merchant-photo-remove-${i}`}>
              <XIcon size={14}/>
            </button>
          </div>
        ))}
        {photos.length < 6 && (
          <button type="button" onClick={() => fileRef.current?.click()}
                        disabled={busy}
                        data-testid="merchant-photos-add-btn"
                        className={`aspect-square rounded-2xl flex flex-col items-center justify-center gap-2 border-2 border-dashed transition-all ${
                          light
                            ? "bg-purple-50/40 border-purple-200 text-purple-700 hover:bg-purple-50"
                            : "bg-slate-800/40 border-slate-700 text-slate-400 hover:border-cyan-500/50"
                        }`}>
            {busy ? <Loader2 size={20} className="animate-spin"/> : <Camera size={22}/>}
            <span className="text-[11px] font-semibold uppercase tracking-wider">Add</span>
          </button>
        )}
      </div>

      <input ref={fileRef} type="file" accept="image/*" hidden multiple
                  onChange={handleFile}
                  data-testid="merchant-photos-file-input"/>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <div className="flex gap-2">
          <GhostBtn light={light} onClick={() => advance("hours")}
                            data-testid="merchant-step-photos-skip">Skip</GhostBtn>
          <PrimaryBtn light={light} onClick={() => advance("hours")}
                                data-testid="merchant-step-photos-submit">
            Continue <ArrowRight size={16}/>
          </PrimaryBtn>
        </div>
      </div>
    </Card>
  );
}


// ─── STEP 6 · Hours (7-day picker + Copy to all) ──────────────────
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday",
                          "saturday", "sunday"];
const DEFAULT_DAY = { open: "09:00", close: "22:00", closed: false };

function StepHours({ light, advance, back, merchant, merchantId,
                                    setMerchant, busy, setBusy }) {
  const [hours, setHours] = useState(() => {
    const src = merchant?.hours || {};
    return Object.fromEntries(DAYS.map(
      (d) => [d, src[d] || { ...DEFAULT_DAY }]));
  });

  const setDay = (d, patch) =>
    setHours((prev) => ({ ...prev, [d]: { ...prev[d], ...patch } }));

  const copyMondayToAll = () => {
    const src = hours.monday;
    setHours(Object.fromEntries(DAYS.map((d) => [d, { ...src }])));
    toast.success("Copied Monday's hours to all days");
  };

  const submit = async () => {
    setBusy(true);
    try {
      await axios.put(`${API}/merchant/${merchantId}/hours`, hours,
                                    { withCredentials: true });
      setMerchant((m) => m ? { ...m, hours } : m);
      toast.success("Hours saved");
      advance("terms");
    } catch (e) {
      toast.error(`Save failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <Card light={light} data-testid="merchant-step-hours">
      <Title light={light} eyebrow="Step 6 of 9"
                  title="Business hours"
                  sub="Set your opening times.  Use “Copy Monday to all” for consistent schedules." />

      <div className="flex justify-end mb-3">
        <GhostBtn light={light} onClick={copyMondayToAll}
                            data-testid="merchant-hours-copy-all">
          <Copy size={14}/> Copy Monday to all
        </GhostBtn>
      </div>

      <div className="space-y-2 mb-6">
        {DAYS.map((d) => (
          <div key={d} className={`grid grid-cols-[100px_1fr_1fr_auto] gap-2 items-center rounded-2xl px-3 py-2 ${
            light ? "bg-slate-50" : "bg-slate-800/40"
          }`} data-testid={`merchant-hours-row-${d}`}>
            <div className={`text-xs font-bold uppercase tracking-wider ${
              light ? "text-slate-700" : "text-slate-300"
            }`}>{d.slice(0, 3)}</div>
            <Input light={light} type="time" value={hours[d].open || ""}
                          disabled={hours[d].closed}
                          onChange={(e) => setDay(d, { open: e.target.value })}
                          data-testid={`merchant-hours-${d}-open`} />
            <Input light={light} type="time" value={hours[d].close || ""}
                          disabled={hours[d].closed}
                          onChange={(e) => setDay(d, { close: e.target.value })}
                          data-testid={`merchant-hours-${d}-close`} />
            <label className={`text-xs font-semibold flex items-center gap-1.5 cursor-pointer ${
              light ? "text-slate-600" : "text-slate-400"
            }`}>
              <input type="checkbox" checked={!!hours[d].closed}
                            onChange={(e) => setDay(d, { closed: e.target.checked })}
                            data-testid={`merchant-hours-${d}-closed`} />
              Closed
            </label>
          </div>
        ))}
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={submit} disabled={busy}
                              data-testid="merchant-step-hours-submit">
          {busy ? "Saving…" : <>Continue <ArrowRight size={16}/></>}
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 7 · Commission terms — SC.3 real rates ────────────────
function StepTerms({ light, advance, back, merchant, merchantId,
                                    setMerchant, busy, setBusy }) {
  const alreadyAccepted = !!merchant?.commission_terms_accepted;
  const [rates, setRates] = useState(null);
  const [ratesErr, setRatesErr] = useState(null);
  const [scrolled, setScrolled] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    axios.get(`${API}/commissions/rates`)
      .then((r) => setRates(r.data))
      .catch((e) => setRatesErr(e?.response?.data?.detail || e.message));
  }, []);

  // Enable the Accept button after the merchant either scrolls the rate
  // table to the bottom OR has already accepted (revisiting the step).
  useEffect(() => {
    if (alreadyAccepted) setScrolled(true);
  }, [alreadyAccepted]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 8) {
      setScrolled(true);
    }
  };

  const submit = async () => {
    if (alreadyAccepted) { advance("stripe"); return; }
    if (!scrolled) {
      toast.error("Please scroll to review the full rate schedule first.");
      return;
    }
    setBusy(true);
    try {
      await axios.post(`${API}/merchant/${merchantId}/accept-terms`, {},
                                    { withCredentials: true });
      setMerchant((m) => m ? { ...m, commission_terms_accepted: true } : m);
      toast.success("Terms accepted");
      advance("stripe");
    } catch (e) {
      toast.error(`Accept failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  const cat = merchant?.category_id;
  const catRates = (cat && rates?.categories?.[cat]) || [];
  const fallback = rates?.fallback;

  return (
    <Card light={light} data-testid="merchant-step-terms">
      <Title light={light} eyebrow="Step 7 of 9"
                  title="Commission terms"
                  sub="These are the current rates for your category.  Scroll to review the full schedule, then accept." />

      {/* Prominent per-category rates card */}
      {cat && (
        <div className={`rounded-2xl p-5 mb-4 ${
          light
            ? "bg-gradient-to-br from-purple-50 to-pink-50 border border-purple-200"
            : "bg-slate-800/60 border border-cyan-500/30"
        }`} data-testid="merchant-terms-category-rates">
          <div className={`text-xs font-bold uppercase tracking-widest mb-2 ${
            light ? "text-purple-700" : "text-cyan-400"
          }`}>Your category · {cat}</div>
          {catRates.length === 0 ? (
            <div className={light ? "text-slate-600 text-sm" : "text-slate-400 text-sm"}>
              Loading rates…
            </div>
          ) : (
            <div className="space-y-1.5">
              {catRates.map((r) => (
                <div key={r.rule_id}
                          data-testid={`merchant-terms-cat-rate-${r.transaction_type}`}
                          className="flex items-baseline justify-between gap-3">
                  <div className={`text-sm ${light ? "text-slate-800" : "text-slate-200"}`}>
                    {(r.transaction_type || "").replace(/_/g, " ")}
                  </div>
                  <div className={`font-black text-lg tabular-nums ${
                    light ? "text-purple-700" : "text-cyan-300"
                  }`}>
                    {r.commission_percent.toFixed(1)}%
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Scrollable terms body — Accept button gates on scroll-to-bottom */}
      <div ref={scrollRef} onScroll={onScroll}
                data-testid="merchant-terms-body"
                className={`rounded-2xl p-5 mb-2 text-sm leading-relaxed max-h-[280px] overflow-y-auto ${
                  light ? "bg-purple-50/60 border border-purple-100 text-slate-700"
                          : "bg-slate-800/60 border border-slate-700 text-slate-300"
                }`}>
        <p className="mb-3">By accepting these terms you agree that:</p>
        <ul className="list-disc pl-5 space-y-1.5">
          <li>BigFM charges a platform commission on transactions processed through the merchant Pay flow.  Current rates are set by the commission rules engine (SC.3) and are subject to change with 30 days notice.</li>
          <li>You&apos;ll receive payouts via your connected Stripe account, on Stripe&apos;s standard payout schedule.</li>
          <li>Coupons, offers, and promotions issued to BigFM users are honoured at your listed price.</li>
          <li>BigFM may audit merchant activity for compliance with the platform&apos;s community + trust policies.</li>
          <li>You may deactivate your merchant account at any time.  Existing payouts and receipts remain accessible.</li>
          {fallback && (
            <li>Uncategorised transactions default to <b>{fallback.commission_percent.toFixed(1)}%</b>.</li>
          )}
        </ul>
        <p className="mt-3 text-xs opacity-80">
          Full public schedule: <a href="/legal/commissions" target="_blank" rel="noreferrer"
                                                            data-testid="merchant-terms-legal-link"
                                                            className={light ? "underline text-purple-700" : "underline text-cyan-400"}>
            /legal/commissions
          </a>
        </p>
        {ratesErr && (
          <p className="mt-3 text-xs text-rose-500">Rate load error: {ratesErr}</p>
        )}
      </div>

      <div className={`text-[11px] mb-4 ${
        scrolled
          ? (light ? "text-emerald-700" : "text-emerald-400")
          : (light ? "text-slate-500" : "text-slate-500")
      }`} data-testid="merchant-terms-scroll-status">
        {scrolled ? "✓ Rate schedule reviewed"
                        : "Scroll the box above to enable the Accept button"}
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={submit}
                              disabled={busy || (!scrolled && !alreadyAccepted)}
                              data-testid="merchant-terms-accept-btn">
          {alreadyAccepted ? <>Already accepted <Check size={16}/></>
                                      : busy ? "Saving…" : <>I accept — continue <Check size={16}/></>}
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 8 · Stripe Connect ────────────────────────────────────
function StepStripe({ light, advance, back, merchant, merchantId,
                                      setMerchant, busy, setBusy }) {
  const [status, setStatus] = useState(
    merchant?.stripe_onboarding_status || "not_started");

  const startStripe = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/onboarding/start`,
        { merchant_id: merchantId },
        { withCredentials: true });
      setStatus("onboarding_in_progress");
      // Open in same tab — Stripe returns to /merchant/onboarding/complete
      window.location.href = data.onboarding_url;
    } catch (e) {
      toast.error(`Stripe start failed: ${e?.response?.data?.detail || e.message}`);
      setBusy(false);
    }
  };

  const refresh = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/status/refresh`,
        { merchant_id: merchantId },
        { withCredentials: true });
      setStatus(data.stripe_onboarding_status);
      setMerchant((m) => m ? { ...m,
        stripe_onboarding_status: data.stripe_onboarding_status,
        stripe_charges_enabled: data.charges_enabled,
        stripe_payouts_enabled: data.payouts_enabled,
        stripe_details_submitted: data.details_submitted } : m);
      toast.success(`Status: ${data.stripe_onboarding_status}`);
    } catch (e) {
      toast.error(`Refresh failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  const canAdvance = !!merchant?.stripe_account_id && !busy;

  const pillClass = light
    ? "bg-purple-100 text-purple-800 border border-purple-200"
    : "bg-cyan-500/10 text-cyan-300 border border-cyan-500/30";

  return (
    <Card light={light} data-testid="merchant-step-stripe">
      <Title light={light} eyebrow="Step 8 of 9"
                  title="Set up payments"
                  sub="We use Stripe Connect Standard so you get your own dashboard, direct payouts, and refund control.  You keep your Stripe account even if you leave BigFM." />

      <div className={`rounded-2xl p-5 mb-6 ${
        light ? "bg-slate-50 border border-slate-200"
                : "bg-slate-800/60 border border-slate-700"
      }`}>
        <div className="flex items-center gap-2 mb-1.5">
          <span className={`text-[11px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full ${pillClass}`}
                      data-testid="merchant-stripe-status">
            {status.replace(/_/g, " ")}
          </span>
          {merchant?.stripe_account_id && (
            <code className={`text-[11px] px-2 py-0.5 rounded ${
              light ? "bg-white text-slate-600 border border-slate-200"
                      : "bg-slate-950 text-slate-400 border border-slate-800"
            }`} data-testid="merchant-stripe-acct-id">
              {merchant.stripe_account_id}
            </code>
          )}
        </div>
        <p className={`text-sm mt-2 ${light ? "text-slate-600" : "text-slate-400"}`}>
          {status === "active"
            ? "Your Stripe account is fully activated and ready to accept payments."
            : status === "onboarding_in_progress"
              ? "Stripe onboarding is in progress.  Click “Refresh status” once you finish."
              : "Click “Start Stripe setup” to open Stripe's hosted onboarding.  You'll return here when you're done."}
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 mb-6">
        <PrimaryBtn light={light} onClick={startStripe} disabled={busy}
                              data-testid="merchant-stripe-start-btn">
          {busy ? <Loader2 className="animate-spin" size={16}/>
                    : merchant?.stripe_account_id
                      ? <>Continue Stripe setup <ExternalLink size={16}/></>
                      : <>Start Stripe setup <ExternalLink size={16}/></>}
        </PrimaryBtn>
        {merchant?.stripe_account_id && (
          <GhostBtn light={light} onClick={refresh} disabled={busy}
                              data-testid="merchant-stripe-refresh-btn">
            Refresh status
          </GhostBtn>
        )}
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={() => advance("review")}
                              disabled={!canAdvance}
                              data-testid="merchant-step-stripe-submit">
          Continue <ArrowRight size={16}/>
        </PrimaryBtn>
      </div>
    </Card>
  );
}


// ─── STEP 9 · Review & Submit ─────────────────────────────────────
function StepReview({ light, advance, back, merchant, merchantId,
                                      setMerchant, busy, setBusy, loadMerchant }) {
  const navigate = useNavigate();

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/merchant/${merchantId}/submit-for-approval`, {},
        { withCredentials: true });
      setMerchant(data);
      toast.success("Application submitted!");
      navigate(`/merchant/status?merchant_id=${merchantId}`);
    } catch (e) {
      const det = e?.response?.data?.detail;
      if (det?.code === "incomplete_application") {
        toast.error(`Missing: ${(det.missing_fields || []).join(", ")}`);
      } else {
        toast.error(`Submit failed: ${det || e.message}`);
      }
    } finally { setBusy(false); }
  };

  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const url = (u) => u?.startsWith("http") ? u : backendBase + (u || "");

  return (
    <Card light={light} data-testid="merchant-step-review">
      <Title light={light} eyebrow="Step 9 of 9"
                  title="Review & submit"
                  sub="Double-check everything.  Once submitted an admin will review your application." />

      <div className="space-y-4 mb-8">
        <SummaryRow light={light} label="Business"
                                value={<div>
                                  <div className="font-semibold">{merchant?.name}</div>
                                  <div className="text-xs opacity-70">{merchant?.category_id}</div>
                                </div>}
                                testId="merchant-review-business" />
        {merchant?.logo_url && (
          <SummaryRow light={light} label="Logo"
                                  value={<img src={url(merchant.logo_url)}
                                                        alt="logo"
                                                        className="w-16 h-16 object-cover rounded-xl"
                                                        data-testid="merchant-review-logo-img"/>}
                                  testId="merchant-review-logo" />
        )}
        <SummaryRow light={light} label="Description"
                                value={<span className="text-sm">{merchant?.description}</span>}
                                testId="merchant-review-description" />
        {merchant?.phone && (
          <SummaryRow light={light} label="Phone" value={merchant.phone}
                                  testId="merchant-review-phone" />
        )}
        {merchant?.website && (
          <SummaryRow light={light} label="Website" value={merchant.website}
                                  testId="merchant-review-website" />
        )}
        <SummaryRow light={light} label="Locations"
                                value={<div className="text-sm">
                                  {(merchant?.locations || []).map((l) => (
                                    <div key={l.location_id}>{l.name || l.address}</div>
                                  ))}
                                </div>}
                                testId="merchant-review-locations" />
        <SummaryRow light={light} label="Photos"
                                value={<span className="text-sm">
                                  {(merchant?.photos || []).length} uploaded
                                </span>}
                                testId="merchant-review-photos" />
        <SummaryRow light={light} label="Stripe"
                                value={<code className={`text-xs px-2 py-0.5 rounded ${
                                  light ? "bg-white border border-slate-200"
                                          : "bg-slate-950 border border-slate-800"
                                }`}>{merchant?.stripe_account_id || "—"}</code>}
                                testId="merchant-review-stripe" />
      </div>

      <div className="flex justify-between">
        <GhostBtn light={light} onClick={back}>Back</GhostBtn>
        <PrimaryBtn light={light} onClick={submit} disabled={busy}
                              data-testid="merchant-review-submit-btn">
          {busy ? <><Loader2 className="animate-spin" size={16}/> Submitting…</>
                      : <>Submit for approval <Check size={16}/></>}
        </PrimaryBtn>
      </div>
    </Card>
  );
}


function SummaryRow({ light, label, value, testId }) {
  return (
    <div data-testid={testId}
              className={`grid grid-cols-[110px_1fr] gap-4 items-start pb-3 border-b ${
                light ? "border-slate-100" : "border-slate-800"
              }`}>
      <div className={`text-xs font-bold uppercase tracking-wider pt-0.5 ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{label}</div>
      <div className={light ? "text-slate-900" : "text-slate-100"}>
        {value}
      </div>
    </div>
  );
}
