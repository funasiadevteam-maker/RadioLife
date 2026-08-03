"""Phase 41 Session 5.A — synthetic analytics seed.

Idempotent — safe to re-run. Populates `listener_session_archive`,
`station_followers`, and `tv_poll_daily` with realistic looking
activity for the seeded community stations so the analytics
dashboard isn't empty during screenshots / demos.

Usage:
    cd /app/backend && python -m scripts.seed_phase41_s5_analytics
"""
from __future__ import annotations
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient


CITIES = [
    ("Dubai",        "UAE"),
    ("Abu Dhabi",    "UAE"),
    ("Sharjah",      "UAE"),
    ("Mumbai",       "IN"),
    ("Delhi",        "IN"),
    ("Bangalore",    "IN"),
    ("Riyadh",       "SA"),
    ("London",       "GB"),
    ("New York",     "US"),
    ("Toronto",      "CA"),
]

STATIONS = ["s3a-smoke-karak", "p41-audit-test"]
SEED_TAG = "phase41_s5_seed_v1"


def random_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:16]}"


async def seed():
    # Deterministic seed → re-runs produce the same shape.
    rand = random.Random(20260608)
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    )[os.environ.get("DB_NAME", "bigfm")]

    # ---- Wipe any prior rows from THIS seed only ----
    rsx = await db.listener_session_archive.delete_many({"seed_tag": SEED_TAG})
    rsy = await db.station_followers.delete_many(
        {"seed_tag": SEED_TAG, "station_id": {"$exists": True}})
    rsz = await db.tv_poll_daily.delete_many({"seed_tag": SEED_TAG})
    print(f"[seed] wiped prior: archive={rsx.deleted_count} "
          f"followers={rsy.deleted_count} tv_polls={rsz.deleted_count}")

    # ---- Lookup station_id by slug ----
    stations = {}
    for slug in STATIONS:
        s = await db.community_radio_stations.find_one({"slug": slug})
        if not s:
            print(f"[seed] WARNING: station '{slug}' not found, skipping")
            continue
        stations[slug] = s

    if not stations:
        print("[seed] no stations to seed")
        return

    # ---- Generate user_id pool ----
    pool_size = 40
    pool = [random_user_id() for _ in range(pool_size)]

    # ---- listener_session_archive ----
    now = datetime.now(timezone.utc)
    archive_docs = []
    for slug, s in stations.items():
        # Weight more recent days heavier (decay).
        for days_ago in range(30):
            day = now - timedelta(days=days_ago)
            # Random count of sessions on this day, weighted to be
            # higher for more recent days and higher for the verified
            # business.
            base = 6 if slug == "s3a-smoke-karak" else 4
            bias = max(1, 12 - days_ago // 3)
            count = rand.randint(base, base + bias)
            for _ in range(count):
                started = day.replace(
                    hour=rand.randint(8, 22),
                    minute=rand.randint(0, 59),
                    second=rand.randint(0, 59),
                    microsecond=0,
                )
                duration_min = rand.choices(
                    population=[2, 5, 8, 15, 22, 35, 45, 60],
                    weights=[15, 22, 18, 16, 12, 8, 6, 3],
                )[0]
                ended = started + timedelta(minutes=duration_min)
                city, country = rand.choice(CITIES)
                archive_docs.append({
                    "_id":          f"lsa_{uuid.uuid4().hex[:16]}",
                    "session_token": f"ls_{uuid.uuid4().hex[:18]}",
                    "station_id":    s["station_id"],
                    "station_slug":  slug,
                    "user_id":       rand.choice(pool),
                    "joined_at":     started,
                    "ended_at":      ended,
                    "duration_sec":  int(duration_min * 60),
                    "city":          city,
                    "country":       country,
                    "seed_tag":      SEED_TAG,
                })
    if archive_docs:
        await db.listener_session_archive.insert_many(archive_docs)
    print(f"[seed] inserted {len(archive_docs)} listener_session_archive rows")

    # ---- station_followers ----
    follower_docs = []
    for slug, s in stations.items():
        # ~25 followers per station, joined times spread across 60 days
        # so 7d/30d/90d windows all see deltas.
        target = 25 if slug == "s3a-smoke-karak" else 18
        for _ in range(target):
            days_ago = rand.randint(0, 60)
            followed_at = (now - timedelta(
                days=days_ago,
                hours=rand.randint(0, 23),
                minutes=rand.randint(0, 59),
            )).isoformat()
            follower_docs.append({
                "_id":         f"fol_{uuid.uuid4().hex[:16]}",
                "user_id":     rand.choice(pool),
                "station_id":  s["station_id"],
                "followed_at": followed_at,
                "seed_tag":    SEED_TAG,
            })
    if follower_docs:
        await db.station_followers.insert_many(follower_docs)
    print(f"[seed] inserted {len(follower_docs)} station_followers rows")

    # ---- tv_poll_daily counters ----
    tv_docs = []
    for slug, s in stations.items():
        # business gets ~150 polls/day on recent days, personal ~25
        base = 150 if slug == "s3a-smoke-karak" else 25
        for days_ago in range(14):
            date_str = (now - timedelta(days=days_ago)).date().isoformat()
            count = max(0, base + rand.randint(-30, 30) - days_ago * 2)
            tv_docs.append({
                "_id": f"tvp_{slug}_{date_str}",
                "station_slug": slug,
                "station_id":   s["station_id"],
                "date_str":     date_str,
                "count":        count,
                "seed_tag":     SEED_TAG,
            })
    if tv_docs:
        await db.tv_poll_daily.insert_many(tv_docs)
    print(f"[seed] inserted {len(tv_docs)} tv_poll_daily rows")

    # ---- Backfill follower_count on the station docs ----
    for slug, s in stations.items():
        cnt = await db.station_followers.count_documents(
            {"station_id": s["station_id"]})
        await db.community_radio_stations.update_one(
            {"station_id": s["station_id"]},
            {"$set": {"follower_count": cnt}})
        print(f"[seed] {slug}: follower_count -> {cnt}")

    print("[seed] DONE")


if __name__ == "__main__":
    asyncio.run(seed())
