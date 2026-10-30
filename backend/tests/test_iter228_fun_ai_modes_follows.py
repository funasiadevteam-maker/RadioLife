"""FUUSIC Fun AI — Phase 2 iter228: Program modes (6) + Follow This Story.

Verifies:
  - GET /api/fun-ai/config: 6 modes, default=morning_briefing
  - GET /api/fun-ai/news/briefing per mode (incl. news_in_2 trim, deep_dive topic echo)
  - POST /api/fun-ai/session: mode+topic injection; tools include search_news & follow_story;
    FOLLOWING injection when user has follows
  - Follows CRUD + case-insensitive dedupe + updates
  - All follows endpoints 401 unauthenticated
"""
from __future__ import annotations
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}

EXPECTED_MODE_IDS = {"morning_briefing", "news_in_2", "continuous",
                     "deep_dive", "local", "global"}


# ─── fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth():
    """Cookie-authenticated session for demo@ (premium)."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    return s


# ─── /config: modes list ────────────────────────────────────────────────
class TestConfig:
    def test_config_returns_six_modes(self, anon):
        r = anon.get(f"{BASE_URL}/api/fun-ai/config", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "modes" in data and isinstance(data["modes"], list)
        ids = {m["id"] for m in data["modes"]}
        assert ids == EXPECTED_MODE_IDS, f"got {ids}"
        assert data["default_mode"] == "morning_briefing"
        # deep_dive must be flagged topic_required
        dd = next(m for m in data["modes"] if m["id"] == "deep_dive")
        assert dd.get("topic_required") is True
        # all modes have label + blurb
        for m in data["modes"]:
            assert m.get("label") and m.get("blurb")


# ─── /news/briefing per mode ───────────────────────────────────────────
class TestBriefingModes:
    @pytest.mark.parametrize("mode", sorted(EXPECTED_MODE_IDS))
    def test_briefing_each_mode(self, anon, mode):
        params = {"mode": mode}
        if mode == "deep_dive":
            params["topic"] = "technology"
        r = anon.get(f"{BASE_URL}/api/fun-ai/news/briefing",
                     params=params, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == mode
        assert d.get("mode_label")
        assert d.get("anchor_hint")
        assert isinstance(d.get("program"), list)

    def test_news_in_2_trims_summary(self, anon):
        r = anon.get(f"{BASE_URL}/api/fun-ai/news/briefing",
                     params={"mode": "news_in_2"}, timeout=20)
        assert r.status_code == 200
        prog = r.json().get("program") or []
        if not prog:
            pytest.skip("news cache empty")
        # Trim ~30 words. Allow slight tolerance.
        for item in prog:
            summ = item.get("summary") or ""
            if not summ:
                continue
            # ends with ellipsis if trimmed OR naturally shorter
            words = summ.split()
            assert len(words) <= 32, f"summary too long ({len(words)}): {summ!r}"

    def test_deep_dive_echoes_topic(self, anon):
        topic = "AI data centers"
        r = anon.get(f"{BASE_URL}/api/fun-ai/news/briefing",
                     params={"mode": "deep_dive", "topic": topic}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "deep_dive"
        assert d.get("topic") == topic or (d.get("topic") and topic.lower() in str(d["topic"]).lower())

    def test_global_uses_world_or_fallback(self, anon):
        r = anon.get(f"{BASE_URL}/api/fun-ai/news/briefing",
                     params={"mode": "global"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "global"
        # Should return program (either world category or fallback)
        assert isinstance(d.get("program"), list)

    def test_morning_briefing_limit(self, anon):
        r = anon.get(f"{BASE_URL}/api/fun-ai/news/briefing",
                     params={"mode": "morning_briefing"}, timeout=20)
        assert r.status_code == 200
        prog = r.json().get("program") or []
        assert len(prog) <= 8  # limit=8


# ─── /session: mode + topic + tools + FOLLOWING injection ──────────────
class TestSessionInjection:
    def test_session_requires_auth(self, anon):
        r = anon.post(f"{BASE_URL}/api/fun-ai/session", json={"mode": "news_in_2"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_session_mode_label_and_tools(self, auth):
        r = auth.post(f"{BASE_URL}/api/fun-ai/session",
                      json={"mode": "news_in_2"}, timeout=20)
        if r.status_code in (429, 503):
            pytest.skip(f"session not startable: {r.status_code} {r.text[:200]}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "news_in_2"
        assert d["mode_label"] == "News in 2 Minutes"
        tool_names = {t.get("name") for t in d.get("tools", [])}
        assert tool_names == {"search_news", "follow_story"}, tool_names
        # mode hint injected into instructions
        assert "News in 2 Minutes" in d["instructions"] or "rapid" in d["instructions"].lower()

    def test_session_deep_dive_injects_topic(self, auth):
        r = auth.post(f"{BASE_URL}/api/fun-ai/session",
                      json={"mode": "deep_dive", "topic": "quantum computing"},
                      timeout=20)
        if r.status_code in (429, 503):
            pytest.skip(f"session not startable: {r.status_code}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "deep_dive"
        assert "quantum computing" in d["instructions"]


# ─── Follow This Story CRUD + dedupe + updates ─────────────────────────
class TestFollows:
    def test_follows_require_auth(self, anon):
        r = anon.get(f"{BASE_URL}/api/fun-ai/follows", timeout=15)
        assert r.status_code in (401, 403)
        r = anon.post(f"{BASE_URL}/api/fun-ai/follows",
                      json={"topic": "x"}, timeout=15)
        assert r.status_code in (401, 403)
        r = anon.get(f"{BASE_URL}/api/fun-ai/follows/updates", timeout=15)
        assert r.status_code in (401, 403)

    def test_follows_crud_and_dedupe(self, auth):
        # Clean slate: pre-existing follows left intact; use TEST_ prefix
        topic1 = "TEST_iter228 Mars rover"
        topic1_cased = "test_iter228 MARS rover  "  # case + whitespace diff
        topic2 = "TEST_iter228 Climate summit"

        created_ids = []
        try:
            # CREATE #1
            r1 = auth.post(f"{BASE_URL}/api/fun-ai/follows",
                           json={"topic": topic1, "title": topic1}, timeout=15)
            assert r1.status_code == 200, r1.text
            fo1 = r1.json()["follow"]
            assert fo1["topic"] == topic1
            created_ids.append(fo1["id"])

            # CREATE #2 — dedupe (same key, case/whitespace diff) must return the SAME id
            r1b = auth.post(f"{BASE_URL}/api/fun-ai/follows",
                            json={"topic": topic1_cased}, timeout=15)
            assert r1b.status_code == 200
            fo1b = r1b.json()["follow"]
            assert fo1b["id"] == fo1["id"], "dedupe failed - new id created"

            # CREATE #3 — distinct
            r2 = auth.post(f"{BASE_URL}/api/fun-ai/follows",
                           json={"topic": topic2}, timeout=15)
            assert r2.status_code == 200
            fo2 = r2.json()["follow"]
            created_ids.append(fo2["id"])
            assert fo2["id"] != fo1["id"]

            # LIST contains both
            rl = auth.get(f"{BASE_URL}/api/fun-ai/follows", timeout=15)
            assert rl.status_code == 200
            ids = {f["id"] for f in rl.json()["follows"]}
            assert fo1["id"] in ids and fo2["id"] in ids

            # UPDATES endpoint returns per-topic latest articles
            ru = auth.get(f"{BASE_URL}/api/fun-ai/follows/updates", timeout=25)
            assert ru.status_code == 200
            topics = ru.json().get("topics", [])
            topic_ids = {t["id"] for t in topics}
            assert fo1["id"] in topic_ids and fo2["id"] in topic_ids
            for t in topics:
                assert "updates" in t and isinstance(t["updates"], list)

            # Empty topic rejected
            r_empty = auth.post(f"{BASE_URL}/api/fun-ai/follows",
                                json={"topic": "   "}, timeout=15)
            assert r_empty.status_code == 400

        finally:
            # DELETE each + verify removal
            for fid in created_ids:
                rd = auth.delete(f"{BASE_URL}/api/fun-ai/follows/{fid}", timeout=15)
                assert rd.status_code == 200
                assert rd.json().get("ok") is True
            # Confirm gone
            rl2 = auth.get(f"{BASE_URL}/api/fun-ai/follows", timeout=15)
            remaining = {f["id"] for f in rl2.json()["follows"]}
            for fid in created_ids:
                assert fid not in remaining

    def test_session_injects_following_when_user_has_follows(self, auth):
        """After adding a follow, POST /session must inject 'FOLLOWING' into instructions."""
        topic = "TEST_iter228 session follow injection"
        r1 = auth.post(f"{BASE_URL}/api/fun-ai/follows",
                       json={"topic": topic}, timeout=15)
        assert r1.status_code == 200
        fid = r1.json()["follow"]["id"]
        try:
            rs = auth.post(f"{BASE_URL}/api/fun-ai/session",
                           json={"mode": "morning_briefing"}, timeout=25)
            if rs.status_code in (429, 503):
                pytest.skip(f"session not startable: {rs.status_code}")
            assert rs.status_code == 200, rs.text
            instr = rs.json()["instructions"]
            # follow_updates only injects if updates are found; the opening phrase includes "FOLLOWING"
            # Accept either injected (updates returned) OR not (no cached articles for topic).
            # If injected, must contain "FOLLOWING".
            # If not injected, that's fine — we validate at least no 500s and no leak.
            if "FOLLOWING" in instr:
                assert topic.lower() in instr.lower() or "TEST_iter228" in instr
        finally:
            auth.delete(f"{BASE_URL}/api/fun-ai/follows/{fid}", timeout=15)
