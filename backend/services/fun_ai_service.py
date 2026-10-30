"""FUUSIC Fun AI — Phase 1 Interactive News service helpers.

Reuses the EXISTING news system (``db.news_articles`` + ``newsdata_client``)
— it does not replace it. Adds the conversational-anchor framing,
source-grounded news retrieval (the Grok ``search_news`` tool), feature
flags, per-user voice usage quotas and an approved sponsor-acknowledgement
config. No music / on-demand selection is involved: this is radio-first.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Optional

log = logging.getLogger("fuusic.fun_ai")

_SPONSOR_SETTINGS_ID = "fun_ai_news"


def _b(name: str, default: str = "false") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── feature flags ─────────────────────────────────────────────────────
def flags() -> dict:
    from services.grok_realtime import (is_configured, voice_model,
                                         voice_provider, ws_url)
    return {
        "enabled": _b("FUN_AI_ENABLED", "true"),
        "news_enabled": _b("FUN_AI_NEWS_ENABLED", "true"),
        "companion_enabled": _b("FUN_AI_COMPANION_ENABLED", "false"),
        "sponsorship_enabled": _b("FUN_AI_SPONSORSHIP_ENABLED", "true"),
        "voice_provider": voice_provider(),
        "voice_model": voice_model(),
        "ws_url": ws_url(),
        "configured": is_configured(),
        "session_seconds": _i("FUN_AI_SESSION_SECONDS", 300),
    }


# ─── usage / quota ─────────────────────────────────────────────────────
def allowance_minutes(user: dict) -> int:
    premium = bool(user.get("is_premium"))
    return (_i("FUN_AI_MAX_VOICE_MINUTES_PER_DAY_PREMIUM", 60) if premium
            else _i("FUN_AI_MAX_VOICE_MINUTES_PER_DAY_FREE", 10))


def max_sessions_per_day() -> int:
    return _i("FUN_AI_MAX_SESSIONS_PER_DAY", 20)


def _today_key() -> str:
    return date.today().isoformat()


async def usage_today(db, user_id: str) -> dict:
    doc = await db.fun_ai_usage.find_one({"user_id": user_id, "day": _today_key()}) or {}
    return {"voice_seconds": int(doc.get("voice_seconds", 0)),
            "sessions": int(doc.get("sessions", 0))}


async def record_session_start(db, user_id: str) -> None:
    await db.fun_ai_usage.update_one(
        {"user_id": user_id, "day": _today_key()},
        {"$inc": {"sessions": 1},
         "$setOnInsert": {"created_at": _now_iso()},
         "$set": {"updated_at": _now_iso()}},
        upsert=True)


async def record_voice_seconds(db, user_id: str, seconds: int) -> None:
    seconds = max(0, min(int(seconds), 3600))
    if not seconds:
        return
    await db.fun_ai_usage.update_one(
        {"user_id": user_id, "day": _today_key()},
        {"$inc": {"voice_seconds": seconds}, "$set": {"updated_at": _now_iso()}},
        upsert=True)


# ─── sponsor config (approved copy only) ───────────────────────────────
DEFAULT_SPONSOR = {"enabled": False, "sponsor_name": "",
                   "opening_line": "", "closing_line": "",
                   "opening_enabled": True, "closing_enabled": True,
                   "mid_enabled": False, "mid_line": "", "mid_after_segment": 3,
                   "premium_ad_free": True}


async def get_sponsor(db) -> dict:
    doc = await db.app_settings.find_one({"_id": _SPONSOR_SETTINGS_ID}) or {}
    return {**DEFAULT_SPONSOR, **(doc.get("sponsor") or {})}


async def set_sponsor(db, sponsor: dict) -> dict:
    clean = {
        "enabled": bool(sponsor.get("enabled")),
        "sponsor_name": (sponsor.get("sponsor_name") or "").strip()[:80],
        "opening_line": (sponsor.get("opening_line") or "").strip()[:240],
        "closing_line": (sponsor.get("closing_line") or "").strip()[:240],
        "opening_enabled": bool(sponsor.get("opening_enabled", True)),
        "closing_enabled": bool(sponsor.get("closing_enabled", True)),
        "mid_enabled": bool(sponsor.get("mid_enabled")),
        "mid_line": (sponsor.get("mid_line") or "").strip()[:240],
        "mid_after_segment": max(1, min(int(sponsor.get("mid_after_segment") or 3), 11)),
        "premium_ad_free": bool(sponsor.get("premium_ad_free", True)),
    }
    await db.app_settings.update_one(
        {"_id": _SPONSOR_SETTINGS_ID},
        {"$set": {"sponsor": clean, "updated_at": _now_iso()}}, upsert=True)
    return clean


# News "station" id that advertisers target for Interactive-News sponsor reads.
NEWS_STATION_ID = "fuusic_news"


async def build_breaks(db, *, user: dict, sponsor: dict, program_count: int,
                       sponsorship_enabled: bool) -> list:
    """Compose the sponsor breaks for a news program: opening + (live or
    approved) mid + closing. Respects Premium ad-free. Live mid-spots are
    pulled from the existing ad inventory (rj_sponsored_reads)."""
    if not (sponsorship_enabled and sponsor.get("enabled")):
        return []
    if user and user.get("is_premium") and sponsor.get("premium_ad_free", True):
        return []
    name = sponsor.get("sponsor_name") or "our sponsor"
    breaks: list = []
    if sponsor.get("opening_enabled", True):
        line = sponsor.get("opening_line") or f"FUUSIC Interactive News is sponsored by {name}."
        breaks.append({"id": "opening", "placement": "opening", "after_index": -1,
                       "kind": "sponsorship", "label": "Sponsored",
                       "disclosure": "Program sponsorship", "text": line,
                       "audio_url": None, "sponsored_read_id": None})
    # Mid-program: try a live paid read from inventory, else approved copy.
    mid_after = min(int(sponsor.get("mid_after_segment") or 3), max(1, program_count - 1))
    live = None
    if program_count > 1:
        try:
            from services import rj_sponsored_read_service as rj
            live = await rj.select_next_sponsored(
                db, station_id=NEWS_STATION_ID,
                user_id=(user or {}).get("user_id"))
        except Exception:
            live = None
    if live:
        breaks.append({"id": live.get("sponsored_read_id") or live.get("id"),
                       "placement": "mid", "after_index": mid_after,
                       "kind": "paid", "label": "Paid advertisement",
                       "disclosure": "Now, a brief paid advertising message",
                       "text": live.get("final_script") or "",
                       "audio_url": live.get("audio_url"),
                       "sponsored_read_id": live.get("sponsored_read_id") or live.get("id")})
    elif sponsor.get("mid_enabled") and sponsor.get("mid_line") and program_count > 1:
        breaks.append({"id": "mid", "placement": "mid", "after_index": mid_after,
                       "kind": "sponsorship", "label": "Sponsored",
                       "disclosure": "A word from our sponsor", "text": sponsor["mid_line"],
                       "audio_url": None, "sponsored_read_id": None})
    if sponsor.get("closing_enabled", True):
        line = sponsor.get("closing_line") or f"That's your news, brought to you by {name}."
        breaks.append({"id": "closing", "placement": "closing", "after_index": program_count,
                       "kind": "sponsorship", "label": "Sponsored",
                       "disclosure": "Sponsor sign-off", "text": line,
                       "audio_url": None, "sponsored_read_id": None})
    return breaks


async def break_report(db, days: int = 30) -> dict:
    """Admin reporting for news sponsor breaks: raw impressions (from
    ``fun_ai_sponsor_events``) broken down by placement, plus paid-spot
    spend derived from the charged plays recorded on the news station."""
    from datetime import timedelta
    days = max(1, min(int(days or 30), 365))
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_iso = since.isoformat()

    by_placement: dict = {}
    total_impr = 0
    paid_impr = 0
    users: set = set()
    async for e in db.fun_ai_sponsor_events.find({"at": {"$gte": since_iso},
                                                  "kind": "impression"}):
        total_impr += 1
        p = e.get("placement") or "unknown"
        by_placement[p] = by_placement.get(p, 0) + 1
        if e.get("sponsored_read_id"):
            paid_impr += 1
        if e.get("user_id"):
            users.add(e["user_id"])

    # Paid spend: charged plays on the news station, priced per read.
    counts: dict = {}
    async for pl in db.rj_sponsored_read_plays.find(
            {"station_id": NEWS_STATION_ID, "played_at": {"$gte": since}}):
        rid = pl.get("sponsored_read_id")
        if rid:
            counts[rid] = counts.get(rid, 0) + 1

    paid_spots = []
    spend_cents = 0
    for rid, plays in counts.items():
        s = await db.rj_sponsored_reads.find_one({"id": rid}) or {}
        cpp = int(s.get("cost_per_play_cents") or 0)
        sp = plays * cpp
        spend_cents += sp
        adv_name = None
        try:
            adv = await db.advertisers.find_one(
                {"advertiser_id": s.get("advertiser_business_id")},
                {"business_name": 1, "display_name": 1, "name": 1})
            if adv:
                adv_name = adv.get("business_name") or adv.get("display_name") or adv.get("name")
        except Exception:
            pass
        paid_spots.append({
            "sponsored_read_id": rid,
            "persona_name": s.get("persona_name"),
            "advertiser": adv_name,
            "plays": plays,
            "cost_per_play_cents": cpp,
            "spend_cents": sp,
            "remaining_budget_cents": int(s.get("remaining_budget_cents") or 0),
            "status": s.get("status"),
        })
    paid_spots.sort(key=lambda x: x["spend_cents"], reverse=True)

    order = ["opening", "mid", "closing"]
    bp = sorted(by_placement.items(),
                key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)

    return {
        "range_days": days,
        "since": since_iso,
        "totals": {
            "impressions": total_impr,
            "unique_listeners": len(users),
            "paid_impressions": paid_impr,
            "spend_cents": spend_cents,
        },
        "by_placement": [{"placement": k, "impressions": v} for k, v in bp],
        "paid_spots": paid_spots,
    }



# ─── Companion Memory (opt-out; only explicit saves, never silent capture) ─
_MEMORY_FIELDS = ("genres", "stations", "disliked", "languages", "interests")
_MEMORY_MAX = 25


async def get_memory(db, user_id: str) -> dict:
    doc = await db.fun_ai_prefs.find_one({"user_id": user_id}) or {}
    mem = doc.get("memory") or {}
    out = {"enabled": doc.get("memory_enabled", True)}
    for k in _MEMORY_FIELDS:
        out[k] = list(mem.get(k) or [])
    return out


async def set_memory_enabled(db, user_id: str, enabled: bool) -> dict:
    await db.fun_ai_prefs.update_one(
        {"user_id": user_id},
        {"$set": {"memory_enabled": bool(enabled), "updated_at": _now_iso()},
         "$setOnInsert": {"user_id": user_id}}, upsert=True)
    return await get_memory(db, user_id)


async def add_memory_item(db, user_id: str, kind: str, value: str) -> Optional[dict]:
    kind = (kind or "").strip().lower()
    value = re.sub(r"\s+", " ", (value or "").strip())[:60]
    if kind not in _MEMORY_FIELDS or not value:
        return None
    cur = await get_memory(db, user_id)
    items = cur.get(kind) or []
    if not any(i.lower() == value.lower() for i in items) and len(items) < _MEMORY_MAX:
        await db.fun_ai_prefs.update_one(
            {"user_id": user_id},
            {"$push": {f"memory.{kind}": value}, "$set": {"updated_at": _now_iso()},
             "$setOnInsert": {"user_id": user_id}}, upsert=True)
    return await get_memory(db, user_id)


async def remove_memory_item(db, user_id: str, kind: str, value: str) -> dict:
    kind = (kind or "").strip().lower()
    if kind in _MEMORY_FIELDS:
        await db.fun_ai_prefs.update_one(
            {"user_id": user_id},
            {"$pull": {f"memory.{kind}": {"$regex": f"^{re.escape(value)}$", "$options": "i"}},
             "$set": {"updated_at": _now_iso()}})
    return await get_memory(db, user_id)


async def clear_memory(db, user_id: str) -> dict:
    await db.fun_ai_prefs.update_one(
        {"user_id": user_id},
        {"$set": {"memory": {}, "updated_at": _now_iso()}})
    return await get_memory(db, user_id)


def memory_instructions(mem: dict) -> str:
    if not mem or not mem.get("enabled"):
        return ""
    bits = []
    if mem.get("genres"):    bits.append(f"likes genres: {', '.join(mem['genres'][:8])}")
    if mem.get("disliked"):  bits.append(f"dislikes (avoid): {', '.join(mem['disliked'][:8])}")
    if mem.get("stations"):  bits.append(f"favourite stations: {', '.join(mem['stations'][:8])}")
    if mem.get("languages"): bits.append(f"preferred languages: {', '.join(mem['languages'][:6])}")
    if mem.get("interests"): bits.append(f"interests: {', '.join(mem['interests'][:8])}")
    if not bits:
        return ""
    return (" LISTENER MEMORY (honour these approved preferences; reference them "
            "naturally and never claim to know private details you were not given): "
            + "; ".join(bits) + ".")


# ─── program modes (all six from the spec) ─────────────────────────────
DEFAULT_MODE = "morning_briefing"
MODES: dict = {
    "morning_briefing": {
        "label": "Morning Briefing", "blurb": "~5–10 min of today's top stories",
        "limit": 8, "trim": None, "category": None, "local": False,
        "hint": ("Open with a brief, warm good-morning greeting, then present the "
                 "top stories as one cohesive 5–10 minute briefing, grouping related "
                 "items and ending with a short outlook.")},
    "news_in_2": {
        "label": "News in 2 Minutes", "blurb": "Fast headline rundown",
        "limit": 6, "trim": 30, "category": None, "local": False,
        "hint": ("Deliver a rapid ~2 minute headline rundown — one or two crisp "
                 "sentences per story, no tangents — then offer to expand any item.")},
    "continuous": {
        "label": "Continuous News", "blurb": "Rolling, non-stop news",
        "limit": 12, "trim": None, "category": None, "local": False,
        "hint": ("Run a continuous, rolling news program, moving smoothly from one "
                 "story to the next with short transitions, like a 24-hour news channel.")},
    "deep_dive": {
        "label": "Deep Dive", "blurb": "One topic, in depth",
        "limit": 5, "trim": None, "category": None, "local": False, "topic_required": True,
        "hint": ("Focus on ONE topic in depth: background, what's new, why it matters "
                 "and differing perspectives — always source-grounded — and keep "
                 "inviting the listener's questions on that topic.")},
    "local": {
        "label": "Local News", "blurb": "News for your market",
        "limit": 8, "trim": None, "category": None, "local": True,
        "hint": ("Present news relevant to the listener's local market; keep the tone "
                 "practical and local.")},
    "global": {
        "label": "Global News", "blurb": "World & international",
        "limit": 8, "trim": None, "category": "world", "local": False,
        "hint": ("Present world, national and international stories, giving brief "
                 "geographic context for each.")},
}


def list_modes() -> list:
    return [{"id": k, "label": v["label"], "blurb": v["blurb"],
             "topic_required": bool(v.get("topic_required"))}
            for k, v in MODES.items()]


def mode_instructions(mode: str, topic: Optional[str] = None) -> str:
    cfg = MODES.get(mode) or MODES[DEFAULT_MODE]
    s = f" PROGRAM MODE — {cfg['label']}: {cfg['hint']}"
    if mode == "deep_dive" and topic:
        s += (f" The chosen deep-dive topic is: {topic}. Stay on this topic and keep "
              "exploring it with the listener.")
    return s


# ─── RJ personalities (shared by the news anchor + the player RJ) ───────
DEFAULT_PERSONALITY = "friendly"
PERSONALITIES: dict = {
    "friendly": {"label": "Friendly", "blurb": "Warm, casual, approachable",
                 "style": ("warm, casual and approachable, like a welcoming local "
                           "host who's glad you're here")},
    "energetic": {"label": "Energetic", "blurb": "Upbeat and lively",
                  "style": ("upbeat, entertaining and lively, with bright pacing and "
                            "genuine enthusiasm")},
    "calm": {"label": "Calm", "blurb": "Soft-spoken and soothing",
             "style": ("soft-spoken, soothing and relaxed, with gentle, unhurried pacing")},
    "funny": {"label": "Funny", "blurb": "Witty and playful",
              "style": ("witty, playful and lightly humorous — a quick joke is welcome, "
                        "but never at the expense of the facts")},
    "thoughtful": {"label": "Thoughtful", "blurb": "Curious and reflective",
                   "style": ("curious, reflective and informative, adding a little extra "
                             "context and perspective")},
}


def list_personalities() -> list:
    return [{"id": k, "label": v["label"], "blurb": v["blurb"]}
            for k, v in PERSONALITIES.items()]


def personality_instructions(pid: str) -> str:
    cfg = PERSONALITIES.get(pid) or PERSONALITIES[DEFAULT_PERSONALITY]
    return (f"PERSONALITY — {cfg['label']}: carry a {cfg['style']} tone throughout, "
            "while staying accurate, respectful and clearly an AI assistant.")


async def get_prefs(db, user_id: str) -> dict:
    doc = await db.fun_ai_prefs.find_one({"user_id": user_id}) or {}
    return {"personality": doc.get("personality") or DEFAULT_PERSONALITY}


async def set_prefs(db, user_id: str, *, personality: Optional[str] = None) -> dict:
    sets = {"updated_at": _now_iso()}
    if personality and personality in PERSONALITIES:
        sets["personality"] = personality
    await db.fun_ai_prefs.update_one({"user_id": user_id},
        {"$set": sets, "$setOnInsert": {"user_id": user_id}}, upsert=True)
    return await get_prefs(db, user_id)


# ─── news (reuse existing news_articles) ───────────────────────────────
def _article_view(r: dict, trim: Optional[int] = None) -> dict:
    """Source-grounded article shape — every item carries its provenance."""
    script = r.get("summary_script") or r.get("description") or ""
    if trim and script:
        words = script.split()
        if len(words) > trim:
            script = " ".join(words[:trim]).rstrip(",.;:") + "…"
    wc = max(1, len(script.split()))
    dur = max(12, min(90, int(wc * 0.4)))
    return {
        "news_id": r.get("news_id"),
        "title": r.get("title"),
        "source_name": r.get("source_name") or r.get("source_id"),
        "summary": script,
        "url": r.get("link") or r.get("url"),
        "pubDate": r.get("pubDate"),
        "image_url": r.get("image_url"),
        "categories": r.get("categories") or [],
        "audio_url": r.get("news_audio_url") or r.get("tts_audio_url"),
        "duration_estimate_sec": int(r.get("news_audio_duration") or dur),
        "retrieved_at": _now_iso(),
        "status": "verified",
    }


async def build_briefing(db, *, mode: str = DEFAULT_MODE, market: Optional[str] = None,
                         topic: Optional[str] = None, limit: Optional[int] = None) -> dict:
    cfg = MODES.get(mode) or MODES[DEFAULT_MODE]
    lim = int(limit or cfg["limit"])
    trim = cfg.get("trim")
    program: list = []

    if mode == "deep_dive":
        t = (topic or "").strip()
        if not t:  # default the deep-dive topic to the current top story
            top = await (db.news_articles.find({"summary_script": {"$nin": [None, ""]}})
                         .sort("pubDate", -1).limit(1)).to_list(1)
            if top:
                topic = top[0].get("title")
                t = topic
        if t:
            program = await search_news(db, query=t, limit=lim)

    if not program and mode != "deep_dive":
        q: dict = {"summary_script": {"$nin": [None, ""]}}
        if cfg.get("local") and market:
            q["market"] = market
        if cfg.get("category"):
            q["categories"] = cfg["category"]
        cur = db.news_articles.find(q).sort("pubDate", -1).limit(lim)
        program = [_article_view(r, trim=trim) async for r in cur]
        if not program and (cfg.get("category") or (cfg.get("local") and market)):
            cur = db.news_articles.find({"summary_script": {"$nin": [None, ""]}}).sort("pubDate", -1).limit(lim)
            program = [_article_view(r, trim=trim) async for r in cur]

    sponsor = await get_sponsor(db)
    from services.news_radio_settings import get_anchor_voice
    voice = await get_anchor_voice(db, market=market)
    out = {"mode": mode, "mode_label": cfg["label"], "anchor_hint": cfg["hint"],
           "topic": topic, "program": program, "sponsor": sponsor,
           "anchor_voice": voice, "count": len(program), "generated_at": _now_iso()}
    if not program:
        out["empty_reason"] = "cache_cold"
        out["retry_hint"] = ("Today's news summaries are being prepared — "
                             "try again in a few seconds.")
    return out


async def search_news(db, *, query: str, category: Optional[str] = None,
                      limit: int = 5) -> list:
    """Tool backing the anchor. Searches the cached, source-verified
    ``news_articles`` first; falls back to the live NewsData.io client when
    the cache has nothing. The model never chooses arbitrary URLs."""
    query = (query or "").strip()[:240]
    results: list = []
    if query:
        rx = re.compile(re.escape(query), re.I)
        q: dict = {"$and": [
            {"summary_script": {"$nin": [None, ""]}},
            {"$or": [{"title": rx}, {"summary_script": rx}, {"description": rx}]},
        ]}
        if category:
            q["$and"].append({"categories": category})
        cur = db.news_articles.find(q).sort("pubDate", -1).limit(limit)
        results = [_article_view(r) async for r in cur]
    if not results:
        try:
            from services.newsdata_client import fetch_latest_headlines
            arts = await fetch_latest_headlines(category=category, limit=limit)
            results = [_article_view(a) for a in arts][:limit]
        except Exception as e:  # pragma: no cover - network path
            log.warning("[fun_ai] live news fallback failed: %s", e)
            results = []
    return results


# ─── Follow This Story ─────────────────────────────────────────────────
def _norm_topic(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip()).lower()[:160]


def _follow_view(d: dict) -> dict:
    return {"id": str(d.get("_id")), "topic": d.get("topic"),
            "title": d.get("title") or d.get("topic"),
            "created_at": d.get("created_at")}


async def add_follow(db, user_id: str, topic: str,
                     title: Optional[str] = None) -> Optional[dict]:
    topic = (topic or "").strip()[:160]
    if not topic:
        return None
    key = _norm_topic(topic)
    now = _now_iso()
    await db.fun_ai_follows.update_one(
        {"user_id": user_id, "key": key},
        {"$set": {"topic": topic, "title": (title or topic)[:200], "updated_at": now},
         "$setOnInsert": {"user_id": user_id, "key": key, "created_at": now}},
        upsert=True)
    doc = await db.fun_ai_follows.find_one({"user_id": user_id, "key": key})
    return _follow_view(doc)


async def list_follows(db, user_id: str) -> list:
    cur = db.fun_ai_follows.find({"user_id": user_id}).sort("created_at", -1).limit(50)
    return [_follow_view(d) async for d in cur]


async def remove_follow(db, user_id: str, follow_id: str) -> bool:
    from bson import ObjectId
    try:
        res = await db.fun_ai_follows.delete_one(
            {"_id": ObjectId(follow_id), "user_id": user_id})
        return res.deleted_count > 0
    except Exception:
        return False


async def follow_updates(db, user_id: str, *, limit_topics: int = 10,
                         per: int = 3) -> list:
    """For each followed topic, fetch the latest verified articles."""
    follows = await list_follows(db, user_id)
    out = []
    for fo in follows[:limit_topics]:
        arts = await search_news(db, query=fo["topic"], limit=per)
        out.append({**fo, "updates": arts, "update_count": len(arts)})
    return out


def follows_opening(follows_with_updates: list) -> str:
    items = [f for f in follows_with_updates if f.get("updates")][:3]
    if not items:
        return ""
    bits = []
    for f in items:
        top = f["updates"][0]
        bits.append(f"'{f['topic']}' (latest: \"{top['title']}\" — {top['source_name']})")
    return (" The listener is FOLLOWING these stories; after a short greeting, briefly "
            "offer a verified update on them (confirm with search_news first) before "
            "moving on: " + "; ".join(bits) + ".")


# ─── anchor persona + tool spec ────────────────────────────────────────
def anchor_instructions(*, voice_name: str, sponsor: dict,
                        sponsorship_enabled: bool = True) -> str:
    base = (
        "You are the FUUSIC Interactive News anchor — a warm, concise radio news "
        "presenter. This is a radio-first experience: speak naturally between "
        "stories in short turns and let the listener interrupt you any time. "
        "ALWAYS call the search_news tool to retrieve current, verified news "
        "before stating any fact, name, number or date. NEVER invent headlines, "
        "quotes, dates, statistics or sources. Attribute each claim to its "
        "source. If something cannot be verified, say so plainly. Clearly "
        "distinguish verified reporting from opinion or analysis. Keep answers "
        "brief and conversational. You are an AI assistant — not a human, and "
        "not a medical, legal or mental-health professional. Never present a "
        "sponsor message as independent journalism."
    )
    if sponsorship_enabled and sponsor.get("enabled") and sponsor.get("sponsor_name"):
        base += (f" This news program is sponsored by {sponsor['sponsor_name']}. "
                 "When you open the program, clearly acknowledge that it is "
                 "sponsored by them, kept separate from the news content.")
    return base


def tools_spec() -> list:
    return [{
        "type": "function",
        "name": "search_news",
        "description": ("Retrieve current, verified news articles for the anchor "
                        "to discuss. Returns source, publication date and URL for "
                        "each article."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Topic, person, place or keywords to look up"},
                "category": {"type": "string",
                             "description": ("Optional category: world, business, "
                                             "technology, sports, entertainment, "
                                             "politics, top")},
            },
            "required": ["query"],
        },
    }, {
        "type": "function",
        "name": "follow_story",
        "description": ("Save a news topic/story the listener wants to follow so "
                        "FUUSIC surfaces verified updates next time. Call when the "
                        "listener says things like 'follow this story', 'save this' "
                        "or 'keep me updated on X'."),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "description": "The topic or story headline to follow"},
            },
            "required": ["topic"],
        },
    }, {
        "type": "function",
        "name": "save_user_approved_memory",
        "description": ("Save a music/listening preference the listener explicitly "
                        "asks you to remember (e.g. 'remember I love retro Hindi', "
                        "'I don't like heavy metal', 'my favourite station is X'). "
                        "ONLY call this on an explicit request. NEVER store sensitive, "
                        "health, relationship or private personal information."),
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string",
                     "enum": ["genres", "stations", "disliked", "languages", "interests"]},
            "value": {"type": "string", "description": "The preference to remember"},
        }, "required": ["kind", "value"]},
    }]


# ─── Phase 2: Talk on the Player (radio voice control) ─────────────────
def player_tools_spec() -> list:
    return [
        {"type": "function", "name": "get_now_playing",
         "description": "Get the current FUUSIC station and, if known, the current programme.",
         "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "name": "get_available_radio_formats",
         "description": ("List the eligible FUUSIC radio formats, moods, energy levels "
                         "and languages you may steer toward."),
         "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "name": "request_radio_action",
         "description": ("Request a radio programming change. The FUUSIC policy engine "
                         "decides whether it is permitted — always respect its result. "
                         "Exact on-demand songs are NOT permitted; if the listener asks "
                         "for one, call this with action 'play_exact_song' and relay the "
                         "decline plus the eligible alternative."),
         "parameters": {"type": "object", "properties": {
             "action": {"type": "string",
                        "enum": ["format_change", "mood_change", "energy_change",
                                 "language_change", "change_station", "skip",
                                 "play_exact_song"]},
             "value": {"type": "string",
                       "description": ("Target value — e.g. 'upbeat', 'hindi_retro', a "
                                       "station name, or the requested song/artist")},
         }, "required": ["action"]}},
        {"type": "function", "name": "record_music_feedback",
         "description": "Record the listener's like/dislike of the current music.",
         "parameters": {"type": "object", "properties": {
             "value": {"type": "string", "enum": ["like", "dislike"]},
         }, "required": ["value"]}},
        {"type": "function", "name": "save_user_approved_memory",
         "description": ("Save a music/listening preference the listener explicitly asks "
                         "you to remember (favourite genre/station, a disliked genre, a "
                         "language, or an interest). ONLY on explicit request; NEVER store "
                         "sensitive or private personal information."),
         "parameters": {"type": "object", "properties": {
             "kind": {"type": "string",
                      "enum": ["genres", "stations", "disliked", "languages", "interests"]},
             "value": {"type": "string", "description": "The preference to remember"},
         }, "required": ["kind", "value"]}},
    ]


def player_anchor_instructions(*, voice_name: str, station_name: str,
                               station_type: str = "managed") -> str:
    base = (
        "You are Fun AI, the FUUSIC radio RJ, chatting with the listener over their "
        "music. Keep turns short and warm; the listener can interrupt any time. This "
        "is RADIO, not on-demand music. You can steer the FUUSIC-managed programming — "
        "format, genre, mood, energy and language — and switch stations by calling "
        "request_radio_action; the FUUSIC policy engine is the authority, so always "
        "respect its allowed/denied result and tell the listener the outcome naturally. "
        "If the listener asks for an EXACT song or artist on demand, call "
        "request_radio_action with action 'play_exact_song' (it will be declined) and "
        "then offer an eligible station or format. Use get_now_playing for the current "
        "station and get_available_radio_formats for options. You may chat about artists "
        "and songs from general knowledge, but never invent facts and never promise "
        "on-demand playback. You are an AI assistant, not a human."
    )
    if station_type == "third_party":
        base += (f" The listener is on '{station_name}', a live third-party broadcast "
                 "whose song sequence cannot be changed — you can only switch stations.")
    else:
        base += f" The current FUUSIC station is '{station_name}'."
    return base
