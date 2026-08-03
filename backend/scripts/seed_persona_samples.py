"""Phase 42-F.5 + Phase H'.1 — Seed persona sample MP3s.

Replaces both the legacy ElevenLabs-only Phase 39 seeder and the F.5
OpenAI-TTS interim.  Default provider = `elevenlabs` (H'.1).  Pass
`--provider openai` to use OpenAI TTS as a fallback / cost-control mode.

H'.1 features:
  • Voice resolution via `services.elevenlabs_tts.resolve_voice_id_for_persona`
    (archetype override → voice_key → legacy default).
  • Persists `elevenlabs_voice_id`, `sample_provider`, `sample_clip_url`
    (with cache-busting `?v=elevenlabs1` query) on each persona doc.
  • Idempotent: skips personas whose `sample_provider` already matches
    the requested provider unless `--force` is passed.
  • Logs ONLY metadata — voice_id, char_count, latency_ms — never the
    ElevenLabs key.

Run:
  python -m scripts.seed_persona_samples                            # default = elevenlabs
  python -m scripts.seed_persona_samples --provider elevenlabs
  python -m scripts.seed_persona_samples --provider openai
  python -m scripts.seed_persona_samples --force                    # regenerate everything
"""
from __future__ import annotations
import argparse
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

log = logging.getLogger("bigfm.persona_samples")

SAMPLE_DIR = Path("/app/backend/storage/persona_samples")
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

# Phase 39 stock scripts — short, persona-flavoured.  ~80-120 chars each.
SAMPLE_SCRIPTS = {
    "p39_dawn_caller":              "[warm] Good morning. [soft] This is your Dawn Caller on BigFM. [warm] Chai chal raha hai? Let's ease into the day, doston.",
    "p39_drive_time_energizer":  "[excited] Morning crew, wheels UP! [hyped] This is Drive Time on BigFM — let's roll into the day, full energy. Let's go!",
    "p39_lunch_cousin":              "[warm] Lunch ho gaya? [chuckles] Pull up your chair — this is your Lunch Cousin on BigFM with the best vibes for the next hour.",
    "p39_afternoon_storyteller":  "[soft] Settle in for a moment. [warm] Ek baat batayein — the afternoon has its own quiet rhythm. This is BigFM, listening with you.",
    "p39_sunset_reflector":      "[soft] Day done, slow down. [warm] Thoda saans le lo. The sun is saying its goodbye — this is your Sunset Reflector on BigFM.",
    "p39_friday_night_hype":      "[shouts] The weekend starts NOW!! [hyped] City is on tonight — turn it UP, doston. Friday Night Hype on BigFM!",
    "p39_late_night_confidant":  "[soft] Still up? [warm] You're not alone. Raat ki chuppi mein bhi music chal raha hai. Late Night Confidant on BigFM.",
    "p39_devotional_murmur":      "[warm] Om Shanti. [soft] Sab thik hoga. Yeh thodi der ki shanti aapke liye hai. BigFM, dil se.",
    "p39_bilingual_news_anchor": "[warm] Here is what you need to know — [excited] the headlines this hour, [warm] sirf BigFM par.",
    "p39_weekend_vibe_curator":  "[warm] Weekend mood, locked in. [chuckles] No rush today, let it flow — Weekend Vibe Curator, BigFM, dil se.",
}

# OpenAI TTS fallback voices (when --provider openai).
OPENAI_VOICE_FOR_PERSONA = {
    "p39_dawn_caller":              "shimmer",
    "p39_drive_time_energizer":  "nova",
    "p39_lunch_cousin":              "fable",
    "p39_afternoon_storyteller":  "alloy",
    "p39_sunset_reflector":      "alloy",
    "p39_friday_night_hype":      "nova",
    "p39_late_night_confidant":  "echo",
    "p39_devotional_murmur":      "shimmer",
    "p39_bilingual_news_anchor": "onyx",
    "p39_weekend_vibe_curator":  "fable",
}


async def _seed_elevenlabs(db, *, force: bool) -> dict:
    """H'.1 path — uses the shared services.elevenlabs_tts helper which
    in turn wraps services.rj.synthesize_elevenlabs_raw."""
    from services.elevenlabs_tts import (
        synthesize, resolve_voice_id_for_persona, LEGACY_DEFAULT_VOICE_ID)
    generated, skipped, failed = 0, 0, 0
    details: list[dict] = []
    async for doc in db.rj_personality_profiles.find({"is_launch_persona": True}):
        pid = doc["_id"]
        existing_provider = doc.get("sample_provider") or ""
        already_eleven = (existing_provider == "elevenlabs_turbo_v2_5"
                                        and doc.get("sample_clip_url"))
        if not force and already_eleven:
            skipped += 1
            details.append({"persona_id": pid,
                                          "status": "skipped_already_elevenlabs"})
            continue
        script = SAMPLE_SCRIPTS.get(pid)
        if not script:
            failed += 1
            details.append({"persona_id": pid,
                                          "status": "no_sample_script"})
            continue
        voice_id = resolve_voice_id_for_persona(doc)
        out_path = SAMPLE_DIR / f"{pid}.mp3"
        res = await asyncio.to_thread(
            synthesize, script, voice_id, energy="medium",
            out_path=out_path)
        if not res["ok"]:
            failed += 1
            details.append({"persona_id": pid,
                                          "voice_id": voice_id,
                                          "status": "tts_failed",
                                          "error":    res.get("error")})
            log.error("[persona_samples] tts_failed pid=%s voice=%s err=%s",
                                    pid, voice_id, res.get("error"))
            continue
        # Persist URL with cache-busting query so old <audio src=...>
        # tags re-fetch.
        clip_url = f"/api/static/persona_samples/{pid}.mp3?v=elevenlabs1"
        await db.rj_personality_profiles.update_one(
            {"_id": pid},
            {"$set": {
                "sample_clip_url":          clip_url,
                "sample_clip_storage_key": f"persona_samples/{pid}.mp3",
                "sample_clip_script":      script,
                "sample_clip_voice":        voice_id,
                "elevenlabs_voice_id":      voice_id,
                "sample_provider":          "elevenlabs_turbo_v2_5",
                "sample_clip_generated_at":
                    datetime.now(timezone.utc).isoformat(),
            }})
        generated += 1
        details.append({"persona_id": pid,
                                      "voice_id":  voice_id,
                                      "url":          clip_url,
                                      "status":    "generated",
                                      "char_count": res["char_count"],
                                      "latency_ms": res["latency_ms"],
                                      "size_bytes": (out_path.stat().st_size
                                                                      if out_path.exists() else None)})
        log.info("[persona_samples] generated pid=%s voice=%s "
                            "chars=%d ms=%d bytes=%d",
                              pid, voice_id, res["char_count"], res["latency_ms"],
                              out_path.stat().st_size if out_path.exists() else 0)
    return {"generated": generated, "skipped": skipped,
                  "failed": failed, "provider": "elevenlabs",
                  "default_fallback_voice": LEGACY_DEFAULT_VOICE_ID,
                  "details": details}


async def _seed_openai(db, *, force: bool) -> dict:
    """Phase 42-F.5 path retained as a cost-control fallback."""
    from openai import OpenAI
    api_key = (os.environ.get("OPENAI_API_KEY")
                  or os.environ.get("EMERGENT_LLM_KEY") or "").strip()
    if not api_key:
        return {"error": "OPENAI_API_KEY missing", "generated": 0,
                      "skipped": 0, "failed": 0, "provider": "openai"}
    client = OpenAI(api_key=api_key)
    generated, skipped, failed = 0, 0, 0
    details: list[dict] = []
    async for doc in db.rj_personality_profiles.find({"is_launch_persona": True}):
        pid = doc["_id"]
        existing_provider = doc.get("sample_provider") or ""
        if (not force and existing_provider == "openai_tts_1"
                and doc.get("sample_clip_url")):
            skipped += 1
            details.append({"persona_id": pid, "status": "skipped_already_openai"})
            continue
        script = SAMPLE_SCRIPTS.get(pid)
        voice = OPENAI_VOICE_FOR_PERSONA.get(pid, "alloy")
        if not script:
            failed += 1
            details.append({"persona_id": pid, "status": "no_sample_script"})
            continue
        try:
            resp = await asyncio.to_thread(
                client.audio.speech.create,
                model="tts-1", voice=voice, input=script,
                response_format="mp3")
            (SAMPLE_DIR / f"{pid}.mp3").write_bytes(resp.content)
        except Exception as e:
            failed += 1
            details.append({"persona_id": pid, "status": "tts_failed",
                                          "error": str(e)[:200]})
            continue
        clip_url = f"/api/static/persona_samples/{pid}.mp3?v=openai1"
        await db.rj_personality_profiles.update_one(
            {"_id": pid},
            {"$set": {
                "sample_clip_url": clip_url,
                "sample_clip_script": script,
                "sample_clip_voice": voice,
                "sample_provider":      "openai_tts_1",
                "sample_clip_generated_at":
                    datetime.now(timezone.utc).isoformat(),
            }})
        generated += 1
        details.append({"persona_id": pid, "voice": voice,
                                      "url": clip_url, "status": "generated"})
    return {"generated": generated, "skipped": skipped,
                  "failed": failed, "provider": "openai",
                  "details": details}


async def seed_samples(db, *, provider: str = "elevenlabs",
                                                  force: bool = False) -> dict:
    p = (provider or "elevenlabs").lower()
    if p == "openai":
        return await _seed_openai(db, force=force)
    return await _seed_elevenlabs(db, force=force)


# Kept for backwards-compat with any caller relying on the F.5 name.
async def seed_samples_via_openai(db, force: bool = False) -> dict:
    return await _seed_openai(db, force=force)


async def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider",
                                          choices=["elevenlabs", "openai"],
                                          default="elevenlabs")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    res = await seed_samples(db, provider=args.provider, force=args.force)
    print("[persona_samples]",
                {k: v for k, v in res.items() if k != "details"})
    for d in res.get("details", []):
        print("  ", d)


if __name__ == "__main__":
    asyncio.run(_main())
