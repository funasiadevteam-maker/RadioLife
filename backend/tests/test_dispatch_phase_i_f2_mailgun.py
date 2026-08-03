"""Tests for UX.1 + Phase I (Business Portal) + F-2 (Ledger flip) + Mailgun webhook."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
BIZ = ("test@bigfm.dubai", "TestUser123!")
DEMO = ("demo@bigfm.dubai", "DemoPass123!")


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


# ---------- Regression: basic ----------
def test_login_demo():
    s = _login(*DEMO)
    r = s.get(f"{BASE}/api/me/points", timeout=10)
    assert r.status_code == 200


def test_now_playing():
    r = requests.get(f"{BASE}/api/community/now_playing", timeout=10)
    assert r.status_code == 200


def test_news_headlines():
    r = requests.get(f"{BASE}/api/news/headlines?market=dubai", timeout=15)
    assert r.status_code == 200


def test_ai_rj_cadence():
    s = _login(*DEMO)
    r = s.get(f"{BASE}/api/ai-rj/segment/cadence", timeout=10)
    assert r.status_code == 200


# ---------- Phase F-2 — Ledger flip ----------
def test_parity_check_admin():
    s = _login(*ADMIN)
    r = s.get(f"{BASE}/api/admin/points/parity-check?limit=5", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("ledger_authoritative") is True
    assert data.get("scanned", 0) >= 1
    assert data.get("drift_count", 99) == 0


def test_bigcoin_me_matches_points_me():
    s = _login(*DEMO)
    a = s.get(f"{BASE}/api/bigcoin/me", timeout=10).json()
    b = s.get(f"{BASE}/api/me/points", timeout=10).json()
    bal_a = a.get("balance")
    bal_b = b.get("balance")
    assert bal_a == bal_b, f"bigcoin/me={bal_a} vs me/points={bal_b}"


# ---------- Phase I — Business portal ----------
def test_business_me():
    s = _login(*BIZ)
    r = s.get(f"{BASE}/api/business/me", timeout=10)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get("name") == "Karak Cafe (QA fixture)"
    assert d.get("verified") is True


def test_business_dashboard_stats_periods():
    s = _login(*BIZ)
    for p in ("today", "week", "month"):
        r = s.get(f"{BASE}/api/business/dashboard/stats?period={p}", timeout=10)
        assert r.status_code == 200, f"period={p}: {r.status_code} {r.text[:200]}"


def test_business_coupon_validate_notfound():
    s = _login(*BIZ)
    r = s.post(f"{BASE}/api/business/coupons/validate",
               json={"code": "NONEXISTENT-XYZ"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d.get("valid") is False
    assert d.get("reason") == "code_not_found"


def test_business_coupon_redeem_notfound():
    s = _login(*BIZ)
    r = s.post(f"{BASE}/api/business/coupons/redeem",
               json={"code": "NONEXISTENT-XYZ", "terminal_pin": "4242"}, timeout=10)
    assert r.status_code == 404
    body = r.json()
    detail = body.get("detail", body)
    txt = str(detail).lower()
    assert "code_not_found" in txt or "not_found" in txt


def test_business_coupon_redeem_bad_pin():
    s = _login(*BIZ)
    r = s.post(f"{BASE}/api/business/coupons/redeem",
               json={"code": "ANYCODE", "terminal_pin": "0000"}, timeout=10)
    assert r.status_code == 401
    txt = str(r.json()).lower()
    assert "bad_pin" in txt or "pin" in txt


def test_business_campaigns_list():
    s = _login(*BIZ)
    r = s.get(f"{BASE}/api/business/campaigns", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d


def test_business_ads_buy_start():
    s = _login(*BIZ)
    r = s.post(f"{BASE}/api/business/campaigns/buy/start",
               json={"placement": "miniplayer"}, timeout=10)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert "deep_link" in d or "url" in d or "redirect" in d


# ---------- Mailgun webhook ----------
def test_mailgun_webhook_ingest_and_admin_endpoints():
    ts = int(time.time())
    payload = {
        "signature": {"timestamp": str(ts), "token": "tok_abc", "signature": "deadbeef"},
        "event-data": {
            "event": "delivered",
            "timestamp": ts,
            "recipient": "qa@test.local",
            "message": {"headers": {"message-id": f"<test_{ts}@x>"}},
            "tags": ["smoke"],
        },
    }
    r = requests.post(f"{BASE}/api/webhooks/mailgun/events", json=payload, timeout=15)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("ok") is True
    assert d.get("event_id", "").startswith("mevt_")
    assert d.get("event_type") == "delivered"

    s = _login(*ADMIN)
    r2 = s.get(f"{BASE}/api/admin/mail/events?since_hours=1", timeout=15)
    assert r2.status_code == 200
    d2 = r2.json()
    count = d2.get("count", len(d2.get("items", [])))
    assert count >= 1
    items = d2.get("items", [])
    if items:
        first = items[0]
        assert "recipient_masked" in first or "recipient" not in first or "@" not in str(first.get("recipient", ""))

    r3 = s.get(f"{BASE}/api/admin/mail/funnel?period=week", timeout=15)
    assert r3.status_code == 200
    d3 = r3.json()
    for k in ("sent", "delivered", "opened", "clicked", "open_rate"):
        assert k in d3, f"missing key {k} in funnel response: {list(d3.keys())}"
