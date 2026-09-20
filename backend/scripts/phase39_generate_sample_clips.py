"""Phase 39 Session 2 — Generate 8-second sample clips for each launch
persona via ElevenLabs.  Idempotent: skips personas that already have
`sample_clip_url` populated.  Caps ElevenLabs calls at 10 per invocation.

Run with `python -m scripts.phase39_generate_sample_clips` or call
`generate_sample_clips(db)` programmatically.

Per persona we synthesize a 1-sentence intro line specific to the
archetype (stored on the persona doc as `sample_clip_script`), then
push the MP3 to Tigris under `persona_samples/<persona_id>.mp3` (when
STORAGE_BACKEND=tigris) or leave it on local disk.
"""
from __future__ import annotations
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

log = logging.getLogger("bigfm.phase39_samples")

SAMPLE_SCRIPTS = {
    "p39_dawn_caller":              "Good morning, this is Asha — let's ease into your day with a soft start. Chai chal raha hai?",
    "p39_drive_time_energizer":  "Morning crew, wheels up! Time to roll into the day with a little extra spark — let's go.",
    "p39_lunch_cousin":              "Lunch ho gaya? Pull up your chair, we've got the best vibes lined up for the next hour.",
    "p39_afternoon_storyteller":  "Settle in for a moment — ek baat batayein. The afternoon has its own quiet rhythm, let's listen together.",
    "p39_sunset_reflector":      "Day done, slow down. Thoda saans le lo. The sun's saying its goodbye, and that's our cue too.",
    "p39_friday_night_hype":      "The weekend starts NOW. City's on tonight — turn it up, we're going in.",
    "p39_late_night_confidant":  "Still up? You're not alone. Raat ki chuppi mein bhi music chal raha hai — let's keep each other company.",
    "p39_devotional_murmur":      "Om Shanti. Sab thik hoga. Yeh thodi der ki shanti aapke liye hai.",
    "p39_bilingual_news_anchor": "Here is what you need to know — the headlines this hour, sirf FUUSIC par.",
    "p39_weekend_vibe_curator":  "Weekend mood, locked in. No rush today, let it flow — we'll be right here with you.",
}


def _sample_storage_key(persona_id: str) -> str:
    return f"persona_samples/{persona_id}.mp3"


async def generate_sample_clips(db, force: bool = False) -> dict:
    """Returns {generated, skipped, failed, calls_made, details[]}."""
    from services.rj import synthesize_solo
    from core.config import DEFAULT_ENERGY
    from services.object_storage import get_storage
    backend = (os.environ.get("STORAGE_BACKEND") or "local").lower()

    generated, skipped, failed, calls_made = 0, 0, 0, 0
    details: list[dict] = []

    async for doc in db.rj_personality_profiles.find({"is_launch_persona": True}):
        pid = doc["_id"]
        if not force and doc.get("sample_clip_url"):
            skipped += 1
            details.append({"persona_id": pid, "status": "skipped_already_has_clip"})
            continue
        voice_id = doc.get("voice_id")
        if not voice_id:
            failed += 1
            details.append({"persona_id": pid, "status": "no_voice_id"})
            continue
        script = SAMPLE_SCRIPTS.get(pid)
        if not script:
            failed += 1
            details.append({"persona_id": pid, "status": "no_sample_script"})
            continue

        try:
            out_path = await asyncio.to_thread(
                synthesize_solo, script, voice_id, DEFAULT_ENERGY)
            calls_made += 1
        except Exception as e:
            failed += 1
            details.append({"persona_id": pid,
                                          "status": f"tts_failed:{type(e).__name__}",
                                          "error": str(e)[:200]})
            log.error("[phase39_samples] tts_failed pid=%s: %s", pid, e)
            continue

        storage_key = _sample_storage_key(pid)
        clip_url: str = ""
        try:
            if backend == "tigris":
                get_storage().upload(local_path=str(out_path),
                                                          key=storage_key,
                                                          content_type="audio/mpeg")
                clip_url = get_storage().get_signed_url(
                    key=storage_key, expires_in=3600)
                # Remove local copy.
                try: out_path.unlink(missing_ok=True)
                except Exception: pass
            else:
                clip_url = f"/storage/rj/{Path(out_path).name}"
        except Exception as e:
            log.warning("[phase39_samples] storage_failed pid=%s: %s", pid, e)
            clip_url = f"/storage/rj/{Path(out_path).name}"

        await db.rj_personality_profiles.update_one(
            {"_id": pid},
            {"$set": {
                "sample_clip_url":          clip_url,
                "sample_clip_storage_key": storage_key,
                "sample_clip_script":      script,
                "sample_clip_generated_at":
                    datetime.now(timezone.utc).isoformat(),
            }})
        generated += 1
        details.append({"persona_id": pid, "status": "generated",
                                      "url_preview": clip_url[:80]})
        log.info("[phase39_samples] generated pid=%s url=%s", pid, clip_url[:80])

    return {"generated":    generated,
                  "skipped":      skipped,
                  "failed":        failed,
                  "calls_made": calls_made,
                  "details":      details}


async def _main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    force = "--force" in sys.argv
    result = await generate_sample_clips(db, force=force)
    print("[phase39_samples]", {k: v for k, v in result.items() if k != "details"})
    for d in result["details"]:
        print("  ", d)


if __name__ == "__main__":
    asyncio.run(_main())
