"""Phase E — Partner API v1 tests: Merchant API, reward-events, conversions,
bulk sync + async jobs, analytics, billing. Also regression smoke over A-D.
Executed against the external URL (REACT_APP_BACKEND_URL) — hits the shared
FastAPI backend under /api/v1.
"""
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv('/app/frontend/.env')
BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/') + '/api/v1'

FULL_KEY = "rlk_test_JZCouNTn_wIP.K8cogkN_HqVTpUTl13byPq7UGzAh_yoi4I3P3K_BHrk"
# Limited key: catalog:read, jobs:write, jobs:read, rewards:read (NO rewards:write, NO conversions:write, NO merchant:*)
LIMITED_KEY = "rlk_test_C0oLiFJD7Kq_.htYkEjph6Tgp9dXiSZET5CeapR2HI14Gr-Iw-nZa80c"

H_FULL = {"Authorization": f"Bearer {FULL_KEY}", "Content-Type": "application/json"}
H_LIMIT = {"Authorization": f"Bearer {LIMITED_KEY}", "Content-Type": "application/json"}

TAG = f"TEST_iter124_{uuid.uuid4().hex[:8]}"


def _hdr_ok(r):
    """Every response — success AND error — must stamp X-RadioLife-API-Version:1 + X-Request-ID."""
    assert r.headers.get("X-RadioLife-API-Version") == "1", r.headers
    assert r.headers.get("X-Request-ID"), r.headers


def _err_ok(r, code=None):
    """Normalized error envelope: {error:{code,message,field,request_id}}"""
    _hdr_ok(r)
    body = r.json()
    assert "error" in body, body
    e = body["error"]
    for k in ("code", "message", "request_id"):
        assert k in e, f"missing {k} in error envelope: {e}"
    if code:
        assert e["code"] == code, f"expected code={code}, got {e['code']}"


# ═════════════════ Capabilities / feature flags ═════════════════════
class TestCapabilities:
    def test_capabilities_phase_e_flags(self):
        r = requests.get(f"{BASE}/capabilities", headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text
        _hdr_ok(r)
        j = r.json()
        ff = j.get("feature_flags") or j
        # Recurse — feature_flags may be nested
        flags_str = str(j)
        for flag in ("merchant_api", "reward_events", "conversions", "bulk_jobs", "analytics", "billing"):
            assert flag in flags_str, f"feature flag {flag} not found in capabilities"

    def test_me_has_phase_e_scopes(self):
        r = requests.get(f"{BASE}/me", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        scopes = set(r.json()["scopes"])
        for s in ("rewards:write", "rewards:read", "conversions:write", "conversions:read",
                  "jobs:write", "jobs:read", "merchant:write", "merchant:read",
                  "analytics:read", "billing:read"):
            assert s in scopes, f"missing scope {s} on full key"


# ═════════════════════════ Merchant API ═════════════════════════════
class TestMerchant:
    merchant_id = None
    offer_id = None
    ext_mid = f"{TAG}_mext"
    ext_oid = f"{TAG}_oext"

    def test_1_create_merchant(self):
        payload = {"name": f"{TAG} Coffee", "category": "food",
                   "contact_email": "shop@test.dev", "external_id": self.ext_mid}
        r = requests.post(f"{BASE}/merchant/businesses", json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 201, r.text
        _hdr_ok(r)
        m = r.json()["merchant"]
        assert m["merchant_id"].startswith("mrc_")
        assert m["name"] == payload["name"]
        assert m["external_id"] == self.ext_mid
        TestMerchant.merchant_id = m["merchant_id"]

    def test_2_external_id_dedup(self):
        """re-send same external_id -> SAME merchant, no duplicate."""
        payload = {"name": f"{TAG} Coffee DIFFERENT NAME", "external_id": self.ext_mid}
        r = requests.post(f"{BASE}/merchant/businesses", json=payload, headers=H_FULL, timeout=20)
        assert r.status_code in (200, 201), r.text
        m = r.json()["merchant"]
        assert m["merchant_id"] == self.merchant_id, "external_id dedup broke"

    def test_3_idempotency_key_replay(self):
        idem = f"{TAG}-idem-merchant"
        payload = {"name": f"{TAG} Idem", "external_id": f"{TAG}_idem_ext"}
        h = {**H_FULL, "Idempotency-Key": idem}
        r1 = requests.post(f"{BASE}/merchant/businesses", json=payload, headers=h, timeout=20)
        assert r1.status_code == 201
        m1 = r1.json()["merchant"]["merchant_id"]
        # Second call with same idem — replay original
        r2 = requests.post(f"{BASE}/merchant/businesses", json={"name": "changed"}, headers=h, timeout=20)
        assert r2.status_code in (200, 201)
        assert r2.json()["merchant"]["merchant_id"] == m1

    def test_4_get_merchant(self):
        r = requests.get(f"{BASE}/merchant/businesses/{self.merchant_id}", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        assert r.json()["merchant"]["merchant_id"] == self.merchant_id

    def test_5_get_merchant_404(self):
        r = requests.get(f"{BASE}/merchant/businesses/mrc_doesnotexist_zzz", headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _err_ok(r, "merchant_not_found")

    def test_6_list_merchants_cursor(self):
        r = requests.get(f"{BASE}/merchant/businesses?limit=5", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        for k in ("data", "count", "next_cursor", "has_more"):
            assert k in j

    def test_7_list_merchants_external_id_filter(self):
        r = requests.get(f"{BASE}/merchant/businesses?external_id={self.ext_mid}",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 200
        data = r.json()["data"]
        assert any(m["merchant_id"] == self.merchant_id for m in data)

    def test_8_patch_merchant(self):
        r = requests.patch(f"{BASE}/merchant/businesses/{self.merchant_id}",
                           json={"description": "updated by test"}, headers=H_FULL, timeout=20)
        assert r.status_code == 200
        assert r.json()["merchant"]["description"] == "updated by test"

    def test_9_create_offer(self):
        payload = {"title": f"{TAG} 10% off", "offer_type": "percent",
                   "value": 10, "external_id": self.ext_oid}
        r = requests.post(f"{BASE}/merchant/businesses/{self.merchant_id}/offers",
                          json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 201, r.text
        o = r.json()["offer"]
        assert o["offer_id"].startswith("off_")
        assert o["offer_type"] == "percent"
        TestMerchant.offer_id = o["offer_id"]

    def test_10_create_offer_invalid_type_400(self):
        payload = {"title": "bad", "offer_type": "not_a_type"}
        r = requests.post(f"{BASE}/merchant/businesses/{self.merchant_id}/offers",
                          json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 400, r.text
        _err_ok(r, "invalid_offer_type")

    def test_11_create_offer_external_dedup(self):
        payload = {"title": "different title", "offer_type": "amount",
                   "value": 5, "external_id": self.ext_oid}
        r = requests.post(f"{BASE}/merchant/businesses/{self.merchant_id}/offers",
                          json=payload, headers=H_FULL, timeout=20)
        assert r.status_code in (200, 201)
        assert r.json()["offer"]["offer_id"] == self.offer_id

    def test_12_create_offer_unknown_merchant_404(self):
        r = requests.post(f"{BASE}/merchant/businesses/mrc_nope_zzz/offers",
                          json={"title": "x"}, headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _err_ok(r, "merchant_not_found")

    def test_13_list_offers(self):
        r = requests.get(f"{BASE}/merchant/businesses/{self.merchant_id}/offers",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert any(o["offer_id"] == self.offer_id for o in j["data"])

    def test_14_patch_offer(self):
        r = requests.patch(f"{BASE}/merchant/offers/{self.offer_id}",
                           json={"description": "updated offer"}, headers=H_FULL, timeout=20)
        assert r.status_code == 200
        assert r.json()["offer"]["description"] == "updated offer"

    def test_15_patch_offer_unknown_404(self):
        r = requests.patch(f"{BASE}/merchant/offers/off_nope_zzz",
                           json={"description": "x"}, headers=H_FULL, timeout=20)
        assert r.status_code == 404


# ═════════════════════════ Reward Events ════════════════════════════
class TestRewardEvents:
    event_id = None
    ext_evid = f"{TAG}_rev_ext"

    def test_1_create(self):
        payload = {"type": "purchase", "value_cents": 500, "points": 10,
                   "external_id": self.ext_evid, "user_ref": "u_test"}
        r = requests.post(f"{BASE}/reward-events", json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["created"] is True
        ev = j["reward_event"]
        assert ev["event_id"].startswith("rev_")
        assert ev["type"] == "purchase"
        assert ev["status"] == "recorded"
        assert ev["credited"] is False, "must NOT credit — safe ingest only"
        TestRewardEvents.event_id = ev["event_id"]

    def test_2_invalid_type_400(self):
        r = requests.post(f"{BASE}/reward-events",
                          json={"type": "not_a_type"}, headers=H_FULL, timeout=20)
        assert r.status_code == 400
        _err_ok(r, "invalid_reward_event_type")

    def test_3_external_id_dedup_preserves_id(self):
        r = requests.post(f"{BASE}/reward-events",
                          json={"type": "signup", "external_id": self.ext_evid},
                          headers=H_FULL, timeout=20)
        assert r.status_code in (200, 201)
        j = r.json()
        assert j["created"] is False, "second external_id must return created=false"
        assert j["reward_event"]["event_id"] == self.event_id

    def test_4_idempotency_key_replays_created(self):
        idem = f"{TAG}-rev-idem"
        ext = f"{TAG}_rev_idem_ext"
        h = {**H_FULL, "Idempotency-Key": idem}
        r1 = requests.post(f"{BASE}/reward-events",
                           json={"type": "purchase", "external_id": ext},
                           headers=h, timeout=20)
        assert r1.status_code == 201
        assert r1.json()["created"] is True
        eid1 = r1.json()["reward_event"]["event_id"]
        # Replay — must return SAME response including created=true
        r2 = requests.post(f"{BASE}/reward-events",
                           json={"type": "signup"}, headers=h, timeout=20)
        assert r2.json()["reward_event"]["event_id"] == eid1
        assert r2.json()["created"] is True, "idem replay must preserve original created flag"

    def test_5_value_cap(self):
        r = requests.post(f"{BASE}/reward-events",
                          json={"type": "purchase", "value_cents": 9_999_999_999,
                                "external_id": f"{TAG}_capped"},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 201
        assert r.json()["reward_event"]["value_cents"] <= 1_000_000

    def test_6_get_and_404(self):
        r = requests.get(f"{BASE}/reward-events/{self.event_id}", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        r2 = requests.get(f"{BASE}/reward-events/rev_nope_zzz", headers=H_FULL, timeout=20)
        assert r2.status_code == 404
        _err_ok(r2, "reward_event_not_found")

    def test_7_list_cursor_and_filters(self):
        r = requests.get(f"{BASE}/reward-events?limit=5&type=purchase", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert set(j.keys()) >= {"data", "count", "next_cursor", "has_more"}
        for ev in j["data"]:
            assert ev["type"] == "purchase"


# ═════════════════════════ Conversions ══════════════════════════════
class TestConversions:
    conversion_id = None
    ext_cid = f"{TAG}_cnv_ext"

    def test_1_create(self):
        payload = {"conversion_type": "purchase", "value_cents": 1500,
                   "external_id": self.ext_cid, "campaign_id": "cmp_test"}
        r = requests.post(f"{BASE}/conversions", json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["created"] is True
        cv = j["conversion"]
        assert cv["conversion_id"].startswith("cnv_")
        assert cv["conversion_type"] == "purchase"
        TestConversions.conversion_id = cv["conversion_id"]

    def test_2_invalid_type_400(self):
        r = requests.post(f"{BASE}/conversions",
                          json={"conversion_type": "nope"}, headers=H_FULL, timeout=20)
        assert r.status_code == 400
        _err_ok(r, "invalid_conversion_type")

    def test_3_external_id_dedup(self):
        r = requests.post(f"{BASE}/conversions",
                          json={"conversion_type": "signup", "external_id": self.ext_cid},
                          headers=H_FULL, timeout=20)
        assert r.status_code in (200, 201)
        assert r.json()["created"] is False
        assert r.json()["conversion"]["conversion_id"] == self.conversion_id

    def test_4_idempotency_replay(self):
        idem = f"{TAG}-cnv-idem"
        h = {**H_FULL, "Idempotency-Key": idem}
        r1 = requests.post(f"{BASE}/conversions",
                           json={"conversion_type": "install",
                                 "external_id": f"{TAG}_cnv_idem"},
                           headers=h, timeout=20)
        assert r1.status_code == 201
        cid1 = r1.json()["conversion"]["conversion_id"]
        r2 = requests.post(f"{BASE}/conversions",
                           json={"conversion_type": "lead"}, headers=h, timeout=20)
        assert r2.json()["conversion"]["conversion_id"] == cid1

    def test_5_get_and_404(self):
        r = requests.get(f"{BASE}/conversions/{self.conversion_id}", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        r2 = requests.get(f"{BASE}/conversions/cnv_nope_zzz", headers=H_FULL, timeout=20)
        assert r2.status_code == 404

    def test_6_list_cursor(self):
        r = requests.get(f"{BASE}/conversions?limit=5", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        assert set(r.json().keys()) >= {"data", "count", "next_cursor", "has_more"}


# ═════════════════════════ Bulk / Jobs ══════════════════════════════
class TestBulkJobs:
    job_id = None

    def test_1_invalid_operation_400(self):
        r = requests.post(f"{BASE}/bulk/not_an_op", json={"items": [{}]},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 400
        _err_ok(r, "invalid_bulk_operation")

    def test_2_bulk_conversions_full_scope(self):
        ext_base = f"{TAG}_bulk_cnv"
        items = [
            {"conversion_type": "purchase", "value_cents": 100, "external_id": f"{ext_base}_a"},
            {"conversion_type": "purchase", "value_cents": 200, "external_id": f"{ext_base}_a"},  # dup
            {"conversion_type": "signup", "external_id": f"{ext_base}_b"},
            {"conversion_type": "not_valid", "external_id": f"{ext_base}_c"},  # error
        ]
        r = requests.post(f"{BASE}/bulk/conversions", json={"items": items},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 202, r.text
        j = r.json()["job"]
        assert j["status"] == "queued"
        assert j["total"] == 4
        TestBulkJobs.job_id = j["job_id"]

    def test_3_poll_job_completion(self):
        assert self.job_id
        deadline = time.time() + 20
        job = None
        while time.time() < deadline:
            r = requests.get(f"{BASE}/jobs/{self.job_id}", headers=H_FULL, timeout=20)
            assert r.status_code == 200
            job = r.json()["job"]
            if job["status"] == "completed":
                break
            time.sleep(0.5)
        assert job and job["status"] == "completed", f"job did not complete: {job}"
        # results per-item
        results = job["results"]
        assert len(results) == 4
        statuses = [x["status"] for x in results]
        assert statuses.count("ok") == 2, f"expected 2 ok, got {statuses}"
        assert statuses.count("duplicate") == 1, f"expected 1 duplicate, got {statuses}"
        assert statuses.count("error") == 1, f"expected 1 error, got {statuses}"
        # every ok/duplicate has id, error has error
        for res in results:
            if res["status"] in ("ok", "duplicate"):
                assert res.get("id"), res
            if res["status"] == "error":
                assert res.get("error"), res

    def test_4_bulk_offers_requires_merchant_id(self):
        items = [{"title": "no merchant"}]
        r = requests.post(f"{BASE}/bulk/offers", json={"items": items},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 202
        jid = r.json()["job"]["job_id"]
        deadline = time.time() + 15
        while time.time() < deadline:
            j = requests.get(f"{BASE}/jobs/{jid}", headers=H_FULL, timeout=20).json()["job"]
            if j["status"] == "completed":
                break
            time.sleep(0.5)
        assert j["status"] == "completed"
        assert j["results"][0]["status"] == "error"
        assert "merchant_id" in j["results"][0]["error"].lower()

    def test_5_list_jobs_cursor(self):
        r = requests.get(f"{BASE}/jobs?limit=5", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        assert set(r.json().keys()) >= {"data", "count", "next_cursor", "has_more"}

    def test_6_job_404(self):
        r = requests.get(f"{BASE}/jobs/job_nope_zzz", headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _err_ok(r, "job_not_found")

    def test_7_scope_enforcement_bulk_conversions_403(self):
        """Limited key has jobs:write but NOT conversions:write -> 403."""
        items = [{"conversion_type": "purchase", "external_id": f"{TAG}_scope_check"}]
        r = requests.post(f"{BASE}/bulk/conversions", json={"items": items},
                          headers=H_LIMIT, timeout=20)
        assert r.status_code == 403, r.text
        _err_ok(r, "insufficient_scope")
        body = r.json()
        assert "conversions:write" in body["error"].get("missing", []) or \
               "conversions:write" in str(body)


# ══════════════════════ Scope enforcement (extra) ═══════════════════
class TestScopeEnforcement:
    def test_reward_events_write_403(self):
        r = requests.post(f"{BASE}/reward-events",
                          json={"type": "purchase"}, headers=H_LIMIT, timeout=20)
        assert r.status_code == 403
        _err_ok(r, "insufficient_scope")

    def test_merchant_write_403(self):
        r = requests.post(f"{BASE}/merchant/businesses",
                          json={"name": "x"}, headers=H_LIMIT, timeout=20)
        assert r.status_code == 403


# ═════════════════════════ Analytics ════════════════════════════════
class TestAnalytics:
    def test_summary(self):
        r = requests.get(f"{BASE}/analytics/summary?days=30", headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("campaigns", "spend_cents", "impressions", "clicks", "ctr",
                  "conversions", "conversion_value_cents", "reward_events",
                  "reward_points", "merchants", "offers", "cvr"):
            assert k in j, f"missing analytics field: {k}"
        # We just created conversions + rewards + merchants — counts should be >0
        assert j["merchants"] >= 1
        assert j["conversions"] >= 1
        assert j["reward_events"] >= 1

    def test_timeseries(self):
        r = requests.get(f"{BASE}/analytics/timeseries?metric=conversions&days=7",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "series" in j and "total" in j
        assert isinstance(j["series"], list)

    def test_timeseries_invalid_metric_400(self):
        r = requests.get(f"{BASE}/analytics/timeseries?metric=not_a_metric",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 400
        _err_ok(r, "invalid_metric")


# ═════════════════════════ Billing ══════════════════════════════════
class TestBilling:
    def test_summary(self):
        r = requests.get(f"{BASE}/billing/summary", headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("balance_cents", "lifetime_spend_cents", "period_conversion_value_cents",
                  "advertisers", "invoices", "currency", "current_period"):
            assert k in j, f"billing summary missing {k}"
        assert j["currency"] == "usd"

    def test_invoices_list(self):
        r = requests.get(f"{BASE}/billing/invoices?limit=20", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert set(j.keys()) >= {"data", "count", "next_cursor", "has_more"}
        # Should include current month as 'open' if any lifetime activity for partner
        for inv in j["data"]:
            assert inv["currency"] == "usd"
            assert inv["status"] in ("open", "final")
            assert "line_items" in inv

    def test_invoice_detail_404(self):
        r = requests.get(f"{BASE}/billing/invoices/inv_nope_zzz",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _err_ok(r, "invoice_not_found")

    def test_invoice_detail_ok(self):
        r = requests.get(f"{BASE}/billing/invoices?limit=1", headers=H_FULL, timeout=20)
        data = r.json()["data"]
        if not data:
            pytest.skip("no invoices for this partner yet")
        iid = data[0]["invoice_id"]
        r2 = requests.get(f"{BASE}/billing/invoices/{iid}", headers=H_FULL, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["invoice"]["invoice_id"] == iid


# ═════════════════════════ Regression A-D ═══════════════════════════
class TestRegression:
    """Smoke coverage across earlier phases to ensure Phase E didn't break anything."""

    def test_phase_a_discovery(self):
        for path in ("/capabilities", "/markets", "/stations", "/targeting/options",
                     "/rate-card", "/status", "/me", "/products", "/inventory"):
            r = requests.get(f"{BASE}{path}", headers=H_FULL, timeout=20)
            assert r.status_code == 200, f"{path} -> {r.status_code}"
            _hdr_ok(r)

    def test_phase_b_quote(self):
        r = requests.post(f"{BASE}/quotes",
                          json={"product": "audio_preroll", "format": "audio_preroll",
                                "market_id": "dubai", "daypart": "morning_drive",
                                "goal": "cpm", "budget_cents": 100_000},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text

    def test_phase_c_creatives_list(self):
        r = requests.get(f"{BASE}/creatives?limit=5", headers=H_FULL, timeout=20)
        assert r.status_code == 200

    def test_phase_d_game_templates(self):
        r = requests.get(f"{BASE}/game-templates", headers=H_FULL, timeout=20)
        assert r.status_code == 200

    def test_phase_d_predictions_eligible(self):
        r = requests.get(f"{BASE}/predictions/eligible", headers=H_FULL, timeout=20)
        assert r.status_code == 200

    def test_phase_d_inventory_display_audio(self):
        for kind in ("display", "audio"):
            r = requests.get(f"{BASE}/inventory/{kind}", headers=H_FULL, timeout=20)
            assert r.status_code == 200, f"{kind} -> {r.status_code}"
