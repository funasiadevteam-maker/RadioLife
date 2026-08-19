"""Idempotent seeding of the SmartReach (Emergent) partner + API credentials.

Run in ANY environment (preview or production) to mint SmartReach's access:

    cd /app/backend && python scripts/seed_smartreach_partner.py

Creates the partner (if absent) and issues a LIVE key, a SANDBOX key, and an
OAuth2 client with all scopes. Secrets are printed ONCE — capture them.
Safe to re-run: it reuses the existing partner and skips key issuance if keys
already exist (rotate via the dashboard instead).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv               # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient   # noqa: E402

from services import partner_api as pa       # noqa: E402

OWNER = "partner-managed:smartreach-emergent"
NAME = "SmartReach (Emergent)"
EMAIL = "smartreach@emergent.sh"


async def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(base, ".env"))
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await pa.ensure_partner_api(db)
    p = await pa.get_or_create_partner(db, owner_user_id=OWNER, name=NAME, contact_email=EMAIL)
    pid = p["partner_id"]
    creds = await pa.list_credentials(db, partner_id=pid)

    out = {"partner_id": pid}
    if not creds["api_keys"]:
        live = await pa.issue_api_key(db, partner_id=pid, environment="live", label="SmartReach live")
        test = await pa.issue_api_key(db, partner_id=pid, environment="sandbox", label="SmartReach sandbox")
        out["live_api_key"] = live["api_key"]
        out["sandbox_api_key"] = test["api_key"]
    else:
        out["note_keys"] = "API keys already exist — not re-issued (rotate via dashboard)."
    if not creds["oauth_clients"]:
        oc = await pa.issue_oauth_client(db, partner_id=pid, environment="live", label="SmartReach live")
        out["oauth_client_id"] = oc["client_id"]
        out["oauth_client_secret"] = oc["client_secret"]
    else:
        out["note_oauth"] = "OAuth client already exists — not re-issued."

    print("=== SmartReach (Emergent) credentials — SAVE NOW, secrets shown once ===")
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
