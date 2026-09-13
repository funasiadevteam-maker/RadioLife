"""Phase F — Partner API v1 tests: webhooks HMAC+retries hardening,
IP allowlist, per-partner feature-flag overrides, admin partner
management (list/credentials/usage/status/rate-limit/revoke),
security headers, and regression smoke over A-E.

Executed against the external URL (REACT_APP_BACKEND_URL) — hits the
shared FastAPI backend under /api/v1 and cookie-auth admin/portal
endpoints under /api/admin/partner-api and /api/partner.
"""
import asyncio
import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv('/app/frontend/.env')
load_dotenv('/app/backend/.env')

BASE = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
V1 = BASE + "/api/v1"

FULL_KEY = "rlk_test_JZCouNTn_wIP.K8cogkN_HqVTpUTl13byPq7UGzAh_yoi4I3P3K_BHrk"
PARTNER_ID = "prt_Ngu4e33qm4KULA"

H_FULL = {"Authorization": f"Bearer {FULL_KEY}", "Content-Type": "application/json"}

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"
USER_EMAIL = "test@bigfm.dubai"
USER_PW = "TestUser123!"

TAG = f"TEST_iter125_{uuid.uuid4().hex[:8]}"


# ═════════════════════════ helpers ══════════════════════════════════
def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin() -> requests.Session:
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def user() -> requests.Session:
    return _login(USER_EMAIL, USER_PW)


def _sec_hdr_ok(r: requests.Response) -> None:
    for k, v in (("X-Content-Type-Options", "nosniff"),
                 ("Referrer-Policy", "no-referrer"),
                 ("Cache-Control", "no-store")):
        got = r.headers.get(k, "")
        assert v in got, f"security header {k} missing/wrong (got={got!r}) at {r.url}"
    assert r.headers.get("X-RadioLife-API-Version") == "1", r.headers
    assert r.headers.get("X-Request-ID"), r.headers


# ══════════════════════ 1. Security headers ═════════════════════════
class TestSecurityHeaders:
    def test_success_response_has_headers(self):
        r = requests.get(f"{V1}/capabilities", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        _sec_hdr_ok(r)

    def test_error_response_has_headers(self):
        # No auth -> 401 but still stamped
        r = requests.get(f"{V1}/capabilities", timeout=20)
        assert r.status_code in (401, 403)
        _sec_hdr_ok(r)

    def test_404_response_has_headers(self):
        r = requests.get(f"{V1}/reward-events/rev_definitely_missing_zzz",
                         headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _sec_hdr_ok(r)


# ══════════════════════ 2. Webhook event catalog ════════════════════
class TestWebhookEventCatalog:
    def test_expanded_catalog(self):
        r = requests.get(f"{V1}/webhooks/events", headers=H_FULL, timeout=20)
        assert r.status_code == 200
        j = r.json()
        events = j.get("events") or j.get("items") or j
        events_str = str(events)
        for ev in ("sponsored_game.created", "conversion.recorded",
                   "reward_event.recorded", "job.completed",
                   "merchant.created", "offer.created", "ping"):
            assert ev in events_str, f"missing event {ev} in catalog"


# ══════════════════════ 3. Webhook lifecycle + HMAC + retry ═════════
class TestWebhookLifecycle:
    webhook_id = None
    original_secret = None
    delivery_id = None

    def test_1_create_webhook(self):
        payload = {"url": "https://example.com/rl-hook-" + TAG,
                   "events": ["conversion.recorded", "reward_event.recorded",
                              "sponsored_game.created", "ping"]}
        r = requests.post(f"{V1}/webhooks", json=payload, headers=H_FULL, timeout=20)
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["webhook_id"].startswith("whk_")
        assert j["secret"].startswith("whsec_"), "signing secret must be whsec_-prefixed"
        assert set(payload["events"]).issubset(set(j["events"]))
        TestWebhookLifecycle.webhook_id = j["webhook_id"]
        TestWebhookLifecycle.original_secret = j["secret"]

    def test_2_emit_via_conversion_creates_delivery(self):
        # Fire a conversion — should produce a delivery to example.com.
        # example.com returns 405 (POST unsupported) which is EXPECTED; the
        # delivery row must still be recorded with the event payload attached.
        r = requests.post(f"{V1}/conversions",
                          json={"conversion_type": "purchase",
                                "value_cents": 1234,
                                "external_id": f"{TAG}_cnv_emit"},
                          headers=H_FULL, timeout=20)
        assert r.status_code in (200, 201), r.text
        # Delivery is async (retries w/ backoff up to ~1-2s). Poll.
        deadline = time.time() + 20
        items = []
        while time.time() < deadline:
            g = requests.get(f"{V1}/webhooks/{self.webhook_id}/deliveries",
                             headers=H_FULL, timeout=20)
            assert g.status_code == 200
            items = g.json().get("items", [])
            if any(d.get("event_type") == "conversion.recorded" for d in items):
                break
            time.sleep(1.0)
        matching = [d for d in items if d.get("event_type") == "conversion.recorded"]
        assert matching, f"no conversion.recorded delivery recorded in {items}"
        d = matching[0]
        for k in ("delivery_id", "event_type", "ok", "status_code"):
            assert k in d, f"delivery row missing {k}: {d}"
        # example.com returns 405 — ok=False + status_code=405 (or None if net error)
        assert d["ok"] is False
        TestWebhookLifecycle.delivery_id = d["delivery_id"]

    def test_3_retry_delivery(self):
        assert self.delivery_id, "prereq missing"
        r = requests.post(
            f"{V1}/webhooks/{self.webhook_id}/deliveries/{self.delivery_id}/retry",
            headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "delivered" in j
        # example.com still 405 so delivered=false, but call must return 200
        assert j["delivered"] is False

    def test_4_retry_unknown_delivery_404(self):
        r = requests.post(
            f"{V1}/webhooks/{self.webhook_id}/deliveries/whd_definitely_missing/retry",
            headers=H_FULL, timeout=20)
        assert r.status_code == 404
        _sec_hdr_ok(r)

    def test_5_rotate_secret(self):
        r = requests.post(f"{V1}/webhooks/{self.webhook_id}/rotate-secret",
                          headers=H_FULL, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["secret"].startswith("whsec_")
        assert j["secret"] != self.original_secret, "rotate must return a NEW secret"

    def test_6_rotate_unknown_404(self):
        r = requests.post(f"{V1}/webhooks/whk_definitely_missing/rotate-secret",
                          headers=H_FULL, timeout=20)
        assert r.status_code == 404

    def test_7_cleanup_delete_webhook(self):
        r = requests.delete(f"{V1}/webhooks/{self.webhook_id}",
                            headers=H_FULL, timeout=20)
        assert r.status_code == 200


# ══════════════════════ 4. IP allowlist ═════════════════════════════
class TestIpAllowlist:
    throwaway_key = None
    throwaway_key_id = None

    @classmethod
    def setup_class(cls):
        # Mint a throwaway sandbox key + set an ip_allowlist that will NOT
        # match the caller. We do this via services.partner_api directly so
        # the shared full-scope key stays untouched.
        async def _mint():
            from dotenv import load_dotenv as _ld
            _ld('/app/backend/.env')
            from motor.motor_asyncio import AsyncIOMotorClient
            from services import partner_api as pa
            db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
            r = await pa.issue_api_key(db, partner_id=PARTNER_ID,
                                       environment='sandbox', scopes=pa.SCOPES,
                                       label=f"{TAG}_ip_throwaway")
            cls.throwaway_key = r['api_key']
            cls.throwaway_key_id = r['key_id']
            await pa.set_key_ip_allowlist(db, partner_id=PARTNER_ID,
                                          key_id=r['key_id'],
                                          ip_allowlist=['203.0.113.5'])
        asyncio.get_event_loop().run_until_complete(_mint())

    @classmethod
    def teardown_class(cls):
        # Revoke the throwaway key so it can't linger
        async def _revoke():
            from motor.motor_asyncio import AsyncIOMotorClient
            from services import partner_api as pa
            db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
            try:
                await pa.revoke_api_key(db, partner_id=PARTNER_ID,
                                        key_id=cls.throwaway_key_id)
            except Exception:
                pass
        try:
            asyncio.get_event_loop().run_until_complete(_revoke())
        except Exception:
            pass

    def test_1_blocked_when_caller_ip_not_in_allowlist(self):
        assert self.throwaway_key
        h = {"Authorization": f"Bearer {self.throwaway_key}"}
        r = requests.get(f"{V1}/me", headers=h, timeout=20)
        assert r.status_code == 403, r.text
        body = r.json()
        # Envelope: {error:{code:'ip_not_allowed', ...}}
        code = body.get("error", {}).get("code") or body.get("detail", {}).get("code")
        assert code == "ip_not_allowed", body
        _sec_hdr_ok(r)

    def test_2_full_key_no_allowlist_still_works(self):
        # sanity — the shared full-scope key has no ip_allowlist and should keep working
        r = requests.get(f"{V1}/me", headers=H_FULL, timeout=20)
        assert r.status_code == 200


# ══════════════════════ 5. Per-partner feature flags ════════════════
class TestPartnerFlags:
    def test_flags_merge_and_reset(self, admin: requests.Session):
        # 1) set override
        r = admin.post(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/flags",
                       json={"flags": {"audio_preroll": False,
                                       "iter125_probe": True}}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["flags"].get("iter125_probe") is True

        # 2) GET flags via admin
        g = admin.get(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/flags",
                      timeout=20)
        assert g.status_code == 200
        assert g.json()["flags"].get("iter125_probe") is True

        # 3) capabilities must reflect override
        cap = requests.get(f"{V1}/capabilities", headers=H_FULL, timeout=20)
        assert cap.status_code == 200
        j = cap.json()
        ff = j.get("feature_flags") or {}
        over = j.get("feature_flag_overrides") or {}
        assert over.get("iter125_probe") is True or ff.get("iter125_probe") is True, j
        # audio_preroll should now be False (overridden)
        assert (over.get("audio_preroll") is False
                or ff.get("audio_preroll") is False), j

        # 4) RESET (mandatory cleanup)
        rr = admin.post(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/flags",
                        json={"flags": {}}, timeout=20)
        assert rr.status_code == 200
        assert rr.json()["flags"] == {}
        # verify overrides gone
        cap2 = requests.get(f"{V1}/capabilities", headers=H_FULL, timeout=20)
        j2 = cap2.json()
        over2 = j2.get("feature_flag_overrides") or {}
        assert "iter125_probe" not in over2


# ══════════════════════ 6. Admin partner management ═════════════════
class TestAdminPartnerMgmt:
    def test_list_partners(self, admin: requests.Session):
        r = admin.get(f"{BASE}/api/admin/partner-api/partners", timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and "count" in j
        assert any(p["partner_id"] == PARTNER_ID for p in j["items"]), \
            "expected shared test partner in admin list"

    def test_credentials(self, admin: requests.Session):
        r = admin.get(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/credentials",
                      timeout=20)
        assert r.status_code == 200
        j = r.json()
        # returns dict with api_keys / oauth_clients (shape from list_credentials)
        assert "api_keys" in j or "keys" in j or "items" in j, j

    def test_usage(self, admin: requests.Session):
        r = admin.get(
            f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/usage?days=30",
            timeout=20)
        assert r.status_code == 200

    def test_invalid_status_400(self, admin: requests.Session):
        r = admin.post(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/status",
                       json={"status": "banana"}, timeout=20)
        assert r.status_code == 400, r.text

    def test_rate_limit_override(self, admin: requests.Session):
        r = admin.post(
            f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/rate-limit",
            json={"per_minute": 900}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("rate_limit_per_minute") == 900
        # restore a generous default
        admin.post(f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/rate-limit",
                   json={"per_minute": 1000}, timeout=20)

    def test_revoke_unknown_key_404(self, admin: requests.Session):
        r = admin.post(
            f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/keys/key_definitely_missing/revoke",
            timeout=20)
        assert r.status_code == 404


# ══════════════════════ 7. Suspension ═══════════════════════════════
class TestSuspension:
    def test_suspend_then_reactivate(self, admin: requests.Session):
        try:
            # 1) Suspend
            r = admin.post(
                f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/status",
                json={"status": "suspended"}, timeout=20)
            assert r.status_code == 200, r.text

            # Meta is cached ~60s; the enforcement path checks partner_meta lazily.
            # Poll up to ~65s for a 403 partner_suspended.
            deadline = time.time() + 70
            got_403 = False
            code = None
            while time.time() < deadline:
                rr = requests.get(f"{V1}/me", headers=H_FULL, timeout=20)
                if rr.status_code == 403:
                    body = rr.json()
                    code = (body.get("error", {}).get("code")
                            or body.get("detail", {}).get("code"))
                    if code == "partner_suspended":
                        got_403 = True
                        break
                time.sleep(2)
            assert got_403, f"partner_suspended enforcement never triggered (last code={code})"
        finally:
            # MANDATORY: reactivate so shared key keeps working
            admin.post(
                f"{BASE}/api/admin/partner-api/partners/{PARTNER_ID}/status",
                json={"status": "active"}, timeout=20)
            # Clear cache directly to speed reactivation for later tests
            try:
                from services import partner_api as pa  # type: ignore
                pa._partner_limit_cache.pop(PARTNER_ID, None)
            except Exception:
                pass

            # Wait for reactivation to propagate (cache ~60s)
            deadline = time.time() + 70
            while time.time() < deadline:
                rr = requests.get(f"{V1}/me", headers=H_FULL, timeout=20)
                if rr.status_code == 200:
                    break
                time.sleep(2)


# ══════════════════════ 8. Regression A-E smoke ═════════════════════
class TestRegressionAE:
    def test_phase_a_discovery(self):
        for path in ("/capabilities", "/me", "/products", "/inventory",
                     "/markets", "/stations"):
            r = requests.get(f"{V1}{path}", headers=H_FULL, timeout=20)
            assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    def test_phase_b_quote(self):
        r = requests.post(f"{V1}/quotes",
                          json={"product": "audio_preroll", "format": "audio_preroll",
                                "market_id": "dubai", "daypart": "morning_drive",
                                "goal": "cpm", "budget_cents": 100_000},
                          headers=H_FULL, timeout=20)
        assert r.status_code == 200

    def test_phase_c_creatives(self):
        r = requests.get(f"{V1}/creatives?limit=5", headers=H_FULL, timeout=20)
        assert r.status_code == 200

    def test_phase_d_endpoints(self):
        for path in ("/game-templates", "/predictions/eligible",
                     "/inventory/display", "/inventory/audio"):
            r = requests.get(f"{V1}{path}", headers=H_FULL, timeout=20)
            assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_phase_e_endpoints(self):
        for path in ("/reward-events?limit=1", "/conversions?limit=1",
                     "/jobs?limit=1", "/analytics/summary?days=7",
                     "/billing/summary", "/billing/invoices?limit=1"):
            r = requests.get(f"{V1}{path}", headers=H_FULL, timeout=20)
            assert r.status_code == 200, f"{path} -> {r.status_code}"
