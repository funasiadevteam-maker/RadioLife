"""Iter 181 — Banner rotation + advertiser self-serve + performance tests.

Coverage:
  - GET /api/ads/banner/decision rotation (multi-campaigns → distinct picks)
  - Premium user still gets {source:'none', reason:'premium'}
  - Portal slots list (5)
  - Upload-creative validation (bad content-type, >4MB, ownership)
  - Publish modes: instant / review / paid
  - Ownership 403 for foreign merchant_id
  - /portal/banner/mine reports impressions/clicks/ctr
  - Toggle active<->paused
"""
from __future__ import annotations
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PASS = "FreePass123!"
DEMO_EMAIL = "demo@bigfm.dubai"        # premium + owns approved biz
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"

# demo user owns this approved biz per problem statement
DEMO_MERCHANT_ID = "biz_8484f6f985d5"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def free_sess() -> requests.Session:
    return _login(FREE_EMAIL, FREE_PASS)


@pytest.fixture(scope="module")
def demo_sess() -> requests.Session:
    return _login(DEMO_EMAIL, DEMO_PASS)


# ─── Portal (self-serve) ─────────────────────────────────────────────

class TestPortalSlots:
    def test_slots_returns_five(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/ads/portal/banner/slots", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "slots" in data
        keys = {s["slot_key"] for s in data["slots"]}
        expected = {"right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3",
                    "inline_mpu_1", "inline_mpu_2"}
        assert keys == expected, f"got {keys}"
        for s in data["slots"]:
            assert "size" in s and s["size"]


def _tiny_png() -> bytes:
    # 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00"
        b"\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class TestPortalUploadCreative:
    def test_upload_ok(self, demo_sess):
        files = {"file": ("banner.png", _tiny_png(), "image/png")}
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                           data={"merchant_id": DEMO_MERCHANT_ID},
                           files=files, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["creative_image_url"].startswith("/api/static/banners/portal/")

    def test_upload_rejects_bad_content_type(self, demo_sess):
        files = {"file": ("bad.txt", b"hello world", "text/plain")}
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                           data={"merchant_id": DEMO_MERCHANT_ID},
                           files=files, timeout=15)
        assert r.status_code == 400
        assert "unsupported_content_type" in r.text

    def test_upload_rejects_too_large(self, demo_sess):
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)
        files = {"file": ("big.png", big, "image/png")}
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                           data={"merchant_id": DEMO_MERCHANT_ID},
                           files=files, timeout=30)
        assert r.status_code == 400
        assert "file_too_large" in r.text

    def test_upload_foreign_merchant_403(self, demo_sess):
        files = {"file": ("banner.png", _tiny_png(), "image/png")}
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                           data={"merchant_id": "biz_does_not_exist_xyz"},
                           files=files, timeout=15)
        assert r.status_code == 403
        assert "not_your_business" in r.text


class TestPortalPublish:
    def _upload(self, s):
        files = {"file": ("banner.png", _tiny_png(), "image/png")}
        r = s.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                   data={"merchant_id": DEMO_MERCHANT_ID},
                   files=files, timeout=30)
        assert r.status_code == 200
        return r.json()["creative_image_url"]

    def test_publish_instant_goes_active(self, demo_sess):
        creative = self._upload(demo_sess)
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": DEMO_MERCHANT_ID,
                                 "creative_image_url": creative,
                                 "slot_keys": ["right_rail_mpu_1"],
                                 "publish_mode": "instant"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "active"
        assert j["live"] is True
        assert j["campaign_id"].startswith("bcamp_")

    def test_publish_review_goes_pending(self, demo_sess):
        creative = self._upload(demo_sess)
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": DEMO_MERCHANT_ID,
                                 "creative_image_url": creative,
                                 "slot_keys": ["right_rail_mpu_2"],
                                 "publish_mode": "review"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending"
        assert j["live"] is False

    def test_publish_paid_goes_pending_payment(self, demo_sess):
        creative = self._upload(demo_sess)
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": DEMO_MERCHANT_ID,
                                 "creative_image_url": creative,
                                 "slot_keys": ["right_rail_mpu_3"],
                                 "publish_mode": "paid"}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending_payment"
        assert j["live"] is False

    def test_publish_foreign_merchant_403(self, demo_sess):
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": "biz_does_not_exist_xyz",
                                 "creative_image_url": "/api/static/banners/portal/x/y.png",
                                 "slot_keys": ["right_rail_mpu_1"],
                                 "publish_mode": "instant"}, timeout=15)
        assert r.status_code == 403
        assert "not_your_business" in r.text

    def test_publish_requires_slot(self, demo_sess):
        r = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": DEMO_MERCHANT_ID,
                                 "creative_image_url": "/x.png",
                                 "slot_keys": [],
                                 "publish_mode": "instant"}, timeout=15)
        assert r.status_code == 400
        assert "slot_required" in r.text


class TestPortalMineAndToggle:
    def test_mine_lists_campaigns(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/ads/portal/banner/mine",
                          params={"merchant_id": DEMO_MERCHANT_ID}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "count" in j
        assert j["count"] >= 1
        item = j["items"][0]
        assert "impressions" in item and "clicks" in item and "ctr" in item
        assert "campaign_id" in item and "status" in item

    def test_mine_foreign_403(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/ads/portal/banner/mine",
                          params={"merchant_id": "biz_does_not_exist_xyz"},
                          timeout=15)
        assert r.status_code == 403

    def test_toggle_flips_status(self, demo_sess):
        # Create then toggle
        files = {"file": ("banner.png", _tiny_png(), "image/png")}
        up = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                            data={"merchant_id": DEMO_MERCHANT_ID},
                            files=files, timeout=30).json()
        pub = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                             json={"merchant_id": DEMO_MERCHANT_ID,
                                   "creative_image_url": up["creative_image_url"],
                                   "slot_keys": ["right_rail_mpu_1"],
                                   "publish_mode": "instant"}, timeout=15).json()
        cid = pub["campaign_id"]
        r1 = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/{cid}/toggle",
                            timeout=15)
        assert r1.status_code == 200
        assert r1.json()["status"] == "paused"
        r2 = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/{cid}/toggle",
                            timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "active"


# ─── Rotation (banner decision) ──────────────────────────────────────

class TestBannerRotation:
    def test_premium_gets_none(self, demo_sess):
        # demo@ is premium
        r = demo_sess.get(f"{BASE_URL}/api/ads/banner/decision",
                          params={"slot_key": "right_rail_mpu_1",
                                  "page_route": "/"}, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("source") == "none"
        assert j.get("reason") == "premium"

    def test_rotation_free_user_multi_campaigns(self, free_sess, demo_sess):
        """Ensure right_rail_mpu_1 has >=2 active campaigns then verify
        weighted-random rotation returns >1 distinct campaign_id over 10 calls."""
        # Pre-check we already have FPK sample; add 2 more via portal
        for _ in range(2):
            files = {"file": ("b.png", _tiny_png(), "image/png")}
            up = demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/upload-creative",
                                data={"merchant_id": DEMO_MERCHANT_ID},
                                files=files, timeout=30).json()
            demo_sess.post(f"{BASE_URL}/api/ads/portal/banner/publish",
                           json={"merchant_id": DEMO_MERCHANT_ID,
                                 "creative_image_url": up["creative_image_url"],
                                 "slot_keys": ["right_rail_mpu_1"],
                                 "publish_mode": "instant"}, timeout=15)

        seen = set()
        sources = []
        for _ in range(15):
            r = free_sess.get(f"{BASE_URL}/api/ads/banner/decision",
                              params={"slot_key": "right_rail_mpu_1",
                                      "page_route": "/"}, timeout=15)
            assert r.status_code == 200
            j = r.json()
            sources.append(j.get("source"))
            if j.get("source") == "direct" and j.get("campaign_id"):
                seen.add(j["campaign_id"])
        # We expect at least 2 distinct direct campaigns across the calls
        assert "direct" in sources, f"no direct served; sources={sources}"
        assert len(seen) >= 2, f"rotation failed: only saw {seen} across {sources}"

    def test_impressions_increment(self, free_sess, demo_sess):
        """After serving decisions, /portal/banner/mine impressions should be > 0
        for at least one campaign."""
        # Force some direct impressions
        for _ in range(4):
            free_sess.get(f"{BASE_URL}/api/ads/banner/decision",
                          params={"slot_key": "right_rail_mpu_1",
                                  "page_route": "/"}, timeout=15)
        r = demo_sess.get(f"{BASE_URL}/api/ads/portal/banner/mine",
                          params={"merchant_id": DEMO_MERCHANT_ID}, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        total_impr = sum(it.get("impressions", 0) for it in items)
        assert total_impr > 0, f"expected impressions > 0, items={items[:3]}"
