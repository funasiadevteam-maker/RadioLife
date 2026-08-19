"""Iteration 94 — RadioLife Ads Public API Phase 2 end-to-end tests.

Covers:
  * Sponsorships (unified /api/v1/sponsorships): inventory, create (trivia),
    list, get, report, submit — using the SmartReach sandbox key.
  * Usage analytics: GET /api/v1/usage returns the full shape.
  * Webhooks: register, list, ping, deliveries, delete, event catalog.
  * Scope guardrails: reports:read gates /usage, campaigns:write gates
    POST /webhooks; cross-partner sponsorship access -> 404.
  * Phase-1 regression: /me, /products (9 items / 3 bookable).
"""
import os
import time
import uuid
import threading
import http.server
import socketserver
import json
import hmac
import hashlib

import requests
import pytest


def _read_env(path, key):
    try:
        for line in open(path):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
            or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

SMARTREACH_SANDBOX = (
    "rlk_test_MTkClmovYPc_.cdkjGLsT9SveRl543RCiI_FCFqyPRlAi-So2QPrL2jE"
)

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")


# ── helpers ────────────────────────────────────────────────────────
def login(session: requests.Session, email: str, password: str) -> str:
    r = session.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token")
    assert tok
    session.headers["Authorization"] = f"Bearer {tok}"
    return tok


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    login(s, *ADMIN)
    return s


@pytest.fixture(scope="module")
def v1():
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {SMARTREACH_SANDBOX}"
    return s


@pytest.fixture(scope="module")
def sandbox_advertiser(v1):
    """Reuse a sandbox advertiser (auto-active) and top it up."""
    r = v1.post(f"{BASE_URL}/api/v1/advertisers",
                json={"name": f"TEST_iter94_{uuid.uuid4().hex[:6]}",
                      "contact_email": "iter94@example.com"}, timeout=20)
    assert r.status_code == 201, r.text
    aid = r.json()["advertiser"]["advertiser_id"]
    r = v1.post(f"{BASE_URL}/api/v1/advertisers/{aid}/funding/topup",
                json={"amount_cents": 50000}, timeout=20)
    assert r.status_code == 200, r.text
    return aid


# ── Phase-1 regression ────────────────────────────────────────────
class TestPhase1Regression:
    def test_me(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/me", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["environment"] == "SANDBOX"
        assert j["credential_type"] == "api_key"
        # SmartReach must have both reports:read and campaigns:write for phase 2
        assert "reports:read" in j["scopes"]
        assert "campaigns:write" in j["scopes"]

    def test_products_9_and_3_bookable(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/products", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["items"]) == 9, f"expected 9 products, got {len(j['items'])}"
        bookable = sorted(p["key"] for p in j["items"] if p.get("bookable"))
        assert bookable == ["audio_preroll", "display_banner", "sponsored_game"]


# ── Sponsorships ───────────────────────────────────────────────────
class TestSponsorships:
    _trivia_id = None

    def test_inventory_trivia(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/inventory",
                   params={"type": "trivia"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "target_types" in j
        assert "any" in j["target_types"]
        assert isinstance(j.get("categories"), list) and len(j["categories"]) > 0

    def test_inventory_rj_read(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/inventory",
                   params={"type": "rj_read"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "personas" in j
        assert "disclosure_prefixes" in j

    def test_inventory_predict_win(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/inventory",
                   params={"type": "predict_win"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j

    def test_create_trivia_sponsorship_autoactive(self, v1, sandbox_advertiser):
        payload = {
            "type": "trivia",
            "advertiser_id": sandbox_advertiser,
            "display_name": f"TEST_trivia_{uuid.uuid4().hex[:6]}",
            "sponsor_target_type": "any",
            "prize_pool": [{"rank": 1, "points_reward": 500,
                            "quantity": 1, "currency": "bc"}],
            "winner_selection": "top_n",
            "start_at": "2026-06-01T00:00:00Z",
            "end_at": "2026-12-31T23:59:59Z",
        }
        r = v1.post(f"{BASE_URL}/api/v1/sponsorships", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        # Response may be wrapped under 'sponsorship' or flat
        obj = j.get("sponsorship", j)
        sid = obj.get("id") or obj.get("sponsorship_id")
        assert sid, f"no id in create response: {j}"
        status = obj.get("status", "").lower()
        assert status in ("active", "approved"), f"expected active in sandbox, got {status}"
        TestSponsorships._trivia_id = sid

    def test_list_sponsorships_trivia(self, v1, sandbox_advertiser):
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships",
                   params={"type": "trivia", "advertiser_id": sandbox_advertiser},
                   timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j
        ids = [it.get("id") or it.get("sponsorship_id") for it in j["items"]]
        assert TestSponsorships._trivia_id in ids

    def test_get_sponsorship(self, v1, sandbox_advertiser):
        sid = TestSponsorships._trivia_id
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/{sid}",
                   params={"type": "trivia", "advertiser_id": sandbox_advertiser},
                   timeout=15)
        assert r.status_code == 200, r.text

    def test_report_sponsorship(self, v1, sandbox_advertiser):
        sid = TestSponsorships._trivia_id
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/{sid}/report",
                   params={"type": "trivia",
                           "advertiser_id": sandbox_advertiser},
                   timeout=15)
        assert r.status_code == 200, r.text

    def test_submit_sponsorship_sandbox_active(self, v1, sandbox_advertiser):
        sid = TestSponsorships._trivia_id
        r = v1.post(f"{BASE_URL}/api/v1/sponsorships/{sid}/submit",
                    params={"type": "trivia",
                            "advertiser_id": sandbox_advertiser},
                    timeout=15)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        obj = j.get("sponsorship", j)
        status = (obj.get("status") or "").lower()
        assert status in ("active", "approved"), f"got {status}"

    def test_cross_partner_sponsorship_404(self, admin_sess, v1):
        # Create a second partner + key + advertiser + trivia sponsorship,
        # then attempt to read/report with the SmartReach key.
        r = admin_sess.post(
            f"{BASE_URL}/api/admin/partner-api/partners",
            json={"name": f"TEST_p2_{uuid.uuid4().hex[:6]}",
                  "contact_email": "p2@x.com"}, timeout=20)
        assert r.status_code == 200
        pid2 = r.json()["partner"]["partner_id"]
        r = admin_sess.post(
            f"{BASE_URL}/api/admin/partner-api/partners/{pid2}/keys",
            json={"environment": "sandbox"}, timeout=20)
        k2 = r.json()["api_key"]
        s2 = requests.Session()
        s2.headers["Authorization"] = f"Bearer {k2}"
        adv = s2.post(f"{BASE_URL}/api/v1/advertisers",
                      json={"name": "TEST_p2_adv",
                            "contact_email": "a@p2.com"},
                      timeout=20).json()["advertiser"]
        s2.post(f"{BASE_URL}/api/v1/advertisers/{adv['advertiser_id']}/funding/topup",
                json={"amount_cents": 5000}, timeout=20)
        sp = s2.post(f"{BASE_URL}/api/v1/sponsorships",
                     json={"type": "trivia",
                           "advertiser_id": adv["advertiser_id"],
                           "display_name": "TEST_p2_trivia",
                           "sponsor_target_type": "any",
                           "prize_pool": [{"rank": 1, "points_reward": 100,
                                           "quantity": 1, "currency": "bc"}],
                           "winner_selection": "top_n",
                           "start_at": "2026-06-01T00:00:00Z",
                           "end_at": "2026-12-31T23:59:59Z"},
                     timeout=20).json()
        other_obj = sp.get("sponsorship", sp)
        sid = other_obj.get("id") or other_obj.get("sponsorship_id")
        assert sid, f"could not create partner-2 sponsorship: {sp}"
        # SmartReach key should NOT see it
        r = v1.get(f"{BASE_URL}/api/v1/sponsorships/{sid}",
                   params={"type": "trivia",
                           "advertiser_id": adv["advertiser_id"]},
                   timeout=15)
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text}"


# ── Usage analytics ───────────────────────────────────────────────
class TestUsage:
    def test_usage_shape(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/usage", params={"days": 30}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("total_calls", "calls_by_day", "calls_by_endpoint",
                  "calls_by_status", "campaigns", "active_campaigns",
                  "spend_cents", "impressions", "clicks", "ctr"):
            assert k in j, f"usage missing key {k}: {list(j.keys())}"
        assert isinstance(j["total_calls"], int)
        assert isinstance(j["calls_by_day"], dict)
        assert isinstance(j["calls_by_endpoint"], dict)
        assert isinstance(j["ctr"], (int, float))


# ── Local HTTP receiver for webhook delivery ──────────────────────
_RECEIVED = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        _RECEIVED.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": body,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_):
        pass


@pytest.fixture(scope="module")
def receiver():
    _RECEIVED.clear()
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield {"port": port, "url": f"http://127.0.0.1:{port}/hook",
           "received": _RECEIVED}
    httpd.shutdown()


# ── Webhooks ──────────────────────────────────────────────────────
class TestWebhooks:
    _webhook_id = None
    _secret = None

    def test_events_catalog(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/webhooks/events", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert set(j["events"]) >= {
            "campaign.approved", "campaign.live",
            "campaign.budget_exhausted", "campaign.completed",
            "sponsorship.approved",
        }

    def test_register_webhook(self, v1, receiver):
        r = v1.post(f"{BASE_URL}/api/v1/webhooks",
                    json={"url": receiver["url"]}, timeout=15)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        assert "secret" in j, "secret must be returned once on create"
        assert j.get("webhook_id") or j.get("id")
        TestWebhooks._webhook_id = j.get("webhook_id") or j.get("id")
        TestWebhooks._secret = j["secret"]

    def test_list_webhooks(self, v1):
        r = v1.get(f"{BASE_URL}/api/v1/webhooks", timeout=15)
        assert r.status_code == 200
        j = r.json()
        ids = [it.get("webhook_id") or it.get("id") for it in j["items"]]
        assert TestWebhooks._webhook_id in ids
        # 'secret' MUST NOT be included in list responses
        for it in j["items"]:
            assert "secret" not in it, "secret leaked in webhook list!"

    def test_ping_delivered(self, v1, receiver):
        wid = TestWebhooks._webhook_id
        r = v1.post(f"{BASE_URL}/api/v1/webhooks/{wid}/ping", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("delivered") is True, f"ping not delivered: {j}"
        # Give receiver a moment
        time.sleep(0.5)
        assert len(receiver["received"]) >= 1
        # Verify HMAC signature header present
        last = receiver["received"][-1]
        sig = None
        for k, v in last["headers"].items():
            if k.lower() == "x-radiolife-signature":
                sig = v
                break
        assert sig, f"missing X-RadioLife-Signature header: {last['headers']}"
        # Signature format is Stripe-style: t=<ts>,v1=<hex hmac>
        # where hex hmac = HMAC_SHA256(secret, f"{ts}.{body}")
        secret = TestWebhooks._secret
        body = last["body"]
        assert sig.startswith("t="), f"unexpected sig format: {sig}"
        parts = dict(kv.split("=", 1) for kv in sig.split(","))
        ts = parts.get("t")
        v1_sig = parts.get("v1")
        assert ts and v1_sig, f"malformed sig: {sig}"
        signed_payload = f"{ts}.".encode() + body
        computed = hmac.new(secret.encode(), signed_payload,
                            hashlib.sha256).hexdigest()
        assert hmac.compare_digest(computed, v1_sig), (
            f"HMAC mismatch. sig={sig} computed={computed}")

    def test_deliveries_list(self, v1):
        wid = TestWebhooks._webhook_id
        r = v1.get(f"{BASE_URL}/api/v1/webhooks/{wid}/deliveries", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j
        assert len(j["items"]) >= 1

    def test_sweep_delivers_campaign_events(self, v1, sandbox_advertiser, receiver):
        """After creating a sandbox campaign, a subsequent authed call
        should trigger a throttled sweep firing campaign.approved +
        campaign.live to the registered webhook."""
        r = v1.post(f"{BASE_URL}/api/v1/campaigns",
                    json={"advertiser_id": sandbox_advertiser,
                          "product": "audio_preroll",
                          "name": f"TEST_camp_iter94_{uuid.uuid4().hex[:6]}",
                          "budget_total_cents": 5000,
                          "pricing_model": "cpm",
                          "cpm_bid_cents": 500,
                          "creative": {"audio_url": "https://example.com/a.mp3"}},
                    timeout=20)
        assert r.status_code == 201, r.text
        # Sweep is throttled ~10s; wait, then make one extra authed call
        time.sleep(12)
        _ = v1.get(f"{BASE_URL}/api/v1/me", timeout=15)
        # Give delivery worker a couple of seconds
        time.sleep(3)
        wid = TestWebhooks._webhook_id
        r = v1.get(f"{BASE_URL}/api/v1/webhooks/{wid}/deliveries",
                   params={"limit": 50}, timeout=15)
        assert r.status_code == 200
        events_seen = set()
        for d in r.json().get("items", []):
            ev = d.get("event") or d.get("event_type")
            if ev:
                events_seen.add(ev)
        # Must include campaign.approved AND campaign.live
        assert "campaign.approved" in events_seen, \
            f"missing campaign.approved. saw {events_seen}"
        assert "campaign.live" in events_seen, \
            f"missing campaign.live. saw {events_seen}"

    def test_delete_webhook(self, v1):
        wid = TestWebhooks._webhook_id
        r = v1.delete(f"{BASE_URL}/api/v1/webhooks/{wid}", timeout=15)
        assert r.status_code in (200, 204), r.text
        # Verify gone
        r = v1.get(f"{BASE_URL}/api/v1/webhooks", timeout=15)
        ids = [it.get("webhook_id") or it.get("id") for it in r.json()["items"]]
        assert wid not in ids


# ── Scope guardrails ──────────────────────────────────────────────
class TestScopeGuardrails:
    """Create an OAuth client with a NARROW scope and confirm gating."""

    def test_reports_read_gates_usage_and_campaigns_write_gates_webhook(self, admin_sess):
        # Self-serve OAuth client with only catalog:read (no reports:read
        # or campaigns:write).
        r = admin_sess.post(f"{BASE_URL}/api/partner/account",
                            json={"name": f"TEST_scope_{uuid.uuid4().hex[:6]}",
                                  "contact_email": "scope@x.com"},
                            timeout=20)
        assert r.status_code == 200, r.text
        r = admin_sess.post(f"{BASE_URL}/api/partner/oauth-clients",
                            json={"environment": "sandbox",
                                  "scopes": ["catalog:read"],
                                  "label": "iter94-scope"},
                            timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["client_id"]
        secret = r.json()["client_secret"]
        r = requests.post(f"{BASE_URL}/api/v1/oauth/token",
                          data={"grant_type": "client_credentials",
                                "client_id": cid, "client_secret": secret},
                          timeout=15)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        # /usage requires reports:read
        r = requests.get(f"{BASE_URL}/api/v1/usage", headers=h, timeout=15)
        assert r.status_code == 403, f"expected 403 for reports:read, got {r.status_code} {r.text}"
        # POST /webhooks requires campaigns:write
        r = requests.post(f"{BASE_URL}/api/v1/webhooks", headers=h,
                          json={"url": "http://127.0.0.1:1/hook"}, timeout=15)
        assert r.status_code == 403, f"expected 403 for campaigns:write, got {r.status_code} {r.text}"
