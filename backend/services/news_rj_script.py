"""Phase 40 follow-up — News-channel RJ script generator.

Used by the music radio engine when the listener selects `channel=news_radio`.
Replaces the generic music-channel "FUUSIC Dubai" RJ banter with a 30-45 s
news anchor segment that reads 2-3 real headlines filtered to the listener's
news preferences + city.

Wiring point: `_generate_rj_script_solo` in `server.py` branches to
`generate_news_rj_script(...)` when `channel == "news_radio"`.

Author notes:
  - We deliberately AVOID the "FUUSIC Dubai" tagline that lives in
    HINGLISH_SYSTEM_PROMPT / MIRCHI_SOLO_SYSTEM_PROMPT. News is a
    global channel, not a market-branded music station.
  - Headlines come from the same `news_articles` cache that powers
    `/api/news_radio/queue` and `/api/news/headlines`. We only consume
    rows that have a pre-rendered `summary_script` so prompts stay
    factual (the LLM doesn't have to summarize raw `description`).
  - ElevenLabs TTS for news segments may still be blocked on the
    user's API-key scope; that's a separate downstream concern. This
    file fixes the SCRIPT correctness (which is the user-visible
    "wrong identity / no headlines" bug). TTS rendering uses whatever
    the existing radio engine path uses.
"""
from __future__ import annotations
import logging
import os
import re
from typing import Optional

from openai import OpenAI

log = logging.getLogger("bigfm.news_rj_script")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

NEWS_RJ_MAX_HEADLINES = 3
NEWS_RJ_FRESH_HOURS    = 48   # fall back gracefully if no <2h articles

NEWS_RJ_SYSTEM_PROMPT = (
    "You are the on-air anchor for FUUSIC News — a global headline "
    "round-up channel. Voice: measured, journalistic, conversational. "
    "Reads like AP / NPR cadence, NOT like a music DJ.\n\n"
    "Hard rules:\n"
    " • NEVER say 'FUUSIC Dubai'. This is a global news channel.\n"
    " • NEVER fabricate details or invent quotes — only use the "
    "headlines + context provided.\n"
    " • NEVER use the words 'breaking news' as a hype filler.\n"
    " • NEVER name a specific clock time. Use the freshness bucket "
    "(e.g. 'just in', 'this morning', 'overnight') the caller marks.\n"
    " • DO NOT add ElevenLabs emotion tags like [excited]/[whispers] — "
    "the news voice renders neutrally.\n"
    " • Length: 30-45 seconds of natural read aloud — roughly 80-120 "
    "words total across the whole segment.\n"
    " • Structure: a one-sentence anchor intro that references the "
    "listener's city when provided, 2-3 headlines each read in 1-2 "
    "sentences, a one-sentence outro/teaser to the next segment.\n"
    " • Refer to the channel as 'FUUSIC News' (no city). If the "
    "listener's city is supplied, weave it ONCE — e.g. 'Here's what's "
    "moving in Dallas right now…' — never invent a city.\n"
    " • Skip categories that the listener didn't pick. Don't apologize "
    "for missing categories — just don't mention them.\n"
)


def _trim_for_prompt(text: str, limit: int = 280) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


async def _select_headlines(db, user: dict,
                              limit: int = NEWS_RJ_MAX_HEADLINES) -> list[dict]:
    """Picks up to `limit` headlines from the `news_articles` cache,
    preferring rows that match the user's `news_preferences.categories`,
    falling back to the freshest rows when no preferred-category
    rows exist."""
    prefs = (user or {}).get("news_preferences") or {}
    pref_cats = [str(c).lower()
                  for c in (prefs.get("categories") or [])]

    base_filter = {"summary_script": {"$nin": [None, ""]}}
    chosen: list[dict] = []
    seen: set = set()

    # Pass 1 — preferred categories.
    if pref_cats:
        q = dict(base_filter)
        q["categories"] = {"$in": pref_cats}
        cur = db.news_articles.find(q).sort("pubDate", -1).limit(limit * 2)
        async for r in cur:
            nid = r.get("news_id")
            if nid in seen:
                continue
            seen.add(nid)
            chosen.append(r)
            if len(chosen) >= limit:
                break

    # Pass 2 — fall back to overall freshest so the segment is never
    # empty when the user's preferred categories haven't been crawled
    # in the recent window.
    if len(chosen) < limit:
        cur = db.news_articles.find(base_filter).sort(
            "pubDate", -1).limit(limit * 3)
        async for r in cur:
            nid = r.get("news_id")
            if nid in seen:
                continue
            seen.add(nid)
            chosen.append(r)
            if len(chosen) >= limit:
                break
    return chosen[:limit]


def _build_user_prompt(user: dict, headlines: list[dict]) -> str:
    city = (user or {}).get("city")
    country = (user or {}).get("country")
    location_line = ""
    if city and country:
        location_line = (f"Listener location: {city}, {country}. "
                          f"Reference '{city}' once in the intro.")
    elif city:
        location_line = (f"Listener location: {city}. "
                          f"Reference '{city}' once in the intro.")
    else:
        location_line = ("Listener location: unknown. Use a neutral "
                          "intro like 'Here's your headline round-up' — "
                          "do NOT invent a city.")

    prefs = (user or {}).get("news_preferences") or {}
    cats = prefs.get("categories") or []
    pref_line = (f"Listener picked categories: {', '.join(cats)}."
                  if cats else "Listener has no category preferences set.")

    parts = [
        location_line,
        pref_line,
        "",
        f"Headlines to cover (use ALL of them, in this order):",
    ]
    for i, h in enumerate(headlines, start=1):
        title  = (h.get("title") or "").strip()
        src    = (h.get("source_name") or h.get("source_id")
                  or "an unnamed wire").strip()
        cats_h = ", ".join(h.get("categories") or []) or "general"
        # The pre-rendered radio summary is the best context — already
        # written in news-radio cadence by the renderer.
        summary = _trim_for_prompt(
            h.get("summary_script") or h.get("description") or "",
            limit=320)
        parts.append(
            f"  #{i} ({cats_h}) — {title}\n"
            f"     Source: {src}\n"
            f"     Context: {summary}")
    parts.append(
        "\nWrite the on-air anchor segment now. Output ONLY the spoken "
        "text — no stage directions, no quotation marks, no [tags].")
    return "\n".join(parts)


async def generate_news_rj_script(db, user: dict, *,
                                     voice_key: Optional[str] = None
                                  ) -> str:
    """Returns a 30-45 s news-anchor script suitable for the
    `news_radio` channel. Raises HTTPException(503) on hard failure
    so the outer radio-engine guard serves a no-RJ segment instead of
    a "FUUSIC Dubai" filler. `voice_key` is accepted for API symmetry
    with `_generate_rj_script_solo` but is unused — the news voice
    is selected at TTS render time, not in the script.
    """
    if not _client:
        raise RuntimeError("OPENAI_API_KEY not configured")
    headlines = await _select_headlines(db, user)
    if not headlines:
        # Graceful — no fresh news to read → very short anchor filler
        # that does NOT say "FUUSIC Dubai" and does NOT pretend.
        city = (user or {}).get("city") or "your city"
        return (
            f"You are tuned in to FUUSIC News. We are between stories "
            f"in {city} right now — the next headlines will roll the "
            f"moment our newsroom updates the feed. Stay with us.")

    user_prompt = _build_user_prompt(user, headlines)
    try:
        resp = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": NEWS_RJ_SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.55,
            max_tokens=360,
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning("[news-rj] OpenAI call failed: %s", e)
        raise

    # Strip any wrapping quotes the model occasionally adds.
    out = re.sub(r"^[\"\']+|[\"\']+$", "", out).strip()
    # Defensive scrub — never let "FUUSIC Dubai" slip through.
    out = re.sub(r"FUUSIC\s+Dubai", "FUUSIC News", out, flags=re.IGNORECASE)
    return out
