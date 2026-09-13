"""One-shot script: mint a limited-scope sandbox API key for the Phase D partner.

Usage: python -m backend.tests._mint_limited_key   (from /app)
Prints the newly-minted API key on stdout as JSON.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services import partner_api as pa  # noqa: E402


async def main() -> None:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    res = await pa.issue_api_key(
        db,
        partner_id="prt_Ngu4e33qm4KULA",
        environment="sandbox",
        scopes=["catalog:read"],
        label="TEST_iter123_limited_scope",
    )
    print(json.dumps(res))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
