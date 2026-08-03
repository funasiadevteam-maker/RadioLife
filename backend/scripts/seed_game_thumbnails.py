"""Phase K.7c — Backfill per-instance thumbnails for existing game
campaigns.

Generates a unique AI thumbnail for every campaign whose
`thumbnail_url` is empty OR currently set to one of the K.7 generic
per-type fallbacks.

Behaviour:
    • Dedupes by `title` — campaigns with identical titles share a
        generated thumbnail (saves spend on test/QA dups like
        "Bad weights" × 90).
    • Idempotent — skips campaigns that already have a per-instance
        thumbnail under `/api/static/game_thumbnails/...`.
    • Hard caps total spend at 30 unique titles per run (override with
        `--limit N`).
    • `--force` regenerates even existing per-instance thumbnails.
    • `--dry-run` previews what would be generated.

Usage:
    python3 backend/scripts/seed_game_thumbnails.py
    python3 backend/scripts/seed_game_thumbnails.py --limit 50
    python3 backend/scripts/seed_game_thumbnails.py --force --limit 5
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
log = logging.getLogger("bigfm.seed_game_thumbnails")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30,
                              help="Max distinct titles to generate per run.")
    ap.add_argument("--force", action="store_true",
                              help="Regenerate even already-per-instance ones.")
    ap.add_argument("--dry-run", action="store_true",
                              help="Print what would be generated, don't call OpenAI.")
    args = ap.parse_args()

    from services.game_thumbnails import (
        generate_thumbnail_sync, _fallback_for, _slug,
    )

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # Find candidates: thumbnail_url empty OR pointing at a generic K.7 image.
    q: dict = {"$or": [
        {"thumbnail_url": {"$in": [None, ""]}},
        {"thumbnail_url": {"$exists": False}},
        {"thumbnail_url": {"$regex": "^/api/static/landing_images/game_"}},
    ]}
    if args.force:
        q = {}

    # Group by title — generate ONE thumbnail per distinct title and
    # propagate to all sibling campaigns sharing that title.
    by_title: dict[str, list[str]] = {}
    async for c in db.game_campaigns.find(q,
                  {"_id": 1, "title": 1, "thumbnail_url": 1,
                    "template_id": 1, "business_id": 1, "sponsor_name": 1}):
        title = (c.get("title") or "").strip() or "Untitled"
        by_title.setdefault(title, []).append(c["_id"])

    distinct_titles = sorted(by_title.keys(),
                                                    key=lambda t: -len(by_title[t]))
    titles_to_do = distinct_titles[: args.limit]
    print(f"[game_thumb] {len(distinct_titles)} distinct titles need work; "
                f"will process {len(titles_to_do)} (limit={args.limit}); "
                f"force={args.force} dry_run={args.dry_run}")

    generated = propagated = failed = 0
    for title in titles_to_do:
        ids = by_title[title]
        anchor = ids[0]
        if args.dry_run:
            print(f"  - title={title!r}  ({len(ids)} sibling(s)) "
                          f"anchor={anchor}")
            continue
        res = await generate_thumbnail_sync(db, anchor, force=args.force)
        if not res.get("ok"):
            failed += 1
            continue
        url = res.get("url")
        if not url:
            failed += 1
            continue
        generated += 1
        # Propagate to siblings (same title).
        if len(ids) > 1:
            r = await db.game_campaigns.update_many(
                {"_id": {"$in": ids[1:]}},
                {"$set": {"thumbnail_url": url,
                              "thumbnail_status": res.get("fallback")
                                  and "fallback_shared" or "generated_shared"}})
            propagated += r.modified_count

    print(f"[game_thumb] generated={generated} propagated_to_siblings="
                f"{propagated} failed={failed} "
                f"distinct_titles_remaining={max(0, len(distinct_titles) - len(titles_to_do))}")


if __name__ == "__main__":
    asyncio.run(main())
