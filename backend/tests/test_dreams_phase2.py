"""Dreams & Guidance Phase 2 — AI readings, clubs, payouts, live Q&A."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO = ("demo@bigfm.dubai", "DemoPass123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
ADVISOR = ("stella.moon@bigfm.dubai", "Advisor123!")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_sess():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def admin_sess():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def advisor_sess():
    return _login(*ADVISOR)


# ═════════════════════════ AI READINGS ═════════════════════════
class TestAIReadings:
    def test_config(self, demo_sess):
        r = demo_sess.get(f"{API}/social/readings/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert set(d["types"]) == {"horoscope", "tarot", "numerology"}
        assert "AI-GENERATED" in d["label"]
        assert "not medical" in d["disclaimer"].lower()

    def test_horoscope_by_dob(self, demo_sess):
        r = demo_sess.post(f"{API}/social/readings/horoscope",
                           json={"dob": "1990-07-15", "timeframe": "today"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "horoscope"
        assert d["subject"] == "Cancer"
        assert "AI-GENERATED" in d["label"]
        assert "not medical" in d["disclaimer"].lower()
        assert "headline" in d["result"]
        pytest.reading_id = d["reading_id"]

    def test_horoscope_bad_input(self, demo_sess):
        r = demo_sess.post(f"{API}/social/readings/horoscope", json={"timeframe": "today"}, timeout=15)
        assert r.status_code == 400

    def test_tarot_three(self, demo_sess):
        r = demo_sess.post(f"{API}/social/readings/tarot",
                           json={"question": "TEST what should I focus on?", "spread": "three"},
                           timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "tarot"
        assert len(d["cards"]) == 3
        for c in d["cards"]:
            assert c["orientation"] in ("upright", "reversed")
        assert "AI-GENERATED" in d["label"]

    def test_numerology(self, demo_sess):
        r = demo_sess.post(f"{API}/social/readings/numerology",
                           json={"full_name": "TEST Demo", "dob": "1990-07-15"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "numerology"
        assert "life_path" in d["result"]

    def test_history_and_get(self, demo_sess):
        r = demo_sess.get(f"{API}/social/readings", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 3
        rid = items[0]["reading_id"]
        r2 = demo_sess.get(f"{API}/social/readings/{rid}", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["reading_id"] == rid

    def test_share_and_delete(self, demo_sess):
        r = demo_sess.get(f"{API}/social/readings", timeout=15)
        rid = r.json()["items"][-1]["reading_id"]
        s = demo_sess.post(f"{API}/social/readings/{rid}/share", json={"public": True}, timeout=15)
        assert s.status_code == 200 and s.json()["public"] is True
        d = demo_sess.delete(f"{API}/social/readings/{rid}", timeout=15)
        assert d.status_code == 200
        # verify 404 after delete
        g = demo_sess.get(f"{API}/social/readings/{rid}", timeout=15)
        assert g.status_code == 404


# ═════════════════════════ DREAM CLUBS ═════════════════════════
class TestClubs:
    def test_list(self, demo_sess):
        r = demo_sess.get(f"{API}/social/clubs", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 6
        slugs = {c["slug"] for c in items}
        assert "lucid-dreamers" in slugs
        assert "nightmare-support" in slugs
        for c in items:
            assert "member_count" in c and "dream_count" in c and "is_member" in c

    def test_detail(self, demo_sess):
        r = demo_sess.get(f"{API}/social/clubs/lucid-dreamers", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["slug"] == "lucid-dreamers"
        assert "dreams" in d

    def test_join_leave_toggle(self, demo_sess):
        j = demo_sess.post(f"{API}/social/clubs/recurring-dreams/join", timeout=15)
        assert j.status_code == 200 and j.json()["is_member"] is True
        # verify in detail
        d = demo_sess.get(f"{API}/social/clubs/recurring-dreams", timeout=15)
        assert d.json()["is_member"] is True
        l = demo_sess.post(f"{API}/social/clubs/recurring-dreams/leave", timeout=15)
        assert l.status_code == 200 and l.json()["is_member"] is False

    def test_post_club_dream_auto_joins(self, demo_sess):
        r = demo_sess.post(f"{API}/social/clubs/prophetic-spiritual/dreams",
                           json={"description": "TEST I dreamed of a golden bridge over a river.",
                                 "anonymous": False, "tags": ["symbols"]},
                           timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("description", "").startswith("TEST")
        # verify auto-join
        detail = demo_sess.get(f"{API}/social/clubs/prophetic-spiritual", timeout=15).json()
        assert detail["is_member"] is True
        # verify dream appears in feed
        dream_ids = [x["dream_id"] for x in detail["dreams"]]
        assert d["dream_id"] in dream_ids

    def test_club_not_found(self, demo_sess):
        r = demo_sess.get(f"{API}/social/clubs/nope-not-real", timeout=15)
        assert r.status_code == 404


# ═════════════════════════ PAYOUTS ═════════════════════════
class TestPayouts:
    def test_status_forbidden_for_non_advisor(self, demo_sess):
        r = demo_sess.get(f"{API}/social/payouts/status", timeout=15)
        assert r.status_code == 403

    def test_status_advisor_ok(self, advisor_sess):
        r = advisor_sess.get(f"{API}/social/payouts/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("onboarding_status", "payouts_enabled", "charges_enabled",
                  "has_account", "commission_pct", "earnings", "ledger"):
            assert k in d
        assert d["commission_pct"] == 30  # default

    def test_onboarding_start(self, advisor_sess):
        r = advisor_sess.post(f"{API}/social/payouts/onboarding/start",
                              json={"country": "US",
                                    "origin_url": BASE_URL},
                              timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["onboarding_url"].startswith("https://")

    def test_status_refresh(self, advisor_sess):
        r = advisor_sess.post(f"{API}/social/payouts/status/refresh", timeout=30)
        # 200 if we have an account after onboarding_start; otherwise 400 no_account
        assert r.status_code in (200, 400)

    def test_admin_get_and_patch_commission(self, admin_sess):
        g = admin_sess.get(f"{API}/admin/dreams/payouts/config", timeout=15)
        assert g.status_code == 200
        original = g.json()["commission_pct"]
        p = admin_sess.patch(f"{API}/admin/dreams/payouts/config",
                             json={"commission_pct": 25}, timeout=15)
        assert p.status_code == 200 and p.json()["commission_pct"] == 25
        # restore
        admin_sess.patch(f"{API}/admin/dreams/payouts/config",
                        json={"commission_pct": original}, timeout=15)

    def test_admin_ledger(self, admin_sess):
        r = admin_sess.get(f"{API}/admin/dreams/payouts/ledger", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "commission_pct" in d

    def test_admin_non_admin_forbidden(self, demo_sess):
        r = demo_sess.get(f"{API}/admin/dreams/payouts/config", timeout=15)
        assert r.status_code in (401, 403)


# ═════════════════════════ LIVE Q&A ═════════════════════════
class TestLive:
    _created_sid = None

    def test_list_live(self, demo_sess):
        r = demo_sess.get(f"{API}/social/live/sessions?status=live", timeout=15)
        assert r.status_code == 200
        assert "items" in r.json() and "live_mode" in r.json()

    def test_list_upcoming(self, demo_sess):
        r = demo_sess.get(f"{API}/social/live/sessions?status=upcoming", timeout=15)
        assert r.status_code == 200

    def test_list_past(self, demo_sess):
        r = demo_sess.get(f"{API}/social/live/sessions?status=past", timeout=15)
        assert r.status_code == 200

    def test_create_forbidden_for_non_advisor(self, demo_sess):
        r = demo_sess.post(f"{API}/social/live/sessions",
                           json={"title": "TEST session", "mode": "audio"},
                           timeout=15)
        assert r.status_code == 403

    def test_advisor_create_and_host_flow(self, advisor_sess, demo_sess):
        # Advisor creates a live session
        c = advisor_sess.post(f"{API}/social/live/sessions",
                              json={"title": "TEST Live Dream Q&A", "mode": "audio",
                                    "description": "TEST session"},
                              timeout=15)
        assert c.status_code == 200, c.text
        sid = c.json()["session_id"]
        TestLive._created_sid = sid
        assert c.json()["status"] == "live"

        # Advisor sees the session with is_host=True + join_token (if live-mode allows) or None
        h = advisor_sess.get(f"{API}/social/live/sessions/{sid}", timeout=15)
        assert h.status_code == 200
        hd = h.json()
        assert hd["is_host"] is True
        assert "questions" in hd
        assert "live_mode" in hd

        # Demo (guest) sees is_host=False
        g = demo_sess.get(f"{API}/social/live/sessions/{sid}", timeout=15)
        assert g.status_code == 200
        assert g.json()["is_host"] is False

        # Demo asks a question
        q = demo_sess.post(f"{API}/social/live/sessions/{sid}/questions",
                           json={"text": "TEST what does a golden bridge mean?"},
                           timeout=15)
        assert q.status_code == 200, q.text
        qid = q.json()["id"]

        # Non-host demo cannot answer
        bad = demo_sess.post(f"{API}/social/live/questions/{qid}/answer", timeout=15)
        assert bad.status_code == 403

        # Advisor host answers
        ans = advisor_sess.post(f"{API}/social/live/questions/{qid}/answer", timeout=15)
        assert ans.status_code == 200

        # Verify answered flag is set
        det = advisor_sess.get(f"{API}/social/live/sessions/{sid}", timeout=15).json()
        found = [x for x in det["questions"] if x["id"] == qid]
        assert found and found[0]["answered"] is True

        # Guest cannot end
        bad_end = demo_sess.post(f"{API}/social/live/sessions/{sid}/end", timeout=15)
        assert bad_end.status_code == 403

        # Host ends
        e = advisor_sess.post(f"{API}/social/live/sessions/{sid}/end", timeout=15)
        assert e.status_code == 200

        # Session now shows in past
        past = demo_sess.get(f"{API}/social/live/sessions?status=past", timeout=15).json()
        past_ids = [x["session_id"] for x in past["items"]]
        assert sid in past_ids
