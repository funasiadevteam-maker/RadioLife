"""FUUSIC content-language preferences.

Language is a HARD filter (hide content in other languages) with a per-user
"Show all languages" escape; genres are a SOFT ranking bias. English-only is
the default until a user explicitly opts into another language, so FUUSIC
never pushes Hindi / other-language content at people who didn't ask for it.

Station `language` data is messy free-text and games/trivia aren't reliably
tagged, so we normalise via keyword detection and treat content with NO
recognisable language token as *neutral* (always shown).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable

# Canonical content languages FUUSIC filters on (superset of onboarding opts).
CANONICAL: dict[str, list[str]] = {
    "english":   ["english", "ingles", "inglés", "anglais"],
    "hindi":     ["hindi", "bollywood", "desi", "hindustani", "filmi", "hindustan"],
    "punjabi":   ["punjabi", "panjabi", "bhangra"],
    "arabic":    ["arabic", "arabesk", "khaleeji", "عرب"],
    "tamil":     ["tamil", "kollywood"],
    "telugu":    ["telugu", "tollywood"],
    "malayalam": ["malayalam", "mallu"],
    "urdu":      ["urdu"],
    "spanish":   ["spanish", "español", "espanol", "latino", "latina"],
}

# Onboarding language option ids -> canonical code.
ONBOARDING_LANG_MAP: dict[str, str] = {
    "hindi": "hindi", "bollywood": "hindi", "punjabi": "punjabi",
    "english": "english", "tamil": "tamil", "arabic": "arabic",
    "malayalam": "malayalam", "telugu": "telugu", "urdu": "urdu",
    "spanish": "spanish",
}

# Broader "this token clearly names a language" set — used to decide whether
# content is in a KNOWN language (so a non-preferred one can be hidden) vs
# neutral. CANONICAL plus common others.
_EXTRA_KNOWN: dict[str, list[str]] = {
    "french": ["french", "français", "francais"],
    "german": ["german", "deutsch"],
    "italian": ["italian", "italiano"],
    "portuguese": ["portuguese", "português", "brasil"],
    "russian": ["russian"],
    "chinese": ["chinese", "mandarin", "cantonese"],
    "japanese": ["japanese"],
    "korean": ["korean", "k-pop", "kpop"],
    "turkish": ["turkish"],
    "bengali": ["bengali", "bangla"],
    "marathi": ["marathi"],
    "gujarati": ["gujarati"],
    "greek": ["greek"],
    "persian": ["persian", "farsi"],
}
KNOWN: dict[str, list[str]] = {**CANONICAL, **_EXTRA_KNOWN}

DEFAULT_LANGUAGES = ["english"]

# Labels for the UI (canonical set only).
LANGUAGE_LABELS = {
    "english": "English", "hindi": "Hindi", "punjabi": "Punjabi",
    "arabic": "Arabic", "tamil": "Tamil", "telugu": "Telugu",
    "malayalam": "Malayalam", "urdu": "Urdu", "spanish": "Spanish",
}


def _kw_regex(codes: Iterable[str]) -> str:
    kws: list[str] = []
    for c in codes:
        kws += KNOWN.get(c, CANONICAL.get(c, [c]))
    return "(" + "|".join(re.escape(k) for k in kws) + ")"


def detect_languages(text: str, universe: dict | None = None) -> set[str]:
    """Return the set of KNOWN language codes named in `text` (may be empty)."""
    if not text:
        return set()
    t = str(text).lower()
    universe = universe or KNOWN
    found: set[str] = set()
    for code, kws in universe.items():
        if any(kw in t for kw in kws):
            found.add(code)
    return found


def to_canonical(raw: str) -> str | None:
    """Map an onboarding id / free-text token to a canonical code."""
    key = str(raw or "").lower().strip()
    if key in ONBOARDING_LANG_MAP:
        return ONBOARDING_LANG_MAP[key]
    det = detect_languages(key)
    return next(iter(det), None)


def user_content_languages(user: dict | None) -> list[str]:
    pv = (user or {}).get("preference_vector") or {}
    out: list[str] = []
    for r in (pv.get("languages") or []):
        c = to_canonical(r)
        if c and c not in out:
            out.append(c)
    return out or list(DEFAULT_LANGUAGES)


def user_show_all(user: dict | None) -> bool:
    pv = (user or {}).get("preference_vector") or {}
    return bool(pv.get("show_all_languages"))


def content_allowed(text_or_lang: str, prefs: Iterable[str],
                    show_all: bool = False, explicit: str | None = None) -> bool:
    """Allowed if show_all, OR explicit content_language is preferred/neutral,
    OR the text names no known language (neutral), OR it names a preferred one."""
    if show_all:
        return True
    pref_set = set(prefs or DEFAULT_LANGUAGES)
    if explicit:
        ec = to_canonical(explicit) or str(explicit).lower()
        if ec in ("neutral", "all"):
            return True
        return ec in pref_set
    detected = detect_languages(text_or_lang or "")
    if not detected:
        return True  # neutral / unknown -> always shown
    return bool(detected & pref_set)


def station_language_or_query(prefs: Iterable[str]) -> dict:
    """Mongo $or: station matches a preferred language OR names no known
    language at all (neutral). Hides stations clearly in a non-preferred lang."""
    pref_rx = _kw_regex(prefs)
    known_rx = _kw_regex(list(KNOWN.keys()))
    return {"$or": [
        {"language": {"$regex": pref_rx, "$options": "i"}},
        {"language": {"$not": {"$regex": known_rx, "$options": "i"}}},
    ]}


def rank_by_genres(items: list, user_genres: Iterable[str],
                   get_genres: Callable[[object], Iterable[str]]) -> list:
    """Stable soft-rank: items sharing a genre with the user surface first."""
    ug = {str(g).lower() for g in (user_genres or [])}
    if not ug:
        return items
    return sorted(
        items,
        key=lambda it: 0 if ({str(x).lower() for x in (get_genres(it) or [])} & ug) else 1,
    )
