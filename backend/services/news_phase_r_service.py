"""Phase R — News Radio Expansion.

Admin-curated news layer that lives ALONGSIDE the pre-existing
`news_articles` cache (RSS/newsdata-pulled).  Introduces four new
collections:

  news_channels    — curator-owned station-like entities.
  news_headlines   — hand-entered / bulk-pasted headlines,
                                    optionally LLM-summarised.
  news_bulletins   — LLM-scripted + ElevenLabs-voiced top-of-hour
                                    bulletins tied to a channel.
  news_alerts      — region-broadcast breaking-news events.

Reuses:
  services.elevenlabs_tts.synthesize                    — TTS.
  services.object_storage.get_storage()                — audio hosting.
  services.notification_trigger_dispatcher.dispatch_event
                                                                            — recipe fan-out.
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("bigfm.phase_r_news")

# ─── constants ────────────────────────────────────────────────
HEADLINE_MAX          = 200
SUMMARY_MAX           = 500
DEFAULT_TTL_DAYS      = 14        # headlines expire after 14 d if not set.
BREAKING_LOOKBACK_HRS = 6
NEWS_ANCHOR_VOICE_ID = os.environ.get(
    "NEWS_ANCHOR_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")   # Rachel default.

VALID_CATEGORIES = {
    "breaking", "politics", "business", "sports", "local", "weather",
    "traffic", "features", "world", "tech", "entertainment",
}
VALID_SEGMENT_TYPES = {
    "top_headlines", "breaking", "weather", "traffic",
    "business", "sports", "features",
}

# ─── helpers ──────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _clean(text: Optional[str], limit: int) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text[:limit]


def _normalise_category(c: Optional[str]) -> str:
    c = (c or "").strip().lower()
    if c in VALID_CATEGORIES:
        return c
    if c in ("news", ""):
        return "features"
    return "features"


async def ensure_indexes(db) -> None:
    try:
        await db.news_headlines.create_index(
            [("region_code", 1), ("published_at", -1)])
        await db.news_headlines.create_index("status")
        await db.news_headlines.create_index("category")
        await db.news_headlines.create_index(
            "expires_at", expireAfterSeconds=0)
        await db.news_channels.create_index("region_code")
        await db.news_channels.create_index("status")
        await db.news_bulletins.create_index(
            [("channel_id", 1), ("generated_at", -1)])
        await db.news_bulletins.create_index("status")
        await db.news_alerts.create_index("region_code")
        await db.news_alerts.create_index("sent_at")
    except Exception as e:
        log.warning("phase_r index setup failed: %s", e)


# ─── LLM helpers (best-effort, fall back to text-only mode) ──
def _openai_client():
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def _summarize_headline(headline: str,
                        source_name: Optional[str] = None) -> Optional[str]:
    """Take a headline and return a 1-2 sentence summary (<=500 chars).
    Returns None if LLM unavailable."""
    client = _openai_client()
    if not client:
        return None
    try:
        prompt = (
            "You write concise news summaries for a radio-app feed.\n"
            "Given the headline below, write ONE sentence (max 40 words) "
            "that a listener would hear read aloud.\n"
            "- Neutral tone. No opinion. No fabricated details.\n"
            "- Do not repeat the headline verbatim; add ONE substantive "
            "detail plausible from the headline (or state 'more details "
            "at source').\n"
            "- Never lead with 'Breaking' or the outlet name."
        )
        user = f"Headline: {headline}\n" + (
            f"Source: {source_name}\n" if source_name else "")
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt},
                      {"role": "user",   "content": user}],
            temperature=0.4,
            max_tokens=140,
        )
        txt = (rsp.choices[0].message.content or "").strip()
        return _clean(txt, SUMMARY_MAX) or None
    except Exception as e:
        log.warning("summarize failed: %s", e)
        return None


def _generate_bulletin_script(headlines: List[Dict[str, Any]],
                              channel: Dict[str, Any]) -> str:
    """Compose a 30-45 s news bulletin script from up to 5 headlines.
    Returns the script text (never empty — falls back to a plain read-out)."""
    client = _openai_client()
    channel_name = channel.get("name") or "FUUSIC News"
    city         = channel.get("city") or ""
    tagline      = channel.get("tagline") or ""

    # Build a plain concat fallback first.
    lines: List[str] = []
    intro = f"You're listening to {channel_name}"
    if city:
        intro += f" from {city}"
    if tagline:
        intro += f" — {tagline}"
    intro += ". Here are the top stories right now."
    lines.append(intro)
    for h in headlines[:5]:
        line = h.get("headline_text") or ""
        summary = h.get("summary_text") or ""
        if summary:
            lines.append(f"{line}. {summary}")
        else:
            lines.append(line)
    lines.append("That's your update. Stay with us.")
    fallback = " ".join([s.strip() for s in lines if s.strip()])

    if not client:
        return fallback

    try:
        sys_prompt = (
            "You are the on-air news anchor for a global radio network. "
            "Voice: measured, journalistic, NPR/AP cadence, NOT a music DJ.\n"
            "Rules:\n"
            "  • Length 30-45 seconds when read aloud — roughly 80-120 "
            "words total across the whole segment.\n"
            "  • Structure: one-sentence anchor intro that names the "
            "channel and (if provided) city, then read each headline in "
            "1-2 sentences, then a one-sentence outro.\n"
            "  • DO NOT fabricate details or invent quotes.\n"
            "  • DO NOT use the phrase 'breaking news' unless the input "
            "explicitly is labelled breaking.\n"
            "  • DO NOT include ElevenLabs stage directions like [pause]."
        )
        headline_list = "\n".join(
            f"- {h.get('headline_text','')} — {h.get('summary_text','') or '(no summary)'}"
            f"{' [BREAKING]' if h.get('is_breaking') else ''}"
            for h in headlines[:5])
        user = (
            f"Channel: {channel_name}\n"
            f"City: {city or 'unspecified'}\n"
            f"Tagline: {tagline or 'unspecified'}\n\n"
            f"Headlines:\n{headline_list}"
        )
        rsp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": sys_prompt},
                      {"role": "user",   "content": user}],
            temperature=0.4,
            max_tokens=400,
        )
        txt = (rsp.choices[0].message.content or "").strip()
        return txt or fallback
    except Exception as e:
        log.warning("bulletin script LLM failed: %s", e)
        return fallback


# ─── TTS + upload ────────────────────────────────────────────
def _render_and_upload_bulletin_audio(
        script: str, bulletin_id: str) -> Dict[str, Any]:
    """Render the script via ElevenLabs, upload to object_storage,
    return `{audio_url, duration_sec, size_bytes, source}` or `{}` when
    TTS is unavailable / quota-blocked."""
    try:
        from services.elevenlabs_tts import synthesize
    except Exception:
        return {}

    # Write to a scratch file so we can measure size + upload atomically.
    # Live on the same filesystem as `services.rj` output so the
    # ElevenLabs helper's os.rename → out_path succeeds (avoids EXDEV
    # "Invalid cross-device link" when TMPDIR lives on a different mount).
    scratch_dir = Path("/app/backend/storage/news_bulletins")
    scratch_dir.mkdir(parents=True, exist_ok=True)
    out_path = scratch_dir / f"{bulletin_id}.mp3"

    result = synthesize(script, NEWS_ANCHOR_VOICE_ID,
                        energy="medium", out_path=out_path)
    if not result.get("ok"):
        log.warning("[news] tts failed: %s", result.get("error"))
        return {"tts_error": result.get("error") or "tts_unavailable"}

    # Upload to object storage.
    try:
        from services.object_storage import get_storage
        storage = get_storage()
        key = f"news_bulletins/{bulletin_id}.mp3"
        storage.upload(local_path=str(out_path), key=key,
                       content_type="audio/mpeg")
        url = storage.get_signed_url(key=key, expires_in=7 * 24 * 3600)
    except Exception as e:
        log.warning("[news] storage upload failed: %s", e)
        return {"tts_error": f"storage_upload_failed: {e}"}

    size_bytes = out_path.stat().st_size if out_path.exists() else 0
    # Approx 130 chars/sec at 128 kbps → 1 s ≈ 16000 bytes.  Best-effort.
    approx_dur = max(1, int(size_bytes / 16000))
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    return {"audio_url":       url,
            "audio_key":       key,
            "duration_sec":    approx_dur,
            "size_bytes":      size_bytes,
            "source":          "elevenlabs"}


# ─── Headline CRUD ──────────────────────────────────────────
async def create_headline(db, *, headline_text: str,
                          summary_text: Optional[str] = None,
                          category: str = "features",
                          region_code: Optional[str] = None,
                          channel_id: Optional[str] = None,
                          source_name: Optional[str] = None,
                          source_url: Optional[str] = None,
                          image_url: Optional[str] = None,
                          priority: int = 5,
                          published_at: Optional[datetime] = None,
                          ttl_days: int = DEFAULT_TTL_DAYS,
                          created_by_user_id: str,
                          auto_summarize: bool = True,
                          ) -> Dict[str, Any]:
    hid = _new_id("hl")
    text = _clean(headline_text, HEADLINE_MAX)
    if not text:
        raise ValueError("empty_headline")
    summ = _clean(summary_text or "", SUMMARY_MAX) or None
    curated_by_llm = False
    if not summ and auto_summarize:
        summ = _summarize_headline(text, source_name)
        curated_by_llm = bool(summ)
    now = _now()
    pub = published_at or now
    doc = {
        "id":                     hid,
        "headline_id":            hid,
        "channel_id":             channel_id,
        "region_code":            region_code,
        "category":               _normalise_category(category),
        "headline_text":          text,
        "summary_text":           summ,
        "source_name":            source_name,
        "source_url":             source_url,
        "image_url":              image_url,
        "published_at":           pub,
        "expires_at":             pub + timedelta(days=ttl_days),
        "priority":               max(1, min(10, int(priority or 5))),
        "status":                 "live",
        "is_breaking":            False,
        "curated_by_llm":         curated_by_llm,
        "created_by_user_id":     created_by_user_id,
        "created_at":             now,
        "updated_at":             now,
    }
    await db.news_headlines.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def bulk_create_headlines(db, *, rows: List[Dict[str, Any]],
                                 auto_summarize: bool = True,
                                 created_by_user_id: str,
                                 ) -> Dict[str, Any]:
    created: List[str] = []
    errors:  List[Dict[str, Any]] = []
    for i, row in enumerate(rows or []):
        try:
            doc = await create_headline(
                db,
                headline_text=(row or {}).get("headline_text") or "",
                summary_text= (row or {}).get("summary_text"),
                category=     (row or {}).get("category") or "features",
                region_code=  (row or {}).get("region_code"),
                channel_id=   (row or {}).get("channel_id"),
                source_name=  (row or {}).get("source_name"),
                source_url=   (row or {}).get("source_url"),
                image_url=    (row or {}).get("image_url"),
                priority=  int((row or {}).get("priority") or 5),
                created_by_user_id=created_by_user_id,
                auto_summarize=auto_summarize,
            )
            created.append(doc["id"])
        except Exception as e:
            errors.append({"row": i, "detail": str(e)})
    return {"created": created, "created_count": len(created),
            "errors":  errors,  "error_count":   len(errors)}


async def list_headlines(db, *, region_code: Optional[str] = None,
                         category: Optional[str] = None,
                         status: Optional[str] = None,
                         limit: int = 100,
                         ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if region_code:
        q["region_code"] = region_code
    if category:
        q["category"] = category
    if status:
        q["status"] = status
    return [
        {**d, "_id": None} async for d in
        db.news_headlines.find(q, {"_id": 0}).sort(
            "published_at", -1).limit(limit)
    ]


async def update_headline(db, headline_id: str,
                          patch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"headline_text", "summary_text", "category", "region_code",
               "channel_id", "source_name", "source_url", "image_url",
               "priority", "status", "is_breaking", "expires_at",
               "published_at"}
    upd = {k: v for k, v in patch.items() if k in allowed and v is not None}
    if not upd:
        raise ValueError("no_fields_to_update")
    if "headline_text" in upd:
        upd["headline_text"] = _clean(upd["headline_text"], HEADLINE_MAX)
    if "summary_text" in upd:
        upd["summary_text"] = _clean(upd["summary_text"], SUMMARY_MAX) or None
    if "category" in upd:
        upd["category"] = _normalise_category(upd["category"])
    if "priority" in upd:
        upd["priority"] = max(1, min(10, int(upd["priority"] or 5)))
    upd["updated_at"] = _now()
    r = await db.news_headlines.find_one_and_update(
        {"id": headline_id}, {"$set": upd},
        return_document=True, projection={"_id": 0})
    if not r:
        raise ValueError("headline_not_found")
    return r


async def promote_breaking(db, headline_id: str) -> Dict[str, Any]:
    """Flag as breaking, boost priority to 10, then fire a
    `news_alert_breaking` event to region-matching users."""
    now = _now()
    r = await db.news_headlines.find_one_and_update(
        {"id": headline_id},
        {"$set": {"is_breaking": True, "priority": 10,
                  "category": "breaking", "status": "live",
                  "updated_at": now}},
        return_document=True, projection={"_id": 0})
    if not r:
        raise ValueError("headline_not_found")

    # Record the alert row.
    alert_id = _new_id("na")
    await db.news_alerts.insert_one({
        "id":                    alert_id,
        "alert_id":              alert_id,
        "headline_id":           headline_id,
        "region_code":           r.get("region_code"),
        "sent_at":               now,
        "delivery_channels":     ["notification", "overlay"],
        "dismissed_by_user_ids": [],
    })

    # Broadcast to region-matching users via trigger_dispatcher.
    minted = 0
    try:
        from services.notification_trigger_dispatcher import dispatch_event
        cursor = db.users.find(
            {"$or": [{"region_code": r.get("region_code")},
                     {"city":        r.get("region_code")}]}
            if r.get("region_code") else {},
            {"user_id": 1})
        # Cap fan-out to 5000 users per broadcast to keep the request bounded.
        n = 0
        async for u in cursor:
            uid = u.get("user_id")
            if not uid:
                continue
            try:
                res = await dispatch_event(
                    db, event_name="news_alert_breaking",
                    user_id=uid,
                    payload={"headline_id":  headline_id,
                             "region_code":  r.get("region_code"),
                             "headline":     r.get("headline_text"),
                             "alert_id":     alert_id})
                minted += (res or {}).get("minted", 0)
            except Exception:
                continue
            n += 1
            if n >= 5000:
                break
    except Exception as e:
        log.warning("[news] alert fan-out failed: %s", e)

    return {"ok": True, "headline_id": headline_id, "alert_id": alert_id,
            "deliveries_minted": minted}


async def soft_delete_headline(db, headline_id: str) -> Dict[str, Any]:
    r = await db.news_headlines.find_one_and_update(
        {"id": headline_id},
        {"$set": {"status": "archived", "updated_at": _now()}},
        return_document=True, projection={"_id": 0})
    if not r:
        raise ValueError("headline_not_found")
    return {"ok": True, "headline_id": headline_id, "status": "archived"}


# ─── Channels ───────────────────────────────────────────────
async def create_channel(db, *, name: str,
                         region_code: Optional[str] = None,
                         city: Optional[str] = None,
                         language: str = "en",
                         tagline: Optional[str] = None,
                         cover_image_url: Optional[str] = None,
                         station_id: Optional[str] = None,
                         program_schedule: Optional[List[Dict[str, Any]]] = None,
                         created_by_user_id: str) -> Dict[str, Any]:
    cid = _new_id("nch")
    schedule = _clean_schedule(program_schedule or [])
    now = _now()
    doc = {
        "id":                  cid,
        "channel_id":          cid,
        "station_id":          station_id,
        "name":                _clean(name, 120),
        "region_code":         region_code,
        "city":                city,
        "language":            (language or "en").lower(),
        "tagline":             _clean(tagline or "", 200),
        "cover_image_url":     cover_image_url,
        "live":                True,
        "status":              "active",
        "program_schedule":    schedule,
        "created_by_user_id":  created_by_user_id,
        "created_at":          now,
        "updated_at":          now,
    }
    await db.news_channels.insert_one(doc)
    doc.pop("_id", None)
    return doc


def _clean_schedule(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows or []:
        try:
            h = int(r.get("hour_of_day"))
            if not 0 <= h <= 23:
                continue
            st = str(r.get("segment_type") or "top_headlines").lower()
            if st not in VALID_SEGMENT_TYPES:
                st = "top_headlines"
            dm = int(r.get("duration_minutes") or 5)
            out.append({"hour_of_day": h, "segment_type": st,
                        "duration_minutes": max(1, min(60, dm))})
        except Exception:
            continue
    return out


async def update_channel(db, channel_id: str,
                         patch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"name", "region_code", "city", "language", "tagline",
               "cover_image_url", "live", "status", "program_schedule",
               "station_id"}
    upd = {k: v for k, v in patch.items() if k in allowed and v is not None}
    if "program_schedule" in upd:
        upd["program_schedule"] = _clean_schedule(upd["program_schedule"])
    if not upd:
        raise ValueError("no_fields_to_update")
    upd["updated_at"] = _now()
    r = await db.news_channels.find_one_and_update(
        {"id": channel_id}, {"$set": upd},
        return_document=True, projection={"_id": 0})
    if not r:
        raise ValueError("channel_not_found")
    return r


async def list_channels_public(db, *, region_code: Optional[str] = None,
                                language: Optional[str] = None,
                                limit: int = 50,
                                ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": "active", "live": True}
    if region_code:
        q["region_code"] = region_code
    if language:
        q["language"] = language.lower()
    return [d async for d in db.news_channels.find(q, {"_id": 0}).limit(limit)]


async def get_channel_public(db, channel_id: str) -> Dict[str, Any]:
    ch = await db.news_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch:
        raise ValueError("channel_not_found")
    # Attach latest headlines (region-matched) + next scheduled bulletin.
    latest = await list_headlines(db, region_code=ch.get("region_code"),
                                   status="live", limit=20)
    upcoming = _upcoming_schedule(ch.get("program_schedule") or [])
    next_b = await db.news_bulletins.find_one(
        {"channel_id": channel_id, "status": "live"},
        sort=[("generated_at", -1)], projection={"_id": 0})
    return {"channel": ch, "latest_headlines": latest[:10],
            "upcoming_schedule": upcoming, "next_bulletin": next_b}


def _upcoming_schedule(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the next 6 program-slot instances starting from now, using
    the current UTC hour as the anchor."""
    now = _now()
    slots_by_hour: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        slots_by_hour.setdefault(r["hour_of_day"], []).append(r)
    out: List[Dict[str, Any]] = []
    for offset in range(0, 12):
        h = (now.hour + offset) % 24
        if h not in slots_by_hour:
            continue
        for slot in slots_by_hour[h]:
            base = now.replace(minute=0, second=0, microsecond=0)
            start = base + timedelta(hours=offset)
            out.append({
                "start_at_utc": start.isoformat(),
                "hour_of_day":  h,
                "segment_type": slot["segment_type"],
                "duration_minutes": slot["duration_minutes"],
            })
            if len(out) >= 6:
                return out
    return out


# ─── Bulletins ─────────────────────────────────────────────
async def generate_bulletin(db, *, channel_id: str,
                            top_n: int = 5,
                            generated_by_user_id: str,
                            ) -> Dict[str, Any]:
    ch = await db.news_channels.find_one({"id": channel_id}, {"_id": 0})
    if not ch:
        raise ValueError("channel_not_found")
    now = _now()

    # Pull top N unexpired, region-matched, live headlines sorted by
    # priority desc + published_at desc.
    q: Dict[str, Any] = {"status": "live", "expires_at": {"$gt": now}}
    if ch.get("region_code"):
        q["region_code"] = {"$in": [ch["region_code"], None]}
    headlines: List[Dict[str, Any]] = []
    async for h in db.news_headlines.find(q, {"_id": 0}).sort(
            [("priority", -1), ("published_at", -1)]).limit(top_n):
        headlines.append(h)

    if not headlines:
        raise ValueError("no_headlines_available")

    # 1. script.
    script = _generate_bulletin_script(headlines, ch)
    # 2. TTS + upload.
    bulletin_id = _new_id("bul")
    tts = _render_and_upload_bulletin_audio(script, bulletin_id)

    doc = {
        "id":                    bulletin_id,
        "bulletin_id":           bulletin_id,
        "channel_id":            channel_id,
        "bulletin_type":         "top_of_hour",
        "headline_ids":          [h["id"] for h in headlines],
        "script_text":           script,
        "audio_url":             tts.get("audio_url"),
        "audio_key":             tts.get("audio_key"),
        "duration_seconds":      tts.get("duration_sec") or 0,
        "size_bytes":            tts.get("size_bytes") or 0,
        "tts_source":            tts.get("source") or "text_only",
        "tts_error":             tts.get("tts_error"),
        "generated_at":          now,
        "generated_by_user_id":  generated_by_user_id,
        "aired_count":           0,
        "status":                "draft",
    }
    await db.news_bulletins.insert_one(doc)

    # Fire self-notification to the admin who generated it.
    try:
        from services.notification_trigger_dispatcher import dispatch_event
        await dispatch_event(
            db, event_name="news_bulletin_ready",
            user_id=generated_by_user_id,
            payload={"bulletin_id": bulletin_id,
                     "channel_id":  channel_id,
                     "duration":    doc["duration_seconds"]})
    except Exception:
        pass

    doc.pop("_id", None)
    return doc


async def publish_bulletin(db, bulletin_id: str) -> Dict[str, Any]:
    r = await db.news_bulletins.find_one_and_update(
        {"id": bulletin_id, "status": {"$ne": "live"}},
        {"$set": {"status": "live", "published_at": _now()}},
        return_document=True, projection={"_id": 0})
    if not r:
        raise ValueError("bulletin_not_found_or_already_live")
    return r


async def list_bulletins_admin(db, *, channel_id: Optional[str] = None,
                                status: Optional[str] = None,
                                limit: int = 50,
                                ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if channel_id:
        q["channel_id"] = channel_id
    if status:
        q["status"] = status
    return [d async for d in db.news_bulletins.find(
        q, {"_id": 0}).sort("generated_at", -1).limit(limit)]


async def get_next_bulletin(db, channel_id: str) -> Optional[Dict[str, Any]]:
    return await db.news_bulletins.find_one(
        {"channel_id": channel_id, "status": "live"},
        sort=[("generated_at", -1)], projection={"_id": 0})


# ─── Public listener queries ───────────────────────────
async def get_breaking_headlines(db, *, region_code: Optional[str] = None,
                                  limit: int = 5,
                                  ) -> List[Dict[str, Any]]:
    cutoff = _now() - timedelta(hours=BREAKING_LOOKBACK_HRS)
    q: Dict[str, Any] = {
        "status":       "live",
        "priority":     {"$gte": 8},
        "published_at": {"$gte": cutoff},
    }
    if region_code:
        q["$or"] = [{"region_code": region_code}, {"region_code": None}]
    return [d async for d in db.news_headlines.find(
        q, {"_id": 0}).sort("published_at", -1).limit(limit)]


async def list_public_headlines(db, *, region_code: Optional[str] = None,
                                category: Optional[str] = None,
                                limit: int = 50,
                                ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"status": "live"}
    if region_code:
        q["$or"] = [{"region_code": region_code}, {"region_code": None}]
    if category:
        q["category"] = category
    return [d async for d in db.news_headlines.find(
        q, {"_id": 0}).sort("published_at", -1).limit(limit)]


__all__ = [
    "ensure_indexes",
    # Headlines
    "create_headline", "bulk_create_headlines", "list_headlines",
    "update_headline", "promote_breaking", "soft_delete_headline",
    "list_public_headlines", "get_breaking_headlines",
    # Channels
    "create_channel", "update_channel", "list_channels_public",
    "get_channel_public",
    # Bulletins
    "generate_bulletin", "publish_bulletin", "list_bulletins_admin",
    "get_next_bulletin",
]
