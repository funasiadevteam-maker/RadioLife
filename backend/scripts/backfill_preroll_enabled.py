"""Phase PREROLL.EXT — Idempotent migration: set `preroll_enabled=True`
on every station across every station collection.

Existing stations without the field default to True at read time
(via `_should_serve_preroll` in `preroll_ad_service.py`) — this
migration just materialises the field so admin toggles work uniformly
and so we can rely on a single query shape.

Run on boot from `server.py::_phase_preroll_ext_bootstrap`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("bigfm.preroll_ext.migrate")


STATION_COLLECTIONS = (
    "imported_radio_stations",  # imp_* — includes flagships (is_flagship=True)
    "community_radio_stations",  # Mongo OID ids
    "channels",                                    # AI channels — slug ids
    # Future station types can be added here without changing any code.
)


async def backfill_preroll_enabled(db) -> Dict[str, Any]:
    stats: Dict[str, int] = {}
    for coll in STATION_COLLECTIONS:
        try:
            r = await db[coll].update_many(
                {"preroll_enabled": {"$exists": False}},
                {"$set": {"preroll_enabled": True}})
            stats[coll] = r.modified_count
        except Exception as e:  # noqa: BLE001
            logger.warning("[preroll_ext] backfill %s failed: %s", coll, e)
            stats[coll] = -1
    logger.info("[preroll_ext] backfill: %s", stats)
    return stats


if __name__ == "__main__":
    import asyncio, os
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        print(await backfill_preroll_enabled(db))
    asyncio.run(_run())
