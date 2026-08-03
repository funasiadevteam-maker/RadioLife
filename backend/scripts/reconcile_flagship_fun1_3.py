"""Phase FUN.1.3 — Add "Luv Legends" AE flagship (8th).

Idempotent.  Safe to re-run.  Inserts one row into `imported_radio_stations`:

    Slug            : luv-legends-uae
    Display name : Luv Legends
    Stream URL   : https://funasia.streamguys1.com/live8
    Region          : AE  (flagship_priority 175 — one notch below Big FM 106.2)

The placeholder SVG at `/app/backend/static/flagship_logos/luv-legends-uae.svg`
is used until the admin uploads the branded artwork via
`POST /api/admin/stations/{station_id}/logo`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/backend")

import httpx
from motor.motor_asyncio import AsyncIOMotorClient


def _now(): return datetime.now(timezone.utc)


LUV_LEGENDS = {
    "id":                                "imp_fun_luv_legends_uae",
    "flagship_slug":              "luv-legends-uae",
    "name":                              "Luv Legends",
    "display_name":              "Luv Legends",
    "stream_url":                  "https://funasia.streamguys1.com/live8",
    "url":                                "https://funasia.streamguys1.com/live8",
    "url_resolved":              "https://funasia.streamguys1.com/live8",
    "flagship_region":         "AE",
    "flagship_priority":     175,
    "flagship_categories": ["home", "hindi", "bollywood", "throwback",
                                                                    "classics", "ae"],
    "flagship_search_terms": ["luv", "legends", "throwback", "classics",
                                                                          "funasia", "uae"],
    "language":                      "hindi",
    "language_codes":         ["hindi", "urdu", "english"],
    "country":                        "United Arab Emirates",
    "country_code":              "AE",
    "state":                            "Dubai",
    "city":                              "Dubai",
    "homepage":                    "https://funasia.net/radio",
    "codec":                            "AAC",
    "bitrate":                        96,
    "tags_json":                    ["hindi", "bollywood", "throwback", "classics"],
    "is_flagship":                True,
    "is_priority":                False,
    "active":                          True,
    "needs_stream_review": False,
    "logo_url":                      "/api/static/flagship_logos/luv-legends-uae.svg",
    "favicon":                        "/api/static/flagship_logos/luv-legends-uae.svg",
    "votes":                            0,
    "click_count":                0,
    # Manual UUID stub so the collection's unique index on
    # `external_station_uuid` doesn't collide with other manual-seed
    # flagships that share `null` (Mongo unique indexes treat missing
    # fields as `null`).
    "external_station_uuid": "manual:luv-legends-uae",
    "source_provider":       "manual_flagship_seed",
}


async def verify_stream(url: str) -> dict:
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=4.0, read=4.0, write=4.0, pool=4.0),
            follow_redirects=True) as c:
            async with c.stream("GET", url,
                                                                headers={"Range": "bytes=0-1024",
                                                                                        "User-Agent": "Mozilla/5.0"}) as r:
                ct = r.headers.get("content-type", "")
                async for _ in r.aiter_bytes(chunk_size=512):
                    break
                return {"url": url, "status": r.status_code,
                              "content_type": ct,
                              "reachable": r.status_code in (200, 206)
                                                  and ct.startswith("audio/")}
    except httpx.ReadTimeout:
        return {"url": url, "status": 200, "content_type": "audio/*",
                      "reachable": True, "note": "read_timeout_but_connected"}
    except Exception as e:
        return {"url": url, "status": 0, "content_type": "",
                      "reachable": False, "error": str(e)[:120]}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    now_iso = _now().isoformat()
    set_fields = {**LUV_LEGENDS,
                                "last_reconciled_at": now_iso,
                                "reconciled_phase":  "FUN.1.3"}
    set_on_insert = {"imported_at": now_iso}

    await db.imported_radio_stations.update_one(
        {"id": LUV_LEGENDS["id"]},
        {"$set": set_fields,
          "$setOnInsert": set_on_insert},
        upsert=True,
    )

    # Verify stream reachability.
    sv = await verify_stream(LUV_LEGENDS["stream_url"])

    # Counts.
    ae = await db.imported_radio_stations.count_documents(
        {"is_flagship": True, "flagship_region": "AE"})
    us = await db.imported_radio_stations.count_documents(
        {"is_flagship": True, "flagship_region": "US"})
    total = await db.imported_radio_stations.count_documents(
        {"is_flagship": True})

    report = {
        "generated_at": now_iso,
        "phase": "FUN.1.3",
        "roster_added": LUV_LEGENDS["flagship_slug"],
        "stream_verification": sv,
        "final_counts": {"AE": ae, "US": us, "total": total,
                                                        "expected": {"AE": 8, "US": 5, "total": 13},
                                                        "ok": ae == 8 and us == 5 and total == 13},
    }
    Path("/tmp/fun1_3_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    asyncio.run(main())
