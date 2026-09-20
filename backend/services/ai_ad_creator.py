"""Phase 18b — AI Ad Creator pipeline.

Generates a ready-to-air 15s/30s radio ad in 4 stages:
  A. script   → OpenAI gpt-4o-mini  (market-lexicon-aware, tone-aware)
  B. voice   → ElevenLabs eleven_turbo_v2_5  (with OpenAI TTS fallback)
  C. image   → Gemini Nano Banana (gemini-2.5-flash-image)
  D. safety → Phase 18a creative_safety classifier

Plus E. VAST 4.0 wrapper (stored on the creative for Phase 18d programmatic).

All stages emit `advertiser_creative_generated_stage` events and the final
save emits `advertiser_creative_uploaded` with `source: "ai_generated"`.
"""
from __future__ import annotations
import asyncio
import base64
import io
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as _xml_escape

from openai import OpenAI

from core.config import (ELEVEN_FALLBACK_MODEL, ELEVEN_MODEL_ID,
                                          ELEVEN_OUTPUT_FORMAT, ELEVENLABS_API_KEY,
                                          OPENAI_API_KEY)
from services.market_lexicon import get_lexicon
from services.creative_safety import classify_creative

logger = logging.getLogger("bigfm.ai_ad_creator")

# ─── Public voice catalog (neutral names — never expose vendor voice_id)
AI_VOICE_CATALOG = [
    {"id": "maya",  "label": "Maya",  "persona": "warm, friendly female",
      "voice_key": "monika_dubai"},
    {"id": "aiden", "label": "Aiden", "persona": "smooth, charming male",
      "voice_key": "veer_dubai"},
    {"id": "layla", "label": "Layla", "persona": "peppy, energetic female",
      "voice_key": "aarti_morning"},
    {"id": "karan", "label": "Karan", "persona": "bold, energetic male",
      "voice_key": "kabir_hindi"},
    {"id": "aarav", "label": "Aarav", "persona": "natural conversational male",
      "voice_key": "raghav_hindi"},
]
_VOICE_BY_ID = {v["id"]: v for v in AI_VOICE_CATALOG}

# Storage
STORAGE_ROOT = Path("/app/backend/static/ad_creatives")
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


# ────────────────────────────────────────────────────────────────────
# Stage A — script
# ────────────────────────────────────────────────────────────────────
_SCRIPT_SYS = """You write 15-30 second radio ad scripts for FUUSIC.
Rules:
- Match the TARGET LENGTH within ±10%% (≈2.5 words/sec).
- Mention the business name EXACTLY ONCE.
- End with a clear single-sentence CTA.
- Stay on-market: only use brands/landmarks/food appropriate to the MARKET.
- Tone must match: friendly / energetic / luxurious / chill / urgent.
- No profanity, gambling, alcohol, political, medical claims, or financial guarantees.
- Output ONLY the script text. No stage directions, no labels, no quotes."""


def generate_script(*, business: str, description: str, tone: str,
                                  audio_length_sec: int, market: str,
                                  keywords: Optional[list[str]] = None) -> dict:
    """Returns {"script": str, "transcript": str, "model": str, "latency_ms": int}.
    Raises RuntimeError on hard failure."""
    if not _openai:
        raise RuntimeError("OPENAI_API_KEY not configured")
    lex = get_lexicon(market)
    local_bits = []
    if lex.get("food"):
        local_bits.append(f"local food refs (use sparingly): {', '.join(lex['food'][:6])}")
    if lex.get("landmarks"):
        local_bits.append(f"local landmarks (do NOT name unless relevant): {', '.join(lex['landmarks'][:5])}")
    locality = " | ".join(local_bits) or "no specific local lexicon"
    kw = (", ".join((keywords or [])[:3])) or "—"
    user_prompt = (
        f"BUSINESS: {business}\n"
        f"OFFER: {description}\n"
        f"TONE: {tone}\n"
        f"TARGET LENGTH: {audio_length_sec} seconds (~{int(audio_length_sec*2.5)} words)\n"
        f"MARKET: {market}  |  {locality}\n"
        f"HARD-INCLUDE KEYWORDS (only if natural): {kw}\n\n"
        f"Write the ad script now."
    )
    t0 = time.time()
    resp = _openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": _SCRIPT_SYS},
                       {"role": "user",   "content": user_prompt}],
        temperature=0.85, max_tokens=240,
    )
    txt = (resp.choices[0].message.content or "").strip().strip('"').strip()
    return {"script": txt, "transcript": txt, "model": "gpt-4o-mini",
              "latency_ms": int((time.time() - t0) * 1000)}


# ────────────────────────────────────────────────────────────────────
# Stage B — voice synthesis
# ────────────────────────────────────────────────────────────────────
def synthesize_voice(*, script: str, voice_id: str,
                                    creative_id: str,
                                    max_sec: float = 32.0) -> dict:
    """Synth voice; returns {"audio_path": str, "audio_url": str,
    "audio_source": "elevenlabs"|"openai_fallback", "latency_ms": int,
    "duration_sec": float}. Raises RuntimeError if both providers fail."""
    voice = _VOICE_BY_ID.get(voice_id)
    if not voice:
        raise RuntimeError(f"unknown voice id: {voice_id}")
    out_path = STORAGE_ROOT / f"{creative_id}.mp3"
    t0 = time.time()
    # Provider A: ElevenLabs
    if ELEVENLABS_API_KEY:
        try:
            from elevenlabs import ElevenLabs, VoiceSettings
            from services.imaging_assets import _voice_id_for
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            vs = VoiceSettings(stability=0.32, similarity_boost=0.7,
                                          style=0.55, use_speaker_boost=True)
            try:
                audio_iter = client.text_to_speech.convert(
                    voice_id=_voice_id_for(voice["voice_key"]),
                    model_id=ELEVEN_MODEL_ID, text=script,
                    output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs)
            except Exception:
                audio_iter = client.text_to_speech.convert(
                    voice_id=_voice_id_for(voice["voice_key"]),
                    model_id=ELEVEN_FALLBACK_MODEL, text=script,
                    output_format=ELEVEN_OUTPUT_FORMAT, voice_settings=vs)
            with open(out_path, "wb") as f:
                for chunk in audio_iter:
                    if chunk:
                        f.write(chunk)
            if out_path.exists() and out_path.stat().st_size > 4_000:
                duration = _probe_duration(out_path) or float(max_sec)
                return {"audio_path": str(out_path),
                          "audio_url": f"/api/static/ad_creatives/{out_path.name}",
                          "audio_source": "elevenlabs",
                          "latency_ms":     int((time.time() - t0) * 1000),
                          "duration_sec": duration,
                          "voice_label":   voice["label"]}
        except Exception as e:
            logger.warning("[ai_creator] ElevenLabs failed (%s); trying OpenAI", e)
    # Provider B: OpenAI TTS fallback
    if _openai:
        try:
            tts = _openai.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="nova" if "female" in voice["persona"] else "onyx",
                input=script, response_format="mp3")
            tts.stream_to_file(out_path)
            duration = _probe_duration(out_path) or float(max_sec)
            return {"audio_path": str(out_path),
                      "audio_url": f"/api/static/ad_creatives/{out_path.name}",
                      "audio_source": "openai_fallback",
                      "latency_ms":     int((time.time() - t0) * 1000),
                      "duration_sec": duration,
                      "voice_label":   voice["label"]}
        except Exception as e:
            logger.error("[ai_creator] OpenAI TTS fallback failed: %s", e)
    raise RuntimeError("both ElevenLabs and OpenAI TTS failed")


def _probe_duration(path: Path) -> Optional[float]:
    """Best-effort duration probe via ffprobe; None if not available."""
    import subprocess, json as _json
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
              "-show_format", str(path)],
            capture_output=True, text=True, timeout=10)
        data = _json.loads(r.stdout or "{}")
        return float(data.get("format", {}).get("duration") or 0) or None
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────
# Stage C — image (Nano Banana)
# ────────────────────────────────────────────────────────────────────
_IMAGE_SYS = "You generate 1024x1024 square poster artwork for radio ad campaigns."


async def generate_image(*, business: str, tagline: str, tone: str,
                                          brand_color: Optional[str],
                                          creative_id: str) -> dict:
    """Returns {"image_url": str|None, "latency_ms": int, "skipped": bool}.
    Never raises; if Nano Banana fails returns skipped=True with image_url=None."""
    t0 = time.time()
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"image_url": None, "latency_ms": 0, "skipped": True,
                  "reason": "EMERGENT_LLM_KEY not set"}
    color = brand_color or "warm gold"
    prompt = (f"Square poster-style brand ad for {business}. "
                  f"Tagline mood: '{tagline}'. {tone.title()} mood. "
                  f"{color} accent palette. Soft texture, hero subject centered, "
                  f"no readable text from the model — text overlay added in post. "
                  f"1024x1024, high quality, no watermark.")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = (LlmChat(api_key=api_key,
                              session_id=f"ai-ad-{creative_id}",
                              system_message=_IMAGE_SYS)
                  .with_model("gemini", "gemini-2.5-flash-image")
                  .with_params(modalities=["image", "text"]))
        _txt, images = await chat.send_message_multimodal_response(
            UserMessage(text=prompt))
        if not images:
            return {"image_url": None,
                      "latency_ms": int((time.time() - t0) * 1000),
                      "skipped": True, "reason": "no image returned"}
        raw = base64.b64decode(images[0]["data"])
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            out_path = STORAGE_ROOT / f"{creative_id}.webp"
            img.save(out_path, format="WEBP", quality=82, method=6)
        except Exception:
            out_path = STORAGE_ROOT / f"{creative_id}.png"
            out_path.write_bytes(raw)
        return {"image_url": f"/api/static/ad_creatives/{out_path.name}",
                  "latency_ms": int((time.time() - t0) * 1000),
                  "skipped": False}
    except Exception as e:
        logger.warning("[ai_creator] Nano Banana failed: %s", e)
        return {"image_url": None,
                  "latency_ms": int((time.time() - t0) * 1000),
                  "skipped": True, "reason": str(e)[:120]}


# ────────────────────────────────────────────────────────────────────
# Stage E — VAST 4.0 wrapper
# ────────────────────────────────────────────────────────────────────
def build_vast_xml(*, creative_id: str, audio_url: str, duration_sec: float,
                              click_url: Optional[str], title: str,
                              advertiser_name: str) -> str:
    """Generate a minimal VAST 4.0 audio-ad wrapper.  Stored on the creative
    doc; not yet served programmatically (that's Phase 18d)."""
    dur = max(1, int(round(duration_sec or 15)))
    h = dur // 3600
    m = (dur % 3600) // 60
    s = dur % 60
    duration_str = f"{h:02d}:{m:02d}:{s:02d}"
    public_base = (os.environ.get("PUBLIC_BACKEND_URL")
                              or "https://mobile-games-v2.preview.emergentagent.com")
    full_audio = audio_url if audio_url.startswith("http") else f"{public_base}{audio_url}"
    click = click_url or full_audio
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<VAST version="4.0">
  <Ad id="{_xml_escape(creative_id)}">
    <InLine>
      <AdSystem version="1.0">FUUSIC</AdSystem>
      <AdTitle><![CDATA[{title}]]></AdTitle>
      <Advertiser><![CDATA[{advertiser_name}]]></Advertiser>
      <Creatives>
        <Creative id="{_xml_escape(creative_id)}" sequence="1">
          <Linear>
            <Duration>{duration_str}</Duration>
            <MediaFiles>
              <MediaFile delivery="progressive" type="audio/mpeg" bitrate="128"
                                  width="0" height="0">
                <![CDATA[{full_audio}]]>
              </MediaFile>
            </MediaFiles>
            <VideoClicks>
              <ClickThrough><![CDATA[{click}]]></ClickThrough>
            </VideoClicks>
          </Linear>
        </Creative>
      </Creatives>
    </InLine>
  </Ad>
</VAST>"""
    return xml.strip()


# ────────────────────────────────────────────────────────────────────
# Full pipeline
# ────────────────────────────────────────────────────────────────────
async def run_pipeline(*, db, advertiser: dict, business: str,
                                      description: str, tone: str,
                                      audio_length_sec: int, voice_id: str,
                                      brand_color: Optional[str] = None,
                                      market: Optional[str] = None,
                                      click_url: Optional[str] = None,
                                      keywords: Optional[list[str]] = None,
                                      include_image: bool = True) -> dict:
    """Runs script → voice → image → safety in sequence, builds VAST,
    emits per-stage telemetry, and returns the full preview payload.
    Does NOT persist to ad_creatives — caller decides via /save_from_ai.
    """
    from services.telemetry import emit_event
    creative_id = _gen("crt_ai")
    mkt = (market or advertiser.get("market") or "dubai").lower()
    stage_lat: dict[str, int] = {}
    t_total = time.time()

    # A — script
    s_res = generate_script(business=business, description=description,
                                          tone=tone, audio_length_sec=audio_length_sec,
                                          market=mkt, keywords=keywords)
    stage_lat["script"] = s_res["latency_ms"]
    script = s_res["script"]

    # B — voice
    try:
        v_res = synthesize_voice(script=script, voice_id=voice_id,
                                              creative_id=creative_id,
                                              max_sec=audio_length_sec + 6)
    except RuntimeError as e:
        await emit_event(db, name="advertiser_creative_generated_failed",
                                 props={"stage": "voice", "error": str(e)[:200]},
                                 advertiser_id=advertiser["id"])
        raise
    stage_lat["voice"] = v_res["latency_ms"]

    # C — image (best-effort)
    if include_image:
        tagline = description[:50]
        i_res = await generate_image(business=business, tagline=tagline,
                                                      tone=tone, brand_color=brand_color,
                                                      creative_id=creative_id)
        stage_lat["image"] = i_res["latency_ms"]
        image_url = i_res.get("image_url")
        image_skipped = i_res.get("skipped", True)
    else:
        image_url = None
        image_skipped = True

    # D — safety
    t_s = time.time()
    safety = await classify_creative(transcript=script, advertiser_market=mkt)
    stage_lat["safety"] = int((time.time() - t_s) * 1000)
    verdict = (safety or {}).get("verdict", "review")

    # E — VAST
    vast = build_vast_xml(creative_id=creative_id, audio_url=v_res["audio_url"],
                                      duration_sec=v_res["duration_sec"],
                                      click_url=click_url, title=business,
                                      advertiser_name=advertiser.get("name", ""))

    # Telemetry — final stage event (per-stage), main creative_uploaded happens on save.
    await emit_event(db, name="advertiser_creative_generated",
                          props={"verdict": verdict,
                                    "audio_source": v_res["audio_source"],
                                    "audio_length_sec": audio_length_sec,
                                    "image_skipped": image_skipped,
                                    "ai_voice": voice_id, "ai_tone": tone,
                                    "market": mkt,
                                    "stage_latency_ms": stage_lat,
                                    "total_latency_ms": int((time.time() - t_total)*1000),
                                    "issues": (safety or {}).get("issues") or []},
                          advertiser_id=advertiser["id"],
                          creative_id=creative_id)

    return {
        "creative_id":   creative_id,
        "script":          script,
        "transcript":  script,
        "audio_url":     v_res["audio_url"],
        "audio_path":   v_res["audio_path"],
        "audio_source": v_res["audio_source"],
        "duration_sec": v_res["duration_sec"],
        "image_url":     image_url,
        "image_skipped": image_skipped,
        "voice_id":       voice_id,
        "voice_label":  v_res["voice_label"],
        "tone":             tone,
        "audio_length_sec": audio_length_sec,
        "brand_safety_check": safety,
        "verdict":         verdict,
        "vast_xml":     vast,
        "stage_latency_ms":  stage_lat,
        "total_latency_ms":  int((time.time() - t_total) * 1000),
    }
