"""Auto-seed tracks on first boot.

Downloads up to 3 royalty-free MP3 clips and trims them to 60s.
Gracefully logs and skips on any failure — never raises.
"""
from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional
import urllib.request

from audio_pipeline import ffprobe_info

logger = logging.getLogger(__name__)

# SoundHelix is a well-known source of royalty-free demo MP3s.
SEED_TRACKS = [
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "title": "Neon Pulse",
        "artist": "SoundHelix",
        "energy_level": "high",
        "mood": "energetic",
    },
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
        "title": "Midnight Lounge",
        "artist": "SoundHelix",
        "energy_level": "chill",
        "mood": "melancholy",
    },
    {
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "title": "Late Night Drive",
        "artist": "SoundHelix",
        "energy_level": "medium",
        "mood": "uplifting",
    },
]

TRIM_SECONDS = 45  # keep clips short for fast tests


def _download(url: str, dest: Path, timeout: int = 25) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BigFM/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
            f.write(r.read())
        return dest.stat().st_size > 1024
    except Exception as e:
        logger.warning(f"Seed download failed for {url}: {e}")
        return False


def _trim(src: Path, dst: Path, seconds: int = TRIM_SECONDS) -> bool:
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-t", str(seconds),
                "-c:a", "libmp3lame", "-b:a", "192k",
                "-ar", "44100", "-ac", "2",
                str(dst),
            ],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            logger.warning(f"ffmpeg trim failed: {proc.stderr[-500:]}")
            return False
        return True
    except Exception as e:
        logger.warning(f"trim error: {e}")
        return False


def seed_tracks(storage_dir: Path) -> List[dict]:
    """Try to download and trim seed tracks. Returns list of metadata dicts.

    Each dict: {id, title, artist, file_path, duration_sec}
    On any failure, that track is skipped (not raised).
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    results: List[dict] = []
    for meta in SEED_TRACKS:
        tmp_path = storage_dir / f"_seed_tmp_{uuid.uuid4().hex}.mp3"
        ok = _download(meta["url"], tmp_path)
        if not ok:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            continue

        track_id = str(uuid.uuid4())
        final_path = storage_dir / f"{track_id}.mp3"
        ok = _trim(tmp_path, final_path, TRIM_SECONDS)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        if not ok or not final_path.exists():
            continue

        try:
            info = ffprobe_info(final_path)
        except Exception as e:
            logger.warning(f"ffprobe failed on seed: {e}")
            final_path.unlink(missing_ok=True)
            continue

        results.append({
            "id": track_id,
            "title": meta["title"],
            "artist": meta["artist"],
            "file_path": str(final_path),
            "duration_sec": info["duration_sec"],
            "energy_level": meta.get("energy_level", "medium"),
            "mood": meta.get("mood", "uplifting"),
        })
        logger.info(f"Seeded track: {meta['title']} ({info['duration_sec']:.1f}s)")

    return results


# ---------- Phase 1: seed test users ----------
from datetime import datetime, timezone


SEED_USERS = [
    {
        "email": "test@bigfm.dubai",
        "name": "Test Listener",
        "password": "TestUser123!",
        "role": "user",
        "onboarding_complete": True,
        "preference_vector": {
            "languages":   ["hindi", "bollywood", "english"],
            "genres":      ["bollywood", "pop", "hip_hop"],
            "eras":        ["2010s", "2020s"],
            "moods":       ["energetic", "chill", "party"],
            "activities":  ["late_night_drive", "party", "evening_commute"],
            "favorite_artists": [],
            "city":        "Dubai",
            "home_area":   "JLT",
            "host_personality": "auto",
            "explicit_ok": True,
        },
    },
    {
        "email": "admin@bigfm.dubai",
        "name": "BigFM Admin",
        "password": "AdminPass123!",
        "role": "admin",
        "onboarding_complete": True,
        "preference_vector": {
            "languages":   ["english", "hindi", "bollywood"],
            "genres":      ["bollywood", "pop", "electronic"],
            "eras":        ["2010s", "2020s"],
            "moods":       ["energetic", "uplifting", "chill"],
            "activities":  ["workday_focus", "evening_commute"],
            "favorite_artists": [],
            "city":        "Dubai",
            "home_area":   "Business Bay",
            "host_personality": "auto",
            "explicit_ok": True,
        },
    },
    # Phase 3 — mocked premium tester (no real Stripe charge required)
    {
        "email": "premium@bigfm.dubai",
        "name": "Premium Tester",
        "password": "PremiumTest123!",
        "role": "user",
        "onboarding_complete": True,
        "preference_vector": {
            "languages":   ["hindi", "english", "bollywood"],
            "genres":      ["bollywood", "indie", "pop"],
            "eras":        ["2010s", "2020s"],
            "moods":       ["chill", "romantic", "uplifting"],
            "activities":  ["evening_commute", "late_night_drive", "dinner"],
            "favorite_artists": [],
            "city":        "Dubai",
            "home_area":   "Marina",
            "host_personality": "auto",
            "explicit_ok": True,
        },
        "is_premium": True,
        "premium_tier": "premium",
        "reward_multiplier": 2.0,
        "subscription_seed": True,  # marks: seed a fake active sub doc below
    },
]


async def seed_users(db, hash_password) -> int:
    """Idempotently create the QA users (test + admin + premium). Returns count created."""
    import uuid as _uuid
    from datetime import timedelta
    created = 0
    for su in SEED_USERS:
        existing = await db.users.find_one({"email": su["email"]}, {"_id": 0})
        now = datetime.now(timezone.utc)
        seed_subscription = su.pop("subscription_seed", False)
        if existing:
            patch = {}
            if not existing.get("password_hash"):
                patch["password_hash"] = hash_password(su["password"])
            if existing.get("role") != su["role"]:
                patch["role"] = su["role"]
            if not existing.get("onboarding_complete") and su.get("onboarding_complete"):
                patch["onboarding_complete"] = True
                patch["preference_vector"] = su["preference_vector"]
            # Phase 3: keep premium flag fresh on seed user (sub doc only set
            # if not yet present, so a paid test from this account isn't clobbered)
            if su.get("is_premium") and not existing.get("is_premium"):
                patch["is_premium"] = True
                patch["premium_tier"] = su.get("premium_tier", "premium")
                patch["reward_multiplier"] = float(su.get("reward_multiplier", 2.0))
            if seed_subscription and not existing.get("subscription"):
                patch["subscription"] = {
                    "stripe_subscription_id": "sub_test_seeded_premium",
                    "stripe_customer_id": "cus_test_seeded_premium",
                    "status": "active",
                    "plan": "premium_annual",
                    "currency": "USD",
                    "current_period_start": now,
                    "current_period_end": now + timedelta(days=365),
                    "trial_end": None,
                    "cancel_at_period_end": False,
                }
            if patch:
                await db.users.update_one({"email": su["email"]}, {"$set": patch})
            continue
        doc = {
            "user_id": f"user_{_uuid.uuid4().hex[:16]}",
            "email": su["email"],
            "name": su["name"],
            "picture": None,
            "auth_provider": "email",
            "password_hash": hash_password(su["password"]),
            "role": su["role"],
            "onboarding_complete": su["onboarding_complete"],
            "preference_vector": su["preference_vector"],
            "created_at": now,
            "last_login_at": None,
        }
        if su.get("is_premium"):
            doc["is_premium"] = True
            doc["premium_tier"] = su.get("premium_tier", "premium")
            doc["reward_multiplier"] = float(su.get("reward_multiplier", 2.0))
        if seed_subscription:
            doc["subscription"] = {
                "stripe_subscription_id": "sub_test_seeded_premium",
                "stripe_customer_id": "cus_test_seeded_premium",
                "status": "active",
                "plan": "premium_annual",
                "currency": "USD",
                "current_period_start": now,
                "current_period_end": now + timedelta(days=365),
                "trial_end": None,
                "cancel_at_period_end": False,
            }
        await db.users.insert_one(doc)
        created += 1
    return created
