"""Rebrand leftover 'BigFM' → 'RadioLife' in USER-VISIBLE display text.

Safe-by-design: only rewrites an ALLOWLIST of display fields. Never
touches identifiers / slugs / emails / URLs / redemption codes / file
paths (those are functional keys — renaming them breaks logins,
station lookups, redemptions, imaging, SSP bids, etc.).

Usage:  python rebrand_bigfm.py            # dry run (counts only)
        python rebrand_bigfm.py --apply    # perform the update
"""
import asyncio
import os
import re
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

# Display fields users actually read. Everything else is left alone.
DISPLAY_FIELDS = {
    "name", "title", "description", "note", "sponsor_name", "station_name",
    "terms_text", "transcript", "rj_script", "initial_script", "phrase",
    "headline", "headline_text", "display_name", "label", "subtitle",
    "body", "message", "tagline", "caption", "summary", "bio",
}

RX = re.compile(r"big\s*fm", re.IGNORECASE)

# Third-party / directory collections — their "BigFM" values are REAL external
# station names (e.g. the German BigFM network, "BigFM 106.2 UAE"), NOT our
# brand. Never rewrite these.
SKIP_COLLECTIONS = {"imported_radio_stations"}


def rebrand(value: str) -> str:
    return RX.sub("RadioLife", value)


async def main(apply: bool) -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    names = await db.list_collection_names()
    total_docs = 0
    total_fields = 0
    per_coll = {}

    for coll in names:
        if coll in SKIP_COLLECTIONS:
            continue
        changed_docs = 0
        changed_fields = 0
        async for doc in db[coll].find({}):
            updates = {}
            for k, v in doc.items():
                if k in DISPLAY_FIELDS and isinstance(v, str) and RX.search(v):
                    new_v = rebrand(v)
                    if new_v != v:
                        updates[k] = new_v
            if updates:
                changed_docs += 1
                changed_fields += len(updates)
                if apply:
                    await db[coll].update_one({"_id": doc["_id"]}, {"$set": updates})
        if changed_docs:
            per_coll[coll] = (changed_docs, changed_fields)
            total_docs += changed_docs
            total_fields += changed_fields

    mode = "APPLIED" if apply else "DRY RUN"
    print(f"=== {mode} ===")
    for coll, (d, f) in sorted(per_coll.items()):
        print(f"{coll}: {d} docs, {f} fields")
    print(f"TOTAL: {total_docs} docs, {total_fields} fields")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
