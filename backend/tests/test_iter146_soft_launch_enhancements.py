"""Iter146 — Soft-launch enhancements (pagination, leaderboard, tier, checklist,
teaser). Backend-only regression. Web cookies for admin + merchant.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests


def _load_backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        try:
            with open("/app/frontend/.env", "r") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE = _load_backend_url()
assert BASE, "REACT_APP_BACKEND_URL missing"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


# ────────────────────────────── fixtures ──────────────────────────────
@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json=DEMO, timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    return s


# ══════════════════════════ 1) DIRECTORY PAGINATION ══════════════════
class TestDirectoryPagination:
    def test_default_shape(self, anon):
        r = anon.get(f"{BASE}/api/launch/businesses", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("total", "items", "loaded", "has_more"):
            assert k in d, f"missing {k} in {list(d)}"
        assert isinstance(d["items"], list)
        assert isinstance(d["total"], int) and d["total"] > 0
        # default limit is 24
        assert len(d["items"]) <= 24
        # loaded is the full cached list length
        assert d["loaded"] >= len(d["items"])

    def test_limit_and_offset_window(self, anon):
        first = anon.get(f"{BASE}/api/launch/businesses?limit=10&offset=0", timeout=15).json()
        second = anon.get(f"{BASE}/api/launch/businesses?limit=10&offset=10", timeout=15).json()
        assert len(first["items"]) == 10
        assert first["has_more"] is True
        # Windowed slices must not overlap
        names_a = [i["name"] for i in first["items"]]
        names_b = [i["name"] for i in second["items"]]
        assert set(names_a).isdisjoint(set(names_b)), "offset windows overlapped"
        # Same total on both calls (cached list)
        assert first["loaded"] == second["loaded"]

    def test_limit_clamped(self, anon):
        # limit clamped 1..60
        high = anon.get(f"{BASE}/api/launch/businesses?limit=999", timeout=15).json()
        low = anon.get(f"{BASE}/api/launch/businesses?limit=0", timeout=15).json()
        assert len(high["items"]) <= 60
        assert len(low["items"]) >= 1  # limit=0 clamps to 1

    def test_has_more_false_at_end(self, anon):
        head = anon.get(f"{BASE}/api/launch/businesses?limit=1&offset=0", timeout=15).json()
        loaded = head["loaded"]
        # Fetch a window past the end
        tail = anon.get(f"{BASE}/api/launch/businesses?limit=10&offset={max(0, loaded - 5)}",
                        timeout=15).json()
        assert tail["has_more"] is False


# ══════════════════════════ 2) REFERRAL LEADERBOARD ══════════════════
class TestLeaderboard:
    def test_shape_and_tiers(self, anon):
        r = anon.get(f"{BASE}/api/launch/leaderboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "tiers" in d and "top" in d
        assert isinstance(d["tiers"], list) and len(d["tiers"]) == 5
        expected_names = ["Waitlisted", "Insider", "VIP", "Founding Fan", "Legend"]
        assert [t["name"] for t in d["tiers"]] == expected_names
        # thresholds
        assert [t["min"] for t in d["tiers"]] == [0, 1, 3, 5, 10]

    def test_top_sorted_and_positive_only(self, anon):
        d = anon.get(f"{BASE}/api/launch/leaderboard?limit=25", timeout=15).json()
        top = d["top"]
        # All entries must have referrals > 0 and be sorted desc by referrals
        for e in top:
            assert e["referrals"] > 0
            assert e["rank"] >= 1
            assert "tier" in e
        # Ranks are 1..N sequential
        assert [e["rank"] for e in top] == list(range(1, len(top) + 1))
        # Sorted desc by referrals
        refs = [e["referrals"] for e in top]
        assert refs == sorted(refs, reverse=True)

    def test_emails_masked(self, anon):
        d = anon.get(f"{BASE}/api/launch/leaderboard?limit=25", timeout=15).json()
        for e in d["top"]:
            name = e["name"]
            # Should NOT be a full e-mail; must contain bullet/ellipsis mask chars.
            # Full email would look like "abc@example.com" — mask uses \u2022 (•) and \u2026 (…).
            assert "\u2022" in name or "\u2026" in name or "someone" == name, \
                f"unmasked leaderboard entry: {name!r}"


# ═══════════════════════ 3) REFERRAL TIER SURFACED ═══════════════════
class TestTierOnWaitlist:
    def test_join_exposes_tier(self, anon):
        email = f"TEST_iter146_tier_{uuid.uuid4().hex[:8]}@example.com"
        r = anon.post(f"{BASE}/api/waitlist", json={"email": email}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ("ok", "ref_code", "share_path", "position", "referrals", "total", "tier"):
            assert k in d, f"missing key {k}"
        assert d["referrals"] == 0
        assert d["tier"] == "Waitlisted"

    def test_position_exposes_tier(self, anon):
        email = f"TEST_iter146_pos_{uuid.uuid4().hex[:8]}@example.com"
        j = anon.post(f"{BASE}/api/waitlist", json={"email": email}, timeout=15).json()
        code = j["ref_code"]
        r = anon.get(f"{BASE}/api/waitlist/position?code={code}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["tier"] == "Waitlisted"
        assert d["referrals"] == 0

    def test_tier_updates_with_referrals(self, anon):
        # Owner
        owner_email = f"TEST_iter146_owner_{uuid.uuid4().hex[:8]}@example.com"
        owner = anon.post(f"{BASE}/api/waitlist", json={"email": owner_email}, timeout=15).json()
        code = owner["ref_code"]
        # 1 referral → Insider
        r1 = anon.post(f"{BASE}/api/waitlist",
                       json={"email": f"TEST_iter146_r1_{uuid.uuid4().hex[:8]}@example.com",
                             "ref": code}, timeout=15).json()
        assert r1["already"] is False
        pos = anon.get(f"{BASE}/api/waitlist/position?code={code}", timeout=15).json()
        assert pos["referrals"] == 1
        assert pos["tier"] == "Insider"


# ══════════════════════════ 4) MERCHANT CHECKLIST ═══════════════════
class TestMerchantChecklist:
    def test_auth_required(self, anon):
        r = anon.get(f"{BASE}/api/merchant/soft-launch/checklist", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_demo_shape(self, demo):
        r = demo.get(f"{BASE}/api/merchant/soft-launch/checklist", timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("items", "progress", "launch_ready", "has_storefront", "catalog_count"):
            assert k in d, f"missing {k}"
        items = d["items"]
        keys = [i["key"] for i in items]
        assert keys == ["claim", "profile", "logo", "catalog", "cover"]
        # cover must be marked optional
        cover = next(i for i in items if i["key"] == "cover")
        assert cover.get("optional") is True
        # each item has required cta fields
        for it in items:
            assert "done" in it and isinstance(it["done"], bool)
            assert it.get("cta_route") and it.get("cta_label")
        # progress counts ONLY 4 required
        assert d["progress"]["total"] == 4
        assert 0 <= d["progress"]["done"] <= 4
        # launch_ready is true iff all 4 required done
        req_done = sum(1 for i in items if not i.get("optional") and i["done"])
        assert d["launch_ready"] == (req_done == 4)

    def test_has_storefront_and_catalog(self, demo):
        d = demo.get(f"{BASE}/api/merchant/soft-launch/checklist", timeout=15).json()
        # demo owns a seeded storefront
        assert d["has_storefront"] is True
        assert isinstance(d["catalog_count"], int)


# ══════════════════════════ 5) TEASER (ADMIN) ════════════════════════
class TestTeaserStats:
    def test_non_admin_blocked_stats(self, anon):
        r = anon.get(f"{BASE}/api/admin/launch/teaser-stats", timeout=15)
        assert r.status_code in (401, 403)

    def test_non_admin_blocked_stats_as_demo(self, demo):
        r = demo.get(f"{BASE}/api/admin/launch/teaser-stats", timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_stats_shape(self, admin):
        r = admin.get(f"{BASE}/api/admin/launch/teaser-stats", timeout=15)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ("total", "teased", "eligible_now"):
            assert k in d and isinstance(d[k], int)


class TestTeaserSend:
    def test_non_admin_blocked_send(self, anon):
        r = anon.post(f"{BASE}/api/admin/launch/teaser", timeout=15)
        assert r.status_code in (401, 403)

    def test_non_admin_blocked_send_as_demo(self, demo):
        r = demo.post(f"{BASE}/api/admin/launch/teaser", timeout=15)
        assert r.status_code in (401, 403)

    def test_seed_and_send_and_idempotent(self, anon, admin):
        # Seed a fresh throwaway @example.com waitlister (not launched_notified)
        email = f"TEST_iter146_teaser_{uuid.uuid4().hex[:8]}@example.com"
        r = anon.post(f"{BASE}/api/waitlist", json={"email": email}, timeout=15)
        assert r.status_code == 200

        stats_before = admin.get(f"{BASE}/api/admin/launch/teaser-stats", timeout=15).json()
        assert stats_before["eligible_now"] >= 1, \
            f"expected our seeded @example.com row to be eligible; stats={stats_before}"

        # First send
        r1 = admin.post(f"{BASE}/api/admin/launch/teaser", timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        d1 = r1.json()
        assert d1.get("ok") is True
        assert isinstance(d1.get("processed"), int)
        assert d1["processed"] >= 1

        # Second send within 48h → idempotent → 0 (or at least less than first)
        r2 = admin.post(f"{BASE}/api/admin/launch/teaser", timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        # Idempotency: same seed row must NOT be re-sent
        assert d2["processed"] == 0, \
            f"teaser not idempotent within 48h: 2nd send processed={d2['processed']}"

        # eligible_now must go down after first send
        stats_after = admin.get(f"{BASE}/api/admin/launch/teaser-stats", timeout=15).json()
        assert stats_after["eligible_now"] < stats_before["eligible_now"]
        assert stats_after["teased"] >= stats_before["teased"] + 1


# ══════════════════════════ 6) REGRESSION ═════════════════════════════
class TestRegression:
    def test_launch_status_exposes_launch_at(self, anon):
        r = anon.get(f"{BASE}/api/launch/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "launch_at" in d
        assert "business_setup_mode" in d
        assert "waitlist_enabled" in d
        assert "offer_months" in d

    def test_waitlist_idempotent_no_double_credit(self, anon):
        owner_email = f"TEST_iter146_regowner_{uuid.uuid4().hex[:8]}@example.com"
        owner = anon.post(f"{BASE}/api/waitlist", json={"email": owner_email}, timeout=15).json()
        code = owner["ref_code"]
        ref_email = f"TEST_iter146_regref_{uuid.uuid4().hex[:8]}@example.com"
        first = anon.post(f"{BASE}/api/waitlist",
                          json={"email": ref_email, "ref": code}, timeout=15).json()
        assert first["already"] is False
        after1 = anon.get(f"{BASE}/api/waitlist/position?code={code}", timeout=15).json()
        # Re-submit SAME email + same ref → must be already:true and NO double-credit
        second = anon.post(f"{BASE}/api/waitlist",
                           json={"email": ref_email, "ref": code}, timeout=15).json()
        assert second["already"] is True
        after2 = anon.get(f"{BASE}/api/waitlist/position?code={code}", timeout=15).json()
        assert after2["referrals"] == after1["referrals"], \
            "double-credit on re-submit"

    def test_invalid_email_400(self, anon):
        r = anon.post(f"{BASE}/api/waitlist", json={"email": "not-an-email"}, timeout=15)
        assert r.status_code == 400

    def test_position_missing_code_400(self, anon):
        r = anon.get(f"{BASE}/api/waitlist/position", timeout=15)
        assert r.status_code == 400

    def test_merchant_claim_idempotent(self, demo):
        r1 = demo.post(f"{BASE}/api/merchant/soft-launch/claim", timeout=15)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1.get("ok") is True
        r2 = demo.post(f"{BASE}/api/merchant/soft-launch/claim", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("already") is True

    def test_shell_home_gating(self, anon, admin):
        # Turn mode ON
        p = admin.patch(f"{BASE}/api/admin/launch-settings",
                        json={"business_setup_mode_enabled": True}, timeout=15)
        assert p.status_code == 200
        try:
            # Guard cache TTL ~10s
            time.sleep(11)
            r_anon = anon.get(f"{BASE}/api/shell/home", timeout=15)
            assert r_anon.status_code == 423, \
                f"expected 423 gated, got {r_anon.status_code}"
            r_admin = admin.get(f"{BASE}/api/shell/home", timeout=15)
            assert r_admin.status_code == 200, \
                f"admin should bypass; got {r_admin.status_code}"
        finally:
            # Turn mode OFF (this may fire launch email — only @example.com seeds affected)
            off = admin.patch(f"{BASE}/api/admin/launch-settings",
                              json={"business_setup_mode_enabled": False}, timeout=15)
            assert off.status_code == 200
            time.sleep(11)
