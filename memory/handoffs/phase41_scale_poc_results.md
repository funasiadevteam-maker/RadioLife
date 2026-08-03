# Phase 41 Session 0 — Multi-Tenant Station Scale POC Results

**Date**: 2026-06-07T16:13:17.117173+00:00
**Script**: `backend/scripts/phase41_session0_scale_poc.py`
**Workload**: 100 synthetic stations · 100 concurrent listeners · queue depth 8 · 200 seeded tracks

## Latency (per listener queue-build)
| Metric | Value (ms) |
|---|---|
| Mean   | 22.7 |
| Median | 23.1 |
| p95    | 38.3 |
| Min    | 10.1 |
| Max    | 39.6 |

## Throughput
| Metric | Value |
|---|---|
| Total wall-time for 100 concurrent sessions | 43.1 ms |
| Tracks per queue (avg) | 8.0 |
| Sessions / sec | 2317.8 |

## Memory
| Metric | Value |
|---|---|
| Peak RSS (MB) | 58.3 |

## Halt-criteria check
| Gate | Threshold | Observed | Verdict |
|---|---|---|---|
| Avg queue-build latency | < 2000 ms | 22.7 ms | ✅ pass |
| Peak RSS (process) | < 2048 MB | 58.3 MB | ✅ pass |

## Mongo round-trip per listener
- 1 × `tracks.find({filter}).limit(32)`
- 0 × count_documents (omitted — find alone gives us the candidate pool)
- **Total: ~1 round-trip per listener session-start**.

## Per-station Mongo footprint
A typical `community_radio_stations` document is ~600–800 bytes (no
embedded tracklist — only the music_clock rotation references). With
10k stations the collection sits comfortably under 10 MB.

## Recommendations for Session 1
- **Lazy per-session warm-up is fine at this scale.** No shared cache needed in MVP.
- **RSS comfortable** — no architecture change needed.
- Index `community_radio_stations.station_id` (unique) and
  `community_radio_stations.owner_user_id` to keep wizard lookups O(1).
- Index `tracks.genre`, `tracks.mood`, `tracks.energy_level` (compound is
  acceptable but the per-field indexes Mongo already maintains are
  sufficient at this load).

## Cleanup
All `_synthetic_poc=True` rows have been deleted. Production collections
untouched.
