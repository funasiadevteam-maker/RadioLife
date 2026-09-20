"""Phase D — One-off seed for an explicit catalog fixture.

Purpose: ensure the catalog has at least one `explicit_flag: true`
active track so the QA tester can exercise Test 2 (explicit gating
on `audience='general'` stations).

Run once against the preview DB:
    cd /app/backend && python3 -m scripts.seed_phase_d_explicit_fixture

Idempotent: re-running is a no-op (uses upsert on a deterministic _id).
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

# Standalone-run support — make backend modules importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FIXTURE_ID = "ugc_qa_phase_d_explicit"
FIXTURE_HASH = ("phase_d_qa_explicit_fixture_sha256_"
                                "deadbeefcafebabe1234567890abcdef")


async def main() -> None:
    client = motor.motor_asyncio.AsyncIOMotorClient(
        os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    doc = {
        "_id":                      FIXTURE_ID,
        "title":                    "Phase D Explicit Test (Do Not Play)",
        "artist":                  "FUUSIC QA",
        "album":                  "Phase D Test Fixtures",
        "duration_sec":      3.03,
        "file_path":              "/app/backend/storage/tracks/phase_d_explicit_fixture.mp3",
        "storage_provider": "disk",
        "status":                  "active",
        "explicit_flag":      True,
        "uploaded_at":        "2026-06-17T00:00:00+00:00",
        "uploaded_by_user": "qa_fixture",
        "source":                  "qa_seed",
        "file_hash":              FIXTURE_HASH,
        "genre":                    "test",
        "mood":                    "energetic",
        "energy_level":      "medium",
        "language":              "english",
        "language_confidence": 1.0,
        "year":                      2026,
        "vibe_tags":              ["qa", "test_fixture", "phase_d"],
        "title_normalized": "phase d explicit test do not play",
        "artist_normalized": "bigfm qa",
    }

    await db.tracks.update_one(
        {"_id": FIXTURE_ID},
        {"$set": doc},
        upsert=True,
    )

    count = await db.tracks.count_documents(
        {"status": "active", "explicit_flag": True})
    print(f"✓ seeded fixture _id={FIXTURE_ID}")
    print(f"✓ active explicit_flag=true count: {count}")
    assert count >= 1, "expected at least one active explicit track"


if __name__ == "__main__":
    asyncio.run(main())
