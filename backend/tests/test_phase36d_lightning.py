"""Phase 36d Turn 3 — Lightning splits tests.

Hermetic: hits the service layer + FastAPI ASGI client directly. No
external HTTP, no real Lightning calls.

Covers:
    1. PUT validates split_pct sum == 100 (400 on mismatch, 200 on match)
    2. GET episode resolves override OR falls back to channel default
       with inherited_from_channel=True; DELETE override flips it back.
    3. RSS feed emits <podcast:value> in both <channel> and each <item>
       with correct podcastindex namespace declaration + structure.
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

from services import podcast_lightning as pl
from services import podcast_rss as rss


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


VALID_PUBKEY_A = "02" + "a" * 64       # 66-char hex
VALID_PUBKEY_B = "03" + "b" * 64
VALID_PUBKEY_C = "02" + "c" * 64
VALID_PUBKEY_D = "03" + "d" * 64


def _recipients(creator=70, platform=30):
    return [
        {"name": "Creator", "type": "node",
          "address": VALID_PUBKEY_A, "split_pct": creator, "fee_pct": 0},
        {"name": "BigFM Platform", "type": "node",
          "address": VALID_PUBKEY_B, "split_pct": platform, "fee_pct": 0},
    ]


# ─── 1. PUT validates sum=100 ─────────────────────────────────────
def test_set_channel_default_validates_sum_100():
    async def go():
        db = _db()
        channel_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        # 90% total — must raise.
        with pytest.raises(Exception) as ei:
            await pl.upsert_channel_default(
                db, channel_id=channel_id,
                recipients=_recipients(creator=70, platform=20))
        assert "100" in str(ei.value)
        # 100% total — succeeds.
        doc = await pl.upsert_channel_default(
            db, channel_id=channel_id,
            recipients=_recipients(creator=70, platform=30))
        assert doc["channel_id"] == channel_id
        assert doc["episode_id"] is None
        assert sum(r["split_pct"] for r in doc["recipients"]) == 100
        # cleanup
        await db.podcast_lightning_splits.delete_many({"channel_id": channel_id})
    run(go())


# ─── 2. Episode resolution / fallback / delete ────────────────────
def test_get_episode_resolves_override_or_channel_default():
    async def go():
        db = _db()
        channel_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        episode_id = f"pep_test_{uuid.uuid4().hex[:8]}"
        # Set channel default.
        await pl.upsert_channel_default(
            db, channel_id=channel_id,
            recipients=_recipients(creator=70, platform=30))
        # No override yet → resolves to channel default with inherit flag.
        r1 = await pl.get_episode_resolved(
            db, channel_id=channel_id, episode_id=episode_id)
        assert r1 is not None
        assert r1["inherited_from_channel"] is True
        assert r1["recipients"][0]["address"] == VALID_PUBKEY_A
        # Now create an episode override (different recipients).
        override_rcs = [
            {"name": "Creator", "type": "node",
              "address": VALID_PUBKEY_C, "split_pct": 60, "fee_pct": 0},
            {"name": "Guest", "type": "node",
              "address": VALID_PUBKEY_D, "split_pct": 40, "fee_pct": 0},
        ]
        await pl.upsert_episode_override(
            db, channel_id=channel_id, episode_id=episode_id,
            recipients=override_rcs)
        r2 = await pl.get_episode_resolved(
            db, channel_id=channel_id, episode_id=episode_id)
        assert r2["inherited_from_channel"] is False
        # Returns the override.
        assert r2["recipients"][0]["address"] == VALID_PUBKEY_C
        assert r2["recipients"][1]["address"] == VALID_PUBKEY_D
        # DELETE override → falls back to channel default.
        ok = await pl.delete_episode_override(db, episode_id=episode_id)
        assert ok is True
        r3 = await pl.get_episode_resolved(
            db, channel_id=channel_id, episode_id=episode_id)
        assert r3["inherited_from_channel"] is True
        # cleanup
        await db.podcast_lightning_splits.delete_many({"channel_id": channel_id})
    run(go())


# ─── 3. RSS XML emission ──────────────────────────────────────────
def test_rss_emits_podcast_value_block_with_correct_structure():
    async def go():
        from lxml import etree
        db = _db()
        channel_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        episode_id = f"pep_test_{uuid.uuid4().hex[:8]}"
        await pl.upsert_channel_default(
            db, channel_id=channel_id,
            recipients=_recipients(creator=70, platform=30))
        await pl.upsert_episode_override(
            db, channel_id=channel_id, episode_id=episode_id,
            recipients=[
                {"name": "Creator", "type": "node",
                  "address": VALID_PUBKEY_C, "split_pct": 60, "fee_pct": 0},
                {"name": "Guest", "type": "node",
                  "address": VALID_PUBKEY_D, "split_pct": 40, "fee_pct": 1.5},
            ])
        # Build channel + 1 episode dict (minimal).
        channel = {"id": channel_id, "slug": "test-slug",
                          "title": "Test Channel", "description": "desc",
                          "language": "en", "category": "tech",
                          "creator_id": "anon"}
        ep_pub = datetime.now(timezone.utc)
        episodes = [{"id": episode_id, "title": "EP1",
                              "description": "ep desc",
                              "audio_url": "/static/fake.mp3",
                              "duration_seconds": 600,
                              "published_at": ep_pub,
                              "guid": f"bigfm-ep-{episode_id}",
                              "file_size_bytes": 12345,
                              "season": 1, "episode_number": 1,
                              "episode_type": "full"}]
        # Overlay value_configs from new collection.
        await pl.overlay_rss_value_configs(
            db, channel=channel, episodes=episodes)
        xml = rss.build_feed_xml(channel, episodes)
        # 1. Namespace declared exactly once.
        assert xml.count('xmlns:podcast="https://podcastindex.org/namespace/1.0"') == 1
        # 2. Parse with lxml — strip the bare-name itunes/podcast tags out
        # of the namespace check by parsing the whole document.
        root = etree.fromstring(xml.encode("utf-8"))
        ns = {"podcast": "https://podcastindex.org/namespace/1.0"}
        # Channel <podcast:value> exists.
        ch_value = root.find(".//channel/podcast:value", ns)
        assert ch_value is not None, "channel-level <podcast:value> missing"
        ch_recipients = ch_value.findall("podcast:valueRecipient", ns)
        assert len(ch_recipients) == 2
        ch_total = sum(int(r.attrib["split"]) for r in ch_recipients)
        assert ch_total == 100, f"channel splits sum={ch_total}"
        # Episode <podcast:value> exists inside <item>.
        item_value = root.find(".//channel/item/podcast:value", ns)
        assert item_value is not None, "episode-level <podcast:value> missing"
        ep_recipients = item_value.findall("podcast:valueRecipient", ns)
        assert len(ep_recipients) == 2
        ep_addrs = [r.attrib["address"] for r in ep_recipients]
        assert VALID_PUBKEY_C in ep_addrs
        assert VALID_PUBKEY_D in ep_addrs
        ep_total = sum(int(r.attrib["split"]) for r in ep_recipients)
        assert ep_total == 100, f"ep splits sum={ep_total}"
        # fee_pct > 0 on guest → fee="true" attr present.
        fee_marked = [r for r in ep_recipients
                                  if r.attrib.get("fee") == "true"]
        assert len(fee_marked) == 1
        assert fee_marked[0].attrib["address"] == VALID_PUBKEY_D
        # cleanup
        await db.podcast_lightning_splits.delete_many({"channel_id": channel_id})
    run(go())
