"""Terrestrial Radio Station Probe Service — Phase RELIABILITY.P2.

Async background health-probe worker for `imported_radio_stations`.

Goals:
- Keep dead streams out of the browse feed so users never click a
  station that plays nothing.
- Never probe on the request path (all probes run as background
  asyncio tasks).
- Cap global concurrency at 8 + per-host at 1 so we don't hammer
  upstream Icecast/Shoutcast providers.
- Idempotent: safe to run cold_fill_task on every boot and
  scheduled_loop forever without duplicating work.

Blend schema (extends the existing `imported_radio_stations` doc):

    stream_health_status  : "unknown" | "alive" | "dead"
                            (was: "unknown" | "ok" | "down" from the
                             legacy Radio-Browser health_check_top_stations,
                             which is retained for backwards compat but
                             our writers now use "alive"/"dead"/"unknown"
                             exclusively).
    hostname              : lowercased hostname parsed from url_resolved,
                            written once for cheap SSRF/allowlist joins.
    codec                 : lowercased codec label, refreshed from the
                            probe's Content-Type when we successfully
                            connect (fills in codecs missing from the
                            RB import).
    last_probed_at        : ISO ts of the most recent probe attempt.
    last_probe_ok_at      : ISO ts of the most recent successful probe.
    probe_failure_count   : consecutive failures.  Reset to 0 on any
                            success.  When it hits FAILURE_THRESHOLD
                            (3) the row is flipped to "dead".
    probe_response_ms     : millisecond RTT of the last probe.
    probe_error           : short string reason for the last failure
                            (connect_timeout / http_4xx / http_5xx /
                             read_error / dns_fail / non_audio_type /
                             ssrf_blocked).  Cleared on success.

Constraints:
- Zero probes fire from HTTP request handlers.  Only cold_fill_task,
  scheduled_loop, and (indirectly) the /api/playback-errors endpoint
  may write to these fields.
- Full stream URLs are never logged at WARN/ERROR level (PII / creator
  privacy).  We log the hostname + reason only.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger("bigfm.station_probe")

# ─── Tunables (do NOT increase without ops review) ─────────────────
GLOBAL_CONCURRENCY  = 8       # max simultaneous probes across the fleet.
PER_HOST_CONCURRENCY = 1      # never two probes on the same origin at once.
FAILURE_THRESHOLD   = 3       # 3 consecutive fails → mark dead.
CONNECT_TIMEOUT_S   = 5.0
READ_TIMEOUT_S      = 6.0
COLD_FILL_BATCH     = 1000    # unknown rows probed per boot pass.
SCHEDULED_INTERVAL_S = 6 * 3600   # re-probe alive+dead every 6 h.
SCHEDULED_BATCH     = 500     # size per scheduled sweep pass.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hostname_of(url: str) -> Optional[str]:
    try:
        h = (urlparse(url or "").hostname or "").lower().strip()
        return h or None
    except Exception:
        return None


def _is_ssrf_safe_ip(host: str) -> bool:
    """Return True only when `host` resolves to a public routable IP.
    Rejects IP literals + any DNS resolution that lands on
    private / loopback / link-local / reserved / multicast ranges."""
    if not host:
        return False
    # IP literal → reject outright.  Real radio hosts always use DNS
    # names; a literal IP in an imported station is almost always a
    # broken import or an SSRF probe.
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    # DNS resolve and check every A/AAAA.  Any private answer → refuse.
    try:
        infos = socket.getaddrinfo(host, None,
                                    type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast
                or ip.is_unspecified):
            return False
    return True


def _codec_from_content_type(ct: Optional[str]) -> Optional[str]:
    if not ct:
        return None
    ct = ct.lower().split(";", 1)[0].strip()
    mapping = {
        "audio/mpeg":         "mp3",
        "audio/mp3":          "mp3",
        "audio/aac":          "aac",
        "audio/aacp":         "aac",
        "audio/ogg":          "ogg",
        "audio/opus":         "opus",
        "audio/flac":         "flac",
        "application/ogg":    "ogg",
        "audio/x-mpegurl":    "hls",
        "application/vnd.apple.mpegurl": "hls",
    }
    return mapping.get(ct)


class _PerHostGate:
    """Tiny async guard: gives out one lock per hostname so we never
    fire two simultaneous probes at the same origin.  Locks are
    cached in a plain dict — no eviction needed for the current
    fleet (<3k unique hosts) but a simple LRU can be added later."""

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}

    def get(self, host: str) -> asyncio.Lock:
        lk = self._locks.get(host)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[host] = lk
        return lk


_per_host_gate = _PerHostGate()
_global_gate = asyncio.Semaphore(GLOBAL_CONCURRENCY)


async def _probe_one_url(client: httpx.AsyncClient,
                          url: str) -> Dict[str, Any]:
    """Single probe.  HEAD first, GET Range fallback.  Returns a dict:
        {"ok": bool, "error": str|None, "content_type": str|None,
         "ms": int, "status": int|None}
    Never raises for network errors — everything is captured in the
    dict so the caller can decide what to write to Mongo.
    """
    start = asyncio.get_event_loop().time()
    try:
        r = await client.head(url, follow_redirects=True,
                              timeout=CONNECT_TIMEOUT_S,
                              headers={"Icy-MetaData": "1"})
        # Some Icecast servers reject HEAD; fall through to GET.
        if r.status_code in (400, 403, 405, 501):
            r = None
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return {"ok": False, "error": "connect_timeout",
                "content_type": None, "ms": 0, "status": None}
    except httpx.ReadTimeout:
        return {"ok": False, "error": "read_timeout",
                "content_type": None, "ms": 0, "status": None}
    except (httpx.HTTPError, ValueError):
        r = None
    except Exception:  # noqa: BLE001 — defensive
        r = None

    if r is None:
        try:
            r = await client.get(url, follow_redirects=True,
                                 timeout=CONNECT_TIMEOUT_S,
                                 headers={"Range": "bytes=0-1023",
                                          "Icy-MetaData": "1"})
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return {"ok": False, "error": "connect_timeout",
                    "content_type": None, "ms": 0, "status": None}
        except httpx.ReadTimeout:
            return {"ok": False, "error": "read_timeout",
                    "content_type": None, "ms": 0, "status": None}
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "error": "http_error",
                    "content_type": None, "ms": 0, "status": None}
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "http_error",
                    "content_type": None, "ms": 0, "status": None}

    ms = int((asyncio.get_event_loop().time() - start) * 1000)
    ct = r.headers.get("Content-Type") or r.headers.get("content-type")
    status = r.status_code
    if status < 200 or status >= 400:
        # 4xx / 5xx are dead.
        bucket = "http_5xx" if status >= 500 else "http_4xx"
        return {"ok": False, "error": bucket,
                "content_type": ct, "ms": ms, "status": status}
    # 200/206/302: an audio origin should return either an audio/*
    # content-type OR an Icecast-style header set.  Accept text/*
    # only when it's audio/x-mpegurl (m3u/HLS playlist).
    is_audio_like = False
    if ct:
        ctl = ct.lower()
        if ctl.startswith("audio/") or ctl.startswith("application/ogg"):
            is_audio_like = True
        elif "mpegurl" in ctl or "octet-stream" in ctl:
            is_audio_like = True
    # Icecast/Shoutcast servers frequently leak identity via icy-*.
    if any(k.lower().startswith("icy-") for k in r.headers.keys()):
        is_audio_like = True
    if not is_audio_like:
        return {"ok": False, "error": "non_audio_type",
                "content_type": ct, "ms": ms, "status": status}
    return {"ok": True, "error": None, "content_type": ct,
            "ms": ms, "status": status}


async def probe_station(db, station: Dict[str, Any],
                        client: httpx.AsyncClient) -> str:
    """Probe one station row and persist the health verdict.
    Returns the new `stream_health_status` value.

    Concurrency: caller MUST hold `_global_gate` before calling this;
    per-host gate is acquired internally.
    """
    url = station.get("url_resolved") or station.get("url") or ""
    host = _hostname_of(url) or ""
    sid = station.get("id") or station.get("_id")
    if not url or not host or not sid:
        return station.get("stream_health_status") or "unknown"

    # SSRF short-circuit: private-IP hosts get flagged dead without
    # opening a socket to them.  We never want a probe to reach
    # internal infra.
    if not _is_ssrf_safe_ip(host):
        prev_fails = int(station.get("probe_failure_count") or 0) + 1
        new_status = ("dead" if prev_fails >= FAILURE_THRESHOLD
                      else (station.get("stream_health_status") or "unknown"))
        await db.imported_radio_stations.update_one(
            {"id": sid},
            {"$set": {"stream_health_status": new_status,
                      "hostname": host,
                      "last_probed_at": _now_iso(),
                      "probe_error": "ssrf_blocked",
                      "probe_response_ms": 0,
                      "probe_failure_count": prev_fails}})
        log.warning("[probe] host=%s sid=%s ssrf_blocked → status=%s",
                    host, sid, new_status)
        return new_status

    async with _per_host_gate.get(host):
        res = await _probe_one_url(client, url)

    now = _now_iso()
    if res["ok"]:
        set_doc: Dict[str, Any] = {
            "stream_health_status": "alive",
            "hostname":             host,
            "last_probed_at":       now,
            "last_probe_ok_at":     now,
            "probe_response_ms":    res["ms"],
            "probe_error":          None,
            "probe_failure_count":  0,
        }
        codec = _codec_from_content_type(res["content_type"])
        if codec and not station.get("codec"):
            set_doc["codec"] = codec
        await db.imported_radio_stations.update_one(
            {"id": sid}, {"$set": set_doc})
        log.info("[probe] host=%s sid=%s alive %sms",
                 host, sid, res["ms"])
        return "alive"

    # Failure: increment counter, flip dead at threshold.
    prev_fails = int(station.get("probe_failure_count") or 0) + 1
    new_status = ("dead" if prev_fails >= FAILURE_THRESHOLD
                  else (station.get("stream_health_status") or "unknown"))
    await db.imported_radio_stations.update_one(
        {"id": sid},
        {"$set": {"stream_health_status": new_status,
                  "hostname":             host,
                  "last_probed_at":       now,
                  "probe_error":          res["error"],
                  "probe_response_ms":    res["ms"],
                  "probe_failure_count":  prev_fails}})
    log.info("[probe] host=%s sid=%s fail=%s (%d/%d) → %s",
             host, sid, res["error"], prev_fails,
             FAILURE_THRESHOLD, new_status)
    return new_status


# ─── Boot-time entrypoints ─────────────────────────────────────────

async def cold_fill_task(db) -> Dict[str, int]:
    """Probe every station whose `stream_health_status` is
    `unknown` (typical after a fresh Radio-Browser import).

    Runs at boot as a fire-and-forget task.  Idempotent — once a
    station is `alive` or `dead` the scheduled loop takes over.
    """
    log.info("[probe.cold_fill] starting…")
    q = {"active": True,
         "$or": [{"stream_health_status": {"$in": [None, "unknown"]}},
                 {"stream_health_status": {"$exists": False}}]}
    cur = db.imported_radio_stations.find(q).limit(COLD_FILL_BATCH)
    rows = [r async for r in cur]
    counts = {"total": len(rows), "alive": 0, "dead": 0, "unknown": 0}
    if not rows:
        log.info("[probe.cold_fill] nothing to probe")
        return counts

    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT_S,
                            read=READ_TIMEOUT_S,
                            write=CONNECT_TIMEOUT_S,
                            pool=CONNECT_TIMEOUT_S)
    async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, max_redirects=3,
            headers={"User-Agent": "FUUSIC-Probe/1.0"}) as client:

        async def _one(row: Dict[str, Any]):
            async with _global_gate:
                verdict = await probe_station(db, row, client)
            counts[verdict] = counts.get(verdict, 0) + 1

        await asyncio.gather(*(_one(r) for r in rows),
                             return_exceptions=True)
    log.info("[probe.cold_fill] done: %s", counts)
    return counts


async def scheduled_loop(db) -> None:
    """Long-lived background loop.  Every SCHEDULED_INTERVAL_S it
    re-probes a rolling window of alive+dead stations so:
      - alive rows caught mid-outage flip to dead quickly, and
      - dead rows that recovered flip back to alive when the
        upstream host returns.

    Runs forever inside a shielded try/except so a single crash
    can't take out the entire background task tree.
    """
    log.info("[probe.scheduled_loop] started; interval=%ss",
             SCHEDULED_INTERVAL_S)
    while True:
        try:
            await asyncio.sleep(SCHEDULED_INTERVAL_S)
            q = {"active": True,
                 "stream_health_status": {"$in": ["alive", "dead"]}}
            # Re-probe least-recently-probed rows first so we cycle
            # the whole fleet evenly.
            cur = (db.imported_radio_stations.find(q)
                   .sort("last_probed_at", 1)
                   .limit(SCHEDULED_BATCH))
            rows = [r async for r in cur]
            if not rows:
                continue
            timeout = httpx.Timeout(connect=CONNECT_TIMEOUT_S,
                                    read=READ_TIMEOUT_S,
                                    write=CONNECT_TIMEOUT_S,
                                    pool=CONNECT_TIMEOUT_S)
            counts = {"total": len(rows), "alive": 0, "dead": 0,
                      "unknown": 0}
            async with httpx.AsyncClient(
                    timeout=timeout, follow_redirects=True,
                    max_redirects=3,
                    headers={"User-Agent": "FUUSIC-Probe/1.0"}
                    ) as client:

                async def _one(row: Dict[str, Any]):
                    async with _global_gate:
                        v = await probe_station(db, row, client)
                    counts[v] = counts.get(v, 0) + 1

                await asyncio.gather(*(_one(r) for r in rows),
                                     return_exceptions=True)
            log.info("[probe.scheduled_loop] pass: %s", counts)
        except asyncio.CancelledError:
            log.info("[probe.scheduled_loop] cancelled")
            raise
        except Exception as e:      # noqa: BLE001
            log.warning("[probe.scheduled_loop] error: %s", e)
            await asyncio.sleep(60)   # backoff before next attempt.


async def bump_failure_from_client(db, station_id: str) -> Optional[str]:
    """Called from the /api/playback-errors endpoint.  Increments the
    probe_failure_count using the same rules the async probes use;
    once it hits FAILURE_THRESHOLD the station is flipped to `dead`
    so the browse feed stops serving it.

    Does NOT open a socket — client-observed failure is trusted
    directly.  The next scheduled probe will confirm/recover.
    """
    if not station_id or not station_id.startswith("imp_"):
        return None
    doc = await db.imported_radio_stations.find_one({"id": station_id})
    if not doc:
        return None
    prev = int(doc.get("probe_failure_count") or 0) + 1
    new_status = ("dead" if prev >= FAILURE_THRESHOLD
                  else (doc.get("stream_health_status") or "unknown"))
    await db.imported_radio_stations.update_one(
        {"id": station_id},
        {"$set": {"stream_health_status": new_status,
                  "hostname":             doc.get("hostname")
                                              or _hostname_of(
                                                  doc.get("url_resolved")
                                                  or doc.get("url") or ""),
                  "last_probed_at":       _now_iso(),
                  "probe_error":          "client_reported",
                  "probe_failure_count":  prev}})
    return new_status


__all__ = [
    "cold_fill_task",
    "scheduled_loop",
    "probe_station",
    "bump_failure_from_client",
    "FAILURE_THRESHOLD",
]
