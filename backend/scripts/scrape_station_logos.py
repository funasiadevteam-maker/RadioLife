"""Phase K.10 — Backfill scraped station logos.

Scans `imported_radio_stations` for stations missing an `image_url` and
whose last scrape attempt was either never done OR > 30 days ago.
Runs the K.10 logo scraper on each, persists results, prints a tidy
summary.

Usage:
    python3 backend/scripts/scrape_station_logos.py
    python3 backend/scripts/scrape_station_logos.py --limit 50
    python3 backend/scripts/scrape_station_logos.py --refresh-days 30
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.scrape_logos")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--refresh-days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.refresh_days)

    # Stations with NO image_url, has a homepage, and (never attempted OR
    # attempted > refresh_days ago).
    q = {
        "$or": [{"image_url": {"$in": [None, ""]}},
                      {"image_url": {"$exists": False}}],
        "homepage": {"$nin": [None, ""]},
        "$and": [{
            "$or": [{"logo_scrape_last_attempt": {"$exists": False}},
                          {"logo_scrape_last_attempt": {"$lt": cutoff}}],
        }],
    }
    total = await db.imported_radio_stations.count_documents(q)
    print(f"[logo_scrape] candidates_total={total}  "
                f"processing_up_to={args.limit}  dry_run={args.dry_run}")

    if args.dry_run:
        return

    from services.station_logo_scraper import scrape_and_persist

    ok = no_logo = no_homepage = 0
    cur = db.imported_radio_stations.find(q,
                  {"id": 1, "_id": 1, "name": 1, "homepage": 1}).limit(args.limit)
    async for doc in cur:
        res = await scrape_and_persist(db, doc)
        if res.get("ok"):
            ok += 1
        elif res.get("reason") == "no_homepage":
            no_homepage += 1
        else:
            no_logo += 1
    print(f"[logo_scrape] scraped={ok} no_logo_found={no_logo} "
                f"no_homepage={no_homepage} "
                f"processed={ok + no_logo + no_homepage}")


if __name__ == "__main__":
    asyncio.run(main())
