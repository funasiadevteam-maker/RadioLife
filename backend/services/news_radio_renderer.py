"""Phase 40 — AI News Radio renderer.

Pre-renders gpt-4o-mini text summaries (and optionally ElevenLabs TTS) for
the top headlines so the listener-facing /api/news/headlines + the
`news_radio` channel never have to wait on external APIs.

Phase H'.2 adds the TTS audio leg.  For each article that has a
`summary_script` but no `news_audio_url`, we send the script through
`services.elevenlabs_tts.synthesize` using the default news-anchor voice
(Rachel via the `news_anchor` archetype → falls back to legacy
`8vqXJx9Riwp7L4KLhsU3` when nothing else maps).  Audio is saved to
`/app/backend/storage/news_clips/<news_id>.mp3` and served via
`/api/static/news_clips/<news_id>.mp3`.

The renderer is intentionally bounded:
  • `NEWS_TTS_BATCH_TOP_N` (env, default 5) caps how many articles get
    audio per run — protects the daily ElevenLabs char budget.
  • `NEWS_TTS_BATCH_ENABLED` (env, default "true") flips the leg off
    entirely so we can degrade News Radio to text-only mode without
    code changes.
  • The shared `elevenlabs_tts.synthesize` helper soft-circuits at 90%
    of `ELEVENLABS_DAILY_CHAR_CAP`; we just check `over_quota` on the
    response and skip the rest of the batch in that case.
"""
from __future__ import annotations
import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openai import OpenAI

log = logging.getLogger("bigfm.news_radio")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

NEWS_SUMMARY_SYS = (
    "You write SHORT (80-120 words, ~30-45 seconds spoken) news radio "
    "summaries. Tone: neutral, factual, conversational. No opinions, no "
    "speculation. Do not say 'breaking news'. Do not invent details. "
    "Start with a single-sentence hook, then 2-3 sentences of context.")

NEWS_CLIP_DIR = Path("/app/backend/storage/news_clips")
NEWS_CLIP_DIR.mkdir(parents=True, exist_ok=True)

# Phase H'.2 — news anchor archetype (resolves to Rachel via VOICE_REGISTRY
# when the catalog has a matching voice, else falls back to the legacy
# default).  We pass an `archetype` hint instead of hard-wiring a voice_id
# so future persona-targeting (e.g. Spanish news) re-routes automatically.
NEWS_ANCHOR_PSEUDO_PERSONA = {"archetype": "news_anchor"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def render_summary_for_article(db, article: dict) -> Optional[str]:
    """Idempotent — only generates if `summary_script` is missing."""
    if article.get("summary_script"):
        return article["summary_script"]
    if not _openai:
        # Deterministic fallback so the news_radio channel still emits text
        # in dev / quota-exhausted environments.
        text = (f"Here's what's happening: {article.get('title','')}. "
                                f"{(article.get('description') or '')[:280]}")
        await db.news_articles.update_one(
            {"news_id": article["news_id"]},
            {"$set": {"summary_script": text,
                                "summary_built_at": _now_iso(),
                                "summary_source":      "fallback"}})
        return text
    user_msg = (f"Title: {article.get('title')}\n"
                            f"Source: {article.get('source_name') or article.get('source_id')}\n"
                            f"Description: {article.get('description') or '(none)'}\n"
                            f"Categories: {', '.join(article.get('categories') or [])}\n\n"
                            f"Write the radio summary now.")
    try:
        resp = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": NEWS_SUMMARY_SYS},
                              {"role": "user",  "content": user_msg}],
            temperature=0.6, max_tokens=220,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return None
        await db.news_articles.update_one(
            {"news_id": article["news_id"]},
            {"$set": {"summary_script":  text,
                                "summary_built_at": _now_iso(),
                                "summary_source":      "gpt-4o-mini"}})
        return text
    except Exception as e:
        log.warning("[news-radio] summary gen failed for %s: %s",
                              article.get("news_id"), e)
        return None


# ─── Phase H'.2 — TTS audio leg ────────────────────────────────────────
def _tts_enabled() -> bool:
    flag = (os.environ.get("NEWS_TTS_BATCH_ENABLED") or "true").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _tts_top_n() -> int:
    try:
        n = int(os.environ.get("NEWS_TTS_BATCH_TOP_N", "5"))
    except (TypeError, ValueError):
        n = 5
    return max(1, min(n, 25))


def _build_anchor_script(article: dict, summary: str) -> str:
    """Turn the bare summary into a tagged news-anchor script ElevenLabs
    can deliver naturally.  We add a "Now on RadioLife News" intro + source
    sign-off so the audio always sounds like a packaged segment."""
    source = (article.get("source_name") or article.get("source_id")
                          or "the wire").strip()
    title  = (article.get("title") or "").strip()
    body = summary.strip()
    intro = f"[warm] Now on RadioLife News. {title}."
    outro = f"[soft] {source}, RadioLife News."
    return f"{intro} {body} {outro}"


async def synthesize_news_audio(db, article: dict, *,
                                                                            force: bool = False) -> dict:
    """Generates the news clip MP3 for `article`. Returns a dict
    `{ok, news_audio_url, char_count, latency_ms, voice_id, error}`.

    Idempotent: if a `news_audio_url` already exists and the file is on
    disk, we skip the live call (unless `force=True`).
    """
    if not _tts_enabled():
        return {"ok": False, "error": "tts_batch_disabled"}
    if not article.get("summary_script"):
        return {"ok": False, "error": "missing_summary"}

    news_id = article.get("news_id")
    if not news_id:
        return {"ok": False, "error": "missing_news_id"}
    out_path = NEWS_CLIP_DIR / f"{news_id}.mp3"

    if not force and article.get("news_audio_url") and out_path.exists():
        return {"ok": True,
                      "news_audio_url": article["news_audio_url"],
                      "char_count": article.get("news_audio_char_count", 0),
                      "voice_id":      article.get("news_audio_voice_id"),
                      "skipped":      "already_rendered"}

    from services.elevenlabs_tts import (
        synthesize, resolve_voice_id_for_persona)
    voice_id = resolve_voice_id_for_persona(NEWS_ANCHOR_PSEUDO_PERSONA)
    script = _build_anchor_script(article, article["summary_script"])
    res = await asyncio.to_thread(
        synthesize, script, voice_id, energy="medium",
        out_path=out_path)
    if not res["ok"]:
        return {"ok": False,
                      "voice_id": voice_id,
                      "over_quota": res.get("over_quota", False),
                      "error":          res.get("error")}

    # Try ffprobe for duration (best-effort).
    duration_sec = None
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-of", "json",
              "-show_format", str(out_path)],
            capture_output=True, text=True, timeout=4)
        import json as _json
        duration_sec = float(_json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        pass

    audio_url = f"/api/static/news_clips/{news_id}.mp3"
    await db.news_articles.update_one(
        {"news_id": news_id},
        {"$set": {
            "news_audio_url":              audio_url,
            "news_audio_voice_id":      voice_id,
            "news_audio_char_count": res["char_count"],
            "news_audio_provider":      "elevenlabs_turbo_v2_5",
            "news_audio_duration":      duration_sec,
            "news_audio_generated_at": _now_iso(),
            "news_audio_script":          script,
        }})
    log.info("[news-radio] tts ok news_id=%s voice=%s chars=%d ms=%d dur=%s",
                          news_id, voice_id, res["char_count"], res["latency_ms"],
                          duration_sec)
    return {"ok": True,
                  "news_audio_url": audio_url,
                  "char_count":      res["char_count"],
                  "voice_id":          voice_id,
                  "duration_sec":  duration_sec}


async def batch_render_news_audio(db, *, top_n: Optional[int] = None,
                                                                              market: Optional[str] = None) -> dict:
    """Phase H'.2 — render TTS audio for the top-N freshest articles
    that have a summary but no audio.  Soft-stops if the ElevenLabs
    quota soft-cap is hit mid-batch.
    """
    if not _tts_enabled():
        return {"skipped": "tts_batch_disabled"}
    n = top_n if top_n is not None else _tts_top_n()
    q = {"summary_script": {"$nin": [None, ""]},
              "$or": [{"news_audio_url": {"$in": [None, ""]}},
                              {"news_audio_url": {"$exists": False}}]}
    if market:
        q["market"] = market
    cur = db.news_articles.find(q).sort("pubDate", -1).limit(n)
    rendered, failed, over_quota = 0, 0, False
    async for art in cur:
        res = await synthesize_news_audio(db, art)
        if res["ok"]:
            rendered += 1
        else:
            failed += 1
            if res.get("over_quota"):
                over_quota = True
                log.warning("[news-radio] quota soft-cap reached — stopping batch")
                break
    return {"rendered": rendered, "failed": failed,
                  "over_quota": over_quota,
                  "ran_at": _now_iso(),
                  "market": market}


async def render_top_n(db, n: int = 10) -> dict:
    """Render text summaries AND (if enabled) TTS audio for the most
    recent N articles missing them.

    Phase H'.2 extends the original behaviour to chain the audio leg
    after the summary leg — same call site (`refresh_cache` cron + boot)
    keeps working without changes.
    """
    cur = db.news_articles.find(
        {"summary_script": {"$in": [None, ""]}}
    ).sort("pubDate", -1).limit(n)
    rendered = 0
    failed   = 0
    async for art in cur:
        out = await render_summary_for_article(db, art)
        if out:
            rendered += 1
        else:
            failed   += 1
    audio = await batch_render_news_audio(db)
    return {"rendered": rendered, "failed": failed,
                  "audio":      audio,
                  "ran_at": _now_iso()}
