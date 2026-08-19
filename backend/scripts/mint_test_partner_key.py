"""Mint a throwaway LIVE partner API key for E2E testing of the Ads API.
Prints the raw key ONCE. Safe to re-run (always issues a fresh key).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services import partner_api as pa  # noqa: E402

OWNER = "partner-managed:e2e-test-harness"
NAME = "E2E Test Harness"
EMAIL = "e2e@emergent.sh"


async def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base, ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await pa.ensure_partner_api(db)
    p = await pa.get_or_create_partner(db, owner_user_id=OWNER, name=NAME, contact_email=EMAIL)
    pid = p["partner_id"]
    live = await pa.issue_api_key(db, partner_id=pid, environment="live", label="e2e live")
    print(f"partner_id: {pid}")
    print(f"LIVE_API_KEY: {live['api_key']}")
    print(f"scopes: {live['scopes']}")


if __name__ == "__main__":
    asyncio.run(main())
