"""Iter 54 backend tests — 4 extra house games, reservation manager, gift card redeem."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/auth/demo", timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ================= House Games =================
EXPECTED_HOUSE = {
    "cmp_house_scratch": "tpl_scratch_card",
    "cmp_house_mystery": "tpl_mystery_box",
    "cmp_house_memory":  "tpl_memory_match",
    "cmp_house_word":    "tpl_word_puzzle",
}


def test_play_and_win_includes_4_new_house_games(headers):
    r = requests.get(f"{BASE_URL}/games_v2/play_and_win", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    unlocked = j.get("unlocked_for_you") or []
    ids = {g["campaign_id"] for g in unlocked}
    for cid in EXPECTED_HOUSE:
        assert cid in ids, f"missing house game {cid} in unlocked_for_you: {sorted(ids)}"
    # spot-check flags on one
    scratch = next(g for g in unlocked if g["campaign_id"] == "cmp_house_scratch")
    assert scratch.get("template_id") == "tpl_scratch_card"


@pytest.mark.parametrize("campaign_id,template_id", list(EXPECTED_HOUSE.items()))
def test_house_game_start_and_submit(headers, campaign_id, template_id):
    # start
    r = requests.post(f"{BASE_URL}/games_v2/campaigns/{campaign_id}/start",
                      json={}, headers=headers, timeout=30)
    assert r.status_code == 200, f"{campaign_id} start: {r.status_code} {r.text}"
    j = r.json()
    sid = j["session_id"]
    rc = j["render_config"]

    # submit with template-appropriate payload
    if template_id == "tpl_scratch_card":
        payload = {}
    elif template_id == "tpl_mystery_box":
        payload = {"box_index": 0}
    elif template_id == "tpl_memory_match":
        # send min_correct_pairs_to_win pairs, within time
        min_pairs = rc.get("min_correct_pairs_to_win", 6)
        payload = {"pairs_found": min_pairs, "time_spent_sec": 30}
    elif template_id == "tpl_word_puzzle":
        # to win we'd need to know target phrase; a losing submit still exercises path
        payload = {"attempted_phrase": "WRONG GUESS", "strikes_used": 6}
    else:
        payload = {}

    r2 = requests.post(f"{BASE_URL}/games_v2/sessions/{sid}/submit",
                       json=payload, headers=headers, timeout=30)
    assert r2.status_code == 200, f"{campaign_id} submit: {r2.status_code} {r2.text}"
    j2 = r2.json()
    assert j2.get("result") in ("win", "lose")


# ================= Reservations (bookings mine / reschedule / cancel) =================
def _get_or_seed_active_booking(headers):
    """Return (booking_id, slots) of a non-cancelled booking, creating one if needed."""
    r = requests.get(f"{BASE_URL}/bookings/mine", headers=headers, timeout=30)
    assert r.status_code == 200
    items = [b for b in (r.json().get("items") or []) if b.get("status") != "cancelled"]
    if items and items[0].get("available_slots"):
        return items[0]["booking_id"], items[0]["available_slots"], items[0].get("slot")

    # Seed a booking via /bookings/available
    av = requests.get(f"{BASE_URL}/bookings/available", headers=headers, timeout=30).json()
    ven = next((v for v in (av.get("items") or []) if v.get("slots")), None)
    if not ven:
        pytest.skip("no booking campaigns available to seed")
    slot = ven["slots"][0]
    rb = requests.post(f"{BASE_URL}/bookings/{ven['campaign_id']}/book",
                       json={"slot": slot, "party_size": 2, "name": "QA",
                             "phone": "+15551234567"}, headers=headers, timeout=30)
    assert rb.status_code == 200, rb.text
    bid = rb.json()["booking"]["booking_id"]
    return bid, ven["slots"], slot


def test_bookings_mine_returns_slots(headers):
    r = requests.get(f"{BASE_URL}/bookings/mine", headers=headers, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "items" in j
    for b in j["items"]:
        assert "status" in b
        assert "available_slots" in b


def test_reschedule_valid_slot(headers):
    bid, slots, cur = _get_or_seed_active_booking(headers)
    target = next((s for s in slots if s != cur), slots[0])
    r = requests.post(f"{BASE_URL}/bookings/{bid}/reschedule",
                      json={"slot": target}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("slot") == target
    # verify persisted
    m = requests.get(f"{BASE_URL}/bookings/mine", headers=headers, timeout=30).json()
    updated = next((b for b in m["items"] if b["booking_id"] == bid), None)
    assert updated and updated["slot"] == target


def test_reschedule_bad_slot_returns_400(headers):
    bid, _, _ = _get_or_seed_active_booking(headers)
    r = requests.post(f"{BASE_URL}/bookings/{bid}/reschedule",
                      json={"slot": "NEVER-EXISTS-99:99"}, headers=headers, timeout=30)
    assert r.status_code == 400
    body = r.json()
    assert (body.get("detail") or {}).get("code") == "bad_slot" or "bad_slot" in str(body)


def test_reschedule_not_found_returns_404(headers):
    r = requests.post(f"{BASE_URL}/bookings/bk_doesnotexist_xxx/reschedule",
                      json={"slot": "18:00"}, headers=headers, timeout=30)
    assert r.status_code == 404


def test_cancel_booking_and_idempotent(headers):
    # Seed a fresh one to cancel
    av = requests.get(f"{BASE_URL}/bookings/available", headers=headers, timeout=30).json()
    ven = next((v for v in (av.get("items") or []) if v.get("slots")), None)
    if not ven:
        pytest.skip("no booking venues")
    rb = requests.post(f"{BASE_URL}/bookings/{ven['campaign_id']}/book",
                       json={"slot": ven["slots"][0], "party_size": 2,
                             "name": "QA-Cancel", "phone": "+15550001111"},
                       headers=headers, timeout=30)
    assert rb.status_code == 200
    bid = rb.json()["booking"]["booking_id"]

    r1 = requests.post(f"{BASE_URL}/bookings/{bid}/cancel", headers=headers, timeout=30)
    assert r1.status_code == 200
    assert r1.json()["status"] == "cancelled"

    # Idempotent — second call is safe
    r2 = requests.post(f"{BASE_URL}/bookings/{bid}/cancel", headers=headers, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


# ================= Gift Card Redeem =================
def _get_or_buy_active_card(headers):
    r = requests.get(f"{BASE_URL}/giftcards/mine", headers=headers, timeout=30)
    assert r.status_code == 200
    items = [c for c in (r.json().get("items") or [])
             if c.get("status") == "active" and int(c.get("balance_cents", 0)) > 0]
    if items:
        return items[0]
    # Buy one with points
    cat = requests.get(f"{BASE_URL}/giftcards/catalog", headers=headers, timeout=30).json()
    prod = cat["items"][0]
    denom = prod["denominations_cents"][0]
    if cat.get("points_balance", 0) < denom:  # not enough points
        pytest.skip("no active card with balance and insufficient points to seed")
    rp = requests.post(f"{BASE_URL}/giftcards/purchase",
                       json={"product_id": prod["product_id"],
                             "amount_cents": denom, "method": "points"},
                       headers=headers, timeout=30)
    assert rp.status_code == 200, rp.text
    return rp.json()["card"]


def test_redeem_deducts_balance(headers):
    card = _get_or_buy_active_card(headers)
    cid = card["card_id"]
    start_bal = int(card["balance_cents"])
    spend = min(500, start_bal - 1) if start_bal > 1 else start_bal
    if spend <= 0:
        pytest.skip("card balance too small")
    r = requests.post(f"{BASE_URL}/giftcards/{cid}/redeem",
                      json={"amount_cents": spend}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["amount_cents"] == spend
    assert j["balance_cents"] == start_bal - spend
    # verify via /mine
    m = requests.get(f"{BASE_URL}/giftcards/mine", headers=headers, timeout=30).json()
    c2 = next((c for c in m["items"] if c["card_id"] == cid), None)
    assert c2 and int(c2["balance_cents"]) == start_bal - spend


def test_redeem_insufficient_balance_400(headers):
    card = _get_or_buy_active_card(headers)
    cid = card["card_id"]
    bal = int(card["balance_cents"])
    r = requests.post(f"{BASE_URL}/giftcards/{cid}/redeem",
                      json={"amount_cents": bal + 100_000}, headers=headers, timeout=30)
    assert r.status_code == 400
    body = r.json()
    assert "insufficient_balance" in str(body)


def test_redeem_zero_balance_marks_spent(headers):
    card = _get_or_buy_active_card(headers)
    cid = card["card_id"]
    bal = int(card["balance_cents"])
    if bal <= 0:
        pytest.skip("card already empty")
    r = requests.post(f"{BASE_URL}/giftcards/{cid}/redeem",
                      json={"amount_cents": bal}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["balance_cents"] == 0
    assert j["status"] == "spent"
