"""Iter 186 — Bar Skin editor + Win Wallet + Reminder countdown backend contracts."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
BIZ = "biz_demo_bar"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def freeuser():
    return _login("freeuser@bigfm.dubai", "FreePass123!")


# ── ENH 2 — Bar Skin Editor ─────────────────────────────────────────
def test_get_bar_game_is_owner_true_for_demo(demo):
    r = demo.get(f"{BASE_URL}/api/bar-games/{BIZ}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("eligible") is True
    assert d.get("is_owner") is True, f"expected is_owner true for demo: {d}"


def test_get_bar_game_is_owner_false_for_freeuser(freeuser):
    r = freeuser.get(f"{BASE_URL}/api/bar-games/{BIZ}", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("is_owner") is False, f"expected is_owner false for freeuser: {d}"


def test_skin_put_403_for_non_owner(freeuser):
    r = freeuser.put(
        f"{BASE_URL}/api/bar-games/{BIZ}/skin",
        json={"accent": "#111111", "accent2": "#222222", "logo_url": None,
              "segments": [{"label": "A", "emoji": "🍺", "win": True, "weight": 8},
                           {"label": "B", "emoji": "🍹", "win": False, "weight": 8},
                           {"label": "C", "emoji": "🍸", "win": True, "weight": 8}]},
        timeout=15,
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"
    body = r.json()
    code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else None
    assert code == "not_bar_owner", f"expected code=not_bar_owner: {body}"


def test_skin_put_owner_saves(demo):
    # Read current config
    r0 = demo.get(f"{BASE_URL}/api/bar-games/{BIZ}", timeout=15).json()
    original_segments = r0["config"]["segments"]
    original_theme = r0["config"].get("theme", {})

    new_segs = [
        {"label": s["label"], "emoji": s["emoji"], "win": s.get("win", True), "weight": s.get("weight", 8)}
        for s in original_segments
    ]
    r = demo.put(
        f"{BASE_URL}/api/bar-games/{BIZ}/skin",
        json={"accent": "#22d3ee", "accent2": "#f472b6",
              "logo_url": original_theme.get("logo_url"), "segments": new_segs},
        timeout=15,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("config", {}).get("theme", {}).get("accent") == "#22d3ee"

    # Verify via GET
    r2 = demo.get(f"{BASE_URL}/api/bar-games/{BIZ}", timeout=15).json()
    assert r2["config"]["theme"]["accent"] == "#22d3ee"


# ── ENH 4 — Win Wallet ("My drink perks") ────────────────────────────
def test_wallet_lists_seeded_perk(demo):
    r = demo.get(f"{BASE_URL}/api/bar-games/wallet", timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    d = r.json()
    assert isinstance(d.get("items"), list)
    codes = [i.get("code") for i in d["items"]]
    assert "BAR-NEON2FOR" in codes, f"expected seeded BAR-NEON2FOR in wallet: {codes}"
    item = next(i for i in d["items"] if i["code"] == "BAR-NEON2FOR")
    assert item["redeemed"] is False
    assert "Free Neon Mojito" in (item.get("label") or "")


def test_wallet_empty_for_freeuser(freeuser):
    r = freeuser.get(f"{BASE_URL}/api/bar-games/wallet", timeout=15)
    assert r.status_code == 200
    # freeuser has no seeded perks
    d = r.json()
    assert d.get("count", 0) == 0 or len(d.get("items", [])) == 0


# ── ENH 3 — Reminder / scheduled show still available ────────────────
def test_upcoming_show_has_scheduled_at(demo):
    r = demo.get(f"{BASE_URL}/api/social/liveshows?status=scheduled", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    show = next((s for s in items if s.get("show_id") == "ls_demo_scheduled_01"), None)
    assert show is not None, f"seeded show ls_demo_scheduled_01 missing: {[s.get('show_id') for s in items]}"
    assert show.get("scheduled_at"), "scheduled_at required for countdown"
