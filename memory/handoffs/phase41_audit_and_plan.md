# Phase 41 — Audit + Session Plan

**Anchor**: HEAD `ee90ad6` · commit 105 · Phase 40 closed (locked sequence
Phase 23 → Phase 22e-stream → Phase 39 → Phase 40 all green).
**Status**: AUDIT ONLY — no code changes shipped from this doc.

Phase 41 brief covers seven product surfaces:

1. **Personal Radio Pages** — every listener gets a mini-station
2. **Influencer Radio Pages** — verified creators with monetization
3. **Business Radio Pages** — venues with check-ins + reviews
4. **Community / Group Radio Pages** — many-to-many shared stations
5. **Event Radio Pages** — time-bounded pop-up stations
6. **In-Store Business TV** — second-screen social feed
7. **Creator Revenue Share** — listener-time attribution + payouts

Plus the user's quick ask: **Home page radio-by-category browsing**.

---

## 1. Audit — what's already shipped vs net-new

### 1.1 Game Wizard (Phase 23) → "Create My Radio" wizard
- **Reusable**: 9-step game wizard pattern (in `routes/games_v2.py` and
  `frontend/src/components/games/wizard/...`). Draft → preview → submit
  → moderation queue → approve.
- **Pattern-match for Phase 41**: a "Create My Radio" wizard can copy the
  draft-save-resume pattern, the moderation-queue handshake, and the
  step-by-step React shell.
- **Net-new**: station-specific fields (persona pick, music seed
  tracks/artists, language mix, cover art, slug uniqueness check).

### 1.2 Persona library + AI RJ personas (Phase 39 S2) → station hosts
- **Reusable**: `services/persona_service.py`, `routes/personas.py`,
  `PersonaLibrary.jsx`, the VOICE_REGISTRY constants, the persona × location
  greeting system (Phase 39 S6).
- **Direct fit**: every user-owned station picks 1–N personas from the
  library exactly as admin channels already do (see `channels.py:hosts[]`).
- **Net-new**: persona-per-station binding storage on the new
  `CommunityRadioStations` collection.

### 1.3 Channel registry + radio engine → user-owned channels
- **Today**: `CHANNELS: List[dict]` in `channels.py` is a hardcoded array
  of 12 admin-curated stations. Engine reads `channel_doc` and runs music
  clock rotation + RJ stitching.
- **Net-new**: Mongo-backed `community_radio_stations` collection that the
  channel resolver can MERGE with `CHANNELS` (admin-curated first, then
  user stations queried lazily). Engine code itself is mostly reusable —
  it operates on a channel dict, doesn't care where it came from, as long
  as music_clock + hosts + filters are populated.
- **Risk**: see §2.1 below — multi-tenant queue isolation at scale.

### 1.4 Podcast Creator Network (Phase 36) → social pages substrate
- **Reusable** (significant overlap):
  - `podcast_creators` collection (display_name, application_status,
    approved_by/at, public profile)
  - `podcast_followers` collection (one row per follow)
  - Approval workflow via `submit_creator_application` →
    `approve_creator` in `services/podcasts.py`
  - Tigris object storage for media uploads
  - `services/moderation.py` (OpenAI `omni-moderation-latest`) — already
    wired for audio + text
  - Frontend `Creator.jsx`, `CreatorChannelSettings.jsx`,
    `CreatorFunnelDashboard.jsx`, `Podcasts.jsx`
- **Decision flag**: should Phase 41 SocialPages be a NEW concept that
  sits alongside `podcast_creators`, or should we EXTEND
  `podcast_creators` into a unified "creator profile" model? Recommend
  **merge** — single creator table with a `page_type ∈ {podcast,
  personal_radio, influencer_radio, business, community, event}`
  discriminator and shared follower/notification plumbing. Saves
  ~30% of the Phase 41 scope.

### 1.5 Wallet + Stripe Connect Express → creator payouts
- **Reusable**: `services/stripe_client.py:create_express_account()` and
  `create_account_link()` already exist (and tested in Phase 36e).
- **Net-new**: `creator_payouts` collection + attribution math service
  (see §2.4) + monthly payout cron + 1099/tax-form metadata stub.

### 1.6 Social Passport (already shipped) → badges
- **Reusable**: badge engine + Social Passport UI; `services/badges.py`
  and `services/badge_engine.py` already exist.
- **Net-new**: badge taxonomy entries for `top_fan`, `early_follower`,
  `super_listener`, `verified_business_visitor` etc.

### 1.7 Admin moderation surface (Phase 23 S5) → SocialModerationLogs
- **Reusable**: `services/games_v2_audit_log.py` taxonomy pattern,
  `AdminPodcasts.jsx` approval queue UI, `services/moderation.py`
  pipeline (AI moderation via OpenAI).
- **Net-new**: `social_moderation_logs` and `business_page_moderation_rules`
  collections; a unified `/admin/social` queue that pulls posts/photos
  across all six page types.

### 1.8 Route patterns + business visits (Phase 39 S6) → check-in posts
- **Reusable**: `UserBusinessVisits` already records venue visits with
  consent gates. A business "verified check-in" badge on social posts
  can be issued by joining `UserBusinessVisits` ∩ `SocialPosts.business_id`.
- **Privacy**: must respect existing `users.location_consent_level >= 3`
  gate; the cross-link is server-side and never exposes user identity to
  the business owner.

### 1.9 Venue TV Hub (Phase 16c) → In-Store Business TV
- **Reusable** (major win): `services/venue_tv_hub.py` already implements
  the in-memory venue → TV WebSocket fan-out. `routes/venues.py` already
  exposes:
  - `POST /api/venue/{id}/tvs/pair` → 6-digit pairing code
  - `POST /api/tv/claim` → exchanges code for long-lived `tv_token`
  - `tv_pairings`, `venues`, `business_offers` collections
- **Net-new**: queue protocol extension to broadcast SocialPost cards (not
  just trivia announcements), TV-side React kiosk layout, content-rotation
  scheduler.

### 1.10 Existing `/api/channels` listing endpoint
- `server.py:1885 async def channels_list()` returns flat list.
- Frontend `Home.jsx` line 314 renders a horizontal "Discover" scroller —
  **no category grouping today**. The user's quick ask is unmet.

### 1.11 Compliance (non-interactive + skip caps)
- `SKIP_LIMIT`, `SKIP_WINDOW_SEC`, `banned_artists_albums` already enforce
  the non-interactive radio rules at the engine boundary. User-owned
  stations MUST inherit these — no per-station override. Easy: enforce at
  the queue-build layer, not the channel-doc layer.

---

## 2. Top 5 risks worth a Phase 41 Session 0 POC

### 2.1 Multi-tenant station queue isolation @ scale
**Risk**: If 10k listeners each spin up a personal station with its own
music clock + RJ queue, the cron + cache layer may explode. Today the 12
admin channels share a small set of pre-warmed clip files.

**POC needed**: build 100 synthetic stations, measure cron warm-up time
+ Mongo working-set growth + Tigris bucket usage. Decide between
(a) lazy on-demand warm-up per listener session, (b) shared clip pool
addressed by music-clock hash, or (c) hybrid.

### 2.2 Non-interactive compliance enforcement on user-owned stations
**Risk**: A user could pick a 30-track seed of one artist and effectively
build an interactive on-demand playlist. Legal blast radius.

**Mitigation (no POC needed, just discipline)**: enforce at queue-build:
- max 4 tracks per artist per hour
- max 3 consecutive tracks from same album
- forced 30% catalog-discovery insertion every cycle

### 2.3 Business TV display protocol
**Risk**: WebSocket disconnects in stores w/ shaky wifi; Chromecast vs
browser kiosk vs Apple TV vs dedicated hardware. The Phase 16c TV Hub
already runs in memory — TVs lose state on backend redeploy.

**Decision needed (not POC)**: pairing-code-via-URL (recommend) + WS with
auto-reconnect + last-known-state cache in Mongo (re-hydrate on reconnect).

### 2.4 Revenue attribution math
**Risk**: Multi-creator overlap (listener follows 3 creators, hears 5
sponsored segments across 2 stations in an hour). Fraud (creator bots
self-listening). Attribution windows (post-stream conversions).

**POC needed**: build the attribution engine offline against a synthetic
listener log, validate the math, THEN integrate. Sessions 0 candidate.

### 2.5 Moderation throughput @ 1000+ posts/day
**Risk**: OpenAI moderation rate limits + human-review SLA. Phase 36's
podcast queue ~handful per day; Phase 41 can be 100x volume.

**Mitigation (built-in)**: AI auto-approve for obvious clean text;
human queue for borderline. Track SLA in a dashboard. Already shipped:
`services/moderation.py` produces a score — just need a threshold table.

---

## 3. Proposed session breakdown — 8 sessions for Phase 41 MVP

Modeled on Phase 39's 7-session pattern. The Phase 2 (mood voting,
collab sessions, top-fan badges, sponsored posts) deferred to **Phase 41M**.

### Session 0 (POC) — Multi-tenant station scale + attribution math
- **Goal**: prove the two biggest unknowns before any product code lands.
- **Risky parts**: §2.1 + §2.4
- **In scope**:
  - 100 synthetic stations smoke test (warm-up time, Mongo size,
    Tigris bucket cost)
  - Offline attribution engine prototype against a synthetic listener
    log; output a Markdown design doc.
- **Acceptance gates**:
  1. 100 stations cold-start < 60s total
  2. Per-station Mongo footprint < 50KB
  3. Attribution math design doc lands at `/app/memory/handoffs/phase41_s0_poc.md`
- **Deps**: none.

### Session 1 — Create-My-Radio wizard + listener Personal Radio Page UI
- **Goal**: Ship the MVP requirements #1–3 — any user can create a station
  and have a public listener page.
- **In scope**:
  - `community_radio_stations` collection (`station_id, owner_user_id,
    slug, page_type, persona_keys[], language_mix, seed_artists[],
    seed_tracks[], cover_color, created_at, status, …`)
  - `POST /api/stations/draft`, `POST /api/stations/publish` (with
    moderation), `GET /api/stations/:slug`
  - Channel resolver merges admin CHANNELS with community stations
  - Wizard React shell mirroring Phase 23 game wizard (steps: name +
    slug → persona pick → seed tracks → cover art → preview → publish)
  - Listener page `/r/:slug` — header card, persona, seed tracks
    summary, "Start listening" CTA wired into the existing radio engine
  - Compliance: §2.2 enforcement at queue-build
- **Acceptance gates**:
  1. User creates station via wizard; appears in `/api/stations/me`
  2. `/r/:slug` plays a valid stream with the chosen persona
  3. Skip cap + per-artist cap enforced (synthetic over-skip test)
  4. Slug uniqueness — duplicate slug returns 409
- **Deps**: Session 0 POC math validated.

### Session 2 — Social posts (text + photo) + reactions + comments + follows + notifications
- **Goal**: MVP requirements #4–6.
- **In scope**:
  - `social_posts {post_id, author_user_id, page_id, page_type, text,
    media_urls[], created_at, status}`
  - `social_reactions`, `social_comments`, `social_follows` (extend
    `podcast_followers` — see §1.4 decision)
  - Reuse `services/moderation.py` for text + image moderation
  - Notification fanout via existing push infra (`services/apns.py`,
    `services/engagement_push.py`)
- **Acceptance gates**:
  1. Post created → moderation pass → appears on author's page within 5s
  2. Follower receives notification within 30s
  3. Reactions + comments increment counters live
  4. Reported post hits `social_moderation_logs` (Session 6 will consume)
- **Deps**: Session 1 — needs page concept.

### Session 3 — Radio discovery by category + Community Radio surface
- **Goal**: Bundle the user's "home page by category" ask with the
  Community Radio discovery UI.
- **In scope**:
  - Add `category` field to channels + stations
  - `GET /api/stations/discover?category=…` returning grouped buckets
    (For You / Trending / Friends / Local / Influencer / Business)
  - Home page redesign: replace single "Discover" scroller with
    category-grouped scrollers (admin channels + community stations)
  - `/radio` page gets a sidebar filter by category
- **Acceptance gates**:
  1. Home renders ≥4 category groups (Top Picks, Friends, Local,
     Influencer/Business) each with horizontal scroller
  2. `?category=local` filters to listener's city (consent ≥ 2)
  3. Trending uses listener-minutes from last 24h
- **Deps**: Sessions 1+2 — needs stations to discover.

### Session 4 — Business Radio Pages + check-in/review posts + business moderation queue
- **Goal**: MVP requirements #7–8.
- **In scope**:
  - Business page subtype on `community_radio_stations` (page_type
    `business`)
  - Verified check-in via cross-join with `UserBusinessVisits` (§1.8)
  - Review posts (1–5 star + text + optional photo)
  - `business_page_moderation_rules` collection (block competitor
    mentions, profanity threshold, etc.)
  - Business owner dashboard: review responses, hide/report tools
- **Acceptance gates**:
  1. Business claims page via existing `businesses.owner_user_ids`
  2. Verified-visit badge appears only when consent ≥ 3 AND visit exists
  3. Owner can hide review → review removed from public, audit logged
- **Deps**: Sessions 1+2.

### Session 5 — Community / Group + Event Radio Pages + In-Store Business TV display
- **Goal**: MVP requirements #9–10. **Largest session — split if needed.**
- **In scope**:
  - Community pages (page_type `community`, many-to-many membership)
  - Event pages (page_type `event`, `starts_at`, `ends_at` window)
  - Extend Phase 16c TV Hub to broadcast SocialPost cards
  - TV-side React kiosk view (`/tv/business/:venue_id`) consuming
    the existing pairing flow
  - Content rotation scheduler (now-playing card → fresh review → check-in
    photo grid → loop)
- **Acceptance gates**:
  1. Event page auto-archives at `ends_at`
  2. Community page allows member-only posting + public listening
  3. Paired TV displays content within 5s of a new review hitting the queue
  4. TV reconnects automatically after backend redeploy (Mongo re-hydration)
- **Deps**: Sessions 1+2+4.

### Session 6 — Creator analytics + revenue attribution + payouts + admin social moderation
- **Goal**: MVP requirements #11–13.
- **In scope**:
  - `creator_listener_minutes` aggregate (rolls up daily from listen logs)
  - `creator_payouts` collection + attribution engine from Session 0 POC
  - Monthly payout cron, Stripe Connect Express transfer (reuse
    `services/stripe_client.py`)
  - Creator dashboard: minutes/$$ chart, follower growth, top posts
  - `/admin/social` queue (unified moderation across all page types)
  - SLA dashboard widget (oldest pending item, 24h target)
- **Acceptance gates**:
  1. Synthetic listener log → attribution engine outputs correct $$ split
  2. Payout cron writes `creator_payouts` row + initiates Stripe transfer
     in test mode
  3. Admin can approve/reject any social post; reasons land in
     `social_moderation_logs`
- **Deps**: Sessions 0 (math) + 1+2+4+5 (data to attribute).

### Session 7 — Phase 41 closure: polish, e2e tests, CURRENT_STATE rollup
- **Goal**: harden + close.
- **In scope**:
  - End-to-end Pytest suite ≥ +30 new tests
  - Frontend Jest ≥ +15
  - Real-data smoke test (≥10 stations, ≥100 posts, ≥3 paired TVs)
  - Update `/app/memory/CURRENT_STATE.md`, write Phase 41 closure section
  - Rotation reminder for any API keys touched
- **Acceptance gates**:
  1. All tests green
  2. CURRENT_STATE.md reflects Phase 41 SHA + closure note
  3. Phase 41M backlog written

---

## 4. Blockers / decisions for the user

These need an explicit thumbs-up before Session 1 starts:

1. **Page type discriminator**: merge with existing `podcast_creators`
   into a unified creator table (recommended), or new `social_pages`
   collection alongside it?
2. **TV pairing flow**: 6-digit code typed into TV's URL bar (matches
   existing Phase 16c venue TV pattern) — confirm OK, or do you want
   QR-scan instead?
3. **Revenue share split**: 50/50 platform/creator, 70/30 creator/platform,
   or other? Industry rough range: Spotify creator fund ~70/30, YouTube
   Partner Program 55/45. Recommend **70/30 creator/platform** for an
   acquisition-stage product.
4. **Page slug uniqueness**: global (Instagram-style — recommended) or
   per-city?
5. **In-store TV access tier**: paid business plan only, or free for any
   claimed venue? Recommend **free for any claimed venue** in MVP, gate
   advanced features (multi-screen, custom branding) behind paid tier
   later.
6. **Customer photo moderation SLA**: recommend 24h human-review target,
   AI auto-approve obvious clean photos within seconds. Confirm.
7. **Quick ask — home page by category**: bundle into Session 3 (clean,
   recommended) or ship as a 30-min pre-Session 1 patch on Home.jsx?

---

## 5. Top 5 reused-from-prior-phases callouts

1. **Phase 16c Venue TV Hub** is the single biggest reuse — already does
   WebSocket fan-out + pairing + tv_token auth. Phase 41 Session 5 just
   extends the payload contract.
2. **Phase 36 Podcast Creator Network** — `podcast_creators` +
   `podcast_followers` + approval workflow + Tigris uploads + RSS infra.
   Merge into unified creator profile.
3. **Phase 23 Games Wizard** — 9-step draft/preview/submit/moderate
   pattern + React shell. Copy-paste for Create-My-Radio.
4. **Phase 12c Moderation pipeline** (`services/moderation.py`) — OpenAI
   `omni-moderation-latest` already wired for text + image. Phase 41 just
   plugs in posts + reviews.
5. **Phase 36e Stripe Connect Express** — `create_express_account` +
   `create_account_link` already shipped + tested. Creator payouts just
   need attribution math + monthly transfer cron.

---

## 6. Top 5 risk register

| # | Risk | Mitigation | Session |
|---|---|---|---|
| R1 | Multi-tenant station scaling explodes Mongo / cron | POC at 100 stations; hybrid lazy warm-up | Session 0 |
| R2 | User-owned stations break non-interactive compliance | Enforce caps at queue-build, never per-station override | Session 1 |
| R3 | Revenue attribution math wrong (fraud, double-count, post-stream gaps) | Offline POC against synthetic log; fraud detection in Session 6 | Sessions 0 + 6 |
| R4 | Moderation queue overwhelmed | AI auto-approve threshold; SLA dashboard | Sessions 2 + 6 |
| R5 | Business TV connection drops mid-day | Mongo state hydration + auto-reconnect | Session 5 |

---

## 7. Estimated Phase 41 MVP cost

- **8 sessions** (Session 0 POC + Sessions 1–7).
- **Phase 2 deferred → Phase 41M**: mood voting, collaborative
  sessions, top-fan dynamic badges, sponsored posts, advanced analytics.

---

## 8. Quick-ask routing

**User's "home page radio by category" ask**:
- Cleanest home: **Session 3** (Community Radio discovery surface) —
  already requires category grouping for For You / Trending /
  Friends / Local / Influencer / Business buckets. Folds in for free.
- Hot-patch alternative: ~30 min change to `Home.jsx` to group the
  existing 12 admin channels by an inferred `category` field. Doable
  pre-Session 1 if the user wants instant visual progress, but the data
  model is incomplete (community stations don't exist yet, so the
  category surface will need a second pass in Session 3 anyway).
- **Recommendation**: defer to Session 3 unless the user explicitly asks
  for a pre-Session 1 hot patch.

---

## Halt — awaiting user review

No code shipped from this audit. Ready to start **Session 0 POC** the
moment the user confirms the §4 decisions.
