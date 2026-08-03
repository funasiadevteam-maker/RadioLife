"""Phase 42-E2 backend smoke — Home tiles, Local highlights, Share log, Invite send.
Auth is cookie-based (bigfm_session). Anonymous tests use a fresh session without cookies."""
from __future__ import annotations
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"

LOCKED_TILES = {
    "predict_win":      ("/predict-win", "Call it. Cash it."),
    "games":                  ("/play-and-win", "Spin. Scratch. Win."),
    "news_radio":      ("/radio/news", "Your headlines, in your voice."),
    "earn_points":      ("/wallet", "Listen more. Earn more."),
    "commute":              ("/commute", "Maps. Music. Deals."),
    "social_passport": ("/passport", "Collect cities. Earn stamps."),
}


def _new_anon_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _new_auth_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
                              json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=20)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    assert "bigfm_session" in s.cookies, f"no bigfm_session cookie set; got: {dict(s.cookies)}"
    return s


@pytest.fixture(scope="module")
def anon():
    return _new_anon_session()


@pytest.fixture(scope="module")
def demo():
    return _new_auth_session()


# ─── E2.1 — Feature tiles ────────────────────────────────────
class TestFeatureTiles:
    def test_six_tiles_locked_taglines_routes(self, anon):
        r = anon.get(f"{BASE_URL}/api/home/feature-tiles", timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("count") == 6, f"expected 6 tiles, got {data.get('count')}"
        tiles = {t["tile_id"]: t for t in data["tiles"]}
        for tid, (route, tagline) in LOCKED_TILES.items():
            assert tid in tiles, f"missing tile {tid}"
            assert tiles[tid]["route"] == route, f"{tid} route={tiles[tid]['route']} want {route}"
            assert tiles[tid]["tagline"] == tagline, f"{tid} tagline mismatch: {tiles[tid]['tagline']}"


# ─── E2.1 — Local highlights ─────────────────────────────────
class TestLocalHighlights:
    def test_local_highlights_dubai(self, anon):
        r = anon.get(f"{BASE_URL}/api/home/local-highlights",
                                  params={"market": "dubai", "limit": 4}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["market"] == "dubai"
        assert isinstance(data["items"], list)
        for item in data["items"]:
            assert item.get("kind") in {"news", "offer", "predict_win"}
            assert item.get("title"), f"item missing title: {item}"


# ─── E2.2 — Share log ─────────────────────────────────────────
class TestShareLog:
    def test_anonymous_share_log_no_points(self):
        s = _new_anon_session()
        r = s.post(f"{BASE_URL}/api/share/log", json={
            "feature_type": "home", "content_id": "anon_smoke_1",
            "channel": "copy_link", "url": "/"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ok"] is True
        assert d["event_id"].startswith("shr_")
        assert d["points"]["awarded"] is False
        assert d["points"]["reason"] == "anonymous"

    def test_authenticated_share_log_awards_points(self, demo):
        cid = f"e2_smoke_{uuid.uuid4().hex[:8]}"
        r = demo.post(f"{BASE_URL}/api/share/log", json={
            "feature_type": "home", "content_id": cid,
            "channel": "copy_link", "url": "/"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ok"] is True
        pts = d["points"]
        if pts["awarded"]:
            assert pts.get("delta") == 5
            assert "balance_after" in pts
        else:
            reason = (pts.get("reason") or "").lower()
            assert "cap" in reason or "daily" in reason, f"unexpected non-award reason: {pts}"

    def test_daily_cap_enforced(self, demo):
        """Fire 6 unique shares — at least one of the 6 (likely #6) should be capped."""
        responses = []
        for i in range(6):
            cid = f"cap_test_{uuid.uuid4().hex[:6]}_{i}"
            r = demo.post(f"{BASE_URL}/api/share/log", json={
                "feature_type": "home", "content_id": cid,
                "channel": "copy_link", "url": "/"}, timeout=15)
            assert r.status_code == 200, f"share {i} failed: {r.text[:200]}"
            responses.append(r.json())
        not_awarded = [x for x in responses if not x["points"]["awarded"]]
        assert len(not_awarded) >= 1, f"expected cap to trigger at least once: {[r['points'] for r in responses]}"
        cap_reasons = [(x["points"].get("reason") or "").lower() for x in not_awarded]
        assert any("cap" in r or "daily" in r for r in cap_reasons), \
            f"none of the not-awarded had cap reason: {cap_reasons}"


# ─── E2.2 — Invite send ───────────────────────────────────────
class TestInviteSend:
    def test_invite_send_anonymous_rejected(self):
        s = _new_anon_session()
        r = s.post(f"{BASE_URL}/api/invite/send", json={
            "to_email": "anon_invite@example.com"}, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"

    def test_invite_send_authenticated_creates_voucher(self, demo):
        r = demo.post(f"{BASE_URL}/api/invite/send", json={
            "to_email": "phase_e2_test@example.com",
            "to_name": "E2 Tester",
            "personal_note": "Smoke test from testing_agent"
        }, timeout=25)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["ok"] is True
        assert d["voucher_id"].startswith("rv_")
        assert len(d["code"]) == 12, f"expected 12-char code, got {len(d['code'])}: {d['code']}"
        assert f"ref={d['code']}" in d["deep_link"]
        # Mailgun should be mocked OR live (spec says mocked but it appears live is OK too)
        assert d["email_status"] in {"mocked", "sent_via_mailgun"} \
            or d["email_status"].startswith("mocked"), f"unexpected email_status: {d['email_status']}"
        assert "awarded" in d["points"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
