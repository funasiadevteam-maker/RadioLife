"""FUUSIC Fun AI — Phase 1 Interactive News voice pilot.

Mounts under ``/api/fun-ai``. The permanent xAI key stays server-side; clients
receive only short-lived ephemeral client secrets. Feature-flag gated, with a
graceful fallback to the existing News Radio TTS program when voice is off or
unavailable. Radio-first: the only model tool is source-grounded news search.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import current_user, current_user_optional, require_admin
from services import fun_ai_service as svc
from services import fun_ai_radio_policy as policy
from services.grok_realtime import (grok_voice, is_configured, mint_client_secret,
                                     voice_model, ws_url)
from services.news_radio_settings import get_anchor_voice

log = logging.getLogger("fuusic.fun_ai")

router = APIRouter(prefix="/api/fun-ai", tags=["fun-ai"])
admin_router = APIRouter(prefix="/api/admin/fun-ai", tags=["admin-fun-ai"])


def _uid(user: dict) -> str:
    return user.get("user_id") or user.get("id") or str(user.get("_id") or "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/config")
async def fun_ai_config(request: Request,
                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    f = svc.flags()
    sponsor = await svc.get_sponsor(db)
    return {
        **f,
        "sponsor": {
            "enabled": bool(sponsor.get("enabled") and f["sponsorship_enabled"]),
            "sponsor_name": sponsor.get("sponsor_name"),
            "opening_line": sponsor.get("opening_line") if f["sponsorship_enabled"] else "",
        },
        "voice_available": bool(f["enabled"] and f["configured"]),
        "personalities": svc.list_personalities(),
        "default_personality": svc.DEFAULT_PERSONALITY,
        "modes": svc.list_modes(),
        "default_mode": svc.DEFAULT_MODE,
        "signed_in": bool(user),
    }


class SessionStartBody(BaseModel):
    mode: Optional[str] = None
    topic: Optional[str] = Field(default=None, max_length=160)
    surface: Optional[str] = None          # "news" (default) | "player"
    station: Optional[dict] = None         # player surface: {slug, name, type}


@router.post("/session")
async def create_session(request: Request,
                         body: Optional[SessionStartBody] = None,
                         user: dict = Depends(current_user)):
    body = body or SessionStartBody()
    db = request.app.state.db
    f = svc.flags()
    if not f["enabled"]:
        raise HTTPException(403, detail={"code": "fun_ai_disabled",
                                         "message": "Fun AI is not enabled yet."})
    if not is_configured():
        raise HTTPException(503, detail={
            "code": "voice_unconfigured",
            "message": "Voice is not configured — the standard news program still plays."})
    uid = _uid(user)
    used = await svc.usage_today(db, uid)
    allow = svc.allowance_minutes(user)
    if used["sessions"] >= svc.max_sessions_per_day():
        raise HTTPException(429, detail={"code": "session_limit",
                                         "message": "Daily session limit reached."})
    if used["voice_seconds"] >= allow * 60:
        raise HTTPException(429, detail={"code": "quota_exceeded",
                                         "allowance_minutes": allow,
                                         "message": "Daily voice minutes used up."})
    try:
        secret = await mint_client_secret(f["session_seconds"])
    except Exception as e:  # pragma: no cover - network path
        log.warning("[fun_ai] mint failed: %s", e)
        raise HTTPException(502, detail={"code": "mint_failed",
                                         "message": "Could not start a voice session."})
    await svc.record_session_start(db, uid)
    sponsor = await svc.get_sponsor(db)
    voice = await get_anchor_voice(db)
    surface = (body.surface or "news").lower()
    mode = body.mode if (body.mode in svc.MODES) else svc.DEFAULT_MODE
    prefs = await svc.get_prefs(db, uid)
    pid = prefs.get("personality") or svc.DEFAULT_PERSONALITY
    persona = svc.personality_instructions(pid)
    mem_instr = svc.memory_instructions(await svc.get_memory(db, uid))

    if surface == "player":
        station = body.station or {}
        st_type = await policy.resolve_station_type(db, station)
        instructions = svc.player_anchor_instructions(
            voice_name=voice.get("name", "the RJ"),
            station_name=station.get("name") or "this station",
            station_type=st_type)
        tools = svc.player_tools_spec()
        mode_label = station.get("name") or "FUUSIC Radio"
    else:
        instructions = svc.anchor_instructions(
            voice_name=voice.get("name", "the anchor"),
            sponsor=sponsor, sponsorship_enabled=f["sponsorship_enabled"]
        ) + svc.mode_instructions(mode, body.topic)
        try:  # open with verified updates on the listener's followed stories
            fups = await svc.follow_updates(db, uid, limit_topics=3, per=1)
            instructions += svc.follows_opening(fups)
        except Exception:
            pass
        tools = svc.tools_spec()
        mode_label = svc.MODES[mode]["label"]

    ins = await db.fun_ai_sessions.insert_one({
        "user_id": uid, "started_at": _now_iso(),
        "provider": f["voice_provider"], "model": f["voice_model"],
        "surface": surface, "mode": mode, "topic": body.topic,
        "station": body.station, "personality": pid})
    return {
        "client_secret": secret["value"],
        "expires_at": secret["expires_at"],
        "ws_url": ws_url(),
        "model": voice_model(),
        "session_id": str(ins.inserted_id),
        "voice": grok_voice(),
        "surface": surface,
        "mode": mode,
        "mode_label": mode_label,
        "personality": pid,
        "personality_label": svc.PERSONALITIES[pid]["label"],
        "instructions": f"{persona} {instructions}{mem_instr}",
        "tools": tools,
        "allowance_minutes": allow,
        "used": used,
    }


class EndBody(BaseModel):
    session_id: Optional[str] = None
    voice_seconds: int = Field(default=0, ge=0, le=3600)


@router.post("/session/end")
async def end_session(body: EndBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = _uid(user)
    await svc.record_voice_seconds(db, uid, body.voice_seconds)
    if body.session_id:
        try:
            from bson import ObjectId
            await db.fun_ai_sessions.update_one(
                {"_id": ObjectId(body.session_id)},
                {"$set": {"ended_at": _now_iso(),
                          "voice_seconds": body.voice_seconds}})
        except Exception:
            pass
    return {"ok": True}


@router.get("/news/briefing")
async def news_briefing(request: Request,
                        mode: str = Query(svc.DEFAULT_MODE),
                        topic: Optional[str] = Query(None),
                        limit: Optional[int] = Query(None, ge=1, le=20),
                        market: Optional[str] = Query(None),
                        user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    f = svc.flags()
    if not f["news_enabled"]:
        raise HTTPException(403, detail={"code": "news_disabled"})
    m = mode if mode in svc.MODES else svc.DEFAULT_MODE
    if svc.MODES[m].get("local") and not market and user:
        market = user.get("market")
    data = await svc.build_briefing(db, mode=m, market=market, topic=topic, limit=limit)
    if not f["sponsorship_enabled"]:
        data["sponsor"] = {**svc.DEFAULT_SPONSOR}
    data["voice_available"] = bool(f["enabled"] and f["configured"])
    data["breaks"] = await svc.build_breaks(
        db, user=user or {}, sponsor=data.get("sponsor") or {},
        program_count=int(data.get("count") or 0),
        sponsorship_enabled=f["sponsorship_enabled"])
    return data


class SearchBody(BaseModel):
    query: str = Field(default="", max_length=240)
    category: Optional[str] = None


@router.post("/news/search")
async def news_search(body: SearchBody, request: Request,
                      user: dict = Depends(current_user)):
    """Tool endpoint relayed by the realtime client on a Grok function call."""
    db = request.app.state.db
    uid = _uid(user)
    arts = await svc.search_news(db, query=body.query, category=body.category)
    await db.fun_ai_tool_audit.insert_one({
        "user_id": uid, "tool": "search_news",
        "query": (body.query or "")[:240], "category": body.category,
        "count": len(arts), "at": _now_iso()})
    return {"ok": True, "articles": arts, "count": len(arts),
            "disclaimer": ("Verified from FUUSIC news sources. Any claim not "
                           "listed here is not confirmed.")}


# ─── RJ personality preferences ────────────────────────────────────────
class PrefsBody(BaseModel):
    personality: Optional[str] = None


@router.get("/preferences")
async def get_preferences(request: Request, user: dict = Depends(current_user)):
    prefs = await svc.get_prefs(request.app.state.db, _uid(user))
    return {**prefs, "personalities": svc.list_personalities()}


@router.put("/preferences")
async def put_preferences(body: PrefsBody, request: Request,
                          user: dict = Depends(current_user)):
    prefs = await svc.set_prefs(request.app.state.db, _uid(user),
                                personality=body.personality)
    return {"ok": True, **prefs}


# ─── Companion Memory ──────────────────────────────────────────────────
class MemToggleBody(BaseModel):
    enabled: bool = True


class MemItemBody(BaseModel):
    kind: str = Field(max_length=20)
    value: str = Field(default="", max_length=60)


@router.get("/memory")
async def get_memory_ep(request: Request, user: dict = Depends(current_user)):
    return await svc.get_memory(request.app.state.db, _uid(user))


@router.put("/memory")
async def put_memory_ep(body: MemToggleBody, request: Request,
                        user: dict = Depends(current_user)):
    return {"ok": True, **(await svc.set_memory_enabled(
        request.app.state.db, _uid(user), body.enabled))}


@router.post("/memory")
async def add_memory_ep(body: MemItemBody, request: Request,
                        user: dict = Depends(current_user)):
    out = await svc.add_memory_item(request.app.state.db, _uid(user),
                                    body.kind, body.value)
    if out is None:
        raise HTTPException(400, detail={"code": "invalid_memory"})
    return {"ok": True, **out}


@router.post("/memory/remove")
async def remove_memory_ep(body: MemItemBody, request: Request,
                           user: dict = Depends(current_user)):
    return {"ok": True, **(await svc.remove_memory_item(
        request.app.state.db, _uid(user), body.kind, body.value))}


@router.post("/memory/clear")
async def clear_memory_ep(request: Request, user: dict = Depends(current_user)):
    return {"ok": True, **(await svc.clear_memory(request.app.state.db, _uid(user)))}


# ─── Sponsor break impression / completion tracking ────────────────────
class BreakEventBody(BaseModel):
    break_id: Optional[str] = None
    kind: str = "impression"
    sponsored_read_id: Optional[str] = None
    placement: Optional[str] = None


@router.post("/news/break-event")
async def break_event(body: BreakEventBody, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = _uid(user)
    await db.fun_ai_sponsor_events.insert_one({
        "user_id": uid, "break_id": body.break_id, "kind": body.kind,
        "placement": body.placement, "sponsored_read_id": body.sponsored_read_id,
        "at": _now_iso()})
    if body.sponsored_read_id and body.kind == "impression":
        try:  # live paid read → decrement budget via the existing ad service
            from services import rj_sponsored_read_service as rj
            await rj.record_play(db, sponsored_read_id=body.sponsored_read_id,
                                 station_id=svc.NEWS_STATION_ID, user_id=uid)
        except Exception:
            pass
    return {"ok": True}


# ─── Follow This Story ─────────────────────────────────────────────────
class FollowBody(BaseModel):
    topic: str = Field(max_length=160)
    title: Optional[str] = Field(default=None, max_length=200)


@router.get("/follows")
async def get_follows(request: Request, user: dict = Depends(current_user)):
    return {"follows": await svc.list_follows(request.app.state.db, _uid(user))}


@router.post("/follows")
async def post_follow(body: FollowBody, request: Request,
                      user: dict = Depends(current_user)):
    fo = await svc.add_follow(request.app.state.db, _uid(user), body.topic, body.title)
    if not fo:
        raise HTTPException(400, detail={"code": "empty_topic"})
    return {"ok": True, "follow": fo}


@router.delete("/follows/{follow_id}")
async def delete_follow(follow_id: str, request: Request,
                        user: dict = Depends(current_user)):
    ok = await svc.remove_follow(request.app.state.db, _uid(user), follow_id)
    return {"ok": ok}


@router.get("/follows/updates")
async def get_follow_updates(request: Request, user: dict = Depends(current_user)):
    return {"topics": await svc.follow_updates(request.app.state.db, _uid(user))}


# ─── Phase 2: Talk on the Player (radio voice control) ─────────────────
@router.get("/radio/formats")
async def radio_formats(user: Optional[dict] = Depends(current_user_optional)):
    return {"formats": policy.FORMATS}


@router.get("/radio/now-playing")
async def radio_now_playing(request: Request,
                            station: Optional[str] = Query(None),
                            name: Optional[str] = Query(None),
                            user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    ch = await db.channels.find_one({"slug": station}) if station else None
    st_type = await policy.resolve_station_type(db, {"slug": station}) if station else "managed"
    return {
        "station": station,
        "station_name": (ch or {}).get("name") or name or station or "FUUSIC Radio",
        "station_type": st_type,
        "genre": (ch or {}).get("music_genre"),
        "program": None,
        "note": ("This is live radio — the exact current track may be unavailable; "
                 "share the station and offer artist info or a format change."),
    }


class RadioActionBody(BaseModel):
    action: str = Field(max_length=40)
    params: dict = Field(default_factory=dict)
    station: dict = Field(default_factory=dict)


@router.post("/radio/action")
async def radio_action(body: RadioActionBody, request: Request,
                       user: dict = Depends(current_user)):
    """Policy-gated radio action relayed by the realtime client on a tool call.
    The model is NOT the authority — RadioProgrammingPolicyService decides."""
    db = request.app.state.db
    uid = _uid(user)
    decision = await policy.evaluate(db, user_id=uid, action=body.action,
                                     params=body.params, station=body.station)
    await db.fun_ai_radio_actions.insert_one({
        "user_id": uid, "action": (body.action or "").strip().lower(),
        "allowed": decision["allowed"], "code": decision.get("code"),
        "station_type": decision.get("station_type"), "at": _now_iso()})
    # Persist permitted programming directives as the listener's radio prefs.
    if decision["allowed"] and decision.get("applied"):
        sets = {f"prefs.{k}": v for k, v in decision["applied"].items() if v}
        if sets:
            sets["updated_at"] = _now_iso()
            await db.fun_ai_radio_prefs.update_one({"user_id": uid},
                {"$set": sets}, upsert=True)
    return decision


class RadioUndoBody(BaseModel):
    fields: list = Field(default_factory=list)


@router.post("/radio/undo")
async def radio_undo(body: RadioUndoBody, request: Request,
                     user: dict = Depends(current_user)):
    """Revert the programming directives just applied (clears those prefs)."""
    db = request.app.state.db
    uid = _uid(user)
    unset = {f"prefs.{k}": "" for k in body.fields
             if isinstance(k, str) and k.isidentifier()}
    if unset:
        await db.fun_ai_radio_prefs.update_one({"user_id": uid}, {"$unset": unset})
    await db.fun_ai_radio_actions.insert_one({
        "user_id": uid, "action": "undo", "allowed": True, "code": "UNDO",
        "fields": list(unset.keys()), "at": _now_iso()})
    return {"ok": True, "undone": list(unset.keys())}




@router.get("/usage")
async def usage(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    used = await svc.usage_today(db, _uid(user))
    allow = svc.allowance_minutes(user)
    return {
        "allowance_minutes": allow,
        "used_minutes": round(used["voice_seconds"] / 60, 1),
        "used_seconds": used["voice_seconds"],
        "sessions_today": used["sessions"],
        "max_sessions": svc.max_sessions_per_day(),
        "is_premium": bool(user.get("is_premium")),
    }


# ─── admin: sponsor acknowledgement (approved copy) ────────────────────
@admin_router.get("/news-sponsor")
async def get_news_sponsor(request: Request, _a: dict = Depends(require_admin)):
    return {"sponsor": await svc.get_sponsor(request.app.state.db)}


class SponsorBody(BaseModel):
    enabled: bool = False
    sponsor_name: str = Field(default="", max_length=80)
    opening_line: str = Field(default="", max_length=240)
    closing_line: str = Field(default="", max_length=240)
    opening_enabled: bool = True
    closing_enabled: bool = True
    mid_enabled: bool = False
    mid_line: str = Field(default="", max_length=240)
    mid_after_segment: int = 3
    premium_ad_free: bool = True


@admin_router.put("/news-sponsor")
async def put_news_sponsor(body: SponsorBody, request: Request,
                           _a: dict = Depends(require_admin)):
    s = await svc.set_sponsor(request.app.state.db, body.dict())
    return {"ok": True, "sponsor": s}


@admin_router.get("/break-report")
async def get_break_report(request: Request,
                           days: int = Query(30, ge=1, le=365),
                           _a: dict = Depends(require_admin)):
    """Sponsor-break impressions (by placement) + paid-spot spend."""
    return await svc.break_report(request.app.state.db, days=days)



# ─── admin: radio programming policy ───────────────────────────────────
@admin_router.get("/radio-policy")
async def get_radio_policy(request: Request, _a: dict = Depends(require_admin)):
    return {"policy": await policy.get_policy(request.app.state.db),
            "formats": policy.FORMATS}


class RadioPolicyBody(BaseModel):
    on_demand_allowed: Optional[bool] = None
    managed_allowed_actions: Optional[list] = None
    third_party_allowed_actions: Optional[list] = None
    skip_per_hour: Optional[int] = None
    jurisdiction: Optional[str] = None


@admin_router.put("/radio-policy")
async def put_radio_policy(body: RadioPolicyBody, request: Request,
                           _a: dict = Depends(require_admin)):
    patch = {k: v for k, v in body.dict().items() if v is not None}
    saved = await policy.set_policy(request.app.state.db, patch)
    return {"ok": True, "policy": saved}
