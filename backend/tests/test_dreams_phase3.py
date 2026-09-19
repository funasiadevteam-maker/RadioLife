"""Dreams & Guidance — Phase 3 backend tests (ads, clusters, compatibility, daily, reminders)."""
import os
import time
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def demo():
    return login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def free():
    return login("freeuser@bigfm.dubai", "FreePass123!")


@pytest.fixture(scope="module")
def admin():
    return login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def advisor():
    return login("stella.moon@bigfm.dubai", "Advisor123!")


# ─── ADS ─────────────────────────────────────────────────────────
class TestAds:
    def test_config_advisor_sees_tiers_and_is_advisor(self, advisor):
        r = advisor.get(f"{BASE}/api/social/ads/config", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["is_advisor"] is True
        keys = sorted(t["key"] for t in j["tiers"])
        prices = sorted(t["price_cents"] for t in j["tiers"])
        assert keys == ["day", "month", "week"]
        assert prices == [2999, 4999, 9999]
        assert "active_promotion" in j

    def test_config_demo_not_advisor(self, demo):
        r = demo.get(f"{BASE}/api/social/ads/config", timeout=30)
        assert r.status_code == 200
        assert r.json()["is_advisor"] is False

    def test_checkout_non_advisor_403(self, demo):
        r = demo.post(f"{BASE}/api/social/ads/checkout",
                      json={"tier": "day", "surface": "advisors",
                            "origin_url": BASE}, timeout=30)
        assert r.status_code == 403
        assert r.json().get("detail", {}).get("code") == "not_an_advisor"

    def test_checkout_advisor_returns_stripe_url(self, advisor):
        r = advisor.post(f"{BASE}/api/social/ads/checkout",
                         json={"tier": "day", "surface": "advisors",
                               "origin_url": BASE}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending_payment"
        assert j["checkout_url"].startswith("https://checkout.stripe.com/")
        assert j["promo_id"].startswith("promo_")
        # Status endpoint
        s = advisor.get(f"{BASE}/api/social/ads/status/{j['promo_id']}", timeout=30)
        assert s.status_code == 200
        assert s.json()["promo_id"] == j["promo_id"]

    def test_mine_advisor(self, advisor):
        r = advisor.get(f"{BASE}/api/social/ads/mine", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_admin_config_get_and_patch(self, admin):
        r = admin.get(f"{BASE}/api/admin/dreams/ads/config", timeout=30)
        assert r.status_code == 200
        orig = r.json()["tiers"]
        # Patch (roll back)
        patch = [{"key": t["key"], "days": t["days"],
                  "price_cents": t["price_cents"] + 100, "label": t["label"]}
                 for t in orig]
        p = admin.patch(f"{BASE}/api/admin/dreams/ads/config",
                        json={"tiers": patch}, timeout=30)
        assert p.status_code == 200
        assert p.json()["tiers"][0]["price_cents"] == orig[0]["price_cents"] + 100
        # Roll back
        rb = admin.patch(f"{BASE}/api/admin/dreams/ads/config",
                         json={"tiers": orig}, timeout=30)
        assert rb.status_code == 200

    def test_admin_promotions_list(self, admin):
        r = admin.get(f"{BASE}/api/admin/dreams/ads/promotions", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)


# ─── CLUSTERS ────────────────────────────────────────────────────
class TestClusters:
    def test_clusters_list(self, demo):
        r = demo.get(f"{BASE}/api/social/clusters", timeout=30)
        assert r.status_code == 200
        clusters = r.json()["clusters"]
        assert isinstance(clusters, list)
        # backfill should produce at least a few clusters
        assert len(clusters) >= 1
        first = clusters[0]
        assert "theme" in first and "label" in first and "count" in first
        assert isinstance(first.get("samples"), list)

    def test_cluster_detail_known_theme(self, demo):
        r = demo.get(f"{BASE}/api/social/clusters/water", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["theme"] == "water"
        assert j["label"] == "Water & Ocean"
        assert isinstance(j["items"], list)

    def test_cluster_unknown_theme_404(self, demo):
        r = demo.get(f"{BASE}/api/social/clusters/not_a_theme", timeout=30)
        assert r.status_code == 404

    def test_shared_dream_becomes_clustered(self, demo):
        body = {"title": "TEST flying dream phase3",
                "description": "I was flying high above the ocean and mountains. "
                               "Water below, sky above, birds beside me.",
                "visibility": "public", "anonymous": False,
                "mood": "Peaceful", "tags": ["Flying", "Water"]}
        c = demo.post(f"{BASE}/api/social/dreams", json=body, timeout=30)
        assert c.status_code == 200, c.text
        did = c.json()["dream_id"]
        # Give background theme extraction a chance (LLM ~5-15s or keyword fallback instant)
        found = False
        for _ in range(8):
            time.sleep(2)
            r = demo.get(f"{BASE}/api/social/dreams/{did}", timeout=30)
            if r.status_code == 200:
                # Themes are stored on the doc; check clusters detail for the dream
                for t in ("flying", "water", "nature"):
                    cr = demo.get(f"{BASE}/api/social/clusters/{t}", timeout=30)
                    if cr.status_code == 200 and any(
                            it["dream_id"] == did for it in cr.json()["items"]):
                        found = True
                        break
            if found:
                break
        assert found, "New public dream did not appear in any cluster within timeout"
        # cleanup
        demo.delete(f"{BASE}/api/social/dreams/{did}", timeout=30)


# ─── COMPATIBILITY ───────────────────────────────────────────────
class TestCompat:
    def test_candidates(self, demo):
        r = demo.get(f"{BASE}/api/social/compatibility/candidates", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_self_match_400(self, demo):
        me = demo.get(f"{BASE}/api/auth/me", timeout=30).json()
        uid = me.get("user_id") or me.get("id")
        assert uid
        r = demo.post(f"{BASE}/api/social/compatibility",
                      json={"target_user_id": uid}, timeout=30)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "cannot_match_self"

    def test_unknown_user_404(self, demo):
        r = demo.post(f"{BASE}/api/social/compatibility",
                      json={"target_user_id": "user_does_not_exist_xxx"}, timeout=30)
        assert r.status_code == 404

    def test_compat_with_friend_if_available(self, demo):
        cand = demo.get(f"{BASE}/api/social/compatibility/candidates",
                        timeout=30).json().get("items") or []
        if not cand:
            pytest.skip("No friend candidates for demo user")
        target = cand[0]["user_id"]
        r = demo.post(f"{BASE}/api/social/compatibility",
                      json={"target_user_id": target}, timeout=45)
        assert r.status_code == 200, r.text
        j = r.json()
        assert 0 <= j["score"] <= 99
        assert j["label"] == "PLAYFUL · entertainment only"
        assert "entertainment" in j["disclaimer"].lower()
        assert isinstance(j["shared_themes"], list)
        assert "headline" in j and "blurb" in j


# ─── DAILY + REMINDERS ───────────────────────────────────────────
class TestDailyReminders:
    def test_daily_premium_unlocked(self, demo):
        r = demo.get(f"{BASE}/api/social/readings/daily", timeout=45)
        assert r.status_code == 200
        j = r.json()
        assert j.get("premium") is True
        assert j.get("detail_locked") is False
        assert j.get("detail") is not None
        assert "card" in j and "name" in j["card"]
        assert j.get("basic", {}).get("summary")

    def test_daily_free_locked(self, free):
        r = free.get(f"{BASE}/api/social/readings/daily", timeout=45)
        assert r.status_code == 200
        j = r.json()
        assert j.get("premium") is False
        assert j.get("detail_locked") is True
        assert "upgrade" in j
        assert j.get("detail") in (None, {})

    def test_daily_stable_per_day(self, demo):
        a = demo.get(f"{BASE}/api/social/readings/daily", timeout=45).json()
        b = demo.get(f"{BASE}/api/social/readings/daily", timeout=45).json()
        assert a["card"]["name"] == b["card"]["name"]
        assert a["date"] == b["date"]

    def test_reminders_get_and_put(self, demo):
        g = demo.get(f"{BASE}/api/social/readings/reminders", timeout=30)
        assert g.status_code == 200
        p = demo.put(f"{BASE}/api/social/readings/reminders",
                     json={"enabled": True, "hour": 8}, timeout=30)
        assert p.status_code == 200
        assert p.json()["enabled"] is True
        assert p.json()["hour"] == 8
        # verify persisted
        g2 = demo.get(f"{BASE}/api/social/readings/reminders", timeout=30).json()
        assert g2["enabled"] is True and g2["hour"] == 8
        # rollback disable
        demo.put(f"{BASE}/api/social/readings/reminders",
                 json={"enabled": False, "hour": 9}, timeout=30)


# ─── FEATURED SORT ROUTES ────────────────────────────────────────
class TestFeaturedSort:
    def test_advisors_list_carries_featured_flag(self, demo):
        r = demo.get(f"{BASE}/api/social/dreams/advisors", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert isinstance(items, list) and len(items) > 0
        # every item should now include a featured field (bool)
        for it in items:
            assert "featured" in it
            assert isinstance(it["featured"], bool)

    def test_live_sessions_returns_ok(self, demo):
        r = demo.get(f"{BASE}/api/social/live/sessions", timeout=30)
        # both surfaces call this — accept 200 with list
        assert r.status_code == 200
        assert isinstance(r.json().get("items", []), list)
