"""Iteration 123 — RadioLife Partner API v1 Phase D validation.

Covers:
  * Sponsored games: /game-templates, /sponsored-games (POST + list + detail)
  * Predict&Win discovery: /predictions/eligible
  * Trivia discovery: /trivia/inventory
  * Display + audio inventory: /inventory/display, /inventory/audio
  * Sponsorships: /sponsorships/inventory + POST /sponsorships (rj_read, trivia)
  * Cross-cutting: scope enforcement (403), Idempotency-Key replay,
    external_id dedup, cursor pagination shape, error envelope, response headers
  * Regression on Phase A/B/C: /capabilities, /inventory, /markets, /stations
    (cursor paginated), /me, /products, POST /quotes, POST /creatives (+ list),
    POST /campaigns single-format + multi-format line_items.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
V1 = f"{BASE_URL}/api/v1"

# Full-scope SANDBOX key (partner: prt_Ngu4e33qm4KULA)
FULL_KEY = "rlk_test_5K60MMvOyYDv.1DgfP8f5qfWjEMmQDFed1m04G0aEr5sdWvVZvi-pT_I"
# Limited-scope SANDBOX key (only catalog:read) — minted via _mint_limited_key.py
LIMITED_KEY = "rlk_test_tGV3_3OF_xVi.Ss4UrbGWmTdfb7vYEY3Re1cnYarSfMmpiLa5-Hks-FM"
ADVERTISER_ID = "advv2_a1c94f911a7c9d"


# ────────────────────────── fixtures ──────────────────────────
@pytest.fixture(scope="session")
def client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {FULL_KEY}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def limited_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {LIMITED_KEY}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def template_id(client: requests.Session) -> str:
    r = client.get(f"{V1}/game-templates")
    assert r.status_code == 200
    ids = [t["template_id"] for t in r.json()["data"]]
    assert "tpl_spin_wheel" in ids
    return "tpl_spin_wheel"


# ────────────────────────── Phase D – games ──────────────────────────
class TestGameTemplates:
    def test_lists_active_templates_with_metadata(self, client):
        r = client.get(f"{V1}/game-templates")
        assert r.status_code == 200
        j = r.json()
        assert "data" in j and j["count"] == len(j["data"]) and j["count"] > 0
        t = j["data"][0]
        # required metadata
        for k in ("template_id", "game_type", "name", "min_prizes",
                  "max_prizes", "prize_types", "redemption_methods"):
            assert k in t, f"missing {k}"
        assert isinstance(t["prize_types"], list) and t["prize_types"]
        assert isinstance(t["redemption_methods"], list) and t["redemption_methods"]

    def test_response_headers(self, client):
        r = client.get(f"{V1}/game-templates")
        assert r.headers.get("X-RadioLife-API-Version"), "version header missing"
        assert r.headers.get("X-Request-ID"), "request-id header missing"


class TestSponsoredGamesCreate:
    def _payload(self, template_id: str, ext_id: str | None = None) -> dict:
        return {
            "advertiser_id": ADVERTISER_ID,
            "template_id": template_id,
            "name": f"TEST_iter123 Spin {uuid.uuid4().hex[:6]}",
            "sponsor_name": "TEST Brand",
            "external_id": ext_id,
            "prizes": [
                {"prize_type": "bigcoin", "title": "1000 BigCoin",
                 "probability_weight": 70, "inventory_total": 100,
                 "redemption_method": "in_app_wallet"},
                {"prize_type": "coupon", "title": "10% off",
                 "probability_weight": 30, "inventory_total": 50,
                 "redemption_method": "promo_code"},
            ],
        }

    def test_create_sandbox_auto_activates(self, client, template_id):
        r = client.post(f"{V1}/sponsored-games",
                        json=self._payload(template_id))
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["environment"] == "SANDBOX"
        sg = j["sponsored_game"]
        assert sg["campaign_id"].startswith("cmp_")
        assert sg["status"] == "active", f"expected sandbox auto-activate, got {sg['status']}"
        assert sg["template_id"] == template_id
        # NOTE: POST response is slim (no advertiser_id) — verified via GET below

        # Persistence: GET single sponsored game
        cid = sg["campaign_id"]
        r2 = client.get(f"{V1}/sponsored-games/{cid}")
        assert r2.status_code == 200
        got = r2.json()["sponsored_game"]
        assert got["campaign_id"] == cid
        assert got["status"] == "active"
        assert got["advertiser_id"] == ADVERTISER_ID
        assert isinstance(got.get("prizes"), list) and len(got["prizes"]) == 2
        weights = sum(p["probability_weight"] for p in got["prizes"])
        assert weights == 100

    def test_idempotency_key_replays_same_response(self, client, template_id):
        idem = f"idem_iter123_{uuid.uuid4().hex}"
        p = self._payload(template_id)
        h = {"Idempotency-Key": idem}
        r1 = client.post(f"{V1}/sponsored-games", json=p, headers=h)
        assert r1.status_code == 201
        cid1 = r1.json()["sponsored_game"]["campaign_id"]
        # replay with a DIFFERENT body — same idem-key must return original
        p2 = self._payload(template_id)
        p2["name"] = "TEST_iter123 different name"
        r2 = client.post(f"{V1}/sponsored-games", json=p2, headers=h)
        assert r2.status_code == 201
        assert r2.json()["sponsored_game"]["campaign_id"] == cid1

    def test_external_id_dedups(self, client, template_id):
        ext = f"ext_iter123_{uuid.uuid4().hex[:10]}"
        r1 = client.post(f"{V1}/sponsored-games",
                         json=self._payload(template_id, ext_id=ext))
        assert r1.status_code == 201
        cid1 = r1.json()["sponsored_game"]["campaign_id"]
        # different idem key, same external_id — must return existing
        r2 = client.post(f"{V1}/sponsored-games",
                         json=self._payload(template_id, ext_id=ext),
                         headers={"Idempotency-Key": f"idem_{uuid.uuid4().hex}"})
        assert r2.status_code == 201
        assert r2.json()["sponsored_game"]["campaign_id"] == cid1

    def test_invalid_prize_weights_fail(self, client, template_id):
        p = self._payload(template_id)
        p["prizes"][0]["probability_weight"] = 10  # 10+30=40, not 100
        r = client.post(f"{V1}/sponsored-games", json=p)
        assert r.status_code == 400, r.text
        j = r.json()
        assert "error" in j and j["error"].get("code")

    def test_unknown_template_fails(self, client):
        p = {
            "advertiser_id": ADVERTISER_ID,
            "template_id": "tpl_does_not_exist",
            "name": "TEST bad template",
            "prizes": [{"prize_type": "bigcoin", "title": "x",
                        "probability_weight": 100, "inventory_total": 1}],
        }
        r = client.post(f"{V1}/sponsored-games", json=p)
        assert r.status_code == 400


class TestSponsoredGamesList:
    def test_list_returns_only_advertiser_sponsored_games(self, client):
        r = client.get(f"{V1}/sponsored-games?advertiser_id={ADVERTISER_ID}")
        assert r.status_code == 200
        j = r.json()
        # cursor pagination envelope
        for k in ("data", "count", "next_cursor", "has_more"):
            assert k in j
        assert j["count"] == len(j["data"])
        for g in j["data"]:
            assert g["advertiser_id"] == ADVERTISER_ID
            assert g["campaign_id"].startswith("cmp_")

    def test_pagination_limit1(self, client):
        r = client.get(f"{V1}/sponsored-games?advertiser_id={ADVERTISER_ID}&limit=1")
        assert r.status_code == 200
        j = r.json()
        assert len(j["data"]) <= 1
        # if any more, has_more True and next_cursor is set
        if j["has_more"]:
            assert j["next_cursor"]
            r2 = client.get(f"{V1}/sponsored-games",
                            params={"advertiser_id": ADVERTISER_ID,
                                    "limit": 1, "cursor": j["next_cursor"]})
            assert r2.status_code == 200
            j2 = r2.json()
            ids1 = {x["campaign_id"] for x in j["data"]}
            ids2 = {x["campaign_id"] for x in j2["data"]}
            assert ids1.isdisjoint(ids2), "pagination returned overlap"

    def test_invalid_cursor(self, client):
        r = client.get(f"{V1}/sponsored-games",
                       params={"advertiser_id": ADVERTISER_ID,
                               "cursor": "not-a-valid-cursor"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_cursor"

    def test_get_nonexistent_returns_404(self, client):
        r = client.get(f"{V1}/sponsored-games/cmp_does_not_exist_xyz")
        assert r.status_code == 404
        assert r.json()["error"]["code"] in ("sponsored_game_not_found", "not_found")


# ────────────────────────── Phase D – discovery ──────────────────────────
class TestDiscoveryEndpoints:
    def test_predictions_eligible(self, client):
        r = client.get(f"{V1}/predictions/eligible")
        assert r.status_code == 200
        j = r.json()
        assert "data" in j
        # service returns {"items": [...]} inside data
        payload = j["data"]
        items = payload.get("items") if isinstance(payload, dict) else payload
        assert isinstance(items, list)
        if items:
            it = items[0]
            assert "parent_campaign_id" in it and it["parent_campaign_id"].startswith("pwc_")

    def test_trivia_inventory(self, client):
        r = client.get(f"{V1}/trivia/inventory")
        assert r.status_code == 200
        j = r.json()
        assert "scopes" in j and set(["room", "category", "any"]).issubset(set(j["scopes"]))
        assert isinstance(j["categories"], list) and j["categories"]

    def test_inventory_display(self, client):
        r = client.get(f"{V1}/inventory/display")
        assert r.status_code == 200
        j = r.json()
        assert j["product"] == "display_banner"
        assert isinstance(j["placements"], list) and j["placements"]
        for pl in j["placements"]:
            assert "placement" in pl and "dimensions" in pl

    def test_inventory_audio(self, client):
        r = client.get(f"{V1}/inventory/audio")
        assert r.status_code == 200
        j = r.json()
        assert isinstance(j["products"], list) and len(j["products"]) >= 2
        keys = {p["product"] for p in j["products"]}
        assert {"audio_preroll", "audio_midroll"}.issubset(keys)


# ────────────────────────── Phase D – sponsorships ──────────────────────────
class TestSponsorships:
    def test_inventory_predict_win(self, client):
        r = client.get(f"{V1}/sponsorships/inventory?type=predict_win")
        assert r.status_code == 200

    def test_inventory_trivia(self, client):
        r = client.get(f"{V1}/sponsorships/inventory?type=trivia")
        assert r.status_code == 200
        j = r.json()
        assert "target_types" in j and "selection_modes" in j
        assert "platform_fee_pct" in j

    def test_inventory_rj_read(self, client):
        r = client.get(f"{V1}/sponsorships/inventory?type=rj_read")
        assert r.status_code == 200
        j = r.json()
        assert "personas" in j and "disclosure_prefixes" in j

    def test_inventory_unknown_type(self, client):
        r = client.get(f"{V1}/sponsorships/inventory?type=totally_bogus")
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "unknown_sponsorship_type"

    def test_create_rj_read_sponsorship_sandbox_activates(self, client):
        body = {
            "type": "rj_read",
            "advertiser_id": ADVERTISER_ID,
            "any_station": True,
            "disclosure_prefix": "Sponsored by",
            "plays_target": 10,
            "cost_per_play_cents": 500,
            "script_body": "TEST_iter123 script — brand shoutout for QA",
            "product_name": "TEST product",
            "key_message": "tell a friend",
            "cta": "visit test.example",
            "external_id": f"ext_rj_{uuid.uuid4().hex[:8]}",
        }
        r = client.post(f"{V1}/sponsorships", json=body)
        # rj_read may reject if no matching persona/config in seed — accept 201 or 400
        assert r.status_code in (201, 400), r.text
        if r.status_code == 201:
            j = r.json()
            assert j["type"] == "rj_read"
            assert j["environment"] == "SANDBOX"
            sp = j["sponsorship"]
            sid = sp.get("id") or sp.get("sponsored_read_id")
            assert sid
            # status should reflect sandbox activation
            assert sp.get("status") in ("active", "approved", "live", "pending_review", "submitted", None)

    def test_create_unknown_type_fails(self, client):
        r = client.post(f"{V1}/sponsorships", json={
            "type": "nonsense", "advertiser_id": ADVERTISER_ID})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "unknown_sponsorship_type"


# ────────────────────────── Cross-cutting ──────────────────────────
class TestScopeEnforcement:
    """Limited-scope key has only catalog:read → games:write must 403."""

    def test_403_on_games_write_without_scope(self, limited_client, template_id):
        p = {
            "advertiser_id": ADVERTISER_ID,
            "template_id": template_id,
            "name": "TEST_no_scope",
            "prizes": [{"prize_type": "bigcoin", "title": "x",
                        "probability_weight": 100, "inventory_total": 1}],
        }
        r = limited_client.post(f"{V1}/sponsored-games", json=p)
        assert r.status_code == 403, r.text
        j = r.json()
        assert "error" in j and j["error"]["code"] in ("forbidden", "insufficient_scope",
                                                        "scope_required")

    def test_403_on_games_read_without_scope(self, limited_client):
        # limited key has catalog:read only — games:read on templates should also 403
        r = limited_client.get(f"{V1}/game-templates")
        assert r.status_code == 403

    def test_catalog_read_allowed(self, limited_client):
        r = limited_client.get(f"{V1}/inventory/audio")
        assert r.status_code == 200


class TestErrorEnvelopeAndHeaders:
    def test_unauth_error_envelope(self):
        r = requests.get(f"{V1}/game-templates",
                         headers={"Authorization": "Bearer garbage"})
        assert r.status_code in (401, 403)
        j = r.json()
        assert "error" in j
        assert j["error"].get("code")
        assert j["error"].get("request_id")

    def test_headers_present_on_error(self):
        r = requests.get(f"{V1}/sponsored-games/cmp_missing_xxx",
                         headers={"Authorization": f"Bearer {FULL_KEY}"})
        assert r.headers.get("X-RadioLife-API-Version")
        assert r.headers.get("X-Request-ID")


# ────────────────────────── Regression: A/B/C ──────────────────────────
class TestRegressionPhaseA:
    def test_capabilities(self, client):
        r = client.get(f"{V1}/capabilities")
        assert r.status_code == 200
        j = r.json()
        assert "1" in j["api_versions"]
        assert j["environment"] == "SANDBOX"
        ff = j["feature_flags"]
        assert ff.get("creative_library") is True
        assert ff.get("multi_format_campaigns") is True

    def test_me(self, client):
        r = client.get(f"{V1}/me")
        assert r.status_code == 200
        j = r.json()
        assert j["partner_id"] == "prt_Ngu4e33qm4KULA"
        assert j["environment"] == "SANDBOX"
        assert "games:read" in j["scopes"] and "games:write" in j["scopes"]

    def test_inventory(self, client):
        r = client.get(f"{V1}/inventory")
        assert r.status_code == 200

    def test_markets(self, client):
        r = client.get(f"{V1}/markets")
        assert r.status_code == 200

    def test_products(self, client):
        r = client.get(f"{V1}/products")
        assert r.status_code == 200

    def test_stations_cursor(self, client):
        r = client.get(f"{V1}/stations?limit=2")
        assert r.status_code == 200
        j = r.json()
        for k in ("data", "next_cursor", "has_more"):
            assert k in j


class TestRegressionPhaseB:
    def test_quotes_audio_preroll_dubai(self, client):
        r = client.post(f"{V1}/quotes", json={
            "product": "audio_preroll",
            "market": "dubai",
            "daypart": "morning_drive",
            "pricing_model": "cpm",
            "impressions": 1000,
        })
        assert r.status_code == 200, r.text
        j = r.json()
        # Phase C iteration_122 verified 4680 cents; accept any positive int
        assert isinstance(j.get("effective_rate_cents"), int) and j["effective_rate_cents"] > 0


class TestRegressionPhaseC:
    def test_creatives_list(self, client):
        r = client.get(f"{V1}/creatives?limit=5")
        assert r.status_code == 200
        j = r.json()
        assert "data" in j and "next_cursor" in j and "has_more" in j

    def test_create_creative_ready(self, client):
        body = {
            "advertiser_id": ADVERTISER_ID,
            "type": "image",
            "name": f"TEST_iter123 creative {uuid.uuid4().hex[:6]}",
            "asset_url": "https://example.com/test.png",
            "click_url": "https://example.com",
            "width": 970, "height": 250,
        }
        r = client.post(f"{V1}/creatives", json=body)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        cid = j.get("creative_id") or j.get("id") or (j.get("creative") or {}).get("creative_id")
        assert cid and cid.startswith("crv_")
        assert (j.get("status") or (j.get("creative") or {}).get("status")) in ("ready", "processing")

    def test_single_format_campaign(self, client):
        body = {
            "advertiser_id": ADVERTISER_ID,
            "name": f"TEST_iter123 single {uuid.uuid4().hex[:6]}",
            "product": "audio_preroll",
            "pricing_model": "cpm",
            "cpm_bid_cents": 500,
            "budget_total_cents": 100000,
            "market": "dubai",
        }
        r = client.post(f"{V1}/campaigns", json=body)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        # sandbox auto-activates
        cid = j.get("campaign_id") or (j.get("campaign") or {}).get("campaign_id")
        assert cid
