"""Phase 42-E2.4 — Direct OpenAI image generation provider.

This is a SECONDARY provider that uses the dedicated `OPENAI_IMAGE_API_KEY`
env var (a user-supplied OpenAI key separate from the shared Emergent LLM
key).  Voice / TTS / text-completion paths continue to use the Emergent
key — only image generation routes through here.

Usage:
    raw_png = await generate_image(
        prompt="Cinematic dark photograph of …",
        size="1024x1024",
        quality="standard",
    )

The function never logs the API key.  Exponential-backoff retry kicks
in on transient OpenAI errors (429 + 5xx).
"""
from __future__ import annotations
import asyncio
import base64
import logging
import os
from typing import Optional

log = logging.getLogger("bigfm.openai_image_provider")

DEFAULT_MODEL = "gpt-image-1"
MAX_RETRIES = 4
BASE_BACKOFF_SEC = 2.0


def _get_key() -> Optional[str]:
    """Return the dedicated image-gen key, with `OPENAI_API_KEY` as a
    legacy fallback so callers don't break if the env hasn't been
    seeded yet."""
    return (os.environ.get("OPENAI_IMAGE_API_KEY")
                  or os.environ.get("OPENAI_API_KEY")
                  or None)


async def generate_image(prompt: str, *,
                                            size: str = "1024x1024",
                                            quality: str = "standard",
                                            model: str = DEFAULT_MODEL,
                                            ) -> bytes:
    """Generate a single image via OpenAI gpt-image-1.  Returns raw PNG
    bytes.  Raises `RuntimeError` after retries are exhausted so the
    caller can fall back to a gradient (callers should already catch).

    `quality` is mapped to gpt-image-1's `quality` parameter:
        - "standard" → "medium"   (sane default, ~$0.02/image)
        - "high"        → "high"        (better detail, ~$0.04/image)
        - "low"          → "low"          (cheap, less detail)
    """
    key = _get_key()
    if not key:
        raise RuntimeError("openai_image_provider: no api key in env "
                                          "(set OPENAI_IMAGE_API_KEY)")
    # Use the direct OpenAI SDK (already a requirement at v1.99+).  We
    # use the sync client inside a thread executor so this async call
    # doesn't block the event loop.
    try:
        from openai import OpenAI, APIStatusError, APIConnectionError, RateLimitError
    except Exception as e:
        raise RuntimeError(f"openai sdk import failed: {e}") from e

    client = OpenAI(api_key=key)
    quality_map = {"standard": "medium", "low": "low", "high": "high",
                          "medium": "medium", "auto": "auto"}
    api_quality = quality_map.get(quality, "medium")

    last_err: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            # Pillow can decode either b64-encoded PNGs or raw URLs.  The
            # gpt-image-1 endpoint returns b64 by default — perfect.
            resp = await asyncio.to_thread(
                client.images.generate,
                model=model,
                prompt=prompt,
                size=size,
                n=1,
                quality=api_quality)
            data = resp.data[0]
            if getattr(data, "b64_json", None):
                return base64.b64decode(data.b64_json)
            # Fallback: download the image via URL if b64 not provided.
            if getattr(data, "url", None):
                import urllib.request
                with urllib.request.urlopen(data.url, timeout=30) as r:
                    return r.read()
            raise RuntimeError("openai response had neither b64_json nor url")
        except (RateLimitError, APIConnectionError, APIStatusError) as e:
            status = getattr(e, "status_code", None)
            retriable = isinstance(e, (RateLimitError, APIConnectionError)) \
                                or (status and status >= 500)
            last_err = e
            if not retriable or attempt == MAX_RETRIES - 1:
                break
            backoff = BASE_BACKOFF_SEC * (2 ** attempt)
            log.warning("openai_image: transient error %s, retry in %.1fs "
                                  "(attempt %d/%d)",
                                  type(e).__name__, backoff, attempt + 1, MAX_RETRIES)
            await asyncio.sleep(backoff)
        except Exception as e:
            last_err = e
            break
    raise RuntimeError(f"openai image gen failed after {MAX_RETRIES} "
                                  f"attempts: {type(last_err).__name__}: {last_err}")
