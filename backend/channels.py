"""RadioLife Phase 2 — Channels + Music Clocks + voice-key routing.

Each channel is a "show" with its own host roster, language/genre/mood/energy
filters, and a music-clock rotation that varies what KIND of track plays in
each slot of a repeating cycle. Real radio stations use this for variety +
brand identity.

Public surface:
- CHANNELS: list of channel dicts to seed
- RJ_VOICES_EXT: the 6 new voice entries (merged with the 3 existing in server.py)
- VOICE_PREVIEW_SCRIPTS_EXT: preview line per new voice
- seed_channels(db): idempotently upsert all channels at startup
- get_channel(db, slug): fetch one
- channel_primary_language(ch): pick the highest-weight language
- pick_voice_for_segment(channel, energy, force_duo=False): returns
    (primary_voice_key, secondary_voice_key_or_None)
- apply_music_clock_slot(candidates, slot_type, channel, user_pv): filter
- slot_for_position(channel, segments_played): the slot type to render
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("bigfm.channels")


# ---------- Extra hosts (6 new) ----------
# All voice_ids are well-known ElevenLabs public voices, chosen for a
# best-effort persona match. See finish summary for A/B notes.
RJ_VOICES_EXT: Dict[str, dict] = {
    "dj_riya_dubai": {
        # Domi — strong young female, club energy
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "display_name": "DJ Riya",
        "persona": "female club MC, late 20s, JBR loft vibes, modern English-heavy delivery, hyped party voice",
        "fits_energies": ("high", "party"),
        "duo_label": "RIYA",
        "duo_blurb": "DJ Riya — female club MC, late-20s, JBR loft, English-heavy, hyped.",
    },
    "pandit_anand": {
        # Adam — deep mature male narrator
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "display_name": "Pandit Anand",
        "persona": "mature Indian male, 55+, wisdom, slow paced, warm baritone, Sanskrit/Hindi fluent, devotional broadcaster",
        "fits_energies": ("chill",),
        "duo_label": "ANAND",
        "duo_blurb": "Pandit Anand — 55+ male, wisdom keeper, devotional broadcaster, slow warm baritone.",
    },
    "gurpreet_bhaji": {
        # Arnold — crisp confident male
        "voice_id": "VR6AewLTigWG4xSOukaG",
        "display_name": "Gurpreet Bhaji",
        "persona": "Punjabi-accented male, hearty/loud, Karama dhaba energy, mid-thirties, balle-balle host",
        "fits_energies": ("medium", "high", "party"),
        "duo_label": "GURPREET",
        "duo_blurb": "Gurpreet Bhaji — Punjabi specialist, Karama dhaba energy, hearty and loud.",
    },
    "aarti_morning": {
        # Bella — soft peppy young female
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "display_name": "Aarti",
        "persona": "Delhi-origin Indian female, mid-twenties, bubbly morning-show enthusiasm, fast peppy delivery, namaste-Dubai-good-morning energy",
        "fits_energies": ("medium", "high"),
        "duo_label": "AARTI",
        "duo_blurb": "Aarti — bubbly morning-show female, Delhi-origin, fast peppy enthusiastic.",
    },
    "kishore_retro": {
        # Josh — deep older male broadcaster
        "voice_id": "TxGEqnHWrfWFTfGW9XjX",
        "display_name": "Kishore Da",
        "persona": "older Indian male, smooth radio drawl, classic late-80s AIR broadcaster nostalgia, deep voice, unhurried",
        "fits_energies": ("chill", "medium"),
        "duo_label": "KISHORE",
        "duo_blurb": "Kishore Da — classic broadcaster, smooth drawl, late-80s AIR nostalgia.",
    },
    "simran_punjabi": {
        # Elli — emotional playful female
        "voice_id": "MF3mGyEYCl7XYWbV9V6O",
        "display_name": "Simran",
        "persona": "Punjabi-accented female, late twenties, playful co-host energy, brings warmth and humor to the Punjabi show",
        "fits_energies": ("medium", "high", "party"),
        "duo_label": "SIMRAN",
        "duo_blurb": "Simran — Punjabi female co-host, playful, warm, teases Gurpreet.",
    },
}


VOICE_PREVIEW_SCRIPTS_EXT: Dict[str, str] = {
    "dj_riya_dubai":   "[hyped] DUBAI! [excited] DJ Riya on RadioLife... [shouts] LET'S GO!!",
    "pandit_anand":    "[warm] [soft] Namaste. [pause] Aap sun rahe ho... RadioLife. Shanti.",
    "gurpreet_bhaji":  "[excited] Sat sri akal DUBAI! [hyped] Gurpreet bhaji speaking — RadioLife par!",
    "aarti_morning":   "[excited] Good morning DUBAI! [hyped] Aapki Aarti on RadioLife... [warm] uth jao!",
    "kishore_retro":   "[warm] [soft] Aap sun rahe ho... RadioLife. [warm] Kishore yahan, retro lounge mein.",
    "simran_punjabi":  "[chuckles] [warm] Hai sat sri akal! [excited] Simran yahan, RadioLife par!",
}


# ---------- Channels ----------
CHANNELS: List[dict] = [
    {
        "slug": "bollywood_mehfil",
        "name": "Bollywood Mehfil",
        "tagline": "Dil se",
        "description": "Hindi 70 · English 30. Bollywood + pop. Veer and Monika anchor the evening.",
        "cover_color": "#ff2d95",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.7}, {"language": "english", "weight": 0.3}],
        "allowed_genres": ["bollywood", "pop", "indie"],
        "allowed_moods": ["romantic", "energetic", "uplifting", "nostalgic", "chill"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "raghav_hindi", "role": "primary"},
                  {"voice_key": "aanya_hindi", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "retro", "mood_match", "regional",
                         "current_hit", "retro", "wildcard", "language_match"],
            "cycle_length": 8,
        },
        "default_for_time": ["evening", "afternoon"],
        "sort_order": 3,
        "active": True,
    },
    {
        "slug": "party_dubai",
        "name": "Party Mix",
        "tagline": "Dance floor PHATEGA",
        "description": "English 60 · Hindi 30 · Punjabi 10. DJ Charlie (American) + DJ Riya (Indian-American) on the decks. Kabir drops by for Hindi hype.",
        "cover_color": "#00d9ff",
        "cover_image_url": None,
        "language_mix": [{"language": "english", "weight": 0.6},
                         {"language": "hindi", "weight": 0.3},
                         {"language": "punjabi", "weight": 0.1}],
        "allowed_genres": ["electronic", "hip_hop", "pop", "punjabi_pop", "bollywood"],
        "allowed_moods": ["party", "energetic", "dance", "intense"],
        "allowed_energy_levels": ["high", "party", "medium"],
        "hosts": [{"voice_key": "charlie_dj", "role": "primary"},
                  {"voice_key": "riya_dj", "role": "secondary"},
                  {"voice_key": "kabir_hindi", "role": "occasional"}],
        "music_clock": {
            "rotation": ["current_hit", "current_hit", "regional", "mood_match",
                         "current_hit", "wildcard", "current_hit", "regional"],
            "cycle_length": 8,
        },
        "default_for_time": ["late_night"],
        "sort_order": 4,
        "active": True,
    },
    {
        "slug": "late_night_drive",
        "name": "Late Night Drive",
        "tagline": "Doo-bye ki sadkein",
        "description": "Hindi 50 · English 50. Chill indie, romantic Bollywood. Veer goes solo, with Marcus dropping in.",
        "cover_color": "#5a2bff",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.5}, {"language": "english", "weight": 0.5}],
        "allowed_genres": ["indie", "pop", "bollywood", "electronic"],
        "allowed_moods": ["chill", "romantic", "nostalgic", "melancholy"],
        "allowed_energy_levels": ["chill", "medium"],
        "hosts": [{"voice_key": "veer_dubai", "role": "primary"},
                  {"voice_key": "marcus_dj", "role": "occasional"}],
        "music_clock": {
            "rotation": ["mood_match", "retro", "mood_match", "wildcard",
                         "mood_match", "retro", "language_match", "wildcard"],
            "cycle_length": 8,
        },
        "default_for_time": ["late_night"],
        "sort_order": 5,
        "active": True,
    },
    {
        "slug": "punjabi_beats",
        "name": "Punjabi Beats",
        "tagline": "Karama se Karachi",
        "description": "Punjabi 80 · Hindi 20. Bhangra, hip-hop. Gurpreet bhaji and Simran teasing each other.",
        "cover_color": "#ff8a5b",
        "cover_image_url": None,
        "language_mix": [{"language": "punjabi", "weight": 0.8}, {"language": "hindi", "weight": 0.2}],
        "allowed_genres": ["punjabi_pop", "bhangra", "hip_hop", "pop"],
        "allowed_moods": ["energetic", "party", "celebration", "uplifting", "dance"],
        "allowed_energy_levels": ["medium", "high", "party"],
        "hosts": [{"voice_key": "gurpreet_bhaji", "role": "primary"},
                  {"voice_key": "simran_punjabi", "role": "secondary"}],
        "music_clock": {
            "rotation": ["language_match", "current_hit", "language_match", "wildcard",
                         "language_match", "retro", "language_match", "current_hit"],
            "cycle_length": 8,
        },
        "default_for_time": ["evening"],
        "sort_order": 6,
        "active": True,
    },
    {
        "slug": "morning_masala",
        "name": "Morning Masala",
        "tagline": "Uthega Dubai!",
        "description": "Hindi 60 · English 40. Wake-up Bollywood + pop with Aanya (Hindi-native) and Aarti.",
        "cover_color": "#4ade80",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.6}, {"language": "english", "weight": 0.4}],
        "allowed_genres": ["bollywood", "pop", "retro", "indie"],
        "allowed_moods": ["uplifting", "energetic", "peppy", "romantic"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "aanya_hindi", "role": "primary"},
                  {"voice_key": "aarti_morning", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "mood_match", "retro", "wildcard",
                         "current_hit", "regional", "mood_match", "current_hit"],
            "cycle_length": 8,
        },
        "default_for_time": ["morning"],
        "sort_order": 7,
        "active": True,
    },
    {
        "slug": "devotional_hour",
        "name": "Devotional Hour",
        "tagline": "Subah ki shanti",
        "description": "Hindi 60 · Sanskrit 20 · English 20. Bhajans, ghazal, sufi. Pandit Anand alone.",
        "cover_color": "#ffb648",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.6}, {"language": "english", "weight": 0.4}],
        "allowed_genres": ["devotional", "sufi", "ghazal", "indie"],
        "allowed_moods": ["peaceful", "devotional", "reflective", "chill", "uplifting"],
        "allowed_energy_levels": ["chill"],
        "hosts": [{"voice_key": "pandit_anand", "role": "solo"}],
        "music_clock": {
            "rotation": ["mood_match", "language_match", "mood_match", "wildcard",
                         "mood_match", "language_match", "retro", "wildcard"],
            "cycle_length": 8,
        },
        "default_for_time": ["morning"],
        "sort_order": 8,
        "active": True,
    },
    {
        "slug": "retro_lounge",
        "name": "Retro Lounge",
        "tagline": "80s/90s wala pyaar",
        "description": "Hindi 70 · English 30. Strictly 80s/90s/2000s Bollywood + retro. Kishore Da hosts with Monika.",
        "cover_color": "#a78bfa",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.7}, {"language": "english", "weight": 0.3}],
        "allowed_genres": ["bollywood", "retro", "ghazal", "indie"],
        "allowed_moods": ["nostalgic", "romantic", "chill", "melancholy"],
        "allowed_energy_levels": ["chill", "medium"],
        "hosts": [{"voice_key": "kishore_retro", "role": "primary"},
                  {"voice_key": "monika_dubai", "role": "secondary"}],
        "music_clock": {
            "rotation": ["retro", "retro", "mood_match", "retro",
                         "regional", "retro", "wildcard", "retro"],
            "cycle_length": 8,
        },
        "default_for_time": ["afternoon", "evening"],
        "sort_order": 9,
        "active": True,
    },
    {
        "slug": "workout_wala",
        "name": "Workout Wala",
        "tagline": "Pump it up",
        "description": "English 50 · Hindi 30 · Punjabi 20. Hip-hop, electronic, bhangra. Charlie DJ leads with Ishita Hindi.",
        "cover_color": "#ff4f6d",
        "cover_image_url": None,
        "language_mix": [{"language": "english", "weight": 0.5},
                         {"language": "hindi", "weight": 0.3},
                         {"language": "punjabi", "weight": 0.2}],
        "allowed_genres": ["hip_hop", "electronic", "punjabi_pop", "pop"],
        "allowed_moods": ["energetic", "party", "intense", "dance"],
        "allowed_energy_levels": ["high", "party"],
        "hosts": [{"voice_key": "charlie_dj", "role": "primary"},
                  {"voice_key": "ishita_hindi", "role": "occasional"}],
        "music_clock": {
            "rotation": ["current_hit", "current_hit", "mood_match", "regional",
                         "current_hit", "current_hit", "wildcard", "current_hit"],
            "cycle_length": 8,
        },
        "default_for_time": ["morning", "afternoon"],
        "sort_order": 10,
        "active": True,
    },
    # ---------- Phase 3: Premium-only channels (promoted to front for upgrade discovery) ----------
    {
        "slug": "vip_lounge",
        "name": "VIP Lounge",
        "tagline": "Strictly mellow, strictly yours",
        "description": "Premium only. Mellow indie + retro Bollywood + late-night chill. Veer goes intimate, Monika adds warmth.",
        "cover_color": "#ffd700",
        "cover_image_url": "https://static.prod-images.emergentagent.com/jobs/6575e7be-4754-4bdb-b0cf-17c22c4a16e8/images/a796d4e8ba873afaac66656a728b3dd94a575f06576b7afc90f3331cb6692dd8.png",
        "language_mix": [{"language": "hindi", "weight": 0.5}, {"language": "english", "weight": 0.5}],
        "allowed_genres": ["indie", "pop", "bollywood", "ghazal", "retro"],
        "allowed_moods": ["chill", "romantic", "nostalgic", "melancholy", "uplifting"],
        "allowed_energy_levels": ["chill", "medium"],
        "hosts": [{"voice_key": "veer_dubai", "role": "primary"},
                  {"voice_key": "monika_dubai", "role": "secondary"}],
        "music_clock": {
            "rotation": ["mood_match", "retro", "mood_match", "wildcard",
                         "mood_match", "retro", "language_match", "wildcard"],
            "cycle_length": 8,
        },
        "default_for_time": ["late_night", "evening"],
        "sort_order": -2,
        "active": True,
        "premium_only": True,
    },
    {
        "slug": "premium_mehfil",
        "name": "Premium Mehfil",
        "tagline": "Deep cuts, gold standard",
        "description": "Premium only. Deep Bollywood cuts + 2020s remixes + curated regional. Aarti + Monika host this gold-tier mehfil.",
        "cover_color": "#ffd700",
        "cover_image_url": "https://static.prod-images.emergentagent.com/jobs/6575e7be-4754-4bdb-b0cf-17c22c4a16e8/images/99977df7586c3a62b55092fcb9f41980f0cd6c56aa34c839163fdfac03b30013.png",
        "language_mix": [{"language": "hindi", "weight": 0.7}, {"language": "english", "weight": 0.3}],
        "allowed_genres": ["bollywood", "pop", "indie", "retro"],
        "allowed_moods": ["romantic", "energetic", "uplifting", "nostalgic", "chill"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "aarti_morning", "role": "primary"},
                  {"voice_key": "monika_dubai", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "current_hit", "retro", "mood_match",
                         "current_hit", "regional", "current_hit", "wildcard"],
            "cycle_length": 8,
        },
        "default_for_time": ["evening", "afternoon"],
        "sort_order": -1,
        "active": True,
        "premium_only": True,
    },
    # ---------- Phase 3.8: DFW market channels (FunAsia AI Radio) ----------
    {
        "slug": "dfw_bollywood_drive",
        "name": "DFW Bollywood Drive",
        "tagline": "Your commute, hyped",
        "description": "Hindi 60 · English 40. Bollywood drive-time energy for the DFW Indian diaspora. Charlie DJ leads with Aanya bringing warmth.",
        "cover_color": "#7A1FA2",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.6}, {"language": "english", "weight": 0.4}],
        "allowed_genres": ["bollywood", "pop", "retro", "indie"],
        "allowed_moods": ["energetic", "uplifting", "happy", "nostalgic"],
        "allowed_energy_levels": ["medium", "high"],
        "hosts": [{"voice_key": "charlie_dj", "role": "primary"},
                  {"voice_key": "aanya_hindi", "role": "secondary"}],
        "music_clock": {
            "rotation": ["current_hit", "retro", "mood_match", "regional",
                         "current_hit", "wildcard", "current_hit", "language_match"],
            "cycle_length": 8,
        },
        "default_for_time": ["morning", "evening"],
        "sort_order": 1,
        "active": True,
        "market": "dfw",
    },
    {
        "slug": "dfw_garba_nights",
        "name": "DFW Garba Nights",
        "tagline": "Navratri & beyond",
        "description": "Hindi 50 · Gujarati 30 · English 20. Garba, devotional & celebration vibes for the DFW community. Kabir + Ishita anchor.",
        "cover_color": "#D946EF",
        "cover_image_url": None,
        "language_mix": [{"language": "hindi", "weight": 0.5},
                         {"language": "gujarati", "weight": 0.3},
                         {"language": "english", "weight": 0.2}],
        "allowed_genres": ["bollywood", "devotional", "regional", "pop"],
        "allowed_moods": ["devotional", "celebration", "uplifting", "energetic"],
        "allowed_energy_levels": ["medium", "high", "party"],
        "hosts": [{"voice_key": "kabir_hindi", "role": "primary"},
                  {"voice_key": "ishita_hindi", "role": "secondary"}],
        "music_clock": {
            "rotation": ["regional", "current_hit", "mood_match", "regional",
                         "current_hit", "wildcard", "regional", "current_hit"],
            "cycle_length": 8,
        },
        "default_for_time": ["evening", "late_night"],
        "sort_order": 2,
        "active": True,
        "market": "dfw",
    },
    # Phase 40 Session 2 — News Radio channel (AI-curated headlines, no music).
    # The radio engine's music pipeline does NOT pick this channel up because
    # `is_music_channel` is False — listeners stream it via /api/news_radio/queue.
    {
        "slug": "news_radio",
        "name": "RadioLife News Radio",
        "tagline": "AI-curated hourly news",
        "description": "Top headlines summarized by gpt-4o-mini, refreshed hourly.",
        "cover_color": "#00d9ff",
        "cover_image_url": None,
        "language_mix": [{"language": "english", "weight": 1.0}],
        "allowed_genres": [],
        "allowed_moods": ["informative"],
        "allowed_energy_levels": ["medium"],
        "hosts": [{"voice_key": "kishore_retro", "role": "primary"}],
        "music_clock": {"rotation": [], "cycle_length": 0},
        "default_for_time": [],
        "sort_order": 99,
        "active": True,
        "is_music_channel": False,
        "category": "news",
    },
]

DEFAULT_CHANNEL_SLUG = "bollywood_mehfil"


# ---------- DB ops ----------
async def seed_channels(db) -> int:
    """Idempotent. Updates name/description/clock/hosts on every boot so a code
    change here propagates without a wipe. Preserves _id (slug) so existing
    sessions and playback_logs remain joinable."""
    created = 0
    for ch in CHANNELS:
        # Phase 15d.1 — channels are globally available programming themes.
        # The RJ wrapper picks up the LISTENER's market via geo; the music
        # catalog filters tracks via `markets_allowed`. Only explicit DFW/
        # regional variants stay scoped (carry their own `market` in the seed).
        doc = {**ch, "_id": ch["slug"], "market": ch.get("market", "global"),
               "updated_at": datetime.now(timezone.utc)}
        existing = await db.channels.find_one({"_id": ch["slug"]})
        if existing:
            # Self-heal: never overwrite a globalised channel's market with
            # the seed default. Drop `market` from the $set so the migration
            # sentinel is honoured.
            if existing.get("_phase15d_market_globalised"):
                doc.pop("market", None)
            await db.channels.update_one({"_id": ch["slug"]}, {"$set": doc})
        else:
            doc["created_at"] = doc["updated_at"]
            await db.channels.insert_one(doc)
            created += 1
    return created


async def get_channel(db, slug: str) -> Optional[dict]:
    return await db.channels.find_one({"_id": slug})


async def list_active_channels(db) -> List[dict]:
    docs = await db.channels.find({"active": True}).sort("sort_order", 1).to_list(50)
    return docs


# ---------- Channel helpers ----------
def channel_primary_language(ch: dict) -> str:
    mix = ch.get("language_mix") or []
    if not mix: return "hindi"
    top = max(mix, key=lambda m: m.get("weight", 0))
    return top.get("language", "hindi")


def channel_supports_duo(ch: dict) -> bool:
    hosts = ch.get("hosts") or []
    if len(hosts) < 2: return False
    return any(h.get("role") != "solo" for h in hosts)


def pick_voice_for_segment(ch: dict, energy: str, force_duo: bool = False
                           ) -> Tuple[str, Optional[str]]:
    """Return (primary_voice_key, secondary_voice_key | None).
    - If channel has only solo host → always solo
    - If channel has duo capability AND force_duo → duo with both hosts
    - Otherwise solo with the primary host
    """
    hosts = ch.get("hosts") or []
    if not hosts:
        return ("veer_dubai", None)  # safe default
    primary = next((h["voice_key"] for h in hosts if h.get("role") == "primary"), None)
    secondary = next((h["voice_key"] for h in hosts if h.get("role") == "secondary"), None)
    solo = next((h["voice_key"] for h in hosts if h.get("role") == "solo"), None)
    if solo and not (primary or secondary):
        return (solo, None)
    if not primary and hosts:
        primary = hosts[0]["voice_key"]
    if force_duo and secondary:
        return (primary, secondary)
    return (primary, None)


# ---------- Music clock ----------
def slot_for_position(ch: dict, segments_played: int) -> str:
    clock = ch.get("music_clock") or {}
    rotation = clock.get("rotation") or ["wildcard"]
    cycle = max(1, int(clock.get("cycle_length") or len(rotation)))
    return rotation[segments_played % cycle]


def _era_bucket(year):
    if not year:
        return None
    if year < 1990:  return "80s"
    if year < 2000:  return "90s"
    if year < 2010:  return "2000s"
    if year < 2020:  return "2010s"
    return "2020s"


def apply_music_clock_slot(candidates: List[dict], slot_type: str,
                           channel: dict, user_pv: dict) -> List[dict]:
    """Filter candidate tracks by slot rule. If 0 candidates survive, return [].
    Caller should fall back to the unfiltered list."""
    primary_lang = channel_primary_language(channel)
    top_mood = (user_pv.get("moods") or [None])[0]

    def is_current_hit(t):
        era = t.get("era") or _era_bucket(t.get("release_year"))
        if era not in ("2010s", "2020s"):
            return False
        d = t.get("danceability")
        return d is None or d > 0.5  # treat unknown danceability permissively

    def is_retro(t):
        era = t.get("era") or _era_bucket(t.get("release_year"))
        return era in ("80s", "90s", "2000s", "pre_2000")

    def is_regional(t):
        lang = t.get("language")
        return lang and lang != primary_lang

    def is_mood_match(t):
        if not top_mood: return False
        if t.get("mood") == top_mood: return True
        return top_mood in (t.get("vibe_tags") or [])

    def is_language_match(t):
        return t.get("language") == primary_lang

    rule = {
        "current_hit":    is_current_hit,
        "retro":          is_retro,
        "regional":       is_regional,
        "mood_match":     is_mood_match,
        "language_match": is_language_match,
        "wildcard":       lambda t: True,
    }.get(slot_type, lambda t: True)
    return [t for t in candidates if rule(t)]


def channel_filter(candidates: List[dict], channel: dict) -> List[dict]:
    """Hard filters: genres, moods, energy_levels of the channel."""
    allowed_genres = set(channel.get("allowed_genres") or [])
    allowed_moods = set(channel.get("allowed_moods") or [])
    allowed_energy = set(channel.get("allowed_energy_levels") or [])
    out: List[dict] = []
    for t in candidates:
        if allowed_energy and t.get("energy_level") not in allowed_energy: continue
        if allowed_genres and t.get("genre") and t.get("genre") not in allowed_genres: continue
        # Mood is soft: allow if matches OR if track has no mood set
        if allowed_moods and t.get("mood") and t.get("mood") not in allowed_moods:
            # Allow via vibe_tags too
            if not any(v in allowed_moods for v in (t.get("vibe_tags") or [])):
                continue
        out.append(t)
    return out
