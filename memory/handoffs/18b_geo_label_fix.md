# Phase 18b — Geo-label fix (2026-06-02)

## Root cause (one paragraph)

The home page had two divergent sources of truth for "which market am I in?".
The "around <city>" header (LocalNewsWidget, CityChip, BigFmBrand) read
`useGeoStore.city` / `useGeoStore.market`, which was populated by
`GET /api/geo/me`. The recommendation rails and channel pools read
`user.market` directly (set during onboarding). `GET /api/geo/me` called
`services.geo.resolve_for_user`, which only honoured `user.preferred_market`
(the CityChip override) before falling all the way through to IP-based
geolocation. Because the cloud preview's egress IP resolves to Dallas — and
the QA demo user had a stale `preferred_market: "dfw"` left over from a
previous test session — the header rendered "Around Dallas" while the
content rails kept rendering Dubai stations.

## Fix
1. `services/geo.py :: resolve_for_user` — new precedence chain:
   preferred_market → user.market → IP geo. Returns `source: "user_profile"`
   when the home market is the winner.
2. `auth.py :: demo_login` — clears stale `preferred_market` /
   `last_resolved_market` keys at every demo login.
3. `auth.py :: _ensure_demo_user` — fresh demo users get `market: "dubai"`
   at the top level (was only nested under preference_vector).
4. `shell/AppShell.jsx` — geo store re-bootstraps when the auth user
   changes, eliminating the ~300 ms flash of anon IP city before login.
5. Data fix (one-time): cleared stale preferred_market on demo + test
   accounts.

## Verification
`POST /api/auth/demo` → `GET /api/geo/me?tz=America/Chicago` returns
`{market: "dubai", city: "Dubai", timezone: "Asia/Dubai", source: "user_profile"}`.
