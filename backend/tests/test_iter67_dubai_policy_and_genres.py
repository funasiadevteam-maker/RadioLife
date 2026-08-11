"""Iteration 67 — Dubai policy + music_genre backfill on Radio browse.

Covers:
  A) GET /api/radio/browse?country=AE&limit=100 — should return exactly the 8
     allowlisted UAE stations (country_code=AE) with a non-empty music_genre.
     'Beat Anthems' must NOT be present.
  B) GET /api/radio/browse?q=Beat — hidden 'Beat Anthems' must NOT appear;
     Beat 97.8 + Urban Beat should.
  C) GET /api/stations/flagship?region=DUBAI — must not include 'Beat Anthems'.
  D) GET /api/radio/browse?source=imported&country=AE — exactly the 8 with
     music_genre, no dubai_hidden stations.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
                      "https://mobile-games-v2.preview.emergentagent.com"

ALLOWED_8 = {
        "Big 106.2 UAE", "Talk 100.3 UAE", "Luv 107.1 UAE", "Beat 97.8",
        "Big Melodies", "Urban Beat", "Luv Legends", "Chilled Luv",
}


def _items(r):
        d = r.json()
        return d.get("items", d) if isinstance(d, dict) else d


class TestDubaiPolicyBrowse:
        # A) browse country=AE
        def test_browse_country_ae_all_source(self):
                r = requests.get(f"{BASE_URL}/api/radio/browse?country=AE&limit=100", timeout=15)
                assert r.status_code == 200
                items = _items(r)
                names = {i.get("name") for i in items}
                # All 8 present
                assert ALLOWED_8.issubset(names), f"Missing from AE list: {ALLOWED_8 - names}"
                # No hidden Beat Anthems
                assert "Beat Anthems" not in names
                # 8 UAE stations (country_code == AE) — exactly 8 and each has a genre
                ae_items = [i for i in items if i.get("country_code") == "AE"]
                assert len(ae_items) == 8, f"Expected 8 AE cc items, got {len(ae_items)}: {[i.get('name') for i in ae_items]}"
                for i in ae_items:
                        assert i.get("music_genre"), f"Missing music_genre on {i.get('name')}"

        # D) source=imported&country=AE — exactly 8 with genres
        def test_browse_imported_ae_exactly_eight(self):
                r = requests.get(
                        f"{BASE_URL}/api/radio/browse?source=imported&country=AE&limit=100",
                        timeout=15,
                )
                assert r.status_code == 200
                items = _items(r)
                names = {i.get("name") for i in items}
                assert names == ALLOWED_8, f"Expected exactly {ALLOWED_8}, got {names}"
                for i in items:
                        assert i.get("music_genre"), f"No genre on {i.get('name')}"
                        assert i.get("country_code") == "AE"


class TestBeatSearchExcludesHidden:
        # B) q=Beat — hidden Beat Anthems excluded, Beat 97.8 + Urban Beat present
        def test_search_beat_no_anthems(self):
                r = requests.get(f"{BASE_URL}/api/radio/browse?q=Beat&limit=50", timeout=15)
                assert r.status_code == 200
                items = _items(r)
                names = [i.get("name") for i in items]
                assert "Beat Anthems" not in names, "Hidden station Beat Anthems leaked in q=Beat"
                assert "Beat 97.8" in names
                assert "Urban Beat" in names


class TestFlagshipDubaiHiddenGuard:
        # C) flagship region=DUBAI must not include Beat Anthems
        def test_flagship_dubai_excludes_beat_anthems(self):
                r = requests.get(f"{BASE_URL}/api/stations/flagship?region=DUBAI", timeout=15)
                assert r.status_code == 200
                items = _items(r)
                names = [i.get("name") for i in items] if isinstance(items, list) else []
                assert "Beat Anthems" not in names

        def test_flagship_default_excludes_beat_anthems(self):
                # Regardless of region param, the dubai_hidden guard should keep
                # Beat Anthems out of the default flagship response.
                r = requests.get(f"{BASE_URL}/api/stations/flagship", timeout=15)
                assert r.status_code == 200
                items = _items(r)
                names = [i.get("name") for i in items] if isinstance(items, list) else []
                assert "Beat Anthems" not in names


class TestBrandedChannelGenres:
        # E) Branded channels (source=bigfm_ai) should each carry a music_genre
        #    per this iteration's spec ("each branded channel gets a music_genre").
        def test_branded_channels_have_genre(self):
                r = requests.get(f"{BASE_URL}/api/radio/browse?source=bigfm_ai&limit=100", timeout=15)
                assert r.status_code == 200
                items = _items(r)
                assert isinstance(items, list) and len(items) > 0, "No branded channels returned"
                missing = [i.get("name") for i in items if not i.get("music_genre")]
                assert not missing, (
                        f"{len(missing)} branded channels missing music_genre in API response: {missing}"
                )
