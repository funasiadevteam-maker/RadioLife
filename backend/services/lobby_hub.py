"""Phase 7 — In-process WebSocket pub/sub hub for lobbies.

Single source of truth for which WebSocket connections belong to which lobby.
Used by both the WS endpoint (registering / unregistering its own socket) and
the REST/lobby business logic (broadcasting events on join/leave/skip/etc).

TODO(scale): multi-pod horizontal scaling needs a real pub/sub fan-out layer
across processes (Mongo change streams piped into each pod, or NATS, or
Redis Streams). Single-pod is fine for the MVP. The function signatures here
are deliberately narrow so swapping the in-memory impl for a network-fan-out
impl later is a contained change.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger("bigfm.lobby.hub")


class LobbyHub:
    """One process-wide instance, attached to `app.state.lobby_hub`.

    Maps lobby_id → set of active WebSocket connections + a lock per lobby
    so segment-advance loops don't trample concurrent join broadcasts.
    """
    def __init__(self):
        self._conns: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._user_index: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # Per-lobby segment-advance background task — one per live lobby.
        self._advance_tasks: Dict[str, asyncio.Task] = {}

    async def register(self, lobby_id: str, user_id: str, ws: WebSocket) -> None:
        async with self._locks[lobby_id]:
            self._conns[lobby_id].add(ws)
            self._user_index[lobby_id][user_id] = ws

    async def unregister(self, lobby_id: str, user_id: str, ws: WebSocket) -> None:
        async with self._locks[lobby_id]:
            self._conns[lobby_id].discard(ws)
            if self._user_index[lobby_id].get(user_id) is ws:
                self._user_index[lobby_id].pop(user_id, None)
            if not self._conns[lobby_id]:
                self._conns.pop(lobby_id, None)
                self._user_index.pop(lobby_id, None)

    def connection_count(self, lobby_id: str) -> int:
        return len(self._conns.get(lobby_id, set()))

    def user_socket(self, lobby_id: str, user_id: str) -> Optional[WebSocket]:
        return self._user_index.get(lobby_id, {}).get(user_id)

    async def broadcast(self, lobby_id: str, message: Dict[str, Any],
                          exclude_user_id: Optional[str] = None) -> None:
        """Fan-out to every socket in the lobby. Drops dead sockets silently."""
        targets = list(self._conns.get(lobby_id, set()))
        if not targets:
            return
        payload = json.dumps(message, default=str)
        dead = []
        for ws in targets:
            if exclude_user_id:
                # Find the user_id mapped to this socket
                try:
                    idx = self._user_index.get(lobby_id, {})
                    uid = next((u for u, w in idx.items() if w is ws), None)
                    if uid == exclude_user_id:
                        continue
                except Exception:
                    pass
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._locks[lobby_id]:
                for ws in dead:
                    self._conns.get(lobby_id, set()).discard(ws)
                    # Best-effort clean of user index
                    idx = self._user_index.get(lobby_id, {})
                    to_drop = [u for u, w in idx.items() if w in dead]
                    for u in to_drop: idx.pop(u, None)

    async def send_to_user(self, lobby_id: str, user_id: str,
                             message: Dict[str, Any]) -> bool:
        ws = self.user_socket(lobby_id, user_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps(message, default=str))
            return True
        except Exception:
            return False

    def claim_advance_task(self, lobby_id: str) -> bool:
        """Returns True iff this caller is now responsible for the lobby's
        segment-advance loop (caller should `asyncio.create_task` and pass it
        to `set_advance_task`)."""
        existing = self._advance_tasks.get(lobby_id)
        if existing and not existing.done():
            return False
        return True

    def set_advance_task(self, lobby_id: str, task: asyncio.Task) -> None:
        self._advance_tasks[lobby_id] = task

    def cancel_advance_task(self, lobby_id: str) -> None:
        t = self._advance_tasks.pop(lobby_id, None)
        if t and not t.done():
            t.cancel()


# Rate limiter — token bucket per WS connection, narrow surface
class TokenBucket:
    """Thread-unsafe (single asyncio loop), per-connection bucket."""
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill = refill_per_sec
        self.tokens = float(capacity)
        self.last = time.monotonic()

    def take(self, cost: int = 1) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill)
        self.last = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
