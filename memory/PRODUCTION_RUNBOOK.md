# BigFM — Production Runbook

This is the operator handbook for everyday production tasks: rotating
secrets, monitoring health, restoring data, and onboarding employees
for testing.

---

## 1. Custom Domain via Emergent

1. Emergent dashboard → your project → **Custom Domain**.
2. Add `bigfantv.com` (apex) and `app.bigfantv.com` (subdomain).
3. Update DNS:
    * `bigfantv.com` → CNAME / ALIAS to `<emergent-target>`.
    * `app.bigfantv.com` → CNAME to `<emergent-target>`.
4. Wait for SSL provisioning (5-15 min). Emergent issues Let's Encrypt
    certificates automatically.
5. Update environment:
    * `backend/.env` → `CORS_ORIGINS=https://bigfantv.com,https://app.bigfantv.com,https://mobile-games-v2.preview.emergentagent.com`
    * `backend/.env` → `BIGFM_PUBLIC_BASE_URL=https://bigfantv.com`
    * `backend/.env` → `PUBLIC_BACKEND_URL=https://app.bigfantv.com`
    * `frontend/.env` → `REACT_APP_BACKEND_URL=https://app.bigfantv.com`
6. Restart: `sudo supervisorctl restart backend frontend`.
7. Confirm: visit `https://bigfantv.com/` and inspect the cert in DevTools.

---

## 2. Dev escape-hatch flip (production go-live)

Every dev mode flag is gated by a single meta-flag.

```bash
# Production cutover — flip all switches to safe defaults.
ENV=production
BIGFM_DEV_ESCAPE_HATCHES=0
BIGFM_DEBUG_GEO=0
BIGCOIN_LEGACY_DUAL_WRITE=0
MAILGUN_WEBHOOK_VERIFY_SIGNATURE=1
STRIPE_WEBHOOK_VERIFY_SIGNATURE=1
INVITE_EMAIL_LIVE=1
```

After flipping:

```bash
sudo supervisorctl restart backend
curl -s "$BACKEND/api/admin/system/health" -b admin.cookie | jq '.production_ready'
# expect true
```

The health endpoint reports `production_ready: true` only when every
high-severity issue is cleared (CORS not wildcard, both webhook sigs
verified, all keys present).

---

## 3. Key rotation

| Provider                              | Where to rotate                                                                  | Restart |
|------------------------------------|-----------------------------------------------------------------------|---------|
| OpenAI (text)                      | Emergent dashboard or platform.openai.com    | backend |
| OpenAI Image                      | platform.openai.com → API keys                              | backend |
| ElevenLabs                          | elevenlabs.io → Profile → API key                          | backend |
| NewsAPI                              | newsapi.org → Dashboard                                              | backend |
| Mailgun                                | mailgun.com → API Keys                                              | backend |
| Mailgun webhook signing | mailgun.com → Sending → Webhooks → Reveal HTTP webhook signing key | backend |
| Stripe (secret + publishable) | dashboard.stripe.com → Developers → API keys                          | both    |
| Stripe webhook                  | dashboard.stripe.com → Developers → Webhooks → endpoint at `/api/webhooks/stripe/events` → Reveal | backend |
| Predexon                            | predexon partner portal                                          | backend |
| Tigris                                  | console.tigris.dev                                                              | backend |
| LiveKit                                | cloud.livekit.io                                                              | backend |

After any rotation:

```bash
sudo supervisorctl restart backend  # (and frontend if its key changed)
curl -s "$BACKEND/api/admin/system/health" -b admin.cookie | jq '.keys_present'
```

---

## 4. MongoDB backup

Manual dump (sufficient for 10-employee internal test):

```bash
# Inside the backend container.
mongodump --uri "$MONGO_URL/$DB_NAME" --out /tmp/bigfm_backup_$(date +%Y%m%d)
tar czf /tmp/bigfm_backup_$(date +%Y%m%d).tgz /tmp/bigfm_backup_$(date +%Y%m%d)
# Copy out via your container console or scp.
```

Restore:

```bash
mongorestore --uri "$MONGO_URL/$DB_NAME" --drop /path/to/dump_dir
```

**Cadence**: run a manual `mongodump` before any major schema change
or every Friday during the 10-employee test. Migration to MongoDB
Atlas with automated backups is a follow-up dispatch.

---

## 5. Background-task verification

Endpoint: `GET /api/admin/system/health` → `background_tasks`.

Expected state: every entry == `"running"`.  If any reads `"done"` or
`"not_started"`, restart the backend.

Cron-style services not exposed in `background_tasks` (verify in
backend.err.log):

* `bigfm.passport_tier_scheduler` — every 5 min, "tier-recompute" line.
* `bigfm.predict_win.sweeper` — every 60s, "cycle=" line.
* `news_radio_renderer` — driven by `NEWS_TTS_BATCH_ENABLED`; runs once
   per market refresh.
* ElevenLabs / Mailgun daily char-cap reset — wakes at 00:00 UTC.

---

## 6. Employee on-boarding (10-person internal test)

Per employee:

1. Admin opens `/admin/users` → search by email.
2. Click **Flag as employee** (calls `POST /api/admin/users/{id}/flag-employee`).
3. The endpoint auto-seeds 500 BC + 3 badges (First Hour, First Share,
    First Prediction) + 1 city stamp (Dallas) — all idempotent.
4. Employee logs in → sees the welcome modal once → starts testing.

Feedback review:

* `GET /api/admin/feedback?status=open` — paginated list with all
    fields except the screenshot data URL (size only).
* `GET /api/admin/feedback/<id>` — full record including screenshot.
* `PATCH /api/admin/feedback/<id>` body `{"status":"resolved","note":"..."}`.

---

## 7. Health check SOPs

Every morning at 09:00 local:

```bash
# Snapshot the kill-switch state + key presence.
curl -s "$BACKEND/api/admin/system/health" -b admin.cookie | jq

# Confirm ledger parity.
curl -s "$BACKEND/api/admin/points/parity-check?limit=5" -b admin.cookie \
    | jq '{scanned,matched,drift_count}'
# expect drift_count: 0
```

Weekly:

```bash
# Revenue collected this month vs last.
curl -s "$BACKEND/api/admin/revenue/this-month" -b admin.cookie

# Email funnel (delivered / open / click rate).
curl -s "$BACKEND/api/admin/mail/funnel?period=week" -b admin.cookie

# Tips volume.
curl -s "$BACKEND/api/admin/tips/stats?period=week" -b admin.cookie
```

---

## 8. Incident playbook

| Symptom                                                | First action                                          |
|------------------------------------------------|-----------------------------------------------|
| 500s spiking on `/api/auth/*`        | `tail -n 200 /var/log/supervisor/backend.err.log` |
| Stripe webhook returning 400      | `STRIPE_WEBHOOK_SECRET` mismatch — rotate + restart backend |
| Mailgun events not landing          | Verify `MAILGUN_WEBHOOK_SIGNING_KEY` + endpoint URL in Mailgun dashboard |
| RJ segments silent                          | Check ElevenLabs char cap; logs `ELEVENLABS_DAILY_CHAR_CAP` |
| News headlines empty                      | NewsAPI quota — see `NEWSAPI_DAILY_LIMIT` + `NEWSAPI_LIVE_BACKOFF_AT` |
| Frontend 404s on legal pages    | Check `public/robots.txt` doesn't disallow them |
| Bad CSP block in browser console | Temporarily set `ENV=development` to drop HSTS, then loosen the offending CSP directive |

---

## 9. Roll-back / rollback discipline

The only "writers" that touch the legacy `bigcoin_balance` field are
gated behind `BIGCOIN_LEGACY_DUAL_WRITE=1`.  If a points-math bug
appears in PointsService, flip that to `1`, restart the backend, then
re-run `python3 backend/scripts/reconcile_legacy_balance_field.py` to
restore parity.

For everything else: Emergent's preview env keeps prior deployments
for ~24h.  Use the Emergent dashboard "Revert to previous deployment"
button.

---

## 10. Stateless deployments & Tigris asset migration  ☁️

The container's local disk (`/app/backend/static/`, `/app/backend/storage/`)
is **ephemeral** in production.  Fresh deploys ship with empty media
directories.  BigFM handles this transparently via two pieces:

1. **One-shot migration** (already executed; idempotent on re-run):
    ```bash
    python3 -m scripts.migrate_local_to_tigris            # static + tracks
    python3 -m scripts.migrate_local_to_tigris --skip-tracks    # static only
    python3 -m scripts.migrate_local_to_tigris --dry-run            # plan
    ```
    Persists a `migration_state.tigris_assets` doc to Mongo.  The
    /admin/health dashboard surfaces this under the **"Asset migration
    · Tigris fallback CDN"** card.

2. **Asset fallback CDN** — `services/static_fallback.py` wraps every
    `StaticFiles(directory=…)` mount with `TigrisFallbackStaticFiles`.
    When a request for `/api/static/<sub>/<rel>` misses on local disk,
    the class HEADs the corresponding `<sub>/<rel>` key in Tigris and
    302-redirects the client to a **7-day presigned URL**.  Redirects
    carry `Cache-Control: public, max-age=86400` so browsers / Cloudflare
    cache the redirect itself for a day.

**Operator note**: *on a fresh prod deploy the fallback CDN automatically
serves assets from Tigris — no manual data sync needed once migration
is complete.*  New uploads land directly in Tigris (the `object_storage`
service picks up `STORAGE_BACKEND=tigris`), so the local disk is purely
a perf shortcut, not a source of truth.

### Why presigned URLs?

The `bigfm-storage` bucket was created **private** at the Tigris infra
layer.  We attempted to flip it via the S3-compatible API
(`put_bucket_acl`, `put_bucket_policy`, `X-Tigris-Visibility: public`
header) — all return 200 OK but the bucket stays anonymously
inaccessible.  Public-read can only be enabled via the Tigris dashboard.
Until that's flipped, the resolver mints 7-day presigned URLs so the
browser fetch still works (7d ≫ 24h redirect cache window).

To flip to public-read later (preferred, removes signing overhead):
1. Tigris dashboard → bucket → "Visibility: public".
2. In `services/tigris_url_resolver.py::public_url_for_key`, replace
    the `get_signed_url(...)` body with:
    `return f"{_bucket_public_base()}/{key}"`.
3. Restart backend.  No other code changes required.

### Migration-state schema (`migration_state.tigris_assets`)

```json
{
  "_id": "tigris_assets",
  "last_run_at": ISO8601,
  "last_run_dry": false,
  "static_summary": { "uploaded": int, "skipped": int, "failed": int,
                                          "bytes_uploaded": int, "per_dir": [...] },
  "tracks_summary": { "migrated": int, "skipped_already_migrated": int,
                                              "missing_local_file": int, "failed": [...] }
}
```

The /admin/health dashboard auto-polls this every 30s along with the
in-process `fallback_hits_today` / lifetime counters.

---

_Last updated: 2026-06-20 (Phase Π+2 — Tigris Asset Migration + Fallback CDN)_

---

## 11. Kubernetes deployment troubleshooting  🚀

The Emergent deploy layer applies our container to a fresh K8s pod and
waits up to **10 minutes** for the readiness probe (`GET /api/health`)
to return HTTP 200.  If the app hasn't finished booting within that
window, K8s marks the deploy failed and rolls back.  This section
lists the 10 boot-blocker root causes we've hardened against.

| # | Root cause | Mitigation shipped |
|---|---|---|
| 1 | Blocking startup lifespan (30+ Mongo/ffmpeg/seed ops sequential) | Lifespan yields immediately; entire body moved to `_deferred_bootstrap` fire-and-forget task |
| 2 | Sync blocking calls at module import (vendor SDKs) | Audited — no module-level HTTP/socket calls in vendor service modules; all use lazy factories |
| 3 | Health probe missing or DB-gated | `GET /api/health`, `/api/healthz`, `/api/readyz`, `/health`, `/healthz`, `/readyz` all return 200 in <1 ms without touching Mongo/Tigris/OpenAI. |
| 4 | MongoDB connection blocking / failing on prod Atlas | Motor client construction wrapped in try/except → localhost fallback if SRV DNS fails.  `serverSelectionTimeoutMS=3000` in `core.db` |
| 5 | StaticFiles mount fails when directory missing | Every mount wrapped in try/except AND preceded by `os.makedirs(..., exist_ok=True)` |
| 6 | Bind address / port | Uvicorn binds `0.0.0.0:8001` (supervisor conf).  K8s ingress terminates TLS and forwards to that port |
| 7 | Frontend serving broken | Backend does NOT serve the frontend build — frontend runs in its own container on port 3000 |
| 8 | CORS parse fails on empty string | `os.environ.get("CORS_ORIGINS", "*").split(",")` with empty-string filter |
| 9 | Env-var parse errors at boot | `core/config.py` uses `.get(..., default)` — no `os.environ[...]` bracket lookups.  Every int/float env parse has a fallback |
| 10 | Import cycles or slow imports | Audited — no cycles.  All heavy work is inside function bodies, not module-level |

### Deploy readiness probe

Emergent K8s hits `GET /api/health` on the backend service.  Expected
response (200 OK):

```json
{
  "ok": true,
  "status": "ok",
  "service": "bigfm-backend",
  "version": "<git-sha or boot-<UTC-ts>>",
  "uptime_seconds": 0.842,
  "ts": "2026-06-20T04:15:30.123456+00:00"
}
```

Set `BIGFM_APP_VERSION` env var in the deploy config to surface a
proper release tag; otherwise the version falls back to a boot-time
UTC stamp.

### Debugging a stuck deploy

```bash
# 1. Simulate the prod boot condition locally.
export MONGO_URL="mongodb+srv://fake:fake@fake.mongodb.net/bigfm"
export DB_NAME="bigfm"
export SKIP_FFMPEG_BOOT_INSTALL=1
export ENV=production
/root/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 18080 &

# 2. Confirm /api/health returns 200 within 5s.
for i in {1..20}; do
  curl -m 1 -s -o /dev/null -w "%{http_code} " http://127.0.0.1:18080/api/health
  sleep 0.5
done

# 3. If it never returns 200, check the boot log for stack traces.
tail -100 /tmp/boot.log
```

### If the boot crashes on `AsyncIOMotorClient(mongodb+srv://…)`

That's a pre-hardening symptom: some module still constructs a Motor
client at module-import time without a try/except.  Grep for
`AsyncIOMotorClient(` outside `core/db.py`, `services/db_routing.py`,
and inside-function scopes:

```bash
grep -rn "AsyncIOMotorClient(" /app/backend --include="*.py" \
  | grep -v __pycache__ | grep -v scripts/ | grep -v "def "
```

Every hit outside `core/db.py` should either be inside a function body
OR wrapped in try/except.  Convert direct-import users to
`from core.db import db`.

### If the deploy hits 8-minute mark still not ready

The lifespan should now yield in <2s.  If it doesn't:

```bash
# 1. Grep for `on_event("startup")` handlers that *aren't* wrapped by
#    the fire-and-forget monkey-patch:
grep -n "on_event(.startup." /app/backend/**/*.py

# 2. Confirm the monkey-patch is active by reading server.py — search for
#    `_make_nonblocking_add_event_handler` — it must be applied to BOTH
#    app.add_event_handler AND app.router.add_event_handler.

# 3. Watch for `[lifespan] fast-path` in backend logs on boot:
grep "fast-path" /var/log/supervisor/backend.err.log | tail -5
```

_Last updated: 2026-07-18 (Phase Ω — K8s Deploy Hardening)_
