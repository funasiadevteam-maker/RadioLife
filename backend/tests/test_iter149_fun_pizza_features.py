"""Iter 149 — Fun Pizza Kitchen: Scratch & Win, Win Wall, Sponsor Bidding, Coupon Redeem."""
import os
import uuid
import pytest
import requests
from pathlib import Path

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE_URL = _load_url()

MERCHANT_ID = "biz_fun_pizza_kitchen"
SPIN_CID = "gc_8a1b4b5494ea42"
SCRATCH_CID = "gc_ddd9445590464f"


# ── Shared fixtures ──
@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def fresh_user_session():
    """Register a fresh user so we get clean plays (max 5/game)."""
    s = requests.Session()
    email = f"iter149{uuid.uuid4().hex[:10]}@bigfm.dubai"
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "IterTest123!",
                     "name": "Iter149 Fresh"})
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return s


# ── 1) Games discovery — TWO games for Fun Pizza Kitchen ──
class TestGameDiscovery:
    def test_discover_two_games(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/games/discover",
                             params={"merchant_id": MERCHANT_ID})
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or data.get("campaigns") or []
        cids = [g.get("campaign_id") for g in items]
        assert SPIN_CID in cids, f"missing spin, got {cids}"
        assert SCRATCH_CID in cids, f"missing scratch, got {cids}"

    def test_scratch_meta_prizes(self, fresh_user_session):
        r = fresh_user_session.get(f"{BASE_URL}/api/games/{SCRATCH_CID}")
        assert r.status_code == 200, r.text
        data = r.json()
        prizes = data.get("prizes") or []
        labels = [p.get("display_label") or p.get("label") for p in prizes]
        # 6 prizes: 10/20/30/40% off, Free Small Pizza, $10 Gift Card
        assert len(prizes) == 6, f"expected 6 prizes, got {len(prizes)}: {labels}"
        joined = " | ".join((s or "") for s in labels)
        for needle in ["10%", "20%", "30%", "40%", "Free Small Pizza", "10"]:
            assert needle.lower() in joined.lower(), f"missing '{needle}' in {labels}"
        # weights hidden from public view
        for p in prizes:
            assert "weight" not in p and "probability" not in p, \
                f"weight leaked: {p}"


# ── 2) Scratch Play ──
class TestScratchPlay:
    def test_play_returns_win(self, fresh_user_session):
        r = fresh_user_session.post(f"{BASE_URL}/api/games/{SCRATCH_CID}/play",
                                     json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("won") is True, f"expected won:true, got {data}"
        outcome = data.get("outcome_type")
        assert outcome in ("coupon", "gift_card"), f"unexpected outcome {outcome}"
        wallet = data.get("wallet_item_type")
        assert wallet in ("coupon", "gift_card"), f"wallet_item_type {wallet}"
        if outcome == "coupon":
            assert data.get("code") or (data.get("coupon") or {}).get("code"), data
        # stash code for redeem test
        code = data.get("code") or (data.get("coupon") or {}).get("code")
        pytest.first_won_code = code
        pytest.first_won_outcome = outcome


# ── 3) Winners feed ──
class TestWinners:
    def test_recent_winners(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/games/winners/recent",
                             params={"merchant_id": MERCHANT_ID, "limit": 15})
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or []
        assert len(items) >= 1, f"expected recent winners, got {items}"
        row = items[0]
        for k in ("first_name", "prize_label", "prize_color", "played_at"):
            assert k in row, f"missing {k} in {row}"


# ── 4) Coupon lookup & redeem ──
class TestCouponFlow:
    def test_lookup_bad_code(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/games/coupon/lookup",
                             params={"code": "BIGFM-DOESNTEXIST-XX"})
        assert r.status_code == 200
        data = r.json()
        assert data.get("found") is False
        assert data.get("reason") == "code_not_found"

    def test_lookup_and_redeem_won_coupon(self, fresh_user_session, anon_session):
        # Play again to guarantee a fresh coupon (previous test may have minted gift card)
        code = getattr(pytest, "first_won_code", None)
        outcome = getattr(pytest, "first_won_outcome", None)
        if not code or outcome != "coupon":
            # Try up to 4 more plays to get a coupon (10% odds gift card)
            for _ in range(4):
                r = fresh_user_session.post(f"{BASE_URL}/api/games/{SCRATCH_CID}/play",
                                     json={})
                if r.status_code != 200:
                    break
                d = r.json()
                if d.get("outcome_type") == "coupon":
                    code = d.get("code") or (d.get("coupon") or {}).get("code")
                    break
        assert code, "could not obtain a fresh game-won coupon after retries"

        # Lookup
        r = anon_session.get(f"{BASE_URL}/api/games/coupon/lookup",
                             params={"code": code})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("found") is True
        assert data.get("prize_title"), data
        assert data.get("business_name"), data
        assert data.get("status") in ("saved", "active", "issued", "unused"), data

        # Redeem (idempotent)
        r = anon_session.post(f"{BASE_URL}/api/games/coupon/redeem",
                              json={"code": code})
        assert r.status_code == 200, r.text
        d1 = r.json()
        assert d1.get("ok") is True
        assert d1.get("status") == "redeemed"

        # Idempotent second call
        r2 = anon_session.post(f"{BASE_URL}/api/games/coupon/redeem",
                               json={"code": code})
        assert r2.status_code == 200, r2.text
        assert r2.json().get("idempotent") is True

    def test_redeem_bad_code_404(self, anon_session):
        r = anon_session.post(f"{BASE_URL}/api/games/coupon/redeem",
                              json={"code": "BIGFM-NOSUCH-CODE"})
        assert r.status_code == 404


# ── 5) Sponsor Bidding ──
class TestSponsorBidding:
    def test_promoted_carries_bid_cents_and_sorted(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/promoted/stations",
                             params={"limit": 6})
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or []
        assert len(items) >= 1
        for it in items:
            assert "bid_cents" in it or "cpm_bid_cents" in it, f"no bid on {it}"
        # bid_cents sorted desc
        bids = [int(it.get("bid_cents") or it.get("cpm_bid_cents") or 0)
                for it in items]
        assert bids == sorted(bids, reverse=True), f"not sorted desc: {bids}"
        pytest.first_promo_id = items[0].get("promo_id")
        pytest.first_promo_bid = bids[0]

    def test_bid_raise(self, admin_session, anon_session):
        # Find a promo we can boost — either unowned, or owned by admin.
        # /api/promoted/stations returns advertiser_id in items? Check via admin.
        r = anon_session.get(f"{BASE_URL}/api/promoted/stations",
                             params={"limit": 20})
        items = r.json().get("items") or []
        boosted_ok = False
        last_err = None
        for it in items:
            pid = it.get("promo_id")
            cur = int(it.get("bid_cents") or it.get("cpm_bid_cents") or 500)
            new_bid = min(cur + 200, 100000)
            rr = admin_session.post(f"{BASE_URL}/api/promoted/{pid}/bid",
                                    json={"cpm_bid_cents": new_bid})
            if rr.status_code == 200:
                data = rr.json()
                assert data.get("ok") is True
                assert data.get("cpm_bid_cents") == new_bid
                pytest.boostable_promo_id = pid
                boosted_ok = True
                break
            last_err = f"{rr.status_code} {rr.text}"
        assert boosted_ok, f"could not find any promo boostable by admin: last={last_err}"

    def test_bid_clamped_min(self, admin_session):
        promo_id = getattr(pytest, "boostable_promo_id", None)
        if not promo_id:
            pytest.skip("no boostable promo from previous test")
        r = admin_session.post(f"{BASE_URL}/api/promoted/{promo_id}/bid",
                               json={"cpm_bid_cents": 1})
        assert r.status_code == 200, r.text
        assert r.json().get("cpm_bid_cents") == 100  # clamped to min

    def test_bid_unauth_401(self, anon_session):
        promo_id = getattr(pytest, "boostable_promo_id", None) \
                    or getattr(pytest, "first_promo_id", None)
        r = anon_session.post(f"{BASE_URL}/api/promoted/{promo_id}/bid",
                              json={"cpm_bid_cents": 500})
        assert r.status_code in (401, 403), r.text
