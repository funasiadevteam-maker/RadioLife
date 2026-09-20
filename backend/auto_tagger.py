"""Auto-tagging pipeline for FUUSIC tracks.

Stages (graceful degradation — any stage failing is non-fatal):
1. ID3 / file metadata via mutagen
2. ACRCloud fingerprint (skipped unless ACRCLOUD_TOKEN env var is set)
3. OpenAI gpt-4o-mini classifier → mood/energy/vibe_tags/etc.
4. BPM via librosa (skipped — too heavyweight; we use OpenAI's bpm_estimate)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("bigfm.tagger")

ENERGY_LEVELS = ("chill", "medium", "high", "party")
MOOD_VALUES = (
    "romantic", "energetic", "melancholy", "uplifting", "dance",
    "chill", "devotional", "nostalgic", "party", "sad", "peppy", "intense",
)
TOD_VALUES = ("morning", "afternoon", "evening", "late_night")
LANG_VALUES = ("hindi", "punjabi", "english", "arabic", "mixed", "bollywood", "tamil", "telugu", "other")
ERA_VALUES = ("pre_2000", "2000s", "2010s", "2020s")


def read_id3(path: str | Path) -> Dict[str, Any]:
    """Pull title/artist/album/genre/year/language from ID3 via mutagen."""
    out: Dict[str, Any] = {}
    try:
        from mutagen import File as MutagenFile
        from mutagen.id3 import ID3
        mf = MutagenFile(str(path))
        if mf is None:
            return out
        tags = getattr(mf, "tags", None)
        if tags is None:
            return out
        def _get(*keys):
            for k in keys:
                if k in tags:
                    v = tags[k]
                    try:
                        return str(v.text[0]) if hasattr(v, "text") else str(v)
                    except Exception:
                        return str(v)
            return None
        out["title"]   = _get("TIT2", "title")
        out["artist"]  = _get("TPE1", "artist")
        out["album"]   = _get("TALB", "album")
        out["genre"]   = _get("TCON", "genre")
        year = _get("TDRC", "TYER", "date")
        if year:
            m = re.search(r"(19|20)\d{2}", str(year))
            if m:
                out["release_year"] = int(m.group(0))
        out["language"] = _get("TLAN", "language")
    except Exception as e:
        logger.warning(f"mutagen read failed for {path}: {e}")
    return {k: v for k, v in out.items() if v}


def _coerce_enum(val: Any, allowed: tuple, default: str) -> str:
    if isinstance(val, str) and val.lower() in allowed:
        return val.lower()
    return default


def _coerce_enum_list(val: Any, allowed: tuple) -> list[str]:
    if not isinstance(val, list):
        return []
    return [v.lower() for v in val if isinstance(v, str) and v.lower() in allowed]


def openai_classify(openai_client, title: str, artist: str, duration_sec: float,
                    genre: Optional[str] = None) -> Dict[str, Any]:
    """Run gpt-4o-mini classifier on track. Returns normalized dict."""
    fallback = {
        "mood": "uplifting",
        "energy_level": "medium",
        "vibe_tags": [],
        "recommended_time_of_day": [],
        "language_confidence": "other",
        "era": "2020s",
        "bpm_estimate": 100,
        "danceability": 0.5,
        "explicit": False,
    }
    if not openai_client:
        return fallback

    prompt = (
        "Classify this song for a personalized radio engine. Respond as strict JSON only — no prose.\n\n"
        f"Track: \"{title}\" by {artist}\n"
        f"Genre: {genre or 'unknown'}\n"
        f"Duration: {duration_sec:.0f}s\n\n"
        "Return JSON with exactly these fields:\n"
        "{\n"
        f"  \"mood\": one of {list(MOOD_VALUES)},\n"
        f"  \"energy_level\": one of {list(ENERGY_LEVELS)},\n"
        "  \"vibe_tags\": array of 3-5 lowercase short tags like \"late-night\",\"monsoon\",\"road-trip\",\"workout\",\"cafe\",\"heartbreak\",\"celebration\",\"drive\",\"study\",\"wedding\",\n"
        f"  \"recommended_time_of_day\": array of any of {list(TOD_VALUES)},\n"
        f"  \"language_confidence\": one of {list(LANG_VALUES)},\n"
        f"  \"era\": one of {list(ERA_VALUES)},\n"
        "  \"bpm_estimate\": integer 60-180,\n"
        "  \"danceability\": float 0.0-1.0,\n"
        "  \"explicit\": boolean\n"
        "}"
    )
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"OpenAI classify failed for '{title}': {e}")
        return fallback

    normalized = {
        "mood": _coerce_enum(data.get("mood"), MOOD_VALUES, "uplifting"),
        "energy_level": _coerce_enum(data.get("energy_level"), ENERGY_LEVELS, "medium"),
        "vibe_tags": [t.lower().strip() for t in (data.get("vibe_tags") or []) if isinstance(t, str)][:5],
        "recommended_time_of_day": _coerce_enum_list(data.get("recommended_time_of_day"), TOD_VALUES),
        "language_confidence": _coerce_enum(data.get("language_confidence"), LANG_VALUES, "other"),
        "era": _coerce_enum(data.get("era"), ERA_VALUES, "2020s"),
        "bpm_estimate": int(data.get("bpm_estimate") or 100) if isinstance(data.get("bpm_estimate"), (int, float)) else 100,
        "danceability": float(max(0.0, min(1.0, data.get("danceability") or 0.5))),
        "explicit": bool(data.get("explicit")),
    }
    return normalized


def auto_tag(
    openai_client,
    file_path: str | Path,
    user_title: Optional[str] = None,
    user_artist: Optional[str] = None,
) -> Dict[str, Any]:
    """Full enrichment pipeline. Returns metadata dict suitable for Mongo upsert."""
    id3 = read_id3(file_path)

    title = (user_title or id3.get("title") or Path(file_path).stem).strip()
    artist = (user_artist or id3.get("artist") or "Unknown Artist").strip()
    album = id3.get("album")
    genre = id3.get("genre")
    release_year = id3.get("release_year")
    id3_language = id3.get("language")

    # Duration via mutagen for the classifier prompt
    duration_sec = 0.0
    try:
        from mutagen import File as MutagenFile
        mf = MutagenFile(str(file_path))
        if mf and mf.info:
            duration_sec = float(mf.info.length or 0)
    except Exception:
        pass

    # ACRCloud is skipped in this iteration — no token configured.
    # Hook left intentionally; future call would refine title/artist/album/isrc.
    fingerprint_match_score = None

    # OpenAI classifier
    cls = openai_classify(openai_client, title, artist, duration_sec, genre)

    language = id3_language or cls["language_confidence"]

    return {
        "title": title,
        "artist": artist,
        "album": album,
        "genre": genre,
        "release_year": release_year,
        "mood": cls["mood"],
        "energy_level": cls["energy_level"],
        "vibe_tags": cls["vibe_tags"],
        "recommended_time_of_day": cls["recommended_time_of_day"],
        "language": language,
        "language_confidence": cls["language_confidence"],
        "era": cls["era"],
        "bpm": cls["bpm_estimate"],
        "danceability": cls["danceability"],
        "explicit": cls["explicit"],
        "isrc": None,
        "fingerprint_match_score": fingerprint_match_score,
        "auto_tagged_at": datetime.now(timezone.utc).isoformat(),
        "manual_overrides": [],
    }
