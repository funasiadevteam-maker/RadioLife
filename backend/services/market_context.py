"""
Phase 15d — bridge between an inbound HTTP request and the market the
caller "lives in". Other services (AI prompt builders, news, weather,
ad targeting) call `get_user_market(request, user)` to resolve a single
canonical market string before reaching the lexicon.
"""
from __future__ import annotations
import re as _re
from typing import Any
from services import geo
from services.market_lexicon import get_lexicon, MARKET_LEXICON


# Phase 15d.1 — content-driven banned-token regex per market. The Dubai
# tokens are the union of all leaks we've seen plus the Hinglish catchphrases
# we want to keep OUT of English markets.
_BANNED_FOR_NON_DUBAI = _re.compile(
    r"\bDubai\b|\bKarak\b|\bKarama\b|\bJLT\b|\bUAE\b|\bBurj\b|\bLulu\b|"
    r"Marina Mall|Dubai Marina|\bJBR\b|Sheikh\s*Zayed|Global\s*Village|"
    r"Atlantis\s*Dubai|Bur\s*Dubai|\bRTA\b|\bSharjah\b",
    _re.IGNORECASE,
)
_HINGLISH_TOKENS = _re.compile(
    r"\bdil\s*se\b|\bdilse\b|\byaar\b|\bdoston\b|\bdosto\b|"
    r"\bchalega\b|\bbhai\b|\bsuno\b|\bsun\s*lo\b|"
    # Phase 15d.1 — common Hinglish bridge words that leaked into English
    # markets via the legacy HINGLISH_SYSTEM_PROMPT. Word-boundary anchored
    # so we don't false-positive on common English (`me` is excluded;
    # `mein` is targeted because it's a Hindi postposition that doesn't
    # exist in English).
    r"\bmein\b|\bkya\b|\bhain\b|\bnahi\b|\bnahin\b|\baapka\b|\bapna\b|"
    r"\baap\s+sun\b|\bsun\s+rahe\b|\bho\s+gaya\b|\bho\s+gayi\b|\bho\s+raha\b|"
    r"\bkyunki\b|\bbilkul\b|\baaj\s+(?:raat|subah|sham)\b|"
    r"\bke\s+saath\b|\bke\s+liye\b|\bke\s+baad\b|\bka\s+waqt\b|"
    r"\btayaar\b|\bhumne\b|\bhumein\b|\bhumara\b|\bhumari\b|"
    r"\bchaand\b|\bneeche\b|\bbaithe\b|\bghusna\b|\bnaye\b|\bdosti\b|"
    r"\bshuruaat\b|\bkhushiyan\b|\bmaayne\b|\brakhte\b"
)


def banned_tokens_for_market(script: str, market: str | None) -> list[str]:
    """Return a list of banned tokens present in `script` given the
       listener's market. Empty list means the script is clean."""
    m = (market or "dubai").strip().lower()
    if m == "dubai":
        return []
    hits: list[str] = []
    hits += [t.group(0) for t in _BANNED_FOR_NON_DUBAI.finditer(script)]
    try:
        lang = (get_lexicon(m).get("language") or "english").lower()
    except Exception:
        lang = "english"
    if lang != "hinglish":
        hits += [t.group(0) for t in _HINGLISH_TOKENS.finditer(script)]
    seen, out = set(), []
    for h in hits:
        k = h.lower()
        if k in seen: continue
        seen.add(k); out.append(h)
    return out


def build_redaction_addendum(market: str | None, banned_hits: list[str]) -> str:
    """When a first generation leaked banned tokens, prepend this addendum
       to the regeneration retry prompt."""
    if not banned_hits:
        return ""
    try:
        city = get_lexicon(market).get("display_name") or market
    except Exception:
        city = market or "this market"
    bad = ", ".join(sorted({h.lower() for h in banned_hits}))
    return (
        f"\n\nREDACTION RULES (your previous script leaked these forbidden "
        f"tokens: {bad}):\n"
        f"- DO NOT use these words anywhere in the next script.\n"
        f"- DO NOT quote a song title that contains any forbidden city — "
        f"refer to it as 'the previous track' or describe its mood instead.\n"
        f"- Speak ONLY in references local to {city}."
    )


async def get_user_market(request, user: dict | None, db: Any) -> str:
    """Return the canonical market key for this request.
       Priority: user override → IP lookup → mock default."""
    resolved = await geo.resolve_for_user(request, user, db)
    return (resolved.get("market") or "dubai").lower()


def build_market_clause(market: str | None) -> str:
    """A drop-in user-prompt addendum that tells the LLM to ONLY mention
       references local to `market`. Same shape used by RJ scripts, trivia
       questions, ad copy, and the AI Ad Creator. The output is plain text
       so it composes with whatever system prompt is already in place."""
    lex = get_lexicon(market)
    brands     = ", ".join(lex["brands"][:6])
    landmarks = ", ".join(lex["landmarks"][:6])
    food       = ", ".join(lex["food"][:6])
    weather   = "; ".join(lex["weather_idioms"][:3])
    lang       = (lex.get("language") or "english").lower()
    # Phase 15d.1 — language-aware sign-off guidance. "Dil se" is a Hinglish
    # catchphrase; for English-only markets the model must use English
    # sign-offs (no romanised Hindi).
    if lang == "hinglish":
        sign_offs = (
            "Use natural Hinglish (~60% English, 40% Hindi connectors in Roman script). "
            "Sign-offs like 'RadioLife, dil se' / 'Music chalega non-stop' are OK."
        )
    else:
        sign_offs = (
            "Speak in NATURAL ENGLISH ONLY. DO NOT use Hindi/Urdu words, "
            "DO NOT use Hinglish, DO NOT say 'dil se', 'yaar', 'doston', "
            "'mein', 'chalega', 'kya scene'. Use English sign-offs like "
            f"'RadioLife {lex['display_name']}, from the heart' / 'Stay tuned' / "
            f"'You're locked in on RadioLife {lex['display_name']}'."
        )
    return (
        f"You are a {lex['display_name']}-based AI radio host on station "
        f"RadioLife {lex['display_name']}.\n"
        f"ONLY mention local landmarks, local brands, local food, "
        f"local weather, and local cultural references for {lex['display_name']}.\n"
        f"DO NOT mention any other city or brand unless explicitly asked.\n"
        f"{sign_offs}\n"
        f"Local examples — brands: {brands}. "
        f"Landmarks: {landmarks}. "
        f"Food: {food}. "
        f"Weather idioms: {weather}."
    )


def is_supported_market(market: str | None) -> bool:
    if not market: return False
    key = market.strip().lower().replace(" ", "_").replace("-", "_")
    return key in MARKET_LEXICON
