# RadioLife Ads API — Partner Reference (v1)

Programmatic access to RadioLife marketing inventory: **audio ads, display banners, sponsorships, programmatic (OpenRTB), and marketplace promotion**. External systems (ad agencies, brands, DSPs) integrate server‑to‑server.

- **Base URL:** `{BACKEND_URL}/api/v1`
- **Interactive docs (OpenAPI/Swagger):** `{BACKEND_URL}/api/v1/docs`
- **OpenAPI schema:** `{BACKEND_URL}/api/v1/openapi.json`

> Replace `{BACKEND_URL}` with your RadioLife host, e.g. `https://radiolife.app`.

---

## 1. Authentication

All endpoints (except `GET /`, `GET /docs`, `POST /oauth/token`) require an `Authorization: Bearer …` header, using **either** mechanism below. Credentials are managed in the RadioLife **Advertiser dashboard → API & Keys**, or by RadioLife ops.

### 1a. Partner API key (simplest)
```
Authorization: Bearer rlk_live_<id>.<secret>
```
- Format is `<key_id>.<secret>`. Only a salted hash of the secret is stored — **the secret is shown once**.
- `rlk_live_…` = production; `rlk_test_…` = sandbox.

### 1b. OAuth2 client‑credentials
Exchange a `client_id` / `client_secret` for a short‑lived access token:
```bash
curl -X POST "{BACKEND_URL}/api/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&scope=campaigns:read campaigns:write"
```
Response:
```json
{ "access_token": "eyJ…", "token_type": "Bearer", "expires_in": 1800, "scope": "campaigns:read campaigns:write" }
```
Then call the API with `Authorization: Bearer <access_token>`.

> **Never** embed a partner secret or `client_secret` in browser/mobile apps. They are confidential and belong on a trusted server.

### Scopes
`catalog:read`, `advertisers:read`, `advertisers:write`, `campaigns:read`, `campaigns:write`, `reports:read`, `funding:write`.
A `403 {"code":"insufficient_scope"}` is returned when a credential lacks the required scope.

### Environments (LIVE vs SANDBOX)
Use a **sandbox** key/client to run the full lifecycle without spending real budget: sandbox advertisers & campaigns are auto‑approved and never serve or bill live inventory. Sandbox and live data are fully isolated.

### Rate limiting
Fixed window per credential (default **120 req/min**). Exceeding it returns `429` with a `Retry-After` header.

---

## 2. Marketing products (catalog)

`GET /products` returns the live catalog. Products with `"bookable": true` can be purchased today via `POST /campaigns`; others are discoverable and onboard in later phases or via dedicated endpoints.

| Product key | Category | Bookable | Pricing | Notes |
|---|---|---|---|---|
| `audio_preroll` | audio | ✅ | cpm, flat | :15–:30 spot before a live stream |
| `display_banner` | display | ✅ | cpm, cpc, flat | In‑app banners (web + mobile) |
| `sponsored_game` | sponsorship | ✅ | cpm, flat | Requires `creative.sponsored_game_campaign_id` |
| `audio_midroll` | audio | ⏳ | cpm | Mid‑stream insertion (coming soon) |
| `sponsorship_predict_win` | sponsorship | ⏳ | per_entry, per_impression | Coming soon |
| `sponsorship_trivia` | sponsorship | ⏳ | flat, cpm | Coming soon |
| `sponsorship_rj_read` | audio | ⏳ | flat | AI‑RJ host‑read (coming soon) |
| `programmatic_openrtb` | programmatic | 🧪 | cpm | RTB seat via `/api/openrtb` + VAST at `/api/vast` |
| `marketplace_promotion` | commerce | ⏳ | flat, cpm | Promoted rail + Category Spotlight (coming soon) |

---

## 3. Endpoints

### Meta
- `GET /` — API info (no auth).
- `GET /me` — the authenticated partner, environment, and scopes.
- `GET /products` — product catalog + pricing models (`catalog:read`).

### Advertisers
- `POST /advertisers` — create an advertiser (brand). Sandbox → auto‑active; live → `pending_approval`. (`advertisers:write`)
- `GET /advertisers/{advertiser_id}` — fetch an advertiser you own. (`advertisers:read`)

### Funding
- `GET /advertisers/{advertiser_id}/balance` — available budget in cents. (`funding:write`)
- `POST /advertisers/{advertiser_id}/funding/topup` — add budget. Sandbox credits instantly; live returns a Stripe `checkout_url`. (`funding:write`)
  ```json
  { "amount_cents": 5000, "success_url": "https://you/ok", "cancel_url": "https://you/cancel" }
  ```

### Campaigns
- `POST /campaigns` — create a campaign for a product. (`campaigns:write`)
- `GET /campaigns?advertiser_id=…&status=…` — list. (`campaigns:read`)
- `GET /campaigns/{id}?advertiser_id=…` — fetch. (`campaigns:read`)
- `POST /campaigns/{id}/creatives?advertiser_id=…` — attach/replace creative. (`campaigns:write`)
- `POST /campaigns/{id}/submit?advertiser_id=…` — submit for review (live). (`campaigns:write`)
- `POST /campaigns/{id}/pause?advertiser_id=…` — pause an active campaign. (`campaigns:write`)
- `POST /campaigns/{id}/stop?advertiser_id=…` — end a campaign. (`campaigns:write`)
- `GET /campaigns/{id}/report?advertiser_id=…` — impressions, clicks, spend, CTR, remaining budget. (`reports:read`)

### Sponsorships
Unified resource for Predict&Win, Trivia, and AI-RJ sponsored reads (`type` = `predict_win` | `trivia` | `rj_read`).
- `GET /sponsorships/inventory?type=…` — what's sponsorable (open Predict&Win events / trivia target types + categories / RJ personas). (`catalog:read`)
- `POST /sponsorships` — book a sponsorship (`type` + `advertiser_id` + type-specific fields). Sandbox → auto-active. (`campaigns:write`)
- `GET /sponsorships?type=…&advertiser_id=…` — list. (`campaigns:read`)
- `GET /sponsorships/{id}?type=…&advertiser_id=…` — fetch. (`campaigns:read`)
- `POST /sponsorships/{id}/submit?type=…&advertiser_id=…` — submit/confirm (live: Predict&Win publishes for review; Trivia charges the prize pool; RJ enters moderation). (`campaigns:write`)
- `GET /sponsorships/{id}/report?type=…&advertiser_id=…` — counters. (`reports:read`)

Type-specific create fields:
- **predict_win**: `parent_campaign_id`, `brand_name`, `brand_asset_url`, `pricing_model` (`per_entry`|`per_correct_impression`), `cpe_cents`/`cpi_cents`, `budget_cents`.
- **trivia**: `sponsor_target_type` (`any`|`category`|`question_set`), `target_id`, `prize_pool` (`[{rank,points_reward,quantity,currency}]`), `winner_selection` (`top_n`|`score_threshold`), `display_name`, `start_at`, `end_at`.
- **rj_read**: `persona_id`, `any_station` or `station_ids`, `disclosure_prefix`, `plays_target`, `cost_per_play_cents`, `script_body` (literal, or `"auto"` to AI-draft), `start_at`, `end_at`.

### Usage analytics
- `GET /usage?days=30` — total calls, calls by day/endpoint/status, campaign count, spend, impressions, clicks, CTR. (`reports:read`)

### Webhooks
- `GET /webhooks/events` — subscribable event types. (`catalog:read`)
- `POST /webhooks` — register `{url, events?}`; returns a signing `secret` **once**. (`campaigns:write`)
- `GET /webhooks` / `DELETE /webhooks/{id}` / `POST /webhooks/{id}/ping` / `GET /webhooks/{id}/deliveries`.

Events: `campaign.approved`, `campaign.live`, `campaign.budget_exhausted`, `campaign.completed`, `sponsorship.approved` (+ `ping`). Each delivery carries headers `X-RadioLife-Event`, `X-RadioLife-Delivery`, and `X-RadioLife-Signature: t=<unix>,v1=<hex>`. Verify by computing `HMAC-SHA256(secret, "<t>.<raw_body>")` and comparing to `v1` (reject if `t` is stale). Body: `{ "id", "type", "created", "environment", "data" }`.

---

#### Campaign create body```json
{
  "advertiser_id": "advv2_…",
  "product": "audio_preroll",
  "name": "Spring launch",
  "budget_total_cents": 30000,
  "pricing_model": "cpm",
  "cpm_bid_cents": 1200,
  "daily_cap_cents": 5000,
  "start_at": "2026-07-01T00:00:00Z",
  "end_at": "2026-07-31T23:59:59Z",
  "targeting": { "cities": ["Dubai"], "user_segments": ["all"], "dayparts": ["morning","evening"], "languages": ["en"], "genres": [] },
  "creative": { "headline": "Try Acme", "audio_url": "https://cdn/acme.mp3", "click_url": "https://acme.example" }
}
```
- `pricing_model`: `cpm` requires `cpm_bid_cents`; `cpc` requires `cpc_bid_cents`; `flat` needs neither.
- `user_segments` ⊆ `{all, free, premium}`; `dayparts` ⊆ `{morning, afternoon, evening, night}`.

---

## 4. Quick start (sandbox)

```bash
BASE="{BACKEND_URL}/api/v1"
KEY="rlk_test_xxx.yyy"                       # from Advertiser dashboard → API & Keys

# 1. Who am I?
curl -s "$BASE/me" -H "Authorization: Bearer $KEY"

# 2. Create an advertiser (auto-active in sandbox)
AID=$(curl -s -X POST "$BASE/advertisers" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme Brand","contact_email":"brand@acme.example"}' | jq -r .advertiser.advertiser_id)

# 3. Fund it (sandbox credits instantly)
curl -s -X POST "$BASE/advertisers/$AID/funding/topup" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{"amount_cents":5000}'

# 4. Launch an audio pre-roll campaign
CID=$(curl -s -X POST "$BASE/campaigns" -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d "{
    \"advertiser_id\":\"$AID\",\"product\":\"audio_preroll\",\"name\":\"Launch\",
    \"budget_total_cents\":3000,\"pricing_model\":\"cpm\",\"cpm_bid_cents\":1200,
    \"creative\":{\"headline\":\"Try Acme\",\"audio_url\":\"https://cdn/acme.mp3\"}}" | jq -r .campaign.campaign_id)

# 5. Pull a report
curl -s "$BASE/campaigns/$CID/report?advertiser_id=$AID" -H "Authorization: Bearer $KEY"
```

For **live**, mint a `rlk_live_…` key, and note that advertisers/campaigns require RadioLife approval, and top‑ups return a Stripe `checkout_url` to complete payment.

---

## 5. Errors

JSON body shape: `{ "detail": { "code": "…" } }`.

| Status | Meaning |
|---|---|
| 400 | Validation error (e.g. `invalid_pricing_model`, `unknown_product`) |
| 401 | Missing/invalid credential (`invalid_credentials`, `invalid_token`, `invalid_client`) |
| 403 | `insufficient_scope` |
| 404 | `advertiser_not_found` / `campaign_not_found` |
| 409 | `advertiser_not_active`, `product_not_bookable_via_api` |
| 429 | `rate_limit_exceeded` (see `Retry-After`) |

---

_Phase 1 covers auth, catalog, advertiser + funding, and bookable campaign types (audio pre‑roll, display banner, sponsored game) with reporting. Programmatic (OpenRTB), the remaining sponsorship types, mid‑roll audio, and marketplace promotion are on the roadmap._
