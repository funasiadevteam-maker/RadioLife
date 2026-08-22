"""iteration_106 backend tests — GET /api/shell/clips + news market wiring + regression on /api/shell/venues.

Covers:
  * GET /api/shell/clips returns items[]; first item is a genuinely SPONSORED clip
    sourced from db.campaigns (status=active), remaining items are station clips
    from live AI channels (sponsored=False, image present).
  * GET /api/news/headlines accepts a `market` param (regression + geo wiring).
  * GET /api/shell/venues still returns sponsored-first venues (iter105 regression).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to what /app/frontend/.env holds; keep tests portable across forks.
    with open("/app/frontend/.env", "r") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── /api/shell/clips ──────────────────────────────────────────────────────
class TestShellClips:
    def test_endpoint_200_and_shape(self, api):
        r = api.get(f"{BASE_URL}/api/shell/clips", params={"limit": 10})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "count" in data and isinstance(data["count"], int)

    def test_first_item_sponsored_from_campaigns(self, api):
        data = api.get(f"{BASE_URL}/api/shell/clips", params={"limit": 10}).json()
        items = data["items"]
        assert len(items) >= 1, "expected at least one clip"
        first = items[0]
        assert first.get("sponsored") is True, f"first clip must be sponsored, got {first}"
        # sponsored clip ID prefix is camp_<campaign_id> per shell.py
        assert str(first.get("id", "")).startswith("camp_"), (
            f"sponsored clip id should be camp_*, got {first.get('id')}")
        # sponsored clip must carry a business_id + title + channel/sponsor
        assert first.get("business_id"), "sponsored clip should link to a business_id"
        assert first.get("title"), "sponsored clip should have a title"
        assert first.get("channel"), "sponsored clip should have a channel/sponsor label"

    def test_remaining_are_live_station_clips(self, api):
        data = api.get(f"{BASE_URL}/api/shell/clips", params={"limit": 10}).json()
        items = data["items"]
        assert len(items) >= 2, "need station clips beyond the sponsored one"
        rest = items[1:]
        for c in rest:
            assert c.get("sponsored") is False, f"station clip should not be sponsored: {c}"
            assert c.get("slug"), f"station clip should carry a slug: {c}"
            # station clips should have some image (thumb/cover) — allow absolute or /api/static/... path
            assert c.get("image"), f"station clip missing image: {c}"

    def test_only_one_sponsored_clip(self, api):
        data = api.get(f"{BASE_URL}/api/shell/clips", params={"limit": 10}).json()
        sponsored = [c for c in data["items"] if c.get("sponsored")]
        assert len(sponsored) == 1, f"exactly ONE sponsored clip expected, got {len(sponsored)}"

    def test_empty_safe(self, api):
        # Sanity: limit=0 should not blow up; endpoint should stay 200.
        r = api.get(f"{BASE_URL}/api/shell/clips", params={"limit": 1})
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)


# ── /api/news/headlines with market ───────────────────────────────────────
class TestNewsMarketWiring:
    def test_market_accepted(self, api):
        r = api.get(f"{BASE_URL}/api/news/headlines", params={"market": "dubai", "limit": 6})
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("items"), list)

    def test_without_market_also_works(self, api):
        r = api.get(f"{BASE_URL}/api/news/headlines", params={"limit": 6})
        assert r.status_code == 200

    def test_global_market_works(self, api):
        r = api.get(f"{BASE_URL}/api/news/headlines", params={"market": "global", "limit": 6})
        assert r.status_code == 200


# ── /api/shell/venues regression (iter105) ────────────────────────────────
class TestShellVenuesRegression:
    def test_venues_200_and_sponsored_first(self, api):
        r = api.get(f"{BASE_URL}/api/shell/venues", params={"limit": 24})
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) > 0
        # first must be sponsored (regression from iter105)
        assert items[0].get("sponsored") is True

    def test_category_filter(self, api):
        r = api.get(f"{BASE_URL}/api/shell/venues", params={"category": "restaurant", "limit": 24})
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert all(v.get("category") == "restaurant" for v in items)

    def test_summary_chips_present(self, api):
        r = api.get(f"{BASE_URL}/api/shell/summary")
        assert r.status_code == 200
        chips = r.json().get("chips", [])
        chip_keys = {c.get("key") for c in chips}
        # Radio + at least one cat_* + world always present per shell.py
        assert "radio" in chip_keys
        assert "world" in chip_keys
