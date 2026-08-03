"""Phase CLAIM.1 — Station edit-request service.

An owner-authored patch on a claimed station's editable fields.  Admin
approves / rejects; approved edits are applied to the station document
in a single atomic $set.  Fields owner CAN edit:

    description_text
    description_audio_url + description_audio_duration_sec
    banner_image_url
    logo_url (overrides owner_overrides.logo_url)
    display name (`name`), homepage, contact email, description, bio
    social_links (dict), tags_json, language

Fields owner CANNOT edit (admin-controlled):
    is_flagship, flagship_region, flagship_priority, is_priority,
    active, claim_status, owner_profile_id, stream_url (needs QA)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("bigfm.claim1.edit_request")


EDIT_STATUSES = {"draft", "pending", "approved", "rejected", "withdrawn"}
CHANGE_TYPES  = {"metadata", "description_text", "description_audio",
                                  "banner_image", "logo", "stream_url", "multiple"}

OWNER_EDITABLE_FIELDS = {
    "description_text",
    "description_audio_url", "description_audio_duration_sec",
    "banner_image_url",
    "logo_url",
    "name", "homepage", "contact_email", "description", "bio",
    "social_links", "tags_json", "language", "broadcast_schedule",
    "market_city", "market_country",
}

# Sanity caps.
MAX_DESCRIPTION_TEXT_CHARS = 10_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return f"ser_{uuid.uuid4().hex[:16]}"


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return doc
    d = {k: v for k, v in doc.items() if k != "_id"}
    for k in ("created_at", "updated_at", "reviewed_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    return d


def _sanitize_changes(proposed: Dict[str, Any]) -> Dict[str, Any]:
    """Drop non-whitelisted fields, cap oversized strings, return clean dict."""
    if not isinstance(proposed, dict):
        raise ValueError("proposed_changes_must_be_object")
    out: Dict[str, Any] = {}
    for k, v in proposed.items():
        if k not in OWNER_EDITABLE_FIELDS:
            continue
        if k == "description_text" and isinstance(v, str):
            v = v[:MAX_DESCRIPTION_TEXT_CHARS]
        out[k] = v
    return out


def _detect_change_type(clean: Dict[str, Any]) -> str:
    keys = set(clean.keys())
    if len(keys) > 1:
        return "multiple"
    only = next(iter(keys), "")
    if only == "description_text":
        return "description_text"
    if only in {"description_audio_url", "description_audio_duration_sec"}:
        return "description_audio"
    if only == "banner_image_url":
        return "banner_image"
    if only == "logo_url":
        return "logo"
    if only == "stream_url":
        return "stream_url"
    return "metadata"


# ─────────────────────── Owner side ───────────────────────
async def submit_edit_request(db, *, station_id: str, owner_user_id: str,
                                                                        proposed_changes: Dict[str, Any],
                                                                        uploaded_files: Optional[List[Dict[str, Any]]] = None
                                                                        ) -> Dict[str, Any]:
    """Create a `pending` edit request for a station the caller owns.
    Ownership check is enforced by the route layer — this service assumes
    the caller has already been authorized."""
    clean = _sanitize_changes(proposed_changes)
    if not clean and not uploaded_files:
        raise ValueError("no_editable_fields_provided")

    # Check station is claimed by this user.
    station = await db.imported_radio_stations.find_one({"id": station_id})
    if not station:
        raise LookupError("station_not_found")
    profile = await db.station_owner_profiles.find_one(
        {"user_id": owner_user_id})
    if not profile or station.get("owner_profile_id") != profile["id"]:
        raise ValueError("not_station_owner")

    # Deny mid-flight duplicate: one pending edit per station per owner.
    dup = await db.station_edit_requests.find_one({
        "station_id": station_id,
        "owner_user_id": owner_user_id,
        "edit_status": {"$in": ["draft", "pending"]},
    })
    if dup:
        raise ValueError("edit_request_already_pending:" + dup["id"])

    # Auto-publish path — some stations bypass admin queue.
    auto = bool(station.get("auto_publish_edits"))

    now = _now()
    edit_id = _new_id()
    doc = {
        "_id":                                edit_id,
        "id":                                  edit_id,
        "station_id":                  station_id,
        "station_source":         "imported_radio_stations",
        "owner_user_id":            owner_user_id,
        "owner_profile_id":     profile["id"],
        "proposed_changes":     clean,
        "change_type":              _detect_change_type(clean),
        "uploaded_files":         uploaded_files or [],
        "edit_status":              "approved" if auto else "pending",
        "admin_reviewer_id":  "auto_publish" if auto else None,
        "review_notes":              None,
        "reviewed_at":                now if auto else None,
        "created_at":                  now,
        "updated_at":                  now,
    }
    await db.station_edit_requests.insert_one(doc)
    if auto:
        await _apply_edit_to_station(db, doc)
    return _strip(doc)


async def list_edit_requests_for_owner(db, *, owner_user_id: str,
                                                                                                status: Optional[str] = None,
                                                                                                limit: int = 50, offset: int = 0
                                                                                                ) -> Tuple[List[Dict[str, Any]], int]:
    q: Dict[str, Any] = {"owner_user_id": owner_user_id}
    if status:
        q["edit_status"] = status
    total = await db.station_edit_requests.count_documents(q)
    items = []
    async for d in db.station_edit_requests.find(q) \
                                                                                        .sort("created_at", -1) \
                                                                                        .skip(offset).limit(limit):
        items.append(_strip(d))
    return items, total


async def withdraw_edit_request(db, *, edit_id: str,
                                                                                owner_user_id: str) -> Dict[str, Any]:
    d = await db.station_edit_requests.find_one({"id": edit_id})
    if not d:
        raise LookupError("edit_request_not_found")
    if d["owner_user_id"] != owner_user_id:
        raise PermissionError("not_owner")
    if d["edit_status"] not in ("draft", "pending"):
        raise ValueError("not_withdrawable:" + d["edit_status"])
    await db.station_edit_requests.update_one(
        {"id": edit_id},
        {"$set": {"edit_status": "withdrawn", "updated_at": _now()}})
    return _strip(await db.station_edit_requests.find_one({"id": edit_id}))


# ─────────────────────── Admin side ───────────────────────
async def list_edit_requests_for_admin(db, *, status: Optional[str] = "pending",
                                                                                                limit: int = 50, offset: int = 0
                                                                                                ) -> Tuple[List[Dict[str, Any]], int]:
    q: Dict[str, Any] = {}
    if status and status != "all":
        q["edit_status"] = status
    total = await db.station_edit_requests.count_documents(q)
    items = []
    async for d in db.station_edit_requests.find(q) \
                                                                                        .sort("created_at", -1) \
                                                                                        .skip(offset).limit(limit):
        # Enrich with station snapshot.
        s = await db.imported_radio_stations.find_one(
            {"id": d["station_id"]},
            projection={"name": 1, "homepage": 1, "country": 1,
                                          "language": 1, "favicon": 1, "logo_url": 1})
        d = _strip(d)
        d["station_snapshot"] = {"id": d["station_id"],
                                                                    "name": (s or {}).get("name"),
                                                                    "homepage": (s or {}).get("homepage"),
                                                                    "logo_url": (s or {}).get("logo_url")
                                                                                                or (s or {}).get("favicon")}
        items.append(d)
    return items, total


async def get_edit_request(db, *, edit_id: str
                                                        ) -> Optional[Dict[str, Any]]:
    d = await db.station_edit_requests.find_one({"id": edit_id})
    if not d:
        return None
    d = _strip(d)
    # Include a before/after diff.
    s = await db.imported_radio_stations.find_one({"id": d["station_id"]})
    diff = {}
    for k, v in d.get("proposed_changes", {}).items():
        diff[k] = {"before": (s or {}).get(k), "after": v}
    d["diff"] = diff
    return d


async def _apply_edit_to_station(db, edit_doc: Dict[str, Any]) -> None:
    """Write approved changes onto the station doc + stamp
    `owner_edited_at`.    Called on approve OR auto-publish."""
    clean = edit_doc.get("proposed_changes") or {}
    if not clean:
        return
    setter = dict(clean)
    setter["owner_edited_at"] = _now().isoformat()
    # Also mirror the editable overrides that Phase 42-C reads.
    overrides = None
    for k in ("logo_url", "description", "market_city",
                        "market_country", "bio"):
        if k in clean:
            overrides = overrides or {}
            overrides[k] = clean[k]
    if overrides:
        setter["owner_overrides"] = overrides
    await db.imported_radio_stations.update_one(
        {"id": edit_doc["station_id"]},
        {"$set": setter})


async def approve_edit_request(db, *, edit_id: str, admin_user_id: str,
                                                                        review_notes: Optional[str] = None
                                                                        ) -> Dict[str, Any]:
    d = await db.station_edit_requests.find_one({"id": edit_id})
    if not d:
        raise LookupError("edit_request_not_found")
    if d["edit_status"] not in ("pending", "draft"):
        raise ValueError("not_pending:" + d["edit_status"])
    now = _now()
    await db.station_edit_requests.update_one(
        {"id": edit_id},
        {"$set": {"edit_status": "approved",
                              "admin_reviewer_id": admin_user_id,
                              "review_notes":         (review_notes or "").strip()[:500],
                              "reviewed_at":            now,
                              "updated_at":              now}})
    fresh = await db.station_edit_requests.find_one({"id": edit_id})
    await _apply_edit_to_station(db, fresh)
    return _strip(fresh)


async def reject_edit_request(db, *, edit_id: str, admin_user_id: str,
                                                                    review_notes: str) -> Dict[str, Any]:
    if not review_notes or not review_notes.strip():
        raise ValueError("review_notes_required")
    d = await db.station_edit_requests.find_one({"id": edit_id})
    if not d:
        raise LookupError("edit_request_not_found")
    if d["edit_status"] not in ("pending", "draft"):
        raise ValueError("not_pending:" + d["edit_status"])
    now = _now()
    await db.station_edit_requests.update_one(
        {"id": edit_id},
        {"$set": {"edit_status": "rejected",
                              "admin_reviewer_id": admin_user_id,
                              "review_notes":         review_notes.strip()[:500],
                              "reviewed_at":            now,
                              "updated_at":              now}})
    return _strip(await db.station_edit_requests.find_one({"id": edit_id}))


async def set_auto_publish(db, *, station_id: str, admin_user_id: str,
                                                        enabled: bool) -> Dict[str, Any]:
    r = await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"auto_publish_edits": bool(enabled),
                              "auto_publish_edits_updated_by": admin_user_id,
                              "auto_publish_edits_updated_at":
                                  _now().isoformat()}})
    if r.matched_count == 0:
        raise LookupError("station_not_found")
    return {"ok": True, "station_id": station_id,
                        "auto_publish_edits": bool(enabled)}
