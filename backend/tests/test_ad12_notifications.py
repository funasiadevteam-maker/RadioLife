"""Phase AD.12a — In-app notification ads backend tests.

Covers: pricing hints, campaign CRUD validation, creative upload validation,
publish rejection for push channel, inbox mint+dedup, click/open/dismiss,
unread count, digest opt-out semantics + send-now.
"""
from __future__ import annotations
import os
import io

import pytest
import requests

ROOT = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"

DEMO_EMAIL   = "demo@bigfm.dubai"
DEMO_PASS    = "DemoPass123!"
ADMIN_EMAIL  = "admin@bigfm.dubai"
ADMIN_PASS   = "AdminPass123!"
ADVERTISER_ID = "advv2_9fac10b21f5595"


# ─── Auth helpers ────────────────────────────────────────────
def _login(email, pw):
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="module")
def demo_headers():
    tok = _login(DEMO_EMAIL, DEMO_PASS)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_headers():
    tok = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {"Authorization": f"Bearer {tok}"}


# ─── AD.12 pricing hints ─────────────────────────────────────
class TestPricingHints:
    def test_notification_cpd_categories(self):
        r = requests.get(f"{API}/ad-pricing-hints", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["notification_default_cpd_cents"] == 10
        cats = d["notification_cpd_by_category_cents"]
        assert cats["food"] == 8
        assert cats["retail"] == 12
        assert cats["nightlife"] == 15
        assert cats["health"] == 10
        assert cats["services"] == 10
        assert isinstance(d["notification_cpd_groups"], list) and len(d["notification_cpd_groups"]) >= 5


# ─── Campaign CRUD validation ────────────────────────────────
class TestCampaignCreateValidation:
    BASE_PAYLOAD = {
        "title": "TEST_ad12 campaign",
        "body": "A test body long enough",
        "cta_text": "Try now",
        "target_url": "https://example.com/promo",
        "channel": "in_app",
        "budget_cents": 5000,
        "cost_per_delivery_cents": 8,
        "targeting": {"country_codes": ["AE"]},
    }

    def _post(self, headers, payload):
        return requests.post(
            f"{API}/advertiser/{ADVERTISER_ID}/notification-campaigns",
            json=payload, headers=headers, timeout=15)

    def test_missing_title(self, demo_headers):
        p = dict(self.BASE_PAYLOAD); p.pop("title")
        r = self._post(demo_headers, p)
        assert r.status_code == 422 or r.status_code == 400

    def test_missing_body(self, demo_headers):
        p = dict(self.BASE_PAYLOAD); p.pop("body")
        r = self._post(demo_headers, p)
        assert r.status_code in (400, 422)

    def test_missing_target_url(self, demo_headers):
        p = dict(self.BASE_PAYLOAD); p.pop("target_url")
        r = self._post(demo_headers, p)
        assert r.status_code in (400, 422)

    def test_budget_too_small(self, demo_headers):
        p = dict(self.BASE_PAYLOAD); p["budget_cents"] = 50
        r = self._post(demo_headers, p)
        # Pydantic ge=100 → 422, or 400 with code budget_too_small
        assert r.status_code in (400, 422)

    def test_create_draft_success(self, demo_headers):
        r = self._post(demo_headers, self.BASE_PAYLOAD)
        assert r.status_code == 200, r.text[:200]
        doc = r.json()
        assert doc["status"] == "draft"
        assert "notification_campaign_id" in doc
        pytest.ad12_draft_id = doc["notification_campaign_id"]


# ─── Creative upload ──────────────────────────────────────────
def _fake_png(size_bytes: int) -> bytes:
    # Minimal PNG header + payload padding to reach target size
    header = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")
    trailer = bytes.fromhex("0000000049454e44ae426082")
    pad = max(0, size_bytes - len(header) - len(trailer))
    return header + b"\x00" * pad + trailer


class TestCreativeUpload:
    def test_upload_icon_png_ok(self, demo_headers):
        cid = getattr(pytest, "ad12_draft_id", None)
        if not cid: pytest.skip("no draft")
        files = {"file": ("icon.png", _fake_png(2048), "image/png")}
        r = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=icon",
            headers=demo_headers, files=files, timeout=15)
        assert r.status_code == 200, r.text[:200]
        assert r.json()["ok"] is True

    def test_upload_icon_too_large(self, demo_headers):
        cid = getattr(pytest, "ad12_draft_id", None)
        if not cid: pytest.skip("no draft")
        files = {"file": ("big.png", _fake_png(600 * 1024), "image/png")}
        r = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=icon",
            headers=demo_headers, files=files, timeout=15)
        assert r.status_code == 400
        assert "file_too_large" in r.text

    def test_upload_invalid_slot(self, demo_headers):
        cid = getattr(pytest, "ad12_draft_id", None)
        if not cid: pytest.skip("no draft")
        files = {"file": ("x.png", _fake_png(1024), "image/png")}
        r = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=bogus",
            headers=demo_headers, files=files, timeout=15)
        assert r.status_code == 400
        assert "invalid_slot" in r.text

    def test_upload_wrong_content_type(self, demo_headers):
        cid = getattr(pytest, "ad12_draft_id", None)
        if not cid: pytest.skip("no draft")
        files = {"file": ("x.gif", b"GIF89a\x00", "image/gif")}
        r = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=icon",
            headers=demo_headers, files=files, timeout=15)
        assert r.status_code == 400


# ─── Publish rejects push channel ─────────────────────────────
class TestPublishPushRejection:
    def test_publish_push_channel_rejected(self, demo_headers):
        # Create a push-channel draft
        p = {
            "title": "TEST_ad12 push", "body": "This is a push draft body",
            "target_url": "https://example.com/x", "channel": "push",
            "budget_cents": 5000, "cost_per_delivery_cents": 8,
        }
        r = requests.post(
            f"{API}/advertiser/{ADVERTISER_ID}/notification-campaigns",
            json=p, headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
        cid = r.json()["notification_campaign_id"]
        # Upload icon (may be required for publish)
        files = {"file": ("icon.png", _fake_png(1024), "image/png")}
        requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=icon",
            headers=demo_headers, files=files, timeout=15)
        # Publish
        r2 = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/publish",
            headers=demo_headers, timeout=15)
        assert r2.status_code == 400
        assert "push_channel_not_enabled" in r2.text

    def test_publish_both_channel_rejected(self, demo_headers):
        p = {
            "title": "TEST_ad12 both", "body": "Body long enough for both ch",
            "target_url": "https://example.com/y", "channel": "both",
            "budget_cents": 5000, "cost_per_delivery_cents": 8,
        }
        r = requests.post(
            f"{API}/advertiser/{ADVERTISER_ID}/notification-campaigns",
            json=p, headers=demo_headers, timeout=15)
        assert r.status_code == 200, r.text[:200]
        cid = r.json()["notification_campaign_id"]
        files = {"file": ("icon.png", _fake_png(1024), "image/png")}
        requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/creative-upload?slot=icon",
            headers=demo_headers, files=files, timeout=15)
        r2 = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/publish",
            headers=demo_headers, timeout=15)
        assert r2.status_code == 400
        assert "push_channel_not_enabled" in r2.text

    def test_publish_missing_icon(self, demo_headers):
        p = {
            "title": "TEST_ad12 no icon", "body": "Body long enough here yes",
            "target_url": "https://example.com/z", "channel": "in_app",
            "budget_cents": 5000, "cost_per_delivery_cents": 8,
        }
        r = requests.post(
            f"{API}/advertiser/{ADVERTISER_ID}/notification-campaigns",
            json=p, headers=demo_headers, timeout=15)
        cid = r.json()["notification_campaign_id"]
        r2 = requests.post(
            f"{API}/advertiser/notification-campaigns/{cid}/publish",
            headers=demo_headers, timeout=15)
        assert r2.status_code == 400
        assert "icon_required" in r2.text


# ─── Inbox: mint + dedup + click/dismiss ─────────────────────
class TestInboxFlow:
    def test_inbox_returns_items(self, admin_headers):
        r = requests.get(f"{API}/user/notifications/inbox",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # can be list or dict
        items = data if isinstance(data, list) else data.get("items", [])
        pytest.ad12_inbox_items = items
        assert isinstance(items, list)

    def test_inbox_idempotent_second_call(self, admin_headers):
        r1 = requests.get(f"{API}/user/notifications/inbox",
                          headers=admin_headers, timeout=20)
        r2 = requests.get(f"{API}/user/notifications/inbox",
                          headers=admin_headers, timeout=20)
        d1 = r1.json(); d2 = r2.json()
        items1 = d1 if isinstance(d1, list) else d1.get("items", [])
        items2 = d2 if isinstance(d2, list) else d2.get("items", [])
        # Same number of sponsored deliveries
        s1 = [i for i in items1 if i.get("is_sponsored") or i.get("kind") == "sponsored"]
        s2 = [i for i in items2 if i.get("is_sponsored") or i.get("kind") == "sponsored"]
        # IDs should match (idempotent per (user, campaign))
        ids1 = set([i.get("delivery_id") or i.get("id") for i in s1])
        ids2 = set([i.get("delivery_id") or i.get("id") for i in s2])
        # Idempotency: every delivery from call-1 must still be present with SAME id in call-2
        # (No re-minting of existing (user,campaign) pairs). New eligible campaigns in call-2 are OK.
        assert ids1.issubset(ids2), f"lost/re-minted: only in 1st: {ids1 - ids2}"

    def test_unread_count(self, admin_headers):
        r = requests.get(f"{API}/user/notifications/unread_count",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json().get("count"), int)

    def test_click_and_dismiss(self, admin_headers):
        items = getattr(pytest, "ad12_inbox_items", [])
        sponsored = [i for i in items if i.get("is_sponsored") or i.get("kind") == "sponsored"]
        if not sponsored:
            pytest.skip("no sponsored deliveries in inbox")
        did = sponsored[0].get("delivery_id") or sponsored[0].get("id")
        # click
        r = requests.post(f"{API}/user/notifications/{did}/click",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("delivery_id") == did
        assert "target_url" in body
        # open
        r = requests.post(f"{API}/user/notifications/{did}/open",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        # dismiss
        r = requests.post(f"{API}/user/notifications/{did}/dismiss",
                          headers=admin_headers, timeout=10)
        assert r.status_code == 200
        # subsequent inbox must omit
        r2 = requests.get(f"{API}/user/notifications/inbox",
                          headers=admin_headers, timeout=15)
        data = r2.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert not any((i.get("delivery_id") or i.get("id")) == did for i in items)


# ─── Digest opt-out semantics ────────────────────────────────
class TestDigestOptOut:
    def test_default_prefs_on(self, demo_headers):
        # Reset to default by patching to true first
        requests.patch(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            json={"email_weekly_digest": True}, headers=demo_headers, timeout=10)
        r = requests.get(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            headers=demo_headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["email_weekly_digest"] is True

    def test_patch_opt_out_persists(self, demo_headers):
        r = requests.patch(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            json={"email_weekly_digest": False}, headers=demo_headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["email_weekly_digest"] is False
        r2 = requests.get(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            headers=demo_headers, timeout=10)
        assert r2.json()["email_weekly_digest"] is False

    def test_send_digest_now_opted_out(self, admin_headers, demo_headers):
        # ensure opted out
        requests.patch(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            json={"email_weekly_digest": False}, headers=demo_headers, timeout=10)
        r = requests.post(
            f"{API}/admin/advertiser/{ADVERTISER_ID}/send-digest-now?force=false",
            headers=admin_headers, timeout=20)
        assert r.status_code == 200
        b = r.json()
        assert b.get("ok") is False
        assert b.get("reason") == "opted_out"

    def test_send_digest_now_opted_in_returns_payload(self, admin_headers, demo_headers):
        # opt back in
        requests.patch(
            f"{API}/advertiser/{ADVERTISER_ID}/digest/preferences",
            json={"email_weekly_digest": True}, headers=demo_headers, timeout=10)
        r = requests.post(
            f"{API}/admin/advertiser/{ADVERTISER_ID}/send-digest-now?force=false",
            headers=admin_headers, timeout=30)
        assert r.status_code == 200
        b = r.json()
        # accept ok=true OR ok=false with non-opted_out reason (e.g., nothing_to_report)
        if b.get("ok"):
            payload = b.get("payload") or b
            for k in ("advertiser_name", "total_spend_display", "total_impressions",
                      "ctr_percent", "spend_by_type", "top_creatives",
                      "recommendations", "opt_out_url"):
                assert k in payload, f"digest payload missing {k} in {list(payload.keys())}"
        else:
            assert b.get("reason") != "opted_out"


# ─── Regression smoke ───────────────────────────────────────
class TestRegressionSmoke:
    def test_coupon_campaigns_live(self):
        r = requests.get(f"{API}/coupon-campaigns/live", timeout=10)
        assert r.status_code == 200

    def test_ad_review_queue_admin(self, admin_headers):
        r = requests.get(f"{API}/ad-review/queue?limit=5",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200

    def test_banner_serve(self):
        r = requests.get(
            f"{API}/banner/serve?zone=landing_hero&session_id=TEST_smoke_sess",
            timeout=10)
        assert r.status_code == 200

    def test_admin_nav_counts(self, admin_headers):
        r = requests.get(f"{API}/admin/nav-counts",
                         headers=admin_headers, timeout=10)
        assert r.status_code == 200
