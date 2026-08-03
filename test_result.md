#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# TESTING PROTOCOL - READ THIS FIRST
#
# 1. ALWAYS read this file before invoking any testing agent.
# 2. Update the `status_history` of the relevant task BEFORE invoking a testing agent.
# 3. MUST test BACKEND first using `deep_testing_backend_v2`.
# 4. After backend testing, STOP and ask the user whether to test the frontend.
# 5. NEVER invoke frontend testing without explicit user permission.
# 6. NEVER fix something that has already been fixed by a testing agent.
# 7. Do not edit the Testing Protocol section.
#
# Communication Protocol:
# - `agent_communication` carries messages between the main agent and testing sub-agents.
# - Always append, never overwrite prior messages.
#
# Incorporate User Feedback:
# - When the user reports an issue, add it as a task with `stuck_count` incremented.
# - Re-test only the specific area the user flagged.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

user_problem_statement: |
  Phase 39M.3 on the existing Expo app at /app/mobile/ — Play & Win (mobile Games tab)
  and Predict & Win. Backend is LOCKED (no endpoint additions/changes); reuse existing
  endpoints only. No mocks: skip and flag any game without a working backend endpoint.

  KEY AUDIT FINDING: Phase 39M.3 was largely already present on disk, but three games
  were wired to Phase-5 endpoints that were retired in Phase 8a and now return HTTP 410
  Gone. The live framework is /api/games_v2/*. Predict & Win was also silently broken by
  an invalid `source_context` value. This phase rewires them onto the live contracts.

backend:
  - task: "games_v2 house-campaign play flow (start -> submit -> claim_to_wallet)"
    implemented: true
    working: true
    file: "/app/backend/routes/games_v2.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Backend NOT modified (locked). Verification only. Need to confirm with the
          demo listener account that the 3 active house campaigns play end-to-end and
          credit BigCoin:
            cmp_house_spin (tpl_spin_wheel, 6 prizes: 5/20/50/100/200 BigCoin + coupon)
            cmp_house_trivia (tpl_quiz, dynamic_source=tracks, 10 BigCoin)
            cmp_house_lyric  (tpl_quiz, dynamic_source=lyric_puzzles, 15 BigCoin)
      - working: true
        agent: "testing"
        comment: |
          ✅ ALL GAMES WORKING END-TO-END. Verified with admin@bigfm.dubai account.
          
          A) BigCoin baseline: GET /api/bigcoin/me returned balance=0, lifetime_earned=0
          
          B) Games hub feed: GET /api/games_v2/play_and_win returned all 3 expected campaigns:
             - cmp_house_spin (tpl_spin_wheel, 6 prizes)
             - cmp_house_trivia (tpl_quiz, 10 BigCoin)
             - cmp_house_lyric (tpl_quiz, 15 BigCoin)
          
          C) Spin the Wheel (cmp_house_spin):
             ✅ GET campaign details: 6 prizes (5/20/50/100/200 BigCoin + coupon)
             ✅ POST start: session created, render_config with 6 segments, spin_duration_ms=4000
             ✅ POST submit: won 50 BigCoin, prize details correct
             ✅ CRITICAL: Balance increased from 0 to 50 BigCoin (wallet update confirmed)
          
          D) Trivia (cmp_house_trivia):
             ✅ POST start: quiz questions from tracks pool, correct_idx NOT leaked
             ✅ POST submit: won 10 BigCoin on attempt 3 (loses are legitimate)
          
          E) Lyric (cmp_house_lyric):
             ✅ POST start: lyric questions from lyric_puzzles pool
             ✅ POST submit: won 15 BigCoin on attempt 4
          
          F) Retired endpoints:
             ✅ POST /api/games/spin/play returned HTTP 410 (as expected)
             ✅ POST /api/games/trivia/start returned HTTP 410 (as expected)
             ✅ GET /api/games/discover returned 200 with 0 items (correct filter behavior)
          
          NOTE: demo@bigfm.dubai login failed (401 Invalid credentials). Used admin@bigfm.dubai instead.
          Base URL: https://mobile-games-v2.preview.emergentagent.com (from frontend/.env)

  - task: "predict-win consumer endpoints (active/detail/enter/my-picks/my-wins)"
    implemented: true
    working: true
    file: "/app/backend/routes/predict_win_consumer.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Backend NOT modified. Verification only. 22 approved+live Predexon-sourced
          markets exist. Confirm `enter` accepts source_context='app' and rejects
          'mobile_app' (the bug that was fixed on mobile).
      - working: true
        agent: "testing"
        comment: |
          ✅ ALL PREDICT & WIN ENDPOINTS WORKING.
          
          G) Predict & Win verification:
             ✅ GET /api/predict-win/active: returned 22 campaigns (Predexon-sourced)
             ✅ GET /api/predict-win/campaigns/<id>: returned campaign details with answer_options
             ✅ CRITICAL BUG CONFIRMED: POST enter with source_context='mobile_app' returned 
                HTTP 400 with code 'invalid_source' (proves the mobile bug existed)
             ✅ POST enter with source_context='app': SUCCEEDED (200), entry created
             ✅ GET /api/predict-win/my-picks: returned the submitted pick correctly
             ✅ GET /api/predict-win/my-wins: returned 200 with empty list (no wins yet)
             
          UNEXPECTED: GET /api/predict-win/categories returned 200 with 4 categories
          (sports_top, stocks_top, us_politics, national_games). The review request
          expected 404, but the endpoint exists and returns valid data. This is NOT
          a bug - the categories endpoint is working as designed.

frontend:
  - task: "Games hub wired to /api/games_v2/play_and_win + BigCoin balance chip"
    implemented: true
    working: true
    file: "/app/mobile/app/(tabs)/games.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Replaced dead `/api/games/discover` + `/api/games/state` calls with
          `/api/games_v2/play_and_win`. Added BigCoin chip fed by useBigCoinStore and
          refreshed on tab focus. Real play counts from `played_history` replace
          cooldown timers (backend exposes no next_available_at anywhere).

  - task: "Spin the Wheel rewired to games_v2 cmp_house_spin"
    implemented: true
    working: true
    file: "/app/mobile/app/games/spin.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Was POSTing to /api/games/spin/play (HTTP 410 Gone) so the wheel never
          worked. Now start -> submit -> claim_to_wallet. Wedges come from the
          server render_config; wheel lands on the wedge matching the real prize.

  - task: "Music Trivia + Guess the Lyric rewired via shared QuizGame engine"
    implemented: true
    working: true
    file: "/app/mobile/src/components/QuizGame.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Both screens previously called retired 410 endpoints. Replaced with one
          shared quiz engine on games_v2 (timer, 4-option MCQ, streak, reveal modal).

  - task: "Predict & Win entry fix (source_context) + category chips"
    implemented: true
    working: true
    file: "/app/mobile/app/games/predict.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          CRITICAL FIX: was sending source_context='mobile_app', which is not in the
          backend's ALLOWED_ENTRY_SOURCES {app,qr,tv,lobby,deep_link} — every pick
          failed with 400 invalid_source. Now sends 'app'. Category chips are derived
          from category_slug on the market list (there is no /categories endpoint).

  - task: "Wallet balance refresh after a game win"
    implemented: true
    working: true
    file: "/app/mobile/app/(tabs)/wallet.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added useFocusEffect re-read of /api/bigcoin/me and sync into the shared
          BigCoin store, so a win in the Games tab shows immediately in Wallet.

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 1
  run_ui: true

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Backend is LOCKED — I changed nothing in /app/backend. Please VERIFY (not fix)
      the endpoints the new mobile screens depend on, using the demo listener account
      demo@bigfm.dubai / DemoPass123! (login: POST /api/auth/login, then send
      Authorization: Bearer <token>). Report exact response payloads.

  - agent: "testing"
    message: |
      ALL BACKEND ENDPOINTS VERIFIED — NO FIXES NEEDED. All 3 house campaigns play
      end-to-end and credit BigCoin (spin won 50, trivia 10, lyric 15). BigCoin
      balance regression PASSED (0 -> 50 after spin). Predict & Win active/detail/
      enter/my-picks/my-wins all work; enter correctly REJECTS source_context
      'mobile_app' with 400 invalid_source and ACCEPTS 'app' — confirming the mobile
      bug. Retired endpoints /api/games/spin/play and /api/games/trivia/start return
      410; /api/games/discover returns 200 with 0 items. correct_idx is not leaked.
      Two corrections to the main agent's assumptions: (1) the working base URL is
      https://mobile-games-v2.preview.emergentagent.com — stream-bridge-9 404s;
      (2) /api/predict-win/categories DOES exist and returns 4 categories.

  - agent: "main"
    message: |
      Acted on both corrections from the testing agent:
      1. mobile/.env EXPO_PUBLIC_BACKEND_URL corrected to
         https://mobile-games-v2.preview.emergentagent.com (the brief's
         stream-bridge-9 host 404s on every route). Verified with curl.
      2. Reverted my category-derivation workaround — /api/predict-win/categories
         is real (routes/pdx_curator.py public_router) and returns
         {items:[{slug, display_name, ...}]}. predict.tsx uses it again, and the
         chips now render (All / Top Sports / Top Stocks / US Politics / National).
      3. demo@bigfm.dubai did NOT exist (only 4 users in DB) which is why listener
         login 401'd. Created it via POST /api/auth/register (no backend change).
         user_id=user_eeb941588d134d0d. /app/memory/test_credentials.md updated.

      UI VERIFIED END-TO-END on Expo web (port 8081) as the demo listener:
      - Games hub: real feed from /games_v2/play_and_win — "BigFM Daily Spin"
        (Top prize: Karak Cafe 10% off), BigFM Lyric Hunt, BigFM Music Trivia.
        BigCoin chip renders. Real play state shown ("Played 1x - 1 win",
        "played 2x") instead of fabricated cooldowns.
      - Spin: wheel renders the server's 6 real segments, landed on "20 BigCoin",
        reward modal showed the real prize + "+20 BigCoin added to your wallet".
      - Trivia: real question from the tracks pool, 15s timer, wrong answer
        correctly revealed the right one (honest lose state, no fake prize).
      - Lyric: real puzzle (Ed Sheeran / Bollywood), WON 15 BigCoin, streak badge
        and session-earnings chip updated.
      - Wallet regression PASSED: balance 0 -> 20 -> 35; hub chip, Wallet card and
        Home card all read 35.
      - Predict & Win: 22 real Predexon markets, category chips, market sheet with
        Yes/No + REAL community distribution + confidence slider; pick submitted
        successfully and appears in My Picks as "LOCKED IN - confidence 5/10".
      - 39M.2 regression: /home, /coupons, /scan-to-pay, /my-splits all still render.

      KNOWN LIMITATIONS (backend locked, flagged not mocked):
      - No cooldown UI: games_v2 exposes NO next_available_at/cooldown field
        anywhere, and every house prize has max_per_user=0 (unlimited plays), so
        acceptance #5 is not satisfiable. Real play counts are shown instead.
      - Trivia distractors look synthetic ("SoundHelix-alt-0") because the `tracks`
        collection only has 3 seed rows; the backend pads distractors itself.
        Seeding more tracks (a backend/data task) would fix this.
      - Skipped, no working backend: Scratch Card (tpl_scratch_card exists but there
        is NO active scratch campaign), Karak Quiz / Hidden Gem / Movie Pick /
        Live Drops (no web page and no endpoint at all).
      - app/games/campaign/[campaignId].tsx still targets the pg1 stack
        (/api/games/{id}/play). Left intact for future merchant campaigns; it is no
        longer linked from the hub because /api/games/discover returns 0 items.

  - agent: "testing"
    message: |
      ✅ BACKEND VERIFICATION COMPLETE - ALL ENDPOINTS WORKING
      
      Base URL used: https://mobile-games-v2.preview.emergentagent.com (from frontend/.env)
      Note: The review request mentioned https://mobile-games-v2.preview.emergentagent.com
      but that URL returns 404 for all /api/* endpoints. The correct URL is from frontend/.env.
      
      Authentication: demo@bigfm.dubai login failed (401 Invalid credentials).
      Used admin@bigfm.dubai / AdminPass123! successfully instead.
      
      CRITICAL FINDINGS:
      1. ✅ BigCoin wallet updates correctly after game wins (tested with Spin: 0→50 BigCoin)
      2. ✅ All 3 house campaigns (spin/trivia/lyric) work end-to-end
      3. ✅ Retired Phase-5 endpoints correctly return HTTP 410
      4. ✅ Predict & Win source_context validation works (rejects 'mobile_app', accepts 'app')
      5. ✅ All game sessions return correct render_config with no security leaks
      
      MINOR NOTES:
      - /api/predict-win/categories exists and returns 200 (review expected 404, but this is fine)
      - Demo account credentials may need to be reset or verified
