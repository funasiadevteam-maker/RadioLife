"""Phase PORTAL.0 — Backend regression for GET /api/portal/context.

Covers:
- Unauthenticated → 401
- Admin (admin@bigfm.dubai) → includes an 'admin' workspace (/admin)
- Merchant owner (demo@bigfm.dubai) → owns >=1 merchant workspaces with role owner,
    needs_workspace_choice true when >1, merchant route /merchant/status?merchant_id=...
- Consumer (freeuser@bigfm.dubai) → workspaces empty, recommended_route '/'
- Design query string does NOT affect access (server-side design-agnostic)
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
    "https://mobile-games-v2.preview.emergentagent.com"

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
DEMO = ("demo@bigfm.dubai", "DemoPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
                          json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return s


# ── Unauthenticated ──────────────────────────────────────────────────
def test_portal_context_unauth_401():
    r = requests.get(f"{BASE_URL}/api/portal/context", timeout=20)
    assert r.status_code == 401


# ── Admin ────────────────────────────────────────────────────────────
def test_portal_context_admin_has_admin_workspace():
    s = _login(*ADMIN)
    r = s.get(f"{BASE_URL}/api/portal/context", timeout=20)
    assert r.status_code == 200
    d = r.json()

    assert d.get("platform_admin") is True
    ws = d.get("workspaces") or []
    admin_ws = [w for w in ws if w.get("type") == "admin"]
    assert admin_ws, f"admin workspace missing: {ws}"
    aw = admin_ws[0]
    assert aw["role"] == "admin"
    assert aw["route"] == "/admin"
    assert isinstance(aw.get("permissions"), list) and len(aw["permissions"]) > 0
    assert d.get("recommended_route") == "/admin"


# ── Merchant owner (demo) ────────────────────────────────────────────
def test_portal_context_merchant_owner_needs_choice():
    s = _login(*DEMO)
    r = s.get(f"{BASE_URL}/api/portal/context", timeout=20)
    assert r.status_code == 200
    d = r.json()

    assert d.get("platform_admin") is False
    ws = d.get("workspaces") or []
    owned = [w for w in ws
                    if w.get("type") == "merchant" and w.get("role") == "owner"]
    assert len(owned) >= 1, f"expected owned merchants, got: {ws}"
    # Every owner workspace should carry the design-independent status route
    for w in owned:
        assert w.get("route", "").startswith("/merchant/"), w
        # For draft/verification_pending → /merchant/status?merchant_id=
        if w.get("merchant_status") in {
                "draft", "stripe_onboarding_pending", "verification_pending",
                "submitted", "rejected"}:
            assert "/merchant/status?merchant_id=" in w["route"]
            assert w["id"] in w["route"]
        assert isinstance(w.get("permissions"), list) and len(w["permissions"]) > 0

    # If demo owns 2 merchants (spec), needs_workspace_choice must be True.
    if len(ws) > 1:
        assert d.get("needs_workspace_choice") is True
    assert d.get("recommended_workspace_id") in {w["id"] for w in ws}


# ── Consumer / free user ─────────────────────────────────────────────
def test_portal_context_consumer_empty():
    s = _login(*FREE)
    r = s.get(f"{BASE_URL}/api/portal/context", timeout=20)
    assert r.status_code == 200
    d = r.json()

    assert d.get("platform_admin") is False
    assert d.get("workspaces") == []
    assert d.get("workspace_count") == 0
    assert d.get("recommended_route") == "/"
    assert d.get("needs_workspace_choice") is False
    assert d.get("preview_access") is False


# ── Design-agnostic (security) ───────────────────────────────────────
@pytest.mark.parametrize("design",
                                              ["legacy", "classic_b", "radiolife", "new_look_v2"])
def test_portal_context_ignores_design_qs_for_consumer(design):
    s = _login(*FREE)
    r = s.get(f"{BASE_URL}/api/portal/context?design={design}", timeout=20)
    assert r.status_code == 200
    d = r.json()
    # A consumer must NEVER gain access by changing design variant.
    assert d.get("workspaces") == []
    assert d.get("platform_admin") is False
    assert d.get("recommended_route") == "/"


@pytest.mark.parametrize("design",
                                              ["legacy", "classic_b", "radiolife", "new_look_v2"])
def test_portal_context_ignores_design_qs_for_admin(design):
    s = _login(*ADMIN)
    r = s.get(f"{BASE_URL}/api/portal/context?design={design}", timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d.get("platform_admin") is True
    assert any(w.get("type") == "admin" for w in (d.get("workspaces") or []))
