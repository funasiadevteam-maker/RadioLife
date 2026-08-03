"""Phase 42-B-redux fixture — demo community radio station.

Creates ONE published community radio station owned by `test@bigfm.dubai`
so:
    1.    The Community rail on `/radio/discover` always has a stable row to
        render (verifies the rail wiring + cards).
    2.    The pre-roll tier-gate test branch (Test 3 — community station ids
        never trigger pre-roll) has a real `cmn_*` id to point at.

Idempotent: re-running upserts the same row by `slug`.  Two tracks from
the channel music catalogue are linked so the station has playable
content (community detail page shows "2 tracks" instead of empty state).

Usage:
    python3 backend/scripts/seed_demo_community_station.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

OWNER_EMAIL = "test@bigfm.dubai"
STATION_SLUG = "demo-community-station"
STATION_NAME = "Demo Community Station (42-B fixture)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    owner = await db.users.find_one({"email": OWNER_EMAIL})
    if not owner:
        print(f"ERROR: owner {OWNER_EMAIL} not found — run the test user "
                  f"seed first.", file=sys.stderr)
        sys.exit(2)
    owner_user_id = owner["user_id"]

    existing = await db.community_radio_stations.find_one({"slug": STATION_SLUG})
    now = _now()
    now_iso = now.isoformat()

    # Pick up to 2 random tracks from the music catalogue so the station
    # detail page renders real content (not strictly required but matches
    # the brief's "at least 2 tracks").
    track_ids: list[str] = []
    async for t in db.tracks.find({}, {"_id": 0, "track_id": 1}).limit(2):
        tid = t.get("track_id")
        if tid:
            track_ids.append(tid)

    doc = {
        "name": STATION_NAME,
        "slug": STATION_SLUG,
        "tagline": "A test fixture for the unified Radio discover surface.",
        "bio": ("Seeded by `scripts/seed_demo_community_station.py` to "
                      "exercise the community tier on /radio/discover and the "
                      "pre-roll tier-gate guard."),
        "owner_user_id": owner_user_id,
        "page_type": "personal_radio",
        "status": "published",
        "privacy": "public",
        "is_public": True,
        "is_business": False,
        "audience": "general",
        "allowed_genres": ["Bollywood Music", "Pop"],
        "allowed_moods": ["uplifting", "party"],
        "allowed_energy_levels": ["high", "medium"],
        "language_mix": [{"language": "english", "weight": 1.0}],
        "music_clock": {"rotation": ["current_hit", "retro", "mood_match"],
                                          "cycle_length": 3},
        "hosts": [{"voice_key": "kishore_retro", "role": "primary"}],
        "cover_image_url": None,
        "cover_color": "#00d9ff",
        "artwork_status": "pending",
        "follower_count": 0,
        "listener_count": 0,
        "track_ids": track_ids,
        "track_count": len(track_ids),
        "updated_at": now_iso,
    }

    if existing:
        await db.community_radio_stations.update_one(
            {"slug": STATION_SLUG},
            {"$set": doc})
        station_id = existing.get("station_id")
        share_id = existing.get("share_id")
        print(f"station_id={station_id}")
        print(f"share_id={share_id}")
        print(f"slug={STATION_SLUG}")
        print(f"owner_user_id={owner_user_id}")
        print(f"tracks_linked={len(track_ids)}")
        print("status=refreshed")
        client.close()
        return

    station_id = _new_id("stn")
    share_id = uuid.uuid4().hex[:10]
    doc.update({
        "_id": station_id,
        "station_id": station_id,
        "share_id": share_id,
        "created_at": now_iso,
        "published_at": now_iso,
    })
    await db.community_radio_stations.insert_one(doc)
    print(f"station_id={station_id}")
    print(f"share_id={share_id}")
    print(f"slug={STATION_SLUG}")
    print(f"owner_user_id={owner_user_id}")
    print(f"tracks_linked={len(track_ids)}")
    print("status=created")
    client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
