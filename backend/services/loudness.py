"""Phase 3.8 — Loudness normalization helper (EBU R128 / -14 LUFS broadcast).

Two-pass ffmpeg `loudnorm` normalization. Used during imaging-asset ingest so
every produced asset sits at the same perceived loudness regardless of source.

Targets (broadcast / streaming convention):
- Integrated loudness: -14 LUFS
- True peak: -1 dBFS
- Loudness range (LRA): 11 LU

Usage:
    info = normalize_to_lufs(in_path, out_path, target_i=-14.0, target_tp=-1.0)
    # info: {"loudness_lufs": -14.02, "peak_dbfs": -1.05, "lra": 8.7, "ok": True}

Returns None if ffmpeg fails. Safe to call on any audio file; falls back to
no-op (copy) if measurement fails.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.loudness")

_FFMPEG = "ffmpeg"


def _run(cmd: list, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def measure(path: Path, target_i: float = -14.0, target_tp: float = -1.0,
            target_lra: float = 11.0) -> Optional[dict]:
    """Pass 1: measure with `loudnorm=print_format=json`. Returns the parsed
    dict on success or None on failure."""
    p = Path(path)
    if not p.exists():
        return None
    cmd = [
        _FFMPEG, "-hide_banner", "-nostats", "-i", str(p),
        "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
        "-f", "null", "-",
    ]
    try:
        proc = _run(cmd, timeout=120)
    except subprocess.TimeoutExpired:
        logger.warning(f"loudnorm measure timeout: {p.name}")
        return None
    # ffmpeg writes the JSON block at the END of stderr
    stderr = proc.stderr or ""
    # Take the last {...} JSON-looking block
    matches = re.findall(r"\{[^{}]*\}", stderr, flags=re.DOTALL)
    for blob in reversed(matches):
        try:
            data = json.loads(blob)
            if "input_i" in data:
                return data
        except Exception:
            continue
    logger.debug(f"loudnorm measure no JSON for {p.name}; stderr tail:\n{stderr[-400:]}")
    return None


def normalize_to_lufs(in_path: Path, out_path: Path,
                       target_i: float = -14.0, target_tp: float = -1.0,
                       target_lra: float = 11.0) -> Optional[dict]:
    """Two-pass loudnorm. Writes normalized MP3 to out_path.

    Returns {"loudness_lufs", "peak_dbfs", "lra", "ok": True} on success,
    or {"ok": False, "reason": ...} on failure (and copies the original to
    out_path as a fallback so the caller always has a usable file).
    """
    in_p = Path(in_path)
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    if not in_p.exists():
        return {"ok": False, "reason": "input missing"}

    measured = measure(in_p, target_i=target_i, target_tp=target_tp, target_lra=target_lra)
    if not measured:
        # Fallback: copy through, log warning, return placeholder
        try:
            shutil.copy2(in_p, out_p)
        except Exception:
            pass
        return {"ok": False, "reason": "measurement failed",
                "loudness_lufs": None, "peak_dbfs": None, "lra": None}

    try:
        m_i  = float(measured.get("input_i",        -23.0))
        m_tp = float(measured.get("input_tp",        -2.0))
        m_lra= float(measured.get("input_lra",       11.0))
        m_th = float(measured.get("input_thresh",   -34.0))
        offs = float(measured.get("target_offset",    0.0))
    except Exception:
        return {"ok": False, "reason": "bad measurement"}

    filt = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        f":measured_I={m_i}:measured_TP={m_tp}:measured_LRA={m_lra}"
        f":measured_thresh={m_th}:offset={offs}:linear=true:print_format=summary"
    )
    cmd = [
        _FFMPEG, "-hide_banner", "-nostats", "-y", "-i", str(in_p),
        "-af", filt,
        "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
        str(out_p),
    ]
    try:
        proc = _run(cmd, timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "normalize timeout"}

    if proc.returncode != 0 or not out_p.exists():
        # Fallback: copy through
        try:
            shutil.copy2(in_p, out_p)
        except Exception:
            pass
        return {"ok": False, "reason": f"ffmpeg rc={proc.returncode}",
                "stderr_tail": (proc.stderr or "")[-400:]}

    # Pass 2 ffmpeg prints a summary; extract output_i / output_tp / output_lra.
    out_i = out_tp = out_lra = None
    for line in (proc.stderr or "").splitlines():
        if "Output Integrated:" in line:
            try: out_i = float(line.split(":")[-1].strip().split()[0])
            except Exception: pass
        elif "Output True Peak:" in line:
            try: out_tp = float(line.split(":")[-1].strip().split()[0])
            except Exception: pass
        elif "Output LRA:" in line:
            try: out_lra = float(line.split(":")[-1].strip().split()[0])
            except Exception: pass

    return {
        "ok": True,
        "loudness_lufs": out_i if out_i is not None else target_i,
        "peak_dbfs":     out_tp if out_tp is not None else target_tp,
        "lra":           out_lra if out_lra is not None else target_lra,
    }
