"""Phase 36b — AI metadata generation pipeline.

Reads the latest completed transcript for an episode and produces:
    title, title_alternatives[], description, show_notes (markdown),
    chapters[], seo_keywords[], social_captions {twitter, instagram,
    linkedin, youtube}, hashtags[], sponsor_read_suggestions[],
    summary_short, summary_long.

Uses the SAME OpenAI client wiring as services/trivia_ai.py and
services/ai_ad_creator.py — does NOT add a new SDK or rewire env vars.
Model: gpt-4o-mini, response_format=json_object.

Every generation run is logged to `podcast_ai_tasks` so creators can
"re-roll" without losing prior versions.

Chapter count tiers (utterance-aligned, never split mid-sentence):
    ≤10  min →   3 chapters
    10-30 min →   4-5 chapters
    30-60 min →   5-7 chapters
    >60  min →   capped at 7 chapters
"""
from __future__ import annotations
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from openai import OpenAI

from core.config import OPENAI_API_KEY

logger = logging.getLogger("bigfm.podcast_ai_metadata")

_MODEL = "gpt-4o-mini"
_CLIENT: Optional[OpenAI] = None


def _client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    return _CLIENT


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _target_chapter_count(duration_seconds: float) -> int:
    m = (duration_seconds or 0) / 60.0
    if m <= 10:  return 3
    if m <= 30:  return 4
    if m <= 60:  return 6
    return 7


def _build_prompt(*, transcript_text: str, utterances: list,
                            channel_title: str, channel_category: str,
                            channel_language: str, episode_title: str,
                            duration_seconds: float,
                            target_chapters: int,
                            script_preference: str = "auto") -> tuple[str, str]:
    lang = (channel_language or "en").lower()
    pref = (script_preference or "auto").lower()
    # script_preference takes precedence over the channel language default.
    # - "latin"             → always Latin script titles, even for hi channels
    # - "devanagari"  → Devanagari allowed for hi channels (and forced if natural)
    # - "auto" (default) → hi → Devanagari OK; everything else → Latin
    if pref == "latin":
        title_lang_rule = (
            "Write the title in LATIN SCRIPT ONLY (no Devanagari, no other "
            "non-Latin scripts). Hinglish words rendered in Latin letters "
            "are fine; pure-English titles are fine."
        )
    elif pref == "devanagari":
        title_lang_rule = (
            "Write the title in DEVANAGARI when natural for the transcript. "
            "If the transcript is mostly English, a Latin-script title is "
            "acceptable."
        )
    else:    # auto
        title_lang_rule = (
            "Write the title in NATURAL ENGLISH only "
            "(no Hinglish, no Devanagari)."
            if lang != "hi" else
            "Write the title in Hindi or English — whichever flows naturally "
            "for the transcript."
        )
    body_lang_rule = (
        "For description, show_notes, and social captions: if the transcript "
        "contains Hindi/Hinglish words, preserve them naturally. Do not "
        "translate Hinglish phrases to pure English."
        if lang in ("hi", "hinglish") else
        "Write description, show_notes, and social captions in clean English."
    )

    # Build utterance window for chapter alignment. Cap at 80 entries.
    utt_window = []
    for i, u in enumerate(utterances[:80]):
        utt_window.append({
            "i":         i,
            "start": float(u.get("start", 0)) / 1000.0,
            "end":   float(u.get("end",     0)) / 1000.0,
            "spk":   u.get("speaker") or "?",
            "text": (u.get("text") or "")[:240],
        })
    utt_blob = json.dumps(utt_window, ensure_ascii=False)
    sys = (
        f"You are a podcast metadata writer for RadioLife. Channel: "
        f"'{channel_title}' (category: {channel_category}, language: {lang}).\n"
        f"Episode current title: '{episode_title}'. Duration: "
        f"{int(duration_seconds or 0)}s.\n\n"
        f"{title_lang_rule}\n{body_lang_rule}\n\n"
        f"Generate EXACTLY {target_chapters} chapters. Each chapter MUST "
        f"start at an utterance boundary (use 'start' values from the "
        f"utterances array — never invent or split mid-utterance).\n"
        f"Return strict JSON matching this schema:\n"
        '{\n'
        '  "title": "...",                                         // <= 80 chars\n'
        '  "title_alternatives": ["...","...","..."],   // 3 strings, each <= 80\n'
        '  "description": "...",                                // <= 300 chars\n'
        '  "show_notes": "...",                              // markdown, <= 4000 chars\n'
        f'  "chapters": [{{ "title":"...", "start_time_seconds":0, "end_time_seconds":0, "summary":"..."}}] // EXACTLY {target_chapters} entries\n'
        '  "seo_keywords": ["...", ...],                  // 6-12 entries\n'
        '  "social_captions": {"twitter":"<=240ch","instagram":"...","linkedin":"...","youtube":"..."},\n'
        '  "hashtags": ["#...", ...],                          // 4-8 entries\n'
        '  "sponsor_read_suggestions": [{"slot":"pre_roll|mid_roll|post_roll","script_text":"...","length_seconds":30}],\n'
        '  "summary_short": "...",                              // <= 150 chars\n'
        '  "summary_long":  "..."                                  // <= 1000 chars\n'
        '}\n'
        "No commentary outside JSON. Ensure chapters' start_time_seconds "
        "values are STRICTLY INCREASING and end_time_seconds equals the next "
        "chapter's start (last chapter's end equals episode duration)."
    )
    user = (
        f"Episode utterances (truncated to 80): {utt_blob}\n\n"
        f"Full transcript text (truncated):\n"
        f"{(transcript_text or '')[:8000]}"
    )
    return sys, user


def _empty_metadata() -> dict:
    return {
        "title":                                     "",
        "title_alternatives":          [],
        "description":                       "",
        "show_notes":                       "",
        "chapters":                             [],
        "seo_keywords":                   [],
        "social_captions":               {"twitter": "", "instagram": "",
                                                            "linkedin": "", "youtube": ""},
        "hashtags":                             [],
        "sponsor_read_suggestions": [],
        "summary_short":                  "",
        "summary_long":                    "",
        "chapter_alignment_log": [],
    }


def _safe_truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else (s[:n - 1] + "…")


def _snap_chapters_to_utterances(raw_chapters: list, utterances: list,
                                                                          duration_seconds: float,
                                                                          target_chapters: int
                                                                          ) -> tuple[list, list]:
    """Phase 36b Round-2 — snap LLM-proposed chapter start/end times to the
    nearest utterance.start (in seconds). Returns (snapped_chapters,
    alignment_log).

    Why: the LLM tends to round chapter starts to whole seconds (3.0, 14.0)
    instead of using actual utterance boundaries (3.2, 14.5). The brief
    requires exact utterance-boundary alignment, never split mid-sentence.

    Rules:
      - Each chapter's start_time_seconds := nearest utterance.start.
      - If two consecutive chapters snap to the same utterance, drop the
          duplicate. (Chapter count may shrink — still respects the MAX cap.)
      - end_time_seconds derived from next chapter's start (last = duration).
      - Tolerance is ZERO: exact match required after snap.
    """
    if not utterances:
        return raw_chapters[:target_chapters], []
    # Build the universe of utterance.start values in seconds.
    starts_sec: list[tuple[int, float, float]] = []    # (idx, start_s, end_s)
    for i, u in enumerate(utterances):
        s_ms = float(u.get("start", 0) or 0)
        e_ms = float(u.get("end",     0) or 0)
        starts_sec.append((i, s_ms / 1000.0, e_ms / 1000.0))

    snapped: list = []
    log: list = []
    seen_indices: set = set()
    last_start = -1.0
    for c in raw_chapters[:target_chapters]:
        proposed = float(c.get("start_time_seconds") or 0)
        # Find nearest utterance start.
        nearest = min(starts_sec, key=lambda t: abs(t[1] - proposed))
        idx, snapped_start, _ = nearest
        # Drop duplicates pointing at the same utterance.
        if idx in seen_indices:
            log.append({
                "llm_proposed_start":      proposed,
                "snapped_start":              snapped_start,
                "snap_delta_ms":             round((snapped_start - proposed) * 1000),
                "source_utterance_index": idx,
                "dropped_as_duplicate":  True,
            })
            continue
        # Enforce monotonic strict-increasing on snapped starts; if a snap
        # would collapse onto an earlier chapter, drop this one too.
        if snapped_start <= last_start:
            log.append({
                "llm_proposed_start":      proposed,
                "snapped_start":              snapped_start,
                "snap_delta_ms":             round((snapped_start - proposed) * 1000),
                "source_utterance_index": idx,
                "dropped_as_non_monotonic": True,
            })
            continue
        seen_indices.add(idx)
        last_start = snapped_start
        snapped.append({
            "title":                            _safe_truncate(c.get("title") or "Chapter", 80),
            "start_time_seconds":   snapped_start,
            "end_time_seconds":     0.0,    # filled below
            "summary":                     _safe_truncate(c.get("summary") or "", 240),
            "chapter_source":         "ai",
        })
        log.append({
            "llm_proposed_start":      proposed,
            "snapped_start":              snapped_start,
            "snap_delta_ms":             round((snapped_start - proposed) * 1000),
            "source_utterance_index": idx,
        })

    # end_time = next chapter's snapped start (or episode duration for last).
    # Snap last chapter's end to the matching utterance.end too.
    for i, c in enumerate(snapped):
        if i + 1 < len(snapped):
            c["end_time_seconds"] = snapped[i + 1]["start_time_seconds"]
        else:
            # Snap end to nearest utterance.end ≥ start_time_seconds.
            candidates = [t for t in starts_sec if t[2] >= c["start_time_seconds"]]
            if candidates:
                _, _, e_s = min(candidates,
                                            key=lambda t: abs(t[2] - float(duration_seconds or 0)))
                c["end_time_seconds"] = e_s
            else:
                c["end_time_seconds"] = max(c["start_time_seconds"] + 1.0,
                                                                float(duration_seconds or 0))
    return snapped, log


def _normalize(payload: dict, *, duration_seconds: float,
                            target_chapters: int,
                            utterances: Optional[list] = None) -> dict:
    out = _empty_metadata()
    out["title"]                         = _safe_truncate(payload.get("title") or "", 80)
    alts = payload.get("title_alternatives") or []
    out["title_alternatives"] = [_safe_truncate(str(a), 80) for a in alts[:3]]
    out["description"]            = _safe_truncate(payload.get("description") or "", 300)
    out["show_notes"]            = _safe_truncate(payload.get("show_notes") or "", 4000)
    out["seo_keywords"]        = [str(k)[:40] for k in (payload.get("seo_keywords") or [])][:12]
    sc = payload.get("social_captions") or {}
    out["social_captions"]    = {
        "twitter":      _safe_truncate(sc.get("twitter") or "", 240),
        "instagram": _safe_truncate(sc.get("instagram") or "", 2000),
        "linkedin":    _safe_truncate(sc.get("linkedin") or "", 2000),
        "youtube":     _safe_truncate(sc.get("youtube") or "", 4000),
    }
    out["hashtags"]                = [str(h)[:30] for h in (payload.get("hashtags") or [])][:8]
    out["summary_short"]      = _safe_truncate(payload.get("summary_short") or "", 150)
    out["summary_long"]        = _safe_truncate(payload.get("summary_long") or "", 1000)
    # Chapters — snap to utterance boundaries (zero-tolerance alignment).
    raw_ch = payload.get("chapters") or []
    snapped, alignment_log = _snap_chapters_to_utterances(
        raw_ch, utterances or [],
        duration_seconds=duration_seconds,
        target_chapters=target_chapters)
    out["chapters"] = snapped
    out["chapter_alignment_log"] = alignment_log    # for `podcast_ai_tasks` audit
    # Sponsor reads
    srs = payload.get("sponsor_read_suggestions") or []
    out["sponsor_read_suggestions"] = [
        {"slot":              (s.get("slot") or "mid_roll"),
          "script_text":   _safe_truncate(s.get("script_text") or "", 600),
          "length_seconds": int(s.get("length_seconds") or 30)}
        for s in srs[:3]
    ]
    return out


async def generate_metadata(db, *, episode_id: str) -> dict:
    """Reads the latest completed transcript + episode, generates the
    full metadata payload, logs to `podcast_ai_tasks`. Does NOT
    automatically apply to the episode (creator must explicitly call
    apply-metadata)."""
    ep = await db.podcast_episodes.find_one({"id": episode_id}, {"_id": 0})
    if not ep:
        raise ValueError(f"episode_not_found:{episode_id}")
    ch = await db.podcast_channels.find_one(
        {"id": ep["channel_id"]}, {"_id": 0})
    tr = await db.podcast_transcripts.find_one(
        {"episode_id": episode_id, "status": "completed"},
        {"_id": 0}, sort=[("created_at", -1)])
    if not tr:
        # No transcript yet — log an empty task and bail.
        await db.podcast_ai_tasks.insert_one({
            "id": _gen("pat"), "episode_id": episode_id,
            "channel_id": ep["channel_id"], "task_type": "metadata",
            "input_json": {}, "output_json": _empty_metadata(),
            "status": "skipped_no_transcript",
            "error_message": "no completed transcript",
            "total_latency_ms": 0,
            "created_at": _now(), "completed_at": _now()})
        return _empty_metadata()

    duration = float(ep.get("duration_seconds") or 0)
    target = _target_chapter_count(duration)
    utterances = tr.get("utterances_json") or []
    script_pref = (ch or {}).get("script_preference") or "auto"
    sys, usr = _build_prompt(
        transcript_text=tr.get("text") or "",
        utterances=utterances,
        channel_title=(ch or {}).get("title") or "RadioLife",
        channel_category=(ch or {}).get("category") or "other",
        channel_language=(ch or {}).get("language") or "en",
        episode_title=ep.get("title") or "",
        duration_seconds=duration,
        target_chapters=target,
        script_preference=script_pref)

    task_id = _gen("pat")
    t0 = time.time()
    status = "error"
    payload: dict = {}
    err: Optional[str] = None
    try:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY missing — cannot generate")
        resp = _client().chat.completions.create(
            model=_MODEL,
            response_format={"type": "json_object"},
            temperature=0.75,
            messages=[{"role": "system", "content": sys},
                          {"role": "user",     "content": usr}],
            timeout=60)
        raw = resp.choices[0].message.content or "{}"
        payload = json.loads(raw)
        status = "completed"
    except Exception as e:
        logger.exception("[podcast_ai_metadata] failed: %s", e)
        err = str(e)[:300]

    out = _normalize(payload, duration_seconds=duration,
                                  target_chapters=target,
                                  utterances=utterances)
    latency_ms = int((time.time() - t0) * 1000)
    await db.podcast_ai_tasks.insert_one({
        "id":                            task_id,
        "episode_id":             episode_id,
        "channel_id":             ep["channel_id"],
        "task_type":                "metadata",
        "input_json":               {"target_chapters":      target,
                                                    "duration_seconds":  duration,
                                                    "language":                  (ch or {}).get("language"),
                                                    "script_preference": script_pref,
                                                    "n_utterances":          len(utterances)},
        "output_json":            out,
        "status":                       status,
        "error_message":         err,
        "total_latency_ms":   latency_ms,
        "created_at":               _now(),
        "completed_at":           _now(),
    })
    return out


async def list_history(db, *, episode_id: str, limit: int = 20) -> list:
    rows = await db.podcast_ai_tasks.find(
        {"episode_id": episode_id, "task_type": "metadata"},
        {"_id": 0}).sort("created_at", -1).limit(int(limit)).to_list(int(limit))
    return rows


async def apply_metadata(db, *, episode_id: str, body: dict) -> dict:
    """PATCH-style apply. Body fields are optional — only the ones the
    creator approved get persisted. Returns the updated episode doc and
    invalidates the RSS cache so the feed reflects the new metadata."""
    ep = await db.podcast_episodes.find_one({"id": episode_id})
    if not ep:
        raise ValueError(f"episode_not_found:{episode_id}")
    upd: dict = {"updated_at": _now()}
    rss_dirty = False
    for k in ("title", "description", "show_notes"):
        v = body.get(k)
        if isinstance(v, str) and v.strip():
            upd[k] = v.strip()
            rss_dirty = True
    if "chapters" in body and isinstance(body["chapters"], list):
        # Normalize/stamp source.
        ch_in = body["chapters"]
        norm = []
        for c in ch_in[:7]:
            norm.append({
                "title":                            _safe_truncate(c.get("title") or "Chapter", 80),
                "start_time_seconds":   float(c.get("start_time_seconds") or 0),
                "end_time_seconds":     float(c.get("end_time_seconds") or 0),
                "summary":                     _safe_truncate(c.get("summary") or "", 240),
                "chapter_source":         c.get("chapter_source") or "ai",
            })
        upd["chapters"] = norm
        rss_dirty = True
    if "social_captions" in body and isinstance(body["social_captions"], dict):
        upd["social_captions"] = body["social_captions"]
    if "seo_keywords" in body and isinstance(body["seo_keywords"], list):
        upd["seo_keywords"] = [str(k)[:40] for k in body["seo_keywords"]][:12]
    if "hashtags" in body and isinstance(body["hashtags"], list):
        upd["hashtags"] = [str(h)[:30] for h in body["hashtags"]][:8]
    if "sponsor_read_suggestions" in body and isinstance(body["sponsor_read_suggestions"], list):
        upd["sponsor_read_suggestions"] = body["sponsor_read_suggestions"][:3]
    if "summary_short" in body:
        upd["summary_short"] = _safe_truncate(body["summary_short"] or "", 150)
    if "summary_long" in body:
        upd["summary_long"] = _safe_truncate(body["summary_long"] or "", 1000)
    r = await db.podcast_episodes.find_one_and_update(
        {"id": episode_id}, {"$set": upd},
        return_document=True)
    if rss_dirty and r:
        from services.podcasts import invalidate_feed_cache
        await invalidate_feed_cache(db, channel_id=r["channel_id"])
    if r: r.pop("_id", None)
    return r
