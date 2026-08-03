"""P0 fix — Mixed-content audio proxy for imported radio streams.

Some upstream radio hosts serve audio over plain HTTP only.  Browsers
refuse to load http:// media inside an https:// page (mixed-content
block), which broke playback across every flagship + community
station whose `stream_url` had not been upgraded to TLS.

Two-pronged fix:
1.  DB migration — rewrote every `funasia.streamguys1.com` URL from
    `http://` (+ optional `:80`) to `https://`.  That host serves the
    same paths over both schemes, so 15-of-17 flagship URLs went green
    immediately.
2.  This proxy — the safety net.  For any surviving `http://` URL (in
    the DB, in a favorites row, in an imported-stations import batch),
    the frontend rewrites the URL to hit `/api/stream-proxy?src=...`
    and this endpoint pipes upstream bytes back over TLS.

Phase RELIABILITY.P2 — Soft allowlist SSRF policy.

Legacy behaviour was a hard hostname allowlist.  That blocked ~75%
of valid Radio-Browser imports (the tail of small regional streams
that never crossed the curator's 43-host allowlist).  We now use a
BLENDED policy that keeps SSRF protection intact while unlocking the
long tail:

    HTTPS + SSRF-safe host          →  allow  (any public hostname)
    HTTP  + SSRF-safe host + on legacy allowlist  →  allow
    HTTP  + not on allowlist        →  400  (still requires curation
                                              to avoid smuggling
                                              unencrypted user data
                                              through the proxy)
    IP literal / private DNS answer →  400  (unchanged)
    Non-http scheme                 →  400  (unchanged)

Range header is forwarded upstream and the upstream's status
(200 / 206) + Content-Type + Content-Length + Content-Range +
Accept-Ranges are forwarded back.  This is what lets the browser
`<audio>` element seek / retry / buffer.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

log = logging.getLogger("bigfm.stream_proxy")

# ─── Legacy HTTP allowlist ────────────────────────────────────────
# Historical curator-approved list.  Under the new blended policy
# this list ONLY gates plaintext HTTP requests; HTTPS hosts pass
# through as long as they are SSRF-safe (public DNS answer, not an
# IP literal).  When adding a new HTTP-only provider, prefer the
# shortest common suffix.
_HTTP_ALLOWLIST_SUFFIXES: tuple[str, ...] = (
    # Flagship-critical hosts.
    "streamguys1.com",
    "alsolnet.com",
    "voxx.pro",
    # Top HTTP-only providers observed in the imported catalog.
    "streamtheworld.com",
    "zeno.fm",
    "laut.fm",
    "qingting.fm",
    "radiobob.de",
    "radioart.com",
    "ihrhls.com",
    "srg-ssr.ch",
    "181fm.com",
    "radiojar.com",
    "1.fm",
    "leanstream.co",
    "hostingradio.ru",
    "fluxfm.de",
    "uber.radio",
    "creacast.com",
    "akamaized.net",
    "rpr1.de",
    "bigfm.de",
    "streamabc.net",
    "worldradio.online",
    "vrtcdn.be",
    "live365.com",
    "infomaniak.ch",
    "bbcmedia.co.uk",
    "franceinfo.fr",
    "franceinter.fr",
    "radiofrance.fr",
    "mosaiquefm.net",
    "cdnstream1.com",
    "bfmtv.com",
    "radioparadise.com",
    "walmradio.com",
    "iraninternational.app",
    "akamaistream.net",
    "dancewave.online",
    "reyfm.de",
    "icecast.vrtcdn.be",
    # BigFM-native infra (not usually proxied, but safe to allow).
    "bigfm.dubai",
    "emergentagent.com",
)

_ALLOWED_SCHEMES = {"http", "https"}

# Headers that must NOT be forwarded upstream (they'd leak the proxy's
# own state or confuse the origin).
_HOP_BY_HOP_REQ = {
    "host", "connection", "content-length", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade",
    "cookie",
}
_HOP_BY_HOP_RESP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "set-cookie",
}


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _resolved_ips(host: str) -> list[ipaddress.IPv4Address
                                     | ipaddress.IPv6Address]:
    """DNS-resolve `host` and return every A/AAAA answer as an
    ipaddress object.  Empty on failure — the caller treats that as
    an SSRF-unsafe host."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return []
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return out


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast
                or ip.is_unspecified)


def _is_ssrf_safe_host(host: str) -> bool:
    """SSRF gate.  Rejects IP literals, and any hostname whose DNS
    answer contains a private / loopback / link-local IP."""
    if not host:
        return False
    if _is_ip_literal(host):
        return False
    ips = _resolved_ips(host)
    if not ips:
        return False
    return all(_is_public_ip(ip) for ip in ips)


def _host_on_http_allowlist(host: str) -> bool:
    if not host:
        return False
    return any(host == s or host.endswith("." + s)
               for s in _HTTP_ALLOWLIST_SUFFIXES)


def _validate_upstream_url(raw: str) -> str:
    """Reject anything that isn't a whitelisted http/https radio host.
    Implements the P2 blended allowlist policy documented at the top
    of this file."""
    if not raw or len(raw) > 2048:
        raise HTTPException(400, "invalid src")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise HTTPException(400, "src must be http or https")
    host = (parsed.hostname or "").lower().strip()
    if not host:
        raise HTTPException(400, "src has no host")

    # 1.  Reject IP literals + private-resolving hosts for BOTH
    #     schemes.  This is the SSRF floor and applies before any
    #     scheme-specific allowlisting.
    if not _is_ssrf_safe_host(host):
        log.warning("[stream-proxy] rejected host=%s scheme=%s "
                    "(ssrf-unsafe or unresolvable)", host, scheme)
        raise HTTPException(400, "src host is not routable / private")

    # 2.  Scheme-specific policy.
    if scheme == "http":
        # Plaintext requires curator vetting to avoid smuggling data
        # through the proxy on behalf of arbitrary origins.
        if not _host_on_http_allowlist(host):
            log.warning("[stream-proxy] http host=%s not on "
                        "legacy allowlist", host)
            raise HTTPException(400,
                                f"src http host not allowed: {host}")
    # scheme == "https": ssrf gate above is sufficient.
    return raw


router = APIRouter(prefix="/api", tags=["stream-proxy"])


@router.get("/stream-proxy")
async def stream_proxy(
    request: Request,
    src: str = Query(..., description="Absolute upstream stream URL"),
):
    """Pipe an upstream radio stream through HTTPS so browsers on an
    HTTPS site can play HTTP-only streams without mixed-content blocks.

    Forwards:
    - `Range` header up (enables seeking on the browser <audio> element).
    - Upstream status code (200 or 206) down.
    - Upstream `Content-Type`, `Content-Length`, `Content-Range`,
      `Accept-Ranges`, `Icy-*` down.
    """
    upstream = _validate_upstream_url(src)

    # Forward Range + basic UA; drop cookies, host, and internal auth.
    fwd_headers: dict[str, str] = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP_REQ:
            continue
        if lk in ("authorization", "referer", "origin", "cookie2"):
            continue
        fwd_headers[k] = v
    # Icy-MetaData=1 asks Icecast/Shoutcast servers to interleave
    # metadata; leave it enabled so the <audio> element gets consistent
    # framing even if the source is a legacy Shoutcast v1 mount.
    fwd_headers.setdefault("Icy-MetaData", "1")
    fwd_headers.setdefault("User-Agent", "BigFM-Proxy/1.0")

    # Fast connect, generous read (live streams are open-ended).
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

    client = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=5,
        # Don't reuse a client across requests — one per proxied stream.
    )
    try:
        req = client.build_request("GET", upstream, headers=fwd_headers)
        resp = await client.send(req, stream=True)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        await client.aclose()
        _hn = (urlparse(upstream).hostname or "unknown").lower()
        log.warning("[stream-proxy] connect fail host=%s err=%s", _hn, e)
        raise HTTPException(502, "upstream unreachable")
    except httpx.HTTPError as e:
        await client.aclose()
        _hn = (urlparse(upstream).hostname or "unknown").lower()
        log.warning("[stream-proxy] http fail host=%s err=%s", _hn, e)
        raise HTTPException(502, "upstream error")

    # Forward status + relevant headers back to the browser.
    out_headers: dict[str, str] = {}
    for k, v in resp.headers.items():
        lk = k.lower()
        if lk in _HOP_BY_HOP_RESP:
            continue
        out_headers[k] = v
    # Ensure CORS is permissive on the proxy so <audio> + a future
    # MediaSource fetch() path both work.
    out_headers["Access-Control-Allow-Origin"] = "*"
    out_headers["Access-Control-Expose-Headers"] = (
        "Content-Length, Content-Range, Accept-Ranges, "
        "Content-Type, Icy-Metadata, Icy-Name"
    )
    out_headers.setdefault(
        "Content-Type",
        resp.headers.get("Content-Type") or "application/octet-stream")

    async def _iter():
        _hn = (urlparse(upstream).hostname or "unknown").lower()
        try:
            async for chunk in resp.aiter_bytes(chunk_size=16 * 1024):
                if chunk:
                    yield chunk
        except (httpx.HTTPError, ConnectionResetError, RuntimeError) as e:
            log.info("[stream-proxy] stream ended host=%s err=%s", _hn, e)
        finally:
            try:
                await resp.aclose()
            finally:
                await client.aclose()

    return StreamingResponse(
        _iter(),
        status_code=resp.status_code,
        headers=out_headers,
    )


@router.head("/stream-proxy")
async def stream_proxy_head(
    src: str = Query(..., description="Absolute upstream stream URL"),
):
    """Cheap validity probe — parses+allowlists src, doesn't open upstream."""
    _validate_upstream_url(src)
    return {"ok": True}


__all__ = ["router"]
