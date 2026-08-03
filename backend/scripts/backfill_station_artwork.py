"""Phase C — Station artwork backfill.

Generates a cover image for every community / business radio station
that currently has ``cover_image_url IS NULL``.  Throttled to one
generation per 12 seconds so we stay well inside OpenAI's per-org
rate limits (current org cap is 50 RPM for gpt-image-1; 12s spacing
gives us 5 RPM, plenty of headroom for concurrent app traffic).

Usage:
    cd /app/backend && set -a && source .env && set +a && \\
        python3 scripts/backfill_station_artwork.py

  -OR-
    python3 scripts/backfill_station_artwork.py --limit 4 --dry-run

Idempotent — stations that already have a non-null ``cover_image_url``
or ``artwork_url`` are skipped.

Cost rough-estimate:
    gpt-image-1 @ 1024x1024 "medium" ≈ $0.02 per image.
    Backfilling 4 stations ≈ $0.08 total.
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Ensure /app/backend is on the import path when called as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Phase 36c — load .env BEFORE importing anything else that touches env.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from motor.motor_asyncio import AsyncIOMotorClient                        # noqa: E402
from services import image_gen as image_gen_svc                              # noqa: E402
from services.station_artwork_prompt import build_prompt                # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.backfill_station_artwork")


async def backfill(*, limit: int = 0, throttle: float = 12.0,
                          dry_run: bool = False, only_slug: str | None = None) -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "bigfm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    q: dict = {
        # Skip stations that already have artwork.
        "$or": [
            {"cover_image_url": {"$in": [None, ""]}},
            {"cover_image_url": {"$exists": False}},
        ],
    }
    if only_slug:
        q = {"slug": only_slug}

    out = {"processed": 0, "generated": 0, "cached": 0, "failed": 0,
              "skipped": 0, "cost_estimate_usd": 0.0,
              "failed_slugs": [], "generated_slugs": []}

    cur = db.community_radio_stations.find(q).sort("created_at", 1)
    stations = await cur.to_list(length=limit or None)
    log.info("backfill: %d stations queued (dry_run=%s)", len(stations), dry_run)

    for i, st in enumerate(stations):
        slug = st["slug"]
        if st.get("cover_image_url"):
            out["skipped"] += 1
            log.info("[%d/%d] skip %s (already has cover)", i + 1, len(stations), slug)
            continue
        prompt = build_prompt(st)
        log.info("[%d/%d] %s prompt[:80]=%s", i + 1, len(stations), slug, prompt[:80])
        if dry_run:
            out["processed"] += 1
            continue
        result = await image_gen_svc.generate(
            db, prompt=prompt, user_id="", station_slug=slug,
            bypass_rate_limit=True)
        out["processed"] += 1
        if not result.get("ok"):
            out["failed"] += 1
            out["failed_slugs"].append({"slug": slug,
                                                            "error": result.get("error")})
            log.warning("  → FAILED %s: %s", slug, result.get("error"))
        else:
            if result.get("cached"):
                out["cached"] += 1
            else:
                out["generated"] += 1
                out["cost_estimate_usd"] += 0.02   # medium quality $/image
            await db.community_radio_stations.update_one(
                {"slug": slug},
                {"$set": {
                    "artwork_url":            result["url"],
                    "cover_image_url":       result["url"],
                    "artwork_source":        "ai_generated",
                    "artwork_generated_at": datetime.now(timezone.utc),
                    "artwork_prompt":        prompt,
                    "artwork_key":             result.get("key"),
                    "artwork_status":        "complete",
                    "artwork_error":          None,
                }})
            out["generated_slugs"].append(slug)
            log.info("  → OK %s url=%s (source=%s)", slug, result["url"],
                          result.get("source"))
        # Throttle between provider calls (skip after last item).
        if i < len(stations) - 1 and not result.get("cached"):
            await asyncio.sleep(throttle)

    client.close()
    log.info("backfill done: %s", out)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0,
                          help="0 = all stations needing artwork")
    p.add_argument("--throttle", type=float, default=12.0,
                          help="seconds between provider calls")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--slug", default=None, help="only backfill this slug")
    args = p.parse_args()
    out = asyncio.run(backfill(limit=args.limit, throttle=args.throttle,
                                              dry_run=args.dry_run, only_slug=args.slug))
    print("---SUMMARY---")
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
