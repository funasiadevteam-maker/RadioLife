"""Phase 36c Stage 3 — Per-participant video transcode + grid mix.

Full-scope (Tigris-unlocked, post-36c.5) envelope:
    - Resolution target:                              1080p (1920x1080)
    - Per-participant video bitrate target:    2.5 Mbps (CRF 23 veryfast h264)
    - Per-participant upload cap (a+v combined): 500 MB
    - Duration cap:                                       60 min (3600 s)
    - Audio bitrate (extracted track):         192 kbps libmp3lame
    - Final mux audio:                                   192 kbps aac

Tile geometry (each output is 1920x1080 final canvas):
    1 participant → identity copy at 1080p
    2 participants → hstack 2×(960x1080) → 1920x1080
    3 participants → speaker_view:
            top  : 1×(1920x540) = first participant (host)
            bottom: 2×(960x540) = next two
    4 participants → 2x2 xstack of 4×(960x540) → 1920x1080

Layout override: session.grid_layout in
    {"auto", "side_by_side", "2x2", "speaker_view"}.
"""
from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bigfm.podcast_video")

# Stage 3 (full-scope) — relaxed caps (Tigris removes the disk constraint).
VIDEO_UPLOAD_CAP_BYTES        = 500 * 1024 * 1024    # 500 MB per-participant
VIDEO_RECORDING_CAP_SEC = 3600                                  # 60 min
TARGET_W, TARGET_H            = 1920, 1080
HALF_W                                          = TARGET_W // 2          # 960
HALF_H                                          = TARGET_H // 2          # 540
SPEAKER_TOP_W                            = TARGET_W                  # 1920
SPEAKER_TOP_H                            = TARGET_H * 3 // 4    # 810
SPEAKER_SUB_W                            = TARGET_W // 2          # 960
SPEAKER_SUB_H                            = TARGET_H - SPEAKER_TOP_H    # 270


def transcode_to_mp4(src_path: Path, mp4_path: Path,
                                          audio_mp3_path: Optional[Path] = None,
                                          target_height: int = TARGET_H) -> int:
    """Transcode src (webm/mp4) → 1080p (or override) H.264+AAC mp4.

    Optional: extract a separate {pid}.mp3 (192 kbps libmp3lame) for the
    audio amix path in finalize. Returns 0 on full success."""
    target_h = max(240, min(2160, int(target_height or TARGET_H)))
    cmd = ["ffmpeg", "-y", "-i", str(src_path),
              "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
              "-vf", f"scale=-2:{target_h}",    # preserve aspect, even width
              "-c:a", "aac", "-b:a", "128k",
              "-movflags", "+faststart", str(mp4_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode != 0:
            logger.warning("[36c-s3] ffmpeg transcode failed rc=%s stderr=%s",
                                          r.returncode,
                                          r.stderr.decode("utf-8", "ignore")[-500:])
            return r.returncode
    except Exception as e:
        logger.warning("[36c-s3] ffmpeg transcode crash: %s", e)
        return -1
    if audio_mp3_path:
        cmd2 = ["ffmpeg", "-y", "-i", str(mp4_path), "-vn",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(audio_mp3_path)]
        try:
            r2 = subprocess.run(cmd2, capture_output=True, timeout=180)
            if r2.returncode != 0:
                logger.warning("[36c-s3] ffmpeg mp3 extract failed rc=%s",
                                              r2.returncode)
                return r2.returncode
        except Exception as e:
            logger.warning("[36c-s3] ffmpeg mp3 extract crash: %s", e)
            return -1
    return 0


def auto_layout(n: int) -> str:
    """Pick a layout based on participant count when grid_layout='auto'."""
    if n <= 1: return "single"
    if n == 2: return "side_by_side"
    if n == 3: return "speaker_view"
    return "2x2"


def resolve_layout(grid_layout: str, n: int,
                                          has_screen: bool = False) -> str:
    """Honor the session's grid_layout setting; fall back to auto for unknown.
    Stage 4: when any participant is screen-sharing the result is forced to
    `screen_priority` regardless of the grid_layout pref (the featured tile
    IS the screen)."""
    if has_screen: return "screen_priority"
    if grid_layout in ("side_by_side", "2x2", "speaker_view"):
        return grid_layout
    return auto_layout(n)


def ffmpeg_grid_mix(mp4_paths: list, out_path: Path, layout: str,
                                              screen_path: Optional[Path] = None) -> int:
    """Combine N participant mp4 video streams into a single 1080p grid mp4.

    Stage 4: when `screen_path` is provided AND layout == "screen_priority",
    the screen capture occupies a 1920x810 featured tile at top while up to
    3 participant tiles fill a 1920x270 bottom strip. Audio is dropped here
    — audio is mixed separately via amix on the mp3 tracks and re-merged
    via merge_video_audio() at the end of finalize.

    Audio is dropped here — audio is mixed separately via amix on the mp3
    tracks and re-merged via merge_video_audio() at the end of finalize."""
    n = len(mp4_paths)
    if n == 0 and not screen_path: return -1
    inputs: list = []
    # Stage 4 — when screen_priority, prepend screen as input 0 so the
    # filter graph can reference it as [0:v]; participants shift to [1:v]…
    if layout == "screen_priority" and screen_path:
        inputs += ["-i", str(screen_path)]
        for p in mp4_paths: inputs += ["-i", str(p)]
        # Build top + bottom strip. Up to 3 participant thumbnails fit the bottom.
        TOP_W, TOP_H = TARGET_W, SPEAKER_TOP_H                      # 1920x810
        BOT_H              = TARGET_H - TOP_H                              # 270
        thumb_n = min(len(mp4_paths), 3)
        thumb_w = TARGET_W // max(thumb_n, 1)                         # 640 or 960
        parts = [f"[0:v]scale={TOP_W}:{TOP_H}:"
                      f"force_original_aspect_ratio=decrease,"
                      f"pad={TOP_W}:{TOP_H}:(ow-iw)/2:(oh-ih)/2[scr]"]
        for i in range(thumb_n):
            parts.append(
                f"[{i + 1}:v]scale={thumb_w}:{BOT_H}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={thumb_w}:{BOT_H}:(ow-iw)/2:(oh-ih)/2[t{i}]")
        if thumb_n == 0:
            chain = (f"color=c=black:size={TARGET_W}x{BOT_H}[botpad];"
                          f"[scr][botpad]vstack=inputs=2[v]")
        elif thumb_n == 1:
            # Single bottom thumbnail — pad laterally to full canvas width.
            chain = (f"[t0]pad={TARGET_W}:{BOT_H}:"
                          f"({TARGET_W}-{thumb_w})/2:0:black[bot];"
                          f"[scr][bot]vstack=inputs=2[v]")
        else:
            tin = "".join(f"[t{i}]" for i in range(thumb_n))
            chain = (f"{tin}hstack=inputs={thumb_n}[bot_raw];"
                          f"[bot_raw]pad={TARGET_W}:{BOT_H}:"
                          f"({TARGET_W}-iw)/2:0:black[bot];"
                          f"[scr][bot]vstack=inputs=2[v]")
        fc = ";".join(parts) + ";" + chain
        cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
                  "-map", "[v]",
                  "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                  "-pix_fmt", "yuv420p",
                  "-movflags", "+faststart", "-an", str(out_path)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=900)
            if r.returncode != 0:
                logger.warning("[36c-s4] ffmpeg screen-priority grid failed "
                                              "rc=%s stderr=%s", r.returncode,
                                              r.stderr.decode("utf-8", "ignore")[-700:])
            return r.returncode
        except Exception as e:
            logger.warning("[36c-s4] ffmpeg screen-priority crash: %s", e)
            return -1

    for p in mp4_paths: inputs += ["-i", str(p)]

    if n == 1 or layout == "single":
        # 1 participant — scale to fit 1920x1080 preserving aspect; pad letterbox.
        fc = (f"[0:v]scale={TARGET_W}:{TARGET_H}:"
                  f"force_original_aspect_ratio=decrease,"
                  f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2[v]")
    elif layout == "side_by_side":
        # Two tiles, each 960x1080.
        fc = (f"[0:v]scale={HALF_W}:{TARGET_H}:"
                  f"force_original_aspect_ratio=decrease,"
                  f"pad={HALF_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2[s0];"
                  f"[1:v]scale={HALF_W}:{TARGET_H}:"
                  f"force_original_aspect_ratio=decrease,"
                  f"pad={HALF_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2[s1];"
                  f"[s0][s1]hstack=inputs=2[v]")
    elif layout == "speaker_view":
        # Top tile = first input (host) at 1920x810.
        # Bottom row: up to 2 tiles at 960x270 each, side by side.
        parts = [f"[0:v]scale={SPEAKER_TOP_W}:{SPEAKER_TOP_H}:"
                      f"force_original_aspect_ratio=decrease,"
                      f"pad={SPEAKER_TOP_W}:{SPEAKER_TOP_H}:(ow-iw)/2:(oh-ih)/2[s0]"]
        bottom_count = min(n - 1, 2)
        for i in range(1, 1 + bottom_count):
            parts.append(
                f"[{i}:v]scale={SPEAKER_SUB_W}:{SPEAKER_SUB_H}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={SPEAKER_SUB_W}:{SPEAKER_SUB_H}:(ow-iw)/2:(oh-ih)/2[s{i}]")
        if bottom_count == 0:
            chain = f"[s0]pad={TARGET_W}:{TARGET_H}:0:0:black[v]"
        elif bottom_count == 1:
            # Top + 1 bottom tile centered horizontally — pad to fill width.
            parts.append(
                f"color=c=black:size={SPEAKER_SUB_W}x{SPEAKER_SUB_H}[bk0]")
            parts.append(
                f"color=c=black:size={SPEAKER_SUB_W}x{SPEAKER_SUB_H}[bk1]")
            chain = (f"[s0][bk0][s1][bk1]"
                          f"xstack=inputs=4:"
                          f"layout=0_0|w0_0|0_h0|w0_h0[v]")
            # NB: bk0 occupies the top-right under TARGET_W; widths add to TARGET_W.
            # When the top tile alone spans full width (SPEAKER_TOP_W=1920) we
            # actually do not need bk0; pivot to a simpler vstack instead:
            chain = (f"[s0]"
                          f"[s1]pad={TARGET_W}:{SPEAKER_SUB_H}:"
                          f"({TARGET_W}-{SPEAKER_SUB_W})/2:0:black[s1p];"
                          f"[s0][s1p]vstack=inputs=2[v]")
        else:    # bottom_count == 2
            chain = (f"[s1][s2]hstack=inputs=2[bot];"
                          f"[s0][bot]vstack=inputs=2[v]")
        fc = ";".join(parts) + ";" + chain
    elif layout == "2x2":
        # Four tiles, each 960x540. If <4 inputs, pad with black tiles.
        parts: list = []
        used = mp4_paths[:4]
        for i in range(len(used)):
            parts.append(
                f"[{i}:v]scale={HALF_W}:{HALF_H}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={HALF_W}:{HALF_H}:(ow-iw)/2:(oh-ih)/2[s{i}]")
        chains = "".join(f"[s{i}]" for i in range(len(used)))
        if len(used) < 4:
            for i in range(4 - len(used)):
                idx = len(used) + i
                parts.append(
                    f"color=c=black:size={HALF_W}x{HALF_H}:d=10[s{idx}]")
                chains += f"[s{idx}]"
        chain = (f"{chains}xstack=inputs=4:"
                      f"layout=0_0|w0_0|0_h0|w0_h0[v]")
        fc = ";".join(parts) + ";" + chain
    else:
        fc = f"[0:v]scale={TARGET_W}:{TARGET_H}[v]"

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
              "-map", "[v]",
              "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
              "-pix_fmt", "yuv420p",
              "-movflags", "+faststart", "-an", str(out_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=900)
        if r.returncode != 0:
            logger.warning("[36c-s3] ffmpeg grid_mix failed rc=%s stderr=%s",
                                          r.returncode,
                                          r.stderr.decode("utf-8", "ignore")[-700:])
        return r.returncode
    except Exception as e:
        logger.warning("[36c-s3] ffmpeg grid_mix crash: %s", e)
        return -1


def merge_video_audio(video_mp4: Path, audio_mp3: Path,
                                              out_path: Path) -> int:
    """Combine the grid video (no audio) with the mixed audio (mp3 → aac).
    -shortest stops at the shorter stream so trailing silence is trimmed."""
    cmd = ["ffmpeg", "-y", "-i", str(video_mp4), "-i", str(audio_mp3),
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", "-shortest", str(out_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode != 0:
            logger.warning("[36c-s3] ffmpeg merge failed rc=%s stderr=%s",
                                          r.returncode,
                                          r.stderr.decode("utf-8", "ignore")[-500:])
        return r.returncode
    except Exception as e:
        logger.warning("[36c-s3] ffmpeg merge crash: %s", e)
        return -1


def ffprobe_video_dimensions(mp4_path: Path) -> dict:
    """Return {width, height, duration} from the first video stream."""
    cmd = ["ffprobe", "-v", "error",
              "-select_streams", "v:0",
              "-show_entries", "stream=width,height,duration",
              "-of", "json", str(mp4_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        if r.returncode != 0: return {}
        import json
        d = json.loads(r.stdout.decode("utf-8", "ignore") or "{}")
        s = (d.get("streams") or [{}])[0]
        return {"width":      int(s.get("width") or 0),
                  "height":     int(s.get("height") or 0),
                  "duration": float(s.get("duration") or 0)}
    except Exception:
        return {}
