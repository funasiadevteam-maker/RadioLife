"""Phase 18d — ads.txt / app-ads.txt content manager.

Persists the seller list as plain text on disk so the public
`/ads.txt` + `/app-ads.txt` endpoints can stream it without DB
round-trips.  Admin POST atomically rewrites the file via the
temp-then-rename pattern.

File location: /app/backend/static/ads.txt
Validation: each non-blank, non-comment line must match the IAB ads.txt
spec line shape:
    domain, publisher_id, RELATIONSHIP, [tag_id]
where RELATIONSHIP ∈ {DIRECT, RESELLER}.
"""
from __future__ import annotations
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

ADS_TXT_PATH = Path(os.environ.get("ADS_TXT_PATH",
                                                          "/app/backend/static/ads.txt"))

_DEFAULT_HEADER = (
    "# FUUSIC authorized seller list — managed via admin dashboard\n"
    "# IAB Tech Lab ads.txt v1.1 — https://iabtechlab.com/ads-txt\n"
)

# domain, publisher_id, RELATIONSHIP[, optional tag_id]
_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9.\-]+)\s*,\s*"          # domain
    r"([A-Za-z0-9_\-]+)\s*,\s*"                # publisher id
    r"(DIRECT|RESELLER)"                              # relationship
    r"(?:\s*,\s*([A-Za-z0-9]+))?"                 # optional tag id
    r"\s*$"
)


def _ensure_parent() -> None:
    ADS_TXT_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_content() -> str:
    """Returns the current ads.txt content.  Self-heals: if the file is
    missing on disk (first boot / hygiene wipe / fork without the file),
    seed it once with the default header so the public route + admin
    GET always read from the same source of truth on disk."""
    if not ADS_TXT_PATH.exists():
        _ensure_parent()
        ADS_TXT_PATH.write_text(_DEFAULT_HEADER, encoding="utf-8")
    return ADS_TXT_PATH.read_text(encoding="utf-8")


def validate(content: str) -> dict:
    """Returns {ok: bool, bad_lines: [...], line_count: int}.

    Empty lines and `#` comments are always allowed.
    """
    bad = []
    valid_lines = 0
    for i, raw in enumerate(content.splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if _LINE_RE.match(s):
            valid_lines += 1
            continue
        bad.append({"line_no": i, "content": raw})
    return {"ok": not bad, "bad_lines": bad, "valid_line_count": valid_lines}


def write_content(content: str) -> dict:
    """Validates, then atomically rewrites the file via tmp+rename.

    Raises ValueError when validation fails (caller maps to HTTP 400).
    """
    v = validate(content)
    if not v["ok"]:
        raise ValueError({"code": "invalid_ads_txt_lines",
                                      "bad_lines": v["bad_lines"]})
    _ensure_parent()
    # Atomic write: temp file in same dir → fsync → rename.
    fd, tmp = tempfile.mkstemp(prefix=".ads_txt_",
                                              dir=str(ADS_TXT_PATH.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ADS_TXT_PATH)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise
    return {"ok": True, "path": str(ADS_TXT_PATH),
              "valid_line_count": v["valid_line_count"],
              "bytes": ADS_TXT_PATH.stat().st_size}
