"""Milestone 1 — Social wall P0 bugs: own-post visibility + persistent engagement.

Backend-only tests. Exercises:
  - POST /api/social/moments → own post visible on top of GET /api/social/feed-v2
    (both mode=following and mode=for_you for a public post), is_mine=True,
    actor.kind='self'.
  - POST /api/social/wall/like / save / share toggle + persist across refetch.
  - POST /api/social/media/upload returns a retrievable URL.
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
EMAIL = "demo@bigfm.dubai"
PASSWORD = "DemoPass123!"


@pytest.fixture(scope="module")
def session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    return s


def _find_in_feed(items: list[dict], moment_id: str) -> dict | None:
    cid = f"MOMENT:{moment_id}"
    for it in items:
        if it.get("id") == cid:
            return it
    return None


def test_own_public_moment_appears_in_following_and_for_you(session):
    # Create a public moment so both Following AND For You can show it.
    caption = f"TEST_milestone1 own-post {int(time.time())}"
    r = session.post(f"{BASE_URL}/api/social/moments",
                     json={"caption": caption, "visibility": "public"}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    mid = r.json()["moment_id"]
    assert mid

    # FOLLOWING: own post must be in the feed and marked as self.
    r = session.get(f"{BASE_URL}/api/social/feed-v2",
                    params={"mode": "following", "limit": 40}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    items = r.json().get("items") or []
    own = _find_in_feed(items, mid)
    assert own is not None, "Own moment missing from Following feed (P0 regression)"
    assert own.get("is_mine") is True
    assert (own.get("actor") or {}).get("kind") == "self"
    # Core P0 fix: own post is INCLUDED (not excluded), with is_mine=True /
    # actor.kind='self'. Also assert the first MOMENT card belongs to the
    # viewer (own-posts outrank discovery). Exact ordering between multiple
    # own-posts isn't contractual.
    pos = next((i for i, c in enumerate(items) if c.get("id") == f"MOMENT:{mid}"), -1)
    assert pos >= 0, f"Own post missing from Following feed (position {pos})"
    first_moment = next((c for c in items if c.get("type") == "MOMENT"), None)
    assert first_moment is not None, "No MOMENT cards present on Following feed"
    assert first_moment.get("is_mine") is True, \
        f"First MOMENT isn't own: {first_moment.get('id')}"
    assert (first_moment.get("actor") or {}).get("kind") == "self"

    # FOR_YOU: own public post should also appear.
    r = session.get(f"{BASE_URL}/api/social/feed-v2",
                    params={"mode": "for_you", "limit": 40}, timeout=20)
    assert r.status_code == 200
    items2 = r.json().get("items") or []
    assert _find_in_feed(items2, mid) is not None, \
        "Own public post missing from For You"


def test_wall_like_save_share_persist(session):
    # Create a moment to engage with.
    r = session.post(f"{BASE_URL}/api/social/moments",
                     json={"caption": "TEST_engagement persistence",
                           "visibility": "public"}, timeout=20)
    assert r.status_code == 200
    mid = r.json()["moment_id"]
    item_id = f"MOMENT:{mid}"

    # LIKE: toggle on, persist via feed refetch meta.liked_by_me=True
    r = session.post(f"{BASE_URL}/api/social/wall/like",
                     json={"item_id": item_id}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True and body.get("liked") is True
    assert body.get("like_count", 0) >= 1

    # SAVE
    r = session.post(f"{BASE_URL}/api/social/wall/save",
                     json={"item_id": item_id}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("saved") is True

    # SHARE
    r = session.post(f"{BASE_URL}/api/social/wall/share",
                     json={"item_id": item_id}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    sj = r.json()
    assert sj.get("shared") is True
    assert int(sj.get("share_count") or 0) >= 1

    # Re-fetch feed → meta.liked_by_me, saved_by_me, share_count persist
    r = session.get(f"{BASE_URL}/api/social/feed-v2",
                    params={"mode": "following", "limit": 40}, timeout=20)
    assert r.status_code == 200
    items = r.json().get("items") or []
    own = _find_in_feed(items, mid)
    assert own is not None, "created moment missing after engagement"
    meta = own.get("meta") or {}
    assert meta.get("liked_by_me") is True, "liked_by_me did not persist"
    assert meta.get("saved_by_me") is True, "saved_by_me did not persist"
    assert int(meta.get("like_count") or 0) >= 1
    # share_count may live on either card.meta or moment doc; assert >=1
    assert int(meta.get("share_count") or 0) >= 1, \
        f"share_count did not persist: meta={meta}"

    # Saved list should include the item
    r = session.get(f"{BASE_URL}/api/social/wall/saved", timeout=20)
    assert r.status_code == 200
    saved_ids = {s.get("item_id") for s in (r.json().get("items") or [])}
    assert item_id in saved_ids


def test_media_upload_returns_retrievable_url(session):
    # Tiny valid PNG header (1x1).
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf"
        b"\xc0\x00\x00\x00\x03\x00\x01\xa7z\xdb\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("tiny.png", io.BytesIO(png), "image/png")}
    r = session.post(f"{BASE_URL}/api/social/media/upload", files=files, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("media_type") == "photo"
    url = body.get("url")
    assert url and body.get("key")

    # URL retrieval
    r2 = session.get(url, timeout=20)
    assert r2.status_code in (200, 206), f"media url not retrievable: {r2.status_code}"
    assert len(r2.content) > 0
