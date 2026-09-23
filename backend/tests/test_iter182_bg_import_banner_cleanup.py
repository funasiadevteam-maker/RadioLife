"""Iter182 — Background bulk-upload, CTR unification, banner weight clamp, sample banners rotation."""
import io
import os
import time
import uuid
import subprocess
import pytest
import requests

def _read_env(path, key):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        return None
    return None

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
        or "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
DEMO = ("demo@bigfm.dubai", "DemoPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")
BIZ_ID = "biz_8484f6f985d5"

# ---------- Helpers ----------
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    tok = j.get("session_token") or j.get("token") or j.get("access_token")
    return s, tok


@pytest.fixture(scope="module")
def admin_session():
    s, tok = _login(*ADMIN)
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def demo_session():
    s, tok = _login(*DEMO)
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def free_session():
    s, tok = _login(*FREE)
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def _mp3_bytes(seconds=1, freq=440):
    """Generate a real mp3 to a temp file and return its bytes. Adds a
    random-frequency-offset in the fractional part so re-runs produce
    genuinely unique file hashes (foreground+bg tests can't hit dedupe
    from previous runs)."""
    import random
    freq = float(freq) + random.uniform(0.001, 0.999)
    p = f"/tmp/qa_bg_{uuid.uuid4().hex[:8]}.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-acodec", "libmp3lame", p],
        check=True, capture_output=True, timeout=15)
    with open(p, "rb") as f:
        data = f.read()
    try: os.unlink(p)
    except Exception: pass
    return data


# ============ TASK A — Background bulk-upload ============
class TestBackgroundBulkUpload:
    def test_background_upload_returns_202_and_completes(self, admin_session):
        artist = f"QA182_{uuid.uuid4().hex[:8]}"
        fname = f"{artist}_bg.mp3"
        data = _mp3_bytes(seconds=1, freq=441)
        files = [("files", (fname, data, "audio/mpeg"))]
        form = {"background": "1", "default_language": "english",
                "default_genre": "test", "default_era": "2020s"}
        r = admin_session.post(f"{BASE}/api/admin/tracks/bulk-upload",
                               files=files, data=form, timeout=60)
        assert r.status_code == 202, f"expected 202 got {r.status_code}: {r.text[:300]}"
        j = r.json()
        assert j.get("ok") is True
        assert j.get("status") == "processing"
        assert j.get("job_id"), "job_id missing"
        assert j.get("queued_files", 0) >= 1
        job_id = j["job_id"]

        # Poll me endpoint until completed
        terminal = {"completed", "partial", "failed", "client_disconnected"}
        deadline = time.time() + 60
        last = None
        while time.time() < deadline:
            rr = admin_session.get(f"{BASE}/api/me/bulk-upload/jobs/{job_id}", timeout=15)
            assert rr.status_code == 200, f"poll failed: {rr.status_code} {rr.text[:200]}"
            last = rr.json()
            if last.get("status") in terminal:
                break
            time.sleep(1)
        assert last and last.get("status") == "completed", f"job status={last.get('status')}, full={last}"
        # imported_count should be >=1
        counts = last.get("counts") or last
        imported = (last.get("imported_count") or counts.get("imported_count")
                    or last.get("uploaded_count") or counts.get("uploaded_count") or 0)
        assert imported >= 1, f"expected imported>=1, got {imported} in {last}"

    def test_foreground_upload_returns_200_regression(self, admin_session):
        artist = f"QA182_{uuid.uuid4().hex[:8]}"
        fname = f"{artist}_fg.mp3"
        data = _mp3_bytes(seconds=1, freq=523)
        files = [("files", (fname, data, "audio/mpeg"))]
        form = {"default_language": "english", "default_genre": "test", "default_era": "2020s"}
        r = admin_session.post(f"{BASE}/api/admin/tracks/bulk-upload",
                               files=files, data=form, timeout=90)
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text[:300]}"
        j = r.json()
        assert j.get("ok") is True
        assert "items" in j and isinstance(j["items"], list) and len(j["items"]) >= 1
        assert j.get("uploaded", 0) >= 1
        assert "job_id" in j

    def test_foreground_dedupe_regression(self, admin_session):
        # Upload same file twice -> second should be duplicate
        data = _mp3_bytes(seconds=1, freq=660)
        fname = f"QA182_dup_{uuid.uuid4().hex[:6]}.mp3"
        form = {"default_language": "english", "default_genre": "test", "default_era": "2020s"}
        r1 = admin_session.post(f"{BASE}/api/admin/tracks/bulk-upload",
                                files=[("files", (fname, data, "audio/mpeg"))],
                                data=form, timeout=60)
        assert r1.status_code == 200
        # 2nd upload of same bytes
        r2 = admin_session.post(f"{BASE}/api/admin/tracks/bulk-upload",
                                files=[("files", (fname, data, "audio/mpeg"))],
                                data=form, timeout=60)
        assert r2.status_code == 200, r2.text[:300]
        j2 = r2.json()
        items = j2.get("items", [])
        assert any(i.get("status") == "duplicate" for i in items), f"no duplicate in {items}"

    def test_no_files_provided(self, admin_session):
        r = admin_session.post(f"{BASE}/api/admin/tracks/bulk-upload",
                               files=[("files", ("", b"", "audio/mpeg"))],
                               data={}, timeout=15)
        assert r.status_code == 400, r.text[:200]


# ============ TASK D — CTR unification + weight clamp ============
class TestBannerCtrAndWeightClamp:
    def test_portal_banner_mine_ctr_is_fraction(self, demo_session):
        r = demo_session.get(f"{BASE}/api/ads/portal/banner/mine",
                             params={"merchant_id": BIZ_ID}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        # Response could be list or dict
        campaigns = j if isinstance(j, list) else (j.get("campaigns") or j.get("items") or [])
        assert isinstance(campaigns, list) and len(campaigns) >= 1, f"no campaigns: {j}"
        # All campaigns must have ctr <= 1 (fraction)
        for c in campaigns:
            ctr = c.get("ctr")
            assert ctr is not None, f"ctr missing: {c}"
            assert 0 <= float(ctr) <= 1.0, f"ctr not a fraction: {ctr} in {c}"

    def test_publish_clamps_weight_to_10(self, demo_session):
        # publish with weight=99999 -> persisted weight must be <=10
        payload = {
            "merchant_id": BIZ_ID,
            "slot_keys": ["right_rail_mpu_1"],
            "creative_image_url": "/api/static/banners/samples/biz_placeholder.jpg",
            "click_url": "https://example.com/qa182",
            "weight": 99999,
            "publish_mode": "instant",
            "headline": "QA182 weight clamp",
        }
        r = demo_session.post(f"{BASE}/api/ads/portal/banner/publish",
                              json=payload, timeout=15)
        assert r.status_code in (200, 201), f"publish failed: {r.status_code} {r.text[:300]}"
        j = r.json()
        cid = j.get("campaign_id") or j.get("id") or (j.get("campaign") or {}).get("id")
        assert cid, f"no campaign_id in response: {j}"

        # Verify weight is clamped by reading the persisted doc directly.
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from motor.motor_asyncio import AsyncIOMotorClient
        async def _fetch():
            c = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = c[os.environ["DB_NAME"]]
            return await db.banner_ad_campaigns.find_one({"_id": cid})
        doc = asyncio.get_event_loop().run_until_complete(_fetch()) if False else asyncio.run(_fetch())
        assert doc is not None, f"campaign {cid} not found in DB"
        w = doc.get("weight")
        assert w is not None and 1 <= int(w) <= 10, f"weight not clamped: {w} in doc"


# ============ TASK B — Sample banners rotation ============
class TestSampleBannersRotation:
    def test_decision_rotates_distinct_sample_creatives(self, free_session):
        seen = set()
        served = 0
        sample_urls = set()
        for i in range(20):
            r = free_session.get(f"{BASE}/api/ads/banner/decision",
                                 params={"slot_key": "right_rail_mpu_1",
                                         "page_route": "/home"}, timeout=15)
            assert r.status_code == 200, r.text[:200]
            j = r.json()
            if j.get("source") == "none":
                continue
            served += 1
            cid = j.get("campaign_id") or (j.get("campaign") or {}).get("id")
            if cid: seen.add(cid)
            url = j.get("creative_image_url") or (j.get("creative") or {}).get("image_url") or ""
            if "/api/static/banners/samples/biz_" in url:
                sample_urls.add(url)
        assert served >= 10, f"too few served: {served}"
        assert len(seen) >= 3, f"expected >=3 distinct campaign_ids, got {len(seen)}: {seen}"
        assert len(sample_urls) >= 3, f"expected >=3 distinct sample creative URLs, got {len(sample_urls)}"

    def test_sample_creative_urls_serve_200_jpeg(self, free_session):
        # Collect a few sample URLs from decisions
        urls = set()
        for _ in range(15):
            r = free_session.get(f"{BASE}/api/ads/banner/decision",
                                 params={"slot_key": "right_rail_mpu_1",
                                         "page_route": "/home"}, timeout=15)
            if r.status_code != 200: continue
            u = (r.json().get("creative_image_url") or "")
            if "/api/static/banners/samples/biz_" in u:
                urls.add(u)
            if len(urls) >= 3: break
        assert len(urls) >= 1, "no sample creative URLs found from decisions"
        for u in list(urls)[:3]:
            full = u if u.startswith("http") else f"{BASE}{u}"
            rr = requests.get(full, timeout=15)
            assert rr.status_code == 200, f"{full} -> {rr.status_code}"
            ct = rr.headers.get("content-type", "")
            assert "image" in ct and "jp" in ct.lower(), f"content-type={ct} for {full}"

    def test_premium_user_gets_none(self, demo_session):
        r = demo_session.get(f"{BASE}/api/ads/banner/decision",
                             params={"slot_key": "right_rail_mpu_1",
                                     "page_route": "/home"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("source") == "none", f"premium should get source=none, got {j}"
        assert j.get("reason") == "premium", f"expected reason=premium, got {j}"
