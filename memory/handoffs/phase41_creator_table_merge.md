# Phase 41 — `podcast_creators` ↔ Social Pages Merge (Design Doc)

> **Status**: DESIGN ONLY. Implementation lands in Phase 41 Session 1.
> **Anchor**: HEAD `a35b4d1` · commit 107.

## 0. Why merge

The Phase 41 brief introduces six "page types":
`personal_radio`, `business_radio`, `influencer_radio`,
`community_radio`, `event_radio`, plus the existing `podcast` (Phase 36).

These share ~90% of the data + workflow plumbing:
- A creator/owner (`user_id`)
- A globally unique slug
- A display name + cover image + bio
- An approval workflow (`application_status` ∈ pending/approved/rejected)
- A follower count + follow/unfollow relationship
- A moderation surface (admin queue)
- An analytics surface (followers, listening hours, posts)

Forking these into two parallel tables (`podcast_creators` + new
`social_pages`) would duplicate the approval admin UI, the follower
notification fanout, the analytics roll-up, and the Stripe Connect
onboarding flow — the four things we are trying NOT to rebuild.

**Decision (locked by user)**: extend `podcast_creators` in-place via a
`page_type` discriminator.

---

## 1. Current `podcast_creators` schema (from Phase 36a)

Source: `/app/backend/services/podcasts.py` lines 70–88.

```python
{
  "id":                  "crt_<14-hex>",         # primary key
  "user_id":             "<uuid>",               # owner
  "display_name":        "<≤80 chars>",
  "bio":                 "<≤1000 chars>",
  "contact_email":       "<email>",
  "market":              "<city slug, default 'dubai'>",
  "application_status":  "pending"|"approved"|"rejected",
  "applied_at":          datetime,
  "approved_at":         datetime|None,
  "approved_by":         "<admin user_id>"|None,
  "rejection_reason":    str|None,
}
```

Existing endpoints that read/write this table:
- `POST /api/podcasts/creator/apply`     → submit_creator_application
- `GET  /api/podcasts/creator/me`         → get_creator_by_user
- `GET  /api/admin/podcasts/applications` → list pending
- `POST /api/admin/podcasts/applications/:id/approve|reject`

---

## 2. Target unified schema (post-Phase 41 Session 1)

All NEW columns are nullable with safe defaults so existing rows
(which are all `page_type='podcast'` after the migration) keep working
unchanged.

```python
{
  # ─── existing (unchanged) ─────────────────────────────
  "id":                  "crt_<14-hex>",
  "user_id":             "<uuid>",
  "display_name":        "<≤80>",
  "bio":                 "<≤1000>",
  "contact_email":       "<email>",
  "market":              "<city slug>",
  "application_status":  "pending|approved|rejected",
  "applied_at":          datetime,
  "approved_at":         datetime|None,
  "approved_by":         str|None,
  "rejection_reason":    str|None,

  # ─── Phase 41 additions (all default None / empty) ────
  "page_type":           "podcast",       # default — existing rows
                                          # valid: podcast | personal_radio
                                          #        | business_radio
                                          #        | influencer_radio
                                          #        | community_radio
                                          #        | event_radio
  "slug":                None,            # globally unique, set on first publish
  "cover_image_url":     None,
  "cover_color":         None,
  "verified":            False,           # influencer badge
  "station_id":          None,            # FK → community_radio_stations
                                          # populated for *_radio page_types
  "business_id":         None,            # FK → businesses
                                          # populated only for business_radio
  "event_starts_at":     None,            # event_radio only
  "event_ends_at":       None,            # event_radio only
  "follower_count":      0,               # denormalized cache
  "stripe_account_id":   None,            # connect Express id, set after onboard
  "stripe_onboarded":    False,
  "deactivated_at":      None,            # soft-delete
}
```

### Indexes (new)
- `slug` — **partial unique** index where `slug IS NOT NULL` (allows
  legacy podcast rows without slug to coexist before we backfill).
- `(page_type, application_status)` — admin queue queries.
- `user_id` (already unique by convention) — keep as-is.
- `station_id` (sparse) — reverse lookup.
- `business_id` (sparse) — reverse lookup.

---

## 3. Migration script outline (non-destructive)

```python
async def migrate_phase41_creator_table(db) -> dict:
    """Idempotent — safe to run multiple times. Run at startup once."""
    # 1. Backfill page_type on all existing rows that lack it.
    r1 = await db.podcast_creators.update_many(
        {"page_type": {"$exists": False}},
        {"$set": {"page_type": "podcast",
                  "follower_count": 0,
                  "verified": False,
                  "stripe_onboarded": False}})

    # 2. Indexes (idempotent — Mongo no-ops if already present).
    await db.podcast_creators.create_index(
        "slug", unique=True, sparse=True,
        partialFilterExpression={"slug": {"$type": "string"}},
        name="creators_slug_unique")
    await db.podcast_creators.create_index(
        [("page_type", 1), ("application_status", 1)],
        name="creators_type_status")
    await db.podcast_creators.create_index(
        "station_id", sparse=True, name="creators_station_id")
    await db.podcast_creators.create_index(
        "business_id", sparse=True, name="creators_business_id")

    # 3. Backfill follower_count for podcast rows from podcast_followers.
    pipe = [{"$group": {"_id": "$channel_id", "n": {"$sum": 1}}}]
    # …feeds podcast_channels.follower_count, NOT podcast_creators —
    # podcasts have a per-channel follower count. New page_types use the
    # podcast_creators.follower_count directly. See §5.

    return {"backfilled": r1.modified_count}
```

**Run policy**: wire into the existing startup hook in `server.py`
right after `seed_channels`. Idempotent — uses `update_many` filtered
on missing keys; `create_index` no-ops on existing index.

---

## 4. Naming decision — keep `podcast_creators` or rename to `creator_pages`?

**Recommendation: KEEP the table name `podcast_creators`**.

Reasons:
- 50+ places in the codebase reference `db.podcast_creators` directly
  (services/podcasts.py, routes/podcasts.py, the admin UI). Rename =
  churn + risk for zero functional benefit.
- A rename would require either:
  (a) full dual-write/cutover migration with rollback path, or
  (b) a MongoDB view aliasing the renamed collection — supported but
       adds latency and a layer of indirection
- A Python module-level alias would be cleaner but cosmetic.

**Compromise**: introduce a Python service-layer alias for conceptual
clarity:

```python
# services/creators.py  (NEW — wraps services/podcasts.py functions)
"""Phase 41 — Unified creator-page interface.

Wraps services/podcasts.py functions for the multi-page-type world.
The underlying collection stays `podcast_creators` to avoid migration
churn — only the Python module name reads as "creators" now.
"""
from services.podcasts import (
    get_creator_by_user      as get_page_owner,
    submit_creator_application as apply_for_page,
    approve_creator          as approve_page,
    reject_creator           as reject_page,
)
```

New code in Phase 41 imports from `services.creators`; legacy podcast
code keeps importing from `services.podcasts` unchanged.

---

## 5. Followers — extend or fork?

Today: `podcast_followers {user_id, channel_id, followed_at}` — one row
per follow, **keyed on `channel_id`** (the podcast channel, NOT the
creator).

For Phase 41, follows are at the **page level** (you follow a creator
not a single podcast channel). Two options:

**Option A — Extend `podcast_followers`** (recommended):
```python
{
  "user_id":      str,
  "channel_id":   str|None,  # set for podcast follows (legacy)
  "creator_id":   str|None,  # set for page follows (new)
  "page_type":    str,        # podcast | personal_radio | …
  "followed_at":  datetime,
}
```
Add partial unique indexes:
- `(user_id, channel_id)` where `channel_id IS NOT NULL`
- `(user_id, creator_id)` where `creator_id IS NOT NULL`

Legacy podcast follows keep working; new follows write `creator_id`.

**Option B — New `social_follows` collection**.
- Cleaner separation; doubles the notification fanout cost.

**Decision: Option A.** Lower migration cost, single notification
fanout path.

---

## 6. Backwards-compat guarantees

All existing `/api/podcasts/*` endpoints continue to work unchanged:

| Endpoint | Behaviour after merge |
|---|---|
| `POST /api/podcasts/creator/apply` | Writes `page_type='podcast'` automatically |
| `GET /api/podcasts/creator/me` | Returns creator row regardless of page_type, frontend filters |
| `GET /api/admin/podcasts/applications` | Adds `?page_type=podcast` filter to scope to legacy view (the new admin queue at `/api/admin/social` will be unfiltered) |
| `GET /api/podcasts/channels/:slug` | Unchanged — operates on `podcast_channels`, not the merged table |

---

## 7. Sample migration diff (preview)

```diff
--- services/podcasts.py
+++ services/podcasts.py
@@ submit_creator_application @@
     doc = {
         "id":                            _gen("crt"),
         "user_id":                  user_id,
         "display_name":        display_name.strip()[:80],
         "bio":                          (bio or "").strip()[:1000],
         "contact_email":        contact_email.strip()[:120],
         "market":                    (market or "dubai")[:32],
         "application_status": "pending",
         "applied_at":              _now(),
         "approved_at":           None,
         "approved_by":           None,
         "rejection_reason":   None,
+        # Phase 41 — multi-page-type discriminator.  Default 'podcast'
+        # for backwards compat; non-podcast pages are created via the
+        # new services/creators.py apply_for_page() entrypoint.
+        "page_type":               "podcast",
+        "slug":                       None,
+        "cover_image_url":   None,
+        "cover_color":           None,
+        "verified":                  False,
+        "station_id":             None,
+        "business_id":         None,
+        "event_starts_at":   None,
+        "event_ends_at":      None,
+        "follower_count":     0,
+        "stripe_account_id": None,
+        "stripe_onboarded":  False,
+        "deactivated_at":     None,
     }
     await db.podcast_creators.insert_one(doc)
```

```diff
+++ services/creators.py   (NEW)
+"""Phase 41 — Unified creator-page interface (alias wrapper)."""
+from services.podcasts import (
+    get_creator_by_user      as get_page_owner,
+    submit_creator_application as apply_for_page,
+    approve_creator          as approve_page,
+    reject_creator           as reject_page,
+)
+
+
+async def apply_for_radio_page(db, *, user_id: str, display_name: str,
+                               bio: str, contact_email: str, market: str,
+                               page_type: str, slug: str) -> dict:
+    """Phase 41 — same as apply_for_page but with page_type + slug."""
+    if page_type not in {"personal_radio", "business_radio",
+                         "influencer_radio", "community_radio",
+                         "event_radio"}:
+        raise ValueError(f"unsupported page_type: {page_type}")
+    # Slug uniqueness — enforced by the partial unique index.
+    # …
```

```diff
+++ server.py  @@startup hook@@
+from services.podcasts import migrate_phase41_creator_table
+
+@app.on_event("startup")
+async def _phase41_creator_migration():
+    r = await migrate_phase41_creator_table(db)
+    logger.info(f"[phase41] creator table migration: {r}")
```

---

## 8. Open questions for user review

1. **Slug ownership at apply-time vs publish-time**: should the slug be
   picked during the wizard (and reserved on draft save) or only on
   publish? Recommend at wizard step 1 so the user can preview their
   `/r/<slug>` URL while still drafting.
2. **Verified badge auto-granting**: any creator with >10k followers
   automatically `verified=True`? Or admin-only manual grant?
   Recommend admin-only in MVP, automation later.
3. **Single-user multi-page**: should one `user_id` be allowed to own
   multiple pages (e.g. a podcaster also creates a personal_radio
   page)? Recommend YES — unique key is `(user_id, page_type)` not
   `user_id` alone. Slight schema impact noted.

---

## 9. Risk assessment

| Risk | Mitigation |
|---|---|
| Existing podcast endpoint regressions | Migration adds NEW fields only, no field renames/deletes. Run full Phase 36 pytest before/after migration. |
| Slug collision between legacy podcast titles and new radio pages | New `slug` partial-unique index spans the whole table; same slug can't be reused across page types. |
| `(user_id, page_type)` uniqueness if we lift the single-per-user constraint | Add compound unique index post-decision in §8.3. |
| Migration runs at every startup | Idempotent — backfill filter `page_type: {$exists: False}` matches zero rows after the first run. Cost: one cheap indexed query. |

---

## 10. Implementation checklist (carried into Session 1)

- [ ] Add `migrate_phase41_creator_table()` to `services/podcasts.py`
- [ ] Wire migration into `server.py` startup hook
- [ ] Create `services/creators.py` alias module
- [ ] Add `apply_for_radio_page()` for non-podcast page types
- [ ] Add `?page_type=` filter to `/api/admin/podcasts/applications`
- [ ] Extend `podcast_followers` schema + partial indexes
- [ ] Add Pytest: post-migration, existing rows have `page_type='podcast'`
      and Phase 36 endpoints still work end-to-end
- [ ] Add Pytest: slug uniqueness enforced across page types
