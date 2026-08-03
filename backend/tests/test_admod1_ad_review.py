"""
Phase ADMOD.1 — Ad Manager + Unified Creative Approval Workflow.

Covers:
  - /api/ad-pricing-hints public
  - Role assignment (admin -> ad_manager) + RBAC gating
  - Publish AD.4 -> review row created + auto-moderation
  - Approve / Reject / Require-changes flows
  - Bulk approve
  - Advertiser block/unblock (HTTP 403 code:advertiser_blocked)
  - Analytics & Audit log
  - Advertiser review-badges
  - OpenAPI listing
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
ADV_ID = "advv2_9fac10b21f5595"


# ── Helpers ─────────────────────────────────────────────────────────
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s, r.json()


@pytest.fixture(scope="module")
def admin():
    s, u = _login("admin@bigfm.dubai", "AdminPass123!")
    return {"session": s, "user": u}


@pytest.fixture(scope="module")
def demo():
    s, u = _login("demo@bigfm.dubai", "DemoPass123!")
    return {"session": s, "user": u}


def _publish_new_draft(demo_session, title="TEST ADMOD Coffee Deal"):
    payload = {
        "title": title,
        "description": "TEST ADMOD.1 benign copy",
        "terms": "Valid at participating locations. One per customer.",
        "sponsoring_merchant_id": "biz_sc5_test_activated",
        "cost_per_save_cents": 15,
        "total_inventory": 5,
        "retail_value_cents": 500,
        "category_tags": ["food", "cafe"],
    }
    r = demo_session.post(
        f"{BASE_URL}/api/advertiser/{ADV_ID}/coupon-campaigns",
        json=payload, timeout=15)
    assert r.status_code == 200, f"create draft failed: {r.status_code} {r.text}"
    cid = r.json().get("campaign_id") or r.json().get("_id") or r.json().get("id")
    assert cid, f"no campaign id in response: {r.json()}"
    p = demo_session.post(
        f"{BASE_URL}/api/advertiser/coupon-campaigns/{cid}/publish", timeout=20)
    return cid, p


def _get_pending_review_by_target(admin_session, target_id):
    r = admin_session.get(f"{BASE_URL}/api/ad-review/queue?status=pending&limit=200", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data.get("rows") or data.get("items") or (data if isinstance(data, list) else [])
    for row in rows:
        if row.get("target_id") == target_id:
            return row
    return None


# ── 1. Public pricing hints ─────────────────────────────────────────
def test_01_ad_pricing_hints_public():
    r = requests.get(f"{BASE_URL}/api/ad-pricing-hints", timeout=10)
    assert r.status_code == 200
    j = r.json()
    assert j.get("default_cents") == 15
    assert "categories" in j and isinstance(j["categories"], dict)
    assert "groups" in j and isinstance(j["groups"], list)
    assert j["categories"].get("food") == 10


# ── 2. Role gating ──────────────────────────────────────────────────
def test_02_role_assign_ad_manager_and_rbac(admin):
    # login test user first
    ts, tuser = _login("test@bigfm.dubai", "TestUser123!")
    original_role = tuser.get("role", "listener")
    uid = tuser["user_id"]

    # promote to ad_manager
    r = admin["session"].patch(
        f"{BASE_URL}/api/admin/users/{uid}/role",
        json={"new_role": "ad_manager", "reason": "ADMOD.1 test"}, timeout=15)
    assert r.status_code == 200, f"promotion failed: {r.status_code} {r.text}"

    # re-login as test user for fresh session/cookies (role in JWT/session)
    ts2, tuser2 = _login("test@bigfm.dubai", "TestUser123!")
    assert tuser2.get("role") == "ad_manager"

    # ad_manager CAN read review queue
    q = ts2.get(f"{BASE_URL}/api/ad-review/queue?limit=5", timeout=15)
    assert q.status_code == 200, f"ad_manager should access queue: {q.status_code} {q.text}"

    # ad_manager CANNOT access /api/admin/users
    u = ts2.get(f"{BASE_URL}/api/admin/users?limit=1", timeout=15)
    assert u.status_code == 403, f"ad_manager should NOT access users: {u.status_code}"

    # revert
    rr = admin["session"].patch(
        f"{BASE_URL}/api/admin/users/{uid}/role",
        json={"new_role": original_role, "reason": "revert ADMOD.1 test"}, timeout=15)
    assert rr.status_code == 200


# ── 3. Publish → creates pending review row + auto-moderation ───────
@pytest.fixture(scope="module")
def published_review(admin, demo):
    cid, p = _publish_new_draft(demo["session"], title="TEST ADMOD Coffee A")
    assert p.status_code == 200, f"publish failed: {p.status_code} {p.text}"
    pj = p.json()
    assert pj.get("status") == "pending_admin"
    time.sleep(1.0)  # allow moderation
    row = _get_pending_review_by_target(admin["session"], cid)
    assert row is not None, "review row not found for published campaign"
    return {"campaign_id": cid, "review": row}


def test_03_publish_creates_review_row(published_review):
    row = published_review["review"]
    assert row["ad_type"] == "coupon_campaign"
    assert row["review_status"] == "pending"
    mod = row.get("auto_moderation_result")
    assert mod is not None
    action = mod.get("action_taken")
    assert action in ("clean", "flagged", "error", "skipped", "empty_input", None), \
        f"unexpected action_taken={action}"


# ── 4. Approve flow ─────────────────────────────────────────────────
def test_04_approve_flow(admin, demo, published_review):
    rid = published_review["review"]["review_id"]
    cid = published_review["campaign_id"]
    r = admin["session"].post(
        f"{BASE_URL}/api/ad-review/queue/{rid}/approve",
        json={"notes": "clean"}, timeout=15)
    assert r.status_code == 200, f"approve failed: {r.status_code} {r.text}"

    # detail
    d = admin["session"].get(f"{BASE_URL}/api/ad-review/queue/{rid}", timeout=15)
    assert d.status_code == 200
    assert d.json().get("review_status") == "approved"

    # campaign should be live
    live = requests.get(f"{BASE_URL}/api/coupon-campaigns/live?market=AE&limit=200", timeout=15)
    assert live.status_code == 200
    ids = [c.get("campaign_id") for c in (live.json().get("items") or live.json().get("campaigns") or live.json() or [])]
    # Fallback: fetch advertiser list to confirm status
    adv_list = demo["session"].get(f"{BASE_URL}/api/advertiser/{ADV_ID}/coupon-campaigns", timeout=15)
    assert adv_list.status_code == 200
    items = adv_list.json().get("items") or adv_list.json().get("campaigns") or []
    match = [c for c in items if c.get("campaign_id") == cid]
    assert match, f"campaign {cid} not returned in advertiser list"
    assert match[0].get("status") == "live", f"campaign status={match[0].get('status')}, expected live"


# ── 5. Reject flow ──────────────────────────────────────────────────
def test_05_reject_flow(admin, demo):
    cid, p = _publish_new_draft(demo["session"], title="TEST ADMOD Reject B")
    assert p.status_code == 200
    time.sleep(0.8)
    row = _get_pending_review_by_target(admin["session"], cid)
    assert row is not None
    rid = row["review_id"]
    r = admin["session"].post(
        f"{BASE_URL}/api/ad-review/queue/{rid}/reject",
        json={"reason": "policy", "notes": "see brand"}, timeout=15)
    assert r.status_code == 200, r.text

    d = admin["session"].get(f"{BASE_URL}/api/ad-review/queue/{rid}", timeout=15)
    assert d.json().get("review_status") == "rejected"

    # advertiser badges show rejected
    b = demo["session"].get(
        f"{BASE_URL}/api/advertiser/{ADV_ID}/review-badges?ad_type=coupon_campaign", timeout=15)
    assert b.status_code == 200
    badges = b.json()
    # badges could be dict keyed by cid or list of objects
    if isinstance(badges, dict) and "badges" in badges:
        badges = badges["badges"]
    if isinstance(badges, dict):
        entry = badges.get(cid) or badges.get(str(cid))
    else:
        entry = next((x for x in badges if x.get("target_id") == cid or x.get("campaign_id") == cid), None)
    assert entry is not None, f"no badge for cid={cid} in {badges}"
    assert entry.get("review_status") == "rejected"
    assert (entry.get("reject_reason") or entry.get("reason")) == "policy"


# ── 6. Require-changes flow ─────────────────────────────────────────
def test_06_require_changes_and_resubmit(admin, demo):
    cid, p = _publish_new_draft(demo["session"], title="TEST ADMOD Changes C")
    assert p.status_code == 200
    time.sleep(0.8)
    row = _get_pending_review_by_target(admin["session"], cid)
    assert row is not None
    rid = row["review_id"]

    r = admin["session"].post(
        f"{BASE_URL}/api/ad-review/queue/{rid}/require-changes",
        json={"notes": "clarify terms"}, timeout=15)
    assert r.status_code == 200, r.text

    d = admin["session"].get(f"{BASE_URL}/api/ad-review/queue/{rid}", timeout=15)
    assert d.json().get("review_status") == "requires_changes"

    # target reverted to draft
    adv_list = demo["session"].get(f"{BASE_URL}/api/advertiser/{ADV_ID}/coupon-campaigns", timeout=15)
    items = adv_list.json().get("items") or adv_list.json().get("campaigns") or []
    m = next((c for c in items if c.get("campaign_id") == cid), None)
    assert m and m.get("status") == "draft", f"status={m and m.get('status')}"

    # advertiser patches + resubmits
    pt = demo["session"].patch(
        f"{BASE_URL}/api/advertiser/coupon-campaigns/{cid}",
        json={"terms": "Clarified: valid Mon-Fri 8am-4pm."}, timeout=15)
    assert pt.status_code == 200
    p2 = demo["session"].post(
        f"{BASE_URL}/api/advertiser/coupon-campaigns/{cid}/publish", timeout=15)
    assert p2.status_code == 200
    time.sleep(0.8)
    row2 = _get_pending_review_by_target(admin["session"], cid)
    assert row2 is not None, "no pending row after resubmit"


# ── 7. Bulk approve ─────────────────────────────────────────────────
def test_07_bulk_approve(admin, demo):
    ids = []
    for i in range(2):
        cid, p = _publish_new_draft(demo["session"], title=f"TEST ADMOD Bulk {i}")
        assert p.status_code == 200
        time.sleep(0.6)
        row = _get_pending_review_by_target(admin["session"], cid)
        assert row is not None
        ids.append(row["review_id"])
    r = admin["session"].post(
        f"{BASE_URL}/api/ad-review/queue/bulk-approve",
        json={"review_ids": ids, "notes": "batch"}, timeout=20)
    assert r.status_code == 200, r.text
    for rid in ids:
        d = admin["session"].get(f"{BASE_URL}/api/ad-review/queue/{rid}", timeout=15)
        assert d.json().get("review_status") == "approved"


# ── 8. Block / Unblock advertiser ───────────────────────────────────
def test_08_block_and_unblock_advertiser(admin, demo):
    # Block
    r = admin["session"].post(
        f"{BASE_URL}/api/ad-review/advertisers/{ADV_ID}/block",
        json={"reason": "test"}, timeout=15)
    assert r.status_code == 200, r.text

    # publish should fail with 403 advertiser_blocked
    payload = {
        "title": "TEST ADMOD Blocked",
        "description": "blocked path",
        "terms": "T",
        "cost_per_save_cents": 15,
        "total_inventory": 3,
        "category_tags": ["food"],
    }
    c = demo["session"].post(
        f"{BASE_URL}/api/advertiser/{ADV_ID}/coupon-campaigns",
        json=payload, timeout=15)
    # Create might succeed (draft) but publish must block
    if c.status_code == 200:
        cid = c.json().get("campaign_id")
        p = demo["session"].post(
            f"{BASE_URL}/api/advertiser/coupon-campaigns/{cid}/publish", timeout=15)
        assert p.status_code == 403, f"expected 403 got {p.status_code} {p.text}"
        detail = p.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "advertiser_blocked"
        else:
            assert "advertiser_blocked" in str(detail)

    # blocked list
    bl = admin["session"].get(f"{BASE_URL}/api/ad-review/blocked-advertisers", timeout=15)
    assert bl.status_code == 200
    lst = bl.json()
    ids = [x.get("advertiser_id") for x in (lst if isinstance(lst, list) else lst.get("items", []))]
    assert ADV_ID in ids

    # Unblock
    ru = admin["session"].post(
        f"{BASE_URL}/api/ad-review/advertisers/{ADV_ID}/unblock", timeout=15)
    assert ru.status_code == 200


# ── 9. Analytics ────────────────────────────────────────────────────
def test_09_analytics(admin):
    r = admin["session"].get(f"{BASE_URL}/api/ad-review/analytics", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("window_days", "by_status", "by_day"):
        assert k in j, f"missing {k}: keys={list(j)}"
    # by_status should have counts
    assert isinstance(j["by_status"], dict)


# ── 10. Audit log ───────────────────────────────────────────────────
def test_10_audit_log(admin):
    r = admin["session"].get(f"{BASE_URL}/api/ad-review/audit-log?limit=200", timeout=15)
    assert r.status_code == 200
    rows = r.json()
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("rows") or []
    actions = {row.get("action") for row in rows}
    # We ran approve, reject, require_changes, and block/unblock this session
    expected_any = {"approve", "reject", "require_changes", "advertiser_block", "advertiser_unblock", "submit", "resubmit"}
    assert actions & expected_any, f"no expected actions in audit: {actions}"


# ── 11. OpenAPI listing ─────────────────────────────────────────────
def test_11_openapi_endpoints_present():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
    assert r.status_code == 200
    paths = set((r.json().get("paths") or {}).keys())
    required = [
        "/api/ad-pricing-hints",
        "/api/ad-review/queue",
        "/api/ad-review/queue/{review_id}",
        "/api/ad-review/queue/{review_id}/approve",
        "/api/ad-review/queue/{review_id}/reject",
        "/api/ad-review/queue/{review_id}/require-changes",
        "/api/ad-review/queue/bulk-approve",
        "/api/ad-review/queue/bulk-reject",
        "/api/ad-review/analytics",
        "/api/ad-review/blocked-advertisers",
        "/api/ad-review/advertisers/{advertiser_id}/block",
        "/api/ad-review/advertisers/{advertiser_id}/unblock",
        "/api/ad-review/audit-log",
        "/api/advertiser/{advertiser_id}/review-badges",
    ]
    missing = [p for p in required if p not in paths and p.replace("{advertiser_id}", "{id}") not in paths]
    # Try variant param names
    still_missing = []
    for p in missing:
        found = False
        for cand in paths:
            # crude match by trailing path segments
            if cand.replace("{", "").replace("}", "").rstrip("/").split("/")[-3:] == p.replace("{", "").replace("}", "").rstrip("/").split("/")[-3:]:
                found = True; break
        if not found:
            still_missing.append(p)
    assert not still_missing, f"missing OpenAPI paths: {still_missing}"
