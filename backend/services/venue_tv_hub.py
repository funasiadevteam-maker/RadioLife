"""
Phase 16c — TV hub for venue displays.

In-process pub/sub for `/api/tv/ws`.  Mirrors the trivia RoomHub
pattern but is keyed by venue_id (one TV → many rooms over its
lifetime).  Lives entirely in memory: a venue can have several
paired TVs, each holding one WebSocket; broadcasts hit them all.

Also routes venue announcement broadcasts to player phone WS via
the trivia RoomHub (TV+phones see the same toast).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, List, Set, Optional

from fastapi import WebSocket

logger = logging.getLogger("bigfm.venue.tv_hub")


class TVHub:
    """In-memory venue → TV WebSocket index."""

    def __init__(self) -> None:
        self._sockets: Dict[str, Dict[str, WebSocket]] = {}  # venue_id → {tv_id: ws}
        self._lock                                        = asyncio.Lock()

    def attach(self, venue_id: str, tv_id: str, ws: WebSocket) -> None:
        self._sockets.setdefault(venue_id, {})[tv_id] = ws

    def detach(self, venue_id: str, tv_id: str, ws: WebSocket) -> None:
        bucket = self._sockets.get(venue_id) or {}
        if bucket.get(tv_id) is ws:
            bucket.pop(tv_id, None)

    def tvs_for(self, venue_id: str) -> List[str]:
        return list((self._sockets.get(venue_id) or {}).keys())

    async def broadcast(self, venue_id: str, message: dict) -> None:
        bucket = dict(self._sockets.get(venue_id) or {})
        if not bucket:
            return
        payload = json.dumps(message, default=str)
        for tv_id, ws in bucket.items():
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.warning("[tv_hub] send to %s/%s failed: %s", venue_id, tv_id, e)

    async def send_to(self, venue_id: str, tv_id: str, message: dict) -> bool:
        ws = (self._sockets.get(venue_id) or {}).get(tv_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps(message, default=str))
            return True
        except Exception as e:
            logger.warning("[tv_hub] direct send %s/%s failed: %s", venue_id, tv_id, e)
            return False

    async def revoke(self, venue_id: str, tv_id: str) -> bool:
        """Send `tv_revoked` then close the socket with code 4001."""
        ws = (self._sockets.get(venue_id) or {}).get(tv_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps({"type": "tv_revoked",
                                                "reason": "revoked_by_staff",
                                                "revoked_at": int(time.time() * 1000)}))
        except Exception as e:
            logger.warning("[tv_hub] revoke notify failed: %s", e)
        try:
            await ws.close(code=4001, reason="revoked")
        except Exception:
            pass
        bucket = self._sockets.get(venue_id) or {}
        if bucket.get(tv_id) is ws:
            bucket.pop(tv_id, None)
        return True
