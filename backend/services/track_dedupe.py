"""Phase 22e — Track dedupe service.

Single source of truth for "is this track already in the catalog?" used
by BOTH the bulk upload route (`routes/admin_tracks_bulk.py`) and the
individual upload route (`server.py::upload_track`).

Three rules, evaluated in priority order:

  1. ISRC exact match            → matched_rule="isrc"
  2. File-hash exact match     → matched_rule="file_hash"
  3. Normalized title+artist+duration±2s → matched_rule="title_artist_duration"

Hard rule: dedupe runs BEFORE any Tigris/disk write of the canonical
asset.  The caller is still allowed to spool to a temp file for ffprobe
+ mutagen + hashing — that's local + cleaned up regardless.

Race protection: `tracks.file_hash` is a UNIQUE sparse index, so a
late-arriving second writer with the same hash hits DuplicateKeyError
on insert.  The bulk + individual routes catch it and re-resolve via
`find_duplicate` to surface a clean "matched_rule=file_hash" response.
"""
from __future__ import annotations
import logging
import re
import unicodedata
from typing import Optional

log = logging.getLogger("bigfm.track_dedupe")

_DEDUPE_INDEXES_READY = False


def normalize_text(s: Optional[str]) -> str:
    """Lowercase, NFKC-fold, collapse whitespace. Empty input → ""."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def ensure_dedupe_indexes(db) -> None:
    """Idempotent. Wired into FastAPI startup.

    Self-heals against legacy duplicate `file_hash` rows that would
    otherwise block the UNIQUE sparse index build: if the build fails
    with E11000, the offending duplicate rows (all but the
    earliest-inserted) are deleted and the build retried once.
    """
    global _DEDUPE_INDEXES_READY
    if _DEDUPE_INDEXES_READY:
        return
    try:
        await db.tracks.create_index([("isrc", 1)], sparse=True,
                                                                    name="tracks_isrc_sparse")
        await db.tracks.create_index([
            ("title_normalized", 1),
            ("artist_normalized", 1),
        ], sparse=True, name="tracks_title_artist_normalized")
        try:
            await db.tracks.create_index(
                [("file_hash", 1)], unique=True, sparse=True,
                name="tracks_file_hash_unique_sparse")
        except Exception as e:
            msg = str(e).lower()
            if "duplicate key" in msg or "e11000" in msg:
                # Self-heal: find dup hash groups, keep oldest, delete rest.
                pipe = [
                    {"$match": {"file_hash": {"$exists": True, "$ne": None}}},
                    {"$group": {"_id": "$file_hash",
                                              "count": {"$sum": 1},
                                              "ids":    {"$push": "$_id"}}},
                    {"$match": {"count": {"$gt": 1}}},
                ]
                to_delete: list[str] = []
                async for d in db.tracks.aggregate(pipe):
                    to_delete.extend(d["ids"][1:])
                if to_delete:
                    r = await db.tracks.delete_many({"_id": {"$in": to_delete}})
                    log.warning("[track_dedupe] purged %d duplicate-hash "
                                          "tracks before building UNIQUE index",
                                          r.deleted_count)
                # retry build (single attempt)
                await db.tracks.create_index(
                    [("file_hash", 1)], unique=True, sparse=True,
                    name="tracks_file_hash_unique_sparse")
            else:
                raise
        _DEDUPE_INDEXES_READY = True
        log.info("[track_dedupe] indexes ensured")
    except Exception as e:
        log.warning("[track_dedupe] ensure_dedupe_indexes failed: %s", e)


async def find_duplicate(
    db,
    *,
    file_hash: Optional[str] = None,
    isrc: Optional[str] = None,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    duration_sec: Optional[float] = None,
    duration_tolerance_sec: float = 2.0,
) -> Optional[dict]:
    """Return None when no match, else
        {"matched_rule": str, "track_id": str,
          "title": str, "artist": str}.
    """
    proj = {"_id": 1, "title": 1, "artist": 1}

    # Rule 1 — ISRC exact (only if isrc looks present + reasonable).
    if isrc and len(isrc) >= 5:
        hit = await db.tracks.find_one({"isrc": isrc}, proj)
        if hit:
            return {"matched_rule":            "isrc",
                          "track_id":                  hit["_id"],
                          "title":                          hit.get("title") or "",
                          "artist":                        hit.get("artist") or ""}

    # Rule 2 — File hash.
    if file_hash:
        hit = await db.tracks.find_one({"file_hash": file_hash}, proj)
        if hit:
            return {"matched_rule":            "file_hash",
                          "track_id":                  hit["_id"],
                          "title":                          hit.get("title") or "",
                          "artist":                        hit.get("artist") or ""}

    # Rule 3 — title+artist+duration fuzzy.
    if title and artist and duration_sec is not None and duration_sec > 0:
        tn = normalize_text(title)
        an = normalize_text(artist)
        if tn and an:
            lo = float(duration_sec) - duration_tolerance_sec
            hi = float(duration_sec) + duration_tolerance_sec
            hit = await db.tracks.find_one({
                "title_normalized":    tn,
                "artist_normalized":  an,
                "duration_sec":          {"$gte": lo, "$lte": hi},
            }, proj)
            if hit:
                return {"matched_rule":            "title_artist_duration",
                              "track_id":                  hit["_id"],
                              "title":                          hit.get("title") or "",
                              "artist":                        hit.get("artist") or ""}

    return None


def attach_dedupe_fields(doc: dict) -> dict:
    """Mutates + returns `doc` to add `title_normalized` /
    `artist_normalized` so rule-3 lookups hit an index.  Call this just
    before inserting a fresh track row."""
    doc["title_normalized"]  = normalize_text(doc.get("title"))
    doc["artist_normalized"] = normalize_text(doc.get("artist"))
    return doc
