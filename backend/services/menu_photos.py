"""Menu photos — merchant upload OR AI generation (Gemini Nano Banana).

Public images served via the `/api/static/menu_photos` StaticFiles mount
(mirrors the shoppable_cards pattern). Stores a relative URL on the item.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.menu_photos")

LOCAL_DIR = Path("/app/backend/static/menu_photos")
LOCAL_DIR.mkdir(parents=True, exist_ok=True)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
NANO_BANANA = "gemini-3.1-flash-image-preview"


def _public_url(item_id: str, ext: str) -> str:
    return f"/api/static/menu_photos/{item_id}.{ext}"


def save_bytes(item_id: str, data: bytes, ext: str = "png") -> str:
    ext = (ext or "png").lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "webp"):
        ext = "png"
    # Remove any older extension variants for this item.
    for e in ("png", "jpg", "jpeg", "webp"):
        p = LOCAL_DIR / f"{item_id}.{e}"
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    (LOCAL_DIR / f"{item_id}.{ext}").write_bytes(data)
    return _public_url(item_id, ext)


def save_base64(item_id: str, b64: str, ext: str = "png") -> str:
    data = base64.b64decode(b64)
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("image_too_large")
    # Validate the bytes really are an image.
    try:
        from PIL import Image
        import io as _io
        with Image.open(_io.BytesIO(data)) as im:
            im.verify()
            fmt = (im.format or "").lower()
        if fmt in ("jpeg", "jpg"):
            ext = "jpg"
        elif fmt in ("png", "webp"):
            ext = fmt
        else:
            raise ValueError("unsupported_image")
    except ValueError:
        raise
    except Exception:
        raise ValueError("not_an_image")
    return save_bytes(item_id, data, ext)


async def generate_ai(item_id: str, *, name: str, description: str = "",
                      section: str = "") -> str:
    """Generate an appetizing dish photo via Nano Banana → save → return URL."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import uuid as _uuid

    prompt = (
        f"A professional, appetizing food photograph of \"{name}\""
        + (f" ({description})" if description else "")
        + ". Overhead or 45-degree angle, natural soft lighting, on a clean "
        "plate over a subtle neutral background, high detail, menu-quality, "
        "no text, no watermark."
    )
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"menuphoto_{_uuid.uuid4().hex}",
                   system_message="You are a food photography image generator.")
    chat.with_model("gemini", NANO_BANANA).with_params(modalities=["image", "text"])
    _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not images:
        raise RuntimeError("no_image_generated")
    img = images[0]
    data = base64.b64decode(img["data"])
    ext = "png"
    mt = (img.get("mime_type") or "").lower()
    if "jpeg" in mt or "jpg" in mt:
        ext = "jpg"
    elif "webp" in mt:
        ext = "webp"
    return save_bytes(item_id, data, ext)



async def _generate(item_id: str, prompt: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import uuid as _uuid
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"photo_{_uuid.uuid4().hex}",
                   system_message="You are a professional commercial photograph generator.")
    chat.with_model("gemini", NANO_BANANA).with_params(modalities=["image", "text"])
    _text, images = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not images:
        raise RuntimeError("no_image_generated")
    img = images[0]
    data = base64.b64decode(img["data"])
    mt = (img.get("mime_type") or "").lower()
    ext = "jpg" if ("jpeg" in mt or "jpg" in mt) else ("webp" if "webp" in mt else "png")
    return save_bytes(item_id, data, ext)


async def generate_service_ai(item_id: str, *, name: str, description: str = "") -> str:
    prompt = (
        f"A clean, inviting promotional photo representing the service \"{name}\""
        + (f" ({description})" if description else "")
        + ". Bright, professional lifestyle setting, soft natural light, high detail, "
        "no text, no watermark, no visible faces."
    )
    return await _generate(item_id, prompt)


async def generate_product_ai(item_id: str, *, name: str, description: str = "") -> str:
    prompt = (
        f"A professional e-commerce product photo of \"{name}\""
        + (f" ({description})" if description else "")
        + ". Centered on a clean white studio background, soft shadows, crisp detail, "
        "catalog-quality, no text, no watermark."
    )
    return await _generate(item_id, prompt)
