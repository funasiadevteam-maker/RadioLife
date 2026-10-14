"""iter_211 — DEAL COUNTDOWN (/social/friends-nearby offer.expires_at) +
SPLIT REMINDER NUDGE (/scan-to-pay/splits/mine invite_urls + shares).
"""
import os
import re
from datetime import datetime, timezone
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# -- DEAL COUNTDOWN --
def test_friends_nearby_has_karak_offer_future_expiry(sess):
    r = sess.get(f"{BASE_URL}/api/social/friends-nearby", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    karak = [i for i in items if i.get("business_id") == "biz_demo_karak"]
    assert karak, f"no biz_demo_karak item in {len(items)} items"
    sample = karak[0]
    offer = sample.get("offer")
    assert offer, "no offer attached to Karak nearby card"
    assert offer.get("offer_id") == "ofr_qa_onetime_demo"
    label = (offer.get("label") or offer.get("title") or "").lower()
    assert "50" in label and "off" in label, f"bad label: {label}"
    exp = offer.get("expires_at")
    assert exp, "offer.expires_at missing"
    exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta_h = (exp_dt - now).total_seconds() / 3600
    assert 0 < delta_h < 24, f"expiry not in near future: {delta_h}h"
    print(f"OK: Karak offer expires in {delta_h:.2f}h ({exp})")


def test_friends_nearby_filters_expired_offers(sess):
    """Endpoint filters expires_at>now at the DB level — items we see all have
    future expiries or null."""
    r = sess.get(f"{BASE_URL}/api/social/friends-nearby", timeout=15)
    items = r.json().get("items") or []
    now = datetime.now(timezone.utc)
    for it in items:
        o = it.get("offer")
        if not o or not o.get("expires_at"):
            continue
        exp = datetime.fromisoformat(o["expires_at"].replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        assert exp > now, f"expired offer leaked: {it['business_id']} {o['expires_at']}"


# -- SPLIT REMINDER NUDGE --
def test_splits_mine_partial_has_invite_urls_and_pending_share(sess):
    r = sess.get(f"{BASE_URL}/api/scan-to-pay/splits/mine", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or r.json().get("splits") or []
    partial = [s for s in items if s.get("split_id") == "bsplit_demo_whospaid"]
    assert partial, "bsplit_demo_whospaid not found in /splits/mine"
    sp = partial[0]
    assert sp.get("status") in ("partial", "partially_paid"), f"status={sp.get('status')}"
    shares = sp.get("shares") or []
    assert len(shares) == 2, f"expected 2 shares, got {len(shares)}"
    unpaid = [sh for sh in shares if sh.get("status") != "paid"
              and (sh.get("display_name") or "").lower() != "you"]
    assert unpaid, "no unpaid non-'you' share"
    assert any((sh.get("display_name") or "").lower() == "alex" for sh in unpaid), \
        "Alex not in unpaid shares"
    invite_urls = sp.get("invite_urls") or {}
    for sh in unpaid:
        sid = sh.get("share_id")
        assert sid in invite_urls, f"invite_urls missing share_id {sid}"
        url = invite_urls[sid]
        assert isinstance(url, str) and url.startswith(("http://", "https://")), \
            f"bad invite url for {sid}: {url}"
    merchant = sp.get("merchant") or {}
    assert "Karak" in (merchant.get("business_name") or ""), \
        f"merchant name regression: {merchant}"
    assert (sp.get("currency") or "").lower() == "aed", f"currency={sp.get('currency')}"
    print(f"OK: partial split has {len(unpaid)} unpaid share(s) with invite URLs")


def test_splits_mine_completed_has_no_pending_shares(sess):
    """Regression — endpoint response shape OK for other statuses; mobile UI
    hides the Remind button when no unpaid non-you share exists."""
    r = sess.get(f"{BASE_URL}/api/scan-to-pay/splits/mine", timeout=15)
    items = r.json().get("items") or r.json().get("splits") or []
    for sp in items:
        if sp.get("status") in ("completed", "paid"):
            unpaid_non_you = [sh for sh in (sp.get("shares") or [])
                              if sh.get("status") != "paid"
                              and (sh.get("display_name") or "").lower() != "you"]
            assert not unpaid_non_you, \
                f"completed split {sp.get('split_id')} has unpaid shares: {unpaid_non_you}"


# -- Regression — nearby offer route target --
def test_nearby_offer_routes_to_offer_id(sess):
    r = sess.get(f"{BASE_URL}/api/social/friends-nearby", timeout=15)
    items = r.json().get("items") or []
    karak = next((i for i in items if i.get("business_id") == "biz_demo_karak"), None)
    assert karak and karak.get("offer", {}).get("offer_id") == "ofr_qa_onetime_demo"
