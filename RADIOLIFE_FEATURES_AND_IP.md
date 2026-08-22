# RadioLife.app — Feature Inventory & IP Notes

> **Purpose:** A shareable summary of everything built so far (for ChatGPT/Claude/investors)
> plus candidate patentable ideas to reconfirm with a patent attorney.
> **Not legal advice.** Patentability depends on a prior‑art search + a registered patent attorney's review (novelty & non‑obviousness). Most items below are shared as *product context*; the "IP Candidates" section flags the few with a plausible novelty angle.

**Product in one line:** A cross‑platform (web + Expo mobile) radio + local‑rewards super‑app — YouTube‑style shell — where listening, local commerce, games/predictions, news and sponsored content all feed one rewards currency ("BigPoints").

**Stack:** FastAPI + MongoDB (shared backend), React web frontend, Expo/React Native mobile app. One `/api` contract serves both clients.

---

## 1. Feature Inventory (what's built)

### A. Radio & Audio
- 14 AI‑curated "channels" with cinematic cover art + host/RJ personas and segment metadata.
- 5,000+ imported live world radio stations (Radio Browser catalog) with search/browse/discover.
- 12 flagship stations with cinematic AI covers; "Your stations" shelf.
- Persistent slim player bar + "now playing" segment info; continue‑listening.
- **Station artwork system** (see IP Candidate #1): every station always has an on‑brand image via a layered resolver (owner → AI‑generated → real logo → deterministic genre‑coloured placeholder), on‑demand generation on first open, curated pre‑generation for top stations, flagship self‑heal, and owner generate/upload/clear controls.
- **Claim‑a‑station** workflow: a local owner can claim an imported/aggregated station and manage its branding/artwork.

### B. BigPoints — Unified Rewards Currency
- Single earn‑and‑redeem currency ("BigPoints", formerly BigCoin/BC) spanning listening, local commerce, trivia/predictions and sponsored actions.
- Wallet with balance, tier, and "Ways to Earn Today" entry point.

### C. Shop & Eat (Local Commerce Marketplace)
- Merchant marketplace profiles by category (restaurant, beauty/salons, fitness, retail) with covers, ratings, per‑venue BigPoints earn rates.
- Home venue shelf, **market‑scoped to the listener's detected city** (falls back gracefully so the shelf is never empty), sponsored‑first ordering.
- Live category chips (Eat / Salons / Fitness / Shops) that filter the shelf, with **sponsored** venue marking driven by real active promotions.
- "Order by chat" AI concierge (floating capsule) and Quick‑Buy sheet.
- Merchant dashboard, "Sell on RadioLife" onboarding, memberships, promotions/campaigns.

### D. Contextual On‑Air Offers (see IP Candidate #2)
- A merchant offer card synchronized to *what is currently playing* + listener location, docked above the player.

### E. Content / Clips
- "Clips" shelf ("RJ moments"), rendered as vertical 9:16 cards.
- **One sponsored clip** injected from a real active advertiser campaign, with branded AI cover art and a **Tap‑to‑Claim** flow that issues an in‑store redemption code (idempotent per user + campaign).

### F. Games & Engagement
- Predict & Win (curated prediction markets), Trivia (city‑aware categories), Spin & Win / Play hub.
- Curated question sets (AI‑generated questions filtered down to a hand‑picked, approved set).

### G. News
- Live headlines (NewsAPI), breaking‑news banner, **city/market‑aware** feed from a single geo source.

### H. Advertising / Monetization
- 7‑slot ad system: leaderboard + in‑feed banner slots, campaign‑driven (`ads_public`), CPM impression/click tracking.
- Sponsored stations, sponsored trivia, sponsored clips, featured‑near‑you placements.

### I. Design / UX Shell
- YouTube‑style app shell: top bar, left sidebar (web) / slide‑out drawer (mobile), sticky filter chips, card grammar (16:9 show cards, 9:16 clip cards, venue cards, news rows, station tiles).
- **Dual theme** (dark/light) via CSS variable tokens; light‑theme audited across deep pages (Trivia, Predict & Win).
- **Empty‑state doctrine:** shelves/nav items with no content are hidden, not shown as "nothing yet".

### J. Cross‑Platform
- Shared FastAPI/Mongo backend; one `/api` contract for web + mobile.
- Mobile (Expo) app: dark YouTube‑style Home with swipeable half‑card‑peek shelves, slide‑out drawer, darkened bottom tab bar.

### K. Location
- Single geo‑resolution source (IP/timezone) that unifies header/search city, news filter, venue market and trivia city.

### L. Admin / Merchant Tooling
- Admin approvals, trivia/station sponsorships, campaign management, seed/curation scripts.

### M. Third‑Party Integrations
- Stripe (payments), Mailgun (email), Tigris (object storage), NewsAPI (news), Gemini Nano Banana + OpenAI (AI image/text/TTS via Emergent LLM key), Emergent Push Notifications (SuprSend), Emergent‑managed auth.

---

## 2. IP Candidates (reconfirm with a patent attorney)

> Rank = my rough sense of how likely there's a defensible *novel system + method* angle. Everything needs a prior‑art search. Frame claims around the **method/pipeline**, not the idea.

### 🟢 Candidate 1 — Self‑healing station‑artwork pipeline *(strongest)*
**What:** A method for automatically populating and maintaining cover art across a large aggregated media catalog.
**Distinctive steps to claim:**
1. Deterministic, instant, genre‑coloured placeholder derived from station metadata → guarantees no blank state for N‑thousand items.
2. Layered art‑resolution priority (owner‑set → AI‑generated → real logo → placeholder) computed at read time.
3. On‑demand AI generation triggered on first view, keyed to station name/genre/description, **deduplicated/cached by prompt hash**, generated once per item, with failure‑reset so it retries later.
4. Proactive curated pre‑generation for top‑ranked items.
5. **Owner claim‑and‑override**: a rights‑holder claims an aggregated item and replaces/regenerates the art, flipping the resolver source.
**Why possibly novel:** the *combination* of instant deterministic placeholder + lazy per‑item AI backfill + claim‑based override as one self‑maintaining system. Prior art likely exists for AI image gen and for placeholders individually — the pipeline orchestration is the angle.

### 🟢 Candidate 2 — Playback‑synchronized contextual offer
**What:** Surfacing a merchant offer tied to the *currently playing* audio segment/station AND the listener's location, with claim + rewards tie‑in.
**Distinctive:** binding a redeemable local commerce offer to real‑time audio context (station/segment) + geo, not just to a page or user profile.

### 🟡 Candidate 3 — Cross‑domain unified rewards loop
**What:** One currency earned/redeemed across listening, local commerce, prediction games, and sponsored actions, with per‑venue dynamic earn rates.
**Caveat:** loyalty/points systems are heavy prior art. Only defensible if a specific *technical mechanism* (e.g., how earn rates are computed/settled across domains) is novel.

### 🟡 Candidate 4 — Single sponsored‑item injection into a personalized shelf
**What:** Deterministically inserting exactly one sponsored clip/venue into a personalized feed with campaign + geo targeting, marked, rate‑limited, and claim‑enabled.
**Caveat:** sponsored‑feed insertion is well‑trodden; needs a specific novel selection/placement method.

### 🟡 Candidate 5 — Claim‑a‑station rights + branding workflow
**What:** Letting a local owner claim an *aggregated third‑party* station record and take over its branding/artwork/offers, with approval + override propagation.
**Caveat:** "claim your business" flows exist (maps/directories); the audio‑station + artwork‑override specifics may narrow a claim.

### ⚪ Weak / product‑only (unlikely alone)
- Single geo‑source content unification (news/venues/trivia/distance).
- Dual‑theme token system; YouTube‑style shell; empty‑state doctrine.
- Currency rename / UI polish.

---

## 3. Suggested next steps for IP
1. Pick the top 1–2 candidates (1 and 2).
2. Run a prior‑art search (attorney or a patent‑search service).
3. File **provisional** applications (cheap, fast, 12‑month priority) with a registered patent attorney, focusing claims on the *method steps* above.
4. Keep an invention disclosure log (dates, diagrams, who conceived what).

*(Generated as a product/engineering summary. Not legal advice.)*
