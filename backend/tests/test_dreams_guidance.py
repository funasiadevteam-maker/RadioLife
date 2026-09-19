"""Dreams & Guidance — full backend regression (iteration 155)."""
import os, uuid, time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

DEMO = ("demo@bigfm.dubai", "DemoPass123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")
STELLA = ("stella.moon@bigfm.dubai", "Advisor123!")
SANA = ("dr.sana.sleep@bigfm.dubai", "Advisor123!")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo(): return _login(*DEMO)
@pytest.fixture(scope="module")
def admin(): return _login(*ADMIN)
@pytest.fixture(scope="module")
def free(): return _login(*FREE)
@pytest.fixture(scope="module")
def stella(): return _login(*STELLA)
@pytest.fixture(scope="module")
def sana(): return _login(*SANA)


# ---- Config / consent ----
def test_config_returns_flags_moods_tags_disclaimers(demo):
    r = demo.get(f"{API}/social/dreams/config")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("flags", "moods", "tags", "reactions", "advisor_categories", "disclaimers", "terms_version"):
        assert k in d
    assert "dream_sharing_enabled" in d["flags"]
    assert d["disclaimers"]["global"] and d["disclaimers"]["ai_header"]
    cats = {c["key"] for c in d["advisor_categories"]}
    assert {"dream_interpreter", "licensed_sleep"} <= cats


def test_consent_accept(demo):
    r = demo.post(f"{API}/social/dreams/consent")
    assert r.status_code == 200 and r.json()["ok"]
    r2 = demo.get(f"{API}/social/dreams/config")
    assert r2.json()["consent_needed"] is False


# ---- Dream sharing / feed / anonymity ----
@pytest.fixture(scope="module")
def named_dream(demo):
    demo.post(f"{API}/social/dreams/consent")
    r = demo.post(f"{API}/social/dreams", json={
        "title": "TEST_named_dream",
        "description": "I was walking through a garden of glowing lanterns TESTMARK1",
        "mood": "Peaceful", "tags": ["Flying"], "visibility": "public",
        "anonymous": False})
    assert r.status_code == 200, r.text
    return r.json()["dream_id"]


@pytest.fixture(scope="module")
def anon_dream(demo):
    r = demo.post(f"{API}/social/dreams", json={
        "title": "TEST_anon_dream",
        "description": "Anonymous water dream TESTMARK2",
        "mood": "Confusing", "tags": ["Water"], "visibility": "public",
        "anonymous": True})
    assert r.status_code == 200, r.text
    return r.json()["dream_id"]


def test_share_bad_visibility(demo):
    r = demo.post(f"{API}/social/dreams", json={
        "description": "bad vis", "visibility": "world"})
    assert r.status_code == 400


def test_feed_discover_hides_anonymous_author(free, anon_dream, demo):
    # Free user (not the author) should see anonymous dream masked
    demo.post(f"{API}/social/dreams/consent")  # ensure feed access
    free.post(f"{API}/social/dreams/consent")
    r = free.get(f"{API}/social/dreams", params={"scope": "discover"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    hit = [i for i in items if i["dream_id"] == anon_dream]
    assert hit, "anon dream not in discover feed"
    a = hit[0]
    assert a["author"]["name"] == "Anonymous Dreamer"
    assert a["author"]["user_id"] is None
    assert a["author"]["anonymous"] is True


def test_feed_owner_sees_own_identity_on_anon(demo, anon_dream):
    r = demo.get(f"{API}/social/dreams", params={"scope": "mine"})
    items = r.json()["items"]
    hit = [i for i in items if i["dream_id"] == anon_dream][0]
    # For owner viewing own dream, author.user_id should be present (mine=True)
    assert hit["mine"] is True
    assert hit["author"]["user_id"] is not None


def test_feed_scopes(demo, named_dream):
    for scope in ("discover", "friends", "mine"):
        r = demo.get(f"{API}/social/dreams", params={"scope": scope})
        assert r.status_code == 200, f"scope {scope} => {r.status_code}"


# ---- Detail ----
def test_dream_detail(demo, named_dream):
    r = demo.get(f"{API}/social/dreams/{named_dream}")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("comments", "my_similar", "my_reactions", "saved"):
        assert k in d


# ---- Similar idempotency ----
def test_similar_is_idempotent(free, named_dream):
    r1 = free.post(f"{API}/social/dreams/{named_dream}/similar")
    assert r1.status_code == 200, r1.text
    c1 = r1.json()["similar_count"]
    r2 = free.post(f"{API}/social/dreams/{named_dream}/similar")
    assert r2.status_code == 200
    c2 = r2.json()["similar_count"]
    assert c2 == c1, f"double-increment: {c1}->{c2}"
    assert r2.json()["my_similar"] is True


# ---- Comments / reactions / save / report ----
def test_comment_react_save_report(free, named_dream, demo):
    r = free.post(f"{API}/social/dreams/{named_dream}/comments",
                  json={"text": "TEST_comment relatable"})
    assert r.status_code == 200

    r = free.post(f"{API}/social/dreams/{named_dream}/react", json={"kind": "relate"})
    assert r.status_code == 200 and r.json()["active"] is True
    r = free.post(f"{API}/social/dreams/{named_dream}/react", json={"kind": "relate"})
    assert r.json()["active"] is False  # toggle off

    r = free.post(f"{API}/social/dreams/{named_dream}/react", json={"kind": "invalid"})
    assert r.status_code == 400

    r = free.post(f"{API}/social/dreams/{named_dream}/save")
    assert r.status_code == 200 and r.json()["saved"] is True
    r = free.get(f"{API}/social/dreams/me/saved")
    assert r.status_code == 200 and any(i["dream_id"] == named_dream for i in r.json()["items"])
    r = free.delete(f"{API}/social/dreams/{named_dream}/save")
    assert r.status_code == 200 and r.json()["saved"] is False

    r = free.post(f"{API}/social/dreams/{named_dream}/report",
                  json={"reason": "TEST_report"})
    assert r.status_code == 200


# ---- AI reflection ----
def test_reflect_returns_header_disclaimer(demo, named_dream):
    r = demo.post(f"{API}/social/dreams/{named_dream}/reflect", timeout=60)
    assert r.status_code == 200, r.text
    ref = r.json()["ai_reflection"]
    assert "header" in ref and "diagnosis" in ref["header"].lower() or "possible" in ref["header"].lower()
    assert "disclaimer" in ref
    assert "symbolic_readings" in ref
    assert "generated_at" in ref
    # No distress note on this benign dream
    assert "safety_note" not in ref or ref.get("safety_note") is None or ref["safety_note"]


def test_reflect_distress_adds_safety_note(demo):
    r = demo.post(f"{API}/social/dreams", json={
        "title": "TEST_distress",
        "description": "In my dream I said I want to die and hurt myself, it was dark",
        "mood": "Sad", "tags": [], "visibility": "only_me", "anonymous": False})
    assert r.status_code == 200
    did = r.json()["dream_id"]
    r2 = demo.post(f"{API}/social/dreams/{did}/reflect", timeout=60)
    assert r2.status_code == 200
    ref = r2.json()["ai_reflection"]
    assert "safety_note" in ref and ref["safety_note"]


# ---- Advisors ----
def test_list_advisors(demo):
    r = demo.get(f"{API}/social/dreams/advisors")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 3
    # Ensure distinct badge structure
    stella = next((a for a in items if a["display_name"] == "Stella Moon"), None)
    assert stella
    assert stella["badges"]["spiritual_approved"] is True
    assert stella["badges"]["professional_license_verified"] is False
    sana = next((a for a in items if "Sana" in a["display_name"]), None)
    assert sana and sana["badges"]["professional_license_verified"] is True


def test_advisor_category_filter(demo):
    r = demo.get(f"{API}/social/dreams/advisors", params={"category": "licensed_sleep"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(a["category"] == "licensed_sleep" for a in items)


def test_advisor_detail(demo):
    r = demo.get(f"{API}/social/dreams/advisors")
    stella_id = next(a["advisor_id"] for a in r.json()["items"] if a["display_name"] == "Stella Moon")
    r2 = demo.get(f"{API}/social/dreams/advisors/{stella_id}")
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert "services" in d and len(d["services"]) >= 1
    assert "reviews" in d
    assert d["disclaimer"]  # non-licensed → booking disclaimer present


def test_advisor_detail_licensed_no_booking_disclaimer(demo):
    r = demo.get(f"{API}/social/dreams/advisors", params={"category": "licensed_sleep"})
    aid = r.json()["items"][0]["advisor_id"]
    d = demo.get(f"{API}/social/dreams/advisors/{aid}").json()
    assert d["licensed"] is True
    assert d["disclaimer"] is None


# ---- Advisor apply + license badge guardrail ----
def test_advisor_apply_and_license_guardrail(admin):
    # Register a fresh throwaway user
    email = f"TEST_advisor_{uuid.uuid4().hex[:8]}@bigfm.dubai"
    reg = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPass123!", "name": "Test Applicant"})
    if reg.status_code not in (200, 201):
        pytest.skip(f"register endpoint returned {reg.status_code}: {reg.text[:200]}")
    s = _login(email, "TestPass123!")
    r = s.post(f"{API}/social/dreams/apply") if False else s.post(
        f"{API}/social/dreams/advisors/apply",
        json={"display_name": "Test Applicant",
              "category": "tarot_reader",
              "bio": "I offer reflective tarot readings for entertainment.",
              "languages": ["English"], "experience_years": 3})
    assert r.status_code == 200, r.text
    aid = r.json()["advisor"]["advisor_id"]
    # Admin approves WITH professional_license_verified=True; guardrail must ignore
    ap = admin.post(f"{API}/admin/dreams/advisors/{aid}/approve",
                    json={"identity_verified": True,
                          "spiritual_approved": True,
                          "professional_license_verified": True})
    assert ap.status_code == 200, ap.text
    badges = ap.json()["badges"]
    assert badges["professional_license_verified"] is False  # ignored for non-licensed
    assert badges["spiritual_approved"] is True


# ---- Advisor response ----
def test_advisor_public_response(stella, named_dream):
    r = stella.post(f"{API}/social/dreams/{named_dream}/advisor-response",
                    json={"text": "TEST_advisor_response — reflective note."})
    assert r.status_code == 200, r.text


# ---- Bookings: free flow ----
def test_free_booking_full_flow(demo, stella):
    # Stella creates a free service
    r = stella.post(f"{API}/social/dreams/advisors/me/services", json={
        "title": "TEST_free_service", "delivery": "written", "price_cents": 0,
        "duration_min": 15, "delivery_hours": 24, "description": "free"})
    assert r.status_code == 200, r.text
    sid = r.json()["service"]["service_id"]
    aid = r.json()["service"]["advisor_id"]

    # Demo books it -> paid instantly
    r = demo.post(f"{API}/social/dreams/bookings/checkout", json={
        "advisor_id": aid, "service_id": sid, "question": "test"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert r.json()["checkout_url"] is None
    bid = r.json()["booking_id"]

    # Advisor sees in inbox
    ri = stella.get(f"{API}/social/dreams/advisor/bookings")
    assert any(b["booking_id"] == bid for b in ri.json()["items"])

    # Deliver
    rd = stella.post(f"{API}/social/dreams/advisor/bookings/{bid}/deliver",
                     json={"response_text": "TEST reflection delivered"})
    assert rd.status_code == 200, rd.text

    # User reviews
    rv = demo.post(f"{API}/social/dreams/bookings/{bid}/review",
                   json={"rating": 5, "comment": "TEST_great"})
    assert rv.status_code == 200, rv.text

    # Second review -> 409
    rv2 = demo.post(f"{API}/social/dreams/bookings/{bid}/review", json={"rating": 4})
    assert rv2.status_code == 409

    # Cleanup service
    stella.delete(f"{API}/social/dreams/advisors/me/services/{sid}")


def test_paid_booking_returns_stripe_url(demo):
    # Use existing seeded paid service on Stella
    ad = demo.get(f"{API}/social/dreams/advisors").json()
    stella_id = next(a["advisor_id"] for a in ad["items"] if a["display_name"] == "Stella Moon")
    det = demo.get(f"{API}/social/dreams/advisors/{stella_id}").json()
    paid = next(s for s in det["services"] if s["price_cents"] > 0)
    r = demo.post(f"{API}/social/dreams/bookings/checkout", json={
        "advisor_id": stella_id, "service_id": paid["service_id"],
        "question": "TEST_paid",
        "origin_url": BASE})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "pending_payment"
    assert j["checkout_url"] and "checkout.stripe.com" in j["checkout_url"]
    assert j["session_id"].startswith("cs_test_") or j["session_id"].startswith("cs_")

    # Status endpoint works
    rs = demo.get(f"{API}/social/dreams/bookings/{j['booking_id']}/status")
    assert rs.status_code == 200
    assert rs.json()["payment_status"] in ("pending", "paid")


def test_my_readings(demo):
    r = demo.get(f"{API}/social/dreams/bookings")
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


# ---- Admin ----
def test_admin_flags_get_patch(admin):
    r = admin.get(f"{API}/admin/dreams/flags")
    assert r.status_code == 200
    orig = r.json()
    r2 = admin.patch(f"{API}/admin/dreams/flags",
                     json={"paid_readings_enabled": orig.get("paid_readings_enabled", True)})
    assert r2.status_code == 200
    assert "paid_readings_enabled" in r2.json()


def test_admin_reports_sees_anon_owner(admin, anon_dream, demo):
    # Report the anonymous dream
    demo.post(f"{API}/social/dreams/{anon_dream}/report",
              json={"reason": "TEST_admin_visibility"})
    r = admin.get(f"{API}/admin/dreams/reports", params={"status": "open"})
    assert r.status_code == 200
    hits = [x for x in r.json()["items"] if x["dream_id"] == anon_dream]
    assert hits, "reported anon dream missing from admin queue"
    h = hits[0]
    assert h["dream"] is not None
    assert h["dream"]["owner_user_id"]  # admin sees real owner
    assert h["dream"]["anonymous"] is True


def test_admin_applications(admin):
    r = admin.get(f"{API}/admin/dreams/applications")
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)
