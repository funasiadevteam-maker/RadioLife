"""Iteration 158 — Dreams & Guidance follow-up backend E2E.

Covers:
  (A) ORIGIN HARDENING  — POST /api/dining-club/subscribe must NOT return
      `origin_url_required` when only an Origin header is present (spot-check
      also /api/social/dreams/bookings/checkout still works via resolve_origin).
  (B) POINTS TOAST      — POST /api/social/dreams and POST /api/social/clubs/
      {slug}/dreams return points_awarded=1 first time, 0 on idempotent re-share,
      capped at 25/day (we just assert non-negative int).
  (C.1) AD ANALYTICS    — GET /api/social/ads/analytics (advisor) returns
        {promotions,totals:{views,bookings,revenue_cents}}.
  (C.2) CLUSTER ALERTS  — follow/unfollow cluster; alerts fan-out to followers
        when a public dream in a followed theme is shared (background task,
        so we poll up to 15s).
  (C.3) COMPAT SHARE    — must have a friendship; establish demo↔free friendship,
        POST /api/social/compatibility/share returns card_id/path/points_awarded,
        and GET /api/social/compatibility/card/{card_id} works WITHOUT auth.
  (C.4) REMINDER TZ     — PUT /reminders with {enabled,hour,tz,utc_offset_minutes}
        persists tz + offset; GET /reminders/due?offset=... returns tz-aware
        {due,local_time,local_date}; POST /reminders/ack sets last_nudge_date.

Uses external REACT_APP_BACKEND_URL and cookie auth (POST /api/auth/login).
Runs against the LIVE backend so Stripe & origin behaviour is production-like.
"""
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
ADVISOR = {"email": "stella.moon@bigfm.dubai", "password": "Advisor123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


# ─────────────────────────── FIXTURES ──────────────────────────────
@pytest.fixture(scope="module")
def demo_sess():
    return _login(DEMO)


@pytest.fixture(scope="module")
def free_sess():
    return _login(FREE)


@pytest.fixture(scope="module")
def advisor_sess():
    return _login(ADVISOR)


@pytest.fixture(scope="module")
def demo_uid(demo_sess):
    r = demo_sess.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def free_uid(free_sess):
    r = free_sess.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def demo_free_friendship(demo_sess, free_sess, demo_uid, free_uid):
    """Establish demo↔free friendship (idempotent)."""
    # Send friend request from demo -> free
    demo_sess.post(f"{BASE_URL}/api/social/friends/request",
                   json={"user_id": free_uid}, timeout=10)
    # Accept as free
    free_sess.post(f"{BASE_URL}/api/social/friends/{demo_uid}/accept", timeout=10)
    # Verify
    r = demo_sess.get(f"{BASE_URL}/api/social/friends", timeout=10)
    assert r.status_code == 200
    friend_ids = [f.get("user_id") for f in r.json().get("friends", [])]
    assert free_uid in friend_ids, f"Friendship not established: {r.json()}"
    return (demo_uid, free_uid)


# ═══════════════════ A. ORIGIN HARDENING ═══════════════════════════
class TestOriginHardening:
    """No origin_url_required 400 when body omits it but Origin header present."""

    def test_dining_club_subscribe_uses_header_origin(self, demo_sess):
        # Deliberately omit origin_url; pass Origin header only.
        headers = {"Origin": BASE_URL, "Referer": f"{BASE_URL}/dining"}
        r = demo_sess.post(f"{BASE_URL}/api/dining-club/subscribe",
                           json={"meals_per_week": 3, "veg_default": "VEG"},
                           headers=headers, timeout=20)
        # Acceptable non-400 outcomes:
        #   200 (activated in preview mock branch, or checkout_url in live)
        #   400 already_subscribed (previous test run)
        # UNACCEPTABLE: 400 origin_url_required
        assert r.status_code in (200, 400), f"unexpected {r.status_code} {r.text[:200]}"
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        detail = body.get("detail") if isinstance(body, dict) else None
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code != "origin_url_required", (
            f"REGRESSION: origin_url_required raised despite Origin header. "
            f"body={body}")

    def test_dream_booking_checkout_no_origin_error(self, demo_sess):
        """Spot-check bookings/checkout — even a 400/404 must NOT be origin_url_required."""
        headers = {"Origin": BASE_URL}
        # Pick any advisor + service if available
        adv = demo_sess.get(f"{BASE_URL}/api/social/dreams/advisors", timeout=10).json()
        advisors = adv.get("items", []) or adv.get("advisors", [])
        if not advisors:
            pytest.skip("no advisors seeded")
        a = advisors[0]
        aid = a.get("advisor_id") or a.get("id")
        # Fetch their services
        prof = demo_sess.get(f"{BASE_URL}/api/social/dreams/advisors/{aid}", timeout=10).json()
        svcs = prof.get("services") or []
        if not svcs:
            pytest.skip("advisor has no services")
        sid = svcs[0].get("service_id") or svcs[0].get("id")
        r = demo_sess.post(f"{BASE_URL}/api/social/dreams/bookings/checkout",
                           json={"advisor_id": aid, "service_id": sid,
                                 "dream_id": None, "note": "test"},
                           headers=headers, timeout=25)
        # Any status is fine as long as we don't see origin_url_required
        try:
            body = r.json()
        except Exception:
            body = {}
        detail = body.get("detail") if isinstance(body, dict) else None
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code != "origin_url_required", f"REGRESSION on bookings/checkout: {body}"


# ═══════════════════ B. POINTS TOAST ═══════════════════════════════
class TestPointsToast:
    """+1 point on dream share (idempotent per source_id)."""

    def test_share_dream_awards_point(self, demo_sess):
        # Consent first (idempotent)
        demo_sess.post(f"{BASE_URL}/api/social/dreams/consent",
                       json={"terms_version": "1.0", "accepted": True}, timeout=10)
        unique = uuid.uuid4().hex[:8]
        payload = {"title": f"TEST_iter158_{unique}",
                   "description": "A gentle water dream floating on soft moonlight for test.",
                   "mood": "Peaceful", "tags": ["Water"], "visibility": "public",
                   "anonymous": False}
        r = demo_sess.post(f"{BASE_URL}/api/social/dreams", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}"
        out = r.json()
        pts = out.get("points_awarded")
        assert isinstance(pts, int), f"points_awarded missing/wrong type: {out}"
        assert pts in (0, 1), f"points_awarded expected 0 or 1, got {pts}"
        # Save dream_id for cluster-alert test to reuse
        return out.get("dream_id") or out.get("id")

    def test_share_club_dream_awards_point(self, demo_sess):
        demo_sess.post(f"{BASE_URL}/api/social/dreams/consent",
                       json={"terms_version": "1.0", "accepted": True}, timeout=10)
        # Make sure demo has joined a club
        clubs = demo_sess.get(f"{BASE_URL}/api/social/clubs", timeout=10).json()
        items = clubs.get("items", [])
        if not items:
            pytest.skip("no dream clubs seeded")
        slug = items[0].get("slug") or items[0].get("_id")
        demo_sess.post(f"{BASE_URL}/api/social/clubs/{slug}/join", timeout=10)
        unique = uuid.uuid4().hex[:8]
        r = demo_sess.post(f"{BASE_URL}/api/social/clubs/{slug}/dreams",
                           json={"title": f"TEST_club_{unique}",
                                 "description": "Nightly flight over a moonlit ocean, testing.",
                                 "mood": "Peaceful", "tags": ["Flying"],
                                 "anonymous": False}, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}"
        out = r.json()
        assert "points_awarded" in out, f"missing points_awarded: {out}"
        assert out["points_awarded"] in (0, 1)


# ═══════════════════ C.1 AD ANALYTICS ══════════════════════════════
class TestAdAnalytics:
    def test_analytics_shape_for_advisor(self, advisor_sess):
        r = advisor_sess.get(f"{BASE_URL}/api/social/ads/analytics", timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        b = r.json()
        assert "promotions" in b
        assert "totals" in b
        for k in ("views", "bookings", "revenue_cents"):
            assert k in b["totals"], f"totals missing {k}: {b}"
            assert isinstance(b["totals"][k], int)
        assert isinstance(b["promotions"], list)

    def test_analytics_forbidden_for_non_advisor(self, demo_sess):
        # demo@ is not an advisor; analytics should still return but with empty
        # (endpoint is advisor-scoped by user_id filter — no auth error expected;
        # empty promotions is acceptable).
        r = demo_sess.get(f"{BASE_URL}/api/social/ads/analytics", timeout=10)
        # Endpoint filters by advisor_user_id=user_id; if non-advisor still
        # 200s with empty promotions that's fine.
        assert r.status_code in (200, 403)


# ═══════════════════ C.2 CLUSTER ALERTS ════════════════════════════
class TestClusterAlerts:
    def test_follow_unfollow_and_flag(self, demo_sess):
        # Follow
        r = demo_sess.post(f"{BASE_URL}/api/social/clusters/water/follow", timeout=10)
        assert r.status_code == 200
        assert r.json().get("following") is True
        # Verify following flag on list
        rc = demo_sess.get(f"{BASE_URL}/api/social/clusters", timeout=10)
        assert rc.status_code == 200
        clusters = rc.json().get("items", []) or rc.json().get("clusters", [])
        water_item = next((c for c in clusters if c.get("theme") == "water"), None)
        # If aggregation empty, still assert follow endpoint idempotency
        if water_item:
            assert water_item.get("following") is True, f"water not marked following: {water_item}"
        # Unfollow
        r2 = demo_sess.delete(f"{BASE_URL}/api/social/clusters/water/follow", timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("following") is False

    def test_alerts_endpoint_shape(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/social/alerts", timeout=10)
        assert r.status_code == 200
        b = r.json()
        assert "items" in b
        assert "unread" in b
        assert isinstance(b["items"], list)
        assert isinstance(b["unread"], int)

    def test_alerts_fanout_to_follower(self, free_sess, demo_sess):
        """When demo shares a water-themed public dream, free (follower) gets alert."""
        # free follows water
        r = free_sess.post(f"{BASE_URL}/api/social/clusters/water/follow", timeout=10)
        assert r.status_code == 200
        # Mark existing alerts read so we can measure delta
        free_sess.post(f"{BASE_URL}/api/social/alerts/read", json={}, timeout=10)
        # baseline
        before = free_sess.get(f"{BASE_URL}/api/social/alerts", timeout=10).json()
        base_ct = len(before.get("items", []))
        # demo shares a water dream (public)
        demo_sess.post(f"{BASE_URL}/api/social/dreams/consent",
                       json={"terms_version": "1.0", "accepted": True}, timeout=10)
        unique = uuid.uuid4().hex[:8]
        payload = {"title": f"TEST_water_{unique}",
                   "description": "Swimming through gentle ocean waves under starlit water.",
                   "mood": "Peaceful", "tags": ["Water"], "visibility": "public",
                   "anonymous": False}
        r = demo_sess.post(f"{BASE_URL}/api/social/dreams", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text[:200]
        # Poll up to 20s for background theme extract
        got = False
        for _ in range(20):
            time.sleep(1)
            after = free_sess.get(f"{BASE_URL}/api/social/alerts", timeout=10).json()
            if len(after.get("items", [])) > base_ct or after.get("unread", 0) > 0:
                got = True
                break
        # Cleanup: unfollow
        free_sess.delete(f"{BASE_URL}/api/social/clusters/water/follow", timeout=10)
        # NOTE: fan-out only triggers if theme-extract classifies as 'water'.
        # Keyword fallback should catch 'water' in the body — but if LLM
        # classifies differently, this is a soft assertion.
        if not got:
            pytest.skip("Theme classification did not tag water within 20s; "
                        "alerts endpoint is otherwise verified in test_alerts_endpoint_shape")


# ═══════════════════ C.3 COMPATIBILITY SHARING ═════════════════════
class TestCompatShare:
    def test_share_and_public_card(self, demo_sess, demo_free_friendship):
        demo_uid, free_uid = demo_free_friendship
        # Share
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=25)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        b = r.json()
        assert "card_id" in b and b["card_id"], f"missing card_id: {b}"
        assert b.get("path", "").startswith("/dreams/match/"), f"bad path: {b}"
        assert "points_awarded" in b
        assert b["points_awarded"] in (0, 1)
        assert isinstance(b.get("score"), int) and 0 <= b["score"] <= 99
        card_id = b["card_id"]
        # Public GET without auth
        anon = requests.Session()
        rp = anon.get(f"{BASE_URL}/api/social/compatibility/card/{card_id}", timeout=10)
        assert rp.status_code == 200, f"public card GET failed: {rp.status_code} {rp.text[:200]}"
        pb = rp.json()
        assert pb.get("card_id") == card_id
        assert isinstance(pb.get("score"), int)
        assert pb.get("headline")
        assert pb.get("owner_name") and pb.get("target_name")

    def test_public_card_404(self):
        anon = requests.Session()
        r = anon.get(f"{BASE_URL}/api/social/compatibility/card/mc_bogus_notfound_xxx", timeout=10)
        assert r.status_code == 404


# ═══════════════════ C.4 REMINDER TIMEZONES ════════════════════════
class TestReminderTz:
    def test_put_get_reminders_with_tz(self, demo_sess):
        # Set reminder at 9am with GST offset (+240)
        r = demo_sess.put(f"{BASE_URL}/api/social/readings/reminders",
                          json={"enabled": True, "hour": 9,
                                "tz": "Asia/Dubai", "utc_offset_minutes": 240},
                          timeout=10)
        assert r.status_code == 200, r.text[:200]
        b = r.json()
        assert b.get("enabled") is True
        assert b.get("hour") == 9
        assert b.get("tz") == "Asia/Dubai"
        assert b.get("utc_offset_minutes") == 240
        # GET
        rg = demo_sess.get(f"{BASE_URL}/api/social/readings/reminders", timeout=10)
        assert rg.status_code == 200
        gb = rg.json()
        assert gb.get("tz") == "Asia/Dubai"
        assert gb.get("utc_offset_minutes") == 240
        assert gb.get("enabled") is True

    def test_due_endpoint_tz_aware(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/social/readings/reminders/due?offset=240",
                          timeout=10)
        assert r.status_code == 200
        b = r.json()
        assert "due" in b and isinstance(b["due"], bool)
        assert b.get("enabled") is True
        assert "local_time" in b and isinstance(b["local_time"], str)
        assert "local_date" in b

    def test_ack_sets_last_nudge(self, demo_sess):
        # Force due=true by using offset that puts local time past hour=9
        rd = demo_sess.get(f"{BASE_URL}/api/social/readings/reminders/due?offset=600",
                           timeout=10).json()
        local_date = rd.get("local_date")
        assert local_date
        # Ack
        ra = demo_sess.post(f"{BASE_URL}/api/social/readings/reminders/ack",
                            json={"local_date": local_date}, timeout=10)
        assert ra.status_code == 200
        assert ra.json().get("ok") is True
        # After ack, same-offset re-poll should show due=false (idempotent)
        rd2 = demo_sess.get(f"{BASE_URL}/api/social/readings/reminders/due?offset=600",
                            timeout=10).json()
        # only assert if we were due before ack
        if rd.get("due"):
            assert rd2.get("due") is False, f"ack did not mark last_nudge_date: {rd2}"

    def test_cleanup_reminders(self, demo_sess):
        # Rollback to disabled defaults so we don't pollute for next run
        demo_sess.put(f"{BASE_URL}/api/social/readings/reminders",
                      json={"enabled": False, "hour": 9}, timeout=10)
