"""Phase 22g — Bulk Upload Job Audit Log endpoints.

Read surfaces around the `bulk_upload_jobs` collection populated by
`routes/admin_tracks_bulk.py`.  Four endpoints:

  - GET   /api/admin/tracks/bulk-upload/jobs                    (admin)
  - GET   /api/admin/tracks/bulk-upload/jobs/{job_id}        (admin, full)
  - GET   /api/me/bulk-upload/jobs                                  (any auth user, own only)
  - POST  /api/admin/tracks/bulk-upload/jobs/sweep-stale (admin utility)
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user, require_admin
from services.bulk_upload_jobs import (get_job, list_jobs, sweep_stale)


router = APIRouter(tags=["admin-tracks-bulk-jobs"])


# ---- admin: list + detail ---------------------------------------------
@router.get("/api/admin/tracks/bulk-upload/jobs",
                        dependencies=[Depends(require_admin)])
async def admin_list_bulk_upload_jobs(
    request: Request,
    status: Optional[str]   = None,
    user_id: Optional[str] = None,
    limit:    int                      = 25,
    cursor: Optional[str]   = None,
):
    """Admin paginated history.  Filterable by status + user_id."""
    db = request.app.state.db
    return await list_jobs(db, status=status, user_id=user_id,
                                                  limit=limit, cursor=cursor)


@router.get("/api/admin/tracks/bulk-upload/jobs/{job_id}",
                        dependencies=[Depends(require_admin)])
async def admin_get_bulk_upload_job(request: Request, job_id: str):
    db = request.app.state.db
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")
    return job


# ---- user-scoped --------------------------------------------------------
@router.get("/api/me/bulk-upload/jobs")
async def me_list_bulk_upload_jobs(
    request: Request,
    limit:    int                      = 25,
    cursor: Optional[str]   = None,
    user: dict = Depends(current_user),
):
    """Caller's own jobs only — works for admins + non-admins (creators
    can see their own attempts without admin role)."""
    db = request.app.state.db
    return await list_jobs(db, user_id=user["user_id"],
                                                  limit=limit, cursor=cursor)


@router.get("/api/me/bulk-upload/jobs/{job_id}")
async def me_get_bulk_upload_job(
    request: Request,
    job_id: str,
    user: dict = Depends(current_user),
):
    db = request.app.state.db
    job = await get_job(db, job_id,
                                              restrict_to_user_id=user["user_id"])
    if not job:
        raise HTTPException(404, "job_not_found")
    return job


# ---- admin: sweep stale ------------------------------------------------
@router.post("/api/admin/tracks/bulk-upload/jobs/sweep-stale",
                          dependencies=[Depends(require_admin)])
async def admin_sweep_stale_bulk_upload_jobs(request: Request):
    db = request.app.state.db
    n = await sweep_stale(db)
    return {"ok": True, "abandoned_count": int(n)}
