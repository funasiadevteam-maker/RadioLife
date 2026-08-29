"""Phase 40 Session 2 — News Radio playable queue.

Listener-facing endpoint returning a sequenced list of news segments
(summary text + optional TTS audio URL).  Does NOT go through the
music radio engine — news_radio is a non-music channel.

Phase 42-F.2 — anonymous-friendly + mode banner.
Phase H'.2 — surfaces `news_audio_url` per item; flips `mode="audio"`
when at least half the visible items have rendered audio; admin
`/health` endpoint reports ElevenLabs quota state and audio coverage.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user_optional, require_admin

router = APIRouter(prefix="/api/news_radio", tags=["news-radio"])
admin_router = APIRouter(prefix="/api/admin/news-radio",
                                                tags=["admin-news-radio"])
log = logging.getLogger("bigfm.news_radio")


def _now_iso() -> str: return datetime.now(timezone.utc).isoformat()


def _tts_provider_state() -> dict:
    """Phase H'.2 — reports ElevenLabs scope + quota.

    `tts_enabled` flips to True when the key is present AND the
    renderer batch leg is enabled (`NEWS_TTS_BATCH_ENABLED`).  The
    quota counter is sourced from the shared `services.elevenlabs_tts`
    module so it covers all H' callers (news + RJ segments + persona
    samples).
    """
    key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    batch_flag = (os.environ.get("NEWS_TTS_BATCH_ENABLED")
                              or "true").strip().lower()
    batch_enabled = batch_flag in {"1", "true", "yes", "on"}
    if not key:
        return {"provider": "elevenlabs",
                      "status": "unconfigured",
                      "tts_enabled": False,
                      "notes": ("No ElevenLabs key set — News Radio runs in "
                                          "text-only mode.")}
    try:
        from services.elevenlabs_tts import quota_state
        quota = quota_state()
    except Exception:
        quota = {"chars": 0, "cap": 0, "remaining": 0,
                          "over_quota": False, "calls": 0}
    return {"provider": "elevenlabs",
                  "status": ("active" if batch_enabled else "key_present_batch_disabled"),
                  "tts_enabled": batch_enabled and not quota["over_quota"],
                  "quota":      quota,
                  "notes": ("Live TTS leg — articles render on the hourly cron "
                                      "and on first request per market."
                                      if batch_enabled else
                                      "Batch leg disabled — clear NEWS_TTS_BATCH_ENABLED to re-enable.")}


@router.get("/queue")
async def news_radio_queue(request: Request,
                                                            limit: int = Query(default=6, ge=1, le=20),
                                                            user: Optional[dict] = Depends(current_user_optional)):
    """Returns up to `limit` news segments newest-first."""
    db = request.app.state.db
    items: list[dict] = []
    cur = db.news_articles.find(
        {"summary_script": {"$nin": [None, ""]}}
    ).sort("pubDate", -1).limit(limit)
    async for r in cur:
        script = r.get("summary_script") or ""
        wc = max(1, len(script.split()))
        dur = max(20, min(60, int(wc * 0.4)))
        audio_url = r.get("news_audio_url") or r.get("tts_audio_url")
        items.append({
            "news_id":              r.get("news_id"),
            "title":                  r.get("title"),
            "source_name":      r.get("source_name") or r.get("source_id"),
            "summary_script": script,
            "duration_estimate_sec": (
                int(r.get("news_audio_duration") or dur)),
            "audio_url":          audio_url,
            "voice_id":          r.get("news_audio_voice_id"),
            "text_only":          not bool(audio_url),
            "pubDate":              r.get("pubDate"),
            "image_url":          r.get("image_url"),
        })
    tts = _tts_provider_state()
    audio_count = sum(1 for it in items if it["audio_url"])
    # Mode = "audio" when at least half (>=3 for limit=6) have audio AND
    # the TTS leg is enabled.  Otherwise the banner stays up.
    threshold = max(1, len(items) // 2)
    mode = ("audio" if (tts.get("tts_enabled") and audio_count >= threshold)
                  else "text")
    if not items:
        return {"channel": "news_radio", "count": 0, "items": [],
                      "empty_reason": "cache_cold",
                      "retry_hint": "summaries are pre-rendered hourly — try again in a minute",
                      "mode": "text",
                      "tts": tts,
                      "audio_coverage": {"with_audio": 0, "total": 0},
                      "fetched_at": _now_iso()}
    return {"channel": "news_radio", "count": len(items),
                  "items": items,
                  "mode": mode,
                  "tts": tts,
                  "audio_coverage": {"with_audio": audio_count,
                                                      "total": len(items)},
                  "fetched_at": _now_iso()}


@router.post("/trigger-batch",
                          description="Anonymous-safe trigger to kick a TTS batch render."
                                                "Rate-limited to once per 30s per IP at the route level.")
async def trigger_news_audio_batch(request: Request,
                                                                            top_n: int = Query(default=5, ge=1, le=10),
                                                                            user: Optional[dict] = Depends(current_user_optional)):
    """Phase H'.2 — listener-facing batch kicker.  Used by the consumer
    page on first paint if `audio_coverage.with_audio == 0` so a fresh
    visit doesn't have to wait for the hourly cron to fire."""
    db = request.app.state.db
    try:
        # Bootstrap-safe: render_top_n generates the text summaries FIRST
        # (with a deterministic fallback when the LLM is unavailable) and then
        # the TTS audio leg — so a cold cache can fill from empty. The old
        # audio-only path could never bootstrap when no scripts existed yet.
        from services.news_radio_renderer import render_top_n
        res = await render_top_n(db, n=top_n)
    except Exception as e:
        log.warning("[news-radio] trigger-batch failed: %s", e)
        raise HTTPException(502, {"code": "batch_failed", "error": str(e)[:140]})
    return res


# Phase 42-F.2 / Phase H'.2 — admin health probe.
@admin_router.get("/health",
                                  description="Diagnostic: TTS provider + cache state.")
async def news_radio_health(request: Request,
                                                            _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    total_articles = await db.news_articles.count_documents({})
    with_summary = await db.news_articles.count_documents(
        {"summary_script": {"$nin": [None, ""]}})
    with_audio = await db.news_articles.count_documents(
        {"news_audio_url": {"$nin": [None, ""]}})
    last = await db.news_articles.find_one(
        {"summary_built_at": {"$exists": True, "$ne": None}},
        sort=[("summary_built_at", -1)],
        projection={"summary_built_at": 1, "news_id": 1, "title": 1})
    last_audio = await db.news_articles.find_one(
        {"news_audio_generated_at": {"$exists": True, "$ne": None}},
        sort=[("news_audio_generated_at", -1)],
        projection={"news_audio_generated_at": 1, "news_id": 1, "title": 1,
                              "news_audio_voice_id": 1, "news_audio_char_count": 1})
    tts = _tts_provider_state()
    return {
        "tts": tts,
        "articles": {
            "total":                  total_articles,
            "with_summary":  with_summary,
            "with_audio":      with_audio,
            "missing_summary": max(0, total_articles - with_summary),
            "text_only_clips": max(0, with_summary - with_audio),
        },
        "last_summary": (None if not last else {
            "news_id":  last.get("news_id"),
            "title":      last.get("title"),
            "built_at": last.get("summary_built_at"),
        }),
        "last_audio": (None if not last_audio else {
            "news_id":      last_audio.get("news_id"),
            "title":          last_audio.get("title"),
            "generated_at": last_audio.get("news_audio_generated_at"),
            "voice_id":      last_audio.get("news_audio_voice_id"),
            "char_count":  last_audio.get("news_audio_char_count"),
        }),
        "mode": ("audio" if (tts.get("tts_enabled") and with_audio > 0)
                          else "text"),
        "queried_at": _now_iso(),
    }


@admin_router.post("/batch-render",
                                          description="Phase H'.2 — admin-triggered batch TTS render.")
async def admin_batch_render(request: Request,
                                                            top_n: int = Query(default=5, ge=1, le=25),
                                                            market: Optional[str] = Query(default=None),
                                                            _admin: dict = Depends(require_admin)):
    db = request.app.state.db
    from services.news_radio_renderer import batch_render_news_audio
    return await batch_render_news_audio(db, top_n=top_n, market=market)


@router.get("/voices", description="List selectable News-Radio anchor voices.")
async def news_radio_voices(request: Request):
    from services.news_radio_settings import (
        CURATED_ANCHOR_VOICES, get_anchor_voice)
    db = request.app.state.db
    current = await get_anchor_voice(db)
    return {"voices": CURATED_ANCHOR_VOICES,
            "current_voice_id": current["voice_id"],
            "current_voice_name": current["name"]}


@admin_router.post("/voice", description="Admin — set the News-Radio anchor voice.")
async def news_radio_set_voice(request: Request,
                               _admin: dict = Depends(require_admin)):
    from services.news_radio_settings import set_anchor_voice
    db = request.app.state.db
    body = await request.json()
    try:
        res = await set_anchor_voice(db, (body or {}).get("voice_id"))
    except ValueError:
        raise HTTPException(400, detail={"error": "unknown_voice"})
    return {"ok": True, **res}
