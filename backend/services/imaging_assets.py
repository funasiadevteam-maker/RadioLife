"""Phase 3.8 — Imaging asset specs + lazy generation + Mongo schema.

Each station ("station_slug") has a starter pack of ~55 imaging assets:
- brand_id_short      x 8   (≤2.5s station identifications)
- brand_id_long       x 6   (≤6s with mini-tagline + USP)
- daypart_opener      x 20  (5 per × 4 dayparts: morning_drive/lunch/evening_drive/nightlife)
- top_of_hour         x 4   (legal/branded hourly ID)
- sponsor_bumper      x 4   ("After this break, we'll be right back...")
- game_stinger        x 4   ("Time to PLAY...")
- winner_stinger      x 4   ("WINNER WINNER WINNER")
- premium_id          x 2   ("RadioLife Premium — ad-free, all the time")
- legal_id            x 1   ("RadioLife. Owned and operated by RadioLife Networks.")
- music_bed           x 4   (chill/medium/uplifting/energetic — ElevenLabs Sound Gen)
- sweeper_short       x 4   (whoosh-style, reused from SFX library if available)

Total: 55+ assets per station.

Two markets are configured: `bigfm_dubai` (RadioLife — Dubai market slug) and `funasia_dfw`
(FunAsia AI Radio / DFW). Each station carries its own brand tagline,
primary/secondary voice keys, and asset texts.

Stored in MongoDB collection `imaging_assets` with schema:
    {
      _id, station_slug, asset_type, slug, voice_key, daypart, energy,
      script, file_path, duration_sec, loudness_lufs, peak_dbfs,
      weight, active, generated_at, generation_status
    }

Files land under `/app/backend/storage/imaging/<station_slug>/<asset_type>/<slug>.mp3`.

Sonic Branding doc (per station) lives in `sonic_branding`:
    { _id, station_slug, station_name, tagline, primary_voice_key,
      secondary_voice_key, sonic_logo_asset_id, brand_words, updated_at }
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

from audio_pipeline import ffprobe_duration, truncate_audio
from core.config import (
    ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID, ELEVEN_OUTPUT_FORMAT,
    ELEVENLABS_API_KEY, STORAGE_DIR,
)
from services.loudness import normalize_to_lufs

logger = logging.getLogger("bigfm.imaging")

IMAGING_DIR = STORAGE_DIR / "imaging"
IMAGING_DIR.mkdir(parents=True, exist_ok=True)


# ---------- Station + Sonic Branding seed ----------
STATIONS: Dict[str, dict] = {
    "bigfm_dubai": {
        "station_slug": "bigfm_dubai",
        "station_name": "RadioLife Dubai",
        "market": "dubai",
        "tagline": "Dubai's #1 AI-powered Bollywood radio.",
        "primary_voice_key": "charlie_dj",      # American hype DJ
        "secondary_voice_key": "raghav_hindi",  # Hindi warm voice
        "brand_words": ["Dubai", "RadioLife", "non-stop", "Bollywood", "dil se", "AI powered", "human energy"],
        "imaging_style_preset": "high_energy_bollywood",
    },
    "funasia_dfw": {
        "station_slug": "funasia_dfw",
        "station_name": "FunAsia AI Radio",
        "market": "dfw",
        "tagline": "Your city, your music, your rewards.",
        "primary_voice_key": "charlie_dj",
        "secondary_voice_key": "aanya_hindi",
        "brand_words": ["FunAsia", "Dallas", "DFW", "Bollywood", "rewards", "deals", "Spin Win Eat Repeat"],
        "imaging_style_preset": "warm_diaspora_bollywood",
    },
}


# ---------- Voice settings for imaging (radio drops, not radio shows) ----------
IMAGING_VOICE_SETTINGS = {
    "stability": 0.18,
    "similarity_boost": 0.62,
    "style": 0.88,
    "use_speaker_boost": True,
}


# ---------- Asset script specs (per station) ----------
# Each entry: (asset_type, slug, daypart_or_null, energy_or_null, primary_or_secondary, max_sec, script)

def _scripts_for_station(st: dict) -> List[Tuple[str, str, Optional[str], Optional[str], str, float, str]]:
    name = st["station_name"]
    is_dxb = st["market"] == "dubai"
    city_drop = "Dubai" if is_dxb else "Dallas"

    brand_short = [
        ("brand_id_short", "bid_01", None, "high",  "primary",   2.4, f"[hyped] You're listening to {name}!"),
        ("brand_id_short", "bid_02", None, "high",  "secondary", 2.6, f"[excited] {name}... [warm] dil se!"
                                                                       if is_dxb else f"[excited] {name}... [warm] yaaron ke saath!"),
        ("brand_id_short", "bid_03", None, "high",  "primary",   2.6, f"[shouts] {city_drop}'s number ONE station — {name}!"),
        ("brand_id_short", "bid_04", None, "high",  "primary",   2.4, f"[hyped] Non-stop hits — {name}!"),
        ("brand_id_short", "bid_05", None, "medium","secondary", 2.6, f"[warm] {name}. [excited] Music chalega NON-stop."),
        ("brand_id_short", "bid_06", None, "high",  "primary",   2.4, f"[hyped] {city_drop} is listening — {name}!"),
        ("brand_id_short", "bid_07", None, "high",  "secondary", 2.5, f"[hyped] Bollywood, beats, {city_drop} — {name}!"),
        ("brand_id_short", "bid_08", None, "high",  "primary",   2.4, f"[shouts] You. Are. ON. {name}!"),
    ]

    brand_long = ([
        ("brand_id_long", "bil_01", None, "medium", "primary",   5.5,
         "[warm] AI powered. [hyped] Human energy. [excited] RadioLife — dil se."),
        ("brand_id_long", "bil_02", None, "medium", "secondary", 5.8,
         "[upbeat] Bollywood hits. Local deals. Real rewards. [hyped] RadioLife."),
        ("brand_id_long", "bil_03", None, "medium", "primary",   5.5,
         "[chill] This is the new sound of radio. [excited] RadioLife."),
        ("brand_id_long", "bil_04", None, "medium", "secondary", 5.5,
         "[warm] Nonstop Bollywood energy, [hyped] personalized for you. RadioLife."),
        ("brand_id_long", "bil_05", None, "medium", "primary",   5.5,
         "[hyped] The world is listening. [warm] You're never alone on a long drive. RadioLife."),
        ("brand_id_long", "bil_06", None, "medium", "secondary", 5.8,
         "[excited] Music chalega non-stop, [warm] kahin bhi, kabhi bhi. [hyped] RadioLife."),
    ] if is_dxb else [
        ("brand_id_long", "bil_01", None, "medium", "primary",   5.8,
         "[upbeat] FunAsia AI Radio — your city, your music, your rewards."),
        ("brand_id_long", "bil_02", None, "medium", "secondary", 5.8,
         "[warm] Bollywood hits. [excited] Local deals. Real rewards. [hyped] This is FunAsia AI."),
        ("brand_id_long", "bil_03", None, "medium", "primary",   5.5,
         "[hyped] Dallas is listening. FunAsia AI Radio."),
        ("brand_id_long", "bil_04", None, "medium", "secondary", 5.5,
         "[warm] Your commute just got smarter. [excited] FunAsia AI Radio."),
        ("brand_id_long", "bil_05", None, "medium", "primary",   5.8,
         "[chill] Music, traffic, weather, and deals on your route. [excited] FunAsia AI."),
        ("brand_id_long", "bil_06", None, "medium", "primary",   5.0,
         "[hyped] Spin. Win. Eat. Repeat. [excited] FunAsia AI."),
    ])

    if is_dxb:
        daypart = [
            # Morning Drive
            ("daypart_opener", "mor_01", "morning_drive", "medium", "primary",   4.5, "[warm] Good morning Dubai. [excited] Morning Drive starts now."),
            ("daypart_opener", "mor_02", "morning_drive", "medium", "secondary", 4.8, "[upbeat] Traffic, weather, Bollywood energy — [excited] let's go."),
            ("daypart_opener", "mor_03", "morning_drive", "high",   "primary",   4.5, "[hyped] Wake up Dubai. RadioLife Morning Drive!"),
            ("daypart_opener", "mor_04", "morning_drive", "medium", "secondary", 5.0, "[warm] Karama to Marina, [upbeat] we've got the soundtrack for your drive."),
            ("daypart_opener", "mor_05", "morning_drive", "medium", "primary",   4.5, "[upbeat] Suprabhat Dubai. RadioLife, Morning Drive."),

            # Lunch Rush
            ("daypart_opener", "lun_01", "lunch_rush", "medium", "primary",   4.5, "[upbeat] Lunch Rush is ON. RadioLife."),
            ("daypart_opener", "lun_02", "lunch_rush", "medium", "secondary", 4.8, "[warm] Hot music, [excited] hotter deals — Lunch Rush."),
            ("daypart_opener", "lun_03", "lunch_rush", "medium", "primary",   4.8, "[upbeat] Your next lunch stop is closer than you think."),
            ("daypart_opener", "lun_04", "lunch_rush", "medium", "secondary", 5.0, "[warm] Midday Mehfil. [excited] Karama special on RadioLife."),
            ("daypart_opener", "lun_05", "lunch_rush", "medium", "primary",   4.5, "[hyped] RadioLife Lunch Rush. Let's eat. Let's groove."),

            # Evening Drive
            ("daypart_opener", "eve_01", "evening_drive", "high", "primary",   4.5, "[hyped] Evening Drive powered by RadioLife!"),
            ("daypart_opener", "eve_02", "evening_drive", "high", "secondary", 4.8, "[excited] Traffic outside. [hyped] Party inside. RadioLife."),
            ("daypart_opener", "eve_03", "evening_drive", "high", "primary",   5.0, "[hyped] Dinner, movies, music, and your route home — RadioLife."),
            ("daypart_opener", "eve_04", "evening_drive", "medium", "secondary", 5.0, "[warm] Sheikh Zayed Road jam? [excited] RadioLife has you covered."),
            ("daypart_opener", "eve_05", "evening_drive", "high", "primary",   4.5, "[hyped] 5 PM Dubai. RadioLife Evening Drive."),

            # Nightlife / Party
            ("daypart_opener", "ngt_01", "nightlife_mode", "party", "primary",   4.5, "[shouts] Nightlife Mode. [hyped] RadioLife!"),
            ("daypart_opener", "ngt_02", "nightlife_mode", "party", "secondary", 4.8, "[hyped] The city is awake. [excited] RadioLife."),
            ("daypart_opener", "ngt_03", "nightlife_mode", "party", "primary",   4.5, "[shouts] Bollywood club energy starts NOW!"),
            ("daypart_opener", "ngt_04", "nightlife_mode", "party", "secondary", 4.8, "[hyped] JBR, Marina, Downtown — [shouts] RadioLife Nightlife!"),
            ("daypart_opener", "ngt_05", "nightlife_mode", "party", "primary",   4.5, "[shouts] Drop. The. Bass. RadioLife!"),
        ]
    else:
        daypart = [
            # Morning Drive
            ("daypart_opener", "mor_01", "morning_drive", "medium", "primary",   4.5, "[warm] Good morning DFW. [excited] Morning Drive starts now."),
            ("daypart_opener", "mor_02", "morning_drive", "medium", "secondary", 4.8, "[upbeat] Traffic, weather, Bollywood energy — [excited] FunAsia AI."),
            ("daypart_opener", "mor_03", "morning_drive", "high",   "primary",   4.5, "[hyped] Wake up Dallas. FunAsia AI Morning Drive!"),
            ("daypart_opener", "mor_04", "morning_drive", "medium", "secondary", 5.0, "[warm] Frisco to Plano, [upbeat] we've got your commute soundtrack."),
            ("daypart_opener", "mor_05", "morning_drive", "medium", "primary",   4.5, "[upbeat] Good morning Texas. FunAsia AI Morning Drive."),

            # Lunch Rush
            ("daypart_opener", "lun_01", "lunch_rush", "medium", "primary",   4.5, "[upbeat] Lunch Rush is ON. FunAsia AI."),
            ("daypart_opener", "lun_02", "lunch_rush", "medium", "secondary", 4.8, "[warm] Hot music, [excited] hot deals — Lunch Rush."),
            ("daypart_opener", "lun_03", "lunch_rush", "medium", "primary",   4.8, "[upbeat] Your next curry stop is closer than you think."),
            ("daypart_opener", "lun_04", "lunch_rush", "medium", "secondary", 5.0, "[warm] Irving special on FunAsia. [excited] Spin, win, eat."),
            ("daypart_opener", "lun_05", "lunch_rush", "medium", "primary",   4.5, "[hyped] FunAsia Lunch Rush. Let's eat. Let's groove."),

            # Evening Drive
            ("daypart_opener", "eve_01", "evening_drive", "high", "primary",   4.5, "[hyped] Evening Drive powered by FunAsia AI!"),
            ("daypart_opener", "eve_02", "evening_drive", "high", "secondary", 4.8, "[excited] Traffic outside. [hyped] Party inside. FunAsia AI."),
            ("daypart_opener", "eve_03", "evening_drive", "high", "primary",   5.0, "[hyped] Dinner, movies, music, and your route home — FunAsia AI."),
            ("daypart_opener", "eve_04", "evening_drive", "medium", "secondary", 5.0, "[warm] 75 South traffic? [excited] FunAsia AI has you covered."),
            ("daypart_opener", "eve_05", "evening_drive", "high", "primary",   4.5, "[hyped] 5 PM Dallas. FunAsia Evening Drive."),

            # Nightlife / Party
            ("daypart_opener", "ngt_01", "nightlife_mode", "party", "primary",   4.5, "[shouts] Nightlife Mode. [hyped] FunAsia AI!"),
            ("daypart_opener", "ngt_02", "nightlife_mode", "party", "secondary", 4.8, "[hyped] Dallas is awake. [excited] FunAsia AI."),
            ("daypart_opener", "ngt_03", "nightlife_mode", "party", "primary",   4.5, "[shouts] Bollywood club energy starts NOW!"),
            ("daypart_opener", "ngt_04", "nightlife_mode", "party", "secondary", 4.8, "[hyped] Toyota Music Factory night — [shouts] FunAsia Nightlife!"),
            ("daypart_opener", "ngt_05", "nightlife_mode", "party", "primary",   4.5, "[shouts] Drop. The. Bass. FunAsia AI Dallas!"),
        ]

    top_of_hour = [
        ("top_of_hour", "toh_01", None, "medium", "primary",   3.5, f"[crisp] It's the top of the hour on {name}."),
        ("top_of_hour", "toh_02", None, "medium", "secondary", 4.0, f"[warm] {name}. [crisp] On the hour, every hour."),
        ("top_of_hour", "toh_03", None, "medium", "primary",   3.8, f"[crisp] Top of the hour — {name}."),
        ("top_of_hour", "toh_04", None, "medium", "secondary", 4.2, f"[warm] You're listening to {name}. [crisp] Top of the hour."),
    ]

    sponsor = [
        ("sponsor_bumper", "spn_01", None, "medium", "primary",   3.5, "[warm] When we're back — [crisp] a word from our partners."),
        ("sponsor_bumper", "spn_02", None, "medium", "secondary", 3.8, "[crisp] After this break, [warm] we'll be right back."),
        ("sponsor_bumper", "spn_03", None, "medium", "primary",   3.5, "[upbeat] Quick word from our sponsors — [warm] don't go anywhere."),
        ("sponsor_bumper", "spn_04", None, "medium", "secondary", 3.5, "[warm] Brought to you by our partners. [upbeat] Stay tuned."),
    ]

    game = [
        ("game_stinger",   "gam_01", None, "high", "primary",   2.6, "[hyped] Time to PLAY!"),
        ("game_stinger",   "gam_02", None, "high", "secondary", 2.6, "[excited] Let's play a game!"),
        ("game_stinger",   "gam_03", None, "party", "primary",  2.4, "[shouts] BIG GAME on RadioLife!" if is_dxb else "[shouts] BIG GAME on FunAsia AI!"),
        ("game_stinger",   "gam_04", None, "high", "secondary", 2.6, "[hyped] Listen up — [excited] this could win you cash!"),
    ]

    winner = [
        ("winner_stinger", "win_01", None, "party", "primary",   2.6, "[shouts] WINNER. WINNER. WINNER."),
        ("winner_stinger", "win_02", None, "party", "primary",   2.6, "[shouts] You. Just. WON!"),
        ("winner_stinger", "win_03", None, "party", "secondary", 2.8, "[hyped] Congratulations! [shouts] You are a winner!"),
        ("winner_stinger", "win_04", None, "party", "primary",   2.4, "[shouts] DING DING DING. WINNER!"),
    ]

    premium = [
        ("premium_id",     "prm_01", None, "medium", "primary",   4.0, f"[warm] {name} Premium — [excited] ad-free, all the time."),
        ("premium_id",     "prm_02", None, "medium", "secondary", 4.2, f"[upbeat] Go Premium. [warm] {name} — yours to enjoy."),
    ]

    legal = [
        ("legal_id",       "lgl_01", None, "medium", "primary",   5.5,
         "[crisp] RadioLife. Owned and operated by RadioLife Networks."
         if is_dxb else
         "[crisp] FunAsia AI Radio. A FunAsia Media production. Dallas, Texas."),
    ]

    return (brand_short + brand_long + daypart + top_of_hour + sponsor + game + winner + premium + legal)


# ---------- Music bed seed (ElevenLabs Sound Generation API) ----------
MUSIC_BED_SEED: List[Tuple[str, str, float]] = [
    # (slug, prompt, duration_sec)
    ("bed_chill",     "chill lofi instrumental, soft electric piano, mellow bass, 28 seconds, no vocals, loopable",          28.0),
    ("bed_medium",    "warm Bollywood-inspired instrumental, mid-tempo, soft acoustic guitar + tabla loop, 28 seconds, no vocals", 28.0),
    ("bed_uplifting", "uplifting pop-Bollywood instrumental, bright synth pad, light percussion, 28 seconds, no vocals, loopable", 28.0),
    ("bed_energetic", "energetic club Bollywood instrumental bed, deep bass + sub kick + light cymbal, 28 seconds, no vocals, loopable", 28.0),
]

# Sweepers — short whoosh-style transitions, reuse Sound Generation
SWEEPER_SEED: List[Tuple[str, str, float]] = [
    ("sweep_01", "fast whoosh sweep with subtle riser, 0.8 seconds, club transition", 0.9),
    ("sweep_02", "riser whoosh with bass drop tail, 1.2 seconds, sharp transition",   1.2),
    ("sweep_03", "downsweep whoosh with vinyl scratch, 1 second, DJ transition",      1.0),
    ("sweep_04", "synth riser sweep, 1.5 seconds, energetic build-up",                1.5),
]

_SOUND_GEN_URL = "https://api.elevenlabs.io/v1/sound-generation"


def _station_dir(station_slug: str, asset_type: str) -> Path:
    p = IMAGING_DIR / station_slug / asset_type
    p.mkdir(parents=True, exist_ok=True)
    return p


def _voice_id_for(voice_key: str) -> str:
    """Look up the ElevenLabs voice_id for a voice_key. Falls back to DJ Charlie."""
    try:
        from services.voice_config import VOICE_REGISTRY
        v = VOICE_REGISTRY.get(voice_key)
        if v and v.get("voice_id"):
            return v["voice_id"]
    except Exception:
        pass
    return "IKne3meq5aSn9XLyUdCD"  # DJ Charlie fallback


# ---------- Mongo bootstrap ----------
async def ensure_imaging_indexes(db) -> None:
    await db.imaging_assets.create_index([("station_slug", 1), ("asset_type", 1), ("active", 1)])
    await db.imaging_assets.create_index([("station_slug", 1), ("asset_type", 1), ("slug", 1)], unique=True)
    await db.imaging_assets.create_index([("station_slug", 1), ("daypart", 1)])
    await db.station_flow_logs.create_index([("user_id", 1), ("played_at", -1)])
    await db.station_flow_logs.create_index([("session_id", 1), ("played_at", -1)])
    await db.sonic_branding.create_index([("station_slug", 1)], unique=True)


async def seed_imaging_assets(db) -> dict:
    """Idempotent: insert one asset doc per spec if it doesn't already exist.
    Does NOT generate the actual MP3 — that's deferred to
    ensure_imaging_audio_blocking()."""
    created = 0
    total = 0
    for st in STATIONS.values():
        slug = st["station_slug"]
        # 1) sonic_branding upsert
        await db.sonic_branding.update_one(
            {"station_slug": slug},
            {"$set": {
                "station_slug": slug,
                "station_name": st["station_name"],
                "market": st["market"],
                "tagline": st["tagline"],
                "primary_voice_key": st["primary_voice_key"],
                "secondary_voice_key": st["secondary_voice_key"],
                "brand_words": st["brand_words"],
                "imaging_style_preset": st["imaging_style_preset"],
                "updated_at": datetime.now(timezone.utc),
            }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

        # 2) voice scripts
        for asset_type, asset_slug, daypart, energy, voice_role, max_sec, script in _scripts_for_station(st):
            total += 1
            voice_key = st["primary_voice_key"] if voice_role == "primary" else st["secondary_voice_key"]
            insert_only = {
                "station_slug": slug,
                "asset_type": asset_type,
                "slug": asset_slug,
                "kind": "tts",
                "file_path": str(_station_dir(slug, asset_type) / f"{asset_slug}.mp3"),
                "duration_sec": 0.0,
                "loudness_lufs": None,
                "peak_dbfs": None,
                "weight": 1.0,
                "generation_status": "pending",
                "generated_at": None,
            }
            r = await db.imaging_assets.update_one(
                {"station_slug": slug, "asset_type": asset_type, "slug": asset_slug},
                {"$setOnInsert": insert_only, "$set": {
                    "script": script, "voice_key": voice_key,
                    "max_duration_sec": max_sec, "active": True,
                    "voice_role": voice_role, "daypart": daypart, "energy": energy,
                }},
                upsert=True,
            )
            if r.upserted_id is not None:
                created += 1

        # 3) music beds (Sound Generation)
        for bed_slug, prompt, dur in MUSIC_BED_SEED:
            total += 1
            insert_only = {
                "station_slug": slug,
                "asset_type": "music_bed",
                "slug": bed_slug,
                "voice_key": None,
                "voice_role": None,
                "daypart": None,
                "kind": "sound_gen",
                "file_path": str(_station_dir(slug, "music_bed") / f"{bed_slug}.mp3"),
                "duration_sec": 0.0,
                "loudness_lufs": None,
                "peak_dbfs": None,
                "weight": 1.0,
                "generation_status": "pending",
                "generated_at": None,
            }
            r = await db.imaging_assets.update_one(
                {"station_slug": slug, "asset_type": "music_bed", "slug": bed_slug},
                {"$setOnInsert": insert_only, "$set": {
                    "script": prompt, "active": True,
                    "max_duration_sec": dur,
                    "energy": bed_slug.replace("bed_", ""),
                }},
                upsert=True,
            )
            if r.upserted_id is not None:
                created += 1

        # 4) sweepers (Sound Generation, short)
        for sw_slug, prompt, dur in SWEEPER_SEED:
            total += 1
            insert_only = {
                "station_slug": slug,
                "asset_type": "sweeper_short",
                "slug": sw_slug,
                "voice_key": None,
                "voice_role": None,
                "daypart": None,
                "energy": "high",
                "kind": "sound_gen",
                "file_path": str(_station_dir(slug, "sweeper_short") / f"{sw_slug}.mp3"),
                "duration_sec": 0.0,
                "loudness_lufs": None,
                "peak_dbfs": None,
                "weight": 1.0,
                "generation_status": "pending",
                "generated_at": None,
            }
            r = await db.imaging_assets.update_one(
                {"station_slug": slug, "asset_type": "sweeper_short", "slug": sw_slug},
                {"$setOnInsert": insert_only,
                 "$set": {"script": prompt, "active": True, "max_duration_sec": dur}},
                upsert=True,
            )
            if r.upserted_id is not None:
                created += 1
    return {"created": created, "total_expected": total * 1, "stations": list(STATIONS.keys())}


# ---------- Actual MP3 generation (slow; runs in background) ----------
def _generate_tts(voice_id: str, script: str, max_sec: float, out_raw: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        return False
    try:
        from elevenlabs import ElevenLabs, VoiceSettings
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        vs = VoiceSettings(**IMAGING_VOICE_SETTINGS)
        try:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_id, model_id=ELEVEN_MODEL_ID, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        except Exception:
            audio_iter = client.text_to_speech.convert(
                voice_id=voice_id, model_id=ELEVEN_FALLBACK_MODEL, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        with open(out_raw, "wb") as f:
            for chunk in audio_iter:
                if chunk:
                    f.write(chunk)
        try:
            truncate_audio(out_raw, max_sec + 0.4, fade_out_ms=120)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning(f"TTS gen failed for {out_raw.name}: {e}")
        return False


def _generate_sound(prompt: str, duration_sec: float, out_raw: Path) -> bool:
    if not ELEVENLABS_API_KEY:
        return False
    try:
        r = requests.post(
            _SOUND_GEN_URL,
            headers={"xi-api-key": ELEVENLABS_API_KEY,
                     "Content-Type": "application/json", "accept": "audio/mpeg"},
            json={"text": prompt,
                  "duration_seconds": min(max(duration_sec, 0.5), 22.0),
                  "prompt_influence": 0.55},
            timeout=120,
        )
        if r.status_code != 200:
            logger.warning(f"sound-gen {out_raw.name} HTTP {r.status_code}: {r.text[:160]}")
            return False
        with open(out_raw, "wb") as f:
            f.write(r.content)
        try:
            truncate_audio(out_raw, duration_sec, fade_out_ms=80)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning(f"sound-gen exception for {out_raw.name}: {e}")
        return False


def _gen_one_asset(asset: dict) -> dict:
    """Synchronous: generate ONE asset + normalize. Returns updated fields."""
    out_path = Path(asset["file_path"])
    raw_path = out_path.with_name(out_path.stem + ".raw.mp3")
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    ok = False
    if asset.get("kind") == "tts":
        voice_id = _voice_id_for(asset.get("voice_key") or "charlie_dj")
        ok = _generate_tts(voice_id, asset["script"], float(asset.get("max_duration_sec", 4.0)), raw_path)
    else:
        ok = _generate_sound(asset["script"], float(asset.get("max_duration_sec", 4.0)), raw_path)

    if not ok or not raw_path.exists() or raw_path.stat().st_size < 200:
        return {"generation_status": "failed", "generated_at": datetime.now(timezone.utc)}

    # Loudness normalize → out_path
    norm = normalize_to_lufs(raw_path, out_path, target_i=-14.0, target_tp=-1.0)
    try:
        raw_path.unlink(missing_ok=True)  # type: ignore
    except Exception:
        pass

    dur = 0.0
    try:
        dur = float(ffprobe_duration(out_path) or 0.0)
    except Exception:
        pass

    return {
        "generation_status": "ready",
        "generated_at": datetime.now(timezone.utc),
        "duration_sec": dur,
        "loudness_lufs": (norm or {}).get("loudness_lufs"),
        "peak_dbfs":     (norm or {}).get("peak_dbfs"),
    }


_GENERATION_TASK_RUNNING = False


async def ensure_imaging_audio_async(db, *, station_slug: Optional[str] = None,
                                     limit: Optional[int] = None,
                                     force: bool = False) -> dict:
    """Background generator. Iterates pending assets and produces MP3 + normalizes.
    Throttled to one asset every ~0.4s. Re-entrant-safe.

    Args:
        station_slug: only generate for this station; None = all
        limit: max number of new assets to generate this run
        force: regenerate even if status='ready'
    """
    global _GENERATION_TASK_RUNNING
    if _GENERATION_TASK_RUNNING and not force:
        return {"started": False, "reason": "already running"}
    _GENERATION_TASK_RUNNING = True
    created = 0
    failed = 0
    try:
        q: Dict = {}
        if station_slug:
            q["station_slug"] = station_slug
        if not force:
            q["generation_status"] = {"$in": ["pending", "failed"]}
        cursor = db.imaging_assets.find(q)
        assets = await cursor.to_list(length=200)
        if limit:
            assets = assets[:limit]
        for a in assets:
            try:
                upd = await asyncio.to_thread(_gen_one_asset, a)
                await db.imaging_assets.update_one({"_id": a["_id"]}, {"$set": upd})
                if upd.get("generation_status") == "ready":
                    created += 1
                else:
                    failed += 1
            except Exception as e:
                logger.warning(f"asset gen exception: {e}")
                failed += 1
            await asyncio.sleep(0.4)
        logger.info(f"Imaging audio gen pass complete: created={created} failed={failed}")
        return {"started": True, "created": created, "failed": failed}
    finally:
        _GENERATION_TASK_RUNNING = False
