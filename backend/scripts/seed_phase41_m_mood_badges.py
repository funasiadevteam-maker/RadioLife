"""Phase 41M seed — ~30 mood votes across 5 moods + badge-trigger events.

Idempotent via `seed_tag: phase41_m_seed`. Run:
    cd /app/backend && python scripts/seed_phase41_m_mood_badges.py
"""
import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient

SEED_TAG  = "phase41_m_seed"
STATIONS  = ["p41-audit-test", "s3a-smoke-karak"]
MOODS     = ["chill", "hype", "sad", "party", "focus"]


def _now(): return datetime.now(timezone.utc)


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    # ── Resolve stations
    s_docs = {}
    for slug in STATIONS:
        d = await db.community_radio_stations.find_one({"slug": slug})
        if not d:
            print(f"  ! station {slug} not found; skipping")
            continue
        s_docs[slug] = d
    if not s_docs:
        print("No stations to seed; abort.")
        return

    # ── Picker pool: test@bigfm.dubai + demo@bigfm.dubai + 10 synthetic
    test_user = await db.users.find_one({"email": "test@bigfm.dubai"})
    demo_user = await db.users.find_one({"email": "demo@bigfm.dubai"})
    voters = []
    if test_user: voters.append(test_user["user_id"])
    if demo_user: voters.append(demo_user["user_id"])
    for i in range(15):
        voters.append(f"u_p41m_seed_{i:02d}")

    # ── Pick 3 tracks for the per_track distribution
    track_ids = []
    async for t in db.tracks.find({}, {"_id": 1}).limit(3):
        track_ids.append(t["_id"])
    if len(track_ids) < 1:
        print("No tracks in catalog; per-track distribution will be empty.")

    # ── Wipe prior seed rows (idempotency)
    await db.mood_votes.delete_many({"seed_tag": SEED_TAG})
    await db.user_station_badges.delete_many({"seed_tag": SEED_TAG})

    random.seed(41)
    mood_rows = []
    base = _now() - timedelta(days=6)
    for slug, station in s_docs.items():
        for i in range(15):       # ~15 votes per station → 30 total
            uid = random.choice(voters)
            track_id = random.choice(track_ids + [None]) if track_ids else None
            mood = random.choice(MOODS)
            mood_rows.append({
                "_id":        f"mv_seed_{uuid.uuid4().hex[:12]}",
                "station_id": station["_id"],
                "station_slug": slug,
                "track_id":   track_id,
                "user_id":    uid,
                "mood":       mood,
                "voted_at":   base + timedelta(hours=random.randint(0, 144),
                                                 minutes=random.randint(0, 59)),
                "first_voted_at": base + timedelta(hours=random.randint(0, 144)),
                "seed_tag":   SEED_TAG,
            })
    # Insert dedup-safe via upsert on unique compound key
    for d in mood_rows:
        try:
            await db.mood_votes.update_one(
                {"station_id": d["station_id"],
                 "track_id":   d["track_id"],
                 "user_id":    d["user_id"]},
                {"$set":       {k: v for k, v in d.items()
                                if k not in ("_id", "first_voted_at")},
                 "$setOnInsert": {"_id": d["_id"],
                                  "first_voted_at": d["first_voted_at"]}},
                upsert=True)
        except Exception as e:
            print(f"  ! mood vote insert failed: {e}")
    inserted_mood = await db.mood_votes.count_documents({"seed_tag": SEED_TAG})
    print(f"mood_votes ({SEED_TAG}): {inserted_mood} rows after upsert")

    # ── Badge-trigger signals for test@bigfm.dubai on p41-audit-test
    if test_user:
        uid = test_user["user_id"]
        station = s_docs.get("p41-audit-test")
        if station:
            sid = station["_id"]
            # 1. listen_minutes ≥ 50 → loyal_listener
            # Insert 60 minutes total via 3 archive rows.
            now = _now()
            archive_rows = [
                {"_id": f"lsa_seed_{uuid.uuid4().hex[:12]}",
                 "session_token": f"st_seed_{i}",
                 "station_id": sid, "station_slug": "p41-audit-test",
                 "user_id":    uid,
                 "joined_at":  now - timedelta(days=i, hours=1),
                 "ended_at":   now - timedelta(days=i, hours=1) + timedelta(minutes=20),
                 "duration_sec": 20 * 60,
                 "city": "Dubai", "country": "AE",
                 "seed_tag": SEED_TAG}
                for i in range(3)
            ]
            await db.listener_session_archive.delete_many(
                {"user_id": uid, "station_id": sid, "seed_tag": SEED_TAG})
            await db.listener_session_archive.insert_many(archive_rows)
            print(f"  listener_session_archive: +{len(archive_rows)} rows (60min)")

            # 2. 12 reactions → top_reactor
            # Find/create 12 reactable targets (posts on this station).
            post_ids = [p["post_id"] async for p in
                        db.station_posts.find({"station_slug": "p41-audit-test"},
                                                {"post_id": 1, "_id": 0})
                        .limit(12)]
            await db.station_reactions.delete_many(
                {"user_id": uid, "seed_tag": SEED_TAG})
            for i, pid in enumerate(post_ids[:12]):
                try:
                    await db.station_reactions.update_one(
                        {"target_type": "post", "target_id": pid,
                         "user_id":     uid},
                        {"$set": {"reaction_type": "fire",
                                  "created_at":    _now().isoformat(),
                                  "seed_tag":      SEED_TAG}},
                        upsert=True)
                except Exception as e:
                    print(f"  ! reaction insert failed: {e}")
            print(f"  station_reactions: 12 fire reactions on posts")

            # 3. 6 comments → comment_champion
            await db.station_comments.delete_many(
                {"author_id": uid, "seed_tag": SEED_TAG})
            for i, pid in enumerate(post_ids[:6]):
                cid = f"scmt_seed_{uuid.uuid4().hex[:12]}"
                await db.station_comments.insert_one({
                    "_id": cid, "comment_id": cid,
                    "post_id":      pid,
                    "station_slug": "p41-audit-test",
                    "author_id":    uid,
                    "author_name":  "RadioLife Test",
                    "body":         f"Phase 41M seed comment #{i+1}",
                    "created_at":   _now().isoformat(),
                    "deleted_at":   None,
                    "reaction_counts": {"fire": 0, "wow": 0, "like": 0,
                                          "laugh": 0, "love": 0},
                    "seed_tag":     SEED_TAG,
                })
            print(f"  station_comments: 6 seed comments")

            # 4. ensure test user is a follower (rank check)
            existing = await db.station_followers.find_one(
                {"user_id": uid, "station_id": sid})
            if not existing:
                await db.station_followers.insert_one({
                    "_id": f"fol_seed_{uuid.uuid4().hex[:12]}",
                    "user_id":    uid,
                    "station_id": sid,
                    "station_slug": "p41-audit-test",
                    "followed_at": (_now() - timedelta(days=20)).isoformat(),
                    "seed_tag":   SEED_TAG,
                })
                print(f"  station_followers: added test user as follower")

            # 5. promote test_user premium for VIP
            await db.users.update_one(
                {"user_id": uid},
                {"$set": {"premium_active": True,
                          "premium_seed_tag": SEED_TAG}})

            # 6. Run grant engine for test user
            from services.station_badge_engine import evaluate_and_grant_badges
            newly = await evaluate_and_grant_badges(
                db, user_id=uid, station_id=sid,
                station_slug="p41-audit-test")
            for n in newly:
                # tag the inserted badge as seed-origin (best-effort)
                await db.user_station_badges.update_one(
                    {"user_id": uid, "station_id": sid,
                     "badge_type": n["badge_type"]},
                    {"$set": {"seed_tag": SEED_TAG}})
            print(f"  user_station_badges granted for test user: {newly}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
