"""Iteration 217 — Game SFX/Haptics (P1) + Winners Ticker (P2) + Streak Rewards (P3).

Backend coverage:
- GET /api/games/streak (shape + behaviour)
- GET /api/games/recent-wins (min items + ordering + sample padding)
- Streak server-authoritative, once-per-UTC-day via wheel/scratch/dice
- Winners ticker: real wins show up at the top with sample=false
- Regression: wheel segment_index, scratch tiles+win, dice die1/die2 still returned
"""
import os
import pytest
import requests
from datetime import datetime, timezone

def _resolve_base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE_URL = _resolve_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

# Shared user accounts
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}


def _login(session: requests.Session, creds: dict) -> bool:
    r = session.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    return r.status_code == 200


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if not _login(s, DEMO):
        pytest.skip("demo login failed")
    return s


@pytest.fixture(scope="module")
def free_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if not _login(s, FREE):
        pytest.skip("free login failed")
    return s


# ──────────────────────────── /api/games/streak ─────────────────────────────
class TestStreakEndpoint:
    def test_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/games/streak", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("current_streak", "longest_streak", "played_today",
                  "claim_available", "pending_bonus_points",
                  "pending_bonus_spin", "cap_day"):
            assert k in d, f"missing {k}: {d}"
        assert d["cap_day"] == 7
        assert isinstance(d["current_streak"], int)
        assert isinstance(d["longest_streak"], int)
        assert isinstance(d["played_today"], bool)
        assert isinstance(d["pending_bonus_points"], int)

    def test_claim_available_mirrors_played_today(self, demo_session):
        d = demo_session.get(f"{BASE_URL}/api/games/streak").json()
        # If already played today, pending_bonus_points should be 0.
        if d["played_today"]:
            assert d["claim_available"] is False
            assert d["pending_bonus_points"] == 0
        else:
            assert d["claim_available"] is True
            assert d["pending_bonus_points"] > 0

    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/games/streak", timeout=10)
        assert r.status_code in (401, 403)


# ────────────────────────── /api/games/recent-wins ──────────────────────────
class TestRecentWinsTicker:
    def test_min_items_and_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/games/recent-wins?limit=20",
                             timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        assert len(items) >= 8, f"expected >= 8 ticker items, got {len(items)}"
        for it in items:
            for k in ("display_name", "game", "game_label", "prize_label",
                      "prize_points", "created_at", "sample"):
                assert k in it, f"missing {k} in ticker item: {it}"
            assert isinstance(it["sample"], bool)
            assert isinstance(it["prize_points"], int)

    def test_real_wins_before_samples(self, demo_session):
        items = (demo_session
                 .get(f"{BASE_URL}/api/games/recent-wins?limit=20")
                 .json()
                 .get("items") or [])
        seen_sample = False
        for it in items:
            if it["sample"]:
                seen_sample = True
            else:
                # once samples start they shouldn't be followed by real wins
                assert not seen_sample, "real win appears after a sample"

    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/games/recent-wins", timeout=10)
        assert r.status_code in (401, 403)


# ─── Streak is once-per-day on real plays + real wins hit the ticker ────────
class TestStreakAndTickerOnPlay:
    """We prefer the free user because demo has usually already played today
    in dev; if free has also played, the second-play idempotency assertion
    still holds (bonus.awarded=false)."""

    def _attempt_play(self, session):
        """Return (streak_block, response_json, status) for the first game
        the user can still play today. None if everything is out."""
        # Try wheel
        r = session.post(f"{BASE_URL}/api/games/wheel/spin",
                         json={"game_id": "spin_house"}, timeout=20)
        if r.status_code == 200:
            return "wheel", r.json(), 200
        # Try scratch
        r = session.post(f"{BASE_URL}/api/games/scratch/play",
                         json={"game_id": "scratch_house"}, timeout=20)
        if r.status_code == 200:
            return "scratch", r.json(), 200
        # Try dice
        r = session.post(f"{BASE_URL}/api/dining-club/dice/roll",
                         json={}, timeout=20)
        if r.status_code == 200:
            return "dice", r.json(), 200
        return None, None, r.status_code

    def test_streak_block_on_play_and_once_per_day(self, free_session):
        game, resp, status = self._attempt_play(free_session)
        if game is None:
            pytest.skip(f"free user has no plays left today (last status={status})")
        # streak block must be present with the right shape
        streak = resp.get("streak")
        assert streak and isinstance(streak, dict), f"missing streak: {resp}"
        assert "bonus" in streak
        bonus = streak["bonus"]
        for k in ("awarded", "points", "bonus_spin", "streak_day"):
            assert k in bonus, f"missing bonus.{k}: {bonus}"
        # If this was first play today, points should equal min(day,7)*10
        if bonus["awarded"]:
            expected = min(int(bonus["streak_day"]), 7) * 10
            assert bonus["points"] == expected, bonus
            assert bonus["points"] > 0
        # Second play (same or different game) must NOT re-credit
        _, resp2, _ = self._attempt_play(free_session)
        if resp2 and resp2.get("streak"):
            assert resp2["streak"]["bonus"]["awarded"] is False, \
                f"second play re-credited the streak bonus: {resp2['streak']}"

    def test_streak_endpoint_reflects_played_today(self, free_session):
        # After the play attempt above, streak endpoint must report played_today
        d = free_session.get(f"{BASE_URL}/api/games/streak").json()
        # Either we played in the previous test, or we were out of plays and
        # played_today could still be true from an earlier run — both OK, but
        # if played_today is true, pending bonus must be 0.
        if d["played_today"]:
            assert d["pending_bonus_points"] == 0
            assert d["claim_available"] is False

    def test_real_win_recorded_to_ticker(self, demo_session, free_session):
        """If any session hit a real win in this run, that win must be in
        the ticker as a non-sample item ordered to the top."""
        # Attempt a few plays across sessions (idempotent for streak via day
        # key but each real win is still recorded in game_wins).
        hit_prize = None
        for sess in (demo_session, free_session):
            for _ in range(3):
                r = sess.post(f"{BASE_URL}/api/games/wheel/spin",
                              json={"game_id": "spin_house"}, timeout=15)
                if r.status_code != 200:
                    break
                prize = r.json().get("prize") or {}
                kind = prize.get("kind")
                pts = int(prize.get("points") or 0)
                if kind == "coupon" or (kind == "points" and pts > 0):
                    hit_prize = prize
                    break
            if hit_prize:
                break
        if not hit_prize:
            pytest.skip("no real win landed within the limited spins")

        items = (demo_session.get(
            f"{BASE_URL}/api/games/recent-wins?limit=20")
            .json().get("items") or [])
        real = [i for i in items if not i["sample"]]
        assert real, "expected at least one real (sample=False) win in ticker"
        # the newest real win should be at the top of the real section
        assert items[0]["sample"] is False, \
            "a real win should sort above sample padding"


# ─────────── Regression: existing server-authoritative fields intact ────────
class TestExistingGameOutcomesUnregressed:
    def test_wheel_returns_segment_index(self, free_session):
        r = free_session.post(f"{BASE_URL}/api/games/wheel/spin",
                              json={"game_id": "spin_house"}, timeout=15)
        if r.status_code == 429:
            pytest.skip("free user out of wheel spins")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "segment_index" in d and isinstance(d["segment_index"], int)
        assert "prize" in d and isinstance(d["prize"], dict)
        assert "spins_left" in d

    def test_scratch_returns_tiles_and_win(self, free_session):
        r = free_session.post(f"{BASE_URL}/api/games/scratch/play",
                              json={"game_id": "scratch_house"}, timeout=15)
        if r.status_code == 429:
            pytest.skip("free user out of scratch cards")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "tiles" in d and isinstance(d["tiles"], list) and len(d["tiles"]) == 3
        assert "win" in d and isinstance(d["win"], bool)
        assert "prize" in d

    def test_dice_returns_die1_die2(self, free_session):
        r = free_session.post(f"{BASE_URL}/api/dining-club/dice/roll",
                              json={}, timeout=15)
        if r.status_code == 429:
            pytest.skip("free user out of dice rolls")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "die1" in d and "die2" in d
        assert isinstance(d["die1"], int) and isinstance(d["die2"], int)
        assert 1 <= d["die1"] <= 6 and 1 <= d["die2"] <= 6
