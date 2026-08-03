"""HTTP Range streaming helpers for serving MP3 files with seek/buffer support."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _parse_range(range_header: str, file_size: int):
    m = _RANGE_RE.match(range_header)
    if not m:
        raise HTTPException(400, "invalid Range header")
    start_s, end_s = m.group(1), m.group(2)
    if start_s == "" and end_s == "":
        raise HTTPException(400, "invalid Range header")
    if start_s == "":
        length = int(end_s)
        start = max(0, file_size - length)
        end = file_size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        raise HTTPException(416, "range not satisfiable")
    return start, end


def _iter_file(path: Path, start: int, end: int, chunk_size: int = 64 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            buf = f.read(min(chunk_size, remaining))
            if not buf:
                break
            remaining -= len(buf)
            yield buf


def range_response(file_path: Path, request: Request) -> StreamingResponse:
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    if range_header:
        start, end = _parse_range(range_header, file_size)
        length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": "audio/mpeg",
            "Cache-Control": "no-cache",
        }
        return StreamingResponse(
            _iter_file(file_path, start, end),
            status_code=206, headers=headers, media_type="audio/mpeg",
        )
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "audio/mpeg",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(
        _iter_file(file_path, 0, file_size - 1),
        status_code=200, headers=headers, media_type="audio/mpeg",
    )


def public_base_url(request: Request) -> str:
    """Best-effort public origin for SSR meta tags."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    proto = forwarded_proto or request.url.scheme
    if forwarded_host:
        return f"{proto}://{forwarded_host}"
    return str(request.base_url).rstrip("/")
