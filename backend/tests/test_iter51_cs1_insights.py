"""Iter51 — CS.1 Creator Studio Video + Listing Insights backend tests.

CS.1: POST /api/podcasts/episodes/{id}/video, PUT /chapters, PUT /transcript,
GET /media — ownership-gated, Tigris upload, chapters sorting, transcript.
Insights: GET /api/merchant/featured/{id}/insights?days=7, and daily counter
bumps via GET /api/discovery/featured + POST /api/discovery/featured/{id}/click.
"""
import os
import io
import time
import uuid
import struct
import requests
import pytest
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

_client = MongoClient(MONGO_URL)
_db = _client[DB_NAME]


# ── helpers ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def demo_bearer():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def demo_user_id(demo_bearer):
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {demo_bearer}"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def owned_episode(demo_user_id):
    """Seed a creator+channel+episode owned by the demo user directly in Mongo."""
    creator_id = f"cr_test_{uuid.uuid4().hex[:8]}"
    channel_id = f"ch_test_{uuid.uuid4().hex[:8]}"
    episode_id = f"ep_test_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    # Cleanup any prior TEST_ creators for demo user (idempotency)
    _db.podcast_creators.delete_many({"user_id": demo_user_id, "id": {"$regex": "^cr_test_"}})
    _db.podcast_creators.insert_one({
        "id": creator_id, "user_id": demo_user_id,
        "name": "TEST_Creator", "status": "approved", "created_at": now,
    })
    _db.podcast_channels.insert_one({
        "id": channel_id, "creator_id": creator_id,
        "name": "TEST_Channel", "created_at": now,
    })
    _db.podcast_episodes.insert_one({
        "id": episode_id, "channel_id": channel_id,
        "title": "TEST_Episode", "publish_status": "draft",
        "duration_sec": 300, "created_at": now,
    })
    yield {"creator_id": creator_id, "channel_id": channel_id, "episode_id": episode_id}
    # teardown
    _db.podcast_episodes.delete_one({"id": episode_id})
    _db.podcast_channels.delete_one({"id": channel_id})
    _db.podcast_creators.delete_one({"id": creator_id})


# ── CS.1: media GET ──────────────────────────────────────────────
class TestCS1Media:
    def test_get_media_unknown_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/podcasts/episodes/does-not-exist/media", timeout=15)
        assert r.status_code == 404

    def test_get_media_default_audio(self, owned_episode):
        r = requests.get(f"{BASE_URL}/api/podcasts/episodes/{owned_episode['episode_id']}/media", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["episode_id"] == owned_episode["episode_id"]
        assert d["media_type"] in ("audio", "video")
        assert d["video_url"] is None  # no upload yet
        assert d["chapters"] == []
        assert d["transcript"] == ""


# ── CS.1: chapters + transcript (ownership + persistence) ────────
class TestCS1ChaptersTranscript:
    def test_put_chapters_owner_persists_sorted(self, demo_bearer, owned_episode):
        ep = owned_episode["episode_id"]
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        body = {"chapters": [
            {"title": "Intro", "start_seconds": 0},
            {"title": "Third bit", "start_seconds": 300},
            {"title": "Middle", "start_seconds": 120},
        ]}
        r = requests.put(f"{BASE_URL}/api/podcasts/episodes/{ep}/chapters",
                         json=body, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        chs = r.json()["chapters"]
        assert [c["start_seconds"] for c in chs] == [0, 120, 300], "must sort"
        # GET media should reflect it
        m = requests.get(f"{BASE_URL}/api/podcasts/episodes/{ep}/media", timeout=15).json()
        assert [c["title"] for c in m["chapters"]] == ["Intro", "Middle", "Third bit"]

    def test_put_transcript_owner_persists(self, demo_bearer, owned_episode):
        ep = owned_episode["episode_id"]
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        txt = "Hello world, this is a test transcript."
        r = requests.put(f"{BASE_URL}/api/podcasts/episodes/{ep}/transcript",
                         json={"transcript": txt}, headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert r.json()["length"] == len(txt)
        m = requests.get(f"{BASE_URL}/api/podcasts/episodes/{ep}/media", timeout=15).json()
        assert m["transcript"] == txt

    def test_chapters_ownership_gated(self, demo_bearer):
        # Seed an episode owned by SOMEONE ELSE
        stranger_id = f"stranger_{uuid.uuid4().hex[:8]}"
        cr = f"cr_stranger_{uuid.uuid4().hex[:6]}"
        ch = f"ch_stranger_{uuid.uuid4().hex[:6]}"
        ep = f"ep_stranger_{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc)
        _db.podcast_creators.insert_one({"id": cr, "user_id": stranger_id, "created_at": now})
        _db.podcast_channels.insert_one({"id": ch, "creator_id": cr, "created_at": now})
        _db.podcast_episodes.insert_one({"id": ep, "channel_id": ch, "created_at": now})
        try:
            hdrs = {"Authorization": f"Bearer {demo_bearer}"}
            r = requests.put(f"{BASE_URL}/api/podcasts/episodes/{ep}/chapters",
                             json={"chapters": [{"title": "x", "start_seconds": 0}]},
                             headers=hdrs, timeout=15)
            assert r.status_code == 403, r.text
        finally:
            _db.podcast_episodes.delete_one({"id": ep})
            _db.podcast_channels.delete_one({"id": ch})
            _db.podcast_creators.delete_one({"id": cr})

    def test_chapters_requires_auth(self, owned_episode):
        r = requests.put(
            f"{BASE_URL}/api/podcasts/episodes/{owned_episode['episode_id']}/chapters",
            json={"chapters": []}, timeout=15)
        assert r.status_code in (401, 403)


# ── CS.1: video upload (Tigris) ──────────────────────────────────
def _tiny_mp4_bytes() -> bytes:
    # Minimal valid-ish MP4 (ftyp box + mdat) — 32 bytes. Enough for content-type upload.
    ftyp = struct.pack(">I", 32) + b"ftyp" + b"isom" + struct.pack(">I", 512) + b"isomiso2mp41"
    return ftyp


class TestCS1VideoUpload:
    def test_upload_rejects_wrong_type(self, demo_bearer, owned_episode):
        ep = owned_episode["episode_id"]
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        files = {"video": ("notavideo.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(f"{BASE_URL}/api/podcasts/episodes/{ep}/video",
                          files=files, headers=hdrs, timeout=30)
        assert r.status_code == 400
        # Detail may be nested in {"detail":{"code":"unsupported_video_type"}}
        assert "unsupported_video_type" in r.text

    def test_upload_video_signed_url_and_media(self, demo_bearer, owned_episode):
        ep = owned_episode["episode_id"]
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        files = {"video": ("tiny.mp4", io.BytesIO(_tiny_mp4_bytes()), "video/mp4")}
        r = requests.post(f"{BASE_URL}/api/podcasts/episodes/{ep}/video",
                          files=files, headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["media_type"] == "video"
        assert d["video_url"], "signed URL should be present"
        # It should be a Tigris/S3 signed URL, not a local proxy path
        assert d["video_url"].startswith("http"), d["video_url"]
        # GET media should also return a signed URL now
        m = requests.get(f"{BASE_URL}/api/podcasts/episodes/{ep}/media", timeout=15).json()
        assert m["media_type"] == "video"
        assert m["video_url"] and m["video_url"].startswith("http")

    def test_upload_ownership_gated(self, demo_bearer):
        stranger_id = f"stranger_{uuid.uuid4().hex[:8]}"
        cr = f"cr_stranger_{uuid.uuid4().hex[:6]}"
        ch = f"ch_stranger_{uuid.uuid4().hex[:6]}"
        ep = f"ep_stranger_{uuid.uuid4().hex[:6]}"
        now = datetime.now(timezone.utc)
        _db.podcast_creators.insert_one({"id": cr, "user_id": stranger_id, "created_at": now})
        _db.podcast_channels.insert_one({"id": ch, "creator_id": cr, "created_at": now})
        _db.podcast_episodes.insert_one({"id": ep, "channel_id": ch, "created_at": now})
        try:
            hdrs = {"Authorization": f"Bearer {demo_bearer}"}
            files = {"video": ("tiny.mp4", io.BytesIO(_tiny_mp4_bytes()), "video/mp4")}
            r = requests.post(f"{BASE_URL}/api/podcasts/episodes/{ep}/video",
                              files=files, headers=hdrs, timeout=30)
            assert r.status_code == 403
        finally:
            _db.podcast_episodes.delete_one({"id": ep})
            _db.podcast_channels.delete_one({"id": ch})
            _db.podcast_creators.delete_one({"id": cr})


# ── Listing Insights ────────────────────────────────────────────
def _find_featured_campaign_for_demo():
    """Find a demo-owned type=featured campaign; prefer mc_7fe45437e320 if present."""
    pref = _db.merchant_campaigns.find_one({"campaign_id": "mc_7fe45437e320"})
    if pref:
        return pref["campaign_id"]
    doc = _db.merchant_campaigns.find_one({"type": "featured"}, sort=[("created_at", -1)])
    return doc["campaign_id"] if doc else None


def _find_active_featured_for_demo(demo_user_id):
    """Active + under-budget featured campaign owned by demo (for counter bump tests)."""
    doc = _db.merchant_campaigns.find_one({
        "type": "featured", "status": "active",
        "owner_user_id": demo_user_id,
        "$expr": {"$lt": ["$spent_usd", "$budget_usd"]},
    })
    return doc["campaign_id"] if doc else None


class TestInsights:
    def test_insights_shape_days7(self, demo_bearer):
        cid = _find_featured_campaign_for_demo()
        if not cid:
            pytest.skip("no featured campaign present to test insights against")
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        r = requests.get(f"{BASE_URL}/api/merchant/featured/{cid}/insights?days=7",
                         headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("title") is not None
        assert "series" in d and isinstance(d["series"], list)
        assert len(d["series"]) == 7
        for p in d["series"]:
            assert set(p.keys()) >= {"day", "impressions", "clicks", "spend_usd"}
        assert "totals" in d
        for k in ("impressions", "clicks", "spend_usd", "budget_usd"):
            assert k in d["totals"]

    def test_insights_days_clamped(self, demo_bearer):
        cid = _find_featured_campaign_for_demo()
        if not cid:
            pytest.skip("no featured campaign")
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        r = requests.get(f"{BASE_URL}/api/merchant/featured/{cid}/insights?days=999",
                         headers=hdrs, timeout=15)
        assert r.status_code == 200
        # max is 30
        assert len(r.json()["series"]) == 30

    def test_insights_not_owner_forbidden(self):
        cid = _find_featured_campaign_for_demo()
        if not cid:
            pytest.skip("no featured campaign")
        # Create a fresh account (non-demo) via /api/auth/demo? demo always returns same account.
        # Instead call without auth — should be 401 (auth-gated).
        r = requests.get(f"{BASE_URL}/api/merchant/featured/{cid}/insights?days=7", timeout=15)
        assert r.status_code in (401, 403)

    def test_daily_counter_bumps_on_featured_and_click(self, demo_bearer, demo_user_id):
        cid = _find_active_featured_for_demo(demo_user_id)
        if not cid:
            pytest.skip("no ACTIVE demo-owned featured campaign under budget")
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        # Reset today's row so the delta is deterministic
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _db.featured_daily.delete_one({"campaign_id": cid, "day": today})
        # Also allow a fresh click today
        _db.featured_clicks.delete_many({"campaign_id": cid, "day": today})
        # Baseline
        r0 = requests.get(f"{BASE_URL}/api/merchant/featured/{cid}/insights?days=7",
                          headers=hdrs, timeout=15).json()
        s0 = {p["day"]: p for p in r0["series"]}[today]
        # Bump impression via GET /api/discovery/featured (public)
        requests.get(f"{BASE_URL}/api/discovery/featured?limit=50", timeout=15)
        # Bump click (auth demo user)
        rc = requests.post(f"{BASE_URL}/api/discovery/featured/{cid}/click",
                           headers=hdrs, timeout=15)
        assert rc.status_code == 200, rc.text
        # Re-fetch insights
        r1 = requests.get(f"{BASE_URL}/api/merchant/featured/{cid}/insights?days=7",
                          headers=hdrs, timeout=15).json()
        s1 = {p["day"]: p for p in r1["series"]}[today]
        assert s1["impressions"] > s0["impressions"], f"{s0} -> {s1}"
        # Click billable is once-per-user-per-day. If charged is True, clicks bumped.
        if rc.json().get("charged"):
            assert s1["clicks"] > s0["clicks"], f"{s0} -> {s1}"
            assert s1["spend_usd"] >= s0["spend_usd"]

    def test_click_fraud_cap_same_day(self, demo_bearer, demo_user_id):
        cid = _find_active_featured_for_demo(demo_user_id)
        if not cid:
            pytest.skip("no ACTIVE demo-owned featured campaign under budget")
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        # First call may or may not charge (depends on prior test state); ensure a fresh state
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _db.featured_clicks.delete_many({"campaign_id": cid, "day": today,
                                         "user_id": {"$exists": True}})
        r1 = requests.post(f"{BASE_URL}/api/discovery/featured/{cid}/click",
                           headers=hdrs, timeout=15).json()
        r2 = requests.post(f"{BASE_URL}/api/discovery/featured/{cid}/click",
                           headers=hdrs, timeout=15).json()
        # First one charges; second must not
        assert r1.get("charged") is True
        assert r2.get("charged") is False


# ── Regression carry-over sanity (light) ────────────────────────
class TestRegressionLight:
    def test_marketplace_campaigns_list(self, demo_bearer):
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        r = requests.get(f"{BASE_URL}/api/merchant/marketplace/campaigns",
                         headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_notif_unread_count(self, demo_bearer):
        hdrs = {"Authorization": f"Bearer {demo_bearer}"}
        r = requests.get(f"{BASE_URL}/api/me/notifications/unread_count",
                         headers=hdrs, timeout=15)
        assert r.status_code == 200
        assert "count" in r.json() or "unread_count" in r.json()
