"""Phase CLAIM.1 — Initialize the `station_edit_requests` collection.

Idempotent.  Called at server boot (see server.py bootstrap) and can be
re-run standalone.

Note: `radio_station_claims` + `station_owner_profiles` already exist
from Phase 42-C; their indexes are created via
`services.station_claim_service.ensure_indexes` which the existing boot
path already invokes.  We only own the NEW collection here.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient

log = logging.getLogger("bigfm.claim1.init")


async def init_collections(db) -> dict:
    report = {"created_indexes": [], "errors": []}

    for keys, opts, label in [
        ([("id", 1)],                                                                                   {"unique": True},   "ser_id_unique"),
        ([("station_id", 1), ("edit_status", 1)],                        {},  "ser_station_status"),
        ([("owner_user_id", 1), ("edit_status", 1)],                {},  "ser_owner_status"),
        ([("edit_status", 1), ("updated_at", -1)],                    {},  "ser_queue"),
    ]:
        try:
            await db.station_edit_requests.create_index(keys, name=label, **opts)
            report["created_indexes"].append(
                f"station_edit_requests.{label}")
        except Exception as e:
            report["errors"].append(f"ser:{label}:{e}")

    # radio_station_claims — reindex on `proof_documents` for admin filter.
    try:
        await db.radio_station_claims.create_index(
            [("has_proof_documents", 1), ("claim_status", 1)],
            name="rsc_has_proof_status")
        report["created_indexes"].append(
            "radio_station_claims.rsc_has_proof_status")
    except Exception as e:
        report["errors"].append(f"rsc:has_proof:{e}")

    return report


async def _cli():
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    logging.basicConfig(level=logging.INFO)
    r = await init_collections(db)
    print(f"Created {len(r['created_indexes'])} indexes; errors={len(r['errors'])}")
    for i in r["created_indexes"]:
        print(f"  + {i}")
    for e in r["errors"]:
        print(f"  ! {e}")


if __name__ == "__main__":
    asyncio.run(_cli())
