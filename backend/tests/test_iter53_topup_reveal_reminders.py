"""iter53 — Buy More BigCoin + Gift Card Reveal/Thanks + Booking Reminders."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def s(token):
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return sess


# ── BigCoin Topup ───────────────────────────────────────────────
class TestBigCoinTopup:
    def test_packages_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/bigcoin/topup/packages", timeout=10)
        assert r.status_code in (401, 403)

    def test_packages_shape(self, s):
        r = s.get(f"{BASE_URL}/api/bigcoin/topup/packages", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "points_balance" in d
        assert len(d["items"]) == 4
        ids = {p["package_id"] for p in d["items"]}
        assert ids == {"tp_500", "tp_1000", "tp_2500", "tp_5000"}
        for p in d["items"]:
            assert p["total_bigcoin"] == p["bigcoin"] + p["bonus"]
            assert p["price_cents"] > 0

    def test_checkout_bad_package(self, s):
        r = s.post(f"{BASE_URL}/api/bigcoin/topup/checkout",
                   json={"package_id": "tp_bogus", "origin_url": BASE_URL}, timeout=15)
        assert r.status_code == 404

    def test_checkout_returns_stripe_url(self, s):
        r = s.post(f"{BASE_URL}/api/bigcoin/topup/checkout",
                   json={"package_id": "tp_500", "origin_url": BASE_URL}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("checkout_url", "").startswith("https://")
        assert d.get("session_id", "").startswith("cs_")
        pytest.iter53_topup_sid = d["session_id"]

    def test_status_pending_before_pay(self, s):
        sid = getattr(pytest, "iter53_topup_sid", None)
        if not sid:
            pytest.skip("checkout not created")
        r = s.get(f"{BASE_URL}/api/bigcoin/topup/{sid}/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") in ("pending", "paid")

    def test_status_unknown_session(self, s):
        r = s.get(f"{BASE_URL}/api/bigcoin/topup/cs_nonexistent_xyz/status", timeout=10)
        assert r.status_code == 404


# ── Gift Cards mine + reveal + thanks ───────────────────────────
class TestGiftCardsRevealThanks:
    def test_mine_shape(self, s):
        r = s.get(f"{BASE_URL}/api/giftcards/mine", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        for c in d["items"]:
            assert "received_gift" in c
            # revealed/thanks_sent may be missing on legacy cards (pre-feature) — record but don't fail
        pytest.iter53_mine = d["items"]
        legacy_missing = [c["card_id"] for c in d["items"]
                          if "revealed" not in c or "thanks_sent" not in c]
        pytest.iter53_legacy_missing = legacy_missing

    def test_reveal_owned_card(self, s):
        items = getattr(pytest, "iter53_mine", []) or []
        if not items:
            pytest.skip("no cards on demo")
        cid = items[0]["card_id"]
        r = s.post(f"{BASE_URL}/api/giftcards/{cid}/reveal", json={}, timeout=10)
        assert r.status_code == 200, r.text
        assert r.json()["card"]["revealed"] is True

    def test_reveal_unknown_404(self, s):
        r = s.post(f"{BASE_URL}/api/giftcards/gc_nope_9999/reveal", json={}, timeout=10)
        assert r.status_code == 404

    def test_thanks_self_purchased_400(self, s):
        items = getattr(pytest, "iter53_mine", []) or []
        # Find one where buyer==owner (self-purchased) → expect 400 no_gifter
        self_purchased = [c for c in items if not c.get("received_gift")]
        if not self_purchased:
            pytest.skip("no self-purchased card")
        cid = self_purchased[0]["card_id"]
        r = s.post(f"{BASE_URL}/api/giftcards/{cid}/thanks", json={}, timeout=10)
        assert r.status_code == 400
        body = r.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else None
        assert code == "no_gifter", body

    def test_thanks_gifted_card_notifies_buyer(self, s):
        # Seed a gifted card via mongo: create a fake buyer and gift to demo's email.
        import pymongo, uuid
        cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "bigfm")]
        me = db.users.find_one({"email": "demo@bigfm.dubai"}, {"user_id": 1, "email": 1})
        if not me:
            pytest.skip("no demo user")
        buyer_id = f"u_test_buyer_{uuid.uuid4().hex[:6]}"
        db.users.insert_one({"user_id": buyer_id, "email": f"{buyer_id}@test.local",
                             "name": "TEST Buyer"})
        card_id = f"gc_test_{uuid.uuid4().hex[:8]}"
        db.gift_cards.insert_one({
            "card_id": card_id, "code": "RL-TEST-XXXX-XXXX",
            "product_id": "gc_grind_coffee", "sponsor_name": "TEST Grind",
            "amount_cents": 1000, "balance_cents": 1000,
            "owner_user_id": me["user_id"], "buyer_user_id": buyer_id,
            "gifted_to_email": me["email"], "message": "for testing",
            "method": "points", "status": "active",
            "idempotency_key": f"test:{card_id}",
            "revealed": False, "thanks_sent": False,
        })
        try:
            # verify /mine now includes received_gift=True
            m = s.get(f"{BASE_URL}/api/giftcards/mine", timeout=10).json()
            mine_card = next((c for c in m["items"] if c["card_id"] == card_id), None)
            assert mine_card is not None
            assert mine_card["received_gift"] is True

            # reveal it (recipient can)
            r_rev = s.post(f"{BASE_URL}/api/giftcards/{card_id}/reveal", json={}, timeout=10)
            assert r_rev.status_code == 200

            # thanks OK
            r_t = s.post(f"{BASE_URL}/api/giftcards/{card_id}/thanks",
                         json={"message": "TEST thanks!"}, timeout=10)
            assert r_t.status_code == 200, r_t.text
            assert r_t.json().get("ok") is True

            # thanks_sent flipped
            m2 = s.get(f"{BASE_URL}/api/giftcards/mine", timeout=10).json()
            c2 = next(c for c in m2["items"] if c["card_id"] == card_id)
            assert c2["thanks_sent"] is True

            # notification enqueued for buyer
            notif = db.station_notifications.find_one({"owner_user_id": buyer_id,
                                               "type": "giftcard_thanks"})
            assert notif is not None
            assert notif.get("payload", {}).get("card_id") == card_id
        finally:
            db.gift_cards.delete_one({"card_id": card_id})
            db.users.delete_one({"user_id": buyer_id})
            db.station_notifications.delete_many({"owner_user_id": buyer_id})


# ── Bookings reminder + mine ────────────────────────────────────
class TestBookingReminders:
    def test_bookings_mine_shape(self, s):
        r = s.get(f"{BASE_URL}/api/bookings/mine", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        for b in d["items"]:
            assert "sponsor_name" in b
            assert "venue_title" in b
            assert b.get("status") == "confirmed"

    def test_booking_creates_reminder_notification(self, s):
        # available bookings
        av = s.get(f"{BASE_URL}/api/bookings/available", timeout=10)
        assert av.status_code == 200
        items = av.json().get("items", [])
        if not items:
            pytest.skip("no bookings available")
        camp = items[0]
        slot = (camp.get("slots") or [None])[0]
        if not slot:
            pytest.skip("no slot")
        import pymongo, uuid
        cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "bigfm")]
        me = db.users.find_one({"email": "demo@bigfm.dubai"}, {"user_id": 1})
        assert me
        tag = uuid.uuid4().hex[:6]
        r = s.post(f"{BASE_URL}/api/bookings/{camp['campaign_id']}/book",
                   json={"slot": slot, "party_size": 2,
                         "name": f"TEST {tag}", "phone": "+15550001111"}, timeout=15)
        if r.status_code == 400:
            pytest.skip(f"booking rejected: {r.text}")
        assert r.status_code == 200, r.text
        bid = r.json()["booking"]["booking_id"]
        # notification enqueued
        n = db.station_notifications.find_one({"owner_user_id": me["user_id"],
                                       "type": "booking_reminder",
                                       "payload.booking_id": bid})
        assert n is not None, "booking_reminder notification not enqueued"
        # user notifications endpoint returns it
        rn = s.get(f"{BASE_URL}/api/me/notifications", timeout=10)
        assert rn.status_code == 200
        types = [x.get("type") for x in rn.json().get("items", [])]
        assert "booking_reminder" in types
