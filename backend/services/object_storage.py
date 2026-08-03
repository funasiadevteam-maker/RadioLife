"""Phase 36c.5 — ObjectStorage abstraction (LocalDisk + Tigris S3).

Single source of truth for every media write path: podcast episodes,
recording mixes, RJ blurbs, ad creatives, music tracks, chapters JSON,
transcript SRTs.

Key naming convention (deterministic, collision-free):
  podcasts/channels/{ch_id}/{ep_id}/audio.mp3
  podcasts/channels/{ch_id}/{ep_id}/cover.jpg
  podcasts/channels/{ch_id}/{ep_id}/video.mp4
  podcasts/recordings/{sid}/{pid}/audio.mp3
  podcasts/recordings/{sid}/{pid}/video.mp4
  podcasts/recordings/{sid}/mixed.mp3
  podcasts/recordings/{sid}/mixed.mp4
  music/tracks/{track_id}.mp3
  rj/{rj_id}.mp3
  ad_creatives/{creative_id}.mp3
  ad_creatives/{creative_id}.webp
  chapters/{ep_id}.json
  transcripts/{ep_id}.srt

Reads:
  - All routes that previously did open(local_path) now look up the `key`
      in MongoDB and either:
      a) signed URL → 302 (when a redirect is acceptable)
      b) byte-range proxy through the backend (for the public RSS audio.mp3
            route, where the URL must stay stable + the same).
  - HEAD + Range are supported natively on both backends.

Two implementations:
  LocalDiskStorage  → /app/backend/storage/{key}   (dev / fallback)
  TigrisStorage          → s3://{TIGRIS_BUCKET}/{key}    (prod)

The factory `get_storage()` reads STORAGE_BACKEND from env. Default is
"local" when unset, so dev machines without Tigris keep working.
"""
from __future__ import annotations
import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

logger = logging.getLogger("bigfm.object_storage")

LOCAL_ROOT_DEFAULT = "/app/backend/storage"


class ObjectStorage(ABC):
    backend_name: str = "abstract"

    @abstractmethod
    def upload(self, *, local_path: str, key: str,
                    content_type: str = "application/octet-stream") -> dict: ...
    @abstractmethod
    def download(self, *, key: str, local_path: str) -> int: ...
    @abstractmethod
    def delete(self, *, key: str) -> bool: ...
    @abstractmethod
    def exists(self, *, key: str) -> bool: ...
    @abstractmethod
    def head(self, *, key: str) -> Optional[dict]: ...    # {size, content_type, etag}
    @abstractmethod
    def get_signed_url(self, *, key: str, expires_in: int = 3600) -> str: ...
    @abstractmethod
    def open_range(self, *, key: str, start: int, end: int) -> bytes: ...
    @abstractmethod
    def list_keys(self, *, prefix: str = "") -> Iterator[dict]: ...


# ─── Local-disk implementation (the legacy path) ─────────────────
class LocalDiskStorage(ObjectStorage):
    backend_name = "local"

    def __init__(self, root: Optional[str] = None) -> None:
        self.root = Path(root or os.environ.get("STORAGE_LOCAL_ROOT")
                                  or LOCAL_ROOT_DEFAULT)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str) -> Path:
        # Defensive: keys must never traverse upward.
        if ".." in Path(key).parts:
            raise ValueError(f"invalid key (traversal): {key!r}")
        return self.root / key

    def upload(self, *, local_path: str, key: str,
                    content_type: str = "application/octet-stream") -> dict:
        dst = self._p(key); dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, dst)
        return {"key": key, "size": dst.stat().st_size,
                  "content_type": content_type, "backend": self.backend_name}

    def download(self, *, key: str, local_path: str) -> int:
        src = self._p(key)
        if not src.is_file(): raise FileNotFoundError(key)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, local_path)
        return src.stat().st_size

    def delete(self, *, key: str) -> bool:
        p = self._p(key)
        if p.is_file(): p.unlink(); return True
        return False

    def exists(self, *, key: str) -> bool:
        return self._p(key).is_file()

    def head(self, *, key: str) -> Optional[dict]:
        p = self._p(key)
        if not p.is_file(): return None
        return {"size": p.stat().st_size, "content_type": None, "etag": None}

    def get_signed_url(self, *, key: str, expires_in: int = 3600) -> str:
        # Local has no signed-URL story — return the proxy route. Callers
        # that need a redirect should use the proxy route directly.
        return f"/api/storage/local/{key}"

    def open_range(self, *, key: str, start: int, end: int) -> bytes:
        p = self._p(key)
        if not p.is_file(): raise FileNotFoundError(key)
        with open(p, "rb") as f:
            f.seek(start); return f.read(end - start + 1)

    def list_keys(self, *, prefix: str = "") -> Iterator[dict]:
        base = self.root / prefix if prefix else self.root
        if not base.exists(): return
        for p in base.rglob("*"):
            if p.is_file():
                yield {"key": str(p.relative_to(self.root)),
                          "size": p.stat().st_size}


# ─── Tigris (S3-compatible) implementation ──────────────────────
class TigrisStorage(ObjectStorage):
    backend_name = "tigris"

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config
        self.bucket    = os.environ.get("TIGRIS_BUCKET") or ""
        self.endpoint = os.environ.get("TIGRIS_ENDPOINT_URL") or ""
        if not self.bucket: raise RuntimeError("TIGRIS_BUCKET not set")
        if not self.endpoint: raise RuntimeError("TIGRIS_ENDPOINT_URL not set")
        self.s3 = boto3.client(
            "s3", endpoint_url=self.endpoint,
            aws_access_key_id=os.environ.get("TIGRIS_ACCESS_KEY_ID") or "",
            aws_secret_access_key=os.environ.get("TIGRIS_SECRET_ACCESS_KEY") or "",
            region_name=os.environ.get("TIGRIS_REGION") or "auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3},
                                  read_timeout=60, connect_timeout=15))

    def upload(self, *, local_path: str, key: str,
                    content_type: str = "application/octet-stream") -> dict:
        size = os.path.getsize(local_path)
        with open(local_path, "rb") as f:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=f,
                                              ContentType=content_type)
        return {"key": key, "size": size, "content_type": content_type,
                  "backend": self.backend_name}

    def download(self, *, key: str, local_path: str) -> int:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self.s3.download_file(self.bucket, key, local_path)
        return os.path.getsize(local_path)

    def delete(self, *, key: str) -> bool:
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            logger.warning("[tigris] delete %s failed: %s", key, e)
            return False

    def exists(self, *, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def head(self, *, key: str) -> Optional[dict]:
        try:
            h = self.s3.head_object(Bucket=self.bucket, Key=key)
            return {"size": int(h.get("ContentLength") or 0),
                      "content_type": h.get("ContentType"),
                      "etag": (h.get("ETag") or "").strip('"')}
        except Exception:
            return None

    def get_signed_url(self, *, key: str, expires_in: int = 3600) -> str:
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in)

    def open_range(self, *, key: str, start: int, end: int) -> bytes:
        r = self.s3.get_object(Bucket=self.bucket, Key=key,
                                                  Range=f"bytes={start}-{end}")
        return r["Body"].read()

    def list_keys(self, *, prefix: str = "") -> Iterator[dict]:
        token = None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": prefix or ""}
            if token: kw["ContinuationToken"] = token
            r = self.s3.list_objects_v2(**kw)
            for it in (r.get("Contents") or []):
                yield {"key": it["Key"], "size": int(it.get("Size") or 0)}
            if not r.get("IsTruncated"): break
            token = r.get("NextContinuationToken")


# ─── Factory ─────────────────────────────────────────────────────
_storage: Optional[ObjectStorage] = None


def get_storage(*, force_backend: Optional[str] = None) -> ObjectStorage:
    """Lazy-init singleton. STORAGE_BACKEND=tigris → Tigris, else local."""
    global _storage
    name = (force_backend or os.environ.get("STORAGE_BACKEND") or "local").lower()
    if _storage and _storage.backend_name == name and not force_backend:
        return _storage
    if name == "tigris":
        _storage = TigrisStorage()
    else:
        _storage = LocalDiskStorage()
    return _storage


def reset_storage() -> None:
    """Test helper — drop the cached singleton (next get_storage rebuilds)."""
    global _storage
    _storage = None


# ─── Canonical key builders (used by routes + migration script) ─
def key_episode_audio(ch_id: str, ep_id: str) -> str:
    return f"podcasts/channels/{ch_id}/{ep_id}/audio.mp3"


def key_episode_video(ch_id: str, ep_id: str) -> str:
    return f"podcasts/channels/{ch_id}/{ep_id}/video.mp4"


def key_episode_cover(ch_id: str, ep_id: str, ext: str = "jpg") -> str:
    return f"podcasts/channels/{ch_id}/{ep_id}/cover.{ext.lstrip('.')}"


def key_recording_participant_audio(sid: str, pid: str) -> str:
    return f"podcasts/recordings/{sid}/{pid}/audio.mp3"


def key_recording_participant_video(sid: str, pid: str) -> str:
    return f"podcasts/recordings/{sid}/{pid}/video.mp4"


def key_recording_participant_screen(sid: str, pid: str) -> str:
    """Phase 36c Stage 4 — per-participant screen-share capture."""
    return f"podcasts/recordings/{sid}/{pid}/screen.mp4"


def key_recording_mixed_audio(sid: str) -> str:
    return f"podcasts/recordings/{sid}/mixed.mp3"


def key_recording_mixed_video(sid: str) -> str:
    return f"podcasts/recordings/{sid}/mixed.mp4"


def key_music_track(track_id: str) -> str:
    return f"music/tracks/{track_id}.mp3"


def key_rj(rj_id: str) -> str:
    return f"rj/{rj_id}.mp3"


def key_ad_creative_audio(creative_id: str, ext: str = "mp3") -> str:
    return f"ad_creatives/{creative_id}.{ext.lstrip('.')}"


def key_ad_creative_image(creative_id: str, ext: str = "webp") -> str:
    return f"ad_creatives/{creative_id}.{ext.lstrip('.')}"


def key_chapters_json(ep_id: str) -> str:
    return f"chapters/{ep_id}.json"


def key_transcript_srt(ep_id: str) -> str:
    return f"transcripts/{ep_id}.srt"
