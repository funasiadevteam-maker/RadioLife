# Phase 39 — AI RJ Personas + Location Intelligence — Audit & Session Plan

**Status**: AUDIT-ONLY. No Phase 39 code shipped yet.
**Date**: 2026-06-07
**Spec source**: `phase39_ai_rj_persona_plus_location_intelligence.md`
**Pre-existing infra discovered**: substantial — significantly reduces net-new build.

---

## 1. Spec summary (one-screen reduction)

### Track 1 — Front-facing AI RJ Personas (premium)
- 10 launch archetype personas (Bambaiya Bhidu, Bollywood Baritone, Punjabi Hype Man, etc.).
- User picks a persona → it intros songs, runs trivia, announces games, chats naturally.
- Strict celebrity-imitation safety filter (LLM-assisted, server-side, non-bypassable).
- 7-day free trial → premium lock.
- Persona Library, Persona Detail, AI RJ Chat (push-to-talk), Custom Persona Builder (premium/VIP), Persona Settings screens.
- DB: `AIPersonas`, `UserAIPersonaSettings`, `CustomAIPersonas`, `AIPersonaInteractions`, `PersonaTrialAccess`, `PersonaSafetyLogs`.

### Track 2 — Background Location Intelligence
- Opt-in only, fully user-controlled, incognito mode.
- Learn: frequent places (home/work/gym/grocery), usual routes, road corridors, business visits.
- AI RJ uses signals for natural greetings ("looks like you may be heading toward your usual morning route").
- Privacy: per-record delete + bulk delete + export-my-data; advertisers only see aggregate segments.
- DB: `UserLocationPermissions`, `UserFrequentPlaces`, `UserRoutePatterns`, `UserTravelEvents`, `UserBusinessVisitHistory`, `UserCorridorPatterns`, `TravelRecommendationEvents`, `RouteAdIntelligenceRules`, `LocationPrivacyAuditLogs`.

### Phasing rule
Spec says **9-10 sessions to MVP**. Audit below adjusts to **7 sessions** (down from 10) due to existing infra leverage.

---

## 2. Existing infrastructure audit (what we already have)

### Backend services discovered
| File | Lines | Status / re-use |
|---|---|---|
| `backend/services/rj.py` | 274 | **Existing RJ engine** — generates RJ scripts + audio. Phase 39 plugs persona prompt + voice_id into the existing pipeline. **High re-use**. |
| `backend/services/personality_profiles.py` | 188 | **Existing personality profiles** — already seeds `rj_personality_profiles` collection with **daypart personalities** (Morning Drive, Lunch Rush, Evening Drive, Nightlife, Chill Late Night, Talk/News). Architecture mirrors what Phase 39 needs. **Phase 39 personas are a new dimension on top of daypart**, not a replacement. **Medium re-use** — same collection pattern + slug-indexed lookups + active flag + sample script + seed-on-boot. |
| `backend/services/maps_client.py` | **1111** | **Fully wired Google Maps integration**: `MapsClient` ABC + `MockMapsClient` + `GoogleMapsClient` + `probe_and_decide_client()` + caching + Haversine + polyline encode/decode + `seed_mock_places()`. **Phase 9 already shipped places/route capability**. Phase 39 location intelligence does NOT need to rebuild any Google Maps wiring. **Very high re-use**. |
| `backend/routes/commute.py` | 509 | **Existing commute routes** — Phase 9 saved-location flows. Origin/destination, route preview, active commute. **Phase 39 frequent-place + route-pattern services build on top, NOT a rewrite**. |
| `backend/services/triggers.py` | (exists) | **Existing trigger engine** — likely contains route-ad opportunity matching. Need to inspect for Phase 39 ad-intelligence rules integration. |
| `backend/services/local_commerce.py` | (exists) | **Existing local commerce DB** with `businesses` Mongo collection. Phase 39 BusinessVisitHistory matches against this. |
| `backend/routes/rj_quality.py` | (exists) | **Existing RJ quality control** — phase 39 PersonaSafetyLogs likely fits here. |
| `backend/models/rj.py` | (exists) | **Existing RJ models** — extend for persona fields. |
| `backend/services/station_ids.py`, `ads_seed.py`, `ai_ad_creator.py` | (exist) | **Already use ElevenLabs** — TTS pipeline + voice_id pattern proven. Phase 39 personas extend this. |

### Existing Mongo collections (relevant to Phase 39)
- `businesses` — local commerce DB (reuse for BusinessVisitHistory matching)
- `commute_sessions` — Phase 9 commute tracking (reuse pattern for travel_events)
- `rj_audios`, `rj_audio_qa` — RJ audio cache + QA flags
- `rj_personality_profiles` — **daypart** personalities seed (use same shape for personas)
- `rj_phrase_bank` — RJ phrase library
- `rj_game_mentions_log` — RJ → game cross-linking log
- `route_ad_decision_log`, `route_ad_opportunities` — **Phase 9c route-ad work already complete**
- `saved_locations` — user-saved home/work locations (Phase 9)

### Environment / keys (already wired)
- `ELEVENLABS_API_KEY` — set live, used in station_ids/ads/ai_ad_creator
- `GOOGLE_MAPS_API_KEY` — set live, used by `maps_client.py::GoogleMapsClient`
- Emergent LLM key (universal) — already wired for GPT-4o-mini in `services/rj.py`
- Tigris `object_storage.py` — for persona sample audio + response audio

### Frontend already present
| File | Re-use |
|---|---|
| `frontend/src/Commute.js` (723 lines) | Existing commute UI — Phase 39 Places/Routes screen builds on the same patterns + state management. |
| `frontend/src/AdminVoices.js` | Existing admin voice management — Phase 39 admin persona library reuses this surface. |
| `frontend/src/components/Phase18Home.jsx` | Existing card-grid + sonner toast pattern. |

---

## 3. Net-new work after re-use accounting

### Definitely net-new (no pre-existing code)
1. **`AIPersonas` collection + seed-on-boot** of 10 launch archetypes with ElevenLabs voice_ids
2. **`UserAIPersonaSettings` + `PersonaTrialAccess`** — premium trial lifecycle
3. **`PersonaSafetyLogs` + celebrity-imitation filter** — LLM-side classifier ("does this style request reference a real public figure?") with safe-archetype fallback
4. **Persona prompt assembler** — combines persona style + location intelligence + game/news state
5. **Listener-facing screens**: Choose Your AI RJ, Persona Detail, AI RJ Chat, Premium Persona Trial, Persona Settings (5 new pages)
6. **`UserLocationPermissions` consent flow** — 4-level permission ladder (Off / While Using / Background / Full)
7. **`UserFrequentPlaces` + DBSCAN-on-grid clustering job** — periodic batch over `commute_sessions` + new `UserTravelEvents`
8. **`UserRoutePatterns` detection job** — origin/destination pair clustering
9. **`UserBusinessVisitHistory`** — match place visits against existing `businesses` collection
10. **`UserTravelEvents` ingestion endpoint** — throttle + dedupe (drop within 100m / 60s windows)
11. **`UserCorridorPatterns`** — Phase-2 deferral per spec (do NOT build in MVP per the spec's section "Phase 2 deferrals")
12. **`LocationPrivacyAuditLogs`** — append-only compliance trail (NEVER user-deletable)
13. **`TravelRecommendationEvents`** — persona × location interaction logging
14. **`RouteAdIntelligenceRules`** — new advertiser-facing campaign matching layer (extension of `route_ad_decision_log`)
15. **Privacy Control Center screen** — toggle every collection layer + delete + export
16. **AI Memory Summary screen** — "what the AI RJ knows" transparency view
17. **AI RJ Greeting Card on home** — likely destination prompt + persona-styled greeting
18. **Smart Recommendations Feed** — grocery / lunch / dinner / events from travel patterns
19. **Aggregate-only advertiser endpoint guard** — `is_advertiser_safe_aggregation()` middleware

### Custom Persona Builder (premium/VIP)
Spec lists in MVP section but also calls it premium/VIP only. **Recommend deferring to a follow-up after MVP** since it requires custom voice_id provisioning per user.

---

## 4. Required integrations — status

| Integration | Status | Action |
|---|---|---|
| **OpenAI GPT-4o-mini** (persona prompt + celebrity classifier) | ✅ Already wired via Emergent LLM key in `services/rj.py` | Re-use |
| **ElevenLabs TTS** (10 persona voices) | ✅ API key set live | **Verify slot quota covers 10 distinct voice_ids**. Each persona needs its own voice_id assigned in dashboard OR generated via API. Spec says: "Voice budget: each of 10 launch personas needs a distinct ElevenLabs `voice_id`. Confirm voice slot quota covers 10 + premium voices BEFORE coding." |
| **Google Maps Places API** | ✅ `maps_client.py` proven for places + geocoding | Re-use |
| **Google Maps Routes API** | ⚠️ Used by `commute.py` (need to confirm Routes API is enabled on user's billing; Places-only billing won't return route polylines) | **Pre-build ask** — confirm Routes API enabled |
| **Tigris object storage** | ✅ `object_storage.py` (path-based upload, just shipped Phase 22e usage) | Re-use for persona sample audio + response audio |
| **Privacy export delivery** | ❌ Mailgun is MOCKED per CURRENT_STATE.md | **Block for "export my data"** — only if user wants emailed export. Workaround: in-app download link works without Mailgun. |

---

## 5. Proposed session breakdown (7 sessions, down from spec's 9-10)

### **Session 1 — POC: Celebrity-imitation safety + persona library seed** (POC-style)
- **Scope**: server-side LLM classifier ("does input X reference a real person?"), `AIPersonas` collection schema + seed-on-boot for the 10 archetypes, `PersonaSafetyLogs` (append-only), admin route `GET /api/admin/personas` + `POST /api/admin/personas/{slug}/test-classifier`.
- **Why POC first**: the celebrity-detection LLM call is the highest-risk path (false negatives = legal exposure). Validate the classifier shape + safe-archetype-suggestion fallback BEFORE building anything user-facing.
- **Deliverables**: `services/persona_service.py`, `services/persona_safety.py`, seed migration, admin-only test endpoint.
- **Acceptance gates**: 10 personas seeded; `POST /api/admin/personas/test-classifier` with "make it sound like [celeb]" returns `blocked=true` + suggested safe archetype; pytest covers 20+ classifier cases (celebrities, fictional characters, archetype names, ambiguous).
- **ElevenLabs**: voice_id assignment NOT in this session — slot quota check happens here as a prereq for Session 2.

### **Session 2 — Persona selection + AI RJ chat MVP**
- **Scope**: User-facing persona library screen + persona detail + selection flow + AI RJ Chat page with push-to-talk and quick-prompts. Persona prompt assembler combines persona style + current daypart personality (existing `rj_personality_profiles`) + station context.
- **Deliverables**: `GET /api/personas`, `POST /api/users/me/persona`, `POST /api/persona/chat` (LLM text + ElevenLabs audio), 3 new pages, `UserAIPersonaSettings` collection.
- **Acceptance gates**: pick persona → home screen RJ break uses that persona's voice + style; safety filter blocks "make it sound like X" both in chat and in custom persona inputs.

### **Session 3 — Premium trial + persona settings**
- **Scope**: 7-day trial lifecycle, premium lock after trial, persona settings (humor/energy/slang sliders), one-trial-per-365-days anti-abuse.
- **Deliverables**: `PersonaTrialAccess` collection, `POST /api/persona/trial/start`, scheduled job to flip trial→expired, premium gating on persona endpoints, settings screen.
- **Acceptance gates**: trial countdown UI, expired trial blocks persona-specific endpoints, anti-abuse reset works.

### **Session 4 — Location intelligence consent + event ingestion**
- **Scope**: 4-level permission ladder, consent screen, `UserTravelEvents` ingestion (throttle 100m/60s windows, drop in incognito), `UserLocationPermissions` collection, `LocationPrivacyAuditLogs` (append-only).
- **Deliverables**: `POST /api/location/consent`, `POST /api/location/events` (batched), Privacy Control Center screen, audit log endpoints.
- **Acceptance gates**: opt-out drops events at receive boundary (not stored-with-flag), audit log records every consent change, incognito truly stops ingestion.

### **Session 5 — Frequent place detection + My Places & Routes**
- **Scope**: DBSCAN-on-grid clustering job (cluster threshold = 5+ visits within ~150m across ≥3 days), `UserFrequentPlaces` collection with confidence buckets (Low/Med/High), Google Places match for business identification, user-confirm flow.
- **Deliverables**: clustering scheduled job, `GET /api/me/frequent-places`, `POST /api/me/frequent-places/{id}/confirm` (rename / hide / delete), My Places & Routes screen, Frequent Place Detail screen.
- **Acceptance gates**: synthetic event seed → cluster appears as candidate → confirm flips `user_confirmed=true` → hide makes it invisible to recommendations.

### **Session 6 — Route patterns + business visit history + persona × location merge**
- **Scope**: `UserRoutePatterns` (origin/destination pair clustering, typical days/times), `UserBusinessVisitHistory` matching against existing `businesses` collection, AI RJ greeting using likely destination + persona style.
- **Deliverables**: route detection job, `GET /api/me/routes`, Usual Route Detail + Business Visit History screens, AI RJ Greeting Card on home, persona prompt extended with location context (phrasing rules: low/med/high confidence variations).
- **Acceptance gates**: morning visit pattern → AI RJ says "looks like you may be heading the usual way?" in the user's persona voice; phrasing rules respected (no creepy "I tracked you 14 times" language).

### **Session 7 — Ad intelligence rules + advertiser dashboard + privacy export/delete**
- **Scope**: `RouteAdIntelligenceRules`, ad-eligibility matcher (frequent_place → eligible_campaigns), `TravelRecommendationEvents` logging, advertiser-facing aggregate-only segments (NEVER per-user), `is_advertiser_safe_aggregation()` guard, privacy export-my-data endpoint, bulk delete, AI Memory Summary screen.
- **Deliverables**: `/api/advertiser/segments/preview` (aggregate counts only), `/api/me/privacy/export` (JSON dump), `/api/me/privacy/delete-all`, advertiser dashboard updates, AI Memory Summary screen.
- **Acceptance gates**: advertiser endpoint returns 403 if requested cut would expose individual rows; export contains every collection layer; bulk delete is irreversible.

### **Mobile mirror (post-MVP, separate Phase 39M)**
Spec calls for "Mobile mirror of both persona + privacy screens via `e1_expo_frontend_dev`: 2 sessions". **Defer to Phase 39M** — web MVP must validate flows + privacy copy before duplicating to Expo.

---

## 6. Pre-build blockers / asks for user

| Blocker | Why it blocks | Recommended action |
|---|---|---|
| **ElevenLabs voice slot quota for 10 personas** | Each archetype needs a distinct `voice_id`. If quota is 3, can't ship all 10. | **User confirms slot count.** If <10, we ship 3-5 personas in launch + roadmap remaining for premium tier. |
| **Voice profiles created in ElevenLabs dashboard vs API-generated** | Dashboard route is more controllable; API route enables custom personas (premium feature). | **User decides**: dashboard for launch 10 (recommended), API for premium custom. |
| **Google Maps Routes API enabled on billing account** | `commute.py` uses Routes; if not billed, routes return mock polylines. Phase 39 corridor work (deferred to Phase 2) needs it. | **User checks Google Cloud Console billing → Routes API enabled?** |
| **Privacy + consent copy legal review** | Spec says "RECOMMENDED before live rollout". | **User opt: ship MVP with placeholder copy + visible "DRAFT" watermark, or block on legal review.** Recommend MVP-with-watermark to unblock build. |
| **Region of operation** | Consent + retention rules vary US/EU/India materially. | **User confirms primary region** (Dubai per current data? US per IP samples?). Default to GDPR-safe (EU-level retention) to over-comply. |
| **Mailgun activation for emailed privacy exports** | Optional — in-app download works without it. | Recommend deferring Mailgun unblock to a Phase 39 follow-up. In-app JSON download covers MVP requirement. |

---

## 7. Risk register

1. **Celebrity-imitation classifier accuracy** — false negatives = legal/IP exposure. Mitigated by Session 1 POC + 20+ test cases + admin retest endpoint + append-only `PersonaSafetyLogs`.
2. **Privacy mistakes** — incognito leak, advertiser-side individual exposure, deleted-but-still-in-backup. Mitigated by `is_advertiser_safe_aggregation()` guard (server-side, non-bypassable) + drop-at-receive-boundary in incognito + audit log on every collection action.
3. **ElevenLabs voice quota** — 10-voice launch may exceed slot count. Mitigated by quota check before Session 2.
4. **DBSCAN clustering performance** — running on every user every hour could be heavy. Mitigated by per-user incremental clustering + batch nightly recompute (similar to existing Phase 9 commute jobs).
5. **Location data exfiltration via aggregate segments** — small segment sizes can re-identify individuals. Mitigated by minimum segment size (≥20 users) enforced server-side.

---

## 8. Estimated session count vs spec

| | Sessions | Notes |
|---|---|---|
| Spec original | 9-10 | Assumes building from scratch |
| **After audit** | **7** | Heavy re-use of `maps_client.py`, `rj.py`, `personality_profiles.py`, `local_commerce.py`, existing `businesses` collection, existing `commute_sessions` pattern |
| Mobile mirror | +2 | Defer to Phase 39M |
| Phase-2 features | +N | Background location, corridor detection, advanced advertiser segments — spec explicitly defers |

---

## 9. Next action

**HALT.** Do NOT start Session 1 until user reviews this audit + confirms:
1. ElevenLabs voice quota for 10 personas
2. Google Maps Routes API billing state
3. Region of operation (drives consent copy)
4. Legal review path for privacy copy (block / placeholder)
5. Custom Persona Builder MVP-or-defer decision
