"""Curated Predict & Win — unapprove the AI-imported junk markets and seed a
hand-picked sports / Bollywood / local set with distinct descriptions.

The consumer /api/predict-win/active endpoint already gates on
approval_status == "approved" + status in (scheduled, live), so unapproving
the imports removes them and the admin approval flow stays intact.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

CURATED = [
    ("Will India win the 2026 ICC T20 World Cup?",
     "India head into the tournament as favourites. Call it before the group stage locks.",
     ["Yes", "No"], "sports_top", "Cricket", 50),
    ("Next El Clásico — who takes it: Real Madrid or Barcelona?",
     "Two giants, one night. Pick the winner of the next Real Madrid vs Barcelona league clash.",
     ["Real Madrid", "Barcelona", "Draw"], "sports_top", "Football", 40),
    ("Will Max Verstappen finish on the podium at the next Grand Prix?",
     "Top-three finish or not — make your call before lights out.",
     ["Yes", "No"], "sports_top", "Formula 1", 30),
    ("Will the Dallas Mavericks make the NBA playoffs this season?",
     "A local favourite for our Dallas listeners — playoffs or bust?",
     ["Yes", "No"], "sports_top", "Basketball", 35),
    ("Will the next big Bollywood release cross ₹100 crore in its opening weekend?",
     "Box-office fever — will the next tent-pole blockbuster smash the ₹100 cr weekend mark?",
     ["Yes", "No"], "national_games", "Bollywood", 30),
    ("Will an Arijit Singh track top the music charts next week?",
     "The playback king vs the charts — predict whether Arijit lands the #1 spot.",
     ["Yes", "No"], "national_games", "Music", 25),
    ("Will a debut performer take home a major trophy at the next Filmfare Awards?",
     "Awards-night upset watch — does a first-timer walk away with a headline award?",
     ["Yes", "No"], "national_games", "Bollywood", 25),
    ("Will the Dubai Fountain add a new soundtrack this season?",
     "A hometown pick for our UAE listeners — new show music before the season ends?",
     ["Yes", "No"], "national_games", "Local", 20),
]


async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]

    # 1) Unapprove the AI-imported junk (they now require admin re-approval).
    res = await db.predict_win_campaigns.update_many(
        {"import_source": {"$ne": None}, "approval_status": "approved"},
        {"$set": {"approval_status": "pending",
                  "approval_reason": "Auto-unapproved: AI import pending editorial review"}})
    print("unapproved imports:", res.modified_count)

    # Clone key structure from any existing doc so no required field is missing.
    template = await db.predict_win_campaigns.find_one({}) or {}
    template_keys = [k for k in template.keys() if k != "_id"]
    now = datetime.now(timezone.utc)

    # Remove previously-seeded curated rows so this script is idempotent.
    await db.predict_win_campaigns.delete_many({"import_source": "curated_editorial"})

    inserted = 0
    for i, (title, desc, opts, slug, label, pts) in enumerate(CURATED):
        cid = f"pwc_curated_{i+1:02d}"
        doc = {k: template.get(k) for k in template_keys}
        doc.update({
            "campaign_id": cid,
            "title": title,
            "description": desc,
            "event_type": "custom",
            "event_label": label,
            "category": slug,
            "category_slug": slug,
            "points_reward": pts,
            "import_source": "curated_editorial",
            "import_source_label": "Editorial pick",
            "external_provider_snapshot": None,
            "external_market_id": None,
            "external_market_url": None,
            "data_provider_id": None,
            "creator_type": "curated",
            "question": {
                "prompt": title,
                "answer_options": [
                    {"option_id": f"opt_{j+1}", "label": lab, "external_outcome_id": f"opt_{j+1}"}
                    for j, lab in enumerate(opts)
                ],
            },
            "start_time": now,
            "lock_time": now + timedelta(days=14),
            "resolve_by": now + timedelta(days=21),
            "approval_status": "approved",
            "approval_reason": "Curated editorial pick",
            "approved_by": "curation",
            "approved_at": now,
            "rejected_by": None,
            "rejected_at": None,
            "status": "live",
            "city": None,
            "region": None,
            "cover_image_url": None,
            "created_by": "curation",
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "merchant_eligible": False,
        })
        await db.predict_win_campaigns.update_one(
            {"campaign_id": cid}, {"$set": doc}, upsert=True)
        inserted += 1
    print("curated inserted:", inserted)

    live = await db.predict_win_campaigns.count_documents(
        {"approval_status": "approved", "status": {"$in": ["scheduled", "live"]}})
    print("approved+live now:", live)


if __name__ == "__main__":
    asyncio.run(main())
