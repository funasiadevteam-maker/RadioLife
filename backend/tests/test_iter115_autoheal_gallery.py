"""Iteration 115 — Auto Heal cron wiring, Variation Gallery restore/history, ensure-flagship-art idempotency."""
import os
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
FLAGSHIP_SID = "imp_fun_big_1062_uae"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


# ── Feature 1: Auto Heal cron ────────────────────────────────────────
class TestAutoHealCron:
    def test_cron_scheduled_log_line(self):
        """Confirm supervisor backend logs contain '[art-autoheal] daily cron scheduled'."""
        try:
            out = subprocess.check_output(
                "grep '\\[art-autoheal\\] daily cron scheduled' /var/log/supervisor/backend.*.log | tail -5",
                shell=True, text=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            out = e.output or ""
        assert "art-autoheal" in out and "daily cron scheduled" in out, \
            f"cron scheduled log line missing: {out[:400]}"

    def test_ensure_flagship_art_shape_and_idempotent(self, admin_session):
        r1 = admin_session.post(f"{API}/imported-stations/ensure-flagship-art", timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        j1 = r1.json()
        assert j1.get("ok") is True
        assert isinstance(j1.get("queued"), int)
        q1 = j1["queued"]

        # Idempotent: immediately calling again should not queue MORE than the first.
        r2 = admin_session.post(f"{API}/imported-stations/ensure-flagship-art", timeout=30)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("ok") is True
        assert isinstance(j2.get("queued"), int)
        assert j2["queued"] <= q1, f"idempotency broken: q1={q1} q2={j2['queued']}"


# ── Feature 2: Variation Gallery (history + restore) ─────────────────
class TestVariationGallery:
    def test_history_shape(self, admin_session):
        r = admin_session.get(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/history", timeout=15)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("ok") is True
        assert "current" in j
        assert "current_source" in j
        assert isinstance(j.get("history"), list)
        # Iteration 114 seeded at least 1 variation for this flagship
        for h in j["history"]:
            assert "url" in h and "source" in h and "archived_at" in h

    def test_restore_rejects_unknown_url(self, admin_session):
        r = admin_session.post(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/restore",
            json={"art_url": "/api/static/station_artwork/does-not-exist-iter115.webp"},
            timeout=15)
        assert r.status_code == 400
        body = r.json()
        detail = body.get("detail") or {}
        assert (isinstance(detail, dict) and detail.get("error") == "unknown_art_url") \
            or (isinstance(detail, str) and "unknown_art_url" in detail), body

    def test_restore_archives_prior_and_flips_art(self, admin_session):
        # Fetch history first; need at least 1 entry to test restore
        h = admin_session.get(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/history", timeout=15).json()
        history = h.get("history") or []
        prior_current = h.get("current")
        if not history:
            pytest.skip("No artwork_history available on flagship — nothing to restore")

        pick = history[0]["url"]
        # Skip if the pick IS already current (idempotent restore is fine, but we want to
        # prove archival of a distinct prior current).
        if pick == prior_current:
            if len(history) > 1:
                pick = history[1]["url"]
            else:
                pytest.skip("history's only entry equals current — cannot exercise flip")

        r = admin_session.post(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/restore",
            json={"art_url": pick}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("ok") is True
        assert j.get("art_url") == pick
        assert j.get("status") == "complete"

        # After restore, GET history must show the previous current archived back into history
        h2 = admin_session.get(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/history", timeout=15).json()
        assert h2.get("current") == pick
        # prior_current should now be present in history[] (unless it was None / external)
        if prior_current and str(prior_current).startswith("/api/static/"):
            urls = [x.get("url") for x in (h2.get("history") or [])]
            assert prior_current in urls, \
                f"prior current {prior_current} not archived. history urls={urls}"

    def test_history_requires_auth(self):
        r = requests.get(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/history", timeout=10)
        assert r.status_code in (401, 403), r.status_code


# ── Feature 3: Regressions from prior iters ──────────────────────────
class TestRegressions:
    def test_variation_prompt_contains_alternate_take(self, admin_session):
        r = admin_session.post(
            f"{API}/imported-stations/{FLAGSHIP_SID}/artwork/generate",
            json={"variation": True}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert "alternate take" in (j.get("prompt") or "").lower()

    def test_heal_channel_thumbnails_admin(self, admin_session):
        r = admin_session.post(f"{API}/admin/channels/thumbnails/heal-all", timeout=30)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j.get("ok") is True
        assert isinstance(j.get("missing"), int)
        assert "started" in j
