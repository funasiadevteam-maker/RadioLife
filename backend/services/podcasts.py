"""Phase 36a — Podcast Foundation: DB ops + FFmpeg transcode + file storage.

Collections:
  - podcast_creators            {id, user_id, display_name, bio, contact_email,
                                              market, application_status, applied_at,
                                              approved_at, approved_by, rejection_reason}
  - podcast_channels            {id, creator_id, slug, title, description, category,
                                              language, city, cover_image_url, explicit_flag,
                                              subscriber_only, rss_enabled, active,
                                              approval_status, tags, follower_count,
                                              created_at, updated_at}
  - podcast_episodes            {id, channel_id, title, description, show_notes, tags,
                                              audio_url, audio_url_external, video_url,
                                              cover_image_url, duration_seconds,
                                              file_size_bytes, season, episode_number,
                                              episode_type, explicit_flag, subscriber_only,
                                              publish_status, published_at,
                                              scheduled_publish_time, guid, source,
                                              storage_path, created_at, updated_at,
                                              archived_at}
  - podcast_feeds                  {channel_id, last_built_at, cached_xml, etag}
  - podcast_platform_submissions {id, channel_id, platform_name, platform_status,
                                                 submission_url, platform_show_url,
                                                 last_checked_at}
  - podcast_followers           {user_id, channel_id, followed_at}
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.podcasts")

STORAGE_ROOT = Path(os.environ.get("PODCASTS_STORAGE_ROOT",
                                                          "/app/backend/storage/podcasts"))

CATEGORIES = {"business", "food_local", "movies_culture", "real_estate",
                       "health_wellness", "legal_finance", "events_community",
                       "news_commentary", "comedy", "true_crime", "devotional",
                       "sports", "tech", "education", "other"}

DISTRIBUTION_PLATFORMS = [
    "apple_podcasts", "spotify", "amazon_music", "youtube_music",
    "pocket_casts", "overcast", "castbox", "podcast_index", "listen_notes",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def slugify(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "channel")[:60]


# ─── Creator applications ─────────────────────────────────────────
async def submit_creator_application(db, *, user_id: str, display_name: str,
                                                                  bio: str, contact_email: str,
                                                                  market: str) -> dict:
    existing = await db.podcast_creators.find_one({"user_id": user_id})
    if existing:
        return existing
    doc = {
        "id":                            _gen("crt"),
        "user_id":                  user_id,
        "display_name":        display_name.strip()[:80],
        "bio":                          (bio or "").strip()[:1000],
        "contact_email":        contact_email.strip()[:120],
        "market":                    (market or "dubai")[:32],
        "application_status": "pending",
        "applied_at":              _now(),
        "approved_at":           None,
        "approved_by":           None,
        "rejection_reason":   None,
    }
    await db.podcast_creators.insert_one(doc)
    return doc


async def approve_creator(db, *, creator_id: str, admin_user_id: str) -> Optional[dict]:
    r = await db.podcast_creators.find_one_and_update(
        {"id": creator_id},
        {"$set": {"application_status": "approved",
                      "approved_at":             _now(),
                      "approved_by":             admin_user_id,
                      "rejection_reason":   None}},
        return_document=True)
    return r


async def reject_creator(db, *, creator_id: str, admin_user_id: str,
                                          reason: str) -> Optional[dict]:
    r = await db.podcast_creators.find_one_and_update(
        {"id": creator_id},
        {"$set": {"application_status": "rejected",
                      "rejection_reason":   (reason or "")[:300],
                      "approved_by":             admin_user_id}},
        return_document=True)
    return r


async def get_creator_by_user(db, user_id: str) -> Optional[dict]:
    return await db.podcast_creators.find_one({"user_id": user_id})


async def require_approved_creator(db, user: dict) -> dict:
    """Returns the creator doc or raises HTTPException 403."""
    from fastapi import HTTPException
    c = await get_creator_by_user(db, user["user_id"])
    if not c:
        raise HTTPException(403, "no_creator_application")
    if c.get("application_status") != "approved":
        raise HTTPException(403, f"creator_{c.get('application_status') or 'unknown'}")
    return c


# ─── Channels ───────────────────────────────────────────────────
async def create_channel(db, *, creator_id: str, body: dict) -> dict:
    cat = body.get("category") or "other"
    if cat not in CATEGORIES:
        from fastapi import HTTPException
        raise HTTPException(400, f"invalid_category:{cat}")
    title = (body.get("title") or "").strip()[:120]
    if not title:
        from fastapi import HTTPException
        raise HTTPException(400, "title_required")
    slug_base = body.get("slug") or slugify(title)
    slug = slug_base
    i = 0
    while await db.podcast_channels.find_one({"slug": slug}):
        i += 1
        slug = f"{slug_base}-{i}"
    doc = {
        "id":                        _gen("pch"),
        "creator_id":          creator_id,
        "slug":                    slug,
        "title":                    title,
        "description":      (body.get("description") or "")[:2000],
        "category":            cat,
        "language":            (body.get("language") or "en")[:8],
        "city":                      (body.get("city") or "")[:64],
        "cover_image_url": body.get("cover_image_url") or None,
        "explicit_flag":     bool(body.get("explicit_flag")),
        "subscriber_only": bool(body.get("subscriber_only")),
        "rss_enabled":      bool(body.get("rss_enabled", True)),
        "script_preference": (body.get("script_preference") or "auto"),    # 36b round-2
        "active":                  False,    # admin must approve before going live
        "approval_status": "pending",
        "tags":                    list(body.get("tags") or [])[:10],
        "follower_count":  0,
        "created_at":          _now(),
        "updated_at":         _now(),
    }
    await db.podcast_channels.insert_one(doc)
    return doc


async def update_channel(db, *, channel_id: str, creator_id: Optional[str],
                                          body: dict) -> Optional[dict]:
    q = {"id": channel_id}
    if creator_id:
        q["creator_id"] = creator_id
    allowed = {"title", "description", "category", "language", "city",
                  "cover_image_url", "explicit_flag", "subscriber_only",
                  "rss_enabled", "tags", "script_preference"}
    upd = {k: v for k, v in (body or {}).items() if k in allowed}
    if "category" in upd and upd["category"] not in CATEGORIES:
        from fastapi import HTTPException
        raise HTTPException(400, f"invalid_category:{upd['category']}")
    upd["updated_at"] = _now()
    r = await db.podcast_channels.find_one_and_update(
        q, {"$set": upd}, return_document=True)
    return r


# ─── Episodes ───────────────────────────────────────────────────
def _ep_dir(channel_id: str, ep_id: str) -> Path:
    p = STORAGE_ROOT / channel_id / ep_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def ffprobe_duration(path: Path) -> Optional[float]:
    """Returns audio duration in seconds, or None on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)
        return None


def ffmpeg_transcode_to_aac128(src: Path, dst: Path) -> bool:
    """Transcode src → dst as MP3/128kbps. Returns True on success."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-codec:a", "libmp3lame",
              "-b:a", "128k", "-ar", "44100", str(dst)],
            capture_output=True, text=True, timeout=180)
        return out.returncode == 0 and dst.exists()
    except Exception as e:
        logger.warning("ffmpeg failed: %s", e)
        return False


async def ingest_episode_upload(db, *, channel_id: str, body: dict,
                                                          audio_bytes: Optional[bytes] = None,
                                                          audio_filename: str = "audio.mp3"
                                                          ) -> dict:
    """Persist an episode from an uploaded audio file. Caller already
    validated channel ownership."""
    ep_id = _gen("pep")
    edir = _ep_dir(channel_id, ep_id)
    audio_path = edir / f"original_{audio_filename}"
    transcoded_path = edir / "audio.mp3"
    duration = None
    file_size = 0
    audio_url = None
    if audio_bytes is not None:
        audio_path.write_bytes(audio_bytes)
        file_size = audio_path.stat().st_size
        ok = await asyncio.get_event_loop().run_in_executor(
            None, ffmpeg_transcode_to_aac128, audio_path, transcoded_path)
        duration = await asyncio.get_event_loop().run_in_executor(
            None, ffprobe_duration, transcoded_path if ok else audio_path)
        audio_url = f"/api/podcasts/episodes/{ep_id}/audio.mp3"
    doc = {
        "id":                        ep_id,
        "channel_id":         channel_id,
        "guid":                    f"bigfm-ep-{ep_id}",
        "title":                    (body.get("title") or "Untitled episode")[:200],
        "description":      (body.get("description") or "")[:2000],
        "show_notes":      (body.get("show_notes") or "")[:8000],
        "tags":                    list(body.get("tags") or [])[:15],
        "audio_url":           audio_url,
        "audio_url_external": body.get("audio_url_external"),
        "video_url":          body.get("video_url"),
        "cover_image_url": body.get("cover_image_url") or None,
        "duration_seconds":  duration,
        "file_size_bytes":  file_size,
        "season":                int(body.get("season") or 1),
        "episode_number":  int(body.get("episode_number") or 0),
        "episode_type":     body.get("episode_type") or "full",
        "explicit_flag":     bool(body.get("explicit_flag")),
        "subscriber_only": bool(body.get("subscriber_only")),
        "publish_status":   "draft",
        "published_at":       None,
        "scheduled_publish_time": body.get("scheduled_publish_time"),
        "source":                  body.get("source") or "upload",
        "storage_path":     str(edir),
        "created_at":           _now(),
        "updated_at":          _now(),
        "archived_at":          None,
    }
    await db.podcast_episodes.insert_one(doc)
    return doc


async def publish_episode(db, *, ep_id: str) -> Optional[dict]:
    r = await db.podcast_episodes.find_one_and_update(
        {"id": ep_id, "publish_status": {"$ne": "archived"}},
        {"$set": {"publish_status": "published",
                      "published_at": _now()}},
        return_document=True)
    if r:
        await invalidate_feed_cache(db, channel_id=r["channel_id"])
    return r


async def archive_episode(db, *, ep_id: str) -> Optional[dict]:
    r = await db.podcast_episodes.find_one_and_update(
        {"id": ep_id},
        {"$set": {"publish_status": "archived",
                      "archived_at": _now()}},
        return_document=True)
    if r:
        await invalidate_feed_cache(db, channel_id=r["channel_id"])
    return r


# ─── Distribution ──────────────────────────────────────────────
async def get_distribution(db, *, channel_id: str) -> list:
    rows = await db.podcast_platform_submissions.find(
        {"channel_id": channel_id}, {"_id": 0}).to_list(50)
    by_plat = {r["platform_name"]: r for r in rows}
    out = []
    for p in DISTRIBUTION_PLATFORMS:
        out.append(by_plat.get(p) or {
            "id":                        None,
            "channel_id":         channel_id,
            "platform_name":   p,
            "platform_status": "not_submitted",
            "submission_url": None,
            "platform_show_url": None,
            "last_checked_at": None,
        })
    return out


async def submit_distribution(db, *, channel_id: str, platform: str,
                                                  submission_url: Optional[str],
                                                  platform_show_url: Optional[str]) -> dict:
    if platform not in DISTRIBUTION_PLATFORMS:
        from fastapi import HTTPException
        raise HTTPException(400, f"invalid_platform:{platform}")
    doc = {
        "id":                            _gen("pps"),
        "channel_id":             channel_id,
        "platform_name":       platform,
        "platform_status":     "pending",
        "submission_url":     submission_url,
        "platform_show_url": platform_show_url,
        "last_checked_at":    _now(),
    }
    await db.podcast_platform_submissions.update_one(
        {"channel_id": channel_id, "platform_name": platform},
        {"$set": doc}, upsert=True)
    return doc


# ─── Feeds ─────────────────────────────────────────────────────
async def invalidate_feed_cache(db, *, channel_id: str) -> None:
    await db.podcast_feeds.update_one(
        {"channel_id": channel_id},
        {"$set": {"cached_xml": None, "invalidated_at": _now()}},
        upsert=True)


async def get_followers_count(db, *, channel_id: str) -> int:
    return await db.podcast_followers.count_documents({"channel_id": channel_id})
