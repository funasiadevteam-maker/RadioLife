"""Phase 8c — Lead capture forms for game campaigns.

A lead form is attached to a campaign and presented to the listener BEFORE
the game starts.  We validate the submitted form against the form's
field schema, store it in `game_lead_submissions`, and dispatch downstream
delivery (CRM/webhook) via `games_v2_webhooks.queue_event`.

The 24-hour dedupe is keyed by (user_id, campaign_id) for authenticated
listeners and (ip, campaign_id) for anonymous landing-page submissions.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.games_v2 import _new_id, _now


FIELD_TYPES = {"text", "email", "phone", "select", "checkbox"}
FORM_OUTCOMES = {"game_completed", "game_won", "game_lost", "abandoned"}
SUBMISSION_DEDUP_HOURS = 24
MAX_LEAD_CSV_ROWS = 100_000


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,20}$")


async def ensure_lead_indexes(db) -> None:
    await db.game_lead_forms.create_index(
        [("campaign_id", 1)], unique=True)
    await db.game_lead_forms.create_index([("active", 1)])
    await db.game_lead_submissions.create_index(
        [("campaign_id", 1), ("submitted_at", -1)])
    await db.game_lead_submissions.create_index([("form_id", 1)])
    await db.game_lead_submissions.create_index([("user_id", 1)])
    await db.game_lead_submissions.create_index([("ip", 1)])


def validate_form_schema(fields: list[dict]) -> list[dict]:
    """Returns the canonicalized fields_json or raises ValueError."""
    if not isinstance(fields, list) or not fields:
        raise ValueError("lead_form.fields_required")
    if len(fields) > 20:
        raise ValueError("lead_form.max_20_fields")
    out = []
    seen_names = set()
    for raw in fields:
        if not isinstance(raw, dict):
            raise ValueError("lead_form.field_must_be_object")
        name = (raw.get("name") or "").strip()
        if not re.match(r"^[a-z][a-z0-9_]{0,40}$", name):
            raise ValueError(f"lead_form.invalid_field_name:{name}")
        if name in seen_names:
            raise ValueError(f"lead_form.duplicate_field:{name}")
        seen_names.add(name)
        ftype = (raw.get("type") or "text").lower()
        if ftype not in FIELD_TYPES:
            raise ValueError(f"lead_form.invalid_field_type:{ftype}")
        label = (raw.get("label") or name).strip()[:120]
        options = raw.get("options") or []
        if ftype == "select":
            if not isinstance(options, list) or not options:
                raise ValueError(f"lead_form.{name}.select_needs_options")
            options = [str(o)[:80] for o in options][:30]
        out.append({
            "name": name, "label": label, "type": ftype,
            "required": bool(raw.get("required", False)),
            "options": options if ftype == "select" else [],
            "validation_regex": (raw.get("validation_regex") or "")[:200],
        })
    return out


def validate_submission(form: dict, payload: dict) -> dict:
    """Validates payload against form schema, returns sanitized data dict."""
    out: dict = {}
    for f in form["fields_json"]:
        name = f["name"]
        val = payload.get(name)
        if val is None or (isinstance(val, str) and not val.strip()):
            if f["required"]:
                raise ValueError(f"field_required:{name}")
            continue
        if f["type"] == "email":
            if not _EMAIL_RE.match(str(val)):
                raise ValueError(f"invalid_email:{name}")
        elif f["type"] == "phone":
            if not _PHONE_RE.match(str(val)):
                raise ValueError(f"invalid_phone:{name}")
        elif f["type"] == "select":
            if str(val) not in f["options"]:
                raise ValueError(f"invalid_option:{name}")
        elif f["type"] == "checkbox":
            val = bool(val)
        if f["type"] != "checkbox" and f["validation_regex"]:
            try:
                if not re.match(f["validation_regex"], str(val)):
                    raise ValueError(f"regex_mismatch:{name}")
            except re.error:
                pass
        if isinstance(val, str):
            val = val.strip()[:500]
        out[name] = val
    return out


async def upsert_lead_form(db, *, campaign_id: str,
                                  fields_json: list[dict],
                                  required_before_play: bool = True,
                                  submit_button_label: str = "Start playing",
                                  consent_text: str = "",
                                  consent_required: bool = True,
                                  crm_sync_enabled: bool = False,
                                  webhook_url: Optional[str] = None,
                                  active: bool = True) -> dict:
    fields = validate_form_schema(fields_json)
    now = _now()
    existing = await db.game_lead_forms.find_one({"campaign_id": campaign_id})
    if existing:
        await db.game_lead_forms.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "fields_json": fields,
                "required_before_play": bool(required_before_play),
                "submit_button_label": submit_button_label[:60],
                "consent_text": consent_text[:2000],
                "consent_required": bool(consent_required),
                "crm_sync_enabled": bool(crm_sync_enabled),
                "webhook_url": (webhook_url or "")[:500] or None,
                "active": bool(active),
                "updated_at": now,
            }})
        return await db.game_lead_forms.find_one({"_id": existing["_id"]})
    fid = _new_id("lf")
    doc = {
        "_id": fid, "form_id": fid,
        "campaign_id": campaign_id,
        "fields_json": fields,
        "required_before_play": bool(required_before_play),
        "submit_button_label": submit_button_label[:60],
        "consent_text": consent_text[:2000],
        "consent_required": bool(consent_required),
        "crm_sync_enabled": bool(crm_sync_enabled),
        "webhook_url": (webhook_url or "")[:500] or None,
        "active": bool(active),
        "created_at": now, "updated_at": now,
    }
    await db.game_lead_forms.insert_one(doc)
    return doc


async def get_lead_form(db, campaign_id: str) -> Optional[dict]:
    return await db.game_lead_forms.find_one({"campaign_id": campaign_id})


async def lead_form_view(form: dict) -> dict:
    """Public-safe view (still includes everything; consumers strip as needed)."""
    return {
        "form_id": form["form_id"],
        "campaign_id": form["campaign_id"],
        "fields_json": form["fields_json"],
        "required_before_play": form.get("required_before_play", True),
        "submit_button_label": form.get("submit_button_label", "Start"),
        "consent_text": form.get("consent_text", ""),
        "consent_required": form.get("consent_required", True),
        "crm_sync_enabled": form.get("crm_sync_enabled", False),
        "webhook_url": form.get("webhook_url"),
        "active": form.get("active", True),
        "updated_at": (form["updated_at"].isoformat()
                          if form.get("updated_at") else None),
    }


async def submit_lead(db, *, campaign_id: str, form: dict,
                          user_id: Optional[str], ip: Optional[str],
                          user_agent: Optional[str],
                          form_data: dict, consent_accepted: bool) -> dict:
    """Validates + stores a lead submission. 24h dedupe per identity."""
    if form.get("consent_required") and not consent_accepted:
        raise ValueError("consent_required")
    sanitized = validate_submission(form, form_data)
    # 24h dedupe
    since = _now() - timedelta(hours=SUBMISSION_DEDUP_HOURS)
    dedupe_q: dict = {"campaign_id": campaign_id,
                          "submitted_at": {"$gt": since}}
    if user_id:
        dedupe_q["user_id"] = user_id
    elif ip:
        dedupe_q["ip"] = ip
        dedupe_q["user_id"] = None
    else:
        dedupe_q["_no_match_"] = True
    prior = await db.game_lead_submissions.find_one(dedupe_q,
                                                              sort=[("submitted_at", -1)])
    if prior:
        return prior
    sid = _new_id("lsub")
    doc = {
        "_id": sid, "submission_id": sid,
        "form_id": form["form_id"],
        "campaign_id": campaign_id,
        "user_id": user_id,
        "form_data_json": sanitized,
        "consent_accepted": bool(consent_accepted),
        "consent_text_snapshot": (form.get("consent_text") or "")[:2000],
        "submitted_at": _now(),
        "ip": ip, "user_agent": user_agent,
        "delivery_status_json": {
            "crm": "pending" if form.get("crm_sync_enabled") else "skipped",
            "webhook": "pending" if form.get("webhook_url") else "skipped",
        },
    }
    await db.game_lead_submissions.insert_one(doc)
    # Hand off to webhook delivery if applicable
    try:
        from services.games_v2_webhooks import queue_event
        await queue_event(
            db, campaign_id=campaign_id,
            event_type="lead_submitted",
            payload={"submission_id": sid,
                      "campaign_id": campaign_id,
                      "form_id": form["form_id"],
                      "user_id": user_id,
                      "form_data": sanitized,
                      "submitted_at": doc["submitted_at"].isoformat()},
            direct_webhook_url=form.get("webhook_url"),
        )
    except Exception:
        pass
    return doc


async def list_leads(db, campaign_id: str,
                          since: Optional[datetime] = None,
                          outcome: Optional[str] = None,
                          limit: int = 100,
                          cursor: Optional[datetime] = None) -> dict:
    q: dict = {"campaign_id": campaign_id}
    ts_q: dict = {}
    if since:
        ts_q["$gte"] = since
    if cursor:
        ts_q["$lt"] = cursor
    if ts_q:
        q["submitted_at"] = ts_q
    items = []
    if outcome:
        if outcome not in FORM_OUTCOMES:
            raise ValueError(f"invalid_outcome:{outcome}")
        # Join with sessions to filter by game outcome
        async for sub in (db.game_lead_submissions
                              .find(q).sort("submitted_at", -1).limit(limit * 4)):
            sess = None
            if sub.get("user_id"):
                sess = await db.game_sessions.find_one({
                    "campaign_id": campaign_id, "user_id": sub["user_id"],
                    "started_at": {"$gte": sub["submitted_at"]
                                          - timedelta(minutes=1)},
                }, sort=[("started_at", 1)])
            mapped = _session_to_outcome(sess)
            if mapped == outcome:
                items.append(_lead_row(sub, sess))
            if len(items) >= limit:
                break
    else:
        async for sub in (db.game_lead_submissions
                              .find(q).sort("submitted_at", -1).limit(limit)):
            items.append(_lead_row(sub, None))
    next_cursor = (items[-1]["submitted_at"]
                       if len(items) == limit and items else None)
    return {"items": items, "next_cursor": next_cursor}


def _session_to_outcome(sess: Optional[dict]) -> str:
    if not sess:
        return "abandoned"
    status = sess.get("status")
    if status not in {"completed", "claimed"}:
        return "abandoned"
    return "game_won" if sess.get("result") == "win" else "game_lost"


def _lead_row(sub: dict, sess: Optional[dict]) -> dict:
    return {
        "submission_id": sub["submission_id"],
        "form_id": sub["form_id"],
        "campaign_id": sub["campaign_id"],
        "user_id": sub.get("user_id"),
        "form_data": sub.get("form_data_json", {}),
        "submitted_at": sub["submitted_at"].isoformat()
                            if sub.get("submitted_at") else None,
        "consent_accepted": sub.get("consent_accepted", False),
        "ip": sub.get("ip"),
        "outcome": _session_to_outcome(sess),
        "delivery_status": sub.get("delivery_status_json", {}),
    }


def leads_to_csv(items: list[dict]) -> str:
    if len(items) > MAX_LEAD_CSV_ROWS:
        raise ValueError("csv_row_cap_exceeded")
    buf = io.StringIO()
    if not items:
        buf.write("submission_id,submitted_at,user_id,outcome,consent_accepted\n")
        return buf.getvalue()
    field_names = set()
    for it in items:
        field_names.update((it.get("form_data") or {}).keys())
    sorted_fields = sorted(field_names)
    base_cols = ["submission_id", "submitted_at", "user_id",
                    "outcome", "consent_accepted", "ip"]
    writer = csv.DictWriter(buf, fieldnames=base_cols + sorted_fields,
                                  extrasaction="ignore")
    writer.writeheader()
    for it in items:
        row = {c: it.get(c) for c in base_cols}
        for f in sorted_fields:
            row[f] = (it.get("form_data") or {}).get(f, "")
        writer.writerow(row)
    return buf.getvalue()


async def find_valid_lead_for_user(db, *, campaign_id: str,
                                          user_id: Optional[str],
                                          ip: Optional[str]) -> Optional[dict]:
    """Returns the most recent valid lead submission within the dedupe
    window for this (user/ip, campaign).  Used by start_session gate."""
    since = _now() - timedelta(hours=SUBMISSION_DEDUP_HOURS)
    q: dict = {"campaign_id": campaign_id, "submitted_at": {"$gt": since}}
    if user_id:
        q["user_id"] = user_id
    elif ip:
        q["ip"] = ip
        q["user_id"] = None
    else:
        return None
    return await db.game_lead_submissions.find_one(q,
                                                            sort=[("submitted_at", -1)])
