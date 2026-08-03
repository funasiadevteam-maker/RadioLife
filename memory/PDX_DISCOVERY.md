# Predexon API Discovery — Phase PDX.1 (2026-07-27)

## TL;DR

- **Predexon is a Polymarket data proxy** — canonical path is `/v2/polymarket/markets`
- **NO real category filter** exists; the `category` query param is silently ignored
- **What actually filters**: `tags=<TagLabel>` (single, case-sensitive) and `search=<free_text>` (title substring match, case-insensitive)
- Default sort is **volume desc** already (confirmed via the base64 pagination_key: `"sort":"volume"`)
- **Pagination uses `pagination_key` cursor**, not `offset` — passing `offset` on page ≥1 returns HTTP 400
- **Rate-limits aggressively**: back-to-back GETs from a single origin trip HTTP 429; safe cadence is ≥ 8s between calls
- **Auth**: `x-api-key` header (already wired via `PREDEXON_API_KEY` env var)

## Canonical response schema (per market)

Sample from `/v2/polymarket/markets?status=open&limit=1`:

```json
{
  "condition_id": "0xb6d6f15a1b5d08753653f1867ccd6126badfbe182a75159a330dc7b15336b309",
  "question_id": "0x55ab76d092f682bf5cbb7e14f13ee12f8410ce7cc1b7906f23b8fb56c11f6507",
  "market_id":       "2063135",
  "market_slug":  "will-gedion-timothewos-be-the-next-prime-minister-of-ethiopia",
  "title":              "Will Gedion Timothewos be the next Prime Minister of Ethiopia?",
  "description":  "General elections are scheduled …",
  "status":            "open",
  "winning_side": "UNKNOWN",
  "start_time":     "2026-04-27T21:55:15.894000Z",
  "end_time":        "2026-06-01T00:00:00Z",
  "close_time":     null,
  "created_time": "2026-04-23T22:32:51.589000Z",
  "image_url":       "https://polymarket-upload.s3…",
  "event_id":         "411239",
  "event_slug":     "ethiopia-election",
  "event_title":    "Ethiopia general election",
  "outcomes":       [ { "id": "…", "label": "Yes" }, { "id": "…", "label": "No" } ],
  "tags":                ["Ethiopia", "Elections", "Main Election", "Global Elections", "Politics"],
  "total_volume_usd":  55880867.36,
  "liquidity_usd":         12345.67,
  "is_neg_risk":            false,
  "rolling_metrics":     { "…" },
  "resolution_source": null
}
```

### Fields we consume in the curator

| Predexon field | BigFM campaign column | Notes |
|---|---|---|
| `market_id` | `external_market_id` | Idempotency key |
| `title` | `title`, `question.prompt` | 160-char cap |
| `description` | `description` | Optional, 600-char cap |
| `outcomes` | `question.answer_options` | Via `normalize_outcomes` (existing helper) |
| `tags` | `external_provider_snapshot.tags` + category detector | Case-sensitive strings |
| `total_volume_usd` | Used to derive `points_reward` | log10-scaled |
| `start_time` | `start_time` | Falls back to `created_time` then `now` |
| `end_time` / `close_time` | `lock_time` | Prefer `end_time`; if null, `+7 days` from `open_time` |
| `market_url` (derived) | `external_market_url` | `https://polymarket.com/event/<market_slug>` |
| `image_url` | `cover_image_url` | Direct S3 URL |

## Filter surface — what works, what doesn't

| Query param | Behavior | Verified |
|---|---|---|
| `status=open` | Filters to live markets | ✅ Documented + used by existing client |
| `limit=<int>` | Max 100 per call | ✅ |
| `offset=<int>` | Works ONLY for the first page. Subsequent pages MUST use `pagination_key` | ✅ HTTP 400 confirmed on offset=100 |
| `pagination_key=<b64>` | Cursor from `pagination.pagination_key` of previous response | ✅ Docs confirm |
| `sort=volume` | Default sort. Confirmed via decoded pagination_key blob | ✅ |
| `tags=<label>` | Case-sensitive single-tag filter. Returns markets whose `tags` array contains the label | ✅ `tags=Sports` → 50 F1 markets; `tags=US Election` → 73 election markets |
| `tags=A,B` | CSV **NOT supported** — returns 0 rows | ❌ Confirmed |
| `search=<text>` | Case-insensitive title substring | ✅ `search=nfl` → 20 NFL Super Bowl markets; `search=cricket` → Legends Cricket League |
| `category=<slug>` | Silently **IGNORED** — returns the same first market regardless | ❌ Confirmed |
| `event_slug=<slug>` | Untested by us, but present in pagination_key blob — likely works for scoping to a specific Polymarket event | – |

## Category taxonomy (final mapping)

The user brief's `category=sports/stocks/politics/games` doesn't map to a Predexon param, so we filter client-side. Chosen source strategies:

| Category slug | Predexon call(s) | Client-side filter | Default points |
|---|---|---|---|
| `sports_top` | `tags=Sports&limit=50` | Take markets NOT already tagged with a league (NFL/NBA/MLB/NHL/IPL). Sort by `total_volume_usd` desc, take top 8. Real pool today = ~50 F1 + few others. | 25 |
| `stocks_top` | `search=Fed rate&limit=20` + `search=earnings&limit=10` + `search=SP500&limit=10` (deduped by `market_id`) | Union client-side, filter to items whose `tags` includes `Fed`, `Economy`, `Stocks`, `Earnings`, or `SPX/SP500` — sort volume desc, take top 4. | 50 |
| `us_politics` | `tags=US Election&limit=50` | Take top 4 by volume. Pool today: 73 markets — abundant. | 75 |
| `national_games` | 4 parallel searches: `search=NFL`, `search=NBA`, `search=MLB`, `search=cricket` (limit=15 each), deduped by `market_id` | Union, dedupe, sort by volume desc, take top 6. Real pool today: ~20 NFL + ~a few cricket markets. | 40 |

**Fallback**: `ensure_minimum_active(20)` — if the 4-category pull yields <20 fresh events, top up from any remaining `us_politics` matches (which is by far the most populous tag).

## Points-from-volume curve

```python
points = max(10, min(100, round(base + math.log10(max(volume_usd, 1)) * 5)))
```

Values on real markets:
- `sports_top` base=25, vol=$8.9M → `25 + log10(8_900_000)*5 = 25 + 34.5 = 60` → clamped to `60`
- `us_politics` base=75, vol=$55.8M → `75 + log10(55_880_867)*5 = 75 + 38.7 = 114` → clamped to `100`
- `national_games` base=40, vol=$4.5M NFL → `40 + log10(4_500_000)*5 = 40 + 33.3 = 73`
- `stocks_top` base=50, vol=$35M Fed → `50 + log10(35_000_000)*5 = 50 + 37.7 = 88`

Bounds guarantee the user directive: **10 ≤ points_reward ≤ 100**.

## Rate-limit strategy

- Space calls at ≥ 8 s per API request (empirically safe)
- One tick = 4 category pulls = ~4-5 Predexon calls with spacing → ~40 s wall time
- Scheduler runs every `PDX_CURATOR_INTERVAL_MIN=60` (default) = zero risk of sustained 429
- Every call already logs to `prediction_api_logs` (TTL 30 days) — audit trail is free

## Idempotency & dedupe

The existing `POST /api/admin/prediction/import-market` in `admin_predexon.py` already enforces idempotency:

```python
dup = await db.predict_win_campaigns.find_one({
    "external_market_id": str(external_market_id),
    "status": {"$ne": "cancelled"},
    "deleted_at": None,
})
if dup:
    raise HTTPException(409, {...})
```

**The curator uses the same rule** — before insert, check for a non-cancelled row with matching `external_market_id`. Skip if present.

## Fields we're adding to `predict_win_campaigns`

| Field | Type | Default | Notes |
|---|---|---|---|
| `category_slug` | string \| null | null | One of `sports_top` / `stocks_top` / `us_politics` / `national_games`, or null for manual admin/business/advertiser campaigns |
| `points_reward` | int | 25 | Bounded `[10, 100]`. Existing rows are backfilled to 25 |
| `imported_at` | datetime \| null | null | ISO date of curator import (null for non-curator rows) |
| `import_source` | string | `"admin_manual"` | One of: `admin_manual`, `pdx_curator`, `advertiser_self_serve`, `business_owner`, `merchant_activation` |

Also, `creator_type` accepts a new value: **`admin_auto`** — indicating the row was inserted by the automated curator, not a human admin.

## New `system_settings` collection

`system_settings` did NOT exist before Phase PDX.1. We create it now with:

```json
{
  "_id": "pdx_curator",
  "enabled": true,
  "interval_min": 60,
  "target_min": 20,
  "target_max": 40,
  "updated_at": "2026-07-27T…"
}
```

Extensible — future phase settings can live under different `_id` keys.

## Sample market URL derivation

Predexon doesn't return a canonical `market_url`, but every `market_slug` maps 1:1 to a Polymarket UI page:

```
https://polymarket.com/event/<market_slug>
```

We store this in `external_market_url` for admin-side "open on Polymarket" links.
