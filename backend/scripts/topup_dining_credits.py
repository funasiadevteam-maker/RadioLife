"""One-off QA helper: issue a fresh weekly grant to the given dining subscribers
so the Use-a-Meal happy path has AVAILABLE credits. Idempotent-ish (adds one grant
per run per user)."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services import dining_club as dc  # noqa: E402

EMAILS = ["test@bigfm.dubai", "demo@bigfm.dubai"]


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    program = await dc.get_program(db)
    for email in EMAILS:
        u = await db.users.find_one({"email": email}, {"user_id": 1})
        if not u:
            print(email, "-> no user")
            continue
        sub = await dc.get_subscription(db, u["user_id"])
        if not sub or sub.get("status") != "active":
            print(email, "-> no active subscription")
            continue
        g = await dc._issue_grant(db, sub, program)
        summ = await dc.credit_summary(db, u["user_id"], True)
        print(email, "-> issued", g["quantity"], "credits; available now:", summ["available"])
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
