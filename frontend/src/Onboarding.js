// Onboarding wizard — 11 steps. Must complete before the radio unlocks.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import {
  ChevronRight, ChevronLeft, Check, Loader2, Plus, X, Play, Pause, Radio as RadioIcon,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { API, useAuth } from "./AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import { consumeIntent } from "@/utils/intent";
import BigFmBrand from "@/components/BigFmBrand";

const LANGUAGES = [
  { id: "hindi",     label: "हिंदी / Hindi" },
  { id: "punjabi",   label: "ਪੰਜਾਬੀ / Punjabi" },
  { id: "english",   label: "English" },
  { id: "bollywood", label: "Bollywood" },
  { id: "tamil",     label: "தமிழ் / Tamil" },
  { id: "arabic",    label: "العربية / Arabic" },
  { id: "malayalam", label: "മലയാളം / Malayalam" },
  { id: "telugu",    label: "తెలుగు / Telugu" },
];

const GENRES = [
  "bollywood", "hip_hop", "pop", "electronic", "retro", "indie",
  "sufi", "ghazal", "devotional", "rock", "punjabi_pop", "arabic_pop",
];

const ERAS = [
  { id: "80s",   label: "80s" },
  { id: "90s",   label: "90s" },
  { id: "2000s", label: "2000s" },
  { id: "2010s", label: "2010s" },
  { id: "2020s", label: "2020s" },
];

const MOODS = ["energetic", "chill", "romantic", "party", "uplifting", "melancholy", "devotional", "nostalgic"];

const ACTIVITIES = [
  { id: "morning_commute", label: "Morning commute" },
  { id: "workday_focus",   label: "Workday focus" },
  { id: "lunch_break",     label: "Lunch break" },
  { id: "evening_commute", label: "Evening commute" },
  { id: "dinner",          label: "Dinner" },
  { id: "late_night_drive",label: "Late-night drive" },
  { id: "workout",         label: "Workout" },
  { id: "party",           label: "Party" },
  { id: "devotional_time", label: "Devotional time" },
];

const DUBAI_AREAS = [
  "Karama", "Bur Dubai", "Deira", "Al Nahda", "JLT", "Business Bay",
  "Downtown", "Marina", "Sharjah", "Other",
];

const DFW_AREAS = [
  "Frisco", "Plano", "Irving", "Carrollton", "Richardson",
  "Dallas", "Fort Worth", "Arlington", "Garland", "Allen",
  "McKinney", "Lewisville", "Other",
];

const MARKETS = [
  { id: "dubai", label: "Dubai", flag: "🇦🇪", blurb: "UAE — Karama, JLT, Marina, Sharjah" },
  { id: "dfw",   label: "DFW",   flag: "🇺🇸", blurb: "Dallas–Fort Worth — Frisco, Plano, Irving" },
];

const VOICES = [
  { id: "veer_dubai",     name: "Veer",          blurb: "Late-night charm, smooth radio host.",       fits: "chill · medium" },
  { id: "monika_dubai",   name: "Monika",        blurb: "Hindi-native, warm and natural.",            fits: "chill · medium" },
  { id: "dj_dubai",       name: "DJ Charlie",    blurb: "Club energy, party MC.",                     fits: "high · party" },
  { id: "dj_riya_dubai",  name: "DJ Riya",       blurb: "JBR-loft female club MC, English-heavy.",    fits: "high · party" },
  { id: "pandit_anand",   name: "Pandit Anand",  blurb: "Wisdom keeper, devotional broadcaster.",     fits: "chill" },
  { id: "gurpreet_bhaji", name: "Gurpreet Bhaji",blurb: "Punjabi specialist, Karama dhaba energy.",   fits: "medium · high · party" },
  { id: "aarti_morning",  name: "Aarti",         blurb: "Bubbly morning-show, Delhi peppy energy.",   fits: "medium · high" },
  { id: "kishore_retro",  name: "Kishore Da",    blurb: "Classic late-80s AIR broadcaster nostalgia.",fits: "chill · medium" },
  { id: "simran_punjabi", name: "Simran",        blurb: "Punjabi female co-host, playful + warm.",    fits: "medium · high · party" },
  { id: "auto",           name: "Auto",          blurb: "Let FUUSIC pick based on the vibe.",          fits: "smart routing" },
];

const STEP_TITLES = [
  "Welcome", "Languages", "Genres", "Eras", "Moods",
  "When", "Market", "Artists (optional)", "Your RJ", "Content filter", "Done",
];

const niceGenre = (g) => g.replace(/_/g, " ");

// Chip multi-select
function ChipGrid({ options, selected, onToggle, "data-testid": dt }) {
  return (
    <div className="chip-grid" data-testid={dt}>
      {options.map((o) => {
        const id = typeof o === "string" ? o : o.id;
        const label = typeof o === "string" ? niceGenre(o) : o.label;
        const on = selected.includes(id);
        return (
          <button
            key={id}
            type="button"
            className={`chip-pill ${on ? "is-on" : ""}`}
            onClick={() => onToggle(id)}
            data-testid={`${dt}-${id}`}
            aria-pressed={on}
          >
            {on && <Check size={14} />}
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

function VoiceCard({ voice, selected, onSelect, currentPlaying, onPreview }) {
  const isPlaying = currentPlaying === voice.id;
  return (
    <button
      type="button"
      className={`voice-card ${selected ? "is-on" : ""}`}
      onClick={() => onSelect(voice.id)}
      data-testid={`voice-card-${voice.id}`}
      aria-pressed={selected}
    >
      <div className="voice-card-head">
        <div className={`voice-avatar voice-avatar-${voice.id}`}>
          <span className="voice-initials">{voice.name.slice(0, 1)}</span>
        </div>
        <div className="voice-info">
          <div className="voice-name">{voice.name}</div>
          <div className="voice-blurb">{voice.blurb}</div>
          <div className="voice-fits mono">{voice.fits.toUpperCase()}</div>
        </div>
      </div>
      {voice.id !== "auto" && (
        <span
          className={`voice-preview-btn ${isPlaying ? "is-on" : ""}`}
          onClick={(e) => { e.stopPropagation(); onPreview(voice.id); }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); onPreview(voice.id); } }}
          data-testid={`voice-preview-${voice.id}`}
        >
          {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          <span>{isPlaying ? "Stop" : "5s preview"}</span>
        </span>
      )}
      {selected && <Check className="voice-check" size={18} />}
    </button>
  );
}

export default function Onboarding() {
  const { user, refresh, setUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  // Bug B — resolved city sourced from the geo store so the onboarding
  // welcome line ("Namaste, {city}.") matches the listener's IP /
  // preferred city instead of the legacy hardcoded "Dubai".
  const city = useGeoStore((s) => s.city);
  const [pv, setPv] = useState({
    languages: [],
    genres: [],
    eras: [],
    moods: [],
    activities: [],
    favorite_artists: [],
    city: "Dubai",
    home_area: null,
    host_personality: "auto",
    explicit_ok: false,
    // Phase 3.7 — Multi-market support
    market: "dubai",
  });
  const [artistDraft, setArtistDraft] = useState("");
  const [recommendedGenres, setRecommendedGenres] = useState([]);
  const audioRef = useRef(null);
  const [previewing, setPreviewing] = useState(null);
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

  // Pre-fill from user's existing prefs (re-doing onboarding)
  useEffect(() => {
    if (user?.preference_vector) {
      const v = user.preference_vector;
      setPv((prev) => ({
        ...prev,
        ...v,
        favorite_artists: v.favorite_artists || [],
      }));
    }
  }, [user]);

  // Auto-detect content language from the browser on first launch (English
  // fallback) so we don't push other-language content at people who didn't ask.
  useEffect(() => {
    if (user?.preference_vector?.languages?.length) return;
    try {
      const code = (navigator.language || "en").slice(0, 2).toLowerCase();
      const MAP = { en: "english", hi: "hindi", pa: "punjabi", ta: "tamil",
                    ar: "arabic", ml: "malayalam", te: "telugu", ur: "urdu", es: "spanish" };
      const detected = MAP[code] || "english";
      const supported = LANGUAGES.some((l) => l.id === detected) ? detected : "english";
      setPv((p) => (p.languages && p.languages.length ? p : { ...p, languages: [supported] }));
    } catch (_e) { /* */ }
  }, [user]);

  // Recommend starter genres from the real catalog (not a fixed list).
  useEffect(() => {
    fetch(`${BACKEND_URL}/api/shell/recommended-genres`)
      .then((r) => r.json())
      .then((d) => setRecommendedGenres(Array.isArray(d.genres) ? d.genres : []))
      .catch(() => setRecommendedGenres([]));
  }, [BACKEND_URL]);

  // Audio cleanup
  useEffect(() => () => {
    if (audioRef.current) {
      try { audioRef.current.pause(); } catch (_e) { /* */ }
      audioRef.current = null;
    }
  }, []);

  const toggle = (key) => (id) => {
    setPv((p) => {
      const arr = p[key] || [];
      return { ...p, [key]: arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id] };
    });
  };

  const stopPreview = useCallback(() => {
    if (audioRef.current) {
      try { audioRef.current.pause(); } catch (_e) { /* */ }
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setPreviewing(null);
  }, []);

  const playPreview = useCallback((voice_id) => {
    if (previewing === voice_id) {
      stopPreview();
      return;
    }
    stopPreview();
    const a = new Audio(`${BACKEND_URL}/api/voices/preview/${voice_id}`);
    a.preload = "auto";
    a.volume = 0.95;
    audioRef.current = a;
    setPreviewing(voice_id);
    a.addEventListener("ended", () => setPreviewing(null));
    a.addEventListener("error", () => {
      toast.error("Could not load voice preview");
      setPreviewing(null);
    });
    a.play().catch(() => {
      toast.warning("Tap the play icon again — browser blocked autoplay");
      setPreviewing(null);
    });
  }, [previewing, stopPreview, BACKEND_URL]);

  const stepValid = useMemo(() => {
    switch (step) {
      case 0:  return true;
      case 1:  return pv.languages.length >= 1;
      case 2:  return pv.genres.length >= 2;
      case 3:  return pv.eras.length >= 1;
      case 4:  return pv.moods.length >= 2;
      case 5:  return pv.activities.length >= 1;
      case 6:  return !!pv.home_area;
      case 7:  return true;
      case 8:  return !!pv.host_personality;
      case 9:  return true;
      case 10: return true;
      default: return true;
    }
  }, [step, pv]);

  const next = async () => {
    if (!stepValid) {
      toast.warning("Pick at least the minimum to continue");
      return;
    }
    if (step < 10) { setStep((s) => s + 1); return; }
    // Save
    setSaving(true);
    stopPreview();
    try {
      const r = await axios.post(`${API}/users/preferences`, pv);
      setUser(r.data);
      toast.success(`Sab set, ${r.data.name}!`);
      navigate(consumeIntent() || "/", { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save preferences");
      await refresh();
    } finally {
      setSaving(false);
    }
  };

  const back = () => { if (step > 0) setStep((s) => s - 1); };

  const addArtist = () => {
    const t = artistDraft.trim();
    if (!t) return;
    if (pv.favorite_artists.length >= 10) {
      toast.warning("Up to 10, yaar"); return;
    }
    if (pv.favorite_artists.some((a) => a.toLowerCase() === t.toLowerCase())) {
      setArtistDraft(""); return;
    }
    setPv((p) => ({ ...p, favorite_artists: [...p.favorite_artists, t] }));
    setArtistDraft("");
  };

  const progress = (step / 10) * 100;

  return (
    <div className="auth-shell wizard-shell" data-testid="onboarding-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="wizard-head">
        <div className="auth-brand">
          <span className="brand-dot" />
          <BigFmBrand variant="inline" testId="onboarding-brand" />
        </div>
        <div className="wizard-step mono" data-testid="wizard-step">
          STEP {step + 1} / 11 · {STEP_TITLES[step].toUpperCase()}
        </div>
      </header>

      <div className="wizard-progress">
        <div className="wizard-progress-bar" style={{ width: `${progress}%` }} />
      </div>

      <main className="wizard-main">
        {step === 0 && (
          <section className="step-section" data-testid="step-welcome">
            <h1 className="step-title">Welcome{city ? `, ${city}` : ""}.</h1>
            <p className="step-lede">
              A few quick questions — then non-stop music. 30 seconds, max.
              We’ll tune FUUSIC to the languages and vibe you choose.
            </p>
            <div className="welcome-bullets">
              <div className="welcome-bullet"><span className="mono num">01</span> Pick languages, genres &amp; moods you like</div>
              <div className="welcome-bullet"><span className="mono num">02</span> Pick your RJ (or let us choose)</div>
              <div className="welcome-bullet"><span className="mono num">03</span> Press ON AIR. Music on.</div>
            </div>
          </section>
        )}

        {step === 1 && (
          <section className="step-section">
            <h1 className="step-title">What do you listen to?</h1>
            <p className="step-lede">Pick your languages (min 1). FUUSIC shows content in these — English by default. You can change this anytime in Profile.</p>
            <ChipGrid options={LANGUAGES} selected={pv.languages} onToggle={toggle("languages")}
                      data-testid="step-languages" />
          </section>
        )}

        {step === 2 && (
          <section className="step-section">
            <h1 className="step-title">Which genres hit the spot?</h1>
            <p className="step-lede">Pick at least 2.</p>
            {recommendedGenres.length > 0 && (
              <div data-testid="step-genres-recommended" style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1,
                              textTransform: "uppercase", color: "#c084fc", marginBottom: 8 }}>
                  ★ Popular on FUUSIC
                </div>
                <ChipGrid options={recommendedGenres} selected={pv.genres} onToggle={toggle("genres")}
                          data-testid="step-genres-recommended-chips" />
              </div>
            )}
            <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1,
                          textTransform: "uppercase", color: "#8b93b0", marginBottom: 8 }}>
              All genres
            </div>
            <ChipGrid options={GENRES} selected={pv.genres} onToggle={toggle("genres")}
                      data-testid="step-genres" />
          </section>
        )}

        {step === 3 && (
          <section className="step-section">
            <h1 className="step-title">Which era is your jam?</h1>
            <p className="step-lede">Pick at least 1.</p>
            <ChipGrid options={ERAS} selected={pv.eras} onToggle={toggle("eras")}
                      data-testid="step-eras" />
          </section>
        )}

        {step === 4 && (
          <section className="step-section">
            <h1 className="step-title">What mood do you want?</h1>
            <p className="step-lede">Pick at least 2 — we'll mix them through the day.</p>
            <ChipGrid options={MOODS} selected={pv.moods} onToggle={toggle("moods")}
                      data-testid="step-moods" />
          </section>
        )}

        {step === 5 && (
          <section className="step-section">
            <h1 className="step-title">When do you tune in?</h1>
            <p className="step-lede">We'll adapt the energy to the time of day.</p>
            <ChipGrid options={ACTIVITIES} selected={pv.activities} onToggle={toggle("activities")}
                      data-testid="step-activities" />
          </section>
        )}

        {step === 6 && (
          <section className="step-section">
            <h1 className="step-title">
              Which FUUSIC are you on?
            </h1>
            <p className="step-lede">
              Pick your market — Dubai or DFW. Voices, drops &amp; offers tune accordingly.
            </p>
            <div className="area-grid" data-testid="step-market-grid">
              {MARKETS.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  className={`area-card ${pv.market === m.id ? "is-on" : ""}`}
                  onClick={() => setPv((p) => ({
                    ...p,
                    market: m.id,
                    city: m.id === "dubai" ? "Dubai" : "DFW",
                    home_area: null,  // clear area on market switch
                  }))}
                  data-testid={`market-card-${m.id}`}
                  style={{ minHeight: 64 }}
                >
                  {pv.market === m.id && <Check size={14} />}
                  <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
                    <span style={{ fontSize: 14, fontWeight: 700 }}>{m.flag} {m.label}</span>
                    <span style={{ fontSize: 11, opacity: 0.65, marginTop: 2 }}>{m.blurb}</span>
                  </span>
                </button>
              ))}
            </div>

            <h2 className="step-sub" style={{ marginTop: 28, fontSize: 16, opacity: 0.85 }}>
              And which area in {pv.market === "dfw" ? "DFW" : "Dubai"}?
            </h2>
            <div className="area-grid" data-testid="step-area-grid">
              {(pv.market === "dfw" ? DFW_AREAS : DUBAI_AREAS).map((a) => (
                <button
                  key={a}
                  type="button"
                  className={`area-card ${pv.home_area === a ? "is-on" : ""}`}
                  onClick={() => setPv((p) => ({ ...p, home_area: a }))}
                  data-testid={`area-card-${a.toLowerCase().replace(/ /g, "-")}`}
                >
                  {pv.home_area === a && <Check size={14} />}
                  <span>{a}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        {step === 7 && (
          <section className="step-section">
            <h1 className="step-title">Favorite artists?</h1>
            <p className="step-lede">
              Up to 10. We use these as <em>hints</em>, not exact picks.
              (FUUSIC is non-interactive radio — server picks the queue.)
            </p>
            <div className="artist-input-row">
              <input
                type="text"
                value={artistDraft}
                onChange={(e) => setArtistDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addArtist(); } }}
                placeholder="Type an artist and hit Enter"
                className="artist-input"
                data-testid="artist-input"
              />
              <button type="button" className="add-pill" onClick={addArtist} data-testid="artist-add-btn">
                <Plus size={14} /> ADD
              </button>
            </div>
            <div className="artist-chips" data-testid="artist-chips">
              {pv.favorite_artists.map((a) => (
                <span key={a} className="artist-chip" data-testid={`artist-chip-${a}`}>
                  {a}
                  <button type="button" onClick={() =>
                    setPv((p) => ({ ...p, favorite_artists: p.favorite_artists.filter((x) => x !== a) }))
                  } aria-label={`Remove ${a}`}>
                    <X size={12} />
                  </button>
                </span>
              ))}
              {pv.favorite_artists.length === 0 && (
                <span className="artist-empty">Nothing yet — totally optional.</span>
              )}
            </div>
          </section>
        )}

        {step === 8 && (
          <section className="step-section">
            <h1 className="step-title">Pick your RJ</h1>
            <p className="step-lede">Tap the 5s preview button to hear each voice.</p>
            <div className="voice-grid" data-testid="step-voices">
              {VOICES.map((v) => (
                <VoiceCard
                  key={v.id}
                  voice={v}
                  selected={pv.host_personality === v.id}
                  onSelect={(id) => setPv((p) => ({ ...p, host_personality: id }))}
                  currentPlaying={previewing}
                  onPreview={playPreview}
                />
              ))}
            </div>
          </section>
        )}

        {step === 9 && (
          <section className="step-section">
            <h1 className="step-title">Explicit content?</h1>
            <p className="step-lede">
              Play songs with adult language? Default is off — toggle on if you don't mind it.
            </p>
            <label className="big-toggle" data-testid="explicit-toggle">
              <input
                type="checkbox"
                checked={pv.explicit_ok}
                onChange={(e) => setPv((p) => ({ ...p, explicit_ok: e.target.checked }))}
                data-testid="explicit-checkbox"
              />
              <span className="toggle-track" />
              <span className="toggle-label">
                {pv.explicit_ok
                  ? <>Explicit ON · we'll include everything that fits your taste</>
                  : <>Explicit OFF · clean-ish radio only</>}
              </span>
            </label>
          </section>
        )}

        {step === 10 && (
          <section className="step-section" data-testid="step-done">
            <h1 className="step-title">Sab set, {user?.name || "yaar"}!</h1>
            <p className="step-lede">
              Aapka personalized FUUSIC ready hai. Tap below to start listening.
            </p>
            <div className="summary-grid" data-testid="summary-grid">
              <SummaryRow label="LANGUAGES" value={pv.languages.join(" · ") || "—"} />
              <SummaryRow label="GENRES"    value={pv.genres.map(niceGenre).join(" · ") || "—"} />
              <SummaryRow label="ERAS"      value={pv.eras.join(" · ") || "—"} />
              <SummaryRow label="MOODS"     value={pv.moods.join(" · ") || "—"} />
              <SummaryRow label="WHEN"      value={pv.activities.join(" · ") || "—"} />
              <SummaryRow label="MARKET"    value={pv.market === "dfw" ? "🇺🇸 DFW" : "🇦🇪 Dubai"} />
              <SummaryRow label="AREA"      value={pv.home_area || "—"} />
              <SummaryRow label="RJ"        value={pv.host_personality} />
              <SummaryRow label="EXPLICIT"  value={pv.explicit_ok ? "ON" : "OFF"} />
            </div>
          </section>
        )}
      </main>

      <footer className="wizard-foot">
        <button
          type="button"
          className="wizard-back"
          onClick={back}
          disabled={step === 0 || saving}
          data-testid="wizard-back-btn"
        >
          <ChevronLeft size={16} /> BACK
        </button>
        <button
          type="button"
          className="wizard-next"
          onClick={next}
          disabled={!stepValid || saving}
          data-testid="wizard-next-btn"
        >
          {saving ? <Loader2 className="spin" size={18} />
            : (step === 10 ? <RadioIcon size={16} /> : <ChevronRight size={16} />)}
          <span>{step === 10 ? "START LISTENING" : "CONTINUE"}</span>
        </button>
      </footer>
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div className="summary-row">
      <div className="summary-label mono">{label}</div>
      <div className="summary-value">{value}</div>
    </div>
  );
}
