"""Phase 36b — Podcast transcription orchestration.

Bridges AssemblyAI (or its mock) into the podcast pipeline. One row per
transcription job lives in `podcast_transcripts`.

Auto-fire policy:
    Episode publish → kick_transcription() (this module).
    Transcript completion → schedule_ai_metadata() (separate module).
    Apply: creator MUST explicitly approve via apply-metadata.

Collection `podcast_transcripts`:
    {id, episode_id, channel_id, provider, transcript_id, status,
     text, utterances_json, language_code, confidence_score,
     error_message, manual_edit, created_at, completed_at}
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from services import assemblyai_client as aai

logger = logging.getLogger("bigfm.podcast_transcription")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _provider() -> str:
    return "assemblyai" if aai.is_live() else "mock"


async def kick_transcription(db, *, episode_id: str) -> dict:
    """Auto-fired on episode publish. Idempotent: if a non-error row
    already exists for this episode, returns it.

    Mock mode: synchronously completes inside this call so tests + the UI
    see status=completed within the same request.
    Live mode: returns status=processing; the background poller
    `poll_pending_transcriptions()` advances it later.
    """
    ep = await db.podcast_episodes.find_one({"id": episode_id}, {"_id": 0})
    if not ep:
        raise ValueError(f"episode_not_found:{episode_id}")

    existing = await db.podcast_transcripts.find_one(
        {"episode_id": episode_id, "status": {"$ne": "error"}},
        {"_id": 0})
    if existing and existing.get("status") in ("processing", "completed"):
        return existing

    base = os.environ.get("PODCAST_PUBLIC_BASE_URL", "").rstrip("/")
    audio_url = (ep.get("audio_url_external")
                          or (base + f"/api/podcasts/episodes/{episode_id}/audio.mp3"))
    language_hint = None
    ch = await db.podcast_channels.find_one(
        {"id": ep["channel_id"]}, {"language": 1, "_id": 0})
    if ch and ch.get("language") in ("en", "hi"):
        language_hint = ch["language"]

    row = {
        "id":                            _gen("ptr"),
        "episode_id":             episode_id,
        "channel_id":             ep["channel_id"],
        "provider":                 _provider(),
        "transcript_id":         None,
        "status":                     "pending",
        "text":                          None,
        "utterances_json":   [],
        "language_code":       None,
        "confidence_score": None,
        "error_message":      None,
        "manual_edit":           False,
        "created_at":             _now(),
        "completed_at":         None,
    }
    await db.podcast_transcripts.insert_one(row)

    try:
        tid = await aai.submit_transcription(
            audio_url, language_hint=language_hint,
            episode_title=ep.get("title") or "",
            episode_id=episode_id)
    except Exception as e:
        logger.exception("[transcription] submit failed: %s", e)
        await db.podcast_transcripts.update_one(
            {"id": row["id"]},
            {"$set": {"status": "error", "error_message": str(e)[:300]}})
        row["status"] = "error"; row["error_message"] = str(e)[:300]
        return row

    await db.podcast_transcripts.update_one(
        {"id": row["id"]},
        {"$set": {"transcript_id": tid, "status": "processing"}})
    row["transcript_id"] = tid; row["status"] = "processing"

    # Mock mode: poll immediately so the request returns a completed row.
    if not aai.is_live():
        await _advance_row(db, row["id"])
        return await db.podcast_transcripts.find_one(
            {"id": row["id"]}, {"_id": 0})
    return row


async def _advance_row(db, row_id: str) -> Optional[dict]:
    """Polls AssemblyAI once for a single row and writes back the new
    state. No-op if the row is already in a terminal state."""
    row = await db.podcast_transcripts.find_one({"id": row_id}, {"_id": 0})
    if not row: return None
    if row["status"] in ("completed", "error"): return row
    if not row.get("transcript_id"):
        return row
    try:
        payload = await aai.poll_transcription(row["transcript_id"])
    except Exception as e:
        await db.podcast_transcripts.update_one(
            {"id": row_id},
            {"$set": {"status": "error", "error_message": str(e)[:300]}})
        return None
    status = payload.get("status")
    if status == "completed":
        upd = {
            "status":                    "completed",
            "text":                       payload.get("text") or "",
            "utterances_json":   payload.get("utterances") or [],
            "language_code":       payload.get("language_code") or "en",
            "confidence_score": float(payload.get("confidence") or 0.0),
            "completed_at":         _now(),
        }
        await db.podcast_transcripts.update_one({"id": row_id}, {"$set": upd})
        # Auto-fire AI metadata generation (best-effort, never fails the
        # transcript update).
        try:
            from services import podcast_ai_metadata as ai_md
            await ai_md.generate_metadata(db, episode_id=row["episode_id"])
        except Exception as e:
            logger.warning("[transcription] auto-AI failed: %s", e)
        return await db.podcast_transcripts.find_one({"id": row_id}, {"_id": 0})
    if status == "error":
        await db.podcast_transcripts.update_one(
            {"id": row_id},
            {"$set": {"status": "error",
                          "error_message": (payload.get("error") or "unknown")[:300]}})
    # Still processing — leave the row as-is.
    return None


async def poll_pending_transcriptions(db) -> int:
    """Advance every processing row by one poll. Called by lifespan cron
    every 30s in live mode. Returns the count of advanced rows."""
    advanced = 0
    cursor = db.podcast_transcripts.find(
        {"status": "processing"}, {"id": 1, "_id": 0})
    async for r in cursor:
        out = await _advance_row(db, r["id"])
        if out and out.get("status") in ("completed", "error"):
            advanced += 1
    return advanced


async def patch_transcript_text(db, *, episode_id: str, text: str) -> dict:
    """Creator-edited transcript. Collapses utterances into a single
    'edited' block; downstream AI knows manual_edit=True so it doesn't
    re-derive from speaker labels."""
    text = (text or "").strip()
    row = await db.podcast_transcripts.find_one(
        {"episode_id": episode_id}, sort=[("created_at", -1)])
    if not row:
        raise ValueError("transcript_not_found")
    new_utterances = [{"speaker": "EDITED", "start": 0,
                                  "end": int((row.get("confidence_score") or 0) * 0) + 1000,
                                  "text": text[:200000]}]
    upd = {
        "text":                       text[:200000],
        "utterances_json":   new_utterances,
        "manual_edit":           True,
    }
    await db.podcast_transcripts.update_one(
        {"id": row["id"]}, {"$set": upd})
    r = await db.podcast_transcripts.find_one({"id": row["id"]}, {"_id": 0})
    return r


async def get_transcript(db, *, episode_id: str) -> Optional[dict]:
    return await db.podcast_transcripts.find_one(
        {"episode_id": episode_id}, {"_id": 0},
        sort=[("created_at", -1)])


def utterances_to_srt(utterances: list) -> str:
    """Build a valid SRT (SubRip) string from AssemblyAI-shaped utterances."""
    def _t(ms: float) -> str:
        ms = max(0, int(round(ms or 0)))
        h = ms // 3_600_000
        m = (ms % 3_600_000) // 60_000
        s = (ms % 60_000) // 1000
        mm = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d},{mm:03d}"
    out = []
    for i, u in enumerate(utterances or [], start=1):
        spk = u.get("speaker") or "?"
        out.append(str(i))
        out.append(f"{_t(u.get('start', 0))} --> {_t(u.get('end', 0))}")
        text = (u.get("text") or "").strip()
        out.append(f"[Speaker {spk}] {text}" if spk and spk != "?" else text)
        out.append("")
    return "\n".join(out)
