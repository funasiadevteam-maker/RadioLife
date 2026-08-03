"""Phase 36b — AssemblyAI v2 transcription client (MOCKED-by-default).

When `ASSEMBLYAI_API_KEY` env is unset, `is_live()` returns False and we
return a deterministic fake completed transcript so the entire podcast
pipeline (publish → transcribe → AI metadata → apply → RSS) is testable
end-to-end without any real third-party calls.

When the key is set, the live path POSTs to AssemblyAI v2 and polls
until the transcript reaches `completed`/`error`. Speaker diarization
is enabled via `speaker_labels=true`; auto chapters are OFF (we generate
chapters via OpenAI for tighter editorial control over chapter titles).

Mock payload shape mirrors AssemblyAI's real shape closely so the rest
of the pipeline doesn't branch on `provider`:
    {status, text, utterances:[{speaker,start,end,text}], language_code,
     confidence}
"""
from __future__ import annotations
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("bigfm.assemblyai")

API_BASE = "https://api.assemblyai.com/v2"

# In-process store for mock transcripts so submit→poll round-trip is
# stable across calls within a single backend process.
_MOCK_STORE: dict[str, dict] = {}


def is_live() -> bool:
    return bool((os.environ.get("ASSEMBLYAI_API_KEY") or "").strip())


def _mock_payload(audio_url: str, language_hint: Optional[str],
                            episode_title: str = "") -> dict:
    """Build a deterministic, plausibly-conversational mock transcript so
    the downstream AI metadata generator produces meaningful titles +
    show notes. The text intentionally references the episode title so
    the generator's output is testable."""
    title = (episode_title or "today's show").strip()
    utterances = [
        {"speaker": "A", "start":      0, "end":  3200,
          "text": f"Welcome back to the show. Today we're talking about {title}."},
        {"speaker": "B", "start":  3200, "end":  8100,
          "text": "Thanks for having me. This topic is super relevant right now, "
                      "especially for our listeners in the Gulf and South Asia."},
        {"speaker": "A", "start":  8100, "end": 14500,
          "text": "Let's start with the basics. What should new listeners "
                      "understand first before we get into the nuances?"},
        {"speaker": "B", "start": 14500, "end": 22300,
          "text": "Great question. The first thing is to set realistic expectations "
                      "— there's no overnight magic, it's about consistent small "
                      "decisions stacking up over months."},
        {"speaker": "A", "start": 22300, "end": 28900,
          "text": "That resonates. Can you share a specific framework or "
                      "checklist our listeners can apply this week?"},
        {"speaker": "B", "start": 28900, "end": 38000,
          "text": "Absolutely. I break it down into three pillars: clarity, "
                      "cadence, and accountability. Each one feeds the other."},
        {"speaker": "A", "start": 38000, "end": 44000,
          "text": "Brilliant. Before we wrap, what's one thing you wish you had "
                      "known when you started?"},
        {"speaker": "B", "start": 44000, "end": 52000,
          "text": "Don't wait for perfect — ship version one, learn, then iterate. "
                      "That mindset shift compounds over time."},
    ]
    full_text = " ".join(u["text"] for u in utterances)
    return {
        "status":                "completed",
        "text":                    full_text,
        "utterances":      utterances,
        "language_code": (language_hint or "en"),
        "confidence":      0.93,
        "audio_url":          audio_url,
        "provider_note": "mock (set ASSEMBLYAI_API_KEY to enable live diarization)",
    }


async def submit_transcription(audio_url: str, *,
                                                          language_hint: Optional[str] = None,
                                                          episode_title: str = "",
                                                          episode_id: str = "") -> str:
    """Returns transcript_id. Mock IDs are prefixed `mock_`."""
    if not is_live():
        tid = f"mock_{episode_id or 'na'}"
        _MOCK_STORE[tid] = _mock_payload(audio_url, language_hint, episode_title)
        return tid
    headers = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    payload: dict[str, Any] = {
        "audio_url":             audio_url,
        "speaker_labels":   True,
        "auto_chapters":   False,
        "format_text":         True,
        "punctuate":             True,
    }
    if language_hint:
        payload["language_code"] = language_hint
    else:
        payload["language_detection"] = True
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.post(f"{API_BASE}/transcript",
                                      headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["id"]


async def poll_transcription(transcript_id: str) -> dict:
    """Returns the AssemblyAI-shaped response dict."""
    if transcript_id.startswith("mock_"):
        return _MOCK_STORE.get(transcript_id) or {"status": "error",
                                                                                  "error": "mock_not_found"}
    headers = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(f"{API_BASE}/transcript/{transcript_id}",
                                    headers=headers)
        r.raise_for_status()
        return r.json()


async def cancel_transcription(transcript_id: str) -> None:
    if transcript_id.startswith("mock_"):
        _MOCK_STORE.pop(transcript_id, None)
        return
    headers = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            await cli.delete(f"{API_BASE}/transcript/{transcript_id}",
                                        headers=headers)
    except Exception as e:
        logger.warning("[assemblyai] cancel failed (non-fatal): %s", e)
