"""RJ script generation (OpenAI) + ElevenLabs TTS synthesis."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import HTTPException
from openai import OpenAI

from audio_pipeline import concat_with_gaps, new_uuid_filename, truncate_audio
from core.config import (
    DEFAULT_ENERGY, ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID, ELEVEN_OUTPUT_FORMAT,
    ELEVENLABS_API_KEY, MAX_RJ_SECONDS, OPENAI_API_KEY, RJ_DIR,
    RJ_RESHORTEN_THRESHOLD, SPEECH_WORDS_PER_SEC, VOICE_SETTINGS_BY_ENERGY,
    make_openai_client,
)
from services.voices import DEFAULT_VOICE_KEY, RJ_VOICES

logger = logging.getLogger("bigfm.rj")

openai_client = make_openai_client()


HINGLISH_SYSTEM_PROMPT = """You are writing scripts for an ElevenLabs eleven_v3 voice on FUUSIC. The voice can render emotion ONLY if you tag it. Untagged text = monotone. ALWAYS tag your output.

OUTPUT FORMAT — use these inline tags liberally:
- [excited] [hyped] [shouts] for high-energy moments and opening hooks
- [soft] [whispers] [warm] for chill/intimate moments
- [laughs] [chuckles] for natural humor (sparingly, once per script max)
- [pause] or "..." for breath
- ALL CAPS on the single most important word per sentence (the engine renders louder)
- Use !! or !!! for explosive endings
- Tag every script with at least 3 emotion markers and at least 1 ALL CAPS word
- Match the tag intensity to the next song's energy_level (chill / medium / high / party)
- Never explain a tag — just use it inline
- Keep total spoken length 15-25 seconds (40-65 words excluding tag markers)
- Mention "FUUSIC" at least once. Do NOT add any city tagline — just say "FUUSIC".

COLLOQUIAL RULES:
- Mix natural Mumbai/Delhi spoken Hinglish. ~60% English + 40% Hindi connectors. Hindi in Roman script.
- You MAY reference the listener's city when given in context (e.g. food, commute, weather), but NEVER bake a city into the FUUSIC brand tagline. The brand is "FUUSIC", full stop.
- Never reveal the upcoming song's title or artist — only mood/vibe/energy hints.
- Always reference the previous song's mood briefly, then transition into the next energy.
- Vary sign-offs: "FUUSIC, dil se" / "Music chalega non-stop" / "Aap sun rahe ho FUUSIC" / "Stay locked in yaar".
- No stage directions in brackets OTHER than the tag list above. No emojis."""

DUO_HINGLISH_SYSTEM_PROMPT = """You are scripting a Hinglish radio banter between TWO co-hosts on FUUSIC. Output is a tagged dialogue between exactly two speakers.

The user will tell you which two hosts to use as HOST_A and HOST_B. Hosts available:
- VEER: smooth late-night charm, late-30s, Mumbai-origin, lives in Bur Dubai. Witty, slightly sarcastic, loves film references.
- MONIKA: warm Delhi-origin, mid-20s, lives in JLT. High-energy, bubbly, foodie, the heart of the duo.
- CHARLIE: party DJ, 30s, Indo-Punjabi, club-MC energy. Always hyped, calls everyone "boss"/"yaar"/"bro".
- RIYA: DJ Riya, female club MC, late-20s, JBR loft, English-heavy, hyped.
- ANAND: Pandit Anand, 55+ male, wisdom keeper, devotional broadcaster, slow warm baritone.
- GURPREET: Punjabi specialist male, Karama dhaba energy, hearty and loud.
- AARTI: bubbly morning-show female, Delhi-origin, fast peppy enthusiastic.
- KISHORE: Kishore Da, classic broadcaster, smooth drawl, late-80s AIR nostalgia.
- SIMRAN: Punjabi female co-host, playful, warm, teases Gurpreet.

OUTPUT FORMAT — use this EXACT structure (one turn per line, starting with the speaker tag in square brackets):
[HOST_A_LABEL] [warm] some line with [tags] inline...
[HOST_B_LABEL] [excited] her reply with [tags] inline!!
[HOST_A_LABEL] [chuckles] ...
[HOST_B_LABEL] [hyped] ...

Rules:
- Use ONLY the two speaker tags I tell you. Never invent others.
- 4 to 6 turns total. Alternate speakers strictly.
- Each turn is 1-2 SHORT sentences (6-16 words). NEVER write a paragraph from one speaker.
- Real Hinglish banter — they tease each other, agree, disagree playfully, react to the previous song, hype the next song's mood.
- Drop authentic Dubai-Indian references (Karama dhabas, JLT brunch, Sheikh Zayed traffic, karak chai, Friday brunch, Global Village, Sharjah commute).
- Match energy of the next song.
- Always end with a hook into the next song mood — never reveal title/artist.
- Pronunciation dictionary already covers Dubai/Karama/JLT/FUUSIC — write them normally.
- Use [tags] every turn. ALL-CAPS one word per turn for emphasis.

TOTAL spoken length: 25-40 seconds (50-90 words across all turns combined). DO NOT exceed 42 seconds."""


def estimate_speech_seconds(script: str) -> float:
    cleaned = re.sub(r"\[[^\]]+\]", " ", script)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = max(1, len(cleaned.split()))
    return words / SPEECH_WORDS_PER_SEC


def _location_block(location_context: Optional[dict]) -> str:
    """Phase 39 Session 6 — persona × location greeting weaver.
    Returns a LOCATION CONTEXT block the persona can naturally weave into
    the greeting. Empty string when no patterns detected.

    HARD RULE: never include clock times — only buckets (morning / lunch /
    evening / night). The Session 4 'no clock time' system-prompt rule
    carries through and is regex-asserted in tests.
    """
    if not location_context:
        return ""
    parts = []
    mc = location_context.get("morning_commute")
    if mc:
        parts.append(f"- The listener regularly heads to '{mc['label']}' "
                     f"({mc['category']}) in the morning.")
    bv = location_context.get("recent_business_visit")
    if bv:
        parts.append(f"- They were recently at '{bv['label']}' "
                     f"({bv['category']}) in the {bv['time_bucket']} bucket.")
    bucket = location_context.get("current_time_bucket")
    if bucket:
        parts.append(f"- Current time bucket: {bucket} "
                     f"(NEVER name a clock time — use this bucket only).")
    if not parts:
        return ""
    return ("\n\nLOCATION CONTEXT — weave at most ONE of these into the "
            "greeting naturally, in the persona's voice (e.g. 'Heading out "
            "to the office?' or 'Just like that Karak Cafe stop yesterday'). "
            "Do NOT list them all. Do NOT mention coordinates. Do NOT name "
            "a clock time.\n" + "\n".join(parts))


def _solo_user_prompt(prev, nxt, ctx, rj_persona, channel_name=None,
                      shorten=False, location_context: Optional[dict] = None) -> str:
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    nxt_mood = nxt.get("mood") or "uplifting"
    if prev:
        prev_energy = prev.get("energy_level", DEFAULT_ENERGY)
        prev_mood = prev.get("mood") or "uplifting"
        prev_line = (f"Previous song just ended: '{prev['title']}' by {prev['artist']} "
                     f"(energy={prev_energy}, mood={prev_mood}).")
        transition = f"Transition: {prev_energy} → {nxt_energy}."
    else:
        prev_line = "This is the opening of the show — no previous song yet."
        transition = f"Opening energy: {nxt_energy}."
    ctx_bits = []
    if ctx.time_of_day:
        ctx_bits.append(f"time of day: {ctx.time_of_day}")
    if ctx.weather_hint:
        ctx_bits.append(f"weather: {ctx.weather_hint}")
    ctx_bits.append(f"city: {ctx.city or 'Dubai'}")
    if channel_name:
        ctx_bits.append(f"show: {channel_name}")
    shorter = " BE SHORTER — keep total spoken length under 30 seconds (40-55 words max)." if shorten else ""
    base = (
        f"You are speaking as: {rj_persona}. "
        f"{prev_line} "
        f"Next song coming up (DO NOT name it): '{nxt['title']}' by {nxt['artist']} "
        f"(energy={nxt_energy}, mood={nxt_mood}). "
        f"{transition} Context — {'; '.join(ctx_bits)}.{shorter} "
        f"Write the Hinglish on-air bridge now, MATCHING the {nxt_energy} energy of the next song."
    )
    return base + _location_block(location_context)


def generate_rj_script_solo(prev, nxt, ctx, voice_key, channel_name=None,
                            location_context: Optional[dict] = None) -> str:
    if not openai_client:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    persona = RJ_VOICES.get(voice_key, RJ_VOICES[DEFAULT_VOICE_KEY])["persona"]
    last = ""
    for attempt in (0, 1):
        user_p = _solo_user_prompt(prev, nxt, ctx, persona, channel_name,
                                   shorten=(attempt == 1),
                                   location_context=location_context)
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": HINGLISH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_p},
                ],
                temperature=0.9, max_tokens=220,
            )
            script = (resp.choices[0].message.content or "").strip()
            script = re.sub(r'^["\']|["\']$', "", script).strip()
            last = script
            if estimate_speech_seconds(script) <= RJ_RESHORTEN_THRESHOLD or attempt == 1:
                return script
        except Exception as e:
            raise HTTPException(502, f"OpenAI error: {e}")
    return last


def _duo_user_prompt(prev, nxt, ctx, host_a, host_b, channel_name=None, shorten=False) -> str:
    nxt_energy = nxt.get("energy_level", DEFAULT_ENERGY)
    nxt_mood = nxt.get("mood") or "uplifting"
    if prev:
        prev_line = (f"Previous song: '{prev['title']}' by {prev['artist']} "
                     f"(energy={prev.get('energy_level', DEFAULT_ENERGY)}, "
                     f"mood={prev.get('mood') or 'uplifting'}).")
    else:
        prev_line = "Opening of the show — no previous song yet."
    ctx_bits = []
    if ctx.time_of_day:
        ctx_bits.append(f"time of day: {ctx.time_of_day}")
    if ctx.weather_hint:
        ctx_bits.append(f"weather: {ctx.weather_hint}")
    ctx_bits.append(f"city: {ctx.city or 'Dubai'}")
    if channel_name:
        ctx_bits.append(f"show: {channel_name}")
    shorter = " BE SHORTER — total under 28 seconds (50-70 words across ALL turns)." if shorten else ""
    return (
        f"Hosts: HOST_A = [{host_a['duo_label']}] ({host_a['duo_blurb']}). "
        f"HOST_B = [{host_b['duo_label']}] ({host_b['duo_blurb']}). "
        f"Use ONLY the speaker tags [{host_a['duo_label']}] and [{host_b['duo_label']}]. "
        f"{prev_line} Next song coming up (DO NOT name it): '{nxt['title']}' by {nxt['artist']} "
        f"(energy={nxt_energy}, mood={nxt_mood}). Context — {'; '.join(ctx_bits)}.{shorter} "
        f"Write the Hinglish co-host banter now, MATCHING the {nxt_energy} energy. "
        f"4-6 alternating turns starting with [{host_a['duo_label']}]."
    )


def generate_duo_script(prev, nxt, ctx, host_a_key, host_b_key, channel_name=None) -> str:
    if not openai_client:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    host_a = RJ_VOICES[host_a_key]
    host_b = RJ_VOICES[host_b_key]
    last = ""
    for attempt in (0, 1):
        user_p = _duo_user_prompt(prev, nxt, ctx, host_a, host_b, channel_name, shorten=(attempt == 1))
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": DUO_HINGLISH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_p},
                ],
                temperature=0.9, max_tokens=420,
            )
            script = (resp.choices[0].message.content or "").strip()
            last = script
            if estimate_speech_seconds(script) <= RJ_RESHORTEN_THRESHOLD or attempt == 1:
                return script
        except Exception as e:
            raise HTTPException(502, f"OpenAI error: {e}")
    return last


def parse_duo_script(script: str, host_a_key: str, host_b_key: str) -> List[Tuple[str, str]]:
    label_to_key = {
        RJ_VOICES[host_a_key]["duo_label"]: host_a_key,
        RJ_VOICES[host_b_key]["duo_label"]: host_b_key,
    }
    pattern = re.compile(r"^\s*\[([A-Z]+)\]\s*(.*)$")
    turns: List[Tuple[str, str]] = []
    for raw in script.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = pattern.match(line)
        if m and m.group(1) in label_to_key:
            turns.append((label_to_key[m.group(1)], m.group(2).strip()))
        elif turns:
            turns[-1] = (turns[-1][0], (turns[-1][1] + " " + line.strip()).strip())
    return [(vk, t) for vk, t in turns if t.strip()]


def synthesize_elevenlabs_raw(script: str, voice_id: str, energy: str) -> Path:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")
    from elevenlabs import ElevenLabs, VoiceSettings
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    settings_dict = VOICE_SETTINGS_BY_ENERGY.get(energy, VOICE_SETTINGS_BY_ENERGY[DEFAULT_ENERGY])
    voice_settings = VoiceSettings(**settings_dict)
    try:
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id, model_id=ELEVEN_MODEL_ID, text=script,
            output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
        )
    except Exception:
        logger.warning("eleven_v3 failed — falling back to multilingual_v2")
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id, model_id=ELEVEN_FALLBACK_MODEL, text=script,
            output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=voice_settings,
        )
    out_path = RJ_DIR / new_uuid_filename("mp3")
    with open(out_path, "wb") as f:
        for chunk in audio_iter:
            if chunk:
                f.write(chunk)
    return out_path


def synthesize_solo(script: str, voice_id: str, energy: str) -> Path:
    out_path = synthesize_elevenlabs_raw(script, voice_id, energy)
    try:
        if truncate_audio(out_path, MAX_RJ_SECONDS, fade_out_ms=200):
            logger.info(f"Solo RJ truncated to {MAX_RJ_SECONDS}s")
    except Exception as e:
        logger.warning(f"Solo RJ truncation failed: {e}")
    return out_path


def synthesize_duo_banter(turns: List[Tuple[str, str]], energy: str) -> Path:
    if not turns:
        raise HTTPException(500, "duo script had no parseable turns")
    turn_paths: List[Path] = []
    for voice_key, text in turns:
        voice_id = RJ_VOICES[voice_key]["voice_id"]
        turn_paths.append(synthesize_elevenlabs_raw(text, voice_id, energy))
    out_path = RJ_DIR / new_uuid_filename("mp3")
    concat_with_gaps([str(p) for p in turn_paths], str(out_path), gap_ms=220)
    try:
        if truncate_audio(out_path, MAX_RJ_SECONDS, fade_out_ms=250):
            logger.info(f"Duo RJ truncated to {MAX_RJ_SECONDS}s")
    except Exception as e:
        logger.warning(f"Duo RJ truncation failed: {e}")
    for p in turn_paths:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    return out_path
