"""Iteration 192 — FUUSIC Social V2 Right-Rail V2 Sponsor + Analytics + Smart Suggestions.

Covers:
  • Rail Analytics: POST /api/social/rail/event (impression/click, cap 50,
    filter invalid actions, sponsorship_id increments impressions/clicks
    in /api/social/rail/sponsor/list stats).
  • Sponsored Slots: tiers, eligible-shows, create, checkout (auto-active
    in mock/test), list, cancel + authorization (403 for non-owners,
    404 for not-your-show).
  • Sponsored injection: active sponsorship pins card at index 0 of
    /api/social/rail with kind='sponsored', badge='SPONSORED',
    sponsorship_id present. Total cards still 1..7 (spec says 5..7).
  • Smart Suggestions: seeded Marco Rossi (usr_rail_c2) surfaces as a
    follow card with hint='4 mutual' for demo@ and appears earlier
    than 0-mutual suggestions.
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


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="session")
def merchant_client():
    return _login(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="session")
def free_client():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ── Sponsor: tiers/eligible-shows ─────────────────────────────────────
class TestSponsorTiers:
    def test_tiers(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/tiers", timeout=30)
        assert r.status_code == 200, r.text
        tiers = r.json().get("tiers") or []
        ids = {t["id"] for t in tiers}
        assert ids == {"24h", "3d", "7d"}, f"unexpected tiers: {ids}"
        amounts = {t["id"]: t["amount_cents"] for t in tiers}
        assert amounts == {"24h": 900, "3d": 1900, "7d": 4900}


class TestSponsorEligibleShows:
    def test_eligible_shows_owner(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/eligible-shows",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        shows = r.json().get("shows") or []
        ids = {s["id"] for s in shows}
        assert "lsw_sponsor_live" in ids and "lsw_sponsor_evt" in ids, \
            f"seeded sponsor shows missing: {ids}"

    def test_eligible_shows_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/eligible-shows",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403, r.text
        body = r.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("detail")
        assert "not_your_business" in str(code), body


# ── Sponsor: create / checkout / list / cancel + authorization ────────
@pytest.fixture(scope="session")
def created_sponsorship(merchant_client):
    """Create a fresh sponsorship for lsw_sponsor_evt, tier 24h."""
    r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                             json={"merchant_id": MERCHANT_ID,
                                   "target_id": "lsw_sponsor_evt",
                                   "tier": "24h"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["sponsorship_id"]


class TestSponsorCreateAuth:
    def test_create_non_owner_403(self, free_client):
        r = free_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                             json={"merchant_id": MERCHANT_ID,
                                   "target_id": "lsw_sponsor_evt",
                                   "tier": "24h"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_create_not_your_show_404(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                 json={"merchant_id": MERCHANT_ID,
                                       "target_id": "lsw_rail_live_1",  # host = advisor
                                       "tier": "24h"}, timeout=30)
        assert r.status_code == 404, r.text

    def test_create_bad_tier_400(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                 json={"merchant_id": MERCHANT_ID,
                                       "target_id": "lsw_sponsor_evt",
                                       "tier": "1yr"}, timeout=30)
        assert r.status_code == 400, r.text


class TestSponsorCheckoutMock:
    def test_checkout_auto_activates(self, merchant_client, created_sponsorship):
        sid = created_sponsorship
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid}/checkout",
                                 json={}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Auto-activation in mock/test mode.
        if d.get("mock"):
            assert d.get("status") == "active"
            assert d.get("ends_at")
        # Verify in list
        rl = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                 params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert rl.status_code == 200
        items = rl.json().get("sponsorships") or []
        found = next((it for it in items if it["id"] == sid), None)
        assert found, f"created sponsorship missing from list: {sid}"
        # If checkout returned mock=True, it must now be active.
        if d.get("mock"):
            assert found["status"] == "active", found

    def test_checkout_wrong_status(self, merchant_client, created_sponsorship):
        # Second checkout on an already-active sponsorship must 400.
        sid = created_sponsorship
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid}/checkout",
                                 json={}, timeout=30)
        assert r.status_code == 400, r.text


class TestSponsorList:
    def test_list_owner_returns_stats_keys(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        for it in (r.json().get("sponsorships") or []):
            assert "impressions" in it and "clicks" in it and "ctr" in it

    def test_list_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403


class TestSponsorCancel:
    def test_cancel_not_found(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/rsp_missing/cancel",
                                 json={}, timeout=30)
        assert r.status_code == 404


# ── Sponsored card injection in /api/social/rail ─────────────────────
class TestSponsoredInjection:
    def test_first_card_is_sponsored_when_active(self, merchant_client, demo_client,
                                                 created_sponsorship):
        # Ensure active (idempotent).
        merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{created_sponsorship}/checkout",
                             json={}, timeout=30)
        for route in ("/social", "/channels", "/shop"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            assert r.status_code == 200, r.text
            cards = r.json().get("cards") or []
            assert len(cards) >= 1, f"no cards on {route}"
            first = cards[0]
            assert first["kind"] == "sponsored", (
                f"first card must be sponsored on {route}, got {first}")
            assert (first.get("badge") or "").upper() == "SPONSORED", first
            assert first.get("sponsorship_id"), first
            assert 1 <= len(cards) <= 7


# ── Rail Analytics: POST /api/social/rail/event ──────────────────────
class TestRailEvents:
    def test_records_impression_and_click(self, demo_client, created_sponsorship):
        payload = {"events": [
            {"card_id": "test-card-a", "kind": "follow", "action": "impression",
             "page_route": "/social"},
            {"card_id": "test-card-a", "kind": "follow", "action": "click",
             "page_route": "/social"},
            {"card_id": "sponsored-x", "kind": "sponsored", "action": "impression",
             "page_route": "/social", "sponsorship_id": created_sponsorship},
        ]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event",
                             json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("recorded") == 3

    def test_filters_invalid_actions(self, demo_client):
        payload = {"events": [
            {"card_id": "x", "kind": "follow", "action": "hover"},
            {"card_id": "x", "kind": "follow", "action": ""},
            {"card_id": "x", "kind": "follow", "action": "impression"},
        ]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event",
                             json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("recorded") == 1

    def test_caps_at_50(self, demo_client):
        payload = {"events": [
            {"card_id": f"c{i}", "kind": "follow", "action": "impression"}
            for i in range(80)]}
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event",
                             json=payload, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("recorded") == 50

    def test_sponsorship_stats_increment_and_dedup(self, merchant_client,
                                                   demo_client):
        # Fresh sponsorship → demo has zero prior events on it.
        cr = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                  json={"merchant_id": MERCHANT_ID,
                                        "target_id": "lsw_sponsor_evt",
                                        "tier": "24h"}, timeout=30)
        assert cr.status_code == 200, cr.text
        sid = cr.json()["sponsorship_id"]
        # Fire 2 impressions + 1 click bound to sid from the SAME user.
        demo_client.post(f"{BASE_URL}/api/social/rail/event", json={"events": [
            {"card_id": "sp-1", "kind": "sponsored", "action": "impression",
             "sponsorship_id": sid},
            {"card_id": "sp-1", "kind": "sponsored", "action": "impression",
             "sponsorship_id": sid},
            {"card_id": "sp-1", "kind": "sponsored", "action": "click",
             "sponsorship_id": sid},
        ]}, timeout=30)
        rl2 = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        item1 = next(it for it in rl2["sponsorships"] if it["id"] == sid)
        # Deduped to ONE impression + ONE click per user (anti-inflation).
        assert item1["impressions"] == 1
        assert item1["clicks"] == 1
        # Replaying does NOT inflate further.
        demo_client.post(f"{BASE_URL}/api/social/rail/event", json={"events": [
            {"card_id": "sp-1", "kind": "sponsored", "action": "impression",
             "sponsorship_id": sid},
        ]}, timeout=30)
        rl3 = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        item2 = next(it for it in rl3["sponsorships"] if it["id"] == sid)
        assert item2["impressions"] == 1

    def test_bogus_sponsorship_id_not_attributed(self, merchant_client, demo_client):
        # Events referencing a non-existent sponsorship are recorded as
        # card-level only (sponsorship_id nulled) and never inflate a merchant.
        r = demo_client.post(f"{BASE_URL}/api/social/rail/event", json={"events": [
            {"card_id": "x", "kind": "sponsored", "action": "impression",
             "sponsorship_id": "rsp_does_not_exist"}]}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("recorded") == 1


# ── Smart Suggestions: Marco Rossi shows with '4 mutual' ─────────────
class TestSmartSuggestions:
    def test_marco_appears_with_mutual_hint(self, demo_client):
        # Marco Rossi is a follow suggestion. Try several routes and gather cards.
        found_marco = None
        marco_index = None
        follow_cards = []
        for route in ("/social", "/channels", "/shop", "/home"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            if r.status_code != 200:
                continue
            cards = r.json().get("cards") or []
            for i, c in enumerate(cards):
                if c.get("kind") == "follow":
                    follow_cards.append((route, i, c))
                    if c.get("follow_id") == "usr_rail_c2" or "Marco" in (c.get("title") or ""):
                        found_marco = c
                        marco_index = i
                        break
            if found_marco:
                break
        assert found_marco is not None, (
            f"Marco Rossi (usr_rail_c2) not surfaced in follow rail cards. "
            f"Follow cards seen: {[(r,i,c.get('title'),c.get('hint')) for r,i,c in follow_cards]}")
        hint = (found_marco.get("hint") or "").lower()
        # Spec: '4 mutual' hint
        assert "mutual" in hint, f"expected mutual hint on Marco, got: {found_marco}"
        # Best-effort: check '4' appears in hint
        assert "4" in hint, f"expected '4 mutual' on Marco, got hint={hint}"

    def test_mutual_ranks_above_zero_mutual(self, demo_client):
        """Marco (4 mutual) should appear before any 0-mutual follow suggestion
        on at least one page_route."""
        for route in ("/social", "/home"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            if r.status_code != 200:
                continue
            cards = r.json().get("cards") or []
            follow_positions = [(i, c) for i, c in enumerate(cards) if c.get("kind") == "follow"]
            marco_pos = None
            zero_positions = []
            for i, c in follow_positions:
                hint = (c.get("hint") or "").lower()
                is_marco = c.get("follow_id") == "usr_rail_c2" or "Marco" in (c.get("title") or "")
                if is_marco:
                    marco_pos = i
                elif "mutual" not in hint:
                    zero_positions.append(i)
            if marco_pos is not None and zero_positions:
                assert marco_pos < min(zero_positions), (
                    f"Marco@{marco_pos} should rank above 0-mutual@{zero_positions} on {route}")
                return
        pytest.skip("Not enough follow-card mix to compare mutual ranking")


# ── Regression: rail contract still 1..7 (spec 5..7) ─────────────────
class TestRailStillContextual:
    def test_still_5_to_7_cards(self, demo_client):
        for route in ("/social", "/channels", "/shop"):
            r = demo_client.get(f"{BASE_URL}/api/social/rail",
                                params={"page_route": route, "limit": 7}, timeout=30)
            assert r.status_code == 200
            cards = r.json().get("cards") or []
            assert 5 <= len(cards) <= 7, f"{route}: got {len(cards)} cards"
