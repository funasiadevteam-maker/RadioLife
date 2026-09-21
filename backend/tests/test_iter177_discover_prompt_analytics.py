"""Iter 177 — GAME DISCOVERY / NEW-CITY PROMPT / SPONSOR ANALYTICS / PRIZE PREVIEW backend."""
import os
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
TEST = {"email": "test@bigfm.dubai", "password": "TestUser123!"}
SEED_GAME = "wheel_spn_02564c15d4"
KARAK_BID = "biz_karak_cafe_karama"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


# ── GAME DISCOVERY ──
class TestSponsorDiscover:
    def test_returns_sponsor_wheel_and_no_house(self):
        s = _login(DEMO)
        r = s.get(f"{API}/games/sponsor/discover", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        ids = [it["game_id"] for it in items]
        # seeded sponsor wheel is present
        assert SEED_GAME in ids, f"missing {SEED_GAME}; got {ids}"
        seed = next(it for it in items if it["game_id"] == SEED_GAME)
        assert seed.get("sponsor_name") == "Karak Cafe"
        assert seed.get("top_prize") is not None
        assert int(seed.get("daily_spins") or 0) == 3
        # house games must NOT appear (they lack sponsor_business_id)
        assert "wheel_house" not in ids
        assert "scratch_house" not in ids


# ── NEW-CITY PROMPT ──
class TestGeoMeDetected:
    def test_geo_me_returns_detected_fields(self):
        s = _login(DEMO)
        r = s.get(f"{API}/geo/me", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "market" in data
        assert "detected_market" in data
        assert "detected_city" in data


# ── SPONSOR ANALYTICS ──
class TestSponsorAnalytics:
    def test_owner_gets_stats(self):
        s = _login(TEST)
        r = s.get(f"{API}/games/sponsor/{KARAK_BID}/branded-games/{SEED_GAME}/analytics", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["plays", "wins", "win_rate", "unique_players",
                  "points_awarded", "coupons_won", "coupons_redeemed",
                  "prize_distribution"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["prize_distribution"], list)
        assert d["game_id"] == SEED_GAME

    def test_non_owner_gets_403_or_404(self):
        s = _login(DEMO)
        r = s.get(f"{API}/games/sponsor/{KARAK_BID}/branded-games/{SEED_GAME}/analytics", timeout=15)
        assert r.status_code in (403, 404), r.text


# ── REGRESSION: wheel list surfaces sponsor game and it's playable ──
class TestWheelListRegression:
    def test_wheel_list_contains_seed_and_config_loads(self):
        s = _login(DEMO)
        r = s.get(f"{API}/games/wheel/list", timeout=15)
        assert r.status_code == 200
        ids = [it["game_id"] for it in (r.json().get("items") or [])]
        assert SEED_GAME in ids
        c = s.get(f"{API}/games/wheel/config?game_id={SEED_GAME}", timeout=15)
        assert c.status_code == 200
        cfg = c.json()
        assert cfg["game_id"] == SEED_GAME
        assert cfg["sponsor_name"] == "Karak Cafe"
        assert cfg["daily_spins"] == 3
