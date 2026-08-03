## 2026-06-02 — ads.txt static-asset-precedence hotfix

**Symptom**: tester confirmed admin `POST /api/admin/integrations/ads-txt` wrote the correct content to `/app/backend/static/ads.txt`, but `curl https://mobile-games-v2.preview.emergentagent.com/ads.txt` kept returning the hardcoded "BigFM Dubai / FunAsia AI Radio — ads.txt" seed body. Localhost backend curl was fine; preview URL was not. Cache-busting + `Cache-Control: no-cache` didn't help.

**Root cause** — `find -name 'ads.txt'` revealed **two stale impostors**:
- `/app/frontend/public/ads.txt`  ← intercepted by CRA dev server
- `/app/frontend/public/app-ads.txt`

The kubernetes ingress routes `/api/*` → backend (8001) and everything else → frontend (3000). The React dev server serves files from `/public/` statically at root, so `/ads.txt` was being satisfied by the impostor BEFORE FastAPI's dynamic route ever got a chance.

**Fix** (2 files, no code logic touched):
1. **Deleted**:
   - `/app/frontend/public/ads.txt`
   - `/app/frontend/public/app-ads.txt`
2. **Created** `/app/frontend/src/setupProxy.js` — CRA auto-loads this; forwards exactly `/ads.txt` + `/app-ads.txt` → `http://localhost:8001`. Narrow scope, nothing else proxied. Production parity note included in the file: ingress / nginx config should mirror this two-path forward.

No edits to `services/ads_txt_manager.py` or `routes/ads_public.py` (already correct).

**Live preview-URL verification (the one that actually matters)**:
```
POST /api/admin/integrations/ads-txt
        {content: "# bigfm-preview-e2e-1780396292-98acbd96\ngoogle.com, pub-preview-e2e, DIRECT, deadbeef\n"}
                                                                            → {ok:true, valid_line_count:1, bytes:86}

GET https://mobile-games-v2.preview.emergentagent.com/ads.txt?bust=…
HTTP/2 200, content-type: text/plain; charset=utf-8, X-Powered-By: Express, x-bigfm-region: ae-uae
  # bigfm-preview-e2e-1780396292-98acbd96
  google.com, pub-preview-e2e, DIRECT, deadbeef

GET https://mobile-games-v2.preview.emergentagent.com/app-ads.txt?bust=…
  (same body — both root paths reflect the latest admin write)

✅ marker found in preview response  (run-id: 1780396292-98acbd96)
```

The `X-Powered-By: Express` header is the give-away that the request is now traversing the dev-server proxy hop before landing on FastAPI — exactly as designed.

**New regression test** (extending `tests/test_phase18d.py`):
- `test_ads_txt_preview_url_reflects_admin_writes_through_full_stack` — uses `requests` against the live `REACT_APP_BACKEND_URL` (not TestClient, not localhost) to catch any future static-asset-precedence regression. Skips gracefully if the preview URL is unset (CI without a deploy).

**Production parity note**: when this app is deployed (Vercel/Railway/Emergent native), the platform's ingress must include a rule equivalent to the dev-server proxy:
```
GET /ads.txt        → backend service
GET /app-ads.txt   → backend service
```
…otherwise the static-asset-precedence bug will recur in prod. Documented in `src/setupProxy.js` header comment so the deploy team has a single source of truth.

**Final counts after hotfix**:
- BE **74/74 green** (was 73 → +1 preview-URL e2e test).
- FE **26/26 green** (unchanged).


## 2026-06-02 — Phase 18d post-tester bug fixes

Tester found 2 defects + 2 warnings. All fixed in this patch:

| # | Issue | Root cause | Fix |
|---|-------|-----------|-----|
| Defect 1 | `POST /admin/integrations/ads-txt` writes succeed, public `/ads.txt` keeps serving the seeded constant | Public route had a try/except fallback to baked-in `_ADS_TXT` string. The dynamic read worked on localhost but any silent exception would mask it. | Removed the try/except fallback — public routes ALWAYS read `services.ads_txt_manager.read_content()`. Added self-heal: `read_content` writes the default header to disk on first miss so the file is guaranteed-present. Single source of truth: `Path(ADS_TXT_PATH env, default /app/backend/static/ads.txt)`. |
| Defect 2 | `POST /admin/advertiser/ads/pick-debug` returns HTTP 500 when waterfall hits GAM/OpenRTB | `routes/admin_advertiser.py:194` did `serve["serve"]["advertiser_id"]` — KeyError on programmatic envelopes which have no advertiser. | Use `.get("advertiser_id")` and skip the balance lookup for programmatic backfills. Also: `_programmatic_fallback` in `services/advertisers.py` now stamps explicit `source` (gam_mock / openrtb_mock), `advertiser_id: None`, `campaign_id: None` on BOTH `serve` and `campaign` sub-docs. |
| Warn 1 | Campaign PATCH silently drops `attribution_window_hours` | Field not in PATCH allowed-fieldset. | Added `attribution_window_hours` to `allowed` in `routes/advertiser.py:update_campaign`. Validates 1 ≤ int ≤ 720 (30 days). Response now returns the updated campaign dict so callers can confirm. |
| Warn 2 | 400 detail was `{detail: {detail: {code, bad_lines}}}` — double-wrapped | The route wrapped the ValueError payload in another `{"detail": ...}` before raising HTTPException. | Flattened: route now raises `HTTPException(400, payload)` directly where `payload = {"code": "invalid_ads_txt_lines", "bad_lines": [...]}`. Single wrapper. Also renamed code to `invalid_ads_txt_lines` per spec. |

### `serve` / `campaign` envelope schema (post-fix)

```jsonc
{
  "serve": {
    "id":          "serve_gam_xxx" | "serve_ortb_xxx" | "serve_yyy",
    "source":     "direct" | "takeover" | "gam_mock" | "openrtb_mock" | "gam_live" | "openrtb_live",
    "advertiser_id": "<id>" | null,    // null = programmatic backfill
    "campaign_id":   "<id>" | null,    // null = programmatic backfill
    "channel_slug": "...",
    "market":        "...",
    "served_at":   ISODate,
    "cost_usd":     0.012,
    "was_takeover": bool,
    "_freq_cap_reason": "..." | null
  },
  "campaign": {
    "id":               "<id>" | null,
    "name":           "GAM backfill" | "OpenRTB backfill" | "<real name>",
    "advertiser_id": "<id>" | null,
    "source":         (same enum as above),
    "was_takeover": bool
  },
  "creative": { ... }
}
```

### Live verification (real HTTP, real Mongo)
```
ads.txt:
  POST /api/admin/integrations/ads-txt {marker + 1 seller}
        → {ok:true, valid_line_count:1, bytes:68}
  GET  http://localhost:8001/ads.txt → marker line + seller line  ✓

pick-debug waterfall:
  POST /api/admin/advertiser/ads/pick-debug
        {user_id:u_fix2_wf, channel_slug:__force_fallback__, market:atlantis}
        → HTTP 200 with serve.source=gam_mock, advertiser_id=None, campaign_id=None  ✓

PATCH attribution_window_hours:
  PATCH /api/advertiser/adv_demo_karak/campaigns/cmp_demo_karak_lunch
        {attribution_window_hours:48}     → {ok:true, campaign.attribution_window_hours:48}
  GET  same URL                                    → campaign.attribution_window_hours=48  ✓
  PATCH with 0                                       → 400 "must be 1..720"  ✓
```

### Tests added in this patch (extending `tests/test_phase18d.py`)
- `test_ads_txt_admin_post_reflects_on_public_route` — round-trip via httpx `TestClient(app)` against `/ads.txt`.
- `test_pick_debug_waterfall_returns_programmatic_source_when_no_direct_sold` — asserts source + explicit nulls.
- `test_patch_campaign_attribution_window_hours_persists` — happy path + 0/1000 rejects.
- `test_ads_txt_invalid_post_returns_flat_400_envelope` — single-wrapper assert.

**Final counts**: BE **73/73 green** (was 69 → +4 bug-fix tests). FE **26/26 green** (unchanged).


# Phase 18d — Programmatic Stack + Polish

**Status**: ✅ COMPLETE (2026-06-02). 69 BE + 26 FE green. Zero existing tests regressed (4 phase-18a assertions updated to reflect new waterfall semantics — "no direct-sold winner" instead of "no ad at all").

## What shipped

### 1. GAM adapter (mock-by-default)
- `services/gam_adapter.py` — `is_live()`, `request_ad(...)`, `report_impression(...)`, `status_snapshot()`.
- Mock returns a deterministic envelope with `source="gam_mock"`, `revenue_usd=$0.012`, embedded VAST 4.0.
- Live path is a guarded stub — `NotImplementedError` is caught and falls back to mock so the waterfall never hard-fails listeners.
- Slot in waterfall: **#3** (after takeover, after direct-sold).

### 2. OpenRTB adapter (mock-by-default)
- `services/openrtb_adapter.py` — full OpenRTB 2.5 BidRequest shape (audio, imp, user, device, geo, site, ext.channel_slug).
- Second-price auction: highest bid wins, charged at runner-up + $0.001. Mock returns 2 bids ($0.008 / $0.006).
- Live path is a guarded stub. Slot in waterfall: **#4**.

### 3. Waterfall integration
- `services/advertisers.py:pick_ad_for_user` now has an inline `_programmatic_fallback(reason)` helper called from BOTH bailout points (no eligible direct-sold AND everyone freq-capped). Order: takeover → direct-sold → GAM → OpenRTB.
- Phase 18c pacing fixtures (`_is_pacing_fixture: True`) are excluded from the eligible query so they never leak into the auction (they exist only for the pacing-health panel).

### 4. VAST 4.0 wrapper
- `services/vast_wrapper.py:build_vast_xml(creative, base_url, serve_id, advertiser_name)`.
- IAB-compliant: `<Ad>`, `<InLine>`, `<AdSystem>`, `<AdTitle>`, `<Description>`, `<Advertiser>`, `<Impression>`, `<Linear>`, `<Duration>`, `<TrackingEvents>` (start, firstQuartile, midpoint, thirdQuartile, complete, mute), `<VideoClicks>`, `<MediaFiles>`.
- Every impression / tracking URL points at our own `/api/ads/tracking/impression?serve_id=<sid>&event=<evt>` so the attribution loop closes for any external VAST consumer.

### 5. ads.txt admin
- `services/ads_txt_manager.py` — file-backed at `/app/backend/static/ads.txt`. Validates each line via regex `(domain),(pub_id),(DIRECT|RESELLER)[,tag_id]`. Atomic write via temp+rename.
- Admin routes (in `routes/phase18d.py`):
  - `GET /api/admin/integrations/ads-txt` → current content + validation report.
  - `POST /api/admin/integrations/ads-txt` `{content: "..."}` → atomically rewrites, 400 on invalid lines.
- Public `/ads.txt` and `/app-ads.txt` (in `routes/ads_public.py`) now read dynamically; `Cache-Control: public, max-age=300` (5min) so admin edits propagate quickly.

### 6. attribution_window_hours polish
- New `attribution_window_hours` field on `ad_campaigns` (default 24, editable via wizard).
- `routes/phase18c.py:/attribution` filters coupon saves / redemptions to only those whose `saved_at` (or `claimed_at`) fell within `window_hours` of the matched serve.
- Stale or unbound coupons (no `attribution_serve_id`) count by default — legacy compatibility.
- Wizard input: `data-testid="wizard-attribution-window-hours"` with help text.

### 7. on_pace fixture polish
- `cmp_test_onpace_001` "Steady Eddie" — spend $500 / $1000, dates ±5d → time_progress 0.5 vs spend_progress 0.5 → `on_pace`.
- Pacing-health panel is exception-only (shows ahead/behind buckets); on_pace fixture supports the test assertion + future "all campaigns" view.

## Phase 18d routes (all new)

| Method | Path                                                 | Auth     | Purpose |
|--------|------------------------------------------------------|----------|---------|
| GET    | `/api/admin/integrations/gam/status`                | admin    | mock state, env flags, last_check_at |
| GET    | `/api/admin/integrations/openrtb/status`           | admin    | mock state, # SSPs configured |
| GET    | `/api/admin/integrations/ads-txt`                    | admin    | current content + validation |
| POST   | `/api/admin/integrations/ads-txt`                    | admin    | atomically rewrite, 400 on invalid |
| GET    | `/api/ads/vast/{creative_id}?serve_id=`            | public   | VAST 4.0 XML for any stored creative |
| GET    | `/api/ads/tracking/impression?serve_id=&event=` | public   | 204 idempotent ping (dedup_key) |

## Env vars (document; no values set in this phase)

- `GAM_NETWORK_CODE` — empty → mock; set + `GAM_SERVICE_ACCOUNT_JSON` → live.
- `GAM_SERVICE_ACCOUNT_JSON` — path or inline JSON. Presence-checked.
- `OPENRTB_SSP_ENDPOINTS` — JSON array of SSP bid endpoints. Empty → mock.
- `VAST_BASE_URL` — overrides request.base_url inside generated VAST XML. Default: preview URL.
- `ADS_TXT_PATH` — override file location (default `/app/backend/static/ads.txt`).

## Live verification (real HTTP, no mocks)

```
GET  /ads.txt                       → 200 text/plain, dynamic from disk
POST /api/admin/integrations/ads-txt
        {content: "google.com, pub-x, DIRECT, fXXX"}
                                                  → {ok:true, valid_line_count:2, bytes:118}
POST same endpoint with bad row → 400 {detail.bad_lines: [{line_no, content}]}
GET  /api/admin/integrations/gam/status     → {is_live:false, mock_cpm_usd:12.0}
GET  /api/admin/integrations/openrtb/status → {is_live:false, ssp_endpoints_configured:[]}
GET  /api/ads/vast/crv_cmp_karak_20off?serve_id=demo
                                                  → 200 application/xml, VAST 4.0 with 6 tracking events
GET  /api/ads/tracking/impression?serve_id=x&event=complete → 204; dedup_key prevents duplicates
GET  /api/admin/advertiser/pacing-health    → ahead[1] + behind[1] live data
```

## Files NOT touched (scope guard honored)

- `services/pacing.py`, `services/freq_caps.py`, `services/engagement_push.py`, `services/hygiene18c.py`, `services/creative_safety.py`, `services/ai_ad_creator.py`, `services/telemetry.py`
- `routes/phase18c.py` (only `/attribution` reader patched for window filter), `routes/advertiser_ai.py`
- `<GlobalAudio />`, trivia WebSockets, geo precedence, market lexicon arrays, AI Ad Creator pipeline
- `/app/mobile/` (Expo mirror — separate follow-up after Phase 18d closes)

## Test counts

- BE: **69/69 green** in `tests/test_phase18*.py` (was 58 — +11 new in `test_phase18d.py`).
- FE: **26/26 green** in `__tests__/Phase18*.test.jsx` (was 23 — +3 new in `Phase18d.test.jsx`).
- Adjacent regressions: 4 phase-18a assertions updated to reflect the new waterfall (programmatic backfill is OK when direct-sold rejects). Not a behavior break — the "no direct-sold winner" guarantee still holds; we just now serve a mock instead of silence.

## Mocked/parked (unchanged)

- Apple APNs / iOS Native push.
- Stripe Connect transfers.
- Real GAM Ad Manager API (env-gated; live path stub raises NotImplementedError → falls back to mock).
- Real OpenRTB SSP POSTs (env-gated; same pattern).

## Next up

- Phase 22 — Podcast Creator Network (user re-prioritized over 19/20/21).
- Mobile (Expo) advertiser mirror — separate follow-up for `e1_expo_frontend_dev` once Phase 18 closes.
- Phases 19/20/21 deferred. Phase 40 News Radio still parked with locked defaults.
