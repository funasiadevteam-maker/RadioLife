# Phase 39M.3 — Mobile Play & Win + Predict & Win

_Shipped 2026-08-03. Scope: `/app/mobile/` only. `/app/backend/` and `/app/frontend/`
were NOT modified._

## TL;DR

Phase 39M.3 was **already ~90% present on disk** — the Games tab was never a stub. The
real problem was that **three games were wired to endpoints retired in Phase 8a** and
**Predict & Win could not accept a single pick**. This phase rewired them onto the live
contracts. Nothing is mocked.

## The three bugs that made this phase worth doing

1. **Spin / Trivia / Lyric were dead.** They POSTed to `/api/games/spin/play`,
   `/api/games/trivia/start|answer`, `/api/games/lyric/start|answer`. Those are Phase 5
   endpoints retired in Phase 8a — `routes/games.py` returns **HTTP 410 Gone** with a
   `moved_to` hint. The spin screen even had an "unavailable" branch for the 410, so the
   wheel visibly never worked.
2. **The hub feed was always empty.** `app/(tabs)/games.tsx` called
   `/api/games/discover` (from `routes/pg1_games.py`), which filters on `active: true`
   **and** `end_at >= now`. The house campaigns have neither field, so the section never
   rendered. Confirmed: that endpoint returns `200` with `0` items.
3. **Predict & Win rejected every pick.** `predict.tsx` sent
   `source_context: 'mobile_app'`, but the backend's `ALLOWED_ENTRY_SOURCES` is
   `{app, qr, tv, lobby, deep_link}` → **400 `invalid_source`** on every entry.

## Live contracts now used

Games (all under `/api/games_v2`):

| Call | Purpose |
|---|---|
| `GET /play_and_win` | hub feed → `unlocked_for_you`, `expiring_soon`, `played_history` |
| `GET /campaigns/{id}` | title, description, prizes, compliance, branding |
| `POST /campaigns/{id}/start` | creates session → `session_id` + `render_config` |
| `POST /sessions/{id}/submit` | server resolves prize → `result`, `prize`, `bigcoin_earned`, `quiz_meta` |
| `POST /sessions/{id}/claim_to_wallet` | **only for non-BigCoin prizes** |

`GET /api/bigcoin/me` → balance. Predict & Win: `GET /api/predict-win/active`,
`/campaigns/{id}`, `POST /campaigns/{id}/enter`, `GET /my-picks`, `/my-wins`,
`GET /api/predict-win/categories` (lives in `routes/pdx_curator.py`, not
`predict_win_consumer.py` — easy to miss).

**BigCoin auto-credits on `submit`.** `claim_to_wallet` is a no-op for BigCoin; it is only
needed to mint a wallet item for coupon prizes.

**Spin wheel is cosmetic.** The server returns `render_config.segments` (label/color/idx)
but never says which wedge won, so `resolveWheelIndex()` matches the returned
`prize.title` back onto a segment (with value/type fallbacks) and lands the wheel there.

## House campaigns (collection `game_campaigns`, DB `bigfm`)

| campaign_id | template | prizes |
|---|---|---|
| `cmp_house_spin` | `tpl_spin_wheel` | 5/20/50/100/200 BigCoin + "Karak Cafe 10% off" coupon |
| `cmp_house_trivia` | `tpl_quiz` | 10 BigCoin — `dynamic_source: tracks` |
| `cmp_house_lyric` | `tpl_quiz` | 15 BigCoin — `dynamic_source: lyric_puzzles` |

All three are `status: active`, `open_to_all: true`, `end_at: null`.

## Files

Created:
- `src/api/gamesApi.ts` — games_v2 layer, error normaliser, `resolveWheelIndex`
- `src/stores/useBigCoinStore.ts` — zustand balance store (optimistic + reconcile)
- `src/components/RewardModal.tsx` — shared reveal modal (real prize only)
- `src/components/QuizGame.tsx` — shared quiz engine (timer, MCQ, streak, reveal)

Modified:
- `app/(tabs)/games.tsx` — live feed, BigCoin chip, real play counts, fixed routes
- `app/games/spin.tsx` — rewired to games_v2; wedges from server
- `app/games/trivia-game.tsx`, `app/games/lyric-game.tsx` — thin wrappers over `QuizGame`
- `app/games/predict.tsx` — `source_context: 'app'` fix
- `app/(tabs)/wallet.tsx` — `useFocusEffect` re-read + store sync
- `mobile/.env` — recreated (gitignored, lost with the workspace)

## Environment gotchas

- `mobile/.env` is **gitignored** — it does not survive a fresh checkout and must be
  recreated or every API call goes to `undefined/api`.
- The correct backend host is **`https://mobile-games-v2.preview.emergentagent.com`**
  (matches protected `frontend/.env`). The brief's `stream-bridge-9...` host **404s on
  every route.**
- `demo@bigfm.dubai` **did not exist**; created via `POST /api/auth/register`.

## Deliberately NOT built (no backend — flagged, not mocked)

- **Scratch Card** — `tpl_scratch_card` template exists, but there is **no active scratch
  campaign**, so there is nothing to play. Add a campaign and it will appear in the hub
  automatically and play via the generic `/game/[campaignId]` player.
- **Karak Quiz, Hidden Gem, Movie Pick, Live Drops** — no web page, no endpoint, no
  template. "Karak" only appears as a coupon prize name ("Karak Cafe 10% off").
- **Cooldown timers** — `games_v2` exposes **no `next_available_at`/cooldown field**, and
  every house prize has `max_per_user: 0` (unlimited). Real play counts from
  `played_history` are shown instead of inventing a countdown.
- **Odds bars / volume / amount input / recent trades / P&L** — the consumer
  Predict & Win model is a *free community pick* (question + answer options +
  `first_n_correct`). There are no prices, no stake and no P&L. `total_volume_usd` exists
  on the campaign doc but is **not exposed** by any consumer endpoint. The market sheet
  shows the **real** `option_pick_distribution` instead.

## Known data-quality issue

Trivia distractors render as `SoundHelix-alt-0/1/2` because the `tracks` collection has
only **3 seed rows**; `_generate_dynamic_quiz_question` pads missing distractors itself.
Seeding more tracks (backend/data task) fixes it — no mobile change needed.
