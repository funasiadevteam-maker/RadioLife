"""Tests for the Tube browse feed API - iteration 99."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── /api/browse/feed ────────────────────────────────────────────────────
class TestBrowseFeed:
    def test_feed_page0_all_shape(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "all"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "chips" in data, "chips missing on page 0"
        assert "blocks" in data
        assert data.get("has_more") is True
        assert isinstance(data["blocks"], list) and len(data["blocks"]) >= 1
        chip_keys = {c["key"] for c in data["chips"]}
        # main-agent expected chips
        for k in ("all", "shopping", "originals", "stations", "podcasts", "games"):
            assert k in chip_keys, f"chip {k} missing (got {chip_keys})"

    def test_feed_all_has_grid_block_with_items(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "all"}, timeout=30)
        data = r.json()
        grids = [b for b in data["blocks"] if b.get("kind") == "grid"]
        assert grids, "no grid block in page 0"
        assert grids[0]["items"], "grid items empty"

    def test_feed_page0_and_page1_return_different_blocks(self, session):
        r0 = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "all"}, timeout=30).json()
        r1 = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 1, "cat": "all"}, timeout=30).json()
        # page 1 must have blocks (rotating shelf variant differs)
        assert r1.get("has_more") is True
        assert r1["blocks"], "page 1 should have blocks"
        # extract the shelf/featured variant kinds/variants
        def sig(blocks):
            return tuple((b.get("kind"), b.get("variant")) for b in blocks)
        assert sig(r0["blocks"]) != sig(r1["blocks"]) or r0["blocks"] != r1["blocks"], \
            "page 1 identical to page 0 - rotation not happening"

    def test_feed_shopping_returns_shop_items(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "shopping"}, timeout=30).json()
        grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
        assert grid and grid["items"], "shopping grid missing/empty"
        # every item in shopping grid should be type=shop
        types = {i.get("type") for i in grid["items"]}
        assert types == {"shop"}, f"shopping grid contains non-shop items: {types}"
        # at least some should have a price
        priced = [i for i in grid["items"] if i.get("price")]
        assert priced, "no priced items in shopping grid"

    def test_feed_all_has_sprinkled_shop_tiles(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "all"}, timeout=30).json()
        grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
        assert grid, "no grid on all-page"
        shop_tiles = [i for i in grid["items"] if i.get("type") == "shop"]
        # main-agent says shop is sprinkled every 6 items → for a 10-item grid expect ~1
        assert shop_tiles, "no shop tiles sprinkled in 'all' grid"

    def test_feed_games_returns_playables_shelf(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "games"}, timeout=30).json()
        variants = [b.get("variant") for b in r["blocks"] if b.get("kind") == "shelf"]
        assert "playables" in variants, f"games cat missing playables shelf (variants={variants})"

    def test_feed_originals_filters(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 0, "cat": "originals"}, timeout=30).json()
        grid = next((b for b in r["blocks"] if b.get("kind") == "grid"), None)
        assert grid and grid["items"], "originals grid missing"
        # every returned item should be type=original (or fallback pool if empty)
        types = {i.get("type") for i in grid["items"]}
        assert "original" in types, f"originals cat returned no 'original' items: types={types}"

    def test_feed_recycles_forever(self, session):
        # verify a deep page (e.g., 20) still returns blocks + has_more True
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 20, "cat": "all"}, timeout=30).json()
        assert r["blocks"], "page 20 returned no blocks (should recycle)"
        assert r.get("has_more") is True

    def test_feed_page1_has_no_chips(self, session):
        r = session.get(f"{BASE_URL}/api/browse/feed", params={"page": 1, "cat": "all"}, timeout=30).json()
        # chips only sent on page 0 per implementation
        assert "chips" not in r, "chips should only be returned on page 0"


# ── /api/browse/home shop rail ─────────────────────────────────────────
class TestBrowseHomeShopRail:
    def test_home_includes_shop_rail(self, session):
        r = session.get(f"{BASE_URL}/api/browse/home", timeout=30)
        assert r.status_code == 200
        data = r.json()
        rail_keys = {rl["key"] for rl in data.get("rails", [])}
        assert "shop" in rail_keys, f"shop rail missing from /browse/home rails: {rail_keys}"
        shop_rail = next(rl for rl in data["rails"] if rl["key"] == "shop")
        assert shop_rail["items"], "shop rail empty"
        # at least one card has a price
        priced = [c for c in shop_rail["items"] if c.get("price")]
        assert priced, "no priced items in shop rail"
