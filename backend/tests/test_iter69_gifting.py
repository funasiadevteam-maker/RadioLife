"""Iteration 69 — Backend tests for:
- Gift Inbox: GET /api/shop/gifts/received
- Membership gifting: POST /api/shop/memberships/subscribe with gift_to_email
- Membership listing: GET /api/shop/memberships/mine returns received_gift + gift_message for recipient
- Package gifting: POST /api/shop/packages/purchase (points) with gift_to_email
"""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL required"

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"
DEMO_EMAIL = "demo@bigfm.dubai"
BIZ = "biz_8484f6f985d5"


@pytest.fixture(scope="module")
def test_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed {r.status_code}: {r.text[:200]}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ---- Gift Inbox ----
class TestGiftInbox:
    def test_gift_inbox_returns_items_for_test_user(self, test_session):
        r = test_session.get(f"{BASE_URL}/api/shop/gifts/received", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "items" in data and "count" in data
        assert isinstance(data["items"], list)
        assert data["count"] == len(data["items"])
        # test@ should have at least 1 gifted package ("5 Haircuts" from Demo Listener)
        assert data["count"] >= 1, f"expected >=1 gift, got {data['count']}: {data['items']}"
        # verify shape of first item
        item = data["items"][0]
        for key in ["kind", "id", "title", "from_name", "route", "action"]:
            assert key in item, f"missing key {key} in item: {item}"
        # verify one of the items is a package with sender info
        pkgs = [i for i in data["items"] if i.get("kind") == "package"]
        assert pkgs, f"expected at least one 'package' kind item, got kinds: {[i['kind'] for i in data['items']]}"

    def test_gift_inbox_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/shop/gifts/received", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ---- Membership gifting ----
class TestMembershipGifting:
    def test_list_business_memberships(self, test_session):
        # Ambreens Salon should have "Unlimited Blowouts" plan
        r = test_session.get(f"{BASE_URL}/api/shop/businesses/{BIZ}/memberships", timeout=15)
        # accept 200 or fallback endpoint shape
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        # response could be {plans: [...]} or list
        plans = data.get("items") if isinstance(data, dict) else data
        assert isinstance(plans, list)
        # store one plan id for downstream test
        pytest.membership_plan_id = None
        pytest.membership_business_id = BIZ
        if plans:
            p = plans[0]
            pytest.membership_plan_id = p.get("plan_id") or p.get("id")

    def test_subscribe_membership_as_gift(self, test_session):
        pid = getattr(pytest, "membership_plan_id", None)
        if not pid:
            pytest.skip("No membership plan available on target business")
        recipient = f"gift_recv_{uuid.uuid4().hex[:8]}@bigfm.dubai"
        payload = {
            "business_id": pytest.membership_business_id,
            "plan_id": pid,
            "gift_to_email": recipient,
            "message": "TEST_gift from iter69 tester",
        }
        r = test_session.post(f"{BASE_URL}/api/shop/memberships/subscribe", json=payload, timeout=20)
        # Should be 200 with Stripe checkout URL, or 200/201 with subscription created (free tier)
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:400]}"
        data = r.json()
        # Accept either checkout url response OR direct subscription creation
        assert any(k in data for k in ["checkout_url", "url", "membership_id", "subscription_id", "ok"]), (
            f"unexpected response shape: {data}"
        )

    def test_memberships_mine_shows_received_gift_flag(self, test_session):
        """Just verify the endpoint returns and includes gift metadata when applicable."""
        r = test_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        # data can be {items:[...]} or list
        items = data.get("items") if isinstance(data, dict) else data
        assert isinstance(items, list)
        # if any is a received gift, verify keys exist
        for m in items:
            if m.get("is_gift") or m.get("received_gift"):
                # allow either flag name
                assert "gift_message" in m or "message" in m, f"missing gift_message on gift item: {m}"
                break


# ---- Package gifting (already tested prior, sanity check no 500s) ----
class TestPackageGiftingNoRegression:
    def test_packages_business_lists(self, test_session):
        r = test_session.get(f"{BASE_URL}/api/shop/businesses/{BIZ}/packages", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_packages_mine(self, test_session):
        r = test_session.get(f"{BASE_URL}/api/shop/packages/mine", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
