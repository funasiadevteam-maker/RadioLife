"""Phase K.URGENT — DB cleanup for the geo-leak.

Deletes / re-tags any `news_articles` row whose persisted `market`
points at a country that doesn't match the article's actual URL host
(per the same whitelist used by the live geo-filter in
`services.news_api_provider._matches_country_domain`).

Behaviour:
    • Pass 1: re-tag articles whose URL host matches a different
        country's whitelist (e.g. a livemint.com row tagged market=dfw
        gets retagged to market=india).
    • Pass 2: delete articles that don't match ANY country's whitelist
        for the market they were persisted under.
    • Idempotent — re-running is a no-op.

Usage:
    python3 backend/scripts/cleanup_news_geo_leak.py
    python3 backend/scripts/cleanup_news_geo_leak.py --dry-run
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.cleanup_news_geo")


# Lowercased market → expected country.
MARKET_TO_COUNTRY = {
    "dfw":              "us",  "dallas":          "us",
    "new_york":      "us",  "los_angeles": "us",
    "sf":              "us",  "chicago":      "us",
    "miami":          "us",  "seattle":      "us",
    "boston":          "us",  "houston":      "us",
    "dubai":          "ae",  "ae":                  "ae",
    "uae":              "ae",  "abu_dhabi":      "ae",
    "london":          "gb",  "gb":                  "gb",
    "uk":                "gb",
    "india":          "in",  "mumbai":          "in",
    "delhi":          "in",  "bangalore":  "in",
    "chennai":      "in",  "hyderabad":  "in",
    "kolkata":      "in",  "pune":              "in",
}


def _url_host(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        h = (urlparse(url).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from services.news_api_provider import _DOMAINS_BY_COUNTRY

    def host_country(host: str) -> str | None:
        for cc, csv in _DOMAINS_BY_COUNTRY.items():
            for d in [s.strip() for s in csv.split(",") if s.strip()]:
                if host == d or host.endswith("." + d):
                    return cc
        return None

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    relabel_ops: list[tuple] = []   # (id, new_market)
    delete_ids: list[str] = []
    total = leaked = retagged = orphan = 0

    async for doc in db.news_articles.find({}, {
            "_id": 1, "news_id": 1, "url": 1, "market": 1, "source_id": 1}):
        total += 1
        market = (doc.get("market") or "").lower()
        expected_cc = MARKET_TO_COUNTRY.get(market)
        if not expected_cc:
            continue   # market not in our scheme — leave untouched
        host = _url_host(doc.get("url"))
        actual_cc = host_country(host) if host else None
        if not actual_cc:
            # Domain isn't in any of our whitelists → orphan candidate.
            # Conservative: only delete if it's an unambiguous non-US
            # market (US has the largest catch-all whitelist so unknown
            # US domains are mostly safe to leave).
            if expected_cc != "us":
                orphan += 1
                delete_ids.append(doc["_id"])
            continue
        if actual_cc == expected_cc:
            continue   # all good
        leaked += 1
        # Re-tag to a sensible default market in the correct country.
        default_market = {"in": "india", "us": "dfw",
                                          "gb": "london", "ae": "dubai"}.get(actual_cc)
        if default_market:
            retagged += 1
            relabel_ops.append((doc["_id"], default_market))
        else:
            delete_ids.append(doc["_id"])

    print(f"[geo-cleanup] scanned={total} leaked={leaked} "
                f"orphan={orphan} retag_pending={len(relabel_ops)} "
                f"delete_pending={len(delete_ids)} dry_run={args.dry_run}")

    if not args.dry_run:
        if relabel_ops:
            # group by target market for fewer round-trips
            from collections import defaultdict
            by_target = defaultdict(list)
            for _id, mk in relabel_ops:
                by_target[mk].append(_id)
            for mk, ids in by_target.items():
                r = await db.news_articles.update_many(
                    {"_id": {"$in": ids}},
                    {"$set": {"market": mk, "geo_cleanup_retagged": True}})
                print(f"  retagged → market={mk!r} modified={r.modified_count}")
        if delete_ids:
            r = await db.news_articles.delete_many({"_id": {"$in": delete_ids}})
            print(f"  deleted={r.deleted_count}")


if __name__ == "__main__":
    asyncio.run(main())
