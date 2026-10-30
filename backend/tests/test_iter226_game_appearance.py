"""Game Art Admin — /api/admin/game-appearance/* + /api/games/appearance.

Covers:
- admin list (requires admin auth)
- public list excludes hidden games
- PUT upsert (label/color/icon/hidden) persists via GET
- POST reorder reorders via GET
- POST image upload returns image_url and persists
- DELETE image clears image_url
- 404 for unknown key, 400 for bad icon, 401 for non-admin
"""
import io
import os

import pytest
import requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("session_token")
    assert token, f"no session_token in response: {r.json()}"
    return token


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


@pytest.fixture(scope="module")
def demo_headers():
    return {"Authorization": f"Bearer {_login(DEMO_EMAIL, DEMO_PASS)}"}


class TestAuthGating:
    def test_admin_list_requires_admin(self, demo_headers):
        # non-admin -> 401/403
        r = requests.get(f"{API}/admin/game-appearance", headers=demo_headers, timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_list_ok(self, admin_headers):
        r = requests.get(f"{API}/admin/game-appearance", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "games" in data and "icons" in data
        assert isinstance(data["games"], list) and len(data["games"]) >= 10
        g = data["games"][0]
        for k in ("key", "kind", "label", "color", "icon", "hidden", "web_key", "mobile_key"):
            assert k in g, f"missing key {k} in game row {g}"

    def test_public_appearance_ok(self, demo_headers):
        r = requests.get(f"{API}/games/appearance", headers=demo_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "games" in data
        # must only include visible games
        assert all(g["hidden"] is False for g in data["games"])


class TestUpsert:
    def test_put_label_color_icon_persists(self, admin_headers):
        key = "trivia"
        new_label = "TEST_Trivia_Blitz"
        new_color = "#123456"
        r = requests.put(f"{API}/admin/game-appearance/{key}",
                          json={"label": new_label, "color": new_color, "icon": "star",
                                "hidden": False},
                          headers=admin_headers, timeout=15)
        assert r.status_code == 200
        g = r.json()["game"]
        assert g["label"] == new_label
        assert g["color"] == new_color
        assert g["icon"] == "star"
        # GET to verify persisted
        r2 = requests.get(f"{API}/admin/game-appearance", headers=admin_headers, timeout=15)
        row = next((x for x in r2.json()["games"] if x["key"] == key), None)
        assert row and row["label"] == new_label
        assert row["color"] == new_color
        assert row["icon"] == "star"

    def test_put_unknown_key_404(self, admin_headers):
        r = requests.put(f"{API}/admin/game-appearance/nonexistent_game",
                          json={"label": "x"}, headers=admin_headers, timeout=15)
        assert r.status_code == 404

    def test_put_bad_icon_400(self, admin_headers):
        r = requests.put(f"{API}/admin/game-appearance/trivia",
                          json={"icon": "notavalidicon"}, headers=admin_headers, timeout=15)
        assert r.status_code == 400

    def test_hidden_excluded_from_public(self, admin_headers, demo_headers):
        key = "dice"
        # hide
        r = requests.put(f"{API}/admin/game-appearance/{key}",
                          json={"hidden": True}, headers=admin_headers, timeout=15)
        assert r.status_code == 200
        pub = requests.get(f"{API}/games/appearance", headers=demo_headers, timeout=15).json()
        assert all(g["key"] != key for g in pub["games"]), "hidden game leaked to public"
        # restore
        r = requests.put(f"{API}/admin/game-appearance/{key}",
                          json={"hidden": False}, headers=admin_headers, timeout=15)
        assert r.status_code == 200


class TestReorder:
    def test_reorder_persists(self, admin_headers):
        r = requests.get(f"{API}/admin/game-appearance", headers=admin_headers, timeout=15)
        keys = [g["key"] for g in r.json()["games"]]
        assert len(keys) >= 3
        # swap first two
        new_order = [keys[1], keys[0]] + keys[2:]
        r2 = requests.post(f"{API}/admin/game-appearance/reorder",
                            json={"keys": new_order}, headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        after = [g["key"] for g in r2.json()["games"]]
        assert after[0] == new_order[0] and after[1] == new_order[1], \
            f"reorder didn't persist: {after[:3]} expected {new_order[:3]}"


class TestImage:
    def test_upload_and_clear(self, admin_headers):
        key = "scratch"
        # 1x1 PNG
        png_bytes = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                      b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
                      b"\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x5c\xcd"
                      b"\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82")
        files = {"file": ("tile.png", io.BytesIO(png_bytes), "image/png")}
        r = requests.post(f"{API}/admin/game-appearance/{key}/image",
                           headers=admin_headers, files=files, timeout=30)
        assert r.status_code == 200, r.text
        url = r.json().get("image_url")
        assert url and "/api/static/game_art/" in url
        # verify via GET
        g = requests.get(f"{API}/admin/game-appearance", headers=admin_headers, timeout=15).json()
        row = next((x for x in g["games"] if x["key"] == key), None)
        assert row and row["image_url"] == url
        # clear
        r2 = requests.delete(f"{API}/admin/game-appearance/{key}/image",
                              headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        g2 = requests.get(f"{API}/admin/game-appearance", headers=admin_headers, timeout=15).json()
        row2 = next((x for x in g2["games"] if x["key"] == key), None)
        assert row2 and row2["image_url"] in (None, "")

    def test_upload_unknown_key_404(self, admin_headers):
        files = {"file": ("x.png", io.BytesIO(b"\x89PNG\r\n"), "image/png")}
        r = requests.post(f"{API}/admin/game-appearance/unknownkey/image",
                           headers=admin_headers, files=files, timeout=15)
        assert r.status_code == 404

    def test_upload_empty_file_400(self, admin_headers):
        files = {"file": ("empty.png", io.BytesIO(b""), "image/png")}
        r = requests.post(f"{API}/admin/game-appearance/spin/image",
                           headers=admin_headers, files=files, timeout=15)
        assert r.status_code == 400
