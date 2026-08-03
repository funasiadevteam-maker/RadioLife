"""Phase 3.5 — SFX library + station ID status endpoints (debug)."""
from __future__ import annotations

from fastapi import APIRouter

from services.sfx_library import library_status, existing_files
from services.station_ids import station_ids_status, existing_station_ids

sfx_router = APIRouter(prefix="/api/sfx", tags=["sfx"])


@sfx_router.get("/status")
async def sfx_status():
    """No auth. Returns counts of SFX files + station IDs currently on disk.
    Useful for verifying Phase 3.5 generation completed."""
    lib = library_status()
    sid = station_ids_status()
    return {
        "library": {
            "total_expected": lib["total_expected"],
            "on_disk": lib["on_disk"],
            "missing": lib["missing"],
            "generation_started": lib["generation_started"],
            "generation_done": lib["generation_done"],
            "files": sorted(p.name for p in existing_files().values()),
        },
        "station_ids": {
            "total_expected": sid["total_expected"],
            "on_disk": sid["on_disk"],
            "generation_started": sid["generation_started"],
            "generation_done": sid["generation_done"],
            "files": sorted(p.name for p in existing_station_ids()),
        },
        "phase": "3.5",
    }
