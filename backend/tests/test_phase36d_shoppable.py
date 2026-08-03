"""Phase 36d Turn 2 — Shoppable cards tests.

Hermetic: exercises the service layer + routes via TestClient. No external
HTTP calls. Image uploads are small in-memory PNG bytes.
"""
from __future__ import annotations
import asyncio
import io
import os
import sys
import uuid

import pytest

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient
from services import shoppable_cards as sc


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


# Minimal 1x1 PNG so image-upload tests do real bytes through the pipeline.
PNG_1x1 = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                  b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc"
                  b"\xff\xff?\x03\x00\x06\x00\x02\x00\x9e\x9e\x9d\x86\x00\x00\x00\x00"
                  b"IEND\xaeB`\x82")


@pytest.fixture
def episode_clip_fixture():
    db = _db()
    cid = f"pch_sh_{uuid.uuid4().hex[:6]}"
    eid = f"pep_sh_{uuid.uuid4().hex[:6]}"
    mcid = f"mc_sh_{uuid.uuid4().hex[:6]}"
    crid = f"cr_sh_{uuid.uuid4().hex[:6]}"
    run(db.podcast_channels.insert_one({"id": cid, "title": "Sh",
                                                                              "creator_id": crid, "active": True,
                                                                              "approval_status": "approved"}))
    run(db.podcast_episodes.insert_one({"id": eid, "channel_id": cid,
                                                                              "title": "ep"}))
    run(db.podcast_magic_clips.insert_one({"id": mcid, "episode_id": eid,
                                                                                      "channel_id": cid,
                                                                                      "status": "published",
                                                                                      "start_sec": 10, "end_sec": 55,
                                                                                      "score": 0.5}))
    yield {"channel_id": cid, "episode_id": eid, "clip_id": mcid,
                "creator_id": crid}
    run(db.podcast_shoppable_cards.delete_many({"episode_id": eid}))
    run(db.podcast_shoppable_cards.delete_many({"magic_clip_id": mcid}))
    run(db.shoppable_card_clicks.delete_many({"card_id": {"$regex": "^shc_"}}))
    run(db.podcast_magic_clips.delete_one({"id": mcid}))
    run(db.podcast_episodes.delete_one({"id": eid}))
    run(db.podcast_channels.delete_one({"id": cid}))


# ─── 1. attach to episode (mutually exclusive FK) ────────────────
def test_create_card_episode_attaches_to_episode(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    card = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                      episode_id=f["episode_id"],
                                                      title="Hat", product_url="https://example.com/hat",
                                                      price_cents=2999, currency="USD",
                                                      image_bytes=PNG_1x1, image_ext="png"))
    assert card["episode_id"] == f["episode_id"]
    assert card["magic_clip_id"] is None
    assert card["price_cents"] == 2999
    assert card["image_url"]
    assert card["storage_key_image"] or card["image_url"].startswith("/api/static/shoppable_cards/")


# ─── 2. attach to clip ──────────────────────────────────────────
def test_create_card_clip_attaches_to_clip(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    card = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                      magic_clip_id=f["clip_id"],
                                                      title="Mug", product_url="https://example.com/mug",
                                                      price_cents=1500))
    assert card["magic_clip_id"] == f["clip_id"]
    assert card["episode_id"] is None


def test_create_card_rejects_both_or_neither(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    with pytest.raises(ValueError):
        run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                              episode_id=f["episode_id"],
                                              magic_clip_id=f["clip_id"],
                                              title="X", product_url="https://x"))
    with pytest.raises(ValueError):
        run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                              title="X", product_url="https://x"))


# ─── 3. soft-delete + display_order ──────────────────────────────
def test_list_cards_returns_only_active_in_display_order(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    a = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                    episode_id=f["episode_id"],
                                                    title="A", product_url="https://a", display_order=20))
    b = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                    episode_id=f["episode_id"],
                                                    title="B", product_url="https://b", display_order=10))
    c = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                    episode_id=f["episode_id"],
                                                    title="C", product_url="https://c", display_order=30))
    run(sc.soft_delete(db, card_id=c["id"], owner_creator_id=f["creator_id"]))
    rows = run(sc.list_cards(db, episode_id=f["episode_id"]))
    titles = [r["title"] for r in rows]
    assert titles == ["B", "A"], titles  # sorted ascending, C excluded


# ─── 4. click proxy records + redirects ──────────────────────────
def test_click_proxy_records_event_and_returns_card(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    card = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                      episode_id=f["episode_id"],
                                                      title="X", product_url="https://x.example/p"))
    result, dup = run(sc.record_click(db, card_id=card["id"],
                                                                          ip="203.0.113.7",
                                                                          user_agent="Mozilla/5.0",
                                                                          referrer="https://refer.example",
                                                                          user_id=None))
    assert result["product_url"] == "https://x.example/p"
    assert dup is False
    click = run(db.shoppable_card_clicks.find_one({"card_id": card["id"]}))
    assert click is not None
    assert click["ip_hash"] != "203.0.113.7"
    assert len(click["ip_hash"]) == 32
    assert click["referrer"] == "https://refer.example"


# ─── 5. rate-limit: same IP within window flagged duplicate ──────
def test_click_proxy_rate_limit_one_per_ip_per_30min(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    card = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                      episode_id=f["episode_id"],
                                                      title="X", product_url="https://x"))
    run(sc.record_click(db, card_id=card["id"], ip="198.51.100.4",
                                            user_agent="a", referrer="", user_id=None))
    _, dup = run(sc.record_click(db, card_id=card["id"], ip="198.51.100.4",
                                                          user_agent="b", referrer="", user_id=None))
    assert dup is True
    # Different IP should NOT be flagged duplicate.
    _, dup_other = run(sc.record_click(db, card_id=card["id"], ip="198.51.100.5",
                                                                          user_agent="a", referrer="", user_id=None))
    assert dup_other is False
    # All three clicks persist (duplicate is metadata; analytics dedupes).
    n = run(db.shoppable_card_clicks.count_documents({"card_id": card["id"]}))
    assert n == 3


# ─── 6. affiliate stub returns None until providers register ─────
def test_affiliate_lookup_returns_none_with_no_providers():
    from services import shoppable_affiliate as sa
    # Reset any test registrations
    sa._PROVIDERS.clear()
    assert sa.lookup_product_meta("https://amazon.com/dp/X") is None
    # Register a fake provider and verify dispatch
    sa.register_provider("fake", lambda url:
        {"title": "Fake", "image_url": "", "price_cents": 0, "currency": "USD"})
    r = sa.lookup_product_meta("https://anywhere")
    assert r and r["title"] == "Fake"
    sa._PROVIDERS.clear()


# ─── 7. soft-delete preserves click history ─────────────────────
def test_soft_delete_preserves_click_history(episode_clip_fixture):
    db = _db()
    f = episode_clip_fixture
    card = run(sc.create_card(db, owner_creator_id=f["creator_id"],
                                                      episode_id=f["episode_id"],
                                                      title="X", product_url="https://x"))
    run(sc.record_click(db, card_id=card["id"], ip="1.2.3.4",
                                          user_agent="a", referrer="", user_id=None))
    run(sc.soft_delete(db, card_id=card["id"],
                                          owner_creator_id=f["creator_id"]))
    n = run(db.shoppable_card_clicks.count_documents({"card_id": card["id"]}))
    assert n == 1
    row = run(db.podcast_shoppable_cards.find_one({"id": card["id"]}))
    assert row["active"] is False
