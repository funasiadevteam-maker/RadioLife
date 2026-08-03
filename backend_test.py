#!/usr/bin/env python3
"""
Backend API Verification Script for Phase 39M.3
VERIFICATION ONLY - Backend is LOCKED, no modifications allowed
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

BASE_URL = "https://mobile-games-v2.preview.emergentagent.com"
API_PREFIX = "/api"

# Test credentials
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_section(title: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.RESET}\n")

def print_pass(msg: str):
    print(f"{Colors.GREEN}✓ PASS:{Colors.RESET} {msg}")

def print_fail(msg: str):
    print(f"{Colors.RED}✗ FAIL:{Colors.RESET} {msg}")

def print_info(msg: str):
    print(f"{Colors.YELLOW}ℹ INFO:{Colors.RESET} {msg}")

def make_request(method: str, endpoint: str, token: Optional[str] = None, 
                 json_data: Optional[Dict] = None, params: Optional[Dict] = None) -> tuple:
    """Make HTTP request and return (status_code, response_json, response_text)"""
    url = f"{BASE_URL}{API_PREFIX}{endpoint}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=json_data, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        try:
            return resp.status_code, resp.json(), resp.text
        except:
            return resp.status_code, None, resp.text
    except Exception as e:
        print_fail(f"Request failed: {e}")
        return None, None, str(e)

def login(email: str, password: str) -> Optional[str]:
    """Login and return session token"""
    print_info(f"Attempting login with {email}...")
    status, data, text = make_request("POST", "/auth/login", 
                                      json_data={"email": email, "password": password})
    
    if status == 200 and data:
        token = data.get("session_token") or data.get("token") or data.get("access_token")
        if token:
            print_pass(f"Login successful for {email}")
            return token
        else:
            print_fail(f"Login response missing token. Response: {json.dumps(data, indent=2)}")
            return None
    else:
        print_fail(f"Login failed with status {status}: {text}")
        return None

def test_a_bigcoin_baseline(token: str) -> Optional[float]:
    """A) BigCoin baseline - GET /api/bigcoin/me"""
    print_section("A) BigCoin Baseline")
    
    status, data, text = make_request("GET", "/bigcoin/me", token=token)
    
    if status == 200 and data:
        balance = data.get("balance")
        lifetime_earned = data.get("lifetime_earned")
        print_pass(f"GET /api/bigcoin/me returned 200")
        print_info(f"BASELINE balance: {balance}")
        print_info(f"BASELINE lifetime_earned: {lifetime_earned}")
        print_info(f"Full response: {json.dumps(data, indent=2)}")
        return balance
    else:
        print_fail(f"GET /api/bigcoin/me failed with status {status}: {text}")
        return None

def test_b_games_hub_feed(token: str):
    """B) Games hub feed - GET /api/games_v2/play_and_win"""
    print_section("B) Games Hub Feed")
    
    status, data, text = make_request("GET", "/games_v2/play_and_win", token=token)
    
    if status == 200 and data:
        print_pass(f"GET /api/games_v2/play_and_win returned 200")
        
        # Report section keys
        sections = list(data.keys())
        print_info(f"Section keys present: {sections}")
        
        # Check for expected sections
        expected_sections = ["unlocked_for_you", "expiring_soon", "played_history"]
        for section in expected_sections:
            if section in data:
                print_pass(f"Section '{section}' exists")
            else:
                print_fail(f"Section '{section}' missing")
        
        # Report campaigns in unlocked_for_you
        if "unlocked_for_you" in data:
            unlocked = data["unlocked_for_you"]
            print_info(f"unlocked_for_you has {len(unlocked)} campaigns:")
            for item in unlocked:
                campaign_id = item.get("campaign_id")
                template_id = item.get("template_id")
                title = item.get("title")
                top_prize_title = item.get("top_prize_title")
                print_info(f"  - campaign_id: {campaign_id}, template_id: {template_id}, title: {title}, top_prize_title: {top_prize_title}")
            
            # Check for expected campaigns
            expected_campaigns = ["cmp_house_spin", "cmp_house_trivia", "cmp_house_lyric"]
            found_campaigns = [item.get("campaign_id") for item in unlocked]
            for exp_cmp in expected_campaigns:
                if exp_cmp in found_campaigns:
                    print_pass(f"Expected campaign '{exp_cmp}' found")
                else:
                    print_fail(f"Expected campaign '{exp_cmp}' NOT found")
        
        print_info(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print_fail(f"GET /api/games_v2/play_and_win failed with status {status}: {text}")

def test_c_spin_wheel(token: str, baseline_balance: Optional[float]) -> Optional[float]:
    """C) Spin the Wheel end-to-end (cmp_house_spin)"""
    print_section("C) Spin the Wheel End-to-End (cmp_house_spin)")
    
    campaign_id = "cmp_house_spin"
    
    # Step 3: GET campaign details
    print_info("Step 3: GET /api/games_v2/campaigns/cmp_house_spin")
    status, data, text = make_request("GET", f"/games_v2/campaigns/{campaign_id}", token=token)
    
    if status == 200 and data:
        print_pass(f"GET campaign details returned 200")
        title = data.get("title")
        status_field = data.get("status")
        prizes = data.get("prizes", [])
        print_info(f"Title: {title}")
        print_info(f"Status: {status_field}")
        print_info(f"Prizes array ({len(prizes)} prizes): {json.dumps(prizes, indent=2)}")
    else:
        print_fail(f"GET campaign details failed with status {status}: {text}")
        return None
    
    # Step 4: POST start session
    print_info("Step 4: POST /api/games_v2/campaigns/cmp_house_spin/start")
    start_payload = {
        "client_seed": "test_abc",
        "source_context": {"surface": "mobile_games"}
    }
    status, data, text = make_request("POST", f"/games_v2/campaigns/{campaign_id}/start", 
                                      token=token, json_data=start_payload)
    
    if status in [200, 201] and data:
        print_pass(f"POST start returned {status}")
        session_id = data.get("session_id")
        render_config = data.get("render_config", {})
        print_info(f"session_id: {session_id}")
        print_info(f"FULL render_config: {json.dumps(render_config, indent=2)}")
        
        if "segments" in render_config:
            segments = render_config["segments"]
            print_info(f"render_config.segments ({len(segments)} segments):")
            for seg in segments:
                label = seg.get("label")
                color = seg.get("color")
                idx = seg.get("idx")
                print_info(f"  - idx: {idx}, label: {label}, color: {color}")
        
        spin_duration = render_config.get("spin_duration_ms")
        print_info(f"spin_duration_ms: {spin_duration}")
    else:
        print_fail(f"POST start failed with status {status}: {text}")
        return None
    
    # Step 5: POST submit
    print_info(f"Step 5: POST /api/games_v2/sessions/{session_id}/submit")
    status, data, text = make_request("POST", f"/games_v2/sessions/{session_id}/submit", 
                                      token=token, json_data={})
    
    if status in [200, 201] and data:
        print_pass(f"POST submit returned {status}")
        result = data.get("result")
        prize = data.get("prize", {})
        bigcoin_earned = data.get("bigcoin_earned")
        share_text = data.get("share_text")
        
        print_info(f"result: {result}")
        print_info(f"FULL prize: {json.dumps(prize, indent=2)}")
        print_info(f"  - prize.title: {prize.get('title')}")
        print_info(f"  - prize.prize_type: {prize.get('prize_type')}")
        print_info(f"  - prize.value_amount: {prize.get('value_amount')}")
        print_info(f"bigcoin_earned: {bigcoin_earned}")
        print_info(f"share_text: {share_text}")
        print_info(f"FULL response: {json.dumps(data, indent=2)}")
        
        return bigcoin_earned
    else:
        print_fail(f"POST submit failed with status {status}: {text}")
        return None

def test_c_step6_balance_check(token: str, baseline_balance: Optional[float], 
                                bigcoin_earned: Optional[float]):
    """C) Step 6: Verify balance increased"""
    print_info("Step 6: GET /api/bigcoin/me again to verify balance increase")
    
    status, data, text = make_request("GET", "/bigcoin/me", token=token)
    
    if status == 200 and data:
        new_balance = data.get("balance")
        print_pass(f"GET /api/bigcoin/me returned 200")
        print_info(f"BEFORE balance: {baseline_balance}")
        print_info(f"BigCoin earned from game: {bigcoin_earned}")
        print_info(f"AFTER balance: {new_balance}")
        
        if baseline_balance is not None and bigcoin_earned is not None and new_balance is not None:
            expected_balance = baseline_balance + bigcoin_earned
            if abs(new_balance - expected_balance) < 0.01:  # Float comparison with tolerance
                print_pass(f"✓✓✓ CRITICAL CHECK PASSED: Balance increased by exactly {bigcoin_earned} BigCoin")
            else:
                print_fail(f"✗✗✗ CRITICAL CHECK FAILED: Expected balance {expected_balance}, got {new_balance}")
        else:
            print_fail("Cannot verify balance increase - missing data")
    else:
        print_fail(f"GET /api/bigcoin/me failed with status {status}: {text}")

def test_d_trivia(token: str):
    """D) Trivia end-to-end (cmp_house_trivia)"""
    print_section("D) Trivia End-to-End (cmp_house_trivia)")
    
    campaign_id = "cmp_house_trivia"
    
    # Try up to 4 times to get a win
    for attempt in range(1, 5):
        print_info(f"Attempt {attempt}/4")
        
        # Step 7: POST start
        print_info(f"Step 7: POST /api/games_v2/campaigns/{campaign_id}/start")
        status, data, text = make_request("POST", f"/games_v2/campaigns/{campaign_id}/start", 
                                          token=token, json_data={})
        
        if status == 503 and data and data.get("code") == "no_questions_available":
            print_fail(f"HTTP 503 with code 'no_questions_available' - track pool is too small")
            return
        
        if status not in [200, 201] or not data:
            print_fail(f"POST start failed with status {status}: {text}")
            return
        
        print_pass(f"POST start returned {status}")
        session_id = data.get("session_id")
        render_config = data.get("render_config", {})
        
        print_info(f"session_id: {session_id}")
        print_info(f"render_config type: {render_config.get('type')}")
        print_info(f"time_per_question_s: {render_config.get('time_per_question_s')}")
        print_info(f"min_correct_to_win: {render_config.get('min_correct_to_win')}")
        
        questions = render_config.get("questions", [])
        if questions:
            q0 = questions[0]
            print_info(f"questions[0].prompt: {q0.get('prompt')}")
            print_info(f"questions[0].options: {q0.get('options')}")
            
            # CRITICAL: Check if correct_idx is leaked
            if "correct_idx" in q0:
                print_fail(f"✗✗✗ SECURITY ISSUE: correct_idx is LEAKED in the response!")
            else:
                print_pass(f"✓ correct_idx is NOT leaked (good)")
        
        # Step 8: POST submit with answer_idx 0
        print_info(f"Step 8: POST /api/games_v2/sessions/{session_id}/submit")
        submit_payload = {"answer_idx": 0, "answers": [0]}
        status, data, text = make_request("POST", f"/games_v2/sessions/{session_id}/submit", 
                                          token=token, json_data=submit_payload)
        
        if status not in [200, 201] or not data:
            print_fail(f"POST submit failed with status {status}: {text}")
            return
        
        print_pass(f"POST submit returned {status}")
        result = data.get("result")
        quiz_meta = data.get("quiz_meta", {})
        bigcoin_earned = data.get("bigcoin_earned")
        
        print_info(f"result: {result}")
        print_info(f"quiz_meta: {json.dumps(quiz_meta, indent=2)}")
        print_info(f"  - correct_idx: {quiz_meta.get('correct_idx')}")
        print_info(f"  - chosen_idx: {quiz_meta.get('chosen_idx')}")
        print_info(f"  - correct: {quiz_meta.get('correct')}")
        print_info(f"bigcoin_earned: {bigcoin_earned}")
        print_info(f"FULL response: {json.dumps(data, indent=2)}")
        
        if result == "win" and bigcoin_earned > 0:
            print_pass(f"✓✓✓ Got a WIN with {bigcoin_earned} BigCoin credited")
            return
        elif result == "lose" and bigcoin_earned == 0:
            print_info(f"Got a LOSE (wrong answer) - this is legitimate, trying again...")
        else:
            print_fail(f"Unexpected result: {result} with bigcoin_earned: {bigcoin_earned}")
    
    print_fail("Failed to get a win after 4 attempts")

def test_e_lyric(token: str):
    """E) Lyric end-to-end (cmp_house_lyric)"""
    print_section("E) Lyric End-to-End (cmp_house_lyric)")
    
    campaign_id = "cmp_house_lyric"
    
    # Try up to 4 times to get a win
    for attempt in range(1, 5):
        print_info(f"Attempt {attempt}/4")
        
        # POST start
        print_info(f"POST /api/games_v2/campaigns/{campaign_id}/start")
        status, data, text = make_request("POST", f"/games_v2/campaigns/{campaign_id}/start", 
                                          token=token, json_data={})
        
        if status == 503 and data and data.get("code") == "no_questions_available":
            print_fail(f"HTTP 503 with code 'no_questions_available' - lyric_puzzles pool is too small")
            return
        
        if status not in [200, 201] or not data:
            print_fail(f"POST start failed with status {status}: {text}")
            return
        
        print_pass(f"POST start returned {status}")
        session_id = data.get("session_id")
        render_config = data.get("render_config", {})
        
        questions = render_config.get("questions", [])
        if questions:
            q0 = questions[0]
            print_info(f"render_config.questions[0].prompt: {q0.get('prompt')}")
            print_info(f"render_config.questions[0].options: {q0.get('options')}")
        
        # POST submit
        print_info(f"POST /api/games_v2/sessions/{session_id}/submit")
        submit_payload = {"answer_idx": 0, "answers": [0]}
        status, data, text = make_request("POST", f"/games_v2/sessions/{session_id}/submit", 
                                          token=token, json_data=submit_payload)
        
        if status not in [200, 201] or not data:
            print_fail(f"POST submit failed with status {status}: {text}")
            return
        
        print_pass(f"POST submit returned {status}")
        result = data.get("result")
        bigcoin_earned = data.get("bigcoin_earned")
        
        print_info(f"result: {result}")
        print_info(f"bigcoin_earned: {bigcoin_earned}")
        
        if result == "win" and bigcoin_earned > 0:
            print_pass(f"✓✓✓ Got a WIN with {bigcoin_earned} BigCoin credited")
            return
        elif result == "lose" and bigcoin_earned == 0:
            print_info(f"Got a LOSE (wrong answer) - this is legitimate, trying again...")
        else:
            print_fail(f"Unexpected result: {result} with bigcoin_earned: {bigcoin_earned}")
    
    print_fail("Failed to get a win after 4 attempts")

def test_f_retired_endpoints(token: str):
    """F) Confirm RETIRED endpoints return 410"""
    print_section("F) Retired Endpoints (should return HTTP 410)")
    
    # Step 10: POST /api/games/spin/play
    print_info("Step 10: POST /api/games/spin/play")
    status, data, text = make_request("POST", "/games/spin/play", token=token, json_data={})
    if status == 410:
        print_pass(f"POST /api/games/spin/play returned HTTP 410 (as expected)")
    else:
        print_fail(f"POST /api/games/spin/play returned {status} (expected 410): {text}")
    
    # Step 11: POST /api/games/trivia/start
    print_info("Step 11: POST /api/games/trivia/start")
    status, data, text = make_request("POST", "/games/trivia/start", token=token, json_data={})
    if status == 410:
        print_pass(f"POST /api/games/trivia/start returned HTTP 410 (as expected)")
    else:
        print_fail(f"POST /api/games/trivia/start returned {status} (expected 410): {text}")
    
    # Step 12: GET /api/games/discover
    print_info("Step 12: GET /api/games/discover")
    status, data, text = make_request("GET", "/games/discover", token=token)
    print_info(f"GET /api/games/discover returned HTTP {status}")
    if status == 200 and data:
        items = data.get("items", [])
        print_info(f"Response has {len(items)} items (expected 0 because filters on active:true + end_at)")
        print_info(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print_info(f"Response: {text}")

def test_g_predict_win(token: str):
    """G) Predict & Win"""
    print_section("G) Predict & Win")
    
    # Step 13: GET /api/predict-win/active
    print_info("Step 13: GET /api/predict-win/active?limit=30")
    status, data, text = make_request("GET", "/predict-win/active", token=token, 
                                      params={"limit": 30})
    
    first_campaign_id = None
    valid_option_id = None
    
    if status == 200 and data:
        print_pass(f"GET /api/predict-win/active returned 200")
        total = data.get("total")
        items = data.get("items", [])
        print_info(f"total: {total}")
        print_info(f"items count: {len(items)}")
        
        # Report first 3 items
        for i, item in enumerate(items[:3]):
            campaign_id = item.get("campaign_id")
            title = item.get("title")
            category_slug = item.get("category_slug")
            points_reward = item.get("points_reward")
            question_prompt = item.get("question", {}).get("prompt")
            answer_options_count = len(item.get("question", {}).get("answer_options", []))
            lock_time = item.get("lock_time")
            user_has_entered = item.get("user_has_entered")
            eligibility = item.get("eligibility")
            
            print_info(f"Item {i+1}:")
            print_info(f"  - campaign_id: {campaign_id}")
            print_info(f"  - title: {title}")
            print_info(f"  - category_slug: {category_slug}")
            print_info(f"  - points_reward: {points_reward}")
            print_info(f"  - question_prompt: {question_prompt}")
            print_info(f"  - answer_options_count: {answer_options_count}")
            print_info(f"  - lock_time: {lock_time}")
            print_info(f"  - user_has_entered: {user_has_entered}")
            print_info(f"  - eligibility: {eligibility}")
            
            if i == 0:
                first_campaign_id = campaign_id
    else:
        print_fail(f"GET /api/predict-win/active failed with status {status}: {text}")
        return
    
    if not first_campaign_id:
        print_fail("No campaigns found in active list")
        return
    
    # Step 14: GET /api/predict-win/campaigns/<id>
    print_info(f"Step 14: GET /api/predict-win/campaigns/{first_campaign_id}")
    status, data, text = make_request("GET", f"/predict-win/campaigns/{first_campaign_id}", 
                                      token=token)
    
    if status == 200 and data:
        print_pass(f"GET campaign detail returned 200")
        answer_options = data.get("campaign", {}).get("question", {}).get("answer_options", [])
        option_pick_distribution = data.get("option_pick_distribution", {})
        user_entry = data.get("user_entry")
        eligibility = data.get("eligibility")
        
        print_info(f"campaign.question.answer_options ({len(answer_options)} options):")
        for opt in answer_options:
            option_id = opt.get("option_id")
            label = opt.get("label")
            print_info(f"  - option_id: {option_id}, label: {label}")
            if not valid_option_id:
                valid_option_id = option_id
        
        print_info(f"option_pick_distribution: {json.dumps(option_pick_distribution, indent=2)}")
        print_info(f"user_entry: {user_entry}")
        print_info(f"eligibility: {eligibility}")
    else:
        print_fail(f"GET campaign detail failed with status {status}: {text}")
        return
    
    if not valid_option_id:
        print_fail("No valid option_id found")
        return
    
    # Step 15: POST enter with invalid source_context
    print_info(f"Step 15: POST /api/predict-win/campaigns/{first_campaign_id}/enter with source_context='mobile_app' (SHOULD FAIL)")
    invalid_payload = {
        "selected_option_id": valid_option_id,
        "confidence": 5,
        "source_context": "mobile_app"
    }
    status, data, text = make_request("POST", f"/predict-win/campaigns/{first_campaign_id}/enter", 
                                      token=token, json_data=invalid_payload)
    
    if status == 400 and data and data.get("code") == "invalid_source":
        print_pass(f"✓✓✓ CRITICAL BUG CONFIRMATION: POST with source_context='mobile_app' returned HTTP 400 with code 'invalid_source' (as expected)")
        print_info(f"Response: {json.dumps(data, indent=2)}")
    else:
        print_fail(f"Expected HTTP 400 with code 'invalid_source', got {status}: {text}")
    
    # Step 16: POST enter with valid source_context
    print_info(f"Step 16: POST /api/predict-win/campaigns/{first_campaign_id}/enter with source_context='app' (SHOULD SUCCEED)")
    valid_payload = {
        "selected_option_id": valid_option_id,
        "confidence": 5,
        "source_context": "app"
    }
    status, data, text = make_request("POST", f"/predict-win/campaigns/{first_campaign_id}/enter", 
                                      token=token, json_data=valid_payload)
    
    if status in [200, 201] and data:
        print_pass(f"✓✓✓ POST with source_context='app' SUCCEEDED with status {status}")
        print_info(f"Response: {json.dumps(data, indent=2)}")
    else:
        print_fail(f"POST with source_context='app' failed with status {status}: {text}")
    
    # Step 17: GET /api/predict-win/my-picks
    print_info("Step 17: GET /api/predict-win/my-picks?status=submitted&limit=50")
    status, data, text = make_request("GET", "/predict-win/my-picks", token=token, 
                                      params={"status": "submitted", "limit": 50})
    
    if status == 200 and data:
        print_pass(f"GET /api/predict-win/my-picks returned 200")
        items = data.get("items", [])
        print_info(f"Found {len(items)} submitted picks")
        
        # Check if our pick from step 16 appears
        found_our_pick = False
        for item in items:
            if item.get("campaign_id") == first_campaign_id:
                found_our_pick = True
                print_pass(f"✓ Pick from step 16 appears in my-picks")
                print_info(f"Item: {json.dumps(item, indent=2)}")
                break
        
        if not found_our_pick:
            print_fail(f"Pick from step 16 NOT found in my-picks")
    else:
        print_fail(f"GET /api/predict-win/my-picks failed with status {status}: {text}")
    
    # Step 18: GET /api/predict-win/my-wins
    print_info("Step 18: GET /api/predict-win/my-wins?limit=50")
    status, data, text = make_request("GET", "/predict-win/my-wins", token=token, 
                                      params={"limit": 50})
    
    if status == 200 and data:
        print_pass(f"GET /api/predict-win/my-wins returned 200")
        print_info(f"Response shape: {json.dumps(data, indent=2)}")
    else:
        print_fail(f"GET /api/predict-win/my-wins failed with status {status}: {text}")
    
    # Step 19: GET /api/predict-win/categories
    print_info("Step 19: GET /api/predict-win/categories")
    status, data, text = make_request("GET", "/predict-win/categories", token=token)
    
    if status == 404:
        print_pass(f"GET /api/predict-win/categories returned HTTP 404 (as expected - no categories endpoint)")
    else:
        print_fail(f"GET /api/predict-win/categories returned {status} (expected 404): {text}")

def main():
    print_section("Backend API Verification - Phase 39M.3")
    print_info(f"Base URL: {BASE_URL}")
    print_info(f"Backend is LOCKED - VERIFICATION ONLY, no modifications")
    
    # Try demo account first
    token = login(DEMO_EMAIL, DEMO_PASSWORD)
    
    # If demo fails, try admin
    if not token:
        print_info("Demo login failed, trying admin account...")
        token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    
    if not token:
        print_fail("Both demo and admin login failed. Cannot proceed with tests.")
        sys.exit(1)
    
    # A) BigCoin baseline
    baseline_balance = test_a_bigcoin_baseline(token)
    
    # B) Games hub feed
    test_b_games_hub_feed(token)
    
    # C) Spin the Wheel
    bigcoin_earned = test_c_spin_wheel(token, baseline_balance)
    if bigcoin_earned is not None:
        test_c_step6_balance_check(token, baseline_balance, bigcoin_earned)
    
    # D) Trivia
    test_d_trivia(token)
    
    # E) Lyric
    test_e_lyric(token)
    
    # F) Retired endpoints
    test_f_retired_endpoints(token)
    
    # G) Predict & Win
    test_g_predict_win(token)
    
    print_section("Verification Complete")
    print_info("Review the results above for PASS/FAIL status of each test")

if __name__ == "__main__":
    main()
