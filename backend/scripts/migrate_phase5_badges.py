#!/usr/bin/env python3
"""Phase 10b — CLI helper that runs the Phase 5 → 10a badge backfill.

Usable in two ways:

  # In-cluster (recommended) — calls the admin endpoint
  python -m scripts.migrate_phase5_badges --admin-cookie <session> \
      --base-url https://your-bigfm-host

  # Direct — bypasses the API and runs the service function against
  # MONGO_URL directly (useful for cron / one-off runs).
  python -m scripts.migrate_phase5_badges --direct
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _direct():
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.passport_public import migrate_phase5_badges
    db = AsyncIOMotorClient(
        os.environ.get("MONGO_URL")
        or "mongodb://localhost:27017"
    )[os.environ.get("DB_NAME") or "bigfm"]
    res = asyncio.run(migrate_phase5_badges(db))
    print(f"phase5_migration: {res}")


def _via_api(admin_cookie: str, base_url: str):
    import requests
    r = requests.post(
        f"{base_url.rstrip('/')}/api/admin/passport/migrate_phase5_badges",
        cookies={"bigfm_session": admin_cookie}, timeout=15)
    r.raise_for_status()
    print(f"phase5_migration: {r.json()}")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--direct", action="store_true")
    p.add_argument("--admin-cookie")
    p.add_argument("--base-url",
                       default=os.environ.get("BIGFM_BASE_URL")
                                  or "http://localhost:8001")
    args = p.parse_args(argv)
    if args.direct:
        _direct()
        return 0
    if not args.admin_cookie:
        print("--admin-cookie required (or use --direct)", file=sys.stderr)
        return 2
    _via_api(args.admin_cookie, args.base_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
