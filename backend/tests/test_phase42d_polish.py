"""Phase 42-D Polish Bundle backend tests (D1/D2/D3 + regression guard)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO = ("demo@bigfm.dubai", "DemoPass123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
PREDICT = ("predictest@bigfm.dubai", "PredictTest123!")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("access_token") or j.get("token") or j.get("session_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ─── D1: Channel thumbnails ───────────────────────────────────────
@pytest.mark.parametrize("slug", [
    "bollywood_mehfil", "vip_lounge", "party_dubai", "late_night_drive"])
def test_d1_channel_thumbnail_200(slug):
    r = requests.head(f"{BASE_URL}/api/static/channel_thumbnails/{slug}.webp",
                      allow_redirects=True, timeout=15)
    if r.status_code == 405:  # HEAD not allowed → try GET
        r = requests.get(f"{BASE_URL}/api/static/channel_thumbnails/{slug}.webp",
                          timeout=15, stream=True)
    assert r.status_code == 200, f"{slug}.webp expected 200, got {r.status_code}"


def test_d1_discover_returns_bigfm_ai_cards_with_slug_id():
    tok = _login(*DEMO)
    r = requests.get(f"{BASE_URL}/api/radio/discover", headers=_hdr(tok), timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # Look in any nested rail for AI cards
    found_party_dubai = None
    def _walk(obj):
        nonlocal found_party_dubai
        if isinstance(obj, dict):
            if obj.get("id") == "party_dubai":
                found_party_dubai = obj
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(data)
    assert found_party_dubai is not None, "party_dubai AI card not found in /api/radio/discover"
    fav = found_party_dubai.get("favicon") or found_party_dubai.get("thumbnail_url")
    assert fav and "party_dubai" in fav and fav.endswith(".webp"), (
        f"party_dubai favicon malformed: {fav}")


# ─── D2: start_premium_trial structured response ──────────────────
def test_d2_start_trial_demo_already_active_or_consumed():
    tok = _login(*DEMO)
    r = requests.post(f"{BASE_URL}/api/billing/start_premium_trial",
                      headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    d = r.json()
    assert "state" in d and "ok" in d and "is_premium_or_trial" in d
    assert d["state"] in ("already_active", "already_consumed", "started", "upgrade_required")


def test_d2_start_trial_admin_already_active():
    tok = _login(*ADMIN)
    r = requests.post(f"{BASE_URL}/api/billing/start_premium_trial",
                      headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] in ("already_active", "already_consumed", "started", "upgrade_required")


def test_d2_start_trial_fresh_user_started():
    """Register a brand-new user and verify 'started' state."""
    email = f"qa_42d_{uuid.uuid4().hex[:10]}@bigfm.dubai"
    reg = requests.post(f"{BASE_URL}/api/auth/register",
                        json={"email": email, "password": "FreshPass123!",
                              "name": "QA Phase 42D"}, timeout=20)
    assert reg.status_code in (200, 201), f"register failed: {reg.status_code} {reg.text}"
    tok = _login(email, "FreshPass123!")
    r = requests.post(f"{BASE_URL}/api/billing/start_premium_trial",
                      headers=_hdr(tok), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] in ("started", "already_active"), f"got state={d.get('state')} body={d}"
    assert d["is_premium_or_trial"] is True


# ─── D2: Admin grant ──────────────────────────────────────────────
def test_d2_admin_grant_non_admin_403():
    tok = _login(*DEMO)
    r = requests.post(f"{BASE_URL}/api/admin/subscriptions/grant",
                      headers=_hdr(tok),
                      json={"user_id": "user_demo_8b88c27e0f",
                            "plan": "trial", "duration_days": 7}, timeout=20)
    assert r.status_code in (401, 403), f"non-admin expected 401/403, got {r.status_code}"


def test_d2_admin_grant_succeeds():
    tok = _login(*ADMIN)
    # First find demo user_id
    me_demo_tok = _login(*DEMO)
    me = requests.get(f"{BASE_URL}/api/users/me", headers=_hdr(me_demo_tok), timeout=15)
    demo_uid = (me.json().get("user_id") if me.status_code == 200 else "user_demo_8b88c27e0f")
    r = requests.post(f"{BASE_URL}/api/admin/subscriptions/grant",
                      headers=_hdr(tok),
                      json={"user_id": demo_uid, "plan": "trial",
                            "duration_days": 7}, timeout=20)
    assert r.status_code == 200, f"admin grant failed: {r.status_code} {r.text}"
    d = r.json()
    assert d.get("ok") is True and "expires_at" in d


# ─── D2: Voucher CRUD + redemption ────────────────────────────────
@pytest.fixture(scope="module")
def voucher_fixture():
    """Create a fresh voucher and yield (code, voucher_id, admin_tok)."""
    tok = _login(*ADMIN)
    r = requests.post(f"{BASE_URL}/api/admin/vouchers/create",
                      headers=_hdr(tok),
                      json={"plan": "premium", "duration_days": 7,
                            "max_redemptions": 5}, timeout=20)
    assert r.status_code == 200, f"voucher create failed: {r.status_code} {r.text}"
    d = r.json()
    assert d["code"].startswith("BIGFM-"), f"code format wrong: {d['code']}"
    yield (d["code"], d["voucher_id"], tok)


def test_d2_voucher_create_and_list(voucher_fixture):
    code, vid, tok = voucher_fixture
    r = requests.get(f"{BASE_URL}/api/admin/vouchers",
                    headers=_hdr(tok), timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert any(it.get("voucher_id") == vid for it in items)


def test_d2_voucher_redeem_then_409_on_reuse(voucher_fixture):
    code, vid, _admin_tok = voucher_fixture
    # Register a brand-new user to redeem the code
    email = f"qa_42d_redeem_{uuid.uuid4().hex[:8]}@bigfm.dubai"
    reg = requests.post(f"{BASE_URL}/api/auth/register",
                        json={"email": email, "password": "RedeemPass123!",
                              "name": "QA Redeem"}, timeout=20)
    assert reg.status_code in (200, 201)
    utok = _login(email, "RedeemPass123!")
    r1 = requests.post(f"{BASE_URL}/api/subscriptions/redeem-voucher",
                      headers=_hdr(utok), json={"code": code}, timeout=20)
    assert r1.status_code == 200, f"redeem failed: {r1.status_code} {r1.text}"
    d = r1.json()
    assert d["plan"] == "premium" and d["duration_days"] == 7 and "expires_at" in d
    # Same user reuse → 409
    r2 = requests.post(f"{BASE_URL}/api/subscriptions/redeem-voucher",
                      headers=_hdr(utok), json={"code": code}, timeout=20)
    assert r2.status_code == 409, f"reuse expected 409, got {r2.status_code} {r2.text}"
    detail = r2.json().get("detail")
    code_field = detail.get("code") if isinstance(detail, dict) else detail
    assert code_field == "voucher_already_redeemed"


def test_d2_voucher_exhausted_with_new_user():
    """Create max=1 voucher, redeem by user A, then user B → 410 exhausted."""
    atok = _login(*ADMIN)
    r = requests.post(f"{BASE_URL}/api/admin/vouchers/create",
                      headers=_hdr(atok),
                      json={"plan": "premium", "duration_days": 3,
                            "max_redemptions": 1}, timeout=15)
    assert r.status_code == 200
    code = r.json()["code"]
    # user A
    a_email = f"qa_42d_a_{uuid.uuid4().hex[:6]}@bigfm.dubai"
    requests.post(f"{BASE_URL}/api/auth/register",
                  json={"email": a_email, "password": "Pwd1234!", "name": "A"}, timeout=15)
    atok2 = _login(a_email, "Pwd1234!")
    ra = requests.post(f"{BASE_URL}/api/subscriptions/redeem-voucher",
                      headers=_hdr(atok2), json={"code": code}, timeout=15)
    assert ra.status_code == 200, ra.text
    # user B → exhausted
    b_email = f"qa_42d_b_{uuid.uuid4().hex[:6]}@bigfm.dubai"
    requests.post(f"{BASE_URL}/api/auth/register",
                  json={"email": b_email, "password": "Pwd1234!", "name": "B"}, timeout=15)
    btok = _login(b_email, "Pwd1234!")
    rb = requests.post(f"{BASE_URL}/api/subscriptions/redeem-voucher",
                      headers=_hdr(btok), json={"code": code}, timeout=15)
    assert rb.status_code == 410, f"expected 410 exhausted, got {rb.status_code} {rb.text}"
    detail = rb.json().get("detail")
    code_field = detail.get("code") if isinstance(detail, dict) else detail
    assert code_field == "voucher_exhausted"


def test_d2_voucher_revoke_then_redeem_410():
    atok = _login(*ADMIN)
    r = requests.post(f"{BASE_URL}/api/admin/vouchers/create",
                      headers=_hdr(atok),
                      json={"plan": "premium", "duration_days": 3,
                            "max_redemptions": 5}, timeout=15)
    assert r.status_code == 200
    v = r.json()
    rv = requests.post(f"{BASE_URL}/api/admin/vouchers/{v['voucher_id']}/revoke",
                      headers=_hdr(atok), timeout=15)
    assert rv.status_code == 200
    # Fresh user tries to redeem
    email = f"qa_42d_rev_{uuid.uuid4().hex[:6]}@bigfm.dubai"
    requests.post(f"{BASE_URL}/api/auth/register",
                  json={"email": email, "password": "Pwd1234!", "name": "R"}, timeout=15)
    utok = _login(email, "Pwd1234!")
    rd = requests.post(f"{BASE_URL}/api/subscriptions/redeem-voucher",
                      headers=_hdr(utok), json={"code": v["code"]}, timeout=15)
    assert rd.status_code == 410
    detail = rd.json().get("detail")
    code_field = detail.get("code") if isinstance(detail, dict) else detail
    assert code_field == "voucher_revoked"


# ─── D3: Station favorites ────────────────────────────────────────
def test_d3_favorite_station_bigfm_idempotent_and_schema():
    tok = _login(*DEMO)
    # Add bigfm
    payload = {"station_id": "bollywood_mehfil", "station_type": "bigfm"}
    r1 = requests.post(f"{BASE_URL}/api/me/favorite-stations",
                        headers=_hdr(tok), json=payload, timeout=15)
    assert r1.status_code == 200, r1.text
    # Second add → already_favorited
    r2 = requests.post(f"{BASE_URL}/api/me/favorite-stations",
                        headers=_hdr(tok), json=payload, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("already_favorited") is True
    # GET schema
    rg = requests.get(f"{BASE_URL}/api/me/favorite-stations",
                      headers=_hdr(tok), timeout=15)
    assert rg.status_code == 200
    items = rg.json().get("items", [])
    bm = next((i for i in items if i["station_id"] == "bollywood_mehfil"), None)
    assert bm is not None
    st = bm.get("station") or {}
    assert "name" in st and ("thumbnail_url" in st or "favicon" in st)
    # DELETE
    rd = requests.delete(f"{BASE_URL}/api/me/favorite-stations/bollywood_mehfil",
                          headers=_hdr(tok), timeout=15)
    assert rd.status_code == 200 and rd.json().get("removed") is True


def test_d3_favorite_imported_station():
    tok = _login(*DEMO)
    # Find an imported station from discover trending
    r = requests.get(f"{BASE_URL}/api/radio/discover", headers=_hdr(tok), timeout=30)
    assert r.status_code == 200
    imp_id = None
    def _walk(obj):
        nonlocal imp_id
        if imp_id: return
        if isinstance(obj, dict):
            sid = obj.get("id") or obj.get("station_id")
            if isinstance(sid, str) and sid.startswith("imp_"):
                imp_id = sid
                return
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
    _walk(r.json())
    if not imp_id:
        pytest.skip("no imported station id found in /api/radio/discover")
    payload = {"station_id": imp_id, "station_type": "imported"}
    r1 = requests.post(f"{BASE_URL}/api/me/favorite-stations",
                        headers=_hdr(tok), json=payload, timeout=15)
    assert r1.status_code == 200, r1.text
    rg = requests.get(f"{BASE_URL}/api/me/favorite-stations",
                      headers=_hdr(tok), timeout=15)
    items = rg.json().get("items", [])
    found = next((i for i in items if i["station_id"] == imp_id), None)
    assert found is not None
    st = found.get("station") or {}
    assert "name" in st
    # Cleanup
    requests.delete(f"{BASE_URL}/api/me/favorite-stations/{imp_id}",
                    headers=_hdr(tok), timeout=15)


# ─── Regression guard: OpenAPI schema includes all paths ──────────
def test_regression_openapi_paths():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=20)
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    expected = [
        "/api/admin/subscriptions/grant",
        "/api/admin/vouchers/create",
        "/api/admin/vouchers",
        "/api/admin/vouchers/{voucher_id}/revoke",
        "/api/subscriptions/redeem-voucher",
        "/api/me/favorite-stations",
        "/api/me/favorite-stations/{station_id}",
        "/api/billing/start_premium_trial",
    ]
    missing = [p for p in expected if p not in paths]
    assert not missing, f"missing paths in openapi: {missing}"
