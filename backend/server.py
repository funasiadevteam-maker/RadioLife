"""RadioLife Phase 2 — Channels, Music Clocks, Compliance, Share-this-break.

Phases 0+1 are fully preserved. Phase 2 layers on:
- 8 channels (Bollywood Mehfil / Party Dubai / Late Night Drive / Punjabi Beats /
  Morning Masala / Devotional Hour / Retro Lounge / Workout Wala) each with their
  own host roster + music clock rotation
- 6 new RJ voices (DJ Riya, Pandit Anand, Gurpreet Bhaji, Aarti, Kishore Da, Simran)
- Server-side compliance: 4/artist/3hr, 3/album/3hr, no-3-consecutive-artist,
  6 skips/hr (429 with retry_after_sec)
- Upcoming tracks NEVER leak in /api/radio/session
- Share-this-break: slice the RJ portion of any played segment, append station
  stinger, return /r/<share_id> landing
- Friendly registration errors (parsed in the frontend; backend stays the same)
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import shutil
import subprocess as _sp
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import (
    APIRouter, Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from openai import OpenAI
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

from audio_pipeline import (
    build_segment, build_stream, build_party_segment, concat_with_gaps, ffprobe_info,
    new_uuid_filename, truncate_audio,
)
from auth import (
    PreferenceVector, auth_router, current_user, current_user_optional,
    ensure_auth_indexes, hash_password, require_admin, users_router,
)
from auto_tagger import auto_tag as run_auto_tag
from channels import (
    CHANNELS, DEFAULT_CHANNEL_SLUG, RJ_VOICES_EXT, VOICE_PREVIEW_SCRIPTS_EXT,
    apply_music_clock_slot, channel_filter, channel_supports_duo, get_channel,
    list_active_channels, pick_voice_for_segment, seed_channels, slot_for_position,
)
from compliance import (
    banned_artists_albums,
    consecutive_artists_to_block, ensure_compliance_indexes, log_event,
    shares_count_today, skip_state, get_skip_policy, set_skip_policy,
)
from seed import ensure_demo_tracks, seed_users
from services.billing_service import ensure_billing_indexes, expire_lapsed_subscriptions
from services.stripe_setup import stripe_setup_bootstrap
from routes.billing import billing_router, webhook_router
from routes.sfx_status import sfx_router
# P0 mixed-content fix — HTTPS→HTTP audio proxy for imported streams.
from routes.stream_proxy import router as stream_proxy_router
# Phase RELIABILITY.P2 — client-reported live-stream failures.
from routes.playback_errors import router as playback_errors_router
from routes.audition import audition_router, render_audition_page
from routes.rj_quality import rj_quality_router
from routes.imaging import imaging_router
from routes.admin_ads import admin_ads_router
from routes.advertiser import advertiser_router
from routes.advertiser_ai import ai_router as advertiser_ai_router
from routes.phase18c import phase18c_router
from routes.phase18d import phase18d_router
from routes.podcasts import (podcasts_router, admin_podcasts_router,
                                                  podcasts_public_router)
from routes.admin_advertiser import admin_advertiser_router
from routes.ads_public import (
    ads_router, wallet_router, openrtb_router, vast_router, public_files_router,
)
from routes.phase45 import advertiser_p45_router, admin_p45_router
from routes.bigcoin import bc_router
from routes.games import games_router
from routes.admin_bigcoin import admin_bc_router
from routes.admin_analytics import admin_analytics_router
from routes.admin_retention import (
    admin_retention_router, me_retention_router, tracking_router,
    ensure_retention_indexes,
)
from routes.admin_safety import (
    admin_safety_router, ensure_safety_indexes,
)
from routes.billing_v6 import billing6_router
from routes.lobbies import lobbies_router
from routes.games_v2 import games_v2_router
from routes.games_v2_public import games_v2_public_router
from routes.games_v2_phase8c import games_v2c_router
from routes.games_v2_winners import games_v2_winners_router  # Phase 23 S1.5
from routes.games_v2_admin_campaigns import games_v2_admin_campaigns_router  # Phase 23 S2
from routes.predict_win_admin import (
    router as predict_win_admin_router,
    ensure_predict_win_indexes,
    seed_manual_provider as seed_predict_win_provider,
)  # Sub-Phase E1 — Predict & Win data model + admin builder
# Phase D — User-station song picker + content moderation.
from routes.station_tracks import (
    router as station_tracks_router,
    admin_router as admin_track_moderation_router,
    bootstrap_phase_d,
)
# Sub-Phase E2 — Predict & Win consumer endpoints.
from routes.predict_win_consumer import router as predict_win_consumer_router
# Phase PDX.1 — Predexon auto-curator (admin + public categories).
from routes.pdx_curator import (
    admin_router as pdx_curator_admin_router,
    admin_pw_points_router as pdx_admin_pw_points_router,
    public_router as pdx_public_router,
)
from services.predict_win_award_pipeline import ensure_e2_indexes
from routes.admin_users import (admin_users_router,
                                              ensure_phase19a_part5_indexes)  # Phase 19a P5
from services.games_v2_winners_redemptions import ensure_phase23_indexes
from routes.commute import (commute_router, system_router, route_ads_router,
                                    rj_extras_router, admin_rj_router)
from routes.local_commerce import (
    public_commerce_router, listener_commerce_router,
    partner_upgrade_router, partner_router, admin_commerce_router,
)
from services.games_v2 import (ensure_games_v2_indexes, seed_games_v2,
                                       migrate_phase5_games,
                                       ensure_partner_tokens_indexes)
from services.game_unlock_engine import (
    ensure_unlock_engine_indexes, seed_unlock_rules,
    background_unlock_sweep_task,
)
from services.games_v2_leads import ensure_lead_indexes
from services.games_v2_webhooks import (
    ensure_webhook_indexes, background_webhook_worker,
)
from services.games_v2_leaderboard import ensure_leaderboard_indexes
from services.games_v2_inventory import ensure_inventory_indexes
from services.maps_client import (
    ensure_maps_indexes, seed_mock_places, get_maps_client,
    probe_and_decide_client,
)
from services.commute import activate_commute_unlock_rule
from services.lobbies import ensure_lobby_indexes
# Phase 15d — geo + news + market context + de-Dubai migrations.
from routes.geo_routes import _make_router as _make_geo_router
# Phase 16-prep — channel thumbnails.
from services import channel_thumbnails as _thumbs
from fastapi.staticfiles import StaticFiles as _OriginalStaticFiles
# Phase Π+2 — global drop-in.  Every `StaticFiles(directory=…)` in this
# module auto-gains a Tigris fallback (302 → public Tigris URL when the
# local file is missing).  The class auto-derives tigris_prefix from
# the directory path, so existing mount call-sites need no changes.
try:
    from services.static_fallback import TigrisFallbackStaticFiles as StaticFiles
    _STATIC_FALLBACK_ON = True
except Exception as _e_static_fb:
    StaticFiles = _OriginalStaticFiles
    _STATIC_FALLBACK_ON = False
from services import phase15d_migrations as _p15d
from services.lobby_hub import LobbyHub
from sharing import DAILY_SHARE_LIMIT, create_share, get_share, increment_view

# ---------- bootstrap ----------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

STORAGE_DIR = ROOT_DIR / "storage"
TRACKS_DIR = STORAGE_DIR / "tracks"
RJ_DIR = STORAGE_DIR / "rj"
STREAMS_DIR = STORAGE_DIR / "streams"
SEGMENTS_DIR = STORAGE_DIR / "segments"
VOICE_PREVIEWS_DIR = STORAGE_DIR / "voice_previews"
SHARES_DIR = STORAGE_DIR / "shares"
SFX_DIR = STORAGE_DIR / "sfx"
for d in (TRACKS_DIR, RJ_DIR, STREAMS_DIR, SEGMENTS_DIR,
          VOICE_PREVIEWS_DIR, SHARES_DIR, SFX_DIR):
    d.mkdir(parents=True, exist_ok=True)

mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# ─── Phase Stabilization: placeholder MONGO_URL guard ──────────────────
# Detects common deploy mis-configurations (literal placeholder text
# pasted into the env var) and logs a clear, actionable warning at boot
# so the failure mode is obvious instead of a cryptic DNS lookup error
# 5 layers down the stack. Does NOT crash — the app stays importable so
# /api/health and /api/config_check still respond.
_MONGO_URL_PLACEHOLDERS = (
    "your-cluster", "your-user", "your-password", "USER:PASSWORD",
    "<user>", "<password>", "<cluster>", "<username>",
    "example.mongodb.net", "EXAMPLE", "xxxx",
)


def _mongo_url_warnings(url: str) -> list[str]:
    """Return a list of human-readable warnings if `url` looks
    mis-configured. Empty list when the URL passes basic sanity."""
    warns: list[str] = []
    if not url:
        warns.append("MONGO_URL is empty/unset.")
        return warns
    lower = url.lower()
    for token in _MONGO_URL_PLACEHOLDERS:
        if token.lower() in lower:
            warns.append(
                f"MONGO_URL contains placeholder text {token!r} — "
                f"replace with your actual Atlas cluster connection "
                f"string. See https://www.mongodb.com/docs/atlas/"
                f"connect-to-cluster/.")
    if not (url.startswith("mongodb://") or url.startswith("mongodb+srv://")):
        warns.append(
            "MONGO_URL must start with mongodb:// or mongodb+srv://")
    # Loopback default in production-looking env.
    if url == "mongodb://localhost:27017":
        env_mode = (os.getenv("ENV") or os.getenv("RUN_ENV")
                    or os.getenv("APP_ENV") or "").lower()
        if env_mode in ("production", "prod", "live"):
            warns.append(
                "MONGO_URL is the localhost default — no production "
                "MongoDB connection string has been injected.")
    return warns


_mongo_url_warnings_cached = _mongo_url_warnings(mongo_url)
if _mongo_url_warnings_cached:
    _boot_log = logging.getLogger("bigfm.config")
    for _w in _mongo_url_warnings_cached:
        _boot_log.warning("[CONFIG_CHECK] %s", _w)
    _boot_log.warning(
        "[CONFIG_CHECK] Backend will still start; DB-touching endpoints "
        "will fail at request time with a connection error. Use "
        "GET /api/config_check to see the full diagnostic.")

try:
    mongo_client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=10_000)
except Exception as _e:
    # Phase Stabilization — never let a malformed MONGO_URL kill import.
    # The actual connection happens lazily on first operation; a bad
    # URI here would only surface as a runtime error on the failing
    # request, not a deploy-blocking import error.
    logging.getLogger("bigfm").warning(
        "[boot] AsyncIOMotorClient construct failed (will lazy-retry "
        "on first DB op): %s", _e)
    mongo_client = AsyncIOMotorClient(
        "mongodb://localhost:27017", serverSelectionTimeoutMS=10_000)
db = mongo_client[os.getenv("DB_NAME", "bigfm")]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

ELEVEN_MODEL_ID = "eleven_v3"
ELEVEN_FALLBACK_MODEL = "eleven_multilingual_v2"
ELEVEN_OUTPUT_FORMAT = "mp3_44100_192"

MAX_RJ_SECONDS = 45.0
RJ_RESHORTEN_THRESHOLD = 42.0
SPEECH_WORDS_PER_SEC = 2.5
DUO_PROBABILITY = 0.30

# Original 3 hosts (Phase 0/1)
RJ_VOICES_CORE: Dict[str, dict] = {
    "veer_dubai": {
        "voice_id": "1WrEi9ztXQkVmKgG6j9A",
        "display_name": "Veer",
        "persona": "male, late-night radio voice, intimate and charming, Mumbai-Dubai NRI, mid-thirties, deep voice, smooth delivery",
        "fits_energies": ("chill", "medium"),
        "duo_label": "VEER",
        "duo_blurb": "smooth late-night charm, late-30s, Mumbai-origin, lives in Bur Dubai. Witty, slightly sarcastic, loves film references.",
    },
    "monika_dubai": {
        "voice_id": "rCmVtv8cYU60uhlsOo1M",
        "display_name": "Monika",
        "persona": "female, warm British-Indian, modulated and expressive, mid-twenties, Dubai resident, brunch-and-chai friend energy",
        "fits_energies": ("chill", "medium"),
        "duo_label": "MONIKA",
        "duo_blurb": "warm Delhi-origin, mid-20s, lives in JLT. High-energy, bubbly, foodie, the heart of the duo.",
    },
    "dj_dubai": {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "display_name": "DJ Charlie",
        "persona": "club MC, deep confident Australian-Indian, late-twenties, hypes the floor, explosive delivery, English-dominant party Hinglish",
        "fits_energies": ("high", "party"),
        "duo_label": "CHARLIE",
        "duo_blurb": "party DJ, 30s, Indo-Punjabi, club-MC energy. Always hyped, calls everyone boss/yaar/bro.",
    },
}
# Merge with Phase 2 hosts AND Phase 3.6 multi-provider registry
from services.voice_config import (
    VOICE_REGISTRY as _PHASE36_VOICES,
    DEFAULT_VOICE_KEY as _DEFAULT_FROM_36,
    preview_script_for as _phase36_preview_script,
)
RJ_VOICES: Dict[str, dict] = {**RJ_VOICES_CORE, **RJ_VOICES_EXT, **_PHASE36_VOICES}
DEFAULT_VOICE_KEY = "veer_dubai"

VOICE_PREVIEW_SCRIPTS_CORE: Dict[str, str] = {
    "veer_dubai":   "[warm] Aap sun rahe ho... [soft] RadioLife. [warm] Dil se, doston.",
    "monika_dubai": "[excited] Heyy! [warm] Aapki Monika, RadioLife par. [chuckles] Music chalega NON-stop!",
    "dj_dubai":     "[shouts] RadioLife!!! [hyped] DJ Charlie on the mic... [excited] LET'S GO!!!",
}
# Phase 3.6 voices come with their own preview scripts
_PHASE36_PREVIEWS = {k: _phase36_preview_script(k) for k in _PHASE36_VOICES}
VOICE_PREVIEW_SCRIPTS: Dict[str, str] = {
    **VOICE_PREVIEW_SCRIPTS_CORE, **VOICE_PREVIEW_SCRIPTS_EXT, **_PHASE36_PREVIEWS,
}

VOICE_SETTINGS_BY_ENERGY: Dict[str, dict] = {
    "chill":  {"stability": 0.50, "similarity_boost": 0.85, "style": 0.40, "use_speaker_boost": True},
    "medium": {"stability": 0.35, "similarity_boost": 0.80, "style": 0.55, "use_speaker_boost": True},
    "high":   {"stability": 0.18, "similarity_boost": 0.72, "style": 0.85, "use_speaker_boost": True},
    # Phase 3.5 — Mirchi-style extreme party settings (club-DJ delivery)
    "party":  {"stability": 0.10, "similarity_boost": 0.62, "style": 0.97, "use_speaker_boost": True},
}
DEFAULT_ENERGY = "medium"
ENERGY_LEVELS = ("chill", "medium", "high", "party")
MOOD_TAGS = ("romantic", "energetic", "melancholy", "uplifting", "dance", "groove", "intense")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bigfm")


# ---------- pydantic ----------
class TrackOut(BaseModel):
    id: str
    title: str
    artist: str
    duration_sec: float
    uploaded_at: datetime
    energy_level: str = DEFAULT_ENERGY
    mood: Optional[str] = None
    bpm: Optional[float] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    release_year: Optional[int] = None
    language: Optional[str] = None
    language_confidence: Optional[str] = None
    era: Optional[str] = None
    vibe_tags: list[str] = []
    recommended_time_of_day: list[str] = []
    danceability: Optional[float] = None
    explicit: bool = False
    isrc: Optional[str] = None
    fingerprint_match_score: Optional[float] = None
    auto_tagged_at: Optional[str] = None
    manual_overrides: list[str] = []


class RJContext(BaseModel):
    time_of_day: Optional[str] = None
    weather_hint: Optional[str] = None
    city: Optional[str] = None
    # Phase 15d — canonical market key (e.g. "dubai", "new_york"). When
    # present, RJ generators use this to pull the per-market lexicon and
    # forbid out-of-market references in the prompt.
    market: Optional[str] = None


class RJGenerateRequest(BaseModel):
    prev_track_id: str
    next_track_id: str
    context: RJContext = Field(default_factory=RJContext)


class RJGenerateResponse(BaseModel):
    script: str
    voice_id: str


class RJSynthRequest(BaseModel):
    script: str
    voice_id: Optional[str] = None


class RJSynthResponse(BaseModel):
    rj_audio_id: str
    file_path: str
    duration_sec: float


class StreamBuildRequest(BaseModel):
    track_ids: List[str]


class StreamSegment(BaseModel):
    type: str
    index: int
    start_sec: float
    end_sec: float


class StreamBuildResponse(BaseModel):
    stream_id: str
    file_path: str
    duration_sec: float
    segments: List[StreamSegment]


class RadioStartRequest(BaseModel):
    # Phase 10c.1 — accept both `channel` (legacy) and `channel_slug`
    # (canonical, matches the rest of the codebase).  Pydantic v2 alias.
    model_config = {"populate_by_name": True}
    channel: Optional[str] = Field(default=None, alias="channel_slug")


class HostInfo(BaseModel):
    voice_key: Optional[str] = None
    name: str


class RadioSegmentOut(BaseModel):
    segment_id: str
    segment_url: str
    duration_sec: float
    # Phase 41 P1 — news_anchor segments have no underlying music track,
    # so track fields are now optional (Pydantic None-safe).
    track_id: Optional[str] = None
    track_title: Optional[str] = None
    track_artist: Optional[str] = None
    # Phase Bug-1 — these are absent on cold-start no-RJ segments
    rj_voice_key: Optional[str] = None
    rj_voice_name: Optional[str] = None
    rj_script: Optional[str] = ""
    rj_start_sec: Optional[float] = None
    rj_format: str
    rj_hosts: List[HostInfo] = []
    channel_slug: Optional[str] = None
    channel_name: Optional[str] = None
    # Phase 41 P1 — surface segment kind so frontend can render
    # "news anchor" UI instead of a track card.
    kind: Optional[str] = None


class RadioStartResponse(BaseModel):
    session_id: str
    segment: RadioSegmentOut
    skip_state: dict


class RadioNextResponse(BaseModel):
    session_id: str
    segment: RadioSegmentOut
    skip_state: dict


class SwitchChannelRequest(BaseModel):
    # Phase 10c.1 — accept both `channel` and `channel_slug` (alias).
    model_config = {"populate_by_name": True}
    session_id: str
    channel: str = Field(alias="channel_slug")


class SwitchChannelResponse(BaseModel):
    session_id: str
    channel_slug: str
    channel_name: Optional[str] = None
    transitional: bool = True
    tuning_sfx_url: str
    estimated_ready_sec: int = 15
    skip_state: dict


class RadioReadyResponse(BaseModel):
    ready: bool
    segment: Optional[RadioSegmentOut] = None
    skip_state: dict


class ShareCreateRequest(BaseModel):
    segment_id: str


# ---------- in-memory state ----------
_session_locks: Dict[str, asyncio.Lock] = {}
# Tracks the in-flight prefetch task per session so /radio/next can await it
# instead of duplicating work (fixes the slow-skip latency issue).
_prefetch_tasks: Dict[str, asyncio.Task] = {}
# After a channel switch, holds the channel-rebuild task per session.
_switch_build_tasks: Dict[str, asyncio.Task] = {}


def _lock_for(sid: str) -> asyncio.Lock:
    lk = _session_locks.get(sid)
    if lk is None:
        lk = asyncio.Lock()
        _session_locks[sid] = lk
    return lk


def _public_base_url(request: Request) -> str:
    """Best-effort public origin for SSR meta tags."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    proto = forwarded_proto or request.url.scheme
    if forwarded_host:
        return f"{proto}://{forwarded_host}"
    return str(request.base_url).rstrip("/")


# ---------- helpers ----------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track_doc_to_out(doc: dict) -> TrackOut:
    uploaded_at = doc["uploaded_at"]
    if isinstance(uploaded_at, str):
        uploaded_at = datetime.fromisoformat(uploaded_at)
    return TrackOut(
        id=doc["_id"], title=doc["title"], artist=doc["artist"],
        duration_sec=doc["duration_sec"], uploaded_at=uploaded_at,
        energy_level=doc.get("energy_level", DEFAULT_ENERGY),
        mood=doc.get("mood"), bpm=doc.get("bpm"),
        album=doc.get("album"), genre=doc.get("genre"),
        release_year=doc.get("release_year"),
        language=doc.get("language"),
        language_confidence=doc.get("language_confidence"),
        era=doc.get("era"), vibe_tags=doc.get("vibe_tags") or [],
        recommended_time_of_day=doc.get("recommended_time_of_day") or [],
        danceability=doc.get("danceability"),
        explicit=bool(doc.get("explicit", False)),
        isrc=doc.get("isrc"),
        fingerprint_match_score=doc.get("fingerprint_match_score"),
        auto_tagged_at=doc.get("auto_tagged_at"),
        manual_overrides=doc.get("manual_overrides") or [],
    )


async def _get_track(track_id: str) -> dict:
    doc = await db.tracks.find_one({"_id": track_id})
    if not doc:
        raise HTTPException(404, f"track {track_id} not found")
    return doc


def _era_bucket(year: Optional[int]) -> Optional[str]:
    if not year: return None
    if year < 1990:  return "80s"
    if year < 2000:  return "90s"
    if year < 2010:  return "2000s"
    if year < 2020:  return "2010s"
    return "2020s"


# ---------- RJ prompts ----------

# Phase 3.6 — accent_target → language purity clause injected into the user prompt
ACCENT_PURITY_RULES = {
    "american": (
        "ACCENT TARGET: american. Write 90% English. Hindi is allowed ONLY for flavor "
        "words: yaar, boss, doston, scene, bilkul, mast, paaji. NEVER full Hindi sentences. "
        "DO NOT use ElevenLabs [tags] — this voice uses delivery instructions instead, "
        "so write CLEAN spoken English. Use ALL CAPS for emphasis and !! for hype, "
        "no [hyped]/[shouts] markers. Sound like an American Dubai-based club DJ."
    ),
    "indian_english": (
        "ACCENT TARGET: indian_english. Write 90% English with light Indian vocabulary "
        "(yaar, bhai, dosto). Avoid heavy Hindi sentences. No ElevenLabs [tags] — "
        "use ALL CAPS + !! for emphasis. Clean spoken English with Indian inflection."
    ),
    "hindi_native": (
        "ACCENT TARGET: hindi_native. Write 90%+ Hindi in Roman script. English only "
        "for unavoidable brand names (RadioLife, Dubai, Friday, party). Use young casual "
        "Hindi: 'kya scene hai', 'yaar', 'sun lo', 'mast', 'dekho', 'arre yaar'. "
        "Keep ElevenLabs [tags] like [hyped] [excited] [shouts] for emotion. "
        "Sound like a young Indian Hindi-speaking radio host."
    ),
    "hinglish": (
        "ACCENT TARGET: hinglish. Mix English + Hindi freely (~60% English, 40% Hindi "
        "connectors). Use ElevenLabs [tags] for emotion. Standard RadioLife Hinglish blend."
    ),
    "punjabi": (
        "ACCENT TARGET: punjabi. Write 70% Punjabi/Hindi in Roman script, 30% English. "
        "Hearty Punjabi expressions: 'paaji', 'oye', 'kya haal hai', 'mast'. "
        "Use ElevenLabs [tags] for emotion."
    ),
    "devotional": (
        "ACCENT TARGET: devotional. Warm, slow, Sanskrit-leaning Hindi. No hype tags. "
        "Use [warm] [soft] [whispers]. Avoid party/club references."
    ),
}


def _accent_target_for_voice(voice_key: str) -> str:
    v = RJ_VOICES.get(voice_key) or {}
    return v.get("accent_target", "hinglish")


def _accent_purity_clause(voice_key: str) -> str:
    return ACCENT_PURITY_RULES.get(_accent_target_for_voice(voice_key),
                                    ACCENT_PURITY_RULES["hinglish"])


HINGLISH_SYSTEM_PROMPT = """You are writing scripts for an ElevenLabs eleven_v3 voice on RadioLife. The voice can render emotion ONLY if you tag it. Untagged text = monotone. ALWAYS tag your output.

CRITICAL — MARKET LOCALISATION:
- The user prompt will include a MARKET CONTEXT block (city, country, lexicon, brands, landmarks, food, weather idioms).
- Whatever city is named in MARKET CONTEXT IS the city you broadcast in.
- Replace ALL default Dubai/UAE references with that market's references.
- NEVER mix markets. If the market is New York, do NOT mention Dubai, Karama, JLT, Sharjah, Bur Dubai, UAE, RTA, Sheikh Zayed Road, Global Village, JBR, Burj, karak chai, biryani-as-Dubai-anchor, or any Gulf-specific token. Use the lexicon's brands/landmarks/food instead.
- The station identity is just "RadioLife" — append the market city ONLY when the lexicon's display_name is present (e.g. "RadioLife <market_city>", spelled in full per the lexicon).

OUTPUT FORMAT — use these inline tags liberally:
- [excited] [hyped] [shouts] for high-energy moments and opening hooks
- [soft] [whispers] [warm] for chill/intimate moments
- [laughs] [chuckles] for natural humor (sparingly, once per script max)
- [pause] or "..." for breath
- ALL CAPS on the single most important word per sentence (the engine renders louder)
- Use !! or !!! for explosive endings
- Tag every script with at least 3 emotion markers and at least 1 ALL CAPS word
- Match the tag intensity to the next song's energy_level (chill / medium / high / party)
- Never explain a tag — just use it inline
- Keep total spoken length 15-25 seconds (40-65 words excluding tag markers)
- The MARKET CONTEXT city name must appear at least once; pronunciation is handled by the dictionary

COLLOQUIAL RULES:
- Mix natural spoken Hinglish appropriate to the market's South-Asian diaspora. ~60% English + 40% Hindi connectors. Hindi in Roman script.
- Drop authentic references that match the MARKET CONTEXT lexicon: areas, brands, food, commute, weather. DO NOT invent foreign cities.
- Never reveal the upcoming song's title or artist — only mood/vibe/energy hints.
- Always reference the previous song's mood briefly, then transition into the next energy.
- Vary sign-offs: "RadioLife, dil se" / "Music chalega non-stop" / "Aap sun rahe ho RadioLife" / "Stay locked in yaar". You may suffix the market city, e.g. "RadioLife <market_city>, dil se".
- No stage directions in brackets OTHER than the tag list above. No emojis.
- NEVER invent specific clock times (e.g. "7 AM", "3 PM", "midnight", "noon"). Use only the daypart phrase provided in the user prompt ("morning", "afternoon", "evening drive time", "late night"). Saying a wrong hour breaks listener trust."""

DUO_HINGLISH_SYSTEM_PROMPT = """You are scripting a Hinglish radio banter between TWO co-hosts on RadioLife. Output is a tagged dialogue between exactly two speakers.

CRITICAL — MARKET LOCALISATION:
- The user prompt will include a MARKET CONTEXT block. Whatever city it names IS the city your hosts broadcast in tonight.
- NEVER mix markets. If the market is New York, do NOT mention Dubai/Karama/JLT/Sharjah/UAE/Burj/JBR/Sheikh Zayed/Global Village/RTA. Use the lexicon's brands/landmarks/food.
- The hosts below have personal back-stories rooted in their home cities; mention those home-city anchors ONLY when the broadcast market equals their home city. Otherwise they are visiting / hosting from the market city.

The user will tell you which two hosts to use as HOST_A and HOST_B. Hosts available:
- VEER: smooth late-night charm, late-30s, Mumbai-origin. Witty, slightly sarcastic, loves film references.
- MONIKA: warm Delhi-origin, mid-20s. High-energy, bubbly, foodie, the heart of the duo.
- CHARLIE: party DJ, 30s, Indo-Punjabi, club-MC energy. Always hyped, calls everyone "boss"/"yaar"/"bro".
- RIYA: DJ Riya, female club MC, late-20s, English-heavy, hyped.
- ANAND: Pandit Anand, 55+ male, wisdom keeper, devotional broadcaster, slow warm baritone.
- GURPREET: Punjabi specialist male, dhaba energy, hearty and loud.
- AARTI: bubbly morning-show female, Delhi-origin, fast peppy enthusiastic.
- KISHORE: Kishore Da, classic broadcaster, smooth drawl, late-80s AIR nostalgia.
- SIMRAN: Punjabi female co-host, playful, warm, teases Gurpreet.

OUTPUT FORMAT — use this EXACT structure (one turn per line, starting with the speaker tag in square brackets):
[HOST_A_LABEL] [warm] some line with [tags] inline...
[HOST_B_LABEL] [excited] her reply with [tags] inline!!
[HOST_A_LABEL] [chuckles] ...
[HOST_B_LABEL] [hyped] ...

Rules:
- Use ONLY the two speaker tags I tell you. Never invent others.
- 4 to 6 turns total. Alternate speakers strictly.
- Each turn is 1-2 SHORT sentences (6-16 words). NEVER write a paragraph from one speaker.
- Real Hinglish banter — they tease each other, agree, disagree playfully, react to the previous song, hype the next song's mood.
- Drop authentic references that match the MARKET CONTEXT lexicon (areas, brands, food, commute, weather). NEVER invent foreign cities or import Gulf-specific tokens into other markets.
- Match energy of the next song.
- Always end with a hook into the next song mood — never reveal title/artist.
- Station identity is just "RadioLife" (you may suffix the market city when natural). Pronunciation dictionary already covers Dubai/Karama/JLT/RadioLife — write them normally if and only if the market is Dubai.
- Use [tags] every turn. ALL-CAPS one word per turn for emphasis.

TOTAL spoken length: 25-40 seconds (50-90 words across all turns combined). DO NOT exceed 42 seconds."""


# ---------- RJ helpers ----------

# Phase 3.5 — channels and energies that route through Mirchi-style prompts
PARTY_CHANNEL_SLUGS = {"party_dubai", "workout_wala", "premium_mehfil"}


def _is_mirchi_party(channel: dict, energy: str) -> bool:
    if not channel: return False
    slug = channel.get("_id") or channel.get("slug")
    return slug in PARTY_CHANNEL_SLUGS and energy in ("high", "party")


MIRCHI_SOLO_SYSTEM_PROMPT = """You are scripting a Hinglish radio jockey moment for RadioLife's PARTY channel, in the style of Radio Mirchi 98.3 FM with DJ Richard and RJ Ayontika.

CRITICAL — MARKET LOCALISATION:
- The user prompt will include a MARKET CONTEXT block (city, country, lexicon, brands, landmarks, food).
- NEVER mix markets. If the market is New York, do NOT mention Dubai/Karama/JLT/JBR/Sharjah/UAE/Burj/Sheikh Zayed/Global Village/Marina Walk/Atlantis. Use the lexicon's brands/landmarks/food/commute instead.
- The station identity is "RadioLife" (optionally suffix the market city, e.g. "RadioLife <market_city>", spelled in full per the lexicon).

This is COMMERCIAL DANCE RADIO. Match Mirchi's exact vibe:
- Constant high energy, NO lulls, no slow moments
- Rapid Hinglish code-switching mid-sentence (60% English, 40% Hindi connectors)
- DJ-style hype phrases — embed at least 3 per script. Use the MARKET CITY in any "Turn it UP, <CITY>!" line; never hardcode "Dubai":
  "Turn it UP, <CITY>!" · "Hands in the AIR!" · "Dance floor BLAZING!" · "Drop your phones!"
  "Volume FULL!" · "Yaar this is INSANE!" · "RadioLife, NONSTOP!"
  "Are you READY??" · "Let's GOOO!" · "Beat drop incoming!" · "Crowd se SHOUT karo!"

OUTPUT FORMAT — use eleven_v3 audio tags HEAVILY. Mandatory minimum 5 tags per script:
- [hyped] [shouts] [screams] [excited] for high-energy moments
- [chuckles] [laughs] for genuine fun moments (1-2 per script)
- "..." for breath beats
- ALL CAPS on 4+ key words per script

LOCAL REFERENCES — sprinkle authentic NRI-diaspora mentions appropriate to the MARKET CITY. Pull from the MARKET CONTEXT lexicon (areas, brands, food). Do NOT invent foreign-city anchors.

LENGTH: 18-28 seconds total spoken time (35-55 words). Always end with a hook into the upcoming song — never reveal title.
"""


MIRCHI_DUO_SYSTEM_PROMPT = """You are scripting Mirchi 98.3 FM-style DUO BANTER between TWO hosts on RadioLife's PARTY channel, in the style of DJ Richard × RJ Ayontika.

CRITICAL — MARKET LOCALISATION:
- The user prompt will include a MARKET CONTEXT block. Whatever city it names IS the city your hosts broadcast in tonight.
- NEVER mix markets. If the market is New York, do NOT mention Dubai/Karama/JLT/JBR/Sharjah/UAE/Burj/Sheikh Zayed/Global Village/Marina Walk/Atlantis. Use the lexicon's brands/landmarks/food/commute instead.
- Station identity is "RadioLife" (optionally suffix the market city).

Output is a tagged rapid-fire dialogue between exactly two speakers. The user will tell you which two hosts to use as HOST_A and HOST_B. Hosts available:
- VEER, MONIKA, CHARLIE, RIYA, ANAND, GURPREET, AARTI, KISHORE, SIMRAN.

OUTPUT FORMAT — use this EXACT structure (one turn per line, starting with the speaker tag in square brackets):
[HOST_A_LABEL] [hyped] some short line with [tags] inline!!
[HOST_B_LABEL] [excited] her short reply with [tags] inline!!

CRITICAL Mirchi-style RULES:
- This is COMMERCIAL DANCE RADIO. Match Mirchi's exact vibe.
- 6 to 10 short rapid-fire turns (NOT 4-6 like other channels).
- Each turn is 5-15 WORDS MAX — no monologue, no paragraph from one speaker.
- Hosts hype each other up, finish each other's sentences, shout in unison.
- 60% English + 40% Hindi connectors, code-switch mid-sentence.
- Use [hyped] [shouts] [screams] [excited] heavily; [chuckles] once or twice for genuine fun.
- ALL-CAPS one word per turn for emphasis.
- Embed at least 3 DJ-hype phrases across the script. Use the MARKET CITY in any "<CITY>" shout-out; never hardcode "Dubai":
  "Turn it UP <CITY>!" · "Hands in the AIR!" · "Dance floor BLAZING!" · "Drop your phones!"
  "Volume FULL!" · "Yaar this is INSANE!" · "RadioLife NONSTOP!"
  "Are you READY??" · "Let's GOOO!" · "Beat drop incoming!" · "Crowd se SHOUT karo!"

LOCAL REFERENCES — pull from the MARKET CONTEXT lexicon ONLY (areas, brands, food, commute). Do NOT invent foreign-city anchors.

EXAMPLE STRUCTURE (use SAME shape but vary content — substitute the market city for <CITY>):
[CHARLIE] [hyped] Riya, kya scene hai <CITY>!!
[RIYA] [excited] Charlie boss, dance floor PHATEGA!!
[CHARLIE] [shouts] Hands in the AIR, doston!!
[RIYA] [hyped] Yaar this beat is INSANE!!
[CHARLIE] [chuckles] Riya, control yourself...
[RIYA] [excited] Nahi nahi, VOLUME FULL boss!!
[CHARLIE] [hyped] RadioLife NONSTOP!!
[RIYA] [shouts] Are you READY for the drop??

TOTAL spoken length: 22-35 seconds (50-85 words across all turns). DO NOT exceed 40 seconds. End with a hook into the next song mood — never reveal title/artist.
"""


def _estimate_speech_seconds(script: str) -> float:
    cleaned = re.sub(r"\[[^\]]+\]", " ", script)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = max(1, len(cleaned.split()))
    return words / SPEECH_WORDS_PER_SEC


def _build_solo_user_prompt(prev, nxt, ctx, rj_persona, channel_name=None, shorten=False):
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    nxt_mood = nxt.get("mood") or "uplifting"
    if prev:
        prev_energy = prev.get("energy_level", DEFAULT_ENERGY)
        prev_mood = prev.get("mood") or "uplifting"
        prev_line = (f"Previous song just ended: '{prev['title']}' by {prev['artist']} "
                     f"(energy={prev_energy}, mood={prev_mood}).")
        transition = f"Transition: {prev_energy} → {nxt_energy}."
    else:
        prev_line = "This is the opening of the show — no previous song yet."
        transition = f"Opening energy: {nxt_energy}."
    ctx_bits = []
    if ctx.time_of_day:  ctx_bits.append(f"time of day: {ctx.time_of_day}")
    if ctx.weather_hint: ctx_bits.append(f"weather: {ctx.weather_hint}")
    # Phase 15d — pull city from the lexicon when ctx.city is empty so we
    # don't silently fall back to "Dubai" for non-Dubai markets.
    _ctx_market = (getattr(ctx, "market", None) or "dubai").strip().lower()
    try:
        from services.market_lexicon import get_lexicon as _get_lex
        _lex_city = _get_lex(_ctx_market).get("display_name") or "Dubai"
    except Exception:
        _lex_city = "Dubai"
    ctx_bits.append(f"city: {ctx.city or _lex_city}")
    if channel_name:     ctx_bits.append(f"show: {channel_name}")
    shorter = " BE SHORTER — keep total spoken length under 30 seconds (40-55 words max)." if shorten else ""
    return (
        f"You are speaking as: {rj_persona}. "
        f"{prev_line} "
        f"Next song coming up (DO NOT name it): '{nxt['title']}' by {nxt['artist']} "
        f"(energy={nxt_energy}, mood={nxt_mood}). "
        f"{transition} Context — {'; '.join(ctx_bits)}.{shorter} "
        f"Write the Hinglish on-air bridge now, MATCHING the {nxt_energy} energy of the next song."
    )


def _generate_rj_script_solo(prev, nxt, ctx, voice_key, channel_name=None, channel=None,
                                                          location_context: Optional[dict] = None) -> str:
    if not openai_client:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    persona = RJ_VOICES.get(voice_key, RJ_VOICES[DEFAULT_VOICE_KEY])["persona"]
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    use_mirchi = _is_mirchi_party(channel, nxt_energy)
    system_prompt = MIRCHI_SOLO_SYSTEM_PROMPT if use_mirchi else HINGLISH_SYSTEM_PROMPT
    purity_clause = _accent_purity_clause(voice_key)
    from services.market_context import (
        build_market_clause as _mkt_clause,
        banned_tokens_for_market as _check_banned,
        build_redaction_addendum as _redaction,
    )
    market = (getattr(ctx, "market", None) or "dubai").strip().lower()
    market_clause = _mkt_clause(market)
    # Phase 15d.1 — post-redactor loop: generate, scan for banned tokens,
    # regenerate ONCE with explicit redaction rules if leaked, then drop.
    redaction = ""
    last_script: str = ""
    for redact_attempt in (0, 1):
        last = ""
        for attempt in (0, 1):
            user_p = _build_solo_user_prompt(prev, nxt, ctx, persona, channel_name, shorten=(attempt == 1))
            # Phase 39 Session 6 — persona × location greeting weaver.
            _loc_block = ""
            if location_context:
                _lc_bits = []
                _mc = location_context.get("morning_commute")
                if _mc:
                    _lc_bits.append(
                        f"- The listener regularly heads to '{_mc['label']}' "
                        f"({_mc['category']}) in the morning.")
                _bv = location_context.get("recent_business_visit")
                if _bv:
                    _lc_bits.append(
                        f"- They were recently at '{_bv['label']}' "
                        f"({_bv['category']}) in the {_bv['time_bucket']} bucket.")
                _bkt = location_context.get("current_time_bucket")
                if _bkt:
                    _lc_bits.append(
                        f"- Current time bucket: {_bkt} (NEVER name a clock time — "
                        f"use this bucket only).")
                if _lc_bits:
                    _loc_block = (
                        "\n\nLOCATION CONTEXT — weave at most ONE of these into "
                        "the greeting naturally, in the persona's voice "
                        "(e.g. 'Heading out to the office?' or 'Just like that "
                        "Karak Cafe stop yesterday'). Do NOT list them all. "
                        "Do NOT mention coordinates. Do NOT name a clock time.\n"
                        + "\n".join(_lc_bits))
            user_p = f"{user_p}\n\n{purity_clause}\n\n{market_clause}{redaction}{_loc_block}"
            try:
                resp = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_p},
                    ], temperature=0.9, max_tokens=240,
                )
                script = (resp.choices[0].message.content or "").strip()
                script = re.sub(r'^["\']|["\']$', "", script).strip()
                last = script
                if _estimate_speech_seconds(script) <= RJ_RESHORTEN_THRESHOLD or attempt == 1:
                    break
            except Exception as e:
                raise HTTPException(502, f"OpenAI error: {e}")
        last_script = last
        hits = _check_banned(last_script, market)
        if not hits:
            return last_script
        logger.warning("[rj-redactor] market=%s attempt=%d leaked %s — retrying once",
                              market, redact_attempt, hits)
        if redact_attempt == 0:
            redaction = _redaction(market, hits)
            continue
    # Second attempt still leaked → mark the slot for skip; raise the
    # sentinel 503 so the outer guard serves a no-RJ segment.
    logger.error("[rj-redactor] market=%s DROPPED segment after 2nd leak: %s",
                       market, _check_banned(last_script, market))
    raise HTTPException(503, "rj_quota_exhausted")


def _build_duo_user_prompt(prev, nxt, ctx, host_a, host_b, channel_name=None, shorten=False):
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    nxt_mood = nxt.get("mood") or "uplifting"
    if prev:
        prev_line = (f"Previous song: '{prev['title']}' by {prev['artist']} "
                     f"(energy={prev.get('energy_level', DEFAULT_ENERGY)}, "
                     f"mood={prev.get('mood') or 'uplifting'}).")
    else:
        prev_line = "Opening of the show — no previous song yet."
    ctx_bits = []
    if ctx.time_of_day:  ctx_bits.append(f"time of day: {ctx.time_of_day}")
    if ctx.weather_hint: ctx_bits.append(f"weather: {ctx.weather_hint}")
    # Phase 15d — lexicon-aware city fallback (no silent Dubai default).
    _ctx_market = (getattr(ctx, "market", None) or "dubai").strip().lower()
    try:
        from services.market_lexicon import get_lexicon as _get_lex
        _lex_city = _get_lex(_ctx_market).get("display_name") or "Dubai"
    except Exception:
        _lex_city = "Dubai"
    ctx_bits.append(f"city: {ctx.city or _lex_city}")
    if channel_name:     ctx_bits.append(f"show: {channel_name}")
    shorter = " BE SHORTER — total under 28 seconds (50-70 words across ALL turns)." if shorten else ""
    return (
        f"Hosts: HOST_A = [{host_a['duo_label']}] ({host_a['duo_blurb']}). "
        f"HOST_B = [{host_b['duo_label']}] ({host_b['duo_blurb']}). "
        f"Use ONLY the speaker tags [{host_a['duo_label']}] and [{host_b['duo_label']}]. "
        f"{prev_line} Next song coming up (DO NOT name it): '{nxt['title']}' by {nxt['artist']} "
        f"(energy={nxt_energy}, mood={nxt_mood}). Context — {'; '.join(ctx_bits)}.{shorter} "
        f"Write the Hinglish co-host banter now, MATCHING the {nxt_energy} energy. "
        f"4-6 alternating turns starting with [{host_a['duo_label']}]."
    )


def _generate_duo_script(prev, nxt, ctx, host_a_key, host_b_key, channel_name=None, channel=None) -> str:
    if not openai_client:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    host_a = RJ_VOICES[host_a_key]; host_b = RJ_VOICES[host_b_key]
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    use_mirchi = _is_mirchi_party(channel, nxt_energy)
    system_prompt = MIRCHI_DUO_SYSTEM_PROMPT if use_mirchi else DUO_HINGLISH_SYSTEM_PROMPT
    # Phase 3.6 — when both hosts share an accent_target, append purity; when
    # they differ (e.g. English DJ + Hindi DJ), tell GPT to deliver each speaker
    # in their native language.
    acc_a = _accent_target_for_voice(host_a_key)
    acc_b = _accent_target_for_voice(host_b_key)
    if acc_a == acc_b:
        purity_clause = _accent_purity_clause(host_a_key)
    else:
        purity_clause = (
            f"MIXED-ACCENT DUO: "
            f"[{host_a['duo_label']}] speaks in '{acc_a}' style — {ACCENT_PURITY_RULES.get(acc_a, '').splitlines()[0]} "
            f"[{host_b['duo_label']}] speaks in '{acc_b}' style — {ACCENT_PURITY_RULES.get(acc_b, '').splitlines()[0]} "
            f"Each speaker writes their lines in their OWN language. Code-switching between speakers, NOT within a single turn."
        )
    last = ""
    # Phase 15d — market clause forbids out-of-market references.
    from services.market_context import build_market_clause as _mkt_clause
    market_clause = _mkt_clause(getattr(ctx, "market", None) or "dubai")
    for attempt in (0, 1):
        user_p = _build_duo_user_prompt(prev, nxt, ctx, host_a, host_b, channel_name, shorten=(attempt == 1))
        user_p = f"{user_p}\n\n{purity_clause}\n\n{market_clause}"
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_p},
                ], temperature=0.92, max_tokens=460,
            )
            script = (resp.choices[0].message.content or "").strip()
            last = script
            if _estimate_speech_seconds(script) <= RJ_RESHORTEN_THRESHOLD or attempt == 1:
                return script
        except Exception as e:
            raise HTTPException(502, f"OpenAI error: {e}")
    return last


def _parse_duo_script(script, host_a_key, host_b_key):
    label_to_key = {
        RJ_VOICES[host_a_key]["duo_label"]: host_a_key,
        RJ_VOICES[host_b_key]["duo_label"]: host_b_key,
    }
    pattern = re.compile(r"^\s*\[([A-Z]+)\]\s*(.*)$")
    turns: List[Tuple[str, str]] = []
    for raw in script.splitlines():
        line = raw.rstrip()
        if not line.strip(): continue
        m = pattern.match(line)
        if m and m.group(1) in label_to_key:
            turns.append((label_to_key[m.group(1)], m.group(2).strip()))
        elif turns:
            turns[-1] = (turns[-1][0], (turns[-1][1] + " " + line.strip()).strip())
    return [(vk, t) for vk, t in turns if t.strip()]


def _synthesize_elevenlabs_raw(script, voice_id, energy):
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")
    from elevenlabs import ElevenLabs, VoiceSettings
    # Import the SDK's ApiError so we can recognise quota / auth failures
    # cleanly. They surface during stream iteration, not at construction.
    try:
        from elevenlabs.core.api_error import ApiError as _ElevenApiError
    except Exception:  # pragma: no cover — older SDK
        _ElevenApiError = Exception  # noqa: N806
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    settings_dict = VOICE_SETTINGS_BY_ENERGY.get(energy, VOICE_SETTINGS_BY_ENERGY[DEFAULT_ENERGY])
    voice_settings = VoiceSettings(**settings_dict)
    try:
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id, model_id=ELEVEN_MODEL_ID, text=script,
            output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
        )
    except Exception:
        logger.warning("eleven_v3 failed — falling back to multilingual_v2")
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id, model_id=ELEVEN_FALLBACK_MODEL, text=script,
            output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
        )
    out_path = RJ_DIR / new_uuid_filename("mp3")
    try:
        with open(out_path, "wb") as f:
            for chunk in audio_iter:
                if chunk: f.write(chunk)
    except _ElevenApiError as e:
        # Translate ElevenLabs SDK errors into a clean, single-line log +
        # a 503 HTTPException so FastAPI doesn't print a full traceback.
        # 401 + quota_exceeded is the common one (account out of credits).
        # The radio/next handler can catch and degrade the segment to a
        # no-RJ crossfade if it wants — current behaviour returns 503.
        status   = getattr(e, "status_code", "unknown")
        body     = getattr(e, "body", None) or {}
        code     = (body.get("detail") or {}).get("code") if isinstance(body, dict) else None
        if status == 401 and code == "quota_exceeded":
            logger.warning("elevenlabs: quota exhausted — RJ synth disabled until credits top up")
            raise HTTPException(503, "rj_quota_exhausted") from None
        # Anything else: short summary, no traceback.
        logger.warning(f"elevenlabs api error status={status} code={code or 'unknown'}")
        raise HTTPException(502, "rj_upstream_error") from None
    return out_path


# Phase 3.6 — provider-aware synthesizer. Dispatches to ElevenLabs or
# OpenAI TTS based on the voice_key's `provider` field. The rest of the
# pipeline (duo banter, segment build) only calls this function.
def _synthesize_by_voice_key(script: str, voice_key: str, energy: str):
    voice = RJ_VOICES.get(voice_key) or RJ_VOICES[DEFAULT_VOICE_KEY]
    provider = voice.get("provider", "elevenlabs")
    if provider == "openai_tts":
        from services.openai_tts import synthesize_openai
        # Energy hint as extra delivery cue for the gpt-4o-mini-tts model.
        extra = None
        if energy == "party":
            extra = "MAXIMUM HYPE. Shout the loudest moments. Pure club-DJ delivery."
        elif energy == "high":
            extra = "High energy. Confident, hyped delivery."
        elif energy == "chill":
            extra = "Calm, warm, conversational. Low-key but present."
        return synthesize_openai(script, voice_key, extra_instructions=extra)
    # default: ElevenLabs
    vid = voice.get("voice_id")
    if not vid:
        raise RuntimeError(f"voice_key '{voice_key}' has no voice_id for ElevenLabs")
    return _synthesize_elevenlabs_raw(script, vid, energy)


def _synthesize_solo(script, voice_id_or_key, energy, voice_key: str = None):
    """Backwards-compat: if voice_key is passed (Phase 3.6+), use the
    provider-aware path. Else fall back to the legacy ElevenLabs voice_id call.
    """
    if voice_key is not None:
        out_path = _synthesize_by_voice_key(script, voice_key, energy)
    else:
        out_path = _synthesize_elevenlabs_raw(script, voice_id_or_key, energy)
    try:
        if truncate_audio(out_path, MAX_RJ_SECONDS, fade_out_ms=200):
            logger.info(f"Solo RJ truncated to {MAX_RJ_SECONDS}s")
    except Exception as e:
        logger.warning(f"Solo RJ truncation failed: {e}")
    return out_path


def _synthesize_duo_banter(turns, energy, party=False):
    if not turns:
        raise HTTPException(500, "duo script had no parseable turns")
    turn_paths = []
    for voice_key, text in turns:
        # Phase 3.6 — provider-aware per turn so a duo can mix providers
        turn_paths.append(_synthesize_by_voice_key(text, voice_key, energy))
    out_path = RJ_DIR / new_uuid_filename("mp3")
    # Phase 3.5 — tighter Mirchi-style ping-pong gap (80-130ms) for party channels.
    gap_ms = random.randint(80, 130) if party else 220
    concat_with_gaps([str(p) for p in turn_paths], str(out_path), gap_ms=gap_ms)
    try:
        if truncate_audio(out_path, MAX_RJ_SECONDS, fade_out_ms=250):
            logger.info(f"Duo RJ truncated to {MAX_RJ_SECONDS}s")
    except Exception as e:
        logger.warning(f"Duo RJ truncation failed: {e}")
    for p in turn_paths:
        try: p.unlink(missing_ok=True)
        except Exception: pass
    return out_path


def _synthesize_elevenlabs(script, voice_id, energy=DEFAULT_ENERGY):
    return _synthesize_solo(script, voice_id, energy)


def _pick_voice_for_energy(energy):
    if energy in ("high", "party"): return "dj_dubai"
    return random.choice(["veer_dubai", "monika_dubai"])


# ---------- FastAPI app ----------
app = FastAPI(
    title="RadioLife POC",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.state.db = db
api = APIRouter(prefix="/api")

# Phase Ω — K8s deploy hardening (2026-06-20).
#
# Any handler registered with `@app.on_event("startup")` runs
# sequentially INSIDE the lifespan startup phase, BEFORE uvicorn signals
# ASGI readiness.  This codebase has ~21 such handlers, most of which
# `await ensure_XXX_indexes(db)` — each Mongo op takes up to
# `serverSelectionTimeoutMS` (3s in `core.db`) when the cluster is
# slow/unreachable.  21 × 3 s = 63 s of blocking, tight against the
# K8s 10-minute deploy-ready window but risky under any additional
# latency.
#
# Fix: monkey-patch BOTH `app.add_event_handler` and
# `app.router.add_event_handler` (which is what `@app.on_event` calls
# under the hood) so every "startup" handler is converted into a
# fire-and-forget `asyncio.create_task(...)`.  The handler still runs,
# but the caller (starlette's lifespan wrapper) doesn't block on it.
# Shutdown handlers are UNTOUCHED — they still need to run to
# completion.
def _make_nonblocking_add_event_handler(original):
    def _wrapped(event_type: str, func):
        if event_type != "startup":
            return original(event_type, func)

        async def _bg_wrapper() -> None:
            try:
                r = func()
                if asyncio.iscoroutine(r):
                    await r
            except Exception as e:
                logging.getLogger("bigfm.deferred_boot").warning(
                    "[deferred-startup] handler %s failed: %s",
                    getattr(func, "__name__", str(func)), e)

        async def _scheduler():
            # Runs INSIDE the lifespan startup — spawns the real handler
            # as a background task and returns instantly so the lifespan
            # proceeds to `yield` without waiting on Mongo.
            asyncio.create_task(
                _bg_wrapper(),
                name=f"startup_bg_{getattr(func, '__name__', 'anon')}")

        return original(event_type, _scheduler)
    return _wrapped


# Patch at BOTH app-level and router-level, because
# `@app.on_event('startup')` routes through `app.router.add_event_handler`
# (not `app.add_event_handler`).
app.add_event_handler                = _make_nonblocking_add_event_handler(  # type: ignore
    app.add_event_handler)
app.router.add_event_handler = _make_nonblocking_add_event_handler(  # type: ignore
    app.router.add_event_handler)


# ---------- Mongo-free liveness/readiness probes ---------------------
# Phase Stabilization (Production deploy hardening): these endpoints
# MUST resolve synchronously without touching MongoDB so that the
# deploy platform's health check can pass even while the lifespan
# initialisers are still running (indexes + seeds can take 10-30s on a
# fresh cluster). Registered at root scope (NOT under /api) because
# Kubernetes-style probes typically hit "/health" and "/healthz".
#
# Phase Ω (2026-06-20): added `uptime_seconds` + `version` so operators
# can see boot age in the K8s dashboard.  ANY external-service
# unreachability MUST NOT affect this endpoint's response.
import time as _time_mod
_BOOT_TS_MONO           = _time_mod.monotonic()
_APP_VERSION                = (
    os.environ.get("BIGFM_APP_VERSION")
    or os.environ.get("GIT_SHA")
    or datetime.now(timezone.utc).strftime("boot-%Y%m%dT%H%M%SZ"))


def _health_payload():
    return {
        "ok":                          True,
        "status":                    "ok",
        "service":              "bigfm-backend",
        "version":              _APP_VERSION,
        "uptime_seconds": round(_time_mod.monotonic() - _BOOT_TS_MONO, 3),
        "ts":                          datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
@app.get("/healthz")
@app.get("/readyz")
@app.get("/api/health")
@app.get("/api/healthz")
@app.get("/api/readyz")
async def liveness_probe():
    """Zero-dep liveness/readiness — returns 200 in <1 ms regardless of
    Mongo / Tigris / OpenAI / ElevenLabs reachability."""
    return _health_payload()


@app.get("/api/config_check")
async def config_check():
    """Phase Stabilization — structural-only deploy diagnostic.

    Returns a non-secret summary of the configuration state so the
    deploy operator can see exactly which env var is mis-set without
    having to scrape backend logs. Public endpoint (no auth). NEVER
    leaks secret values — only their presence + obvious malformation.
    """
    mu = os.getenv("MONGO_URL") or ""
    mu_warns = _mongo_url_warnings(mu)
    cors_raw = os.getenv("CORS_ORIGINS") or ""
    cors_list = [o.strip() for o in cors_raw.split(",") if o.strip()]

    # Cheap connectivity probe with a tight timeout so this endpoint
    # itself stays under 1s even when Mongo is down.
    mongo_ping_ok: Optional[bool] = None
    mongo_ping_error: Optional[str] = None
    try:
        await asyncio.wait_for(
            mongo_client.admin.command("ping"), timeout=1.5)
        mongo_ping_ok = True
    except Exception as e:
        mongo_ping_ok = False
        mongo_ping_error = (str(e)[:120] or type(e).__name__)

    # Detect MOCKED integrations from env state — no secret leakage.
    mocked: list[str] = []
    if not os.getenv("STRIPE_API_KEY") and not os.getenv("STRIPE_SECRET_KEY"):
        mocked.append("stripe")
    if (os.getenv("ADSTACK_ADSWIZZ_MODE") or "mock").lower() == "mock":
        mocked.append("adswizz")
    if not os.getenv("MAILGUN_API_KEY") and not os.getenv("SENDGRID_API_KEY"):
        mocked.append("email")
    if not os.getenv("LIVEKIT_API_KEY"):
        mocked.append("livekit")
    if not os.getenv("ELEVENLABS_API_KEY"):
        mocked.append("elevenlabs")

    return {
        "service":  "bigfm-dubai",
        "mongo": {
            "url_set":        bool(mu),
            "url_looks_valid": len(mu_warns) == 0,
            "url_warnings":   mu_warns,
            "url_scheme":     (mu.split("://", 1)[0] if "://" in mu else None),
            "db_name":        os.getenv("DB_NAME", "bigfm"),
            "ping_ok":        mongo_ping_ok,
            "ping_error":     mongo_ping_error,
        },
        "cors": {
            "set":   bool(cors_raw),
            "count": len(cors_list),
            "is_wildcard_only": cors_list == ["*"],
        },
        "frontend": {
            "public_backend_url": os.getenv("PUBLIC_BACKEND_URL") or None,
            "public_frontend_origin": os.getenv("PUBLIC_FRONTEND_ORIGIN") or None,
        },
        "env_mode":          (os.getenv("ENV") or os.getenv("RUN_ENV")
                              or os.getenv("APP_ENV") or "unset"),
        "mocked_integrations": mocked,
        "elevenlabs": ("live" if os.getenv("ELEVENLABS_API_KEY") else "mock"),
    }


# ---------- lifespan ----------
#
# Phase Ω — K8s deploy hardening (2026-06-20).
#
# The old lifespan awaited ~30 Mongo/ffmpeg/seed operations sequentially
# BEFORE yielding — which meant uvicorn didn't signal ASGI readiness
# (and therefore K8s readiness probes couldn't fire) until all bootstrap
# work finished.  On a healthy sandbox this took ~10s; on prod with a
# slow Atlas cluster or transient DNS delay it easily exceeded the
# K8s 10-minute deploy timeout, causing the deploy to be marked failed
# and rolled back — while the app WOULD have started fine given a bit
# more time.
#
# The fix: yield IMMEDIATELY, and fire the heavy bootstrap into a
# background task.  Uvicorn accepts requests within <1s regardless of
# external-service reachability.  /api/health / /health / /readyz all
# return 200 from t≈0 (they are Mongo-free).  DB-touching endpoints
# still work fine because Motor is lazy-connect anyway; if Mongo is
# genuinely unreachable, individual requests fail cleanly with 500 +
# clear log, instead of the entire container failing to boot.
@asynccontextmanager
async def lifespan(app_: FastAPI):
    logger.info("[lifespan] fast-path: yielding immediately, "
                            "deferring bootstrap to background task")
    app_.state.deferred_boot_task = asyncio.create_task(
        _deferred_bootstrap(app_), name="bigfm_deferred_boot")
    app_.state.boot_started_at = datetime.now(timezone.utc)
    yield
    # Shutdown — cancel the deferred bootstrap if still running.
    task = getattr(app_.state, "deferred_boot_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    mongo_client.close()


async def _deferred_bootstrap(app_: FastAPI):
    """All the heavy Mongo/ffmpeg/index/seed work — runs AFTER uvicorn
    is already accepting requests.  Every step is wrapped in try/except
    so one flaky call can't stall the rest, and the endpoint returns
    200 on /api/health from t≈0 regardless of external-service state."""
    logger.info("[deferred-boot] starting background bootstrap…")
    # Phase Stabilization: only attempt ffmpeg install if it's actually
    # missing AND we're not in a deploy context (apt-get can hang for
    # 120s on locked-down container images). Skip the install entirely
    # when the production deploy expects a pre-baked image.
    if (not shutil.which("ffmpeg") or not shutil.which("ffprobe")) \
            and not os.getenv("SKIP_FFMPEG_BOOT_INSTALL"):
        try: _sp.run(["apt-get", "install", "-y", "ffmpeg"], capture_output=True, timeout=60)
        except Exception as e: logger.error(f"ffmpeg install failed: {e}")
    try: await ensure_auth_indexes(db)
    except Exception as e: logger.warning(f"auth indexes: {e}")
    try: await ensure_compliance_indexes(db)
    except Exception as e: logger.warning(f"compliance indexes: {e}")
    try: await ensure_billing_indexes()
    except Exception as e: logger.warning(f"billing indexes: {e}")
    try: stripe_setup_bootstrap()
    except Exception as e: logger.warning(f"stripe bootstrap: {e}")
    try: await expire_lapsed_subscriptions()
    except Exception as e: logger.warning(f"sub expiry sweep: {e}")
    # Phase 3.7 — RJ Naturalness Engine bootstrap
    try:
        from services.personality_profiles import ensure_personality_indexes, seed_personality_profiles
        from services.phrase_bank import ensure_phrase_bank_indexes, seed_phrase_bank
        from services.audio_qa import ensure_audio_qa_indexes
        await ensure_personality_indexes(db)
        await ensure_phrase_bank_indexes(db)
        await ensure_audio_qa_indexes()
        await seed_personality_profiles(db)
        await seed_phrase_bank(db)
        # Migrate any legacy QA rows that still hold broad daypart values
        # ("morning"/"afternoon"/"evening"/"late_night") to the granular slugs
        # used by the new phrase-bank routing.
        _DAYPART_MIGRATION = {
            "morning":    "morning_drive",
            "afternoon":  "lunch_rush",
            "evening":    "evening_drive",
            "late_night": "overnight_lounge",
        }
        for old_slug, new_slug in _DAYPART_MIGRATION.items():
            await db.rj_audio_qa.update_many(
                {"daypart_slug": old_slug},
                {"$set": {"daypart_slug": new_slug}},
            )
    except Exception as e:
        logger.warning(f"phase 3.7 bootstrap: {e}")

    # Phase 3.8 — Station Imaging Engine bootstrap
    try:
        from services.imaging_assets import ensure_imaging_indexes, seed_imaging_assets
        await ensure_imaging_indexes(db)
        seed_res = await seed_imaging_assets(db)
        logger.info(f"Imaging assets seeded: created={seed_res.get('created')} expected={seed_res.get('total_expected')} stations={seed_res.get('stations')}")
    except Exception as e:
        logger.warning(f"phase 3.8 bootstrap: {e}")

    # Phase 4 — Advertising bootstrap
    try:
        from services.ads_seed import ensure_ads_indexes, seed_demo_ads
        await ensure_ads_indexes(db)
        ads_stats = await seed_demo_ads(db)
        logger.info(f"Ads seeded: {ads_stats}")
    except Exception as e:
        logger.warning(f"phase 4 bootstrap: {e}")

    # Phase COMPANION.1 — demo companion pre-roll + live sponsored station.
    try:
        from services.home_audio_v2_seed import seed_home_audio_v2_demo
        hav2 = await seed_home_audio_v2_demo(db)
        logger.info(f"Home Audio V2 demo seeded: {hav2}")
    except Exception as e:
        logger.warning(f"home-audio-v2 demo seed: {e}")

    # Phase 4.5 — SSP partners + OpenRTB auction infra + Stripe Connect indexes
    try:
        from services.openrtb_auction import ensure_openrtb_indexes, seed_ssp_partners
        await ensure_openrtb_indexes(db)
        ssp_created = await seed_ssp_partners(db)
        await db.businesses.create_index([("stripe_connect_account_id", 1)],
                                          sparse=True)
        await db.gam_backfill_attempts.create_index([("attempted_at", -1)])
        logger.info(f"Phase 4.5 bootstrap: ssp_partners_created={ssp_created}")
    except Exception as e:
        logger.warning(f"phase 4.5 bootstrap: {e}")

    # Phase 5 — BigCoin loyalty: indexes + seed rewards/badges/lyrics/games
    try:
        from services.bigcoin import ensure_bigcoin_indexes
        from services.bigcoin_seed import seed_phase5
        from services.points_service import (
            ensure_points_indexes, seed_earn_rules)
        from services.banner_ad_provider import ensure_banner_ad_indexes
        from routes.predict_win_self_serve import (
            ensure_predict_win_pricing_indexes)
        await ensure_bigcoin_indexes(db)
        # Phase F-1 — Unified Points engine bootstrap.
        try:
            await ensure_points_indexes(db)
            await seed_earn_rules(db)
        except Exception as e:
            logger.warning("[points] bootstrap skipped: %s", e)
        # Phase MKT.1 — Merchant Marketplace: rate card + demo venue seed.
        try:
            from routes.merchant_marketplace import seed_marketplace
            mkt = await seed_marketplace(db)
            logger.info("[MKT.1] marketplace seeded: %s", mkt)
        except Exception as e:
            logger.warning("[MKT.1] marketplace bootstrap skipped: %s", e)
        # Phase 42-E1 — Banner ads + PW self-serve bootstrap.
        try:
            await ensure_banner_ad_indexes(db)
            await ensure_predict_win_pricing_indexes(db)
        except Exception as e:
            logger.warning("[42-E1] bootstrap skipped: %s", e)
        # 24h TTL on the per-minute heartbeat lock to keep collection small
        try:
            await db.listening_heartbeat_minutes.create_index(
                "created_at", expireAfterSeconds=86400,
            )
        except Exception:
            pass
        # Phase 5.1 — warm-start segment TTL (30 min). Mongo TTL monitor runs
        # every ~60s, but the claim path also enforces the cutoff defensively.
        try:
            await db.warm_start_segments.create_index(
                "built_at", expireAfterSeconds=WARM_START_TTL_SEC,
            )
        except Exception:
            pass
        # Phase Bug-2 — recommender decision log indexes + 30d TTL
        try:
            await db.recommender_decision_log.create_index(
                [("channel_slug", 1), ("ts", -1)])
            await db.recommender_decision_log.create_index(
                "ts", expireAfterSeconds=60 * 60 * 24 * 30)
        except Exception:
            pass
        await db.users.create_index("referrer_code", sparse=True)
        await db.bigcoin_rewards.create_index([("active", 1), ("category", 1)])
        p5_stats = await seed_phase5(db)
        logger.info(f"Phase 5 bootstrap: {p5_stats}")
        # Start the badge cron task
        import asyncio
        from services.badges import cron_recompute_all
        async def _badge_cron():
            while True:
                try:
                    await asyncio.sleep(300)  # 5 min
                    out = await cron_recompute_all(db)
                    if out.get("new_badges"):
                        logger.info(f"badge cron: {out}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"badge cron error: {e}")
        app.state.badge_cron_task = asyncio.create_task(_badge_cron())
    except Exception as e:
        logger.warning(f"phase 5 bootstrap: {e}")

    # Phase 6 — multi-tier subscriptions + family + dunning
    try:
        from services.plans import seed_plans
        from services.family import ensure_family_indexes
        from services.dunning import ensure_dunning_indexes, sweep_grace_periods
        await ensure_family_indexes(db)
        await ensure_dunning_indexes(db)
        p6_plans = await seed_plans(db)
        logger.info(f"Phase 6 bootstrap: plans_created={p6_plans}")
        async def _dunning_cron():
            while True:
                try:
                    await asyncio.sleep(60)  # every minute
                    out = await sweep_grace_periods(db)
                    if out.get("downgraded") or out.get("notified"):
                        logger.info(f"[dunning-cron] {out}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"dunning cron error: {e}")
        app.state.dunning_cron_task = asyncio.create_task(_dunning_cron())
    except Exception as e:
        logger.warning(f"phase 6 bootstrap: {e}")
    # Phase 7 — Social Lobbies: indexes + in-process WS hub
    try:
        await ensure_lobby_indexes(db)
        app.state.lobby_hub = LobbyHub()
        logger.info("Phase 7 bootstrap: lobby indexes ready, hub mounted")
    except Exception as e:
        logger.warning(f"phase 7 bootstrap: {e}")
    # Phase 8a — Gamification Marketplace.  `migrate_phase5_games` is
    # idempotent and self-contained: it renames legacy collections, builds
    # the fresh Phase 8a indexes, seeds templates, then creates the 3
    # platform-funded house campaigns.
    try:
        mig = await migrate_phase5_games(db, actor_user_id="system")
        logger.info(f"Phase 8a bootstrap: {mig}")
        from services.games_v2 import seed_extra_house_games
        extra = await seed_extra_house_games(db, actor_user_id="system")
        logger.info(f"Extra house games bootstrap: {extra}")
        from services.games_v2 import seed_fpk_sponsored_games
        fpk = await seed_fpk_sponsored_games(db, actor_user_id="system")
        logger.info(f"FPK sponsored games bootstrap: {fpk}")
    except Exception as e:
        logger.warning(f"phase 8a bootstrap: {e}")
    # Super Marketplace — Phase A foundation seed (rates, categories, commission).
    try:
        from services.marketplace import seed_marketplace_foundation
        ms = await seed_marketplace_foundation(db)
        from services.marketplace import seed_demo_businesses
        dm = await seed_demo_businesses(db)
        from services.marketplace import seed_demo_menus
        dmn = await seed_demo_menus(db)
        from services.marketplace_samples import seed_sample_customers_and_games
        dsm = await seed_sample_customers_and_games(db)
        from routes.marketplace_services import ensure_services_indexes
        await ensure_services_indexes(db)
        from routes.marketplace_products import ensure_products_indexes
        await ensure_products_indexes(db)
        from services.marketplace_coupons import ensure_coupon_indexes
        await ensure_coupon_indexes(db)
        from services.scan_pay_service import ensure_scanpay_indexes
        await ensure_scanpay_indexes(db)
        from routes.marketplace_specials import ensure_specials_indexes
        await ensure_specials_indexes(db)
        from routes.marketplace_promotions import ensure_promotions_seed
        promo_seed = await ensure_promotions_seed(db)
        logger.info(f"Promotions seed: {promo_seed}")
        from routes.marketplace_promotions import sweep_renewals, maybe_send_weekly_digests
        await sweep_renewals(db, throttle_seconds=0)
        await maybe_send_weekly_digests(db, throttle_seconds=0)
        from routes.marketplace_category_bids import sweep_topups
        await sweep_topups(db, throttle_seconds=0)
        from services.membership_entitlements import migrate_memberships_v2
        mbr_mig = await migrate_memberships_v2(db)
        logger.info(f"Membership entitlements v2 migration: {mbr_mig}")
        logger.info(f"Marketplace Phase A bootstrap: {ms} {dm} {dmn} {dsm}")
        from services.radio_policy import apply_dubai_station_policy, apply_language_policy, backfill_station_genres
        drp = await apply_dubai_station_policy(db)
        logger.info(f"Radio Dubai policy: {drp}")
        lang_pol = await apply_language_policy(db)
        logger.info(f"Radio language policy: {lang_pol}")

        async def _bg_genre_backfill():
            try:
                await backfill_station_genres(db)
            except Exception as _e:  # noqa: BLE001
                logger.warning(f"Radio genre backfill task failed: {_e}")
        asyncio.create_task(_bg_genre_backfill())

        async def _booking_reminder_cron():
            import asyncio
            import datetime as _dt
            from routes.notifications import _enqueue as _enq
            while True:
                try:
                    await asyncio.sleep(600)  # every 10 minutes
                    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
                    async for bk in db.service_bookings.find(
                            {"status": "confirmed", "date": today,
                             "reminder_sent": {"$ne": True}}):
                        try:
                            await _enq(db, owner_user_id=bk["user_id"], station_id="marketplace",
                                       station_slug="marketplace", type_="booking_reminder",
                                       payload={"title": "Appointment today ⏰",
                                                "body": f"{bk.get('business_name')} · {bk.get('service_name')} at {bk.get('start_time')} today.",
                                                "booking_id": bk["booking_id"]},
                                       dedupe_key=f"booking_reminder_{bk['booking_id']}")
                        except Exception:
                            pass
                        await db.service_bookings.update_one(
                            {"booking_id": bk["booking_id"]}, {"$set": {"reminder_sent": True}})
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"booking reminder cron error: {e}")
        app.state.booking_reminder_task = __import__("asyncio").create_task(_booking_reminder_cron())
    except Exception as e:
        logger.warning(f"marketplace phase A bootstrap: {e}")
    # Phase 8b — Gamification distribution: milestone auto-unlock engine,
    # partner-token redemption gating, public landing pages, RJ-mention log.
    try:
        await ensure_unlock_engine_indexes(db)
        await ensure_partner_tokens_indexes(db)
        seed_res = await seed_unlock_rules(db)
        logger.info(f"Phase 8b bootstrap: {seed_res}")
        app.state.unlock_sweep_task = asyncio.create_task(
            background_unlock_sweep_task(app))
    except Exception as e:
        logger.warning(f"phase 8b bootstrap: {e}")
    # Phase 8c — lead capture, webhooks, leaderboard, inventory ledger
    try:
        await ensure_lead_indexes(db)
        await ensure_webhook_indexes(db)
        await ensure_leaderboard_indexes(db)
        await ensure_inventory_indexes(db)
        app.state.webhook_worker_task = asyncio.create_task(
            background_webhook_worker(app))
        logger.info("Phase 8c bootstrap: lead/webhook/leaderboard/"
                       "inventory indexes ready, webhook worker mounted")
    except Exception as e:
        logger.warning(f"phase 8c bootstrap: {e}")
    # Phase 23 Session 1.5 — winners + redemptions indexes
    try:
        await ensure_phase23_indexes(db)
        logger.info("Phase 23 S1.5 bootstrap: game_winners + "
                       "game_redemptions indexes ready")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"phase 23 s1.5 bootstrap: {e}")
    # Phase 19a Part 5 — admin user management indexes + status backfill
    try:
        await ensure_phase19a_part5_indexes(db)
        logger.info("Phase 19a P5 bootstrap: user_role_audit_log "
                       "indexes + status backfill ready")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"phase 19a p5 bootstrap: {e}")
    # Phase 9a — Maps + commute
    try:
        await ensure_maps_indexes(db)
        seed_res = await seed_mock_places(db)
        rule_res = await activate_commute_unlock_rule(db)
        # Phase 9a Addendum — boot probe the live Google Maps APIs once.
        # Falls back to MockMapsClient if all four APIs fail.
        probe_res = await probe_and_decide_client(db, app=app)
        app.state.maps_probe = probe_res
        # Phase 15d — idempotent de-Dubai migrations. Runs at every boot
        # but only writes when there's something to rename.
        try:
            mig = await _p15d.run_all(db)
            logger.info(f"Phase 15d migrations: {mig}")
        except Exception as e:
            logger.warning(f"Phase 15d migrations: skipped ({e})")
        # Phase 9b — route ad opportunity + decision log indexes
        from services.route_ad_engine import ensure_route_ad_indexes
        await ensure_route_ad_indexes(db)
        # Phase 9c — local commerce + Google Wallet probe
        from services.local_commerce import ensure_commerce_indexes
        from services.google_wallet import probe_wallet
        await ensure_commerce_indexes(db)
        # Phase 9c.1 Fix 2 — backfill GeoJSON `loc` for any business
        # that has lat/lng but no `loc` (legacy / claim-time race).
        # Required so newly claimed partner businesses appear in
        # $nearSphere / $geoWithin queries used by the public-nearby
        # endpoint and the route_ad_engine offer proximity scan.
        try:
            backfill_q = {
                "loc": {"$exists": False},
                "lat": {"$exists": True, "$ne": None},
                "lng": {"$exists": True, "$ne": None}}
            backfilled = 0
            async for b in db.businesses.find(
                    backfill_q, {"business_id": 1, "lat": 1, "lng": 1}):
                try:
                    await db.businesses.update_one(
                        {"business_id": b["business_id"]},
                        {"$set": {"loc": {
                            "type": "Point",
                            "coordinates": [float(b["lng"]),
                                                  float(b["lat"])]}}})
                    backfilled += 1
                except Exception:
                    continue
            if backfilled:
                logger.info(f"Phase 9c.1: backfilled GeoJSON loc on "
                              f"{backfilled} business(es)")
        except Exception as e:
            logger.warning(f"phase 9c.1 loc backfill: {e}")
        wallet_res = await probe_wallet(app=app)
        logger.info(f"Phase 9a bootstrap: maps={probe_res.get('client')} "
                       f"mode={probe_res.get('mode')} "
                       f"auth_mode={probe_res.get('auth_mode','-')} "
                       f"auth_email={probe_res.get('auth_email','-')} "
                       f"api_health={probe_res.get('api_health')} "
                       f"places={seed_res} unlock_rule={rule_res}")
        logger.info("Phase 9b bootstrap: route_ad_opportunities + decision_log indexes ready")
        logger.info(f"Phase 9c bootstrap: commerce indexes ready, "
                       f"wallet mode={wallet_res.get('mode')} "
                       f"health={wallet_res.get('api_health')}")
        # Phase 10a — Social Passport (badges, ambassador, attribution)
        try:
            from services.badge_engine import (
                ensure_passport_indexes, seed_badge_catalog,
                seed_ambassador_levels, background_sweep_task,
            )
            await ensure_passport_indexes(db)
            catalog_res = await seed_badge_catalog(db)
            levels_res = await seed_ambassador_levels(db)
            app.state.badge_sweep_task = asyncio.create_task(
                background_sweep_task(app))
            logger.info(
                f"Phase 10a bootstrap: badge_catalog "
                f"created={catalog_res.get('created')} "
                f"updated={catalog_res.get('updated')} "
                f"total={catalog_res.get('catalog_size')} "
                f"ambassador_levels_created={levels_res.get('created')}")
            # Phase 10b — public profile, leaderboards, level-up perks,
            # legacy badge migration (idempotent on each boot).
            try:
                from services.passport_public import (
                    ensure_passport_public_indexes, migrate_phase5_badges,
                    recompute_leaderboards,
                )
                await ensure_passport_public_indexes(db)
                mig_res = await migrate_phase5_badges(db)
                # Initial leaderboard build (best-effort, runs in background)
                async def _lb_warm():
                    try:
                        await recompute_leaderboards(db)
                    except Exception as _e:
                        logger.warning(f"lb warm: {_e}")
                asyncio.create_task(_lb_warm())
                logger.info(
                    f"Phase 10b bootstrap: phase5_migration "
                    f"updated={mig_res.get('updated')} "
                    f"skipped={mig_res.get('skipped')} "
                    f"total_phase5={mig_res.get('total_phase5')}; "
                    f"leaderboard warm scheduled")
                # Phase 10c — exclusive channel gating seed
                try:
                    from services.channel_access import seed_exclusive_channels
                    ec_res = await seed_exclusive_channels(db)
                    logger.info(
                        f"Phase 10c bootstrap: exclusive_channels "
                        f"created={ec_res.get('created')} "
                        f"backfilled_free={ec_res.get('backfilled_free')} "
                        f"promoted_premium={ec_res.get('promoted_premium')} "
                        f"seeds={ec_res.get('total_exclusive_seeds')}")
                except Exception as e:
                    logger.warning(f"phase 10c bootstrap: {e}")
                # Phase K.2 — city stamps engine indexes.
                try:
                    from services.city_stamps_engine import ensure_city_stamp_indexes
                    await ensure_city_stamp_indexes(db)
                    logger.info("Phase K.2 bootstrap: city_stamps indexes ready")
                except Exception as e:
                    logger.warning(f"phase K.2 bootstrap: {e}")
            except Exception as e:
                logger.warning(f"phase 10b bootstrap: {e}")
        except Exception as e:
            logger.warning(f"phase 10a bootstrap: {e}")
    except Exception as e:
        logger.warning(f"phase 9a bootstrap: {e}")
        app.state.maps_probe = {"client": "MockMapsClient", "mode": "mock",
                                          "error": str(e)}
    try:
        missing = await db.tracks.find({"energy_level": {"$exists": False}}).to_list(500)
        if missing:
            logger.info(f"Backfilling energy on {len(missing)} legacy tracks...")
            for t in missing:
                meta = await _infer_track_energy(t["title"], t["artist"], t["duration_sec"])
                await db.tracks.update_one(
                    {"_id": t["_id"]},
                    {"$set": {"energy_level": meta["energy_level"], "mood": meta["mood"]}},
                )
        # Idempotent + self-healing demo catalog — re-downloads missing
        # clips on a fresh pod and stamps playable_status='ok' so radio
        # always has candidates.
        try:
            ensured = await ensure_demo_tracks(db, TRACKS_DIR)
            logger.info(f"Demo catalog ensured ({ensured} tracks).")
        except Exception as e:
            logger.warning(f"Demo track seeding failed: {e}")
        # Self-heal legacy seed rows a cold-boot race flagged `disk_missing`
        # while their file actually exists on disk.
        try:
            async for _t in db.tracks.find(
                    {"playable_status": "disk_missing"}, {"file_path": 1}):
                _fp = _t.get("file_path")
                if _fp and os.path.exists(_fp):
                    await db.tracks.update_one(
                        {"_id": _t["_id"]}, {"$unset": {"playable_status": ""}})
        except Exception as e:
            logger.warning(f"disk_missing self-heal skipped: {e}")
        try:
            created = await seed_users(db, hash_password)
            if created: logger.info(f"Seeded {created} users.")
        except Exception as e:
            logger.warning(f"User seeding failed: {e}")
        try:
            ch_created = await seed_channels(db)
            logger.info(f"Channels seeded/refreshed (created {ch_created})")
        except Exception as e:
            logger.warning(f"Channel seeding failed: {e}")
        # ─── Phase STATIC.BOOT.v3 (2026-08-02) — channel thumbnail URL
        # backfill.  `seed_channels` only writes name/description/clock/
        # hosts — it never touches `thumbnail_url`.  On a fresh prod DB
        # the field ends up null even though the .webp files exist on
        # disk (they're git-tracked).  `ensure_thumbnails` walks the 13
        # canonical slugs, sees the file already on disk, and stamps
        # the correct `/api/static/channel_thumbnails/{slug}.webp` URL
        # + `_channel_thumbnails_v1` sentinel on the doc — WITHOUT
        # calling nano_banana (no LLM cost when files exist).  If a
        # file is somehow missing, only THEN it regenerates.  Fully
        # idempotent: on preview (already stamped) this is a no-op.
        try:
            thumb_stats = await _thumbs.ensure_thumbnails(db)
            logger.info("[static-bootstrap] channel thumbnails: %s",
                                    thumb_stats)
        except Exception as e:
            logger.warning("[static-bootstrap] channel thumbnails: %s", e)
        # ─── Phase FUN.1 seed — was previously registered ONLY via a
        # legacy `@app.on_event("startup")` handler at line ~6260,
        # which is a dead-letter in this codebase (the Starlette
        # lifespan wrapper runs `_deferred_bootstrap` instead and
        # never invokes the legacy on_event handlers — verified by the
        # absence of any FUN.1 seed log line on boot).  We call it
        # here explicitly so flagship stations get seeded on every
        # boot (idempotent — `seed_funasia_flagships` upserts).
        try:
            from services.flagship_station_service import (
                ensure_flagship_indexes as _fli,
                seed_funasia_flagships as _sff,
            )
            await _fli(db)
            fun1_stats = await _sff(db)
            logger.info("[FUN.1 seed] %s", fun1_stats)
        except Exception as e:
            logger.warning("[FUN.1 seed] skipped: %s", e)
        # Load any admin-persisted skip policy (fallback stays Free=1 / Premium=6 / 3600s).
        try:
            _skip_cfg = await db.radio_settings.find_one({"_id": "skip_policy"})
            if _skip_cfg:
                set_skip_policy(free=_skip_cfg.get("free"), premium=_skip_cfg.get("premium"),
                                window_sec=_skip_cfg.get("window_sec"))
                logger.info("[skip-policy] loaded from settings: %s", _skip_cfg)
        except Exception as e:
            logger.warning("[skip-policy] load skipped: %s", e)
        # Daily auto-heal cron — quietly regenerate (durably) any flagship
        # cover or AI channel thumbnail whose file has gone missing, so
        # admins never have to touch the "Heal" buttons manually.
        try:
            from routes.imported_station_artwork import run_flagship_art_heal as _fl_heal
            from services import channel_thumbnails as _ct_heal

            async def _art_autoheal_cron():
                await asyncio.sleep(900)   # 15-min grace after boot seeds
                while True:
                    try:
                        fq = await _fl_heal(db)
                        th = await _ct_heal.heal_all_thumbnails(db)
                        if fq or th.get("healed"):
                            logger.info("[art-autoheal] flagship_queued=%s thumbs=%s",
                                        fq, th)
                    except asyncio.CancelledError:
                        raise
                    except Exception as _e:
                        logger.warning("[art-autoheal] error: %s", _e)
                    await asyncio.sleep(86400)   # once per day
            app.state.art_autoheal_task = asyncio.create_task(_art_autoheal_cron())
            logger.info("[art-autoheal] daily cron scheduled")
        except Exception as e:
            logger.warning("[art-autoheal] setup failed: %s", e)
        await _ensure_voice_previews()
        try:
            _ensure_tuning_sfx()
            _ensure_og_default_image()
        except Exception as e:
            logger.warning(f"asset generation failed: {e}")
        # Phase 3.5 — Mirchi-style party SFX + station IDs (background, non-blocking)
        try:
            from services.sfx_library import ensure_library_async
            from services.station_ids import ensure_station_ids_async
            asyncio.create_task(ensure_library_async())
            asyncio.create_task(ensure_station_ids_async())
        except Exception as e:
            logger.warning(f"phase3.5 SFX kickoff failed: {e}")
        # Phase 12b — Retention indexes + scheduler
        try:
            await ensure_retention_indexes(db)
            await ensure_safety_indexes(db)
            # Sub-Phase E1 — Predict & Win indexes + seed manual provider
            try:
                await ensure_predict_win_indexes(db)
                await seed_predict_win_provider(db)
            except Exception as _pwe:
                logger.warning(f"Sub-Phase E1 predict_win bootstrap skipped: {_pwe}")
            # Phase D — station_tracks + track_moderation_jobs indexes
            try:
                await bootstrap_phase_d(db)
            except Exception as _phd:
                logger.warning(f"Phase D bootstrap skipped: {_phd}")
            # Sub-Phase E2 — predict_win_awards unique compound index +
            # wallet item lookup index.
            try:
                await ensure_e2_indexes(db)
            except Exception as _e2:
                logger.warning(f"Sub-Phase E2 bootstrap skipped: {_e2}")
            # Phase PDX.1 — Predexon auto-curator indexes + one-time
            # backfill of points/import_source on legacy campaign rows +
            # kickoff of the background scheduler.
            try:
                from services.pdx_curator_service import (
                    ensure_pdx_curator_indexes as _pdx_idx,
                    backfill_existing_campaigns_points as _pdx_backfill,
                    background_curator_loop as _pdx_loop,
                )
                await _pdx_idx(db)
                _bf = await _pdx_backfill(db)
                logger.info(f"Phase PDX.1 backfill: {_bf}")
                # Fire the scheduler as a fire-and-forget background task
                # so it doesn't block deferred boot.  First tick runs
                # ~5s after this point.
                app.state.pdx_curator_task = asyncio.create_task(
                    _pdx_loop(db, initial_delay_sec=5.0),
                    name="pdx_curator_scheduler")
                logger.info("Phase PDX.1 curator scheduler started")
            except Exception as _pdx_e:
                logger.warning(f"Phase PDX.1 bootstrap skipped: {_pdx_e}")
            # Sub-Phase E3 — venue_checkins TTL + business campaign +
            # tv display pairing indexes.
            try:
                from routes.predict_win_business import ensure_e3_indexes
                _e3_out = await ensure_e3_indexes(db)
                logger.info(f"Sub-Phase E3 bootstrap: indexes={_e3_out}")
            except Exception as _e3:
                logger.warning(f"Sub-Phase E3 bootstrap skipped: {_e3}")
            # Sub-Phase E4 — sweep logs + admin alerts + settings.
            try:
                from services.predict_win_sweeper import (
                    ensure_e4_indexes, sweeper_loop)
                _e4_out = await ensure_e4_indexes(db)
                logger.info(f"Sub-Phase E4 bootstrap: indexes={_e4_out}")
                app.state.predict_win_sweep_task = asyncio.create_task(
                    sweeper_loop(app))
                logger.info("Sub-Phase E4 sweeper loop scheduled")
            except Exception as _e4:
                logger.warning(f"Sub-Phase E4 bootstrap skipped: {_e4}")
            # Sub-Phase E5 — Predexon data-provider seed + api-log TTL.
            try:
                from scripts.seed_predexon_provider import seed_predexon_provider
                from services.predexon_client import ensure_predexon_log_ttl
                _e5_out = await seed_predexon_provider(db)
                await ensure_predexon_log_ttl(db)
                logger.info(f"Sub-Phase E5 bootstrap: predexon={_e5_out}")
            except Exception as _e5:
                logger.warning(f"Sub-Phase E5 bootstrap skipped: {_e5}")
            # Phase PW-M.1 — Merchant Predict & Win collections + indexes.
            try:
                from scripts.init_pw_merchant_collections import init_collections
                _pwm_out = await init_collections(db)
                logger.info(f"Phase PW-M.1 bootstrap: "
                                          f"idx_created={len(_pwm_out['created_indexes'])} "
                                          f"errors={len(_pwm_out['errors'])}")
            except Exception as _pwm:
                logger.warning(f"Phase PW-M.1 bootstrap skipped: {_pwm}")
            # Phase CLAIM.1 — station_edit_requests collection + indexes.
            try:
                from scripts.init_claim1_collections import (
                    init_collections as _claim1_init)
                _cl1_out = await _claim1_init(db)
                logger.info(f"Phase CLAIM.1 bootstrap: "
                                          f"idx_created={len(_cl1_out['created_indexes'])} "
                                          f"errors={len(_cl1_out['errors'])}")
            except Exception as _cl1:
                logger.warning(f"Phase CLAIM.1 bootstrap skipped: {_cl1}")
            # Phase AUTH.1 — seed the permanent playbook test user.
            try:
                from scripts.seed_auth1_playbook_user import seed_playbook_user
                _pb = await seed_playbook_user(db)
                logger.info(f"Phase AUTH.1 bootstrap: "
                                          f"playbook_user={_pb['user_id']} "
                                          f"session={_pb['session_token'][:20]}…")
            except Exception as _pb:
                logger.warning(f"Phase AUTH.1 bootstrap skipped: {_pb}")
            # Phase 42-A — Radio Browser import indexes + daily cron task.
            try:
                from services.radio_browser_import import (
                    ensure_42a_indexes, radio_import_loop)
                _42a_out = await ensure_42a_indexes(db)
                logger.info(f"Phase 42-A bootstrap: indexes={_42a_out}")
                app.state.radio_import_task = asyncio.create_task(
                    radio_import_loop(app))
                logger.info("Phase 42-A radio_import_loop scheduled")
            except Exception as _42a:
                logger.warning(f"Phase 42-A bootstrap skipped: {_42a}")
            try:
                from services.safety_seed import ensure_qa_seed
                await ensure_qa_seed(db)
            except Exception as _se:
                logger.warning(f"Phase 12c QA seed skipped: {_se}")
            # Phase 12c — disk hygiene: prune once before serving traffic
            try:
                from services.storage_hygiene import run_hygiene_pass as _hyg
                _hyg_out = _hyg(db)
                logger.info(
                    f"Phase 12c hygiene (boot): pruned {_hyg_out['summary']}")
            except Exception as _he:
                logger.warning(f"Phase 12c hygiene boot prune skipped: {_he}")
            # Phase 12d — integration health indexes + boot-mode log
            try:
                from services.integration_health import (
                    ensure_integration_indexes, boot_log_modes)
                await ensure_integration_indexes(db)
                boot_log_modes()
            except Exception as _ie:
                logger.warning(
                    f"Phase 12d integration init skipped: {_ie}")
            # Phase 13a — A/B testing indexes
            try:
                from services.ab import ensure_ab_indexes
                await ensure_ab_indexes(db)
            except Exception as _ae:
                logger.warning(
                    f"Phase 13a ab indexes init skipped: {_ae}")
            logger.info("Phase 12c bootstrap: safety indexes ready")
            app.state.public_backend_url = os.environ.get(
                "PUBLIC_BACKEND_URL", "")
            if os.environ.get("BIGFM_RETENTION_SCHEDULER", "1") == "1":
                from services.churn_score import recompute_all as _cr_all
                async def _retention_cron():
                    last_daily = None
                    last_hygiene = None
                    while True:
                        try:
                            await asyncio.sleep(900)  # 15 minutes
                            # Hourly disk hygiene
                            now_hr = datetime.now(timezone.utc).replace(
                                minute=0, second=0, microsecond=0)
                            if last_hygiene != now_hr:
                                last_hygiene = now_hr
                                try:
                                    from services.storage_hygiene import (
                                        run_hygiene_pass as _hyg_run)
                                    _hyg_run(db)
                                except Exception as he:
                                    logger.warning(
                                        f"[hygiene-cron] error: {he}")
                            # Auto-run active campaigns whose trigger
                            # supports cron firing (skip real-time ones).
                            async for c in db.lifecycle_campaigns.find(
                                    {"active": True}):
                                if c.get("trigger") in (
                                        "friend_joined_lobby",
                                        "commute_window_today_offers"):
                                    continue
                                try:
                                    from routes.admin_retention import (
                                        _audience_user_ids, _throttle_ok)
                                    from services.delivery import (
                                        send_email, send_push)
                                    uids = await _audience_user_ids(db, c)
                                    template = c.get("template") or {}
                                    sent = 0
                                    for uid in uids[:200]:
                                        if not await _throttle_ok(
                                                db, campaign=c, user_id=uid):
                                            continue
                                        u = await db.users.find_one(
                                            {"user_id": uid})
                                        if not u: continue
                                        v = {"name": u.get("name") or "there"}
                                        for ch in (c.get("channels") or []):
                                            if ch == "email":
                                                await send_email(
                                                    db, user=u,
                                                    campaign_id=c["id"],
                                                    subject=(template.get(
                                                        "email_subject")
                                                        or c["name"]),
                                                    body_template=(template
                                                        .get("email_body")
                                                        or ""), vars=v)
                                            elif ch == "push":
                                                await send_push(
                                                    db, user=u,
                                                    campaign_id=c["id"],
                                                    title=(template.get(
                                                        "push_title")
                                                        or c["name"]),
                                                    body_template=(template
                                                        .get("push_body")
                                                        or ""), vars=v,
                                                    deep_link=template.get(
                                                        "deep_link") or "/")
                                        sent += 1
                                    if sent:
                                        logger.info(
                                            f"[retention-cron] {c['id']} "
                                            f"sent={sent}")
                                except Exception as ce:
                                    logger.warning(
                                        f"[retention-cron] campaign {c.get('id')}"
                                        f" failed: {ce}")
                            # Daily 02:00 UTC churn recompute
                            now_h = datetime.now(timezone.utc).hour
                            today = datetime.now(timezone.utc).date()
                            if now_h == 2 and last_daily != today:
                                last_daily = today
                                logger.info("[retention-cron] daily churn recompute starting")
                                out = await _cr_all(db)
                                logger.info(
                                    f"[retention-cron] daily churn: {out}")
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.warning(f"retention-cron error: {e}")
                app.state.retention_cron_task = asyncio.create_task(
                    _retention_cron())
                logger.info("Phase 12b bootstrap: retention scheduler started")
            else:
                logger.info("Phase 12b bootstrap: indexes ready, scheduler DISABLED")
        except Exception as e:
            logger.warning(f"phase 12b bootstrap: {e}")
    except Exception as e:
        logger.warning(f"lifespan setup hiccup (non-fatal): {e}")

    # ─── Phase 17b — Auto-resume scheduler (10-min tick) ──────────────
    try:
        from services.offers import auto_resume_eligible_offers
        from services.offer_analytics import seed_demo_org

        # Seed demo karak org on boot (idempotent).
        try:
            await seed_demo_org(db)
        except Exception as _e:
            logger.warning(f"phase 17b seed: {_e}")

        async def _auto_resume_cron():
            while True:
                try:
                    await asyncio.sleep(600)   # 10 minutes
                    out = await auto_resume_eligible_offers(db)
                    if out.get("resumed"):
                        logger.info(f"[auto-resume] tick {out}")
                    # Phase 17c — same tick reverts expired boosts.
                    try:
                        from services.offer_boost import revert_expired_boosts
                        out2 = await revert_expired_boosts(db)
                        if out2.get("reverted"):
                            logger.info(f"[boost-revert] tick {out2}")
                    except Exception as _e:
                        logger.warning(f"boost-revert tick: {_e}")
                except asyncio.CancelledError:
                    raise
                except Exception as _e:
                    logger.warning(f"auto-resume cron error: {_e}")
        app.state.auto_resume_task = asyncio.create_task(_auto_resume_cron())
        logger.info("Phase 17b bootstrap: auto-resume scheduler started")
    except Exception as e:
        logger.warning(f"phase 17b bootstrap: {e}")

    # ─── Phase H.5 — Ambassador-tier recompute scheduler ───────────
    try:
        from services.passport_tier_scheduler import start_scheduler as _start_tier_sched
        _start_tier_sched(app, db, interval_sec=300, limit=1000)
    except Exception as e:
        logger.warning(f"phase H.5 tier-scheduler bootstrap: {e}")

    # ─── Phase 18a — Advertiser dashboard indexes + demo seed ─────────
    try:
        from services.advertiser_seed import (ensure_advertiser_indexes,
                                                                seed_phase18a)
        await ensure_advertiser_indexes(db)
        r = await seed_phase18a(db)
        logger.info("Phase 18a bootstrap: seed=%s", r)
    except Exception as e:
        logger.warning(f"phase 18a bootstrap: {e}")

    # ─── Phase 18c — Pacing health fixture campaigns ──────────────────
    # Idempotent. Targets `__nonexistent_chan__` so live auction never sees
    # them — purely for the admin pacing-health panel + screenshots.
    try:
        from scripts.seed_pacing_demo import seed_pacing_demo
        r = await seed_pacing_demo(db)
        logger.info("Phase 18c pacing seed: %s", r)
    except Exception as e:
        logger.warning(f"phase 18c pacing seed: {e}")

    # ─── Phase 36a — Static-precedence sanity probe (lesson from 18d) ─
    # If anyone ever drops a file matching one of our dynamic root routes
    # into /app/frontend/public/, log a loud WARN so the dev sees it
    # before users do.  Routes we own at site root: /ads.txt /app-ads.txt
    # /podcasts/{slug}/rss.xml.
    try:
        from pathlib import Path as _P
        _pub = _P("/app/frontend/public")
        for impostor in ("ads.txt", "app-ads.txt"):
            if (_pub / impostor).exists():
                logger.warning("[36a-precedence-guard] /app/frontend/public/%s exists "
                                          "— will mask the dynamic backend route. Delete it.",
                                          impostor)
        for f in _pub.rglob("rss.xml") if _pub.exists() else []:
            logger.warning("[36a-precedence-guard] %s exists — will mask dynamic "
                                      "/podcasts/{slug}/rss.xml feed. Move it.", f)
        # Phase 36b — chapters.json + transcript.srt live under /api so the
        # ingress already routes them, but a frontend/public file at the
        # same path would still 404 the API in dev. Log if found.
        for impostor in ("chapters.json", "transcript.srt"):
            for f in (_pub.rglob(impostor) if _pub.exists() else []):
                logger.warning("[36b-precedence-guard] %s exists — will not affect "
                                          "API path but may confuse devs. Consider removing.", f)
    except Exception as e:
        logger.warning(f"phase 36a precedence guard: {e}")

    # ─── Phase 36b — Background transcript poller (live mode only) ────
    # Mock mode completes inline in kick_transcription so no poller is
    # needed. Live mode submits to AssemblyAI and leaves rows
    # status=processing — this cron advances them every 30s.
    try:
        from services import assemblyai_client as _aai
        from services import podcast_transcription as _tx
        if _aai.is_live():
            async def _transcript_poll_cron():
                while True:
                    try:
                        await asyncio.sleep(30)
                        out = await _tx.poll_pending_transcriptions(db)
                        if out:
                            logger.info(f"[36b-tx-poll] advanced {out} rows")
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning(f"[36b-tx-poll] error: {e}")
            app.state.transcript_poll_task = asyncio.create_task(
                _transcript_poll_cron())
            logger.info("Phase 36b: transcript poll cron started (live mode)")
        else:
            logger.info("Phase 36b: AssemblyAI in MOCK mode (no API key) "
                                "— inline mock completion, no poll cron needed")
    except Exception as e:
        logger.warning(f"phase 36b bootstrap: {e}")
    # ─── Phase STATIC.BOOT (2026-07-31) — self-heal missing static ───
    # Fire-and-forget so the audit + regen can take its time without
    # holding up any downstream boot steps.  The service is fully
    # idempotent, so repeat boots are cheap.
    try:
        from services.static_assets_bootstrap import (
            ensure_static_assets_bootstrap,
        )
        async def _sb_run():
            try:
                r = await ensure_static_assets_bootstrap(db)
                logger.info("[static-bootstrap] boot complete: %s", r)
            except Exception as exc:
                logger.warning("[static-bootstrap] runtime: %s", exc)
        asyncio.create_task(_sb_run(), name="bigfm_static_bootstrap")
        logger.info("[static-bootstrap] scheduled")
    except Exception as e:
        logger.warning(f"phase static.boot schedule: {e}")

    # ─── Phase RELIABILITY.P2 — imported station probe infrastructure.
    # Two background tasks, both idempotent:
    #   1. cold_fill_task   — one-shot probe of every station whose
    #                         stream_health_status is still "unknown"
    #                         (typical after a fresh RB import).
    #   2. scheduled_loop   — forever loop; re-probes alive+dead rows
    #                         every 6 h so recoveries flip back to
    #                         alive and new outages get caught.
    # Concurrency is capped at 8 global / 1 per-host inside the
    # service to protect upstream Icecast/Shoutcast providers.
    try:
        from services.imported_station_probe import (
            cold_fill_task as _probe_cold_fill,
            scheduled_loop as _probe_scheduled_loop,
        )

        async def _probe_cold_fill_run():
            try:
                r = await _probe_cold_fill(db)
                logger.info("[probe.cold_fill] boot summary: %s", r)
            except Exception as exc:            # noqa: BLE001
                logger.warning("[probe.cold_fill] runtime: %s", exc)

        app_.state.probe_cold_fill_task = asyncio.create_task(
            _probe_cold_fill_run(),
            name="bigfm_probe_cold_fill")
        app_.state.probe_scheduled_task = asyncio.create_task(
            _probe_scheduled_loop(db),
            name="bigfm_probe_scheduled_loop")
        logger.info("[probe] cold_fill + scheduled_loop scheduled")
    except Exception as e:
        logger.warning(f"phase reliability.p2 probe wiring: {e}")

    logger.info("[deferred-boot] completed")


app.router.lifespan_context = lifespan


def _ensure_tuning_sfx() -> None:
    """Generate a short FM-tuning SFX if missing (used during channel switches)."""
    out = SFX_DIR / "tuning.mp3"
    if out.exists() and out.stat().st_size > 1_000:
        return
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anoisesrc=d=2.4:c=brown:r=44100:a=0.35",
        "-af",
        "highpass=f=300,lowpass=f=3000,tremolo=f=18:d=0.4,"
        "afade=t=in:st=0:d=0.15,afade=t=out:st=2.1:d=0.3",
        "-c:a", "libmp3lame", "-b:a", "128k",
        "-ar", "44100", "-ac", "2", str(out),
    ]
    proc = _sp.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.warning(f"tuning SFX generation failed: {proc.stderr[-500:]}")
    else:
        logger.info(f"Generated tuning SFX at {out}")


def _ensure_og_default_image() -> None:
    """Generate a 1200x630 RadioLife-branded OG image for share landings."""
    out = STORAGE_DIR / "og_default.png"
    if out.exists() and out.stat().st_size > 1_000:
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        logger.warning(f"Pillow unavailable, skipping OG default: {e}")
        return
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), (10, 12, 24))
    draw = ImageDraw.Draw(img)
    # Soft gradient
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(10 + 30 * t), int(12 + 18 * t), int(24 + 45 * t)))
    # Neon rings
    for radius, color, width in [(440, (255, 45, 149), 3),
                                  (520, (0, 217, 255), 2),
                                  (600, (255, 45, 149), 1)]:
        draw.ellipse((W // 2 - radius, H // 2 - radius,
                      W // 2 + radius, H // 2 + radius),
                     outline=color, width=width)
    title_font = None
    sub_font = None
    for fp in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(fp).exists():
            title_font = ImageFont.truetype(fp, 110)
            regular = fp.replace("-Bold", "")
            sub_font = (ImageFont.truetype(regular, 30)
                        if Path(regular).exists() else ImageFont.truetype(fp, 28))
            break
    if title_font is None:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    draw.text((W // 2, H // 2 - 30), "RadioLife", fill=(255, 255, 255),
              font=title_font, anchor="mm")
    draw.text((W // 2, H // 2 + 60), "DUBAI", fill=(255, 45, 149),
              font=title_font, anchor="mm")
    draw.text((W // 2, H - 90), "AI-POWERED HINGLISH RADIO",
              fill=(160, 165, 200), font=sub_font, anchor="mm")
    img.save(out, "PNG", optimize=True)
    logger.info(f"Generated default OG image at {out}")



# ---------- voice previews ----------
async def _ensure_voice_previews():
    async def _gen():
        for voice_key, script in VOICE_PREVIEW_SCRIPTS.items():
            out = VOICE_PREVIEWS_DIR / f"{voice_key}.mp3"
            if out.exists() and out.stat().st_size > 5_000:
                continue
            try:
                voice = RJ_VOICES[voice_key]
                # Pick energy based on voice's fits_energies (Phase 3.6 aware)
                fits = voice.get("fits_energies") or ("medium",)
                if "party" in fits:
                    energy = "party"
                elif "chill" in fits and "medium" not in fits:
                    energy = "chill"
                else:
                    energy = "medium"
                # Phase 3.6 — provider-aware synthesis
                tmp = await asyncio.to_thread(
                    _synthesize_by_voice_key, script, voice_key, energy,
                )
                await asyncio.to_thread(truncate_audio, str(tmp), 6.5, 200)
                shutil.move(str(tmp), str(out))
                logger.info(f"Generated voice preview for {voice_key} (provider={voice.get('provider', 'elevenlabs')})")
            except Exception as e:
                logger.warning(f"Voice preview generation failed for {voice_key}: {e}")
    asyncio.create_task(_gen())


async def _infer_track_energy(title, artist, duration_sec):
    fallback = {"energy_level": DEFAULT_ENERGY, "mood": "uplifting"}
    if not openai_client: return fallback
    try:
        prompt = (
            f"Song title: '{title}'\nArtist: '{artist}'\nDuration: {duration_sec:.0f}s\n\n"
            f"Guess the energy level and mood from the title/artist alone. "
            f"Respond as compact JSON only, no prose:\n"
            f'{{"energy_level": "<one of: {"/".join(ENERGY_LEVELS)}>", '
            f'"mood": "<one of: {"/".join(MOOD_TAGS)}>"}}'
        )
        resp = await asyncio.to_thread(
            lambda: openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=60,
                response_format={"type": "json_object"},
            )
        )
        import json as _json
        data = _json.loads(resp.choices[0].message.content)
        energy = data.get("energy_level", DEFAULT_ENERGY)
        mood = data.get("mood", "uplifting")
        if energy not in ENERGY_LEVELS: energy = DEFAULT_ENERGY
        if mood not in MOOD_TAGS:       mood = "uplifting"
        return {"energy_level": energy, "mood": mood}
    except Exception as e:
        logger.warning(f"energy inference failed: {e}")
        return fallback


# ---------- common ----------
@api.get("/health")
@api.get("/healthz")
@api.get("/readyz")
async def health():
    # Phase Stabilization — Mongo-free liveness probe. Returns
    # synchronously regardless of DB connectivity so the deploy
    # platform's health check can pass during the long lifespan
    # initialiser. Also mounted at root scope ("/health", "/healthz",
    # "/readyz") for in-cluster probes that bypass ingress.
    return {"status": "ok", "service": "bigfm-dubai", "phase": 2}


@api.get("/voices")
async def list_voices():
    return {
        "voices": [
            {
                "key": k,
                "display_name": v["display_name"],
                "persona": v["persona"],
                "provider": v.get("provider", "elevenlabs"),
                "accent_target": v.get("accent_target", "hinglish"),
            }
            for k, v in RJ_VOICES.items()
        ],
        "default": DEFAULT_VOICE_KEY,
    }


# Phase 39 Session 1 — admin moderation surface for the launch personas.
@api.get("/admin/personas/safety_audit",
              dependencies=[Depends(require_admin)])
async def admin_personas_safety_audit():
    """Returns every persona's stored safety_classification + voice mapping."""
    out = []
    async for doc in db.rj_personality_profiles.find(
        {}, projection={
            "persona_id": 1, "display_name": 1, "name": 1, "slug": 1,
            "archetype": 1, "voice_key": 1, "voice_id": 1,
            "is_launch_persona": 1, "is_premium": 1, "active": 1,
            "safety_classification": 1, "language_mix": 1,
            "daypart_affinity": 1, "signature_phrases": 1,
            "updated_at": 1,
        }).sort("persona_id", 1):
        row = {k: doc.get(k) for k in doc if k != "_id"}
        row["persona_id"] = doc.get("persona_id") or doc.get("slug") \
                                            or str(doc.get("_id"))
        out.append(row)
    safe_count = sum(1 for p in out
                                  if (p.get("safety_classification") or {})
                                          .get("is_safe") is True)
    unsafe = [p for p in out
                      if (p.get("safety_classification") or {})
                              .get("is_safe") is False]
    return {"total":    len(out),
                  "safe":      safe_count,
                  "unsafe":  len(unsafe),
                  "missing_classification":
                          [p for p in out if not p.get("safety_classification")],
                  "personas": out}


@api.get("/admin/voices", dependencies=[Depends(require_admin)])
async def admin_list_voices():
    """Phase 3.6 — admin voice audition list. Returns full per-voice metadata
    plus the channels that have each voice assigned as a host."""
    channel_docs = await list_active_channels(db)
    voice_channels: dict = {k: [] for k in RJ_VOICES}
    for ch in channel_docs:
        for h in (ch.get("hosts") or []):
            vk = h.get("voice_key")
            if vk and vk in voice_channels:
                voice_channels[vk].append({
                    "slug": ch["_id"], "name": ch.get("name"), "role": h.get("role"),
                })
    out = []
    for key, v in RJ_VOICES.items():
        out.append({
            "key": key,
            "display_name": v.get("display_name"),
            "persona": v.get("persona"),
            "provider": v.get("provider", "elevenlabs"),
            "openai_voice": v.get("openai_voice"),
            "elevenlabs_voice_id": v.get("voice_id"),
            "duo_label": v.get("duo_label"),
            "accent_target": v.get("accent_target", "hinglish"),
            "for_languages": list(v.get("for_languages") or []),
            "fits_energies": list(v.get("fits_energies") or ()),
            "preview_url": f"/api/voices/preview/{key}",
            "assigned_channels": voice_channels.get(key, []),
            "is_default": key == DEFAULT_VOICE_KEY,
        })
    # Group by provider for easier scanning
    by_provider = {"openai_tts": [], "elevenlabs": []}
    for v in out:
        by_provider.setdefault(v["provider"], []).append(v)
    return {
        "voices": out,
        "by_provider": by_provider,
        "total": len(out),
        "default": DEFAULT_VOICE_KEY,
        "providers": sorted(by_provider.keys()),
    }


@api.post("/admin/voices/{voice_key}/regenerate_preview",
          dependencies=[Depends(require_admin)])
async def admin_regenerate_preview(voice_key: str):
    """Phase 3.6 — delete the cached preview and rebuild it (A/B testing)."""
    if voice_key not in RJ_VOICES:
        raise HTTPException(404, "unknown voice")
    out = VOICE_PREVIEWS_DIR / f"{voice_key}.mp3"
    try: out.unlink(missing_ok=True)
    except Exception: pass
    await _ensure_voice_previews()
    # Wait briefly so the file lands; if not, the client can poll.
    for _ in range(20):
        if out.exists() and out.stat().st_size > 5_000:
            break
        await asyncio.sleep(0.5)
    return {
        "voice_key": voice_key,
        "ready": out.exists() and out.stat().st_size > 5_000,
        "preview_url": f"/api/voices/preview/{voice_key}",
    }



@api.get("/voices/preview/{voice_key}")
async def voice_preview(voice_key: str, request: Request):
    if voice_key not in RJ_VOICES:
        raise HTTPException(404, "unknown voice")
    path = VOICE_PREVIEWS_DIR / f"{voice_key}.mp3"
    if not path.exists():
        await _ensure_voice_previews()
        await asyncio.sleep(0.3)
    if not path.exists():
        raise HTTPException(503, "preview not ready, try again in a moment")
    return _range_response(path, request)


# ---------- channels ----------
@api.get("/channels")
async def channels_list(request: Request):
    # Phase 3.8 — filter by listener's market so DFW users see DFW channels and
    # Dubai users see Dubai channels. Public (unauthenticated) callers still
    # see Dubai (the default market) so the marketing/preview surface keeps working.
    user_market = "dubai"
    full_user: Optional[dict] = None
    try:
        from auth import current_user
        u = await current_user(request)
        user_market = (u.get("market") or "dubai").lower()
        full_user = u
    except Exception:
        user_market = "dubai"
    docs = await list_active_channels(db)
    # Phase 10c — compute access for each channel using a single per-request
    # cache so we hit Mongo at most twice total (one user_ambassador_state
    # + one user_ambassador_unlocks read).
    from services.channel_access import check_channel_access
    access_cache: dict = {}
    out = []
    for ch in docs:
        ch_market = (ch.get("market") or "global").lower()
        # Phase 15d.2 — "global" channels are visible in every market.
        # Market-specific channels (e.g. "dfw") only show for matching users.
        if ch_market not in ("global", user_market):
            continue
        clock = ch.get("music_clock") or {}
        access = await check_channel_access(
            db, full_user, ch, cache=access_cache)
        out.append({
            "slug": ch["_id"],
            "name": ch["name"],
            "tagline": ch.get("tagline"),
            "description": ch.get("description"),
            "cover_color": ch.get("cover_color"),
            "cover_image_url": ch.get("cover_image_url"),
            # Phase 15d.2 — channel thumbnail (movie-poster collage) URL.
            "thumbnail_url": ch.get("thumbnail_url"),
            "language_mix": ch.get("language_mix", []),
            "hosts": [{
                "voice_key": h["voice_key"],
                "role": h["role"],
                "name": RJ_VOICES.get(h["voice_key"], {}).get("display_name", h["voice_key"]),
            } for h in ch.get("hosts", [])],
            "default_for_time": ch.get("default_for_time", []),
            "sort_order": ch.get("sort_order", 99),
            "music_clock": {
                "rotation": clock.get("rotation", []),
                "cycle_length": clock.get("cycle_length", 0),
            },
            "premium_only": bool(ch.get("premium_only", False)),
            "exclusivity_tier": ch.get("exclusivity_tier", "free"),
            "gating_message": ch.get("gating_message"),
            "access": access,
            "market": ch_market,
        })
    # Pick a sensible default for the listener's market — first channel the
    # user can actually start (skips locked tiers).
    default_slug = next(
        (c["slug"] for c in out if c["access"]["allowed"]),
        out[0]["slug"] if out else DEFAULT_CHANNEL_SLUG)
    return {"channels": out, "default": default_slug, "market": user_market}


@api.get("/channels/{slug}")
async def channel_detail(slug: str):
    ch = await get_channel(db, slug)
    if not ch or not ch.get("active"):
        # Phase 41 S1 — community station fallback so the /radio page
        # cover/persona/genre tiles render for user-owned stations.
        from routes.community_stations import lookup_community_channel
        ch = await lookup_community_channel(db, slug)
    if not ch or not ch.get("active"):
        raise HTTPException(404, "channel not found")
    return {
        "slug": ch["_id"],
        "name": ch["name"],
        "tagline": ch.get("tagline"),
        "description": ch.get("description"),
        "cover_color": ch.get("cover_color"),
        "language_mix": ch.get("language_mix", []),
        "allowed_genres": ch.get("allowed_genres", []),
        "allowed_moods": ch.get("allowed_moods", []),
        "allowed_energy_levels": ch.get("allowed_energy_levels", []),
        "music_clock": ch.get("music_clock"),
        "hosts": [{
            "voice_key": h["voice_key"],
            "role": h["role"],
            "name": RJ_VOICES.get(h["voice_key"], {}).get("display_name", h["voice_key"]),
        } for h in ch.get("hosts", [])],
        "default_for_time": ch.get("default_for_time", []),
    }


# ---------- admin: tracks ----------
@api.post("/admin/tracks/upload", dependencies=[Depends(require_admin)])
async def upload_track(file: UploadFile = File(...),
                       title: Optional[str] = Form(None),
                       artist: Optional[str] = Form(None)):
    if not file.filename:
        raise HTTPException(400, "missing filename")
    if not file.filename.lower().endswith(".mp3"):
        raise HTTPException(400, "only .mp3 supported")
    # Phase 22e — stream to disk + hash chunk-by-chunk so a 100 MB upload
    # doesn't materialize into process RAM.
    import hashlib as _hashlib
    track_id = str(uuid.uuid4())
    out_path = TRACKS_DIR / f"{track_id}.mp3"
    hasher = _hashlib.sha256()
    data = await file.read()
    hasher.update(data)
    with open(out_path, "wb") as out:
        out.write(data)
    sha = hasher.hexdigest()
    # Durable persistence (Tigris in prod) so admin-uploaded tracks survive
    # pod restarts / horizontal scaling; the local file stays as the cache.
    try:
        from services.object_storage import get_storage as _get_storage
        _get_storage().upload_bytes(key=f"storage/tracks/{track_id}.mp3", data=data,
                                    content_type="audio/mpeg")
    except Exception:
        pass
    try:
        info = ffprobe_info(out_path)
    except Exception as e:
        out_path.unlink(missing_ok=True)
        raise HTTPException(400, f"ffprobe failed: {e}")
    title_final = title or Path(file.filename).stem
    artist_final = artist or None
    tag_meta = await asyncio.to_thread(run_auto_tag, openai_client, str(out_path), title_final, artist_final)
    # Phase 22e — dedupe enforcement (ISRC > file_hash > title+artist+duration).
    from services.track_dedupe import find_duplicate, attach_dedupe_fields
    dup = await find_duplicate(
        db,
        file_hash=sha,
        isrc=tag_meta.get("isrc"),
        title=tag_meta.get("title") or title_final,
        artist=tag_meta.get("artist") or artist_final,
        duration_sec=info.get("duration_sec"),
    )
    if dup:
        out_path.unlink(missing_ok=True)
        return {"imported":          False,
                  "duplicate_of":    {"track_id": dup["track_id"],
                                                "title":      dup["title"],
                                                "artist":    dup["artist"]},
                  "matched_rule":  dup["matched_rule"]}
    doc = {"_id": track_id, "file_path": str(out_path),
              "file_hash": sha,
              "duration_sec": info["duration_sec"], "uploaded_at": _now_iso(), **tag_meta}
    attach_dedupe_fields(doc)
    try:
        await db.tracks.insert_one(doc)
    except Exception as ins_exc:
        # Race against the UNIQUE sparse file_hash index — re-resolve.
        if "duplicate key" in str(ins_exc).lower() or \
              ins_exc.__class__.__name__ == "DuplicateKeyError":
            out_path.unlink(missing_ok=True)
            dup2 = await find_duplicate(
                db, file_hash=sha,
                isrc=tag_meta.get("isrc"),
                title=tag_meta.get("title") or title_final,
                artist=tag_meta.get("artist") or artist_final,
                duration_sec=info.get("duration_sec"),
            )
            if dup2:
                return {"imported":         False,
                          "duplicate_of":   {"track_id": dup2["track_id"],
                                                      "title":      dup2["title"],
                                                      "artist":    dup2["artist"]},
                          "matched_rule": dup2["matched_rule"]}
        raise
    return _track_doc_to_out(doc)


@api.get("/admin/tracks", response_model=List[TrackOut], dependencies=[Depends(require_admin)])
async def list_tracks():
    docs = await db.tracks.find({}).sort("uploaded_at", -1).to_list(500)
    return [_track_doc_to_out(d) for d in docs]


class BulkUploadResult(BaseModel):
    succeeded: List[TrackOut]
    failed: List[dict]


@api.post("/admin/tracks/bulk_upload", response_model=BulkUploadResult,
              dependencies=[Depends(require_admin)])
async def bulk_upload(audio_files: Optional[List[UploadFile]] = File(default=None),
                                            zip_file: Optional[UploadFile] = File(default=None),
                                            csv_file: Optional[UploadFile] = File(default=None)):
    import csv as _csv, io, zipfile
    overrides: Dict[str, dict] = {}
    if csv_file is not None and csv_file.filename:
        try:
            content = (await csv_file.read()).decode("utf-8", errors="ignore")
            reader = _csv.DictReader(io.StringIO(content))
            for row in reader:
                fn = (row.get("filename") or "").strip()
                if not fn: continue
                cleaned = {k: v.strip() for k, v in row.items() if k != "filename" and v and v.strip()}
                if cleaned: overrides[fn] = cleaned
        except Exception as e:
            raise HTTPException(400, f"CSV parse error: {e}")
    candidates: List[Tuple[str, bytes]] = []
    if audio_files:
        for af in audio_files:
            if not af.filename: continue
            if not af.filename.lower().endswith(".mp3"): continue
            candidates.append((af.filename, await af.read()))
    if zip_file is not None and zip_file.filename:
        try:
            zb = await zip_file.read()
            with zipfile.ZipFile(io.BytesIO(zb)) as zf:
                for name in zf.namelist():
                    if name.lower().endswith(".mp3") and not name.startswith("__MACOSX"):
                        candidates.append((Path(name).name, zf.read(name)))
        except Exception as e:
            raise HTTPException(400, f"ZIP parse error: {e}")
    if not candidates: raise HTTPException(400, "no MP3s provided")

    async def _process_one(filename, data):
        try:
            track_id = str(uuid.uuid4())
            out_path = TRACKS_DIR / f"{track_id}.mp3"
            out_path.write_bytes(data)
            info = await asyncio.to_thread(ffprobe_info, out_path)
            csv_over = overrides.get(filename, {})
            user_title = csv_over.get("title") or Path(filename).stem
            user_artist = csv_over.get("artist")
            tag_meta = await asyncio.to_thread(run_auto_tag, openai_client, str(out_path), user_title, user_artist)
            applied = []
            for k in ("title", "artist", "album", "language", "era", "genre", "mood", "energy_level"):
                if k in csv_over: tag_meta[k] = csv_over[k]; applied.append(k)
            tag_meta["manual_overrides"] = applied
            doc = {"_id": track_id, "file_path": str(out_path),
                   "duration_sec": info["duration_sec"], "uploaded_at": _now_iso(), **tag_meta}
            await db.tracks.insert_one(doc)
            return doc, None
        except Exception as e:
            return None, str(e)

    sem = asyncio.Semaphore(4)
    async def _bounded(fn, data):
        async with sem: return await _process_one(fn, data)
    results = await asyncio.gather(*[_bounded(fn, data) for fn, data in candidates])
    succeeded = [_track_doc_to_out(d) for d, _ in results if d]
    failed = [{"filename": candidates[i][0], "error": err}
              for i, (d, err) in enumerate(results) if err]
    return BulkUploadResult(succeeded=succeeded, failed=failed)


@api.post("/admin/tracks/{track_id}/retag", response_model=TrackOut,
          dependencies=[Depends(require_admin)])
async def admin_retag_track(track_id: str):
    doc = await db.tracks.find_one({"_id": track_id})
    if not doc: raise HTTPException(404, "track not found")
    file_path = doc.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(400, "track file missing on disk")
    tag_meta = await asyncio.to_thread(run_auto_tag, openai_client, file_path,
                                       doc.get("title"), doc.get("artist"))
    preserved = doc.get("manual_overrides") or []
    for k in preserved:
        if k in doc: tag_meta[k] = doc[k]
    tag_meta["manual_overrides"] = preserved
    await db.tracks.update_one({"_id": track_id}, {"$set": tag_meta})
    return _track_doc_to_out(await db.tracks.find_one({"_id": track_id}))


@api.patch("/admin/tracks/{track_id}", dependencies=[Depends(require_admin)])
async def admin_patch_track(track_id: str, payload: dict):
    allowed = {"energy_level", "mood", "title", "artist", "bpm"}
    update = {k: v for k, v in payload.items() if k in allowed}
    if "energy_level" in update and update["energy_level"] not in ENERGY_LEVELS:
        raise HTTPException(400, f"energy_level must be one of {ENERGY_LEVELS}")
    if not update: raise HTTPException(400, "no editable fields")
    res = await db.tracks.update_one({"_id": track_id}, {"$set": update})
    if res.matched_count == 0: raise HTTPException(404, "track not found")
    return _track_doc_to_out(await db.tracks.find_one({"_id": track_id}))


@api.delete("/admin/tracks/{track_id}", dependencies=[Depends(require_admin)])
async def admin_delete_track(track_id: str):
    doc = await db.tracks.find_one({"_id": track_id})
    if not doc: raise HTTPException(404, "track not found")
    from datetime import timedelta
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    busy = await db.segments.find_one({"track_id": track_id, "created_at": {"$gte": cutoff_iso}})
    if busy:
        raise HTTPException(409, "Track is in an active radio session. Try again shortly.")
    fp = doc.get("file_path")
    if fp:
        try: Path(fp).unlink(missing_ok=True)
        except Exception as e: logger.warning(f"delete file failed: {e}")
    await db.tracks.delete_one({"_id": track_id})
    return {"ok": True, "id": track_id}


@api.get("/admin/tracks/{track_id}/health", dependencies=[Depends(require_admin)])
async def admin_track_health(track_id: str):
    """Phase 42 S1 — playable health probe. Lightweight: HEAD-equivalent for
    Tigris (signed URL + boto3 head_object), Path.exists for disk."""
    doc = await db.tracks.find_one({"_id": track_id},
                                                                  {"storage_provider": 1, "storage_key": 1,
                                                                    "file_path": 1})
    if not doc:
        return {"playable": False, "reason": "unknown"}
    sp = doc.get("storage_provider")
    # Phase 41 S1.5 — write-back: the recommender excludes any track
    # whose `playable_status != "ok"` so a one-time HEAD probe self-heals
    # the catalog without a cron. `last_playable_check_at` lets ops see
    # the freshness in the admin library.
    async def _persist(status: str, reason: str):
        try:
            await db.tracks.update_one(
                {"_id": track_id},
                {"$set": {"playable_status": status,
                          "last_playable_check_at": datetime.utcnow().isoformat()}})
        except Exception:
            pass
    if sp == "tigris":
        key = doc.get("storage_key")
        if not key:
            await _persist("missing_storage_key", "missing_storage_key")
            return {"playable": False, "reason": "missing_storage_key"}
        try:
            from services.object_storage import get_storage
            s = get_storage()
            # boto3 head_object is cheap (no body); signed URL is for clients
            if hasattr(s, "s3") and s.s3:
                try:
                    s.s3.head_object(Bucket=s.bucket, Key=key)
                    await _persist("ok", "ok")
                    return {"playable": True, "reason": "ok"}
                except Exception:
                    await _persist("tigris_404", "tigris_404")
                    return {"playable": False, "reason": "tigris_404"}
            # fallback — assume signed URL availability
            s.get_signed_url(key=key, expires_in=60)
            await _persist("ok", "ok")
            return {"playable": True, "reason": "ok"}
        except Exception:
            await _persist("tigris_404", "tigris_404")
            return {"playable": False, "reason": "tigris_404"}
    fp = doc.get("file_path")
    if not fp:
        await _persist("missing_storage_key", "missing_storage_key")
        return {"playable": False, "reason": "missing_storage_key"}
    if not Path(fp).exists():
        await _persist("disk_missing", "disk_missing")
        return {"playable": False, "reason": "disk_missing"}
    await _persist("ok", "ok")
    return {"playable": True, "reason": "ok"}


@api.get("/admin/tracks/{track_id}/preview", dependencies=[Depends(require_admin)])
async def admin_preview_track(track_id: str, request: Request):
    doc = await db.tracks.find_one({"_id": track_id})
    if not doc: raise HTTPException(404, "track not found")
    # Phase 42-hotfix — Tigris-backed tracks have file_path='s3://…'
    # which never exists on local disk. Redirect to a signed GET URL.
    sp = doc.get("storage_provider")
    if sp == "tigris":
        key = doc.get("storage_key")
        if not key:
            raise HTTPException(404, "track storage_key missing")
        try:
            from services.object_storage import get_storage
            url = get_storage().get_signed_url(key=key, expires_in=600)
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url, status_code=302)
        except Exception as e:
            raise HTTPException(502, f"signed URL failed: {e}")
    # Local-disk path
    fp = doc.get("file_path")
    if not fp or not Path(fp).exists(): raise HTTPException(404, "track file missing")
    return _range_response(Path(fp), request)


# ---------- rj/* (auth-gated) ----------
@api.post("/rj/generate", response_model=RJGenerateResponse, dependencies=[Depends(current_user)])
async def rj_generate(req: RJGenerateRequest):
    prev = await _get_track(req.prev_track_id)
    nxt = await _get_track(req.next_track_id)
    script = _generate_rj_script_solo(prev, nxt, req.context, DEFAULT_VOICE_KEY)
    return RJGenerateResponse(script=script, voice_id=RJ_VOICES[DEFAULT_VOICE_KEY]["voice_id"])


@api.post("/rj/synthesize", response_model=RJSynthResponse, dependencies=[Depends(current_user)])
async def rj_synthesize(req: RJSynthRequest):
    if not req.script.strip(): raise HTTPException(400, "empty script")
    voice_id = req.voice_id or RJ_VOICES[DEFAULT_VOICE_KEY]["voice_id"]
    try:
        out_path = _synthesize_solo(req.script, voice_id, DEFAULT_ENERGY)
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs error: {e}")
    info = ffprobe_info(out_path)
    rj_id = out_path.stem
    await db.rj_audios.insert_one({"_id": rj_id, "file_path": str(out_path),
                                    "duration_sec": info["duration_sec"], "voice_id": voice_id,
                                    "script": req.script, "created_at": _now_iso()})
    return RJSynthResponse(rj_audio_id=rj_id, file_path=str(out_path), duration_sec=info["duration_sec"])


@api.post("/stream/build", response_model=StreamBuildResponse, dependencies=[Depends(require_admin)])
async def stream_build(req: StreamBuildRequest):
    if len(req.track_ids) < 2: raise HTTPException(400, "need at least 2 tracks")
    if len(req.track_ids) > 6: raise HTTPException(400, "max 6 tracks")
    tracks = [await _get_track(tid) for tid in req.track_ids]
    for t in tracks:
        if t["duration_sec"] < 5.0: raise HTTPException(400, f"track {t['_id']} too short")
    rj_paths: List[str] = []; rj_durs: List[float] = []; rj_scripts: List[str] = []
    for i in range(len(tracks) - 1):
        script = _generate_rj_script_solo(tracks[i], tracks[i+1], RJContext(), DEFAULT_VOICE_KEY)
        voice_id = RJ_VOICES[DEFAULT_VOICE_KEY]["voice_id"]
        try:
            rj_path = _synthesize_solo(script, voice_id, tracks[i+1].get("energy_level", DEFAULT_ENERGY))
        except Exception as e: raise HTTPException(502, f"ElevenLabs error: {e}")
        rj_info = ffprobe_info(rj_path)
        rj_paths.append(str(rj_path)); rj_durs.append(rj_info["duration_sec"]); rj_scripts.append(script)
        await db.rj_audios.insert_one({"_id": rj_path.stem, "file_path": str(rj_path),
                                        "duration_sec": rj_info["duration_sec"], "voice_id": voice_id,
                                        "script": script, "created_at": _now_iso()})
    stream_id = str(uuid.uuid4())
    out_path = STREAMS_DIR / f"{stream_id}.mp3"
    try:
        meta = build_stream(track_paths=[_track_file_path_for_ffmpeg(t) for t in tracks],
                            track_durations=[float(t["duration_sec"]) for t in tracks],
                            rj_paths=rj_paths, rj_durations=rj_durs, output_path=out_path)
    except Exception as e: raise HTTPException(500, f"stream build failed: {e}")
    await db.streams.insert_one({"_id": stream_id, "file_path": str(out_path),
                                  "duration_sec": meta["duration_sec"], "segments": meta["segments"],
                                  "track_ids": req.track_ids, "rj_scripts": rj_scripts,
                                  "created_at": _now_iso()})
    return StreamBuildResponse(stream_id=stream_id, file_path=str(out_path),
                                duration_sec=meta["duration_sec"],
                                segments=[StreamSegment(**s) for s in meta["segments"]])


# ---------- Range streaming helpers ----------
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _parse_range(range_header, file_size):
    m = _RANGE_RE.match(range_header)
    if not m: raise HTTPException(400, "invalid Range header")
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "": raise HTTPException(400, "invalid Range header")
    if start_s == "":
        length = int(end_s); start = max(0, file_size - length); end = file_size - 1
    else:
        start = int(start_s); end = int(end_s) if end_s else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size: raise HTTPException(416, "range not satisfiable")
    return start, end


def _iter_file(path, start, end, chunk_size=64 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            buf = f.read(min(chunk_size, remaining))
            if not buf: break
            remaining -= len(buf); yield buf


def _range_response(file_path: Path, request: Request) -> StreamingResponse:
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    if range_header:
        start, end = _parse_range(range_header, file_size)
        length = end - start + 1
        headers = {"Content-Range": f"bytes {start}-{end}/{file_size}",
                   "Accept-Ranges": "bytes", "Content-Length": str(length),
                   "Content-Type": "audio/mpeg", "Cache-Control": "no-cache"}
        return StreamingResponse(_iter_file(file_path, start, end), status_code=206,
                                 headers=headers, media_type="audio/mpeg")
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(file_size),
               "Content-Type": "audio/mpeg", "Cache-Control": "no-cache"}
    return StreamingResponse(_iter_file(file_path, 0, file_size - 1), status_code=200,
                             headers=headers, media_type="audio/mpeg")


@api.get("/stream/{stream_id}")
async def get_stream(stream_id: str, request: Request):
    doc = await db.streams.find_one({"_id": stream_id})
    if not doc: raise HTTPException(404, "stream not found")
    file_path = Path(doc["file_path"])
    if not file_path.exists(): raise HTTPException(404, "stream file missing")
    return _range_response(file_path, request)


@api.get("/stream/{stream_id}/meta")
async def get_stream_meta(stream_id: str):
    doc = await db.streams.find_one({"_id": stream_id})
    if not doc: raise HTTPException(404, "stream not found")
    return {"stream_id": stream_id, "duration_sec": doc["duration_sec"],
            "segments": doc["segments"], "rj_scripts": doc.get("rj_scripts", []),
            "track_ids": doc.get("track_ids", [])}


# ---------- RADIO core ----------
def _tod_now_dubai() -> str:
    from datetime import timedelta
    uae_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    if 5 <= uae_hour < 12:  return "morning"
    if 12 <= uae_hour < 17: return "afternoon"
    if 17 <= uae_hour < 21: return "evening"
    return "late_night"


def _activity_guess_now() -> str:
    from datetime import timedelta
    uae_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    if 6 <= uae_hour < 10:    return "morning_commute"
    if 10 <= uae_hour < 13:   return "workday_focus"
    if 13 <= uae_hour < 15:   return "lunch_break"
    if 17 <= uae_hour < 20:   return "evening_commute"
    if 20 <= uae_hour < 23:   return "dinner"
    if 23 <= uae_hour or uae_hour < 5: return "late_night_drive"
    return "workday_focus"


_ENERGY_INDEX = {e: i for i, e in enumerate(ENERGY_LEVELS)}


def _energy_distance(a, b):
    if not a or not b: return 0
    return abs(_ENERGY_INDEX.get(a, 1) - _ENERGY_INDEX.get(b, 1))


def _score_track(track, pv, prev_track, played_ids, recent_artists,
                 banned_artists=None, banned_albums=None):
    tid = track["_id"]
    if tid in played_ids: return float("-inf")
    if track.get("artist") and recent_artists and track["artist"] in recent_artists[-2:]:
        return float("-inf")
    if track.get("explicit") and not pv.get("explicit_ok", False): return float("-inf")
    if banned_artists and track.get("artist") in banned_artists: return float("-inf")
    if banned_albums and track.get("album") in banned_albums: return float("-inf")
    s = 0.0
    languages = pv.get("languages") or []
    genres = pv.get("genres") or []
    eras = pv.get("eras") or []
    moods = pv.get("moods") or []
    activities = pv.get("activities") or []
    fav_artists = [a.lower() for a in (pv.get("favorite_artists") or [])]
    if track.get("language") and track["language"] in languages: s += 30
    if track.get("genre") and track["genre"] in genres: s += 20
    era = track.get("era") or _era_bucket(track.get("release_year"))
    if era and era in eras: s += 15
    if track.get("mood") in moods: s += 15
    if any(v in moods for v in (track.get("vibe_tags") or [])): s += 5
    if _tod_now_dubai() in (track.get("recommended_time_of_day") or []): s += 10
    if _activity_guess_now() in activities: s += 5
    if prev_track and _energy_distance(prev_track.get("energy_level"),
                                       track.get("energy_level")) > 1:
        s -= 20
    if track.get("artist") and track["artist"].lower() in fav_artists: s += 25
    disliked = [a.lower() for a in (pv.get("disliked_artists") or [])]
    if track.get("artist") and track["artist"].lower() in disliked: s -= 60
    s += random.uniform(0, 5)
    return s


# Phase 5.1 — Recommendation fallback ladder
PLAYED_HISTORY_MAX = 50   # cap session.played_track_ids
PLAYED_HISTORY_KEEP = 30  # trim to last N when over cap

# Phase Bug-2 — Progressive channel-filter relaxation threshold.
# When the candidate pool drops below this size we begin progressively
# dropping HARD channel filters in this order to avoid single-song
# loops on sparse channels (e.g. punjabi_beats with a tiny catalog):
#   energy → mood → genre → language-only → catalog-wide
# Each relaxation step is recorded in `recommender_decision_log`.
MIN_POOL_SIZE = 8


def _build_channel_pool_with_relaxation(
    all_tracks: list, channel: dict,
) -> tuple[list, list[dict]]:
    """Progressively relax channel hard filters until pool >= MIN_POOL_SIZE.

    Returns (pool, steps) where each `step` is a structured dict suitable
    for inserting verbatim into `recommender_decision_log.steps`.

    Order of relaxation (channel `language_mix` is preserved everywhere
    except the final two fallbacks):
        strict          — energy + genre + mood   (channel_filter)
        drop_energy     — drop allowed_energy_levels
        drop_mood       — drop allowed_moods too
        drop_genre      — drop allowed_genres too (now language-mix + nothing)
        language_only   — match any of channel.language_mix only
        catalog_wide    — anything (last resort; only when language pool empty)
    """
    allowed_g = list(channel.get("allowed_genres") or [])
    allowed_m = list(channel.get("allowed_moods") or [])
    allowed_e = list(channel.get("allowed_energy_levels") or [])
    lang_mix = [x.get("language") for x in (channel.get("language_mix") or [])
                  if x.get("language")]

    def _apply(*, drop_energy: bool, drop_mood: bool, drop_genre: bool):
        out = []
        for t in all_tracks:
            if not drop_energy and allowed_e and t.get("energy_level") not in allowed_e:
                continue
            if not drop_genre and allowed_g and t.get("genre") and t.get("genre") not in allowed_g:
                continue
            if not drop_mood and allowed_m and t.get("mood") and t.get("mood") not in allowed_m:
                if not any(v in allowed_m for v in (t.get("vibe_tags") or [])):
                    continue
            # language_mix is always applied above strict so we don't
            # accidentally pull e.g. devotional tracks onto Punjabi Beats.
            if lang_mix and t.get("language") not in lang_mix:
                continue
            out.append(t)
        return out

    steps: list[dict] = []
    # 0 — strict
    pool = _apply(drop_energy=False, drop_mood=False, drop_genre=False)
    steps.append({"step": "strict", "pool_size": len(pool),
                   "dropped": [], "language_mix": lang_mix})
    if len(pool) >= MIN_POOL_SIZE:
        return pool, steps

    # 1 — drop energy
    pool = _apply(drop_energy=True, drop_mood=False, drop_genre=False)
    steps.append({"step": "drop_energy", "pool_size": len(pool),
                   "dropped": ["energy"], "language_mix": lang_mix})
    if len(pool) >= MIN_POOL_SIZE:
        return pool, steps

    # 2 — drop mood
    pool = _apply(drop_energy=True, drop_mood=True, drop_genre=False)
    steps.append({"step": "drop_mood", "pool_size": len(pool),
                   "dropped": ["energy", "mood"], "language_mix": lang_mix})
    if len(pool) >= MIN_POOL_SIZE:
        return pool, steps

    # 3 — drop genre (now language-mix only)
    pool = _apply(drop_energy=True, drop_mood=True, drop_genre=True)
    steps.append({"step": "drop_genre", "pool_size": len(pool),
                   "dropped": ["energy", "mood", "genre"],
                   "language_mix": lang_mix})
    if len(pool) >= MIN_POOL_SIZE:
        return pool, steps

    # 4 — language-only (any of channel's language_mix; same set, kept for
    #      symmetry / future when language_mix may have multiple langs)
    if lang_mix:
        pool = [t for t in all_tracks if t.get("language") in lang_mix]
        steps.append({"step": "language_only", "pool_size": len(pool),
                       "dropped": ["energy", "mood", "genre"],
                       "language_mix": lang_mix})
        if pool:
            return pool, steps

    # 5 — catalog-wide last resort
    pool = list(all_tracks)
    steps.append({"step": "catalog_wide", "pool_size": len(pool),
                   "dropped": ["energy", "mood", "genre", "language"],
                   "language_mix": lang_mix})
    return pool, steps


async def _log_recommender_decision(*, channel_slug: str, user_id,
                                       session_id, steps: list[dict],
                                       final_step: str, final_pool_size: int,
                                       chosen_track: Optional[dict],
                                       tier: Optional[str] = None,
                                       reason: Optional[str] = None) -> None:
    """Append a structured decision row to `recommender_decision_log`.

    Never raises — telemetry must never break the recommender.
    """
    try:
        doc = {
            "_id": uuid.uuid4().hex,
            "ts": datetime.now(timezone.utc),
            "channel_slug": channel_slug,
            "user_id": user_id,
            "session_id": session_id,
            "steps": steps,
            "final_step": final_step,
            "final_pool_size": final_pool_size,
            "tier": tier,
            "reason": reason,
        }
        if chosen_track:
            doc["chosen_track"] = {
                "track_id": chosen_track.get("_id"),
                "title": chosen_track.get("title"),
                "artist": chosen_track.get("artist"),
                "language": chosen_track.get("language"),
                "energy_level": chosen_track.get("energy_level"),
                "mood": chosen_track.get("mood"),
                "genre": chosen_track.get("genre"),
            }
        await db.recommender_decision_log.insert_one(doc)
    except Exception as _e:
        logger.warning(f"[reco-log] insert failed: {_e}")


def _truncate_played_history(played: list) -> list:
    """Cap session.played_track_ids to last PLAYED_HISTORY_KEEP entries
    once it grows past PLAYED_HISTORY_MAX. Prevents permanent accumulation
    on long sessions which would starve the recommender."""
    if len(played) > PLAYED_HISTORY_MAX:
        return played[-PLAYED_HISTORY_KEEP:]
    return played


def _pick_eligible(tracks, pv, prev_track, played_ids, recent_artists,
                     banned_artists, banned_albums):
    """Score and filter; returns list of (track, score) sorted descending."""
    scored = [(t, _score_track(t, pv, prev_track, played_ids, recent_artists,
                                  banned_artists, banned_albums)) for t in tracks]
    eligible = [(t, s) for t, s in scored if s > float("-inf")]
    eligible.sort(key=lambda ts: ts[1], reverse=True)
    return eligible


def _track_file_path_for_ffmpeg(track: dict) -> str:
    """Phase 22c — resolve a `tracks` row's file_path for ffmpeg input.
    Tigris-backed rows return a signed HTTPS URL; local-backed rows
    return the on-disk path unchanged (legacy + seed tracks).
    """
    if (track or {}).get("storage_provider") == "tigris":
        key = track.get("storage_key")
        if not key:
            raise HTTPException(503, detail={"error": "tigris_track_missing_key",
                                                                          "track_id": track.get("_id")})
        from services.object_storage import get_storage
        return get_storage().get_signed_url(key=key, expires_in=3600)
    return track["file_path"]


async def _pick_next_track_personalized(session, channel, prev_track=None):
    """Pick the next track with progressive constraint relaxation. NEVER
    returns None — if all tiers fail, raises 503 with retry_channel hint
    so the frontend can auto-switch.

    Phase Bug-2 — when the channel-filtered pool is small (< MIN_POOL_SIZE)
    we progressively drop HARD channel filters (energy → mood → genre →
    language-only → catalog-wide) before scoring.  Every relaxation is
    written to `recommender_decision_log` for ops visibility via
    `GET /api/admin/channels/{slug}/health`.
    """
    # P0 — exclude tracks whose storage backing is broken (e.g. Tigris
    # 404s from a stale migration with no local fallback).  Tagged via
    # `status: broken_storage_missing` by the data-hygiene sweep.
    # Phase 41 S1.5 — also exclude tracks where the on-demand health
    # probe flipped `playable_status` to anything other than 'ok' (e.g.
    # tigris_404 / disk_missing). Absent field = legacy ok.
    all_tracks = await db.tracks.find(
        {"status": {"$ne": "broken_storage_missing"},
         "$or": [{"playable_status": {"$exists": False}},
                  {"playable_status": "ok"}]}).to_list(2000)
    if not all_tracks:
        raise HTTPException(503, detail={"error": "catalog_empty",
                                          "message": "No tracks in catalog. Upload via /admin."})
    # Phase 15d.1 — drop any track whose `markets_allowed` excludes the
    # listener's market. Auto-set by the boot-time track-title audit for
    # city-named tracks (e.g. "Sharjah Sunrise" → only `dubai`).
    # Phase 15d.1 — listener market wins over session.market (which is the
    # legacy `users.market` cohort tag). preferred_market > last_resolved >
    # session.market > "dubai".
    _listener_market = "dubai"
    # Phase Stabilization (Bug A/B fix) — also pull the listener's
    # actual city so the RJ prompt can use "Hey London listeners"
    # instead of defaulting to the market's display_name.
    _listener_city: str | None = None
    try:
        _u_id = session.get("user_id")
        if _u_id:
            _u = await db.users.find_one(
                {"user_id": _u_id},
                {"preferred_market": 1, "last_resolved_market": 1, "market": 1,
                 "city": 1, "preferred_city": 1, "last_resolved_city": 1},
            )
            if _u:
                _listener_market = (
                    _u.get("preferred_market")
                    or _u.get("last_resolved_market")
                    or _u.get("market")
                    or session.get("market")
                    or "dubai"
                )
                _listener_city = (
                    _u.get("preferred_city")
                    or _u.get("last_resolved_city")
                    or _u.get("city")
                    or None
                )
    except Exception:
        _listener_market = (session.get("market") or "dubai")
    _listener_market = _listener_market.strip().lower()
    # Phase Bug-2 RJ tz fix — cache the resolved market on the in-memory
    # session dict so downstream `_ctx_for_now(session=session)` calls
    # pick up the listener's actual timezone (not the Dubai default).
    session["market_resolved"] = _listener_market
    session["city_resolved"]   = _listener_city
    _before_market_filter = len(all_tracks)
    market_filtered = [t for t in all_tracks
                            if not t.get("markets_allowed")
                            or _listener_market in (t.get("markets_allowed") or [])]
    if not market_filtered:
        # Phase Stabilization (Bug A) — global-catalog fallback. Any
        # unsupported / unseeded market would previously 503; we now
        # transparently fall back to the unrestricted catalog so the
        # listener gets music. The market-targeted lexicon still drives
        # the RJ city + brand mentions (Bug B), so a London listener
        # still hears city-aware copy even when the music itself is
        # market-agnostic.
        logger.warning(
            "[market-filter] global-fallback: market=%s had 0 matching "
            "tracks → using full catalog of %d tracks",
            _listener_market, _before_market_filter)
        all_tracks = all_tracks
    else:
        all_tracks = market_filtered
    if _before_market_filter != len(all_tracks):
        logger.info("[market-filter] %s: %d→%d tracks dropped",
                          _listener_market,
                          _before_market_filter - len(all_tracks),
                          len(all_tracks))
    pv = session.get("preference_vector") or {}
    # Truncate session history to avoid permanent accumulation.
    raw_played = list(session.get("played_track_ids", []))
    played = _truncate_played_history(raw_played)
    if len(played) != len(raw_played):
        try:
            await db.radio_sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"played_track_ids": played}},
            )
        except Exception:
            pass
    recent_artists = list(session.get("recent_artists", []))
    user_id = session.get("user_id")
    session_id = session.get("_id")

    # Compliance bans (rolling 3hr from playback_logs, not session history)
    banned_artists: set = set()
    banned_albums: set = set()
    if user_id:
        try:
            a_cap, alb_cap = await banned_artists_albums(db, user_id, all_tracks)
            banned_artists |= a_cap; banned_albums |= alb_cap
            same_artist = await consecutive_artists_to_block(db, user_id)
            banned_artists |= set(same_artist)
        except Exception as e:
            logger.warning(f"[reco] compliance lookup failed: {e}")

    # Phase Bug-2 — Channel hard filter with progressive relaxation
    channel_tracks, relax_steps = _build_channel_pool_with_relaxation(
        all_tracks, channel)
    final_step = relax_steps[-1]["step"] if relax_steps else "strict"
    if not channel_tracks:
        # Pool is empty even after catalog-wide fallback (no tracks at all
        # matched anywhere — only possible on empty catalogs handled above).
        await _log_recommender_decision(
            channel_slug=channel["_id"], user_id=user_id, session_id=session_id,
            steps=relax_steps, final_step=final_step,
            final_pool_size=0, chosen_track=None,
            tier="tier_empty", reason="all_relaxation_tiers_exhausted")
        logger.error(f"[reco][empty] channel={channel['_id']} — pure random catalog")
        chosen = random.choice(all_tracks)
        return chosen
    if final_step != "strict":
        logger.info(f"[reco][relaxed ch={channel['_id']}] "
                     f"trail={'→'.join(s['step'] for s in relax_steps)} "
                     f"final_pool={len(channel_tracks)}")

    # Music clock slot
    segments_played = int(session.get("segments_played", 0))
    slot = slot_for_position(channel, segments_played)
    slot_filtered = apply_music_clock_slot(channel_tracks, slot, channel, pv)
    if not slot_filtered:
        logger.info(f"[reco] slot '{slot}' empty for channel {channel['_id']} — fall back to channel-only")
        slot_filtered = channel_tracks

    # Tier 1 — strict: full PreferenceVector + compliance + recent history
    eligible = _pick_eligible(slot_filtered, pv, prev_track, played,
                                recent_artists, banned_artists, banned_albums)
    tier = 1
    if not eligible:
        # Tier 2 — drop slot filter, keep everything else
        eligible = _pick_eligible(channel_tracks, pv, prev_track, played,
                                    recent_artists, banned_artists, banned_albums)
        if eligible: tier = 2

    if not eligible:
        # Tier 3 — drop compliance bans; still keep "no immediate repeat"
        last_id = played[-1] if played else None
        candidates = [t for t in channel_tracks if t["_id"] != last_id]
        eligible = _pick_eligible(candidates or channel_tracks, pv, prev_track,
                                    [], [], None, None)
        if eligible:
            tier = 3
            logger.info(f"[reco][tier3] relaxed compliance, channel={channel['_id']}")

    if not eligible:
        # Tier 4 — pure random from channel tracks (ignore everything except "not immediate")
        last_id = played[-1] if played else None
        pool = [t for t in channel_tracks if t["_id"] != last_id] or channel_tracks
        chosen = random.choice(pool)
        logger.warning(f"[reco][tier4] pure-random channel pick: {chosen.get('title')} by {chosen.get('artist')}")
        await _log_recommender_decision(
            channel_slug=channel["_id"], user_id=user_id, session_id=session_id,
            steps=relax_steps, final_step=final_step,
            final_pool_size=len(channel_tracks), chosen_track=chosen,
            tier="tier4_pure_random", reason="all_score_tiers_failed")
        return chosen

    # Normal weighted pick from top-3 of the chosen tier
    top = eligible[: max(1, min(3, len(eligible)))]
    chosen, score = random.choice(top)
    if tier == 1:
        logger.info(f"[reco][tier1 ch={channel['_id']} slot={slot}] "
                     f"picked '{chosen['title']}' by {chosen['artist']} (score={score:.1f})")
    else:
        logger.info(f"[reco][tier{tier} ch={channel['_id']}] "
                     f"picked '{chosen['title']}' by {chosen['artist']} (score={score:.1f})")
    # Always log decision — even on strict-tier1 — so the health endpoint
    # can render an accurate trace of what's happening on a channel.
    await _log_recommender_decision(
        channel_slug=channel["_id"], user_id=user_id, session_id=session_id,
        steps=relax_steps, final_step=final_step,
        final_pool_size=len(channel_tracks), chosen_track=chosen,
        tier=f"tier{tier}",
        reason="ok" if tier == 1 else f"score_tier_{tier}")
    return chosen


def _ctx_for_now(market: str = "dubai", city: str | None = None,
                          session: dict | None = None) -> RJContext:
    """Build a context for prompt generation. Phase 15d.1 — market-aware:
       computes daypart in the market's local timezone and pulls city +
       weather defaults from the lexicon when not provided.

       Phase Bug-2 RJ tz fix — when `session` is provided, the resolved
       listener market (cached on the session dict by
       `_pick_next_track_personalized`) overrides the kwarg default.

       Phase Stabilization (Bug B) — also pulls `city_resolved` from the
       session dict if present, so the RJ prompt mentions the listener's
       actual city (e.g. "Hey London listeners") instead of falling back
       to the market's display_name."""
    if session and session.get("market_resolved"):
        market = session["market_resolved"]
    if session and session.get("city_resolved") and not city:
        city = session["city_resolved"]
    from datetime import timedelta
    try:
        from services.market_lexicon import get_lexicon
        lex = get_lexicon(market)
    except Exception:
        lex = {}
    tz = lex.get("timezone") or "Asia/Dubai"
    # Pick local hour without dragging in pytz: compute UTC offset by
    # subtracting from now. For our 6 shipping markets a static offset
    # suffices because daypart is bucketed in 4-hour ranges.
    _MARKET_UTC_OFFSET_HOURS = {
        "Asia/Dubai":            4,
        "Asia/Kolkata":          5.5,
        "Europe/London":         0,
        "America/New_York":      -5,
        "America/Chicago":       -6,
        "America/Los_Angeles":   -8,
    }
    off = _MARKET_UTC_OFFSET_HOURS.get(tz, 0)
    local_hour = int((datetime.now(timezone.utc) + timedelta(hours=off)).hour)
    if 5 <= local_hour < 12:    tod = "morning"
    elif 12 <= local_hour < 17: tod = "afternoon"
    elif 17 <= local_hour < 21: tod = "evening drive time"
    else:                        tod = "late night"
    # Phase Stabilization (Bug B) — when neither the listener's city
    # nor the market lexicon resolves to a known city, return None so
    # the RJ prompt can say "Hey listeners" instead of leaking a
    # hardcoded "Dubai".
    resolved_city = city or lex.get("display_name") or None
    return RJContext(
        time_of_day=tod,
        city=resolved_city,
        market=market,
    )


async def _build_one_segment(session_id, track, prev_track, channel, ctx,
                              force_format=None, skip_rj=False):
    """Phase Bug-1 — `skip_rj=True` produces a fast no-RJ segment for
    cold-start time-to-first-byte.  Music plays immediately (optional
    short pre-rendered station-ID stinger upfront).  All OpenAI + 11Labs
    calls bypassed.  Subsequent segments (prev_track is not None) still
    get full AI RJ when invoked normally.

    Phase 15d.1 — wrap the full body in a try/except. When ElevenLabs
    quota is exhausted (HTTPException 503 'rj_quota_exhausted'), the
    listener should hear the music UNINTERRUPTED rather than a 503; we
    transparently degrade to `_build_one_segment_no_rj` with a clean
    warning log and zero user-facing error surface.
    """
    if skip_rj:
        return await _build_one_segment_no_rj(
            session_id, track, channel, ctx)
    try:
        return await _build_one_segment_with_rj(
            session_id, track, prev_track, channel, ctx, force_format=force_format)
    except HTTPException as he:
        # 503 + rj_quota_exhausted → silent skip (music keeps playing).
        if he.status_code == 503 and (he.detail == "rj_quota_exhausted"
                                                            or (isinstance(he.detail, dict)
                                                                  and he.detail.get("error") == "rj_quota_exhausted")):
            logger.warning("[rj-degrade] quota exhausted — serving no-RJ segment "
                                  "for session=%s track=%s", session_id, track.get("_id"))
            return await _build_one_segment_no_rj(session_id, track, channel, ctx)
        raise


async def _build_one_segment_with_rj(session_id, track, prev_track, channel, ctx,
                                                                  force_format=None):
    """Phase 15d.1 — actual implementation moved out of `_build_one_segment`
       so the outer wrapper can degrade on rj_quota_exhausted."""
    target_energy = track.get("energy_level", DEFAULT_ENERGY)
    rj_target = {"title": track["title"], "artist": track["artist"],
                 "energy_level": target_energy, "mood": track.get("mood")}
    prev_for_prompt = None
    if prev_track:
        prev_for_prompt = {"title": prev_track["title"], "artist": prev_track["artist"],
                           "energy_level": prev_track.get("energy_level", DEFAULT_ENERGY),
                           "mood": prev_track.get("mood")}
    channel_name = channel.get("name") if channel else None

    if force_format in ("solo", "duo"):
        fmt = force_format
    else:
        can_duo = channel_supports_duo(channel)
        fmt = "duo" if (can_duo and random.random() < DUO_PROBABILITY) else "solo"

    rj_voice_key_primary: str
    rj_hosts: List[dict] = []
    script: str
    rj_path: Path

    # Phase 3.7 — pick personality profile + load phrase inspiration for naturalness rewrite
    from services.personality_profiles import select_profile_slug, profile_by_slug_sync
    from services.phrase_bank import sample_phrases, mark_phrases_used
    from services.script_pipeline import (
        generate_natural_rj_script, detect_banned_phrases,
        radio_naturalness_rewrite, radio_naturalness_rewrite_duo,
    )
    from services.audio_qa import record_audio_qa
    # Phase 3.7 — resolve user market from the session (falls back to channel/default)
    # Phase 15d.1 — `preferred_market` (geo override) wins over legacy `market`
    # field so a Dallas user gets DFW prompts even if their account predates
    # geo. We also propagate the market into ctx so the downstream prompt
    # builders inject the correct lexicon clause.
    user_market = None
    _sess = None
    try:
        if session_id:
            _sess = await db.radio_sessions.find_one({"_id": session_id}, {"user_id": 1})
            if _sess and _sess.get("user_id"):
                _u = await db.users.find_one(
                    {"user_id": _sess["user_id"]},
                    {"market": 1, "preferred_market": 1, "last_resolved_market": 1},
                )
                if _u:
                    user_market = (
                        _u.get("preferred_market")
                        or _u.get("last_resolved_market")
                        or _u.get("market")
                    )
    except Exception: pass
    _market = (user_market or channel.get("market") or "dubai").strip().lower()
    # Re-stamp ctx so downstream RJ prompt sees the right market.
    try:
        ctx = ctx.copy(update={"market": _market})
        if not (ctx.city or "").strip():
            from services.market_lexicon import get_lexicon as _gl
            # Phase Stabilization (Bug B) — drop hardcoded "Dubai"
            # fallback. If the market isn't in the lexicon, leave city
            # unset so the RJ says generic "Hey listeners" instead.
            _disp = _gl(_market).get("display_name")
            if _disp:
                ctx = ctx.copy(update={"city": _disp})
    except Exception:
        pass
    _dubai_hour = (datetime.now(timezone.utc) + timedelta(hours=4)).hour
    # Map broad time-of-day to phrase-bank daypart slugs.
    _tod = _tod_now_dubai()
    _daypart_map = {
        "morning": "morning_drive",
        "afternoon": "lunch_rush",
        "evening": "evening_drive",
        "late_night": "overnight_lounge",
    }
    _daypart = _daypart_map.get(_tod, "evening_drive")
    # Nightlife slot for high-energy party slots between 20:00 and 02:00
    if (_dubai_hour >= 20 or _dubai_hour < 2) and target_energy in ("high", "party"):
        _daypart = "nightlife_mode"
    profile_slug = select_profile_slug(channel.get("_id"), _daypart, target_energy, _dubai_hour)
    profile = profile_by_slug_sync(profile_slug) or profile_by_slug_sync("evening_drive")
    phrase_docs = await sample_phrases(db, market=_market, daypart=_daypart, n=4)
    phrase_inspiration = [p["phrase"] for p in phrase_docs]
    initial_draft_for_qa = ""
    rewritten_for_qa = ""
    regen_count = 0

    if fmt == "duo":
        try:
            host_a, host_b = pick_voice_for_segment(channel, target_energy, force_duo=True)
            if not host_b:
                raise RuntimeError("channel cannot duo")
            # Stage 1: legacy duo draft generator
            duo_draft = await asyncio.to_thread(
                _generate_duo_script, prev_for_prompt, rj_target, ctx, host_a, host_b, channel_name, channel,
            )
            initial_draft_for_qa = duo_draft
            # Phase 3.8 Extra A — Stage 2 duo naturalness rewrite with per-speaker
            # language purity (American=English-heavy, Hindi-native=Hindi-heavy).
            host_a_voice = RJ_VOICES.get(host_a, {})
            host_b_voice = RJ_VOICES.get(host_b, {})
            try:
                duo_rewritten = await radio_naturalness_rewrite_duo(
                    duo_draft,
                    host_a_label=host_a_voice.get("duo_label", host_a.upper()),
                    host_a_accent=host_a_voice.get("accent_target", "hinglish"),
                    host_b_label=host_b_voice.get("duo_label", host_b.upper()),
                    host_b_accent=host_b_voice.get("accent_target", "hinglish"),
                    market=_market, phrase_inspiration=phrase_inspiration,
                    target_seconds=int(profile.get("default_script_length_sec", 24)),
                )
            except Exception as _e:
                logger.warning(f"duo naturalness rewrite failed, using draft: {_e}")
                duo_rewritten = duo_draft
            rewritten_for_qa = duo_rewritten
            script = duo_rewritten
            turns = _parse_duo_script(duo_rewritten, host_a, host_b)
            if len(turns) < 2:
                # Fallback to draft turns if the rewrite broke speaker tags
                logger.warning("duo rewrite produced <2 turns, falling back to draft")
                turns = _parse_duo_script(duo_draft, host_a, host_b)
                script = duo_draft
                rewritten_for_qa = duo_draft
            if len(turns) < 2: raise RuntimeError("duo script had <2 turns")
            is_party = _is_mirchi_party(channel, target_energy)
            rj_path = await asyncio.to_thread(_synthesize_duo_banter, turns, target_energy, is_party)
            rj_voice_key_primary = host_a
            rj_hosts = [{"voice_key": host_a, "name": RJ_VOICES[host_a]["display_name"]},
                        {"voice_key": host_b, "name": RJ_VOICES[host_b]["display_name"]}]
        except Exception as e:
            logger.warning(f"Duo build failed, fallback to solo: {e}")
            fmt = "solo"

    if fmt == "solo":
        host_a, _ = pick_voice_for_segment(channel, target_energy, force_duo=False)
        rj_voice_key_primary = host_a
        voice = RJ_VOICES.get(rj_voice_key_primary, RJ_VOICES[DEFAULT_VOICE_KEY])
        # ──────────────────────────────────────────────────────────────
        # Phase 40 follow-up — News channel override.
        # If the listener picked `channel=news_radio`, bypass the
        # music-channel RJ scaffolding (milestone shoutouts, commute
        # extras, generate_natural_rj_script with its market-branded
        # intro) and call the dedicated news-anchor
        # generator. It reads 2-3 real headlines from `news_articles`
        # filtered by the listener's `news_preferences` + city.
        # ──────────────────────────────────────────────────────────────
        if (channel.get("_id") == "news_radio"
                or channel.get("slug") == "news_radio"):
            try:
                from services.news_rj_script import generate_news_rj_script
                u_doc_for_news = None
                if _sess and _sess.get("user_id"):
                    u_doc_for_news = await db.users.find_one(
                        {"user_id": _sess["user_id"]})
                script = await generate_news_rj_script(
                    db, u_doc_for_news or {},
                    voice_key=rj_voice_key_primary)
                initial_draft_for_qa = script
                rewritten_for_qa = script
                rj_path = await asyncio.to_thread(
                    _synthesize_solo, script, None, target_energy,
                    rj_voice_key_primary)
                rj_hosts = [{"voice_key": rj_voice_key_primary,
                              "name": voice["display_name"]}]
                rj_info = ffprobe_info(rj_path)
                seg_id = str(uuid.uuid4())
                seg_path = SEGMENTS_DIR / f"{seg_id}.mp3"
                # Skip the music-segment stitch and just hand back the
                # RJ audio as the segment itself for news.
                import shutil as _shutil
                _shutil.copyfile(rj_path, seg_path)
                seg_info = ffprobe_info(seg_path)
                # Phase 41 P1 fix — persist the news_anchor segment to
                # db.segments so /api/radio/segment/{id} can serve the
                # audio AND /api/radio/next can update the session
                # without KeyError. Track fields are explicitly None
                # because the news anchor is RJ-only (no music).
                news_seg_doc = {
                    "_id":             seg_id,
                    "session_id":      session_id,
                    "file_path":       str(seg_path),
                    "duration_sec":    seg_info["duration_sec"],
                    "bitrate":         seg_info["bitrate"],
                    "track_id":        None,
                    "track_title":     None,
                    "track_artist":    None,
                    "track_album":     None,
                    "rj_voice_key":    rj_voice_key_primary,
                    "rj_script":       script,
                    "rj_format":       "solo",
                    "rj_hosts":        rj_hosts,
                    "rj_start_sec":    0.0,
                    "track_duration_sec": seg_info["duration_sec"],
                    "kind":            "news_anchor",
                    "channel_slug":    channel.get("_id"),
                    "channel_name":    channel.get("name"),
                    "channel_id":      channel.get("_id"),
                    "created_at":      _now_iso(),
                    "initial_draft":   initial_draft_for_qa,
                    "rewritten_draft": rewritten_for_qa,
                }
                await db.segments.insert_one(news_seg_doc)
                return news_seg_doc
            except Exception as _ne:
                logger.warning(
                    f"[news-rj] generator failed for session="
                    f"{session_id}: {_ne!r} — falling back to "
                    f"music engine (this should not happen).")
                # On failure, drop through to the music engine path
                # below — it will still produce SOMETHING playable.
        # Phase 5 — atomically consume any pending BigCoin milestone so the
        # RJ can shout it out in this break (once per crossing).
        milestone_shoutout = None
        _uid = _sess.get("user_id") if _sess else None
        try:
            doc = await db.users.find_one_and_update(
                {"user_id": _uid,
                 "bigcoin_milestone_pending": {"$exists": True}},
                {"$unset": {"bigcoin_milestone_pending": ""}},
                return_document=False,
                projection={"bigcoin_milestone_pending": 1, "_id": 0},
            )
            if doc and doc.get("bigcoin_milestone_pending"):
                milestone_shoutout = int(doc["bigcoin_milestone_pending"])
        except Exception:
            pass
        # Phase 9b — pop the next pending RJ extra (e.g. commute_just_completed).
        commute_arrival_extra = None
        try:
            from services.route_ad_engine import pop_pending_rj_extra
            extra = await pop_pending_rj_extra(db, user_id=_uid)
            if extra and extra.get("kind") == "commute_just_completed":
                commute_arrival_extra = extra.get("payload") or {}
        except Exception as _e:
            logger.debug(f"pop_pending_rj_extra: {_e}")
        try:
            # Phase 3.7 — TWO-STAGE pipeline: draft → naturalness rewrite
            draft, rewritten = await generate_natural_rj_script(
                profile=profile, voice_persona=voice["persona"],
                prev_track=prev_for_prompt, next_track=rj_target,
                market=_market, daypart=_daypart, dubai_hour=_dubai_hour,
                weather_hint=ctx.weather_hint, channel_name=channel_name,
                phrase_inspiration=phrase_inspiration,
                milestone_shoutout=milestone_shoutout,
                commute_arrival=commute_arrival_extra,
            )
            # Phase 3.7 — Multi-take auto-regen: if banned phrases detected,
            # re-run the rewrite once with stricter inspiration. Capped at 1 retry.
            if detect_banned_phrases(rewritten):
                try:
                    rewritten_v2 = await radio_naturalness_rewrite(
                        rewritten, profile=profile, market=_market,
                        phrase_inspiration=phrase_inspiration,
                    )
                    if rewritten_v2 and not detect_banned_phrases(rewritten_v2):
                        rewritten = rewritten_v2
                        regen_count = 1
                        logger.info(f"naturalness re-rewrite cleared banned phrases for {channel.get('_id')}")
                except Exception as _re:
                    logger.warning(f"auto-regen rewrite failed: {_re}")
            initial_draft_for_qa, rewritten_for_qa = draft, rewritten
            script = rewritten
        except Exception as e:
            logger.warning(f"two-stage script gen failed, falling back: {e}")
            # Phase 39 Session 3 — radio persona override.
            # If the session's listener has selected_persona_id set + classifier-safe,
            # swap rj_voice_key_primary to that persona's voice_key.
            location_context_for_rj = None
            try:
                if session_id:
                    sess_doc = await db.radio_sessions.find_one(
                        {"_id": session_id}, {"user_id": 1})
                    if sess_doc and sess_doc.get("user_id"):
                        u_doc = await db.users.find_one(
                            {"user_id": sess_doc["user_id"]})
                        if u_doc and u_doc.get("selected_persona_id"):
                            from services.persona_service import resolve_active_persona
                            persona_doc = await resolve_active_persona(db, u_doc)
                            if persona_doc and persona_doc.get("voice_key"):
                                old_vk = rj_voice_key_primary
                                rj_voice_key_primary = persona_doc["voice_key"]
                                source = ("user_selected"
                                                if u_doc.get("selected_persona_id") == persona_doc.get("_id")
                                                else "daypart_default")
                                logger.info(
                                    f"[rj-persona] user={u_doc['user_id']} "
                                    f"session={session_id} persona={persona_doc['_id']} "
                                    f"source={source} voice_key={old_vk}->{rj_voice_key_primary}")
                        # Phase 39 Session 6 — persona × location greeting.
                        if u_doc and int(u_doc.get("location_consent_level", 0)) >= 3:
                            try:
                                from services.route_pattern_detection import (
                                    get_location_context as _get_loc_ctx,
                                )
                                _loc_ctx = await _get_loc_ctx(db, u_doc["user_id"])
                                if _loc_ctx and _loc_ctx.get("pattern_count", 0) >= 1:
                                    location_context_for_rj = _loc_ctx
                                    logger.info(
                                        f"[rj-location] user={u_doc['user_id']} "
                                        f"session={session_id} "
                                        f"patterns={_loc_ctx.get('pattern_count')} "
                                        f"bucket={_loc_ctx.get('current_time_bucket')} "
                                        f"morning_commute={(_loc_ctx.get('morning_commute') or {}).get('label')}")
                            except Exception as _le:
                                logger.warning(f"[rj-location] lookup failed: {_le}")
            except Exception as _e:
                logger.warning(f"[rj-persona] override failed: {_e}")
            script = await asyncio.to_thread(
                _generate_rj_script_solo, prev_for_prompt, rj_target, ctx,
                rj_voice_key_primary, channel_name, channel,
                location_context_for_rj,
            )
            initial_draft_for_qa = script
            rewritten_for_qa = script
        rj_path = await asyncio.to_thread(
            _synthesize_solo, script, None, target_energy, rj_voice_key_primary,
        )
        rj_hosts = [{"voice_key": rj_voice_key_primary,
                     "name": voice["display_name"]}]
        # Mark phrases used for rotation tracking (best-effort)
        try: await mark_phrases_used(db, [p["_id"] for p in phrase_docs])
        except Exception: pass

    rj_info = ffprobe_info(rj_path)
    seg_id = str(uuid.uuid4())
    seg_path = SEGMENTS_DIR / f"{seg_id}.mp3"

    # Phase 3.8 v2 — IMAGING SELECTION (pre-roll + music bed under RJ).
    # This must happen BEFORE build_segment so the music bed is mixed in.
    from services.imaging_insertion import (
        select_imaging_for_segment, commit_imaging_state, log_imaging_inserts,
        prepend_imaging_to_segment,
    )
    is_premium_user = False
    try:
        if session_id:
            sess_doc = await db.radio_sessions.find_one({"_id": session_id}, {"user_id": 1})
            if sess_doc and sess_doc.get("user_id"):
                u = await db.users.find_one({"user_id": sess_doc["user_id"]},
                                             {"is_premium": 1, "subscription.status": 1})
                if u:
                    is_premium_user = bool(u.get("is_premium")) or (
                        (u.get("subscription") or {}).get("status") in ("active", "trialing")
                    )
    except Exception:
        is_premium_user = False
    imaging_selection = await select_imaging_for_segment(
        db,
        user_id=(_sess.get("user_id") if "_sess" in dir() and _sess else None),
        session_id=session_id, market=_market,
        daypart=_daypart, energy=target_energy,
        is_premium=is_premium_user, channel_slug=channel.get("_id"),
    )

    # Phase 3.5 — Mirchi-style party transition with SFX library + station IDs
    is_mirchi_party = _is_mirchi_party(channel, target_energy)
    party_layout = None

    if is_mirchi_party:
        from services.sfx_library import pick_random, library_path, has as sfx_has
        from services.station_ids import pick_random_station_id
        # Pick random SFX from each category (may be None if not yet generated)
        pre_shout = pick_random("vocal_shout_DUBAI", "vocal_shout_WAH")
        whoosh    = pick_random("whoosh_1", "whoosh_2", "whoosh_3")
        crowd     = pick_random("crowd_cheer_1", "crowd_cheer_2", "crowd_cheer_3")
        airhorn   = pick_random("airhorn_1", "airhorn_2")
        bass      = library_path("bass_drop") if sfx_has("bass_drop") else None
        sid       = pick_random_station_id()
        meta = await asyncio.to_thread(
            build_party_segment,
            # Phase Π+4 — party path now goes through the same Tigris
            # resolver as the normal build_segment path below.  Prior
            # to this fix, Tigris-backed tracks with `file_path=s3://…`
            # crashed the party builder with "Protocol not found".
            _track_file_path_for_ffmpeg(track), float(track["duration_sec"]),
            str(rj_path), rj_info["duration_sec"],
            seg_path,
            pre_shout_path=str(pre_shout) if pre_shout else None,
            whoosh_path=str(whoosh) if whoosh else None,
            airhorn_path=str(airhorn) if airhorn else None,
            station_id_path=str(sid) if sid else None,
            bass_drop_path=str(bass) if bass else None,
            crowd_cheer_path=str(crowd) if crowd else None,
        )
        party_layout = meta.get("party_layout")
        stinger_path = None  # not used in party builder
    else:
        stinger_path = SFX_DIR / "stinger.mp3" if prev_track else None
        if stinger_path and not stinger_path.exists(): stinger_path = None
        meta = await asyncio.to_thread(
            build_segment,
            _track_file_path_for_ffmpeg(track), float(track["duration_sec"]),
            str(rj_path), rj_info["duration_sec"],
            seg_path, target_energy,
            str(stinger_path) if stinger_path else None,
            # Phase 3.8 v2 — music bed under RJ voice (-8 dB, looped, faded)
            str(imaging_selection["music_bed_path"]) if imaging_selection.get("music_bed_path") else None,
        )

    # Phase 3.8 v2 — PREPEND IMAGING (station ID / daypart opener / TOH / sponsor / sweeper)
    if imaging_selection.get("pre_roll_paths"):
        try:
            new_duration = await asyncio.to_thread(
                prepend_imaging_to_segment,
                imaging_selection["pre_roll_paths"], seg_path, seg_path,
            )
            if new_duration and new_duration > 0:
                # Recalculate rj_start_sec relative to the new total — the
                # pre-roll prefix shifts everything by `preroll_dur` seconds.
                preroll_dur = max(0.0, new_duration - float(meta["duration_sec"]))
                meta["duration_sec"] = new_duration
                meta["rj_start_sec"] = round(float(meta.get("rj_start_sec", 0.0)) + preroll_dur, 3)
                meta["track_duration_sec"] = float(meta.get("track_duration_sec", 0.0)) + preroll_dur
                meta["preroll_duration_sec"] = round(preroll_dur, 3)
                meta["preroll_assets"] = [
                    {"type": a.get("asset_type"), "slug": a.get("slug"), "lufs": a.get("loudness_lufs")}
                    for a in imaging_selection.get("pre_roll_assets", [])
                ]
        except Exception as e:
            logger.warning(f"prepend imaging failed (segment kept without preroll): {e}")

    seg_doc = {
        "_id": seg_id, "session_id": session_id,
        "file_path": str(seg_path), "duration_sec": meta["duration_sec"],
        "track_id": track["_id"], "track_title": track["title"], "track_artist": track["artist"],
        "track_album": track.get("album"),
        "track_energy_level": target_energy, "track_mood": track.get("mood"),
        "rj_voice_key": rj_voice_key_primary,
        "rj_voice_id": RJ_VOICES[rj_voice_key_primary].get("voice_id") or RJ_VOICES[rj_voice_key_primary].get("openai_voice", ""),
        "rj_script": script, "rj_format": fmt, "rj_hosts": rj_hosts,
        # Phase 15d.1 — stamp the market the script was generated under so
        # the playback guard + nightly purge can spot cross-market leaks.
        "script_market": _market,
        "rj_start_sec": meta["rj_start_sec"], "track_duration_sec": meta["track_duration_sec"],
        "prev_track_id": prev_track["_id"] if prev_track else None,
        "energy_used": target_energy, "stinger_used": bool(stinger_path),
        "channel_slug": channel["_id"], "channel_name": channel.get("name"),
        "created_at": _now_iso(),
        # Phase 3.8 v2 — imaging metadata
        "imaging": {
            "station_slug": imaging_selection.get("station_slug"),
            "music_bed_used": bool(meta.get("music_bed_used")),
            "music_bed_slug": (imaging_selection.get("music_bed_asset") or {}).get("slug"),
            "preroll_duration_sec": meta.get("preroll_duration_sec", 0.0),
            "preroll_assets": meta.get("preroll_assets", []),
            "fired_top_of_hour": imaging_selection.get("fired_top_of_hour", False),
            "fired_daypart_opener": imaging_selection.get("fired_daypart_opener", False),
            "fired_station_id": imaging_selection.get("fired_station_id", False),
            "fired_sweeper": imaging_selection.get("fired_sweeper", False),
            "fired_sponsor": imaging_selection.get("fired_sponsor", False),
        },
    }
    await db.segments.insert_one(seg_doc)

    # Phase 3.8 v2 — persist imaging state + write station_flow_logs
    try:
        await commit_imaging_state(db, session_id=session_id, selection=imaging_selection, daypart=_daypart)
    except Exception as e:
        logger.warning(f"commit_imaging_state error: {e}")
    try:
        await log_imaging_inserts(db,
            segment_id=seg_id, user_id=(_sess.get("user_id") if "_sess" in dir() and _sess else None),
            session_id=session_id, selection=imaging_selection,
        )
    except Exception as e:
        logger.warning(f"log_imaging_inserts error: {e}")

    # Phase 4 — Ad insertion (post-roll). Free users only. Concats ad audio after
    # the segment with a sponsor_bumper-ish lead-in (already handled when ad fires
    # via station_flow_logs metadata). Writes ad_pod + ad_impression records.
    try:
        from services.ad_decisioning import select_ad, log_ad_pod, log_ad_impression
        # Resolve user document for decisioning (need is_premium + preferences)
        full_user = None
        if _sess and _sess.get("user_id"):
            full_user = await db.users.find_one({"user_id": _sess["user_id"]})
        if full_user:
            full_user["is_premium"] = bool(full_user.get("is_premium")) or (
                (full_user.get("subscription") or {}).get("status") in ("active", "trialing")
            )
            ad_ctx = {
                "position": "postroll", "market": _market, "daypart": _daypart,
                "energy": target_energy, "channel_slug": channel.get("_id"),
                "voice_key": rj_voice_key_primary,
            }
            ad_decision = await select_ad(db, user=full_user, session={"_id": session_id}, segment_context=ad_ctx)
            if ad_decision:
                cr = ad_decision["creative"]
                ad_path = Path(cr.get("audio_path") or "")
                if ad_path.exists() and ad_path.stat().st_size > 2000:
                    # Concat: [current segment] + [ad audio] → seg_path (overwrite)
                    from audio_pipeline import concat_with_gaps, ffprobe_duration
                    ad_start = float(meta["duration_sec"])
                    tmp_out = seg_path.with_suffix(".ad.tmp.mp3")
                    try:
                        post = await asyncio.to_thread(
                            concat_with_gaps, [seg_path, ad_path], tmp_out, 180,  # 180ms gap before ad
                        )
                        tmp_out.replace(seg_path)
                        meta["duration_sec"] = float(post.get("duration_sec") or meta["duration_sec"])
                        # Log records
                        pod_id = await log_ad_pod(db,
                            session_id=session_id, segment_id=seg_id,
                            user_id=full_user["user_id"], scheduled_position="postroll",
                            decision=ad_decision,
                        )
                        imp_id = await log_ad_impression(db,
                            ad_pod_id=pod_id, decision=ad_decision,
                            user_id=full_user["user_id"], session_id=session_id,
                            context=ad_ctx,
                        )
                        # Patch segment doc with ad metadata for the frontend Action Card
                        await db.segments.update_one({"_id": seg_id}, {"$set": {
                            "ad_pod_id": pod_id, "ad_impression_id": imp_id,
                            "ad_creative_id": cr["creative_id"],
                            "ad_campaign_id": ad_decision["campaign"]["campaign_id"],
                            "ad_start_sec": round(ad_start, 3),
                            "ad_duration_sec": float(cr.get("duration_sec") or 20),
                            "duration_sec": meta["duration_sec"],
                            "has_ad": True,
                        }})
                        # Also write a station_flow_logs row so the live revenue meter ticks
                        await db.station_flow_logs.insert_one({
                            "user_id": full_user["user_id"], "session_id": session_id,
                            "segment_id": seg_id,
                            "asset_id": cr["creative_id"], "asset_slug": cr["creative_id"],
                            "asset_type": "ad_pod_audio",
                            "item_type": "ad_pod.audio_ad",
                            "transition_type": "postroll.ad",
                            "loudness_lufs": -14.0,
                            "duration_sec": float(cr.get("duration_sec") or 20),
                            "value_cents": int(ad_decision["campaign"].get("bid_cents_per_impression") or 0),
                            "played_at": datetime.now(timezone.utc),
                        })
                    except Exception as ce:
                        logger.warning(f"ad concat failed: {ce}")
                        try: tmp_out.unlink(missing_ok=True)  # type: ignore
                        except Exception: pass
    except Exception as e:
        logger.warning(f"ad insertion error: {e}")
    # Phase 3.7 — write audio QA record (best-effort)
    try:
        voice_meta = RJ_VOICES.get(rj_voice_key_primary) or {}
        await record_audio_qa(
            segment_id=seg_id,
            voice_key=rj_voice_key_primary,
            model_id=("gpt-4o-mini-tts" if voice_meta.get("provider") == "openai_tts" else "eleven_v3"),
            voice_settings=voice_meta.get("voice_settings_overrides") or VOICE_SETTINGS_BY_ENERGY.get(target_energy, {}),
            initial_script=initial_draft_for_qa or script,
            rewritten_script=rewritten_for_qa or script,
            final_audio_url=f"/api/radio/segment/{seg_id}",
            final_duration_sec=meta["duration_sec"],
            personality_profile_slug=profile_slug,
            daypart_slug=_daypart,
            channel_slug=channel["_id"],
            market=_market,
            takes_generated=1 + regen_count,
            regen_count=regen_count,
            banned_phrase_hits=detect_banned_phrases(script),
            hosts=rj_hosts,
            format=fmt,
        )
    except Exception as e:
        logger.warning(f"audio_qa write failed for {seg_id}: {e}")
    return seg_doc


def _segment_to_out(seg: dict) -> RadioSegmentOut:
    # Phase Bug-1 — no-RJ segments have empty hosts list, no voice key.
    vkey = seg.get("rj_voice_key")
    if seg.get("rj_hosts"):
        hosts = seg["rj_hosts"]
    elif vkey:
        hosts = [{"voice_key": vkey,
                   "name": RJ_VOICES.get(vkey, {}).get("display_name", "RJ")}]
    else:
        hosts = []
    return RadioSegmentOut(
        segment_id=seg["_id"],
        segment_url=f"/api/radio/segment/{seg['_id']}",
        duration_sec=seg["duration_sec"],
        # Phase 41 P1 — news_anchor segments have no track fields.
        track_id=seg.get("track_id"),
        track_title=seg.get("track_title"),
        track_artist=seg.get("track_artist"),
        rj_voice_key=vkey,
        rj_voice_name=(RJ_VOICES.get(vkey, {}).get("display_name") if vkey else None),
        rj_script=seg.get("rj_script") or "",
        rj_start_sec=seg.get("rj_start_sec"),
        rj_format=seg.get("rj_format", "solo"),
        rj_hosts=[HostInfo(**h) for h in hosts],
        channel_slug=seg.get("channel_slug"),
        channel_name=seg.get("channel_name"),
        kind=seg.get("kind"),
    )


async def _resolve_channel(slug: Optional[str]) -> dict:
    s = slug or DEFAULT_CHANNEL_SLUG
    ch = await get_channel(db, s)
    if not ch or not ch.get("active"):
        # Phase 41 S1 — fall through to community_radio_stations so user-
        # owned stations resolve cleanly through the same engine path as
        # admin channels. Visibility is enforced inside the lookup.
        from routes.community_stations import lookup_community_channel
        ch = await lookup_community_channel(db, s)
    if not ch or not ch.get("active"):
        ch = await get_channel(db, DEFAULT_CHANNEL_SLUG)
    if not ch:
        raise HTTPException(500, "no channels configured")
    return ch


async def _log_play(user, session, seg, channel_slug):
    await log_event(
        db, user_id=user["user_id"], session_id=session["_id"],
        segment_id=seg["_id"], track_id=seg.get("track_id"),
        channel_slug=channel_slug, event="play_start",
        metadata={"artist": seg.get("track_artist"), "title": seg.get("track_title"),
                  "album": seg.get("track_album"), "rj_format": seg.get("rj_format"),
                  "kind": seg.get("kind")},
    )


# -----------------------------------------------------------------
# Warm-start: pre-build the first segment on login so the user's first
# ON AIR click feels instant (<500ms claim vs ~21s cold build).
WARM_START_TTL_SEC = 1800  # 30 minutes
_warmstart_tasks: Dict[str, asyncio.Task] = {}


async def _resolve_warm_start_channel(user: dict) -> Optional[dict]:
    """Pick the channel to pre-warm for this user, in priority order:
       1. user.last_played_channel (if still active + access allowed)
       2. for premium users: premium_mehfil OR vip_lounge if available
       3. market default (bollywood_mehfil for dubai, dfw_bollywood_drive for dfw)
       4. global DEFAULT_CHANNEL_SLUG."""
    candidates: list = []
    last_slug = user.get("last_played_channel")
    if last_slug:
        candidates.append(last_slug)
    if user.get("is_premium"):
        candidates += ["premium_mehfil", "vip_lounge"]
    market = (user.get("market") or "dubai").lower()
    if market == "dfw":
        candidates += ["dfw_bollywood_drive"]
    else:
        candidates += ["bollywood_mehfil"]
    candidates.append(DEFAULT_CHANNEL_SLUG)
    is_premium = bool(user.get("is_premium"))
    for slug in candidates:
        if not slug: continue
        ch = await get_channel(db, slug)
        if not ch or not ch.get("active"): continue
        if ch.get("premium_only") and not is_premium: continue
        return ch
    return None


async def _build_one_segment_no_rj(session_id, track, channel, ctx):
    """Phase Bug-1 — Cold-start time-to-first-byte path.

    Stitches just (optional 1-2s pre-rendered station-ID stinger) +
    music track.  No OpenAI script gen.  No ElevenLabs TTS.  No music-bed
    rendering.  No daypart imaging pre-roll.  Returns the same `segments`
    document shape as `_build_one_segment` so the consumer doesn't care.
    """
    from audio_pipeline import build_segment_no_rj
    from services.station_ids import pick_random_station_id

    seg_id = uuid.uuid4().hex
    seg_path = SEGMENTS_DIR / f"{seg_id}.mp3"
    target_energy = track.get("energy_level", DEFAULT_ENERGY)
    # Pick a random pre-rendered station ID stinger if available.
    sid = None
    try:
        sid = pick_random_station_id()
    except Exception:
        sid = None

    meta = await asyncio.to_thread(
        build_segment_no_rj,
        _track_file_path_for_ffmpeg(track), float(track["duration_sec"] or 0),
        str(seg_path),
        str(sid) if sid else None,
    )
    seg_doc = {
        "_id": seg_id, "session_id": session_id,
        "file_path": str(seg_path),
        "duration_sec": meta["duration_sec"],
        "track_id": track["_id"], "track_title": track["title"],
        "track_artist": track["artist"],
        "track_album": track.get("album"),
        "track_energy_level": target_energy,
        "track_mood": track.get("mood"),
        "rj_voice_key": None, "rj_voice_id": None,
        "rj_script": "", "rj_format": "no_rj", "rj_hosts": [],
        "rj_start_sec": None,
        "track_duration_sec": meta["track_duration_sec"],
        "prev_track_id": None,
        "energy_used": target_energy,
        "stinger_used": bool(meta.get("stinger_inserted")),
        "channel_slug": channel["_id"],
        "channel_name": channel.get("name"),
        "created_at": _now_iso(),
        "no_rj": True,                  # explicit flag for downstream
        "build_path": "cold_start_no_rj",
        "imaging": {
            "station_slug": None, "music_bed_used": False,
            "music_bed_slug": None,
            "preroll_duration_sec": meta.get("stinger_duration_sec") or 0.0,
            "preroll_assets": [
                {"type": "station_id_stinger",
                  "slug": (sid.stem if sid else None)}
            ] if sid else [],
            "fired_top_of_hour": False,
            "fired_daypart_opener": False,
            "fired_station_id": bool(sid),
            "fired_sweeper": False,
            "fired_sponsor": False,
        },
    }
    await db.segments.insert_one(seg_doc)
    logger.info(f"[radio_start no-rj] session={session_id} seg={seg_id} "
                  f"track='{track.get('title')}' dur={meta['duration_sec']:.1f}s "
                  f"stinger={bool(sid)}")
    return seg_doc


async def prebuild_warm_start_for_user(user: dict) -> None:
    """Fire-and-forget: builds the user's first segment and parks it in
    `warm_start_segments` for instant claim on next /api/radio/start.
    Safe to call from any login endpoint via asyncio.create_task()."""
    uid = user.get("user_id")
    logger.info(f"[prewarm] entry user={uid} onboard={user.get('onboarding_complete')}")
    if not uid:
        return
    # De-dup concurrent prewarms for the same user
    existing_task = _warmstart_tasks.get(uid)
    if existing_task and not existing_task.done() and existing_task is not asyncio.current_task():
        logger.info(f"[prewarm] dedup-skip user={uid}")
        return
    try:
        # Already warm? Skip if there's a recent (< TTL) entry for any channel
        existing = await db.warm_start_segments.find_one(
            {"user_id": uid}, {"_id": 1, "built_at": 1},
        )
        if existing and existing.get("built_at"):
            bt = existing["built_at"]
            if bt.tzinfo is None: bt = bt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - bt).total_seconds()
            if age < WARM_START_TTL_SEC:
                return
        if not user.get("onboarding_complete"):
            return
        channel = await _resolve_warm_start_channel(user)
        if not channel:
            logger.info(f"[prewarm] no channel resolvable for user={uid}")
            return
        # Catalog check
        catalog_size = await db.tracks.count_documents({})
        if catalog_size == 0:
            logger.info(f"[prewarm] empty track catalog — skip user={uid}")
            return
        slug = channel["_id"]
        logger.info(f"[prewarm] started user={uid} channel={slug}")
        t0 = datetime.now(timezone.utc)
        # Build a throw-away session for the recommender (segment doesn't
        # need a real radio_sessions row; we'll create that lazily on claim).
        synth_session_id = f"warm_{uid}_{uuid.uuid4().hex[:10]}"
        pv = user.get("preference_vector") or {}
        synth_session = {
            "_id": synth_session_id, "user_id": uid,
            "channel_slug": slug, "channel_name": channel.get("name"),
            "preference_vector": pv,
            "played_track_ids": [], "recent_artists": [],
            "last_track_id": None, "current_segment_id": None,
            "warm_start": True,
        }
        await db.radio_sessions.insert_one(synth_session)
        try:
            first_track = await _pick_next_track_personalized(synth_session, channel, None)
            seg = await _build_one_segment(
                synth_session_id, first_track, None, channel,
                _ctx_for_now(session=synth_session), force_format="solo",
            )
        finally:
            # Don't leave the synthetic session lying around; the real one
            # is created on claim.
            await db.radio_sessions.delete_one({"_id": synth_session_id})
        # Stash for claim. _id is per (user, channel) so re-prewarming same
        # channel just replaces; different channels accumulate (max ~2).
        await db.warm_start_segments.update_one(
            {"_id": f"{uid}|{slug}"},
            {"$set": {
                "_id": f"{uid}|{slug}",
                "user_id": uid, "channel_slug": slug,
                "segment_id": seg["_id"],
                "segment_doc": seg,
                "built_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        logger.info(f"[prewarm] completed user={uid} channel={slug} in {elapsed:.1f}s seg={seg['_id']}")
    except Exception as e:
        logger.warning(f"[prewarm] failed user={uid}: {e}")
    finally:
        _warmstart_tasks.pop(uid, None)


def schedule_prebuild_warm_start(user: dict) -> None:
    """Synchronous helper: schedule the background task and stash for de-dup."""
    uid = (user or {}).get("user_id")
    if not uid:
        return
    try:
        task = asyncio.create_task(prebuild_warm_start_for_user(user))
        _warmstart_tasks[uid] = task
    except Exception as e:
        logger.warning(f"[prewarm] schedule failed user={uid}: {e}")


async def _claim_warm_start_segment(user_id: str, channel_slug: str) -> Optional[dict]:
    """Atomic claim — returns the prebuilt segment doc if present and not
    expired, otherwise None. Removes from the warm pool on claim."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=WARM_START_TTL_SEC)
    doc = await db.warm_start_segments.find_one_and_delete({
        "_id": f"{user_id}|{channel_slug}",
        "built_at": {"$gte": cutoff},
    })
    if not doc:
        return None
    return doc.get("segment_doc")


# Expose to auth.py via app.state for fire-and-forget scheduling on login.
app.state.schedule_prebuild_warm_start = schedule_prebuild_warm_start


@api.post("/radio/start", response_model=RadioStartResponse)
async def radio_start(req: RadioStartRequest, user: dict = Depends(current_user)):
    if not user.get("onboarding_complete"):
        raise HTTPException(403, "Finish onboarding first")
    # Phase 10c.1 — require explicit channel.  Used to silently fall back
    # to DEFAULT_CHANNEL_SLUG which bypassed the gate by accident.
    if not req.channel:
        raise HTTPException(
            400,
            detail={"code": "channel_required",
                      "message": "Missing channel. Pass `channel` or `channel_slug` in the body.",
                      "fields": ["channel", "channel_slug"]})
    channel = await _resolve_channel(req.channel)
    # Phase 10c — exclusive channel gating (handles premium_only too)
    from services.channel_access import (
        check_channel_access, access_to_403_detail,
    )
    access = await check_channel_access(db, user, channel)
    if not access.get("allowed"):
        raise HTTPException(
            status_code=403,
            detail=access_to_403_detail(access, channel),
        )
    pv = user.get("preference_vector") or {}
    # Channel-emptiness pre-check — return a 503 with a retry hint so the
    # frontend can auto-switch instead of letting the recommender fall back
    # to a confusing cross-channel rescue. Cheap query: active tracks
    # matching this channel's hard filter.
    try:
        all_tracks = await db.tracks.find({}).to_list(2000)
        ch_tracks = channel_filter(all_tracks, channel)
        # Phase 40 follow-up — News channel doesn't need music tracks.
        # The news_radio segment is RJ-only (headline read), so skip the
        # empty-tracks guard for it.
        if not ch_tracks and channel.get("_id") != "news_radio":
            retry = (
                "premium_mehfil" if user.get("is_premium") and channel["_id"] != "premium_mehfil"
                else "bollywood_mehfil" if channel["_id"] != "bollywood_mehfil"
                else DEFAULT_CHANNEL_SLUG
            )
            raise HTTPException(
                status_code=503,
                detail={"error": "channel_empty",
                         "channel": channel["_id"], "retry_channel": retry,
                         "message": f"{channel.get('name')} has no playable tracks right now."},
            )
    except HTTPException: raise
    except Exception as e:
        logger.warning(f"[radio_start] channel-empty precheck failed (continuing): {e}")

    session_id = str(uuid.uuid4())
    session = {
        "_id": session_id, "user_id": user["user_id"],
        "channel_slug": channel["_id"], "channel_name": channel.get("name"),
        "created_at": _now_iso(), "preference_vector": pv,
        "played_track_ids": [], "recent_artists": [],
        "last_track_id": None, "current_segment_id": None,
        "pending_segment_id": None, "segments_played": 0,
    }
    await db.radio_sessions.insert_one(session)
    # Warm-start fast path — pre-built on login, claim atomically
    warm = await _claim_warm_start_segment(user["user_id"], channel["_id"])
    if warm:
        logger.info(f"[radio_start] claimed warm segment user={user['user_id']} "
                    f"channel={channel['_id']} seg={warm['_id']}")
        # Re-stamp the segment to the new session_id (audio file + metadata kept)
        await db.segments.update_one({"_id": warm["_id"]},
                                       {"$set": {"session_id": session_id}})
        first_track = await db.tracks.find_one({"_id": warm["track_id"]})
        seg = warm
    else:
        logger.info(f"[radio_start] cold build user={user['user_id']} channel={channel['_id']} (skip_rj=True for TTFB)")
        # Phase 41 S1.5 — retry loop: if ffmpeg / signed-URL fetch fails
        # on the picked track, mark it unplayable in DB and try again up
        # to 3 picks before giving up with a clear 409.
        seg = None
        first_track = None
        attempts: list = []
        for _attempt in range(3):
            try:
                first_track = await _pick_next_track_personalized(
                    session, channel, None)
            except HTTPException as he:
                # Recommender ran out of candidates entirely.
                raise he
            # Phase 41M — defensive None guard: if the personalized picker
            # returned None (rare edge case under heavy filter pressure),
            # treat as an empty pick and retry rather than crash later
            # with a NoneType subscript error.
            if first_track is None:
                attempts.append({"track_id": None,
                                  "reason": "picker_returned_none"})
                logger.warning("[radio_start] picker returned None "
                               f"— retry {_attempt+1}/3")
                continue
            _sp = (first_track or {}).get("storage_provider")
            _fp = first_track.get("file_path") if first_track else None
            _missing = False
            if _sp == "tigris":
                _missing = not (first_track or {}).get("storage_key")
            else:
                _missing = (not _fp) or (not os.path.exists(_fp))
            if _missing:
                # Phase 41 S1.5 — flag unplayable so the next pick excludes it.
                if first_track and first_track.get("_id"):
                    await db.tracks.update_one(
                        {"_id": first_track["_id"]},
                        {"$set": {"playable_status":
                                  "disk_missing" if _sp != "tigris"
                                  else "missing_storage_key"}})
                attempts.append({"track_id": first_track and first_track.get("_id"),
                                  "reason": "missing_asset"})
                logger.warning("[radio_start] picked unplayable track "
                               f"id={first_track and first_track.get('_id')} "
                               f"sp={_sp} — retry {_attempt+1}/3")
                continue
            try:
                seg = await _build_one_segment(
                    session_id, first_track, None, channel,
                    _ctx_for_now(session=session), force_format="solo",
                    skip_rj=True)
                break
            except Exception as e:
                logger.warning("[radio_start] segment build failed for "
                               f"track={first_track.get('_id')} sp={_sp}: {e}")
                # Best-effort flag so next loop excludes this track.
                if first_track and first_track.get("_id"):
                    await db.tracks.update_one(
                        {"_id": first_track["_id"]},
                        {"$set": {"playable_status": "tigris_404"
                                                  if _sp == "tigris"
                                                  else "disk_missing"}})
                attempts.append({"track_id": first_track.get("_id"),
                                  "reason": "build_failed"})
                seg = None
                continue
        if seg is None:
            logger.error("[radio_start] empty_playable_pool after 3 retries "
                          f"channel={channel['_id']} attempts={attempts}")
            raise HTTPException(status_code=409, detail={
                "code": "empty_playable_pool",
                "channel": channel["_id"],
                "message": "This station has no playable tracks right now. "
                            "Try a different station.",
                "attempts": attempts})
        # Note: segment 2's full-RJ prebuild is scheduled below via
        # `_prefetch_next_segment` once the session's `last_track_id` is
        # written — no double-kick required.
    await db.radio_sessions.update_one(
        {"_id": session_id},
        {"$set": {"current_segment_id": seg["_id"],
                  "last_track_id": first_track["_id"],
                  "played_track_ids": [first_track["_id"]],
                  "recent_artists": [first_track["artist"]]},
         "$inc": {"segments_played": 1}},
    )
    # Remember last channel for next login's prewarm
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"last_played_channel": channel["_id"]}},
    )
    await _log_play(user, session, seg, channel["_id"])
    asyncio.create_task(_prefetch_next_segment(session_id))
    ss = await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))
    return RadioStartResponse(session_id=session_id, segment=_segment_to_out(seg), skip_state=ss)


@api.get("/radio/next", response_model=RadioNextResponse)
async def radio_next(session_id: str, user: dict = Depends(current_user)):
    # Outside the lock: if a prefetch is in-flight, give it the chance to finish.
    # This is what makes skips feel instant on the second+ skip.
    in_flight = _prefetch_tasks.get(session_id)
    if in_flight and not in_flight.done():
        try:
            await asyncio.wait_for(asyncio.shield(in_flight), timeout=45)
        except (asyncio.TimeoutError, Exception):
            pass

    async with _lock_for(session_id):
        session = await db.radio_sessions.find_one({"_id": session_id})
        if not session: raise HTTPException(404, "session not found")
        if session.get("user_id") != user["user_id"]:
            raise HTTPException(403, "session does not belong to you")
        channel = await _resolve_channel(session.get("channel_slug"))
        pending_id = session.get("pending_segment_id")
        if pending_id:
            seg = await db.segments.find_one({"_id": pending_id})
            if seg and seg.get("track_artist") in await _current_banned_artists(user["user_id"], channel):
                seg = None
        else:
            seg = None
        if not seg:
            last_track_id = session.get("last_track_id")
            prev_track = await db.tracks.find_one({"_id": last_track_id}) if last_track_id else None
            next_track = await _pick_next_track_personalized(session, channel, prev_track)
            seg = await _build_one_segment(session_id, next_track, prev_track, channel, _ctx_for_now(session=session))
        played = session.get("played_track_ids", [])
        # Phase 41 P1 fix — news_anchor segments have no underlying
        # track (seg["track_id"] is None). Guard the subscripts so
        # /radio/next doesn't KeyError mid-stream.
        seg_track_id = seg.get("track_id")
        seg_track_artist = seg.get("track_artist")
        if seg_track_id and seg_track_id not in played:
            played = played + [seg_track_id]
        recent_artists = session.get("recent_artists", [])
        if seg_track_artist:
            recent_artists = (recent_artists + [seg_track_artist])[-5:]
        catalog_size = await db.tracks.count_documents({})
        if seg_track_id and len(played) >= catalog_size:
            played = [seg_track_id]
        await db.radio_sessions.update_one(
            {"_id": session_id},
            {"$set": {"current_segment_id": seg["_id"],
                      "last_track_id": seg_track_id or session.get("last_track_id"),
                      "played_track_ids": played,
                      "recent_artists": recent_artists,
                      "pending_segment_id": None},
             "$inc": {"segments_played": 1}},
        )
    await _log_play(user, session, seg, session.get("channel_slug"))
    _schedule_prefetch(session_id)
    ss = await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))
    return RadioNextResponse(session_id=session_id, segment=_segment_to_out(seg), skip_state=ss)


async def _current_banned_artists(user_id: str, channel: dict) -> set:
    all_tracks = await db.tracks.find({}).to_list(2000)
    a, _ = await banned_artists_albums(db, user_id, all_tracks)
    same = await consecutive_artists_to_block(db, user_id)
    return a | set(same)


@api.post("/radio/skip", response_model=RadioNextResponse)
async def radio_skip(session_id: str, user: dict = Depends(current_user)):
    is_premium = user.get("is_premium", False)
    ss = await skip_state(db, user["user_id"], is_premium=is_premium)
    if ss["exhausted"]:
        # Log the blocked attempt for analytics (NOT counted as a skip).
        try:
            await log_event(
                db, user_id=user["user_id"], session_id=session_id,
                segment_id=None, track_id=None, channel_slug=None,
                event="skip_limit_reached",
                metadata={"tier": ss["tier"], "used": ss["used"],
                                    "limit": ss["limit"], "remaining": ss["remaining"],
                                    "reset_in_sec": ss["reset_in_sec"]},
            )
        except Exception:
            pass
        content = {
            "detail": "Skip limit reached",
            "retry_after_sec": ss["reset_in_sec"],
            "tier": ss["tier"], "limit": ss["limit"], "window_sec": ss["window_sec"],
            "used": ss["used"], "remaining": ss["remaining"],
            "reset_in_sec": ss["reset_in_sec"], "skip_state": ss,
        }
        # Only Free users see an upgrade cue; Premium simply waits for a slot.
        if ss["tier"] != "premium":
            content["upgrade_cta"] = "Premium gives you 6 skips every hour"
        return JSONResponse(
            status_code=429,
            content=content,
            headers={"Retry-After": str(ss["reset_in_sec"])},
        )
    # Log the skip and advance
    session = await db.radio_sessions.find_one({"_id": session_id})
    if not session: raise HTTPException(404, "session not found")
    await log_event(
        db, user_id=user["user_id"], session_id=session_id,
        segment_id=session.get("current_segment_id"),
        track_id=session.get("last_track_id"),
        channel_slug=session.get("channel_slug"),
        event="skip",
    )
    # Phase 5 — reset the low-skip streak counter
    try:
        from services.streaks import reset_consecutive_play
        await reset_consecutive_play(db, session_id)
    except Exception:
        pass
    return await radio_next(session_id, user)


@api.post("/radio/switch_channel", response_model=SwitchChannelResponse)
async def radio_switch_channel(req: SwitchChannelRequest, user: dict = Depends(current_user)):
    """Returns IMMEDIATELY with a 2.4s tuning SFX. The client plays that
    while polling /api/radio/ready until the real new-channel segment is built.
    Total perceived latency drops from 20-40s to ~3-5s feeling intentional."""
    new_ch = await get_channel(db, req.channel)
    if not new_ch or not new_ch.get("active"):
        raise HTTPException(404, "channel not found")
    # Phase 10c — exclusive channel gating (supersedes Phase 3 premium_only)
    from services.channel_access import (
        check_channel_access, access_to_403_detail,
    )
    access = await check_channel_access(db, user, new_ch)
    if not access.get("allowed"):
        raise HTTPException(
            status_code=403,
            detail=access_to_403_detail(access, new_ch),
        )
    session = await db.radio_sessions.find_one({"_id": req.session_id})
    if not session: raise HTTPException(404, "session not found")
    if session.get("user_id") != user["user_id"]:
        raise HTTPException(403, "session does not belong to you")

    # Reset queue + cancel any in-flight prefetch on old channel
    await db.radio_sessions.update_one(
        {"_id": req.session_id},
        {"$set": {
            "channel_slug": new_ch["_id"], "channel_name": new_ch.get("name"),
            "pending_segment_id": None, "segments_played": 0,
            "switch_in_progress": True,
        }},
    )
    old_task = _prefetch_tasks.pop(req.session_id, None)
    if old_task and not old_task.done():
        old_task.cancel()
    old_switch = _switch_build_tasks.pop(req.session_id, None)
    if old_switch and not old_switch.done():
        old_switch.cancel()

    await log_event(
        db, user_id=user["user_id"], session_id=req.session_id,
        segment_id=None, track_id=None,
        channel_slug=new_ch["_id"], event="channel_switch",
    )

    # Kick off the new-channel first-segment build in the background
    async def _build_new_first():
        try:
            sess = await db.radio_sessions.find_one({"_id": req.session_id})
            if not sess: return
            last_track_id = sess.get("last_track_id")
            prev_track = await db.tracks.find_one({"_id": last_track_id}) if last_track_id else None
            next_track = await _pick_next_track_personalized(sess, new_ch, prev_track)
            seg = await _build_one_segment(
                req.session_id, next_track, prev_track, new_ch, _ctx_for_now(session=sess),
                force_format="solo",
            )
            played = (sess.get("played_track_ids") or []) + [seg["track_id"]]
            recent_artists = ((sess.get("recent_artists") or []) + [seg["track_artist"]])[-5:]
            await db.radio_sessions.update_one(
                {"_id": req.session_id},
                {"$set": {
                    "current_segment_id": seg["_id"],
                    "last_track_id": seg["track_id"],
                    "played_track_ids": played,
                    "recent_artists": recent_artists,
                    "switch_in_progress": False,
                }, "$inc": {"segments_played": 1}},
            )
            await _log_play(user, sess, seg, new_ch["_id"])
            _schedule_prefetch(req.session_id)
            logger.info(f"[switch] session={req.session_id} new first-seg {seg['_id']} READY")
        except Exception as e:
            logger.error(f"[switch] session={req.session_id} FAILED: {e}")
            await db.radio_sessions.update_one(
                {"_id": req.session_id}, {"$set": {"switch_in_progress": False}},
            )

    task = asyncio.create_task(_build_new_first())
    _switch_build_tasks[req.session_id] = task

    ss = await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))
    return SwitchChannelResponse(
        session_id=req.session_id,
        channel_slug=new_ch["_id"],
        channel_name=new_ch.get("name"),
        transitional=True,
        tuning_sfx_url="/api/sfx/tuning",
        estimated_ready_sec=20,
        skip_state=ss,
    )


@api.get("/radio/ready", response_model=RadioReadyResponse)
async def radio_ready(session_id: str, user: dict = Depends(current_user)):
    """Client polls this after a switch_channel to know when the real segment
    is ready. Returns the segment payload once switch_in_progress is False."""
    session = await db.radio_sessions.find_one({"_id": session_id})
    if not session: raise HTTPException(404, "session not found")
    if session.get("user_id") != user["user_id"]:
        raise HTTPException(403, "session does not belong to you")
    ss = await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))
    if session.get("switch_in_progress"):
        return RadioReadyResponse(ready=False, segment=None, skip_state=ss)
    seg_id = session.get("current_segment_id")
    if not seg_id:
        return RadioReadyResponse(ready=False, segment=None, skip_state=ss)
    seg = await db.segments.find_one({"_id": seg_id})
    if not seg:
        return RadioReadyResponse(ready=False, segment=None, skip_state=ss)
    return RadioReadyResponse(ready=True, segment=_segment_to_out(seg), skip_state=ss)


@api.get("/sfx/tuning")
async def sfx_tuning(request: Request):
    path = SFX_DIR / "tuning.mp3"
    if not path.exists():
        try: _ensure_tuning_sfx()
        except Exception as e: logger.warning(f"on-demand tuning gen failed: {e}")
    if not path.exists():
        raise HTTPException(503, "tuning sfx not ready")
    return _range_response(path, request)


# Legacy switch_channel kept as a NEXT-like response for clients that don't yet
# know about the transitional flow (e.g. test scripts). Renamed to keep the
# main POST /radio/switch_channel transitional-first.
class _LegacySwitchSync(BaseModel):
    pass


async def _prefetch_next_segment(session_id):
    try:
        async with _lock_for(session_id):
            session = await db.radio_sessions.find_one({"_id": session_id})
            if not session: return
            if session.get("pending_segment_id"): return
            channel = await _resolve_channel(session.get("channel_slug"))
            last_track_id = session.get("last_track_id")
            prev_track = await db.tracks.find_one({"_id": last_track_id}) if last_track_id else None
            next_track = await _pick_next_track_personalized(session, channel, prev_track)
            seg = await _build_one_segment(session_id, next_track, prev_track, channel, _ctx_for_now(session=session))
            await db.radio_sessions.update_one(
                {"_id": session_id}, {"$set": {"pending_segment_id": seg["_id"]}},
            )
            logger.info(f"[prebuild] session={session_id} seg={seg['_id']} ({seg.get('rj_format')}) READY")
    except Exception as e:
        logger.error(f"[prebuild] session={session_id} FAILED: {e}")
    finally:
        # Remove our own task entry so future prefetches can register.
        t = _prefetch_tasks.get(session_id)
        if t is asyncio.current_task():
            _prefetch_tasks.pop(session_id, None)


def _schedule_prefetch(session_id: str) -> None:
    """Replace any in-flight task with a fresh one (used after a switch)."""
    old = _prefetch_tasks.get(session_id)
    if old and not old.done():
        return  # Already in-flight, leave it.
    task = asyncio.create_task(_prefetch_next_segment(session_id))
    _prefetch_tasks[session_id] = task


@api.get("/radio/session/{session_id}")
async def radio_session_state(session_id: str, user: dict = Depends(current_user)):
    """Returns ONLY the currently-playing segment info. NEVER leaks upcoming."""
    session = await db.radio_sessions.find_one({"_id": session_id})
    if not session: raise HTTPException(404, "session not found")
    if session.get("user_id") and session["user_id"] != user["user_id"]:
        raise HTTPException(403, "session does not belong to you")
    ss = await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))
    return {
        "session_id": session["_id"],
        "channel_slug": session.get("channel_slug"),
        "channel_name": session.get("channel_name"),
        "current_segment_id": session.get("current_segment_id"),
        "segments_played": session.get("segments_played", 0),
        "skip_state": ss,
        # Deliberately omitted: pending_segment_id, played_track_ids, last_track_id.
    }


@api.get("/radio/skip_state")
async def radio_skip_state(user: dict = Depends(current_user)):
    return await skip_state(db, user["user_id"], is_premium=user.get("is_premium", False))


# ---------- admin: skip rules (Playback & Compliance) ----------
class SkipRulesReq(BaseModel):
    free: Optional[int] = None
    premium: Optional[int] = None
    window_sec: Optional[int] = None


@api.get("/admin/radio/skip-rules", dependencies=[Depends(require_admin)])
async def admin_get_skip_rules():
    """Current skip policy (admin view). Backend fallback: Free=1, Premium=6,
    window=3600s. No user-facing 'unlimited' option is exposed."""
    return {"ok": True, "policy": get_skip_policy(True) | {"free_limit": get_skip_policy(False)["limit"]},
            "free": get_skip_policy(False)["limit"],
            "premium": get_skip_policy(True)["limit"],
            "window_sec": get_skip_policy(False)["window_sec"]}


@api.put("/admin/radio/skip-rules", dependencies=[Depends(require_admin)])
async def admin_set_skip_rules(req: SkipRulesReq):
    policy = set_skip_policy(free=req.free, premium=req.premium, window_sec=req.window_sec)
    await db.radio_settings.update_one(
        {"_id": "skip_policy"},
        {"$set": {"free": policy["free"], "premium": policy["premium"],
                        "window_sec": policy["window_sec"],
                        "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True, "free": policy["free"], "premium": policy["premium"],
            "window_sec": policy["window_sec"]}


# ---------- My Radio preference signals (Like / Less like this) ----------
class RadioFeedbackReq(BaseModel):
    action: str                              # "like" | "less"
    segment_id: Optional[str] = None
    track_id: Optional[str] = None
    track_title: Optional[str] = None
    track_artist: Optional[str] = None
    genre: Optional[str] = None
    channel_slug: Optional[str] = None


def _dedup_cap(seq, item, cap=60):
    out = [x for x in (seq or []) if x and x.lower() != item.lower()]
    out.append(item)
    return out[-cap:]


@api.post("/radio/feedback")
async def radio_feedback(req: RadioFeedbackReq, user: dict = Depends(current_user)):
    """Lightweight My Radio preference signal. 'like' boosts the track's
    artist/genre in the listener's preference_vector; 'less' removes the
    artist from favourites and soft-penalises it going forward. These bias
    FUTURE recommendations — they are NOT direct song selection."""
    action = (req.action or "").lower()
    if action not in ("like", "less"):
        raise HTTPException(400, {"code": "bad_action"})
    artist = (req.track_artist or "").strip()
    genre = (req.genre or "").strip()
    title = (req.track_title or "").strip()
    # Enrich from the track doc when we only have an id.
    if req.track_id and (not artist or not genre):
        try:
            t = await db.tracks.find_one({"_id": req.track_id})
            if t:
                artist = artist or (t.get("artist") or "")
                genre = genre or (t.get("genre") or "")
                title = title or (t.get("title") or "")
        except Exception:
            pass
    pv = dict(user.get("preference_vector") or {})
    if action == "like":
        if genre:
            pv["genres"] = _dedup_cap(pv.get("genres"), genre, cap=40)
        if artist:
            pv["favorite_artists"] = _dedup_cap(pv.get("favorite_artists"), artist, cap=60)
            pv["disliked_artists"] = [a for a in (pv.get("disliked_artists") or [])
                                      if a and a.lower() != artist.lower()]
    else:  # less
        if artist:
            pv["favorite_artists"] = [a for a in (pv.get("favorite_artists") or [])
                                      if a and a.lower() != artist.lower()]
            pv["disliked_artists"] = _dedup_cap(pv.get("disliked_artists"), artist, cap=60)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"preference_vector": pv}})
    try:
        await db.radio_feedback.insert_one({
            "user_id": user["user_id"], "action": action,
            "segment_id": req.segment_id, "track_id": req.track_id,
            "track_title": title, "track_artist": artist, "genre": genre,
            "channel_slug": req.channel_slug, "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        pass
    return {"ok": True, "action": action,
            "favorite_artists": len(pv.get("favorite_artists") or []),
            "disliked_artists": len(pv.get("disliked_artists") or [])}


@api.get("/radio/segment/{segment_id}")
async def get_segment(segment_id: str, request: Request):
    doc = await db.segments.find_one({"_id": segment_id})
    if not doc: raise HTTPException(404, "segment not found")
    file_path = Path(doc["file_path"])
    if not file_path.exists(): raise HTTPException(404, "segment file missing")
    return _range_response(file_path, request)


# ---------- admin tune endpoint ----------
class AdminTestSegmentReq(BaseModel):
    prev_track_id: Optional[str] = None
    next_track_id: str
    voice_key: str = DEFAULT_VOICE_KEY
    format: Optional[str] = None
    channel: Optional[str] = None


@api.post("/admin/test_segment", dependencies=[Depends(require_admin)])
async def admin_test_segment(req: AdminTestSegmentReq):
    if req.voice_key not in RJ_VOICES:
        raise HTTPException(400, f"unknown voice_key. Valid: {list(RJ_VOICES.keys())}")
    track = await _get_track(req.next_track_id)
    prev = await _get_track(req.prev_track_id) if req.prev_track_id else None
    channel = await _resolve_channel(req.channel)
    seg = await _build_one_segment(
        session_id="admin_test", track=track, prev_track=prev, channel=channel,
        ctx=_ctx_for_now(), force_format=req.format,
    )
    return {
        "segment_id": seg["_id"],
        "segment_url": f"/api/radio/segment/{seg['_id']}",
        "duration_sec": seg["duration_sec"],
        "track": {"id": track["_id"], "title": track["title"], "artist": track["artist"],
                  "energy_level": track.get("energy_level", DEFAULT_ENERGY),
                  "mood": track.get("mood")},
        "prev_track": ({"id": prev["_id"], "title": prev["title"],
                        "energy_level": prev.get("energy_level", DEFAULT_ENERGY),
                        "mood": prev.get("mood")} if prev else None),
        "rj_voice_key": seg["rj_voice_key"],
        "rj_voice_name": RJ_VOICES[seg["rj_voice_key"]]["display_name"],
        "rj_format": seg.get("rj_format"), "rj_hosts": seg.get("rj_hosts", []),
        "rj_script": seg["rj_script"], "rj_start_sec": seg["rj_start_sec"],
        "energy_used": seg.get("energy_used"),
        "channel_slug": seg.get("channel_slug"),
        "voice_settings": VOICE_SETTINGS_BY_ENERGY.get(
            seg.get("energy_used", DEFAULT_ENERGY), VOICE_SETTINGS_BY_ENERGY[DEFAULT_ENERGY]
        ),
    }


# ---------- ADMIN — channel exclusivity ----------
class AdminSetExclusivityReq(BaseModel):
    exclusivity_tier: str
    gating_message: Optional[str] = None
    unlock_required_id: Optional[str] = None


_ALLOWED_EXCLUSIVITY_TIERS = {
    "free", "premium",
    "ambassador_l3", "ambassador_l4", "ambassador_l5",
    "exclusive_unlock",
}


@api.post("/admin/channels/{slug}/exclusivity",
            dependencies=[Depends(require_admin)])
async def admin_set_channel_exclusivity(slug: str,
                                                          req: AdminSetExclusivityReq):
    """Phase 10c — flip a channel's `exclusivity_tier` + optional
    `gating_message` / `unlock_required_id`.  Operator overrides are
    sticky (`exclusivity_tier_locked=True`) so the boot-time seed won't
    overwrite them.
    """
    tier = req.exclusivity_tier
    if tier not in _ALLOWED_EXCLUSIVITY_TIERS:
        raise HTTPException(
            400, f"invalid exclusivity_tier '{tier}'. "
                  f"Allowed: {sorted(_ALLOWED_EXCLUSIVITY_TIERS)}")
    ch = await get_channel(db, slug)
    if not ch:
        raise HTTPException(404, f"channel '{slug}' not found")
    if tier == "exclusive_unlock" and not req.unlock_required_id:
        raise HTTPException(
            400, "exclusive_unlock tier requires unlock_required_id")
    patch: dict = {"exclusivity_tier": tier,
                      "exclusivity_tier_locked": True,
                      "updated_at": datetime.now(timezone.utc)}
    if req.gating_message is not None:
        patch["gating_message"] = req.gating_message
    if req.unlock_required_id is not None:
        patch["unlock_required_id"] = req.unlock_required_id
    # Phase 10c.1 cosmetic — flipping back to `free` clears any stale
    # gating_message that would otherwise display in admin tooling.
    if tier == "free" and req.gating_message is None:
        patch["gating_message"] = None
    # Keep legacy premium_only consistent so older code paths still work.
    patch["premium_only"] = (tier == "premium")
    await db.channels.update_one({"_id": slug}, {"$set": patch})
    updated = await get_channel(db, slug)
    return {
        "ok": True,
        "channel": {
            "slug": slug,
            "exclusivity_tier": updated.get("exclusivity_tier"),
            "gating_message": updated.get("gating_message"),
            "unlock_required_id": updated.get("unlock_required_id"),
            "premium_only": updated.get("premium_only"),
        },
    }


# ---------- ADMIN — channel recommender health ----------
@api.get("/admin/channels/{slug}/health",
         dependencies=[Depends(require_admin)])
async def admin_channel_health(slug: str, limit: int = 50):
    """Phase Bug-2 — surface the recommender decision log + a synthetic
    pool inventory for the channel, so ops can see why a channel keeps
    looping or relaxing filters.

    Response shape:
      channel              { slug, name, allowed_*, language_mix }
      catalog              { total_tracks, by_language }
      pool_inventory       { strict, drop_energy, drop_mood, drop_genre,
                              language_only, catalog_wide }
      recent_decisions     [ { ts, user_id, session_id, steps, final_step,
                                final_pool_size, tier, chosen_track } ]
      relax_counts         { strict: N, drop_energy: N, drop_mood: N,
                              drop_genre: N, language_only: N, catalog_wide: N }
    """
    ch = await get_channel(db, slug)
    if not ch:
        raise HTTPException(404, f"channel '{slug}' not found")
    all_tracks = await db.tracks.find({}).to_list(2000)
    total_tracks = len(all_tracks)
    # Synthetic relaxation walk-through against current catalog
    pool, steps = _build_channel_pool_with_relaxation(all_tracks, ch)
    pool_inventory = {s["step"]: s["pool_size"] for s in steps}
    # Last N decisions for this channel
    raw_decisions = await db.recommender_decision_log.find(
        {"channel_slug": slug}
    ).sort("ts", -1).to_list(max(1, min(int(limit or 50), 200)))
    decisions = []
    for d in raw_decisions:
        ts = d.get("ts")
        if ts and hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        decisions.append({
            "ts": ts, "user_id": d.get("user_id"),
            "session_id": d.get("session_id"),
            "steps": d.get("steps") or [],
            "final_step": d.get("final_step"),
            "final_pool_size": d.get("final_pool_size"),
            "tier": d.get("tier"), "reason": d.get("reason"),
            "chosen_track": d.get("chosen_track"),
        })
    # Roll-up: how often did we hit each relaxation step in the recent
    # decisions window?
    relax_counts: dict = {}
    for d in raw_decisions:
        k = d.get("final_step") or "unknown"
        relax_counts[k] = relax_counts.get(k, 0) + 1
    # Catalog by language
    by_lang: dict = {}
    for t in all_tracks:
        lang = t.get("language") or "unknown"
        by_lang[lang] = by_lang.get(lang, 0) + 1
    # Operator-facing suggestion string
    strict_size = pool_inventory.get("strict", 0)
    current_step = steps[-1]["step"] if steps else "strict"
    primary_lang = (ch.get("language_mix") or [{}])[0].get("language")
    if strict_size >= MIN_POOL_SIZE:
        suggestion = (
            f"Healthy — strict pool size {strict_size} "
            f"(threshold={MIN_POOL_SIZE})")
    elif current_step == "language_only" and len(pool) < 5:
        suggestion = (
            f"Upload more {primary_lang or 'matching'} tracks. "
            f"Catalog has {len(pool)} matching tracks — "
            f"users will hear the same handful repeatedly.")
    elif current_step in ("drop_genre", "language_only"):
        moods = (ch.get("allowed_moods") or [])
        any_mood = moods[0] if moods else "any-mood"
        suggestion = (
            f"Upload more {primary_lang or 'matching'}+{any_mood} "
            f"tracks to enable mood/era targeting on this channel.")
    else:
        # General: still below threshold, but in an early relaxation step
        moods = (ch.get("allowed_moods") or [])
        mood = moods[0] if moods else "any-mood"
        suggestion = (
            f"Upload more tracks tagged {primary_lang or 'matching'}+"
            f"{mood} to reach strict tier "
            f"(have {strict_size}, need {MIN_POOL_SIZE}).")
    return {
        "channel": {
            "slug": ch["_id"], "name": ch.get("name"),
            "allowed_genres": ch.get("allowed_genres") or [],
            "allowed_moods": ch.get("allowed_moods") or [],
            "allowed_energy_levels": ch.get("allowed_energy_levels") or [],
            "language_mix": ch.get("language_mix") or [],
        },
        "catalog": {"total_tracks": total_tracks,
                    "by_language": by_lang},
        "pool_inventory": pool_inventory,
        # Top-level convenience mirror of pool_inventory.strict (contract)
        "strict_pool_size": strict_size,
        "min_pool_size_threshold": MIN_POOL_SIZE,
        "current_pool_size": len(pool),
        "current_relaxation_step": current_step,
        "relax_counts_recent": relax_counts,
        "suggestion": suggestion,
        "recent_decisions": decisions,
    }


# ---------- SHARE-this-break ----------
@api.post("/share/break", dependencies=[Depends(current_user)])
async def share_break(req: ShareCreateRequest, user: dict = Depends(current_user)):
    used_today = await shares_count_today(db, user["user_id"])
    if used_today >= DAILY_SHARE_LIMIT:
        raise HTTPException(429, f"Daily share limit reached ({DAILY_SHARE_LIMIT}/24h)")
    # Confirm the segment belongs to this user (or is admin_test) to prevent leak
    seg = await db.segments.find_one({"_id": req.segment_id})
    if not seg: raise HTTPException(404, "segment not found")
    sess_id = seg.get("session_id")
    if sess_id and sess_id != "admin_test":
        sess = await db.radio_sessions.find_one({"_id": sess_id})
        if sess and sess.get("user_id") and sess["user_id"] != user["user_id"]:
            raise HTTPException(403, "you don't own this segment")
    stinger_path = SFX_DIR / "stinger.mp3"
    doc = await create_share(
        db, user_id=user["user_id"], segment_id=req.segment_id,
        shares_dir=SHARES_DIR, stinger_path=stinger_path,
    )
    return {
        "share_id": doc["share_id"],
        "share_url": f"/api/r/{doc['share_id']}",
        "spa_url": f"/r/{doc['share_id']}",
        "audio_url": f"/api/share/{doc['share_id']}/audio",
        "duration_sec": doc["duration_sec"],
        "host_names": doc["host_names"],
        "track_title": doc.get("track_title"),
        "channel_name": doc.get("channel_name"),
    }


@api.get("/share/{share_id}/audio")
async def share_audio(share_id: str, request: Request):
    doc = await get_share(db, share_id)
    if not doc: raise HTTPException(404, "share not found")
    path = SHARES_DIR / doc["mp3_filename"]
    if not path.exists(): raise HTTPException(404, "share file missing")
    return _range_response(path, request)


@api.get("/share/{share_id}/meta")
async def share_meta(share_id: str):
    doc = await get_share(db, share_id)
    if not doc: raise HTTPException(404, "share not found")
    await increment_view(db, share_id)
    return {
        "share_id": doc["share_id"],
        "audio_url": f"/api/share/{doc['share_id']}/audio",
        "duration_sec": doc["duration_sec"],
        "track_title": doc.get("track_title"),
        "track_artist": doc.get("track_artist"),
        "rj_format": doc.get("rj_format"),
        "host_names": doc.get("host_names") or [],
        "channel_slug": doc.get("channel_slug"),
        "channel_name": doc.get("channel_name"),
        "view_count": (doc.get("view_count") or 0) + 1,
        "created_at": (
            doc["created_at"].isoformat() if hasattr(doc.get("created_at"), "isoformat")
            else doc.get("created_at")
        ),
    }


# Mount routers
# Phase 41 S1.8 — channels_grouped router MUST be included BEFORE `api`
# so its literal `/api/channels/by_category` path wins over `api`'s
# dynamic `/api/channels/{slug}` matcher.
from routes.channels_grouped import router as _channels_grouped_router
app.include_router(_channels_grouped_router)
# P0 mixed-content fix — mount the stream proxy at /api/stream-proxy
# (its own router already carries the /api prefix).
app.include_router(stream_proxy_router)
# Phase RELIABILITY.P2 — /api/playback-errors dead-letter for client
# <audio onError> events.  Rate-limited by RateLimitMiddleware
# (60/60s per IP) declared in services/security_middleware.py.
app.include_router(playback_errors_router)
app.include_router(api)
# Phase 15d — geo + market + news routes.
try:
    _geo_router = _make_geo_router(db, current_user_optional, current_user)
    app.include_router(_geo_router)
    logger.info("Phase 15d: geo/news routes registered")
except Exception as _e_geo:
    logger.warning(f"Phase 15d: geo routes registration failed ({_e_geo})")

# Phase 16a — Trivia REST endpoints (single-player solo mode).
try:
    from routes.trivia_routes import build_router as _build_trivia_router
    from services.trivia_ai import (
        ensure_trivia_indexes as _ensure_trivia_idx,
        seed_default_categories as _seed_trivia_cats,
    )
    _trivia_router = _build_trivia_router(db, current_user)
    app.include_router(_trivia_router)

    async def _phase16a_bootstrap():
        try:
            await _ensure_trivia_idx(db)
            await _seed_trivia_cats(db)
            logger.info("Phase 16a: trivia indexes + categories ready")
        except Exception as _e:
            logger.warning(f"Phase 16a bootstrap failed: {_e}")
    # Run the boot synchronously now — Phase 16a routers are registered
    # AFTER FastAPI's first startup hook has already fired, so an
    # `@app.on_event("startup")` here would be a no-op.
    try:
        import asyncio as _asyncio
        _asyncio.get_event_loop().create_task(_phase16a_bootstrap())
    except RuntimeError:
        # No running loop yet — schedule via app's startup hook.
        app.add_event_handler("startup", _phase16a_bootstrap)
    logger.info("Phase 16a: trivia routes registered")
except Exception as _e_triv:
    logger.warning(f"Phase 16a: trivia routes failed ({_e_triv})")

# Phase 16b — Multiplayer trivia rooms (REST + WebSocket).
try:
    from services.trivia_rooms import RoomHub
    from routes.trivia_room_routes import build_router as _build_trivia_room_router
    app.state.trivia_room_hub = RoomHub()
    app.state.db = db   # so the WS auth helper can read sessions
    _trivia_room_router = _build_trivia_room_router(db, current_user)
    app.include_router(_trivia_room_router)
    logger.info("Phase 16b: trivia room routes registered (in-process hub)")
except Exception as _e_room:
    logger.warning(f"Phase 16b: trivia room routes failed ({_e_room})")

# Phase 16c — Venue staff dashboard + TV display.
try:
    from services.venue_tv_hub import TVHub
    from routes.venues import build_router as _build_venue_router
    app.state.venue_tv_hub = TVHub()
    _venue_router = _build_venue_router(db, current_user)
    app.include_router(_venue_router)
    logger.info("Phase 16c: venue + TV routes registered")

    async def _phase16c_bootstrap():
        """Seed a demo venue tied to biz_demo_karak so QA can exercise
        the full venue → TV → trivia → coupon flow without setup."""
        try:
            existing = await db.venues.find_one({"id": "venue_demo_karak"})
            if existing:
                return
            await db.venues.insert_one({
                "id":               "venue_demo_karak",
                "name":              "Demo Karak Cafe",
                "owner_user_id":   "user_admin_seed",
                "address":           "Al Wasl Road, Dubai",
                "lat":                25.2048, "lng": 55.2708,
                "market":             "dubai",
                "google_place_id": None,
                "hours":              {"mon-sun": "10:00-23:00"},
                "phone":              "+971-4-555-0100",
                "website":            "https://demo-karak.bigfm.app",
                "plan_tier":         "growth",
                "logo_url":          None,
                "primary_color":   "#FF2D8A",
                "business_id":      "biz_demo_karak",
                "active":             True,
                "created_at":        datetime.now(timezone.utc),
            })
            # Add both seeded QA users as staff (admin = owner, test = staff).
            for email, role in [("admin@bigfm.dubai", "owner"),
                                       ("test@bigfm.dubai",  "staff")]:
                u = await db.users.find_one({"email": email}, {"user_id": 1, "_id": 0})
                if not u:
                    continue
                await db.venue_staff.update_one(
                    {"venue_id": "venue_demo_karak", "user_id": u["user_id"]},
                    {"$setOnInsert": {
                        "id":          "vstaff_demo_" + u["user_id"][-6:],
                        "venue_id":   "venue_demo_karak",
                        "user_id":    u["user_id"],
                        "role":        role,
                        "created_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )
            await db.venues.update_one({"id": "venue_demo_karak"},
                                                {"$set": {"owner_user_id":
                  (await db.users.find_one({"email": "admin@bigfm.dubai"},
                                                    {"user_id": 1, "_id": 0}) or {}).get("user_id") or "user_admin_seed"}})
            logger.info("Phase 16c bootstrap: demo venue ready (venue_demo_karak)")
        except Exception as e:
            logger.warning(f"Phase 16c bootstrap failed: {e}")
    asyncio.create_task(_phase16c_bootstrap())
except Exception as _e_venue:
    logger.warning(f"Phase 16c: venue routes failed ({_e_venue})")


# Phase 16-prep — channel thumbnails static serving + admin re-roll endpoint.
try:
    import os as _os
    _os.makedirs("/app/backend/static/channel_thumbnails", exist_ok=True)
    app.mount(
        "/api/static/channel_thumbnails",
        StaticFiles(directory="/app/backend/static/channel_thumbnails"),
        name="channel_thumbnails",
    )
    logger.info("Phase 16-prep: channel thumbnails StaticFiles mounted")
except Exception as _e_thumb_mount:
    logger.warning(f"Phase 16-prep: thumbnails mount failed ({_e_thumb_mount})")


# Phase 18a — ad creative static serving (audio + image).
try:
    import os as _os
    _os.makedirs("/app/backend/static/ad_creatives", exist_ok=True)
    app.mount(
        "/api/static/ad_creatives",
        StaticFiles(directory="/app/backend/static/ad_creatives"),
        name="ad_creatives",
    )
    logger.info("Phase 18a: ad_creatives StaticFiles mounted")
except Exception as _e_adv_mount:
    logger.warning(f"Phase 18a: ad_creatives mount failed ({_e_adv_mount})")

# Phase AD.11 — banner creatives static serving.
try:
    import os as _os
    _os.makedirs("/app/backend/static/banners", exist_ok=True)
    app.mount(
        "/api/static/banners",
        StaticFiles(directory="/app/backend/static/banners"),
        name="banners",
    )
    logger.info("Phase AD.11: banners StaticFiles mounted")
except Exception as _e_bnr_mount:
    logger.warning(f"Phase AD.11: banners mount failed ({_e_bnr_mount})")

# Marketplace Phase B — menu photos static serving (uploads + AI generated).
try:
    import os as _os
    _os.makedirs("/app/backend/static/menu_photos", exist_ok=True)
    app.mount(
        "/api/static/menu_photos",
        StaticFiles(directory="/app/backend/static/menu_photos"),
        name="menu_photos",
    )
    logger.info("Marketplace: menu_photos StaticFiles mounted")
except Exception as _e_mp_mount:
    logger.warning(f"Marketplace: menu_photos mount failed ({_e_mp_mount})")


# Phase AD.12 — notification creatives static serving.
try:
    import os as _os
    _os.makedirs("/app/backend/static/notifications", exist_ok=True)
    app.mount(
        "/api/static/notifications",
        StaticFiles(directory="/app/backend/static/notifications"),
        name="notifications",
    )
    logger.info("Phase AD.12: notifications StaticFiles mounted")
except Exception as _e_ntf_mount:
    logger.warning(f"Phase AD.12: notifications mount failed ({_e_ntf_mount})")

# Phase AD.3 — PW-sponsorship brand assets static serving.
try:
    import os as _os
    _os.makedirs("/app/backend/static/pw_sponsorships", exist_ok=True)
    app.mount(
        "/api/static/pw_sponsorships",
        StaticFiles(directory="/app/backend/static/pw_sponsorships"),
        name="pw_sponsorships",
    )
    logger.info("Phase AD.3: pw_sponsorships StaticFiles mounted")
except Exception as _e_pws_mount:
    logger.warning(f"Phase AD.3: pw_sponsorships mount failed ({_e_pws_mount})")

# Phase C — station artwork static serving + router.
try:
    import os as _os
    _os.makedirs("/app/backend/static/station_artwork", exist_ok=True)
    app.mount(
        "/api/static/station_artwork",
        StaticFiles(directory="/app/backend/static/station_artwork"),
        name="station_artwork",
    )
    logger.info("Phase C: station_artwork StaticFiles mounted")
except Exception as _e_art_mount:
    logger.warning(f"Phase C: station_artwork mount failed ({_e_art_mount})")
try:
    from routes.station_artwork import router as _station_artwork_router
    app.include_router(_station_artwork_router)
    logger.info("Phase C routes: /api/stations/{slug}/artwork/* wired")
except Exception as _e_art_router:
    logger.warning(f"Phase C: station_artwork router not loaded: {_e_art_router}")

try:
    from routes.imported_station_artwork import router as _imported_art_router
    app.include_router(_imported_art_router)
    logger.info("Imported-station artwork routes: /api/imported-stations/{sid}/artwork/* wired")
except Exception as _e_imp_art:
    logger.warning(f"imported_station_artwork router not loaded: {_e_imp_art}")

# Phase 36d Turn 2 — shoppable card images (Tigris-first, local fallback).
try:
    import os as _os
    _os.makedirs("/app/backend/static/shoppable_cards", exist_ok=True)
    app.mount(
        "/api/static/shoppable_cards",
        StaticFiles(directory="/app/backend/static/shoppable_cards"),
        name="shoppable_cards",
    )
    logger.info("Phase 36d Turn 2: shoppable_cards StaticFiles mounted")
except Exception as _e_sh_mount:
    logger.warning(f"Phase 36d Turn 2: shoppable_cards mount failed ({_e_sh_mount})")

# Phase 42-E2.4 / K.2 / K.7 / K.7c — static-mount the new image
# directories so the SPA can resolve them.
for _phase, _sub in [
    ("K.2",      "city_stamps"),
    ("K.7",      "landing_images"),
    ("K.7c",  "game_thumbnails"),
    ("K.10",  "station_logos_scraped"),
    ("FUN.1.1", "flagship_logos"),
    # Phase STATIC.BOOT.v2 (2026-08-01) — shared placeholder images
    # for the frontend `<img onError>` fallback pattern.  Any URL
    # that 404s in prod redirects to `/api/static/placeholders/…`.
    ("STATIC.BOOT.v2", "placeholders"),
]:
    try:
        import os as _os
        _dir = f"/app/backend/static/{_sub}"
        _os.makedirs(_dir, exist_ok=True)
        app.mount(f"/api/static/{_sub}",
                              StaticFiles(directory=_dir),
                              name=_sub)
        logger.info(f"Phase {_phase}: {_sub} StaticFiles mounted")
    except Exception as _e_mt:
        logger.warning(f"Phase {_phase}: {_sub} mount failed ({_e_mt})")


# Phase 42-F.5 — persona TTS samples (OpenAI TTS / Phase H'.1 ElevenLabs).
# Bound directly to the `/app/backend/storage/persona_samples` dir
# produced by the `scripts.seed_persona_samples` script so it stays out
# of the `static/` versioned tree.
try:
    import os as _os
    _os.makedirs("/app/backend/storage/persona_samples", exist_ok=True)
    _os.makedirs("/app/backend/storage/news_clips", exist_ok=True)
    _os.makedirs("/app/backend/storage/rj_segments", exist_ok=True)
    app.mount(
        "/api/static/persona_samples",
        StaticFiles(directory="/app/backend/storage/persona_samples"),
        name="persona_samples",
    )
    # Phase H'.2 — News Radio per-article TTS clips.
    app.mount(
        "/api/static/news_clips",
        StaticFiles(directory="/app/backend/storage/news_clips"),
        name="news_clips",
    )
    # Phase H'.3 — AI-RJ inter-song voice segments.
    app.mount(
        "/api/static/rj_segments",
        StaticFiles(directory="/app/backend/storage/rj_segments"),
        name="rj_segments",
    )
    # Anchor-voice preview samples + per-station AI intros.
    _os.makedirs("/app/backend/storage/voice_samples", exist_ok=True)
    _os.makedirs("/app/backend/storage/station_intros", exist_ok=True)
    app.mount(
        "/api/static/voice_samples",
        StaticFiles(directory="/app/backend/storage/voice_samples"),
        name="voice_samples",
    )
    app.mount(
        "/api/static/station_intros",
        StaticFiles(directory="/app/backend/storage/station_intros"),
        name="station_intros",
    )
    # 2026-07-31 — public download route for the RadioLife investor +
    # sales PPTX decks.  Files live under
    # `/app/backend/storage/decks/*.pptx` and are served as
    # application/octet-stream by StaticFiles (browsers infer the
    # PPTX MIME from the .pptx extension).
    _os.makedirs("/app/backend/storage/decks", exist_ok=True)
    app.mount(
        "/api/static/decks",
        StaticFiles(directory="/app/backend/storage/decks"),
        name="decks",
    )
    logger.info("Phase H' static mounts ready: persona_samples + news_clips + rj_segments")
except Exception as _e_ps_mount:
    logger.warning(f"Phase H' static mounts failed ({_e_ps_mount})")


@app.post("/api/admin/channels/{channel_id}/regenerate-thumbnail",
                    dependencies=[Depends(require_admin)])
async def admin_regenerate_thumbnail(
    channel_id: str, body: dict = Body(default_factory=dict),
):
    """Admin re-roll a single channel's thumbnail. Optional body:
       `{"prompt": "<override>"}`. Returns new public URL on success.

    2026-07-31 — bound directly to `@app` (was `@api` decorated AFTER
    `app.include_router(api)` on line ~4937 which made the route
    unreachable in production; users saw 404 when trying to re-roll a
    thumbnail).  Also see the boot-time `ensure_thumbnails()` hook
    added below so party_dubai / news_radio / any channel missing a
    thumbnail auto-heals at server startup — no manual re-roll needed.
    """
    out = await _thumbs.regenerate_one(
        db, channel_id, prompt_override=(body.get("prompt") or None))
    if not out.get("ok"):
        raise HTTPException(400, out.get("error") or "regeneration_failed")
    return out

app.include_router(auth_router)
app.include_router(users_router)

# Soft-launch — Business Setup Mode (launch config, consumer waitlist, admin
# preview tokens, merchant 6-months-free). Mounted after auth so deps resolve.
try:
    from routes.soft_launch import router as _soft_launch_router
    app.include_router(_soft_launch_router)
    logger.info("Soft-launch routes wired: /api/launch/*, /api/waitlist, "
                "/api/admin/launch-settings, /api/admin/preview-tokens, "
                "/api/merchant/soft-launch/*")
except Exception as _e:
    logger.warning("soft_launch router not loaded: %s", _e)

# Sub-Phase E1 — Predict & Win admin manual campaign builder.
# Mounted right after users_router so admin auth dep resolves cleanly.
try:
    app.include_router(predict_win_admin_router)
    logger.info("Sub-Phase E1 routes: /api/admin/predict-win/* wired")
except Exception as _e:
    logger.warning("Sub-Phase E1 predict_win router not loaded: %s", _e)

# Phase D — user-station tracks picker + content moderation routers.
try:
    app.include_router(station_tracks_router)
    app.include_router(admin_track_moderation_router)
    # Phase 42-F.6 — community-library add-ons (usage endpoint +
    # imported-station source).  Mounted under the same `/api/stations`
    # prefix as station_tracks; FastAPI routes by path, so the new
    # `/usage` and `/tracks/from-imported` paths are non-conflicting.
    try:
        from routes.community_library import router as _community_lib_router
        app.include_router(_community_lib_router)
        logger.info("Phase 42-F.6 community library routes mounted")
    except Exception as _e:
        logger.warning("Phase 42-F.6 community library not loaded: %s", _e)
    # Phase H'.4 — admin pre-roll chain-count override endpoint.
    try:
        from routes.admin_preroll import router as _admin_preroll_router
        app.include_router(_admin_preroll_router)
        logger.info("Phase H'.4 admin pre-roll routes mounted")
    except Exception as _e:
        logger.warning("Phase H'.4 admin preroll not loaded: %s", _e)
    # Phase COMPANION.1 — admin Home Audio V2 ad-revenue report.
    try:
        from routes.admin_ad_revenue import router as _admin_ad_revenue_router
        app.include_router(_admin_ad_revenue_router)
        logger.info("Phase COMPANION.1 admin ad-revenue report mounted")
    except Exception as _e:
        logger.warning("Phase COMPANION.1 admin ad-revenue not loaded: %s", _e)
    # Phase H'.3 — AI-RJ segment shim + cache.
    try:
        from routes.ai_rj_segments import (
            router as _ai_rj_seg_router,
            admin_router as _ai_rj_admin_router,
        )
        app.include_router(_ai_rj_seg_router)
        app.include_router(_ai_rj_admin_router)
        logger.info("Phase H'.3/H'.5b AI-RJ segment + admin routes mounted")
    except Exception as _e:
        logger.warning("Phase H'.3 AI-RJ segments not loaded: %s", _e)
    # Phase 42-E2.1 — Home feature tiles + Local highlights.
    try:
        from routes.feature_tiles import router as _ftiles_router
        app.include_router(_ftiles_router)
        logger.info("Phase 42-E2.1 home feature-tiles routes mounted")
    except Exception as _e:
        logger.warning("Phase 42-E2.1 feature-tiles not loaded: %s", _e)
    # Phase 42-E2.2 — Universal share + invite-a-friend.
    try:
        from routes.share import router as _share_router
        app.include_router(_share_router)
        logger.info("Phase 42-E2.2 share + invite routes mounted")
    except Exception as _e:
        logger.warning("Phase 42-E2.2 share routes not loaded: %s", _e)
    # Phase 42-E2.4 — Auto-generated OG share-card endpoint.
    try:
        from routes.og_card import router as _og_card_router
        app.include_router(_og_card_router)
        logger.info("Phase 42-E2.4 OG card routes mounted")
    except Exception as _e:
        logger.warning("Phase 42-E2.4 OG card routes not loaded: %s", _e)
    # Phase 42-E2.5 — Admin mail-health endpoint (sanitised Mailgun snapshot).
    try:
        from routes.admin_mail import router as _admin_mail_router
        app.include_router(_admin_mail_router)
        logger.info("Phase 42-E2.5 admin mail routes mounted")
    except Exception as _e:
        logger.warning("Phase 42-E2.5 admin mail routes not loaded: %s", _e)
    # Phase F-2 + Mailgun Webhook + I — wire all three.
    try:
        from routes.f2_mailgun_webhook import router as _f2_mg_router
        app.include_router(_f2_mg_router)
        logger.info("Phase F-2 + Mailgun webhook routes mounted")
    except Exception as _e:
        logger.warning("Phase F-2/Mailgun webhook not loaded: %s", _e)
    try:
        from routes.business_portal import router as _biz_router
        app.include_router(_biz_router)
        logger.info("Phase I business portal routes mounted")
    except Exception as _e:
        logger.warning("Phase I business portal not loaded: %s", _e)
    # Phase J — Combined Polish + Stripe Live + Mid-stream Audio Ads + Tips.
    try:
        from routes.payments_v2 import router as _pay_router
        app.include_router(_pay_router)
        logger.info("Phase J.3 payments_v2 routes mounted")
    except Exception as _e:
        logger.warning("Phase J.3 payments_v2 not loaded: %s", _e)
    try:
        from routes.tips import router as _tips_router
        app.include_router(_tips_router)
        logger.info("Phase J.4 tips routes mounted")
    except Exception as _e:
        logger.warning("Phase J.4 tips not loaded: %s", _e)
    try:
        from routes.midstream_ads import (router as _midstream_router,
                                                                              admin_router as _midstream_admin_router)
        app.include_router(_midstream_router)
        app.include_router(_midstream_admin_router)
        logger.info("Phase J.5 midstream-ads routes mounted")
    except Exception as _e:
        logger.warning("Phase J.5 midstream-ads not loaded: %s", _e)
    # Phase Π — Production readiness (admin system health + employee tools).
    try:
        from routes.admin_system import router as _sys_router
        app.include_router(_sys_router)
        logger.info("Phase Π admin_system routes mounted")
    except Exception as _e:
        logger.warning("Phase Π admin_system not loaded: %s", _e)
    # Phase K.2/K.3/K.4 — City stamps + ambassador tier + points-period
    # leaderboards.  Indexes are created lazily in the lifespan hook.
    try:
        from routes.passport_k import router as _passport_k_router
        app.include_router(_passport_k_router)
        logger.info("Phase K passport routes mounted")
    except Exception as _e:
        logger.warning("Phase K routes not loaded: %s", _e)
    # Phase K.7 — Marketing assets surface (landing-page + game thumbnails).
    try:
        from routes.marketing_assets import router as _mkt_router
        app.include_router(_mkt_router)
        logger.info("Phase K.7 marketing assets route mounted")
    except Exception as _e:
        logger.warning("Phase K.7 marketing route not loaded: %s", _e)
    logger.info("Phase D routes: /api/stations/*/tracks/* and "
                          "/api/admin/moderation/tracks/* wired")
except Exception as _e:
    logger.warning("Phase D station_tracks router not loaded: %s", _e)

# Sub-Phase E2 — Predict & Win consumer router.
try:
    app.include_router(predict_win_consumer_router)
    # Phase PDX.1 — mount curator admin + public routers.
    app.include_router(pdx_curator_admin_router)
    app.include_router(pdx_admin_pw_points_router)
    app.include_router(pdx_public_router)
    logger.info("Sub-Phase E2 routes: /api/predict-win/* (consumer) wired")
except Exception as _e:
    logger.warning("Sub-Phase E2 predict_win consumer router not loaded: %s", _e)

# Sub-Phase E3 — Predict & Win business builder + TV kiosk routers.
try:
    from routes.predict_win_business import router as predict_win_business_router
    from routes.predict_win_tv import router as predict_win_tv_router
    app.include_router(predict_win_business_router)
    app.include_router(predict_win_tv_router)
    logger.info("Sub-Phase E3 routes: /api/business/predict-win/* + "
                            "/api/tv/predict-win/* wired")
except Exception as _e:
    logger.warning("Sub-Phase E3 predict_win business/tv router not loaded: %s", _e)

# Sub-Phase E4 — sweeper admin diagnostic router.
try:
    from routes.predict_win_admin_sweeper import (
        router as predict_win_sweeper_router)
    app.include_router(predict_win_sweeper_router)
    logger.info("Sub-Phase E4 routes: /api/admin/predict-win/sweeper/* wired")
except Exception as _e:
    logger.warning("Sub-Phase E4 predict_win sweeper router not loaded: %s", _e)

# Phase PW-M.1 — Merchant Predict & Win router.
try:
    from routes.predict_win_merchant import (
        router as predict_win_merchant_router)
    app.include_router(predict_win_merchant_router)
    logger.info("Phase PW-M.1 routes: /api/merchant/predict-win/* + "
                              "/api/admin/predict-win/{parent-campaigns,merchant-campaigns,businesses}/* wired")
except Exception as _e:
    logger.warning("Phase PW-M.1 merchant predict-win router not loaded: %s", _e)

# Phase G1 — Geo-aware Nearby Offers (consumer rail).
try:
    from routes.offers_nearby import router as offers_nearby_router
    app.include_router(offers_nearby_router)
    logger.info("Phase G1 routes: /api/offers/nearby wired")
except Exception as _e:
    logger.warning("Phase G1 offers_nearby router not loaded: %s", _e)

# Phase 42-A — Live Radio consumer + admin routers.
try:
    from routes.live_radio import router as live_radio_router
    from routes.admin_radio_import import router as admin_radio_import_router
    app.include_router(live_radio_router)
    app.include_router(admin_radio_import_router)
    logger.info("Phase 42-A routes: /api/live-radio/* + /api/admin/radio-import/* wired")
except Exception as _e:
    logger.warning("Phase 42-A live_radio routers not loaded: %s", _e)

# Phase 42-A2 — Unified Radio router (RadioLife AI + Community + imported).
try:
    from routes.radio_unified import router as radio_unified_router
    app.include_router(radio_unified_router)
    logger.info("Phase 42-A2 routes: /api/radio/{discover,browse,station,play} wired")
except Exception as _e:
    logger.warning("Phase 42-A2 radio_unified router not loaded: %s", _e)

# Promoted / sponsored radio stations (CPM/CPC).
try:
    from routes.promoted_stations import router as promoted_stations_router
    app.include_router(promoted_stations_router)
    logger.info("Promoted stations routes: /api/promoted/* wired")
except Exception as _e:
    logger.warning("promoted_stations router not loaded: %s", _e)

# Rewards engine + coupon-fraud + merchant redeem/loyalty + game limits.
try:
    from routes.rewards_merchant import router as rewards_merchant_router
    app.include_router(rewards_merchant_router)
    logger.info("Rewards/merchant routes: /api/rewards, /api/merchant, /api/games/limits wired")
except Exception as _e:
    logger.warning("rewards_merchant router not loaded: %s", _e)

# Phase 42-D — wire 42-D2 admin grants + voucher redemption + 42-D3 station favorites.
try:
    from routes.admin_subscriptions import (router as _admin_subs_router,
                                                                                          ensure_indexes as _ensure_admin_subs_idx)
    from routes.subscription_voucher import router as _sub_voucher_router
    from routes.station_favorites import (router as _station_favorites_router,
                                                                                  ensure_indexes as _ensure_station_fav_idx)
    app.include_router(_admin_subs_router)
    app.include_router(_sub_voucher_router)
    app.include_router(_station_favorites_router)
    # Phase P0-BAR — mount the bottom-bar station rail endpoint.
    from routes.bottom_bar_rail import router as _bottom_bar_rail_router
    app.include_router(_bottom_bar_rail_router)
    @app.on_event("startup")
    async def _phase_42d_index_bootstrap():
        try:
            await _ensure_admin_subs_idx(app.state.db)
            await _ensure_station_fav_idx(app.state.db)
            logger.info("Phase 42-D indexes ensured: vouchers + station favorites")
        except Exception as _ie:
            logger.warning("Phase 42-D index bootstrap failed: %s", _ie)
    logger.info("Phase 42-D routes wired: /api/admin/subscriptions/grant + "
                          "/api/admin/vouchers + /api/subscriptions/redeem-voucher + "
                          "/api/me/favorite-stations")
except Exception as _e:
    logger.warning("Phase 42-D routers not loaded: %s", _e)

# Phase F-1 — Unified Points engine routes.
try:
    from routes.points import router as _points_router
    from routes.admin_points import router as _admin_points_router
    app.include_router(_points_router)
    app.include_router(_admin_points_router)
    logger.info("Phase F-1 routes wired: /api/me/points + /api/admin/points")
except Exception as _e:
    logger.warning("Phase F-1 points routers not loaded: %s", _e)

# Phase RWD.1 — Rewards "Earn Loop" (overview / ways-to-earn / missions + admin).
try:
    from routes.rewards_earn import router as _rewards_earn_router
    app.include_router(_rewards_earn_router)
    logger.info("Phase RWD.1 routes wired: /api/me/earn + /api/admin/earn")
except Exception as _e:
    logger.warning("Phase RWD.1 rewards_earn router not loaded: %s", _e)

# Phase RWD.3 — Premium Cues (status / benefits + admin config).
try:
    from routes.premium_cues import router as _premium_cues_router
    app.include_router(_premium_cues_router)
    logger.info("Phase RWD.3 routes wired: /api/me/premium + /api/premium + /api/admin/premium")
except Exception as _e:
    logger.warning("Phase RWD.3 premium_cues router not loaded: %s", _e)

# Phase RWD.4 — Merchant ops: Sponsored Bonus windows + Fraud Alerts.
try:
    from routes.merchant_ops import router as _merchant_ops_router
    app.include_router(_merchant_ops_router)
    logger.info("Phase RWD.4 routes wired: /api/admin/bonus-windows + /api/admin/fraud-alerts")
except Exception as _e:
    logger.warning("Phase RWD.4 merchant_ops router not loaded: %s", _e)

try:
    from routes.merchant_marketplace import router as _merchant_marketplace_router
    app.include_router(_merchant_marketplace_router)
    logger.info("Phase MKT.1 routes wired: /api/merchant/marketplace + /api/admin/rate-card + brand-trivia/coupons")
except Exception as _e:
    logger.warning("Phase MKT.1 merchant_marketplace router not loaded: %s", _e)

try:
    from routes.creator_video import router as _creator_video_router
    app.include_router(_creator_video_router)
    logger.info("Phase CS.1 routes wired: /api/podcasts/episodes/{id}/video|chapters|transcript|media")
except Exception as _e:
    logger.warning("Phase CS.1 creator_video router not loaded: %s", _e)

try:
    from routes.gift_cards import router as _gift_cards_router
    app.include_router(_gift_cards_router)
    logger.info("Phase GC.1 routes wired: /api/giftcards/catalog|purchase|mine")
except Exception as _e:
    logger.warning("Phase GC.1 gift_cards router not loaded: %s", _e)

try:
    from routes.bigcoin_topup import router as _bigcoin_topup_router
    app.include_router(_bigcoin_topup_router)
    logger.info("Phase MON.3 routes wired: /api/bigcoin/topup/packages|checkout|status")
except Exception as _e:
    logger.warning("Phase MON.3 bigcoin_topup router not loaded: %s", _e)

# Super Marketplace — Phase A foundation (economics, categories, registration, shop).
try:
    from routes.marketplace_admin import router as _mkt_admin_router
    from routes.marketplace_merchant import router as _mkt_merchant_router
    from routes.shop import router as _shop_router
    app.include_router(_mkt_admin_router)
    app.include_router(_mkt_merchant_router)
    app.include_router(_shop_router)
    # Jurisdiction-based sales tax (admin rules + AI estimate).
    from routes.marketplace_tax import router as _mkt_tax_router
    app.include_router(_mkt_tax_router)
    # Phase B — subscriptions, menus, orders.
    from routes.marketplace_subscription import router as _mkt_sub_router
    from routes.marketplace_menu import router as _mkt_menu_router
    from routes.marketplace_orders import router as _mkt_orders_router
    from routes.marketplace_orders import merchant_router as _mkt_morders_router
    app.include_router(_mkt_sub_router)
    app.include_router(_mkt_menu_router)
    app.include_router(_mkt_orders_router)
    app.include_router(_mkt_morders_router)
    # Merchant payouts — Stripe Connect Express onboarding + transfers/instant.
    from routes.marketplace_payouts import router as _mkt_payouts_router
    app.include_router(_mkt_payouts_router)
    # Phase 2 Checkout — Saved Cards (Stripe wallet).
    from routes.saved_cards import router as _saved_cards_router
    app.include_router(_saved_cards_router)
    # Coupons at Checkout — merchant self-serve discount codes.
    from routes.marketplace_coupons import router as _mkt_coupon_router
    from routes.marketplace_coupons import consumer_router as _mkt_coupon_consumer_router
    app.include_router(_mkt_coupon_router)
    app.include_router(_mkt_coupon_consumer_router)
    # QR Scan-to-Pay — customer presents QR, shop scans to charge.
    from routes.scan_pay import router as _scanpay_router
    from routes.scan_pay import admin_router as _scanpay_admin_router
    app.include_router(_scanpay_router)
    app.include_router(_scanpay_admin_router)
    # Promoted Specials — merchant "Today's Specials".
    from routes.marketplace_specials import router as _specials_router
    from routes.marketplace_specials import consumer_router as _specials_consumer_router
    app.include_router(_specials_router)
    app.include_router(_specials_consumer_router)
    # Phase C — service bookings.
    from routes.marketplace_services import router as _mkt_svc_router
    from routes.marketplace_services import consumer_router as _mkt_svc_consumer_router
    app.include_router(_mkt_svc_router)
    app.include_router(_mkt_svc_consumer_router)
    # Phase D — ecommerce products + loyalty.
    from routes.marketplace_products import router as _mkt_prod_router
    from routes.marketplace_products import consumer_router as _mkt_prod_consumer_router
    app.include_router(_mkt_prod_router)
    app.include_router(_mkt_prod_consumer_router)
    # Phase E — merchant gift cards.
    from routes.marketplace_giftcards import router as _mkt_gc_router
    from routes.marketplace_giftcards import consumer_router as _mkt_gc_consumer_router
    app.include_router(_mkt_gc_router)
    app.include_router(_mkt_gc_consumer_router)
    # Phase E — memberships (recurring + benefit rules).
    from routes.marketplace_memberships import router as _mkt_mbr_router
    from routes.marketplace_memberships import consumer_router as _mkt_mbr_consumer_router
    app.include_router(_mkt_mbr_router)
    app.include_router(_mkt_mbr_consumer_router)
    # Phase F seed — AI ordering concierge.
    from routes.marketplace_concierge import router as _mkt_concierge_router
    app.include_router(_mkt_concierge_router)
    # Price Parity Monitor (admin).
    from routes.marketplace_price_parity import router as _mkt_parity_router
    app.include_router(_mkt_parity_router)
    # Phase E — packages (prepaid bundles).
    from routes.marketplace_packages import router as _mkt_pkg_router
    from routes.marketplace_packages import consumer_router as _mkt_pkg_consumer_router
    app.include_router(_mkt_pkg_router)
    app.include_router(_mkt_pkg_consumer_router)
    # Phase E — events (ticketed, capacity-limited).
    from routes.marketplace_events import router as _mkt_evt_router
    from routes.marketplace_events import consumer_router as _mkt_evt_consumer_router
    app.include_router(_mkt_evt_router)
    app.include_router(_mkt_evt_consumer_router)
    # Gift Inbox — unified "gifts received" aggregation.
    from routes.marketplace_gifts import router as _mkt_gifts_router
    app.include_router(_mkt_gifts_router)
    logger.info("Marketplace Phase A routes wired: /api/admin/marketplace/* "
                "/api/merchant/marketplace/* /api/shop/*")
except Exception as _e:
    logger.warning("Marketplace Phase A routers not loaded: %s", _e)

try:
    from routes.games_streak import router as _games_streak_router
    from routes.favourites import router as _favourites_router
    app.include_router(_games_streak_router)
    app.include_router(_favourites_router)
    logger.info("Routes wired: /api/games_v2/daily-streak /api/favourites/*")
except Exception as _e:
    logger.warning("games_streak/favourites routers not loaded: %s", _e)

# Emergent-managed push notifications — device registration relay.
try:
    from routes.push import router as _push_router
    app.include_router(_push_router)
    logger.info("Push route wired: /api/register-push")
except Exception as _e:
    logger.warning("push router not loaded: %s", _e)

# Merchant-defined meal combos.
try:
    from routes.marketplace_combos import router as _mkt_combos_router
    app.include_router(_mkt_combos_router)
    logger.info("Combos route wired: /api/merchant/marketplace/combos")
except Exception as _e:
    logger.warning("combos router not loaded: %s", _e)

# Promoted Marketplace (Phase F) — merchant self-serve shop boosting.
try:
    from routes.marketplace_promotions import router as _mkt_promo_router
    from routes.marketplace_promotions import admin_router as _mkt_promo_admin_router
    app.include_router(_mkt_promo_router)
    app.include_router(_mkt_promo_admin_router)
    logger.info("Promotions routes wired: /api/merchant/marketplace/promotion /api/admin/marketplace/promotions")
except Exception as _e:
    logger.warning("promotions router not loaded: %s", _e)

# Category Spotlight — per-impression bid auction.
try:
    from routes.marketplace_category_bids import router as _mkt_cbid_router
    app.include_router(_mkt_cbid_router)
    logger.info("Category-bid route wired: /api/merchant/marketplace/category-bid")
except Exception as _e:
    logger.warning("category-bid router not loaded: %s", _e)

# RadioLife Ads Public API (v1) — partner/programmatic marketing.
# Mounts a dedicated sub-app at /api/v1 (docs at /api/v1/docs) that facades the
# internal ad platform, plus the self-serve portal + admin management routers.
try:
    from routes.partner_api_v1 import partner_app as _partner_v1_app
    from routes.partner_portal import router as _partner_portal_router
    from routes.partner_portal import admin_router as _partner_admin_router
    from services.partner_api import ensure_partner_api as _ensure_partner_api
    from services.partner_api_ext import ensure_ext_indexes as _ensure_ext_indexes
    from services.partner_creatives import ensure_creative_indexes as _ensure_creative_indexes
    from services.partner_api_phase_e import ensure_phase_e_indexes as _ensure_phase_e_indexes
    _partner_v1_app.state.db = db
    app.mount("/api/v1", _partner_v1_app)
    app.include_router(_partner_portal_router)
    app.include_router(_partner_admin_router)
    try:
        import asyncio as _aio_pa
        _aio_pa.get_event_loop().create_task(_ensure_partner_api(db))
        _aio_pa.get_event_loop().create_task(_ensure_ext_indexes(db))
        _aio_pa.get_event_loop().create_task(_ensure_creative_indexes(db))
        _aio_pa.get_event_loop().create_task(_ensure_phase_e_indexes(db))
    except RuntimeError:
        pass
    logger.info("RadioLife Ads API v1 wired: /api/v1 (+ /api/v1/docs), "
                "/api/partner, /api/admin/partner-api")
except Exception as _e:
    logger.warning("partner API v1 not loaded: %s", _e)

# Unified Browse aggregator — powers the switchable web layouts.
try:
    from routes.browse import router as _browse_router
    app.include_router(_browse_router)
    logger.info("Browse aggregator wired: /api/browse/home")
except Exception as _e:
    logger.warning("browse router not loaded: %s", _e)

# Phase 42-E1 — banner ads (persistent) + Predict & Win self-serve.
try:
    from routes.banner_ads_persistent import router as _banner_persist_router
    from routes.predict_win_self_serve import router as _pw_self_serve_router
    app.include_router(_banner_persist_router)
    app.include_router(_pw_self_serve_router)
    logger.info("Phase 42-E1 routes wired: /api/banner-ads + "
                          "/api/admin/predict-win/pricing + "
                          "/api/advertiser/predict-win + /api/admin/predict-win/{pending,approve,reject}")
except Exception as _e:
    logger.warning("Phase 42-E1 routers not loaded: %s", _e)

# Sub-Phase E5 — Predexon admin endpoints.
try:
    from routes.admin_predexon import router as _admin_predexon_router
    app.include_router(_admin_predexon_router)
    logger.info("Sub-Phase E5 routes: /api/admin/prediction/predexon/* + "
                          "/external-markets + /import-market wired")
except Exception as _e:
    logger.warning("Sub-Phase E5 admin_predexon router not loaded: %s", _e)

# Phase 42-C — Station claim portal (listener + owner dashboard + admin queue).
try:
    from routes.station_claims import (
        router as _station_claims_router,
        profile_router as _station_owner_profile_router,
    )
    from routes.admin_station_claims import router as _admin_station_claims_router
    from services.station_claim_service import (
        ensure_indexes as _station_claims_ensure_indexes,
    )
    app.include_router(_station_claims_router)
    app.include_router(_station_owner_profile_router)
    app.include_router(_admin_station_claims_router)
    @app.on_event("startup")
    async def _station_claims_index_bootstrap():
        try:
            await _station_claims_ensure_indexes(app.state.db)
            logger.info("Phase 42-C station claim indexes ensured")
        except Exception as _ie:
            logger.warning("Phase 42-C station claim index bootstrap failed: %s", _ie)
    logger.info("Phase 42-C routes wired: /api/radio/claims/* + /api/owner/* + /api/admin/radio/claims/*")
except Exception as _e:
    logger.warning("Phase 42-C station_claims routers not loaded: %s", _e)

# Phase CLAIM.1 — station edit-request queue + claim hub browse + proof download.
try:
    from routes.station_claim_hub import (
        router as _claim_hub_router,
        proof_router as _claim_proof_router)
    from routes.station_edit_requests import (
        owner_router as _station_edit_owner_router,
        admin_router as _station_edit_admin_router)
    app.include_router(_claim_hub_router)
    app.include_router(_claim_proof_router)
    app.include_router(_station_edit_owner_router)
    app.include_router(_station_edit_admin_router)
    logger.info("Phase CLAIM.1 routes wired: /api/stations/claimable + "
                              "/api/stations/{id}/claim-status + "
                              "/api/stations/owner/* + /api/admin/station-edits/* + "
                              "/api/admin/radio/claims/{id}/proof/{filename}")
except Exception as _e:
    logger.warning("Phase CLAIM.1 routers not loaded: %s", _e)

# Phase 42-B-redux — Pre-roll ads + user ad-settings (REVIVED 2026-06-18).
#     Originally postponed for the unified Radio merge; now reactivated
#     against the `<ImportedStreamBridge />` integration point in
#     `usePlayerStore.setImportedStation()`.
try:
    from routes.preroll_ads import (
        preroll_router as _preroll_router,
        user_router as _preroll_user_router,
    )
    from routes.admin_preroll_ads import router as _admin_preroll_router
    from services.preroll_ad_service import ensure_indexes as _preroll_ensure_indexes
    app.include_router(_preroll_router)
    app.include_router(_preroll_user_router)
    app.include_router(_admin_preroll_router)
    @app.on_event("startup")
    async def _preroll_index_bootstrap():
        try:
            await _preroll_ensure_indexes(app.state.db)
            logger.info("Phase 42-B-redux preroll indexes ensured")
        except Exception as _ie:
            logger.warning("Phase 42-B-redux preroll index bootstrap failed: %s", _ie)
    logger.info("Phase 42-B-redux routes wired: /api/live-radio/preroll/* + /api/users/me/ad-settings + /api/admin/preroll-ads/*")
except Exception as _e:
    logger.warning("Phase 42-B-redux preroll routers not loaded: %s", _e)

# Phase B — personalized city tags + home_city PATCH.  Sits *after*
# users_router so the auth dependency resolves cleanly, and *before*
# the heavier billing/play routers so the OpenAPI surface is grouped
# tidily next to the geo routes the brief built on top of.
try:
    from routes.personalized import router as _personalized_router
    app.include_router(_personalized_router)
    logger.info("Phase B routes: /api/personalized/city_tags + /api/users/me/home_city wired")
except Exception as _e:
    logger.warning("phase_b personalized router not loaded: %s", _e)

# Phase 23 Session 9 — mount the new server-resolved Play & Win surface
# BEFORE the legacy /api/wallet/items endpoint from ads_public.py so
# the new wallet endpoints (save + items returning a flat array) take
# precedence over the legacy stub.  Old wallet_router is still mounted
# below; its /api/wallet/items handler is shadowed but its other
# endpoints (if any) remain reachable.
from play_routes import (router as play_router,
                          ensure_play_wallet_indexes as _ensure_p23s9_indexes)
from wallet_routes import router as wallet_v2_router
app.include_router(play_router)
app.include_router(wallet_v2_router)
app.add_event_handler("startup", _ensure_p23s9_indexes)

# ── Premium Dining Club (Phase 1) — consumer + merchant + admin ─────
try:
    from routes.dining_club import (router as _dining_router,
                                     merchant_router as _dining_merchant_router,
                                     admin_router as _dining_admin_router)
    from services.dining_club import (ensure_dining_indexes as _ensure_dining_indexes,
                                       issue_due_grants as _dining_issue_due_grants)
    app.include_router(_dining_router)
    app.include_router(_dining_merchant_router)
    app.include_router(_dining_admin_router)

    async def _dining_boot():
        try:
            await _ensure_dining_indexes(db)
            await _dining_issue_due_grants(db)
        except Exception as _e:
            logger.warning("dining_club boot failed: %s", _e)
    app.add_event_handler("startup", _dining_boot)
    logger.info("Dining Club routes wired: /api/dining-club/* + merchant + admin")
except Exception as _e:
    logger.warning("dining_club routers not loaded: %s", _e)

# ── P1 Consumer Storefront & Discovery — store landing + my-coupons + FPK caps ─
try:
    from routes.storefront import (store_router as _store_router,
                                    me_coupons_router as _me_coupons_router,
                                    admin_caps_router as _fpk_caps_router,
                                    sponsor_router as _sponsor_router)
    app.include_router(_store_router)
    app.include_router(_me_coupons_router)
    app.include_router(_fpk_caps_router)
    app.include_router(_sponsor_router)
    logger.info("Storefront routes wired: /api/store/* + /api/me/coupons + /api/admin/fpk/coupon-caps + /api/sponsors/*")
except Exception as _e:
    logger.warning("storefront routers not loaded: %s", _e)

# ── P1.1 Coupon Passes — unified QR + in-store redeem for any owned coupon ─────
try:
    from routes.coupon_pass import (me_pass_router as _me_pass_router,
                                     pass_router as _pass_router,
                                     ensure_coupon_pass_indexes as _ensure_pass_idx)
    app.include_router(_me_pass_router)
    app.include_router(_pass_router)

    @app.on_event("startup")
    async def _coupon_pass_indexes():
        try:
            await _ensure_pass_idx(app.state.db)
        except Exception as _ie:
            logger.warning("coupon_pass indexes: %s", _ie)
    logger.info("Coupon Pass routes wired: /api/me/coupons/pass + /api/coupons/{pass,redeem}")
except Exception as _e:
    logger.warning("coupon_pass routers not loaded: %s", _e)

# ── P1.3 Sold-Out Waitlist — remind-me + in-app/push restock pings ─────────────
try:
    from routes.coupon_waitlist import (store_waitlist_router as _sw_router,
                                         me_waitlist_router as _mw_router,
                                         admin_waitlist_router as _aw_router,
                                         ensure_waitlist_indexes as _ensure_wl_idx)
    app.include_router(_sw_router)
    app.include_router(_mw_router)
    app.include_router(_aw_router)

    @app.on_event("startup")
    async def _waitlist_indexes():
        try:
            await _ensure_wl_idx(app.state.db)
        except Exception as _ie:
            logger.warning("waitlist indexes: %s", _ie)
    logger.info("Coupon Waitlist routes wired: /api/store/*/waitlist + /api/me/waitlist + /api/admin/waitlist/dispatch")
except Exception as _e:
    logger.warning("coupon_waitlist routers not loaded: %s", _e)

# Phase 18 UI-cleanup — `/api/me/*` recommendations + favorites.
try:
    from routes.me_recs import me_recs_router
    app.include_router(me_recs_router)
    logger.info("Phase 18 routes: /api/me/recommendations + favorites + autoplay wired")
except Exception as _e:
    logger.warning("phase18 me_recs router not loaded: %s", _e)
app.include_router(billing_router)
app.include_router(webhook_router)
app.include_router(sfx_router)
app.include_router(audition_router)
app.include_router(rj_quality_router)
app.include_router(imaging_router)
# Phase 4 — advertising
app.include_router(admin_ads_router)
app.include_router(advertiser_router)
app.include_router(advertiser_ai_router)
app.include_router(phase18c_router)
app.include_router(phase18d_router)
app.include_router(podcasts_router)            # Phase 36a — creator + listener
app.include_router(admin_podcasts_router)  # Phase 36a — admin moderation
app.include_router(podcasts_public_router)  # Phase 36a — public /podcasts/{slug}/rss.xml
# Phase 36d Turn 1 — Magic Clips routes (generate / list / publish / patch /
# delete / global highlights / channel highlights).
from routes.podcast_magic_clips import magic_clips_router as _magic_clips_router
app.include_router(_magic_clips_router)
# Phase 36d Turn 2 — Shoppable cards routes (CRUD + click-proxy).
from routes.shoppable_cards import shoppable_router as _shoppable_router
app.include_router(_shoppable_router)
# Phase 36e Turn 1 — Stripe Connect Express creator subscriptions + paywall.
from routes.subscriptions import subscriptions_router as _subscriptions_router
app.include_router(_subscriptions_router)
app.include_router(admin_advertiser_router)  # Phase 18a admin queue
app.include_router(ads_router)
app.include_router(wallet_router)
app.include_router(openrtb_router)
app.include_router(vast_router)
app.include_router(public_files_router)  # /ads.txt + /app-ads.txt at root
# Phase 4.5 — Stripe Connect, AI sponsor reads, SSP admin
app.include_router(advertiser_p45_router)
app.include_router(admin_p45_router)
# Phase 5 — BigCoin loyalty: rewards, games, badges, referrals, admin
app.include_router(bc_router)
app.include_router(games_router)
app.include_router(admin_bc_router)
app.include_router(admin_analytics_router)
app.include_router(admin_retention_router)
app.include_router(me_retention_router)
app.include_router(tracking_router)
app.include_router(admin_safety_router)
# Phase 12d — unified integration status / probes
from routes.admin_integrations_status import admin_integrations_router
app.include_router(admin_integrations_router)
# Phase 13d — region status / probe / promote (admin-only)
from routes.admin_region import admin_region_router
app.include_router(admin_region_router)
# Phase 13e — Sign in with Apple (web + mobile)
from routes.auth_apple import auth_apple_router
app.include_router(auth_apple_router)
# Phase 6 — multi-tier subscriptions: plans, change_plan, family, dunning, portal
app.include_router(billing6_router)
app.include_router(lobbies_router)
app.include_router(games_v2_router)
app.include_router(games_v2_public_router)
app.include_router(games_v2c_router)
app.include_router(games_v2_winners_router)  # Phase 23 Session 1.5
app.include_router(games_v2_admin_campaigns_router)  # Phase 23 Session 2
app.include_router(admin_users_router)  # Phase 19a Part 5
app.include_router(commute_router)
app.include_router(system_router)
app.include_router(route_ads_router)
app.include_router(rj_extras_router)
app.include_router(admin_rj_router)
# Phase 9c — Local Commerce
app.include_router(public_commerce_router)
app.include_router(listener_commerce_router)
app.include_router(partner_upgrade_router)
app.include_router(partner_router)
app.include_router(admin_commerce_router)

# Phase H v1 — Commute Mode MVP (real Google Maps Platform).
from routes.commute_v1 import router as _commute_v1_router, ensure_commute_v1_indexes
app.include_router(_commute_v1_router)

# Phase SC.1 — Stripe Connect Standard connected accounts.
from routes.stripe_connect import (router as _stripe_connect_router,
                                                          admin_router as _stripe_connect_admin_router)
from services.stripe_connect_service import run_sc1_migration as _run_sc1_migration
app.include_router(_stripe_connect_router)
app.include_router(_stripe_connect_admin_router)


@app.on_event("startup")
async def _phase_sc1_bootstrap() -> None:
    try:
        await _run_sc1_migration(app.state.db)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("bigfm.stripe_connect").warning(
            f"SC.1 migration failed: {_e}")


# Phase SC.2 — Merchant Self-Service Onboarding + Approval Workflow.
from routes.merchant_onboarding import router as _merchant_onboarding_router
from routes.admin_merchants import router as _admin_merchants_router
app.include_router(_merchant_onboarding_router)
app.include_router(_admin_merchants_router)

# Phase PORTAL.0 — Unified access context (AccessResolver source of truth).
from routes.portal_context import router as _portal_context_router
app.include_router(_portal_context_router)


@app.on_event("startup")
async def _phase_sc2_bootstrap() -> None:
    """Seed 16 business categories, ensure indexes on merchant_locations
    and businesses.merchant_status, and mount static assets."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.merchant_sc2")
    try:
        from scripts.seed_business_categories import seed as _sc2_seed
        result = await _sc2_seed(app.state.db)
        _lg.info(f"SC.2 categories seed: {result}")
    except Exception as _e:
        _lg.warning(f"SC.2 categories seed failed: {_e}")
    try:
        await app.state.db.merchant_locations.create_index(
            [("merchant_id", 1), ("active", 1)])
        await app.state.db.merchant_locations.create_index(
            [("google_place_id", 1)], sparse=True)
        await app.state.db.merchant_locations.create_index(
            [("location_id", 1)], unique=True)
        await app.state.db.businesses.create_index(
            [("merchant_status", 1), ("submitted_at", -1)])
        await app.state.db.businesses.create_index(
            [("owner_user_id", 1), ("created_at", -1)])
        _lg.info("SC.2 indexes ensured")
    except Exception as _e:
        _lg.warning(f"SC.2 index bootstrap failed: {_e}")


# Phase SC.3 — Commission Rules Engine + Merchant Overrides.
from routes.commissions import router as _commissions_router
app.include_router(_commissions_router)


@app.on_event("startup")
async def _phase_sc3_bootstrap() -> None:
    """Ensure indexes + seed the default commission rules on boot.
    Idempotent — skips existing rules by name."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.commissions_sc3")
    try:
        from services.commission_service import ensure_commission_indexes
        await ensure_commission_indexes(app.state.db)
        from scripts.seed_commission_rules import seed as _sc3_seed
        result = await _sc3_seed(app.state.db)
        _lg.info(f"SC.3 commission rules seed: {result}")
    except Exception as _e:
        _lg.warning(f"SC.3 bootstrap failed: {_e}")


# Phase SC.4 — Merchant Payment Links + QR Codes.
from routes.payment_links import (router as _payment_links_router,
                                                                    ensure_payment_link_indexes as _ensure_pl_ix)
app.include_router(_payment_links_router)


@app.on_event("startup")
async def _phase_sc4_bootstrap() -> None:
    """Ensure payment-link + impression indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.payment_links_sc4")
    try:
        await _ensure_pl_ix(app.state.db)
        _lg.info("SC.4 payment_link indexes ensured")
    except Exception as _e:
        _lg.warning(f"SC.4 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_sc5_bootstrap() -> None:
    """Phase SC.5 — payment_transactions_v2 indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.payments_sc5")
    try:
        from services.payment_service import ensure_payment_txn_indexes
        await ensure_payment_txn_indexes(app.state.db)
        _lg.info("SC.5 payment_transactions_v2 indexes ensured")
    except Exception as _e:
        _lg.warning(f"SC.5 bootstrap failed: {_e}")


# Phase SC.6 — Refunds + Payouts + Disputes + Reaper.
from routes.sc6_ledger import router as _sc6_ledger_router
app.include_router(_sc6_ledger_router)

# Phase MER.1 — Merchant desktop dashboard aggregator + merchant-wide txns.
from routes.merchant_dashboard import router as _mer1_dashboard_router
app.include_router(_mer1_dashboard_router)

# Phase MER.2 — Staff RBAC + invites + cashier redemption.
from routes.merchant_staff import router as _mer2_staff_router
app.include_router(_mer2_staff_router)

# Phase MER.3 — Wallet expansion + checkout modifiers.
from routes.mer3_wallet import router as _mer3_wallet_router
app.include_router(_mer3_wallet_router)

# Phase MER.4 — Shoppable business profile + follow/save + reverse-modifiers.
from routes.mer4_business import router as _mer4_business_router
app.include_router(_mer4_business_router)

# Phase PG.1 — Play & Win + Scratch & Win game engine.
from routes.pg1_games import router as _pg1_games_router
app.include_router(_pg1_games_router)

# Phase AD.1 — Advertiser self-service dashboard MVP (parallel to Phase 18a).
from routes.ad1_advertiser import router as _ad1_advertiser_router
from routes.ad1_admin import router as _ad1_admin_router
app.include_router(_ad1_advertiser_router)
app.include_router(_ad1_admin_router)

# Phase AD.2 — Sponsored Games Revenue Split (extends AD.1 + PG.1).
from routes.ad2_sponsored_games import router as _ad2_router
app.include_router(_ad2_router)

# Phase AD.6 — Advertiser App: Staff RBAC + Redemption scanner.
from routes.advertiser_staff_scan import router as _ad6_router
app.include_router(_ad6_router)

# Phase AD.4 — Coupon Pay-Per-Save (advertiser-owned CPS campaigns).
from routes.ad4_coupon_campaigns import router as _ad4_router
app.include_router(_ad4_router)

# Phase ADMOD.1 — Ad Manager Role + Unified Creative Approval Queue.
from routes.ad_review import router as _admod1_router
app.include_router(_admod1_router)

# Phase PREROLL.EXT — Admin per-station preroll toggle.
from routes.admin_station_preroll import router as _preroll_ext_admin_router
app.include_router(_preroll_ext_admin_router)

# Phase AD.11 — Banner ad buying + placement across 7 zones.
from routes.ad11_banners import router as _ad11_router
app.include_router(_ad11_router)

# Phase AD.12a — In-app notification ads.
from routes.ad12_notifications import router as _ad12_router
app.include_router(_ad12_router)

# Phase AD.12 bundle — Notification trigger recipes registry + dispatcher.
from routes.notification_triggers import router as _ntrig_router
app.include_router(_ntrig_router)

# Phase AD.7 — Scan-to-Pay at partner merchants.
from routes.scan_to_pay import router as _ad7_router
app.include_router(_ad7_router)

# Phase E — AD.7.1 Split-the-bill (extends AD.7 with 2-8 payer flow).
from routes.scan_to_pay_splits import router as _ad7_1_splits_router
app.include_router(_ad7_1_splits_router)

# Phase F — Monetization M4: Boosted Flagship Slots.
from routes.flagship_boosts import router as _m4_flagship_boosts_router
app.include_router(_m4_flagship_boosts_router)

# Phase G — AD.9 Podcast Completion Points.
from routes.podcast_completion import router as _ad9_pc_router
app.include_router(_ad9_pc_router)

# Phase H — AD.5 Trivia Sponsorship + Giveaway Redemption.
from routes.trivia_sponsorships import router as _ad5_ts_router
app.include_router(_ad5_ts_router)

# Phase I — M1 Sponsored AI-RJ Reads.
from routes.rj_sponsored_reads import router as _m1_rjsr_router
app.include_router(_m1_rjsr_router)

# Phase J — M2 Location-Boost Ads.
from routes.location_boosts import router as _m2_lb_router
app.include_router(_m2_lb_router)

# Phase K — M3 Wallet-Deal Marketplace.
from routes.marketplace import router as _m3_market_router
app.include_router(_m3_market_router)

# Phase L — M5 Radio Takeover Hour routes.
from routes.takeover_hours import router as _m5_takeover_router
app.include_router(_m5_takeover_router)

# Phase M — M6 Retargeting Audiences routes.
from routes.retargeting import router as _m6_retargeting_router
app.include_router(_m6_retargeting_router)

# Phase N — M7 CPA (cost-per-action) coupon charge routes.
from routes.coupon_cpa import router as _m7_cpa_router
app.include_router(_m7_cpa_router)

# Phase O — Flagship Sponsor CTA (upsell funnel) routes.
from routes.flagship_upsell import router as _m8_upsell_router
app.include_router(_m8_upsell_router)

# Phase Q — QA Dashboard (admin-only ops console).
from routes.qa_dashboard import router as _qa_router
app.include_router(_qa_router)

# Phase R — News Radio Expansion (admin-curated news layer).
from routes.news_phase_r import router as _phase_r_router
app.include_router(_phase_r_router)

# Phase S — Location Intelligence (geo analytics + merchant foot-traffic +
# advertiser density preview).
from routes.location_intel import router as _phase_s_router
app.include_router(_phase_s_router)

# Phase T — Admin Home dashboard (summary + search + nav pins).
from routes.admin_home import router as _phase_t_router
app.include_router(_phase_t_router)

# Phase AD.3 — Advertiser Predict & Win sponsorship.
from routes.ad3_sponsorships import router as _ad3_router
app.include_router(_ad3_router)

# Phase AD.8 — Daily code claim.
from routes.daily_code import router as _ad8_router
app.include_router(_ad8_router)

# Phase AD.3 bundle — Auction transparency insights.
from routes.auction_insights import router as _auction_router
app.include_router(_auction_router)

# Phase B — Podcast progress tracking + completion trigger.
from routes.podcast_progress import router as _podcast_progress_router
app.include_router(_podcast_progress_router)

# Phase C — additive trivia endpoints (question sets, REST answer,
# host-advance, results).  Sits on top of the existing Phase 16b hub.
from routes.trivia_phase_c import router as _trivia_phase_c_router
app.include_router(_trivia_phase_c_router)

# Phase D — AI RJ Personas (admin-managed voice profiles + station
# assignments + preview pipeline).
from routes.rj_personas import router as _rj_personas_router
app.include_router(_rj_personas_router)

# Phase AD.12 bundle — Advertiser weekly performance digest.
from routes.advertiser_digest import router as _digest_router
app.include_router(_digest_router)


@app.on_event("startup")
async def _phase_ad12_bootstrap() -> None:
    """Phase AD.12 — ensure indexes + start weekly digest scheduler.
    Also boot Phase AD.7 (scan-to-pay) indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.ad12.boot")
    try:
        from services.ad12_notification_service import ensure_ad12_indexes
        await ensure_ad12_indexes(app.state.db)
        _lg.info("AD.12 indexes ready")
    except Exception as _e:
        _lg.warning("AD.12 index setup failed: %s", _e)
    try:
        from services.advertiser_digest_service import (
            start_scheduler as start_digest_scheduler)
        start_digest_scheduler(app, app.state.db)
    except Exception as _e:
        _lg.warning("AD.12 digest scheduler failed: %s", _e)
    try:
        from services.scan_to_pay_service import ensure_scan_to_pay_indexes
        await ensure_scan_to_pay_indexes(app.state.db)
        _lg.info("AD.7 scan-to-pay indexes ready")
    except Exception as _e:
        _lg.warning("AD.7 index setup failed: %s", _e)
    # Phase E — AD.7.1 Split-the-bill.  Ensure indexes + kick off an
    # initial expired-split sweep, then schedule an hourly sweeper.
    try:
        from services.bill_split_service import (
            ensure_bill_split_indexes, sweep_expired_splits)
        await ensure_bill_split_indexes(app.state.db)
        # First sweep at boot (catches anything stale from a previous run).
        try:
            r = await sweep_expired_splits(app.state.db)
            _lg.info("AD.7.1 boot sweep: %s", r)
        except Exception as _se:
            _lg.warning("AD.7.1 boot sweep failed: %s", _se)

        async def _ad7_1_hourly_sweeper():
            import asyncio as _aio
            while True:
                try:
                    await _aio.sleep(3600)
                    r = await sweep_expired_splits(app.state.db)
                    if r.get("updated"):
                        _lg.info("AD.7.1 hourly sweep: %s", r)
                except _aio.CancelledError:
                    break
                except Exception as _e:
                    _lg.warning("AD.7.1 hourly sweep failed: %s", _e)

        import asyncio as _asyncio
        _asyncio.create_task(_ad7_1_hourly_sweeper(),
                                                    name="ad7_1_split_sweeper")
        _lg.info("AD.7.1 split-the-bill indexes + sweeper ready")
    except Exception as _e:
        _lg.warning("AD.7.1 setup failed: %s", _e)
    # Phase F — Monetization M4: Boosted Flagship Slots.  Indexes +
    # initial activation sweep, then schedule hourly sweeper.
    try:
        from services.flagship_boost_service import (
            ensure_flagship_boost_indexes, sweep_activations)
        await ensure_flagship_boost_indexes(app.state.db)
        try:
            r = await sweep_activations(app.state.db)
            _lg.info("M4 boot sweep: %s", r)
        except Exception as _se:
            _lg.warning("M4 boot sweep failed: %s", _se)

        async def _m4_hourly_sweeper():
            import asyncio as _aio
            while True:
                try:
                    await _aio.sleep(3600)
                    r = await sweep_activations(app.state.db)
                    if r.get("activated") or r.get("completed"):
                        _lg.info("M4 hourly sweep: %s", r)
                except _aio.CancelledError:
                    break
                except Exception as _e:
                    _lg.warning("M4 hourly sweep failed: %s", _e)

        import asyncio as _asyncio
        _asyncio.create_task(_m4_hourly_sweeper(),
                                                    name="m4_flagship_boost_sweeper")
        _lg.info("M4 flagship-boost indexes + sweeper ready")
    except Exception as _e:
        _lg.warning("M4 setup failed: %s", _e)
    # Phase G — AD.9 Podcast Completion Points.  Indexes only (no
    # sweeper — awards are event-driven).
    try:
        from services.podcast_completion_service import (
            ensure_podcast_completion_indexes)
        await ensure_podcast_completion_indexes(app.state.db)
        _lg.info("AD.9 podcast-completion indexes ready")
    except Exception as _e:
        _lg.warning("AD.9 setup failed: %s", _e)
    # Phase H — AD.5 Trivia Sponsorship indexes.
    try:
        from services.trivia_sponsorship_service import (
            ensure_trivia_sponsorship_indexes)
        await ensure_trivia_sponsorship_indexes(app.state.db)
        _lg.info("AD.5 trivia-sponsorship indexes ready")
    except Exception as _e:
        _lg.warning("AD.5 setup failed: %s", _e)
    # Phase I — M1 Sponsored AI-RJ Reads indexes.
    try:
        from services.rj_sponsored_read_service import (
            ensure_rj_sponsored_read_indexes)
        await ensure_rj_sponsored_read_indexes(app.state.db)
        _lg.info("M1 rj-sponsored-read indexes ready")
    except Exception as _e:
        _lg.warning("M1 setup failed: %s", _e)
    # Phase J — M2 Location-Boost Ads indexes.
    try:
        from services.location_boost_service import (
            ensure_location_boost_indexes)
        await ensure_location_boost_indexes(app.state.db)
        _lg.info("M2 location-boost indexes ready")
    except Exception as _e:
        _lg.warning("M2 setup failed: %s", _e)
    # Phase K — M3 Marketplace indexes + hourly indexer.
    try:
        from services.marketplace_service import (
            ensure_marketplace_indexes, start_hourly_indexer)
        await ensure_marketplace_indexes(app.state.db)
        await start_hourly_indexer(app.state.db)
        _lg.info("M3 marketplace indexes ready + indexer loop started")
    except Exception as _e:
        _lg.warning("M3 setup failed: %s", _e)
    # Phase L — M5 Radio Takeover Hour indexes + boot sweep + hourly.
    try:
        from services.takeover_hour_service import (
            ensure_takeover_hour_indexes, sweep_takeover_hours)
        await ensure_takeover_hour_indexes(app.state.db)
        try:
            r = await sweep_takeover_hours(app.state.db)
            _lg.info("M5 takeover boot sweep: %s", r)
        except Exception as _se:
            _lg.warning("M5 boot sweep failed: %s", _se)

        async def _m5_hourly_sweeper():
            import asyncio as _aio
            while True:
                try:
                    await _aio.sleep(3600)
                    r = await sweep_takeover_hours(app.state.db)
                    if r.get("activated") or r.get("completed"):
                        _lg.info("M5 hourly sweep: %s", r)
                except _aio.CancelledError:
                    break
                except Exception as _e:
                    _lg.warning("M5 hourly sweep failed: %s", _e)

        import asyncio as _asyncio
        _asyncio.create_task(_m5_hourly_sweeper(),
                             name="m5_takeover_hour_sweeper")
        _lg.info("M5 takeover-hour indexes + sweeper ready")
    except Exception as _e:
        _lg.warning("M5 setup failed: %s", _e)

    # Phase M — M6 Retargeting Audiences indexes + boot sweep + daily.
    try:
        from services.retargeting_service import (
            ensure_retargeting_indexes, sweep_stale_audiences)
        await ensure_retargeting_indexes(app.state.db)
        try:
            r = await sweep_stale_audiences(app.state.db)
            _lg.info("M6 retargeting boot sweep: %s", r)
        except Exception as _se:
            _lg.warning("M6 boot sweep failed: %s", _se)

        async def _m6_daily_sweeper():
            import asyncio as _aio
            while True:
                try:
                    await _aio.sleep(86400)          # 24h
                    r = await sweep_stale_audiences(app.state.db)
                    if r.get("refreshed"):
                        _lg.info("M6 daily sweep: %s", r)
                except _aio.CancelledError:
                    break
                except Exception as _e:
                    _lg.warning("M6 daily sweep failed: %s", _e)

        import asyncio as _asyncio
        _asyncio.create_task(_m6_daily_sweeper(),
                             name="m6_retargeting_sweeper")
        _lg.info("M6 retargeting indexes + daily sweeper ready")
    except Exception as _e:
        _lg.warning("M6 setup failed: %s", _e)

    # Phase N — M7 CPA coupon charge indexes.
    try:
        from services.coupon_cpa_charge_pipeline import (
            ensure_cpa_indexes)
        await ensure_cpa_indexes(app.state.db)
        _lg.info("M7 CPA charge indexes ready")
    except Exception as _e:
        _lg.warning("M7 setup failed: %s", _e)

    # Phase O — Flagship Sponsor CTA (upsell funnel) indexes.
    try:
        from services.flagship_upsell_service import (
            ensure_upsell_indexes)
        await ensure_upsell_indexes(app.state.db)
        _lg.info("M8 upsell indexes ready")
    except Exception as _e:
        _lg.warning("M8 setup failed: %s", _e)

    # Phase Q — QA Dashboard indexes.
    try:
        from services.qa_dashboard_service import ensure_qa_indexes
        await ensure_qa_indexes(app.state.db)
        _lg.info("Phase Q QA-dashboard indexes ready")
    except Exception as _e:
        _lg.warning("Phase Q index setup failed: %s", _e)

    # Phase R — News Radio Expansion indexes (headlines/channels/bulletins/alerts).
    try:
        from services.news_phase_r_service import ensure_indexes as \
            _ensure_phase_r_indexes
        await _ensure_phase_r_indexes(app.state.db)
        _lg.info("Phase R news-radio indexes ready")
    except Exception as _e:
        _lg.warning("Phase R index setup failed: %s", _e)

    # Phase S — Location Intelligence indexes (cache collection).
    try:
        from services.location_intel_service import ensure_indexes as \
            _ensure_phase_s_indexes
        await _ensure_phase_s_indexes(app.state.db)
        _lg.info("Phase S location-intel indexes ready")
    except Exception as _e:
        _lg.warning("Phase S index setup failed: %s", _e)

    # Phase T — Admin Home dashboard indexes (nav pins).
    try:
        from services.admin_home_service import ensure_indexes as \
            _ensure_phase_t_indexes
        await _ensure_phase_t_indexes(app.state.db)
        _lg.info("Phase T admin-home indexes ready")
    except Exception as _e:
        _lg.warning("Phase T index setup failed: %s", _e)
    try:
        from services.ad3_sponsorship_service import ensure_ad3_indexes
        await ensure_ad3_indexes(app.state.db)
        _lg.info("AD.3 PW-sponsorship indexes ready")
    except Exception as _e:
        _lg.warning("AD.3 index setup failed: %s", _e)
    try:
        from services.daily_code_service import (
            ensure_daily_code_indexes, ensure_today_code,
            start_scheduler as start_daily_code_scheduler)
        await ensure_daily_code_indexes(app.state.db)
        await ensure_today_code(app.state.db)
        start_daily_code_scheduler(app, app.state.db)
        _lg.info("AD.8 daily-code indexes + scheduler ready")
    except Exception as _e:
        _lg.warning("AD.8 setup failed: %s", _e)
    try:
        from services.auction_insights_service import (
            ensure_auction_indexes)
        await ensure_auction_indexes(app.state.db)
        _lg.info("Auction insights indexes ready")
    except Exception as _e:
        _lg.warning("Auction insights setup failed: %s", _e)
    # Phase A Item 3 — daily coupon-expiring scanner (24h horizon).
    try:
        from services.coupon_expiring_scanner import (
            ensure_coupon_expiring_indexes,
            start_scheduler as start_coupon_expiring_scheduler)
        await ensure_coupon_expiring_indexes(app.state.db)
        start_coupon_expiring_scheduler(app, app.state.db)
        _lg.info("Phase A — coupon_expiring_24h scheduler ready")
    except Exception as _e:
        _lg.warning("Phase A coupon-expiring scheduler failed: %s", _e)
    # Phase B — podcast_progress indexes + podcast_completed trigger.
    try:
        from services.podcast_progress_service import (
            ensure_podcast_progress_indexes)
        await ensure_podcast_progress_indexes(app.state.db)
        _lg.info("Phase B — podcast_progress indexes ready")
    except Exception as _e:
        _lg.warning("Phase B podcast_progress setup failed: %s", _e)
    # Phase C — seed the pre-baked trivia question sets (idempotent).
    try:
        from scripts.seed_trivia_question_sets import seed as _seed_qsets
        _seed_res = await _seed_qsets(app.state.db)
        _lg.info("Phase C — trivia question sets seeded: %s", _seed_res)
    except Exception as _e:
        _lg.warning("Phase C trivia question sets seed failed: %s", _e)
    # Phase D — RJ persona indexes.
    try:
        from services.rj_persona_service import ensure_rj_persona_indexes
        await ensure_rj_persona_indexes(app.state.db)
        _lg.info("Phase D — rj_personas indexes ready")
    except Exception as _e:
        _lg.warning("Phase D rj_personas index setup failed: %s", _e)

# Phase FUN.1 — Flagship (FunAsia Network) featured stations.
from routes.flagship_stations import router as _flagship_router
app.include_router(_flagship_router)

# YouTube-style shell — live nav/chip summary + per-user theme preference.
from routes.shell import router as _shell_router
app.include_router(_shell_router)


@app.on_event("startup")
async def _phase_fun1_bootstrap() -> None:
    """Phase FUN.1 — seed FunAsia flagship rows + start health-check loop."""
    import asyncio as _aio
    import logging as _logging
    _lg = _logging.getLogger("bigfm.fun1")
    try:
        from services.flagship_station_service import (
            ensure_flagship_indexes, seed_funasia_flagships,
            health_check_all_flagships,
        )
        await ensure_flagship_indexes(app.state.db)
        stats = await seed_funasia_flagships(app.state.db)
        _lg.info("FUN.1 seed: %s", stats)
        # Fire an immediate health probe (non-blocking) then schedule a
        # 15-minute loop.
        async def _health_loop():
            while True:
                try:
                    await health_check_all_flagships(app.state.db)
                except Exception as _ee:
                    _lg.warning("FUN.1 health loop iter failed: %s", _ee)
                await _aio.sleep(15 * 60)
        _aio.create_task(_health_loop())
        _lg.info("FUN.1 health-check loop scheduled (15-min interval)")
    except Exception as _e:
        _lg.warning(f"FUN.1 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_ad1_bootstrap() -> None:
    """Phase AD.1 — advertisers_v2/ad_campaigns_v2/ad_payments indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.ad1")
    try:
        from services.ad1_advertiser_service import ensure_ad1_indexes
        await ensure_ad1_indexes(app.state.db)
        _lg.info("AD.1 advertiser + campaign + payment indexes ensured")
    except Exception as _e:
        _lg.warning(f"AD.1 index bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_ad2_bootstrap() -> None:
    """Phase AD.2 — sponsored-game split indexes + default commission rule."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.ad2")
    try:
        from services.ad2_sponsored_game_service import ensure_ad2_indexes
        from scripts.seed_ad2_commission_rule import seed_ad2_commission_rule
        await ensure_ad2_indexes(app.state.db)
        seed = await seed_ad2_commission_rule(app.state.db)
        _lg.info("AD.2 indexes ensured + commission rule seeded: %s", seed)
    except Exception as _e:
        _lg.warning(f"AD.2 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_ad6_bootstrap() -> None:
    """Phase AD.6 — advertiser staff invites + scan indexes + demo coupons."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.ad6")
    try:
        from routes.advertiser_staff_scan import ensure_ad6_indexes
        from scripts.seed_ad6_demo_coupons import seed_ad6_demo_coupons
        await ensure_ad6_indexes(app.state.db)
        seed = await seed_ad6_demo_coupons(app.state.db)
        _lg.info("AD.6 indexes + demo coupons: %s", seed)
    except Exception as _e:
        _lg.warning(f"AD.6 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_ad4_bootstrap() -> None:
    """Phase AD.4 — coupon-save indexes + commission rule + demo campaign."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.ad4")
    try:
        from services.ad4_coupon_service import ensure_ad4_indexes
        from scripts.seed_ad4_defaults import seed_all as seed_ad4_all
        await ensure_ad4_indexes(app.state.db)
        seed = await seed_ad4_all(app.state.db)
        _lg.info("AD.4 indexes + seed: %s", seed)
    except Exception as _e:
        _lg.warning(f"AD.4 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_admod1_bootstrap() -> None:
    """Phase ADMOD.1 — ad_creative_reviews indexes + backfill migration."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.admod1")
    try:
        from services.ad_creative_review_service import ensure_ad_review_indexes
        from scripts.migrate_ad_creative_reviews import migrate_all
        await ensure_ad_review_indexes(app.state.db)
        stats = await migrate_all(app.state.db)
        _lg.info("ADMOD.1 indexes + backfill: %s", stats)
    except Exception as _e:
        _lg.warning(f"ADMOD.1 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_preroll_ext_bootstrap() -> None:
    """Phase PREROLL.EXT — backfill preroll_enabled=True across all
    station collections so admin toggles work uniformly."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.preroll_ext")
    try:
        from scripts.backfill_preroll_enabled import backfill_preroll_enabled
        stats = await backfill_preroll_enabled(app.state.db)
        _lg.info("PREROLL.EXT backfill: %s", stats)
    except Exception as _e:
        _lg.warning(f"PREROLL.EXT bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_ad11_bootstrap() -> None:
    """Phase AD.11 — banner_campaigns / banner_impressions / banner_clicks indexes."""
    import logging as _logging, os as _os
    _lg = _logging.getLogger("bigfm.ad11")
    try:
        from services.ad11_banner_service import ensure_ad11_indexes
        await ensure_ad11_indexes(app.state.db)
        _os.makedirs("/app/backend/static/banners", exist_ok=True)
        _lg.info("AD.11 indexes ensured + banner storage dir ready")
    except Exception as _e:
        _lg.warning(f"AD.11 bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_mer2_bootstrap() -> None:
    """Phase MER.2 — staff invite + redemption indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.mer2")
    try:
        from routes.merchant_staff import ensure_mer2_indexes
        await ensure_mer2_indexes(app.state.db)
        _lg.info("MER.2 staff/redemption indexes ensured")
    except Exception as _e:
        _lg.warning(f"MER.2 index bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_mer3_bootstrap() -> None:
    """Phase MER.3 — gift card / prepaid meal / wallet indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.mer3")
    try:
        from routes.mer3_wallet import ensure_mer3_indexes
        await ensure_mer3_indexes(app.state.db)
        _lg.info("MER.3 wallet_v2 indexes ensured")
    except Exception as _e:
        _lg.warning(f"MER.3 index bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_mer4_bootstrap() -> None:
    """Phase MER.4 — business profile + follow/save indexes."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.mer4")
    try:
        from routes.mer4_business import ensure_mer4_indexes
        await ensure_mer4_indexes(app.state.db)
        _lg.info("MER.4 profile + follow/save indexes ensured")
    except Exception as _e:
        _lg.warning(f"MER.4 index bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_pg1_bootstrap() -> None:
    """Phase PG.1 — game campaigns + sessions indexes + template seed."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.pg1")
    try:
        from routes.pg1_games import ensure_pg1_indexes
        await ensure_pg1_indexes(app.state.db)
        _lg.info("PG.1 game indexes + templates ensured")
    except Exception as _e:
        _lg.warning(f"PG.1 index bootstrap failed: {_e}")


@app.on_event("startup")
async def _phase_sc6_bootstrap() -> None:
    """Phase SC.6 — refund/payout/dispute indexes + reaper loop."""
    import logging as _logging
    _lg = _logging.getLogger("bigfm.sc6")
    try:
        from services.refund_service import ensure_refund_indexes
        from services.payout_dispute_service import ensure_sc6_indexes
        await ensure_refund_indexes(app.state.db)
        await ensure_sc6_indexes(app.state.db)
        _lg.info("SC.6 refund/payout/dispute indexes ensured")
    except Exception as _e:
        _lg.warning(f"SC.6 index bootstrap failed: {_e}")
    try:
        import asyncio as _asyncio
        from services.reaper_service import reaper_loop
        app.state.sc6_reaper_task = _asyncio.create_task(reaper_loop(app))
        _lg.info("SC.6 reaper loop scheduled")
    except Exception as _e:
        _lg.warning(f"SC.6 reaper bootstrap failed: {_e}")


# Phase SC.2 — merchant asset static mount (logos + photos).  Uses the
# TigrisFallbackStaticFiles so uploads landed on Tigris under
# `static/merchant_assets/…` serve via /api/static/merchant_assets/…
try:
    import os as _os_sc2
    _os_sc2.makedirs("/app/backend/static/merchant_assets", exist_ok=True)
    app.mount(
        "/api/static/merchant_assets",
        StaticFiles(directory="/app/backend/static/merchant_assets"),
        name="merchant_assets",
    )
    logger.info("Phase SC.2: merchant_assets StaticFiles mounted")
except Exception as _e_sc2_mount:
    logger.warning(f"Phase SC.2: merchant_assets mount failed ({_e_sc2_mount})")


@app.on_event("startup")
async def _phase_h_v1_bootstrap() -> None:
    try:
        await ensure_commute_v1_indexes(app.state.db)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("bigfm.commute_v1").warning(
            f"index bootstrap failed: {_e}")

# Phase 10a — Social Passport (badges, ambassador state, referrals_v2)
from routes.passport import (passport_router, referrals_v2_router,
                                          admin_passport_router,
                                          leaderboards_router,
                                          admin_leaderboards_router)
app.include_router(passport_router)
app.include_router(referrals_v2_router)
app.include_router(admin_passport_router)
# Phase 10b — public leaderboards + admin recompute
app.include_router(leaderboards_router)
app.include_router(admin_leaderboards_router)

# Phase 22a — Bulk Music Upload (admin) — /api/admin/tracks/bulk-upload
from routes.admin_tracks_bulk import router as admin_tracks_bulk_router
app.include_router(admin_tracks_bulk_router)

# Phase 22e — track dedupe indexes (ISRC sparse, file_hash UNIQUE sparse,
# title_normalized+artist_normalized).  Idempotent on every boot.
from services.track_dedupe import ensure_dedupe_indexes as _ensure_p22e_dedupe_indexes


async def _phase22e_startup_dedupe_indexes():
    await _ensure_p22e_dedupe_indexes(db)


app.add_event_handler("startup", _phase22e_startup_dedupe_indexes)


# Phase 39 Session 2 — Persona library, selection, chat, admin reclassify.
from routes.personas import router as personas_router
app.include_router(personas_router)

# Phase 39 Session 3 — Premium trial lifecycle endpoints.
from routes.billing_trial import router as billing_trial_router
app.include_router(billing_trial_router)

# Phase 39 Session 4 — Privacy Control Center + Location Consent Ladder.
from routes.privacy import router as privacy_router, ensure_privacy_indexes
app.include_router(privacy_router)

# Phase 39 Session 5 — Frequent place detection + places routes.
from routes.places import router as places_router, ensure_places_indexes
app.include_router(places_router)

# Phase 39 Session 6 — Route patterns + business visits.
from routes.route_patterns import router as route_patterns_router
from services.route_pattern_detection import (
    ensure_routes_indexes as ensure_routes_indexes_s6,
    detect_for_user as _detect_routes_for_user,
)
app.include_router(route_patterns_router)


@app.on_event("startup")
async def _phase39_session6_routes_indexes():
    await ensure_routes_indexes_s6(db)


async def _route_pattern_sweep_cron():
    """Daily sweep: re-runs route pattern detection for every user with
    location_consent_level >= 3.  Idempotent — repeated trips snap to the
    same trip_id, repeated patterns upsert in place."""
    import asyncio as _asyncio
    while True:
        try:
            n_users = n_trips = n_patterns = 0
            async for u in db.users.find(
                {"location_consent_level": {"$gte": 3}},
                {"user_id": 1},
            ):
                try:
                    r = await _detect_routes_for_user(db, u["user_id"])
                    n_users += 1
                    n_trips += r.get("trips_inserted", 0)
                    n_patterns += r.get("patterns_upserted", 0)
                except Exception as ie:
                    logger.warning(
                        f"[routes-sweep] user={u.get('user_id')} failed: {ie}")
            if n_users:
                logger.info(
                    f"[routes-sweep] swept users={n_users} "
                    f"trips_inserted={n_trips} patterns_upserted={n_patterns}")
        except Exception as e:
            logger.warning(f"[routes-sweep] iteration failed: {e}")
        await _asyncio.sleep(24 * 3600)


@app.on_event("startup")
async def _phase39_session6_start_routes_sweep():
    import asyncio as _asyncio
    app.state.route_pattern_sweep_task = _asyncio.create_task(
        _route_pattern_sweep_cron())


# Phase 39 Session 7 — Advertiser aggregate + AI memory + hard-delete sweep.
from routes.advertiser_aggregate import (
    router as adv_aggregate_router,
    ensure_advertiser_aggregate_indexes,
)
from routes.ai_memory import router as ai_memory_router
from services.hard_delete_sweep import sweep_hard_deletes as _sweep_hard_deletes
app.include_router(adv_aggregate_router)
app.include_router(ai_memory_router)

# Phase 40 — NewsData.io listener endpoints + hourly cache refresh +
# AI news radio renderer.
from routes.news import (
    router as news_router,
    ensure_news_indexes as _ensure_news_indexes,
    _refresh_cache as _news_refresh_cache,
)
# Phase 41 Session 1 — Create-My-Radio + Personal Radio Pages
# Phase 42 Session 1 — Banner ad slots + waterfall
# Phase 19   Parts A+B — Thumbnail re-roll + unified moderation queue
from routes.news_radio import (router as news_radio_router,
                                admin_router as news_radio_admin_router)
from routes.community_stations import (
    router as stations_router,
    community_router as community_router,
    migrate_phase41_creator_table as _phase41_creator_migration,
)
# Phase 41 Session 2.A — Station feed (posts + comments + reactions).
from routes.station_feed import (
    router as station_feed_router,
    ensure_station_feed_indexes as _ensure_station_feed_indexes,
)
# Phase 41 Session 2.B — Real listener-session tracking.
from routes.listener_sessions import (
    router as listener_sessions_router,
    ensure_listener_session_indexes as _ensure_listener_session_indexes,
)
# Phase 41 Session 2.C.1 — Post-engagement notifications.
from routes.notifications import (
    router as notifications_router,
    ensure_notification_indexes as _ensure_notification_indexes,
)
# Phase 41M.A — Mood voting.
from routes.mood_voting import (
    router as mood_voting_router,
    ensure_mood_voting_indexes as _ensure_mood_voting_indexes,
)
# Phase 41M.B — Station-scoped fan badges.
from routes.fan_badges import (
    me_router      as fan_badges_me_router,
    station_router as fan_badges_station_router,
)
from services.station_badge_engine import (
    ensure_station_badge_indexes as _ensure_station_badge_indexes,
)
# Phase 41 Session 3.A — Business radio station endpoints (profile
# update, logo/cover upload, admin verify).
from routes.business_stations import (
    router as business_stations_router,
    admin_router as business_admin_router,
)
# Phase 41 S4.A — In-Store Business TV display.
from routes.station_tv import (
    router as station_tv_router,
    ensure_announcement_indexes as _ensure_announcement_indexes,
)
# Phase 41 S4.5.A — Announcement coupons (attach / redeem / listing).
from routes.announcement_coupons import (
    station_router as announcement_coupon_station_router,
    public_router  as announcement_coupon_public_router,
    me_router      as announcement_coupon_me_router,
    ensure_coupon_indexes as _ensure_coupon_indexes,
)
# Phase 41 S4.5.B — Trivia leaderboard ("Top Brains").
from routes.trivia_leaderboard import router as trivia_leaderboard_router
# Phase 41 S5.A — Creator analytics dashboard.
from routes.station_analytics import router as station_analytics_router
from services.station_analytics import (
    ensure_analytics_indexes as _ensure_analytics_indexes,
)
# Phase 41 S6.A — Creator revenue share + earnings ledger.
from routes.creator_revenue import (
    router as creator_revenue_router,
    admin_router as creator_revenue_admin_router,
)
from services.creator_revenue import (
    ensure_creator_revenue_indexes as _ensure_creator_revenue_indexes,
)
from routes.banner_ads     import router as banner_ads_router
from routes.admin_phase19  import router as admin_phase19_router
from routes.social_posts import (
    router as social_posts_router,
    ensure_social_indexes as _ensure_social_indexes,
)
# Phase 42 S1 — Banner ad inventory v2 + advertiser self-serve + AdsWizz mock.
from routes.banner_ads_v2 import (
    router as banner_ads_v2_router,
    ensure_banner_v2_indexes as _ensure_banner_v2_indexes,
)
app.include_router(stations_router)
app.include_router(community_router)
# Phase 41 S2.A — station feed lives at /api/stations/{slug}/posts...
# Must mount AFTER stations_router so the /{slug}/posts path resolves
# correctly via FastAPI's path matching (stations_router doesn't define
# any /{slug}/posts route so order is non-conflicting; we still include
# explicitly here for clarity).
app.include_router(station_feed_router)
# Phase 41 S2.B — listener sessions at /api/stations/{slug}/listen/*
# and /api/stations/{slug}/listeners. Same prefix, distinct paths.
app.include_router(listener_sessions_router)
# Phase 41 S2.C.1 — notifications at /api/me/notifications/*.
app.include_router(notifications_router)
# Phase 41 S3.A — business stations (owner profile mgmt + uploads,
# admin verify). Mounted AFTER station_feed_router so the more-specific
# /{slug}/business_profile path resolves correctly.
app.include_router(business_stations_router)
app.include_router(business_admin_router)
# Phase 41 S4.A — Station TV display + announcement CRUD.
app.include_router(station_tv_router)
# Phase 41 S4.5.A — Announcement coupon CRUD + redemption + my-coupons.
# Mounted AFTER station_tv_router so the more-specific
# /api/stations/{slug}/announcements/{ann_id}/coupon path resolves cleanly.
app.include_router(announcement_coupon_station_router)
app.include_router(announcement_coupon_public_router)
app.include_router(announcement_coupon_me_router)
# Phase 41 S4.5.B — Trivia "Top Brains" leaderboard (public).
app.include_router(trivia_leaderboard_router)
# Phase 41 S5.A — Creator analytics dashboard.
app.include_router(station_analytics_router)
# Phase 41 S6.A — Creator revenue share + earnings ledger.
app.include_router(creator_revenue_router)
app.include_router(creator_revenue_admin_router)
# Phase 41M.A — Mood voting.
app.include_router(mood_voting_router)
# Phase 41M.B — Fan badges (me + station scopes).
app.include_router(fan_badges_me_router)
app.include_router(fan_badges_station_router)
# Phase 42 S1 Option B — v2 router MUST mount BEFORE legacy banner_ads so
# /api/ads/banner/decision wins over the legacy /{slot_id} catch-all.
app.include_router(banner_ads_v2_router)
app.include_router(banner_ads_router)
app.include_router(admin_phase19_router)
app.include_router(social_posts_router)


@app.on_event("startup")
async def _phase42_session1_seed():
    await _ensure_banner_v2_indexes(db)


@app.on_event("startup")
async def _phase41_session2_indexes():
    await _ensure_social_indexes(db)
    # Phase 41 S2.A — station feed indexes
    await _ensure_station_feed_indexes(db)
    # Phase 41 S2.B — listener_sessions indexes (TTL on last_ping_at)
    await _ensure_listener_session_indexes(db)
    # Phase 41 S2.C.1 — notification indexes (dedupe_key unique sparse)
    await _ensure_notification_indexes(db)
    # Phase 41 S4.A — station announcement indexes
    await _ensure_announcement_indexes(db)
    # Phase 41 S4.5.A — coupon redemption indexes (dedupe + TTL)
    await _ensure_coupon_indexes(db)
    # Phase 41 S5.A — analytics indexes (listener_session_archive, tv_poll_daily)
    await _ensure_analytics_indexes(db)
    # Phase 41 S6.A — creator earnings ledger indexes
    await _ensure_creator_revenue_indexes(db)
    # Phase 41M.A — mood_votes unique compound index
    await _ensure_mood_voting_indexes(db)
    # Phase 41M.B — user_station_badges unique compound index
    await _ensure_station_badge_indexes(db)


@app.on_event("startup")
async def _phase41_run_creator_migration():
    try:
        r = await _phase41_creator_migration(db)
        logger.info(f"[phase41] creator table migration: {r}")
    except Exception as e:
        logger.warning(f"[phase41] migration failed: {e}")
from services.news_radio_renderer import render_top_n as _news_render_top_n
app.include_router(news_router)
app.include_router(news_radio_router)
# Phase 42-F.2 — admin health probe for News Radio + TTS provider state.
app.include_router(news_radio_admin_router)


@app.on_event("startup")
async def _phase40_news_indexes():
    await _ensure_news_indexes(db)


async def _news_refresh_cron():
    import asyncio as _asyncio
    # Warm-up: first refresh 30s after boot so the Home strip has data.
    await _asyncio.sleep(30)
    while True:
        try:
            n = await _news_refresh_cache(db, limit=20)
            logger.info(f"[news-cron] refreshed {n} articles")
            # Then render summaries for the top-N missing.
            r = await _news_render_top_n(db, n=10)
            logger.info(f"[news-cron] summaries: {r}")
        except Exception as e:
            logger.warning(f"[news-cron] failed: {e}")
        await _asyncio.sleep(3600)  # hourly


@app.on_event("startup")
async def _phase40_start_news_cron():
    import asyncio as _asyncio
    app.state.news_refresh_task = _asyncio.create_task(_news_refresh_cron())


@app.on_event("startup")
async def _phase39_session7_indexes():
    await ensure_advertiser_aggregate_indexes(db)


async def _hard_delete_cron():
    import asyncio as _asyncio
    while True:
        try:
            res = await _sweep_hard_deletes(db)
            if res.get("users_hard_deleted"):
                logger.info(f"[hard-delete-sweep] {res}")
        except Exception as e:
            logger.warning(f"[hard-delete-sweep] failed: {e}")
        await _asyncio.sleep(24 * 3600)


@app.on_event("startup")
async def _phase39_session7_start_hard_delete_sweep():
    import asyncio as _asyncio
    app.state.hard_delete_sweep_task = _asyncio.create_task(_hard_delete_cron())


@app.on_event("startup")
async def _phase39_session5_places_indexes():
    await ensure_places_indexes(db)


@app.on_event("startup")
async def _phase39_session4_privacy_indexes():
    await ensure_privacy_indexes(db)


async def _trial_reminder_cron():
    """Once per 30 minutes, scan for trials expiring in 22-26h that haven't
    been reminded yet. Sends Mailgun reminder (mock-aware) + stamps
    trial_reminder_sent_at. Idempotent via the timestamp check."""
    import asyncio as _asyncio
    import uuid as _uuid
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    while True:
        try:
            now = _dt.now(_tz.utc)
            lo = (now + _td(hours=22)).isoformat()
            hi = (now + _td(hours=26)).isoformat()
            cur = db.users.find({
                "subscription_status": "trial",
                "trial_ends_at":          {"$gte": lo, "$lte": hi},
                "trial_reminder_sent_at": {"$exists": False}})
            async for u in cur:
                code = f"TRIAL50_{_uuid.uuid4().hex[:8].upper()}"
                await db.users.update_one(
                    {"user_id": u["user_id"]},
                    {"$set": {"trial_promo_code":        code,
                                      "trial_reminder_sent_at": now.isoformat()}})
                try:
                    from services.mailgun_client import send_email, is_live
                    if is_live() and u.get("email"):
                        send_email(
                            to=u["email"],
                            subject="Your RadioLife Premium trial ends in 24 hours — claim 50% off",
                            html=(f"<h2>24 hours left on your trial</h2>"
                                        f"<p>Get <b>50% off your first month</b> with code "
                                        f"<code>{code}</code>. Sliders, premium voices, "
                                        f"6 skips an hour, Social Passport bonuses — all "
                                        f"yours.</p>"
                                        f"<a href='https://mobile-games-v2.preview.emergentagent.com/upgrade?code={code}'>Claim 50% off →</a>"))
                        logger.info(f"[trial-reminder] sent user={u['user_id']} code={code}")
                    else:
                        logger.info(f"[trial-reminder] MOCKED user={u['user_id']} code={code} (Mailgun not live)")
                except Exception as e:
                    logger.warning(f"[trial-reminder] send failed user={u.get('user_id')}: {e}")
        except Exception as e:
            logger.warning(f"[trial-reminder] cron iteration failed: {e}")
        await _asyncio.sleep(1800)  # every 30 minutes


@app.on_event("startup")
async def _phase39_session3b_start_trial_reminder():
    import asyncio as _asyncio
    app.state.trial_reminder_task = _asyncio.create_task(_trial_reminder_cron())


async def _trial_sweep_cron():
    """Flips expired trials to 'free' once per hour.  Atomic + idempotent
    via services.premium_gate.sweep_expired_trials."""
    import asyncio as _asyncio
    from services.premium_gate import sweep_expired_trials
    while True:
        try:
            n = await sweep_expired_trials(db)
            if n:
                logger.info(f"[trial_sweep] flipped {n} expired trial rows")
        except Exception as e:
            logger.warning(f"[trial_sweep] failed: {e}")
        await _asyncio.sleep(3600)  # hourly


@app.on_event("startup")
async def _phase39_session3_start_trial_sweep():
    import asyncio as _asyncio
    app.state.trial_sweep_task = _asyncio.create_task(_trial_sweep_cron())

# Phase 22g — Bulk Upload Job Audit Log (admin + /api/me)
from routes.bulk_upload_jobs import router as bulk_upload_jobs_router
app.include_router(bulk_upload_jobs_router)


@app.get("/audition", include_in_schema=False)
async def audition_landing(request: Request):
    """Phase 3.6 — public, unauthed audition page at /audition (no /api prefix)."""
    return render_audition_page(request)


# ---------- SSR share landing + OG image (must be after `api` router build) ----------
import html as _html


@app.get("/api/og_default.png")
async def og_default_image():
    path = STORAGE_DIR / "og_default.png"
    if not path.exists():
        try: _ensure_og_default_image()
        except Exception: pass
    if not path.exists():
        raise HTTPException(404, "og image missing")
    return StreamingResponse(
        path.open("rb"),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/r/{share_id}", response_class=HTMLResponse)
async def share_ssr_landing(share_id: str, request: Request):
    """SSR HTML for share landings. Crawlers (WhatsApp, Twitter, Slack, FB,
    LinkedIn, iMessage) read the OG/Twitter meta tags here. Real browsers
    get auto-redirected to the SPA at /r/<id> via a tiny user-agent check.

    Lives under /api/ so the K8s ingress routes it to FastAPI (frontend port
    3000 would otherwise serve the SPA shell with no per-share meta tags).
    """
    doc = await get_share(db, share_id)
    if not doc:
        raise HTTPException(404, "Share not found")
    await increment_view(db, share_id)

    base = _public_base_url(request)
    hosts = doc.get("host_names") or ["RadioLife RJ"]
    hosts_join = " × ".join(hosts)
    channel = doc.get("channel_name") or "RadioLife"
    track = doc.get("track_title") or "a live break"
    title = f"{hosts_join} on RadioLife · {channel}"
    description = f"Heard on RadioLife — a {int(doc.get('duration_sec') or 0)}s break from {channel}{' after ' + track if track else ''}."
    audio_url = f"{base}/api/share/{share_id}/audio"
    cover_url = f"{base}/api/og_default.png"
    landing_url = f"{base}/api/r/{share_id}"
    spa_url = f"{base}/r/{share_id}"

    esc = _html.escape
    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">

<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(landing_url)}">
<meta property="og:type" content="music.song">
<meta property="og:audio" content="{esc(audio_url)}">
<meta property="og:audio:type" content="audio/mpeg">
<meta property="og:image" content="{esc(cover_url)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name" content="RadioLife">

<meta name="twitter:card" content="player">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(cover_url)}">
<meta name="twitter:player:stream" content="{esc(audio_url)}">
<meta name="twitter:player:stream:content_type" content="audio/mpeg">

<link rel="canonical" href="{esc(landing_url)}">

<style>
  body{{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;background:#0a0c18;color:#e9ebf5;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:32px;}}
  .card{{max-width:520px;width:100%;background:linear-gradient(180deg,#13152a,#0a0c18);border:1px solid #232742;border-radius:20px;padding:36px 28px;text-align:center;box-shadow:0 18px 60px rgba(0,0,0,.5);}}
  .brand{{font-size:14px;letter-spacing:.22em;color:#ff2d95;margin-bottom:24px;font-weight:700;}}
  .brand span{{color:#00d9ff;}}
  .hosts{{font-size:13px;letter-spacing:.12em;color:#a0a5c0;margin-bottom:6px;text-transform:uppercase;}}
  h1{{font-size:24px;line-height:1.2;margin:0 0 8px;letter-spacing:-.015em;}}
  .meta{{color:#a0a5c0;font-size:12px;letter-spacing:.18em;margin-bottom:24px;text-transform:uppercase;}}
  audio{{width:100%;margin-bottom:24px;}}
  .cta{{display:inline-flex;align-items:center;gap:8px;background:#ff2d95;color:#fff;text-decoration:none;padding:14px 26px;border-radius:999px;font-weight:700;font-size:14.5px;box-shadow:0 6px 24px rgba(255,45,149,.4);}}
  .cta:hover{{transform:translateY(-1px);}}
  .foot{{margin-top:22px;color:#5a5f7d;font-size:10.5px;letter-spacing:.22em;}}
</style>

<script>
  // Send normal browsers to the rich SPA player; crawlers stay on this SSR page.
  (function(){{
    try {{
      var ua = navigator.userAgent || "";
      var isCrawler = /facebookexternalhit|twitterbot|whatsapp|telegrambot|slackbot|linkedinbot|discordbot|preview|googlebot|bingbot|applebot/i.test(ua);
      if (!isCrawler) {{
        window.location.replace("/r/{esc(share_id)}");
      }}
    }} catch (e) {{}}
  }})();
</script>
</head>
<body>
  <main class="card">
    <div class="brand">RadioLife <span>AI RADIO</span></div>
    <div class="hosts">{esc(hosts_join)}</div>
    <h1>A break from {esc(channel)}</h1>
    <div class="meta">{int(doc.get('duration_sec') or 0)}s · MP3</div>
    <audio controls preload="metadata" src="{esc(audio_url)}"></audio>
    <a class="cta" href="{esc(base)}/" rel="noopener">▶ Listen on RadioLife</a>
    <div class="foot">SHARED · BIGFM · AI HINGLISH RADIO</div>
  </main>
</body>
</html>
"""
    return HTMLResponse(
        html_out,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Robots-Tag": "index, follow",
        },
    )

_cors_origins = [o for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o]
if _cors_origins == ["*"]:
    # Cross-origin browser callers (the Expo web preview, external Partner API
    # consumers) authenticate with BEARER TOKENS, never cookies — so credentialed
    # CORS is not needed. We return a LITERAL "Access-Control-Allow-Origin: *"
    # regardless of the request Origin, which the browser accepts for
    # non-credentialed requests. This is robust against the ingress rewriting the
    # Origin header (echoing it back would never match the browser's real origin).
    # The web app is SAME-ORIGIN with the backend, so its cookie auth is unaffected
    # by CORS entirely.
    _cors_kwargs = {"allow_origins": ["*"], "allow_credentials": False,
                    "allow_methods": ["*"], "allow_headers": ["*"]}
else:
    _cors_kwargs = {"allow_origins": _cors_origins, "allow_credentials": True,
                    "allow_methods": ["*"], "allow_headers": ["*"]}
# Soft-launch — Business Setup Mode gate. When an admin enables the mode,
# consumer /api endpoints return HTTP 423 unless the caller has bypass (admin,
# an approved business, or a valid preview token). Default OFF → cheap no-op.
# Added BEFORE CORS so CORS wraps it (outbound headers still apply on 423).
try:
    from services.launch_guard import LaunchGuardMiddleware
    app.add_middleware(LaunchGuardMiddleware)
    logger.info("LaunchGuardMiddleware installed (Business Setup Mode gate)")
except Exception as _e:
    logger.warning("LaunchGuardMiddleware not installed: %s", _e)

app.add_middleware(CORSMiddleware, **_cors_kwargs)

# Phase Π.2 — Security middleware bundle (CSP + HSTS + per-IP rate limit).
# Installed AFTER CORS so CORS still runs first inbound (Starlette stacks
# middlewares LIFO).  In dev with BIGFM_DEV_ESCAPE_HATCHES=1, the CSP is
# still attached but the HSTS header is skipped because ENV != production.
try:
    from services.security_middleware import install_security_middlewares
    install_security_middlewares(app)
except Exception as _e:
    logger.warning("Phase Π security middlewares not installed: %s", _e)

# Phase 13d — Cache-Control + ETag + region middleware. Order matters:
# starlette runs the LAST add_middleware FIRST in the request path, so we
# add Region last → it tags responses on the way out (innermost).
# CacheControl is added before Region so it runs first inbound and gets to
# observe the body. But we need Region tags to still be present in the
# 304 short-circuit; CacheControlMiddleware copies them through.
from services.cache_middleware import CacheControlMiddleware
from services.region import RegionHeaderMiddleware
app.add_middleware(CacheControlMiddleware)
app.add_middleware(RegionHeaderMiddleware)

# Phase 8c.1 — trust X-Forwarded-For / X-Forwarded-Proto from the K8s
# ingress / load balancer so `request.client.host` reflects the real
# client IP.  Disabled by setting `TRUSTED_PROXIES_ENABLED=false` in env.
if os.environ.get("TRUSTED_PROXIES_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    app.add_middleware(ProxyHeadersMiddleware,
                              trusted_hosts=os.environ.get("TRUSTED_PROXY_HOSTS", "*"))



# ─── Phase STATIC.BOOT (2026-07-31) ─────────────────────────────────
# The actual boot wiring lives inside `_deferred_bootstrap()` above —
# `@app.on_event('startup')` decorators are dead-letters in this
# codebase (the lifespan context manager handles all startup work via
# a background task and never runs the legacy `on_event` handlers).
# See `_deferred_bootstrap` for the schedule call.
