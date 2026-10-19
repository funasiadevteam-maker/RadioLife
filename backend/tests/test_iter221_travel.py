"""Backend tests for Travel vertical (iter221).

Covers:
- GET /api/travel/deals + filters/search/sort
- GET /api/travel/deals/{id}
- GET/POST/DELETE /api/travel/follow
- POST /api/travel/deals/{id}/book + GET /api/travel/orders
- Admin CRUD + non-admin 403 + bad deal_type 400
- Feed parity: /api/social/feed-v2?mode=following shows TRAVEL_DEAL cards only while following
"""
from __future__ import annotations

import os
import time
import pytest
import requests

def _base_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # fall back to reading /app/frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not set"
    return url.rstrip("/")


BASE_URL = _base_url()

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}


def _login(session: requests.Session, creds: dict) -> bool:
    r = session.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    return r.status_code == 200


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    if not _login(s, DEMO):
        pytest.skip("demo login failed")
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    if not _login(s, ADMIN):
        pytest.skip("admin login failed")
    return s


# --- deals list / detail --------------------------------------------------

class TestTravelDeals:
    def test_list_deals_default(self):
        r = requests.get(f"{BASE_URL}/api/travel/deals", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data.get("items"), list)
        assert len(data["items"]) >= 10, f"expected >=10 seeded deals, got {len(data['items'])}"
        assert data.get("types") == ["flight", "hotel", "package", "experience", "cruise"]
        d = data["items"][0]
        for key in ("deal_id", "title", "deal_type", "price_cents", "bigpoints"):
            assert key in d, f"missing {key}"

    def test_list_deals_filter_type(self):
        for t in ["flight", "hotel", "package", "experience", "cruise"]:
            r = requests.get(f"{BASE_URL}/api/travel/deals", params={"type": t}, timeout=20)
            assert r.status_code == 200
            items = r.json()["items"]
            assert items, f"no deals for type={t}"
            assert all(x["deal_type"] == t for x in items)

    def test_list_deals_search(self):
        r = requests.get(f"{BASE_URL}/api/travel/deals", params={"q": "Dubai"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_list_deals_sort_price_low(self):
        r = requests.get(f"{BASE_URL}/api/travel/deals", params={"sort": "price_low"}, timeout=20)
        assert r.status_code == 200
        prices = [x["price_cents"] for x in r.json()["items"]]
        assert prices == sorted(prices)

    def test_deal_detail(self):
        items = requests.get(f"{BASE_URL}/api/travel/deals", timeout=20).json()["items"]
        did = items[0]["deal_id"]
        r = requests.get(f"{BASE_URL}/api/travel/deals/{did}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        deal = body.get("deal") or body
        assert deal["deal_id"] == did

    def test_deal_detail_404(self):
        r = requests.get(f"{BASE_URL}/api/travel/deals/nope_xxx", timeout=20)
        assert r.status_code == 404


# --- follow + feed integration -------------------------------------------

class TestTravelFollowFeed:
    def test_follow_toggle_and_feed(self, demo_session):
        # start clean
        demo_session.delete(f"{BASE_URL}/api/travel/follow", timeout=20)
        s = demo_session.get(f"{BASE_URL}/api/travel/follow", timeout=20)
        assert s.status_code == 200
        assert s.json().get("following") is False

        # feed should NOT include travel cards
        f0 = demo_session.get(f"{BASE_URL}/api/social/feed-v2", params={"mode": "following"}, timeout=20)
        assert f0.status_code == 200
        items0 = f0.json().get("items", [])
        travel0 = [x for x in items0 if x.get("type") == "TRAVEL_DEAL"]
        assert travel0 == [], f"expected no travel cards pre-follow, found {len(travel0)}"

        # follow
        p = demo_session.post(f"{BASE_URL}/api/travel/follow", timeout=20)
        assert p.status_code == 200
        assert p.json().get("following") is True

        time.sleep(1)
        f1 = demo_session.get(f"{BASE_URL}/api/social/feed-v2", params={"mode": "following"}, timeout=20)
        assert f1.status_code == 200
        items1 = f1.json().get("items", [])
        travel1 = [x for x in items1 if x.get("type") == "TRAVEL_DEAL"]
        assert travel1, "expected TRAVEL_DEAL cards after follow"
        card = travel1[0]
        actor = (card.get("actor") or {}).get("name") or card.get("actor_name")
        assert actor and "Travel" in actor, f"actor unexpected: {actor}"
        cta = card.get("cta") or {}
        assert cta.get("action") == "open_travel", f"cta action unexpected: {cta}"

        # unfollow
        d = demo_session.delete(f"{BASE_URL}/api/travel/follow", timeout=20)
        assert d.status_code == 200
        assert d.json().get("following") is False

        time.sleep(1)
        f2 = demo_session.get(f"{BASE_URL}/api/social/feed-v2", params={"mode": "following"}, timeout=20)
        travel2 = [x for x in f2.json().get("items", []) if x.get("type") == "TRAVEL_DEAL"]
        assert travel2 == [], f"expected no travel cards after unfollow, got {len(travel2)}"


# --- book + orders -------------------------------------------------------

class TestTravelBooking:
    def test_book_and_order(self, demo_session):
        items = requests.get(f"{BASE_URL}/api/travel/deals", timeout=20).json()["items"]
        did = items[0]["deal_id"]
        r = demo_session.post(f"{BASE_URL}/api/travel/deals/{did}/book", json={"travelers": 2}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status") in ("confirmed", "ok", "success") or body.get("confirmed") is True
        assert body.get("order_id") or body.get("id")

        o = demo_session.get(f"{BASE_URL}/api/travel/orders", timeout=20)
        assert o.status_code == 200
        orders = o.json().get("items") or o.json().get("orders") or []
        assert any((x.get("deal_id") == did) for x in orders), "newly booked deal missing from orders"


# --- admin CRUD ----------------------------------------------------------

class TestTravelAdmin:
    def test_non_admin_forbidden(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/travel/admin/deals", timeout=20)
        assert r.status_code == 403

    def test_admin_crud(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/travel/admin/deals", timeout=20)
        assert r.status_code == 200

        payload = {
            "title": "TEST_Phuket Escape",
            "deal_type": "package",
            "destination": "Phuket",
            "origin": "Dubai",
            "price_cents": 129900,
            "bigpoints": 500,
            "blurb": "Test deal",
            "active": True,
        }
        c = admin_session.post(f"{BASE_URL}/api/travel/admin/deals", json=payload, timeout=20)
        assert c.status_code in (200, 201), c.text
        created = c.json().get("deal") or c.json()
        did = created.get("deal_id") or created.get("id")
        assert did

        # bad type
        bad = admin_session.post(
            f"{BASE_URL}/api/travel/admin/deals",
            json={**payload, "deal_type": "spaceship"},
            timeout=20,
        )
        assert bad.status_code == 400

        # update — PUT requires full DealBody
        u = admin_session.put(
            f"{BASE_URL}/api/travel/admin/deals/{did}",
            json={**payload, "title": "TEST_Phuket Escape v2"},
            timeout=20,
        )
        assert u.status_code == 200
        updated = u.json().get("deal") or u.json()
        assert updated.get("title") == "TEST_Phuket Escape v2"
        # appears in consumer list
        lst = requests.get(f"{BASE_URL}/api/travel/deals", params={"q": "TEST_Phuket"}, timeout=20).json()
        assert any(x["deal_id"] == did for x in lst["items"])

        # delete
        d = admin_session.delete(f"{BASE_URL}/api/travel/admin/deals/{did}", timeout=20)
        assert d.status_code in (200, 204)
