"""Phase 4.5 — AI sponsor read generation.

Reuses the Phase 3.7 two-stage pipeline:
  Stage 1: OpenAI generates a sponsor-read draft from a brief
  Stage 2: Naturalness rewrite (radio-style)
  Stage 3: ElevenLabs TTS with selected voice
  Stage 4: loudnorm to -14 LUFS
  Stage 5: persist as ad_creative + return creative_id

Public: generate_sponsor_read(brief, voice_key, duration_sec, business) → creative_id
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.config import (
    ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID, ELEVEN_OUTPUT_FORMAT,
    ELEVENLABS_API_KEY, STORAGE_DIR,
)

logger = logging.getLogger("bigfm.ads.sponsor_read")

ADS_DIR = STORAGE_DIR / "ads"
ADS_DIR.mkdir(parents=True, exist_ok=True)


SPONSOR_READ_SYSTEM = """You write radio sponsor reads for RadioLife {market_label}.

OUTPUT FORMAT: a single block of natural Hinglish radio voice text (no headings, no labels).

STYLE RULES:
- {duration_sec}-second read (~{word_budget} words)
- Tone: {tone}
- Mention the business name TWICE, the offer ONCE, end with the business name
- Include a clear call-to-action that references tapping the Action Card on the RadioLife player
- Use ElevenLabs v3 audio tags inline where natural: [warm], [excited], [hyped], [smiles], [pause]
- NO formal Hindi opener (no "namaskar", "main aapka RJ hoon", "hello listeners")
- Natural radio voice — like a human host endorsing the business, not reading a brochure

PRONUNCIATION HINTS: spell brand and place names exactly so the TTS handles them:
{pronunciation_block}
"""


SPONSOR_READ_USER_TEMPLATE = """Write a sponsor read.

BUSINESS: {business_name}
OFFER / KEY MESSAGE: {brief}
ACTION CARD LABELS: {action_labels}
DURATION: {duration_sec} seconds (~{word_budget} words)

Return ONLY the sponsor read. No explanations."""


def _word_budget(duration_sec: int) -> int:
    return int(duration_sec * 2.5)


def _pronunciation_block(business: dict) -> str:
    addr = (business or {}).get("address") or ""
    name = (business or {}).get("name") or ""
    return f"- BUSINESS NAME: {name}\n- ADDRESS: {addr}\n- Common: FunAsia, Thakkar, Jay Bhavani, Frisco, Plano, Irving, Karama, JLT, Diwali, Eid, Navratri"


async def _draft_sponsor_read(*, brief: str, business_name: str, market: str,
                                tone: str, duration_sec: int,
                                action_labels: list, business: dict) -> str:
    from services.script_pipeline import _run_chat
    market_label = "Dubai" if market == "dubai" else "DFW"
    sys = SPONSOR_READ_SYSTEM.format(
        market_label=market_label, duration_sec=duration_sec,
        word_budget=_word_budget(duration_sec), tone=tone,
        pronunciation_block=_pronunciation_block(business),
    )
    user = SPONSOR_READ_USER_TEMPLATE.format(
        business_name=business_name, brief=brief,
        action_labels=", ".join(action_labels) or "Action Card",
        duration_sec=duration_sec, word_budget=_word_budget(duration_sec),
    )
    out = await _run_chat(system=sys, user=user, temperature=0.78, max_tokens=320)
    return out.strip()


def _generate_ad_tts(creative_id: str, script: str, voice_key: str,
                      max_sec: float) -> bool:
    """Synchronous ElevenLabs TTS + loudnorm. Reuses imaging asset machinery."""
    out_path = ADS_DIR / f"{creative_id}.mp3"
    if not ELEVENLABS_API_KEY:
        return False
    try:
        from services.imaging_assets import _voice_id_for, IMAGING_VOICE_SETTINGS
        from services.loudness import normalize_to_lufs
        from elevenlabs import ElevenLabs, VoiceSettings
        from audio_pipeline import truncate_audio
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        vs = VoiceSettings(stability=0.30, similarity_boost=0.72, style=0.52, use_speaker_boost=True)
        raw_path = out_path.with_name(out_path.stem + ".raw.mp3")
        try:
            it = client.text_to_speech.convert(
                voice_id=_voice_id_for(voice_key), model_id=ELEVEN_MODEL_ID, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        except Exception:
            it = client.text_to_speech.convert(
                voice_id=_voice_id_for(voice_key), model_id=ELEVEN_FALLBACK_MODEL, text=script,
                output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs,
            )
        with open(raw_path, "wb") as f:
            for chunk in it:
                if chunk: f.write(chunk)
        try: truncate_audio(raw_path, max_sec + 0.4, fade_out_ms=160)
        except Exception: pass
        normalize_to_lufs(raw_path, out_path, target_i=-14.0, target_tp=-1.0)
        try: raw_path.unlink(missing_ok=True)
        except Exception: pass
        return out_path.exists() and out_path.stat().st_size > 4_000
    except Exception as e:
        logger.warning(f"sponsor read TTS failed: {e}")
        return False


async def generate_sponsor_read(
    db,
    *, advertiser_id: str, business_id: str, brief: str,
    voice_key: str, duration_sec: int = 20, tone: str = "warm-energetic",
    action_labels: Optional[list] = None,
) -> dict:
    """End-to-end AI sponsor-read pipeline. Returns:
      {creative_id, audio_url, transcript, duration_sec}
    """
    if duration_sec not in (15, 20, 30): duration_sec = 20
    biz = await db.businesses.find_one({"business_id": business_id}) or {}
    market = biz.get("market") or "dubai"

    # Stage 1: draft
    draft = await _draft_sponsor_read(
        brief=brief, business_name=biz.get("name") or "this business",
        market=market, tone=tone, duration_sec=duration_sec,
        action_labels=action_labels or [], business=biz,
    )

    # Stage 2: naturalness rewrite (reuse existing radio_naturalness_rewrite)
    try:
        from services.personality_profiles import profile_by_slug_sync
        from services.script_pipeline import radio_naturalness_rewrite
        profile = profile_by_slug_sync("evening_drive") or {}
        rewritten = await radio_naturalness_rewrite(
            draft, profile=profile, market=market, phrase_inspiration=[],
        ) or draft
    except Exception as e:
        logger.debug(f"naturalness rewrite failed for sponsor read: {e}")
        rewritten = draft

    # Stage 3+4: TTS + loudnorm
    creative_id = f"crv_ai_{uuid.uuid4().hex[:12]}"
    import asyncio
    ok = await asyncio.to_thread(_generate_ad_tts, creative_id, rewritten,
                                    voice_key, float(duration_sec))
    if not ok:
        raise RuntimeError("TTS generation failed")
    audio_path = ADS_DIR / f"{creative_id}.mp3"
    try:
        from audio_pipeline import ffprobe_duration
        dur_actual = float(ffprobe_duration(audio_path) or duration_sec)
    except Exception:
        dur_actual = duration_sec

    # Stage 5: persist as ad_creative
    now = datetime.now(timezone.utc)
    preview_url = f"/api/ads/creative/{creative_id}/preview"
    await db.ad_creatives.insert_one({
        "_id": creative_id, "creative_id": creative_id,
        "advertiser_id": advertiser_id, "campaign_id": None,
        "creative_type": "audio_ad", "duration_sec": dur_actual,
        "audio_path": str(audio_path),
        "audio_url": preview_url,
        "transcript": rewritten,
        "initial_draft": draft,
        "voice_key": voice_key, "voice_provider": "elevenlabs",
        "is_ai_generated": True,
        "approval_status": "pending",  # admin re-approves AI creatives
        "active": False,                # active when campaign goes active
        "created_at": now, "updated_at": now,
    })
    return {"creative_id": creative_id,
            "audio_url": preview_url,
            "transcript": rewritten, "duration_sec": dur_actual,
            "draft": draft}
