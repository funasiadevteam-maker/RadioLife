"""
Phase 16b — Multiplayer trivia rooms.

In-process room registry + WebSocket pub/sub hub.  Mirrors the
`services/lobby_hub.py` pattern so a future swap to Redis pub/sub (for
horizontal scale) is a contained change — every fan-out path here goes
through `RoomHub.broadcast()`.

The Room state machine (host = first player):
    lobby   → host pressed Start ⇒ generate 10 Qs ⇒ question[0]
    question→ 15-s server timer per Q (or all answered) ⇒ reveal
    reveal  → 4 s ⇒ leaderboard
    leaderboard → 4 s ⇒ next question OR done if i == 9
    done    → final scoreboard + BC awards
                room TTL of 5 min then GC'd from the registry.

Server is the authority on:
    • room phase + question_started_at + deadlines
    • answer correctness, latency, point award
    • multiplayer first-correct bonuses (+100 / +75 / +50)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
import string
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("bigfm.trivia.rooms")

# Phase 16b — room-code alphabet excludes ambiguous chars.
ROOM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/l
ROOM_CODE_LEN     = 6
ROOM_CODE_PREFIX = "BFM-"

# Phase timings (seconds).  Tunable per market later; constants for now.
QUESTION_DURATION_SEC   = 15
REVEAL_DURATION_SEC     = 4
LEADERBOARD_DURATION_SEC = 4
ROOM_GC_TTL_SEC          = 300            # 5 min after `done`
MAX_PLAYERS_DEFAULT     = 20

# Multiplayer first-correct-arrival bonuses (on top of the 16a base score).
FIRST_CORRECT_BONUSES = [100, 75, 50]


def generate_room_code() -> str:
    """6-char alphanumeric code, ambiguity-free.  Caller is responsible
    for collision checks against the live registry — caller retries on
    collision."""
    body = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LEN))
    return f"{ROOM_CODE_PREFIX}{body}"


@dataclass
class PlayerState:
    user_id:    str
    name:       str
    avatar:     Optional[str] = None
    score:      int            = 0
    rank:       int            = 0
    joined_at: datetime       = field(default_factory=lambda: datetime.now(timezone.utc))
    answers:   Dict[str, dict] = field(default_factory=dict)   # qid → {choice_id, latency_ms, correct, points}
    ws:         Optional[WebSocket] = None     # active socket (None when disconnected)

    def to_public(self) -> dict:
        return {
            "user_id": self.user_id,
            "name":     self.name,
            "avatar":   self.avatar,
            "score":    self.score,
            "rank":     self.rank,
            "connected": self.ws is not None,
        }


@dataclass
class Room:
    code:          str
    host_user_id: str
    category_id:  str
    category_slug: str
    market:        str
    is_private:    bool             = False
    max_players:  int              = MAX_PLAYERS_DEFAULT
    players:       Dict[str, PlayerState] = field(default_factory=dict)
    questions:    List[dict]        = field(default_factory=list)  # full Q docs (with correct_choice_id)
    current_index: int               = -1
    phase:         str               = "lobby"  # lobby|question|reveal|leaderboard|done
    question_started_at: Optional[datetime] = None
    phase_deadline_at:   Optional[datetime] = None
    correct_order:        List[str]   = field(default_factory=list)  # user_ids in correct-answer arrival order, current Q
    created_at:    datetime          = field(default_factory=lambda: datetime.now(timezone.utc))
    done_at:       Optional[datetime] = None
    advance_task: Optional[asyncio.Task] = None
    venue_id:      Optional[str]      = None   # Phase 16c — venue-branded room
    # Phase H — AD.5 trivia sponsorship binding (optional).  Populated
    # at room create time when the host supplies a valid sponsorship_id.
    sponsorship_id:                Optional[str]  = None
    sponsorship_display_name:  Optional[str]  = None
    sponsorship_tagline:          Optional[str]  = None
    sponsorship_logo_url:      Optional[str]  = None
    sponsorship_prize_pool_public: Optional[List[Dict[str, Any]]] = None

    def current_question(self) -> Optional[dict]:
        if 0 <= self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None

    def public_question(self) -> Optional[dict]:
        q = self.current_question()
        if not q:
            return None
        # Strip correct_choice_id before exposing to clients.
        return {
            "id":         q["id"],
            "prompt":     q["prompt"],
            "choices":    q["choices"],
            "category":   q.get("category"),
            "difficulty": q.get("difficulty"),
        }

    def leaderboard(self, top: int = 5) -> List[dict]:
        ordered = sorted(self.players.values(), key=lambda p: -p.score)
        for i, p in enumerate(ordered):
            p.rank = i + 1
        return [p.to_public() for p in ordered[:top]]

    def to_public(self) -> dict:
        return {
            "code":         self.code,
            "host_user_id": self.host_user_id,
            "category_id":  self.category_id,
            "category_slug": self.category_slug,
            "market":       self.market,
            "is_private":   self.is_private,
            "max_players":  self.max_players,
            "phase":        self.phase,
            "current_index": self.current_index,
            "total_questions": len(self.questions),
            "players":     [p.to_public() for p in self.players.values()],
            "deadline_ms":  int(self.phase_deadline_at.timestamp() * 1000)
                              if self.phase_deadline_at else None,
            "question":    self.public_question() if self.phase == "question" else None,
            "created_at":  self.created_at.isoformat(),
            "done":         self.phase == "done",
            # Phase H — expose sponsorship binding to WebSocket clients.
            "sponsorship": (
                {"sponsorship_id":  self.sponsorship_id,
                  "display_name":      self.sponsorship_display_name,
                  "tagline":              self.sponsorship_tagline,
                  "logo_url":            self.sponsorship_logo_url,
                  "prize_pool_public": self.sponsorship_prize_pool_public or []}
                if self.sponsorship_id else None),
        }


class RoomHub:
    """In-process registry + WebSocket pub/sub.  Singleton instance
    attached to `app.state.trivia_room_hub`.
    """
    def __init__(self):
        self._rooms: Dict[str, Room] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._gc_task: Optional[asyncio.Task] = None

    def get(self, code: str) -> Optional[Room]:
        return self._rooms.get(code)

    def all_rooms(self) -> Dict[str, Room]:
        return dict(self._rooms)

    async def create(self, *, host_user: dict, category_id: str,
                       category_slug: str, market: str,
                       is_private: bool = False,
                       max_players: int = MAX_PLAYERS_DEFAULT,
                       sponsorship: Optional[Dict[str, Any]] = None) -> Room:
        # Collision-retry on the 6-char body — the alphabet has 31 chars,
        # so a single collision in <1M concurrent rooms is the practical
        # cap.  Retry budget of 10 is way more than enough.
        for _ in range(10):
            code = generate_room_code()
            if code not in self._rooms:
                break
        else:
            raise RuntimeError("Could not allocate a unique room code")

        room = Room(
            code=code,
            host_user_id=host_user["user_id"],
            category_id=category_id,
            category_slug=category_slug,
            market=market,
            is_private=is_private,
            max_players=max_players,
        )
        # Phase H — bind sponsorship metadata (safe subset only — the
        # advertiser_business_id + Stripe internals stay server-side).
        if sponsorship:
            room.sponsorship_id                          = sponsorship.get("sponsorship_id")
            room.sponsorship_display_name          = sponsorship.get("display_name")
            room.sponsorship_tagline                  = sponsorship.get("tagline")
            room.sponsorship_logo_url                  = sponsorship.get("logo_url")
            room.sponsorship_prize_pool_public  = sponsorship.get("prize_pool_public")
        # Host auto-joins as a player.
        room.players[host_user["user_id"]] = PlayerState(
            user_id=host_user["user_id"],
            name=(host_user.get("name") or "Host"),
            avatar=host_user.get("avatar"),
        )
        self._rooms[code] = room
        logger.info("[room.create] code=%s host=%s cat=%s mkt=%s sp=%s",
                      code, host_user["user_id"], category_slug, market,
                      room.sponsorship_id or "none")
        return room

    async def add_player(self, code: str, user: dict) -> Room:
        async with self._locks[code]:
            room = self._rooms.get(code)
            if not room:
                raise KeyError("room_not_found")
            if room.phase != "lobby":
                raise PermissionError("room_in_progress")
            if user["user_id"] in room.players:
                return room
            if len(room.players) >= room.max_players:
                raise PermissionError("room_full")
            room.players[user["user_id"]] = PlayerState(
                user_id=user["user_id"],
                name=(user.get("name") or "Player"),
                avatar=user.get("avatar"),
            )
            return room

    async def remove_player(self, code: str, user_id: str) -> None:
        async with self._locks[code]:
            room = self._rooms.get(code)
            if not room:
                return
            room.players.pop(user_id, None)
            # If the host left in lobby, kill the room.
            if room.phase == "lobby" and user_id == room.host_user_id:
                self._rooms.pop(code, None)
                if room.advance_task:
                    room.advance_task.cancel()

    async def kick(self, code: str, user_id: str) -> bool:
        """Notify the kicked user (targeted `kicked` frame + clean close
        with code 4001) BEFORE we evict them from the player dict, then
        broadcast `player_left` to everyone who's still there.  Returns
        True if the user was a current member, False otherwise."""
        room = self._rooms.get(code)
        if not room:
            return False
        victim = room.players.get(user_id)
        was_member = victim is not None
        victim_ws = victim.ws if victim else None
        if victim_ws is not None:
            payload = {
                "type":      "kicked",
                "reason":    "removed_by_host",
                "room_code": code,
                "kicked_at": int(time.time() * 1000),
            }
            try:
                await victim_ws.send_text(json.dumps(payload))
            except Exception as e:
                logger.warning("[hub.kick] notify failed %s: %s", user_id, e)
            try:
                # WebSocket spec: 4001 is in the private-use range.
                await victim_ws.close(code=4001, reason="kicked")
            except Exception as e:
                logger.warning("[hub.kick] close failed %s: %s", user_id, e)
        await self.remove_player(code, user_id)
        await self.broadcast(code, {
            "type":     "player_left",
            "user_id":  user_id,
            "reason":   "kicked",
        })
        return was_member

    def attach_socket(self, code: str, user_id: str, ws: WebSocket) -> None:
        room = self._rooms.get(code)
        if not room or user_id not in room.players:
            return
        room.players[user_id].ws = ws

    def detach_socket(self, code: str, user_id: str, ws: WebSocket) -> None:
        room = self._rooms.get(code)
        if not room or user_id not in room.players:
            return
        if room.players[user_id].ws is ws:
            room.players[user_id].ws = None

    async def broadcast(self, code: str, message: dict) -> None:
        room = self._rooms.get(code)
        if not room:
            return
        payload = json.dumps(message, default=str)
        for p in list(room.players.values()):
            ws = p.ws
            if not ws:
                continue
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning("[room.broadcast] drop %s: %s", p.user_id, e)
                p.ws = None

    async def send_to(self, code: str, user_id: str, message: dict) -> None:
        room = self._rooms.get(code)
        if not room:
            return
        p = room.players.get(user_id)
        if not p or not p.ws:
            return
        try:
            await p.ws.send_text(json.dumps(message, default=str))
        except Exception:
            p.ws = None

    def gc_now(self) -> int:
        """Drop rooms whose `done_at` is older than ROOM_GC_TTL_SEC."""
        now = datetime.now(timezone.utc)
        dropped = []
        for code, room in list(self._rooms.items()):
            if room.done_at and (now - room.done_at).total_seconds() > ROOM_GC_TTL_SEC:
                dropped.append(code)
        for code in dropped:
            r = self._rooms.pop(code, None)
            if r and r.advance_task:
                r.advance_task.cancel()
        return len(dropped)
