"""Iteration 194 — FUUSIC Social V2 Right-Rail Ad-Wallet + per-area DAILY
SECOND-PRICE (Vickrey) auction + Category Targeting + Bid Alerts + Interest
Onboarding.

Replaces the old one-time-Stripe-checkout sponsor tests (billing model was
swapped to a continuous ad-wallet + daily clearing model).

Covers:
  • Config: GET /api/social/rail/sponsor/config (durations 1d/3d/7d, areas
    social/shop/listen, daily floor, increment, top-up presets).
  • Ad-Wallet: GET /api/social/rail/wallet (balance + txns) + owner auth.
  • Standing bids: create with target_pages + daily_bid_cents (+ validation:
    non-owner 403, not-your-show 404, bad duration 400, no areas 400,
    below-floor 400); list returns per-area status + wallet balance + spend;
    adjust bid (re-settle) + below-floor guard; cancel (404 + ended).
  • Second-price: highest bid wins each area's single slot; clearing price
    <= own bid and >= floor; single isolated bidder clears at the floor.
  • Bid alerts: GET /rail/alerts + POST /rail/alerts/read + owner auth.
  • Interests + first-run onboarding: GET/PUT /interests (invalid filtered),
    POST /interests/skip flips needs_onboarding false.
  • Rail analytics: POST /api/social/rail/event (impression/click, dedup by
    sponsorship, cap 50, invalid filtered, bogus sponsorship nulled).
  • Sponsored injection into /api/social/rail (pinned card kind='sponsored').
  • Smart Suggestions: Marco Rossi surfaces with a '4 mutual' hint.
  • Rail still 5..7 contextual cards.
"""
import os
import requests
import pytest


def _read_env(path, key):
    try:
        with open(path) as f:
            for ln in f:
                if ln.startswith(f"{key}="):
                    return ln.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai";     DEMO_PASSWORD = "DemoPass123!"
TEST_EMAIL = "test@bigfm.dubai";     TEST_PASSWORD = "TestUser123!"
FREE_EMAIL = "freeuser@bigfm.dubai"; FREE_PASSWORD = "FreePass123!"

MERCHANT_ID = "biz_karak_cafe_karama"
FLOOR = 500  # $5 / area / day


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


def _detail_code(resp):
    body = resp.json()
    d = body.get("detail")
    if isinstance(d, dict):
        return d.get("code")
    return d


@pytest.fixture(scope="session")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="session")
def merchant_client():
    return _login(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="session")
def free_client():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ── Config ────────────────────────────────────────────────────────────
class TestSponsorConfig:
    def test_config_shape(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/config", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        dur_ids = {x["id"] for x in d["durations"]}
        assert dur_ids == {"1d", "3d", "7d"}, dur_ids
        area_ids = {a["id"] for a in d["areas"]}
        assert area_ids == {"social", "shop", "listen"}, area_ids
        assert d["daily_floor_cents"] == FLOOR
        assert d["increment_cents"] >= 1
        assert isinstance(d["topup_presets_cents"], list) and d["topup_presets_cents"]


# ── Ad-Wallet ─────────────────────────────────────────────────────────
class TestWallet:
    def test_wallet_owner(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/wallet",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["balance_cents"], int) and d["balance_cents"] >= 0
        assert isinstance(d["txns"], list)

    def test_wallet_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/wallet",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403, r.text
        assert "not_your_business" in str(_detail_code(r))


# ── Eligible shows ────────────────────────────────────────────────────
class TestEligibleShows:
    def test_eligible_shows_owner(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/eligible-shows",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        ids = {s["id"] for s in (r.json().get("shows") or [])}
        assert "lsw_sponsor_live" in ids and "lsw_sponsor_evt" in ids, ids

    def test_eligible_shows_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/eligible-shows",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403, r.text


# ── Create standing bid + validation ──────────────────────────────────
class TestCreateValidation:
    def test_non_owner_403(self, free_client):
        r = free_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                            json={"merchant_id": MERCHANT_ID, "target_id": "lsw_sponsor_evt",
                                  "duration_tier": "1d", "daily_bid_cents": 800,
                                  "target_pages": ["shop"]}, timeout=30)
        assert r.status_code == 403, r.text

    def test_not_your_show_404(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                json={"merchant_id": MERCHANT_ID, "target_id": "lsw_rail_live_1",
                                      "duration_tier": "1d", "daily_bid_cents": 800,
                                      "target_pages": ["shop"]}, timeout=30)
        assert r.status_code == 404, r.text

    def test_bad_duration_400(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                json={"merchant_id": MERCHANT_ID, "target_id": "lsw_sponsor_evt",
                                      "duration_tier": "1yr", "daily_bid_cents": 800,
                                      "target_pages": ["shop"]}, timeout=30)
        assert r.status_code == 400 and "bad_duration" in str(_detail_code(r)), r.text

    def test_no_target_areas_400(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                json={"merchant_id": MERCHANT_ID, "target_id": "lsw_sponsor_evt",
                                      "duration_tier": "1d", "daily_bid_cents": 800,
                                      "target_pages": []}, timeout=30)
        assert r.status_code == 400 and "no_target_areas" in str(_detail_code(r)), r.text

    def test_bid_below_floor_400(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                json={"merchant_id": MERCHANT_ID, "target_id": "lsw_sponsor_evt",
                                      "duration_tier": "1d", "daily_bid_cents": 300,
                                      "target_pages": ["shop"]}, timeout=30)
        assert r.status_code == 400 and "bid_below_floor" in str(_detail_code(r)), r.text


@pytest.fixture(scope="session")
def created_sponsorship(merchant_client):
    """A fresh standing bid on lsw_sponsor_evt targeting ONLY shop, below the
    seeded shop bidder so it doesn't disturb the seed auction assertions."""
    r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                            json={"merchant_id": MERCHANT_ID, "target_id": "lsw_sponsor_evt",
                                  "duration_tier": "1d", "daily_bid_cents": 700,
                                  "target_pages": ["shop"]}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["sponsorship_id"]
    assert d["target_pages"] == ["shop"]
    assert d["daily_bid_cents"] == 700
    return d["sponsorship_id"]


# ── List + per-area status ────────────────────────────────────────────
class TestList:
    def test_list_shape(self, merchant_client, created_sponsorship):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "wallet_balance_cents" in d and "daily_floor_cents" in d
        assert d["daily_floor_cents"] == FLOOR
        for it in d["sponsorships"]:
            for k in ("target_pages", "daily_bid_cents", "area_status",
                      "featured_any", "spend_cents", "impressions", "clicks", "ctr"):
                assert k in it, f"missing {k}: {it}"

    def test_list_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403


class TestSecondPrice:
    def test_highest_bid_wins_social_slot(self, merchant_client):
        # Seeded: rsp_seed_hi (2500, social+listen) beats rsp_seed_lo (900) and
        # rsp_seed_mid (1500) for the single SOCIAL slot.
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        by_id = {it["id"]: it for it in r.json()["sponsorships"]}
        hi = by_id.get("rsp_seed_hi")
        assert hi, "seeded rsp_seed_hi present"
        soc = (hi["area_status"] or {}).get("social") or {}
        assert soc.get("featured") is True and soc.get("rank") == 1, soc
        # Second-price: pays at most its own bid, at least the floor.
        clearing = soc.get("clearing_cents")
        assert clearing is not None and FLOOR <= clearing <= hi["daily_bid_cents"], soc

    def test_single_bidder_clears_at_floor(self, merchant_client):
        # rsp_seed_hi is the ONLY bidder on the LISTEN slot → clears at floor.
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        hi = next(it for it in r.json()["sponsorships"] if it["id"] == "rsp_seed_hi")
        listen = (hi["area_status"] or {}).get("listen") or {}
        assert listen.get("featured") is True, listen
        assert listen.get("clearing_cents") == FLOOR, listen


# ── Adjust bid (re-settle) + cancel ───────────────────────────────────
class TestAdjustAndCancel:
    def test_adjust_bid_ok(self, merchant_client, created_sponsorship):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{created_sponsorship}/bid",
            json={"daily_bid_cents": 2000}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["daily_bid_cents"] == 2000

    def test_adjust_bid_below_floor_400(self, merchant_client, created_sponsorship):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{created_sponsorship}/bid",
            json={"daily_bid_cents": 300}, timeout=30)
        assert r.status_code == 400 and "bid_below_floor" in str(_detail_code(r)), r.text

    def test_cancel_not_found_404(self, merchant_client):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/rsp_missing/cancel", json={}, timeout=30)
        assert r.status_code == 404

    def test_cancel_ends_campaign(self, merchant_client, created_sponsorship):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{created_sponsorship}/cancel",
            json={}, timeout=30)
        assert r.status_code == 200, r.text
        rl = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        found = next((it for it in rl.json()["sponsorships"]
                      if it["id"] == created_sponsorship), None)
        assert found and found["status"] == "ended", found


# ── Insights ──────────────────────────────────────────────────────────
class TestInsights:
    def test_insights_daily_series(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/rsp_seed_hi/insights",
                                params={"days": 7}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["series"]) == 7
        assert all("date" in x and "impressions" in x and "clicks" in x for x in d["series"])
        assert d["totals"]["impressions"] > 0

    def test_insights_non_owner_404(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/rsp_seed_hi/insights",
                            timeout=30)
        assert r.status_code == 404


# ── Bid alerts ────────────────────────────────────────────────────────
class TestAlerts:
    def test_alerts_owner(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/alerts",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["alerts"], list) and isinstance(d["unread"], int)

    def test_alerts_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/alerts",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403

    def test_alerts_mark_read(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/alerts/read", None,
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        rl = merchant_client.get(f"{BASE_URL}/api/social/rail/alerts",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert rl.json()["unread"] == 0


# ── Interests + first-run onboarding ──────────────────────────────────
class TestInterests:
    def test_get_shape(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/interests", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["topics"]) >= 8
        assert "selected" in d and "needs_onboarding" in d

    def test_put_filters_invalid(self, merchant_client):
        # Use the merchant account so the demo user stays needs_onboarding=true
        # for the mobile / V2-shell onboarding demo in preview.
        r = merchant_client.put(f"{BASE_URL}/api/social/interests",
                            json={"interests": ["ASTROLOGY", "DJ_SETS", "NOT_A_TOPIC"]},
                            timeout=30)
        assert r.status_code == 200, r.text
        assert set(r.json()["selected"]) == {"ASTROLOGY", "DJ_SETS"}

    def test_skip_flips_onboarding(self, free_client):
        r = free_client.post(f"{BASE_URL}/api/social/interests/skip", json={}, timeout=30)
        assert r.status_code == 200, r.text
        g = free_client.get(f"{BASE_URL}/api/social/interests", timeout=30)
        assert g.json()["needs_onboarding"] is False


# ── Rail analytics ────────────────────────────────────────────────────
class TestRailEvents:
    def test_records_impression_and_click(self, demo_client):
        import uuid
        cid = f"test-card-{uuid.uuid4().hex[:8]}"
        payload = {"events": [
            {"card_id": cid, "kind": "follow", "action": "impression",
             "page_route": "/social"},
            {"card_id": cid, "kind": "follow", "action": "click",
             "page_route": "/social"},
            {"card_id": f"{cid}-2", "kind": "follow", "action": "impression",
             "page_route": "/social"},
        ]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        # Card-level events (no sponsorship_id) are recorded freely, not deduped.
        assert r.json().get("recorded") == 3

    def test_filters_invalid_actions(self, demo_client):
        payload = {"events": [
            {"card_id": "x", "kind": "follow", "action": "hover"},
            {"card_id": "x", "kind": "follow", "action": ""},
            {"card_id": "x", "kind": "follow", "action": "impression"},
        ]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("recorded") == 1

    def test_caps_at_50(self, demo_client):
        payload = {"events": [
            {"card_id": f"c{i}", "kind": "follow", "action": "impression"}
            for i in range(80)]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("recorded") == 50

    def test_bogus_sponsorship_not_attributed(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event", json={"events": [
            {"card_id": "x", "kind": "sponsored", "action": "impression",
             "sponsorship_id": "rsp_does_not_exist"}]}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("recorded") == 1


# ── Sponsored injection into the compact rail ─────────────────────────
class TestSponsoredInjection:
    def test_first_card_sponsored_when_active(self, demo_client):
        for route in ("/social", "/channels", "/shop"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            assert r.status_code == 200, r.text
            cards = r.json().get("cards") or []
            assert len(cards) >= 1, f"no cards on {route}"
            first = cards[0]
            assert first["kind"] == "sponsored", f"{route}: first {first}"
            assert (first.get("badge") or "").upper() == "SPONSORED", first
            assert first.get("sponsorship_id"), first


# ── Smart Suggestions ─────────────────────────────────────────────────
class TestSmartSuggestions:
    def test_marco_with_mutual_hint(self, demo_client):
        found = None
        for route in ("/social", "/channels", "/shop", "/home"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            if r.status_code != 200:
                continue
            for c in (r.json().get("cards") or []):
                if c.get("kind") == "follow" and (
                        c.get("follow_id") == "usr_rail_c2"
                        or "Marco" in (c.get("title") or "")):
                    found = c
                    break
            if found:
                break
        assert found is not None, "Marco Rossi (usr_rail_c2) not surfaced as a follow card"
        hint = (found.get("hint") or "").lower()
        assert "mutual" in hint and "4" in hint, found


# ── Regression: rail still 5..7 contextual cards ──────────────────────
class TestRailContract:
    def test_five_to_seven_cards(self, demo_client):
        for route in ("/social", "/channels", "/shop"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            assert r.status_code == 200
            cards = r.json().get("cards") or []
            assert 5 <= len(cards) <= 7, f"{route}: got {len(cards)} cards"
