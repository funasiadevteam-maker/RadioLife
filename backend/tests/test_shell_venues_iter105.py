"""Iter 105 — GET /api/shell/venues + summary chip parity."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

REQUIRED_KEYS = {"business_id", "name", "category", "category_label",
                 "image", "rating", "earn", "sponsored"}
TEST_TOKENS = ("TEST_", "Iter", "Test Shop", "QA Demo")


def _get(path, **params):
    r = requests.get(f"{BASE}{path}", params=params or None, timeout=15)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
    return r.json()


# ── /api/shell/venues (unauthenticated) ────────────────────────────────
def test_venues_default_returns_8_real_venues():
    data = _get("/api/shell/venues")
    items = data["items"]
    assert data["count"] == 8, f"expected 8 venues, got {data['count']}"
    assert len(items) == 8
    for v in items:
        assert REQUIRED_KEYS.issubset(v.keys()), f"missing keys in {v}"
        for tok in TEST_TOKENS:
            assert tok.lower() not in (v["name"] or "").lower(), \
                f"test/seed venue leaked: {v['name']}"


def test_venues_sponsored_first_ordering():
    items = _get("/api/shell/venues")["items"]
    seen_non_sponsored = False
    for v in items:
        if not v["sponsored"]:
            seen_non_sponsored = True
        elif seen_non_sponsored:
            raise AssertionError(f"sponsored {v['name']} appears after non-sponsored")


def test_venues_filter_cat_restaurant():
    d = _get("/api/shell/venues", category="cat_restaurant")
    assert d["count"] == 4
    assert all(v["category"] == "restaurant" for v in d["items"])


def test_venues_filter_cat_beauty():
    d = _get("/api/shell/venues", category="cat_beauty")
    assert d["count"] == 2
    assert all(v["category"] == "beauty" for v in d["items"])


def test_venues_filter_cat_fitness():
    d = _get("/api/shell/venues", category="cat_fitness")
    assert d["count"] == 1
    assert d["items"][0]["category"] == "fitness"


def test_venues_filter_cat_retail():
    d = _get("/api/shell/venues", category="cat_retail")
    assert d["count"] == 1
    assert d["items"][0]["category"] == "retail"


def test_venues_filter_raw_category_also_works():
    # Backend should accept both `cat_x` chip key and raw `x` category.
    d = _get("/api/shell/venues", category="restaurant")
    assert d["count"] == 4


# ── /api/shell/summary chip counts parity ──────────────────────────────
def test_summary_chip_counts_match_venue_counts():
    s = _get("/api/shell/summary")
    chips = {c["key"]: c.get("count") for c in s["chips"]}
    assert chips.get("cat_restaurant") == 4
    assert chips.get("cat_beauty") == 2
    assert chips.get("cat_fitness") == 1
    assert chips.get("cat_retail") == 1
    assert s["badges"]["shop"] == 8
