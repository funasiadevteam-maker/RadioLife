"""Phase A - Partner API v1 discovery endpoints & foundation tests.

Covers:
- /status (public), /capabilities, /inventory, /markets, /targeting/options,
  /rate-card, /stations (cursor pagination), auth/scope enforcement,
  X-Request-ID + X-RadioLife-API-Version response headers, normalized error
  envelope (adds `error` while preserving legacy `detail`),
- regression: /me, /products, /openapi.json.
"""
import os
import pytest
import requests
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or \
    dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")
V1 = f"{BASE_URL}/api/v1"

# Sandbox key with catalog:read scope
API_KEY = "rlk_test_BdmWmROSnKO1.7gBxOXKXEIsKhfWOwunaKO2zBlhrtvbgU8uAmkZBwIk"

EXPECTED_MARKETS = {"dubai", "new_york", "london", "mumbai", "los_angeles", "dfw"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {API_KEY}"})
    return sess


def _assert_headers(r):
    assert r.headers.get("X-RadioLife-API-Version") == "1", r.headers
    assert r.headers.get("X-Request-ID"), r.headers


# ── /status (public) ────────────────────────────────────────────────
def test_status_public_no_auth():
    r = requests.get(f"{V1}/status", timeout=15)
    assert r.status_code == 200, r.text
    _assert_headers(r)
    body = r.json()
    assert body.get("status") == "operational"
    assert body.get("api_version") == "1"
    assert isinstance(body.get("services"), dict) and body["services"]


def test_status_request_id_echoed():
    rid = "test-req-abc-123"
    r = requests.get(f"{V1}/status", headers={"X-Request-ID": rid}, timeout=15)
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID") == rid


# ── /capabilities ───────────────────────────────────────────────────
def test_capabilities(s):
    r = s.get(f"{V1}/capabilities", timeout=15)
    assert r.status_code == 200, r.text
    _assert_headers(r)
    d = r.json()
    assert d.get("api_versions") == ["1"]
    ct = d.get("campaign_types") or []
    assert len(ct) == 17, f"expected 17 campaign_types, got {len(ct)}"
    api_bookable = [c for c in ct if c.get("api_bookable")]
    assert len(api_bookable) == 7, f"expected 7 api_bookable, got {len(api_bookable)}"
    assert d.get("inventory_types") and isinstance(d["inventory_types"], list)
    assert set(d.get("supported_markets") or []) == EXPECTED_MARKETS
    assert isinstance(d.get("supported_game_types"), list)
    assert isinstance(d.get("feature_flags"), dict)
    assert isinstance(d.get("scopes"), list) and "catalog:read" in d["scopes"]


# ── /inventory ──────────────────────────────────────────────────────
def test_inventory(s):
    r = s.get(f"{V1}/inventory", timeout=15)
    assert r.status_code == 200
    _assert_headers(r)
    cats = r.json().get("categories") or []
    assert cats
    labels = [c["label"] for c in cats]
    assert len(labels) == len(set(labels)), f"duplicate category labels: {labels}"
    for c in cats:
        assert "available" in c
        assert isinstance(c.get("products"), list) and c["products"]


# ── /markets ────────────────────────────────────────────────────────
def test_markets(s):
    r = s.get(f"{V1}/markets", timeout=15)
    assert r.status_code == 200
    _assert_headers(r)
    data = r.json().get("data") or []
    assert len(data) == 6, f"expected 6 markets got {len(data)}"
    ids = {m["market_id"] for m in data}
    assert ids == EXPECTED_MARKETS
    for m in data:
        for f in ("market_id", "city", "country", "timezone", "currency"):
            assert m.get(f), f"market missing {f}: {m}"


# ── /targeting/options ──────────────────────────────────────────────
def test_targeting_options(s):
    r = s.get(f"{V1}/targeting/options", timeout=15)
    assert r.status_code == 200
    _assert_headers(r)
    data = r.json().get("data") or []
    assert data
    keys = [t["key"] for t in data]
    for exp in ("market", "station", "daypart", "device"):
        assert exp in keys, f"targeting key {exp!r} missing"


# ── /rate-card ──────────────────────────────────────────────────────
def test_rate_card(s):
    r = s.get(f"{V1}/rate-card", timeout=15)
    assert r.status_code == 200
    _assert_headers(r)
    d = r.json()
    assert d.get("currency") == "USD"
    assert isinstance(d.get("pricing_models"), dict) and d["pricing_models"]
    base = d.get("base_rates") or []
    mults = d.get("multipliers") or []
    assert len(base) == 8, f"expected 8 base_rates, got {len(base)}"
    assert len(mults) == 5, f"expected 5 multipliers, got {len(mults)}"


# ── /stations pagination ────────────────────────────────────────────
def test_stations_pagination_and_next(s):
    r1 = s.get(f"{V1}/stations", params={"country": "AE", "limit": 3}, timeout=20)
    assert r1.status_code == 200, r1.text
    _assert_headers(r1)
    p1 = r1.json()
    assert "data" in p1 and "next_cursor" in p1 and "has_more" in p1
    if not p1["data"]:
        pytest.skip("no AE stations seeded — cannot exercise pagination")
    assert len(p1["data"]) <= 3
    if not p1.get("has_more"):
        return
    cur = p1["next_cursor"]
    assert cur
    r2 = s.get(f"{V1}/stations",
               params={"country": "AE", "limit": 3, "cursor": cur}, timeout=20)
    assert r2.status_code == 200, r2.text
    p2 = r2.json()
    ids1 = {x["station_id"] for x in p1["data"]}
    ids2 = {x["station_id"] for x in p2["data"]}
    assert ids1.isdisjoint(ids2), "page 2 overlaps page 1"


def test_stations_radiolife_type(s):
    r = s.get(f"{V1}/stations", params={"station_type": "radiolife"}, timeout=20)
    assert r.status_code == 200, r.text
    _assert_headers(r)
    data = r.json().get("data") or []
    assert len(data) == 14, f"expected 14 RadioLife AI channels, got {len(data)}"
    for c in data:
        assert c.get("station_type") == "radiolife"


def test_stations_invalid_cursor_normalized_envelope(s):
    r = s.get(f"{V1}/stations",
              params={"country": "AE", "cursor": "not-a-valid-cursor"}, timeout=15)
    assert r.status_code == 400, r.text
    _assert_headers(r)
    body = r.json()
    # legacy field
    assert "detail" in body
    # normalized envelope
    err = body.get("error") or {}
    assert err.get("code") == "invalid_cursor", body
    assert err.get("request_id"), body


# ── auth / scope ────────────────────────────────────────────────────
def test_unauth_returns_401_normalized_envelope():
    r = requests.get(f"{V1}/capabilities", timeout=15)
    assert r.status_code == 401, r.text
    _assert_headers(r)
    body = r.json()
    assert "detail" in body
    err = body.get("error") or {}
    assert err.get("code") in ("missing_bearer_token", "unauthorized"), body
    assert err.get("request_id"), body


# ── regression ──────────────────────────────────────────────────────
def test_regression_me(s):
    r = s.get(f"{V1}/me", timeout=15)
    assert r.status_code == 200, r.text
    _assert_headers(r)
    d = r.json()
    assert d.get("partner_id")
    assert d.get("environment") in ("LIVE", "SANDBOX")


def test_regression_products(s):
    r = s.get(f"{V1}/products", timeout=15)
    assert r.status_code == 200, r.text
    _assert_headers(r)
    d = r.json()
    assert isinstance(d.get("items"), list) and d["items"]


def test_regression_openapi_includes_new_paths():
    r = requests.get(f"{V1}/openapi.json", timeout=20)
    assert r.status_code == 200
    paths = (r.json() or {}).get("paths") or {}
    for p in ("/capabilities", "/stations", "/markets", "/inventory",
              "/targeting/options", "/rate-card", "/status"):
        assert p in paths, f"openapi missing {p}"
