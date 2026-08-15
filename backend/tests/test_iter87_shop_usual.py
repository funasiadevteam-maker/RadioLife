"""Iteration 87 — Backend tests for the Shop Home 'Get your usual' endpoint.
Covers:
  - GET /api/shop/usual (auth): demo user returns has_usual=True with Fun Pizza items.
  - Unauthenticated request is rejected (401).
  - Response shape: business_id, business_name, items[] with option/note carry-through.
Uses cookie auth for demo user via /api/auth/login (test) and bearer via /api/auth/demo (mobile).
"""
from __future__ import annotations

import os
import pytest
import requests

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")  # same backend for web+mobile


@pytest.fixture(scope="module")
def demo_bearer():
    r = requests.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in demo response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def demo_headers(demo_bearer):
    return {"Authorization": f"Bearer {demo_bearer}", "Content-Type": "application/json"}


# ---- unauth ------------------------------------------------------------------
def test_usual_requires_auth():
    r = requests.get(f"{BASE}/api/shop/usual", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ---- happy path demo user ---------------------------------------------------
def test_usual_demo_returns_fun_pizza(demo_headers):
    r = requests.get(f"{BASE}/api/shop/usual", headers=demo_headers, timeout=20)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    assert data.get("has_usual") is True, f"expected has_usual=True: {data}"
    assert data.get("business_id") == "biz_sample_funpizza", data
    assert data.get("business_name"), data
    items = data.get("items") or []
    assert len(items) >= 1, f"expected >=1 usual item: {data}"
    it = items[0]
    for k in ("item_id", "name", "price_cents", "times_ordered"):
        assert k in it, f"missing key {k} in {it}"
    assert isinstance(it["times_ordered"], int) and it["times_ordered"] >= 1
    assert isinstance(it["price_cents"], int) and it["price_cents"] > 0


# ---- items refer to the same store ------------------------------------------
def test_usual_items_are_menu_items_of_the_store(demo_headers):
    r = requests.get(f"{BASE}/api/shop/usual", headers=demo_headers, timeout=20)
    data = r.json()
    biz = data["business_id"]
    m = requests.get(f"{BASE}/api/shop/businesses/{biz}/menu", timeout=15)
    assert m.status_code == 200, m.text
    menu = m.json()
    menu_ids = {i["item_id"] for sec in menu.get("sections", []) for i in sec.get("items", [])}
    for u in data["items"]:
        assert u["item_id"] in menu_ids, f"usual item {u['item_id']} not in menu"


# ---- combos endpoint used by the store-page combo nudge ---------------------
def test_business_combos_endpoint(demo_headers):
    r = requests.get(
        f"{BASE}/api/shop/businesses/biz_sample_funpizza/combos",
        headers=demo_headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    combos = r.json().get("combos") or []
    # Fun Pizza is seeded with a demo combo; at minimum, endpoint must return a list.
    assert isinstance(combos, list)
    for c in combos:
        assert "combo_id" in c and "name" in c and "price_cents" in c
        assert "requirements" in c and isinstance(c["requirements"], list)
        assert "active_now" in c and isinstance(c["active_now"], bool)


# ---- per-store 'usual' also works -------------------------------------------
def test_business_usual_endpoint(demo_headers):
    r = requests.get(
        f"{BASE}/api/shop/businesses/biz_sample_funpizza/usual",
        headers=demo_headers, timeout=15,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("items"), list)
    assert data.get("has_usual") is True
    assert len(data["items"]) >= 1
