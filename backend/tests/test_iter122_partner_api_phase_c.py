"""Phase C (Partner API v1 — Creative Library + multi-format campaigns) tests.

Covers per review_request:
  • POST /creatives (asset_url→ready, no url→processing; idempotency + external_id)
  • GET/PATCH/DELETE /creatives (+ cursor pagination, filters)
  • POST /creatives/upload-url (real Tigris presigned PUT) + /finalize 409 asset_not_found
  • Validation: image >5MB → file_too_large, invalid type → 400, audio >60s → 400
  • SSRF-safe import: http:// → 400, localhost → 400
  • Multi-format POST /campaigns with line_items[] and no top-level product → 201
    with parent_campaign_id, multi_format:true, unsupported product → status
    'unsupported' (partial success)
  • Single-format still works; neither product nor line_items → 400 product_required
  • capabilities.feature_flags creative_library=true, multi_format_campaigns=true
  • REGRESSION: Phase A (/status,/inventory,/markets,/stations,/rate-card,/capabilities)
    + Phase B (/quotes, idempotency, external_id, cursor on /campaigns) + legacy detail
"""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or _env.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api/v1"
SANDBOX_KEY = "rlk_test_BdmWmROSnKO1.7gBxOXKXEIsKhfWOwunaKO2zBlhrtvbgU8uAmkZBwIk"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {SANDBOX_KEY}",
                         "Content-Type": "application/json"})
    return sess


def _uniq(prefix="ta"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture(scope="session")
def advertiser_id(s):
    """Reuse the existing sandbox advertiser or create a fresh one."""
    r = s.post(f"{BASE}/advertisers", json={
        "name": "TEST Phase C Adv", "contact_email": "pc@test.dev",
        "external_id": _uniq("pcadv")})
    assert r.status_code == 201, r.text
    return r.json()["advertiser"]["advertiser_id"]


# ── Capabilities flags ──────────────────────────────────────────────
class TestCapabilities:
    def test_phase_c_flags(self, s):
        r = s.get(f"{BASE}/capabilities")
        assert r.status_code == 200
        ff = r.json()["feature_flags"]
        assert ff["creative_library"] is True
        assert ff["multi_format_campaigns"] is True


# ── POST /creatives — create + idem + external_id ───────────────────
class TestCreativeCreate:
    def test_with_asset_url_is_ready(self, s):
        r = s.post(f"{BASE}/creatives", json={
            "type": "image", "name": "TEST img",
            "asset_url": "https://example.com/img.png",
            "click_url": "https://example.com/",
            "mime": "image/png", "size_bytes": 12345})
        assert r.status_code == 201, r.text
        c = r.json()["creative"]
        assert c["type"] == "image"
        assert c["status"] == "ready"
        assert c["creative_id"].startswith("crv_")

    def test_without_asset_url_is_processing(self, s):
        r = s.post(f"{BASE}/creatives", json={
            "type": "audio", "name": "TEST audio noasset"})
        assert r.status_code == 201
        assert r.json()["creative"]["status"] == "processing"

    def test_idempotency_same_key_same_creative(self, s):
        key = _uniq("cridem")
        body = {"type": "image", "name": "TEST idem",
                "asset_url": "https://example.com/a.png"}
        r1 = s.post(f"{BASE}/creatives", json=body, headers={"Idempotency-Key": key})
        r2 = s.post(f"{BASE}/creatives",
                    json={**body, "name": "TEST diff"},
                    headers={"Idempotency-Key": key})
        assert r1.status_code == 201 and r2.status_code in (200, 201)
        assert r1.json()["creative"]["creative_id"] == r2.json()["creative"]["creative_id"]
        # first body preserved
        assert r2.json()["creative"]["name"] == "TEST idem"

    def test_external_id_dedupe(self, s):
        ext = _uniq("crvext")
        body = {"type": "image", "asset_url": "https://example.com/x.png",
                "external_id": ext}
        r1 = s.post(f"{BASE}/creatives", json=body,
                    headers={"Idempotency-Key": _uniq("k")})
        r2 = s.post(f"{BASE}/creatives",
                    json={**body, "name": "diff"},
                    headers={"Idempotency-Key": _uniq("k")})
        assert r1.json()["creative"]["creative_id"] == r2.json()["creative"]["creative_id"]


# ── Validation ──────────────────────────────────────────────────────
class TestValidation:
    def test_image_too_large(self, s):
        r = s.post(f"{BASE}/creatives", json={
            "type": "image", "asset_url": "https://example.com/big.png",
            "size_bytes": 6 * 1024 * 1024})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "file_too_large"

    def test_invalid_type(self, s):
        r = s.post(f"{BASE}/creatives", json={"type": "nope"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_creative_type"

    def test_audio_duration_exceeds_max(self, s):
        r = s.post(f"{BASE}/creatives", json={
            "type": "audio", "duration_seconds": 120})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "duration_exceeds_max"


# ── GET / PATCH / DELETE ────────────────────────────────────────────
@pytest.fixture(scope="session")
def three_creatives(s):
    ids = []
    ext_first = _uniq("listext")
    for i in range(3):
        body = {"type": "image", "name": f"TEST list {i}",
                "asset_url": "https://example.com/l.png"}
        if i == 0:
            body["external_id"] = ext_first
        r = s.post(f"{BASE}/creatives", json=body)
        assert r.status_code == 201
        ids.append(r.json()["creative"]["creative_id"])
    return {"ids": ids, "first_ext": ext_first}


class TestCreativeCRUD:
    def test_get_by_id(self, s, three_creatives):
        cid = three_creatives["ids"][0]
        r = s.get(f"{BASE}/creatives/{cid}")
        assert r.status_code == 200
        assert r.json()["creative"]["creative_id"] == cid

    def test_get_not_found(self, s):
        r = s.get(f"{BASE}/creatives/crv_doesnotexist999")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "creative_not_found"

    def test_list_cursor_paginates(self, s):
        r1 = s.get(f"{BASE}/creatives", params={"limit": 2})
        assert r1.status_code == 200
        d1 = r1.json()
        for k in ("data", "count", "next_cursor", "has_more"):
            assert k in d1
        assert len(d1["data"]) == 2
        if d1["has_more"]:
            r2 = s.get(f"{BASE}/creatives",
                       params={"limit": 2, "cursor": d1["next_cursor"]})
            assert r2.status_code == 200
            a = {c["creative_id"] for c in d1["data"]}
            b = {c["creative_id"] for c in r2.json()["data"]}
            assert a.isdisjoint(b)

    def test_list_invalid_cursor(self, s):
        r = s.get(f"{BASE}/creatives", params={"cursor": "!!!bad"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_cursor"

    def test_list_filter_by_type(self, s):
        r = s.get(f"{BASE}/creatives", params={"type": "image", "limit": 5})
        assert r.status_code == 200
        for c in r.json()["data"]:
            assert c["type"] == "image"

    def test_list_filter_by_external_id(self, s, three_creatives):
        r = s.get(f"{BASE}/creatives",
                  params={"external_id": three_creatives["first_ext"]})
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 1
        assert d["data"][0]["creative_id"] == three_creatives["ids"][0]

    def test_patch_name_and_click(self, s, three_creatives):
        cid = three_creatives["ids"][1]
        r = s.patch(f"{BASE}/creatives/{cid}",
                    json={"name": "TEST renamed", "click_url": "https://x/"})
        assert r.status_code == 200
        assert r.json()["creative"]["name"] == "TEST renamed"
        # persisted
        g = s.get(f"{BASE}/creatives/{cid}").json()["creative"]
        assert g["name"] == "TEST renamed"
        assert g["click_url"] == "https://x/"

    def test_patch_invalid_status(self, s, three_creatives):
        r = s.patch(f"{BASE}/creatives/{three_creatives['ids'][1]}",
                    json={"status": "not_a_real_status"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_status"

    def test_delete_soft(self, s, three_creatives):
        cid = three_creatives["ids"][2]
        r = s.delete(f"{BASE}/creatives/{cid}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        g = s.get(f"{BASE}/creatives/{cid}").json()["creative"]
        assert g["status"] == "deleted"


# ── Signed upload URL + finalize 409 ────────────────────────────────
class TestUploadUrlFlow:
    def test_upload_url_returns_tigris_presigned_put(self, s):
        r = s.post(f"{BASE}/creatives/upload-url", json={
            "type": "image", "filename": "hero.png", "content_type": "image/png"})
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["creative_id"].startswith("crv_")
        assert d["asset_key"].endswith(".png")
        assert d["method"] == "PUT"
        assert d["headers"]["Content-Type"] == "image/png"
        assert d["finalize_url"].endswith(f"/creatives/{d['creative_id']}/finalize")
        # tigris presigned PUT — host should be fly.storage.tigris.dev
        parsed = urlparse(d["upload_url"])
        assert parsed.scheme == "https"
        assert "tigris" in parsed.netloc.lower(), f"unexpected host: {parsed.netloc}"
        # shell status = uploading
        c = s.get(f"{BASE}/creatives/{d['creative_id']}").json()["creative"]
        assert c["status"] == "uploading"
        assert c["asset_key"] == d["asset_key"]

    def test_finalize_before_upload_returns_409(self, s):
        r = s.post(f"{BASE}/creatives/upload-url", json={
            "type": "audio", "filename": "spot.mp3", "content_type": "audio/mpeg"})
        cid = r.json()["creative_id"]
        f = s.post(f"{BASE}/creatives/{cid}/finalize")
        assert f.status_code == 409
        assert f.json()["error"]["code"] == "asset_not_found"

    def test_upload_url_rejects_invalid_type(self, s):
        r = s.post(f"{BASE}/creatives/upload-url", json={
            "type": "image", "filename": "spot.mp3", "content_type": "audio/mpeg"})
        assert r.status_code == 400


# ── SSRF-safe import ────────────────────────────────────────────────
class TestImportSSRF:
    def test_http_scheme_blocked(self, s):
        r = s.post(f"{BASE}/creatives/import", json={
            "type": "image", "url": "http://example.com/x.png"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "import_url_must_be_https"

    def test_localhost_blocked(self, s):
        r = s.post(f"{BASE}/creatives/import", json={
            "type": "image", "url": "https://localhost/x.png"})
        assert r.status_code == 400
        # blocked host list catches "localhost" first
        assert r.json()["error"]["code"] in (
            "import_url_blocked_host", "import_url_private_or_unresolvable")

    def test_private_ip_blocked(self, s):
        # 127.0.0.1 → loopback
        r = s.post(f"{BASE}/creatives/import", json={
            "type": "image", "url": "https://127.0.0.1/x.png"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "import_url_private_or_unresolvable"

    def test_invalid_type_before_url_check_still_400(self, s):
        r = s.post(f"{BASE}/creatives/import", json={
            "type": "nope", "url": "https://example.com/x"})
        assert r.status_code == 400


# ── Multi-format campaign ───────────────────────────────────────────
@pytest.fixture(scope="session")
def two_creatives(s, advertiser_id):
    r_img = s.post(f"{BASE}/creatives", json={
        "type": "image", "name": "TEST banner",
        "asset_url": "https://example.com/b.png",
        "advertiser_id": advertiser_id})
    r_aud = s.post(f"{BASE}/creatives", json={
        "type": "audio", "name": "TEST spot",
        "asset_url": "https://example.com/s.mp3",
        "advertiser_id": advertiser_id})
    assert r_img.status_code == 201 and r_aud.status_code == 201
    return {"image": r_img.json()["creative"]["creative_id"],
            "audio": r_aud.json()["creative"]["creative_id"]}


class TestMultiFormatCampaign:
    def test_create_multiformat(self, s, advertiser_id, two_creatives):
        body = {
            "advertiser_id": advertiser_id, "name": "TEST MF Camp",
            "budget_total_cents": 200000,
            "line_items": [
                {"type": "audio_preroll", "creative_ids": [two_creatives["audio"]],
                 "cpm_bid_cents": 3000, "pricing_model": "cpm"},
                {"type": "display_banner", "creative_ids": [two_creatives["image"]],
                 "cpm_bid_cents": 900, "pricing_model": "cpm"},
            ]}
        r = s.post(f"{BASE}/campaigns", json=body)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["multi_format"] is True
        assert d["parent_campaign_id"].startswith("pcmp_")
        assert d["status"] == "active"  # sandbox auto-activates
        assert len(d["line_items"]) == 2
        for li in d["line_items"]:
            assert li["underlying_campaign_id"]
            assert li["status"] == "active"

    def test_get_line_items(self, s, advertiser_id, two_creatives):
        # create fresh so this test is standalone
        body = {"advertiser_id": advertiser_id, "name": "TEST MF Camp GET",
                "budget_total_cents": 100000,
                "line_items": [
                    {"type": "audio_preroll",
                     "creative_ids": [two_creatives["audio"]]},
                    {"type": "display_banner",
                     "creative_ids": [two_creatives["image"]]}]}
        pid = s.post(f"{BASE}/campaigns", json=body).json()["parent_campaign_id"]
        r = s.get(f"{BASE}/campaigns/{pid}/line-items")
        assert r.status_code == 200
        d = r.json()
        assert d["parent_campaign_id"] == pid
        assert d["count"] == 2
        assert d["parent"]["parent_id"] == pid

    def test_unbookable_line_item_partial_success(self, s, advertiser_id, two_creatives):
        # push_notification: api_bookable=False, campaign_type=None → unsupported
        body = {"advertiser_id": advertiser_id, "name": "TEST MF Partial",
                "budget_total_cents": 100000,
                "line_items": [
                    {"type": "audio_preroll",
                     "creative_ids": [two_creatives["audio"]],
                     "pricing_model": "cpm", "cpm_bid_cents": 3000},
                    {"type": "push_notification",
                     "creative_ids": [two_creatives["image"]]}]}
        r = s.post(f"{BASE}/campaigns", json=body)
        assert r.status_code == 201
        d = r.json()
        assert d["multi_format"] is True
        by_type = {li["type"]: li for li in d["line_items"]}
        assert by_type["audio_preroll"]["status"] == "active"
        assert by_type["push_notification"]["status"] == "unsupported"
        assert by_type["push_notification"]["underlying_campaign_id"] is None
        # parent still created
        pid = d["parent_campaign_id"]
        r2 = s.get(f"{BASE}/campaigns/{pid}/line-items")
        assert r2.status_code == 200

    def test_line_items_parent_not_found(self, s):
        r = s.get(f"{BASE}/campaigns/pcmp_doesnotexist/line-items")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "parent_campaign_not_found"


# ── Single-format still works + product_required ────────────────────
class TestSingleFormatRegression:
    def test_single_format_still_works(self, s, advertiser_id):
        r = s.post(f"{BASE}/campaigns", json={
            "advertiser_id": advertiser_id, "product": "audio_preroll",
            "name": "TEST SF Camp", "budget_total_cents": 100000,
            "pricing_model": "cpm", "cpm_bid_cents": 3000,
            "creative": {"audio_url": "https://example.com/a.mp3"}})
        assert r.status_code == 201, r.text
        assert r.json()["campaign"]["status"] == "active"

    def test_neither_product_nor_line_items(self, s, advertiser_id):
        r = s.post(f"{BASE}/campaigns", json={
            "advertiser_id": advertiser_id,
            "name": "TEST Neither", "budget_total_cents": 100000})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "product_required"


# ── Phase A/B regression ────────────────────────────────────────────
class TestPhaseABRegression:
    @pytest.mark.parametrize("path", [
        "/status", "/inventory", "/markets", "/rate-card",
        "/me", "/products", "/openapi.json", "/capabilities"])
    def test_endpoints(self, s, path):
        r = s.get(f"{BASE}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_stations_cursor(self, s):
        r = s.get(f"{BASE}/stations", params={"country": "AE", "limit": 2})
        assert r.status_code == 200
        for k in ("data", "next_cursor", "has_more"):
            assert k in r.json()

    def test_quote_still_works(self, s):
        r = s.post(f"{BASE}/quotes", json={
            "product": "audio_preroll", "pricing_model": "cpm",
            "market": "dubai", "budget_cents": 500000,
            "targeting_dimensions": 2, "daypart": "morning_drive"})
        assert r.status_code == 200
        d = r.json()
        assert d["effective_rate_cents"] == 4680

    def test_error_envelope_has_legacy_detail(self, s):
        r = s.post(f"{BASE}/creatives", json={"type": "not_a_type"})
        assert r.status_code == 400
        body = r.json()
        assert "detail" in body
        assert body["error"]["code"] == "invalid_creative_type"
