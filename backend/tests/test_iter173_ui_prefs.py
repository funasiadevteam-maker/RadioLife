"""Iter173 — Per-user UI prefs (player dock) regression."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


def test_get_ui_prefs_initial(client):
    r = client.get(f"{BASE_URL}/api/me/ui-prefs", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "ui_prefs" in data
    assert isinstance(data["ui_prefs"], dict)


def test_put_float_and_read_back(client):
    r = client.put(f"{BASE_URL}/api/me/ui-prefs", json={"player_dock": "float"}, timeout=10)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    r2 = client.get(f"{BASE_URL}/api/me/ui-prefs", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["ui_prefs"]["player_dock"] == "float"


@pytest.mark.parametrize("dock", ["bottom", "top", "left", "right", "float"])
def test_all_valid_docks(client, dock):
    r = client.put(f"{BASE_URL}/api/me/ui-prefs", json={"player_dock": dock}, timeout=10)
    assert r.status_code == 200
    r2 = client.get(f"{BASE_URL}/api/me/ui-prefs", timeout=10)
    assert r2.json()["ui_prefs"]["player_dock"] == dock


def test_invalid_dock_400(client):
    r = client.put(f"{BASE_URL}/api/me/ui-prefs", json={"player_dock": "middle"}, timeout=10)
    assert r.status_code == 400
    body = r.json()
    # FastAPI wraps HTTPException detail in {"detail": ...}
    assert body.get("detail", {}).get("code") == "invalid_player_dock" or body.get("code") == "invalid_player_dock"


def test_reset_to_bottom(client):
    r = client.put(f"{BASE_URL}/api/me/ui-prefs", json={"player_dock": "bottom"}, timeout=10)
    assert r.status_code == 200
