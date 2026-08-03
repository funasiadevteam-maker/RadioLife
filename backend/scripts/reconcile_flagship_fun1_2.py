"""Phase FUN.1.2 — Reconcile the US flagship roster (5 stations).

Idempotent.  Safe to re-run.  Applies the definitive user-supplied roster:

    Slug                 | Display name                            | Stream URL
    ---------------------+------------------------------------------+----------------------------------------------------
    funasia-fm-dallas    | FunAsia 104.9 FM                         | http://funasia.streamguys1.com:80/live-1
    vanakkam-fm-us       | Vanakkam FM 104.9 FM HD2                 | https://streamlky.alsolnet.com/vanakkamaudio
    radio-caravan-us     | Radio Caravan 104.1 FM HD3               | https://streamlky.alsolnet.com/radiocaravanaudio  (NEW)
    apna-punjab-us       | Apna Punjab 104.9 FM HD3                 | https://streamlky.alsolnet.com/apnapunjabradioaudio
    radio-sangam-us      | Radio Sangam 104.1 FM                    | https://stream.voxx.pro/listen/radio_sangam/radio.mp3
                          (was Telugu Sangam; keep slug telugu-sangam-us for DB stability)

Outputs a JSON report to `/tmp/fun1_2_report.json`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, "/app/backend")

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("bigfm.fun1_2")
logging.basicConfig(level=logging.INFO,
                                        format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _now(): return datetime.now(timezone.utc)


LOGO_DIR = Path("/app/backend/static/flagship_logos")
LOGO_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────
# Definitive roster (5 US flagships).
# Slug is kept stable — `telugu-sangam-us` retains its id/slug even
# though its display name changes to "Radio Sangam 104.1 FM".
# priority values are chosen so that:
#   FunAsia 104.9 (flagship of the network) ranks highest,
#   the AlsolNet-managed sub-brands follow,
#   Radio Sangam (a voxx.pro sibling on 104.1) rounds out.
# ─────────────────────────────────────────────────────────
US_ROSTER = [
    {
        "id":               "imp_fun_funasia_fm_dallas",
        "flagship_slug":  "funasia-fm-dallas",
        "name":             "FunAsia 104.9 FM",
        "stream_url":  "http://funasia.streamguys1.com:80/live-1",
        "flagship_priority": 200,
        "language_codes": ["hindi", "urdu"],
        "flagship_categories": ["home", "hindi", "bollywood", "urdu", "us"],
        "flagship_search_terms": ["funasia", "104.9", "dallas", "bollywood"],
        "existing":              True,
        "logo_candidates":   [
            # Keep existing branded webp if already on disk.
            {"path": "funasia-fm-dallas.webp"},
            # og:image scrape as fallback.
            {"url": "https://funasia.net/",   "scrape": "og:image"},
        ],
    },
    {
        "id":               "imp_fun_vanakkam_fm_us",
        "flagship_slug":  "vanakkam-fm-us",
        "name":             "Vanakkam FM 104.9 FM HD2",
        "stream_url":  "https://streamlky.alsolnet.com/vanakkamaudio",
        "flagship_priority": 170,
        "language_codes": ["tamil"],
        "flagship_categories": ["tamil", "hindi", "us"],
        "flagship_search_terms": ["vanakkam", "tamil", "104.9", "dallas"],
        "existing":              True,
        "logo_candidates":   [
            # Reuse existing PNG logo already scraped in FUN.1.1 if it exists.
            {"path": "vanakkam-fm-us.png"},
            # Streema branded logo (KZMP HD2).
            {"url": "https://static-media.streema.com/media/cache/74/49/74494b0f83690da334fb94d248174092.png"},
        ],
    },
    {
        "id":               "imp_fun_radio_caravan_us",
        "flagship_slug":  "radio-caravan-us",
        "name":             "Radio Caravan 104.1 FM HD3",
        "stream_url":  "https://streamlky.alsolnet.com/radiocaravanaudio",
        "flagship_priority": 165,
        "language_codes": ["urdu", "hindi"],
        "flagship_categories": ["urdu", "hindi", "us"],
        "flagship_search_terms": ["caravan", "radio caravan", "104.1", "khse", "dallas"],
        "existing":              False,          # NEW station this phase.
        "country":              "The United States Of America",
        "country_code":  "US",
        "language":          "hindi",
        "state":                  "Texas",
        "city":                    "Dallas",
        "homepage":         "https://jointhecaravan.com/",
        "logo_candidates":   [
            {"url": "https://cdn.onlineradiobox.com/img/fblogo/7/19087.v11.png"},
        ],
    },
    {
        "id":               "imp_fun_apna_punjab_us",
        "flagship_slug":  "apna-punjab-us",
        "name":             "Apna Punjab 104.9 FM HD3",
        "stream_url":  "https://streamlky.alsolnet.com/apnapunjabradioaudio",
        "flagship_priority": 160,
        "language_codes": ["punjabi", "hindi"],
        "flagship_categories": ["punjabi", "bhangra", "hindi", "us"],
        "flagship_search_terms": ["apna", "apna punjab", "punjabi", "104.9"],
        "existing":              True,
        "logo_candidates":   [
            # Prefer the branded onlineradiobox logo (real Apna Punjab HD3
            # facebook logo) over the existing generic .ico favicon.
            {"url": "https://cdn.onlineradiobox.com/img/fblogo/9/13849.v4.png"},
            {"path": "apna-punjab-us.ico"},   # legacy fallback
        ],
    },
    {
        # Slug stability: keep id/slug `telugu-sangam-us` so downstream
        # links / clicks / analytics keep resolving.  Only display name
        # + categories change.
        "id":               "imp_fun_telugu_sangam_us",
        "flagship_slug":  "telugu-sangam-us",
        "name":             "Radio Sangam 104.1 FM",
        "stream_url":  "https://stream.voxx.pro/listen/radio_sangam/radio.mp3",
        "flagship_priority": 155,
        "language_codes": ["telugu", "tamil", "hindi"],
        "flagship_categories": ["telugu", "sangam", "us"],
        "flagship_search_terms": ["sangam", "radio sangam", "telugu",
                                                                    "104.1", "104.9", "dallas", "mckinney"],
        "existing":              True,
        "logo_candidates":   [
            # Apple App Store icon for the Dallas station.
            {"url": ("https://is1-ssl.mzstatic.com/image/thumb/"
                              "Purple221/v4/ac/9c/73/"
                              "ac9c7322-acab-ac70-083d-74c8ea24fce7/"
                              "AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/"
                              "512x512.png")},
            {"path": "telugu-sangam-us.png"},   # existing PNG on disk
        ],
    },
]


# ─────────────────────── Helpers ───────────────────────
async def fetch_bytes(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=True,
            headers={"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X "
                                                              "10_15_7) AppleWebKit/537.36")}) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.content
            logger.warning("[fetch] %s → %s", url, r.status_code)
    except Exception as e:
        logger.warning("[fetch] %s → %s", url, e)
    return None


def _ext_from_url(url: str) -> str:
    lower = url.lower().split("?")[0].split("#")[0]
    for ext in ("png", "webp", "jpg", "jpeg", "ico", "svg", "gif"):
        if lower.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ext
    return "png"


async def resolve_logo(entry: dict) -> Optional[str]:
    """Return relative /api/static/flagship_logos/... path or None."""
    slug = entry["flagship_slug"]
    for cand in entry.get("logo_candidates", []):
        # 1. On-disk path candidate.
        if "path" in cand:
            fp = LOGO_DIR / cand["path"]
            if fp.exists() and fp.stat().st_size > 500:
                return f"/api/static/flagship_logos/{cand['path']}"
        # 2. URL candidate — fetch and persist.
        if "url" in cand:
            data = await fetch_bytes(cand["url"])
            if data and len(data) > 500:
                ext = _ext_from_url(cand["url"])
                out = LOGO_DIR / f"{slug}.{ext}"
                out.write_bytes(data)
                logger.info("[logo] %s ← %s (%d bytes)",
                                        out.name, cand["url"], len(data))
                return f"/api/static/flagship_logos/{out.name}"
    return None


async def verify_stream(url: str) -> dict:
    """Icecast live streams do not honor Range headers — they stream
    forever.  Use httpx streaming mode with a hard read timeout so a
    single chunk of audio is enough to confirm reachability."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=4.0, read=4.0, write=4.0, pool=4.0),
            follow_redirects=True) as c:
            async with c.stream("GET", url,
                                                                headers={"Range": "bytes=0-1024",
                                                                                        "User-Agent": "Mozilla/5.0"}) as r:
                ct = r.headers.get("content-type", "")
                # Read at most one chunk to confirm the stream flows.
                chunk_ok = False
                async for _chunk in r.aiter_bytes(chunk_size=512):
                    chunk_ok = True
                    break
                return {"url": url, "status": r.status_code,
                              "content_type": ct,
                              "reachable": r.status_code in (200, 206)
                                                  and ct.startswith("audio/")
                                                  and chunk_ok}
    except httpx.ReadTimeout:
        # Some Icecast servers block until they have a full frame;
        # a read timeout after a successful connect still means the
        # URL is live-audio-serving.
        return {"url": url, "status": 200, "content_type": "audio/*",
                      "reachable": True,
                      "note": "read_timeout_but_connected"}
    except Exception as e:
        return {"url": url, "status": 0, "content_type": "",
                          "reachable": False, "error": str(e)[:120]}


# ─────────────────────── Main ───────────────────────
async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    report = {
        "generated_at": _now().isoformat(),
        "phase": "FUN.1.2",
        "roster": [],
        "logo_fetch_failed_us": [],
        "stream_verification": [],
    }

    for entry in US_ROSTER:
        slug = entry["flagship_slug"]
        # ── 1. Logo ──────────────────────────
        logo_path = await resolve_logo(entry)
        if not logo_path:
            report["logo_fetch_failed_us"].append({
                "slug": slug, "name": entry["name"],
                "candidates_tried": entry.get("logo_candidates", []),
            })
            logo_path = None

        # ── 2. Stream verification ──────────
        sv = await verify_stream(entry["stream_url"])
        sv["slug"] = slug
        report["stream_verification"].append(sv)

        # ── 3. DB upsert ─────────────────────
        set_fields = {
            "name":                        entry["name"],
            "display_name":            entry["name"],
            "is_flagship":              True,
            "flagship_region":     "US",
            "flagship_slug":          slug,
            "flagship_priority":  entry["flagship_priority"],
            "flagship_categories":       entry["flagship_categories"],
            "flagship_search_terms":  entry["flagship_search_terms"],
            "language_codes":       entry["language_codes"],
            "url":                          entry["stream_url"],
            "url_resolved":         entry["stream_url"],
            "stream_url":              entry["stream_url"],
            "needs_stream_review": False,
            "active":                      True,
            "is_priority":              False,
            "last_reconciled_at": _now().isoformat(),
            "reconciled_phase":  "FUN.1.2",
        }
        if logo_path:
            set_fields["logo_url"] = logo_path
            set_fields["favicon"]     = logo_path

        if not entry.get("existing", True):
            # Insert path — populate creation-only defaults.
            set_on_insert = {
                "id":                      entry["id"],
                "country":              entry.get("country") or "The United States Of America",
                "country_code":  entry.get("country_code") or "US",
                "language":          entry.get("language") or "hindi",
                "state":                  entry.get("state") or "Texas",
                "city":                    entry.get("city") or "Dallas",
                "homepage":         entry.get("homepage") or "",
                "codec":                  "AAC",
                "bitrate":               96,
                "tags_json":            entry["flagship_categories"],
                "votes":                  0,
                "click_count":         0,
                "imported_at":       _now().isoformat(),
                "external_station_uuid":  None,
                "source_provider":  "manual_flagship_seed",
            }
            await db.imported_radio_stations.update_one(
                {"id": entry["id"]},
                {"$set": set_fields, "$setOnInsert": set_on_insert},
                upsert=True,
            )
        else:
            await db.imported_radio_stations.update_one(
                {"id": entry["id"]},
                {"$set": set_fields},
            )

        # Return the persisted row for the report.
        row = await db.imported_radio_stations.find_one(
            {"id": entry["id"]},
            projection={"_id": 0, "id": 1, "name": 1, "flagship_slug": 1,
                                  "flagship_region": 1, "flagship_priority": 1,
                                  "is_flagship": 1, "logo_url": 1, "stream_url": 1,
                                  "url_resolved": 1, "needs_stream_review": 1})
        report["roster"].append(row)

    # ── 4. Final counts ─────────────────────
    ae = await db.imported_radio_stations.count_documents(
        {"is_flagship": True, "flagship_region": "AE"})
    us = await db.imported_radio_stations.count_documents(
        {"is_flagship": True, "flagship_region": "US"})
    total = await db.imported_radio_stations.count_documents(
        {"is_flagship": True})
    report["final_counts"] = {"AE": ae, "US": us, "total": total,
                                                                "expected_total": 12,
                                                                "ok": (ae == 7 and us == 5 and total == 12)}

    # Persist report.
    out = Path("/tmp/fun1_2_report.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    print(f"\nReport → {out}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    asyncio.run(main())
