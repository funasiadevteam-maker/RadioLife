"""Iteration 222 — Travel vertical: nearest-airport + trending w/ origin_city."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---- nearest-airport -------------------------------------------------------
class TestNearestAirport:
    def test_returns_200_and_schema(self, api):
        r = api.get(f"{BASE_URL}/api/travel/nearest-airport", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d, dict)
        assert "origin" in d and "city" in d and "confident" in d
        assert isinstance(d["origin"], str) and len(d["origin"]) == 3
        assert isinstance(d["city"], str) and d["city"]
        assert isinstance(d["confident"], bool)

    def test_fallback_contract(self, api):
        """Must never 500 — unknown/datacenter IP still returns a usable origin."""
        r = api.get(f"{BASE_URL}/api/travel/nearest-airport", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # IP may be datacenter; origin must still be a 3-letter IATA
        assert d["origin"].isalpha()


# ---- trending (origin switcher + origin_city) -----------------------------
class TestTrending:
    @pytest.mark.parametrize("origin,city", [("DXB", "Dubai"), ("DOH", "Doha"),
                                              ("LON", "London"), ("JED", "Jeddah")])
    def test_trending_hubs_include_origin_city(self, api, origin, city):
        r = api.get(f"{BASE_URL}/api/travel/trending",
                    params={"origin": origin, "limit": 6}, timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("origin") == origin
        assert d.get("origin_city") == city
        assert isinstance(d.get("items"), list)
        # If items present, verify shape
        if d["items"]:
            it = d["items"][0]
            for k in ("origin", "destination", "city", "country", "emoji",
                      "price", "transfers", "deep_link"):
                assert k in it, f"missing {k}"
            assert it["origin"] == origin
            assert isinstance(it["price"], int)

    def test_trending_default_origin_dxb(self, api):
        r = api.get(f"{BASE_URL}/api/travel/trending", timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert d["origin"] == "DXB"
        assert d["origin_city"] == "Dubai"

    def test_trending_unknown_origin_no_500(self, api):
        """Unknown IATA code should return items=[] (or stale cache) WITHOUT 500."""
        r = api.get(f"{BASE_URL}/api/travel/trending",
                    params={"origin": "ZZZ", "limit": 4}, timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert d["origin"] == "ZZZ"
        assert isinstance(d["items"], list)
        # origin_city falls back to the raw IATA when unknown
        assert d["origin_city"] == "ZZZ"

    def test_trending_cache_flag_present(self, api):
        r = api.get(f"{BASE_URL}/api/travel/trending",
                    params={"origin": "LON"}, timeout=25)
        d = r.json()
        assert "cached" in d
        # Hitting twice in quick succession should surface cached=True
        r2 = api.get(f"{BASE_URL}/api/travel/trending",
                     params={"origin": "LON"}, timeout=25)
        d2 = r2.json()
        assert d2.get("cached") is True

    def test_trending_limit_respected(self, api):
        r = api.get(f"{BASE_URL}/api/travel/trending",
                    params={"origin": "DXB", "limit": 3}, timeout=25)
        d = r.json()
        assert len(d["items"]) <= 3
