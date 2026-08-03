# Phase 39 — Interactive AI RJ Personas + Location Intelligence + Commute Learning

**Status**: SPEC ONLY — deferred to a future session sequence. No code shipped.
**Supersedes**: prior `phase39_ai_rj_persona_companion.md` (renamed in this commit).
**Combines**: AI RJ Personas (front-facing premium experience) + Location Intelligence (background personalization + ad-intelligence layer). Both ship as one phase because the persona uses the location intelligence in its natural conversation.

## Goal
Two-track build, one phase:

**Track 1 — Front-facing premium AI RJ Personas**: users choose from original archetype hosts (Bambaiya Bhidu Style, Legendary Bollywood Baritone, etc.). The selected persona interacts throughout the session — intros songs, reacts to mood, suggests stations, announces games, reads news, runs trivia, chats naturally.

**Track 2 — Background location intelligence**: the app learns the user's common travel patterns, common commute times, common destinations, frequent roads/corridors, frequently visited businesses, and recurring places — conceptually similar to Google Maps Timeline but fully permission-based and user-controlled. The AI RJ uses this intelligence for personalized, contextual recommendations.

## Hard legal + safety rules

### AI RJ persona safety
- DO NOT clone, impersonate, or directly claim to be any real actor, actress, celebrity, or public figure unless the platform has documented rights + licensed voice permission.
- Personas are ORIGINAL ARCHETYPES inspired by broad entertainment styles, never identified as a specific real person.
- Forbidden labels: any "[Real person name] voice".
- Allowed archetype labels: Legendary Bollywood Baritone, Bambaiya Bhidu Style, Retro Angry Young Man, Romantic Bollywood Host, Smooth Hollywood Trailer Voice, British Spy Host, Punjabi Hype Man, South Indian Mass Hero, Desi Comedy Uncle, Luxury Lounge RJ, Gen Z Hinglish RJ, Cricket Commentary Host, News Anchor Pro, Tapori Mumbai Dost, Shaadi DJ Host, Devotional Morning Guide, Club Night Hype RJ.
- Safety filter on user input: requests like "make it sound like [celeb]" are BLOCKED and redirected to safe archetypes ("Try Bambaiya Bhidu Style — a playful Mumbai-style host with casual street flavor.").

### Location intelligence privacy
- Opt-in only. Never default-on.
- User-editable. Every detected place, route, and visit is renameable / hideable / deletable.
- User-deletable. Bulk delete + per-record delete + export-my-data must all work.
- Advertisers NEVER see individual user location history. Only privacy-safe aggregate segments.
- Incognito mode pauses all collection.
- Background-location requires a SEPARATE opt-in on top of basic location intelligence.

## 10 launch AI RJ personas (verbatim from user spec)

1. **Bambaiya Bhidu Style** — Mumbai street-smart, Hinglish ("bhidu", "apun", "kya scene", "mast"). Sample: "Arre bhidu, kya scene hai! Mood ko thoda mast banate hain. Aaj ka vibe full on filmy hai."
2. **Legendary Bollywood Baritone** — deep, dramatic, poetic. Sample: "Dosto, zindagi ke safar mein music hi woh saathi hai jo har mod par saath deta hai. Chaliye, is shaam ko yaadgaar banate hain."
3. **Retro Angry Young Man** — strong, intense. Sample: "System chahe traffic ka ho ya Monday ka, mood down nahi hone denge. Aaj music bolega."
4. **Smooth Hollywood Trailer Voice** — cinematic international. Sample: "In a city full of noise, one station brings the energy back. You're listening to BigFM AI."
5. **British Spy Host** — classy, witty Hinglish. Sample: "Good evening. The mission is simple: great music, sharp updates, and a few surprises along the way."
6. **Punjabi Hype Man** — party/gym/nightlife. Sample: "Oye hoye! Energy full charge kar lo, kyunki ab station ka mood seedha party mode mein jaa raha hai."
7. **Desi Comedy Uncle** — family-friendly. Sample: "Beta, traffic ka tension mat lo. Gaane suno, smile karo, aur coupon wallet check karna mat bhoolna."
8. **News Anchor Pro** — credible, sharp. Sample: "Good morning. Here are your top local updates, weather, and community headlines for the hour."
9. **Romantic Bollywood Host** — soft, poetic. Sample: "Kuch gaane sirf sune nahi jaate, mehsoos kiye jaate hain. This one is for the heart."
10. **Club Night Hype RJ** — fast, stylish. Sample: "City lights on, volume up. Tonight's vibe is Bollywood, bass, and full weekend energy."

## Persona × location-intelligence interaction examples

Morning: "Good morning, Sam. Looks like you usually head toward work around this time. Want your usual Morning Drive station?"
Evening: "Looks like you may be heading home soon. Want Evening Drive or Local Pulse news recap?"
Grocery: "You usually stop near this grocery area on Thursdays. There's a special deal nearby today. Want me to save it?"
Restaurant: "You often visit Frisco for lunch. One of your nearby restaurants has a 15% lunch offer."
Route ad: "You're often on this road around 6 PM. There's a dinner deal 4 minutes off your usual route."
Funny persona: "Arre bhidu, usual office route lag raha hai. Music chalu karun? Aur haan, grocery ka ek mast deal bhi route ke paas hai."

## Location intelligence — what gets learned

### Frequent places
home area (user-confirmed), work area (user-confirmed), gym, grocery stores, restaurants, cafes, schools, temples/community centers, theaters, clubs, malls, gas stations, offices, frequent entertainment locations, frequent local businesses.

### Travel patterns
common morning route, common evening route, common lunch route, common weekend route, common destination clusters, average departure time, average arrival time, days of week, route confidence score, destination confidence score, visit frequency.

### Road/corridor intelligence
Track common road corridors or zones the user travels through (NOT just exact points). Examples: "usually travels through Plano → Frisco", "often passes Legacy Drive", "often goes near Irving on weekends", "frequently drives near grocery corridor", "often visits restaurants near a specific shopping center".

### Business visit history
For each business or place visited (with permission): business name if matched, category, visit count, last visit, typical visit day/time, whether user redeemed offer there, whether user saved coupon there, whether user checked in there, whether user wants future recommendations.

### Recommendation intelligence
Use travel history to recommend: grocery deals, restaurant offers, coffee/breakfast, lunch deals, dinner deals, gas/car wash, gym/wellness, movie theaters, concerts/events, salons/spas, appointment offers, retail deals, product sampling, live trivia nearby.

## Permission levels

1. **Off** — no location personalization.
2. **While Using App** — location only during active app sessions.
3. **Background Location** — background location for commute and frequent-place detection. Requires OS permission.
4. **Full Personalization** — location + listening + wallet + offer engagement to personalize recommendations.

## Required user controls

enable location intelligence, enable background location, enable frequent place detection, enable business visit history, enable personalized route ads, enable AI recommendations from travel history, pause tracking, incognito mode, delete specific place, delete specific trip, delete all location history, disable all location learning, export my data.

## Frontend screens

### Persona track
1. Choose Your AI RJ (persona cards, sample audio, categories, free/premium labels)
2. Persona Detail (description, sample lines, sample audio, recommended stations, language support, try now)
3. AI RJ Chat (persona avatar, push-to-talk, text input, quick prompts, current station, action cards)
4. Premium Persona Trial (7-day free trial, unlocked personas, countdown, upgrade CTA)
5. Custom Persona Builder (style sliders, language mix, catchphrases, preview script, generate sample audio)
6. Persona Settings (selected persona, humor/energy/slang levels, language preference, reset to default)

### Location intelligence track
7. Location Intelligence Onboarding (explain benefits + permissions before any collection)
8. My Places & Routes (frequent places + usual routes summary)
9. Frequent Place Detail (confirm / rename / hide / delete / disable recommendations)
10. Usual Route Detail (route polyline, common days/times, enable/disable recommendations)
11. Business Visit History (businesses visited + offer history)
12. Privacy Control Center (toggle every collection layer, delete data, export data)
13. AI Memory Summary (what the AI RJ knows — usual station, usual commute time, frequent places, favorite businesses, preferred offer categories, favorite RJ persona)

### Cross-feature
14. AI RJ Greeting Card (likely destination prompt + suggested station + suggested offer + persona style)
15. Smart Recommendations Feed (grocery / lunch / dinner / events / live trivia / marketplace offers based on travel patterns)

## Database tables

### Persona-side
**AIPersonas**: id, name, slug, description, category, language, dialect_style, energy_level, humor_level, drama_level, formality_level, voice_provider, voice_id, sample_script, sample_audio_url, premium_only, vip_only, active, created_at
**UserAIPersonaSettings**: id, user_id, selected_persona_id, language_preference, humor_level, energy_level, slang_level, custom_catchphrases_json, blocked_topics_json, created_at, updated_at
**CustomAIPersonas**: id, user_id, name, description, style_prompt, language_mix, catchphrases_json, voice_id, approval_status, premium_required, created_at
**AIPersonaInteractions**: id, user_id, persona_id, session_id, user_message, ai_response_text, ai_response_audio_url, intent, action_taken, created_at
**PersonaTrialAccess**: id, user_id, trial_start, trial_end, status, converted_to_paid, created_at
**PersonaSafetyLogs**: id, user_id, requested_style, blocked_reason, suggested_safe_persona_id, created_at

### Location-side
**UserLocationPermissions**: id, user_id, location_intelligence_enabled, foreground_location_permission, background_location_permission, frequent_place_detection_enabled, business_visit_history_enabled, personalized_route_ads_enabled, ai_travel_recommendations_enabled, consent_version, consented_at, revoked_at, updated_at
**UserFrequentPlaces**: id, user_id, place_label, place_type, latitude, longitude, address_summary, google_place_id, business_id, category, confidence_score, visit_count, first_detected_at, last_detected_at, typical_visit_days_json, typical_visit_times_json, user_confirmed, hidden, deleted_at
**UserRoutePatterns**: id, user_id, route_name, origin_place_id, destination_place_id, route_polyline_hash, corridor_summary_json, days_of_week_json, typical_start_time, typical_end_time, average_duration_minutes, confidence_score, trip_count, last_detected_at, user_confirmed, recommendations_enabled, active
**UserTravelEvents**: id, user_id, event_type, latitude, longitude, timestamp, matched_place_id, matched_business_id, route_pattern_id, source, privacy_mode, deleted_at
**UserBusinessVisitHistory**: id, user_id, business_id, google_place_id, business_name, category, visit_count, first_visit_at, last_visit_at, typical_days_json, typical_times_json, coupon_saved_count, coupon_redeemed_count, checkin_count, recommendations_enabled, user_hidden, deleted_at
**UserCorridorPatterns**: id, user_id, corridor_name, corridor_geojson, common_days_json, common_times_json, trip_count, confidence_score, active
**TravelRecommendationEvents**: id, user_id, recommendation_type, source_pattern_type, source_pattern_id, business_id, campaign_id, offer_id, reason, ai_rj_persona_id, shown_at, saved_at, clicked_at, redeemed_at, dismissed_at
**RouteAdIntelligenceRules**: id, advertiser_id, business_id, campaign_id, target_pattern_type, target_category, radius_miles, corridor_enabled, daypart_id, time_window_json, weather_trigger_json, bid_amount, active
**LocationPrivacyAuditLogs**: id, user_id, action_type, data_type, record_id, performed_by, performed_at — NEVER user-deletable (compliance audit trail)

## Backend services

### Persona
**AIPersonaService**: listPersonas, getPersona, selectPersona, createCustomPersona, generatePersonaPrompt, checkCelebrityImitationRisk, suggestSafeAlternative
**AIInteractionService**: startPersonaSession, handleUserMessage, detectIntent, generatePersonaResponse, executeAction, generateVoiceAudio
**PersonaTrialService**: startTrial, checkTrialStatus, lockAfterTrial, upgradeToPremium
**SafetyService**: detectCelebrityName, blockDirectImitation, suggestArchetype, logSafetyEvent

### Location
**LocationPermissionService**: saveConsent, revokeConsent, checkPermissionLevel, auditPrivacyAction
**LocationIngestionService**: receiveLocationEvent, filterLowQualitySignals, respectPrivacyMode, storeTravelEvent, deleteTravelData
**FrequentPlaceDetectionService**: clusterLocationEvents, detectFrequentPlaces, matchGooglePlaces, matchInternalBusinesses, calculateConfidence, askUserToConfirm
**RoutePatternService**: detectRoutes, detectCommonCorridors, calculateTypicalTimes, updateConfidence, generateRouteSummary
**BusinessVisitService**: detectBusinessVisit, matchPlaceToBusiness, updateVisitHistory, respectUserHiddenPlaces
**AdIntelligenceService**: findEligibleCampaigns, matchTravelPatternToCampaign, rankRecommendations, generateReason, triggerAIRJRecommendation, logRecommendationEvent
**AIContextService**: prepareUserTravelContext, preparePersonaContext, generateMorningGreeting, generateOfferPrompt
**PrivacyExportDeleteService**: exportLocationHistory, deleteTrip, deletePlace, deleteBusinessVisit, deleteAllLocationHistory

## AI RJ × location intelligence prompt rules

Inputs into the persona prompt at runtime: user selected persona, time of day, daypart, likely route/destination, confidence score, frequent place suggestions, eligible ads/offers, user privacy settings.

Phrasing rules (CRITICAL — don't sound creepy):
- If confidence LOW → ask a neutral question ("What's the vibe today?")
- If confidence MEDIUM → suggest destination ("Heading the usual way?")
- If confidence HIGH → proactively offer ("Looks like you may be heading toward your usual morning route. Want me to start your favorite station?")

Good vs avoid:
- Good: "You often shop in this area. There's a grocery deal nearby today."
- Avoid: "We know you go to this grocery every Thursday at 6:12 PM."
- Good: "Looks like you may be heading toward your usual morning route."
- Avoid: "I tracked you going to this exact store 14 times."

Never speak exact surveillance-like details unless the user is actively viewing the history screen.

## Advertiser targeting (privacy-safe segments only)

Advertisers CANNOT select or view individual users. They CAN target on privacy-safe aggregate segments:
- users who frequently pass nearby
- users who often visit this shopping corridor
- users with grocery visit patterns
- users with restaurant lunch patterns
- users near route during 12–2
- users likely commuting during morning drive
- users who have visited similar businesses
- users who saved but did not redeem offers
- users who frequently visit this category

Advertiser dashboard shows: estimated reachable audience, impressions, saves, redemptions, visits, aggregated route-based conversions. NO individual location history.

## MVP build scope

1. Location permission flow (consent screen with full disclosure)
2. While-using-app location events only (no background until separate opt-in)
3. Frequent place detection (clustering + confidence scoring)
4. Manual user confirmation of Home / Work / Favorite Places
5. Basic business visit history
6. Basic usual route pattern detection
7. My Places & Routes screen
8. Privacy delete controls (per-record + bulk + export)
9. Ad Intelligence matching frequent places → eligible campaigns
10. AI RJ greeting using likely destination
11. Offer recommendation based on common travel time + place category
12. NO background location until user explicitly enables it
13. Aggregated-only advertiser analytics
14. Persona library (10 launch personas)
15. Persona selection + push-to-talk chat
16. 7-day free trial + premium lock
17. Celebrity-imitation safety filter
18. Persona × location-intelligence merged greeting card

## Phase 2 (post-MVP deferrals)

- Background location collection
- Corridor detection (geojson zones, not just point clusters)
- Google Places API matching for richer business identification
- Richer route history (multi-stop trips, recurring trip detection)
- Push reminders (e.g. "your usual evening route in 10 min")
- Advanced advertiser route segments (sub-corridor targeting, time-of-day clustering)
- AI prediction confidence (per-trip prediction with confidence bands)
- Cross-day/cross-time pattern learning
- Custom Persona Builder UI (premium/VIP)
- Mobile mirror of all persona + privacy screens
- Voice-cloned premium personas (with documented user consent for voice profile use)

## Implementation notes for the future building agent

- **Reuse existing infra**: `services/object_storage.py` (Tigris) for sample/response audio. Existing ElevenLabs client (Phase 36c provisioned). Existing Mailgun client for privacy-export-ready notifications.
- **Voice budget**: each of 10 launch personas needs a distinct ElevenLabs `voice_id`. Confirm voice slot quota covers 10 + premium voices BEFORE coding.
- **LLM safety**: celebrity-name detection should be LLM-assisted (regex misses creative spellings) and must run SERVER-SIDE before persona prompt assembly. Client cannot bypass.
- **PersonaSafetyLogs + LocationPrivacyAuditLogs**: never user-deletable. Compliance audit trail.
- **7-day trial**: per-user, NOT per-persona. Once consumed, only one trial reset allowed per 365 days (anti-abuse).
- **Location ingestion**: throttle + dedupe. A noisy GPS pin every 2 seconds bloats the events table. Cluster on the device + send batched samples; server-side filterLowQualitySignals drops dupes within 100m / 60s windows.
- **Place clustering**: use a simple DBSCAN-on-grid pass for MVP — no ML model needed. Cluster threshold: 5+ visits within ~150m radius across ≥3 different days = candidate frequent place. User must confirm before it becomes active.
- **Confidence scoring**: linear combination of visit_count, recency, day-of-week consistency, time-of-day consistency. Normalize 0-1. Show as 3-bucket (Low/Medium/High) in the UI — never expose the raw number.
- **Privacy mode (incognito)**: when ON, LocationIngestionService MUST drop events at the receive boundary — never write them with a flag. Stricter than just hiding.
- **Aggregate-only advertiser view**: enforce on the BACKEND. Frontend cannot be trusted. Every advertiser-facing query must run through a `is_advertiser_safe_aggregation()` guard that returns 403 if the requested cut would expose individual rows.

## Estimated build size

- Persona MVP backend + frontend (web only): 2 sessions
- Location intelligence MVP backend + frontend (web only): 3 sessions
- Privacy controls + export/delete + audit log: 1 session
- Ad intelligence rules engine + advertiser dashboard updates: 1.5 sessions
- Mobile mirror of both persona + privacy screens via `e1_expo_frontend_dev`: 2 sessions

**Total: ~9-10 sessions to MVP.** Significantly larger than the prior persona-only scope. Do NOT bundle with any other phase.

## Pre-build user-side asks (block start)

Before this phase can begin:
- Google Maps Platform API key (Places + Geocoding minimum; Routes API + Weather API needed for Phase 2 corridor + weather-trigger features)
- Confirmation of ElevenLabs voice slot quota
- Privacy + consent copy review (legal review of the consent screen text is RECOMMENDED before live rollout)
- Region of operation confirmation (consent + retention rules vary materially between US, EU, India; spec is written generically but the consent copy + retention windows need to match the deployment region)
