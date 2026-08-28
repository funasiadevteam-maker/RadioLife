"""Phase 18a — Advertiser self-serve REST surface.

Mounted at /api/advertiser.  Replaces the Phase 4 advertiser apply/me/campaigns
router.  Wires to services/advertisers.py.  Auth model:

- POST /onboard          authed user (creates advertiser + makes them owner)
- GET  /me               authed (list of advertisers user is staff of)
- GET  /{aid}            staff role >= analyst
- POST /{aid}/staff      owner only
- DEL  /{aid}/staff/{u}  owner only
- POST /{aid}/topup      owner+manager (Stripe Checkout)
- *    /{aid}/campaigns* owner+manager (read for analyst)
- *    /{aid}/creatives* owner+manager
- GET  /{aid}/campaigns/{cid}/performance   any staff

Brand-safety: creative upload triggers services.creative_safety.classify_creative
which writes brand_safety_check into the creative doc; submit_campaign reads it.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                          UploadFile)
from pydantic import BaseModel

from auth import current_user
from services.advertisers import (admin_approve, admin_reject, assert_membership,
                                                    create_campaign, create_topup_checkout,
                                                    get_membership, onboard_advertiser,
                                                    pick_ad_for_user, set_status,
                                                    submit_campaign)
from services.creative_safety import classify_creative

logger = logging.getLogger("bigfm.advertiser.routes")

advertiser_router = APIRouter(prefix="/api/advertiser", tags=["advertiser-18a"])

STORAGE_ROOT  = Path("/app/backend/static/ad_creatives")
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

MAX_AUDIO_BYTES   = 5 * 1024 * 1024     # 5 MB
MAX_IMAGE_BYTES   = 1 * 1024 * 1024     # 1 MB
MAX_AUDIO_SEC      = 30


# ─── tiny helpers ────────────────────────────────────────────────────
def _now()  -> datetime: return datetime.now(timezone.utc)
def _gen(p: str) -> str: return f"{p}_{secrets.token_hex(6)}"


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def _require_staff(request: Request, advertiser_id: str,
                                   min_role: str = "analyst") -> dict:
    """Return user doc + staff doc OR raise 403."""
    user = await current_user(request)
    if user.get("role") == "admin":
        return {"user": user, "staff": {"role": "owner", "admin_passthrough": True}}
    db = request.app.state.db
    try:
        staff = await assert_membership(db, advertiser_id=advertiser_id,
                                                  user_id=user["user_id"], min_role=min_role)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return {"user": user, "staff": staff}


# ─── 1) Onboarding ───────────────────────────────────────────────────
class OnboardBody(BaseModel):
    name:                str
    contact_email:   str
    contact_phone:   Optional[str] = None
    market:              str = "dubai"
    address:             Optional[str] = None


@advertiser_router.post("/onboard")
async def onboard(request: Request, body: OnboardBody,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await onboard_advertiser(
        db, owner_user_id=user["user_id"],
              name=body.name, contact_email=body.contact_email,
              contact_phone=body.contact_phone, market=body.market)
    return {"advertiser_id": doc["id"],
              "stripe_customer_id": doc.get("stripe_customer_id"),
              "name": doc["name"], "market": doc["market"]}


@advertiser_router.get("/me")
async def my_advertisers(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = await db.advertiser_staff.find(
        {"user_id": user["user_id"]}).to_list(50)
    out = []
    for r in rows:
        adv = await db.advertisers.find_one({"id": r["advertiser_id"]})
        if adv:
            out.append({"advertiser_id": adv["id"], "name": adv["name"],
                          "role": r.get("role", "analyst"),
                          "market": adv.get("market"),
                          "account_balance_usd": adv.get("account_balance_usd", 0.0),
                          "status": adv.get("status", "active")})
    return {"items": out}


@advertiser_router.get("/{advertiser_id}")
async def advertiser_detail(advertiser_id: str, request: Request):
    ctx = await _require_staff(request, advertiser_id, "analyst")
    db = request.app.state.db
    adv = await db.advertisers.find_one({"id": advertiser_id})
    if not adv:
        raise HTTPException(404, "advertiser not found")
    return {"advertiser": _clean(adv), "my_role": ctx["staff"].get("role")}


# ─── 2) Staff ────────────────────────────────────────────────────────
class StaffAddBody(BaseModel):
    email: str
    role:    str = "manager"   # manager | analyst


@advertiser_router.post("/{advertiser_id}/staff")
async def add_staff(advertiser_id: str, request: Request, body: StaffAddBody):
    await _require_staff(request, advertiser_id, "owner")
    if body.role not in ("manager", "analyst"):
        raise HTTPException(400, "role must be 'manager' or 'analyst'")
    db = request.app.state.db
    target = await db.users.find_one({"email": body.email.lower()})
    if not target:
        raise HTTPException(404, "user with that email not found")
    existing = await get_membership(db, advertiser_id=advertiser_id,
                                                  user_id=target["user_id"])
    if existing:
        await db.advertiser_staff.update_one(
            {"id": existing["id"]},
            {"$set": {"role": body.role, "updated_at": _now()}})
        return {"staff_id": existing["id"], "updated": True}
    sid = _gen("astaff")
    await db.advertiser_staff.insert_one({
        "id":              sid,
        "advertiser_id": advertiser_id,
        "user_id":     target["user_id"],
        "role":           body.role,
        "created_at": _now(),
    })
    return {"staff_id": sid, "updated": False}


@advertiser_router.delete("/{advertiser_id}/staff/{user_id}")
async def remove_staff(advertiser_id: str, user_id: str, request: Request):
    await _require_staff(request, advertiser_id, "owner")
    db = request.app.state.db
    r = await db.advertiser_staff.delete_one(
        {"advertiser_id": advertiser_id, "user_id": user_id,
          "role": {"$in": ["manager", "analyst"]}})
    return {"ok": True, "removed": r.deleted_count}


# ─── 3) Top-up (Stripe Checkout) ────────────────────────────────────
class TopupBody(BaseModel):
    amount_usd:      float
    success_url:     Optional[str] = None
    cancel_url:      Optional[str] = None


@advertiser_router.post("/{advertiser_id}/topup")
async def topup(advertiser_id: str, body: TopupBody, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    if body.amount_usd <= 0:
        raise HTTPException(400, "amount_usd must be > 0")
    db = request.app.state.db
    public_base = (os.environ.get("PUBLIC_BACKEND_URL")
                              or "https://mobile-games-v2.preview.emergentagent.com")
    s_url = body.success_url or f"{public_base}/advertiser/billing"
    c_url = body.cancel_url   or f"{public_base}/advertiser/billing"
    out = await create_topup_checkout(db, advertiser_id=advertiser_id,
                                                    amount_usd=body.amount_usd,
                                                    success_url=s_url, cancel_url=c_url)
    return {"checkout_url": out["url"], "session_id": out["session_id"],
              "mocked": out.get("mocked", False)}


# ─── 4) Campaigns ────────────────────────────────────────────────────
@advertiser_router.post("/{advertiser_id}/campaigns")
async def create_campaign_route(advertiser_id: str, body: dict, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    try:
        doc = await create_campaign(db, advertiser_id=advertiser_id, body=body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"campaign_id": doc["id"], "status": doc["status"]}


@advertiser_router.get("/{advertiser_id}/campaigns")
async def list_campaigns(advertiser_id: str, request: Request,
                                    status: Optional[str] = None):
    await _require_staff(request, advertiser_id, "analyst")
    db = request.app.state.db
    q = {"advertiser_id": advertiser_id}
    if status:
        q["status"] = status
    docs = await db.ad_campaigns.find(q).sort([("created_at", -1)]).to_list(200)
    return {"items": [_clean(d) for d in docs]}


@advertiser_router.get("/{advertiser_id}/campaigns/{campaign_id}")
async def campaign_detail(advertiser_id: str, campaign_id: str, request: Request):
    await _require_staff(request, advertiser_id, "analyst")
    db = request.app.state.db
    c = await db.ad_campaigns.find_one({"id": campaign_id,
                                                              "advertiser_id": advertiser_id})
    if not c:
        raise HTTPException(404, "campaign not found")
    creatives = await db.ad_creatives.find(
        {"id": {"$in": c.get("creative_ids") or []}}).to_list(20)
    return {"campaign":   _clean(c),
              "creatives": [_clean(x) for x in creatives]}


@advertiser_router.patch("/{advertiser_id}/campaigns/{campaign_id}")
async def update_campaign(advertiser_id: str, campaign_id: str,
                                       body: dict, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    allowed = {"name", "objective", "budget_total_usd", "budget_daily_usd",
                  "start_date", "end_date", "targeting", "creative_ids",
                  "attribution_window_hours"}
    upd = {k: v for k, v in body.items() if k in allowed}
    # Phase 18d — validate attribution_window_hours (positive int, ≤ 720 / 30d).
    if "attribution_window_hours" in upd:
        try:
            w = int(upd["attribution_window_hours"])
        except Exception:
            raise HTTPException(400, "attribution_window_hours must be int")
        if w < 1 or w > 720:
            raise HTTPException(400, "attribution_window_hours must be 1..720")
        upd["attribution_window_hours"] = w
    upd["updated_at"] = _now()
    db = request.app.state.db
    r = await db.ad_campaigns.update_one(
        {"id": campaign_id, "advertiser_id": advertiser_id},
        {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "campaign not found")
    updated = await db.ad_campaigns.find_one(
        {"id": campaign_id}, {"_id": 0})
    return {"ok": True, "campaign": updated}


@advertiser_router.post("/{advertiser_id}/campaigns/{campaign_id}/submit")
async def submit_campaign_route(advertiser_id: str, campaign_id: str,
                                                  request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    try:
        return await submit_campaign(db, advertiser_id=advertiser_id,
                                                  campaign_id=campaign_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        detail = e.args[0] if e.args and isinstance(e.args[0], dict) else {"message": str(e)}
        raise HTTPException(422, detail)


@advertiser_router.post("/{advertiser_id}/campaigns/{campaign_id}/pause")
async def pause_campaign(advertiser_id: str, campaign_id: str, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    return await set_status(db, advertiser_id=advertiser_id,
                                    campaign_id=campaign_id, status="paused")


@advertiser_router.post("/{advertiser_id}/campaigns/{campaign_id}/resume")
async def resume_campaign(advertiser_id: str, campaign_id: str, request: Request):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    return await set_status(db, advertiser_id=advertiser_id,
                                    campaign_id=campaign_id, status="active")


@advertiser_router.delete("/{advertiser_id}/campaigns/{campaign_id}")
async def delete_campaign(advertiser_id: str, campaign_id: str, request: Request):
    await _require_staff(request, advertiser_id, "owner")
    db = request.app.state.db
    r = await db.ad_campaigns.delete_one(
        {"id": campaign_id, "advertiser_id": advertiser_id,
          "status": {"$in": ["draft", "rejected", "paused"]}})
    return {"ok": True, "removed": r.deleted_count}


@advertiser_router.get("/{advertiser_id}/campaigns/{campaign_id}/performance")
async def campaign_performance(advertiser_id: str, campaign_id: str,
                                                request: Request,
                                                fromm: Optional[str] = None,
                                                to:        Optional[str] = None):
    await _require_staff(request, advertiser_id, "analyst")
    db = request.app.state.db
    q = {"campaign_id": campaign_id}
    serves = await db.ad_serves.find(q).to_list(5000)
    by_day: dict[str, dict] = {}
    for s in serves:
        d = (s.get("served_at") or _now()).strftime("%Y-%m-%d") \
                if isinstance(s.get("served_at"), datetime) \
                else (s.get("served_at") or "")[:10]
        b = by_day.setdefault(d, {"impressions": 0, "completes": 0,
                                                "saves": 0, "redeems": 0, "spend_usd": 0.0})
        b["impressions"] += 1
        if s.get("completed"):       b["completes"] += 1
        if s.get("coupon_saved"): b["saves"]     += 1
        if s.get("redeemed"):       b["redeems"] += 1
        b["spend_usd"] += float(s.get("cost_usd") or 0.0)
    days = [{"date": d, **b} for d, b in sorted(by_day.items())]
    totals = {
        "impressions": sum(d["impressions"] for d in days),
        "completes":   sum(d["completes"] for d in days),
        "saves":          sum(d["saves"]      for d in days),
        "redeems":     sum(d["redeems"]   for d in days),
        "spend_usd":  round(sum(d["spend_usd"] for d in days), 4),
    }
    return {"days": days, "totals": totals}


# ─── 5) Creatives (multipart upload) ────────────────────────────────
@advertiser_router.post("/{advertiser_id}/creatives")
async def create_creative(advertiser_id: str, request: Request,
                                       audio:           UploadFile = File(...),
                                       title:           str          = Form(...),
                                       transcript:   str          = Form(""),
                                       click_url:     str          = Form(""),
                                       campaign_id: Optional[str] = Form(None),
                                       image:          Optional[UploadFile] = File(None)):
    await _require_staff(request, advertiser_id, "manager")
    db = request.app.state.db
    adv = await db.advertisers.find_one({"id": advertiser_id})
    if not adv:
        raise HTTPException(404, "advertiser not found")

    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(400, f"audio over {MAX_AUDIO_BYTES // (1024*1024)} MB")
    cid = _gen("crt")
    audio_filename = f"{cid}.mp3"
    audio_path     = STORAGE_ROOT / audio_filename
    audio_path.write_bytes(audio_bytes)
    duration_sec = _ffprobe_duration(str(audio_path))
    if duration_sec and duration_sec > MAX_AUDIO_SEC + 0.5:
        audio_path.unlink(missing_ok=True)
        raise HTTPException(400, f"audio over {MAX_AUDIO_SEC} sec")

    image_filename = None
    image_ext = None
    if image and image.filename:
        img_bytes = await image.read()
        if len(img_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(400, f"image over {MAX_IMAGE_BYTES // 1024} KB")
        ext = (Path(image.filename).suffix or ".png").lower()
        image_ext = ext.lstrip(".")
        image_filename = f"{cid}{ext}"
        (STORAGE_ROOT / image_filename).write_bytes(img_bytes)

    # Phase 36c.5 (post-repack ads migration) — push to Tigris when configured.
    # Local files remain as a fallback (serve route prefers Tigris key).
    storage_key_creative_audio = None
    storage_key_creative_image = None
    try:
        from services import object_storage as obs
        st = obs.get_storage()
        if st.backend_name == "tigris":
            k_a = obs.key_ad_creative_audio(cid, "mp3")
            st.upload_bytes(key=k_a, data=audio_bytes,
                              content_type="audio/mpeg")
            storage_key_creative_audio = k_a
            if image_filename and image_ext:
                k_i = obs.key_ad_creative_image(cid, image_ext)
                st.upload_bytes(key=k_i, data=img_bytes,
                                  content_type=f"image/{image_ext}")
                storage_key_creative_image = k_i
    except Exception as e:
        logger.warning("[advertiser.creatives] tigris upload failed (local kept): %s", e)

    safety = await classify_creative(transcript=transcript,
                                                  advertiser_market=adv.get("market", "dubai"))
    verdict = (safety or {}).get("verdict", "review")
    status  = "approved" if verdict == "approved" else (
                  "rejected" if verdict == "rejected" else "pending_review")

    # Phase 18b — VAST 4.0 wrapper for manual uploads too.
    from services.ai_ad_creator import build_vast_xml
    vast_xml = build_vast_xml(creative_id=cid,
                                                audio_url=f"/api/static/ad_creatives/{audio_filename}",
                                                duration_sec=duration_sec or 15,
                                                click_url=click_url or None, title=title,
                                                advertiser_name=adv.get("name", ""))

    doc = {
        "id":                cid,
        "advertiser_id":  advertiser_id,
        "campaign_id":    campaign_id,
        "kind":               "audio_15s",
        "title":              title,
        "audio_url":      f"/api/static/ad_creatives/{audio_filename}",
        "audio_path":     str(audio_path),
        "image_url":     f"/api/static/ad_creatives/{image_filename}" if image_filename else None,
        "storage_key_creative_audio": storage_key_creative_audio,
        "storage_key_creative_image": storage_key_creative_image,
        "click_url":       click_url or None,
        "transcript":     transcript,
        "duration_sec": duration_sec or 0,
        "status":           status,
        "brand_safety_check": safety,
        "vast_xml":      vast_xml,
        "source":          "manual_upload",
        "created_at":   _now(),
    }
    await db.ad_creatives.insert_one(doc)
    # Phase 18b — telemetry.
    from services.telemetry import emit_event
    await emit_event(db, name="advertiser_creative_uploaded",
                              props={"source": "manual_upload",
                                        "verdict": verdict,
                                        "was_blocked": status == "rejected",
                                        "audio_length_sec": int(duration_sec or 15),
                                        "market": adv.get("market"),
                                        "issues": (safety or {}).get("issues") or []},
                              advertiser_id=advertiser_id, creative_id=cid)
    return {"creative_id": cid, "brand_safety_check": safety, "status": status,
              "audio_url": doc["audio_url"], "image_url": doc["image_url"]}


@advertiser_router.get("/{advertiser_id}/creatives")
async def list_creatives(advertiser_id: str, request: Request):
    await _require_staff(request, advertiser_id, "analyst")
    db = request.app.state.db
    docs = await db.ad_creatives.find(
        {"advertiser_id": advertiser_id}).sort([("created_at", -1)]).to_list(200)
    return {"items": [_clean(d) for d in docs]}


# ─── ffprobe helper (best-effort, returns None on failure) ──────────
def _ffprobe_duration(path: str) -> Optional[float]:
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
              "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip()) if r.stdout.strip() else None
    except Exception:
        return None
