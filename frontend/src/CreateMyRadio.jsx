/** Phase 41 Session 1 + 1.7 + 3.A — Create-My-Radio wizard.
 *
 *  Personal flow: name → music taste → AI RJ → privacy → publish.
 *  Business flow: name → biz basics → hours → branding → music taste
 *                   → AI RJ → privacy → publish.
 *
 *  Step 0 (NEW S3.A): "Personal or Business?" choice card.
 *  Slug auto-derived from name server-side (S1.7). Logo/cover uploaded
 *  to Tigris via dedicated business endpoints after the draft saves.
 */
import React, { useState, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Radio as RadioIcon, Check, ChevronLeft, User, Briefcase,
  Image as ImageIcon, X } from "lucide-react";
import { API } from "@/AuthContext";
import BusinessHoursPicker from "@/components/BusinessHoursPicker";

const GENRES = ["pop", "indie", "bollywood", "electronic", "hip_hop",
                  "rock", "classical", "jazz", "punjabi"];
const MOODS  = ["energetic", "chill", "romantic", "party", "focus", "uplifting"];
const PERSONAS = [
  { id: "kishore_retro", label: "Kishore (Retro Hindi)" },
  { id: "raghav_hindi",  label: "Raghav (Modern Hindi)" },
  { id: "charlie_dj",    label: "Charlie (English DJ)" },
  { id: "aanya_hindi",   label: "Aanya (Bilingual)" },
];
const CATEGORIES = ["restaurant", "cafe", "club", "retail",
                       "salon", "gym", "other"];

const DEFAULT_HOURS = {
  mon: { open: "09:00", close: "18:00", closed: false },
  tue: { open: "09:00", close: "18:00", closed: false },
  wed: { open: "09:00", close: "18:00", closed: false },
  thu: { open: "09:00", close: "18:00", closed: false },
  fri: { open: "09:00", close: "18:00", closed: false },
  sat: { open: "10:00", close: "16:00", closed: false },
  sun: { open: null,    close: null,    closed: true  },
};

// Personal flow uses these 5 labels; business inserts 3 extra steps
// after Name.
const PERSONAL_STEPS = ["Name", "Music Taste", "AI RJ Persona",
                          "Privacy & Cover", "Review & Publish"];
const BUSINESS_STEPS = ["Name", "Business Basics", "Hours", "Branding",
                          "Music Taste", "AI RJ Persona",
                          "Privacy & Cover", "Review & Publish"];

function slugifyPreview(name) {
  const cleaned = (name || "").toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim().replace(/\s+/g, "-").replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (!cleaned || cleaned.length < 4) return "";
  return cleaned.slice(0, 50);
}

export default function CreateMyRadio() {
  const navigate = useNavigate();
  // Step -1 = choose page_type. Once chosen, flow starts at step 0.
  const [pageType, setPageType] = useState(null); // "personal"|"business"
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState({
    name: "", tagline: "", bio: "",
    genres: [], moods: [], persona_key: "kishore_retro",
    privacy: "public", is_public: true, cover_color: "#00d9ff",
    business_profile: {
      legal_name: "", display_name: "", category: "restaurant",
      address: "", city: "", country: "", postal_code: "",
      phone: "", website: "",
      hours: DEFAULT_HOURS,
      social_links: { instagram: "", facebook: "", tiktok: "", twitter: "" },
    },
  });
  const [logoFile, setLogoFile]   = useState(null);
  const [coverFile, setCoverFile] = useState(null);
  const [logoPreview, setLogoPreview]   = useState(null);
  const [coverPreview, setCoverPreview] = useState(null);
  const [stationId, setStationId] = useState(null);
  const [publishedSlug, setPublishedSlug] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const logoRef  = useRef(null);
  const coverRef = useRef(null);

  const isBiz = pageType === "business";
  const STEPS = isBiz ? BUSINESS_STEPS : PERSONAL_STEPS;
  // Step indices for business flow:
  //   0 Name · 1 BizBasics · 2 Hours · 3 Branding · 4 Music · 5 RJ
  //   · 6 Privacy · 7 Review
  // Personal: 0 Name · 1 Music · 2 RJ · 3 Privacy · 4 Review
  const slugPreview = useMemo(() => slugifyPreview(draft.name), [draft.name]);

  const update = (k, v) => setDraft(prev => ({ ...prev, [k]: v }));
  const updateBiz = (patch) => setDraft(prev => ({
    ...prev, business_profile: { ...prev.business_profile, ...patch } }));
  const updateSocial = (k, v) => updateBiz({
    social_links: { ...draft.business_profile.social_links, [k]: v } });
  const toggle = (k, v) =>
    setDraft(prev => ({ ...prev,
      [k]: prev[k].includes(v) ? prev[k].filter(x => x !== v)
                                  : [...prev[k], v].slice(0, 5) }));

  const pickLogo = (f) => {
    setErr(null);
    if (!f) { setLogoFile(null); setLogoPreview(null); return; }
    if (f.size > 2 * 1024 * 1024) { setErr("Logo must be ≤ 2 MB."); return; }
    setLogoFile(f);
    const r = new FileReader();
    r.onload = () => setLogoPreview(r.result);
    r.readAsDataURL(f);
  };
  const pickCover = (f) => {
    setErr(null);
    if (!f) { setCoverFile(null); setCoverPreview(null); return; }
    if (f.size > 5 * 1024 * 1024) { setErr("Cover must be ≤ 5 MB."); return; }
    setCoverFile(f);
    const r = new FileReader();
    r.onload = () => setCoverPreview(r.result);
    r.readAsDataURL(f);
  };

  const saveDraft = async () => {
    setBusy(true); setErr(null);
    try {
      const payload = { ...draft };
      if (isBiz) {
        payload.page_type = "business";
        // Strip the social_links into top-level keys the backend
        // already expects from the validator.
        payload.business_profile = { ...draft.business_profile };
        // Backend defaults display_name to legal_name if empty.
        if (!payload.business_profile.display_name) {
          payload.business_profile.display_name = draft.name;
        }
      } else {
        payload.page_type = "personal";
        delete payload.business_profile;
      }
      const r = await axios.post(`${API}/stations/draft`, payload,
                                          { withCredentials: true });
      setStationId(r.data.station_id);
      setPublishedSlug(r.data.slug);
      // For business flow, fire logo + cover uploads against the new slug.
      if (isBiz) {
        if (logoFile) {
          const fd = new FormData();
          fd.append("image", logoFile);
          await axios.post(`${API}/stations/${r.data.slug}/business_profile/logo`,
                              fd, { withCredentials: true,
                                    headers: { "Content-Type": "multipart/form-data" }});
        }
        if (coverFile) {
          const fd = new FormData();
          fd.append("image", coverFile);
          await axios.post(`${API}/stations/${r.data.slug}/business_profile/cover`,
                              fd, { withCredentials: true,
                                    headers: { "Content-Type": "multipart/form-data" }});
        }
      }
      setStep(s => s + 1);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      const field = e.response?.data?.detail?.field;
      setErr(field
        ? `${field}: ${e.response?.data?.detail?.message || code || "invalid"}`
        : (e.response?.data?.detail?.message || `Could not save draft (${code || "error"}).`));
    } finally { setBusy(false); }
  };

  const publish = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/stations/${stationId}/publish`, {},
                              { withCredentials: true });
      // Phase C — kick off cover-art persistence based on the user's
      // chosen source.  Fire-and-forget for AI gen (the grid shows a
      // "Generating cover…" pill until /artwork/status flips complete);
      // synchronous upload for the uploaded path so the user lands on
      // the station page with the cover already visible.
      const src = draft.artwork_source || "ai_generated";
      const slug = publishedSlug;
      try {
        if (src === "ai_generated" && slug) {
          axios.post(`${API}/stations/${slug}/artwork/generate`, {},
                          { withCredentials: true }).catch(() => {});
        } else if (src === "uploaded" && slug && coverFile) {
          const fd = new FormData();
          fd.append("file", coverFile);
          await axios.post(`${API}/stations/${slug}/artwork/upload`, fd,
                                          { withCredentials: true,
                                            headers: { "Content-Type": "multipart/form-data" }});
        }
        // "gradient_fallback" leaves cover_image_url null — no API call.
      } catch (_artErr) {
        // Non-fatal — the user can still re-roll from Station Edit later.
      }
      navigate(`/r/${publishedSlug}`);
    } catch {
      setErr("Publish failed.");
    } finally { setBusy(false); }
  };

  // Validation: business basics step requires legal_name+address+city+country.
  const stepValid = () => {
    if (pageType == null) return false;
    if (step === 0)  return draft.name && slugPreview.length >= 4;
    if (!isBiz)      return true;
    if (step === 1)  {
      const bp = draft.business_profile;
      return bp.legal_name && bp.address && bp.city && bp.country;
    }
    return true;
  };

  const savePersonalStepIdx  = 3;  // Privacy step before Review
  const savePublishStepIdx   = 4;
  const saveBusinessStepIdx  = 6;
  const publishBusinessStepIdx = 7;

  // ---- page_type chooser screen (before the numbered wizard starts) -
  if (pageType == null) {
    return (
      <div data-testid="create-radio-wizard"
           style={{ maxWidth: 720, margin: "0 auto", padding: 24, color: "#fff" }}>
        <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                     fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
          <RadioIcon size={22} color="#00d9ff" /> Create My Radio
        </h1>
        <p style={{ color: "#9aa3af", fontSize: 14, marginBottom: 22 }}>
          What kind of radio do you want to build?
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
                       gap: 16 }}>
          <button type="button"
                  data-testid="wizard-page-type-personal"
                  onClick={() => setPageType("personal")}
                  style={{ ...choiceCardStyle, borderColor: "rgba(0,217,255,0.15)" }}>
            <User size={28} color="#00d9ff" style={{ marginBottom: 12 }} />
            <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px",
                          color: "#fff" }}>Personal</h3>
            <p style={{ color: "#9aa3af", fontSize: 13, lineHeight: 1.5,
                          margin: 0 }}>
              Your own radio station — pick a name, music taste, and AI RJ.
            </p>
          </button>
          <button type="button"
                  data-testid="wizard-page-type-business"
                  onClick={() => setPageType("business")}
                  style={{ ...choiceCardStyle, borderColor: "rgba(251,146,60,0.25)" }}>
            <Briefcase size={28} color="#fb923c" style={{ marginBottom: 12 }} />
            <h3 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 6px",
                          color: "#fff" }}>Business</h3>
            <p style={{ color: "#9aa3af", fontSize: 13, lineHeight: 1.5,
                          margin: 0 }}>
              In-store radio for restaurants, cafés, clubs, retail, salons,
              gyms. Includes hours, address, and verified-business chip.
            </p>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="create-radio-wizard"
         data-page-type={pageType}
         style={{ maxWidth: 720, margin: "0 auto", padding: 24, color: "#fff" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
        <RadioIcon size={22} color="#00d9ff" /> Create My Radio
        <span style={{ fontSize: 11, padding: "3px 8px", borderRadius: 999,
                        background: isBiz ? "rgba(251,146,60,0.18)"
                                          : "rgba(0,217,255,0.18)",
                        color: isBiz ? "#fb923c" : "#00d9ff",
                        fontWeight: 600, textTransform: "uppercase",
                        letterSpacing: "0.05em" }}>
          {pageType}
        </span>
      </h1>
      <p style={{ color: "#9aa3af", fontSize: 14, marginBottom: 22 }}>
        Step {step + 1} of {STEPS.length} · {STEPS[step]}
      </p>
      <div style={{ height: 4, background: "rgba(255,255,255,0.08)",
                     borderRadius: 2, marginBottom: 26 }}>
        <div style={{ height: 4, width: `${((step + 1) / STEPS.length) * 100}%`,
                       background: "#00d9ff", borderRadius: 2,
                       transition: "width 0.2s" }} />
      </div>
      {err && (
        <div data-testid="wizard-error"
             style={{ background: "rgba(239,68,68,0.1)", border: "1px solid #ef4444",
                       color: "#fca5a5", padding: "8px 12px", borderRadius: 6,
                       fontSize: 13, marginBottom: 16 }}>{err}</div>
      )}

      {step === 0 && (
        <div data-testid="wizard-step-name" style={{ display: "grid", gap: 14 }}>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 4 }}>
              {isBiz ? "Business display name" : "Station name"}
            </div>
            <input data-testid="wizard-name" value={draft.name}
                   onChange={e => update("name", e.target.value)}
                   placeholder={isBiz ? "The Karak Café" : "Friday Night Bollywood"}
                   style={inputStyle} />
            <div data-testid="wizard-slug-preview"
                 style={{ fontSize: 11, color: "#6b7280", marginTop: 6,
                          fontFamily: "monospace" }}>
              Your URL: <span style={{ color: "#9aa3af" }}>bigfm.app/r/</span>
              <span style={{ color: slugPreview ? "#00d9ff" : "#6b7280" }}>
                {slugPreview || "(type a name)"}
              </span>
            </div>
          </label>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 4 }}>Tagline (optional)</div>
            <input data-testid="wizard-tagline" value={draft.tagline}
                   onChange={e => update("tagline", e.target.value)} style={inputStyle} />
          </label>
        </div>
      )}

      {/* Business: step 1 = basics */}
      {isBiz && step === 1 && (
        <div data-testid="wizard-step-biz-basics"
             style={{ display: "grid", gap: 12 }}>
          <Field label="Legal name">
            <input data-testid="biz-legal-name"
                   value={draft.business_profile.legal_name}
                   onChange={e => updateBiz({ legal_name: e.target.value })}
                   placeholder="Karak Café LLC" style={inputStyle} />
          </Field>
          <Field label="Category">
            <select data-testid="biz-category"
                    value={draft.business_profile.category}
                    onChange={e => updateBiz({ category: e.target.value })}
                    style={inputStyle}>
              {CATEGORIES.map(c => <option key={c} value={c}
                style={{ background: "#0b0b0b" }}>{c}</option>)}
            </select>
          </Field>
          <Field label="Address">
            <input data-testid="biz-address"
                   value={draft.business_profile.address}
                   onChange={e => updateBiz({ address: e.target.value })}
                   placeholder="221B Baker Street" style={inputStyle} />
          </Field>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 120px", gap: 8 }}>
            <Field label="City">
              <input data-testid="biz-city"
                     value={draft.business_profile.city}
                     onChange={e => updateBiz({ city: e.target.value })}
                     style={inputStyle} />
            </Field>
            <Field label="Country">
              <input data-testid="biz-country"
                     value={draft.business_profile.country}
                     onChange={e => updateBiz({ country: e.target.value })}
                     style={inputStyle} />
            </Field>
            <Field label="Postal code">
              <input data-testid="biz-postal-code"
                     value={draft.business_profile.postal_code}
                     onChange={e => updateBiz({ postal_code: e.target.value })}
                     style={inputStyle} />
            </Field>
          </div>
          <Field label="Phone">
            <input data-testid="biz-phone"
                   value={draft.business_profile.phone}
                   onChange={e => updateBiz({ phone: e.target.value })}
                   placeholder="+971 50 123 4567" style={inputStyle} />
          </Field>
          <Field label="Website">
            <input data-testid="biz-website"
                   value={draft.business_profile.website}
                   onChange={e => updateBiz({ website: e.target.value })}
                   placeholder="https://example.com" style={inputStyle} />
          </Field>
        </div>
      )}

      {/* Business: step 2 = hours */}
      {isBiz && step === 2 && (
        <div data-testid="wizard-step-hours">
          <div style={{ fontSize: 13, color: "#9aa3af", marginBottom: 8 }}>
            Set business hours per day (24-hour). Toggle "Closed" for off-days.
          </div>
          <BusinessHoursPicker
            value={draft.business_profile.hours}
            onChange={(hours) => updateBiz({ hours })} />
        </div>
      )}

      {/* Business: step 3 = branding */}
      {isBiz && step === 3 && (
        <div data-testid="wizard-step-branding" style={{ display: "grid", gap: 14 }}>
          <Field label="Logo (square, ≤ 2 MB)">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button type="button" data-testid="biz-pick-logo"
                      onClick={() => logoRef.current?.click()}
                      style={btnSecondary}><ImageIcon size={14} /> Choose logo</button>
              <input ref={logoRef} type="file"
                     accept="image/png,image/jpeg,image/webp"
                     style={{ display: "none" }}
                     onChange={e => pickLogo(e.target.files?.[0])} />
              {logoPreview && (
                <div style={{ position: "relative" }}>
                  <img src={logoPreview} alt="logo preview"
                       style={{ width: 64, height: 64, objectFit: "cover",
                                 borderRadius: 8 }} />
                  <button type="button"
                          onClick={() => pickLogo(null)}
                          style={clearBtnStyle}><X size={10} /></button>
                </div>
              )}
            </div>
          </Field>
          <Field label="Cover (16:9, ≤ 5 MB)">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button type="button" data-testid="biz-pick-cover"
                      onClick={() => coverRef.current?.click()}
                      style={btnSecondary}><ImageIcon size={14} /> Choose cover</button>
              <input ref={coverRef} type="file"
                     accept="image/png,image/jpeg,image/webp"
                     style={{ display: "none" }}
                     onChange={e => pickCover(e.target.files?.[0])} />
              {coverPreview && (
                <div style={{ position: "relative" }}>
                  <img src={coverPreview} alt="cover preview"
                       style={{ width: 144, height: 81, objectFit: "cover",
                                 borderRadius: 8 }} />
                  <button type="button"
                          onClick={() => pickCover(null)}
                          style={clearBtnStyle}><X size={10} /></button>
                </div>
              )}
            </div>
          </Field>
          <div style={{ fontSize: 12, color: "#9aa3af", marginTop: 6,
                          fontWeight: 600 }}>Social links (optional)</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {["instagram", "facebook", "tiktok", "twitter"].map(k => (
              <input key={k} data-testid={`biz-social-${k}`}
                     value={draft.business_profile.social_links[k]}
                     onChange={e => updateSocial(k, e.target.value)}
                     placeholder={`${k} URL`} style={inputStyle} />
            ))}
          </div>
        </div>
      )}

      {/* Music taste step — index 1 personal, 4 business */}
      {((!isBiz && step === 1) || (isBiz && step === 4)) && (
        <div data-testid="wizard-step-music" style={{ display: "grid", gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Pick 1–5 genres</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {GENRES.map(g => (
                <Chip key={g} testId={`wizard-genre-${g}`}
                      on={draft.genres.includes(g)}
                      onClick={() => toggle("genres", g)}>{g}</Chip>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Pick 1–4 moods</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {MOODS.map(m => (
                <Chip key={m} testId={`wizard-mood-${m}`}
                      on={draft.moods.includes(m)}
                      onClick={() => toggle("moods", m)}>{m}</Chip>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* AI RJ step — index 2 personal, 5 business */}
      {((!isBiz && step === 2) || (isBiz && step === 5)) && (
        <div data-testid="wizard-step-persona" style={{ display: "grid", gap: 10 }}>
          <div style={{ fontSize: 13, color: "#9aa3af", marginBottom: 6 }}>
            Choose the AI RJ that hosts your station
          </div>
          {PERSONAS.map(p => (
            <button key={p.id} data-testid={`wizard-persona-${p.id}`}
                    onClick={() => update("persona_key", p.id)}
                    style={{ textAlign: "left", padding: 12, borderRadius: 10,
                             background: draft.persona_key === p.id ? "rgba(0,217,255,0.12)" : "rgba(255,255,255,0.04)",
                             border: `1px solid ${draft.persona_key === p.id ? "#00d9ff" : "rgba(255,255,255,0.05)"}`,
                             color: "#fff", fontSize: 14, cursor: "pointer" }}>
              {p.label}
              {draft.persona_key === p.id && <Check size={14} style={{ marginLeft: 8, color: "#00d9ff" }} />}
            </button>
          ))}
        </div>
      )}

      {/* Privacy step — index 3 personal, 6 business.  Phase C — extended
            with a Cover Art picker (AI / Upload / Gradient).  Default AI; the
            generation kicks off automatically on publish so the user lands
            on the station page with the cover already in flight. */}
      {((!isBiz && step === 3) || (isBiz && step === 6)) && (
        <div data-testid="wizard-step-privacy" style={{ display: "grid", gap: 14 }}>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 6 }}>Privacy</div>
            <select data-testid="wizard-privacy" value={draft.privacy}
                    onChange={e => {
                      const p = e.target.value;
                      setDraft(d => ({ ...d, privacy: p, is_public: p === "public" }));
                    }}
                    style={{ ...inputStyle, paddingRight: 28 }}>
              <option value="public"   style={{ background: "#0b0b0b" }}>Public — anyone can listen and find this in /community</option>
              <option value="unlisted" style={{ background: "#0b0b0b" }}>Unlisted — only accessible via direct link</option>
              <option value="private"  style={{ background: "#0b0b0b" }}>Private — only you can see and listen</option>
            </select>
          </label>
          {/* Phase C — Cover Art chooser.  Three mutually-exclusive options. */}
          <div data-testid="wizard-step-cover-art">
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 8 }}>
              Cover art · choose how your station looks on the grid
            </div>
            <div style={{ display: "grid",
                                gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
                                gap: 8 }}>
              {[
                {key: "ai_generated",      icon: "✨", label: "AI-generate",
                  hint: "OpenAI picks a vibe based on your name + genres."},
                {key: "uploaded",            icon: "📤", label: "Upload",
                  hint: "Bring your own image (JPG/PNG/WebP, ≤ 5 MB)."},
                {key: "gradient_fallback", icon: "🎨", label: "Gradient",
                  hint: "Stick with a simple gradient in your accent color."},
              ].map((opt) => {
                const active = (draft.artwork_source || "ai_generated") === opt.key;
                return (
                  <button key={opt.key} type="button"
                    data-testid={`wizard-cover-source-${opt.key}`}
                    data-active={active ? "true" : "false"}
                    onClick={() => update("artwork_source", opt.key)}
                    style={{ textAlign: "left",
                                  background: active ? "rgba(0,217,255,0.10)" : "rgba(255,255,255,0.04)",
                                  border: active ? "1px solid rgba(0,217,255,0.55)" : "1px solid rgba(255,255,255,0.08)",
                                  borderRadius: 10, padding: "10px 12px",
                                  color: "#fff", cursor: "pointer" }}>
                    <div style={{ display: "flex", alignItems: "center",
                                          justifyContent: "space-between",
                                          fontSize: 13, fontWeight: 700 }}>
                      <span><span style={{ marginRight: 6 }}>{opt.icon}</span>{opt.label}</span>
                      {active && <span style={{ color: "#00d9ff",
                                                                fontSize: 9, fontWeight: 700,
                                                                letterSpacing: "0.04em",
                                                                textTransform: "uppercase" }}>
                                              ✓ Selected
                                            </span>}
                    </div>
                    <div style={{ marginTop: 4, fontSize: 11, color: "#9aa3af" }}>
                      {opt.hint}
                    </div>
                  </button>
                );
              })}
            </div>
            {/* Option-specific UI under the row */}
            {(draft.artwork_source || "ai_generated") === "uploaded" && (
              <div style={{ marginTop: 12 }} data-testid="wizard-cover-upload-row">
                <input ref={coverRef} type="file"
                          accept="image/jpeg,image/png,image/webp"
                          data-testid="wizard-cover-upload-input"
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            if (!f) return;
                            if (f.size > 5 * 1024 * 1024) {
                              setErr("Image must be ≤ 5 MB.");
                              return;
                            }
                            setCoverFile(f);
                            setCoverPreview(URL.createObjectURL(f));
                          }} />
                {coverPreview && (
                  <img src={coverPreview} alt="cover preview"
                          data-testid="wizard-cover-upload-preview"
                          style={{ marginTop: 8, width: 120, height: 120,
                                          objectFit: "cover", borderRadius: 8 }} />
                )}
              </div>
            )}
            {(draft.artwork_source || "ai_generated") === "gradient_fallback" && (
              <label style={{ marginTop: 12, display: "block" }}
                        data-testid="wizard-cover-gradient-row">
                <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 6 }}>Gradient accent color</div>
                <input type="color" data-testid="wizard-color"
                          value={draft.cover_color}
                          onChange={e => update("cover_color", e.target.value)} />
              </label>
            )}
            {(draft.artwork_source || "ai_generated") === "ai_generated" && (
              <div style={{ marginTop: 12, padding: "10px 12px",
                                  borderRadius: 8,
                                  background: "rgba(0,217,255,0.06)",
                                  border: "1px solid rgba(0,217,255,0.20)",
                                  fontSize: 12, color: "#bff7ff" }}
                      data-testid="wizard-cover-ai-info">
                ✨ Your cover will be generated by OpenAI gpt-image-1 the
                moment you publish.  The grid shows a "Generating cover…"
                pill for ~30 seconds, then snaps to the real image.
                You can re-roll or replace it later from Station Edit.
              </div>
            )}
          </div>
          <label>
            <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 4 }}>Bio (optional)</div>
            <textarea data-testid="wizard-bio" value={draft.bio} rows={3}
                        onChange={e => update("bio", e.target.value)}
                        style={{ ...inputStyle, fontFamily: "inherit" }} />
          </label>
        </div>
      )}

      {/* Review step — index 4 personal, 7 business */}
      {((!isBiz && step === 4) || (isBiz && step === 7)) && (
        <div data-testid="wizard-step-review" style={{ padding: 16, borderRadius: 12,
                                                    background: "rgba(255,255,255,0.04)" }}>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{draft.name}</div>
          <div style={{ color: "#9aa3af", fontSize: 13, marginBottom: 10 }}>/r/{publishedSlug || slugPreview}</div>
          {isBiz && (
            <>
              <div style={{ fontSize: 13, marginBottom: 6 }}>
                {draft.business_profile.category} · {draft.business_profile.city}, {draft.business_profile.country}
              </div>
              <div style={{ fontSize: 12, color: "#fca5a5", marginBottom: 8 }}>
                Pending admin verification — your business will show a “verified” badge once approved.
              </div>
            </>
          )}
          <div style={{ fontSize: 13, marginBottom: 8 }}>Genres: {draft.genres.join(", ") || "—"}</div>
          <div style={{ fontSize: 13, marginBottom: 8 }}>Moods: {draft.moods.join(", ") || "—"}</div>
          <div style={{ fontSize: 13, marginBottom: 8 }}>Host: {draft.persona_key}</div>
          <div style={{ fontSize: 13 }}>{
            draft.privacy === "public"   ? "🌍 Public station"
            : draft.privacy === "unlisted" ? "🔗 Unlisted — link-only access"
                                              : "🔒 Private — only you"
          }</div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 26 }}>
        {step > 0
          ? <button data-testid="wizard-back" onClick={() => setStep(s => s - 1)}
                     style={btnSecondary}>
              <ChevronLeft size={14} /> Back
            </button>
          : <button data-testid="wizard-back-to-type"
                     onClick={() => setPageType(null)}
                     style={btnSecondary}>
              <ChevronLeft size={14} /> Change type
            </button>}
        {/* Next button: present on every step except the save & publish steps */}
        {((!isBiz && step < savePersonalStepIdx)
          || (isBiz && step < saveBusinessStepIdx)) && (
          <button data-testid="wizard-next" onClick={() => setStep(s => s + 1)}
                  disabled={!stepValid()}
                  style={btnPrimary}>Next →</button>
        )}
        {((!isBiz && step === savePersonalStepIdx)
          || (isBiz && step === saveBusinessStepIdx)) && (
          <button data-testid="wizard-save" onClick={saveDraft} disabled={busy}
                  style={btnPrimary}>{busy ? "Saving..." : "Save draft →"}</button>
        )}
        {((!isBiz && step === savePublishStepIdx)
          || (isBiz && step === publishBusinessStepIdx)) && (
          <button data-testid="wizard-publish" onClick={publish} disabled={busy}
                  style={btnPrimary}>{busy ? "Publishing..." : "Publish station 🎙️"}</button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: "block" }}>
      <div style={{ fontSize: 12, color: "#9aa3af", marginBottom: 4 }}>{label}</div>
      {children}
    </label>
  );
}

function Chip({ testId, on, onClick, children }) {
  return (
    <button data-testid={testId} onClick={onClick}
            style={{ background: on ? "#00d9ff" : "rgba(255,255,255,0.05)",
                     color: on ? "#0b0b0b" : "#cbd5e1",
                     border: "1px solid rgba(255,255,255,0.08)",
                     padding: "6px 12px", borderRadius: 16,
                     fontSize: 12, cursor: "pointer",
                     fontWeight: on ? 600 : 400 }}>{children}</button>
  );
}

const inputStyle = { width: "100%", padding: "8px 12px", borderRadius: 8,
                      background: "rgba(255,255,255,0.05)", color: "#fff",
                      border: "1px solid rgba(255,255,255,0.08)", fontSize: 14 };
const btnPrimary = { background: "#00d9ff", color: "#0b0b0b", border: "none",
                       padding: "10px 18px", borderRadius: 8, fontWeight: 600,
                       cursor: "pointer", fontSize: 14 };
const btnSecondary = { background: "rgba(255,255,255,0.06)", color: "#fff",
                          border: "1px solid rgba(255,255,255,0.08)",
                          padding: "8px 14px", borderRadius: 8, cursor: "pointer",
                          fontSize: 13, display: "inline-flex", alignItems: "center",
                          gap: 4 };
const choiceCardStyle = { padding: 24, borderRadius: 16,
                            background: "rgba(255,255,255,0.04)",
                            border: "2px solid rgba(255,255,255,0.06)",
                            color: "#fff", textAlign: "left", cursor: "pointer",
                            transition: "border-color 150ms" };
const clearBtnStyle = { position: "absolute", top: -6, right: -6,
                          background: "rgba(0,0,0,0.7)", color: "#fff",
                          border: "1px solid rgba(255,255,255,0.1)",
                          borderRadius: 999, width: 18, height: 18,
                          display: "grid", placeItems: "center",
                          cursor: "pointer" };
