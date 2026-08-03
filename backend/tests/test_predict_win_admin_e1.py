"""Sub-Phase E1 — Predict & Win Data Model + Admin Manual Campaign Builder acceptance tests."""
import os
import re
import time
import pytest
import requests
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
_be = dotenv_values("/app/backend/.env")
BASE_URL = (_fe.get("REACT_APP_BACKEND_URL") or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
os.environ.setdefault("MONGO_URL", _be.get("MONGO_URL", ""))
os.environ.setdefault("DB_NAME", _be.get("DB_NAME", ""))
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO)


# ---------- auth + listing ----------
class TestAuthAndListing:
    def test_list_unauthenticated_returns_401(self):
        r = requests.get(f"{API}/admin/predict-win/campaigns", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code} {r.text[:200]}"

    def test_admin_list_returns_items(self, admin_session):
        r = admin_session.get(f"{API}/admin/predict-win/campaigns", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)

    def test_demo_user_forbidden(self, demo_session):
        r = demo_session.get(f"{API}/admin/predict-win/campaigns", timeout=30)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"


# ---------- event types ----------
class TestEventTypes:
    def test_event_types_exact_seven_and_disabled_flag(self, admin_session):
        r = admin_session.get(f"{API}/admin/predict-win/event-types", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("event_types") if isinstance(body, dict) else body
        assert isinstance(items, list)
        assert len(items) == 7, f"expected 7 event types, got {len(items)}: {items}"
        lsm = next((x for x in items if x.get("value") == "live_sports_moment" or x.get("key") == "live_sports_moment" or x.get("id") == "live_sports_moment"), None)
        assert lsm is not None, f"live_sports_moment missing: {items}"
        assert lsm.get("disabled") is True
        assert lsm.get("disabled_reason") == "Disabled pending legal review"


def _iso_future(minutes):
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _campaign_body(title, event_type="club_event", compliance_id=None):
    return {
        "title": title,
        "event_type": event_type,
        "question": {
            "prompt": "Who will win?",
            "answer_options": [
                {"id": "opt_1", "label": "Team A"},
                {"id": "opt_2", "label": "Team B"},
            ],
        },
        "start_time": _iso_future(2),
        "lock_time": _iso_future(30),
        "compliance_settings_id": compliance_id,
    }


# ---------- guardrails ----------
class TestGuardrails:
    def test_live_sports_moment_blocked_422(self, admin_session):
        payload = _campaign_body("TEST_E1_lsm campaign for sports", event_type="live_sports_moment")
        r = admin_session.post(f"{API}/admin/predict-win/campaigns", json=payload, timeout=30)
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text[:300]}"
        body = r.json()
        detail = body.get("detail", body)
        # detail can be dict or list
        if isinstance(detail, list):
            detail = detail[0] if detail else {}
        assert detail.get("code") == "event_type_disabled", f"unexpected detail: {body}"

    def test_forbidden_terminology_blocked_400(self, admin_session):
        payload = _campaign_body("Place your bet to win prize")
        r = admin_session.post(f"{API}/admin/predict-win/campaigns", json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:300]}"
        body = r.json()
        detail = body.get("detail", body)
        if isinstance(detail, list):
            detail = detail[0] if detail else {}
        assert detail.get("code") == "forbidden_terminology"
        assert detail.get("matched", "").lower() == "bet"


# ---------- happy path & rejection ----------
class TestHappyPathAndRejection:
    def _get_compliance_id(self, admin_session):
        # Try GET first, create if missing
        r = admin_session.get(f"{API}/admin/predict-win/compliance", timeout=30)
        if r.status_code == 200:
            body = r.json()
            items = body.get("items") if isinstance(body, dict) else body
            if items:
                for it in items:
                    if it.get("is_default"):
                        return it.get("id") or it.get("_id") or it.get("compliance_id")
                return items[0].get("id") or items[0].get("_id") or items[0].get("compliance_id")
        # else create one
        r = admin_session.post(f"{API}/admin/predict-win/compliance", json={
            "name": "TEST_E1_compliance",
            "jurisdiction": "UAE",
            "is_default": False,
            "disclaimer_text": "Free contest. No purchase required.",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        return body.get("id") or body.get("_id") or body.get("compliance_id")

    @pytest.fixture(scope="class")
    def compliance_id(self, admin_session):
        return self._get_compliance_id(admin_session)

    def test_full_happy_path(self, admin_session, compliance_id):
        payload = _campaign_body(f"TEST_E1_happy_{int(time.time())}", compliance_id=compliance_id)
        r = admin_session.post(f"{API}/admin/predict-win/campaigns", json=payload, timeout=30)
        assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:400]}"
        camp = r.json()
        camp = camp.get("campaign", camp)
        cid = camp.get("campaign_id") or camp.get("id") or camp.get("_id")
        assert cid

        # Submit-approval before prize => 400 prize_required
        rs = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/submit-approval", timeout=30)
        assert rs.status_code == 400, f"expected 400 got {rs.status_code} {rs.text[:300]}"
        d = rs.json().get("detail", rs.json())
        if isinstance(d, list):
            d = d[0] if d else {}
        assert d.get("code") == "prize_required"

        # Add prize
        pr = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/prizes", json={
            "title": "TEST_E1_prize",
            "quantity": 1,
            "rank": 1,
        }, timeout=30)
        assert pr.status_code in (200, 201), f"prize add failed: {pr.status_code} {pr.text[:300]}"

        # Submit again
        rs2 = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/submit-approval", timeout=30)
        assert rs2.status_code == 200, f"submit failed: {rs2.status_code} {rs2.text[:300]}"
        assert rs2.json().get("approval_status") == "pending_review"

        # Approve
        ra = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/approve", timeout=30)
        assert ra.status_code == 200, f"approve failed: {ra.status_code} {ra.text[:300]}"
        body_a = ra.json()
        assert body_a.get("approval_status") == "approved"
        assert body_a.get("status") == "scheduled"

        # State guards
        re_edit = admin_session.patch(f"{API}/admin/predict-win/campaigns/{cid}", json={"title": "modified"}, timeout=30)
        assert re_edit.status_code == 409, f"expected 409 lock got {re_edit.status_code} {re_edit.text[:200]}"
        d2 = re_edit.json().get("detail", re_edit.json())
        if isinstance(d2, list):
            d2 = d2[0] if d2 else {}
        assert d2.get("code") == "campaign_locked_for_edit"

        re_sub = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/submit-approval", timeout=30)
        assert re_sub.status_code == 409

        # Force-resolve on scheduled => 409
        fr = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/force-resolve", json={
            "winning_option_id": "opt_1", "audit_notes": "manual", "data_source_url": None}, timeout=30)
        assert fr.status_code == 409, f"expected 409 got {fr.status_code} {fr.text[:200]}"

    def test_rejection_and_autobounce(self, admin_session, compliance_id):
        payload = _campaign_body(f"TEST_E1_reject_{int(time.time())}", compliance_id=compliance_id)
        r = admin_session.post(f"{API}/admin/predict-win/campaigns", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        jr = r.json(); jr = jr.get("campaign", jr); cid = jr.get("campaign_id") or jr.get("id") or jr.get("_id")

        # add prize
        admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/prizes", json={"title": "p", "quantity": 1, "rank": 1}, timeout=30)
        # submit
        s = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/submit-approval", timeout=30)
        assert s.status_code == 200, s.text
        # reject
        rj = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/reject", json={"reason": "TEST_E1 reason"}, timeout=30)
        assert rj.status_code == 200, rj.text
        body = rj.json()
        assert body.get("approval_status") == "rejected"
        assert body.get("status") == "draft"

        # patch with new title => auto-bounce to draft, clear rejected fields
        p = admin_session.patch(f"{API}/admin/predict-win/campaigns/{cid}", json={"title": f"TEST_E1_reject_edited_{int(time.time())}"}, timeout=30)
        assert p.status_code == 200, f"patch after reject failed: {p.status_code} {p.text[:300]}"
        body2 = p.json()
        assert body2.get("approval_status") == "draft", body2
        for f in ("rejected_at", "rejected_by", "approval_reason"):
            v = body2.get(f)
            assert v in (None, "", 0), f"field {f} not cleared: {v}"

    def test_force_resolve_on_draft_409(self, admin_session, compliance_id):
        payload = _campaign_body(f"TEST_E1_draft_{int(time.time())}", compliance_id=compliance_id)
        r = admin_session.post(f"{API}/admin/predict-win/campaigns", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        jr = r.json(); jr = jr.get("campaign", jr); cid = jr.get("campaign_id") or jr.get("id") or jr.get("_id")
        fr = admin_session.post(f"{API}/admin/predict-win/campaigns/{cid}/force-resolve", json={
            "winning_option_id": "opt_1", "audit_notes": "manual", "data_source_url": None}, timeout=30)
        assert fr.status_code == 409


# ---------- approval queue ----------
class TestApprovalQueue:
    def test_queue_only_pending(self, admin_session):
        r = admin_session.get(f"{API}/admin/predict-win/approval-queue", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        items = body.get("items") if isinstance(body, dict) else body
        assert isinstance(items, list)
        for it in items:
            assert it.get("approval_status") == "pending_review", f"non-pending in queue: {it}"


# ---------- indexes & seed ----------
class TestIndexesAndSeed:
    EXPECTED = [
        "prediction_data_providers",
        "prediction_markets_external",
        "predict_win_campaigns",
        "predict_win_prizes",
        "predict_win_entries",
        "predict_win_resolutions",
        "predict_win_awards",
        "predict_win_tv_displays",
        "predict_win_analytics_events",
        "prediction_compliance_settings",
        "prediction_api_logs",
        "predict_win_winner_rules",
    ]

    def test_collections_and_indexes(self):
        from pymongo import MongoClient
        url = os.environ.get("MONGO_URL")
        dbname = os.environ.get("DB_NAME")
        assert url and dbname
        cli = MongoClient(url)
        db = cli[dbname]
        existing = set(db.list_collection_names())
        for name in self.EXPECTED:
            assert name in existing, f"collection missing: {name}"
            idx = db[name].index_information()
            # require at least one non-_id index
            non_id = [k for k in idx.keys() if k != "_id_"]
            assert len(non_id) >= 1, f"collection {name} has no extra indexes: {list(idx.keys())}"

    def test_manual_provider_seeded(self):
        from pymongo import MongoClient
        url = os.environ.get("MONGO_URL")
        dbname = os.environ.get("DB_NAME")
        cli = MongoClient(url)
        db = cli[dbname]
        row = db.prediction_data_providers.find_one({"provider_name": "manual"})
        assert row is not None, "manual provider row missing"
        assert row.get("active") is True


# ---------- frontend lexicon grep ----------
class TestFrontendLexicon:
    def test_no_forbidden_terms_in_predictwin_jsx(self):
        path = "/app/frontend/src/Admin/PredictWinCampaigns.jsx"
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        # remove single-line and block comments to avoid false positives
        no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        pattern = re.compile(r"\bbet\b|\bwager\b|\bgamble\b|spread.*betting|order.book|buy.*shares|sell.*shares", re.IGNORECASE)
        matches = pattern.findall(no_line)
        assert not matches, f"forbidden terms found: {matches}"
