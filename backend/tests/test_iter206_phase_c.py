"""iter_206 Phase C — friends-nearby + full-points capture receipt."""
import os, requests, pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return s

@pytest.fixture(scope="module")
def demo(): return _login("demo@bigfm.dubai", "DemoPass123!")

@pytest.fixture(scope="module")
def free(): return _login("freeuser@bigfm.dubai", "FreePass123!")

@pytest.fixture(scope="module")
def merch(): return _login("test@bigfm.dubai", "TestUser123!")


def test_friends_nearby_demo_returns_items(demo):
    r = demo.get(f"{BASE}/api/social/friends-nearby", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert len(body["items"]) >= 1, f"expected >=1 nearby item for demo, got {body}"
    it = body["items"][0]
    for k in ("user_id","name","avatar_url","business_id","business_name",
              "business_logo","business_slug","activity","when"):
        assert k in it, f"missing {k} in {it}"
    assert it["activity"] in ("checked in", "paid")


def test_friends_nearby_empty_for_free(free):
    r = free.get(f"{BASE}/api/social/friends-nearby", timeout=20)
    assert r.status_code == 200
    assert r.json() == {"items": []} or r.json().get("items") == []


def test_full_points_scan_to_pay_capture(demo):
    biz = "biz_demo_karak"
    # 1) QR generate (demo is seeded as owner of biz_demo_karak)
    r = demo.post(f"{BASE}/api/merchant/scan-to-pay/qr/generate",
                   json={"merchant_id": biz, "amount_cents": 500}, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    # 2) Resolve as consumer (demo)
    r = demo.get(f"{BASE}/api/scan-to-pay/qr/{token}", timeout=20)
    assert r.status_code == 200, r.text
    resolved = r.json()
    bal = int(resolved["user_points_balance"])
    assert bal >= 500, f"demo needs >=500 BigPoints, has {bal}"
    assert resolved["settings"]["max_points_redemption_pct"] == 100

    # 3) Quote: use full subtotal in points, no tip
    r = demo.post(f"{BASE}/api/scan-to-pay/quote",
                  json={"qr_token": token, "points_to_use": 500, "tip_cents": 0}, timeout=20)
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["card_cents"] == 0 and q["points_value_cents"] == 500
    assert q["total_cents"] == 500

    # 4) Authorize (no payment_method needed since card_cents=0)
    r = demo.post(f"{BASE}/api/scan-to-pay/authorize",
                  json={"qr_token": token, "points_to_use": 500, "tip_cents": 0}, timeout=20)
    assert r.status_code == 200, r.text
    auth = r.json()
    assert auth["status"] == "authorized"
    assert auth["card_cents"] == 0
    tx_id = auth["transaction_id"]

    # 5) Capture
    r = demo.post(f"{BASE}/api/scan-to-pay/capture",
                  json={"transaction_id": tx_id}, timeout=20)
    assert r.status_code == 200, r.text
    cap = r.json()
    assert cap["status"] == "captured"
    for k in ("subtotal_cents","tip_cents","points_used","charge_cents","bigcoin_earned"):
        assert k in cap, f"capture missing {k}: {cap}"
    assert cap["charge_cents"] == 0
    assert cap["points_used"] == 500
    assert cap["subtotal_cents"] == 500
    assert cap["bigcoin_earned"] == 0  # points-only → no earn
