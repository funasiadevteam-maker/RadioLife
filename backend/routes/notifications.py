"""Phase 41 Session 2.C.1 — Post-engagement notifications.

In-app surface only — no push, no email. The notification triggers
are fire-and-forget from `station_feed.py`: if the insert raises, the
originating mutation still succeeds.

Schema (`station_notifications`):
    {
      _id, owner_user_id, station_id, station_slug,
      type ("new_comment" | "post_reaction_milestone"),
      payload,
      related_post_id|null, related_comment_id|null,
      created_at, read_at|null,
      dedupe_key   # indexed unique + sparse
    }

Dedupe keys:
    "comment:{comment_id}"             — one ping per comment
    "milestone:{post_id}:{milestone}"  — one ping per (post, threshold)

The milestone scan uses `MILESTONES = (5, 25, 100)`. Triggers compute
the current total reaction count and `$setOnInsert` for every passed
milestone — duplicates are no-ops thanks to the unique sparse index.
"""
from __future__ import annotations
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user

router = APIRouter(prefix="/api/me/notifications",
                    tags=["notifications"])
log = logging.getLogger("bigfm.notifications")

MILESTONES = (5, 25, 100)
NOTIF_PAGE_SIZE_MAX = 50

# In-process cache for the unread_count endpoint (5 s).
_UNREAD_CACHE: dict = {}    # user_id -> {value:int, expires_at:float}
_UNREAD_TTL_SEC = 5.0


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str:  return _now().isoformat()


async def ensure_notification_indexes(db) -> None:
    """Best-effort idempotent index creation. Wraps each index call in
    its own try/except so a failure on one (e.g. spec drift) does NOT
    silently block subsequent ones (which previously caused the unique
    `notif_dedupe_unique` index to go missing whenever the recent-sort
    index touched a corrupted state during a hot-reload).

    All failures log the full exception class + message so a clean boot
    leaves a discoverable trail instead of a silent shrug.
    """
    specs = [
        # name                       args
        ("notif_owner_recent",  ([("owner_user_id", 1), ("created_at", -1)],), {}),
        ("notif_owner_unread",  ([("owner_user_id", 1), ("read_at", 1)],), {}),
        ("notif_dedupe_unique", ("dedupe_key",), {"unique": True, "sparse": True}),
    ]
    for name, args, kw in specs:
        try:
            await db.station_notifications.create_index(
                *args, name=name, **kw)
        except Exception as e:
            log.warning("[notifications] index %s ensure FAILED (%s): %s",
                        name, type(e).__name__, e)


# ----- enqueue helper (called from station_feed.py) ---------------
async def _enqueue(db, *, owner_user_id: str, station_id: str,
                    station_slug: str, type_: str, payload: dict,
                    dedupe_key: str,
                    related_post_id: Optional[str] = None,
                    related_comment_id: Optional[str] = None) -> bool:
    """Upsert by `dedupe_key`. Returns True if a new row was created."""
    nid = "notif_" + uuid.uuid4().hex[:14]
    doc_on_insert = {
        "_id":                nid,
        "owner_user_id":      owner_user_id,
        "station_id":         station_id,
        "station_slug":       station_slug,
        "type":               type_,
        "payload":            payload,
        "related_post_id":    related_post_id,
        "related_comment_id": related_comment_id,
        "created_at":         _now_iso(),
        "read_at":            None,
        "dedupe_key":         dedupe_key,
    }
    try:
        r = await db.station_notifications.update_one(
            {"dedupe_key": dedupe_key},
            {"$setOnInsert": doc_on_insert}, upsert=True)
        if r.upserted_id is not None:
            # Bust unread cache for this owner so the bell refreshes.
            _UNREAD_CACHE.pop(owner_user_id, None)
            return True
        return False
    except Exception as e:
        log.warning("[notifications] enqueue failed dedupe=%s: %s",
                    dedupe_key, e)
        return False


def _milestones_passed(total: int) -> list:
    return [m for m in MILESTONES if total >= m]


async def trigger_for_comment(db, station: dict, post: dict,
                                comment: dict, commenter: dict) -> None:
    """Fire-and-forget — never raises."""
    try:
        owner_id = station.get("owner_user_id")
        commenter_id = (commenter or {}).get("user_id")
        if not owner_id or owner_id == commenter_id:
            return
        excerpt = (comment.get("body") or "")[:80]
        await _enqueue(db,
            owner_user_id=owner_id,
            station_id=station["station_id"],
            station_slug=station["slug"],
            type_="new_comment",
            payload={
                "post_id":          post["post_id"],
                "comment_id":       comment["comment_id"],
                "commenter_user_id": commenter_id,
                "commenter_handle": (commenter.get("name")
                                      or commenter.get("email", "")
                                                  .split("@")[0]),
                "comment_excerpt":  excerpt,
                "station_name":     station.get("name") or station["slug"],
            },
            related_post_id=post["post_id"],
            related_comment_id=comment["comment_id"],
            dedupe_key=f"comment:{comment['comment_id']}")
    except Exception as e:
        log.warning("[notifications] trigger_for_comment failed: %s", e)


async def trigger_for_reaction(db, station: dict, post: dict,
                                 reactor: dict) -> None:
    """Fire-and-forget. Re-reads the post's current reaction totals and
    enqueues one notification per passed milestone — dedupe handles
    the "first time only" semantics."""
    try:
        owner_id = station.get("owner_user_id")
        reactor_id = (reactor or {}).get("user_id")
        if not owner_id or owner_id == reactor_id:
            log.debug("[notifications] trigger_for_reaction: owner-self skip "
                      "owner=%s reactor=%s post=%s",
                      owner_id, reactor_id, post.get("post_id"))
            return
        # Refresh totals from source-of-truth post doc.
        fresh = await db.station_posts.find_one(
            {"post_id": post["post_id"]},
            {"reaction_counts": 1, "_id": 0})
        counts = (fresh or {}).get("reaction_counts") or {}
        total = sum(int(v or 0) for v in counts.values())
        passed = _milestones_passed(total)
        log.info("[notifications] trigger_for_reaction CALLED post=%s "
                 "total=%s milestones_passed=%s",
                 post.get("post_id"), total, passed)
        for m in passed:
            await _enqueue(db,
                owner_user_id=owner_id,
                station_id=station["station_id"],
                station_slug=station["slug"],
                type_="post_reaction_milestone",
                payload={
                    "post_id":         post["post_id"],
                    "milestone":       m,
                    "total_reactions": total,
                    "station_name":    station.get("name") or station["slug"],
                },
                related_post_id=post["post_id"],
                dedupe_key=f"milestone:{post['post_id']}:{m}")
    except Exception as e:
        # Full traceback so future silent failures aren't invisible.
        log.exception("[notifications] trigger_for_reaction failed: %s", e)


# ----- HTTP endpoints ---------------------------------------------
def _serialize(n: dict) -> dict:
    out = {**n}
    out.pop("_id", None)
    out["id"] = n.get("_id") or n.get("id")
    return out


@router.get("")
async def list_notifications(request: Request, limit: int = 20,
                               before: Optional[str] = None,
                               unread_only: bool = False,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    q: dict = {"owner_user_id": user["user_id"]}
    if before:
        q["created_at"] = {"$lt": before}
    if unread_only:
        q["read_at"] = None
    cap = max(1, min(limit, NOTIF_PAGE_SIZE_MAX))
    rows = []
    async for n in db.station_notifications.find(q)\
            .sort("created_at", -1).limit(cap):
        rows.append(_serialize(n))
    return {"items": rows,
            "count": len(rows),
            "next_before": rows[-1]["created_at"] if rows else None}


@router.get("/unread_count")
async def unread_count(request: Request,
                         user: dict = Depends(current_user)):
    """5s in-process cache to dampen 60s-bell-poll burst load."""
    uid = user["user_id"]
    now = time.time()
    cached = _UNREAD_CACHE.get(uid)
    if cached and cached["expires_at"] > now:
        return {"count": cached["value"]}
    db = request.app.state.db
    c = await db.station_notifications.count_documents(
        {"owner_user_id": uid, "read_at": None})
    _UNREAD_CACHE[uid] = {"value": c, "expires_at": now + _UNREAD_TTL_SEC}
    return {"count": c}


@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.station_notifications.update_one(
        {"_id": notif_id, "owner_user_id": user["user_id"],
         "read_at": None},
        {"$set": {"read_at": _now_iso()}})
    _UNREAD_CACHE.pop(user["user_id"], None)
    if r.matched_count == 0:
        # Could already be read or not owned by caller — both are
        # idempotent from the caller's POV.
        return {"ok": True, "already_read": True}
    return {"ok": True}


@router.post("/read_all")
async def mark_all_read(request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    r = await db.station_notifications.update_many(
        {"owner_user_id": user["user_id"], "read_at": None},
        {"$set": {"read_at": _now_iso()}})
    _UNREAD_CACHE.pop(user["user_id"], None)
    return {"ok": True, "marked": r.modified_count}
