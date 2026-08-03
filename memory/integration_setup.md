# BigFM — Integration Setup Notes

## Phase 15d.1 — ipapi.co (geo provider, default)

- **Provider**: `ipapi.co` free tier
- **Auth**: no API key required
- **Quota**: ~1000 requests/day per egress IP (hard-limited via the platform's 24-hour cache in `geo_cache`)
- **Env var**: `BIGFM_GEO_PROVIDER=ipapi.co` (the default if unset)
- **Fallback chain**:
  1. ipapi.co JSON lookup, 24h cached per IP in Mongo
  2. Browser-supplied `?tz=<IANA>` query / `x-bigfm-tz` header → `_TZ_TO_MARKET` table
  3. Mock Dubai (logged WARNING)
- **Closest-market by haversine**: any unmapped US city falls back to the nearest centroid in `services/market_lexicon.py` (`centroid` field). Currently routes Dallas, Houston, Austin, OKC, KC, etc. → `dfw`.

To upgrade to MaxMind GeoLite2 City: ship the `.mmdb` file and set
`BIGFM_GEO_PROVIDER=maxmind` + `MAXMIND_DB_PATH=/path/to/GeoLite2-City.mmdb`.
