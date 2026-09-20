"""FFmpeg pipeline helpers for FUUSIC Phase 0.

Builds a continuous radio stream from N tracks + (N-1) RJ voiceovers by:
- Equal-power crossfading adjacent tracks (4 seconds).
- Overlaying RJ voice during each crossfade region.
- Ducking the music to ~-12 dB while the RJ speaks.

Phase Π+4 (2026-07-24) — defensive `s3://` resolver:
Every ffmpeg / ffprobe subprocess call feeds its input paths through
`_resolve_ffmpeg_input()` FIRST.  If a caller ever hands us a raw
`s3://bucket/key` string (as happened in server.py's party-segment
path for Tigris-backed tracks — reported as "Protocol not found" in
the pre-warm logs) we transparently mint a 1-hour presigned HTTPS
URL that ffmpeg CAN natively consume via its https protocol handler.
Local paths and http(s):// URLs pass through unchanged.
"""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

_log = logging.getLogger("bigfm.audio_pipeline")


def _resolve_ffmpeg_input(url) -> str:
    """Normalise any input URL into a form ffmpeg's -i can consume.

    - `s3://bucket/key`   → Tigris presigned HTTPS URL (1 h TTL).
    - `http(s)://…`             → passthrough.
    - local absolute path → passthrough.
    - None                                → returns "" (caller will typically
                                                skip or error out cleanly).

    Failure to mint a signed URL falls back to the raw `s3://` string so
    ffmpeg surfaces the underlying credential / network issue cleanly
    instead of hiding it — the caller's exception handler is responsible
    for the graceful skip.
    """
    if url is None:
        return ""
    s = str(url)
    if not s.startswith("s3://"):
        return s
    try:
        # s3://bucket/key…  →  bucket, key
        _, _, rest = s.partition("s3://")
        bucket, _, key = rest.partition("/")
        if not bucket or not key:
            return s
        from services.object_storage import get_storage
        # Force the tigris backend so we don't try to sign against a
        # local FS shim during tests / dev.
        st = get_storage(force_backend="tigris")
        return st.get_signed_url(key=key, expires_in=3600)
    except Exception as _e:                # noqa: BLE001
        _log.warning("[audio_pipeline] s3:// resolve failed for %s: %s "
                                  "— passing through raw (ffmpeg will fail cleanly)",
                                  s, _e)
        return s


def ffprobe_duration(file_path: str | Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    inp = _resolve_ffmpeg_input(file_path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            inp,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def ffprobe_info(file_path: str | Path) -> dict:
    """Return {duration_sec, bitrate} via ffprobe."""
    inp = _resolve_ffmpeg_input(file_path)
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            inp,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    return {
        "duration_sec": float(fmt.get("duration", 0.0)),
        "bitrate": int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else None,
    }


CROSSFADE_SEC = 4.0
DUCK_VOLUME = 0.25  # ~ -12 dB on linear gain (legacy multi-track builder)

# Energy-based linear gain for music ducked under RJ voice:
# chill -14 dB → 0.20  | medium -12 dB → 0.25 | high -8 dB → 0.40 | party -4 dB → 0.63 (Mirchi tuning)
DUCK_BY_ENERGY = {
    "chill":  0.20,
    "medium": 0.25,
    "high":   0.40,
    "party":  0.63,
}


def build_stream(
    track_paths: List[str],
    track_durations: List[float],
    rj_paths: List[str],
    rj_durations: List[float],
    output_path: str | Path,
) -> dict:
    """Stitch N tracks together with crossfades and overlay (N-1) RJ voiceovers.

    Returns metadata: {duration_sec, segments: [...]}
    """
    n = len(track_paths)
    assert n >= 2, "need at least 2 tracks"
    assert len(rj_paths) == n - 1, "need exactly N-1 RJ clips"
    assert len(track_durations) == n
    assert len(rj_durations) == n - 1

    # Inputs: tracks [0..n-1], rj voices [n..2n-2]
    # Phase Π+4 — every track path is resolved through
    # `_resolve_ffmpeg_input` so `s3://…` inputs get a presigned HTTPS
    # URL before ffmpeg sees them (raw `s3://` → "Protocol not found").
    inputs: List[str] = []
    for p in track_paths:
        inputs += ["-i", _resolve_ffmpeg_input(p)]
    for p in rj_paths:
        inputs += ["-i", _resolve_ffmpeg_input(p)]

    filters: List[str] = []

    # Normalize each track to stereo 44100
    for i in range(n):
        filters.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[t{i}]")

    # RJ aformat
    for j in range(n - 1):
        idx = n + j
        filters.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[r{j}]")

    # Crossfade chain
    # m0 = t0 ⨯ t1 ; mi = m(i-1) ⨯ t(i+1) using acrossfade d=4 equal-power (curves esin)
    prev_label = "t0"
    for i in range(1, n):
        out_label = f"m{i-1}"
        filters.append(
            f"[{prev_label}][t{i}]acrossfade=d={CROSSFADE_SEC}:c1=esin:c2=esin[{out_label}]"
        )
        prev_label = out_label
    music_label = prev_label  # final music continuum label

    # Compute crossfade start times in the music continuum (where RJ overlays begin)
    # Crossfade i (between music-so-far and track i+1, i=0..n-2) starts at:
    #   sum(D[0..i]) - CROSSFADE_SEC*(i+1)
    crossfade_starts: List[float] = []
    running = 0.0
    for i in range(n - 1):
        running += track_durations[i]
        start = running - CROSSFADE_SEC * (i + 1)
        crossfade_starts.append(max(0.0, start))

    # Total music continuum length
    music_total = sum(track_durations) - CROSSFADE_SEC * (n - 1)

    # Build a volume expression that ducks music whenever ANY RJ region overlaps t.
    # RJ j plays from crossfade_starts[j] to crossfade_starts[j] + rj_durations[j].
    between_terms = []
    for j in range(n - 1):
        s = crossfade_starts[j]
        e = s + rj_durations[j]
        between_terms.append(f"between(t,{s:.3f},{e:.3f})")
    duck_expr = "+".join(between_terms) if between_terms else "0"
    filters.append(
        f"[{music_label}]volume=eval=frame:volume='if(gt({duck_expr},0),{DUCK_VOLUME},1.0)'[ducked]"
    )

    # Delay each RJ to its crossfade start, then mix all voices to one stream
    for j in range(n - 1):
        delay_ms = int(crossfade_starts[j] * 1000)
        filters.append(f"[r{j}]adelay={delay_ms}|{delay_ms}[rd{j}]")

    if n - 1 == 1:
        voice_label = "rd0"
    else:
        mix_inputs = "".join(f"[rd{j}]" for j in range(n - 1))
        filters.append(
            f"{mix_inputs}amix=inputs={n-1}:duration=longest:normalize=0[voice]"
        )
        voice_label = "voice"

    # Final mix: ducked music + voice. Voice slightly boosted before mix.
    filters.append(f"[{voice_label}]volume=1.4[voiceboost]")
    filters.append(
        "[ducked][voiceboost]amix=inputs=2:duration=longest:normalize=0,"
        "alimiter=limit=0.95[out]"
    )

    filter_complex = ";".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={proc.returncode}):\nCMD: {' '.join(cmd)}\nSTDERR:\n{proc.stderr[-4000:]}"
        )

    # Build segments metadata for the UI timeline
    segments = []
    running = 0.0
    for i in range(n):
        seg_start = max(0.0, running - (CROSSFADE_SEC if i > 0 else 0.0))
        if i == 0:
            seg_start = 0.0
        # show each track and rj clearly
        track_end = running + track_durations[i] - (CROSSFADE_SEC if i > 0 else 0.0)
        segments.append({
            "type": "track",
            "index": i,
            "start_sec": round(seg_start if i == 0 else crossfade_starts[i-1], 3),
            "end_sec": round(track_end, 3),
        })
        running = track_end
        if i < n - 1:
            rj_start = crossfade_starts[i]
            segments.append({
                "type": "rj",
                "index": i,
                "start_sec": round(rj_start, 3),
                "end_sec": round(rj_start + rj_durations[i], 3),
            })

    actual_duration = ffprobe_duration(output_path)
    return {
        "duration_sec": actual_duration,
        "music_total_sec": round(music_total, 3),
        "segments": segments,
    }


def new_uuid_filename(ext: str = "mp3") -> str:
    return f"{uuid.uuid4().hex}.{ext}"


def concat_with_gaps(
    parts: List[str | Path],
    out_path: str | Path,
    gap_ms: int = 200,
) -> dict:
    """Concatenate several MP3 files into one, inserting `gap_ms` of silence
    between turns. Used for duo-RJ banter (each turn is a separate ElevenLabs
    render, joined here with a natural conversational beat).
    Returns {duration_sec}.
    """
    if not parts:
        raise ValueError("concat_with_gaps: no parts")
    n = len(parts)
    inputs: List[str] = []
    for p in parts:
        inputs += ["-i", str(p)]

    gap_sec = max(0.0, gap_ms / 1000.0)
    filters: List[str] = []
    # Normalize each turn to 44100 stereo
    for i in range(n):
        filters.append(
            f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[p{i}]"
        )

    if gap_sec > 0 and n > 1:
        # Build [p0][gap][p1][gap]...[pN] -> concat
        filters.append(
            f"aevalsrc=0:d={gap_sec:.3f}:c=stereo,aformat=sample_rates=44100:channel_layouts=stereo[gap]"
        )
        # We need a copy of [gap] per gap insertion — use asplit
        if n - 1 > 1:
            split_labels = "".join(f"[g{j}]" for j in range(n - 1))
            filters.append(f"[gap]asplit={n-1}{split_labels}")
        else:
            filters.append("[gap]anull[g0]")
        concat_inputs = ""
        for i in range(n):
            concat_inputs += f"[p{i}]"
            if i < n - 1:
                concat_inputs += f"[g{i}]"
        filters.append(f"{concat_inputs}concat=n={2*n - 1}:v=0:a=1[out]")
    else:
        concat_inputs = "".join(f"[p{i}]" for i in range(n))
        filters.append(f"{concat_inputs}concat=n={n}:v=0:a=1[out]")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-ar", "44100", "-ac", "2",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed (rc={proc.returncode}): {proc.stderr[-2000:]}")
    return {"duration_sec": ffprobe_duration(out_path)}


def truncate_audio(
    src: str | Path,
    max_sec: float,
    fade_out_ms: int = 200,
) -> bool:
    """If `src` is longer than `max_sec`, truncate IN-PLACE with a short fade-out.
    Returns True if a truncation actually happened.
    """
    dur = ffprobe_duration(src)
    if dur <= max_sec + 0.05:
        return False
    fade_start = max(0.0, max_sec - fade_out_ms / 1000.0)
    tmp = str(Path(src).with_suffix(".tmp.mp3"))
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-t", f"{max_sec:.3f}",
        "-af", f"afade=t=out:st={fade_start:.3f}:d={fade_out_ms/1000.0:.3f}",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-ar", "44100", "-ac", "2",
        tmp,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg truncate failed (rc={proc.returncode}): {proc.stderr[-2000:]}")
    Path(tmp).replace(src)
    return True


def build_party_segment(
    track_path: str | Path,
    track_duration: float,
    rj_path: str | Path,
    rj_duration: float,
    output_path: str | Path,
    *,
    pre_shout_path: Optional[str | Path] = None,    # ~0.7s "DUBAI!" before RJ, NOT ducked
    whoosh_path: Optional[str | Path] = None,        # ~0.5s sweep into the shout
    airhorn_path: Optional[str | Path] = None,       # ~1s airhorn over the LAST seconds of RJ
    station_id_path: Optional[str | Path] = None,    # ~2s station-ID sting after RJ
    bass_drop_path: Optional[str | Path] = None,     # ~0.5s lead-in to the track beat
    crowd_cheer_path: Optional[str | Path] = None,   # ~1.5s crowd cheer over RJ's opening
) -> dict:
    """Phase 3.5 — Mirchi-style party transition.

    Layout (timeline, seconds from segment start):
      0                    track_duration - 4 - shout_dur
                                     ↓
      [track plays full ............]              ← music continuum, ducked partly
                          [whoosh 0.5s]            ← lightly ducks music
                       [DUBAI shout 0.7s]          ← LOUD, music ducked harder
                          [crowd cheer 1.5s]       ← overlaps RJ opening
              [RJ banter 25-45s, ducked to -4 dB]
                                   [airhorn 1s]   ← over the last 1s of RJ
                                            [station_id ~2s]
                                                       [bass_drop 0.5s]
                                                       [next track will follow]

    Returns the same shape as build_segment so the caller doesn't care which
    builder ran.
    """
    DUCK_LEAD = 4.0   # seconds music ducks while voice fades in
    duck_volume = DUCK_BY_ENERGY.get("party", 0.63)
    deep_duck = duck_volume * 0.55  # extra duck while SFX hits (DUBAI shout)

    track_duration = float(track_duration)
    rj_duration = float(rj_duration)

    # Optional SFX durations
    def _dur(p):
        if not p:
            return 0.0
        try:
            return float(ffprobe_duration(p))
        except Exception:
            return 0.0

    shout_d = _dur(pre_shout_path)
    whoosh_d = _dur(whoosh_path)
    airhorn_d = _dur(airhorn_path)
    sid_d = _dur(station_id_path)
    bass_d = _dur(bass_drop_path)
    cheer_d = _dur(crowd_cheer_path)

    # Timeline anchors
    rj_start = max(0.0, track_duration - DUCK_LEAD)
    shout_start = max(0.0, rj_start - shout_d)
    whoosh_start = max(0.0, shout_start - whoosh_d + 0.1)  # whoosh ends inside shout
    cheer_start = rj_start + 0.05                            # cheer over RJ opening
    rj_end = rj_start + rj_duration
    airhorn_start = max(rj_start, rj_end - airhorn_d * 0.85)
    sid_start = rj_end
    bass_start = sid_start + max(sid_d - 0.1, 0.0)  # bass overlaps tail of SID

    delay_ms = int(rj_start * 1000)

    # Track + RJ inputs always present
    # Phase Π+4 — track_path may be `s3://…`; resolve it to a presigned
    # HTTPS URL before ffmpeg sees it (otherwise "Protocol not found").
    # RJ + SFX paths are always local and pass through unchanged.
    inputs: List[str] = ["-i", _resolve_ffmpeg_input(track_path),
                                          "-i", _resolve_ffmpeg_input(rj_path)]
    optional_specs: List[tuple] = []  # (label, path, delay_ms, gain)
    if shout_d > 0:
        optional_specs.append(("shout", pre_shout_path, int(shout_start * 1000), 1.3))
    if whoosh_d > 0:
        optional_specs.append(("whoosh", whoosh_path, int(whoosh_start * 1000), 1.1))
    if cheer_d > 0:
        optional_specs.append(("cheer", crowd_cheer_path, int(cheer_start * 1000), 0.85))
    if airhorn_d > 0:
        optional_specs.append(("airhorn", airhorn_path, int(airhorn_start * 1000), 1.0))
    if sid_d > 0:
        optional_specs.append(("sid", station_id_path, int(sid_start * 1000), 1.25))
    if bass_d > 0:
        optional_specs.append(("bass", bass_drop_path, int(bass_start * 1000), 1.2))

    for _label, p, _dms, _g in optional_specs:
        inputs += ["-i", str(p)]

    # Music duck windows — RJ region + each SFX hit
    duck_windows = [(rj_start, min(track_duration, rj_end), duck_volume)]
    deep_windows = []
    if shout_d > 0:
        deep_windows.append((shout_start, shout_start + shout_d, deep_duck))
    if whoosh_d > 0:
        duck_windows.append((whoosh_start, whoosh_start + whoosh_d, duck_volume))

    # Build duck expression: deep windows take priority over normal duck
    duck_terms = [f"between(t,{s:.3f},{e:.3f})" for s, e, _ in duck_windows]
    deep_terms = [f"between(t,{s:.3f},{e:.3f})" for s, e, _ in deep_windows]
    deep_expr = "+".join(deep_terms) if deep_terms else "0"
    duck_expr = "+".join(duck_terms) if duck_terms else "0"
    vol_expr = (
        f"if(gt({deep_expr},0),{deep_duck:.3f},"
        f"if(gt({duck_expr},0),{duck_volume:.3f},1.0))"
    )

    filters: List[str] = [
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[t]",
        "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[r]",
        f"[t]volume=eval=frame:volume='{vol_expr}'[ducked]",
        f"[r]adelay={delay_ms}|{delay_ms},volume=1.55[rd]",
    ]

    # Normalize + delay each optional SFX
    sfx_labels: List[str] = []
    for idx, (label, _p, dms, gain) in enumerate(optional_specs):
        input_idx = 2 + idx
        filters.append(
            f"[{input_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[s{label}_raw]"
        )
        filters.append(
            f"[s{label}_raw]adelay={dms}|{dms},volume={gain:.2f}[s{label}]"
        )
        sfx_labels.append(f"[s{label}]")

    # Mix everything
    mix_inputs = "[ducked][rd]" + "".join(sfx_labels)
    n_mix = 2 + len(sfx_labels)
    filters.append(
        f"{mix_inputs}amix=inputs={n_mix}:duration=longest:normalize=0,alimiter=limit=0.96[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg party segment failed (rc={proc.returncode}): {proc.stderr[-2000:]}"
        )

    actual = ffprobe_duration(output_path)
    return {
        "duration_sec": actual,
        "track_duration_sec": track_duration,
        "rj_start_sec": round(rj_start, 3),
        "rj_end_sec": round(rj_end, 3),
        "stinger_inserted": shout_d > 0 or whoosh_d > 0,
        "party_sfx_count": len(optional_specs),
        "party_layout": {
            "whoosh_start_sec": round(whoosh_start, 3) if whoosh_d > 0 else None,
            "shout_start_sec":  round(shout_start, 3)  if shout_d > 0  else None,
            "cheer_start_sec":  round(cheer_start, 3)  if cheer_d > 0  else None,
            "airhorn_start_sec": round(airhorn_start, 3) if airhorn_d > 0 else None,
            "station_id_start_sec": round(sid_start, 3) if sid_d > 0 else None,
            "bass_drop_start_sec": round(bass_start, 3) if bass_d > 0 else None,
        },
    }


def build_short_station_id_transition(
    track_a_path: str | Path,
    track_a_duration: float,
    track_b_path: str | Path,
    track_b_duration: float,
    station_id_path: str | Path,
    output_path: str | Path,
    *,
    whoosh_path: Optional[str | Path] = None,
    bass_drop_path: Optional[str | Path] = None,
) -> dict:
    """Phase 3.5 — quick station-ID-only transition (no full RJ break).

    Used on party channels ~40% of the time to mimic Mirchi's pattern of
    "drop the station ID + bass drop + into next track" without a full
    on-air RJ break every single song.

    Layout:
      [track A 0 → end]
      [whoosh ~0.5s overlapping last 0.5s of A]
      [station_id ~2s overlapping last 1s of A + tail]
      [bass_drop ~0.5s overlapping start of B]
      [track B 0 → end] starts at A.end - 0.3s overlap

    Returns {duration_sec, segments: [...]}.
    """
    track_a_duration = float(track_a_duration)
    track_b_duration = float(track_b_duration)
    sid_d = float(ffprobe_duration(station_id_path))
    whoosh_d = float(ffprobe_duration(whoosh_path)) if whoosh_path else 0.0
    bass_d = float(ffprobe_duration(bass_drop_path)) if bass_drop_path else 0.0

    # Track A ducks lightly during the SID region only.
    duck_lead = 0.5
    sid_start = max(0.0, track_a_duration - duck_lead)
    whoosh_start = max(0.0, sid_start - whoosh_d + 0.05)
    # Track B starts overlapping the SID tail a touch so the listener doesn't hear silence
    b_start = sid_start + max(0.0, sid_d - 0.4)
    bass_start = max(0.0, b_start - 0.2)

    duck_a_end = b_start + 0.3
    duck_volume = DUCK_BY_ENERGY.get("party", 0.63)
    duck_terms = [f"between(t,{sid_start:.3f},{duck_a_end:.3f})"]
    duck_expr = "+".join(duck_terms)

    inputs = [
        # Phase Π+4 — track_a/track_b may be `s3://…` (Tigris tracks);
        # station_id is local SFX but resolver passes local paths through.
        "-i", _resolve_ffmpeg_input(track_a_path),
        "-i", _resolve_ffmpeg_input(station_id_path),
        "-i", _resolve_ffmpeg_input(track_b_path),
    ]
    extras: List[tuple] = []  # (label, path, delay_ms, gain)
    if whoosh_d > 0:
        extras.append(("whoosh", whoosh_path, int(whoosh_start * 1000), 1.1))
    if bass_d > 0:
        extras.append(("bass", bass_drop_path, int(bass_start * 1000), 1.2))
    for _l, p, _d, _g in extras:
        inputs += ["-i", str(p)]

    filters: List[str] = [
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[ta]",
        f"[ta]volume=eval=frame:volume='if(gt({duck_expr},0),{duck_volume:.3f},1.0)'[ta_d]",
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1,adelay={int(sid_start*1000)}|{int(sid_start*1000)},volume=1.25[sid]",
        f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1,adelay={int(b_start*1000)}|{int(b_start*1000)}[tb]",
    ]
    sfx_labels: List[str] = []
    for idx, (label, _p, dms, gain) in enumerate(extras):
        input_idx = 3 + idx
        filters.append(
            f"[{input_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1,adelay={dms}|{dms},volume={gain:.2f}[s{label}]"
        )
        sfx_labels.append(f"[s{label}]")

    mix_inputs = "[ta_d][sid][tb]" + "".join(sfx_labels)
    n_mix = 3 + len(sfx_labels)
    filters.append(
        f"{mix_inputs}amix=inputs={n_mix}:duration=longest:normalize=0,alimiter=limit=0.96[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        "-ar", "44100", "-ac", "2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg short-SID transition failed (rc={proc.returncode}): {proc.stderr[-2000:]}"
        )

    actual = ffprobe_duration(output_path)
    return {
        "duration_sec": actual,
        "track_a_end_sec": round(track_a_duration, 3),
        "track_b_start_sec": round(b_start, 3),
        "station_id_start_sec": round(sid_start, 3),
        "station_id_duration_sec": round(sid_d, 3),
    }


def build_segment(
    track_path: str | Path,
    track_duration: float,
    rj_path: str | Path,
    rj_duration: float,
    output_path: str | Path,
    energy_level: str = "medium",
    stinger_path: Optional[str | Path] = None,
    music_bed_path: Optional[str | Path] = None,
) -> dict:
    """Build one continuous-radio SEGMENT: full track + outro RJ overlay.

    Layout (with optional station stinger + optional music bed under RJ):
      - Track plays 0 → track_duration
      - Optional stinger (1-1.5s) plays at (track_duration - DUCK_LEAD - stinger_dur)
      - RJ voice starts at (track_duration - DUCK_LEAD), music ducks
        by an energy-dependent amount.
      - Optional music bed plays UNDERNEATH the RJ at -8 dB, fade in 400ms /
        out 600ms, looped to cover rj_duration. Bed adds produced-radio polish
        on top of the ducked song bed.
      - RJ may continue briefly past track end.

    Returns {duration_sec, track_duration_sec, rj_start_sec, rj_end_sec,
             stinger_inserted, music_bed_used}.
    """
    DUCK_LEAD = 4.0  # seconds music ducks while voice fades in
    duck_volume = DUCK_BY_ENERGY.get(energy_level, DUCK_VOLUME)

    track_duration = float(track_duration)
    rj_duration = float(rj_duration)
    rj_start = max(0.0, track_duration - DUCK_LEAD)
    rj_end = rj_start + rj_duration
    duck_end = min(track_duration, rj_end)
    delay_ms = int(rj_start * 1000)

    stinger_dur = 0.0
    stinger_inserted = False
    if stinger_path:
        try:
            stinger_dur = ffprobe_duration(stinger_path)
            stinger_inserted = True
        except Exception:
            stinger_dur = 0.0
            stinger_inserted = False

    # Phase 3.8 v2 — music bed under RJ voice (-8 dB, looped, fade-in/out)
    music_bed_used = False
    if music_bed_path:
        try:
            _ = ffprobe_duration(music_bed_path)  # validate
            music_bed_used = True
        except Exception:
            music_bed_used = False

    # Inputs: [0]=track, [1]=rj, [2]=stinger (optional), [next]=music_bed (optional)
    # Phase Π+4 — track_path may be `s3://…`; RJ / stinger / music_bed
    # are always local but the resolver is a no-op for local paths so
    # we wrap uniformly.
    inputs = ["-i", _resolve_ffmpeg_input(track_path),
                        "-i", _resolve_ffmpeg_input(rj_path)]
    next_input_idx = 2
    if stinger_inserted:
        inputs += ["-i", str(stinger_path)]
        stinger_input_idx = next_input_idx
        next_input_idx += 1
    if music_bed_used:
        inputs += ["-stream_loop", "-1", "-i", str(music_bed_path)]
        bed_input_idx = next_input_idx
        next_input_idx += 1

    # Music ducked under voice AND under stinger
    duck_terms = [f"between(t,{rj_start:.3f},{duck_end:.3f})"]
    if stinger_inserted:
        stinger_delay_ms = int(max(0.0, rj_start - stinger_dur) * 1000)
        stinger_end = rj_start
        duck_terms.append(f"between(t,{max(0.0, rj_start - stinger_dur):.3f},{stinger_end:.3f})")
    duck_expr = "+".join(duck_terms) if duck_terms else "0"

    filters = [
        f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[t]",
        f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[r]",
        f"[t]volume=eval=frame:volume='if(gt({duck_expr},0),{duck_volume},1.0)'[ducked]",
        f"[r]adelay={delay_ms}|{delay_ms},volume=1.4[rd]",
    ]

    # Stinger branch
    if stinger_inserted:
        filters += [
            f"[{stinger_input_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1[s]",
            f"[s]adelay={stinger_delay_ms}|{stinger_delay_ms},volume=1.1[sd]",
        ]

    # Music-bed branch — loop, trim to rj_duration, gentle envelope, fade
    if music_bed_used:
        bed_fade_in  = 0.4
        bed_fade_out = 0.6
        bed_full_dur = max(0.5, rj_duration + 0.5)
        bed_fade_out_start = max(0.0, bed_full_dur - bed_fade_out)
        # Bed is delayed to start exactly when the RJ voice starts (rj_start).
        # `volume=0.40` → roughly -8 dB linear gain.
        filters += [
            f"[{bed_input_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=duration={bed_full_dur:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={bed_fade_in:.3f},"
            f"afade=t=out:st={bed_fade_out_start:.3f}:d={bed_fade_out:.3f},"
            f"volume=0.40,adelay={delay_ms}|{delay_ms}[bed]",
        ]

    # Final mix
    mix_chain_inputs = "[ducked]"
    if stinger_inserted:
        filters.append(f"[ducked][sd]amix=inputs=2:duration=longest:normalize=0[withstinger]")
        mix_chain_inputs = "[withstinger]"
    # Mix RJ + bed (if any) into one wet RJ stem, then mix with the song bed
    if music_bed_used:
        filters.append(
            f"[rd][bed]amix=inputs=2:duration=longest:normalize=0:weights='1.0 0.55'[rjwet]"
        )
        rj_label = "[rjwet]"
    else:
        rj_label = "[rd]"
    filters.append(
        f"{mix_chain_inputs}{rj_label}amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg segment failed (rc={proc.returncode}): {proc.stderr[-2000:]}"
        )

    actual = ffprobe_duration(output_path)
    return {
        "duration_sec": actual,
        "track_duration_sec": track_duration,
        "rj_start_sec": round(rj_start, 3),
        "rj_end_sec": round(rj_end, 3),
        "stinger_inserted": stinger_inserted,
        "music_bed_used": music_bed_used,
    }


def build_segment_no_rj(
    track_path: "str | Path",
    track_duration: float,
    output_path: "str | Path",
    stinger_path: Optional["str | Path"] = None,
) -> dict:
    """Phase Bug-1 (cold-start TTFB) — Build a segment WITHOUT AI RJ.

    Layout:
      - Optional 1-2s pre-rendered station ID stinger upfront
      - Full music track immediately after (back-to-back, no gap)

    Skips the OpenAI script-generation + ElevenLabs TTS calls that
    historically added 25-30 sec to the cold-start critical path.
    The next break (segment 2+) still gets full AI RJ.

    Returns the same shape as `build_segment(...)` so callers that
    expect `duration_sec` / `rj_start_sec` keep working.
    """
    track_duration = float(track_duration)
    stinger_dur = 0.0
    stinger_inserted = False
    if stinger_path:
        try:
            stinger_dur = ffprobe_duration(stinger_path)
            stinger_inserted = True
        except Exception:
            stinger_dur = 0.0
            stinger_inserted = False

    if not stinger_inserted:
        # Pure copy + transcode — fastest path (~200ms ffmpeg).
        # Phase Π+4 — resolve s3:// → presigned HTTPS.
        cmd = [
            "ffmpeg", "-y",
            "-i", _resolve_ffmpeg_input(track_path),
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-ar", "44100", "-ac", "2",
            str(output_path),
        ]
    else:
        # Stinger upfront, then track (concatenated via filter_complex)
        # Phase Π+4 — resolve s3:// → presigned HTTPS on track_path.
        cmd = [
            "ffmpeg", "-y",
            "-i", _resolve_ffmpeg_input(stinger_path),
            "-i", _resolve_ffmpeg_input(track_path),
            "-filter_complex",
            "[0:a]aresample=44100,aformat=channel_layouts=stereo[s0];"
            "[1:a]aresample=44100,aformat=channel_layouts=stereo[s1];"
            "[s0][s1]concat=n=2:v=0:a=1[out]",
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            "-ar", "44100", "-ac", "2",
            str(output_path),
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg no-rj segment failed (rc={proc.returncode}): "
            f"{proc.stderr[-2000:]}")
    actual = ffprobe_duration(output_path)
    return {
        "duration_sec": actual,
        "track_duration_sec": track_duration,
        "rj_start_sec": None,
        "rj_end_sec": None,
        "stinger_inserted": stinger_inserted,
        "stinger_duration_sec": round(stinger_dur, 3),
        "music_bed_used": False,
        "no_rj": True,
    }
