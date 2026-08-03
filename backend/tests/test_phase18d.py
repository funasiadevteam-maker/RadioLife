"""Phase 18d — programmatic stack tests (GAM, OpenRTB, VAST, ads.txt,
attribution_window_hours, on_pace fixture)."""
import asyncio, os, secrets, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ─── 1. GAM mock returns deterministic envelope ────────────────────────
def test_gam_adapter_mock_returns_envelope_with_vast_and_revenue():
    from services import gam_adapter
    assert gam_adapter.is_live() is False    # no env vars in QA → mock
    env = run(gam_adapter.request_ad(
        channel_slug="morning_masala", user_id="u_gam",
        market="dubai"))
    assert env is not None
    assert env["source"] == "gam_mock"
    assert env["revenue_usd"] > 0
    assert env["vast_xml"].startswith("<?xml")
    assert env["creative_id"].startswith("gam_mock_")


# ─── 2. OpenRTB mock returns deterministic 2-bid response + 2nd price ──
def test_openrtb_adapter_mock_returns_second_price_winner():
    from services import openrtb_adapter
    assert openrtb_adapter.is_live() is False
    req  = openrtb_adapter.build_bid_request(user_id="u_ortb",
                                                                          channel_slug="party_dubai",
                                                                          market="dubai")
    assert req["imp"][0]["audio"]["protocols"] == [7, 8, 9]
    bids = run(openrtb_adapter.send_to_ssps(req))
    assert len(bids) == 2
    win = openrtb_adapter.select_winning_bid(bids)
    assert win is not None
    # 2nd-price: clear price < highest bid price (which is 0.008)
    assert 0 < win["clear_price"] < 0.008 + 0.001
    assert win["mocked"] is True


# ─── 3. Waterfall order: takeover → direct → GAM → OpenRTB ────────────
def test_waterfall_falls_through_to_gam_when_no_direct_sold_eligible():
    """When pick_ad_for_user has no eligible direct-sold campaign, it
    falls through to GAM (mock).  We verify by calling with a market
    that has zero active campaigns matching."""
    from services.advertisers import pick_ad_for_user
    db = AsyncIOMotorClient(MONGO)[DBN]
    # Use a synthetic "novirgin_market" no real campaign targets.
    res = run(pick_ad_for_user(db,
                                              user_id=f"u_waterfall_{secrets.token_hex(3)}",
                                              channel_slug="__nonexistent_chan__",
                                              market="zzz_no_market"))
    # Either GAM envelope (mock) or OpenRTB envelope — both have `source`.
    assert res is not None
    src = (res.get("campaign") or {}).get("source") or \
              (res.get("serve") or {}).get("source")
    assert src in ("gam_mock", "openrtb_mock")


# ─── 4. VAST XML parses, has tracking URL with serve_id ────────────────
def test_vast_wrapper_emits_parseable_xml_with_serve_id_tracker():
    from services.vast_wrapper import build_vast_xml
    creative = {"id": "crt_test_001", "title": "Hot Karak",
                      "audio_url": "/api/static/ad_creatives/x.mp3",
                      "click_url": "https://example.com",
                      "duration_sec": 15, "transcript": "Hot karak now."}
    xml = build_vast_xml(creative, serve_id="serve_phase18d_abc",
                                      advertiser_name="Demo Advertiser")
    root = ET.fromstring(xml)
    assert root.tag == "VAST"
    assert root.attrib["version"] == "4.0"
    imp = root.find(".//Impression")
    assert imp is not None
    assert "serve_id=serve_phase18d_abc" in (imp.text or "")
    assert "event=impression" in (imp.text or "")


# ─── 5. Tracking endpoint dedup: same (serve_id, event) → single ping ─
def test_tracking_impression_dedups_same_serve_event_pair():
    """Idempotency via dedup_key on ad_serve_event_pings."""
    db = AsyncIOMotorClient(MONGO)[DBN]
    sid = f"serve_track_{secrets.token_hex(4)}"
    run(db.ad_serve_event_pings.delete_many({"serve_id": sid}))
    # Simulate 3 calls to the same (sid, "impression") tuple.
    for _ in range(3):
        run(db.ad_serve_event_pings.update_one(
            {"dedup_key": f"{sid}|impression"},
            {"$setOnInsert": {"dedup_key": f"{sid}|impression",
                                          "serve_id": sid, "event": "impression",
                                          "first_seen": datetime.now(timezone.utc)},
              "$inc": {"hits": 1},
              "$set": {"last_seen": datetime.now(timezone.utc)}},
            upsert=True))
    docs = run(db.ad_serve_event_pings.find({"serve_id": sid}).to_list(10))
    assert len(docs) == 1
    assert docs[0]["hits"] == 3


# ─── 6. ads.txt validator: bad rows are flagged, good rows accepted ───
def test_ads_txt_validator_rejects_bad_rows_accepts_good():
    from services.ads_txt_manager import validate
    content = "# header comment\n" \
                  "google.com, pub-1234, DIRECT, f08c47fec0942fa0\n" \
                  "this is not valid\n" \
                  "openx.com, 539, RESELLER\n" \
                  "\n"
    v = validate(content)
    assert v["ok"] is False
    assert v["valid_line_count"] == 2
    assert len(v["bad_lines"]) == 1
    assert v["bad_lines"][0]["line_no"] == 3

    good = "# only good\n" \
              "google.com, pub-1234, DIRECT\n" \
              "openx.com, 539, RESELLER, abc123\n"
    v2 = validate(good)
    assert v2["ok"] is True
    assert v2["valid_line_count"] == 2


def test_ads_txt_write_then_read_roundtrip():
    """The write_content+read_content roundtrip persists the seller list."""
    from services import ads_txt_manager
    # Use a temp file so we don't clobber a real preview file.
    original_path = ads_txt_manager.ADS_TXT_PATH
    tmp = Path(f"/tmp/ads_txt_test_{secrets.token_hex(3)}.txt")
    ads_txt_manager.ADS_TXT_PATH = tmp
    try:
        body = "# test seller list\ngoogle.com, pub-test-001, DIRECT\n"
        r = ads_txt_manager.write_content(body)
        assert r["ok"] is True
        assert r["valid_line_count"] == 1
        assert ads_txt_manager.read_content() == body
    finally:
        ads_txt_manager.ADS_TXT_PATH = original_path
        tmp.unlink(missing_ok=True)


# ─── 7. attribution_window_hours filter ────────────────────────────────
def test_attribution_window_hours_excludes_save_outside_window():
    """Two coupons + one serve: save_at T+1h passes, save_at T+25h fails
    when window=24h. We simulate by calling the underlying mongo query
    flow the /attribution endpoint uses."""
    db = AsyncIOMotorClient(MONGO)[DBN]
    cid = f"cmp_winhr_{secrets.token_hex(3)}"
    aid = f"adv_winhr_{secrets.token_hex(3)}"
    sid = f"serve_winhr_{secrets.token_hex(3)}"
    served_at = datetime.now(timezone.utc) - timedelta(hours=30)
    run(db.ad_campaigns.delete_many({"id": cid}))
    run(db.coupons.delete_many({"attribution_campaign_id": cid}))
    run(db.ad_serve_events.delete_many({"campaign_id": cid}))
    # Seed: 1 campaign with window_hours=24
    run(db.ad_campaigns.insert_one(
        {"id": cid, "advertiser_id": aid, "status": "active",
          "attribution_window_hours": 24, "spend_usd": 5.0,
          "budget_total_usd": 100.0}))
    run(db.ad_serve_events.insert_one(
        {"id": sid, "serve_id": sid, "user_id": "u_winhr",
          "campaign_id": cid, "advertiser_id": aid,
          "channel_slug": "morning_masala",
          "served_at": served_at}))
    # In-window coupon (saved 1h after serve)
    cp_in_id = f"cp_in_{secrets.token_hex(3)}"
    run(db.coupons.insert_one(
        {"_id": cp_in_id, "coupon_id": cp_in_id,
          "user_id": "u_winhr", "status": "saved",
          "attribution_serve_id": sid,
          "attribution_campaign_id": cid,
          "saved_at": served_at + timedelta(hours=1)}))
    # Out-of-window coupon (saved 27h after serve)
    cp_out_id = f"cp_out_{secrets.token_hex(3)}"
    run(db.coupons.insert_one(
        {"_id": cp_out_id, "coupon_id": cp_out_id,
          "user_id": "u_winhr", "status": "saved",
          "attribution_serve_id": sid,
          "attribution_campaign_id": cid,
          "saved_at": served_at + timedelta(hours=27)}))
    # Call the route handler directly via its async function
    from routes.phase18c import attribution
    from unittest.mock import MagicMock
    req = MagicMock(); req.app.state.db = db
    out = run(attribution(aid, cid, req))
    assert out["impressions"] == 1
    assert out["coupon_saves"] == 1, "27h-late save must be excluded"
    assert out["attribution_window_hours"] == 24


# ─── 8. on_pace fixture present in seed + classified correctly ────────
def test_on_pace_fixture_present_and_classified_as_on_pace():
    """Self-reseed the fixture (earlier phase 18a tests may have wiped
    all adv_demo_karak campaigns) so this assertion is deterministic."""
    from services.pacing import pacing_status
    from scripts.seed_pacing_demo import seed_pacing_demo
    db = AsyncIOMotorClient(MONGO)[DBN]
    run(seed_pacing_demo(db))
    c = run(db.ad_campaigns.find_one({"id": "cmp_test_onpace_001"}))
    assert c is not None, "on_pace fixture not seeded"
    assert c["name"] == "Steady Eddie"
    p = pacing_status(c)
    assert p["status"] == "on_pace", f"expected on_pace, got {p['status']}"


# ─── 9. GAM + OpenRTB status snapshots ────────────────────────────────
def test_gam_status_snapshot_reports_mock_state():
    from services.gam_adapter import status_snapshot
    s = status_snapshot()
    assert s["is_live"] is False
    assert "network_code_present" in s
    assert "service_account_present" in s


def test_openrtb_status_snapshot_reports_mock_state():
    from services.openrtb_adapter import status_snapshot
    s = status_snapshot()
    assert s["is_live"] is False
    assert s["ssp_endpoints_configured"] == []



# ─── 18d.1 — three bug-fix regression tests ───────────────────────────

def test_ads_txt_admin_post_reflects_on_public_route():
    """Round-trip: admin writes via ads_txt_manager → public route reads
    the new content from the SAME file. Uses an httpx TestClient against
    the live FastAPI app so we exercise the actual /ads.txt route, not
    just the underlying module."""
    from services import ads_txt_manager
    from fastapi.testclient import TestClient
    # Save & restore the real preview file so this test never clobbers
    # real seller data.
    orig_path = ads_txt_manager.ADS_TXT_PATH
    tmp_path  = Path(f"/tmp/ads_txt_e2e_{secrets.token_hex(3)}.txt")
    ads_txt_manager.ADS_TXT_PATH = tmp_path
    try:
        # Import the app AFTER patching so the route resolves the new path.
        from server import app
        marker = f"# e2e-marker-{secrets.token_hex(4)}\n"
        body   = marker + "google.com, pub-e2e-001, DIRECT, ftest\n"
        r = ads_txt_manager.write_content(body)
        assert r["ok"] is True
        with TestClient(app) as client:
            resp = client.get("/ads.txt")
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/plain")
            assert marker.strip() in resp.text, \
                f"public /ads.txt did not surface admin write; got: {resp.text!r}"
            assert "pub-e2e-001" in resp.text
    finally:
        ads_txt_manager.ADS_TXT_PATH = orig_path
        tmp_path.unlink(missing_ok=True)


def test_ads_txt_preview_url_reflects_admin_writes_through_full_stack():
    """Regression for the static-asset-precedence bug found on 2026-06-02:
    /app/frontend/public/ads.txt was being served by the CRA dev server
    BEFORE the request ever reached FastAPI. The fix removed those
    impostor files and added a setupProxy.js forwarding /ads.txt and
    /app-ads.txt to the backend.

    This test hits the REAL preview URL (not localhost, not TestClient)
    to ensure the full request path (CF → frontend dev server → proxy →
    FastAPI → ads_txt_manager) is correct end-to-end.

    Skipped if REACT_APP_BACKEND_URL is not set (CI without preview)."""
    import os, requests
    preview = os.environ.get("REACT_APP_BACKEND_URL")
    if not preview:
        pytest.skip("REACT_APP_BACKEND_URL not set — skipping preview e2e")
    # 1) Log in as admin and POST a unique marker.
    s = requests.Session()
    r_login = s.post(f"{preview}/api/auth/login", timeout=10,
                                json={"email":      "admin@bigfm.dubai",
                                          "password": "AdminPass123!"})
    if r_login.status_code != 200:
        pytest.skip(f"preview admin login unavailable (got {r_login.status_code})")
    marker = f"# preview-e2e-{secrets.token_hex(5)}"
    body    = marker + "\ngoogle.com, pub-preview-test, DIRECT, ftest\n"
    r_post = s.post(f"{preview}/api/admin/integrations/ads-txt",
                            json={"content": body}, timeout=10)
    assert r_post.status_code == 200, r_post.text
    # 2) GET the public URL (no auth) and assert the marker is present.
    r_get = requests.get(f"{preview}/ads.txt?nocache={secrets.token_hex(3)}",
                                    headers={"Cache-Control": "no-cache"},
                                    timeout=10)
    assert r_get.status_code == 200
    assert r_get.headers.get("content-type", "").startswith("text/plain")
    assert marker in r_get.text, (
        f"PREVIEW URL did not surface admin write through full stack; "
        f"marker={marker!r} body={r_get.text!r}")
    # 3) Same for /app-ads.txt.
    r_get2 = requests.get(f"{preview}/app-ads.txt?nocache={secrets.token_hex(3)}",
                                      headers={"Cache-Control": "no-cache"},
                                      timeout=10)
    assert r_get2.status_code == 200
    assert marker in r_get2.text


def test_pick_debug_waterfall_returns_programmatic_source_when_no_direct_sold():
    """Regression for the 500 KeyError: pick-debug must NOT raise when the
    waterfall lands on a programmatic (GAM/OpenRTB) backfill — those
    envelopes carry advertiser_id=None.  Asserts source ∈ {gam_mock, openrtb_mock}
    and explicit None for advertiser_id / campaign_id."""
    from services.advertisers import pick_ad_for_user
    db = AsyncIOMotorClient(MONGO)[DBN]
    # Force the no-direct-sold path with a synthetic channel slug.
    res = run(pick_ad_for_user(
        db, user_id=f"u_picdbg_{secrets.token_hex(3)}",
        channel_slug="__force_fallback_18d__",
        market="atlantis_nonexistent"))
    assert res is not None, "waterfall must produce a backfill envelope"
    serve = res.get("serve") or {}
    assert serve.get("source") in ("gam_mock", "openrtb_mock"), \
        f"unexpected source: {serve.get('source')!r}"
    assert serve.get("advertiser_id") is None
    assert serve.get("campaign_id")    is None
    # Same shape on the campaign sub-doc — the pick-debug handler reads it.
    camp = res.get("campaign") or {}
    assert camp.get("id") is None
    assert camp.get("advertiser_id") is None


def test_patch_campaign_attribution_window_hours_persists():
    """attribution_window_hours must be in the PATCH allowed set, and
    validation must enforce 1 ≤ hours ≤ 720. We invoke the route handler
    directly to avoid the full auth chain."""
    from routes.advertiser import update_campaign
    from unittest.mock import AsyncMock, MagicMock
    db   = AsyncIOMotorClient(MONGO)[DBN]
    aid  = "adv_demo_karak"
    cid  = f"cmp_winhr_patch_{secrets.token_hex(3)}"
    # Seed a minimal campaign owned by adv_demo_karak so the update_one
    # matches.
    run(db.ad_campaigns.delete_many({"id": cid}))
    run(db.ad_campaigns.insert_one({
        "id": cid, "advertiser_id": aid, "status": "draft",
        "name": "PATCH window test", "budget_total_usd": 100,
        "attribution_window_hours": 24}))

    # Build a request object whose `_require_staff` dependency is bypassed
    # via monkeypatching at module level.
    import routes.advertiser as adv_routes
    real_require = adv_routes._require_staff
    adv_routes._require_staff = AsyncMock(return_value=None)
    request = MagicMock()
    request.app.state.db = db
    try:
        # ─── valid: 48 persists ────────────────
        out = run(update_campaign(aid, cid, {"attribution_window_hours": 48},
                                                request))
        assert out["ok"] is True
        assert out["campaign"]["attribution_window_hours"] == 48
        on_disk = run(db.ad_campaigns.find_one({"id": cid}))
        assert on_disk["attribution_window_hours"] == 48

        # ─── negative: 0 rejected ────────────────
        from fastapi import HTTPException
        try:
            run(update_campaign(aid, cid, {"attribution_window_hours": 0},
                                              request))
            assert False, "expected HTTP 400 for 0"
        except HTTPException as e:
            assert e.status_code == 400

        # ─── negative: 1000 rejected ────────────────
        try:
            run(update_campaign(aid, cid,
                                              {"attribution_window_hours": 1000},
                                              request))
            assert False, "expected HTTP 400 for 1000"
        except HTTPException as e:
            assert e.status_code == 400
    finally:
        adv_routes._require_staff = real_require
        run(db.ad_campaigns.delete_many({"id": cid}))


def test_ads_txt_invalid_post_returns_flat_400_envelope():
    """Regression for the double-wrapped detail bug. POST with bad rows
    must return `{detail: {code, bad_lines: [...]}}` — single wrapper."""
    from routes.phase18d import admin_set_ads_txt, AdsTxtBody
    from fastapi import HTTPException
    from unittest.mock import MagicMock
    body = AdsTxtBody(content="not valid\nalso bad\n")
    try:
        run(admin_set_ads_txt(body, _admin=MagicMock()))
        assert False, "expected HTTPException 400"
    except HTTPException as e:
        assert e.status_code == 400
        detail = e.detail
        # Single-wrapped: detail is a dict with `code` + `bad_lines` directly.
        assert isinstance(detail, dict)
        assert detail.get("code") == "invalid_ads_txt_lines"
        assert "bad_lines" in detail
        assert isinstance(detail["bad_lines"], list)
        assert len(detail["bad_lines"]) >= 1
        # Crucial: no double `detail` nesting.
        assert "detail" not in detail
