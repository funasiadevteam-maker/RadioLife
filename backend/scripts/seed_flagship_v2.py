"""Phase FUN.1-v2 — Geo-aware flagship reconciliation.

Idempotent. Safe to re-run.  Reconciles the FUN.1 flagship set with the
final brief's 7 Dubai + 4 US station lineup, updates streams to
funasia.streamguys1.com/live2-live7, marks non-flagship Dubai stations
as `is_priority`, and demotes stations no longer in the flagship list.

Report format:
    {
        'dubai_flagship_count': int,       'us_flagship_count': int,
        'demoted': [slug],                       'added': [slug],
        'stream_url_missing': [slug],       'logo_fetch_failed': [slug],
        'priority_dubai_count': int,
    }
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("bigfm.flagship_v2")


def _now(): return datetime.now(timezone.utc)


# ─── Final flagship manifest (7 AE + 4 US) ────────────────────
DUBAI_FLAGSHIPS = [
    # (slug, name, stream_url, keep_existing_stream)
    ("luv-1071-uae",       "Luv 107.1 UAE",           "https://funasia.streamguys1.com/live2", False),
    ("beat-978-uae",         "Beat 97.8",                     "https://funasia.streamguys1.com/live3", False),
    ("big-1062-uae",         "Big 106.2 UAE",             "https://funasia.streamguys1.com/live4", False),
    ("beat-anthems",       "Beat Anthems",             "https://funasia.streamguys1.com/live5", False),
    ("urban-beat",             "Urban Beat",                 "https://funasia.streamguys1.com/live6", False),
    ("chilled-luv",             "Chilled Luv",                 "https://funasia.streamguys1.com/live7", False),
    ("talk-1003-uae",       "Talk 100.3 UAE",           None, True),      # keep existing
]

# US flagships — reuse pre-existing rows where slug matches, insert 2 new.
US_FLAGSHIPS = [
    # (slug, name, city, languages, description, tags)
    ("funasia-fm-dallas",     "FunAsia 104.9 FM",       "Dallas", ["hindi", "urdu"],
      "FunAsia 104.9 FM — Bollywood + desi talk from Dallas.",
      ["music", "talk", "south_asian", "bollywood", "hindi", "urdu"]),
    ("telugu-sangam-us",     "Telugu Sangam",           "Dallas", ["telugu"],
      "Telugu Sangam — Telugu music + talk community.",
      ["music", "talk", "south_asian", "telugu"]),
    ("vanakkam-fm-us",         "Vanakkam FM",                 "Dallas", ["tamil"],
      "Vanakkam FM — Tamil music + community radio.",
      ["music", "talk", "south_asian", "tamil"]),
    ("apna-punjab-us",         "Apna Punjab",                 "Dallas", ["punjabi"],
      "Apna Punjab — Punjabi music + culture radio.",
      ["music", "talk", "south_asian", "punjabi"]),
]

# US station website (used for future logo scraping / manual stream URL entry)
US_META = {
    "vanakkam-fm-us":     {"homepage": "https://vanakkamfm.net/",       "priority": 160},
    "apna-punjab-us":       {"homepage": "https://apnapunjab.net/",       "priority": 160},
    "telugu-sangam-us": {"homepage": "https://telugusangam.net/",   "priority": 160},
    "funasia-fm-dallas": {"homepage": "https://funasia.net/",             "priority": 180},
}

# Slugs that USED to be flagship but are NOT in the final lineup.
DEMOTE_SLUGS = ["big-melodies", "luv-legends", "radio-sangam-dallas", "radio-caravan-dallas"]


async def run(db) -> dict:
    report = {
        "dubai_flagship_count":     0, "us_flagship_count":        0,
        "demoted":                            [], "added":                                 [],
        "stream_url_missing":           [], "logo_fetch_failed":            [],
        "priority_dubai_count":       0,
        "url_updates":                       [],
    }
    now = _now()

    # 1. Update Dubai flagships — set flagship_region=AE, country_code=AE,
    #      is_priority=false, and swap stream URLs to live2-live7.
    for slug, name, new_url, keep_stream in DUBAI_FLAGSHIPS:
        row = await db.imported_radio_stations.find_one({"flagship_slug": slug})
        if not row:
            logger.warning("[flagship_v2] Dubai flagship missing: %s", slug)
            continue
        upd = {
            "is_flagship":       True,
            "flagship_region": "AE",
            "country_code":     "AE",
            "is_priority":         False,
            "updated_at":         now,
        }
        if not keep_stream and new_url:
            if row.get("url_resolved") != new_url:
                report["url_updates"].append({"slug": slug,
                                                                                    "old": row.get("url_resolved"),
                                                                                    "new": new_url})
                upd["url_resolved"] = new_url
                upd["url"] = new_url
        await db.imported_radio_stations.update_one(
            {"flagship_slug": slug}, {"$set": upd})
        report["dubai_flagship_count"] += 1

    # 2. Reconcile US flagships.
    for slug, name, city, langs, desc, tags in US_FLAGSHIPS:
        row = await db.imported_radio_stations.find_one({"flagship_slug": slug})
        if row:
            # Existing (funasia-fm-dallas) — just tag it.
            upd = {
                "is_flagship":               True,
                "flagship_region":         "US",
                "country_code":             "US",
                "is_priority":                 False,
                "flagship_categories":  tags,
                "language_codes":         langs,
                "language":                     " ".join(langs),
                "description":                 desc,
                "flagship_priority":       (US_META.get(slug) or {}).get("priority", 160),
                "updated_at":                 now,
            }
            await db.imported_radio_stations.update_one(
                {"flagship_slug": slug}, {"$set": upd})
        else:
            # Create the new US flagship rows.
            homepage = (US_META.get(slug) or {}).get("homepage", "https://funasia.net/")
            new_id = f"imp_fun_{slug.replace('-', '_')}"
            new_uuid = f"bigfm-fun1v2-{slug}"
            new_doc = {
                "id":                                new_id,
                "provider":                    "funasia_flagship_seed_v2",
                "name":                            name,
                "homepage":                    homepage,
                "url":                              "",
                "url_resolved":             "",
                "favicon":                      f"https://ui-avatars.com/api/?name={name.replace(' ', '+')}&size=256&background=8b5cf6&color=fff&bold=true&font-size=0.4",
                "tags_raw":                    ",".join(tags),
                "tags_json":                  tags,
                "country":                      "United States",
                "country_code":            "US",
                "city":                              city,
                "language":                    " ".join(langs),
                "language_codes":         langs,
                "codec":                          "mp3",
                "bitrate":                      128,
                "hls":                              False,
                "active":                          True,
                "description":                desc,
                "frequency":                  "Web · US",
                "is_flagship":               True,
                "flagship_region":         "US",
                "is_priority":                 False,
                "flagship_slug":            slug,
                "flagship_priority":       (US_META.get(slug) or {}).get("priority", 160),
                "flagship_categories":  tags,
                "flagship_search_terms": [name.split()[0].lower()] + tags[:3],
                "flagship_since":            now,
                "flagship_by":                "system_seed_v2",
                "external_station_uuid": new_uuid,
                "imported_at":              now,
                "updated_at":                now,
                "playable_status":         "pending",
                "needs_stream_review":  True,
            }
            await db.imported_radio_stations.insert_one(new_doc)
            report["added"].append(slug)
            report["stream_url_missing"].append(slug)
        report["us_flagship_count"] += 1

    # 3. Demote outgoing flagships to `is_priority` (if Dubai) or plain.
    for slug in DEMOTE_SLUGS:
        row = await db.imported_radio_stations.find_one({"flagship_slug": slug})
        if not row:
            continue
        upd = {
            "is_flagship":       False,
            "flagship_region": None,
            "is_priority":         (row.get("city") == "Dubai"),
            "updated_at":         now,
        }
        await db.imported_radio_stations.update_one(
            {"flagship_slug": slug}, {"$set": upd})
        report["demoted"].append(slug)

    # 4. Sweep Dubai non-flagships → is_priority=true.
    r_pri = await db.imported_radio_stations.update_many(
        {"is_flagship": {"$ne": True},
          "$or": [{"city": "Dubai"},
                          {"country_code": "AE"},
                          {"country": {"$regex": "United Arab Emirates", "$options": "i"}}]},
        {"$set": {"is_priority": True, "updated_at": now}})
    report["priority_dubai_count"] = r_pri.modified_count
    # Community-radio-stations Dubai → priority too (parallel collection).
    if "community_radio_stations" in await db.list_collection_names():
        r_pri2 = await db.community_radio_stations.update_many(
            {"is_flagship": {"$ne": True},
              "$or": [{"city": "Dubai"},
                              {"country_code": "AE"}]},
            {"$set": {"is_priority": True, "updated_at": now}})
        report["priority_dubai_count"] += r_pri2.modified_count

    # 5. Logo fetch pass — best-effort via existing favicon column.
    #      Full site scraping is deferred to the reporter; here we just mark
    #      any flagship whose favicon is still the ui-avatars fallback so the
    #      report list is clear.
    async for d in db.imported_radio_stations.find({"is_flagship": True}):
        if not d.get("favicon") or str(d.get("favicon", "")).startswith("https://ui-avatars.com"):
            report["logo_fetch_failed"].append(d.get("flagship_slug"))

    return report


# CLI usage
if __name__ == "__main__":
    import json, sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    async def _cli():
        db = AsyncIOMotorClient(
            os.environ.get("MONGO_URL")
        ).get_database(os.environ.get("DB_NAME", "bigfm"))
        r = await run(db)
        print(json.dumps(r, indent=2, default=str))
    asyncio.run(_cli())
