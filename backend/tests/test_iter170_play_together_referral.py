"""
Iter 170 — Play Together referral + On-Air Offer coupon claim regression.

Covers:
- POST /api/social/play/sessions (accepts invitees[], returns session_id, invited flag on GET)
- POST /api/social/play/sessions/{sid}/join with {ref:<referrerUserId>}:
    * response.reward = {points:500, joiner_points:500, referrer_id, referrer_points:500}
    * 2nd join by same user -> reward:null (idempotent)
    * self-referral (ref == joiner) -> reward:null
- GET /api/social/play/sessions returns 'invited' boolean per session
- POST /api/commerce/offers/{offer_id}/claim (in-stock -> coupon_id;
  out_of_inventory -> 409)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           "https://mobile-games-v2.preview.emergentagent.com"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PASS = "FreePass123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    return s, data["user_id"]


@pytest.fixture(scope="module")
def demo_ctx():
    s, uid = _login(DEMO_EMAIL, DEMO_PASS)
    return {"s": s, "uid": uid}


@pytest.fixture(scope="module")
def free_ctx():
    s, uid = _login(FREE_EMAIL, FREE_PASS)
    return {"s": s, "uid": uid}


# ══════ Play Together ══════

def test_create_play_session_with_invitees(demo_ctx):
    r = demo_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions",
                           json={"game_key": "trivia",
                                 "title": "TEST_iter170 host session",
                                 "invitees": []}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "session_id" in data and data["session_id"].startswith("ps_")
    assert data["is_host"] is True
    assert data["game_key"] == "trivia"
    pytest.session_id_demo = data["session_id"]


def test_list_play_sessions_has_invited_flag(demo_ctx):
    r = demo_ctx["s"].get(f"{BASE_URL}/api/social/play/sessions", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)
    # every item MUST carry the 'invited' boolean
    for it in body["items"]:
        assert "invited" in it, f"missing invited flag on {it.get('session_id')}"
        assert isinstance(it["invited"], bool)
        assert "joined" in it
        assert "is_host" in it


def test_referral_join_awards_both_users(demo_ctx, free_ctx):
    # freeuser joins demo's session with ref=demo -> both get 500 points
    sid = pytest.session_id_demo
    r = free_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions/{sid}/join",
                           json={"ref": demo_ctx["uid"]}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["joined"] is True
    reward = body.get("reward")
    assert reward is not None, f"expected reward object, got null: {body}"
    assert reward.get("points") == 500
    assert reward.get("joiner_points") == 500
    assert reward.get("referrer_points") == 500
    assert reward.get("referrer_id") == demo_ctx["uid"]


def test_rejoin_is_idempotent_no_double_award(demo_ctx, free_ctx):
    # 2nd join by the same user returns reward:null
    sid = pytest.session_id_demo
    r = free_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions/{sid}/join",
                           json={"ref": demo_ctx["uid"]}, timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["joined"] is True
    assert body.get("reward") is None, f"expected reward=null on rejoin, got {body}"


def test_self_referral_yields_no_reward(demo_ctx):
    # Create a new session hosted by demo, and demo attempts self-join with ref=demo.
    r = demo_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions",
                           json={"game_key": "trivia",
                                 "title": "TEST_iter170 self-ref session",
                                 "invitees": []}, timeout=20)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    # demo is host = already a participant; a "join" should return reward:null
    # via idempotency AND self-referral guard.
    j = demo_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions/{sid}/join",
                           json={"ref": demo_ctx["uid"]}, timeout=20)
    assert j.status_code == 200
    body = j.json()
    assert body.get("reward") is None, f"self-referral should not award: {body}"


def test_new_session_new_joiner_no_ref_no_reward(demo_ctx, free_ctx):
    # Create a fresh session with no invitees; freeuser joins with NO ref.
    r = demo_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions",
                           json={"game_key": "trivia",
                                 "title": "TEST_iter170 no-ref session",
                                 "invitees": []}, timeout=20)
    assert r.status_code == 200
    sid = r.json()["session_id"]
    j = free_ctx["s"].post(f"{BASE_URL}/api/social/play/sessions/{sid}/join",
                           json={}, timeout=20)
    assert j.status_code == 200
    body = j.json()
    # freeuser is NOT in invitees + no ref -> no referrer -> reward:null
    assert body.get("reward") is None, f"no-ref no-invitee join should not award: {body}"


# ══════ On-Air Offer coupon claim ══════

def test_claim_in_stock_offer_returns_coupon(free_ctx):
    r = free_ctx["s"].post(
        f"{BASE_URL}/api/commerce/offers/ofr_qa_onetime_demo/claim",
        json={"claim_source": "rj_action_card"}, timeout=20)
    # Happy path: 200 + coupon_id. If already claimed by this user
    # (max_per_user_reached), 409 is also acceptable.
    if r.status_code == 200:
        body = r.json()
        # coupon minted -> must expose an id
        assert (body.get("coupon_id") or body.get("id")), \
            f"expected coupon_id in response: {body}"
    else:
        assert r.status_code == 409, r.text[:300]
        # already claimed once — acceptable idempotent outcome
        assert "max_per_user_reached" in r.text or "already" in r.text.lower() \
            or "out_of_inventory" in r.text, r.text[:300]


def test_claim_out_of_inventory_offer_returns_409():
    # Use a fresh session so we're not double-claiming
    s, _uid = _login(DEMO_EMAIL, DEMO_PASS)
    r = s.post(f"{BASE_URL}/api/commerce/offers/off_fpk_40/claim",
               json={"claim_source": "rj_action_card"}, timeout=20)
    assert r.status_code == 409, f"expected 409 out_of_inventory, got {r.status_code}: {r.text[:200]}"
    assert "out_of_inventory" in r.text
