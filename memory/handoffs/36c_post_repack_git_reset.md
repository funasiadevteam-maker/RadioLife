# Post-repack git reset — 2026-06-04

## What happened
Mid-execution of an ad-hoc disk-cleanup dispatch (Tasks 1/2/3 audit greenlight), the agent
moved `/app/.git` to `/tmp/_gitwork` to give the `git gc --aggressive --prune=now` repack
enough free disk (the `/app` volume had only 789 MB free; the pack file needed ~800 MB
alongside the loose objects during the rewrite). While the aggressive repack was running
(window=250, ~10+ min in), the container restarted (visible in MongoDB supervisor uptime
flip back to 0:00:25 and the block-device id `nvme0n7 → nvme0n6` swap). `/tmp` lives on
the container's overlay upperdir, which is wiped on container restart. `.git` was lost
from both `/tmp/_gitwork` AND `/app/.git`.

## What was lost
- Git history: **221 commits**
- Last HEAD: **ef28c4de8e126fafaf4ba7dc2ca34dc322cd57b4** (`chore: refresh yarn.lock files`)
- All branches including `stage3-wip` (Phase 36c Stage 3 work-in-progress preserved during the Tigris migration dispatch)
- All tags, reflog, loose objects

## What survived
- **Every line of source code** on `/app` — backend, frontend, mobile, tests, memory docs, handoffs
- All `.env` files (correctly excluded from new commit via .gitignore)
- All Tigris data — `bigfm-storage` bucket untouched
- All test artifacts on disk (zombie sessions in `/app/backend/storage/podcasts/recordings/`)

## Recovery action chosen (by user)
Option 3: re-initialize `git init -b main` + single big initial commit, history reset.
- New HEAD: **8d2531eafc3b1bd4b3845bdc309c777e25f697cc**
- Commit message preserves the lost HEAD SHA and commit count for traceability.
- Working tree IS the post-Phase-36c-Stage-4 + ad-creatives-pending state.

## Lessons (do not repeat)
1. **NEVER move `.git` to `/tmp`.** `/tmp` is on the overlay upperdir and gets wiped on
    container restart. If a repack needs more space than `/app` has free, either:
    a. Free space inside `/app` itself first (cleanup proposals 2/3 from the audit), OR
    b. Symlink `.git/objects/pack` to a path on the persistent root overlay (NOT `/tmp`),
        keeping `.git` itself in place, OR
    c. Use a `git --git-dir=...` workflow that writes packs to a persistent location, OR
    d. Ask the user before any relocation.
2. **NEVER use `git gc --aggressive` on a small container.** The default `--window=250`
    runs CPU-bound for hours on multi-GB repos. Plain `git gc --prune=now` uses
    `--window=10` and gets 95% of the compression in 1/25 of the time.
3. **NEVER background-detach a multi-minute git operation without a heartbeat check loop**
    that the operator can cancel safely. The Emergent platform's container can restart for
    unrelated reasons (yarn install, supervisor restart). A long detached job risks data
    loss if the container layer turns over during the operation.
4. **Always run repacks against a clone**, not the live working repo, unless absolutely
    sure the operation will complete before any other supervisor process needs disk.

## Mitigation now in place
- `.gitignore` extended with `backend/storage/podcasts/recordings/`, `backend/storage/streams/`,
    `backend/storage/segments/`, `backend/storage/ads/`, `backend/storage/rj/`,
    `backend/storage/tracks/`, `/app/secrets/`, `secrets/`, `*.pyc`, `*.pyo`, `*.swp`,
    `.DS_Store`, `*.egg-info/`.
- Apple AuthKey + GCP service account JSON were caught BEFORE the initial commit and
    excluded.

## Next steps queued
Tasks 2 (hygiene cron upgrade) and 3 (ad-creatives migration) resume immediately on top of
the new commit `8d2531e`.

## 2026-06-05 — ffmpeg re-install
- Container restart during the failed repack wiped writable-layer packages.
- Reinstalled via `apt-get install -y ffmpeg` (5.1.9-0+deb12u1). Filters confirmed: ebur128, silencedetect, amix, loudnorm, xstack, vstack, hstack.
- Phase 36c stage 3 video test suite: 13/13 pass post-reinstall.
- TODO: bake into image OR add to post-restart provisioning hook so we don't lose it next restart.
