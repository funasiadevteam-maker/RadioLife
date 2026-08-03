"""Phase 12c — Content / UGC moderation pipeline.

Two-stage:
    1. Rule-based pre-filter (profanity + regex leak + caps + spam).
    2. AI moderation via OpenAI `omni-moderation-latest` when
       `OPENAI_API_KEY` is set; otherwise log HIGHLIGHTED MOCK and
       fall back to rule-only.

Output:
    {verdict: "allow"|"warn"|"block",
      categories: [...], score, reason}

Every check is persisted to `moderation_audit`.
"""
from __future__ import annotations
import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("bigfm.moderation")

OPENAI_MODERATION_URL = "https://api.openai.com/v1/moderations"
OPENAI_MODEL = "omni-moderation-latest"

# Minimal multi-language profanity seed list.  Expandable via
# safety_settings.profanity_extra (per-language).
PROFANITY_SEED: dict[str, list[str]] = {
    "en": ["fuck", "shit", "bitch", "asshole", "cunt", "nigger",
              "faggot", "retard", "slut", "whore"],
    "hi": ["chutiya", "bhenchod", "madarchod", "lund", "gandu"],
    "ur": ["kuttay", "haram"],
    "pa": ["pendu"],
    "ar": ["كلب", "حقير"],   # placeholder seed; real list expanded later
}

LEAK_PHONE = re.compile(
    r"(?:\+?\d[\s\-\.]?){8,}\d", re.UNICODE)
LEAK_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LEAK_URL = re.compile(
    r"(?:https?://|www\.)\S{4,}", re.IGNORECASE)
# Bare-hostname URL detection: `my-site.com`, `example.com for more` etc.
# Curated TLD allow-list — favours accuracy over completeness so that
# `v1.2.3`, `file.txt`, `e.g.`, `pkg.json` do NOT false-positive.
# Hostname rule: each label 1-63 chars, must contain a letter, only
# a-z/0-9/- allowed; second-level label must start with a letter (rules
# out `1.2.com` style matches inside version strings).
_TLD_LIST = (
    "com|net|org|io|app|co|me|info|biz|tech|dev|ai"
    "|dubai|ae|uk|us|in|pk|sa|gulf|qa")
LEAK_URL_BARE = re.compile(
    r"\b(?=[a-z0-9-]{1,63}\.)[a-z][a-z0-9-]{0,62}"
    r"(?:\.[a-z][a-z0-9-]{0,62})*"
    r"\.(?:" + _TLD_LIST + r")\b",
    re.IGNORECASE)
EXCESS_CAPS_THRESHOLD = 0.75  # of letters uppercase, when len>=10
REPEAT_CHAR = re.compile(r"(.)\1{6,}")  # 7+ same char in a row

CHAT_REF = "chat"
PROFILE_REF = "profile"
AD_REF = "ad_creative"
OFFER_REF = "partner_offer"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:24]


async def ensure_moderation_indexes(db) -> None:
    await db.moderation_audit.create_index(
        [("user_id", 1), ("created_at", -1)])
    await db.moderation_audit.create_index("ref_type")
    await db.moderation_audit.create_index("verdict")
    await db.safety_settings.create_index("_id")


async def _load_safety_settings(db) -> dict:
    """Load safety settings.  Defensive: a previously-saved bad shape
    (e.g., `profanity_extra: []` from a list-style admin save) must NOT
    crash the moderation pipeline."""
    doc = await db.safety_settings.find_one({"_id": "global"}) or {}
    raw_prof = doc.get("profanity_extra")
    profanity_extra = raw_prof if isinstance(raw_prof, dict) else {}
    raw_allow = doc.get("leak_allowlist_partner_ids")
    allowlist = raw_allow if isinstance(raw_allow, list) else []
    return {
        "profanity_extra": profanity_extra,
        "leak_allowlist_partner_ids": allowlist,
        "strike_thresholds": doc.get("strike_thresholds") or {
            "mute_after_medium": 3, "suspend_after_high": 1},
    }


def _rule_check(text: str, *, ref_type: str,
                       profanity_extra: dict | None = None,
                       allow_leaks: bool = False) -> dict:
    """Run cheap rules; never raises. Returns the same dict shape as
    `moderate(...)`."""
    if not text:
        return {"verdict": "allow", "categories": [], "score": 0.0,
                  "reason": "empty"}
    categories: list[str] = []
    score = 0.0
    lowered = text.lower()
    # Profanity — defensive shape check (profanity_extra MUST be dict)
    extra = profanity_extra if isinstance(profanity_extra, dict) else {}
    merged_profanity = {**PROFANITY_SEED, **extra}
    for lang, words in merged_profanity.items():
        if not isinstance(words, (list, tuple)):
            continue
        for w in words:
            if w and isinstance(w, str) and w.lower() in lowered:
                categories.append(f"profanity:{lang}")
                score = max(score, 0.85)
                break
    # Leak regex (only for chat by default; profile/ad allow URLs but we
    # downgrade phone/email to "warn", never block).
    if not allow_leaks:
        if LEAK_PHONE.search(text):
            categories.append("contact_phone")
            score = max(score, 0.55)
        if LEAK_EMAIL.search(text):
            categories.append("contact_email")
            score = max(score, 0.55)
        if LEAK_URL.search(text):
            categories.append("contact_url")
            score = max(score, 0.5)
        elif LEAK_URL_BARE.search(text):
            # Bare hostname like `my-site.com` (no http:// or www. prefix)
            categories.append("contact_url")
            score = max(score, 0.5)
    # Excess caps
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 10:
        upper = sum(1 for c in letters if c.isupper())
        if upper / len(letters) >= EXCESS_CAPS_THRESHOLD:
            categories.append("excess_caps")
            score = max(score, 0.3)
    # Repeat-char spam
    if REPEAT_CHAR.search(text):
        categories.append("repeat_spam")
        score = max(score, 0.4)

    if any(c.startswith("profanity") for c in categories):
        verdict = "block"
    elif (not allow_leaks) and any(
            c.startswith("contact_") for c in categories):
        # Default-deny on contact leaks (phone/email/URL) — block, not
        # just warn — so /api/passport/me/settings 422s the save. The
        # caller can pass allow_leaks=True for verified partners.
        verdict = "block"
        score = max(score, 0.8)
    elif score >= 0.7:
        verdict = "block"
    elif score >= 0.3:
        verdict = "warn"
    else:
        verdict = "allow"
    return {"verdict": verdict, "categories": categories,
              "score": round(score, 3),
              "reason": ",".join(categories) or "clean"}


async def _openai_check(text: str) -> dict | None:
    """OpenAI omni-moderation-latest. Returns None on any error so the
    caller falls back to rule-only verdict."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                OPENAI_MODERATION_URL,
                json={"model": OPENAI_MODEL, "input": text},
                headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"})
        if r.status_code >= 300:
            logger.warning(f"openai moderation HTTP {r.status_code}: "
                                f"{r.text[:120]}")
            return None
        data = r.json()
        result = (data.get("results") or [{}])[0]
        flagged = bool(result.get("flagged"))
        cats_map = result.get("categories") or {}
        cats = [k for k, v in cats_map.items() if v]
        scores = result.get("category_scores") or {}
        max_score = max([float(v) for v in scores.values()] or [0.0])
        if flagged and max_score >= 0.8:
            verdict = "block"
        elif flagged:
            verdict = "warn"
        else:
            verdict = "allow"
        return {"verdict": verdict, "categories": cats,
                  "score": round(max_score, 3),
                  "reason": ",".join(cats) or "clean"}
    except Exception as e:
        logger.warning(f"openai moderation call failed: {e}")
        return None


async def moderate(db, *, text: str, user_id: Optional[str],
                          ref_type: str, ref_id: Optional[str] = None,
                          allow_leaks: bool = False) -> dict:
    """Returns the combined verdict and writes a `moderation_audit`
    row.  Strictest verdict wins between the rule path and the OpenAI
    path."""
    settings = await _load_safety_settings(db)
    rules = _rule_check(text, ref_type=ref_type,
                                profanity_extra=settings["profanity_extra"],
                                allow_leaks=allow_leaks)
    ai_used = False
    model = "rules_only"
    if os.environ.get("OPENAI_API_KEY"):
        ai = await _openai_check(text)
        if ai is not None:
            ai_used = True
            model = OPENAI_MODEL
            # Strictest wins: block > warn > allow
            order = {"allow": 0, "warn": 1, "block": 2}
            if order[ai["verdict"]] > order[rules["verdict"]]:
                combined = ai
            else:
                combined = rules
            combined["categories"] = list(set(
                rules["categories"] + ai["categories"]))
        else:
            combined = rules
    else:
        # *** HIGHLIGHTED MOCK ***
        logger.warning(
            "***** HIGHLIGHTED MOCK ***** OpenAI moderation skipped "
            "(OPENAI_API_KEY unset); using rule-based fallback only.")
        combined = rules

    audit_id = f"mod_{uuid.uuid4().hex[:14]}"
    await db.moderation_audit.insert_one({
        "_id": audit_id, "moderation_id": audit_id,
        "ref_type": ref_type, "ref_id": ref_id,
        "user_id": user_id,
        "input_hash": _hash(text),
        "verdict": combined["verdict"],
        "categories": combined["categories"],
        "score": combined["score"],
        "model": model, "ai_used": ai_used,
        "created_at": _now(),
    })
    combined["moderation_id"] = audit_id
    combined["model"] = model
    return combined
