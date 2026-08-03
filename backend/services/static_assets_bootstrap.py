"""Boot-time self-heal for missing static image assets.

Purpose (Phase STATIC.BOOT, 2026-07-31): the app references dozens of
image assets under `backend/static/**` and prod deploys have twice now
shipped without one or more of them, resulting in broken tiles /
placeholder glyphs on the live site (channel thumbnails, marketing
splash images, home-page game cards, etc).

This module scans the local static tree at startup, identifies any
files listed in `image_prompts_registry.REGISTRY` that are missing on
disk, and regenerates them via nano_banana (Gemini).  It runs
asynchronously in the background so it never blocks startup.

Idempotent — files that exist on disk are left untouched.

Wired into `server.py` startup via `ensure_static_assets_bootstrap(db)`.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from services.image_prompts_registry import REGISTRY, ImagePromptSpec

log = logging.getLogger("bigfm.static_bootstrap")

# Root of the static tree served by the FastAPI StaticFiles mounts.
_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def _file_path(category: str, slug: str, ext: str) -> Path:
    return _STATIC_ROOT / category / f"{slug}.{ext}"


async def _generate_bytes(prompt: str) -> Optional[bytes]:
    """Call nano_banana (Gemini image gen) via emergentintegrations.

    Returns raw PNG bytes on success, None on failure.
    Fail-quiet: any exception (missing key, quota, decode) returns None
    so the bootstrap continues with the next asset.

    NOTE — mirrors `services.channel_thumbnails._call_gemini_image` so
    the model name + call pattern stay in sync.  The correct model
    name is `gemini-2.5-flash-image` (NOT the `-preview` variant which
    Gemini returns 404 on since 2026-06).
    """
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        log.warning("[static-bootstrap] EMERGENT_LLM_KEY not set — "
                                "skipping image generation")
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as exc:
        log.warning("[static-bootstrap] emergentintegrations import "
                                "failed: %s", exc)
        return None
    try:
        chat = (LlmChat(
            api_key=key, session_id=f"static-bootstrap-{prompt[:20]}",
            system_message=("You generate a single 1024x1024 image "
                                                    "based on the user's prompt.  Return "
                                                    "the image only."))
                      .with_model("gemini", "gemini-2.5-flash-image")
                      .with_params(modalities=["image", "text"]))
        msg = UserMessage(text=prompt)
        _text, images = await chat.send_message_multimodal_response(msg)
        if not images:
            log.warning("[static-bootstrap] no images returned for prompt: "
                                    "%s...", prompt[:80])
            return None
        return base64.b64decode(images[0]["data"])
    except Exception as exc:
        log.warning("[static-bootstrap] gemini gen failed: %s", exc)
        return None


async def _write_asset(category: str, slug: str, ext: str,
                                                raw_bytes: bytes) -> bool:
    """Write raw image bytes.  If ext == 'webp' and Pillow is
    available, convert; otherwise write raw."""
    target = _file_path(category, slug, ext)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if ext.lower() == "webp":
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
                # Downscale huge previews to a reasonable channel-thumbnail
                # size to save bytes.
                if img.width > 1024:
                    img.thumbnail((1024, 1024))
                img.save(target, "WEBP", quality=88, method=4)
                return True
            except Exception as exc:
                log.warning("[static-bootstrap] webp conversion failed "
                                        "for %s: %s — writing raw png", slug, exc)
                # Fall through — write raw
        target.write_bytes(raw_bytes)
        return True
    except Exception as exc:
        log.warning("[static-bootstrap] file write failed for %s: %s",
                                slug, exc)
        return False


async def _stamp_db(db, slug: str, spec: ImagePromptSpec) -> None:
    """If the registry entry carries a db_hint, stamp the URL back on
    the referenced document so the FE + admin views see it."""
    hint = spec[3]
    if not hint:
        return
    coll = hint.get("collection")
    filter_key = hint.get("filter_key")
    url_field = hint.get("url_field")
    value = hint.get("value_template")
    if not (coll and filter_key and url_field and value):
        return
    try:
        await db[coll].update_one(
            {filter_key: slug},
            {"$set": {url_field: value}})
    except Exception as exc:
        log.warning("[static-bootstrap] db stamp failed for %s: %s",
                                slug, exc)


async def _audit_and_regenerate(db) -> Dict[str, Any]:
    """Walk the registry.  For each slug, if the file is missing, try
    to regenerate.  Returns a summary dict for logging.

    Phase STATIC.BOOT.v3 (2026-08-02): if the file is already present
    but the registry entry carries a `db_hint`, still stamp the DB so
    a fresh-DB deploy (where `channels.thumbnail_url` was never
    populated by any seed) can be healed WITHOUT any LLM cost.
    Idempotent — repeated boots are cheap `$set` no-ops."""
    summary = {"total": 0, "already_present": 0,
                              "regenerated": 0, "db_stamped": 0,
                              "failed": 0, "missing_after": []}
    for slug, spec in REGISTRY.items():
        category, prompt, ext, hint = spec
        summary["total"] += 1
        target = _file_path(category, slug, ext)
        if target.exists() and target.stat().st_size > 0:
            summary["already_present"] += 1
            # File is on disk; still stamp the URL back on the DB doc
            # if the caller supplied a db_hint.  This handles the case
            # where a fresh prod DB has `thumbnail_url: null` even
            # though the .webp is git-shipped.
            if hint:
                await _stamp_db(db, slug, spec)
                summary["db_stamped"] += 1
            continue
        raw = await _generate_bytes(prompt)
        if not raw:
            summary["failed"] += 1
            summary["missing_after"].append(slug)
            continue
        ok = await _write_asset(category, slug, ext, raw)
        if ok:
            summary["regenerated"] += 1
            if hint:
                await _stamp_db(db, slug, spec)
                summary["db_stamped"] += 1
        else:
            summary["failed"] += 1
            summary["missing_after"].append(slug)
    return summary


# DB-scan diagnostic (Phase STATIC.BOOT — deliverable #5).
# Walks the collections that historically carry `*_url` fields
# pointing at `/api/static/*`, extracts the referenced slugs, and
# reports which slugs are referenced by a DB doc but MISSING on disk
# AND not covered by REGISTRY.  This is READ-ONLY — it doesn't
# regenerate; it produces a diagnostic list so an operator knows what
# to add to the registry.
_DB_URL_FIELDS = [
    # (collection, field-name)
    ("channels",                    "thumbnail_url"),
    ("marketing_assets",     "image_url"),
    ("marketing_assets",     "url"),
    ("businesses",              "logo_url"),
    ("businesses",              "cover_image_url"),
    ("rj_personas",              "avatar_url"),
    ("games_v2_campaigns", "sponsor_logo_url"),
    ("games_v2_campaigns", "icon_url"),
    ("games_v2_campaigns", "cover_image_url"),
    ("banner_ads",              "creative_url"),
    ("station_artwork",     "url"),
    ("flagship_logos",       "logo_url"),
]


def _slug_from_static_url(url: str) -> Optional[Tuple[str, str, str]]:
    """If `url` starts with `/api/static/<category>/<slug>.<ext>`, return
    `(category, slug, ext)`; else None."""
    if not url or not isinstance(url, str):
        return None
    if not url.startswith("/api/static/"):
        return None
    rest = url[len("/api/static/"):]
    parts = rest.split("/", 1)
    if len(parts) != 2:
        return None
    category, filename = parts
    if "." not in filename:
        return None
    slug, ext = filename.rsplit(".", 1)
    # Trim any query string.
    slug = slug.split("?", 1)[0]
    ext = ext.split("?", 1)[0]
    return category, slug, ext


async def _db_scan_diagnostic(db) -> Dict[str, Any]:
    """Walk the DB, extract every `/api/static/...` URL, and report which
    slugs are referenced but MISSING on disk.  This is READ-ONLY and is
    designed to help operators discover new assets that should be added
    to `image_prompts_registry` for future self-healing.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for coll, field in _DB_URL_FIELDS:
        try:
            cursor = db[coll].find({field: {"$regex": r"^/api/static/"}},
                                                              {field: 1, "_id": 1}).limit(500)
            async for doc in cursor:
                url = doc.get(field) or ""
                parsed = _slug_from_static_url(url)
                if not parsed:
                    continue
                category, slug, ext = parsed
                key = f"{category}/{slug}.{ext}"
                entry = seen.setdefault(key, {
                    "category": category, "slug": slug, "ext": ext,
                    "referenced_by": [],
                    "on_disk": None,
                    "in_registry": slug in REGISTRY,
                })
                entry["referenced_by"].append({"collection": coll,
                                                                                    "field": field})
        except Exception as exc:
            log.warning("[static-bootstrap] db scan failed for %s.%s: %s",
                                    coll, field, exc)
    missing_and_unregistered = []
    missing_but_registered   = []
    for key, entry in seen.items():
        target = _STATIC_ROOT / entry["category"] / f"{entry['slug']}.{entry['ext']}"
        entry["on_disk"] = target.exists() and target.stat().st_size > 0
        if entry["on_disk"]:
            continue
        if entry["in_registry"]:
            missing_but_registered.append(key)
        else:
            missing_and_unregistered.append(key)
    if missing_and_unregistered:
        log.warning("[static-bootstrap] %d DB-referenced assets are MISSING "
                                "on disk AND NOT in image_prompts_registry — add "
                                "prompts for these to enable auto-heal:\n  %s",
                                len(missing_and_unregistered),
                                "\n  ".join(missing_and_unregistered[:20]))
    return {"scanned_collections": len(_DB_URL_FIELDS),
                      "unique_urls": len(seen),
                      "missing_but_registered": missing_but_registered,
                      "missing_and_unregistered": missing_and_unregistered}


async def ensure_static_assets_bootstrap(db) -> Dict[str, Any]:
    """Public entrypoint — call once at server startup.

    Runs the audit + regeneration synchronously (each nano_banana call
    is ~5-15 s so a 5-asset regenerate can take a minute).  Callers
    should schedule this as a background task, not await it during the
    startup event, if they want the server to accept traffic promptly.
    """
    if not _STATIC_ROOT.exists():
        log.info("[static-bootstrap] static root missing at %s — nothing "
                          "to check", _STATIC_ROOT)
        return {"skipped": True}
    log.info("[static-bootstrap] auditing %d registered assets under %s",
                      len(REGISTRY), _STATIC_ROOT)
    summary = await _audit_and_regenerate(db)
    # Read-only DB diagnostic — surface URLs that reference missing
    # files that are NOT covered by the registry so an operator knows
    # what to add.
    try:
        diag = await _db_scan_diagnostic(db)
        summary["db_scan"] = diag
    except Exception as exc:
        log.warning("[static-bootstrap] db scan failed: %s", exc)
        summary["db_scan"] = {"error": str(exc)}
    log.info("[static-bootstrap] done: %s", summary)
    return summary


def schedule_bootstrap(app_state) -> None:
    """Fire-and-forget background task wrapper.  Call from the FastAPI
    startup event.  Requires `app.state.db` to already be set."""
    db = getattr(app_state, "db", None)
    if db is None:
        log.warning("[static-bootstrap] db not yet attached to app.state; "
                                "skipping bootstrap")
        return
    async def _run():
        try:
            await ensure_static_assets_bootstrap(db)
        except Exception as exc:
            log.warning("[static-bootstrap] uncaught: %s", exc)
    try:
        asyncio.create_task(_run())
    except Exception as exc:
        log.warning("[static-bootstrap] task-schedule failed: %s", exc)


__all__ = ["ensure_static_assets_bootstrap", "schedule_bootstrap"]
