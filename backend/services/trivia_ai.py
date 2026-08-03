"""
Phase 16a — AI Trivia generator.

Generates market-scoped multiple-choice trivia questions using OpenAI's
chat completion API with `response_format=json_object` for reliable
parsing.  Inherits the same market-scoping + banned-token discipline as
the RJ script pipeline (services/script_pipeline.py + market_context.py),
so a DFW question NEVER references Dubai brands / landmarks / food.

Idempotency: every generated question is content-hashed (sha256 of the
prompt text) and upserted into `trivia_questions` keyed by that hash.
If the model regenerates the same prompt, we silently de-dupe.

Freshness: the lookup-and-serve path in `pick_for_user` excludes any
question the caller has answered in the past 90 days.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from openai import OpenAI

from core.config import OPENAI_API_KEY
from services.market_lexicon import get_lexicon
from services.market_context import (
    banned_tokens_for_market,
    build_redaction_addendum,
)

logger = logging.getLogger("bigfm.trivia_ai")

_OPENAI_CLIENT: Optional[OpenAI] = None
_MODEL = "gpt-4o-mini"


def _client() -> OpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    return _OPENAI_CLIENT


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().lower().encode("utf-8")).hexdigest()[:24]


def _build_system_prompt(market: str, category: str, difficulty: int) -> str:
    lex = get_lexicon(market)
    display = lex.get("display_name") or market.title()
    brands     = ", ".join(lex["brands"][:8])
    landmarks = ", ".join(lex["landmarks"][:8])
    food       = ", ".join(lex["food"][:8])
    language  = (lex.get("language") or "english").lower()
    lang_rule = (
        "Questions and choices in NATURAL ENGLISH ONLY. "
        "Do NOT use Hindi/Urdu words, Hinglish, or transliterated terms."
        if language != "hinglish" else
        "Questions in English; cultural references may use familiar "
        "Hinglish terms (e.g. karak, biryani) where natural."
    )
    return (
        f"You are a trivia question writer for BigFM, an AI radio app "
        f"serving the South Asian diaspora in {display}.\n"
        f"Generate trivia questions for the category '{category}' at "
        f"difficulty {difficulty}/5 (1=easy, 5=hard).\n\n"
        f"STRICT MARKET-SCOPING RULES:\n"
        f"- ALL references must be local to {display}. Local brands include "
        f"{brands}. Landmarks include {landmarks}. Food includes {food}.\n"
        f"- DO NOT mention any other city, country, or brand outside the "
        f"{display} market unless the category is 'global' or 'general'.\n"
        f"- {lang_rule}\n\n"
        f"OUTPUT CONTRACT (return JSON only, no commentary):\n"
        f'{{\n'
        f'  "questions": [\n'
        f'    {{\n'
        f'      "prompt": "What... ?",\n'
        f'      "choices": ["A", "B", "C", "D"],\n'
        f'      "correct_index": 0  // 0..3, the index of the correct choice in `choices`\n'
        f'    }}\n'
        f'  ]\n'
        f'}}\n\n'
        f"QUESTION QUALITY:\n"
        f"- Each question has EXACTLY 4 plausible choices.\n"
        f"- Exactly ONE correct answer per question.\n"
        f"- Wrong choices must be plausible (not obviously absurd).\n"
        f"- Prompts under 140 characters. Each choice under 60 characters.\n"
        f"- Avoid trick questions and pop-culture spoilers."
    )


def _parse_raw(raw: str) -> list[dict]:
    """Parse the OpenAI JSON response into a list of normalized question
    dicts.  Tolerates the model returning {"questions": [...]} or a bare
    array."""
    try:
        data = json.loads(raw)
    except Exception:
        # Strip ``` fences if the model added them.
        cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        data = json.loads(cleaned)
    if isinstance(data, dict) and "questions" in data:
        items = data["questions"]
    elif isinstance(data, list):
        items = data
    else:
        items = []
    out = []
    for q in items:
        prompt = (q.get("prompt") or q.get("question") or "").strip()
        choices = q.get("choices") or []
        idx = q.get("correct_index")
        if idx is None and "correct_choice_id" in q:
            idx = q.get("correct_choice_id")
        if not prompt or len(choices) != 4 or idx is None:
            continue
        try:
            idx = int(idx)
        except Exception:
            continue
        if not (0 <= idx <= 3):
            continue
        out.append({"prompt": prompt, "choices": list(choices), "correct_index": idx})
    return out


def _attach_ids(items: list[dict]) -> list[dict]:
    """Add stable choice IDs (a/b/c/d) and a correct_choice_id field that
    matches the on-disk schema."""
    LETTERS = ["a", "b", "c", "d"]
    norm = []
    for q in items:
        choice_objs = [
            {"id": LETTERS[i], "text": str(c).strip()}
            for i, c in enumerate(q["choices"])
        ]
        norm.append({
            "prompt": q["prompt"].strip(),
            "choices": choice_objs,
            "correct_choice_id": LETTERS[q["correct_index"]],
        })
    return norm


async def generate_questions(
    db,
    market: str,
    category: str,
    difficulty: int = 2,
    count: int = 10,
) -> list[dict]:
    """Generate `count` questions for the given market/category.  Persists
    each unique question into `trivia_questions` (idempotent on content
    hash).  Returns the list of stored docs (with `id`, no
    `correct_choice_id` stripping — the caller decides what to expose)."""
    if not OPENAI_API_KEY:
        logger.warning("[trivia_ai] OPENAI_API_KEY missing — returning []")
        return []

    market = (market or "dubai").lower()
    system = _build_system_prompt(market, category, difficulty)
    user_msg = (
        f"Generate {count} trivia questions. Category: {category}. "
        f"Difficulty: {difficulty}/5. Return JSON in the contract above."
    )

    try:
        resp = _client().chat.completions.create(
            model=_MODEL,
            response_format={"type": "json_object"},
            temperature=0.85,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            timeout=60,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        logger.exception("[trivia_ai] OpenAI call failed: %s", e)
        return []

    parsed = _parse_raw(raw)

    # Post-redaction: per-question banned-token check.  Retry the leaked
    # ones ONCE with an explicit redaction addendum; drop if still leaks.
    cleaned: list[dict] = []
    leaked: list[dict] = []
    for q in parsed:
        blob = q["prompt"] + " " + " ".join(q["choices"])
        hits = banned_tokens_for_market(blob, market)
        if hits:
            leaked.append({"q": q, "hits": hits})
        else:
            cleaned.append(q)

    if leaked:
        logger.warning(
            "[trivia_ai] market=%s leaked %d/%d questions — retrying",
            market, len(leaked), len(parsed),
        )
        all_hits = [h for item in leaked for h in item["hits"]]
        addendum = build_redaction_addendum(market, all_hits)
        retry_msg = (
            user_msg + addendum +
            f"\n\nRegenerate {len(leaked)} fresh questions — different "
            f"prompts, NO forbidden tokens."
        )
        try:
            resp2 = _client().chat.completions.create(
                model=_MODEL,
                response_format={"type": "json_object"},
                temperature=0.9,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": retry_msg},
                ],
                timeout=60,
            )
            retry_parsed = _parse_raw(resp2.choices[0].message.content or "")
            for q in retry_parsed:
                blob = q["prompt"] + " " + " ".join(q["choices"])
                if not banned_tokens_for_market(blob, market):
                    cleaned.append(q)
        except Exception as e:
            logger.warning("[trivia_ai] redaction retry failed: %s", e)

    normalized = _attach_ids(cleaned)

    # Idempotent upsert: content hash on prompt.  Multiple rapid calls
    # with the same model output won't duplicate rows.
    now = datetime.now(timezone.utc)
    stored: list[dict] = []
    for q in normalized:
        h = _prompt_hash(q["prompt"])
        doc = {
            "id": f"q_{h}",
            "prompt_hash": h,
            "prompt": q["prompt"],
            "choices": q["choices"],
            "correct_choice_id": q["correct_choice_id"],
            "category": category,
            "market": market,
            "difficulty": difficulty,
            "language": (get_lexicon(market).get("language") or "english"),
            "source": "openai_gpt4o_mini",
            "created_at": now,
            "used_count": 0,
            "rating": None,
        }
        existing = await db.trivia_questions.find_one({"prompt_hash": h})
        if existing:
            stored.append(existing)
        else:
            await db.trivia_questions.insert_one(doc)
            stored.append(doc)

    logger.info(
        "[trivia_ai] market=%s cat=%s diff=%d → %d kept (%d leaked, %d total)",
        market, category, difficulty,
        len(stored), len(leaked), len(parsed),
    )
    return stored


async def pick_for_user(
    db,
    user_id: str,
    market: str,
    category: str,
    count: int = 10,
    *,
    difficulty: int = 2,
    freshness_days: int = 90,
) -> list[dict]:
    """Return `count` questions for the user, regenerating via OpenAI on
    cache miss.  Skips questions the user has answered within
    `freshness_days`."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    recent_qids = set()
    async for row in db.trivia_answers.find(
        {"user_id": user_id, "answered_at": {"$gte": cutoff}},
        projection={"question_id": 1, "_id": 0},
    ):
        recent_qids.add(row.get("question_id"))

    # Try the cache first.
    query = {
        "market": {"$in": [market, "global"]},
        "category": category,
    }
    fresh_pool = []
    async for q in db.trivia_questions.find(query).limit(200):
        if q["id"] in recent_qids:
            continue
        fresh_pool.append(q)
        if len(fresh_pool) >= count * 3:
            break

    if len(fresh_pool) < count:
        # Generate the missing ones and try again.
        await generate_questions(db, market, category, difficulty, count - len(fresh_pool) + 5)
        fresh_pool = []
        async for q in db.trivia_questions.find(query).limit(200):
            if q["id"] in recent_qids:
                continue
            fresh_pool.append(q)
            if len(fresh_pool) >= count * 3:
                break

    # Bump used_count + sort by least-recently-used (best-effort
    # cycling, not strict).
    fresh_pool.sort(key=lambda q: (q.get("used_count", 0), q.get("created_at") or datetime.min))
    picked = fresh_pool[:count]
    if picked:
        ids = [q["id"] for q in picked]
        await db.trivia_questions.update_many(
            {"id": {"$in": ids}}, {"$inc": {"used_count": 1}},
        )
    return picked


async def ensure_trivia_indexes(db) -> None:
    await db.trivia_questions.create_index("id", unique=True)
    await db.trivia_questions.create_index("prompt_hash", unique=True)
    await db.trivia_questions.create_index([("market", 1), ("category", 1)])
    await db.trivia_categories.create_index("id", unique=True)
    await db.trivia_categories.create_index([("market", 1), ("active", 1)])
    await db.trivia_sessions.create_index("id", unique=True)
    await db.trivia_sessions.create_index([("user_id", 1), ("started_at", -1)])
    await db.trivia_answers.create_index([("session_id", 1)])
    await db.trivia_answers.create_index([("user_id", 1), ("answered_at", -1)])
    await db.trivia_answers.create_index([("user_id", 1), ("question_id", 1)])


async def seed_default_categories(db) -> None:
    """Idempotent seed of 5 base trivia categories across the supported
    markets.  Gated by the `_phase16a_categories_seeded` migration flag."""
    flag = await db.migration_flags.find_one({"_id": "_phase16a_categories_seeded"})
    if flag and flag.get("done"):
        return

    base = [
        ("general",        "General Knowledge", "Brainy bites — anything goes"),
        ("music",           "Music",                  "From classics to chart-toppers"),
        ("local-culture",  "Local Culture",         "Your city, your flavour"),
        ("movies",          "Movies",                "Big screen, bigger questions"),
        ("sports",          "Sports",                "Pitch, court, podium"),
    ]
    markets = ["global", "dubai", "dfw", "new_york", "london", "toronto"]
    docs: list[dict] = []
    for slug, name, tagline in base:
        # `local-culture` is per-market; the others ship as `global`.
        if slug == "local-culture":
            for m in [x for x in markets if x != "global"]:
                docs.append({
                    "id": f"{m}-{slug}",
                    "slug": slug,
                    "name": f"{(get_lexicon(m).get('display_name') or m.title())} Culture",
                    "tagline": tagline,
                    "market": m,
                    "language": (get_lexicon(m).get("language") or "english"),
                    "active": True,
                    "weight": 1.0,
                    "icon": "🌆",
                })
        else:
            docs.append({
                "id": f"global-{slug}",
                "slug": slug,
                "name": name,
                "tagline": tagline,
                "market": "global",
                "language": "english",
                "active": True,
                "weight": 1.0,
                "icon": {"general":"🧠","music":"🎵","movies":"🎬","sports":"🏟️"}[slug],
            })
    for d in docs:
        await db.trivia_categories.update_one(
            {"id": d["id"]}, {"$setOnInsert": d}, upsert=True,
        )
    await db.migration_flags.update_one(
        {"_id": "_phase16a_categories_seeded"},
        {"$set": {"done": True, "at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    logger.info("[trivia_ai] seeded %d default categories", len(docs))
