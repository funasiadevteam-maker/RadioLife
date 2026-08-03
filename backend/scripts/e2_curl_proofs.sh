#!/usr/bin/env bash
# Sub-Phase E2 — curl proof harness.
#
# Runs the 5 mandated test cases against the live preview and saves
# the raw responses to /tmp/e2_curl_proofs/.
set -u

API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
OUT=/tmp/e2_curl_proofs
mkdir -p "$OUT"

FRIDAY_CID="pwc_6f9af6f5ed6840"    # approved+scheduled, 0 entries, lock~45 min
CLOSED_CID="$1"                                 # e.g. pwc_de16d5f8628f42 (lock~90s)
KARAOKE_CID="pwc_bb4a9a1587d243"  # already-resolved, 1 winner, 1 loser

echo "API=$API"
echo "FRIDAY_CID=$FRIDAY_CID"
echo "CLOSED_CID=$CLOSED_CID"
echo "KARAOKE_CID=$KARAOKE_CID"
echo ""

# Re-login the fixtures (cookie jars in /tmp).
echo "→ Re-login fixture users…"
curl -s -c /tmp/admin_cookie -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bigfm.dubai","password":"AdminPass123!"}' >/dev/null
curl -s -c /tmp/test_cookie -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@bigfm.dubai","password":"TestUser123!"}' >/dev/null
curl -s -c /tmp/demo_cookie -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@bigfm.dubai","password":"DemoPass123!"}' >/dev/null
echo "  ✓ admin/test/demo logged in"
echo ""

# 1. GET /active anon
echo "### TEST 1a — GET /api/predict-win/active (anon)"
curl -sS -w "\nhttp=%{http_code}\n" "$API/api/predict-win/active?limit=10" \
  | tee "$OUT/01a_active_anon.json"
echo ""

echo "### TEST 1b — GET /api/predict-win/active (authed as demo)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  "$API/api/predict-win/active?limit=10" \
  | tee "$OUT/01b_active_authed.json"
echo ""

# 2. POST /enter happy path — demo enters Friday Night with opt_1
echo "### TEST 2 — POST /enter (happy path: demo picks opt_1 on Friday Night)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  -X POST "$API/api/predict-win/campaigns/$FRIDAY_CID/enter" \
  -H "Content-Type: application/json" \
  -d '{"selected_option_id":"opt_1","confidence":7,"source_context":"app"}' \
  | tee "$OUT/02_enter_happy.json"
echo ""

# 3. POST /enter again (same user same campaign) → expect 400 already_entered
echo "### TEST 3 — POST /enter (second submission: expect 400 already_entered)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  -X POST "$API/api/predict-win/campaigns/$FRIDAY_CID/enter" \
  -H "Content-Type: application/json" \
  -d '{"selected_option_id":"opt_2","confidence":3,"source_context":"app"}' \
  | tee "$OUT/03_enter_already_entered.json"
echo ""

# 4. POST /enter on closed campaign (lock_time elapsed)
# Wait until the closed campaign has actually locked, then attempt /enter.
echo "### TEST 4 — POST /enter AFTER lock_time (expect 400 entries_closed)"
echo "    waiting until $CLOSED_CID has locked…"
while :; do
    LOCK_REMAINING=$(curl -s "$API/api/predict-win/campaigns/$CLOSED_CID" \
        | python3 -c "import sys,json
try:
    d=json.load(sys.stdin); print(int(d['campaign']['lock_seconds_remaining']))
except Exception:
    print(-1)")
    if [ "$LOCK_REMAINING" -le 0 ]; then
        echo "    lock_seconds_remaining=$LOCK_REMAINING ⇒ locked, attempting /enter…"
        break
    fi
    echo "    lock_seconds_remaining=$LOCK_REMAINING (sleeping 10s)…"
    sleep 10
done
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  -X POST "$API/api/predict-win/campaigns/$CLOSED_CID/enter" \
  -H "Content-Type: application/json" \
  -d '{"selected_option_id":"opt_1","confidence":5,"source_context":"app"}' \
  | tee "$OUT/04_enter_entries_closed.json"
echo ""

# 5. Resolve flow proof — inspect Karaoke campaign that's already
#         been force-resolved.  This is the cleanest end-to-end proof
#         (1 winner picked opt_1, 1 loser picked opt_2, award row
#         exists, winner's bigcoin was credited).
echo "### TEST 5a — Karaoke campaign final state (already force-resolved)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/admin_cookie \
  "$API/api/admin/predict-win/campaigns/$KARAOKE_CID" \
  | tee "$OUT/05a_karaoke_admin_detail.json"
echo ""

echo "### TEST 5b — winner's /my-wins (logged in as demo, the karaoke winner)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  "$API/api/predict-win/my-wins?limit=10" \
  | tee "$OUT/05b_my_wins.json"
echo ""

echo "### TEST 5c — winner's /my-picks (Friday Night submitted + Karaoke winner)"
curl -sS -w "\nhttp=%{http_code}\n" -b /tmp/demo_cookie \
  "$API/api/predict-win/my-picks?limit=20" \
  | tee "$OUT/05c_my_picks.json"
echo ""

echo "=== DONE.  All proofs in $OUT ==="
ls -la "$OUT"
