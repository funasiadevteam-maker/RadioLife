"""Sub-Phase E5 — Idempotent seed for the Predexon data-provider row.

Adds (or refreshes) `prediction_data_providers.predexon`.  Safe to run
many times.

Usage:
    PYTHONPATH=/app/backend python3 /app/backend/scripts/seed_predexon_provider.py
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_predexon_provider(db) -> dict:
    existing = await db.prediction_data_providers.find_one(
        {"provider_name": "predexon"})
    if existing:
        await db.prediction_data_providers.update_one(
            {"provider_name": "predexon"},
            {"$set": {"active": True,
                              "auth_type": "x-api-key",
                              "base_url": (os.environ.get("PREDEXON_BASE_URL")
                                                          or "https://api.predexon.com"),
                              "api_key_env_var": "PREDEXON_API_KEY",
                              "updated_at": _now()}})
        return {"action": "refreshed",
                      "provider_id": existing.get("provider_id") or existing["_id"]}
    pid = f"pdp_predexon"
    await db.prediction_data_providers.insert_one({
        "_id": pid, "provider_id": pid,
        "provider_name": "predexon",
        "active": True,
        "auth_type": "x-api-key",
        "base_url": (os.environ.get("PREDEXON_BASE_URL")
                              or "https://api.predexon.com"),
        "api_key_env_var": "PREDEXON_API_KEY",
        "created_at": _now(),
        "updated_at": _now(),
    })
    return {"action": "created", "provider_id": pid}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    res = await seed_predexon_provider(db)
    print(res)
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
