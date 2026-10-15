"""Phase: Expiring Soon — /api/social/deals-expiring (cookie auth)."""
import os
import requests
from datetime import datetime, timezone

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://mobile-games-v2.preview.emergentagent.com"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    return s


def test_deals_expiring_demo_user_has_karak_offer():
    s = _login("demo@bigfm.dubai", "DemoPass123!")
    r = s.get(f"{BASE}/api/social/deals-expiring", timeout=20)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "items" in data
    items = data["items"]
    assert len(items) >= 1, f"expected >=1 expiring deal for demo, got {items}"
    # Should contain Karak demo offer
    karak = [i for i in items if i.get("business_id") == "biz_demo_karak"]
    assert karak, f"no karak offer found: {items}"
    o = karak[0]
    assert o.get("offer_id") == "ofr_qa_onetime_demo", f"unexpected offer_id: {o}"
    assert "Karak" in (o.get("business_name") or ""), o
    assert o.get("label"), f"missing label: {o}"
    assert o.get("expires_at"), f"missing expires_at: {o}"
    # expires_at must be future ISO
    exp = datetime.fromisoformat(o["expires_at"].replace("Z", "+00:00"))
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    assert exp > datetime.now(timezone.utc)
    # soonest first ordering
    def _p(x):
        d = datetime.fromisoformat(x["expires_at"].replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    exps = [_p(i) for i in items]
    assert exps == sorted(exps)


def test_deals_expiring_within_hours_clamp_and_filter():
    s = _login("demo@bigfm.dubai", "DemoPass123!")
    # 1h — Karak is ~6h out, so should return []
    r = s.get(f"{BASE}/api/social/deals-expiring?within_hours=1", timeout=20)
    assert r.status_code == 200
    assert r.json().get("items") == [], r.json()
    # 24h — should include Karak
    r2 = s.get(f"{BASE}/api/social/deals-expiring?within_hours=24", timeout=20)
    assert any(i.get("business_id") == "biz_demo_karak" for i in r2.json()["items"])
    # Out-of-range clamped (999 -> 168h)
    r3 = s.get(f"{BASE}/api/social/deals-expiring?within_hours=999", timeout=20)
    assert r3.status_code == 200


def test_deals_expiring_follows_nothing_returns_empty():
    # Admin typically does not follow any business.
    s = _login("admin@bigfm.dubai", "AdminPass123!")
    r = s.get(f"{BASE}/api/social/deals-expiring", timeout=20)
    assert r.status_code == 200
    # admin follows nothing in demo graph → []
    assert r.json().get("items") == []


def test_deals_expiring_requires_auth():
    r = requests.get(f"{BASE}/api/social/deals-expiring", timeout=20)
    assert r.status_code in (401, 403), r.status_code


def test_friends_nearby_still_returns_karak_for_demo():
    s = _login("demo@bigfm.dubai", "DemoPass123!")
    r = s.get(f"{BASE}/api/social/friends-nearby", timeout=20)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items, "friends-nearby should return at least one entry"
    assert any(i.get("business_id") == "biz_demo_karak" for i in items)
    # offer must carry expires_at for the countdown
    one = next(i for i in items if i.get("business_id") == "biz_demo_karak")
    assert one.get("offer"), one
    assert one["offer"].get("expires_at"), one["offer"]
