"""Iteration 119 — Games: FREE (house) 1/day per type vs SPONSORED (FPK) unlimited.

Covers:
- POST /api/play/resolve: free game 1st play 200; 2nd same-type same-day → 429
  daily_type_limit_reached; idempotent replay returns original (no 429).
- FPK sponsored games: multiple plays with distinct idempotency keys all 200.
- FPK prizes: coupon 10/20/30/40/50% with weights 50/25/13/8/4; daily_issued
  increments and daily_issued_date set to today.
- GET /api/games_v2/play_and_win: play_eligibility for sponsored FPK
  {sponsored:true, unlimited:true, can_play:true}; house games can_play flag.
"""
import os
import secrets
import requests
import pytest
import pymongo
import datetime as dt

def _load_frontend_env(key: str) -> str:
    v = os.environ.get(key)
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith(f"{key}="):
                    return ln.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        pass
    raise RuntimeError(f"{key} not set")


BASE_URL = _load_frontend_env("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

FPK_IDS = [
    "cmp_fpk_spin", "cmp_fpk_scratch", "cmp_fpk_quiz",
    "cmp_fpk_mystery", "cmp_fpk_memory", "cmp_fpk_word", "cmp_fpk_card",
]


@pytest.fixture(scope="module")
def mongo():
    c = pymongo.MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _register_fresh_user():
    """Create a brand-new listener account so no daily plays are used."""
    s = requests.Session()
    email = f"TEST_iter119_{secrets.token_hex(4)}@bigfm.dubai"
    pwd = "TestUser1!"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": pwd,
        "name": "Iter119 Tester",
    })
    if r.status_code not in (200, 201):
        # some deployments use /signup or similar; fall back to demo login
        r2 = s.post(f"{API}/auth/login", json={
            "email": email, "password": pwd})
        if r2.status_code != 200:
            pytest.skip(f"register failed {r.status_code} {r.text[:120]} "
                        f"and login fallback also failed")
    else:
        # ensure session cookie
        s.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    return s, email


@pytest.fixture
def fresh_session():
    s, email = _register_fresh_user()
    yield s
    # nothing to clean; TEST_ prefix marks it


@pytest.fixture
def demo_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"})
    if r.status_code != 200:
        pytest.skip(f"demo login failed {r.status_code}")
    return s


# ------------------ FPK sponsored games UNLIMITED ------------------

class TestFPKUnlimited:
    def test_fpk_games_seeded(self, mongo):
        """All 7 FPK sponsored games exist and are active."""
        for gid in FPK_IDS:
            c = mongo.game_campaigns.find_one({"campaign_id": gid})
            assert c, f"missing FPK campaign {gid}"
            assert c.get("status") == "active"
            assert bool(c.get("is_platform_funded")) is False, \
                f"{gid} should NOT be platform funded"
            assert c.get("funded_source") == "fpk_sponsored"

    def test_fpk_prize_tiers_weights(self, mongo):
        """FPK spin has 5 tiers with weights 50/25/13/8/4 and correct caps."""
        prizes = list(mongo.game_prizes.find(
            {"campaign_id": "cmp_fpk_spin", "active": True}))
        assert len(prizes) == 5
        by_pct = {int(p["value_amount"]): p for p in prizes}
        assert sorted(by_pct.keys()) == [10, 20, 30, 40, 50]
        expected_weights = {10: 50, 20: 25, 30: 13, 40: 8, 50: 4}
        expected_caps = {10: 200, 20: 100, 30: 40, 40: 15, 50: 5}
        for pct, w in expected_weights.items():
            assert int(by_pct[pct]["probability_weight"]) == w
            assert int(by_pct[pct]["daily_quantity_cap"]) == expected_caps[pct]
            assert by_pct[pct]["value_currency"] == "percent"
            assert "% off" in by_pct[pct]["title"]

    def test_fpk_multi_play_unlimited(self, fresh_session):
        """4 plays with distinct idempotency keys on cmp_fpk_spin all 200."""
        results = []
        for _ in range(4):
            key = "k_" + secrets.token_hex(8)
            r = fresh_session.post(f"{API}/play/resolve", json={
                "gameId": "cmp_fpk_spin", "idempotencyKey": key})
            assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
            body = r.json()
            assert "playId" in body
            results.append(body)
        # At least most plays should have won a coupon (weights sum 100 & inventory huge).
        wins = [x for x in results if x.get("won")]
        assert len(wins) >= 3, f"expected mostly wins, got {len(wins)}/4"
        # A winning play must include a coupon with an FPK-style code
        for w in wins:
            assert w.get("coupon") and w["coupon"].get("code"), \
                f"winner missing coupon: {w}"
            assert "% off" in (w.get("prizeTitle") or "")
            assert w["prizeTitle"].startswith("FPK ")

    def test_fpk_daily_issued_incremented(self, mongo, fresh_session):
        """After a fresh play on cmp_fpk_scratch daily_issued>0 on the picked
        tier and daily_issued_date == today's UTC date."""
        # play once (fresh user has no plays today)
        key = "k_" + secrets.token_hex(8)
        r = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_fpk_scratch", "idempotencyKey": key})
        assert r.status_code == 200
        body = r.json()
        assert body.get("won"), "expected a win given weights+huge inventory"
        prize_id = body["prizeId"]
        today = dt.datetime.utcnow().strftime("%Y-%m-%d")
        p = mongo.game_prizes.find_one({"prize_id": prize_id})
        assert p, "prize row not found"
        assert p.get("daily_issued_date") == today
        assert int(p.get("daily_issued") or 0) >= 1


# ------------------ FREE (house) games 1/day per TYPE ------------------

class TestHouseDailyLimit:
    def test_first_play_ok_second_429(self, fresh_session):
        """Fresh user: first cmp_house_spin play OK; second same-type same-day
        should 429 daily_type_limit_reached."""
        k1 = "k_" + secrets.token_hex(8)
        r1 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_spin", "idempotencyKey": k1})
        assert r1.status_code == 200, f"first play failed: {r1.status_code} {r1.text[:200]}"
        b1 = r1.json()
        assert "playId" in b1

        k2 = "k_" + secrets.token_hex(8)
        r2 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_spin", "idempotencyKey": k2})
        assert r2.status_code == 429, f"expected 429, got {r2.status_code}: {r2.text[:200]}"
        body = r2.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        # FastAPI wraps HTTPException(429, {..}) into {"detail": {...}}
        payload = detail if isinstance(detail, dict) else body
        assert payload.get("code") == "daily_type_limit_reached", \
            f"unexpected 429 body: {body}"

    def test_idempotent_replay_returns_original(self, fresh_session):
        """Same idempotencyKey replay returns the original play, no 429."""
        key = "k_" + secrets.token_hex(8)
        r1 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_scratch", "idempotencyKey": key})
        assert r1.status_code == 200
        b1 = r1.json()
        original_play_id = b1["playId"]

        # replay same key → same play row, still 200
        r2 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_scratch", "idempotencyKey": key})
        assert r2.status_code == 200, f"idempotent replay failed: {r2.status_code} {r2.text[:200]}"
        b2 = r2.json()
        assert b2["playId"] == original_play_id
        assert b2.get("won") == b1.get("won")
        assert b2.get("prizeId") == b1.get("prizeId")

    def test_sponsored_after_free_not_blocked(self, fresh_session):
        """After playing free house_spin once, a sponsored cmp_fpk_spin still
        plays 200 (sponsored is unlimited and NOT affected by the free gate)."""
        # play house first
        k1 = "k_" + secrets.token_hex(8)
        r1 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_spin", "idempotencyKey": k1})
        assert r1.status_code == 200
        # then sponsored FPK spin (same game_type=spin_wheel) should still work
        k2 = "k_" + secrets.token_hex(8)
        r2 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_fpk_spin", "idempotencyKey": k2})
        assert r2.status_code == 200, f"sponsored blocked: {r2.status_code} {r2.text[:200]}"


# ------------------ GET /api/games_v2/play_and_win eligibility ------------------

class TestPlayAndWinEligibility:
    def test_sponsored_flag_shape(self, fresh_session):
        r = fresh_session.get(f"{API}/games_v2/play_and_win")
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        data = r.json()
        assert "unlocked_for_you" in data
        campaigns = data["unlocked_for_you"]
        assert len(campaigns) > 0, "unlocked_for_you empty"
        fpk = [c for c in campaigns if c["campaign_id"] in FPK_IDS]
        assert len(fpk) == 7, f"expected 7 FPK games, got {len(fpk)}"
        for c in fpk:
            elig = c.get("play_eligibility")
            assert elig, f"no play_eligibility on {c['campaign_id']}"
            assert elig.get("sponsored") is True
            assert elig.get("unlimited") is True
            assert elig.get("can_play") is True

    def test_house_can_play_when_fresh(self, fresh_session):
        r = fresh_session.get(f"{API}/games_v2/play_and_win")
        assert r.status_code == 200
        campaigns = r.json()["unlocked_for_you"]
        house = [c for c in campaigns
                 if c.get("is_platform_funded") is True]
        assert len(house) > 0, "no house games listed"
        for c in house:
            elig = c.get("play_eligibility") or {}
            # fresh user: can_play True on every house type
            assert elig.get("can_play") is True, \
                f"fresh user blocked from {c['campaign_id']}: {elig}"
            assert elig.get("sponsored") is False

    def test_house_can_play_false_after_play(self, fresh_session):
        """After a play via /api/play/resolve, the play_and_win eligibility
        for the SAME game_type must flip to can_play:false, reason:played_today.
        This validates parity between the play engine (db.plays) and the
        eligibility check."""
        # 1) confirm can_play True beforehand
        r0 = fresh_session.get(f"{API}/games_v2/play_and_win")
        camps0 = {c["campaign_id"]: c for c in r0.json()["unlocked_for_you"]}
        spin = camps0.get("cmp_house_spin")
        assert spin, "cmp_house_spin missing"
        assert (spin.get("play_eligibility") or {}).get("can_play") is True

        # 2) play the free house spin
        r1 = fresh_session.post(f"{API}/play/resolve", json={
            "gameId": "cmp_house_spin",
            "idempotencyKey": "k_" + secrets.token_hex(8)})
        assert r1.status_code == 200

        # 3) re-check eligibility
        r2 = fresh_session.get(f"{API}/games_v2/play_and_win")
        camps = {c["campaign_id"]: c for c in r2.json()["unlocked_for_you"]}
        spin_after = camps.get("cmp_house_spin")
        elig = (spin_after or {}).get("play_eligibility") or {}
        assert elig.get("can_play") is False, \
            f"after play, expected can_play:false, got {elig}"
        assert elig.get("reason") == "played_today", \
            f"expected reason:played_today, got {elig}"
        assert isinstance(elig.get("resets_in_sec"), int)
