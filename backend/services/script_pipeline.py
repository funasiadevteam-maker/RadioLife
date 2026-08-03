"""Phase 3.7 — Two-stage RJ script generation.

Pipeline:
   Stage 1: `draft_script()`  → OpenAI gpt-4o-mini using the personality
                                profile's voice_direction_prompt + context.
   Stage 2: `radio_naturalness_rewrite()` → second OpenAI pass that rewrites
                                the draft into natural spoken Hinglish per the
                                user's exhaustive rule list.

The rewritten script is then handed to the TTS layer (ElevenLabs or
OpenAI TTS) — `services/openai_tts.py` for `openai_tts` voices, the
existing ElevenLabs path for the rest.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from core.config import OPENAI_API_KEY

logger = logging.getLogger("bigfm.script_pipeline")

_OPENAI_CLIENT: Optional[OpenAI] = None
_MODEL = "gpt-4o-mini"
_TEMP_DRAFT = 0.95
_TEMP_REWRITE = 0.85


# Phase 15d.1 — single source of truth for the city display label used in
# RJ prompts. Pulls `display_name` from the market lexicon (e.g. dfw → Dallas,
# new_york → New York). Falls back to `.title()` only when an unknown market
# slips through so the raw "DFW" / "NEW_YORK" never reaches the LLM.
def _market_display(market: str | None) -> str:
    m = (market or "dubai").strip().lower()
    try:
        from services.market_lexicon import get_lexicon
        return get_lexicon(m).get("display_name") or m.replace("_", " ").title()
    except Exception:
        return m.replace("_", " ").title()


def _market_language(market: str | None) -> str:
    m = (market or "dubai").strip().lower()
    try:
        from services.market_lexicon import get_lexicon
        return (get_lexicon(m).get("language") or "english").lower()
    except Exception:
        return "english"


def _client() -> OpenAI:
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        _OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY)
    return _OPENAI_CLIENT


# ===========================================================================
# Stage 2: The Radio Naturalness Rewrite System Prompt
# ===========================================================================
NATURALNESS_REWRITE_SYSTEM_PROMPT_TEMPLATE = """You rewrite formal RJ scripts into natural spoken Hinglish for a {profile_name} radio host on BigFM {market_label}.

RULES (apply ALL):
- Convert formal lines to spoken Hinglish. Hindi in Roman script.
- Replace "listeners" → "dosto" or "guys" or just drop the address
- Replace "we will now play" → "ab vibe ko thoda aur upar le jaate hain"
- Replace "stay tuned" → "kahin mat jaana" / "stay with me"
- Replace "the next song is" → "coming up, energy thodi aur badhne wali hai" — and NEVER reveal exact upcoming song name/artist (non-interactive compliance)
- Replace "Main aapka RJ hoon..." → just start with the actual content, drop the intro
- Replace "Hello listeners, welcome to..." → "Kya scene hai, {market_label}!" or "{market_label}, good morning!" or similar context-appropriate opening
- Avoid formal Hindi: NO "shrotaon", "namaskar", "padharo" unless explicitly news/talk station
- DON'T translate every English word — keep technical/lifestyle terms in English (vibe, traffic, weekend, brunch, club, scene, mood, energy)
- Bilingual phrasing should feel NATURAL, not forced 50/50 — let one language dominate per sentence with light code-switching
- Short spoken sentences. Add punctuation for pacing — "." for breaths, "," for micro-pauses, "..." for thinking beats
- Add 2-5 ElevenLabs v3 audio tags inline — match to the host's tone: {tone_tags}
- Add ONE small pause or emotional cue where natural [pause], [smiles], [warmly]
- Keep under {word_budget} words (we speak ~2.5 words/sec, target {target_seconds} spoken seconds)
- Match the host's energy — don't make every line peak-excited

USEFUL TAGS (use sparingly):
[warmly] [upbeat] [smiles] [laughs softly] [pause] [quick beat] [confident] [softly]
[excited but controlled] [radio host energy] [builds anticipation] [relaxed]
[whispers playfully] [punchy] [smooth]

INSPIRATION PHRASES (do NOT copy verbatim — use only for cadence + word choice):
{phrase_inspiration}

OUTPUT FORMAT examples:

Morning Drive example:
[upbeat, radio host energy] DFW, good morning! Traffic thoda slow hai, but music bilkul high-energy rakhenge. [pause] Aap sun rahe ho BigFM DFW — Bollywood hits, local updates, aur thode surprises all the way. [smiles] Stay with me.

Lunch example:
[warmly] Lunch ka time ho gaya hai, [smiles] aur deals bhi garam hain. Aap route pe ho, aur ek solid food stop nearby hai. [quick beat] Spin karo — shayad dessert free mil jaaye.

Nightlife example:
[punchy] Friday night ka scene set hai. [confident] Party mode on, DFW. Club energy, Bollywood flavor, aur thoda surprise coming up. [builds anticipation] Volume thoda aur up...

NEVER:
- "Hello listeners, welcome to..." or any variant
- "Main aapka RJ hoon..." or "I am your RJ..."
- Long paragraphs
- Formal announcement style
- Robotic station IDs
- Literal translations
- Excessive Hindi OR excessive English
- Fake excitement on every line
- Generic AI assistant language
- Same phrases repeatedly

PRONUNCIATION HINTS — spell brand/place/festival names exactly so the TTS reads them right:
- DFW cities & areas: Frisco, Plano, Irving, Carrollton, Richardson, Dallas, Fort Worth, Arlington, Garland, Allen, McKinney, Lewisville, Grapevine, Coppell, Las Colinas, Little Elm
- Dubai areas (already covered): Karama, Bur Dubai, Deira, Al Nahda, JLT, Business Bay, Downtown, Marina, Sharjah, Sheikh Zayed, Global Village, Atlantis, JBR, Festival City
- South Asian brand names — write them as-is, the TTS handles them: FunAsia, Jay Bhavani, Thakkar Restaurant, Sangam, Saravana Bhavan, Tarka, Bombay Chopsticks, Mughlai, Roomali, Chaat House, India Bazaar, Patel Brothers
- Common South Asian surnames: Thakkar, Bhavani, Patel, Reddy, Sharma, Singh, Khan, Iyer, Kapoor, Mehta, Shah, Gupta, Agarwal, Chandra, Nair
- South Asian celebrity names — spell as-is: Shah Rukh Khan, Salman Khan, Aamir Khan, Deepika Padukone, Priyanka Chopra, Alia Bhatt, Ranveer Singh, Ranbir Kapoor, Diljit Dosanjh, AP Dhillon, Karan Aujla, Honey Singh, Badshah, Arijit Singh, Shreya Ghoshal, Neha Kakkar
- Festivals — write as-is: Diwali, Holi, Eid, Eid al-Fitr, Eid al-Adha, Navratri, Karva Chauth, Raksha Bandhan, Janmashtami, Ganesh Chaturthi, Onam, Pongal, Baisakhi, Lohri, Christmas, New Year
- Music labels & brands: T-Series, Sony Music India, YRF Music, Saregama, Zee Music, Tips Music
- Avoid spelling out acronyms like "DFW" letter-by-letter — leave as "DFW", TTS handles it
- For honorifics, write "ji" / "bhaiya" / "didi" / "anna" / "akka" as-is

Return ONLY the rewritten script — no explanations."""


# Phase 15d.1 — English-only rewrite template for english-language markets
# (dfw, new_york, london, los_angeles). The Hinglish template above is used
# for hinglish markets (dubai, mumbai).
NATURALNESS_REWRITE_SYSTEM_PROMPT_TEMPLATE_EN = """You rewrite formal RJ scripts into natural spoken ENGLISH for a {profile_name} radio host on BigFM {market_label}.

CRITICAL — ENGLISH-ONLY MARKET:
- This script is for {market_label}, a NON-Hinglish market.
- Output 100% ENGLISH. DO NOT use any Hindi/Urdu/Hinglish words.
- NEVER use: "yaar", "dosto", "doston", "kya scene", "abhi", "chalu hai", "ho gaya", "mein", "ke saath", "ke liye", "raha hai", "chalega", "dil se", "suno", "bhai", "thoda", "bilkul", "wahi", "ke baad".
- NEVER use Dubai-specific anchors: Karak, JLT, Karama, JBR, Burj, Sharjah, Sheikh Zayed, RTA, UAE.
- Station identity is "BigFM {market_label}" (e.g. "BigFM Dallas", "BigFM <market_city>"). NEVER write the market_id raw — always spell the city.

RULES (apply ALL):
- Convert formal/announcement lines into natural conversational ENGLISH that sounds like a real American/British radio host.
- Replace "listeners" → "you all", "everyone", "{market_label}", or drop the address.
- Replace "we will now play" → "up next, we're keeping the energy going" / "coming up".
- Replace "stay tuned" → "stick around" / "stay with me" / "right here on BigFM {market_label}".
- Replace "the next song is" → "coming up, the vibe stays..." — and NEVER reveal the exact upcoming song name/artist.
- Replace "Hello listeners, welcome to..." → "Hey {market_label}!" or "{market_label}, how we doing?" or "What's going on, {market_label}?"
- Short spoken sentences. Use natural pauses ("...", "—") for breath.
- Add 2-5 ElevenLabs v3 audio tags inline — match to the host's tone: {tone_tags}
- Add ONE small emotional cue where natural [pause], [smiles], [warmly], [chuckles].
- Keep under {word_budget} words (~2.5 words/sec, target {target_seconds} spoken seconds).
- Drop authentic local references for {market_label} — areas, food, weather, traffic, brands. (The user prompt will include a MARKET CONTEXT block with the lexicon for this market.)
- Sign-off variants: "BigFM {market_label}, from the heart" / "Stay locked in on BigFM {market_label}" / "You're on BigFM {market_label}" / "That's BigFM {market_label}".

USEFUL TAGS (use sparingly):
[warmly] [upbeat] [smiles] [laughs softly] [pause] [quick beat] [confident] [softly]
[excited but controlled] [radio host energy] [builds anticipation] [relaxed]
[whispers playfully] [punchy] [smooth]

INSPIRATION PHRASES (do NOT copy verbatim — use only for cadence + word choice):
{phrase_inspiration}

OUTPUT FORMAT examples (these are for Dallas — adapt for {market_label}):

Morning Drive example:
[upbeat, radio host energy] Dallas, good morning! Traffic's a little slow on the 75, but we're keeping the music HIGH-energy. [pause] You're locked in on BigFM Dallas — the hits, local updates, and a few surprises coming up. [smiles] Stick around.

Lunch example:
[warmly] Lunchtime, Dallas, [smiles] and the patio weather is unreal today. Whether you're grabbing breakfast tacos at Velvet Taco or queso at Torchy's, we got the soundtrack. [quick beat] Stay with me.

Evening example:
[punchy] Friday night, Dallas. [confident] Patio set, queso ready, and the energy is right where it should be — high. [builds anticipation] Volume up...

NEVER:
- "Hello listeners, welcome to..." or any variant
- "Main aapka RJ hoon..." or "I am your RJ..."
- Long paragraphs
- Formal announcement style
- Robotic station IDs
- ANY Hindi/Urdu/Hinglish word — output is 100% English
- Generic AI-assistant phrasing
- Same opener phrases on every script

Return ONLY the rewritten script — no explanations."""


# ===========================================================================
# Stage 1: Draft script (uses personality profile's voice_direction_prompt)
# ===========================================================================
async def draft_script(
    *, profile: dict, voice_persona: str, prev_track: Optional[dict],
    next_track: dict, market: str, daypart: str, dubai_hour: int,
    weather_hint: Optional[str] = None, channel_name: Optional[str] = None,
    milestone_shoutout: Optional[int] = None,
    commute_arrival: Optional[dict] = None,
) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    target = profile.get("default_script_length_sec", 22)
    market_label = _market_display(market)

    nxt_energy = next_track.get("energy_level", "medium")
    nxt_mood = next_track.get("mood") or "uplifting"
    if prev_track:
        prev_line = (f"Previous song: '{prev_track['title']}' by {prev_track['artist']} "
                     f"(energy={prev_track.get('energy_level', 'medium')}, "
                     f"mood={prev_track.get('mood') or 'uplifting'}).")
    else:
        prev_line = "This is the opening of the show — no previous song yet."

    milestone_block = ""
    if milestone_shoutout:
        milestone_block = (
            f"\nIMPORTANT — listener milestone shoutout: this listener just "
            f"crossed {milestone_shoutout} BigCoin lifetime earned. Weave a "
            f"natural shoutout into the script (mention the number {milestone_shoutout} "
            f"and 'BigCoin'). Keep it celebratory but brief — 1 sentence max.\n"
        )
    commute_block = ""
    if commute_arrival:
        dest = commute_arrival.get("destination_label") or "your destination"
        dur_h = commute_arrival.get("duration_human") or "a quick"
        wx = commute_arrival.get("weather_condition") or "clear"
        commute_block = (
            f"\nLISTENER JUST ARRIVED at {dest} after {dur_h} drive in {wx} "
            f"weather.  Open with ONE short welcome-back line that names "
            f"the destination and the drive — natural, warm, 5-8 words max — "
            f"BEFORE bridging to the next track.  Do it once only.\n"
        )

    user_prompt = (
        f"You are speaking as: {voice_persona}.\n"
        f"You are a {profile['name']} host on BigFM {market_label}. "
        f"Tone tags: {', '.join(profile['tone_tags'])}.\n"
        f"{prev_line}\n"
        f"Next song coming up (DO NOT name it): '{next_track['title']}' by {next_track['artist']} "
        f"(energy={nxt_energy}, mood={nxt_mood}).\n"
        f"Daypart: {daypart}. {market_label} hour: {dubai_hour}:00. "
        f"{('Weather: ' + weather_hint) if weather_hint else ''}\n"
        f"{('Show: ' + channel_name) if channel_name else ''}\n"
        f"{milestone_block}"
        f"{commute_block}"
        f"Target: {target} spoken seconds.\n\n"
        f"Write a natural Hinglish RJ break for this moment."
    )

    resp = await _run_chat(
        system=profile["voice_direction_prompt"],
        user=user_prompt,
        temperature=_TEMP_DRAFT,
        max_tokens=320,
    )
    return resp.strip()


# ===========================================================================
# Stage 2: Naturalness Rewrite
# ===========================================================================
async def radio_naturalness_rewrite(
    draft: str, *, profile: dict, market: str, phrase_inspiration: List[str],
) -> str:
    if not OPENAI_API_KEY:
        return draft
    market_label = _market_display(market)
    target = profile.get("default_script_length_sec", 22)
    word_budget = int(target * 2.5)
    inspiration_block = "\n".join(f"  • {p}" for p in phrase_inspiration[:6]) if phrase_inspiration else "  (none available — write fresh)"

    # Phase 15d.1 — pick the template that matches the market's spoken
    # language. English-language markets (dfw, new_york, london, los_angeles)
    # use the English-only variant so the rewrite never re-injects Hinglish.
    is_english_market = _market_language(market) != "hinglish"
    template = (NATURALNESS_REWRITE_SYSTEM_PROMPT_TEMPLATE_EN
                      if is_english_market
                      else NATURALNESS_REWRITE_SYSTEM_PROMPT_TEMPLATE)
    system_prompt = template.format(
        profile_name=profile["name"],
        market_label=market_label,
        tone_tags=", ".join(profile["tone_tags"]),
        word_budget=word_budget,
        target_seconds=target,
        phrase_inspiration=inspiration_block,
    )
    user_prompt = (
        f"REWRITE THIS DRAFT into natural spoken "
        f"{'English' if is_english_market else 'Hinglish'} "
        f"for {market_label}, following ALL rules above:\n\n"
        f"{draft}\n\n"
        f"Return only the rewritten script."
    )

    rewritten = await _run_chat(
        system=system_prompt, user=user_prompt,
        temperature=_TEMP_REWRITE, max_tokens=300,
    )
    # Defensive guards — strip surrounding quotes if the model added them
    rewritten = re.sub(r'^["\']|["\']$', "", rewritten.strip()).strip()
    # Phase 15d.1 — POST-REDACTOR on rewrite output. If the model still
    # leaked banned tokens for this market (yaar/doston for English markets,
    # or any Dubai-anchor for non-Dubai markets), regenerate ONCE with an
    # explicit redaction addendum; if the retry still leaks, fall back to
    # the draft (which went through Stage-1 generation already).
    try:
        from services.market_context import (
            banned_tokens_for_market as _check,
            build_redaction_addendum as _addendum,
        )
        hits = _check(rewritten, market)
        if hits:
            logger.warning(
                "[script_pipeline.rewrite] market=%s leaked %s — regenerating once",
                market, hits,
            )
            addn = _addendum(market, hits)
            user2 = user_prompt + addn
            rewritten2 = await _run_chat(
                system=system_prompt, user=user2,
                temperature=_TEMP_REWRITE, max_tokens=300,
            )
            rewritten2 = re.sub(r'^["\']|["\']$', "", rewritten2.strip()).strip()
            if not _check(rewritten2, market):
                rewritten = rewritten2
            else:
                logger.error(
                    "[script_pipeline.rewrite] market=%s STILL leaked after "
                    "retry — falling back to draft", market,
                )
                rewritten = draft
    except Exception as _e:
        logger.warning("[script_pipeline.rewrite] redactor skipped: %s", _e)
    return rewritten or draft


# ===========================================================================
# Stage 1+2 combined
# ===========================================================================
async def generate_natural_rj_script(
    *, profile: dict, voice_persona: str, prev_track: Optional[dict],
    next_track: dict, market: str, daypart: str, dubai_hour: int,
    weather_hint: Optional[str] = None, channel_name: Optional[str] = None,
    phrase_inspiration: Optional[List[str]] = None,
    milestone_shoutout: Optional[int] = None,
    commute_arrival: Optional[dict] = None,
) -> Tuple[str, str]:
    """Returns (draft, rewritten). Both kept so audio QA can compare."""
    draft = await draft_script(
        profile=profile, voice_persona=voice_persona, prev_track=prev_track,
        next_track=next_track, market=market, daypart=daypart, dubai_hour=dubai_hour,
        weather_hint=weather_hint, channel_name=channel_name,
        milestone_shoutout=milestone_shoutout,
        commute_arrival=commute_arrival,
    )
    rewritten = await radio_naturalness_rewrite(
        draft, profile=profile, market=market,
        phrase_inspiration=phrase_inspiration or [],
    )
    return draft, rewritten


# ---------- Helpers ----------
async def _run_chat(*, system: str, user: str, temperature: float, max_tokens: int) -> str:
    import asyncio
    def _sync():
        resp = _client().chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    return await asyncio.to_thread(_sync)


# ===========================================================================
# Banned phrase detector (for QA dashboard "common issues" tile)
# ===========================================================================
BANNED_PATTERNS = [
    (re.compile(r"main aapka rj h(oo|u)n", re.I),       "main aapka RJ hoon"),
    (re.compile(r"hello listeners", re.I),               "hello listeners"),
    (re.compile(r"\bnamaskar\b", re.I),                  "namaskar (formal)"),
    (re.compile(r"\bshrotaon\b", re.I),                  "shrotaon (formal)"),
    (re.compile(r"\bpadharo\b", re.I),                   "padharo (formal)"),
    (re.compile(r"we will now play", re.I),              "we will now play"),
    (re.compile(r"\bstay tuned\b", re.I),                "stay tuned"),
    (re.compile(r"welcome to bigfm", re.I),              "welcome to bigfm (formal)"),
]


def detect_banned_phrases(script: str) -> List[str]:
    hits = []
    for pat, label in BANNED_PATTERNS:
        if pat.search(script):
            hits.append(label)
    return hits


# ===========================================================================
# DUO Naturalness Rewrite (Phase 3.8 Extra A)
# ===========================================================================
# Rewrites each turn of a duo dialog while preserving speaker tags and
# enforcing per-speaker language purity (American=English-heavy, Hindi-native
# =Hindi-heavy, Hinglish=free mix). One OpenAI call for the whole dialog.
# ===========================================================================
DUO_REWRITE_SYSTEM_TEMPLATE = """You are a senior Indian-diaspora radio producer in {market_label}.

Rewrite this Duo-RJ break (two hosts in conversation) into natural radio dialog. STRICT RULES:

1) PRESERVE speaker tags in this EXACT format: [LABEL_A] ...turn 1... [LABEL_B] ...turn 2... etc. Same number of turns. Same speaker order. Do NOT rename labels.

2) PER-SPEAKER ACCENT PURITY (CRITICAL):
{speaker_purity_block}

3) NATURALNESS:
   - 2-4 short sentences per turn, conversational pacing
   - Real radio energy, not a press release
   - Include `[smiles]`, `[laughs]`, `[pause]`, `[warm]`, `[upbeat]`, `[hyped]` audio tags inline where they fit
   - NEVER say "main aapka RJ hoon" / "hello listeners" / "namaskar shrotaon"
   - Hosts can interrupt each other naturally — short interjections like "haan haan", "totally", "for real" are OK
   - Pull from phrase inspiration when natural:
{phrase_inspiration}

4) TIMING: total dialog should run ~{target_seconds} seconds when spoken (~{word_budget} words combined).

5) DO NOT add explanations. Return ONLY the rewritten dialog with speaker tags.

PRONUNCIATION (write as-is, TTS handles it): FunAsia, Thakkar, Jay Bhavani, Frisco, Plano, Irving, Karama, Diwali, Eid, Navratri, Shah Rukh Khan, AP Dhillon, Arijit Singh."""


def _format_speaker_purity(host_a_label: str, host_a_accent: str,
                            host_b_label: str, host_b_accent: str) -> str:
    rule_map = {
        "american":  "→ 90% English with light radio flavor words ('yaar', 'boss', 'dosto'). NEVER speak Hindi sentences.",
        "english":   "→ 90% English. Light flavor words allowed.",
        "hindi-native": "→ 90%+ Hindi (Roman script). Only English brand/place names.",
        "hindi_native": "→ 90%+ Hindi (Roman script). Only English brand/place names.",
        "hindi":     "→ 80% Hindi (Roman script), 20% English allowed.",
        "hinglish":  "→ Mixed Hindi-English code-switching, natural diaspora flow.",
        "punjabi":   "→ Punjabi-flavored Hindi with words like 'paaji', 'shava-shava', 'balle'.",
        "devotional": "→ Hindi-Sanskrit warm baritone, slow pace, devotional vocabulary.",
    }
    a_rule = rule_map.get((host_a_accent or "hinglish").lower(), rule_map["hinglish"])
    b_rule = rule_map.get((host_b_accent or "hinglish").lower(), rule_map["hinglish"])
    return (
        f"   [{host_a_label}] is a '{host_a_accent}' voice {a_rule}\n"
        f"   [{host_b_label}] is a '{host_b_accent}' voice {b_rule}\n"
        f"   The two speakers can be in DIFFERENT languages — that's natural code-switching between hosts."
    )


async def radio_naturalness_rewrite_duo(
    draft_dialog: str,
    *,
    host_a_label: str, host_a_accent: str,
    host_b_label: str, host_b_accent: str,
    market: str,
    phrase_inspiration: List[str],
    target_seconds: int = 24,
) -> str:
    """Stage 2 rewrite for duo dialogs. Returns rewritten dialog preserving
    [LABEL_A] / [LABEL_B] structure. On any error, returns the draft unchanged."""
    if not OPENAI_API_KEY:
        return draft_dialog
    if not draft_dialog or not draft_dialog.strip():
        return draft_dialog

    market_label = _market_display(market)
    word_budget = int(target_seconds * 2.5)
    inspiration_block = "\n".join(f"     • {p}" for p in (phrase_inspiration or [])[:6]) if phrase_inspiration else "     (write fresh)"
    speaker_purity = _format_speaker_purity(host_a_label, host_a_accent, host_b_label, host_b_accent)

    system_prompt = DUO_REWRITE_SYSTEM_TEMPLATE.format(
        market_label=market_label,
        speaker_purity_block=speaker_purity,
        phrase_inspiration=inspiration_block,
        word_budget=word_budget,
        target_seconds=target_seconds,
    )
    user_prompt = (
        f"REWRITE THIS DUO DIALOG into natural radio banter following ALL rules above. "
        f"PRESERVE speaker tags [{host_a_label}] / [{host_b_label}] exactly.\n\n"
        f"DRAFT:\n{draft_dialog}\n\n"
        f"Return only the rewritten dialog with the same speaker tags."
    )
    try:
        rewritten = await _run_chat(
            system=system_prompt, user=user_prompt,
            temperature=_TEMP_REWRITE, max_tokens=420,
        )
    except Exception:
        return draft_dialog
    rewritten = rewritten.strip()
    # Sanity check — the rewrite MUST contain both speaker labels. If not,
    # bail out and keep the original draft so we don't break the audio pipeline.
    if f"[{host_a_label}]" not in rewritten or f"[{host_b_label}]" not in rewritten:
        return draft_dialog
    return rewritten
